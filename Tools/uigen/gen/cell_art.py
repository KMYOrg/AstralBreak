"""화면 원본 아트 속 칸 자리 — 시안이 그린 칸을 그 칸의 승인한 그림으로 바꾼다 (설계 §11 'Phase 3 설계' ②, Phase 3-3).

칸은 자기 run 에서 사람이 승인한 그림이 정답이다. 화면 시안은 같은 칸을 여러 번 그리는데 AI 가 그린 반복은 서로 같은 픽셀이 아니다
[실측 hub_ready_sheet — 파티 줄 2 ~ 4 는 줄 1 과 국소 ΔE00 최대 14 ~ 20, 세로 1 ~ 2 px 어긋남]. 시안의 픽셀을 그대로 정답으로 두면 첫 줄 밖은 늘 '틀린 그림'이 된다.
그래서 normalize 가
  ① 요청한 자리(at — 칸의 왼쪽 위, 크기는 칸 캔버스)에서 시안이 그린 것과 칸 그림의 어긋남을 재고(±SHIFT_R 정수 px, 회색 바탕) SHIFT_MAX 를 넘으면 멈춘다
     (자리를 잘못 적었다 — 진단은 칸 그림끼리 견주므로 여기서 잡는다),
  ② 그 둘레(CLEAR_PAD)까지 시안이 그린 것을 지우고 칸 그림을 얹는다. 다른 요소와 이어진 그림이면 건드리지 않고, 칸 상자와 겹치면 멈춘다.
"""
from __future__ import annotations

import numpy as np

CLEAR_PAD = 12            # 칸 상자 둘레 이만큼(px)까지는 그 칸의 그림(삐져나온 끝 · 옅은 얼룩)
SHIFT_R = 8               # 어긋남을 찾는 범위(px)
SHIFT_MAX = 3             # 이보다 어긋나면 자리를 잘못 적은 것
LINK_ALPHA = 0.1          # 이보다 진한 픽셀이 이어지면 한 그림
GRAY = 128.0


class CellArtError(ValueError):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def _over_gray(col, a):
    return col * a[..., None] + GRAY * (1 - a[..., None])


def measure(color, alpha, picture, at) -> dict:
    """시안(곧은 색 · 알파)의 at 자리 ↔ 칸 그림(곧은 RGBA) — {shift, mean_diff, at_diff}. shift = 시안이 그린 자리 − 요청한 자리."""
    H, W = alpha.shape
    h, w = picture.shape[:2]
    x, y = int(at[0]), int(at[1])
    want = _over_gray(picture[..., :3], picture[..., 3] / 255.0)
    best, here = None, None
    for dy in range(-SHIFT_R, SHIFT_R + 1):
        for dx in range(-SHIFT_R, SHIFT_R + 1):
            x0, y0 = x + dx, y + dy
            if x0 < 0 or y0 < 0 or x0 + w > W or y0 + h > H:
                continue
            got = _over_gray(color[y0:y0 + h, x0:x0 + w], alpha[y0:y0 + h, x0:x0 + w])
            d = float(np.abs(got - want).mean())
            if dx == 0 and dy == 0:
                here = d
            if best is None or d < best[0] - 1e-9 or (abs(d - best[0]) <= 1e-9 and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2])):
                best = (d, dx, dy)
    if best is None:
        raise CellArtError("CELL_OUTSIDE", f"the cell at {[x, y]} ({w}x{h}) does not fit the {W}x{H} canvas")
    return {"shift": [best[1], best[2]], "mean_diff": round(best[0], 2), "at_diff": None if here is None else round(here, 2)}


def zones(alpha, boxes: list[list[int]]) -> list[np.ndarray]:
    """칸마다 지울 자리(캔버스 bool) — 상자 + 둘레 중 다른 요소와 이어진 픽셀이 아닌 것. 다른 요소가 칸 상자에 걸치면 CellArtError."""
    import cv2
    H, W = alpha.shape
    n, lab = cv2.connectedComponents((alpha > LINK_ALPHA).astype(np.uint8), connectivity=8)
    total = np.bincount(lab.ravel(), minlength=n)
    out = []
    for x, y, w, h in boxes:
        z = np.zeros((H, W), bool)
        z[max(0, y - CLEAR_PAD):min(H, y + h + CLEAR_PAD), max(0, x - CLEAR_PAD):min(W, x + w + CLEAR_PAD)] = True
        inner = np.zeros((H, W), bool)
        inner[y:y + h, x:x + w] = True
        inside = np.bincount(lab[z], minlength=n)
        foreign = [i for i in range(1, n) if inside[i] and inside[i] < 0.5 * total[i]]
        for i in foreign:
            m = lab == i
            hit = int((m & inner).sum())
            if hit > 8:
                ys, xs = np.nonzero(m)
                raise CellArtError("CELL_ART_OVERLAP", f"the art draws another element over the cell box {[x, y, w, h]} ({hit} px of a drawing at "
                                   f"{[int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]})", box=[x, y, w, h])
            z &= ~m
        out.append(z)
    return out


def apply(color, alpha, boxes: list[list[int]], pictures: list[np.ndarray], zs: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """지울 자리를 비우고 칸 그림을 얹은 (곧은 색, 알파) — 사본."""
    col, a = np.asarray(color, float).copy(), np.asarray(alpha, float).copy()
    for z in zs:
        a[z] = 0.0
        col[z] = 0.0
    for (x, y, w, h), pic in zip(boxes, pictures):
        pa = pic[..., 3] / 255.0
        sa = a[y:y + h, x:x + w]
        over = pa + sa * (1 - pa)
        pm = pic[..., :3] * pa[..., None] + col[y:y + h, x:x + w] * (sa * (1 - pa))[..., None]
        col[y:y + h, x:x + w] = np.where(over[..., None] > 1e-4, pm / np.maximum(over, 1e-4)[..., None], 0.0)
        a[y:y + h, x:x + w] = over
    return col, a


class Paste:
    """한 화면의 칸 붙이기 — 원본 아트에서 자리를 재고(prepare), 같은 자리를 아트 · 글자 참고판에 똑같이 얹는다(__call__)."""

    def __init__(self, cells: list[dict], pictures: dict[str, np.ndarray]):
        """cells = [{widget, cell, at, size}], pictures = 위젯 id → 칸 그림(곧은 RGBA float, 크기 = size)."""
        self.cells = cells
        self.boxes = [[int(c["at"][0]), int(c["at"][1]), int(c["size"][0]), int(c["size"][1])] for c in cells]
        self.pictures = [pictures[c["widget"]] for c in cells]
        self.zs: list[np.ndarray] | None = None
        self.record: list[dict] = []

    def prepare(self, color, alpha) -> None:
        for c, box, pic in zip(self.cells, self.boxes, self.pictures):
            if list(pic.shape[:2]) != [box[3], box[2]]:
                raise CellArtError("CELL_SIZE", f"cell '{c['widget']}' picture is {pic.shape[1]}x{pic.shape[0]}, its canvas is {box[2]}x{box[3]}", widget=c["widget"])
            m = measure(color, alpha, pic, c["at"])
            self.record.append({"widget": c["widget"], "cell": c["cell"], "box": box, **m})
            if max(abs(v) for v in m["shift"]) > SHIFT_MAX:
                raise CellArtError("CELL_PLACE", f"cell '{c['widget']}' is asked at {list(c['at'])} but the art draws it {m['shift']} px away — fix 'at'", widget=c["widget"],
                                   **m)
        self.zs = zones(alpha, self.boxes)
        for r, z in zip(self.record, self.zs):
            r["cleared_px"] = int((z & (alpha > 0.02)).sum())

    def __call__(self, color, alpha) -> tuple[np.ndarray, np.ndarray]:
        if self.zs is None:
            self.prepare(color, alpha)
        return apply(color, alpha, self.boxes, self.pictures, self.zs)
