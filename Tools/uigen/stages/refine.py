"""refine — raw 를 검사 · 정리해 assets/final/ 과 manifest.json 으로 (설계 §2-2 · §7 'refine').

procedural(1a): 크기 일치 · 알파 · 9-slice margin(spec 값, 없으면 모양에서 계산) · 압축. 글자를 그리지 않으므로 OCR '해당 없음'.
생성 이미지(codex — 1b-5, gen/postprocess · core/ocr):
  배경 제거(이미 투명이면 그대로, 아니면 테두리 색 flood fill) → 여백 자르기 → spec 크기로(9-slice 는 늘림, 나머지는 비율 유지 + 투명 여백) →
  9-slice margin 추정(가운데와 같은 열 · 행 띠 — 실패하면 spec 값) → 알파 검사 → OCR(구운 글자 검출 상자 수 → ocr_text).
  margin 을 추정했으면 spec 의 그 에셋 margin 과 그 에셋을 쓰는 box · border 브러시 margin 을 추정값으로 바꾼다(build 가 브러시 margin 을 쓴다) —
  바꾼 것은 refine.json 에 남는다. 글자가 검출되면 실패가 아니라 기록이다 — verify 의 baked_text 게이트가 잡고 fixer 가 재생성을 낸다.
  margin 추정은 축마다 따로(1b 후속 A) — 실패한 축만 spec 값(source mixed).
컨셉에서 따온 것(source_mode: extract — 1b 후속 A): 먼저 편집 결과에서 요소 상자만 되자르고(gen.jsonl extract 의 영역 · 요소 상자), 위 다듬기를 그대로
  거친 뒤 frame · panel_bg 는 안쪽 알파(pipeline.yaml extract.interior_alpha — built-in image_gen 이 반투명을 못 내서)를 넣는다. 마지막에 충실도
  (gen/fidelity — 비율 · 실루엣 · 장식선 · 대표색 ΔE00, 기록만)와 나란히 그림 assets/compare/<id>.png 를 남긴다.
  따온 에셋을 쓰는 box/border 브러시는 위젯 크기가 고정이면 image 로 바꾼다(pipeline.yaml extract.fixed_size_draw_as — refine.json brush_updates).
  (1b 후속 G) extract.concept_pixels 면 안쪽 한 색 칠하기 대신 컨셉 픽셀을 옮겨 심는다(gen/concept_pixels — codex 는 실루엣만, 색 · 모서리 장식 ·
  안쪽 빛은 컨셉 그대로, 글자 자리는 메움). 게이지가 겹친 프레임 · 실루엣이 컨셉과 안 맞는 판 · 옮긴 뒤 OCR 이 글자 자국을 잡은 판은 한 색 칠하기로
  물러난다(refine.json concept_pixels.reason).
(1b 후속 H) extract.cutout 이면 위 따오기 대신 컨셉 픽셀을 오린다(_cut_entry · gen/cutout): 알파는 ⓐ ⓑ normalize 의 reference_alpha,
  ⓒ GrabCut(codex 편집 결과는 실루엣 시드로만 — 작은 요소 · ⓐ ⓑ 는 codex 없이), 색은 컨셉 그대로, 가려진 자리는 줄 보간. 안쪽 한 색 칠하기 ·
  IoU 물러남은 이 길에 없다. 실루엣이 위젯 상자 밖으로 이어지면(넘침) 텍스처 상자를 넓히고 주인 브러시는 비운 채 캔버스 직속 장식 Image
  (<주인>Overhang)로 그린다(refine.json overhang_updates — 다시 다듬을 때 걷고 새로).
압축(spec → 종류별 기본 → 전체 기본). 출력: assets/final/<id>.png · manifest.json · refine.json(에셋별 처리 기록).
"""
from __future__ import annotations

import hashlib
import json
import shutil

from core import config
from core import png
from core import schema
from core import spec as spec_mod
from gen import procedural
from stages import StageError

NEEDS_ALPHA = {"frame", "panel_bg", "ornament", "icon"}
OCR_NOT_APPLICABLE = "n/a — procedural 에셋은 글자를 그리지 않는다(Phase 1a). OCR 은 생성 이미지가 들어오는 1b 부터"
MARGIN_UPDATE_MIN = 0.02


def _procedural_entry(run, asset: dict, raw, backend: str) -> tuple[dict, dict]:
    aid = asset["asset_id"]
    w, h, rgba = png.read_rgba(raw)
    if [w, h] != [int(v) for v in asset["size"]]:
        raise StageError("SIZE_MISMATCH", f"'{aid}' is {w}x{h}, spec says {asset['size']}", asset=aid)
    has_alpha = any(rgba[i] < 255 for i in range(3, len(rgba), 4))
    if asset.get("kind") in NEEDS_ALPHA and not has_alpha:
        raise StageError("NO_ALPHA", f"'{aid}' ({asset['kind']}) is fully opaque — HUD assets need a transparent background", asset=aid)
    margin = None
    if asset.get("nine_slice"):
        margin = asset.get("margin") or procedural.nine_slice_margin(asset)
        if margin is None:
            raise StageError("NO_MARGIN", f"'{aid}' is nine_slice but has no margin and none can be derived", asset=aid)
    final = run.path("assets", "final", f"{aid}.png")
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(raw, final)
    return ({"alpha": has_alpha, "nine_slice_margin": margin, "ocr_text": None,
             "ocr": OCR_NOT_APPLICABLE if backend == "procedural" else "pending", "size": [w, h]},
            {"asset_id": aid, "backend": backend, "steps": "copied (procedural)"})


OVERHANG_SUFFIX = "Overhang"   # 1b 후속 H — 넘침 장식 Image 의 id = <주인 id>Overhang


def overhang_decos(spec: dict | None) -> set[str]:
    """refine 이 넣은 넘침 장식 Image(1b 후속 H) — id 가 <주인>Overhang 이고 주인 브러시가 같은 에셋의 draw_as none 인 것."""
    index = spec_mod.widget_index(spec or {"widgets": []})
    out = set()
    for w in (spec or {}).get("widgets", []):
        wid = w["id"]
        if not wid.endswith(OVERHANG_SUFFIX) or len(wid) == len(OVERHANG_SUFFIX):
            continue
        owner = index.get(wid[:-len(OVERHANG_SUFFIX)])
        aid = ((w.get("style") or {}).get("brush") or {}).get("asset")
        if owner and aid and any(isinstance(b, dict) and b.get("asset") == aid and b.get("draw_as") == "none"
                                 for k, b in (owner.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS):
            out.add(wid)
    return out


def asset_users(spec: dict | None, aid: str) -> list[dict]:
    """이 에셋을 브러시로 쓰는 위젯(넘침 장식 Image 는 빼고)."""
    decos = overhang_decos(spec)
    return [w for w in (spec or {}).get("widgets", []) if w["id"] not in decos
            and any(isinstance(b, dict) and b.get("asset") == aid for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS)]


def extract_target_box(spec: dict | None, asset: dict, extract: dict) -> list[float]:
    """따온 텍스처를 되자를 상자(reference 좌표) — 이 에셋을 브러시로 쓰는 위젯의 bbox_intent(텍스처가 그 위젯에 1:1 로 그려지게),
    여럿이면 codex 입력 영역과 가장 많이 겹치는 위젯(그 자리에서 따왔다), 입력 영역과 겹치는 위젯이 없으면 ref_bbox, 그것도 없으면 입력의 요소 상자.
    [실측 G2 파티 HUD] 파티원 슬롯 3개가 같은 문장 테두리 · 게이지 프레임을 쓰는데 첫 위젯 상자로 되자르다가 입력 영역 밖이라 상자가 뒤집혔다(오류).
    (1b 후속 H) 넘침 장식 Image 는 후보가 아니다(주인 위젯 상자가 기준)."""
    region = [float(v) for v in extract["region"]]
    best, best_a = None, 0.0
    decos = overhang_decos(spec)
    for w in (spec or {}).get("widgets", []):
        if w["id"] in decos:
            continue
        for key, brush in (w.get("style") or {}).items():
            if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset") == asset["asset_id"] and w.get("bbox_intent"):
                b = [float(v) for v in w["bbox_intent"]]
                a = (max(0.0, min(b[0] + b[2], region[0] + region[2]) - max(b[0], region[0]))
                     * max(0.0, min(b[1] + b[3], region[1] + region[3]) - max(b[1], region[1]))) / max(1e-6, b[2] * b[3])
                if a > best_a:
                    best, best_a = b, a
    if best is not None:
        return best
    if asset.get("ref_bbox"):
        return [float(v) for v in asset["ref_bbox"]]
    rx, ry = extract["region"][:2]
    ex, ey, ew, eh = extract["element"]
    return [rx + ex, ry + ey, ew, eh]


MARK_TEXT_OVERLAP = 0.2    # 검출 상자 넓이의 이 비율 이상이 글자 위젯 상자와 겹치면 구운 글자


def _split_marks(det: dict, box, size, spec: dict | None) -> tuple[list[dict], list[dict]]:
    """따온 에셋(위젯 상자 1:1)의 OCR 검출 상자 → (글자 위젯 자리와 겹치는 것, 안 겹치는 것) — 상자는 컨셉 좌표로 바꿔 기록."""
    sx, sy = float(box[2]) / max(1, size[0]), float(box[3]) / max(1, size[1])
    texts = [w["bbox_intent"] for w in (spec or {}).get("widgets", []) if w.get("type") == "TextBlock" and w.get("bbox_intent")]
    baked, decor = [], []
    for b in det.get("boxes", []):
        x, y, w, h = (float(v) for v in b["box"])
        r = [round(box[0] + x * sx, 1), round(box[1] + y * sy, 1), round(w * sx, 1), round(h * sy, 1)]
        area = max(1e-6, r[2] * r[3])
        hit = max((max(0.0, min(r[0] + r[2], t[0] + t[2]) - max(r[0], t[0])) * max(0.0, min(r[1] + r[3], t[1] + t[3]) - max(r[1], t[1])) / area
                   for t in texts), default=0.0)
        (baked if hit >= MARK_TEXT_OVERLAP else decor).append({"box": r, "score": b.get("score"), "text_overlap": round(hit, 3)})
    return baked, decor


def _generated_entry(run, asset: dict, raw, backend: str, gen_rec: dict | None = None, spec: dict | None = None) -> tuple[dict, dict]:
    from core import ocr
    from gen import postprocess as pp
    aid = asset["asset_id"]
    try:
        im = pp.load_rgba(raw)
    except OSError as exc:
        raise StageError("RAW_UNREADABLE", f"{raw}: {exc}", asset=aid) from exc
    log = {"asset_id": aid, "backend": backend, "raw_size": [im.width, im.height]}
    extract = (gen_rec or {}).get("extract") if (gen_rec or {}).get("source_mode") == "extract" else None
    if extract and (run.cfg.get("extract") or {}).get("cutout", False) and run.path("reference.png").is_file():
        return _cut_entry(run, asset, raw, backend, gen_rec, spec, log)
    cropped, box = None, None
    if extract:
        # [실측 B run] 요소 상자 + 여유로 되자른 뒤 trim(알파 > 8)하면 끝 캡 바깥의 옅은 빛이 남아 텍스처 안의 프레임이 위젯보다 작아지고
        # 캡이 27 px 안쪽에 그려졌다(게이지 채움이 덮음) → 위젯 상자 그대로 되자르고 trim 하지 않는다(텍스처 = 위젯 1:1, 컨셉 위치 그대로).
        log["source_mode"] = "extract"
        box = extract_target_box(spec, asset, extract)
        rx, ry = extract["region"][:2]
        im, log["crop_back"] = pp.crop_back(im, extract["region"], [box[0] - rx, box[1] - ry, box[2], box[3]], pad=0)
        log["crop_back"]["target_box"] = box
        cropped = im.copy()
    im, log["background"] = pp.remove_background(im)
    if extract:
        log["trim_bbox"] = "skipped (extract — the texture maps 1:1 onto the widget box)"
        if not pp.alpha_stats(im)["transparent_ratio"] < 1.0:
            raise StageError("EMPTY_IMAGE", f"'{aid}' has no visible content in its widget box", asset=aid)
    else:
        im, log["trim_bbox"] = pp.trim(im)
        if log["trim_bbox"] is None:
            raise StageError("EMPTY_IMAGE", f"'{aid}' has no visible content after background removal", asset=aid)
    im, log["fit"] = pp.fit(im, asset["size"], stretch=bool(asset.get("nine_slice")) or bool(extract))
    ext_cfg = run.cfg.get("extract") or {}
    fitted, flat = None, None
    if extract and asset.get("kind") in ("frame", "panel_bg") and ext_cfg.get("interior_alpha") is not None:
        fitted = im
        moved = None
        if ext_cfg.get("concept_pixels"):
            moved, log["concept_pixels"] = _concept_pixels(run, spec, asset, box, im, float(ext_cfg["interior_alpha"]))
        flat, interior_log = _interior(im, ext_cfg)
        if moved is not None:
            im = moved
        else:
            im, log["interior"] = flat, interior_log
    st = pp.alpha_stats(im)
    log["alpha"] = st
    if asset.get("kind") in NEEDS_ALPHA and not st["has_alpha"]:
        raise StageError("NO_ALPHA", f"'{aid}' ({asset['kind']}) is still fully opaque after background removal", asset=aid)
    margin, est = None, None
    if asset.get("nine_slice"):
        # 옮겨 심은 텍스처는 안쪽에 컨셉 결 · 빛이 있어 띠 판정이 흔들린다 — margin 은 안쪽 한 색 판(장식 자리는 같음)에서 잰다(1b 후속 G)
        est = pp.estimate_nine_slice(flat if flat is not None else im)
        margin, source = pp.merge_margin(est, asset.get("margin"))
        if margin is None:
            raise StageError("NO_MARGIN", f"'{aid}' is nine_slice, no margin in the spec for the axis that could not be estimated ({est})", asset=aid)
        log["margin"] = {"spec": asset.get("margin"), "estimated": est, "used": margin, "source": source}
    final = run.path("assets", "final", f"{aid}.png")
    final.parent.mkdir(parents=True, exist_ok=True)
    im.save(final, format="PNG")
    try:
        det = ocr.detect(final)
    except ocr.OcrError as exc:
        raise StageError("OCR_UNAVAILABLE", str(exc), asset=aid) from exc
    if det["count"] and (log.get("concept_pixels") or {}).get("applied") and fitted is not None and _split_marks(det, box, (im.width, im.height), spec)[0]:
        # 글자 구멍이 덜 메워져 컨셉 글자 자국이 남았다 — 옮겨 심기를 접고 안쪽 한 색 칠하기로(baked_text 게이트 → 재생성이 같은 자국을 되풀이하지 않게)
        log["concept_pixels"].update(applied=False, reason=f"OCR found {det['count']} text-like box(es) after moving the concept pixels — fell back to the flat interior",
                                     ocr=det)
        im, log["interior"] = flat, interior_log
        im.save(final, format="PNG")
        try:
            det = ocr.detect(final)
        except ocr.OcrError as exc:
            raise StageError("OCR_UNAVAILABLE", str(exc), asset=aid) from exc
        log["alpha"] = pp.alpha_stats(im)
    log["ocr"] = det
    count, top = det["count"], det["max_score"]
    if extract and count:
        # 1b 후속 G2 — 컨셉에서 따온 에셋의 검출 상자는 컨셉 좌표로 옮겨 글자 위젯 자리와 겹치는 것만 '구운 글자'로 센다 — 겹치지 않는 것은 컨셉에
        # 그려진 장식(키 · 마우스 아이콘 등)이다. [실측 G2 조작 안내] 왼쪽 라벨 띠의 원형 마우스 · 스페이스 아이콘 3개가 0.72 ~ 0.75 로 잡혀 재생성 3번 뒤 실패
        baked, decor = _split_marks(det, box, (im.width, im.height), spec)
        if decor:
            log["ocr_decor"] = {"count": len(decor), "boxes": decor,
                                "note": "text-like marks outside every text widget box — drawn in the concept (icons), not baked labels"}
            count = len(baked)
            top = max((b["score"] for b in baked), default=0.0)
    if extract:
        log["fidelity"] = _extract_fidelity(run, aid, box, cropped, im)
    text = "" if count == 0 else f"{count} text-like box(es), max score {top}"
    return ({"alpha": st["has_alpha"], "nine_slice_margin": margin, "ocr_text": text,
             "ocr": f"{det['engine']} — detection boxes with score ≥ {det['min_score']} and area ≥ {det['min_area_px']} px", "size": [im.width, im.height]},
            log)


def _interior(im, ext_cfg: dict):
    from gen import postprocess as pp
    return pp.interior_fill(im, float(ext_cfg["interior_alpha"]), float(ext_cfg.get("interior_max_lightness", pp.INTERIOR_MAX_L)),
                            flatten=bool(ext_cfg.get("interior_flatten", True)))


def _overlap(a, b) -> float:
    """b 가 a 와 겹치는 넓이 / b 넓이."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / max(1e-6, b[2] * b[3])


CHILD_IMAGE_MAX = 0.5      # 뺄 상자 = 프레임 넓이의 이 비율 이하인 자식 이미지(아이콘) — 더 크면 뒤에 깔린 빛 · 배경


RUNTIME_INSIDE_MIN = 0.5   # 런타임 이미지(초상화)는 그 넓이의 이만큼 이상이 이 요소 상자 안일 때만 이 요소의 '속'이다(초상화 테두리)


def runtime_boxes(spec: dict | None, box) -> list[list[float]]:
    """이 요소 상자(reference)의 속인 런타임 이미지(binding kind image) 자리(이 조각 좌표) — 1b 후속 H 오리기에서 투명하게 비운다(그 자리는 게임이
    넣는 그림이 보인다). 이 요소가 큰 런타임 이미지 위에 얹힌 작은 것(초상화 모서리 배지 · 옆 아이콘)이면 속이 아니다
    [실측 H 오프라인 — G2 파티 HUD 초상화 상자가 배지 · 검 아이콘 상자를 덮어 문양이 지워졌다]."""
    out = []
    for w in (spec or {}).get("widgets", []):
        bb = w.get("bbox_intent")
        if bb and w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image" and _overlap(bb, box) > 0 \
                and _overlap(box, bb) >= RUNTIME_INSIDE_MIN:
            out.append([float(bb[0]) - float(box[0]), float(bb[1]) - float(box[1]), float(bb[2]), float(bb[3])])
    return out


def concept_pixel_inputs(spec: dict | None, asset: dict, box, gauge_holes: bool = False,
                         keep_cut_children: bool = False) -> tuple[list[dict], list[list[float]], str | None, list[dict]]:
    """옮겨 심기에 넘길 글자 상자 · 뺄 상자(이 조각 좌표) · 건너뛸 이유 · 게이지(1b 후속 G · G2).
    게이지(ProgressBar)가 겹친 프레임: 채움이 컨셉 모양(procedural concept_fill — 채움 측정값이 있음)이면 옮겨 심되 채움이 구워진 트랙 자리를
    빈 트랙 색으로 메운다(gen/concept_fill.unfilled_track — 컨셉은 채움 한 상태만 보여 준다). 다른 채움이면 예전처럼 건너뛴다.
    뺄 상자는 컨셉에 보이는 자식 이미지(아이콘)만 — 숨은 이미지(visibility collapsed · hidden)와 프레임 넓이의 CHILD_IMAGE_MAX 넘는 이미지
    (뒤에 깔린 빛)는 빼지 않는다(빼면 프레임 전체가 구멍이 된다 — 오의 준비 빛은 게이지 프레임보다 크다).
    gauge_holes(1b 후속 H 오리기)면 채움을 컨셉에서 못 잰 게이지는 건너뛰지 않고 그 막대 상자를 구멍(줄 보간)으로 — 한 색 칠하기 물러남이 없다.
    keep_cut_children(1b 후속 H 오리기)면 컨셉에서 따오는(extract) 자식 이미지 자리는 구멍으로 두지 않는다 — 자식 텍스처도 같은 컨셉 픽셀이라
    위에 그대로 겹친다(메우면 줄 보간 줄무늬가 자식 실루엣 밖으로 보였다 [실측 H 오프라인 — 조작 안내 엠블럼 가운데]). 런타임 이미지 · 새로 그리는
    자식은 그대로 구멍."""
    bx, by = float(box[0]), float(box[1])
    users = {w["id"] for w in (spec or {}).get("widgets", []) for k, b in (w.get("style") or {}).items()
             if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset") == asset["asset_id"]}
    assets = {a["asset_id"]: a for a in (spec or {}).get("assets", [])}
    texts, excludes, gauges = [], [], []
    for w in (spec or {}).get("widgets", []):
        bb = w.get("bbox_intent")
        if not bb or w["id"] in users or _overlap(box, bb) <= 0:
            continue
        local = [float(bb[0]) - bx, float(bb[1]) - by, float(bb[2]), float(bb[3])]
        if w.get("type") == "ProgressBar" and _overlap(box, bb) >= 0.2:
            fill = (w.get("style") or {}).get("fill")
            proc = (assets.get(fill.get("asset")) or {}).get("procedural") or {} if isinstance(fill, dict) else {}
            if proc.get("shape") != "concept_fill":
                if gauge_holes:
                    excludes.append(local)
                    gauges.append({"widget": w["id"], "hole": True})
                    continue
                return [], [], f"gauge {w['id']} sits on this frame and its fill is not measured from the concept (kept the flat interior)", []
            gauges.append({"widget": w["id"], "params": proc})
            continue
        if w.get("type") == "TextBlock":
            texts.append({"id": w["id"], "box": local, "glow": float(((w.get("font") or {}).get("glow") or {}).get("size") or 0)})
        elif w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image":
            if keep_cut_children:
                continue                # 1b 후속 H 오리기 — 속인 런타임 이미지는 runtime_boxes 로 투명하게, 아니면 GrabCut 이 가른다
            excludes.append(local)      # 런타임 이미지(초상화 등) — 컨셉 그림을 프레임에 남기지 않는다(1b 후속 G2)
        elif w.get("type") == "Image" and any(isinstance(b, dict) and b.get("asset") for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS):
            if w.get("visibility") in ("collapsed", "hidden") or float(bb[2]) * float(bb[3]) > CHILD_IMAGE_MAX * float(box[2]) * float(box[3]):
                continue
            if keep_cut_children and all((assets.get(b.get("asset")) or {}).get("source_mode") == "extract"
                                         for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")):
                continue
            excludes.append(local)
    return texts, excludes, None, gauges


def _fill_tracks(arr, gauges: list[dict]):
    """채움이 구워진 게이지 트랙 자리를 빈 트랙 색으로(gen/concept_fill.unfilled_track — 1b 후속 G2) → (새 배열, 기록). 못 하면 ValueError(이유)."""
    import numpy as np
    from gen import concept_fill
    arr = arr.copy()
    tracks = []
    for g in gauges:
        if g.get("hole"):
            tracks.append({"widget": g["widget"], "hole": "fill not measured from the concept — the bar box is filled from its neighbours"})
            continue
        try:
            hole, filled = concept_fill.unfilled_track(arr, g["params"])
        except concept_fill.ConceptFillError as exc:
            raise ValueError(f"gauge {g['widget']}: {exc}") from exc
        ox, oy, ow, oh = (int(v) for v in g["params"]["frame_box"])
        sub = arr[oy:oy + oh, ox:ox + ow]
        sub[hole] = np.clip(np.round(filled[hole]), 0, 255).astype(arr.dtype)
        tracks.append({"widget": g["widget"], "frame_box": [ox, oy, ow, oh], "track_px": int(hole.sum())})
    return arr, tracks


def _concept_pixels(run, spec, asset: dict, box, im, alpha: float) -> tuple:
    """1b 후속 G — gen/concept_pixels.transplant. → (새 텍스처 또는 None, 기록)."""
    import numpy as np
    from PIL import Image
    from gen import concept_pixels as cp
    texts, excludes, skip, gauges = concept_pixel_inputs(spec, asset, box)
    if skip:
        return None, {"applied": False, "reason": skip}
    x0, y0 = int(round(box[0])), int(round(box[1]))
    x1, y1 = int(round(box[0] + box[2])), int(round(box[1] + box[3]))
    with Image.open(run.path("reference.png")) as ref:
        if x0 < 0 or y0 < 0 or x1 > ref.width or y1 > ref.height:
            return None, {"applied": False, "reason": f"widget box {list(box)} is outside the reference"}
        arr = np.asarray(ref.convert("RGB"))
    tracks = []
    if gauges:      # 1b 후속 G2 — 채움이 구워진 트랙 자리를 빈 트랙 색으로 메운 컨셉으로 옮겨 심는다
        try:
            arr, tracks = _fill_tracks(arr, gauges)
        except ValueError as exc:
            return None, {"applied": False, "reason": str(exc)}
    concept = arr[y0:y1, x0:x1]
    try:
        out, rec = cp.transplant(concept, im, texts, excludes, alpha)
    except cp.ConceptPixelsError as exc:
        return None, {"applied": False, "reason": str(exc)}
    rec.update(applied=True, concept_box=[x0, y0, x1 - x0, y1 - y0])
    if tracks:
        rec["gauge_tracks"] = tracks
    return out, rec


# ---------------------------------------------------------------------------------------------------------------------
# 1b 후속 H — 컨셉 픽셀 직접 오리기 (gen/cutout)

def _reference_layers(run, bg: str):
    """→ (곧은 색 float HxWx3, 알파 0 ~ 1 또는 None) — ⓐ ⓑ 는 normalize 의 reference_color · reference_alpha, ⓒ 는 reference.png 색 · 알파 없음."""
    import numpy as np
    from PIL import Image
    if bg in ("transparent", "flat") and run.path("reference_alpha.png").is_file() and run.path("reference_color.png").is_file():
        with Image.open(run.path("reference_color.png")) as c, Image.open(run.path("reference_alpha.png")) as a:
            return np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0
    with Image.open(run.path("reference.png")) as c:
        return np.asarray(c.convert("RGB"), float), None


def _notext_layers(run, bg: str):
    """글자 없는 판(normalize 의 reference_notext_color · reference_notext_alpha — inputs concept_notext) → (곧은 색, 알파 또는 None) 또는 None.
    ⓒ 는 알파를 쓰지 않는다(GrabCut 실루엣 그대로 — 판의 알파는 전부 1)."""
    import numpy as np
    from PIL import Image
    p = run.path("normalize.json")
    nt = ((run.read_json("normalize.json").get("background") or {}).get("notext") or {}) if p.is_file() else {}
    if not nt.get("used") or not run.path(nt["color"]).is_file() or not run.path(nt["alpha"]).is_file():
        return None
    with Image.open(run.path(nt["color"])) as c, Image.open(run.path(nt["alpha"])) as a:
        col = np.asarray(c.convert("RGB"), float)
        alpha = np.asarray(a.convert("L"), float) / 255.0
    return col, (alpha if bg in ("transparent", "flat") else None)


def _pad_crop(arr, x0: int, y0: int, x1: int, y1: int, p: int):
    """arr[y0:y1, x0:x1] 를 사방 p px 크게(그림 밖은 가장자리 픽셀 되풀이)."""
    import numpy as np
    H, W = arr.shape[:2]
    return arr[np.ix_(np.clip(np.arange(y0 - p, y1 + p), 0, H - 1), np.clip(np.arange(x0 - p, x1 + p), 0, W - 1))]


def _hidden_by_flag(spec: dict, wid: str) -> bool:
    """이 위젯이나 조상이 런타임에 접힐 수 있나(flag 바인딩 · 시작값 collapsed/hidden) — 넘침 장식 Image 는 바인딩이 없어 같이 접히지 않는다."""
    index = spec_mod.widget_index(spec)
    w = index.get(wid)
    while w is not None:
        if (w.get("binding") or {}).get("kind") == "flag" or w.get("visibility") in ("collapsed", "hidden"):
            return True
        w = index.get(w.get("parent")) if w.get("parent") else None
    return False


def overhang_blockers(spec: dict, aid: str, box) -> list[str]:
    """넘침을 막는 이유(없으면 빈 목록) — 쓰는 위젯마다 크기 고정(점 앵커 영역 안)이어야 하고 런타임에 접히지 않아야 한다."""
    why = []
    users = asset_users(spec, aid)
    if not users:
        why.append("no widget uses this asset")
    for u in users:
        if not fixed_size(spec, u["id"]):
            why.append(f"{u['id']} changes size with the screen (9-slice box draw stays inside the box)")
        if _hidden_by_flag(spec, u["id"]):
            why.append(f"{u['id']} can be collapsed at runtime (a decoration Image would stay visible)")
        if u.get("type") == "Image" and _small_cut_icon(spec, u):
            why.append(f"{u['id']} is a small icon — its silhouette stays inside its box")
    return why


def _small_cut_icon(spec: dict, w: dict) -> bool:
    """컨셉에서 오리는(extract) 작은 정사각형 이미지(짧은 변 < 128 px · 긴 변 < 짧은 변 × 1.5 — 키 배지 · 아이콘)인가."""
    from gen import cutout
    bb = w.get("bbox_intent") or [0, 0, 0, 0]
    lo, hi = min(float(bb[2]), float(bb[3])), max(float(bb[2]), float(bb[3]))
    if not (0 < lo < cutout.GC_BOX_SEED_MAX and hi < cutout.COMPACT_ASPECT * lo):
        return False
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    ids = [b.get("asset") for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")]
    return bool(ids) and all((assets.get(i) or {}).get("source_mode") == "extract" for i in ids)


ICON_SOLID_A = 0.85         # 작은 아이콘 실루엣 = 알파 > 이것의 채운 모양 — [실측 H3 R20261117_095249] 진짜 알파 컨셉에선 둘레 소용돌이도 0.65 라 0.5 면 아이콘
                            # 텍스처가 상자 모서리까지 소용돌이를 품어 엠블럼과 이중(위 마우스 아이콘 오른쪽 위 밝은 네모 — 덮임 0.81 ↔ 컨셉 0.65)


def _cut_widget(spec: dict, w: dict) -> bool:
    """브러시에 컨셉에서 오리는(extract) 에셋이 있는 위젯인가."""
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    return any(isinstance(b, dict) and b.get("asset") and (assets.get(b["asset"]) or {}).get("source_mode") == "extract"
               for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS)


def _icon_mask(ca):
    """작은 아이콘 텍스처가 갖는 자리 = 불투명(ICON_SOLID_A) 실루엣을 채우고 2 px 넓힌 것."""
    from gen import cutout, fidelity
    solid = fidelity.fill_shape(ca > ICON_SOLID_A)[0]
    return cutout._dilate(solid, 2) if solid.any() else solid


def _blocked_mask(spec: dict, aid: str, box, sb):
    """검색 상자(sb = [x0, y0, x1, y1]) 안의 다른 '그리는' 위젯 자리(BLOCK_PAD 넓힘) — 글자 · 게이지 · 이미지 · 에셋 브러시. 이 에셋을 쓰는 위젯 ·
    넘침 장식 · 접힌 위젯은 빼고. 넘침은 이 자리로 넓히지 않는다(그 위젯이 제 텍스처로 그린다 — 뒤에 깔린 바탕 위젯도 그 둘레는 바탕이 그린다).
    [실측 H 오프라인 — G2 조작 안내] 스킬 다이아몬드가 둘레 엠블럼 바탕 자리로 7284 px 넘쳤고, 엠블럼이 이웃 띠 bbox 바로 밖 테두리선 조각을 가져갔다."""
    import numpy as np
    from gen import cutout
    x0, y0, x1, y1 = sb
    m = np.zeros((y1 - y0, x1 - x0), bool)
    mine = {u["id"] for u in asset_users(spec, aid)} | overhang_decos(spec)
    p = cutout.BLOCK_PAD
    for w in spec.get("widgets", []):
        bb = w.get("bbox_intent")
        if not bb or w["id"] in mine:
            continue
        if w.get("visibility") in ("collapsed", "hidden") and w.get("type") == "Image" and _overlap(bb, box) >= 0.9:
            continue     # 뒤에 깔린 숨은 빛(가득 찬 게이지 빛 — 프레임보다 큼)은 막지 않는다. 접힌 글자 · 아이콘은 막는다(보일 때 그 자리를 그린다)
            # [실측 H run — 단색 컨셉] 접힌 '오의 불가' 자리를 막지 않아 게이지 프레임 넘침이 그 글자 빛 · 획을 가져가 샘플 렌더에 자국이 남았다
        draws = w.get("type") in ("TextBlock", "ProgressBar", "Image") or any(
            isinstance(b, dict) and b.get("asset") for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS)
        if not draws:
            continue
        if w.get("type") == "Image" and _small_cut_icon(spec, w):
            continue     # 컨셉에서 오리는 작은 정사각형 아이콘은 자기 실루엣만 그린다 — 그 상자 모서리는 이웃(띠 · 장식)이 넘쳐 채운다(아이콘이 위에 겹침)
            # [실측 H 끝 run 2차 — 조작 안내] 띠 넘침이 마우스 키 아이콘 상자에서 네모나게 끊겨 검은 홈이 생겼다
        # 오리는 이미지(extract 에셋)는 상자째로만 막는다(여유 없음) — 그 위젯은 상자 밖을 그리지 않고(넘치면 넘침 장부가 가른다) 두 상자의 여유가
        # 서로 막은 모서리는 아무도 안 그렸다 [실측 H3 — 띠 상자 모서리 5 × 5 틈, run 마다 0 ~ 75 px]. 글자 · 게이지 · 생성 이미지는 여유째(안티앨리어싱)
        pw = 0 if _cut_widget(spec, w) else p
        bx0, by0 = max(x0, int(np.floor(bb[0])) - pw), max(y0, int(np.floor(bb[1])) - pw)
        bx1, by1 = min(x1, int(np.ceil(bb[0] + bb[2])) + pw), min(y1, int(np.ceil(bb[1] + bb[3])) + pw)
        if bx1 > bx0 and by1 > by0:
            m[by0 - y0:by1 - y0, bx0 - x0:bx1 - x0] = True
    return m


NEST_FRAC = 0.9             # 한쪽 상자의 이만큼 이상이 다른 쪽 안이면 포함 관계 — 띠 위 배지 · 엠블럼 속 다이아몬드처럼 설계대로 겹쳐 그린다
OWN_BODY = 0.5              # 물체 속 = 알파 > 이것이고 알파 경계가 아닌 픽셀 — 그 모양(거리 변환)으로 가는 목을 찾는다
OWN_EDGE = 0.006            # 알파 경계 = 알파 기울기(소벨 / 8, px 당)가 이것보다 큼. [실측 I 오프라인 — 조작 안내 투명 컨셉] 배너 띠 0.98 ~ 0.99 ↔ 배너 사이
                            # 엠블럼 바탕 0.84 ~ 0.95 — 알파 문턱 하나(0.75)로는 띠 · 바탕 · 다음 띠가 한 덩어리(띠 가운데 거리 72)라 엠블럼 바탕이 띠 끝을
                            # 가져갔다. 어빌리티 띠는 0.85 ~ 0.94 라 문턱을 올려도 못 가른다 — 띠 속은 알파가 고르고 띠 · 바탕 사이엔 알파 계단이 있다
OWN_VISIBLE = 0.02          # 보이는 픽셀
OWN_REACH = 48              # 몸통에 안 닿은 픽셀의 주인을 찾는 거리(px) — 그 안에 어느 후보의 픽셀도 없으면 작은 상자 몫


def _cut_participants(spec: dict) -> list[dict]:
    """겹친 자리를 나눌 오리는 위젯 — extract 에셋 브러시 · 상자 있음 · 넘침 장식 아님 · 작은 아이콘 아님(실루엣만 그리고 위에 겹친다 — 빼면 그 상자
    모서리에 홈)."""
    decos = overhang_decos(spec)
    return [w for w in spec.get("widgets", []) if w.get("bbox_intent") and w["id"] not in decos and _cut_widget(spec, w)
            and not (w.get("type") == "Image" and _small_cut_icon(spec, w))]


def _int_box(bb, W: int, H: int) -> tuple[int, int, int, int]:
    """bbox_intent → 캔버스 정수 상자 [x0, y0, x1) — _cut_entry 의 위젯 상자(bl)와 같은 반올림."""
    x0, y0 = int(round(float(bb[0]))), int(round(float(bb[1])))
    x1, y1 = int(round(float(bb[0]) + float(bb[2]))), int(round(float(bb[1]) + float(bb[3])))
    return max(0, x0), max(0, y0), min(W, x1), min(H, y1)


def _body_depth(a):
    """알파 → (물체 속 bool, 물체 속 깊이 = 알파 경계 · 옅은 자리까지 거리)."""
    import cv2
    import numpy as np
    f = np.asarray(a, np.float32)
    g = np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)) / 8.0
    body = (f > OWN_BODY) & (g <= OWN_EDGE)
    return body, cv2.distanceTransform(body.astype(np.uint8), cv2.DIST_L2, 5)


OWN_RING = 8                # 넘칠 수 있는 위젯은 자기 상자 둘레 이만큼(px)도 상대 상자 안에서 겨룬다 — [실측 I 오프라인 — 조작 안내] analyze 배너 상자가
                            # 띠보다 2 ~ 5 px 작아 띠 위아래 테두리 줄이 엠블럼 상자 쪽(엠블럼 몫)이었다
OWN_EDGE_NEAR = 4           # 물체 속에서 이만큼(px) 안의 경계 · 반투명 픽셀(안티앨리어싱 · 테두리 줄)은 그 물체 주인 몫
OWN_TIE = 0.25              # 넓은 길 값이 가장 큰 값의 1 / (1 + 이것) 이상이면 동점 — 동점은 작은 상자(더 구체적인 요소)
OWN_BLEED = 2               # 내 픽셀에 이만큼(px) 안으로 붙은 남의 불투명 몫은 같이 그린다(확대 때 절취선 메움 — 이중선형은 한 텍셀 너머까지 섞는다)
OWN_BLEED_ALPHA = 0.97      # 같이 그리는 '불투명' — 1:1 에서 두 번 쌓여도 덮임 차가 0.03 이하


def cut_ownership(spec: dict, alpha, ring_ok: set | None = None) -> dict | None:
    """ⓐ ⓑ — 오리는 위젯 상자가 일부만 겹친 자리(포함 관계 NEST_FRAC 은 빼고 — 띠 위 배지 · 엠블럼 속 다이아몬드는 설계대로 겹쳐 그린다)의 픽셀마다
    주인 하나를 정한다 → {"ids", "cand"(캔버스 — 후보 비트: 상자, 넘칠 수 있는 위젯(ring_ok)은 상자 + OWN_RING), "contested", "owner"(캔버스 —
    -1 = 겹친 자리 아님 · -2 = 안 보임)} 또는 None. 겨루는 자리 = 두 상자가 겹친 곳 + 넘칠 수 있는 쪽 상자 둘레 OWN_RING 중 상대 상자 안.
    물체 단위: 물체 속(알파가 고른 자리 — _body_depth) 픽셀은 '씨앗(겨루지 않는 자기 상자 쪽 물체 속)에서 그 픽셀까지 길의 가장 가는 곳'이 가장 두꺼운
    위젯 몫(가장 넓은 길) — 경계가 가장 가는 목(연결선)에 놓여 몸통에 이어진 끝 · 끝 장식은 크기와 상관없이 그 몸통 몫이고, 목 없이 두껍게 붙은
    자리(같은 두께)는 작은 상자(더 구체적인 요소) 몫이다. 물체 속이 아닌 픽셀(경계 · 반투명 · 떨어진 조각)은 OWN_EDGE_NEAR 안 물체 속 주인 → OWN_REACH
    안 가장 가까운 자기 픽셀 주인 → 작은 상자 순. 후보 = 그 픽셀을 (넓힌) 상자에 품은 위젯뿐. 한 run 에서 한 번 — 모든 오리는 위젯이 같은 지도를
    쓴다(셋 이상 겹쳐도 같은 답).
    [실측 H 마무리 R20261117_120813] 예전 '두 상자 합친 영역 · 겹친 자리 둘레 24 px 에서 어느 쪽 픽셀이 많은가' 판정은 배너 끝이 엠블럼 장식과
    이어져 세 배너의 끝(뾰족한 끝 · 문양 · 고리)을 엠블럼 상자 경계(x 540)부터 엠블럼 텍스처에 넘겼고, 이를 막으려던 '글자 주인 둘레' 사각형 규칙이
    직사각형 계단을, '반투명은 작은 상자 몫' 규칙이 배너 오른쪽 소용돌이 조각을 남겼다."""
    import heapq
    import cv2
    import numpy as np
    parts = _cut_participants(spec)
    n = len(parts)
    if n < 2 or n > 62:
        return None
    H, W = alpha.shape
    boxes = [_int_box(w["bbox_intent"], W, H) for w in parts]
    areas = [max(0, (b[2] - b[0])) * max(0, (b[3] - b[1])) for b in boxes]
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            bi, bj = boxes[i], boxes[j]
            inter = max(0, min(bi[2], bj[2]) - max(bi[0], bj[0])) * max(0, min(bi[3], bj[3]) - max(bi[1], bj[1]))
            if 0 < inter < NEST_FRAC * min(areas[i], areas[j]):
                pairs.append((i, j))
    if not pairs:
        return None
    real = np.zeros((H, W), np.int64)
    cand = np.zeros((H, W), np.int64)
    ring_ok = set(ring_ok or ())
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        real[y0:y1, x0:x1] |= np.int64(1) << i
        g = OWN_RING if parts[i]["id"] in ring_ok else 0
        cand[max(0, y0 - g):min(H, y1 + g), max(0, x0 - g):min(W, x1 + g)] |= np.int64(1) << i
    contested = np.zeros((H, W), bool)
    for i, j in pairs:
        bit = (np.int64(1) << i) | (np.int64(1) << j)
        contested |= ((cand & bit) == bit) & ((real & bit) != 0)      # 둘 다 후보 · 둘 중 한 상자 안
    # 어느 상자에도 안 속한 빈 자리 중 넘칠 수 있는 위젯 둘레(OWN_RING)도 지도로 — 먼저 온 넘침(H3 장부 · spec 순서)이 남의 삐진 테두리 줄을 가져가지
    # 않게. [실측 I 오프라인 — 조작 안내] 엠블럼 넘침이 엠블럼 상자 왼쪽 빈 자리의 배너 위아래 테두리 줄을 먼저 가져갔다
    contested |= (cand != 0) & (real == 0)
    if not contested.any():
        return None
    a = np.asarray(alpha, float)
    vis = a > OWN_VISIBLE
    solid, dist = _body_depth(a)
    ys, xs = np.nonzero(contested)
    M = OWN_REACH + 2
    rx0, ry0, rx1, ry1 = max(0, xs.min() - M), max(0, ys.min() - M), min(W, xs.max() + 1 + M), min(H, ys.max() + 1 + M)
    cR, conR, visR, solR = cand[ry0:ry1, rx0:rx1], contested[ry0:ry1, rx0:rx1], vis[ry0:ry1, rx0:rx1], solid[ry0:ry1, rx0:rx1]
    h, w = conR.shape
    # 몸통 씨앗 — 겹친 자리 밖 불투명 픽셀은 그 픽셀을 품은 가장 큰 상자의 위젯(포함 관계면 바깥 것)
    seed = np.full((h, w), -1, np.int32)
    for i in sorted(range(n), key=lambda k: areas[k]):
        x0, y0, x1, y1 = boxes[i]
        sx0, sy0, sx1, sy1 = max(0, x0 - rx0), max(0, y0 - ry0), min(w, x1 - rx0), min(h, y1 - ry0)
        if sx1 > sx0 and sy1 > sy0:
            seed[sy0:sy1, sx0:sx1] = i
    seed[conR | ~solR] = -1
    unknown = conR & solR
    # 가장 넓은 길: 겹친 자리 물체 속 픽셀은 '씨앗에서 그 픽셀까지 길의 가장 가는 곳(거리 변환 최솟값)'이 가장 두꺼운 위젯 몫 — 같으면 작은 상자.
    # 표준 watershed(낮은 곳부터 채우기)는 씨앗이 비탈에 있으면 그대로 흘러내린다 — [실측 I 오프라인 — 조작 안내] 배너 띠가 배너 상자 위아래로 몇 px
    # 삐져나온 자리(엠블럼 상자 안 = 엠블럼 씨앗)에서 엠블럼이 띠 속으로 흘러들어 띠 끝 전체를 가져갔다. 넓은 길이면 배너 몸통 쪽 길은 띠 두께,
    # 삐져나온 가장자리 쪽 길은 몇 px 라 배너가 갖고, 가는 연결선으로만 배너에 붙은 엠블럼 장식은 엠블럼 쪽 길이 더 두껍다. 동점을 '씨앗 깊이'로
    # 가르자 점프 띠 끝과 목 없이 붙은 엠블럼 몸통(거리 99.6)이 띠 위쪽 반을 가져갔다 → 동점은 작은 상자(브리프 — 배너 몸통에 이어진 것은 배너 몫).
    # 위젯마다 넓은 길 값을 따로 구하고 OWN_TIE 안이면 동점 — 같은 두께 길도 씨앗 자리에 따라 43.0 · 43.4 처럼 갈려 소수점이 주인을 정했다(I 시험)
    W2 = w + 2
    unk = np.pad(unknown, 1, constant_values=False).ravel().tolist()
    cnd = np.pad(cR, 1).ravel().tolist()
    dd = np.pad(dist[ry0:ry1, rx0:rx1], 1).ravel().tolist()
    nbrs = (-W2 - 1, -W2, -W2 + 1, -1, 1, W2 - 1, W2, W2 + 1)
    k3 = np.ones((3, 3), np.uint8)
    touch = cv2.dilate(unknown.astype(np.uint8), k3).astype(bool)           # 겹친 자리에 닿은 씨앗만 길을 낸다
    widest = np.zeros((n, h, w), np.float32)
    for k in range(n):
        sy_, sx_ = np.nonzero((seed == k) & touch)
        if not len(sy_):
            continue
        heap = [(-dd[(y + 1) * W2 + x + 1], (y + 1) * W2 + x + 1, True) for y, x in zip(sy_.tolist(), sx_.tolist())]
        heapq.heapify(heap)
        bk = [0.0] * ((h + 2) * W2)
        while heap:
            nb, idx, is_seed = heapq.heappop(heap)
            if not is_seed:
                if bk[idx] > 0.0:
                    continue
                bk[idx] = -nb
            b = -nb
            for d in nbrs:
                j = idx + d
                if unk[j] and bk[j] == 0.0 and (cnd[j] >> k) & 1:
                    heapq.heappush(heap, (-min(b, dd[j]), j, False))
        widest[k] = np.asarray(bk, np.float32).reshape(h + 2, W2)[1:-1, 1:-1]
    labR = np.full((h, w), -1, np.int32)
    best = widest.max(axis=0)
    for k in sorted(range(n), key=lambda q: -areas[q]):                     # 큰 상자부터 — 동점(OWN_TIE 안)이면 뒤의 작은 상자가 덮는다
        win = unknown & (widest[k] > 0) & (widest[k] * (1.0 + OWN_TIE) >= best)
        labR[win] = k
    flooded = int((labR >= 0).sum())
    rest = conR & visR & (labR < 0)
    near = edge_near = semi_near = 0
    if rest.any():
        rR = real[ry0:ry1, rx0:rx1]
        order = sorted(range(n), key=lambda q: areas[q])           # argmin 동점 = 작은 상자
        # 물체 속 4 px 안(안티앨리어싱 · 테두리 줄) → 겨루지 않는 자기 반투명 픽셀이 가까운 쪽(반투명 장식은 반투명끼리 — [실측 I — 조작 안내 R135820]
        # 배너 끝 둘레 소용돌이(알파 0.16 ~ 0.45)가 '가장 가까운 자기 픽셀'이면 바로 옆 배너 끝 몸통으로 가 엠블럼이 배너 상자 끝에서 세로 직선으로 잘렸다)
        # → 가장 가까운 자기 픽셀 → 작은 상자
        for tier in ("body", "semi", "visible"):
            dists = np.full((n, h, w), np.inf, np.float32)
            for pos, k in enumerate(order):
                bitk = ((cR >> k) & 1).astype(bool)
                own_real = ((rR >> k) & 1).astype(bool) & ~conR
                if tier == "body":
                    ownk = (own_real & solR) | (labR == k)
                elif tier == "semi":
                    ownk = own_real & visR & ~solR
                else:
                    ownk = (own_real & visR) | (labR == k)
                if not ownk.any():
                    continue
                dk = cv2.distanceTransform((~ownk).astype(np.uint8), cv2.DIST_L2, 5)
                dists[pos] = np.where(bitk & (dk <= (OWN_EDGE_NEAR if tier == "body" else OWN_REACH)), dk, np.inf)
            pos_best, bestd = dists.argmin(axis=0), dists.min(axis=0)
            ok = rest & np.isfinite(bestd)
            labR[ok] = np.asarray(order, np.int32)[pos_best[ok]]
            if tier == "body":
                edge_near = int(ok.sum())
            elif tier == "semi":
                semi_near = int(ok.sum())
            else:
                near = int(ok.sum())
            rest = rest & ~ok
            if not rest.any():
                break
        left = rest
        if left.any():                                   # 둘레에 어느 후보 픽셀도 없음 — 작은 상자 몫
            for k in sorted(range(n), key=lambda q: -areas[q]):
                sel = left & ((cR >> k) & 1).astype(bool)
                labR[sel] = k
    owner = np.full((H, W), -1, np.int32)
    sub = owner[ry0:ry1, rx0:rx1]
    sub[conR] = np.where(visR[conR], labR[conR], -2)
    owner[ry0:ry1, rx0:rx1] = sub
    return {"ids": [w["id"] for w in parts], "cand": cand, "contested": contested, "owner": owner,
            "pairs": [[parts[i]["id"], parts[j]["id"]] for i, j in pairs],
            "ring": sorted(ring_ok & {w["id"] for w in parts}),
            "stats": {"contested_px": int(contested.sum()), "flooded_px": flooded, "edge_near_px": edge_near, "semi_near_px": semi_near,
                      "nearest_px": near}}


def _ownership(run, spec: dict, alpha):
    """run 한 번(refine.run 이 비움)의 소유 지도 — spec 객체마다 한 번 계산. 둘레를 겨루는 위젯 = 넘칠 수 있는 위젯(overhang_blockers 없음)."""
    cache = getattr(run, "cut_ownership_cache", None)
    if cache is None:
        cache = {}
        try:
            run.cut_ownership_cache = cache
        except AttributeError:
            pass
    key = id(spec)
    if key not in cache:
        ext_cfg = (getattr(run, "cfg", None) or {}).get("extract") or {}
        ring_ok = set()
        if ext_cfg.get("overhang", True) and ext_cfg.get("fixed_size_draw_as", "image") == "image":
            for w in _cut_participants(spec):
                ids = [b.get("asset") for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")]
                if ids and all(not overhang_blockers(spec, i, w["bbox_intent"]) for i in ids):
                    ring_ok.add(w["id"])
        cache[key] = cut_ownership(spec, alpha, ring_ok)
    return cache[key]


def _owner_masks(own: dict | None, spec: dict, aid: str, sb):
    """소유 지도 → (남의 몫 = 겨루는 자리 중 남이 가진 보이는 픽셀 — 그리지도 넘치지도 않는다, 내 몫 = 겨루는 자리 중 내가 가진 것) — 검색 상자 sb 조각
    좌표 bool, 소유 지도가 없거나 이 에셋 위젯이 겨루지 않으면 None."""
    import numpy as np
    if not own:
        return None
    users = {u["id"] for u in asset_users(spec, aid)}
    ks = [i for i, wid in enumerate(own["ids"]) if wid in users]
    if not ks:
        return None
    x0, y0, x1, y1 = sb
    o = own["owner"][y0:y1, x0:x1]
    con = own["contested"][y0:y1, x0:x1]
    held = con & np.isin(o, ks)
    return con & (o >= 0) & ~held, held


def _opaque_bleed(drop, a):
    """남의 몫(drop) 중 내가 같이 그릴 자리 — 내 보이는 픽셀에서 OWN_BLEED px 안 · 컨셉 알파 ≥ OWN_BLEED_ALPHA(불투명 위 같은 불투명이라 1:1 에선 안 보임)."""
    from gen import cutout
    kept = (a > 0) & ~drop
    return drop & cutout._dilate(kept, OWN_BLEED) & (a >= OWN_BLEED_ALPHA)


def _region_of(spec: dict, wid: str) -> str:
    """루트 직계 조상(영역) id."""
    index = spec_mod.widget_index(spec)
    root = spec.get("root") or "Root"
    cur = index.get(wid)
    while cur and cur.get("parent") and cur.get("parent") != root:
        cur = index.get(cur["parent"])
    return cur["id"] if cur else wid


def _drop_covered_below(a, spec: dict, aid: str, sb, box, alpha_full):
    """ⓐ ⓑ — 이 텍스처가 위에 그려져 가리게 될 다른 영역의 글자 · 오린 이미지 자리를 비운다 → (알파, 뺀 px, 위젯들).
    대상 = 이 위젯 상자 안에 담긴(NEST_FRAC) 그리는 위젯 중 그리는 순서(캔버스 z · 자식 순서)가 이 에셋의 최상위 영역보다 앞(아래)인 것 — 글자는 상자
    (+2 px), 오린 이미지는 그 텍스처 자리(상자 안 알파 > 0 · 작은 아이콘은 불투명 실루엣 + 2 px). 넘침 장식은 영역 바로 앞에 놓이므로 영역 기준이다.
    [실측 H3 R20261117_094157 — 투명 컨셉] analyze 가 가운데 엠블럼 영역(z 2)을 T 배지까지 덮게 잡아 엠블럼 텍스처가 T 배지 상자를 통째로 품고(포함 관계라
    '겹친 자리 한쪽만' 규칙 밖) 위에 그려져 엔진 'T' 를 가렸다. 위에 그려지는 자식(띠 위 배지)은 같은 픽셀로 덮으므로 그대로 둔다 — 비우면 네모 구멍
    · 줄 보간 줄무늬가 생겼다(H3 오프라인)."""
    import numpy as np
    from gen import backdrop
    order = backdrop.paint_order(spec)
    idx = {w["id"]: i for i, w in enumerate(order)}
    index = spec_mod.widget_index(spec)
    root = spec.get("root") or "Root"

    def region(wid):
        cur = index.get(wid)
        while cur and cur.get("parent") and cur.get("parent") != root:
            cur = index.get(cur["parent"])
        return cur["id"] if cur else wid
    users = asset_users(spec, aid)
    if not users:
        return a, 0, []
    start = min(idx.get(region(u["id"]), 10 ** 9) for u in users)
    x0, y0 = sb[0], sb[1]
    H, W = a.shape
    bxa, bya, bwa, bha = (float(v) for v in box)
    mine = {u["id"] for u in users} | overhang_decos(spec)
    assets = {x["asset_id"]: x for x in spec.get("assets", [])}
    drop = np.zeros((H, W), bool)
    hit_ids = []
    for w in order:
        if idx[w["id"]] >= start:
            break
        bb = w.get("bbox_intent")
        if not bb or w["id"] in mine or _hidden_by_flag(spec, w["id"]):
            continue
        is_text = w.get("type") in ("TextBlock", "RichTextBlock")
        ids = [b.get("asset") for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")
               and b.get("draw_as") != "none"]
        is_cut = any((assets.get(i) or {}).get("source_mode") == "extract" for i in ids)
        if not (is_text or is_cut):
            continue
        ix = max(0.0, min(bxa + bwa, bb[0] + bb[2]) - max(bxa, bb[0]))
        iy = max(0.0, min(bya + bha, bb[1] + bb[3]) - max(bya, bb[1]))
        area = float(bb[2]) * float(bb[3])
        if area <= 0 or ix * iy < NEST_FRAC * area:
            continue
        pad = 2 if is_text else 0
        cx0, cy0 = max(0, int(np.floor(bb[0])) - pad - x0), max(0, int(np.floor(bb[1])) - pad - y0)
        cx1, cy1 = min(W, int(np.ceil(bb[0] + bb[2])) + pad - x0), min(H, int(np.ceil(bb[1] + bb[3])) + pad - y0)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        if is_text:
            keep = np.ones((cy1 - cy0, cx1 - cx0), bool)
        else:
            ca = alpha_full[cy0 + y0:cy1 + y0, cx0 + x0:cx1 + x0]
            if w.get("type") == "Image" and _small_cut_icon(spec, w):
                keep = _icon_mask(ca)
            else:
                keep = ca > 0
        drop[cy0:cy1, cx0:cx1] |= keep
        hit_ids.append(w["id"])
    if not drop.any():
        return a, 0, []
    out = a.copy()
    n = int((drop & (out > 0)).sum())
    out[drop] = 0.0
    return out, n, hit_ids


def _codex_seed(raw, extract: dict, canvas, sb):
    """ⓒ — codex 편집 결과(입력 영역을 늘린 캔버스)의 알파를 reference 좌표 검색 상자로(GrabCut '아마 전경' 시드). 배경이 안 빠졌으면 테두리 flood fill."""
    import numpy as np
    from PIL import Image
    from gen import postprocess as pp
    im, _ = pp.remove_background(pp.load_rgba(raw))
    rx, ry, rw, rh = (int(v) for v in extract["region"])
    a = np.asarray(im.resize((rw, rh), Image.Resampling.BILINEAR))[..., 3].astype(float) / 255.0
    full = np.zeros((int(canvas[1]), int(canvas[0])), float)
    ys, xs = slice(max(0, ry), min(full.shape[0], ry + rh)), slice(max(0, rx), min(full.shape[1], rx + rw))
    full[ys, xs] = a[ys.start - ry:ys.stop - ry, xs.start - rx:xs.stop - rx]
    x0, y0, x1, y1 = sb
    return full[y0:y1, x0:x1]


def _cut_entry(run, asset: dict, raw, backend: str, gen_rec: dict, spec: dict | None, log: dict) -> tuple[dict, dict]:
    """1b 후속 H — 컨셉 픽셀을 오려 텍스처로(gen/cutout): 알파(ⓐ ⓑ reference_alpha · ⓒ GrabCut ← codex 실루엣 · 장식선 시드, 사각 패널은 상자) →
    넘침(가리지 않은 바깥으로 이어진 덩어리) → 색 = 컨셉(ⓑ 언믹싱) → 가려진 자리 줄 보간 · 게이지 트랙 메우기 → frame · panel_bg 안쪽 알파(ⓐ 는 그대로).
    안쪽 한 색 칠하기 · 'IoU < 0.85 면 물러남'은 이 길에 없다. codex 결과로 물러나는 것은 ⓒ 에서 GrabCut 이 실패할 때뿐."""
    import numpy as np
    from PIL import Image
    from core import ocr
    from gen import cutout
    from gen import postprocess as pp
    from stages import generate
    aid = asset["asset_id"]
    extract = gen_rec["extract"]
    ext_cfg = run.cfg.get("extract") or {}
    log["source_mode"] = "extract"
    box = [float(v) for v in extract_target_box(spec, asset, extract)]
    bg = generate.background_kind(run) or "scene"
    color, alpha = _reference_layers(run, bg)
    notext = _notext_layers(run, bg) if ext_cfg.get("notext", True) else None
    H, W = color.shape[:2]
    _, _, _, gauges = concept_pixel_inputs(spec, asset, box, gauge_holes=True)
    tracks = []
    if any(not g.get("hole") for g in gauges):
        try:
            color, tracks = _fill_tracks(color, gauges)
        except ValueError as exc:
            tracks = [{"error": str(exc)}]
    blockers = overhang_blockers(spec or {"widgets": []}, aid, box) if ext_cfg.get("overhang", True) else ["extract.overhang is off"]
    if (ext_cfg.get("fixed_size_draw_as", "image") != "image") and not blockers:
        blockers = ["extract.fixed_size_draw_as is not image"]
    can_over = not blockers
    sb = cutout.search_box(box, (W, H), can_over)
    sx0, sy0, sx1, sy1 = sb
    bl = [int(round(box[0])) - sx0, int(round(box[1])) - sy0, int(round(box[0] + box[2])) - sx0, int(round(box[1] + box[3])) - sy0]
    bl = [max(0, bl[0]), max(0, bl[1]), min(sx1 - sx0, bl[2]), min(sy1 - sy0, bl[3])]
    if bl[2] - bl[0] < 2 or bl[3] - bl[1] < 2:
        raise StageError("EXTRACT_OUTSIDE", f"'{aid}' widget box {box} is outside the reference", asset=aid)
    crop = color[sy0:sy1, sx0:sx1]
    inbox = np.zeros(crop.shape[:2], bool)
    inbox[bl[1]:bl[3], bl[0]:bl[2]] = True
    blocked = _blocked_mask(spec or {"widgets": []}, aid, box, sb)
    rec: dict = {"background": bg, "widget_box": box, "search_box": [sx0, sy0, sx1 - sx0, sy1 - sy0]}
    nb_drop = None
    held_out = None                          # 소유 지도가 이 위젯에 준 상자 밖 둘레 픽셀(ⓐ ⓑ)
    if gauges:
        rec["gauges"] = tracks or gauges
    if alpha is not None:
        a = alpha[sy0:sy1, sx0:sx1].copy()
        rec["alpha_from"] = "reference_alpha"
        a_in = a
        # 오리는 위젯 상자가 일부 겹친 자리는 물체 단위 소유 지도대로 한쪽만(cut_ownership — run 에서 한 번, 모든 위젯이 같은 지도). 글자 구멍 메우기 ·
        # 비우기는 그 뒤 자기 몫 안에서만 일어난다(남의 몫은 메우기 뒤에도 투명 — nb_drop)
        own = _ownership(run, spec or {"widgets": []}, alpha)
        masks = _owner_masks(own, spec or {"widgets": []}, aid, sb)
        dropped = 0
        if masks is not None:
            drop, held = masks
            blocked = blocked | drop                                # 남의 몫은 넘침으로도 안 가져간다
            # 내 픽셀에 OWN_BLEED px 안으로 붙은 남의 불투명 몫은 같이 그린다 — 1:1 에선 불투명 위 같은 불투명이라 안 보이고, 엔진이 텍스처를 따로 늘릴 때
            # 두 가장자리가 같이 옅어져 생기던 틈(절취선)을 메운다. 반투명은 겹치면 1:1 에서 두 번 쌓이므로 안 함
            # [실측 I — 조작 안내 R20261117_135820 디자이너 확대: 엠블럼 ↔ 배너 경계를 따라 검은 절취선]
            bleed = _opaque_bleed(drop, a)
            if bleed.any():
                drop = drop & ~bleed
            dropped = int((drop & (a > 0)).sum())
            held_out = held & ~inbox & (a > cutout.OVERHANG_ALPHA) if can_over else None
            if held_out is not None and not held_out.any():
                held_out = None
            if dropped or held_out is not None:
                a = np.where(drop, 0.0, a)
                rec["ownership"] = {"rule": "object split — widest path from each widget's own box side (tie = smaller box), then nearest",
                                    "dropped_px": dropped, "held_outside_box_px": int(held_out.sum()) if held_out is not None else 0,
                                    "opaque_bleed_px": int(bleed.sum()), **own["stats"]}
            if held_out is not None:
                blocked = blocked & ~held                       # 내 몫으로 받은 둘레(상대 상자 안)는 넘칠 수 있다
        a, covered, cov_ids = _drop_covered_below(a, spec or {"widgets": []}, aid, sb, box, alpha)
        if covered:
            rec["covered_below_dropped"] = {"px": covered, "widgets": cov_ids}
        if dropped or covered:
            nb_drop = (a_in > 0) & (a == 0)
        # 위에 그려지는 담긴 자식(키 아이콘 · 원판 · 다이아몬드) 자리는 비우지 않는다 — [실측 H3 오프라인 — 투명 컨셉] ⓐ 에선 뒤 장식 · 띠가 불투명해 작은 아이콘의
        # 실루엣이 상자 전체가 되고(텍스처 = 상자째 같은 컨셉 픽셀) 다이아몬드도 상자째라, 담는 쪽을 비우면 네모 구멍이 생기고 어빌리티 띠는 T 배지 네모 둘레
        # 줄 보간 줄무늬 · 네모 테가 생겼다. 자식이 같은 픽셀로 위를 덮어 회색 바탕에서도 차이가 없다(알파 MAE 0.0076 → 0.0059 뿐) — 기록만
        users = asset_users(spec or {"widgets": []}, aid)
        if users and all(u.get("type") == "Image" and _small_cut_icon(spec, u) for u in users):
            # 작은 아이콘은 불투명 실루엣(+2 px)만 — 상자 모서리의 뒤 띠 반투명 픽셀까지 오리면 띠 텍스처 위에 같은 반투명이 두 번 쌓여 네모가 보였다
            # [실측 H — UI 만 컨셉 E 배지: 모서리 알파 0.15 · 텍스처의 29 % 반투명]
            icon_mask = _icon_mask(a)
            if icon_mask.any():
                a[~icon_mask] = 0.0
                rec["icon_alpha"] = "solid silhouette only (+2 px)"
                # 메우기 뒤에도 실루엣 밖은 투명 — [실측 H2 R20261116_210642] 'E' 글자 구멍 사각형(배지 상자 전체)을 글자 없는 판이 채워 원판 바깥
                # 모서리에 띠의 반투명이 다시 들어가 배지 뒤 네모가 보였다
                nb_drop = ~icon_mask if nb_drop is None else (nb_drop | ~icon_mask)
    else:
        rgb8 = np.clip(np.round(crop), 0, 255).astype(np.uint8)
        is_rect, fill = cutout.rect_panel(rgb8[bl[1]:bl[3], bl[0]:bl[2]])
        rec["concept_box_fill"] = fill
        is_rect = is_rect and min(bl[2] - bl[0], bl[3] - bl[1]) >= cutout.RECT_MIN_PX
        if is_rect:
            a = inbox.astype(float)
            rec["alpha_from"] = "widget box (rectangular panel)"
            can_over = False
            blockers = blockers + ["rectangular panel — the silhouette is the widget box"]
        else:
            seed = _codex_seed(raw, extract, (W, H), sb) if backend == "codex" else None
            try:
                a, rec["grabcut"] = cutout.grabcut_alpha(rgb8, bl, seed, blocked)
                rec["alpha_from"] = "grabcut" + (" (codex silhouette seed)" if seed is not None else " (widget box seed)")
                if seed is not None:
                    # 반투명하게 장면으로 옅어지는 띠 끝은 색이 장면과 비슷해 GrabCut 이 배경으로 뗀다 — codex 실루엣 속(침식)은 위젯 상자 안에서 더한다
                    # [실측 H 오프라인 — G2 조작 안내 '돌진 공격' 띠] 왼쪽 옅어지는 반이 잘려 띠가 뚝 끊겼다
                    core = cutout._erode(seed > 0.5, cutout.SEED_ERODE) & inbox
                    added = core & (a < 0.5)
                    a = np.maximum(a, core.astype(float))
                    rec["codex_core_added_px"] = int(added.sum())
            except cutout.CutoutError as exc:
                rec["grabcut"] = {"failed": str(exc)}
                can_over = False                      # 물러난 실루엣은 상자 안만 — codex 가 상자 밖에 그린 것을 넘침으로 받지 않는다
                blockers = blockers + ["GrabCut failed — the fallback silhouette stays inside the widget box"]
                if seed is not None and (seed[inbox] > 0.5).any():
                    a = np.clip(seed, 0.0, 1.0) * inbox
                    rec["alpha_from"] = "codex silhouette (GrabCut failed)"
                else:
                    a = inbox.astype(float)
                    rec["alpha_from"] = "widget box (GrabCut failed, no codex silhouette)"
        rec["scene_mixed"] = "the concept pixels are a scene composite — baked opaque with the scene behind translucent parts (not unmixed)"
    if can_over:
        claims = getattr(run, "overhang_claims", None)
        claimed = claims[sy0:sy1, sx0:sx1] if claims is not None and claims.shape == (H, W) else None
        if claimed is not None and claimed.any():
            # 앞 에셋의 넘침이 이미 차지한 빈 자리(어느 위젯 상자도 아닌 곳)는 막는다 — [실측 H3 R20261117_092636 — 투명 컨셉 회색 바탕] 위 · 아래 띠의
            # 넘침이 두 띠 사이 반투명 소용돌이를 둘 다 가져가 두 번 쌓였다(덮임 0.6 ~ 0.8 ↔ 컨셉 0.27 ~ 0.45, 2.2 만 px — 검정에선 안 보임)
            blocked = blocked | (claimed & ~inbox)
            ov_claimed = int((claimed & ~inbox).sum())
        else:
            ov_claimed = 0
        keep, ov = cutout.overhang(a, bl, blocked)
        if held_out is not None and held_out.any():
            # 소유 지도가 준 둘레 픽셀은 넘침 최소 폭(OVERHANG_MIN_EXTENT)과 상관없이 그린다 — 상대는 이미 그 자리를 비웠다(안 그리면 구멍)
            extra = held_out & ~keep & ~(claimed & ~inbox if claimed is not None else np.zeros_like(inbox))
            if extra.any():
                keep = keep | extra
                ys_, xs_ = np.where(keep | inbox)
                bb_ = [int(xs_.min()), int(ys_.min()), int(xs_.max() + 1), int(ys_.max() + 1)]
                ov = {**ov, "used": True, "box": bb_, "px": int(keep.sum()), "owned_ring_px": int(extra.sum()),
                      "extent_px": max(bl[0] - bb_[0], bl[1] - bb_[1], bb_[2] - bl[2], bb_[3] - bl[3])}
        if ov_claimed:
            ov["blocked_claimed_px"] = ov_claimed
        if claims is not None and claims.shape == (H, W) and ov.get("used"):
            claims[sy0:sy1, sx0:sx1] |= keep & ~inbox & (a > cutout.OVERHANG_ALPHA)
    else:
        keep, ov = np.zeros_like(inbox), {"used": False, "blocked_by": blockers}
    rec["overhang"] = ov
    a = np.where(inbox | keep, a, 0.0)
    tb = ov["box"] if ov.get("used") else bl
    T = [sx0 + tb[0], sy0 + tb[1], tb[2] - tb[0], tb[3] - tb[1]]
    ys, xs = slice(tb[1], tb[3]), slice(tb[0], tb[2])
    col_t, a_t, keep_t = crop[ys, xs], a[ys, xs], (inbox | keep)[ys, xs]
    if nb_drop is not None:
        # 이웃 몫으로 비운 자리는 메우기(줄 보간 · 글자 없는 판) 뒤에도 투명하게 — [실측 H2 R20261116_210642] 그 자리에 걸친 'E' 글자 구멍을 판이 다시 채워
        # 위(z)에 그려지는 엠블럼 장식이 E 배지 오른쪽 아래를 어둡게 덮었다
        keep_t = keep_t & ~nb_drop[ys, xs]
    sx_s, sy_s = float(asset["size"][0]) / box[2], float(asset["size"][1]) / box[3]
    tw, th = max(1, int(round(T[2] * sx_s))), max(1, int(round(T[3] * sy_s)))
    if max(tw, th) > 1024:
        k = 1024.0 / max(tw, th)
        tw, th = max(1, int(round(tw * k))), max(1, int(round(th * k)))
    texts, excludes, _, gauges_t = concept_pixel_inputs(spec, asset, T, gauge_holes=True, keep_cut_children=True)
    clears = runtime_boxes(spec, T)
    fill_from, fill_skip = None, []
    if notext is not None and texts:
        # 글자 없는 판의 같은 조각(사방 NOTEXT_SHIFT 크게 — compose 가 요소마다 다시 맞춘다). 게이지 막대 자리는 판에도 채움이 구워져 있어 빼고 예전 메우기
        P = cutout.NOTEXT_SHIFT
        ax0, ay0, ax1, ay1 = sx0 + tb[0], sy0 + tb[1], sx0 + tb[2], sy0 + tb[3]
        fill_from = (_pad_crop(notext[0], ax0, ay0, ax1, ay1, P), _pad_crop(notext[1], ax0, ay0, ax1, ay1, P) if notext[1] is not None else None)
        index = spec_mod.widget_index(spec or {"widgets": []})
        for g in gauges_t:
            bb = (index.get(g["widget"]) or {}).get("bbox_intent")
            if bb:
                fill_skip.append([float(bb[0]) - T[0], float(bb[1]) - T[1], float(bb[2]), float(bb[3])])
    if clears:
        rec["runtime_image_cleared"] = clears
    kind = asset.get("kind")
    ia = ext_cfg.get("interior_alpha")
    # 안쪽 알파는 ⓒ 만 — ⓐ ⓑ 는 컨셉의 투명도를 이미 안다(알파 · 언믹싱). [실측 H — UI 만 컨셉 run] ⓑ 띠의 불투명 부분에 0.9 를 씌우자
    # 그 자리만 컨셉보다 약 10 % 어둡게 그려져(텍스처의 27 %) 옅어지는 끝과의 경계가 '어두운 그림자'로 보였다(엔진 섞기는 sRGB 값 그대로 — 실측 일치)
    interior = float(ia) if (ia is not None and kind in ("frame", "panel_bg") and bg == "scene") else None
    cropped = cutout.to_image(col_t, a_t, (int(round(T[2])), int(round(T[3]))))

    def make(whole: bool, use_nt: bool = True):
        try:
            rgb_o, a_o, comp = cutout.compose(col_t, a_t, texts, excludes, interior_alpha=interior, lock_lines=(bg == "scene"), whole_text_boxes=whole,
                                              clear_boxes=clears, hole_alpha="alpha" if bg == "scene" else "shape",
                                              fill_from=fill_from if use_nt else None, fill_skip=fill_skip)
        except cutout.CutoutError as exc:
            raise StageError("EMPTY_IMAGE", f"'{aid}': {exc}", asset=aid) from exc
        a_o[~keep_t] = 0.0
        return cutout.to_image(rgb_o, a_o, (tw, th)), comp

    def detect(img):
        try:
            return ocr.detect(img)
        except ocr.OcrError as exc:
            raise StageError("OCR_UNAVAILABLE", str(exc), asset=aid) from exc
    nt_boxes: dict = {}

    def split(det, img, comp) -> tuple[list, list]:
        """OCR 검출 → (구운 글자, 장식). 글자 없는 판을 쓴 요소는 같은 이동의 판 조각도 OCR 해, 거기도 있는 자국(IoU ≥ 0.3)은 그림 장식으로 —
        [실측 H2 오프라인 — 조작 안내 '링크 어택' 띠] 컨셉에 원래 있던 옅은 사선(글자 상자 안)을 OCR 이 글자로 잡아(0.766, 판 이동 1 px 차로 켜졌다
        꺼짐) 판 없이 다시 하자 띠가 줄 보간 패치로 돌아갔다. 판에 codex 가 글자를 남겼다면 그것도 '판에 있음'이 되므로 판은 사람 눈으로 확인한다."""
        if not det["count"]:
            return [], []
        baked, decor = _split_marks(det, T, (img.width, img.height), spec)
        nt = comp.get("notext") or {}
        if baked and nt.get("used"):
            key = tuple(nt["shift"])
            if key not in nt_boxes:
                dx, dy = key
                P = cutout.NOTEXT_SHIFT
                h, w = a_t.shape
                c = fill_from[0][P + dy:P + dy + h, P + dx:P + dx + w]
                al = fill_from[1][P + dy:P + dy + h, P + dx:P + dx + w] if fill_from[1] is not None else a_t
                ref_im = cutout.to_image(c, np.where(keep_t, al, 0.0), (tw, th))
                nb, nd = _split_marks(detect(ref_im), T, (tw, th), spec)
                nt_boxes[key] = [b["box"] for b in nb + nd]

            def iou(p, q):
                ix = max(0.0, min(p[0] + p[2], q[0] + q[2]) - max(p[0], q[0]))
                iy = max(0.0, min(p[1] + p[3], q[1] + q[3]) - max(p[1], q[1]))
                inter = ix * iy
                return inter / max(1e-6, p[2] * p[3] + q[2] * q[3] - inter)
            same = [b for b in baked if any(iou(b["box"], r) >= 0.3 for r in nt_boxes[key])]
            baked = [b for b in baked if b not in same]
            decor = decor + [{**b, "in_text_free_concept": True} for b in same]
        return baked, decor
    im, comp = make(False)
    final = run.path("assets", "final", f"{aid}.png")
    final.parent.mkdir(parents=True, exist_ok=True)
    im.save(final, format="PNG")
    det = detect(final)
    baked, decor = split(det, im, comp)
    if baked and texts:
        # 글자 구멍이 덜 메워져 컨셉 글자 자국이 남았다 — 글자 위젯 상자 전체를 구멍으로 한 번 더(한 색 칠하기 물러남 없음). 글자 없는 판이 있으면 판으로 먼저,
        # 그래도 남으면 판 없이(판이 어긋났거나 판에 글자가 남은 자리 — 예전 길: 줄 보간)
        rec["text_marks_first"] = {"count": det["count"], "max_score": det["max_score"], "baked": baked}
        if comp.get("notext"):
            rec["notext_first"] = comp["notext"]
        im, comp = make(True)
        det = detect(im)
        baked, decor = split(det, im, comp)
        if baked and (comp.get("notext") or {}).get("used"):
            rec["text_marks_second"] = {"count": det["count"], "max_score": det["max_score"], "baked": baked, "notext": comp["notext"]}
            im, comp = make(True, use_nt=False)
            comp["notext"] = {"used": False, "reason": "text marks remained with the text-free concept (whole text boxes too) — redone without it"}
            det = detect(im)
            baked, decor = split(det, im, comp)
        im.save(final, format="PNG")
    st = pp.alpha_stats(im)
    margin = None
    if asset.get("nine_slice"):
        est = pp.estimate_nine_slice(im)
        margin, source = pp.merge_margin(est, asset.get("margin"))
        if margin is None:
            raise StageError("NO_MARGIN", f"'{aid}' is nine_slice, no margin in the spec for the axis that could not be estimated ({est})", asset=aid)
        log["margin"] = {"spec": asset.get("margin"), "estimated": est, "used": margin, "source": source}
    log["ocr"] = det
    count, top = det["count"], det["max_score"]
    if count and decor:
        log["ocr_decor"] = {"count": len(decor), "boxes": decor,
                            "note": "text-like marks outside every text widget box, or also in the text-free concept — drawn in the concept "
                                    "(icons · ornaments), not baked labels"}
        count = len(baked)
        top = max((b["score"] for b in baked), default=0.0)
    log.update(cut=rec, compose=comp, crop_back={"target_box": box, "texture_box": T}, alpha=st, size=[tw, th],
               trim_bbox="skipped (cut from the concept — texture box = widget box or its overhang box)")
    if ov.get("used"):
        log["overhang"] = {"widget_box": box, "texture_box": T, "size_new": [tw, th], "size_old": [int(v) for v in asset["size"]]}
    log["fidelity"] = _extract_fidelity(run, aid, T, cropped, im)
    text = "" if count == 0 else f"{count} text-like box(es), max score {top}"
    return ({"alpha": st["has_alpha"], "nine_slice_margin": margin, "ocr_text": text,
             "ocr": f"{det['engine']} — detection boxes with score ≥ {det['min_score']} and area ≥ {det['min_area_px']} px", "size": [im.width, im.height]},
            log)


def _top_region(spec: dict, wid: str) -> dict | None:
    index = spec_mod.widget_index(spec)
    w = index.get(wid)
    while w is not None and w.get("parent") and w["parent"] != spec.get("root"):
        w = index.get(w["parent"])
    return w if w is not None and w.get("parent") == spec.get("root") else None


def drop_overhang(spec: dict, aid: str, prev: dict | None) -> list[dict]:
    """다시 다듬기 전에 이 에셋의 넘침 장식 Image 를 걷는다 — 장식 위젯 · 그 겹침 허용 쌍을 빼고 주인 브러시를 image 로, 에셋 크기를 원래대로(prev = 지난 기록)."""
    decos = {d for d in overhang_decos(spec) if ((spec_mod.widget_index(spec)[d].get("style") or {}).get("brush") or {}).get("asset") == aid}
    if not decos:
        return []
    index = spec_mod.widget_index(spec)
    for d in decos:
        owner = index[d[:-len(OVERHANG_SUFFIX)]]
        for k, b in (owner.get("style") or {}).items():
            if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset") == aid and b.get("draw_as") == "none":
                b["draw_as"] = "image"
    spec["widgets"] = [w for w in spec["widgets"] if w["id"] not in decos]
    spec["allow_overlap"] = [p for p in spec.get("allow_overlap", []) if not set(p) & decos]
    a = next((x for x in spec.get("assets", []) if x["asset_id"] == aid), None)
    restored = None
    if a and prev and prev.get("size_old") and list(a.get("size") or []) == list(prev.get("size_new") or []):
        a["size"] = list(prev["size_old"])
        restored = prev["size_old"]
    return [{"asset": aid, "removed": sorted(decos), "size_restored": restored}]


def apply_overhang(spec: dict, aid: str, over: dict) -> list[dict]:
    """넘침 그리기 (가') — 쓰는 위젯마다 주인 브러시는 비우고(draw_as none · 에셋은 남김 — 왕복 · 다시 다듬기 식별), 같은 앵커의 캔버스 직속
    장식 Image(<주인>Overhang — 텍스처 상자를 그 위젯 크기 비율로 옮긴 자리 · 같은 z · 그 영역 바로 앞 순서라 주인 영역 · 글자 아래)로 그린다.
    겹치는 캔버스 형제와의 쌍은 allow_overlap 에 넣는다(기록). 에셋 크기 = 텍스처 크기."""
    out = []
    root = spec.get("root")
    cw, ch = (float(v) for v in spec.get("canvas", [1920, 1080]))
    wb, tb = over["widget_box"], over["texture_box"]
    for u in asset_users(spec, aid):
        reg = _top_region(spec, u["id"])
        if reg is None or not u.get("bbox_intent"):
            continue
        ub = [float(v) for v in u["bbox_intent"]]
        su, sv = ub[2] / wb[2], ub[3] / wb[3]
        dx, dy, dw, dh = ub[0] + (tb[0] - wb[0]) * su, ub[1] + (tb[1] - wb[1]) * sv, tb[2] * su, tb[3] * sv
        dx0, dy0 = max(0.0, dx), max(0.0, dy)
        dw, dh = min(cw, dx + dw) - dx0, min(ch, dy + dh) - dy0
        bbox = [round(dx0, 2), round(dy0, 2), round(dw, 2), round(dh, 2)]
        slot = reg.get("slot") or {}
        an, al = list(slot.get("anchors") or [0, 0, 0, 0]), list(slot.get("alignment") or [0, 0])
        pos = [round(bbox[0] + al[0] * bbox[2] - an[0] * cw, 2), round(bbox[1] + al[1] * bbox[3] - an[1] * ch, 2)]
        did = f"{u['id']}{OVERHANG_SUFFIX}"
        deco = {"id": did, "type": "Image", "parent": root, "bbox_intent": bbox,
                "slot": {"kind": "canvas", "anchors": an, "alignment": al, "position": pos, "size": [bbox[2], bbox[3]], "z": slot.get("z", 0)},
                "style": {"brush": {"draw_as": "image", "asset": aid}}}
        for k, b in (u.get("style") or {}).items():
            if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset") == aid:
                b["draw_as"] = "none"
                b.pop("margin", None)
        idx = next(i for i, w in enumerate(spec["widgets"]) if w["id"] == reg["id"])
        spec["widgets"].insert(idx, deco)
        pairs = []
        for w in spec["widgets"]:
            if w.get("parent") == root and w["id"] != did and w.get("bbox_intent") and _overlap(w["bbox_intent"], bbox) > 0:
                pair = sorted([did, w["id"]])
                if pair not in spec.setdefault("allow_overlap", []):
                    spec["allow_overlap"].append(pair)
                pairs.append(w["id"])
        out.append({"asset": aid, "owner": u["id"], "deco": did, "bbox": bbox, "allow_overlap_with": pairs})
    a = next((x for x in spec.get("assets", []) if x["asset_id"] == aid), None)
    if a is not None and out:
        a["size"] = list(over["size_new"])
    return out


def _extract_fidelity(run, aid: str, box, cropped, final) -> dict:
    """컨셉의 같은 상자(되자른 상자 — 위젯 bbox_intent) ↔ 되자른 결과 · 최종 텍스처 — 기록 + assets/compare/<id>.png (gen/fidelity, 게이트 아님)."""
    import numpy as np
    from PIL import Image
    from gen import fidelity
    x0, y0 = max(0, int(round(box[0]))), max(0, int(round(box[1])))
    x1, y1 = int(round(box[0] + box[2])), int(round(box[1] + box[3]))
    with Image.open(run.path("reference.png")) as im:
        concept = np.asarray(im.convert("RGB"))[y0:y1, x0:x1]
    try:
        fid, sheet = fidelity.extract_fidelity(concept, cropped, final)
    except Exception as exc:  # noqa: BLE001 — 기록 지표라 실패해도 run 은 계속(이유를 남김)
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    out = run.path("assets", "compare", f"{aid}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="PNG")
    fid["compare"] = f"assets/compare/{aid}.png"
    fid["concept_box"] = [x0, y0, x1 - x0, y1 - y0]
    return fid


def _apply_margins(run, spec: dict, updates: dict[str, list[float]]) -> list[dict]:
    """추정 margin 을 spec 의 에셋 margin · 그 에셋을 쓰는 box/border 브러시에 넣는다(차이가 MARGIN_UPDATE_MIN 이상일 때만)."""
    changes = []
    for a in spec.get("assets", []):
        new = updates.get(a["asset_id"])
        if new and a.get("margin") != new:
            old = a.get("margin")
            if old is None or max(abs(x - y) for x, y in zip(old, new)) >= MARGIN_UPDATE_MIN:
                a["margin"] = new
                changes.append({"asset": a["asset_id"], "where": "assets", "old": old, "new": new})
    for w in spec.get("widgets", []):
        for key, brush in (w.get("style") or {}).items():
            if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset") in updates and brush.get("draw_as") in ("box", "border"):
                new, old = updates[brush["asset"]], brush.get("margin")
                if old is None or max(abs(x - y) for x, y in zip(old, new)) >= MARGIN_UPDATE_MIN:
                    brush["margin"] = new
                    changes.append({"asset": brush["asset"], "where": f"{w['id']}.style.{key}", "old": old, "new": new})
    return changes


def fixed_size(spec: dict, wid: str) -> bool:
    """위젯 크기가 해상도 · 내용과 무관하게 고정인가 — 최상위 영역(Root 의 자식)이 canvas 점 앵커 + 고정 size(auto_size 아님)."""
    index = spec_mod.widget_index(spec)
    w = index.get(wid)
    if not w:
        return False
    while w.get("parent") and w["parent"] != spec.get("root") and w["parent"] in index:
        w = index[w["parent"]]
    slot = w.get("slot") or {}
    a = slot.get("anchors") or [0, 0, 0, 0]
    return slot.get("kind") == "canvas" and a[0] == a[2] and a[1] == a[3] and bool(slot.get("size")) and not slot.get("auto_size")


def _extract_brushes_to_image(spec: dict, extract_ids: set[str]) -> list[dict]:
    """따온 에셋을 쓰는 box/border 브러시를 image 로(크기 고정 위젯만) — [소스] SlateCore ElementBatcher.cpp:857-860: box 모서리 = 텍스처 픽셀 × margin
    이라, 위젯보다 큰 텍스처(analyze 가 2배까지)는 모서리가 커지고 margin 합이 위젯을 넘으면 가운데가 눌린다(A run 2 — 배너 위+아래 123 px / 높이 124).
    image 는 텍스처를 위젯에 맞춰 통째로 줄이므로 컨셉 비율 그대로다. 크기가 변하는 위젯(늘림 앵커 등)은 box 를 그대로 둔다."""
    changes = []
    for w in spec.get("widgets", []):
        for key, brush in (w.get("style") or {}).items():
            if (key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset") in extract_ids
                    and brush.get("draw_as") in ("box", "border") and fixed_size(spec, w["id"])):
                changes.append({"widget": w["id"], "key": key, "asset": brush["asset"], "old": {"draw_as": brush["draw_as"], "margin": brush.get("margin")},
                                "new": {"draw_as": "image"}})
                brush["draw_as"] = "image"
                brush.pop("margin", None)
    return changes


def _claim_previous_overhang(run, aid: str, over: dict | None) -> None:
    """다시 다듬기에서 건너뛴 에셋(only_assets 밖)의 지난 넘침 자리를 장부에 — 그 텍스처 알파(텍스처 상자) 중 위젯 상자 밖."""
    claims = getattr(run, "overhang_claims", None)
    final = run.path("assets", "final", f"{aid}.png")
    if claims is None or not over or not over.get("texture_box") or not final.is_file():
        return
    import numpy as np
    from PIL import Image
    from gen import cutout
    tx, ty, tw, th = (int(round(float(v))) for v in over["texture_box"])
    wx, wy, ww, wh = (float(v) for v in over.get("widget_box") or over["texture_box"])
    if tw <= 0 or th <= 0:
        return
    with Image.open(final) as im:
        al = np.asarray(im.convert("RGBA").resize((tw, th), Image.Resampling.BILINEAR))[..., 3] / 255.0
    H, W = claims.shape
    yy, xx = np.mgrid[ty:ty + th, tx:tx + tw]
    outside = (xx < wx) | (xx >= wx + ww) | (yy < wy) | (yy >= wy + wh)
    ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W) & outside & (al > cutout.OVERHANG_ALPHA)
    claims[yy[ok], xx[ok]] = True


def run(run, opts) -> str:
    spec = run.read_json("spec.json")
    backends, gen_recs = {}, {}
    gp = run.path("gen.jsonl")
    if gp.is_file():
        for line in gp.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("ok"):
                backends[rec["asset_id"]] = rec["backend"]
                gen_recs[rec["asset_id"]] = rec          # 마지막 성공 기록(재생성이면 새 것)
    previous = {}
    if run.path("manifest.json").is_file():
        previous = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}
    only = set(getattr(opts, "only_assets", None) or [])
    entries, logs, margin_updates = [], [], {}
    prev_over: dict = {}
    if run.path("refine.json").is_file():
        for p in run.read_json("refine.json").get("passes", []):
            for o in p.get("overhang_updates", []):
                if o.get("size_new"):
                    prev_over[o["asset"]] = o
    dropped, over_recs = [], {}
    # 1b 후속 H3 — 넘침이 차지한 빈 자리(위젯 상자 밖) 장부: 앞 에셋(spec 순서)이 가져간 자리는 뒤 에셋의 넘침이 못 가져간다(_cut_entry)
    import numpy as np
    cw, ch = (int(v) for v in spec.get("canvas", [0, 0]))
    run.overhang_claims = np.zeros((ch, cw), bool) if cw > 0 and ch > 0 else None
    run.cut_ownership_cache = {}             # 1b 후속 I — 겹친 자리 물체 단위 소유 지도(_ownership — 이 spec 으로 한 번)
    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if only and aid not in only and aid in previous:
            entries.append(previous[aid])
            _claim_previous_overhang(run, aid, prev_over.get(aid))
            continue
        dropped += drop_overhang(spec, aid, prev_over.get(aid))        # 1b 후속 H — 다시 다듬을 때는 지난 넘침 장식을 걷고 새로
        raw = run.path("assets", "raw", f"{aid}.png")
        if not raw.is_file():
            raise StageError("RAW_MISSING", f"{raw} was not generated", asset=aid)
        backend = backends.get(aid, asset["provenance"])
        if backend == "procedural":
            info, log = _procedural_entry(run, asset, raw, backend)
        else:
            info, log = _generated_entry(run, asset, raw, backend, gen_recs.get(aid), spec)
            if (log.get("margin") or {}).get("source") in ("estimated", "mixed"):
                margin_updates[aid] = log["margin"]["used"]
            if log.get("overhang"):
                over_recs[aid] = log["overhang"]
        logs.append(log)
        final = run.path("assets", "final", f"{aid}.png")
        entries.append({
            "asset_id": aid,
            "kind": asset["kind"],
            "file": f"assets/final/{aid}.png",
            "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
            "size": info["size"],
            "alpha": info["alpha"],
            "nine_slice_margin": info["nine_slice_margin"],
            "ocr_text": info["ocr_text"],
            "ocr": info["ocr"],
            "provenance": asset["provenance"],
            "backend": backend,
            "procedural": asset.get("procedural") or {},
            "prompt": asset.get("prompt"),
            "anchor": bool(asset.get("anchor", False)),
            "ue_path": None,
            "compression": config.compression_for(asset, run.cfg),
        })
    changes = _apply_margins(run, spec, margin_updates) if margin_updates else []
    extract_ids = {a["asset_id"] for a in spec.get("assets", []) if a.get("provenance") == "codex" and a.get("source_mode") == "extract"}
    draw_mode = (run.cfg.get("extract") or {}).get("fixed_size_draw_as", "image")
    brush_changes = _extract_brushes_to_image(spec, extract_ids) if extract_ids and draw_mode == "image" else []
    over_changes = []
    for aid, over in over_recs.items():
        added = apply_overhang(spec, aid, over)
        if added:
            over_changes.append({"asset": aid, **{k: over[k] for k in ("widget_box", "texture_box", "size_old", "size_new")}, "decos": added})
    if changes or brush_changes or over_changes or dropped:
        errs = spec_mod.validate_semantics(spec)
        if errs:
            raise StageError("SPEC_INVALID", "refine left an invalid spec: " + "; ".join(errs[:6]), errors=errs)
        schema.require("spec", spec)
        run.write_json("spec.json", spec)
    manifest = {"schema_version": 1, "run_id": run.run_id, "assets": entries}
    schema.require("manifest", manifest)
    run.write_json("manifest.json", manifest)
    if any(l.get("backend") != "procedural" for l in logs) or changes or brush_changes or over_changes or dropped:
        prev_log = run.read_json("refine.json") if run.path("refine.json").is_file() else {"passes": []}
        prev_log["passes"].append({"attempt": int(getattr(opts, "attempt", 0) or 0), "assets": logs, "margin_updates": changes,
                                   "brush_updates": brush_changes, "overhang_updates": over_changes, "overhang_dropped": dropped})
        run.write_json("refine.json", prev_log)
    comp = ", ".join(f"{e['asset_id']}={e['compression']}" for e in entries)
    texty = [e["asset_id"] for e in entries if e.get("ocr_text")]
    extracted = [l["asset_id"] for l in logs if l.get("source_mode") == "extract"]
    extra = (f"; margins from the images: {len(changes)} change(s)" if changes else "") + (f"; text-like marks in {texty}" if texty else "") \
        + (f"; extracted from the concept: {extracted} (compare: assets/compare/)" if extracted else "") \
        + (f"; fixed-size brushes drawn as image: {[c['widget'] for c in brush_changes]}" if brush_changes else "") \
        + (f"; overhang decorations: {[d['deco'] for c in over_changes for d in c['decos']]}" if over_changes else "")
    return (f"{len(entries)} asset(s) in manifest ({comp}){extra}") if entries else "no assets"
