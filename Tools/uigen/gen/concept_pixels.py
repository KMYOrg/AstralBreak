"""따온 프레임에 컨셉 픽셀 옮겨 심기 (1b 후속 G — codex · LLM 없음).

A 의 따오기는 codex 편집 결과를 텍스처로 쓰고 안쪽만 대표색 한 색으로 칠했다(`postprocess.interior_fill`). 사용자 사람 눈(11-15)에서 남은 차이 둘이
여기서 나왔다:
  - 배너 위아래 빛 — [실측 F run 4] 컨셉 배너 안쪽은 위아래 테두리 근처가 밝다(가운데 열 위 안쪽 L 126 ~ 139 · 아래 104 ~ 124, 옆 27 ~ 36,
    한가운데 24). 한 색으로 칠하면 18.9 로 평평해진다. 바깥은 금테 밖 어두운 테(L 13 ~ 15)뿐이라 구울 빛이 없다.
  - 체인 패널 모서리 — codex 가 모서리 장식을 다시 그렸다(작게 · 오른쪽 아래는 거의 없음). 외형 라운드의 다시 따오기도 금테 색을 바꿨다
    (run 4 배너 선 ΔE00 7.9 → 14.6).
그래서 codex 결과는 **실루엣(알파 — 장면에서 요소를 가르는 일)** 에만 쓰고, 색은 컨셉 픽셀을 그대로 쓴다:
  1. 정합 — 위젯 해상도에서 codex 장식선 ↔ 컨셉 장식선 F1(허용 1 px)이 가장 큰 이동(±SHIFT_MAX px)으로 codex 텍스처를 옮긴다(이득 ≥ SHIFT_MIN_GAIN 일 때만).
  2. 실루엣 — 컨셉 장식선을 채운 모양이 위젯 상자를 RECT_FILL 이상 채우면(사각 패널) 실루엣 = 상자 그대로(codex 와 무관 — run 마다 같음, 1 단계 생략).
     아니면 codex 실루엣 ↔ 컨셉 모양 IoU < MIN_SILHOUETTE_IOU 면 옮겨 심지 않는다(ConceptPixelsError → 호출 쪽이 한 색 칠하기로).
  3. 글자 구멍 — 글자 위젯 상자(+HOLE_PAD) 안 획(`fidelity.text_ink`)과 그 둘레의 바탕과 다른 픽셀(어두운 테 · 빛)을 HOLE_GROW + 빛 크기 × HOLE_GLOW_K 넓힌 곳.
     **테두리에 이어진 장식선 덩어리(테두리선 · 모서리 장식)와 테두리 띠에 닿는 획 덩어리(채도 낮은 테두리선 조각)는 빼고** — 패널 폭 글자 상자('체인' · '2/4')가
     모서리 장식까지 획으로 잡는다(획 상자 폭 326 · 327 px).
     자식 Image 상자(exclude)도 구멍. 구멍은 줄마다 좌우 가장 가까운 성한 픽셀(장식선 아님) 사이 직선 보간 — 안쪽 빛은 세로 단면이라 줄 밝기가 남는다.
  4. 합치기(텍스처 해상도) — RGB = 컨셉(구멍 메운 것), 알파 = codex 알파. 단 안쪽(가장자리에서 짧은 변 4 % 안 · 장식선 아님) = interior_alpha,
     컨셉 장식선(codex 실루엣 LINE_NEAR px 안 · 글자 구멍 밖) = 1(codex 가 조금 어긋나게 그린 선도 컨셉 자리에 선다),
     실루엣 가장 바깥 띠의 비장식선 픽셀 · 바깥은 codex 색(장면이 섞인 컨셉 픽셀을 쓰지 않음).
같은 입력 → 같은 바이트(난수 없음).
"""
from __future__ import annotations

import numpy as np

from core import color

SHIFT_MAX = 6
SHIFT_MIN_GAIN = 0.02
MIN_SILHOUETTE_IOU = 0.85
RECT_FILL = 0.97            # 컨셉 모양이 위젯 상자의 이만큼 이상이면 사각 패널 — 실루엣 = 상자([실측] 체인 패널 0.995 ~ 0.999, 배너 0.74 · 게이지 0.79)
EDGE_FRAC = 0.04            # postprocess.INTERIOR_EDGE_FRAC 과 같은 '안쪽' 정의
HOLE_PAD = 6
HOLE_WIDEN = 2              # 1b 후속 G2 — 글자 획이 상자 좌우 끝에 걸치면 그쪽을 넓혀 다시 잡는 횟수
HOLE_NEAR = 6               # 획 안쪽에서 이 거리 안의 '바탕과 다른' 픽셀(어두운 테 · 안티앨리어싱 · 빛)도 글자
HOLE_MIN_DL = 6.0
HOLE_GROW = 6
HOLE_GLOW_K = 1.5
LINE_NEAR = 3
FILL_SEARCH = 12            # 구멍 끝에서 성한 픽셀을 찾는 거리


class ConceptPixelsError(ValueError):
    pass


def _dilate(mask, r: int):
    import cv2
    if r <= 0:
        return np.asarray(mask, bool)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(np.asarray(mask, np.uint8), k) > 0


def _shift(mask, dx: int, dy: int):
    out = np.zeros_like(mask)
    h, w = mask.shape[:2]
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = mask[ys, xs]
    return out


def _f1(ref, got, ref_d, got_d) -> float:
    p = float((got & ref_d).sum() / max(1, got.sum()))
    r = float((ref & got_d).sum() / max(1, ref.sum()))
    return 2 * p * r / (p + r) if p + r else 0.0


def register(concept_lines, tex_lines, max_shift: int = SHIFT_MAX) -> dict:
    """codex 장식선을 (dx, dy) 옮겼을 때 컨셉 장식선과의 F1(허용 1 px)이 가장 큰 이동 — F1 이 0.01 안에서 같으면 허용 없는 겹침(IoU)이 큰 것,
    그것도 같으면 작은 이동. (굵은 선은 허용 1 px F1 이 여러 이동에서 거의 같고, codex 에 없는 컨셉 장식이 1 px 옆을 조금 더 높게 만든다.)"""
    cd = _dilate(concept_lines, 1)
    td = _dilate(tex_lines, 1)
    cl = np.asarray(concept_lines, bool)
    rows = []
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            t = _shift(tex_lines, dx, dy)
            u = (cl | t).sum()
            rows.append((_f1(cl, t, cd, _shift(td, dx, dy)), float((cl & t).sum() / u) if u else 0.0, dx, dy))
    f0 = next(r[0] for r in rows if r[2] == 0 and r[3] == 0)
    top = max(r[0] for r in rows)
    f, _, bx, by = max((r for r in rows if r[0] >= top - 0.01), key=lambda r: (round(r[1], 4), -(abs(r[2]) + abs(r[3]))))
    use = f - f0 >= SHIFT_MIN_GAIN
    return {"shift_px": [bx, by] if use else [0, 0], "best_shift_px": [bx, by], "line_f1_before": round(f0, 4), "line_f1_best": round(f, 4), "applied": bool(use)}


def frame_lines(concept_rgb, sil, edge_px: float):
    """테두리에 이어진 장식선 덩어리 — 컨셉 장식선(3×3 넓힘)의 8-연결 덩어리 중 실루엣 가장자리 띠(edge_px + 2)에 닿는 것."""
    import cv2
    from gen import fidelity
    lm = cv2.dilate(fidelity.line_mask(concept_rgb).astype(np.uint8), np.ones((3, 3), np.uint8))
    _, lab = cv2.connectedComponents(lm, connectivity=8)
    P = 8
    dist_in = cv2.distanceTransform(cv2.copyMakeBorder(np.asarray(sil, np.uint8), P, P, P, P, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[P:-P, P:-P]
    ring = (dist_in > 0) & (dist_in <= edge_px + 2)
    ids = np.unique(lab[ring & (lm > 0)])
    return np.isin(lab, ids[ids > 0])


def edge_ring(sil, edge_px: float):
    """실루엣 가장자리 띠(안쪽 edge_px + 2 px) — 테두리 자리."""
    import cv2
    P = 8
    dist_in = cv2.distanceTransform(cv2.copyMakeBorder(np.asarray(sil, np.uint8), P, P, P, P, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[P:-P, P:-P]
    return (dist_in > 0) & (dist_in <= edge_px + 2)


def text_holes(concept_rgb, texts, frame_mask, excludes=(), ring=None, drop_frame_touch: bool = False) -> tuple[np.ndarray, list[dict]]:
    """texts: [{"id", "box": [x, y, w, h] (이 조각 좌표), "glow": px}] · excludes: [[x, y, w, h]] · ring: 테두리 띠(edge_ring) → (구멍 마스크, 기록).
    drop_frame_touch(1b 후속 H2 오리기만)면 지키는 테두리 장식선(frame_mask 2 px 넓힘)에 닿는 획 덩어리를 통째로 뺀다 — 테두리에 이어진 모서리 장식이다
    [실측 H2 끝 run — 단색 전투 HUD R184545] analyze 가 체인 패널 글자 상자를 패널 폭 전체로 잡자 금색 모서리 장식이 글자 획으로 잡혀(ink_box 13 ~ 306)
    줄 보간이 장식을 가로로 번지게 했고, OCR 이 그 줄을 글자로 봐 baked_text 게이트가 4 번 실패했다.
    ring 에 닿는 획 덩어리는 글자가 아니라 테두리다 — [실측 G 끝 run 2] 체인 패널 오른쪽 테두리 가운데는 연보라 선(채도 낮아 장식선 판정 밖)이라
    패널 폭 글자 상자('체인')의 획 검출이 그 조각을 글자로 잡아 메웠다(y 214 ~ 235 끊김)."""
    import cv2
    from gen import fidelity
    rgb = np.asarray(concept_rgb, float)[:, :, :3]
    H, W = rgb.shape[:2]
    hole = np.zeros((H, W), bool)
    keep = _dilate(frame_mask, 2)
    recs = []
    for t in texts:
        x, y, w, h = (float(v) for v in t["box"])
        x0, y0 = max(0, int(np.floor(x - HOLE_PAD))), max(0, int(np.floor(y - HOLE_PAD)))
        x1, y1 = min(W, int(np.ceil(x + w + HOLE_PAD))), min(H, int(np.ceil(y + h + HOLE_PAD)))
        if x1 - x0 < 4 or y1 - y0 < 4:
            recs.append({"widget": t.get("id"), "box": [x0, y0, x1 - x0, y1 - y0], "skipped": "box outside the frame"})
            continue
        # analyze 상자가 글자보다 좁으면 획이 상자 좌우 끝에 걸친다 — text_ink 는 끝에 닿은 덩어리를 지우므로 지우기 전 획으로 보고 그쪽을 넓혀 다시
        # (획 높이 × 0.5 씩 HOLE_WIDEN 번, 다른 글자 상자 앞까지 — style._concept_ink 와 같은 생각)
        # [실측 G2 전투 HUD run 2] '체인' 상자 46 px · 컨셉 글자 62 px → 양끝 획이 체인 패널 텍스처에 남아 렌더 글자 옆에 조각이 보였다
        widened = 0
        for _ in range(HOLE_WIDEN):
            raw = fidelity.text_ink(rgb[y0:y1, x0:x1], drop_edges=False)
            rb = fidelity.bbox_of(raw & ~keep[y0:y1, x0:x1]) if raw is not None else None
            if not rb:
                break
            left, right = rb[0] <= 0 and x0 > 0, rb[0] + rb[2] >= x1 - x0 and x1 < W
            if not (left or right):
                break
            e = max(HOLE_PAD, int(round(0.5 * rb[3])))
            nx0, nx1 = (max(0, x0 - e) if left else x0), (min(W, x1 + e) if right else x1)
            for o in texts:
                if o is t:
                    continue
                ox, oy, ow, oh = (float(v) for v in o["box"])
                if min(oy + oh, y1) - max(oy, y0) > 0 and not (ox < x1 and ox + ow > x0):
                    if ox >= x1:
                        nx1 = min(nx1, int(ox))
                    if ox + ow <= x0:
                        nx0 = max(nx0, int(np.ceil(ox + ow)))
            if (nx0, nx1) == (x0, x1):
                break
            x0, x1, widened = nx0, nx1, widened + 1
        rec = {"widget": t.get("id"), "box": [x0, y0, x1 - x0, y1 - y0], **({"widened": widened} if widened else {})}
        sub = rgb[y0:y1, x0:x1]
        ink = fidelity.text_ink(sub)
        if ink is not None and drop_frame_touch and keep[y0:y1, x0:x1].any():
            # 글자 상자 가로 가운데 절반에 걸치지 않는 덩어리만 — 가운데 덩어리(키 배지 테두리처럼 획으로 잡힌 것)는 그대로 두어 판 · 메우기가 그 자리를 덮게
            # [실측 H2 오프라인 — 조작 안내 T 배지: 통째로 빼자 띠 텍스처에 'T' 가 남았다]
            n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
            mx0, mx1 = x + 0.25 * w - x0, x + 0.75 * w - x0
            touch = [i for i in np.unique(lab[ink & keep[y0:y1, x0:x1]]) if i > 0 and (
                stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] <= mx0 or stats[i, cv2.CC_STAT_LEFT] >= mx1)]
            if touch:
                ink = ink & ~np.isin(lab, touch)
                rec["frame_pieces_dropped"] = int(len(touch))
        if ink is not None:
            ink = ink & ~keep[y0:y1, x0:x1]
            if ring is not None:
                n, lab = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)
                touch = np.unique(lab[ink & ring[y0:y1, x0:x1]])
                touch = touch[touch > 0]
                if len(touch):
                    ink = ink & ~np.isin(lab, touch)
                    rec["border_pieces_dropped"] = int(len(touch))
        if ink is None or int(ink.sum()) < fidelity.INK_MIN_PIXELS:
            recs.append({**rec, "skipped": "no glyph pixels in the concept"})
            continue
        L = color.srgb_to_lab(sub)[..., 0]
        far = ~_dilate(ink, 2 * HOLE_NEAR) & ~keep[y0:y1, x0:x1]
        bg = float(np.median(L[far])) if far.any() else float(np.median(L[~ink]))
        m = (ink | ((np.abs(L - bg) > HOLE_MIN_DL) & _dilate(ink, HOLE_NEAR))) & ~keep[y0:y1, x0:x1]
        r = HOLE_GROW + int(round(HOLE_GLOW_K * float(t.get("glow") or 0)))
        sub_hole = _dilate(m, r) & ~keep[y0:y1, x0:x1]
        hole[y0:y1, x0:x1] |= sub_hole
        bb = fidelity.bbox_of(ink)
        recs.append({**rec, "ink_box": [bb[0] + x0, bb[1] + y0, bb[2], bb[3]], "grow_px": r, "hole_px": int(sub_hole.sum())})
    for ex in excludes:
        x, y, w, h = (float(v) for v in ex)
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(W, int(np.ceil(x + w))), min(H, int(np.ceil(y + h)))
        if x1 > x0 and y1 > y0:
            hole[y0:y1, x0:x1] |= ~keep[y0:y1, x0:x1]
            recs.append({"exclude_box": [x0, y0, x1 - x0, y1 - y0]})
    return hole, recs


def row_fill(img, hole, avoid=None) -> np.ndarray:
    """구멍을 줄마다 왼쪽 · 오른쪽 가장 가까운 성한 픽셀(구멍 · avoid 아님, FILL_SEARCH px 안) 3 개 중앙값 사이 직선 보간.
    한쪽만 있으면 그 색, 둘 다 없으면 구멍 밖 전체 중앙값."""
    out = np.asarray(img, float).copy()
    H, W = hole.shape
    valid = ~hole if avoid is None else (~hole & ~avoid)
    fallback = np.median(out[valid], axis=0) if valid.any() else np.median(out.reshape(-1, out.shape[2]), axis=0)

    def side(y, start, step):
        got, x = [], start
        while 0 <= x < W and abs(x - start) <= FILL_SEARCH and len(got) < 3:
            if valid[y, x]:
                got.append(out[y, x])
            x += step
        return np.median(got, axis=0) if got else None
    for y in range(H):
        xs = np.where(hole[y])[0]
        if len(xs) == 0:
            continue
        for run in np.split(xs, np.where(np.diff(xs) > 1)[0] + 1):
            a, b = side(y, int(run[0]) - 1, -1), side(y, int(run[-1]) + 1, 1)
            if a is None and b is None:
                a = b = fallback
            a = b if a is None else a
            b = a if b is None else b
            t = (np.arange(len(run)) + 1) / (len(run) + 1)
            out[y, run] = a[None] * (1 - t[:, None]) + b[None] * t[:, None]
    return out


def transplant(concept_rgb, texture, texts=(), excludes=(), interior_alpha: float = 0.9) -> tuple:
    """concept_rgb: 위젯 상자의 컨셉 조각(numpy RGB, 위젯 해상도) · texture: 따온 텍스처(PIL RGBA, 에셋 크기 — 위젯 상자 1:1)
    → (PIL RGBA 같은 크기, 기록). 못 하면 ConceptPixelsError(이유)."""
    import cv2
    from PIL import Image
    from gen import fidelity
    concept = np.asarray(concept_rgb, float)[:, :, :3]
    h, w = concept.shape[:2]
    tex = np.asarray(texture.convert("RGBA"), float)
    TH, TW = tex.shape[:2]
    sx, sy = TW / float(w), TH / float(h)

    def at_widget(arr):
        return np.asarray(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA").resize((w, h), Image.Resampling.LANCZOS), float)
    boxes = np.zeros((h, w), bool)
    for t in texts:
        x, y, bw, bh = (int(round(float(v))) for v in t["box"])
        boxes[max(0, y):max(0, y + bh), max(0, x):max(0, x + bw)] = True
    cl = fidelity.line_mask(concept)
    shape_c, how = fidelity.fill_shape(cl)
    box_fill = round(float(shape_c.mean()), 4)
    rect = box_fill >= RECT_FILL
    tw_ = at_widget(tex)
    if rect:
        # 위젯 상자를 꽉 채우는 사각 패널 — 실루엣 = 상자 그대로(codex 와 무관 · run 마다 같음). [실측 F run 5] codex 가 옆선을 오목하게 따와
        # 실루엣 IoU 0.804 — codex 실루엣을 쓰면 물러날 수밖에 없었다
        reg = {"shift_px": [0, 0], "applied": False, "note": "rectangular panel — the silhouette is the widget box"}
        tex[:, :, 3] = 255.0
    else:
        reg = register(cl & ~boxes, fidelity.line_mask(tw_[:, :, :3]) & (tw_[:, :, 3] > 128) & ~boxes)
        if reg["applied"]:
            dx, dy = reg["shift_px"]
            M = np.float32([[1, 0, dx * sx], [0, 1, dy * sy]])
            tex = cv2.warpAffine(tex.astype(np.float32), M, (TW, TH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)).astype(float)
            tw_ = at_widget(tex)
    sil_w = np.ones((h, w), bool) if rect else tw_[:, :, 3] > 128
    if not sil_w.any():
        raise ConceptPixelsError("the extracted texture has no opaque silhouette")
    sil_iou = fidelity.iou(shape_c, tw_[:, :, 3] > 128)
    rec: dict = {"registration": reg, "silhouette_iou": sil_iou, "concept_shape_from": how, "concept_box_fill": box_fill,
                 "silhouette_from": "widget box (rectangular panel)" if rect else "codex", "size": [TW, TH], "widget_size": [w, h]}
    if not rect and sil_iou < MIN_SILHOUETTE_IOU:
        raise ConceptPixelsError(f"codex silhouette vs concept shape IoU {sil_iou} < {MIN_SILHOUETTE_IOU} — the extraction does not match the concept")
    bb = fidelity.bbox_of(sil_w)
    edge_px = max(2.0, EDGE_FRAC * min(bb[2], bb[3]))
    fl = frame_lines(concept, sil_w, edge_px)
    hole, hole_recs = text_holes(concept, texts, fl, excludes, ring=edge_ring(sil_w, edge_px))
    filled = row_fill(concept, hole, avoid=_dilate(cl, 1))
    # 텍스처 해상도로 — 컨셉은 위젯 해상도라 늘린다(그려질 때 다시 위젯 크기로 준다)
    up = lambda a: np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").resize((TW, TH), Image.Resampling.BICUBIC), float)   # noqa: E731
    upm = lambda m: np.asarray(Image.fromarray(np.asarray(m, np.uint8) * 255, "L").resize((TW, TH), Image.Resampling.NEAREST)) > 127   # noqa: E731
    filled_t = up(filled)
    hole_t = _dilate(upm(hole), 1)
    s = max(sx, sy)
    A = tex[:, :, 3]
    sil_t = A > 128
    core_t = ~_dilate(~sil_t, max(1, int(round(s))))
    lines_t = fidelity.line_mask(up(concept)) & _dilate(sil_t, int(round(LINE_NEAR * s))) & ~hole_t
    rgb = filled_t.copy()
    use_codex = np.zeros_like(sil_t) if rect else (sil_t & ~core_t & ~lines_t) | (~sil_t & ~lines_t)
    rgb[use_codex] = tex[:, :, :3][use_codex]
    sil2 = sil_t | lines_t
    P = 8
    dist_in = cv2.distanceTransform(cv2.copyMakeBorder(sil2.astype(np.uint8), P, P, P, P, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[P:-P, P:-P]
    lines_d = _dilate(lines_t, 1) & sil2
    interior = (dist_in > edge_px * s) & ~lines_d
    alpha = A.copy()
    alpha[interior] = float(interior_alpha) * 255.0
    alpha[lines_t] = 255.0
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha, 0, 255)]).round().astype(np.uint8)
    rec.update(edge_px=round(edge_px, 1), frame_line_px=int(fl.sum()), texts=hole_recs, hole_ratio=round(float(hole.sum() / (w * h)), 4),
               lines_added_outside_px=int((lines_t & ~sil_t).sum()), interior_ratio=round(float(interior.mean()), 4), interior_alpha=float(interior_alpha),
               changed_ratio=round(float((~use_codex & sil2).mean()), 4))
    return Image.fromarray(out, "RGBA"), rec
