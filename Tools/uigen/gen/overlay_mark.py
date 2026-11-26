"""바탕 위에 그려진 표시 — 켜고 끄는 그림(방장 초승달)이 늘 보이는 띠 위에 있을 때 둘로 나눈다 (설계 §11 'Phase 3-3 결과').

지금까지 접히는 그림은 투명 위에 있었다 — 상자째 오려 내고 판에서 그 상자를 빼면 됐다. 불투명한 띠 위의 표시를 그렇게 오리면 껐을 때 띠에 네모 구멍이 난다.
표시 밑의 띠는 시안에 없는 픽셀이라 지어내야 하지만, 표시는 가는 선이고 띠는 매끈하므로 **표시 획만** 둘레에서 메우면 된다:
  ① 표시 획 = 상자 안에서 '둘레에서 메운 띠'와 크게 다른 픽셀 덩어리(+ 안티앨리어싱 2 px)
  ② 바탕 = 획 자리만 둘레 경계값으로 메운 아트 — 획 밖은 시안 그대로
  ③ 표시 그림 = 바탕 위에 얹으면 시안이 되는 색 · 알파 — 덮는 정도는 시안의 알파에서(검정 · 회색 어느 바탕에서도 맞게), 그 색이 0 ~ 255 를 넘으면 들 만큼만 더 덮는다.
     띠보다 어두운 가장자리(그림을 키울 때 생긴 테)는 그리지 않는다 — 어두운 띠 위에서는 안 보이고 밝은 바탕에서는 검은 점이 된다
analyze(자리 — fit_box) · layer(마스크 · 바탕 · 그림) · 상태 검사(껐을 때 흔적 · 구멍)가 같은 함수를 쓴다.
"""
from __future__ import annotations

import numpy as np

PAD = 10                  # 상자 둘레 — 바탕을 재는 고리(px)
SEED_DIFF = 24.0          # 획 씨앗 — 메운 띠와 채널 최대 차(검정 바탕)
EDGE_DIFF = 6.0           # 획 가장자리 — 씨앗에서 EDGE_PX 안에서 이만큼 다르면 획
EDGE_PX = 3
GROW = 1                  # 마지막으로 넓히는 px(옅은 가장자리)
MARGIN = 2                # 위젯 상자 = 획 상자 + 이만큼
REACH = 12                # LLM 상자가 모자랄 수 있는 만큼(px)
MIN_PX = 24
BAND_WY = 0.2             # 메움의 세로 무게 — 띠는 가로로 이어진다(아래 강철 선 · 세로 그라데이션을 가로질러 섞지 않게)


class MarkError(ValueError):
    pass


def window(box, shape) -> tuple[int, int, int, int]:
    H, W = shape
    return (max(0, int(np.floor(float(box[0]))) - PAD), max(0, int(np.floor(float(box[1]))) - PAD),
            min(W, int(np.ceil(float(box[0]) + float(box[2]))) + PAD), min(H, int(np.ceil(float(box[1]) + float(box[3]))) + PAD))


def fill(color, alpha, hole, win) -> tuple[np.ndarray, np.ndarray]:
    """구멍(캔버스 bool)을 둘레에서 메운 (곧은 색, 알파) — 창(win) 조각. 구멍 밖은 그대로."""
    from stages.refine import _harmonic_fill
    x0, y0, x1, y1 = win
    c, a, h = color[y0:y1, x0:x1], alpha[y0:y1, x0:x1], hole[y0:y1, x0:x1]
    pm = np.dstack([c * a[..., None], a[..., None] * 255.0])
    f = _harmonic_fill(pm, h, wy=BAND_WY)
    fa = np.clip(f[..., 3] / 255.0, 0, 1)
    fc = np.where(fa[..., None] > 1e-4, f[..., :3] / np.maximum(fa, 1e-4)[..., None], 0.0)
    return np.where(h[..., None], np.clip(fc, 0, 255), c), np.where(h, fa, a)


def measure(color, alpha, box) -> dict:
    """상자 안의 표시 → {mask(캔버스 bool), box(정수 상자), stroke(획 상자), window, base(곧은 색, 알파 — 창 조각), rgba(표시 그림 — box 크기, 곧은 RGBA float), record}."""
    import cv2
    H, W = alpha.shape
    bx0, by0 = max(0, int(np.floor(float(box[0])))), max(0, int(np.floor(float(box[1]))))
    bx1, by1 = min(W, int(np.ceil(float(box[0]) + float(box[2])))), min(H, int(np.ceil(float(box[1]) + float(box[3]))))
    if bx1 - bx0 < 6 or by1 - by0 < 6:
        raise MarkError(f"the mark box {list(box)} is too small")
    full, d, win = _strokes(color, alpha, [bx0, by0, bx1, by1])
    x0, y0, x1, y1 = win
    cw, aw = color[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    sub = np.zeros((H, W), bool)
    sub[by0:by1, bx0:bx1] = True
    sub, keep = sub[y0:y1, x0:x1], full[y0:y1, x0:x1]
    near = cv2.dilate(keep.astype(np.uint8), np.ones((2 * EDGE_PX + 1,) * 2, np.uint8)) > 0
    m = cv2.dilate((keep | (near & (d > EDGE_DIFF) & sub)).astype(np.uint8), np.ones((2 * GROW + 1,) * 2, np.uint8)) > 0
    if (keep & ~(cv2.erode(sub.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)).any():
        raise MarkError(f"the mark runs out of its box {list(box)} — its strokes touch the edge of the box")
    m &= sub
    ys, xs = np.nonzero(m)
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = m
    bc, ba = fill(color, alpha, mask, win)                                       # 바탕 — 획 자리만 다시(가까운 둘레에서)
    cp, bp = cw * aw[..., None], bc * ba[..., None]
    diff = cp - bp
    mag = np.linalg.norm(diff, axis=2)
    core = m & (mag >= np.percentile(mag[m], 90))
    k = np.median(cp[core], axis=0)
    toward = (diff * (k - bp)).sum(axis=2) > 0                                     # 표시 색 쪽으로 다른 픽셀만 — 반대쪽(테)은 바탕 그대로
    need = np.where(diff > 0, diff / np.maximum(255.0 - bp, 1e-6), -diff / np.maximum(bp, 1e-6)).max(axis=2)      # 얹은 색이 0 ~ 255 안에 들 만큼
    want = (aw - ba) / np.maximum(1.0 - ba, 1e-6)                                   # 시안의 알파가 되는 덮임
    ma = np.where(m & toward, np.clip(np.maximum(want, np.clip(need, 0, 1)), 0, 1), 0.0)
    fp = np.clip(cp - (1 - ma)[..., None] * bp, 0, 255.0 * ma[..., None])
    fc = np.where(ma[..., None] > 1e-3, fp / np.maximum(ma, 1e-3)[..., None], k[None, None])
    stroke = [int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    b = [bx0, by0, bx1 - bx0, by1 - by0]
    s = (slice(b[1] - y0, b[1] - y0 + b[3]), slice(b[0] - x0, b[0] - x0 + b[2]))
    rgba = np.dstack([np.clip(fc, 0, 255), ma * 255.0])[s]
    back = fc * ma[..., None] + bp * (1 - ma)[..., None]
    rec = {"box": b, "stroke": stroke, "px": int(m.sum()), "core_color": [round(float(v), 1) for v in k], "rebuild_max": round(float(np.abs(back - cp)[m].max()), 2),
           "base_alpha": round(float(np.median(ba[m])), 3)}
    return {"mask": mask, "box": b, "stroke": stroke, "window": list(win), "base": (bc, ba), "rgba": rgba, "record": rec}


def fit_box(color, alpha, box) -> list[int]:
    """LLM 이 잡은 상자 → 획 상자 + MARGIN(위젯 자리 · 에셋 크기). 뒤 단계는 이 자리에서 다시 잰다 — 옅은 가장자리는 바탕을 어디서 재는가에 따라 1 px 흔들려
    빠듯한 상자는 다시 잴 때마다 달라진다 [실측 hub_member_row 44 ↔ 45 px].
    LLM 상자는 몇 px 모자랄 수 있다 [실측 R20261125_210820 — 초승달 아래 끝이 상자 밖] → 획이 닿은 변만 2 px 씩, 모두 REACH 까지 넓힌다(한 번에 넓히면 아래 강철 선까지
    든다)."""
    H, W = alpha.shape
    b = [max(0, int(np.floor(float(box[0])))), max(0, int(np.floor(float(box[1])))), 0, 0]
    b[2], b[3] = min(W, int(np.ceil(float(box[0]) + float(box[2])))), min(H, int(np.ceil(float(box[1]) + float(box[3]))))
    start = list(b)
    while True:
        keep = _strokes(color, alpha, b)[0][b[1]:b[3], b[0]:b[2]]
        touch = [keep[:, :1].any(), keep[:1].any(), keep[:, -1:].any(), keep[-1:].any()]
        if not any(touch):
            break
        for k in range(4):
            if touch[k]:
                b[k] = b[k] - 2 if k < 2 else b[k] + 2
        b = [max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3])]
        if max(start[0] - b[0], start[1] - b[1], b[2] - start[2], b[3] - start[3]) > REACH or b[0] == 0 or b[1] == 0 or b[2] == W or b[3] == H:
            raise MarkError(f"the mark runs out of its box {list(box)} — its strokes reach {[b[0], b[1], b[2] - b[0], b[3] - b[1]]}")
    ys, xs = np.nonzero(keep)
    g = GROW + MARGIN
    x0, y0 = max(0, b[0] + int(xs.min()) - g), max(0, b[1] + int(ys.min()) - g)
    return [x0, y0, min(W, b[0] + int(xs.max()) + 1 + g) - x0, min(H, b[1] + int(ys.max()) + 1 + g) - y0]


def _strokes(color, alpha, b) -> tuple[np.ndarray, np.ndarray, tuple]:
    """상자 [x0, y0, x1, y1] 안의 획 → (씨앗 덩어리 캔버스 bool, 메운 띠와의 차(창 조각), 창)."""
    import cv2
    H, W = alpha.shape
    win = window([b[0], b[1], b[2] - b[0], b[3] - b[1]], (H, W))
    x0, y0, x1, y1 = win
    inside = np.zeros((H, W), bool)
    inside[b[1]:b[3], b[0]:b[2]] = True
    bc, ba = fill(color, alpha, inside, win)
    d = np.abs(color[y0:y1, x0:x1] * alpha[y0:y1, x0:x1][..., None] - bc * ba[..., None]).max(axis=2)
    seed = (d > SEED_DIFF) & inside[y0:y1, x0:x1]
    n, lab, _, _ = cv2.connectedComponentsWithStats(cv2.dilate(seed.astype(np.uint8), np.ones((3, 3), np.uint8)), connectivity=8)
    keep = np.zeros((H, W), bool)
    for i in range(1, n):
        comp = seed & (lab == i)
        if int(comp.sum()) >= MIN_PX:
            keep[y0:y1, x0:x1] |= comp
    if not keep.any():
        raise MarkError(f"no mark stands out from its background in {[b[0], b[1], b[2] - b[0], b[3] - b[1]]}")
    return keep, d, win


def paste_base(color, alpha, marks: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """표시를 걷은 아트 — marks = measure 결과들(또는 {window, base}). 사본."""
    col, a = np.asarray(color, float).copy(), np.asarray(alpha, float).copy()
    for m in marks:
        x0, y0, x1, y1 = m["window"]
        col[y0:y1, x0:x1], a[y0:y1, x0:x1] = m["base"]
    return col, a
