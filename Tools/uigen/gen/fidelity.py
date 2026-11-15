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
