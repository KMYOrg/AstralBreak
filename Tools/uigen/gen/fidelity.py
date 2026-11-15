"""컨셉에서 따온 에셋의 충실도 (1b 후속 A — source_mode: extract). 기록만 한다(결정 6 · §8-2 — 게이트 아님).

입력: 컨셉 조각(reference 의 요소 상자 = ref_bbox + pad) · 편집 결과를 같은 상자로 되자른 것(crop_back, 다듬기 전) · 최종 텍스처.
지표 [채록 A-1 에서 고른 것]:
  - framing   : 편집이 구도를 지켰나 — 되자른 결과의 모양 상자 ↔ 컨셉 모양 상자의 중심 차(px) · 크기 비 · IoU
  - aspect    : 모양 상자의 가로세로비 오차(%) — 최종 텍스처는 spec 크기로 늘어나므로 늘리기 전 값
  - shape_iou : 최종 텍스처를 컨셉 모양 상자에 맞춰 놓았을 때 실루엣 IoU
  - line_f1   : 테두리 띠 안의 장식선(밝고 채도 있는 선) 일치 — 허용 2 px, precision · recall 따로
  - delta_e00 : 대표색(영역 Lab 중앙값) ΔE00 — 장식선 · 안쪽(최종 텍스처를 컨셉 위에 얹은 것), 픽셀별 평균 · p95 는 보조
모양(실루엣)은 컨셉에 알파가 없으므로 장식선 마스크의 바깥 윤곽을 채워 만든다(가장 큰 윤곽이 볼록 껍질의 60 % 미만이면 껍질).
장식선 기준 L* ≥ 45 · C* ≥ 20 은 금 · 색 테두리용이다 — 은색 · 어두운 테는 못 잡는다(잠정).
"""
from __future__ import annotations

import math

import numpy as np

from core import color

LINE_MIN_L = 45.0
LINE_MIN_C = 20.0
RING_FRAC = 0.12          # 테두리 띠 = 모양 가장자리에서 짧은 변의 12 % 안
LINE_TOL_PX = 2
INTERIOR_ERODE_FRAC = 0.04


def line_mask(rgb) -> np.ndarray:
    lab = color.srgb_to_lab(rgb)
    return (lab[..., 0] >= LINE_MIN_L) & (np.hypot(lab[..., 1], lab[..., 2]) >= LINE_MIN_C)


PAD = 8   # 마스크를 0 테두리로 덧대고 계산 — 모양이 그림 가장자리에 닿으면 close 가 가장자리를 메우고(침식 테두리값 = 최대)
          # distanceTransform 이 그림 밖을 바깥으로 치지 않는다 [실측 B run — 위젯 상자로 바짝 되자르자 테두리 띠가 비어 F1 0]


def _padded(mask) -> np.ndarray:
    import cv2
    return cv2.copyMakeBorder(np.asarray(mask, np.uint8), PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=0)


def fill_shape(mask) -> tuple[np.ndarray, str]:
    import cv2
    m = _padded(mask) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(m)
    if not cnts:
        return out[PAD:-PAD, PAD:-PAD] > 0, "empty"
    big = max(cnts, key=cv2.contourArea)
    hull = cv2.convexHull(np.vstack(cnts))
    use, how = (hull, "hull") if cv2.contourArea(big) < 0.6 * cv2.contourArea(hull) else (big, "contour")
    cv2.drawContours(out, [use], -1, 255, thickness=-1)
    return out[PAD:-PAD, PAD:-PAD] > 0, how


def bbox_of(mask) -> list[int] | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def iou(a, b) -> float:
    u = (a | b).sum()
    return round(float((a & b).sum() / u), 4) if u else 0.0


def _morph(mask, px, op):
    import cv2
    if px <= 0:
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
    return (cv2.dilate if op == "dilate" else cv2.erode)(np.asarray(mask, np.uint8), k) > 0


def f1_tol(ref, got, tol=LINE_TOL_PX) -> dict:
    dr, dg = _morph(ref, tol, "dilate"), _morph(got, tol, "dilate")
    prec = float((got & dr).sum() / max(1, got.sum()))
    rec = float((ref & dg).sum() / max(1, ref.sum()))
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "tol_px": tol}


def _shape_of_rgba(arr) -> np.ndarray:
    return fill_shape(arr[:, :, 3] > 128)[0]


def _ring(shape) -> np.ndarray:
    import cv2
    bb = bbox_of(shape)
    if not bb:
        return shape
    dist = cv2.distanceTransform(_padded(shape), cv2.DIST_L2, 3)[PAD:-PAD, PAD:-PAD]
    return shape & (dist <= max(3.0, RING_FRAC * min(bb[2], bb[3])))


def _checker(w, h, step=12):
    from PIL import Image
    yy, xx = np.mgrid[0:h, 0:w]
    v = np.where(((xx // step) + (yy // step)) % 2 == 0, 200, 150).astype(np.uint8)
    return Image.fromarray(np.dstack([v, v, v, np.full_like(v, 255)]), "RGBA")


def _sheet(panels, vertical: bool):
    from PIL import Image, ImageDraw
    w0 = panels[0][1].width
    scale = 2 if w0 < 500 else 1
    ims = []
    for label, p in panels:
        p = p.convert("RGB").resize((p.width * scale, p.height * scale))
        dr = ImageDraw.Draw(p)
        dr.rectangle([0, 0, 8 + 7 * len(label), 14], fill=(0, 0, 0))
        dr.text((4, 2), label, fill=(255, 255, 0))
        ims.append(p)
    sw = max(i.width for i in ims) if vertical else sum(i.width + 6 for i in ims)
    sh = sum(i.height + 6 for i in ims) if vertical else max(i.height for i in ims)
    sheet = Image.new("RGB", (sw, sh), (20, 20, 20))
    pos = 0
    for i in ims:
        sheet.paste(i, (0, pos) if vertical else (pos, 0))
        pos += (i.height if vertical else i.width) + 6
    return sheet


INK_MIN_PIXELS = 30
INK_MIN_SPREAD = 20.0     # 상자 안 L* 범위가 이보다 좁으면 글자가 없다고 본다
INK_CORE = 0.3            # 글자 쪽 L* 를 문턱에서 끝값 쪽으로 30 % 들인 '획 안쪽' — 가장자리 안티앨리어싱 · 외곽선 섞임 빼기


def text_ink(rgb) -> np.ndarray | None:
    """글자 상자 안 글자(획 안쪽) 픽셀 (1b 후속 D · C). L* 를 Otsu 로 둘로 나눠 **적은 쪽**을 글자로 본다(글자는 상자의 소수) —
    어두운 바탕 위 밝은 글자 · 밝은 바탕 위 어두운 글자 모두. 상자가 거의 한 색이거나 획이 너무 적으면 None."""
    import cv2
    lab = color.srgb_to_lab(np.asarray(rgb)[:, :, :3])
    L = lab[..., 0]
    lo, hi = float(np.percentile(L, 2)), float(np.percentile(L, 98))
    if hi - lo < INK_MIN_SPREAD:
        return None
    L8 = np.clip(np.round(L * 2.55), 0, 255).astype(np.uint8)
    t8, _ = cv2.threshold(L8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu 와 같은 양자화(L8)로 가른다 — 바탕이 한 값이면 문턱 = 바탕 값이라 실수 L* 로 비교하면 바탕이 '밝은 쪽'이 된다
    t, lo8, hi8 = float(t8), float(np.percentile(L8, 2)), float(np.percentile(L8, 98))
    bright = L8 > t
    if bright.sum() <= (~bright).sum():
        ink = L8 >= t + max(1.0, INK_CORE * (hi8 - t))
    else:
        ink = L8 <= t - INK_CORE * (t - lo8)
    ink = _text_band(ink)
    return ink if int(ink.sum()) >= INK_MIN_PIXELS else None


INK_LINE_ROW = 0.6        # 상자 폭의 60 % 넘게 칠해진 줄 = 가로 테두리선(글자 줄은 그만큼 차지 않는다)
INK_BAND_GAP = 3          # 글자 줄 띠 안에서 허용하는 빈 줄
INK_MIN_PART = 0.1        # 가장 큰 덩어리 대비 이보다 작은 덩어리는 잔조각
INK_VLINE_W = 0.25        # 1b 후속 F — 폭 ≤ 상자 높이 × 이 값 · 높이 ≥ 상자 높이 × INK_VLINE_H 인 덩어리 = 세로 테두리선
INK_VLINE_H = 0.8


def _text_band(ink) -> np.ndarray:
    """상자에 걸친 프레임 금테를 뺀다 [실측 D — 증거 run '2/4' 상자 아래 패널 금테가 가짜 그라데이션 ΔE00 28]:
    가로선 줄(폭 60 % 이상)을 지우고, 빈 줄 3 개까지 이어 붙인 줄 띠 중 획이 가장 많은 띠만 남긴다."""
    import cv2
    ink = ink.copy()
    w = ink.shape[1]
    counts = ink.sum(axis=1)
    ink[counts >= INK_LINE_ROW * w] = False
    # 상자 좌우 끝에 닿은 덩어리(패널 모서리 장식) 빼기 — 남는 획이 절반 이상일 때만 [실측 D — '2/4' 상자 아래 양쪽 모서리 장식]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    # 세로 테두리선(상자 높이 80 % 이상 · 폭 ≤ 상자 높이 25 % — 글자 획은 줄 상자의 60 % 를 못 넘는다) 빼기
    # [실측 F 끝 run 3] 빛 글자 '4.2' 의 넓은 상자에 패널 안쪽 세로선이 걸려 획 상자 = 상자 전체(높이 비 2.0) — 컨셉 선은 6 ~ 8 px, 렌더 선은 1 px
    hh = ink.shape[0]
    vlines = [i for i in range(1, n) if stats[i, cv2.CC_STAT_HEIGHT] >= INK_VLINE_H * hh and stats[i, cv2.CC_STAT_WIDTH] <= INK_VLINE_W * hh]
    if vlines:
        ink &= ~np.isin(lab, vlines)
    # [실측 F] '닿음'을 '폭 4 % 안'으로 넓히면 글자가 꽉 찬 상자에서 첫 글자를 지웠다('오의 불가' 폭 비 1.286) — 닿은 것만
    edge = [i for i in range(1, n) if i not in vlines and (stats[i, cv2.CC_STAT_LEFT] == 0 or stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] >= w)]
    if edge:
        drop = np.isin(lab, edge)
        if (ink & ~drop).sum() >= 0.5 * ink.sum():
            ink &= ~drop
    # 남은 잔조각(장식 끝 · 잡티) — 가장 큰 덩어리의 10 % 미만
    areas = {i: int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n) if ink[lab == i].any()}
    if areas:
        big = max(areas.values())
        small = [i for i, a in areas.items() if a < INK_MIN_PART * big]
        if small:
            ink &= ~np.isin(lab, small)
    rows = np.where(ink.sum(axis=1) > 0)[0]
    if len(rows) == 0:
        return ink
    bands, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r - prev > INK_BAND_GAP + 1:
            bands.append((start, prev))
            start = r
        prev = r
    bands.append((start, prev))
    best = max(bands, key=lambda b: int(ink[b[0]:b[1] + 1].sum()))
    keep = np.zeros_like(ink)
    keep[best[0]:best[1] + 1] = ink[best[0]:best[1] + 1]
    return keep


def ink_box(ink) -> list[int] | None:
    return bbox_of(ink) if ink is not None else None


def render_vs_concept(concept_rgb, render_rgb, exclude=None) -> tuple[dict, object]:
    """WBP 렌더(같은 상자) ↔ 컨셉 — 이식이 맞는지(1b 후속 A, 기록만). 렌더는 검은 바탕 불투명이라 비치는 안쪽은 비교하지 않고
    장식선(테두리 띠 안, 글자 위젯 자리 제외)의 위치 · 대표색과 모양 실루엣만 본다."""
    from PIL import Image
    c = np.asarray(concept_rgb)[:, :, :3]
    r = np.asarray(render_rgb)[:, :, :3]
    excl = np.zeros(c.shape[:2], bool) if exclude is None else np.asarray(exclude, bool)
    lines_c, lines_r = line_mask(c) & ~excl, line_mask(r) & ~excl
    shape_c, how = fill_shape(lines_c)
    shape_r, _ = fill_shape(lines_r)
    ring = _ring(shape_c) & ~excl
    out = {"shape_iou": iou(shape_c, shape_r), "concept_shape_from": how, "line_f1": f1_tol(lines_c & ring, lines_r & ring),
           "delta_e00": {"lines": color.region_delta_e(c, r, lines_c & ring, lines_r & ring)["representative"],
                         "ring_pixel": color.region_delta_e(c, r, ring)["pixel"]},
           "note": "render is opaque over black — the see-through interior is not compared; text widget boxes are excluded"}
    sheet = _sheet([("concept", Image.fromarray(c.astype(np.uint8))), ("WBP render", Image.fromarray(r.astype(np.uint8)))], vertical=c.shape[1] >= c.shape[0])
    return out, sheet


def render_comparisons(reference_path, render_path, spec: dict, asset_ids, out_dir, pad: int = 4) -> dict:
    """따온 에셋을 쓰는 위젯마다 bbox_intent(+pad) 상자에서 render_vs_concept → {asset_id: [{widget, box, …, compare}]} + out_dir/<id>_render_<widget>.png."""
    import pathlib
    from PIL import Image
    ref = np.asarray(Image.open(reference_path).convert("RGB"))
    ren = np.asarray(Image.open(render_path).convert("RGB"))
    if ref.shape != ren.shape:
        return {"error": f"reference {ref.shape[:2]} and render {ren.shape[:2]} differ"}
    H, W = ref.shape[:2]
    texts = [w["bbox_intent"] for w in spec.get("widgets", []) if w.get("type") == "TextBlock" and w.get("bbox_intent")]
    out: dict = {}
    for w in spec.get("widgets", []):
        for key, brush in (w.get("style") or {}).items():
            if not (isinstance(brush, dict) and brush.get("asset") in asset_ids and w.get("bbox_intent")):
                continue
            x, y, bw, bh = w["bbox_intent"]
            x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
            x1, y1 = min(W, int(math.ceil(x + bw)) + pad), min(H, int(math.ceil(y + bh)) + pad)
            excl = np.zeros((y1 - y0, x1 - x0), bool)
            for tx, ty, tw, th in texts:
                ax0, ay0, ax1, ay1 = int(tx) - 2 - x0, int(ty) - 2 - y0, int(math.ceil(tx + tw)) + 2 - x0, int(math.ceil(ty + th)) + 2 - y0
                excl[max(0, ay0):max(0, ay1), max(0, ax0):max(0, ax1)] = True
            rec, sheet = render_vs_concept(ref[y0:y1, x0:x1], ren[y0:y1, x0:x1], excl)
            name = f"{brush['asset']}_render_{w['id']}.png"
            pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
            sheet.save(pathlib.Path(out_dir) / name)
            rec.update(widget=w["id"], brush=key, draw_as=brush.get("draw_as"), box=[x0, y0, x1 - x0, y1 - y0], compare=f"assets/compare/{name}")
            out.setdefault(brush["asset"], []).append(rec)
    return out


def _clip_box(bb, W, H, pad: int = 0) -> tuple[int, int, int, int]:
    x, y, w, h = bb
    return max(0, int(x) - pad), max(0, int(y) - pad), min(W, int(math.ceil(x + w)) + pad), min(H, int(math.ceil(y + h)) + pad)


def text_vs_concept(concept_rgb, render_rgb) -> dict:
    """글자 상자 하나 — 컨셉 ↔ 렌더 글자 획(text_ink) 상자 · 크기 비 · 중심 차 · 획 대표색 ΔE00 (1b 후속 C, 기록만)."""
    c, r = np.asarray(concept_rgb)[:, :, :3].astype(float), np.asarray(render_rgb)[:, :, :3].astype(float)
    ic, ir = text_ink(c), text_ink(r)
    bc, br = ink_box(ic), ink_box(ir)
    out: dict = {"ink_box_concept": bc, "ink_box_render": br}
    if ic is None or ir is None:
        out["error"] = "no glyph pixels in the " + ("concept" if ic is None else "render")
        return out
    cc, cr = np.median(c[ic], axis=0), np.median(r[ir], axis=0)
    out.update(h_ratio=round(br[3] / bc[3], 3), w_ratio=round(br[2] / bc[2], 3),
               center_dx=round(br[0] + br[2] / 2 - bc[0] - bc[2] / 2, 1), center_dy=round(br[1] + br[3] / 2 - bc[1] - bc[3] / 2, 1),
               ink_de00=round(float(color.delta_e00(color.srgb_to_lab(cc), color.srgb_to_lab(cr))), 2),
               concept_ink="#%02X%02X%02X" % tuple(int(round(v)) for v in cc), render_ink="#%02X%02X%02X" % tuple(int(round(v)) for v in cr))
    return out


def region_report(reference_path, render_path, spec: dict, out_dir, pad: int = 4) -> dict:
    """1b 후속 C — 영역(루트 직계) · 글자(TextBlock) · 게이지 전부의 컨셉 ↔ 렌더 비교(기록만 — 결정 6). 렌더는 force_visible(render.png):
    샘플 렌더는 꺼진 flag(배너 등)를 접지만 컨셉에는 그것이 보이기 때문. 렌더는 검은 바탕 불투명이라 비치는 안쪽은 영역 대표색에 섞인다(그대로 기록).
    → {regions{id: {box, line_f1, shape_iou, delta_e00, representative_de00, sheet}}, texts{id: text_vs_concept + box}, gauges{id: gauge_vs_concept},
       summary{…}} + out_dir/<영역>.png(컨셉 | 렌더 나란히 — 그 영역의 글자 상자를 노랑으로)."""
    import pathlib
    from PIL import Image, ImageDraw
    ref = np.asarray(Image.open(reference_path).convert("RGB"))
    ren = np.asarray(Image.open(render_path).convert("RGB"))
    if ref.shape != ren.shape:
        return {"error": f"reference {ref.shape[:2]} and render {ren.shape[:2]} differ"}
    H, W = ref.shape[:2]
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    widgets = spec.get("widgets", [])
    root = spec.get("root")
    by_id = {w["id"]: w for w in widgets}

    def region_of(wid):
        cur = by_id.get(wid)
        while cur is not None and cur.get("parent") not in (root, None):
            cur = by_id.get(cur.get("parent"))
        return cur["id"] if cur is not None and cur.get("parent") == root else None

    texts = [w for w in widgets if w.get("type") == "TextBlock" and w.get("bbox_intent")]
    out: dict = {"render": pathlib.Path(render_path).name, "regions": {}, "texts": {}, "gauges": {}}
    for w in widgets:
        if w.get("parent") != root or not w.get("bbox_intent"):
            continue
        x0, y0, x1, y1 = _clip_box(w["bbox_intent"], W, H, pad)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        excl = np.zeros((y1 - y0, x1 - x0), bool)
        mine = [t for t in texts if region_of(t["id"]) == w["id"]]
        for t in mine:
            tx0, ty0, tx1, ty1 = _clip_box(t["bbox_intent"], W, H, 2)
            excl[max(0, ty0 - y0):max(0, ty1 - y0), max(0, tx0 - x0):max(0, tx1 - x0)] = True
        cc, rr = ref[y0:y1, x0:x1], ren[y0:y1, x0:x1]
        rec, _ = render_vs_concept(cc, rr, excl)
        rec["representative_de00"] = color.region_delta_e(cc, rr, ~excl)["representative"]
        rec["box"] = [x0, y0, x1 - x0, y1 - y0]
        rec["texts"] = [t["id"] for t in mine]
        pc, pr = Image.fromarray(cc.astype(np.uint8)), Image.fromarray(rr.astype(np.uint8))
        for p in (pc, pr):
            d = ImageDraw.Draw(p)
            for t in mine:
                tx0, ty0, tx1, ty1 = _clip_box(t["bbox_intent"], W, H)
                d.rectangle([tx0 - x0, ty0 - y0, tx1 - x0 - 1, ty1 - y0 - 1], outline=(255, 230, 0))
        name = f"{w['id']}.png"
        _sheet([("concept", pc), ("render", pr)], vertical=(x1 - x0) >= (y1 - y0)).save(out_dir / name)
        rec["sheet"] = name
        out["regions"][w["id"]] = rec
    for t in texts:
        bb = list(t["bbox_intent"])
        g = float(((t.get("font") or {}).get("glow") or {}).get("size") or 0)
        if g:   # 1b 후속 F — 빛 글자는 analyze 가 상자를 사방 빛 크기만큼 넓혔다 → 원래 줄 상자에서 잰다
            # [실측 F 끝 run 3] 넓힌 상자가 패널 안쪽 세로선을 덮어 획 상자 = 상자 전체(높이 비 2.015)
            bb = [bb[0] + g, bb[1] + g, bb[2] - 2 * g, bb[3] - 2 * g]
        x0, y0, x1, y1 = _clip_box(bb, W, H)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        rec = text_vs_concept(ref[y0:y1, x0:x1], ren[y0:y1, x0:x1])
        rec.update(box=[x0, y0, x1 - x0, y1 - y0], region=region_of(t["id"]))
        out["texts"][t["id"]] = rec
    for w in widgets:
        st = w.get("style") or {}
        if w.get("type") == "ProgressBar" and w.get("bbox_intent") and isinstance(st.get("percent"), (int, float)):
            try:
                out["gauges"][w["id"]] = gauge_vs_concept(reference_path, render_path, w["bbox_intent"], st["percent"], st.get("bar_fill_type", "left_to_right"))
                out["gauges"][w["id"]]["shape"] = gauge_shape(reference_path, render_path, w["bbox_intent"], st["percent"], st.get("bar_fill_type", "left_to_right"))
            except Exception as exc:  # noqa: BLE001 — 기록 지표
                out["gauges"][w["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    out["summary"] = report_summary(out)
    return out


def report_summary(rep: dict) -> dict:
    """라운드 전후를 한눈에 — 글자 획 ΔE00 평균 · 글자 높이 비 |1 − r| 평균 · 영역 장식선 F1 평균 · 영역 대표색 ΔE00 평균 · 게이지 채움 줄 단위 평균."""
    def mean(v):
        v = [x for x in v if isinstance(x, (int, float))]
        return round(float(np.mean(v)), 3) if v else None
    t = [x for x in (rep.get("texts") or {}).values() if "error" not in x]
    r = list((rep.get("regions") or {}).values())
    g = [x for x in (rep.get("gauges") or {}).values() if isinstance(x, dict) and x.get("filled")]
    return {"text_ink_de00": mean([x.get("ink_de00") for x in t]), "text_h_ratio_err": mean([abs(1 - x["h_ratio"]) for x in t if x.get("h_ratio")]),
            "text_w_ratio_err": mean([abs(1 - x["w_ratio"]) for x in t if x.get("w_ratio")]),
            "region_line_f1": mean([(x.get("line_f1") or {}).get("f1") for x in r]), "region_de00": mean([x.get("representative_de00") for x in r]),
            "gauge_fill_rows_de00": mean([x["filled"]["rows"]["mean"] for x in g]), "texts": len(t), "regions": len(r)}


def gauge_vs_concept(reference_path, render_path, bbox, percent: float, fill_type: str = "left_to_right", edge: float = 0.04) -> dict:
    """게이지(ProgressBar) 상자에서 채워진 부분 · 빈 부분의 컨셉 ↔ 렌더 대표색 ΔE00(+ 픽셀별 평균) — 1b 후속 B, 기록만.
    렌더는 검은 바탕 불투명이라 빈 부분(비치는 트랙)은 컨셉보다 어둡게 나올 수 있다."""
    from PIL import Image
    ref = np.asarray(Image.open(reference_path).convert("RGB"))
    ren = np.asarray(Image.open(render_path).convert("RGB"))
    H, W = ref.shape[:2]
    x, y, bw, bh = (float(v) for v in bbox)
    y0, y1 = max(0, int(round(y))), min(H, int(round(y + bh)))
    p = float(percent)
    filled, empty = ((x + edge * bw, x + (p - edge) * bw), (x + (p + edge) * bw, x + (1 - edge) * bw)) if fill_type != "right_to_left" else \
        ((x + (1 - p + edge) * bw, x + (1 - edge) * bw), (x + edge * bw, x + (1 - p - edge) * bw))
    out = {"box": [int(round(x)), y0, int(round(bw)), y1 - y0], "percent": p}
    for name, (a, b) in (("filled", filled), ("empty", empty)):
        a, b = max(0, int(round(a))), min(W, int(round(b)))
        if b - a < 4 or y1 - y0 < 2:
            out[name] = None
            continue
        m = np.zeros(ref.shape[:2], bool)
        m[y0:y1, a:b] = True
        d = color.region_delta_e(ref, ren, m)
        rows = color.delta_e00(color.srgb_to_lab(np.median(ref[y0:y1, a:b].astype(float), axis=1)),
                               color.srgb_to_lab(np.median(ren[y0:y1, a:b].astype(float), axis=1)))     # 줄마다 대표색 — 세로 그라데이션
        out[name] = {"x": [a, b], "representative": d["representative"], "pixel": d["pixel"],
                     "rows": {"mean": round(float(rows.mean()), 2), "max": round(float(rows.max()), 2)}}
    return out


def gauge_shape(reference_path, render_path, bbox, percent: float, fill_type: str = "left_to_right", tail_px: int = 12) -> dict:
    """게이지 채움 실루엣 — 막대 상자 안 밝은(L > T) 픽셀의 컨셉 ↔ 렌더 IoU(왼쪽 끝 '<' 모양 · 위아래 범위), 진행 끝 앞까지만(1b 후속 F, 기록만).
    T = (채운 부분 L 중앙값 + 빈 부분 L 중앙값) / 2 를 컨셉에서(gen/concept_fill 과 같은 밝기). 시작 끝(left_to_right 면 왼쪽)에서 처음 밝은 열의 차도 준다.
    열 범위는 상자 시작 ~ 진행률 자리 − tail_px — 컨셉의 실제 채움 길이가 샘플과 달라도 끝은 비교하지 않는다."""
    from PIL import Image
    from gen.concept_fill import luminance
    ref = np.asarray(Image.open(reference_path).convert("RGB")).astype(float)
    ren = np.asarray(Image.open(render_path).convert("RGB")).astype(float)
    H, W = ref.shape[:2]
    x, y, bw, bh = (float(v) for v in bbox)
    p = float(percent)
    y0, y1 = max(0, int(round(y))), min(H, int(round(y + bh)))
    flip = fill_type == "right_to_left"
    if flip:
        a, b = int(round(x + (1 - p) * bw)) + tail_px, int(round(x + bw))
    else:
        a, b = int(round(x)), int(round(x + p * bw)) - tail_px
    a, b = max(0, a), min(W, b)
    if b - a < 8 or y1 - y0 < 4:
        return {"error": "box too small"}
    Lc, Lr = luminance(ref[y0:y1]), luminance(ren[y0:y1])
    r0, r1 = int(0.25 * (y1 - y0)), max(int(0.75 * (y1 - y0)), int(0.25 * (y1 - y0)) + 1)
    fill_cols = slice(int(a + 0.3 * (b - a)), int(a + 0.7 * (b - a)) + 1)
    e0, e1 = (int(round(x + 0.03 * bw)), int(round(x + max(0.0, (1 - p) - 0.08) * bw))) if flip else \
        (int(round(x + min(1.0, p + 0.08) * bw)), int(round(x + 0.97 * bw)))
    if e1 - e0 < 4:
        return {"error": "no empty part to set the brightness threshold"}
    T = (float(np.median(Lc[r0:r1, fill_cols])) + float(np.median(Lc[r0:r1, e0:e1]))) / 2.0
    mc, mr = Lc[:, a:b] > T, Lr[:, a:b] > T
    out = {"columns": [a, b], "rows": [y0, y1], "threshold": round(T, 1), "iou": iou(mc, mr)}
    mid = slice(r0, r1)
    def tip(m):
        cols = np.where(m[mid].any(axis=0))[0]
        if len(cols) == 0:
            return None
        return int(a + (cols.max() if flip else cols.min()))
    tc, tr = tip(mc), tip(mr)
    out.update(tip_concept=tc, tip_render=tr, tip_dx=(tr - tc) if tc is not None and tr is not None else None,
               rows_concept=int(mc.any(axis=1).sum()), rows_render=int(mr.any(axis=1).sum()))
    return out


def extract_fidelity(concept_rgb, cropped, final) -> tuple[dict, object]:
    """concept_rgb: 컨셉 요소 상자(numpy RGB) · cropped: 편집 결과를 같은 상자로 되자른 PIL RGBA · final: 최종 텍스처 PIL RGBA.
    → (기록 dict, 나란히 그림 PIL RGB)."""
    from PIL import Image
    concept_rgb = np.asarray(concept_rgb)[:, :, :3]
    H, W = concept_rgb.shape[:2]
    lines_c = line_mask(concept_rgb)
    shape_c, how = fill_shape(lines_c)
    cbox = bbox_of(shape_c)
    out: dict = {"concept_shape_bbox": cbox, "concept_shape_from": how, "line_rule": f"L*>={LINE_MIN_L:g}, C*>={LINE_MIN_C:g}"}
    concept_im = Image.fromarray(concept_rgb.astype(np.uint8), "RGB")
    if not cbox:
        out["error"] = "no decorative line found in the concept crop"
        return out, concept_im
    # framing — 되자른 결과(요소 상자 격자)를 컨셉 크기로
    fr = np.asarray(cropped.convert("RGBA").resize((W, H)))
    shape_f = _shape_of_rgba(fr)
    fbox = bbox_of(shape_f)
    raw_shape = _shape_of_rgba(np.asarray(cropped.convert("RGBA")))
    rbox = bbox_of(raw_shape)
    if fbox:
        out["framing"] = {"iou": iou(shape_c, shape_f),
                          "center_offset_px": [round(fbox[0] + fbox[2] / 2 - cbox[0] - cbox[2] / 2, 1), round(fbox[1] + fbox[3] / 2 - cbox[1] - cbox[3] / 2, 1)],
                          "size_ratio": [round(fbox[2] / cbox[2], 3), round(fbox[3] / cbox[3], 3)]}
    if rbox:
        ca, ra = cbox[2] / cbox[3], rbox[2] / rbox[3]
        out["aspect"] = {"concept": round(ca, 3), "result": round(ra, 3), "error_pct": round((ra / ca - 1) * 100, 2)}
    # 최종 텍스처를 컨셉 모양 상자에 맞춰 놓기
    fin = final.convert("RGBA")
    fshape = _shape_of_rgba(np.asarray(fin))
    fb = bbox_of(fshape) or [0, 0, fin.width, fin.height]
    placed = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    placed.alpha_composite(fin.crop((fb[0], fb[1], fb[0] + fb[2], fb[1] + fb[3])).resize((cbox[2], cbox[3]), Image.Resampling.LANCZOS), (cbox[0], cbox[1]))
    pa = np.asarray(placed)
    shape_p = _shape_of_rgba(pa)
    lines_p = line_mask(pa[:, :, :3]) & (pa[:, :, 3] > 128)
    comp = np.asarray(Image.alpha_composite(concept_im.convert("RGBA"), placed).convert("RGB"))
    ring = _ring(shape_c)
    interior = _morph(shape_c, max(2, int(INTERIOR_ERODE_FRAC * min(cbox[2], cbox[3]))), "erode") & ~_morph(lines_c, 3, "dilate")
    out["shape_iou"] = iou(shape_c, shape_p)
    out["line_f1"] = f1_tol(lines_c & ring, lines_p & ring)
    out["delta_e00"] = {"lines": color.region_delta_e(concept_rgb, pa[:, :, :3], lines_c & ring, lines_p & ring)["representative"],
                        "interior": color.region_delta_e(concept_rgb, comp, interior)["representative"],
                        "shape_pixel": color.region_delta_e(concept_rgb, comp, shape_c | shape_p)["pixel"]}
    # 나란히 그림: 컨셉 | 체크무늬 위 최종 텍스처 | 컨셉 위에 얹은 것
    chk = _checker(W, H)
    chk.alpha_composite(placed)
    panels = [("concept crop", concept_im), ("final texture (shape-aligned)", chk.convert("RGB")), ("final over concept", Image.fromarray(comp))]
    return out, _sheet(panels, vertical=W >= H)
