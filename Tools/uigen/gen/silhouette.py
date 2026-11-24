"""모양 막대 — 프레임 · 빈 트랙 그림이 없는 막대를 컨셉 알파에서 재고 픽셀을 나눈다 (메인 HUD, 11-24 — 설계 §11 '메인 HUD 설계' 결정 6).

progress 바인딩인 ProgressBar 에 요청이 `bar{track}` 을 주면: 막대 하나 = 텍스처 한 장(컨셉 픽셀 그대로 — 픽셀마다 주인 하나), 채움 브러시 = 그 텍스처를
진행률만큼 자름(엔진 UProgressBar 기본 Mask), 빈 자리 = **같은 텍스처를 track 색으로 물들인 배경 브러시**. 컨셉은 막대를 가득 찬 상태로 그린다(sample 1).
머티리얼 · 바인딩 · setter 는 보통 ProgressBar 그대로다.

  재는 법 — 알파 > ON_ALPHA 덩어리 중 요청 상자(analyze)와 가장 많이 겹치는 것. 두 막대가 한 덩어리면(사이 알파가 이어짐 [실측 hud_blade_sheet 동료 줄 0.37 ~ 0.9])
  두 상자 가운데 줄 사이에서 평균 알파가 가장 낮은 줄에서 가른다. 옅은 가장자리(알파 > SOFT_ALPHA · GROW px 안)는 가장 가까운 막대 몫.
  못 재면 BarError — 조용히 물러나지 않는다.
"""
from __future__ import annotations

import numpy as np

ON_ALPHA = 0.25              # 막대 덩어리
SOFT_ALPHA = 0.02            # 옅은 가장자리(안티앨리어싱 · 그림자)까지 막대 몫
GROW = 4                     # 그 가장자리를 덩어리에서 이만큼(px) 안에서만
SEARCH_PAD = 14              # 요청 상자를 이만큼 넓힌 밖까지 덩어리가 뻗으면 다른 그림과 이어진 것
MIN_ASPECT = 4.0             # 가로 막대 — 폭 ≥ 높이 × 이것
WIDTH_TOL = 0.25             # 잰 폭 ÷ 요청 상자 폭이 1 ± 이것 밖이면 다른 것을 잡았다
MIN_COVER = 0.5              # 요청 상자 넓이의 이만큼은 막대여야 한다(빈 자리 · 옆 그림을 가리킴)
DEFAULT_TRACK = "#404144CC"  # 빈 자리 색 — 밝은 바탕 · 어두운 바탕 모두 보이는 먹색(사용자 선택 11-24 B)


class BarError(ValueError):
    def __init__(self, widget: str, reason: str):
        super().__init__(f"'{widget}': {reason}")
        self.widget, self.reason = widget, reason


def bar_asset(w: dict, assets: dict[str, dict]) -> str | None:
    """이 위젯이 모양 막대면(채움 · 배경 브러시가 같은 '컨셉에서 오리는' 텍스처) 그 에셋 id, 아니면 None."""
    if w.get("type") != "ProgressBar":
        return None
    st = w.get("style") or {}
    f, b = st.get("fill"), st.get("background")
    if not isinstance(f, dict) or not isinstance(b, dict) or not f.get("asset") or f["asset"] != b.get("asset"):
        return None
    return f["asset"] if (assets.get(f["asset"]) or {}).get("source_mode") == "extract" else None


def bars(spec: dict) -> dict[str, str]:
    """모양 막대 위젯 id → 에셋 id."""
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    out = {}
    for w in spec.get("widgets", []):
        aid = bar_asset(w, assets)
        if aid:
            out[w["id"]] = aid
    return out


def asset_id(wid: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", wid).lower()


def _overlap(m, box) -> int:
    x0, y0, x1, y1 = box
    return int(m[y0:y1, x0:x1].sum())


def measure(alpha, boxes: dict[str, list]) -> dict[str, dict]:
    """alpha(캔버스 0 ~ 1) · boxes(막대 위젯 id → analyze 상자) → 위젯 id → {"box"(정수 [x, y, w, h]), "mask"(캔버스 bool), "record"}."""
    import cv2
    H, W = alpha.shape
    a = np.asarray(alpha, float)
    n, lab = cv2.connectedComponents((a > ON_ALPHA).astype(np.uint8), connectivity=8)
    ibox, comp = {}, {}
    for wid, b in boxes.items():
        x, y, w, h = (float(v) for v in b)
        x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
        x1, y1 = min(W, int(np.ceil(x + w))), min(H, int(np.ceil(y + h)))
        if x1 - x0 < 8 or y1 - y0 < 2:
            raise BarError(wid, f"box {list(b)} is empty or outside the canvas")
        ibox[wid] = (x0, y0, x1, y1)
        ids, cnt = np.unique(lab[y0:y1, x0:x1], return_counts=True)
        best = max(((int(c), int(i)) for i, c in zip(ids, cnt) if i), default=None)
        if best is None:
            raise BarError(wid, f"no drawn pixels (alpha > {ON_ALPHA}) inside {list(b)}")
        comp[wid] = best[1]
    core: dict[str, np.ndarray] = {}
    rows: dict[str, tuple[int, int]] = {}                 # 한 덩어리를 나눈 막대가 가질 수 있는 줄(나눈 줄에서 딱 끊는다)
    splits: dict[str, list[int]] = {}
    for cid in set(comp.values()):
        ws = sorted((w for w in comp if comp[w] == cid), key=lambda w: ibox[w][1] + ibox[w][3])
        m = lab == cid
        cuts = []
        for up, dn in zip(ws, ws[1:]):
            bu, bd = ibox[up], ibox[dn]
            cu, cd = (bu[1] + bu[3]) // 2, (bd[1] + bd[3]) // 2
            x0, x1 = max(bu[0], bd[0]), min(bu[2], bd[2])
            if cd - cu < 4 or x1 - x0 < 16:
                raise BarError(dn, f"it is drawn as one piece with '{up}' and there is no row to split them at (boxes {bu} / {bd})")
            prof = a[cu:cd + 1, x0:x1].mean(axis=1)
            cuts.append(cu + int(np.argmin(prof)))
        lo = 0
        for k, wid in enumerate(ws):
            hi = cuts[k] if k < len(cuts) else H            # 나눈 줄은 아래 막대 몫
            r = np.zeros((H, W), bool)
            r[lo:hi] = True
            core[wid] = m & r
            rows[wid] = (lo, hi)
            splits[wid] = cuts
            lo = hi
    dist = {wid: cv2.distanceTransform((~c).astype(np.uint8), cv2.DIST_L2, 5) for wid, c in core.items()}
    other = np.zeros((H, W), bool)                        # 막대가 아닌 덩어리 — 가장자리도 그 그림 몫
    other |= (lab > 0) & ~np.any(np.stack(list(core.values())), axis=0) if core else False
    od = cv2.distanceTransform((~other).astype(np.uint8), cv2.DIST_L2, 5) if other.any() else np.full((H, W), np.inf)
    out: dict[str, dict] = {}
    for wid, c in core.items():
        if not c.any():
            raise BarError(wid, "nothing is left after splitting it from its neighbour")
        soft = (a > SOFT_ALPHA) & (dist[wid] <= GROW) & ~other & (dist[wid] < od)
        for o, d in dist.items():
            if o != wid:
                soft &= ~core[o] & ((dist[wid] < d) | ((dist[wid] == d) & (wid < o)))
        lo, hi = rows[wid]
        soft[:lo] = False
        soft[hi:] = False
        mask = c | soft
        ys, xs = np.nonzero(mask)
        box = [int(xs.min()), int(ys.min()), int(xs.max()) - int(xs.min()) + 1, int(ys.max()) - int(ys.min()) + 1]
        x0, y0, x1, y1 = ibox[wid]
        if box[0] < x0 - SEARCH_PAD or box[1] < y0 - SEARCH_PAD or box[0] + box[2] > x1 + SEARCH_PAD or box[1] + box[3] > y1 + SEARCH_PAD:
            raise BarError(wid, f"the drawing there reaches {box}, far outside the box {list(boxes[wid])} — it is joined to something else")
        if box[2] < MIN_ASPECT * box[3]:
            raise BarError(wid, f"measured {box[2]}×{box[3]} px — not a horizontal bar")
        ratio = box[2] / max(1.0, float(x1 - x0))
        if abs(ratio - 1.0) > WIDTH_TOL:
            raise BarError(wid, f"measured width {box[2]} px against the box width {x1 - x0} px")
        cover = _overlap(mask, ibox[wid]) / max(1, (x1 - x0) * (y1 - y0))
        if cover < MIN_COVER:
            raise BarError(wid, f"only {cover:.0%} of the box {list(boxes[wid])} is the bar")
        out[wid] = {"box": box, "mask": mask,
                    "record": {"box": box, "core_px": int(c.sum()), "mask_px": int(mask.sum()), "box_fill": round(float(mask.sum()) / (box[2] * box[3]), 3),
                               "width_ratio": round(ratio, 3), **({"split_rows": splits[wid]} if splits[wid] else {})}}
    return out
