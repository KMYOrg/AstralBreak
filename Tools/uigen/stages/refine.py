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

def art_files(run) -> tuple[str, str] | None:
    """1b 후속 K-a → L-1 — normalize 가 '글자 없는 아트가 정답'(L-2 원본 생성 아트 — role original)으로 정했으면 (곧은 색, 알파) 파일 이름, 아니면 None.
    글자 든 컨셉이 사람이 승인한 그림이면 None(컨셉 픽셀 + 글자 자리만 판 — diagnose.art_mode 와 같은 조건)."""
    from gen import diagnose as dg
    try:
        bgrec = run.read_json("normalize.json").get("background") or {}
    except (OSError, ValueError):
        return None
    art = bgrec.get("art") or {}
    if dg.art_mode(bgrec) and run.path(str(art.get("color"))).is_file() and run.path(str(art.get("alpha"))).is_file():
        return art["color"], art["alpha"]
    return None


def _art_element_free(run) -> bool:
    """아트가 K 의 요소 없는 판(게이지 채움을 비운 판)인가 — L-2 원본 아트(element_free False)는 아님(diagnose.art_element_free)."""
    from gen import diagnose as dg
    try:
        return dg.art_element_free(run.read_json("normalize.json").get("background") or {})
    except (OSError, ValueError):
        return True


def _art_clear_text(run, col, alpha):
    """1b 후속 K-a — 글자 없는 아트에서 투명 위 글자 자리의 잔상을 지운다: 글자 상자(+ 빛 + 2 px) 안을 컨셉(곧은 색 · 알파)으로 바꾸고, 컨셉 글자 획
    (컨셉 ↔ 아트가 다른 픽셀 + 3 px + 빛)만 둘레 컨셉으로 메운다. 상자 둘레 컨셉이 불투명(띠 · 패널 위 글자)이면 아트 그대로.
    [실측 K R20261117_233356 — codex 요소 없는 판이 투명 위 붉은 '오의 불가' 를 붉은 얼룩으로 남김: 렌더 얼룩 + 숨은 상태 오판]. → (색, 알파) — 기록은 run 폴더 art_clear.json."""
    import numpy as np
    from PIL import Image
    from gen import diagnose as dg
    if not run.path("spec.json").is_file() or not run.path("reference_alpha.png").is_file():
        return col, alpha
    if dg.residue_free((run.read_json("normalize.json").get("background") or {}).get("art")):
        return col, alpha           # 1b 후속 L-2 — 원본 아트는 글자를 그린 적 없다: 지울 잔상이 없고, 글자 상자 안 아트 장식을 비우면 안 된다
    with Image.open(run.path("reference_color.png")) as c, Image.open(run.path("reference_alpha.png")) as a:
        cc, ca = np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0
    col, alpha, recs = dg.clear_text_residue(col, alpha, cc, ca, run.read_json("spec.json"))
    if recs:
        run.write_json("art_clear.json", {"texts": recs})
    return col, alpha


def _reference_layers(run, bg: str):
    """→ (곧은 색 float HxWx3, 알파 0 ~ 1 또는 None) — ⓐ ⓑ 는 normalize 의 reference_color · reference_alpha, ⓒ 는 reference.png 색 · 알파 없음."""
    import numpy as np
    from PIL import Image
    art = art_files(run)
    if art and bg in ("transparent", "flat"):
        # 1b 후속 K-a — 우리가 만든 컨셉: 아트의 정답 = 글자 없는 아트(글자 구멍 · 메우기 없음) — 단 투명 위 글자 자리의 잔상은 컨셉 투명도로
        with Image.open(run.path(art[0])) as c, Image.open(run.path(art[1])) as a:
            col, alpha = np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0
        return _art_clear_text(run, col, alpha)
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
    if art_files(run):
        texts = []          # 1b 후속 K-a — 글자 없는 아트에서 오린다: 지울 글자가 없다
        rec["art"] = "text-free art (generated concept) — no text holes"
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
    if fill_from is not None and fill_from[1] is not None and texts:
        # 1b 후속 J — 글자 없는 판이 있으면 글자마다 '판과 다른 글자 획'만 판 픽셀로 먼저(_plate_item_fill — 정적 판과 같은 길), 못 맞춘 글자만 아래
        # 사각 구멍(cutout.compose). 사각형째 판으로 바꾸면 배너 아래 반투명 그림자 줄까지 판의 더 진한 그림자로 바뀌어 회색 위 어두운 띠가 생겼다
        # [실측 J R20261117_180053 — 버스트 배너 아래 2 px, 알파 0.28 → 0.72]
        col_t, a_t = col_t.copy(), a_t.copy()
        left, done = [], []
        orig = (col_t.copy(), a_t.copy())
        for t in texts:
            r = _plate_item_fill(col_t, a_t, fill_from[0], fill_from[1], t, orig=orig)
            done.append({"text": t.get("id"), **{k: v for k, v in r.items() if k in ("used", "shift", "diff", "hole_px", "reason", "alpha_from", "halo_px",
                                                                                      "line_up_diff", "plate_clear_px")}})
            if not (r.get("used") or r.get("nothing")):
                left.append(t)
        rec["glyph_fill"] = done
        texts = left

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
        # 판을 쓴 이동 — compose 의 글자 구멍(사각) 또는 J 글자 획만 메우기(glyph_fill)의 첫 이동
        shift = nt["shift"] if nt.get("used") else next((g["shift"] for g in rec.get("glyph_fill", []) if g.get("used")), None)
        if baked and shift is not None and fill_from is not None:
            key = tuple(shift)
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
    if count and art_files(run) and baked:
        # 1b 후속 K-a — 아트 모드: 텍스처가 글자 없는 아트 그대로라 자국은 모두 '글자 없는 판에도 있는 자국'(장식) — 글자 잔상은 진단 E1(획 둘레 ↔ 글자 든 컨셉) ·
        # E8 이 본다 [실측 K R20261118_004331 단색 버스트 배너 장식 0.74]
        decor, baked = list(decor or []) + list(baked), []
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


# ---------------------------------------------------------------------------------------------------------------------
# 1b 후속 J-a — 정적 판 (stages/layer)

PLATE_TEXT_MARGIN = 24      # 글자 메우기 창 = 글자 상자 + 이만큼(px) — 메우기 원천 · 판 정합 둘레가 창 안에 들게
PLATE_TEXT_IN = 0.3         # 글자 상자 넓이의 이만큼 이상이 판 마스크 안이어야 이 판이 그 글자 자리를 메운다(나머지는 기능 요소 몫)


def _merge_windows(wins: list[list[int]]) -> list[list[int]]:
    wins = [list(w) for w in wins]
    changed = True
    while changed:
        changed = False
        out = []
        for w in wins:
            for o in out:
                if w[0] < o[2] and o[0] < w[2] and w[1] < o[3] and o[1] < w[3]:
                    o[:] = [min(o[0], w[0]), min(o[1], w[1]), max(o[2], w[2]), max(o[3], w[3])]
                    changed = True
                    break
            else:
                out.append(w)
        wins = out
    return wins


PLATE_GLYPH_GROW = 3        # 판으로 바꿀 자리 = 글자 획(컨셉 ↔ 글자 없는 판이 다른 픽셀) + 이만큼(안티앨리어싱 · 외곽선 섞인 가장자리) — K: 빛은 실제 밝은 픽셀만
PLATE_HALO_L = 10.0         # 1b 후속 K (나) — 빛 글자: 빛 반경 안에서 컨셉이 판보다 이만큼(밝기 0 ~ 255) 넘게 밝은 픽셀만 메울 자리에 더함
PLATE_TONE_MAX = 40.0       # 1b 후속 K (나) — 판 조각 색조 보정(둘레 고리 평면 맞춤) 채널당 상한
PLATE_TEXT_DE = 20.0        # 획 = 글자색에 ΔE00 이만큼 안으로 가까운 픽셀(글자색을 알 때)
PLATE_ALPHA_MISMATCH = 0.3  # 글자 둘레에서 판 알파 ↔ 컨셉 알파 중앙값 차가 이보다 크면 판 알파를 안 믿는다(둘레 컨셉 알파를 이어 씀)
PLATE_CLEAR_ALPHA = 0.35    # 1b 후속 J — 글자 둘레 컨셉 알파 중앙값이 이보다 낮고(투명 위 글자) 판 알파가 안 맞으면 판 정합 없이 둘레 컨셉으로 메운다
                            # [실측 J R20261117_195827 — 본문 SDF 빛을 단 '오의 불가': 빛 번짐까지 획이 돼 둘레가 codex 판의 불투명 바탕(0.9)에 닿아 정합 차 30 → 줄 보간 물러남 · 글자 윗획이 판에 남음]
PLATE_FILL_SOURCE_DIFF = 40.0   # 둘레 컨셉으로 메울 때 원천 = 둘레 미리 곱한 색 중앙값과 채널 최대 차가 이 미만인 픽셀(밝은 이웃 장식 가장자리 빼기)
PLATE_EMPTY_GAUGE = 0.02   # 판 위 게이지(채움이 컨셉 모양이 아닌 것)의 컨셉 진행률이 이 이하면 판을 안 바꾼다 — 컨셉이 이미 빈 트랙
                            # [실측 J R20261117_192631 파티 HUD — 0 % 게이지 셋을 codex 판 트랙으로 바꿔 줄마다 국소 ΔE00 23 ~ 31]


def _font_colors(w: dict) -> list[list[int]]:
    """글자 위젯의 글자색(그라데이션이면 위 · 아래) RGB 목록."""
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    g = f.get("gradient") if isinstance(f.get("gradient"), dict) else None
    out = []
    for h in ([g.get("top_color"), g.get("bottom_color")] if g else [f.get("color") or spec_mod.FONT_DEFAULT.get("color")]):
        h = str(h or "").lstrip("#")
        if len(h) >= 6:
            out.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    return out


NARROW_EDGE_PX = 3          # 1b 후속 L-3b 좁은 둘레 메움 — 획 · 빛 반경 밖으로 외곽선 · 그림자를 볼 거리(px)
NARROW_DIFF = 12.0          # 그 안에서 매끈한 바탕과 채널 최대 차가 이보다 크면 글자 몫(빛 · 외곽선 · 그림자)
SMOOTH_FILL_SIGMAS = (2.0, 4.0, 8.0, 16.0, 32.0)   # 매끈한 메움 — 원천 가우스 가중 평균, 받침(가중치 합)이 모자라면 다음 크기로
SMOOTH_FILL_SUPPORT = 0.05


def _smooth_fill(pm, alpha, src) -> tuple:
    """1b 후속 L-3b — 원천(src) 픽셀의 미리 곱한 색 · 알파를 가우스 가중 평균으로(정규화 합성곱 — 작은 반경부터, 받침이 모자란 픽셀만 큰 반경). 줄 보간과 달리
    줄마다 다른 양끝 원천을 잇지 않아 가로 줄무늬가 없다. → (미리 곱한 색 HxWx3, 알파 HxW) — 원천이 없으면 둘 다 0."""
    import cv2
    import numpy as np
    H, W = alpha.shape
    out_pm, out_a = np.zeros((H, W, 3)), np.zeros((H, W))
    w = np.asarray(src, np.float32)
    if not w.any():
        return out_pm, out_a
    done = np.zeros((H, W), bool)
    for s in SMOOTH_FILL_SIGMAS:
        den = cv2.GaussianBlur(w, (0, 0), s)
        ok = (den > SMOOTH_FILL_SUPPORT) & ~done
        if ok.any():
            num = np.dstack([cv2.GaussianBlur((pm[..., i] * w).astype(np.float32), (0, 0), s) for i in range(3)])
            na = cv2.GaussianBlur((alpha * w).astype(np.float32), (0, 0), s)
            out_pm[ok] = num[ok] / den[ok][:, None]
            out_a[ok] = na[ok] / den[ok]
            done |= ok
        if done.all():
            break
    if not done.all():
        out_pm[~done] = np.median(pm[w > 0], axis=0)
        out_a[~done] = float(np.median(alpha[w > 0]))
    return out_pm, np.clip(out_a, 0.0, 1.0)


PLATE_SAME_SHIFT = 2     # 구조물 판정 — 판을 이만큼(px) 옮긴 것 중 가장 작은 차 · 가장 밝은 값(다시 그린 판의 몇 px 어긋남을 덮음)
PLATE_SAME_RATIO = 0.6     # 판(이동 중 가장 밝은 값)이 컨셉 밝기(미리 곱한 색 채널 최대)의 이만큼 이상이면 판에도 같은 것이 있다


def _plate_same(cw, aw, ntc_w, nta_w, P: int, ratio: bool = True):
    """1b 후속 L-3b — 컨셉 픽셀 중 글자 없는 판에도 있는 것 = 구조물(글자 · 빛이 아님): 미리 곱한 색 채널 최대 차의 ±PLATE_SAME_SHIFT 이동 최소 < INK_FLOOR,
    또는 판이 그 둘레에서 컨셉만큼 밝다(≥ PLATE_SAME_RATIO 배) — codex 판은 구조선을 1 px 어긋나고 더 밝게 다시 그려 차가 42 ~ 46 이고, 글자 빛 줄은 판이
    어두워(밝기 비 0.3) 차가 33 ~ 57 이라 차 문턱 하나로는 못 가른다 [실측 L 오프라인 092315 — 이름 아래 HP 막대 윗선]."""
    import numpy as np
    from gen import diagnose as dg
    h, w = aw.shape
    pm_c = cw * aw[..., None]
    best = np.full((h, w), np.inf)
    pmax = np.zeros((h, w))
    s = min(PLATE_SAME_SHIFT, P)
    for dy in range(-s, s + 1):
        for dx in range(-s, s + 1):
            pm_n = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w] * nta_w[P + dy:P + dy + h, P + dx:P + dx + w][..., None]
            best = np.minimum(best, np.abs(pm_c - pm_n).max(axis=2))
            pmax = np.maximum(pmax, pm_n.max(axis=2))
    if not ratio:
        # 밝기 비 규칙은 투명 · 어두운 바탕 위 밝은 구조선용 — 밝은 바탕(회색 배지) 위 흰 글자는 판 배지 밝기가 글자의 0.72 라 구조물로 오판했다
        # [실측 L run R20261118_122008 조작 안내 'E' · 'T' — 획에서 빠져 자국 → 상자 통째 다시 → E1]
        return best < dg.INK_FLOOR
    cmag = pm_c.max(axis=2)
    return (best < dg.INK_FLOOR) | ((cmag > dg.INK_FLOOR) & (pmax >= PLATE_SAME_RATIO * cmag))


def _narrow_neigh_fill(col, a, win, cw, aw, g0, rect, glow: float, bh: float, why: str, **extra) -> dict:
    """1b 후속 L-3b — 판 정합이 안 되는 글자의 둘레 컨셉 메움(제자리에서 고침): 바꿀 자리 = 획(g0) + PLATE_GLYPH_GROW, 빛 글자면 빛 반경 안에서 '매끈한 바탕
    (획 · 빛 반경 밖 원천의 가우스 가중 평균)보다 PLATE_HALO_L 넘게 밝은' 픽셀 중 획에 이어진 것(글자보다 긴 가로 · 세로 구조선 제외 — 판 길 K (나) 와 같은 규칙),
    글자 상자(+2) 안까지. 원천 = 바꿀 자리 밖에서 둘레 대표색(빛 반경 밖 고리 중앙값)과 채널 차 PLATE_FILL_SOURCE_DIFF 미만(이웃 글자 · 밝은 장식 가장자리 빼기)."""
    import cv2
    import numpy as np
    from gen import cutout
    from gen import diagnose as dg
    y0, y1, x0, x1 = win
    h, w = aw.shape
    pm_w = cw * aw[..., None]
    gr = int(np.ceil(glow))
    reach = dg._dilate(g0, gr + PLATE_GLYPH_GROW + NARROW_EDGE_PX)
    ring = dg._dilate(reach, cutout.NOTEXT_RING) & ~reach
    med = np.median(pm_w[ring], axis=0) if int(ring.sum()) >= 10 else np.median(pm_w[~reach], axis=0)
    similar = np.abs(pm_w - med).max(axis=2) < PLATE_FILL_SOURCE_DIFF
    hole = dg._dilate(g0, PLATE_GLYPH_GROW)
    # 원천 = 둘레 대표색과 비슷한 픽셀(이웃 장식 · 막대 색이 구멍으로 번지지 않게). 거르지 않으면 트랙 끝에 걸친 '0 %' 에 위 초록 막대가 흘러내렸다 —
    # 거르면 그 자리 트랙이 다수(투명)에 밀려 짧아진다(판이 트랙까지 지운 모호한 자리 — 진단에 맡김) [실측 L 오프라인 092315 '0 %']
    bg_pm, _ = _smooth_fill(pm_w, aw, ~reach & similar)
    # 획에 이어진 '매끈한 바탕과 다른' 픽셀 — 밝은 빛만이 아니라 어두운 외곽선 · 그림자도(채널 최대 차 — 파란 빛은 루마 가중치가 작아 루마로는 못 넘었다)
    # [실측 L run R20261118_113122 배너 '3' — 외곽선이 텍스처에 남아 baked_text 0.709 · L-3b 오프라인 092315 이름 파란 빛 잔상]
    br = reach & (np.abs(pm_w - bg_pm).max(axis=2) > NARROW_DIFF)
    lh = cv2.morphologyEx(br.astype(np.uint8), cv2.MORPH_OPEN, np.ones((1, max(3, int(1.5 * bh))), np.uint8)) > 0
    lv = cv2.morphologyEx(br.astype(np.uint8), cv2.MORPH_OPEN, np.ones((max(3, int(1.05 * bh)), 1), np.uint8)) > 0
    br &= ~dg._dilate(lh | lv, 1)
    n_b, lab_b = cv2.connectedComponents((br | g0).astype(np.uint8), connectivity=8)
    touch = np.unique(lab_b[g0 & (lab_b > 0)])
    br &= np.isin(lab_b, touch[touch > 0])
    halo_px = int((br & ~hole).sum())
    hole = dg._dilate(hole | br, 1)
    hole &= rect
    if not hole.any():
        return {"used": False, "reason": "no glyph pixels to fill inside the text box", "nothing": True}
    fpm, fa = _smooth_fill(pm_w, aw, ~hole & similar if int((~hole & similar).sum()) >= 10 else ~hole)
    blend = cv2.GaussianBlur(dg._dilate(hole, 1).astype(np.float32), (0, 0), 1.0).astype(float)
    blend = np.clip(np.where(hole, 1.0, blend), 0.0, 1.0)
    out_a = blend * fa + (1 - blend) * aw
    pm = blend[..., None] * fpm + (1 - blend)[..., None] * pm_w
    col[y0:y1, x0:x1] = np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw)
    a[y0:y1, x0:x1] = out_a
    return {"used": True, "shift": [0, 0], "hole_px": int(hole.sum()), "halo_px": halo_px, "whole": False, "alpha_from": why, "fill": "smooth", **extra}


def _plate_item_fill(col, a, ntc_pad, nta_pad, item: dict, whole: bool = False, orig=None) -> dict:
    """정적 판의 한 글자(또는 게이지 막대) 자리를 글자 없는 판 픽셀로(제자리에서 고침) → 기록. used False 면 고치지 않음(이유).
    바꿀 자리 = 컨셉 ↔ 판이 다른 글자 획(gen/diagnose 와 같은 정의 — 가는 선 · 상자 밖 덩어리 · 가는 호 빼기) + PLATE_GLYPH_GROW + 빛 —
    글자 상자 사각형 전체를 바꾸면 codex 판이 몇 px 다르게 다시 그린 배지 테두리가 사각형 가장자리에서 어긋나 '배지 양옆 선'이 됐다
    [실측 J-a 오프라인 R20261117_154442 — E · T · R 배지 양옆 국소 ΔE00 최대 17.6]. whole(OCR 이 자국을 잡은 뒤) · 게이지 막대는 상자째.
    정합 = 획 둘레로 ±NOTEXT_SHIFT(cutout._notext_shift), 판 알파 수준 맞춤(_notext_alpha_gain) · 흐린 경계 섞기는 cutout.compose 와 같다."""
    import cv2
    import numpy as np
    from gen import cutout
    from gen import diagnose as dg
    H, W = a.shape
    P = cutout.NOTEXT_SHIFT
    bx, by, bw, bh = (float(v) for v in item["box"])
    glow = float(item.get("glow") or 0)
    e = max(6.0, 0.5 * bh) if not item.get("gauge") else float(cutout.NOTEXT_RING + 2)
    m = int(np.ceil(e + glow + PLATE_GLYPH_GROW + cutout.NOTEXT_RING + 2))
    x0, y0 = max(0, int(np.floor(bx)) - m), max(0, int(np.floor(by)) - m)
    x1, y1 = min(W, int(np.ceil(bx + bw)) + m), min(H, int(np.ceil(by + bh)) + m)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return {"used": False, "reason": "outside the plate"}
    cw, aw = col[y0:y1, x0:x1], a[y0:y1, x0:x1]
    ntc_w, nta_w = ntc_pad[y0:y1 + 2 * P, x0:x1 + 2 * P], nta_pad[y0:y1 + 2 * P, x0:x1 + 2 * P]
    h, w = aw.shape
    own = np.zeros((h, w), bool)
    own[max(0, int(by) - y0):min(h, int(np.ceil(by + bh)) - y0), max(0, int(bx) - x0):min(w, int(np.ceil(bx + bw)) - x0)] = True
    rect = dg._dilate(own, 2)
    if item.get("mask") is not None:
        # 1b 후속 J — 가득 찬 게이지: 채움 텍스처(컨셉 조각)가 덮는 자리 그대로만 판 픽셀로(넓히기 · 흐린 섞기 없음 — 채움이 그 자리를 알파 1 로 덮는다)
        hole = np.asarray(item["mask"], bool)[y0:y1, x0:x1]
        if not hole.any():
            return {"used": False, "reason": "the gauge track mask is empty here", "nothing": True}
        sh = cutout._notext_shift(cw, aw, hole, dg._dilate(hole, 3), ntc_w, nta_w, strokes=hole)
        dx, dy = sh.get("shift") or (0, 0)
        if sh.get("diff") is None or sh["diff"] > cutout.NOTEXT_MAX_DIFF:
            dx, dy = 0, 0
        nc, na = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w], nta_w[P + dy:P + dy + h, P + dx:P + dx + w]
        col[y0:y1, x0:x1] = np.where(hole[..., None], nc, cw)
        a[y0:y1, x0:x1] = np.where(hole, na, aw)
        return {"used": True, "shift": [int(dx), int(dy)], "diff": sh.get("diff"), "hole_px": int(hole.sum()), "whole": True, "mask": "full gauge track"}

    near = None
    if not (item.get("gauge") or whole):
        # 글자색에 가까운 픽셀만 획 — codex 판이 배지를 몇 px 크게 다시 그려 테두리 어긋남 덩어리도 '판과 다른 픽셀'이라 배지 전체가 판으로 바뀌었다
        # [실측 J-a 오프라인 154442 T 배지 — 획 상자 74 × 72, 'T' 는 30 × 36]. 글자색은 spec 이 아니라 컨셉에서 — 자기 상자 안에서 판과 가장 많이 다른
        # 픽셀(위 · 아래 반의 중앙값 — 그라데이션)로 잰다: analyze 색 파생이 '점프' 를 남색으로 잘못 잡자 띠의 어두운 면이 '글자색 근처'가 돼 판으로
        # 바뀌었다 [실측 J R20261117_174247 — 글자 오른쪽 국소 ΔE00 17.6]
        from core import color as color_mod
        d0 = np.abs(cw * aw[..., None] - ntc_w[P:P + h, P:P + w] * nta_w[P:P + h, P:P + w][..., None]).max(axis=2)
        strong = own & (d0 > dg.INK_MIN)
        # 1b 후속 L-3b — 상자 밖으로 이어진 덩어리(모서리 장식 — 판이 다르게 다시 그려 '가장 다른 픽셀'이 됨)는 글자색 원천에서 뺀다 [실측 L run R20261118_115506
        # 단색 — 패널 폭 '2/4' 상자에서 글자색을 금색 장식으로 잡아 '2/' 는 못 잡고 오른쪽 아래 장식을 지움]
        strong_f = dg._filter_glyph_parts(strong, own)
        if int(strong_f.sum()) >= 20:
            strong = strong_f
        if int(strong.sum()) >= 20:
            strong &= d0 >= np.percentile(d0[strong], 60)
            ys = np.nonzero(strong)[0]
            mid = float(np.median(ys))
            cols = [np.median(cw[strong & (np.arange(h)[:, None] <= mid)], axis=0), np.median(cw[strong & (np.arange(h)[:, None] > mid)], axis=0)]
            cols = [c for c in cols if np.isfinite(c).all()]
        else:
            cols = [np.asarray(c, float) for c in (item.get("colors") or [])]
        if cols:
            lab = color_mod.srgb_to_lab(cw)
            near = np.min([color_mod.delta_e00(lab, color_mod.srgb_to_lab(np.asarray(c, float).reshape(1, 1, 3))) for c in cols], axis=0) < PLATE_TEXT_DE

    def plate_text(nc, na):
        """1b 후속 L-3b — 판에 남은 글자 자국(codex 판이 못 지운 획): 판 픽셀이 판 자기 둘레(미디언 — 글자 높이 크기 창)와 INK_MIN 넘게 다름 · 글자 상자 근처만.
        다시 그린 자국은 색이 컨셉 글자색과 달라(더 밝게) 글자색으로는 못 잡았다 [실측 L run R20261118_115506 단색 '2/']. 글자색 근처가 없으면 None."""
        if near is None:
            return None
        pm_n = np.clip(np.asarray(nc, float) * np.asarray(na, float)[..., None], 0, 255).astype(np.uint8)
        k = max(5, int(round(bh)) | 1)
        med_n = cv2.medianBlur(pm_n, min(k, 255)).astype(float)
        return (np.abs(pm_n.astype(float) - med_n).max(axis=2) > dg.INK_MIN) & dg._dilate(own, int(round(e)))

    def glyph_of(nc, na):
        if item.get("gauge") or whole:
            return rect.copy()
        d = np.abs(cw * aw[..., None] - nc * na[..., None]).max(axis=2)
        diff = d > dg.INK_MIN
        pt = plate_text(nc, na)
        if pt is not None:
            # 판에도 같은 글자가 남았으면 '판과 다른 픽셀'로는 획이 안 잡힌다 — 그 자리도 획(메움은 아래에서 판 대신 둘레)
            # [실측 L run R20261118_115506 단색 — 요소 없는 판에 '2/' 가 남아 체인 패널 텍스처에 '2/' 가 구워짐, baked_text 0.818]
            diff |= pt & near
        cand = dg._dilate(own, int(round(e))) & diff
        if near is not None:
            cand &= near
            # 판에도 있는 구조물(장식 · 테두리선 — 판이 몇 px 어긋나고 밝기가 달라도)은 획이 아니다 [실측 L run R20261118_115506 단색 — 패널 폭 '2/4' 상자 안
            # 모서리 장식 하이라이트 · 아래 금선이 글자색 근처라 획으로 잡혀 얼룩]
            cand &= ~same_struct
        return dg._filter_glyph_parts(dg._drop_small(cand), own)
    same_struct = _plate_same(cw, aw, ntc_w, nta_w, P, ratio=False) & (aw > 0.5) if near is not None else None
    g0 = glyph_of(ntc_w[P:P + h, P:P + w], nta_w[P:P + h, P:P + w])
    if not g0.any():
        return {"used": False, "reason": "no glyph pixels differ from the text-free concept here", "nothing": True}
    if not (item.get("gauge") or whole):
        # 투명 위 글자(상자 둘레 컨셉 알파가 낮고 판은 불투명 바탕) — 판 픽셀은 어차피 안 쓴다(알파 · 색 모두 둘레 컨셉에서). 정합을 요구하면 빛 번짐까지 획이 된
        # 글자는 둘레가 판의 불투명 바탕에 닿아 늘 실패해 줄 보간으로 물러났다(글자 윗획이 판에 남음 — PLATE_CLEAR_ALPHA). 획도 판과의 차이로는 못 찾는다
        # (판이 불투명이라 상자 전체가 한 덩어리 → 걸러져 '오의' 만 남음) → 바꿀 자리 = 글자 상자 전체, 단 상자 밖으로 이어진 불투명 구조물(프레임 선)은 3 px 넓혀 지킨다
        import cv2
        n_o, lab_o = cv2.connectedComponents((aw > 0.5).astype(np.uint8), connectivity=8)
        cross = np.unique(lab_o[(lab_o > 0) & ~rect])
        protect = dg._dilate(np.isin(lab_o, cross[cross > 0]), 3) if len(cross) else np.zeros_like(rect)
        if near is not None and protect.any():
            # 글자색에 가까운 픽셀(+ 빛 반경)은 지키지 않는다 — 빛 번짐이 글자 아랫획을 상자 밖 막대 · 프레임과 한 덩어리로 이어 글자가 판에 남았다
            # [실측 J R20261117_205334 파티 HUD 이름 — 컨셉 획 아래 반이 판에 남아 진단 높이 비 1.6]
            # 1b 후속 L-3b — 단 글자 없는 판에도 있는 구조물(판 ±2 px 이동 최소 차 < INK_FLOOR · 불투명 — 막대 윗선 등)은 계속 지킨다: 글자 · 빛은 판에 없고
            # 구조물은 있다 [실측 K R20261118_092315 · L 오프라인 — HP 막대 윗선 청록 빛 줄이 이름 · HP 숫자 아래에서 지워져 어두운 띠 E1 20 ~ 26.
            # 선 모양(길고 얇음)으로 가르면 빛으로 이어진 글자 획 · 띠까지 선으로 잡혔다]
            # (판이 글자 자리의 구조물까지 지운 곳 — 트랙 끝에 걸친 '0 %' 의 '0' 속 — 을 '둘레 구조물 색과 같은 픽셀'로 지키는 규칙은 구조물에 이어진 컨셉 빛까지
            # 지켜 막대 위 회녹색 얼룩을 만들어 뺐다 [실측 L 오프라인 092315])
            same = _plate_same(cw, aw, ntc_w, nta_w, P) & (aw > 0.5)
            protect &= ~(dg._dilate(near & rect, int(np.ceil(glow)) + 2) & ~dg._dilate(same, 1))
        h0 = rect & ~protect
        r0 = dg._dilate(rect, cutout.NOTEXT_RING) & ~rect & ~protect
        clear0 = float(np.median(aw[r0])) if int(r0.sum()) >= 20 else None

        def neigh_fill(why: str, **extra) -> dict:
            blend = cv2.GaussianBlur(dg._dilate(h0, cutout.NOTEXT_GROW).astype(np.float32), (0, 0), cutout.NOTEXT_BLUR).astype(float)
            blend = np.clip(np.where(h0, 1.0, np.where(protect, 0.0, blend)), 0.0, 1.0)     # 지킨 구조물은 흐린 경계로도 안 섞음(L-3b)
            # 원천 = 둘레 대표(미리 곱한 색 중앙값)에 가까운 픽셀만 — 줄 보간이 이웃 장식의 밝은 가장자리를 끌어와 회색 줄무늬가 됐다
            # [실측 J R20261117_205334 파티 HUD 이름 — 초상화 테두리 가장자리]
            pm_w = cw * aw[..., None]
            med = np.median(pm_w[r0], axis=0) if int(r0.sum()) else np.zeros(3)
            similar = np.abs(pm_w - med).max(axis=2) < PLATE_FILL_SOURCE_DIFF
            src_ok = ~h0 & (similar if int((similar & r0).sum()) >= 10 else True)
            # 1b 후속 L-3b — 매끈한 메움(원천 가우스 가중 평균). 줄 보간은 줄마다 다른 양끝 원천을 이어 가로 줄무늬를 남겼다 [실측 K R20261118_092315 이름]
            fpm, fa = _smooth_fill(pm_w, aw, src_ok)
            out_a = blend * fa + (1 - blend) * aw
            pm = blend[..., None] * fpm + (1 - blend)[..., None] * pm_w
            col[y0:y1, x0:x1] = np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw)
            a[y0:y1, x0:x1] = out_a
            return {"used": True, "shift": [0, 0], "hole_px": int(h0.sum()), "whole": False, "alpha_from": why, **extra}
        if int(r0.sum()) >= 20 and h0.any():
            na0 = nta_w[P:P + h, P:P + w]
            mism0 = float(np.median(np.abs(na0[r0] - aw[r0])))
            clear0 = float(np.median(aw[r0]))
            # 1b 후속 L-3b — 글자 획 둘레(빛 반경 밖 고리)가 투명하면 판 알파가 맞든 안 맞든 판을 쓰지 않는다: 상자(구조물 빼고)를 둘레 매끈한 메움(≈ 투명) —
            # 글자 · 빛은 엔진이 그린다. 판도 투명이면 예전엔 정합으로 갔다 — 빛 덩어리(컨셉 알파 1)가 정합 둘레를 넘어 실패하면 줄 보간 줄무늬, 정합되면 판 잔상을
            # 알파 이득(× 4)이 키워 유령 숫자가 남았다 [실측 K R20261118_092315 이름 · L 오프라인 '/44993']. 상자 둘레 고리가 아니라 획 둘레로 — 빛 여백까지
            # 넓힌 상자가 배너 밖으로 나가 배너 위 '3' 을 투명 위 글자로 봐 외곽선이 남았다 [실측 L run R20261118_113122 — baked_text 0.709]
            rg = int(np.ceil(glow)) + PLATE_GLYPH_GROW
            ring_g = dg._dilate(g0, rg + cutout.NOTEXT_RING) & ~dg._dilate(g0, rg)
            clear_g = float(np.median(aw[ring_g])) if int(ring_g.sum()) >= 20 else 1.0
            if clear_g < PLATE_CLEAR_ALPHA or (mism0 > PLATE_ALPHA_MISMATCH and clear0 < PLATE_CLEAR_ALPHA):
                return neigh_fill("concept neighbourhood — text on a (nearly) transparent concept (the text-free concept is not used)",
                                  alpha_mismatch=round(mism0, 3), ring_alpha=round(clear0, 3), glyph_ring_alpha=round(clear_g, 3))
    else:
        neigh_fill = None
    # 빛 글자는 정합 둘레를 빛 반경 밖으로 — 둘레가 빛 번짐 안이면 codex 판(빛까지 지움)과 늘 25 ~ 28 차이로 정합 실패였다
    # [실측 J R20261117_210351 파티 HUD 이름 · HP 숫자 — 둘레 보간으로 물러나 컨셉 획 측정이 깨짐]
    gr = int(np.ceil(glow))
    # 정합은 원래 컨셉에 대고(orig) — 앞 글자를 먼저 메운 결과가 둘레를 바꿔 같은 글자가 순서에 따라 정합 11 ↔ 30 으로 갈렸다 [실측 L 오프라인 092315 '0 %']
    cw_r, aw_r = (orig[0][y0:y1, x0:x1], orig[1][y0:y1, x0:x1]) if orig is not None else (cw, aw)
    sh = cutout._notext_shift(cw_r, aw_r, dg._dilate(g0, gr) if gr else g0, dg._dilate(g0, 3 + gr), ntc_w, nta_w, strokes=g0)
    if sh.get("diff") is None or sh["diff"] > cutout.NOTEXT_MAX_DIFF:
        if neigh_fill is not None and h0.any() and int(r0.sum()) >= 20:
            # 정합이 안 되면 둘레 컨셉으로 — 단 좁은 자리만(획 + 안티앨리어싱 + 획에 이어진 실제 빛 픽셀, 판 정합 길의 K (나) 와 같은 범위) · 매끈한 가우스 가중
            # 메움. 글자 상자 전체를 줄 보간으로 메우자 가로 줄무늬가 생기고 그 줄무늬가 컨셉 획 측정을 오염시켜 글자색까지 어둡게 맞췄다
            # [실측 K R20261118_092315 파티 HUD 이름 — 회청색 + 줄무늬 · 측정 불가]. 예전 물러남(cutout.compose 줄 상자 + 가로 여유)은 이웃 장식까지 팠다
            # [실측 J R20261117_204115 — 초상화 테두리 오른쪽 8 × 33 구멍]
            return _narrow_neigh_fill(col, a, (y0, y1, x0, x1), cw, aw, g0, rect, glow, bh,
                                      f"concept neighbourhood around the glyphs — the text-free concept does not line up (ring diff {sh.get('diff')})",
                                      line_up_diff=sh.get("diff"))
        return {"used": False, "reason": f"text-free concept does not line up here (ring diff {sh.get('diff')}, ring {sh.get('ring_px')} px)", **sh}
    dx, dy = sh["shift"]
    nc, na = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w], nta_w[P + dy:P + dy + h, P + dx:P + dx + w]
    glyph = glyph_of(nc, na) | (g0 if not (item.get("gauge") or whole) else False)
    tone = None
    if item.get("gauge") or whole:
        hole = dg._dilate(glyph, PLATE_GLYPH_GROW + int(np.ceil(glow)))
    else:
        # 1b 후속 K (나) — 좁은 메우기: 획 + 안티앨리어싱(PLATE_GLYPH_GROW)만, 빛 글자면 빛 반경 안에서 컨셉이 판보다 실제로 밝은 픽셀(컨셉 빛 번짐 — 엔진이
        # 다시 그린다)만 더한다. 빛 크기만큼 통째로 부풀리면 판 조각이 넓게 드러나 글자 둘레 구름 얼룩이 됐다 [실측 J 남은 일 사람 눈 '공격' — 국소 ΔE00 13 ~ 22]
        hole = dg._dilate(glyph, PLATE_GLYPH_GROW)
        if glow > 0:
            lum = np.array([0.299, 0.587, 0.114])
            brighter = ((cw * aw[..., None]) @ lum - (nc * na[..., None]) @ lum) > PLATE_HALO_L
            br = dg._dilate(glyph, int(np.ceil(glow))) & brighter
            # 글자 빛만 — 글자보다 긴 가로 · 세로 선(막대 테두리 빛 줄 등 구조물)은 빼고, 글자 획에 이어진 덩어리만
            # [실측 K R20261118_090900 파티 HUD — HP 막대 윗선 청록 빛 줄이 이름 · HP 숫자 아래에서 판 픽셀로 바뀌어 어두운 띠, E1 20 ~ 26]
            lh = cv2.morphologyEx(br.astype(np.uint8), cv2.MORPH_OPEN, np.ones((1, max(3, int(1.5 * bh))), np.uint8)) > 0
            lv = cv2.morphologyEx(br.astype(np.uint8), cv2.MORPH_OPEN, np.ones((max(3, int(1.05 * bh)), 1), np.uint8)) > 0
            br &= ~dg._dilate(lh | lv, 1)
            n_b, lab_b = cv2.connectedComponents((br | glyph).astype(np.uint8), connectivity=8)
            touch = np.unique(lab_b[glyph & (lab_b > 0)])
            br &= np.isin(lab_b, touch[touch > 0])
            hole |= br
            hole = dg._dilate(hole, 1)
        # 판 조각 색조를 둘레 컨셉에 맞춤 — 둘레 고리(구멍 밖 NOTEXT_RING px)의 곧은 색 차(컨셉 − 판)를 채널마다 평면(a + bx + cy)으로 맞춰 구멍 안 판에 더한다
        ring_t = dg._dilate(hole, cutout.NOTEXT_RING) & ~hole & (aw > 0.5) & (na > 0.5)
        if int(ring_t.sum()) >= 20:
            yy, xx = np.nonzero(ring_t)
            A = np.stack([np.ones(len(xx)), xx / max(1.0, w), yy / max(1.0, h)], axis=1)
            coef, *_ = np.linalg.lstsq(A, (cw - nc)[ring_t], rcond=None)
            gy, gx = np.mgrid[0:h, 0:w]
            corr = np.clip(coef[0][None, None] + coef[1][None, None] * (gx / max(1.0, w))[..., None] + coef[2][None, None] * (gy / max(1.0, h))[..., None],
                           -PLATE_TONE_MAX, PLATE_TONE_MAX)
            nc = np.clip(nc + corr, 0, 255)
            tone = [round(float(v), 1) for v in coef[0]]
    if not (item.get("gauge") or whole):
        # 바꾸는 자리는 글자 상자(+2 px) 안까지 — 빛 글자 상자는 analyze 가 이미 빛 크기만큼 넓혔다(엔진도 그 안에 그린다). 넘어가면 이웃 장식선을
        # codex 판의 어긋난 선으로 바꿨다 [실측 J R20261117_182358 — '오의 불가' 아래 게이지 프레임 윗선 1 px 이중]
        hole &= rect
        if same_struct is not None:
            # 1b 후속 L-3b — 판에도 있는 구조물(테두리선)은 컨셉 픽셀 그대로 — 획 둘레 3 px 가 아래 금선에 닿아 회색 점 [실측 L run R20261118_115506 단색 '2/4']
            hole &= ~(same_struct & ~dg._dilate(glyph, 1))
    glyph &= hole
    blend = cv2.GaussianBlur(dg._dilate(hole, cutout.NOTEXT_GROW).astype(np.float32), (0, 0), cutout.NOTEXT_BLUR).astype(float)
    blend = np.clip(np.where(hole, 1.0, blend), 0.0, 1.0)
    ring = dg._dilate(hole, cutout.NOTEXT_RING) & ~hole
    mism = float(np.median(np.abs(na[ring] - aw[ring]))) if int(ring.sum()) >= 20 else 0.0
    if mism > PLATE_ALPHA_MISMATCH:
        # 판의 알파가 글자 둘레 컨셉 알파와 크게 다르다(codex 가 투명한 자리를 불투명 바탕으로 그림) — 판 알파 대신 둘레 컨셉 알파를 구멍 안으로 이어 쓴다
        # [실측 J R20261117_182358 — 투명 위 '오의 불가': 컨셉 0.03 ↔ 판 0.9 ~ 0.99, 수준 맞춤 뒤에도 0.33 띠가 글자 아래 프레임 윗선까지]
        _, na2 = cutout.fill_holes(cw, aw, hole, ~hole)
        grec = {"alpha_from": "concept neighbourhood (text-free concept alpha disagrees)", "alpha_mismatch": round(mism, 3)}
    else:
        gain, grec = cutout._notext_alpha_gain(aw, na, glyph, hole, blend > 0)
        na2 = np.clip(na * gain, 0.0, 1.0) if gain is not None else na
    if not (item.get("gauge") or whole) and int(ring.sum()) >= 20:
        # 1b 후속 L-3b — 판이 글자 자리를 투명하게 비웠다(구멍 안 판 알파가 그 픽셀의 둘레 컨셉 매끈한 메움 알파보다 PLATE_ALPHA_MISMATCH 넘게 낮음) — 그 픽셀은
        # 둘레 메움. 픽셀마다 비교 — 트랙 끝에 걸친 글자는 둘레 절반이 투명이라 고리 중앙값 하나로는 못 가린다
        # [실측 K R20261118_092315 파티 HUD '0 %' — 트랙 위 글자 자리가 판에서 투명, 텍스처에 어두운 '0%' 모양 구멍]
        fpm, fa = _smooth_fill(cw * aw[..., None], aw, ~hole)
        low = hole & (na2 < fa - PLATE_ALPHA_MISMATCH)
        pt = plate_text(nc, na)
        if pt is not None:
            low |= hole & dg._dilate(pt & dg._dilate(glyph, 2), 1)      # 판에 남은 글자 자리(획 근처만)도 판 대신 둘레 메움(위 glyph_of)
        if int(low.sum()) >= 10:
            nc = np.where(low[..., None], fpm / np.maximum(fa, 1e-4)[..., None], nc)
            na2 = np.where(low, fa, na2)
            grec = {**grec, "alpha_from": grec.get("alpha_from") or "text-free concept — its transparent glyph holes from the concept neighbourhood",
                    "plate_clear_px": int(low.sum())}
    out_a = blend * na2 + (1 - blend) * aw
    pm = blend[..., None] * nc * na2[..., None] + (1 - blend)[..., None] * cw * aw[..., None]
    out_c = np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw)
    col[y0:y1, x0:x1], a[y0:y1, x0:x1] = out_c, out_a
    return {"used": True, "shift": [dx, dy], "diff": sh["diff"], "hole_px": int(hole.sum()), "whole": bool(whole or item.get("gauge")),
            **({"tone": tone} if tone is not None else {}),
            **{k: v for k, v in grec.items() if k in ("alpha_gain", "alpha_gain_applied", "alpha_from", "alpha_mismatch", "plate_clear_px")}}


def _plate_entry(run, asset: dict, spec: dict) -> tuple[dict, dict]:
    """정적 판 텍스처 — 판 마스크(layer/plate_<n>.png)의 컨셉 픽셀(곧은 색 · 알파), 글자 자리는 글자 없는 판(있으면 — 창마다 ±6 px 정합,
    cutout.compose 와 같은 길) · 없으면 줄 보간, 판 위 게이지 트랙은 빈 트랙으로(채움이 컨셉 모양이면 unfilled_track, 아니면 막대 상자를 판 · 보간으로).
    OCR 이 글자 자국을 잡으면 글자 상자 전체를 구멍으로 다시 → 그래도면 판 없이. 텍스처 = 판 상자 1:1(상한 layers.plate_max)."""
    import numpy as np
    from PIL import Image
    from core import ocr
    from gen import cutout
    from gen import postprocess as pp
    from stages import generate
    from stages import layer as layer_mod
    aid = asset["asset_id"]
    lay = run.read_json("layer.json") if run.path("layer.json").is_file() else {}
    p = next((x for x in lay.get("plates", []) if x.get("asset") == aid), None)
    if p is None:
        raise StageError("PLATE_UNKNOWN", f"'{aid}' is a static plate but layer.json has no plate for it", asset=aid)
    n = p["widget"][len(layer_mod.PLATE_PREFIX):]
    with Image.open(run.path("layer", f"plate_{n}.png")) as im:
        mask_full = np.asarray(im.convert("L")) > 127
    bg = generate.background_kind(run) or "scene"
    color, alpha = _reference_layers(run, bg)
    if alpha is None:
        raise StageError("PLATE_NO_ALPHA", f"'{aid}': the static plate needs the concept alpha (background {bg})", asset=aid)
    ext_cfg = run.cfg.get("extract") or {}
    notext = _notext_layers(run, bg) if ext_cfg.get("notext", True) else None
    x, y, w, h = (int(v) for v in p["box"])
    box = [x, y, w, h]
    log: dict = {"asset_id": aid, "backend": "concept_plate", "source_mode": "plate", "plate": {"box": box, "region": p.get("region")}}
    index = spec_mod.widget_index(spec)
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    # 판 위 게이지 — 채움이 컨셉 모양(concept_fill)이면 트랙을 빈 트랙 색으로(그 막대가 위에 채움을 그린다), 아니면 막대 상자를 메울 구멍으로
    tracks, gauge_items = [], []
    for g in spec.get("widgets", []):
        bb = g.get("bbox_intent")
        if g.get("type") != "ProgressBar" or not bb or _overlap(box, bb) < 0.2:
            continue
        fill = (g.get("style") or {}).get("fill")
        proc = ((assets.get(fill.get("asset")) or {}).get("procedural") or {}) if isinstance(fill, dict) else {}
        if proc.get("shape") == "concept_fill" and proc.get("full"):
            # 1b 후속 J — 가득 찬 게이지: 채움 텍스처(컨셉 트랙 조각)가 덮는 자리만 요소 없는 판(빈 트랙)으로 — 진행률이 줄면 그 판이 보인다
            from gen import concept_fill
            try:
                with Image.open(run.path("reference.png")) as im_ref:
                    ref_png = np.asarray(im_ref.convert("RGB"), float)
                hole, _ = concept_fill.track_hole(ref_png, proc)
                if proc.get("flip"):
                    hole = hole[:, ::-1]
                fx, fy, fw, fh = (int(v) for v in proc["frame_box"])
                full_mask = np.zeros((h, w), bool)
                sx0, sy0 = max(fx, x), max(fy, y)
                sx1, sy1 = min(fx + fw, x + w), min(fy + fh, y + h)
                if sx1 > sx0 and sy1 > sy0:
                    full_mask[sy0 - y:sy1 - y, sx0 - x:sx1 - x] = hole[sy0 - fy:sy1 - fy, sx0 - fx:sx1 - fx]
                ys_, xs_ = np.nonzero(full_mask)
                if len(ys_):
                    gauge_items.append({"id": g["id"], "box": [float(xs_.min()), float(ys_.min()), float(xs_.max() - xs_.min() + 1), float(ys_.max() - ys_.min() + 1)],
                                        "glow": 0.0, "gauge": True, "mask": full_mask})
                tracks.append({"widget": g["id"], "full": True, "track_px": int(full_mask.sum()), "mask_from": "reference.png"})
            except (concept_fill.ConceptFillError, KeyError, ValueError) as exc:
                tracks.append({"widget": g["id"], "error": str(exc)})
            continue
        if proc.get("shape") == "concept_fill" and art_files(run) and _art_element_free(run):
            # 1b 후속 K-a — 아트(요소 없는 판)는 이미 게이지 채움을 비운 빈 트랙이다 — 컨셉에서 계산한 빈 트랙으로 덧칠하면 아트 트랙과 어긋난다
            # [실측 K R20261118_004754 단색 — 게이지 끝 E1 16.9]. L-2 원본 아트는 채움까지 그린 그림이라 아래 덧칠(빈 트랙)을 그대로 한다
            tracks.append({"widget": g["id"], "kept": "text-free art already has the empty track"})
            continue
        if proc.get("shape") == "concept_fill":
            # 빈 트랙으로 메울 자리는 채움 텍스처(procedural concept_fill — reference.png 에서 그림)와 같은 그림에서 잰다 — 곧은 색으로 재면 반투명 띠가
            # 더 밝아 자리가 어긋나 채움이 안 덮는 판 자리에 빈 트랙 색 조각이 보였다 [실측 J R20261117_181500 — 게이지 왼쪽 끝 국소 ΔE00 41]
            from gen import concept_fill
            try:
                with Image.open(run.path("reference.png")) as im_ref:
                    ref_png = np.asarray(im_ref.convert("RGB"), float)
                hole, filled = concept_fill.unfilled_track(ref_png, proc)
                fx, fy, fw, fh = (int(v) for v in proc["frame_box"])
                color = color.copy()
                sub, sa = color[fy:fy + fh, fx:fx + fw], alpha[fy:fy + fh, fx:fx + fw]
                straight = np.where(sa[..., None] > 0.5, filled / np.maximum(sa, 0.5)[..., None], filled)
                sub[hole] = np.clip(straight[hole], 0, 255)
                tracks.append({"widget": g["id"], "frame_box": [fx, fy, fw, fh], "track_px": int(hole.sum()), "mask_from": "reference.png"})
            except (concept_fill.ConceptFillError, KeyError, ValueError) as exc:
                tracks.append({"widget": g["id"], "error": str(exc)})
        else:
            # 채움이 컨셉 모양이 아니면 컨셉 진행률만큼만 판(빈 트랙)으로 — 0 % 면 컨셉이 이미 빈 트랙이라 안 바꾼다(PLATE_EMPTY_GAUGE)
            st_g = g.get("style") or {}
            pct = st_g.get("percent")
            ftype = st_g.get("bar_fill_type", "left_to_right")
            gx, gy, gw, gh = float(bb[0]) - x, float(bb[1]) - y, float(bb[2]), float(bb[3])
            if isinstance(pct, (int, float)) and ftype in ("left_to_right", "right_to_left"):
                if pct <= PLATE_EMPTY_GAUGE:
                    tracks.append({"widget": g["id"], "kept": f"empty in the concept (percent {pct:g}) — the plate keeps the concept track"})
                    continue
                if pct < 1.0:
                    fw_ = gw * float(pct)
                    gx = gx if ftype == "left_to_right" else gx + gw - fw_
                    gw = fw_
                    tracks.append({"widget": g["id"], "filled_part": [round(gx + x, 1), round(gy + y, 1), round(gw, 1), round(gh, 1)], "percent": pct})
            gauge_items.append({"id": g["id"], "box": [gx, gy, gw, gh], "glow": 0.0, "gauge": True})
    if tracks:
        log["gauge_tracks"] = tracks
    col0 = color[y:y + h, x:x + w].copy()
    mask = mask_full[y:y + h, x:x + w]
    a0 = np.where(mask, alpha[y:y + h, x:x + w], 0.0)
    texts = []
    for t in spec.get("widgets", []):
        bb = t.get("bbox_intent")
        if t.get("type") not in ("TextBlock", "RichTextBlock") or not bb or _overlap(box, bb) <= 0:
            continue
        x0, y0 = max(0, int(bb[0]) - x), max(0, int(bb[1]) - y)
        x1, y1 = min(w, int(np.ceil(bb[0] + bb[2])) - x), min(h, int(np.ceil(bb[1] + bb[3])) - y)
        if x1 <= x0 or y1 <= y0 or float(mask[y0:y1, x0:x1].mean()) * (x1 - x0) * (y1 - y0) < PLATE_TEXT_IN * float(bb[2]) * float(bb[3]):
            continue
        texts.append({"id": t["id"], "box": [float(bb[0]) - x, float(bb[1]) - y, float(bb[2]), float(bb[3])],
                      "glow": float(((t.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(t.get("font"), dict) else 0.0,
                      "colors": _font_colors(t)})
    if art_files(run):
        texts = []          # 1b 후속 K-a — 판 = 글자 없는 아트: 지울 글자가 없다
        log["art"] = "text-free art (generated concept) — no text fill"
    items = texts + gauge_items
    M = PLATE_TEXT_MARGIN
    wins = _merge_windows([[max(0, int(it["box"][0]) - M), max(0, int(it["box"][1]) - M), min(w, int(np.ceil(it["box"][0] + it["box"][2])) + M),
                            min(h, int(np.ceil(it["box"][1] + it["box"][3])) + M)] for it in items])

    P = cutout.NOTEXT_SHIFT
    nt_pad = None
    if notext is not None:
        nt_pad = (_pad_crop(notext[0], x, y, x + w, y + h, P),
                  _pad_crop(notext[1], x, y, x + w, y + h, P) if notext[1] is not None else np.pad(a0, P, mode="edge"))

    def bake(whole: bool, use_nt: bool):
        col, a = col0.copy(), a0.copy()
        recs = []
        # 가득 찬 게이지(mask)는 요소 없는 판으로만 — 판이 없거나 못 쓰면 컨셉 그대로(채움이 같은 자리를 덮는다), 줄 보간 안 함
        left = items if not any(it.get("mask") is not None for it in items) else [it for it in items if it.get("mask") is None]
        if use_nt and nt_pad is not None:
            # 글자 없는 판이 있으면 글자마다 '판과 다른 획'만 판 픽셀로(_plate_item_fill) — 못 맞춘 글자만 아래 줄 보간으로
            left = []
            for it in items:
                r = _plate_item_fill(col, a, nt_pad[0], nt_pad[1], it, whole=whole, orig=(col0, a0))
                recs.append({"item": it["id"], **r})
                if not r.get("used") and not r.get("nothing") and it.get("mask") is None:
                    left.append(it)
        lw =_merge_windows([[max(0, int(it["box"][0]) - M), max(0, int(it["box"][1]) - M), min(w, int(np.ceil(it["box"][0] + it["box"][2])) + M),
                              min(h, int(np.ceil(it["box"][1] + it["box"][3])) + M)] for it in left]) if left is not items else wins
        for wx0, wy0, wx1, wy1 in lw:
            loc = [{**it, "box": [it["box"][0] - wx0, it["box"][1] - wy0, it["box"][2], it["box"][3]]} for it in left
                   if it["box"][0] < wx1 and it["box"][0] + it["box"][2] > wx0 and it["box"][1] < wy1 and it["box"][1] + it["box"][3] > wy0]
            if not loc:
                continue
            sub_c, sub_a = col[wy0:wy1, wx0:wx1], a[wy0:wy1, wx0:wx1]
            ff = None
            gauge_win = any(it.get("gauge") for it in loc)
            try:
                rgb_o, a_o, comp = cutout.compose(sub_c, sub_a, loc, [], interior_alpha=None, lock_lines=False, whole_text_boxes=whole or gauge_win,
                                                  clear_boxes=[], hole_alpha="shape", fill_from=ff)
            except cutout.CutoutError as exc:
                # 창 안에 불투명 실루엣이 없다(투명 위 글자뿐) — 글자 상자를 판 픽셀로(있으면) 아니면 투명으로
                rgb_o, a_o = sub_c.copy(), sub_a.copy()
                for it in loc:
                    bx0, by0 = max(0, int(it["box"][0]) - 2), max(0, int(it["box"][1]) - 2)
                    bx1, by1 = min(wx1 - wx0, int(np.ceil(it["box"][0] + it["box"][2])) + 2), min(wy1 - wy0, int(np.ceil(it["box"][1] + it["box"][3])) + 2)
                    if ff is not None:
                        P = cutout.NOTEXT_SHIFT
                        rgb_o[by0:by1, bx0:bx1] = ff[0][P + by0:P + by1, P + bx0:P + bx1]
                        a_o[by0:by1, bx0:bx1] = ff[1][P + by0:P + by1, P + bx0:P + bx1] if ff[1] is not None else 0.0
                    else:
                        a_o[by0:by1, bx0:bx1] = 0.0
                comp = {"fallback": f"{exc} — text boxes {'from the text-free concept' if ff is not None else 'cleared'}"}
            a_o = np.where(mask[wy0:wy1, wx0:wx1] | (sub_a > 0), a_o, 0.0)
            col[wy0:wy1, wx0:wx1], a[wy0:wy1, wx0:wx1] = rgb_o, a_o
            recs.append({"window": [x + wx0, y + wy0, wx1 - wx0, wy1 - wy0], "items": [it["id"] for it in loc],
                         "notext": (comp.get("notext") or {}).get("used") if isinstance(comp, dict) else None,
                         "shift": (comp.get("notext") or {}).get("shift") if isinstance(comp, dict) else None,
                         **({"fallback": comp["fallback"]} if isinstance(comp, dict) and comp.get("fallback") else {})})
        return col, a, recs

    lim = int(layer_mod.settings(run.cfg)["plate_max"])
    tw, th = w, h
    if max(tw, th) > lim:
        k = lim / max(tw, th)
        tw, th = max(1, int(round(tw * k))), max(1, int(round(th * k)))

    def detect(img):
        try:
            return ocr.detect(img)
        except ocr.OcrError as exc:
            raise StageError("OCR_UNAVAILABLE", str(exc), asset=aid) from exc
    nt_marks = None

    def baked_of(det):
        nonlocal nt_marks
        if not det["count"]:
            return [], []
        baked, decor = _split_marks(det, box, (tw, th), spec)
        if baked and notext is not None:
            if nt_marks is None:
                nc = notext[0][y:y + h, x:x + w]
                na = notext[1][y:y + h, x:x + w] if notext[1] is not None else a0
                nb, nd = _split_marks(detect(cutout.to_image(nc, np.where(mask, na, 0.0), (tw, th))), box, (tw, th), spec)
                nt_marks = [b["box"] for b in nb + nd]

            def iou(p_, q):
                ix = max(0.0, min(p_[0] + p_[2], q[0] + q[2]) - max(p_[0], q[0]))
                iy = max(0.0, min(p_[1] + p_[3], q[1] + q[3]) - max(p_[1], q[1]))
                return ix * iy / max(1e-6, p_[2] * p_[3] + q[2] * q[3] - ix * iy)
            same = [b for b in baked if any(iou(b["box"], r) >= 0.3 for r in nt_marks)]
            baked = [b for b in baked if b not in same]
            decor = decor + [{**b, "in_text_free_concept": True} for b in same]
        return baked, decor
    col, a, recs = bake(False, True)
    im = cutout.to_image(col, a, (tw, th))
    det = detect(im)
    baked, decor = baked_of(det)
    if baked and items:
        log["text_marks_first"] = {"count": det["count"], "baked": baked}
        col, a, recs = bake(True, True)
        im = cutout.to_image(col, a, (tw, th))
        det = detect(im)
        baked, decor = baked_of(det)
        if baked and notext is not None:
            log["text_marks_second"] = {"count": det["count"], "baked": baked}
            col, a, recs = bake(True, False)
            im = cutout.to_image(col, a, (tw, th))
            det = detect(im)
            baked, decor = baked_of(det)
    final = run.path("assets", "final", f"{aid}.png")
    final.parent.mkdir(parents=True, exist_ok=True)
    im.save(final, format="PNG")
    st = pp.alpha_stats(im)
    log.update(windows=recs, texts=[t["id"] for t in texts], gauge_holes=[g["id"] for g in gauge_items], alpha=st, size=[tw, th], ocr=det,
               notext_available=notext is not None)
    if baked and art_files(run):
        decor, baked = list(decor or []) + list(baked), []      # 1b 후속 K-a — 판 = 글자 없는 아트 그대로(잔상은 진단 E1 · E8)
    if decor:
        log["ocr_decor"] = {"count": len(decor), "boxes": decor}
    text = "" if not baked else f"{len(baked)} text-like box(es), max score {max(b['score'] for b in baked)}"
    return ({"alpha": st["has_alpha"], "nine_slice_margin": None, "ocr_text": text,
             "ocr": f"{det['engine']} — detection boxes with score ≥ {det['min_score']} and area ≥ {det['min_area_px']} px", "size": [tw, th]}, log)


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
        if not raw.is_file() and asset.get("source_mode") != "plate":      # 판은 raw 를 쓰지 않는다(컨셉 · layer 마스크에서 굽는다)
            raise StageError("RAW_MISSING", f"{raw} was not generated", asset=aid)
        backend = backends.get(aid, asset["provenance"])
        if asset.get("source_mode") == "plate":         # 1b 후속 J-a — 정적 판
            backend = "concept_plate"
            info, log = _plate_entry(run, asset, spec)
        elif backend == "procedural":
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
