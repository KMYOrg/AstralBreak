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


def end_caps(spec: dict | None) -> set[str]:
    """1b 후속 L 다음 H4 — 게이지 끝 덮개 Image(브러시 에셋이 procedural concept_end_cap) — 아래 프레임 · 판과 같은 픽셀을 다시 그려 오리기의 구멍 · 넘침 막기가 아니다."""
    caps = {a["asset_id"] for a in (spec or {}).get("assets", []) if (a.get("procedural") or {}).get("shape") == "concept_end_cap"}
    return {w["id"] for w in (spec or {}).get("widgets", []) if ((w.get("style") or {}).get("brush") or {}).get("asset") in caps} if caps else set()


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


def _ocr_marks(baked: list[dict], decor: list[dict], spec: dict | None) -> list[dict]:
    """V6 — 지운 판 텍스처 OCR 검출(_split_marks · 판 대조 뒤 — 캔버스 상자) → 상자 + 근처 글자(그 글자 bbox_intent + OCR_NEAR_PAD 와 검출 넓이의
    MARK_TEXT_OVERLAP 이상 겹침). 글자 없는 판에도 있는 자국(in_text_free_concept — 그림 장식)은 뺀다. 근처 글자가 있으면 잔여물(그 글자 반복 보강 대상), 없으면
    먼 검출(spec 에 없는 글자 — analyze 누락 의심, 지우지 않고 기록)."""
    texts = [(w["id"], w["bbox_intent"]) for w in (spec or {}).get("widgets", []) if w.get("type") in ("TextBlock", "RichTextBlock") and w.get("bbox_intent")]
    out = []
    for b in list(baked or []) + list(decor or []):
        if b.get("in_text_free_concept"):
            continue
        r = [float(v) for v in b["box"]]
        area = max(1e-6, r[2] * r[3])
        near = []
        for tid, t in texts:
            t0, t1 = float(t[0]) - OCR_NEAR_PAD, float(t[1]) - OCR_NEAR_PAD
            t2, t3 = float(t[0]) + float(t[2]) + OCR_NEAR_PAD, float(t[1]) + float(t[3]) + OCR_NEAR_PAD
            ov = max(0.0, min(r[0] + r[2], t2) - max(r[0], t0)) * max(0.0, min(r[1] + r[3], t3) - max(r[1], t1)) / area
            if ov >= MARK_TEXT_OVERLAP:
                near.append(tid)
        out.append({"box": r, "score": b.get("score"), "near": near})
    return out


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
        if w["id"] in end_caps(spec):
            continue                    # 1b 후속 L 다음 H4 — 게이지 끝 덮개는 아래 프레임과 같은 컨셉 픽셀을 다시 그린다(구멍으로 메우면 중간 진행률에 보인다)
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
    mine = {u["id"] for u in asset_users(spec, aid)} | overhang_decos(spec) | end_caps(spec)
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


def own_mask(run, spec: dict | None, aid: str):
    """L-2 기본 전환 ④ — 이 에셋을 그리는 접히는 위젯의 자기 마스크(layer 가 상자를 넓힌 것 — 캔버스 bool), 없으면 None. 마스크 밖(넓힌 네모 안의 이웃 픽셀)은
    그리지 않는다(정적 판 · 이웃 위젯의 몫)."""
    import numpy as np
    from stages import layer as layer_mod
    users = asset_users(spec, aid)
    rings = layer_mod.radial_masks(run)
    ring = next((rings[u["id"]] for u in users if u["id"] in rings), None)
    if ring is not None:
        return ring                                 # 전투 HUD 동작(11-23) — 원형 진행(고리)은 자기 픽셀만
    wants = [u["id"] for u in users if ((u.get("style") or {}).get("brush") or {}).get("wipe")]
    if wants:
        raise StageError("RADIAL_MASK", f"'{aid}' is drawn by the ring {wants} but layer.json has no ring mask — the layer stage must run first", asset=aid)
    masks = layer_mod.own_masks(run)
    own = next((masks[u["id"]] for u in users if u["id"] in masks), None)
    for wid, m in rings.items():                    # 고리와 같은 자리를 품은 다른 에셋(고리 안 띠)은 고리 픽셀을 뺀다 — 픽셀마다 주인 하나
        H, W = m.shape
        for u in users:
            if not u.get("bbox_intent"):
                continue
            x0, y0, x1, y1 = layer_mod._int_box(u["bbox_intent"], W, H)
            if m[y0:y1, x0:x1].any():
                own = (np.ones((H, W), bool) if own is None else own) & ~m
                break
    return own


def cut_ownership(spec: dict, alpha, ring_ok: set | None = None, own_masks: dict | None = None) -> dict | None:
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
        om = (own_masks or {}).get(parts[i]["id"])       # L-2 기본 전환 ④ — 상자를 넓힌 접히는 위젯은 자기 마스크만 후보(넓힌 네모 안의 이웃 픽셀을 겨루지 않게)
        if om is not None:
            real[om] |= np.int64(1) << i
            cand[om] |= np.int64(1) << i
            continue
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
        from stages import layer as layer_mod
        cache[key] = cut_ownership(spec, alpha, ring_ok, layer_mod.own_masks(run))
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
    from gen import diagnose as dg_mod
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
        om = own_mask(run, spec, aid)
        foreign = 0
        if om is not None:
            # L-2 기본 전환 ④ — 빛 · 넘침까지 넓힌 상자: 자기 마스크 밖은 이웃 · 정적 판의 픽셀이라 그리지 않는다
            om_s = om[sy0:sy1, sx0:sx1]
            foreign = int(((a > 0) & ~om_s).sum())
            a = np.where(om_s, a, 0.0)
            rec["own_mask"] = {"px": int(om_s.sum()), "foreign_px": foreign}
        if dropped or covered or foreign:
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
    erasing = False                  # 글자 지우기 마감 — 이 굽기에 지운 판 후보 글자가 있나(OCR 물러남 끔)
    zacc = np.zeros(a_t.shape, bool)  # V1 — 이 굽기의 글자 메움이 바꿀 수 있는 자리(조각 T 좌표)
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
        orig = (col_t.copy(), a_t.copy())
        # 1b 후속 L 다음 — 글자마다 지우기 방법(erase_method)은 run.erase_plan 이 정한다(첫 판 = 모두 lama). 지운 판 · 좁은 판 고르기는 refine 끝에 게이트와 같은
        # 함수로 캔버스 합성에서(_gate_erase_choice — 텍스처 단독 점수는 조작 안내 악화를 못 가렸다)
        hook = _erase_setup(run, spec, texts, orig[0], rec, aid=aid, origin=(T[0], T[1]))
        c_, a_ = orig[0].copy(), orig[1].copy()
        left, done = [], []
        for t in texts:
            r = _fill_text_item(c_, a_, fill_from[0], fill_from[1], t, orig=orig, others=[o["box"] for o in texts if o is not t],
                                inpaint=hook if t.get("erase") else None)
            _zone_add(zacc, r)
            nz = r.pop("_ntz", None)
            if nz is not None and isinstance(r.get("no_truth"), dict):
                bw_ = r["no_truth"].get("box_win") or [0, 0, 0, 0]
                r["no_truth"]["box"] = [round(T[0] + nz[2] + bw_[0], 1), round(T[1] + nz[0] + bw_[1], 1), bw_[2], bw_[3]]
            done.append({"text": t.get("id"), **{k: v for k, v in r.items() if k in ("used", "shift", "diff", "hole_px", "reason", "alpha_from", "halo_px",
                                                                                      "line_up_diff", "plate_clear_px", "erase_tail", "erase_tails",
                                                                                      "erase_added_px", "erase_px_steps", "fill", "lama_paste_px",
                                                                                      "lama_error", "path", "erase_method", "struct_kept_px",
                                                                                      "despeckle_px", "background", "no_truth", "clear_alpha", "alpha_tail",
                                                                                      "bg_alpha", "plate_edge_px", "enclosed_px", "diff_tail", "diff_far",
                                                                                      "diff_profile", "plate_px", "plate_marks_px")}})
            if not (r.get("used") or r.get("nothing")):
                left.append(t)
        col_t, a_t = c_, a_
        rec["glyph_fill"] = done
        erasing = any(t.get("erase") for t in texts)
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
    if erasing:
        rec["ocr_marks"] = _ocr_marks(baked, decor, spec)     # V6 — 지운 판 OCR: 글자 상자 근처 = 잔여물(반복 보강) · 먼 것 = 기록
    if baked and erasing:
        # 글자 지우기 마감 — 지운 판 후보에선 상자째 다시 굽는 물러남 안 함(기록만 — _plate_entry 와 같음). 남은 글자는 게이트 고르기(S4)가 거른다
        rec["text_marks_erase"] = {"count": det["count"], "max_score": det["max_score"], "baked": baked}
        baked = []
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
    # V1 — compose 가 메운 남은 글자 상자(판 정합 못 한 글자 · 상자째 다시)는 상자 + 메움 여유를 바꿀 수 있는 자리로(보수적)
    whole_ = bool(rec.get("text_marks_first"))
    for t in texts:
        gl_ = int(np.ceil(float(t.get("glow") or 0)))
        zacc |= dg_mod._box_mask(zacc.shape, t["box"], gl_ + cutout.NOTEXT_RING + cutout.NOTEXT_GROW + 6 + (4 if whole_ else 0))
    log["_zone"] = _zone_to_size(zacc, (im.width, im.height))
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


# 1b 후속 L 다음 — 글자 지우기 다음 V1 검증 A: 글자 메움 함수는 '바꿀 수 있는 자리'(메울 자리 + 섞임 띠 = 넓힘 grow + 흐림 3σ) 밖을 **바이트로** 안 바꾼다 —
# 섞임 무게는 그 자리 밖에서 0 으로 자르고(가우스 꼬리 4σ 의 잔값), 쓰기는 그 자리 안만(pm / 알파 → 곧은 색 되돌림의 반올림 차도 안 남김). 자리는 기록(_zone)으로
# 돌려줘 refine 끝 고르기가 지운 판 후보 ↔ 예전 판의 '자리 밖 RGBA 같음'을 잰다(_outside_changed — 다르면 그 후보 버림)
def _blend_band(hole, grow: int, sigma: float):
    """메울 자리 hole → (섞임 무게 HxW float — 자리 안 1 · 밖은 넓혀 흐린 값을 '바꿀 수 있는 자리' 밖에서 0, 바꿀 수 있는 자리 HxW bool)."""
    import cv2
    import numpy as np
    from gen import diagnose as dg
    hole = np.asarray(hole, bool)
    zone = dg._dilate(hole, int(grow) + int(np.ceil(3.0 * float(sigma))))
    b = cv2.GaussianBlur(dg._dilate(hole, int(grow)).astype(np.float32), (0, 0), float(sigma)).astype(float)
    b = np.where(hole, 1.0, np.where(zone, np.clip(b, 0.0, 1.0), 0.0))
    return b, zone | hole


def _put(col, a, win, zone, new_c, new_a) -> None:
    """창(win = y0, y1, x0, x1) 안 바꿀 수 있는 자리(zone)만 새 곧은 색 · 알파로 — 그 밖은 지금 값 그대로(바이트 같음)."""
    import numpy as np
    y0, y1, x0, x1 = win
    z = np.asarray(zone, bool)
    col[y0:y1, x0:x1] = np.where(z[..., None], new_c, col[y0:y1, x0:x1])
    a[y0:y1, x0:x1] = np.where(z, new_a, a[y0:y1, x0:x1])


def _zone_rec(win, zone) -> dict:
    """기록에 넣을 바꿀 수 있는 자리 — {"_zone": (y0, y1, x0, x1, 창 크기 bool)} (refine 이 모아 텍스처 크기 마스크로, JSON 에는 안 씀)."""
    import numpy as np
    return {"_zone": (int(win[0]), int(win[1]), int(win[2]), int(win[3]), np.asarray(zone, bool).copy())}


def _zone_add(acc, rec: dict) -> None:
    """기록(rec)의 _zone 을 꺼내 누적 마스크(acc — 창 좌표계 전체 크기)에 더한다(rec 에서는 지움)."""
    z = rec.pop("_zone", None) if isinstance(rec, dict) else None
    if z is None or acc is None:
        return
    y0, y1, x0, x1, m = z
    acc[y0:y1, x0:x1] |= m


def _zone_to_size(zone, size):
    """바꿀 수 있는 자리(조각 크기) → 텍스처 크기(size = (w, h)). 같으면 그대로, 다르면 가장 가까운 픽셀로 늘린 뒤 LANCZOS 반경(3 원본 px × 비)만큼 넓힘."""
    import numpy as np
    from PIL import Image
    from gen import diagnose as dg
    if zone is None:
        return None
    h, w = zone.shape
    tw, th = int(size[0]), int(size[1])
    if (tw, th) == (w, h):
        return zone.copy()
    z = np.asarray(Image.fromarray(zone.astype(np.uint8) * 255).resize((tw, th), Image.Resampling.NEAREST)) > 0
    k = max(tw / max(1, w), th / max(1, h))
    return dg._dilate(z, int(np.ceil(3.0 * max(1.0, k))) + 1)


def _outside_changed(png_c: bytes, zone_c, png_o: bytes, zone_o) -> dict:
    """V1 검증 A — 지운 판 후보(png_c)가 예전 판(png_o)과 두 판의 바꿀 수 있는 자리 합 밖에서 RGBA 바이트로 같은가. 알파 0 픽셀 둘의 RGB 는 번짐 색(가장 가까운
    보이는 픽셀에서 파생 — cutout.bleed_transparent_rgb)이라 안 견줌. → {"px": 다른 픽셀 수, "box": 그 상자}."""
    import numpy as np
    from gen import diagnose as dg
    A, B = _decode(png_c), _decode(png_o)
    if A.shape != B.shape:
        return {"px": int(A.shape[0] * A.shape[1]), "reason": f"texture size differs {A.shape[:2]} vs {B.shape[:2]}"}
    allowed = np.zeros(A.shape[:2], bool)
    for z in (zone_c, zone_o):
        if z is not None and z.shape == allowed.shape:
            allowed |= z
    vis = (A[..., 3] > 0) | (B[..., 3] > 0)
    diff = (A[..., 3] != B[..., 3]) | ((A[..., :3] != B[..., :3]).any(axis=2) & vis)
    ch = diff & ~allowed
    return {"px": int(ch.sum()), **({"box": dg._bbox(ch)} if ch.any() else {}), "allowed_px": int(allowed.sum()), "diff_px": int(diff.sum())}


HARMONIC_ITERS = 1500      # 1b 후속 L 다음 F1 — 경계값 보간(라플라스) 빨강-검정 SOR 반복 상한 · 완화 계수 · 멈춤(미리 곱한 색 0 ~ 255 단위 최대 변화)
HARMONIC_OMEGA = 1.9
HARMONIC_TOL = 0.02


def _harmonic_fill(vals, hole, init=None, wy: float = 1.0, screen: float = 0.0):
    """구멍(hole) 안을 둘레 값(구멍 밖 픽셀 — 고정)에서 라플라스 방정식으로 메움 — 배열 가장자리는 기울기 0. 경계와 이어지고 단계 · 줄무늬가 없다
    (가우스 가중 평균 _smooth_fill 은 받침이 모자란 가운데를 원천 중앙값으로 채워 반원 경계가 남았다 [실측 R20261119_091634 F1 첫 판 — 흰 바탕 '오의 불가' 자리]).
    wy = 세로 이웃 무게(가로 1) — 작으면 줄마다 양끝 둘레 사이 선형 보간에 가깝다(가로로 이어진 테두리 빛 띠가 자리를 그대로 가로지름), 0 보다 크면 줄 사이를
    살짝 이어 줄무늬를 막는다. vals HxWxC(구멍 밖 값을 씀) · init = 구멍 안 첫 값(없으면 구멍 밖 평균). → HxWxC float.
    screen > 0 = 가림 라플라스((4 + screen) u = Σ 이웃 — 글자 지우기 다음 V5): 경계값이 거리 약 1/√screen px 로 0 을 향해 사라진다(투명 바탕 위 빛 자리 —
    지킨 구조물 · 판 구조물 가장자리에서 짧게 끊기고 가운데는 투명)."""
    import numpy as np
    u = np.asarray(vals, np.float64).copy()
    hole = np.asarray(hole, bool)
    if not hole.any():
        return u
    if init is not None:
        u[hole] = np.asarray(init, np.float64)[hole]
    elif (~hole).any():
        u[hole] = u[~hole].mean(axis=0)
    yy, xx = np.indices(hole.shape)
    halves = [hole & ((yy + xx) % 2 == k) for k in (0, 1)]
    for it in range(HARMONIC_ITERS):
        delta = 0.0
        for m in halves:
            p = np.pad(u, ((1, 1), (1, 1), (0, 0)), mode="edge")
            avg = ((p[:-2, 1:-1] + p[2:, 1:-1]) * wy + p[1:-1, :-2] + p[1:-1, 2:]) / (2.0 + 2.0 * wy + screen)
            new = (1.0 - HARMONIC_OMEGA) * u[m] + HARMONIC_OMEGA * avg[m]
            if it % 25 == 0:
                delta = max(delta, float(np.abs(new - u[m]).max()) if new.size else 0.0)
            u[m] = new
        if it % 25 == 0 and delta < HARMONIC_TOL:
            break
    return u


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


def _other_text_mask(others, x0: int, y0: int, h: int, w: int):
    """1b 후속 L 다음 — 같은 판 · 조각의 다른 글자 상자(창 좌표, 넓히지 않음) → (합친 마스크, 상자마다 마스크). 없으면 (None, [])."""
    import numpy as np
    masks = []
    for b in others or []:
        bx, by, bw, bh = (float(v) for v in b)
        m = np.zeros((h, w), bool)
        m[max(0, int(by) - y0):max(0, min(h, int(np.ceil(by + bh)) - y0)), max(0, int(bx) - x0):max(0, min(w, int(np.ceil(bx + bw)) - x0))] = True
        if m.any():
            masks.append(m)
    if not masks:
        return None, []
    return np.logical_or.reduce(masks), masks


GLYPH_LIKE_MIN = 0.5        # 글자색 근처 픽셀 중 상자 테두리에 안 닿는 덩어리 몫이 이 미만이면 띠 · 바탕 색으로 본다
GLYPH_LIKE_GAIN = 0.2       # 사양 글자색 쪽이 이만큼 더 글자 같으면 그것으로


def _glyph_like(m, own) -> float:
    """1b 후속 L 다음 — 마스크(상자 안) 중 상자 테두리에 안 닿는 덩어리의 몫. 글자 획은 상자 안에 떠 있고 띠 · 바탕은 테두리까지 이어진다."""
    import cv2
    import numpy as np
    m = np.asarray(m, bool)
    n = int(m.sum())
    if n < 20:
        return 0.0
    k, lab = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
    border = own & ~cv2.erode(own.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    touch = np.unique(lab[border & m])
    return float((m & ~np.isin(lab, touch[touch > 0])).sum()) / n


PLATE_STRUCT_OVERLAP = 0.1 # 투명 위 글자 · 빛 자리(획 + 빛 + 3 px)의 이 비율 이상이 상자 밖으로 이어진 불투명 구조물(+3 px)이면 판 중앙값 메움
THIN_LINE_GAP = 3          # 가는 선 = 위아래(좌우) 이만큼(px) 떨어진 두 픽셀 모두와 미리 곱한 색 채널 최대 차 > INK_MIN 인 픽셀의 긴 줄


def _thin_lines(cw, aw, bh: float):
    """1b 후속 L 다음 — 컨셉의 길고 가는 가로 · 세로 선(막대 윗선 · 테두리선 — 글자보다 긴: 가로 1.5 × 상자 높이 · 세로 1.05 ×). 넓은 띠 · 트랙 · 글자 빛 고리는 아님
    (계단 경계는 한쪽과만 다르다). 채널 최대 차 — 밝기로 재면 초록 막대 위 청록 윗선이 막대와 같게 나왔다 [실측 L 다음 오프라인 파티 130201 HP 숫자 밑]."""
    import cv2
    import numpy as np
    from gen import diagnose as dg
    pm = cw * aw[..., None]
    g = THIN_LINE_GAP
    out = np.zeros(aw.shape, bool)
    for axis, ker in ((0, np.ones((1, max(3, int(1.5 * bh))), np.uint8)), (1, np.ones((max(3, int(1.05 * bh)), 1), np.uint8))):
        p = np.pad(pm, ((g, g), (0, 0), (0, 0)) if axis == 0 else ((0, 0), (g, g), (0, 0)), mode="edge")
        a_, b_ = (p[:-2 * g], p[2 * g:]) if axis == 0 else (p[:, :-2 * g], p[:, 2 * g:])
        ridge = (np.abs(pm - a_).max(axis=2) > dg.INK_MIN) & (np.abs(pm - b_).max(axis=2) > dg.INK_MIN)
        out |= cv2.morphologyEx(ridge.astype(np.uint8), cv2.MORPH_OPEN, ker) > 0
    return out


OTHER_SHARE_MARGIN = 0.25   # 획 후보 덩어리가 다른 글자 상자 안 비율이 자기 상자 안 비율보다 이만큼 넘게 크면 그 글자 몫(이 글자 획 아님)


def _drop_other_glyphs(cand, own, other_masks):
    """1b 후속 L 다음 — 획 후보 덩어리 중 다른 글자 몫(다른 상자 안 비율 > 자기 상자 안 비율 + OTHER_SHARE_MARGIN)은 뺀다. 상자가 겹친 같은 몫(동점)은 둘 다
    메운다(예전 그대로). [실측 L 다음 오프라인 단색 R20261118_124503 — 원래 컨셉으로 '2/4' 획을 찾자 창이 위 '4.2' 의 '.' · '2' 아랫부분까지 잡아 정합이 흔들리고
    가는 '/' 가 두께 규칙(STROKE_SHARE)에 걸려 빠졌다]"""
    import cv2
    import numpy as np
    if not other_masks or not cand.any():
        return cand
    k, lab = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    drop = []
    for i in range(1, k):
        sel = lab == i
        mine = float(own[sel].mean())
        theirs = max(float(m[sel].mean()) for m in other_masks)
        if theirs > mine + OTHER_SHARE_MARGIN:
            drop.append(i)
    return cand & ~np.isin(lab, drop) if drop else cand


def _narrow_neigh_fill(col, a, win, cw, aw, g0, rect, glow: float, bh: float, why: str, orig_w=None, oth=None, **extra) -> dict:
    """1b 후속 L-3b — 판 정합이 안 되는 글자의 둘레 컨셉 메움(제자리에서 고침): 바꿀 자리 = 획(g0) + PLATE_GLYPH_GROW, 빛 글자면 빛 반경 안에서 '매끈한 바탕
    (획 · 빛 반경 밖 원천의 가우스 가중 평균)보다 PLATE_HALO_L 넘게 밝은' 픽셀 중 획에 이어진 것(글자보다 긴 가로 · 세로 구조선 제외 — 판 길 K (나) 와 같은 규칙),
    글자 상자(+2) 안까지. 원천 = 바꿀 자리 밖에서 둘레 대표색(빛 반경 밖 고리 중앙값)과 채널 차 PLATE_FILL_SOURCE_DIFF 미만(이웃 글자 · 밝은 장식 가장자리 빼기).
    1b 후속 L 다음 — 판정 · 원천은 원래 컨셉(orig_w — 앞 글자 메움 전)에서, 다른 글자 상자(oth, +2 px) 안은 원천 · 둘레에서 뺀다(이웃 글자 빛이 메움으로 번짐)."""
    import cv2
    import numpy as np
    from gen import cutout
    from gen import diagnose as dg
    y0, y1, x0, x1 = win
    h, w = aw.shape
    co, ao = orig_w if orig_w is not None else (cw, aw)
    pm_w = co * ao[..., None]
    pm_cur = cw * aw[..., None]
    free = ~dg._dilate(oth, 2) if oth is not None else np.ones((h, w), bool)
    gr = int(np.ceil(glow))
    reach = dg._dilate(g0, gr + PLATE_GLYPH_GROW + NARROW_EDGE_PX)
    ring = dg._dilate(reach, cutout.NOTEXT_RING) & ~reach
    if int((ring & free).sum()) >= 10:
        ring &= free
    med = np.median(pm_w[ring], axis=0) if int(ring.sum()) >= 10 else np.median(pm_w[~reach], axis=0)
    similar = np.abs(pm_w - med).max(axis=2) < PLATE_FILL_SOURCE_DIFF
    if int((similar & free & ~reach).sum()) >= 10:
        similar &= free
    hole = dg._dilate(g0, PLATE_GLYPH_GROW)
    # 원천 = 둘레 대표색과 비슷한 픽셀(이웃 장식 · 막대 색이 구멍으로 번지지 않게). 거르지 않으면 트랙 끝에 걸친 '0 %' 에 위 초록 막대가 흘러내렸다 —
    # 거르면 그 자리 트랙이 다수(투명)에 밀려 짧아진다(판이 트랙까지 지운 모호한 자리 — 진단에 맡김) [실측 L 오프라인 092315 '0 %']
    bg_pm, _ = _smooth_fill(pm_w, ao, ~reach & similar)
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
    fpm, fa = _smooth_fill(pm_w, ao, ~hole & similar if int((~hole & similar).sum()) >= 10 else ~hole)
    blend, zone = _blend_band(hole, 1, 1.0)
    out_a = blend * fa + (1 - blend) * aw
    pm = blend[..., None] * fpm + (1 - blend)[..., None] * pm_cur
    _put(col, a, win, zone, np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw), out_a)
    return {"used": True, "shift": [0, 0], "hole_px": int(hole.sum()), "halo_px": halo_px, "whole": False, "alpha_from": why, "fill": "smooth", **extra,
            **_zone_rec(win, zone)}


HIDDEN_TEXT_PAD = 4         # 1b 후속 L 다음 F1 — 숨는 글자 자리 = 상자 + 빛 + 이만큼(px) — 상태 검사 S1(gen/state_check) · diagnose.HIDDEN_PAD 와 같은 자리
HIDDEN_ALPHA_SIMILAR = 0.3  # 그 자리 메움 원천 = 둘레 대표와 미리 곱한 색 차 < PLATE_FILL_SOURCE_DIFF 이고 알파 차 < 이것(어둡고 불투명한 트랙 ≠ 투명)
HIDDEN_GLYPH_EVIDENCE = 0.05  # 컨셉이 그 글자를 그렸나 — 상자 안 '글자 없는 판과 크게 다른'(없으면 글자색 근처) 픽셀 비율(diagnose.GLYPH_EVIDENCE 와 같음)
HIDDEN_FILL_WY = 0.05       # 그 자리 경계값 보간의 세로 이웃 무게(가로 1) — 가로로 이어진 둘레(테두리 윗빛 띠)를 줄마다 잇고 줄 사이는 살짝만


ERASE_METHODS = ("lama", "harmonic", "clear_alpha")   # 글자 지우기 마감 — 지운 판 후보: lama = G1 넓힌 자리 + 인페인팅(extract.text_fill) · harmonic = 넓힌 자리
                                       # 경계값 보간(F1 식 — 미리 곱한 색 · 알파 함께) · (글자 지우기 다음 V5) clear_alpha = 투명 바탕 글자만 알파 꼬리로 자리 · 경계(아니면 예전 판과 같음).
                                       # 'off' = 예전 좁은 판. 글자마다 게이트와 같은 함수로 고른다(_gate_erase_choice)


ERASE_DEFAULT = ("lama", "harmonic")   # 글자 지우기 다음 — 기본 후보. clear_alpha 는 옵트인(extract.text_erase_methods): 투명 바탕 빛 글자의 넓은 컨셉 빛까지 지워 빈 값
                                       # 상태(S4)는 깨끗해지지만 컨셉 상태 진단(E1 글자 구역 바탕 — 엔진 빛은 그만큼 넓지 않음)이 새 얼룩을 잡았다 — 고르기는 S4 만 봐서 못 본다
                                       # [실측 R20261120_142400 파티 — Lv clear_alpha S4 2.6 → 0.0 인데 E1 9]


def erase_methods(cfg: dict | None) -> tuple:
    """지운 판 후보 방법(pipeline.yaml extract.text_erase_methods — 없으면 ERASE_DEFAULT, ERASE_METHODS 안의 것만)."""
    m = ((cfg or {}).get("extract") or {}).get("text_erase_methods")
    return tuple(x for x in (m or ERASE_DEFAULT) if x in ERASE_METHODS)


def _hidden_root(spec: dict, wid: str) -> str | None:
    """이 위젯을 시작 때 숨기는 가장 바깥 조상(자기 포함 — visibility collapsed · hidden) 또는 None."""
    index = spec_mod.widget_index(spec)
    w, root = index.get(wid), None
    while w is not None:
        if w.get("visibility") in ("collapsed", "hidden"):
            root = w["id"]
        w = index.get(w.get("parent")) if w.get("parent") else None
    return root


def _same_hidden_group(spec: dict, wid: str, aid: str | None) -> bool:
    """1b 후속 L 다음 H1 — 시작 때 숨는 글자의 밑 텍스처(aid)를 쓰는 위젯이 모두 같은 숨는 위젯 아래면(배너 BurstBanner — 텍스처째 숨음) 그 글자 자리도
    지운다(켠 상태 + 글자 빈 값에서 글자 밑이 보인다). 글자만 숨고 판은 보이는 경우('오의 불가' — 판 위)는 아님(F1)."""
    root = _hidden_root(spec, wid)
    users = asset_users(spec, aid) if aid else []
    if root is None or not users:
        return False
    index = spec_mod.widget_index(spec)

    def under(i):
        w = index.get(i)
        while w is not None:
            if w["id"] == root:
                return True
            w = index.get(w.get("parent")) if w.get("parent") else None
        return False
    return all(under(u["id"]) for u in users)


def _plan_method(v) -> tuple[str, int]:
    """글자 지우기 계획 값 '방법' 또는 '방법@단계'(V6 반복 보강 — 여백 단계) → (방법, 단계)."""
    s = str(v or "off")
    m, _, lv = s.partition("@")
    return m, int(lv) if lv.isdigit() else 0


def _concept_ocr(run) -> list[list[float]]:
    """V7 — 컨셉(reference.png)의 OCR 검출 상자(캔버스 좌표) — run 에 한 번(캐시 파일 refine_concept_ocr.json)."""
    import json as json_
    c = getattr(run, "concept_ocr", None)
    if c is not None:
        return c
    p = run.path("refine_concept_ocr.json")
    boxes: list = []
    try:
        if p.is_file():
            boxes = json_.loads(p.read_text(encoding="utf-8")).get("boxes") or []
        elif run.path("reference.png").is_file():
            from core import ocr
            det = ocr.detect(run.path("reference.png"), max_boxes=400)
            boxes = [b["box"] for b in det["boxes"]]
            p.write_text(json_.dumps({"engine": det["engine"], "min_score": det["min_score"], "boxes": boxes}, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — OCR 이 없으면 V7 없이(기록)
        boxes = []
        run.concept_ocr_error = f"{type(exc).__name__}: {exc}"[:160]
    run.concept_ocr = boxes
    return boxes


def _ocr_boxes_for(boxes: list, tb, origin) -> list[list[float]]:
    """V7 — 캔버스 OCR 상자 중 이 글자 상자(tb — 조각 좌표, origin = 조각 원점 캔버스 좌표)와 겹치는 것(검출 넓이의 MARK_TEXT_OVERLAP 이상 또는 글자 상자의 절반 이상)
    → 조각 좌표 상자들."""
    ox, oy = float(origin[0]), float(origin[1])
    t = [float(tb[0]) + ox, float(tb[1]) + oy, float(tb[2]), float(tb[3])]
    out = []
    for b in boxes or []:
        ix = max(0.0, min(b[0] + b[2], t[0] + t[2]) - max(b[0], t[0]))
        iy = max(0.0, min(b[1] + b[3], t[1] + t[3]) - max(b[1], t[1]))
        inter = ix * iy
        if inter > 0 and (inter >= MARK_TEXT_OVERLAP * max(1e-6, b[2] * b[3]) or inter >= 0.5 * max(1e-6, t[2] * t[3])):
            out.append([float(b[0]) - ox, float(b[1]) - oy, float(b[2]), float(b[3])])
    return out


def _erase_setup(run, spec: dict | None, texts: list[dict], orig_rgb, log: dict, aid: str | None = None, origin=None):
    """1b 후속 L 다음 G1 · G2 — extract.text_erase(off | values | values_glow | all)에 따라 글자 항목에 erase 표시 + erase_method(지우기 방법 — run.erase_plan[aid]
    가 있으면 글자마다 그 값 · 없으면 첫 판 = 모두 lama), 아트 모드는 지울 글자 없음. 시작 때 숨는 글자는 그 밑 텍스처가 같이 숨을 때만(H1 — _same_hidden_group),
    아니면 F1 몫. extract.text_fill == lama 면 인페인팅 hook(gen/inpaint.patch — 원래 컨셉 조각 orig_rgb 위 창) → hook 또는 None. 기록은 log['text_erase']."""
    ext = run.cfg.get("extract") or {}
    mode = str(ext.get("text_erase") or "off")
    if mode not in ("values", "values_glow", "all") or not texts or art_files(run):
        return None
    sp = spec or {"widgets": []}
    index = spec_mod.widget_index(sp)
    plan = (getattr(run, "erase_plan", None) or {}).get(aid) if aid else None
    use_ocr = bool(ext.get("text_erase_ocr", True)) and origin is not None
    cboxes = _concept_ocr(run) if use_ocr else []
    marked, methods = [], {}
    for t in texts:
        w = index.get(t.get("id")) or {}
        for k_ in ("erase", "erase_method", "erase_pad", "ocr_boxes"):
            t.pop(k_, None)
        if t.get("hidden") or _starts_hidden(sp, t.get("id")):
            if not _same_hidden_group(sp, t.get("id"), aid):
                continue
            t["hidden_group"] = _hidden_root(sp, t.get("id"))
        dynamic = isinstance(w.get("text"), dict) and w["text"].get("source") == "dynamic"
        # values_glow — 값 글자 + 빛 글자. 'all'(11-19 사용자 결정 — 모든 글자 다시 시도)은 게이트와 같은 고르기(_gate_erase_choice)가 예전보다 나빠지는 글자를
        # 예전 판으로 되돌린다(텍스처 단독 점수로 고를 땐 조작 안내가 나빠져 values_glow 로 좁혔었다 [실측 회귀 j/k_final_1119])
        glowing = float(t.get("glow") or 0) > 0
        if mode == "all" or dynamic or (mode == "values_glow" and glowing):
            marked.append(t.get("id"))
            v = (plan or {}).get(t.get("id"), "off") if plan is not None else "lama"
            methods[t.get("id")] = v
            m, lv = _plan_method(v)
            if m in ERASE_METHODS:
                t["erase"] = True
                t["erase_method"] = m
                if lv:
                    t["erase_pad"] = lv                       # V6 반복 보강 단계
                ob = _ocr_boxes_for(cboxes, t["box"], origin) if use_ocr else []
                if ob:
                    t["ocr_boxes"] = ob                       # V7 컨셉 OCR 상자(조각 좌표)
    rec = {"mode": mode, "texts": marked, "methods": methods, "fill": "plate"}
    if use_ocr:
        rec["ocr_boxes"] = {t["id"]: len(t.get("ocr_boxes") or []) for t in texts if t.get("erase")}
        if getattr(run, "concept_ocr_error", None):
            rec["ocr_error"] = run.concept_ocr_error
    hook = None
    if any(_plan_method(m)[0] == "lama" for m in methods.values()) and str(ext.get("text_fill") or "plate") == "lama":
        from gen import inpaint
        inpaint.configure(ext.get("lama_model"))
        rec["fill"] = "lama"
        rec["model"] = inpaint.status()["path"]

        def hook(x0, y0, hole, extra):
            return inpaint.patch(orig_rgb, x0, y0, hole | extra)
    log["text_erase"] = rec
    return hook


def _starts_hidden(spec: dict, wid: str) -> bool:
    """이 위젯이나 조상이 시작 때 숨는가(visibility collapsed · hidden) — flag 바인딩만 있고 시작 때 보이는 위젯(체인 패널)은 아니다."""
    index = spec_mod.widget_index(spec)
    w = index.get(wid)
    while w is not None:
        if w.get("visibility") in ("collapsed", "hidden"):
            return True
        w = index.get(w.get("parent")) if w.get("parent") else None
    return False


def _hidden_text_fill(col, a, item: dict, orig=None, others=None, mask=None, nt_pad=None) -> dict:
    """1b 후속 L 다음 F1 — 시작 때 숨는 글자(_starts_hidden)의 판 자리: 글자 획만이 아니라 자리(상자 + 빛 + HIDDEN_TEXT_PAD) 전체를 둘레에서 매끈하게
    메운다(경계값 보간 _harmonic_fill — 첫 값 _smooth_fill). 게임 시작 상태엔 엔진 글자가 없어 판이 그 자리를 그대로 보인다 — 예전 길(투명 위 글자 → 상자 + 2 px 둘레 메움)은 원천을 미리 곱한
    색으로만 골라 아래 어둡고 불투명한 게이지 트랙이 '투명과 비슷'하다며 끌려왔고, 원천에서 먼 가운데는 원천 전체 중앙값(트랙 알파)으로 채워 회색 둥근 상자 ·
    어두운 덩어리가 됐다 [실측 R20261119_091634 '오의 불가' — 판5, 사용자 인게임]. 자리를 가로지르는 구조물(자리 밖으로 이어진 불투명 덩어리 — 게이지 테두리
    윗선 · 가운데 장식, 글자색 · 빛 자리는 뺌)은 3 px · 길고 가는 선(_thin_lines)은 1 px 넓혀 지키고(컨셉 그대로), 원천 = 자리 밖 창 픽셀 중 둘레 고리(구조물
    · 다른 글자 상자 뺌) 대표와 미리 곱한 색 · 알파가 모두 비슷한 것(어둡고 불투명한 트랙 · 밝은 테두리선은 원천 아님). 판 마스크 밖(다른 판 · 기능 요소 자리)은
    안 칠한다. 컨셉이 그 글자를 안 그렸으면(글자 증거 < HIDDEN_GLYPH_EVIDENCE) 고치지 않음(used False — 예전 길로)."""
    import cv2
    import numpy as np
    from core import color as color_mod
    from gen import cutout
    from gen import diagnose as dg
    H, W = a.shape
    bx, by, bw, bh = (float(v) for v in item["box"])
    glow = float(item.get("glow") or 0)
    pad = HIDDEN_TEXT_PAD + glow
    m = int(np.ceil(pad)) + cutout.NOTEXT_RING + cutout.NOTEXT_GROW + 6
    x0, y0 = max(0, int(np.floor(bx - m))), max(0, int(np.floor(by - m)))
    x1, y1 = min(W, int(np.ceil(bx + bw + m))), min(H, int(np.ceil(by + bh + m)))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return {"used": False, "reason": "outside the plate"}
    cw_cur, aw_cur = col[y0:y1, x0:x1], a[y0:y1, x0:x1]
    cw, aw = (orig[0][y0:y1, x0:x1], orig[1][y0:y1, x0:x1]) if orig is not None else (cw_cur.copy(), aw_cur.copy())
    h, w = aw.shape
    own = dg._box_mask((h, w), [bx - x0, by - y0, bw, bh])
    zone = dg._box_mask((h, w), [bx - x0, by - y0, bw, bh], pad)
    oth, _ = _other_text_mask(others, x0, y0, h, w)
    free = ~dg._dilate(oth, 2) if oth is not None else np.ones((h, w), bool)
    pm_w = cw * aw[..., None]
    # 컨셉이 그 글자를 그렸나 — 글자 없는 판이 있으면 그것과 크게 다른 픽셀, 없으면 사양 글자색 근처 픽셀의 상자 안 비율
    lab = color_mod.srgb_to_lab(cw)
    cols = [np.asarray(c, float) for c in (item.get("colors") or [])]
    near = np.min([color_mod.delta_e00(lab, color_mod.srgb_to_lab(c.reshape(1, 1, 3))) for c in cols], axis=0) < PLATE_TEXT_DE if cols else None
    if near is not None:
        near &= aw > 0.3
    if nt_pad is not None:
        P = cutout.NOTEXT_SHIFT
        pm_n = nt_pad[0][P + y0:P + y1, P + x0:P + x1] * nt_pad[1][P + y0:P + y1, P + x0:P + x1][..., None]
        ev = float(((np.abs(pm_w - pm_n).max(axis=2) > dg.INK_MIN) & own).sum()) / max(1, int(own.sum()))
        ev_from = "text-free concept difference"
    else:
        ev = float((near & own).sum()) / max(1, int(own.sum())) if near is not None else 0.0
        ev_from = "spec text colour"
    if ev < HIDDEN_GLYPH_EVIDENCE:
        return {"used": False, "reason": f"hidden text not drawn in the concept (glyph evidence {ev:.3f} by {ev_from})", "glyph_evidence": round(ev, 3)}
    glyphish = dg._dilate(near & zone, int(np.ceil(glow)) + 2) if near is not None else np.zeros((h, w), bool)
    n_o, lab_o = cv2.connectedComponents((aw > 0.5).astype(np.uint8), connectivity=8)
    cross = np.unique(lab_o[(lab_o > 0) & ~zone])
    crossm = np.isin(lab_o, cross[cross > 0]) if len(cross) else np.zeros((h, w), bool)
    protect = dg._dilate(crossm & ~glyphish, 3) | dg._dilate(_thin_lines(cw, aw, bh) & ~glyphish, 1)
    hole = zone & ~protect & free
    if mask is not None:
        hole &= np.asarray(mask, bool)[y0:y1, x0:x1] | (aw_cur > 0)
    if not hole.any():
        return {"used": False, "reason": "nothing to fill in the hidden text spot", "nothing": True}
    ring = dg._dilate(zone, cutout.NOTEXT_RING) & ~zone & ~protect & free
    if int(ring.sum()) >= 10:
        med_pm, med_a = np.median(pm_w[ring], axis=0), float(np.median(aw[ring]))
    else:
        med_pm, med_a = np.zeros(3), 0.0
    similar = (np.abs(pm_w - med_pm).max(axis=2) < PLATE_FILL_SOURCE_DIFF) & (np.abs(aw - med_a) < HIDDEN_ALPHA_SIMILAR)
    src = ~hole & similar & free            # 지킨 구조물 가장자리(테두리 윗선 빛)도 원천 — 자리 안 빛 띠가 가운데서 끊기지 않게
    src_from = "ring-like pixels outside the hole"
    if int(src.sum()) < 10:
        src, src_from = ~hole & free, "every pixel outside the hole (no ring-like source)"
    fpm, fa = _smooth_fill(pm_w, aw, src)
    # 경계값 보간(_harmonic_fill — 첫 값 = 매끈한 메움, 세로 무게 HIDDEN_FILL_WY): 둘레(지금 판 — 구멍 밖 픽셀)에 이어지고 단계 · 줄무늬 없음, 구멍 밖은 그대로.
    # 판 상자 끝에 닿은 창 가장자리는 투명 경계(이 판은 거기서 끝난다) — 아니면 기울기 0 이라 아래 테두리 빛이 위로 넓게 번져 돔 모양 아지랑이가 남았다
    # [실측 R20261119_091634 F1 둘째 판 — 등방 보간, 흰 바탕 알파 최대 0.15]
    cur = np.dstack([cw_cur * aw_cur[..., None], aw_cur])
    cur_p = np.pad(cur, ((1, 1), (1, 1), (0, 0)), mode="edge")
    for cond, sl in ((y0 == 0, (0, slice(None))), (y1 == H, (-1, slice(None))), (x0 == 0, (slice(None), 0)), (x1 == W, (slice(None), -1))):
        if cond:
            cur_p[sl] = 0.0
    init_p = np.pad(np.dstack([fpm, fa]), ((1, 1), (1, 1), (0, 0)), mode="edge")
    u = _harmonic_fill(cur_p, np.pad(hole, 1, constant_values=False), init=init_p, wy=HIDDEN_FILL_WY)[1:-1, 1:-1]
    out_a = np.where(hole, np.clip(u[..., 3], 0.0, 1.0), aw_cur)
    pm = np.where(hole[..., None], np.clip(u[..., :3], 0.0, 255.0), cur[..., :3])
    col[y0:y1, x0:x1] = np.where(hole[..., None] & (out_a[..., None] > 1e-4), pm / np.maximum(out_a, 1e-4)[..., None], cw_cur)
    a[y0:y1, x0:x1] = out_a
    return {"used": True, "fill": "hidden_text", "hole_px": int(hole.sum()), "protect_px": int((protect & zone).sum()), "zone_pad": round(pad, 1),
            "ring_alpha": round(med_a, 3), "source_px": int(src.sum()), "source": src_from, "glyph_evidence": round(ev, 3), "evidence_from": ev_from,
            **_zone_rec((y0, y1, x0, x1), hole)}


ERASE_DE = 3.0              # 1b 후속 L 다음 G1 — 넓힌 지울 자리 = 핵심 획에 이어지고 컨셉이 정합된 판(색조 맞춤)과 ΔE00 이만큼 넘게 다른 픽셀
ERASE_TAIL_MAX = 24         # G1 — 빛 꼬리(glow_measure) 상한(px)
ERASE_STRUCT_DE = 10.0      # G1 — 지킬 판 구조물 = 판에도 있고(_plate_same) 둘레 바탕 추정과 ΔE00 이만큼 넘게 다른 픽셀(장식선 · 테두리) — 평평한 바탕 · 옅은 빛 잔재는 아님
LAMA_MASK_GROW = 2          # G2 (가) — 인페인팅 마스크 = 지울 자리 + 이만큼(px — 가장자리 안티앨리어싱이 원천에 남아 글자를 다시 그렸다)
LAMA_OTHER_GROW = 12        # G2 (가) — 같은 창의 다른 글자 획 + 이만큼(빛)도 원천에서 가린다(그 빛을 이 자리로 이어 그리지 않게)
LAMA_SEAM_MAX = 12.0        # G2 (가) 매끈한 이음 — 테두리 (컨셉 − 인페인팅) 차가 채널 최대 이보다 크면 그 픽셀은 이음에 안 씀
LAMA_SEAM = False           # 매끈한 이음 끔 — 세 판 모두 나빠짐 [실측 오프라인 R20261119_144231 S4 7.6 → 14.8 · 9.6, 붙일 자리 + 4 px 테두리 판 3.2 → 11.3 · 단색 001742 28.7 → 68.6]
LAMA_CONTEXT_K = 2          # G2 (가) — 원천 가림 = 획 + 빛 꼬리 × 이것 + LAMA_CONTEXT_PAD(붙이는 자리는 지울 자리 그대로) — 마스크 밖 옅은 빛 기울기를 '가운데
LAMA_CONTEXT_PAD = 6        # 광원'으로 이어 그려 '4' 안 따뜻한 아지랑이가 났다 [실측 오프라인 R20261119_144231 — S4 7.6]
ERASE_PAD = 6               # 글자 지우기 마감 — 지울 자리 최소 = 획 + 이만큼(차이와 상관없이 · 상자 밖 획 둘레 포함, 지킬 것 빼고)
ERASE_CLOSE = 12            # 글자 지우기 다음 — 한 글자 위젯 안 글자 · 낱말 사이 틈을 지울 자리로 닫는 반경(px, 0 = 끔) — [실측 오프라인 235452 배너: 6 은 글자 사이만
                            # 닫아 낱말 사이 띄어쓰기 자리의 바탕 얼룩이 점으로 남음, 12 는 글자 자리가 한 덩어리 — 고립된 점 없음]
ERASE_DIFF_TAIL = False     # 글자 지우기 다음 — 차이 꼬리(둘레 · 판과 견준 밝힌 그림 차 고리로 지울 자리 넓힘) — 끔: 배너엔 3 ~ 4 px 로 효과 작고 단색 '2/4' lama 를
                            # 5.87 로 나쁘게 했다(끄면 1.62) [실측 단색 001742 끄기 실험]
DIFF_TAIL_EXCESS = 0.15   # 글자 지우기 다음 — 차이 꼬리: 고리의 '둘레 바탕과 다른' 비율이 먼 고리 기준보다 이만큼 넘는 거리까지
ERASE_PAD_STEP = 6          # 글자 지우기 다음 V6 — 반복 보강 단계마다 여백 · 빛 · 알파 꼬리 + 이만큼(ERASE_PAD 6 → 12 → 18)
ERASE_RETRIES = 2           # V6 — 받은 후보가 없거나 결함이 남은 글자만 여백 키워 다시 굽는 횟수 상한
OCR_BOX_PAD = 6             # V7 — 컨셉 OCR 상자 + 이만큼을 지울 수 있는 범위(rect_e)에 합침
OCR_NEAR_PAD = 6            # V6 — 지운 판 OCR 검출이 글자 상자 + 이만큼 안이면 잔여물(반복 보강 대상), 밖이면 먼 검출(ocr_far — 기록만)


def _tone_plane(cw, aw, nc, na, hole):
    """판 조각 색조를 둘레 컨셉에 맞춤(_plate_item_fill 안 K (나) 와 같은 식 — 구멍 밖 NOTEXT_RING 고리 평면 맞춤). → (맞춘 판 색, 계수 또는 None)."""
    import numpy as np
    from gen import cutout
    from gen import diagnose as dg
    h, w = aw.shape
    ring_t = dg._dilate(hole, cutout.NOTEXT_RING) & ~hole & (aw > 0.5) & (na > 0.5)
    if int(ring_t.sum()) < 20:
        return nc, None
    yy, xx = np.nonzero(ring_t)
    A = np.stack([np.ones(len(xx)), xx / max(1.0, w), yy / max(1.0, h)], axis=1)
    coef, *_ = np.linalg.lstsq(A, (cw - nc)[ring_t], rcond=None)
    gy, gx = np.mgrid[0:h, 0:w]
    corr = np.clip(coef[0][None, None] + coef[1][None, None] * (gx / max(1.0, w))[..., None] + coef[2][None, None] * (gy / max(1.0, h))[..., None],
                   -PLATE_TONE_MAX, PLATE_TONE_MAX)
    return np.clip(nc + corr, 0, 255), [round(float(v), 1) for v in coef[0]]


def _erase_zone(cw, aw, nc, na, glyph, hole, own, glow: float, keep_out, same=None, bh: float = 20.0, pad_level: int = 0, ocr_r=None, oth_box=None):
    """1b 후속 L 다음 G1 — 좁은 메움 자리(hole — 획 + 3 px + 판보다 L 10 밝은 빛)를 컨셉 빛 꼬리까지 넓힌다: 핵심 획(glyph) + 빛 꼬리(glow_measure — 컨셉 ↔
    색조 맞춘 판, ≤ ERASE_TAIL_MAX) 안에서 컨셉이 판과 ΔE00 ERASE_DE 넘게 다르고 좁은 자리에 이어진 픽셀. 상자(+2 px + 빛 꼬리가 analyze 빛보다 긴 만큼) 밖 ·
    keep_out(다른 글자 상자 · 판에도 있는 구조물)은 안 넣는다. 좁은 메움 경계에서 끊긴 빛이 텍스처에 윤곽으로 남았다 [실측 R20261119_144231 체인 패널 '4.2' —
    컨셉 − 판 L* 1 px +12.4 · 3 px +7.0 · 5 px +3.7 · 7 px +1.1, 메움 경계 고리 2 466 px]. → (넓힌 자리, 기록)."""
    import cv2
    import numpy as np
    from core import color as color_mod
    from gen import diagnose as dg
    pm_c, pm_n = cw * aw[..., None], nc * na[..., None]
    # 빛 꼬리 — 판과 견준 것 · 둘레(획 10 ~ 14 px 띠)와 견준 것 중 긴 쪽: codex 판이 글자 빛을 덜 지워 남기면 판과 견준 꼬리가 짧다
    # [실측 R20261119_144231 '4.2' — 판에 갈색 빛 잔재, 판으로 넓게 메운 판에서 '4.2' 모양 갈색 얼룩]
    tails = [int(np.ceil(glow))]
    for bg_ in (pm_n, None):
        gm = dg.glow_measure(pm_c, bg_, glyph, max_d=ERASE_TAIL_MAX) if glyph.any() else None
        tails.append(int(gm["size"]) if gm and gm.get("size") else 0)
    st_ = ERASE_PAD_STEP * int(pad_level)          # V6 반복 보강 — 단계마다 여백 · 빛 꼬리 + ERASE_PAD_STEP
    tail = max(tails) + st_
    pad = ERASE_PAD + st_
    reach = dg._dilate(glyph, tail + PLATE_GLYPH_GROW)
    # 글자 지우기 마감 — 상자 밖으로 나간 획 둘레(ERASE_PAD)도: analyze 상자가 획보다 좁으면 잘린 획 끝 · 어두운 외곽선이 인페인팅 마스크 경계에 걸려 LaMa 가 그 흰
    # 가장자리로 글자를 다시 그렸다 [실측 오프라인 R20261119_190059 배너 '3' — S4 76.6]. V7 — 컨셉 OCR 상자(+ OCR_BOX_PAD)도 지울 수 있는 범위(안의 지울 픽셀은
    # 아래 규칙 그대로 — 상자째 지우지 않음)
    rect_e = dg._dilate(own, 2 + max(0, tail - int(np.ceil(glow)))) | dg._dilate(glyph, pad)
    if ocr_r is not None and np.asarray(ocr_r).any():
        rect_e |= np.asarray(ocr_r, bool)
    lab_c = color_mod.srgb_to_lab(pm_c)
    de = color_mod.delta_e00(lab_c, color_mod.srgb_to_lab(pm_n)) > ERASE_DE
    # 둘레 바탕 추정(빛 꼬리 밖 · 다른 글자 밖 · 불투명 원천의 매끈한 메움)과도 다르면 자리 — 판에 남은 글자 빛 잔재도 지운다
    src = ~dg._dilate(glyph, tail + PLATE_GLYPH_GROW) & ~keep_out & (aw > 0.5)
    de_s = None
    diff_rec: dict = {}
    if int(src.sum()) >= 20 and not ERASE_DIFF_TAIL:
        fpm, _ = _smooth_fill(pm_c, aw, src)
        de_s = color_mod.delta_e00(lab_c, color_mod.srgb_to_lab(fpm))
        de |= de_s > ERASE_DE
    elif int(src.sum()) >= 20:
        fpm, _ = _smooth_fill(pm_c, aw, src)
        de_s = color_mod.delta_e00(lab_c, color_mod.srgb_to_lab(fpm))
        # 글자 지우기 다음 — 차이 꼬리(ERASE_DIFF_TAIL — 기본 끔): 빛 꼬리(glow_measure)는 밝은 쪽만 재서 어두운 외곽 그림자 꼬리는 0 이었다 — 배너 글자 사이 · 아래에 그림자 조각이 지울 자리(획 + 6)
        # 밖에 남아 × 3 밝힘에서 점이 됐다 [실측 R20261119_235452 배너 — 사용자 눈 '점', 오프라인 그림: 점 = 바뀐 자리 사이 틈]. 획에서 거리마다 고리 픽셀이 둘레 바탕
        # 추정과 다른(ΔE00 · 밝힌 그림 ΔE00 큰 쪽 > ERASE_DE) 비율이 먼 고리 기준보다 DIFF_TAIL_EXCESS 넘는 데까지(밝은 빛 · 어두운 그림자 모두)
        lab_f = color_mod.srgb_to_lab(fpm)
        de_l = color_mod.delta_e00(color_mod.srgb_to_lab(np.clip(pm_c * DESPECKLE_LIFT, 0, 255)), color_mod.srgb_to_lab(np.clip(fpm * DESPECKLE_LIFT, 0, 255)))
        okr = (aw > 0.5) & ~keep_out
        # 둘레 추정과 견준 것 · 글자 없는 판(색조 맞춘 판 — 빛무리 · 그림자 없음)과 밝힌 그림으로 견준 것 중 긴 쪽(둘레 추정은 그림자 자체를 끌어와 짧게 잰다)
        de_pl = color_mod.delta_e00(color_mod.srgb_to_lab(np.clip(pm_c * DESPECKLE_LIFT, 0, 255)), color_mod.srgb_to_lab(np.clip(pm_n * DESPECKLE_LIFT, 0, 255)))
        difs = {"smooth": (np.maximum(de_s, de_l) > ERASE_DE) & okr, "plate": (de_pl > 2 * ERASE_DE) & okr & (na > 0.5)}
        dtail, profs, f0s = 0, {}, {}
        for kd, dif in difs.items():
            prof, prev = [], glyph
            for d in range(1, ERASE_TAIL_MAX + 1):
                cur = dg._dilate(glyph, d)
                ring = cur & ~prev & okr
                prev = cur
                prof.append(float(dif[ring].mean()) if int(ring.sum()) >= 8 else None)
            far = [v for v in prof[-6:] if v is not None]
            f0 = float(np.median(far)) if far else 0.0
            t_, gap = 0, 0
            for d, v in enumerate(prof, start=1):
                if v is not None and v > f0 + DIFF_TAIL_EXCESS:
                    t_, gap = d, 0
                else:
                    gap += 1
                    if gap > 2:
                        break
            dtail = max(dtail, t_)
            profs[kd], f0s[kd] = [None if v is None else round(v, 2) for v in prof[:16]], round(f0, 3)
        diff_rec = {"diff_tail": dtail, "diff_far": f0s, "diff_profile": profs}
        if dtail + st_ > tail:
            tail = dtail + st_
            reach = dg._dilate(glyph, tail + PLATE_GLYPH_GROW)
            rect_e = dg._dilate(own, 2 + max(0, tail - int(np.ceil(glow)))) | dg._dilate(glyph, pad) | (np.asarray(ocr_r, bool) if ocr_r is not None else False)
            src = ~dg._dilate(glyph, tail + PLATE_GLYPH_GROW) & ~keep_out & (aw > 0.5)
            if int(src.sum()) >= 20:
                fpm, _ = _smooth_fill(pm_c, aw, src)
                lab_f = color_mod.srgb_to_lab(fpm)
                de_s = color_mod.delta_e00(lab_c, lab_f)
                de_l = color_mod.delta_e00(color_mod.srgb_to_lab(np.clip(pm_c * DESPECKLE_LIFT, 0, 255)),
                                           color_mod.srgb_to_lab(np.clip(fpm * DESPECKLE_LIFT, 0, 255)))
        de |= de_s > ERASE_DE
        de |= dg._dilate(glyph, tail + PLATE_GLYPH_GROW) & (de_l > ERASE_DE) & (aw > 0.5)         # 어두운 판의 낮은 대비 그림자(밝힌 그림)
    # 지킬 것 — 다른 글자 상자(keep_out) · 길고 가는 선 · 판에도 있는 뚜렷한 구조물(둘레 추정과 ΔE00 ERASE_STRUCT_DE 넘게 다름). _plate_same 만으로 지키면 평평한
    # 패널 바탕 · 판에 남은 옅은 빛 잔재까지 '구조물'이라 넓힘이 0 이었다 [실측 오프라인 R20261119_144231 '4.2' — 넓힘 0 px]
    # 글자 지우기 마감 — 길고 가는 선도 글자 · 빛 자리를 가로지르는 것만(글자 어두운 외곽선이 '가는 선'으로 지켜져 harmonic 메움의 경계값 → 글자 자리 검은 점
    # [실측 오프라인 R20261119_190059 배너])
    keep = keep_out | _crossing(dg._dilate(_thin_lines(cw, aw, bh), 1), dg._dilate(glyph, max(tail, pad) + PLATE_GLYPH_GROW))
    struct = np.zeros_like(keep)
    if same is not None:
        # 글자 지우기 마감 H2 — 판 구조물은 글자 · 빛 자리를 가로지르는 것만(_crossing) — 자리 안에 갇힌 것은 codex 판이 덜 지운 글자 흔적('4' 안쪽 윤곽)
        struct = _crossing(same & ~dg._dilate(glyph, 1) & ((de_s > ERASE_STRUCT_DE) if de_s is not None else True), reach)
        keep |= struct
    ext = reach & de & rect_e & ~keep
    # 글자 지우기 마감 — 획 + ERASE_PAD 는 차이와 상관없이(어두운 외곽 그림자 · 낮은 대비 테두리는 ΔE00 3 아래라 빠져 배너 글자 모양 얼룩으로 남았다
    # [실측 R20261119_190059 배너 — 컨셉 − 판 획 밖 2 px L* −1.1], 마스크 경계가 깨끗한 바탕에 오게)
    ext |= dg._dilate(glyph, pad) & rect_e & ~keep
    # 단계별 픽셀 수(기록 — 넓힘이 어디서 막히는지): 빛 꼬리 안 · 다름 · 둘 다 · 상자 안 · 지킴 뺌 · 좁은 자리 밖
    steps = [int(reach.sum()), int(de.sum()), int((reach & de).sum()), int((reach & de & rect_e).sum()), int(ext.sum()), int((ext & ~hole).sum())]
    n, lab = cv2.connectedComponents((ext | hole).astype(np.uint8), connectivity=8)
    touch = np.unique(lab[hole & (lab > 0)])
    ext &= np.isin(lab, touch[touch > 0])
    new = hole | ext
    closed_px = 0
    lone = oth_box is None or not (dg._dilate(own, 2 + ERASE_CLOSE) & np.asarray(oth_box, bool)).any()
    if ERASE_CLOSE > 0 and lone:
        # 다른 글자 상자와 겹치는(닫기 반경 안) 글자는 닫지 않는다 — 겹친 상자에서 닫기가 이웃 경계에서 곧게 잘려 가는 선(골격 98)이 남거나 이웃 글자 빛 자리를
        # 지워 서로를 나쁘게 했다 [실측 회귀 q_next_1120 · 단색 001742 겨루기 — 체인 패널이 통째로 예전 판]. 배너 '체인 버스트' 는 '3' 상자와 떨어져 닫힌다
        # 글자 지우기 다음 — 한 글자 위젯 안 글자 사이 틈(두 글자의 어두운 빛무리 · 그림자가 겹친 자리)도 지울 자리로: 닫기(지름 2 × ERASE_CLOSE + 1) ∩ 지울 수 있는
        # 범위 · 지킬 것 밖 — 틈에 남은 컨셉 그림자가 지운 자리 사이에서 × 3 밝힘 점이 됐다 [실측 R20261119_235452 배너 '체' · '인' 사이 — 오프라인 그림]
        k_ = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ERASE_CLOSE + 1, 2 * ERASE_CLOSE + 1))
        cl = (cv2.morphologyEx(new.astype(np.uint8), cv2.MORPH_CLOSE, k_) > 0) & rect_e & ~keep & dg._dilate(own, 2)
        closed_px = int((cl & ~new).sum())
        new = new | cl
    return new, {"erase_tail": tail, "erase_tails": tails[1:], "erase_added_px": int((new & ~hole).sum()), "erase_px_steps": steps, "_keep": keep,
                 "_struct": struct, **diff_rec, **({"closed_px": closed_px} if closed_px else {})}


ERASE_ACCEPT_FLOOR = 3.0    # 글자 지우기 고르기(_gate_erase_choice) — 지운 판 S4(바탕 셋 3 × 3 국소 최대)가 max(좁은 판, 이것) + ERASE_ACCEPT_MARGIN 이하 ·
ERASE_ACCEPT_MARGIN = 0.5   # 결함 수 · 가는 선 길이가 좁은 판보다 늘지 않음 · 밝힌 검정이 좁은 판 + ERASE_LIFT_MARGIN 이하일 때만 받는다(아니면 좁은 판 — 예전 판)
ERASE_LIFT_MARGIN = 1.5     # [실측 오프라인 — L-1 144231 '4.2' 좁은 6.5 → LaMa 3.2(받음), 단색 001742 '4.2' 좁은 10.6 → LaMa 28.7(안 받음)]
ERASE_CONTOUR_FLOOR = 20    # 가는 선 골격 길이 — 좁은 판보다 길어도 이 이하면 같다고 봄(잡티)
ERASE_BG_MARGIN = 24        # 글자 지우기 다음 — 컨셉 상태 글자 구역 바탕 국소 > local_de 픽셀이 좁은 판보다 이만큼(진단 결함 최소 넓이) 넘게 늘면 못 받음


def _crossing(mask, reach):
    """mask 덩어리(8-연결) 중 reach 밖으로 이어진 것만 — 글자 · 빛 자리를 가로지르는 구조물(테두리 금선 · 막대 윗선). 자리 안에 갇힌 '판에도 있는 것'은 codex 판이
    덜 지운 글자 흔적이다 [실측 R20261119_190059 '4' 안쪽 윤곽 — 판 구조물 지킴(same_struct)이 남긴 컨셉 빛 테두리 385 px 가 전부 자리 안]."""
    import cv2
    import numpy as np
    mask = np.asarray(mask, bool)
    if not mask.any():
        return mask
    n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    ids = np.unique(lab[mask & ~np.asarray(reach, bool)])
    ids = ids[ids > 0]
    return np.isin(lab, ids) if len(ids) else np.zeros_like(mask)


def _fill_enclosed(hole):
    """지울 자리 안에 갇힌 칠 안 된 픽셀(획 속 · 'ㅇ' 속 — 바깥 경계 안)도 자리로 — 갇힌 것은 자리를 가로지르는 구조물일 수 없다. 남기면 harmonic 메움의 경계값 ·
    인페인팅 원천이 돼 글자 자리에 검은 점이 남았다 [실측 오프라인 R20261119_190059 배너 '체인 버스트' — 갇힌 131 px]."""
    import cv2
    import numpy as np
    hole = np.asarray(hole, bool)
    if not hole.any():
        return hole
    filled = np.zeros(hole.shape, np.uint8)
    cnts, _ = cv2.findContours(hole.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(filled, cnts, -1, 1, thickness=-1)
    return hole | (filled > 0)


def _struct_keep(cw, aw, same, glyph, reach, bh: float, free=None):
    """글자 지우기 마감 — 지우는 글자 자리에서 지킬 구조물(판 중앙값 · 좁은 둘레 길 — 판 정합 길은 _erase_zone 안 같은 규칙): 판에도 있고(same) 둘레 바탕 추정(reach 밖 ·
    불투명 원천의 매끈한 메움)과 ΔE00 ERASE_STRUCT_DE 넘게 다른 픽셀 ∪ 길고 가는 선 — 그중 글자 · 빛 자리(reach)를 가로지르는 덩어리만(_crossing)."""
    import numpy as np
    from core import color as color_mod
    from gen import diagnose as dg
    cand = dg._dilate(_thin_lines(cw, aw, bh), 1)
    if same is not None:
        pm = cw * aw[..., None]
        src = ~reach & (aw > 0.5) & (free if free is not None else True)
        if int(src.sum()) >= 20:
            fpm, _ = _smooth_fill(pm, aw, src)
            distinct = color_mod.delta_e00(color_mod.srgb_to_lab(pm), color_mod.srgb_to_lab(fpm)) > ERASE_STRUCT_DE
            cand = cand | (same & ~dg._dilate(glyph, 1) & distinct)
    return _crossing(cand, reach)


DESPECKLE_BAND = 3          # V4 — 경계 잡티를 보는 지울 자리 밖 띠(px)
DESPECKLE_DE = 6.0          # 5 × 5 중앙값(지울 자리는 둘레 매끈한 메움으로 바꾼 그림)과 ΔE00 이만큼 넘게 다른 픽셀
DESPECKLE_MAX_PX = 12       # 잡티 = 그런 픽셀의 8-연결 덩어리 중 넓이 ≤ 이것 · 상자 긴 변 ≤ DESPECKLE_MAX_SIDE(선 · 구조물은 길어 빠짐)
DESPECKLE_MAX_SIDE = 5
DESPECKLE_LIFT = 3.0        # 어두운 자리 점은 밝힌 그림(× 이것)으로도 잼
ERASE_DESPECKLE = True     # harmonic 메움에 V4 를 쓸지(겨루기 — 설계 §11 '글자 지우기 다음' V4)
BG_BAND = 6                 # V8 — 복잡 배경 판정 둘레 띠(지울 자리 밖 px)
BG_SOBEL = 40.0             # 엣지 = 미리 곱한 루마(0 ~ 255) 소벨 3 × 3 크기 > 이것
BG_LINE_LEN = 15            # 이 길이(px) 넘는 곧은 가로 · 세로 엣지 줄(구조선)은 결이 아니라 빼고 잰다


def _boundary_specks(cw, aw, hole, keep):
    """V4 — 지울 자리(hole) 바로 밖 DESPECKLE_BAND px 띠에 걸린 작은 잡티(어두운 점 · 그림자 조각) 마스크. 중앙값은 지울 자리를 둘레 매끈한 메움으로 바꾼 그림에서
    (글자 획이 중앙값을 끌지 않게), keep(지킬 구조물 · 다른 글자 자리)은 1 px 넓혀 뺀다."""
    import cv2
    import numpy as np
    from core import color as color_mod
    from gen import diagnose as dg
    hole = np.asarray(hole, bool)
    pm = cw * aw[..., None]
    fpm, _ = _smooth_fill(pm, aw, ~hole)
    img = np.where(hole[..., None], fpm, pm)
    med = cv2.medianBlur(np.clip(img, 0, 255).astype(np.uint8), 5).astype(float)
    de = color_mod.delta_e00(color_mod.srgb_to_lab(img), color_mod.srgb_to_lab(med))
    # 어두운 판(L* ≈ 9)의 점은 ΔE00 이 둔하다(SL 가중) — 밝힌 검정(× DESPECKLE_LIFT — 진단 text_trace_lift 와 같은 눈)으로도 재서 큰 쪽
    # [실측 R20261119_235452 배너 — 사람 눈은 × 3 밝힘에서 점을 봄]
    de = np.maximum(de, color_mod.delta_e00(color_mod.srgb_to_lab(np.clip(img * DESPECKLE_LIFT, 0, 255)),
                                            color_mod.srgb_to_lab(np.clip(med * DESPECKLE_LIFT, 0, 255))))
    diff = (de > DESPECKLE_DE) & ~hole & ~dg._dilate(np.asarray(keep, bool), 1)
    band = dg._dilate(hole, DESPECKLE_BAND) & ~hole
    out = np.zeros(hole.shape, bool)
    if not (diff & band).any():
        return out
    n, lab, st, _ = cv2.connectedComponentsWithStats(diff.astype(np.uint8), connectivity=8)
    for i in np.unique(lab[diff & band]):
        if i <= 0:
            continue
        x, y, w_, h_, area = (int(v) for v in st[i])
        if area <= DESPECKLE_MAX_PX and max(w_, h_) <= DESPECKLE_MAX_SIDE:
            out |= lab == i
    return out


def _background_stats(cw, aw, hole, free=None) -> dict:
    """V8 — 지울 자리 둘레 BG_BAND px 띠(다른 글자 자리 뺌)의 엣지 밀도(미리 곱한 루마 소벨 크기 > BG_SOBEL 비율) · 색 분산(L* 표준편차)."""
    import cv2
    import numpy as np
    from core import color as color_mod
    from gen import diagnose as dg
    hole = np.asarray(hole, bool)
    band = dg._dilate(hole, BG_BAND) & ~hole
    if free is not None:
        band &= np.asarray(free, bool)
    if int(band.sum()) < 10:
        return {"band_px": int(band.sum())}
    pm = np.clip(cw * aw[..., None], 0, 255)
    luma = (pm @ np.array([0.299, 0.587, 0.114])).astype(np.float32)
    mag = np.hypot(cv2.Sobel(luma, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(luma, cv2.CV_32F, 0, 1, ksize=3))
    L = color_mod.srgb_to_lab(pm)[..., 0]
    # 복잡 배경 = 결(무늬) — 띠를 가로지르는 긴 곧은 구조선(막대 윗선 · 테두리)은 뺀다: 투명 바탕 위 HP 숫자의 띠에 막대 윗선이 걸려 엣지 0.36 · L* 39 로 '복잡'이 됐다
    # [실측 R20261120_005215 오프라인 첫 판]
    e8 = (mag > BG_SOBEL).astype(np.uint8)
    lines = (cv2.morphologyEx(e8, cv2.MORPH_OPEN, np.ones((1, BG_LINE_LEN), np.uint8)) | cv2.morphologyEx(e8, cv2.MORPH_OPEN, np.ones((BG_LINE_LEN, 1), np.uint8))) > 0
    lines &= cv2.blur(e8.astype(np.float32), (9, 9)) < 0.6          # 둘레가 엣지로 빽빽한 곳(결 자체)의 줄은 선이 아님
    bt = band & ~dg._dilate(lines, 2)
    if int(bt.sum()) < 10:
        return {"band_px": int(band.sum()), "texture_px": int(bt.sum()), "edge_frac": 0.0, "l_std": 0.0, "line_px": int((band & lines).sum())}
    return {"band_px": int(band.sum()), "texture_px": int(bt.sum()), "edge_frac": round(float(np.mean(mag[bt] > BG_SOBEL)), 3),
            "l_std": round(float(np.std(L[bt])), 1), "line_px": int((band & lines).sum())}


def complex_background(bg: dict | None, cfg: dict | None) -> bool:
    """V8 — 둘레 엣지 밀도 · 색 분산이 둘 다 문턱(pipeline.yaml extract.complex_background{edge_frac, l_std})을 넘으면 복잡 배경(생성형 메움 · 수동 확인 대상)."""
    c = ((cfg or {}).get("extract") or {}).get("complex_background") or {}
    if not bg or bg.get("edge_frac") is None:
        return False
    return float(bg["edge_frac"]) > float(c.get("edge_frac", 0.35)) and float(bg["l_std"]) > float(c.get("l_std", 12.0))


def _erase_fill(col, a, win, cw_cur, aw_cur, hole, method: str, inpaint=None, other_g=None, free=None, keep=None, despeckle: bool | None = None) -> dict:
    """1b 후속 L 다음 H2 · H3 — 지운 판 메우기(판 중앙값 · 투명 위 글자 둘레 · 좁은 둘레 길과 판 정합 길의 harmonic). hole = 다시 칠할 자리(창 좌표).
      lama     색 = 외부 인페인팅(원래 컨셉 조각 위 — 마스크 hole + LAMA_MASK_GROW ∪ 같은 창 다른 글자 가림), 알파 = 둘레(지금 그림) 경계값 보간,
               섞임 띠 = 인페인팅 출력(판 색을 안 섞음 — 섞임 띠의 판 색이 '4' 바깥 윤곽이었다 [실측 R20261119_190059])
      harmonic 미리 곱한 색 · 알파를 함께 둘레에서 경계값 보간(F1 식 — 첫 값 매끈한 메움) — 경계와 이어져 띠가 필요 없다
    인페인팅을 못 하면 harmonic 으로 물러나 기록. → 기록(used True)."""
    import cv2
    import numpy as np
    from gen import cutout
    from gen import diagnose as dg
    y0, y1, x0, x1 = win
    hole = np.asarray(hole, bool)
    h, w = hole.shape
    pm_cur = cw_cur * aw_cur[..., None]
    n0 = int(hole.sum())
    hole = _fill_enclosed(hole)
    rec = {"used": True, "erase_method": method, "hole_px": int(hole.sum()), "shift": [0, 0], "enclosed_px": int(hole.sum()) - n0}
    if not hole.any():
        return {**rec, "used": False, "nothing": True, "reason": "nothing to erase"}
    free = np.ones((h, w), bool) if free is None else free
    lam = None
    og = other_g if other_g is not None else np.zeros((h, w), bool)
    if method == "lama":
        run_m = dg._dilate(hole, LAMA_MASK_GROW)
        if inpaint is not None:
            try:
                lam = inpaint(x0, y0, run_m, og)
            except Exception as exc:  # noqa: BLE001 — 기록하고 harmonic 으로
                rec["lama_error"] = f"{type(exc).__name__}: {exc}"[:160]
        if lam is None:
            rec["fill"] = "harmonic (lama unavailable)"
    if lam is not None:
        na = np.clip(_harmonic_fill(np.where(hole, 0.0, aw_cur)[..., None], hole)[..., 0], 0.0, 1.0)
        out_a = np.where(hole, na, aw_cur)
        gen_m = dg._dilate(hole, LAMA_MASK_GROW) | og
        b_, zb = _blend_band(hole, cutout.NOTEXT_GROW, cutout.NOTEXT_BLUR)
        blend = np.where(hole, 1.0, np.where(gen_m, b_, 0.0))
        zone = hole | (gen_m & zb)
        src = np.where(gen_m[..., None], np.clip(lam, 0, 255), cw_cur)
        pm = blend[..., None] * src * out_a[..., None] + (1 - blend)[..., None] * pm_cur
        rec["fill"] = "lama"
    else:
        if ERASE_DESPECKLE if despeckle is None else despeckle:
            # V4 — 경계 잡티 빼기: 지울 자리 밖 DESPECKLE_BAND px 띠의 작은 잡티(5 × 5 중앙값과 ΔE00 DESPECKLE_DE 넘게 다른 작은 덩어리 — 지킬 것 · 다른 글자 뺌)는
            # 경계값에서 빼고 그 자리도 메운다 [실측 R20261119_235452 배너 — 경계에 걸린 어두운 잡티가 라플라스 보간으로 번져 × 3 밝힘에서 점]
            sp = _boundary_specks(cw_cur, aw_cur, hole, (keep if keep is not None else np.zeros((h, w), bool)) | ~free)
            if sp.any():
                rec["despeckle_px"] = int(sp.sum())
                hole = hole | sp
                rec["hole_px"] = int(hole.sum())
        src = ~hole & free if int((~hole & free).sum()) >= 10 else ~hole
        fpm, fa = _smooth_fill(pm_cur, aw_cur, src)
        u = _harmonic_fill(np.dstack([pm_cur, aw_cur]), hole, init=np.dstack([fpm, fa]))
        out_a = np.where(hole, np.clip(u[..., 3], 0.0, 1.0), aw_cur)
        pm = np.where(hole[..., None], np.clip(u[..., :3], 0.0, 255.0), pm_cur)
        zone = hole
        rec.setdefault("fill", "harmonic")
    rec["background"] = _background_stats(cw_cur, aw_cur, hole, free)          # V8 — 메우기 전 그림으로(cw_cur 는 col 의 창 보기)
    _put(col, a, win, zone, np.where(out_a[..., None] > 1e-4, np.clip(pm / np.maximum(out_a, 1e-4)[..., None], 0, 255), cw_cur), out_a)
    rec.update(_zone_rec(win, zone))
    return rec


CLEAR_TAIL_MAX = 32         # V5 clear_alpha — 알파 꼬리 상한(px — 밝기 꼬리와 따로)
CLEAR_TAIL_EXCESS = 0.03    # 알파 꼬리 = 획에서 거리마다 컨셉 알파 중앙값 − 바탕 알파가 이만큼 넘는 데까지(이어진 거리만)
CLEAR_HOLE_PAD = 2          # 지울 자리 = 획 + 알파 꼬리 + 이만큼
CLEAR_PLATE_OPAQUE = 0.5    # '정답 없음' 갈래 — 판이 지울 자리 안 구조물 쪽을 이 알파 넘게(불투명) 그렸으면 그 판 픽셀을 경계로


NO_TRUTH_MIN_PX = 20        # 사용자 결정 ③(11-20) '정답 없음' — 글자 · 빛 자리 안 불투명 구조물 픽셀이 이만큼 이상이고
NO_TRUTH_STRUCT_A = 0.5     # 그 자리 컨셉 알파 중앙값 > 이것(구조물이 글자 밑으로 들어감)인데
NO_TRUTH_PLATE_A = 0.35     # 글자 없는 판 알파 중앙값 < 이것(판은 그 구조물을 거기 안 그림 — 판도 구조물 끝을 다르게 그림)


NO_TRUTH_RING = 0.2         # 획 둘레 고리 중 구조물 색 비율 하한(글자가 구조물 위에 앉음)
NO_TRUTH_PLATE_DE = 10.0    # 판이 그 구조물을 같게 그린 것으로 볼 판 ±2 px ΔE00 중앙값 상한(넘으면 판도 다르게 그림)
NO_TRUTH_SEP = 10.0        # 구조물 대표색 ↔ 글자 빛 대표색 ΔE00 이 이보다 작으면 가를 수 없음(근거 없음)
NO_TRUTH_MARGIN = 5.0       # 자리 픽셀이 구조물 대표색에 빛 대표색보다 이만큼 넘게 가까워야 구조물


def _no_truth(cw, aw, na, g0, cross_m, glow: float, win, plate_de=None) -> dict:
    """사용자 결정 ③ — 글자 밑 정답이 없는 자리(트랙 끝에 걸친 '0 %'): 글자 획 + 빛 자리 안의 '상자 밖으로 이어진 불투명 구조물' 픽셀 — 단 그 자리 밖 구조물(자리
    둘레 8 px)의 대표색에 글자 빛 대표색(획 3 ~ 6 px 고리)보다 NO_TRUTH_MARGIN 넘게 가까운 것만(이 컨셉은 글자 빛이 불투명이라 빛 고리가 막대와 한 덩어리였다 —
    빛을 구조물로 세면 이름 자리까지 '정답 없음'이 됐다 [실측 R20261120_005215 이름 — 오프라인 첫 판]) — 이 NO_TRUTH_MIN_PX 이상 · 그 자리 컨셉 알파 >
    NO_TRUTH_STRUCT_A 인데 글자 없는 판은 거기를 투명하게(< NO_TRUTH_PLATE_A) 그렸을 때: 컨셉은 글자가 덮어 구조물 끝을 모르고 판은 그 구조물을 다른 데서 끝냈다.
    → {"no_truth": 근거 + 창 상자, "_ntz": (창, 마스크)} 또는 {} — 근거가 없으면 표시 안 함(남발 막기)."""
    import numpy as np
    from core import color as color_mod
    from gen import diagnose as dg
    cross_m = np.asarray(cross_m, bool)
    zone = dg._dilate(g0, int(np.ceil(glow)) + PLATE_GLYPH_GROW)
    out_s = cross_m & ~zone & dg._dilate(zone, 8)
    halo = dg._dilate(g0, 6) & ~dg._dilate(g0, 2) & (aw > 0.3)
    if int(out_s.sum()) < NO_TRUTH_MIN_PX or int(halo.sum()) < 10:
        return {}
    pm = cw * aw[..., None]
    lab = color_mod.srgb_to_lab(pm)
    s_ref = np.median(pm[out_s], axis=0)
    d_s = color_mod.delta_e00(lab, color_mod.srgb_to_lab(s_ref.reshape(1, 1, 3)))
    # 빛 대표색 = 획 고리 중 구조물 대표색과 뚜렷이 다른 픽셀(빛이 구조물 위에 걸친 고리는 섞여 있다) — 없으면 빛 ≈ 구조물이라 가를 수 없음
    hg = halo & (d_s > 1.5 * NO_TRUTH_SEP)
    if int(hg.sum()) < 10:
        return {}
    g_ref = np.median(pm[hg], axis=0)
    sep = float(color_mod.delta_e00(color_mod.srgb_to_lab(s_ref.reshape(1, 1, 3)), color_mod.srgb_to_lab(g_ref.reshape(1, 1, 3)))[0, 0])
    if sep < NO_TRUTH_SEP:
        return {}
    d_g = color_mod.delta_e00(lab, color_mod.srgb_to_lab(g_ref.reshape(1, 1, 3)))
    struct_like = d_s < d_g - NO_TRUTH_MARGIN
    # ① 글자가 구조물 위에 앉았나 — 획 둘레 고리(1 ~ 4 px)의 NO_TRUTH_RING 이상이 구조물 색(빛만 막대에 이어진 이름 · Lv 는 고리가 빛 색)
    ring_g = dg._dilate(g0, 4) & ~dg._dilate(g0, 1) & (aw > 0.3)
    ring_frac = float(struct_like[ring_g].mean()) if int(ring_g.sum()) >= 10 else 0.0
    # ② 구조물 가장자리(구조물 ↔ 투명)가 글자 자리로 들어가나 — 자리 밖 6 px 안의 가장자리 픽셀
    edge = cross_m & dg._dilate(aw < 0.3, 1)
    edge_px = int((edge & dg._dilate(zone, 6) & ~zone).sum())
    ntz = zone & struct_like & (aw > NO_TRUTH_STRUCT_A)
    n = int(ntz.sum())
    if ring_frac < NO_TRUTH_RING or edge_px < 10 or n < NO_TRUTH_MIN_PX:
        return {}
    # ③ 판이 그 구조물을 글자 밑에서 다르게 그렸나 — 자리 안 구조물 픽셀의 판 ±2 px 이동 최소 ΔE00 중앙값 > NO_TRUTH_PLATE_DE(판이 같게 그렸으면 판이 정답)
    ca = float(np.median(aw[ntz]))
    pa = float(np.median(np.asarray(na)[ntz]))
    pde = float(np.median(plate_de[ntz])) if plate_de is not None else None
    if pde is not None and pde <= NO_TRUTH_PLATE_DE and pa > NO_TRUTH_PLATE_A:
        return {}
    bb = dg._bbox(ntz)
    return {"no_truth": {"px": n, "concept_alpha": round(ca, 3), "plate_alpha": round(pa, 3), "struct_glow_de": round(sep, 1), "ring_frac": round(ring_frac, 2),
                         "edge_px": edge_px, **({"plate_de": round(pde, 1)} if pde is not None else {}), "box_win": bb,
                         "rule": f"glyphs sit on an opaque structure that leaves the box ({ring_frac:.0%} of the stroke ring has the structure colour, its edge "
                                 f"runs under the text — {edge_px} px) and the text-free plate draws it differently there (ΔE00 {pde if pde is None else round(pde, 1)}, "
                                 f"alpha {pa:.2f}) — the structure end under the glyphs has no ground truth"},
            "_ntz": (int(win[0]), int(win[1]), int(win[2]), int(win[3]), ntz.copy())}


def _alpha_tail(aw, g0, free, prot, max_d: int) -> tuple[int, float, list]:
    """V5 — 획(g0)에서 거리마다 컨셉 알파 중앙값(다른 글자 · 지킨 구조물 뺌)이 바탕 알파(max_d 밖 고리 중앙값)보다 CLEAR_TAIL_EXCESS 넘는 거리까지 → (꼬리, 바탕 알파, 거리별 값)."""
    import numpy as np
    from gen import diagnose as dg
    ok = np.asarray(free, bool) & ~np.asarray(prot, bool)
    far = dg._dilate(g0, max_d + 6) & ~dg._dilate(g0, max_d) & ok
    bg_a = float(np.median(aw[far])) if int(far.sum()) >= 10 else float(np.percentile(aw[ok], 20)) if ok.any() else 0.0
    prev = g0
    tail, prof = 0, []
    for d in range(1, max_d + 1):
        cur = dg._dilate(g0, d)
        ring = cur & ~prev & ok
        prev = cur
        if int(ring.sum()) < 4:
            prof.append(None)
            continue
        v = float(np.median(aw[ring])) - bg_a
        prof.append(round(v, 3))
        if v > CLEAR_TAIL_EXCESS:
            tail = d
        elif d > tail + 2:
            break
    return tail, bg_a, prof


CLEAR_SCREEN = 0.5          # V5 — 판이 투명한 자리의 가림 라플라스 계수(경계값이 약 1/√이것 ≈ 1.4 px 로 사라짐)
CLEAR_BAND_DE = 10.0        # V5 — 띠 줄: Z 토막 양끝 바로 밖 불투명 픽셀 둘의 ΔE00 이 이 미만이면 양끝 사이 직선 보간(state_check.BAND_DE 와 같은 값)


def _plate_min_de(cw, aw, ntc_w, nta_w, P: int, r: int = 2):
    """컨셉(미리 곱한 색) ↔ 판(미리 곱한 색)을 ±r px 옮긴 것의 ΔE00 최소(창 크기)."""
    import numpy as np
    from core import color as color_mod
    h, w = aw.shape
    lab = color_mod.srgb_to_lab(np.clip(cw * aw[..., None], 0, 255))
    best = np.full((h, w), 1e9, np.float32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            nc, na = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w], nta_w[P + dy:P + dy + h, P + dx:P + dx + w]
            best = np.minimum(best, color_mod.delta_e00(lab, color_mod.srgb_to_lab(np.clip(nc * na[..., None], 0, 255))).astype(np.float32))
    return best
CLEAR_PLATE_ANY = 0.05      # 판 알파가 이것보다 크면 그 판 픽셀(정합 · 색조 맞춤)을 그대로 — 판이 그린 구조물 · 트랙 끝


def _clear_alpha_fill(col, a, win, cw, aw, cw_cur, aw_cur, g0, rect, others, free, glow: float, bh: float, pad_level: int = 0, plate_pad=None) -> dict:
    """V5 — 투명 바탕 글자 후보(clear_alpha, 설계 §11 '글자 지우기 다음'): 투명 바탕 위 빛 글자는 컨셉 빛이 지울 자리 밖까지 알파로 넓게 남아 lama(투명 자리에 무늬) ·
    harmonic(경계가 빛 속 — 둘레 빛 알파를 이어 뿌연 덩어리)이 예전 판보다 나빴다 [실측 R20261120_005215 파티 이름 · '0 %']. 밝기 꼬리가 아니라 **알파 꼬리**로 —
    ① 획에서 거리마다 컨셉 알파 − 바탕 알파 > CLEAR_TAIL_EXCESS 인 데까지(≤ CLEAR_TAIL_MAX + 단계) ② 지울 자리 Z = 획 + 알파 꼬리 + CLEAR_HOLE_PAD ∪ 자기 상자
    (다른 글자 획 + 2 px 만 뺌 — 겹친 상자를 통째로 빼면 두 글자 모두 그 자리를 안 지웠다 [실측 같은 run — 'Lv 100' 윗부분이 남음]) ③ 글자 없는 판(± NOTEXT_SHIFT
    정합 · 둘레 색조 맞춤)이 그린 자리(알파 > CLEAR_PLATE_ANY — 막대 윗선 · 트랙 끝: 판이 정답)는 판 픽셀 그대로, 판에 남은 글자 자국(판 자기 둘레 중앙값과 크게
    다른 획 근처 픽셀)은 빼고 ④ 판이 투명한 나머지는 미리 곱한 색 · 알파를 함께 가림 라플라스(CLEAR_SCREEN)로 — 경계(지킨 · 판 구조물 · Z 밖)에서 1 ~ 2 px 안에
    사라져 투명(지킨 구조물에 이어져 남는 알파 자리 색 = 가장 가까운 구조물 색). 처음 판(경계를 알파 꼬리 고리로 둔 라플라스 + 상자 통째 빼기)은 이름 77 · Lv 87 로
    예전 판보다 훨씬 나빴다(빛과 이어진 막대를 지켜 30 px 넘게 번짐). → 기록(used · erase_method clear_alpha · _zone)."""
    import cv2
    import numpy as np
    from core import color as color_mod
    from gen import cutout
    from gen import diagnose as dg
    y0, y1, x0, x1 = win
    h, w = aw.shape
    free = np.ones((h, w), bool) if free is None else np.asarray(free, bool)
    # 다른 글자 획(+2 px)은 지킴 — 단 내 상자 안의 획은 빼지 않는다(상자가 겹친 두 글자가 경계의 획을 서로 남의 것으로 봐 둘 다 안 지웠다 [실측 파티 HP '3/'])
    oth_g = (dg._dilate(np.asarray(others, bool), 2) & ~np.asarray(rect, bool)) if others is not None else np.zeros((h, w), bool)
    st_ = ERASE_PAD_STEP * int(pad_level)
    tail, bg_a, prof = _alpha_tail(aw, g0, free, oth_g, CLEAR_TAIL_MAX + st_)
    rec = {"used": True, "erase_method": "clear_alpha", "shift": [0, 0], "alpha_tail": tail, "bg_alpha": round(bg_a, 3), "alpha_profile": prof[:40]}
    Z = dg._dilate(g0, max(tail, int(np.ceil(glow))) + CLEAR_HOLE_PAD + st_) | np.asarray(rect, bool)
    Z = _fill_enclosed(Z & ~oth_g) & ~oth_g
    if not Z.any():
        return {**rec, "used": False, "nothing": True, "reason": "nothing to erase"}
    pm_cur = cw_cur * aw_cur[..., None]
    vals = np.dstack([pm_cur, aw_cur])
    fixed = np.zeros((h, w), bool)
    if plate_pad is not None:
        P = cutout.NOTEXT_SHIFT
        ntc_w, nta_w = plate_pad
        sh = cutout._notext_shift(cw, aw, Z, dg._dilate(Z, 3), ntc_w, nta_w, strokes=g0)
        dx, dy = sh.get("shift") or (0, 0)
        if sh.get("diff") is None or sh["diff"] > cutout.NOTEXT_MAX_DIFF:
            dx, dy = 0, 0
        # 판에도 같은 것이 있는 불투명 컨셉 픽셀(±2 px 이동 최소 차 — 막대 띠 · 윗선 자체)은 컨셉 그대로(Z 에서 뺌) — 판 띠는 조금 다르게 그려 Z 원 경계가 띠를 가르며
        # 어두운 호가 났다 [실측 파티 HP 숫자 — 오프라인 둘째 판]. 글자 빛에 물든 띠 픽셀(판과 다름)만 판으로
        nc, na = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w], nta_w[P + dy:P + dy + h, P + dx:P + dx + w]
        nc_t, tone = _tone_plane(cw, aw, nc, na, Z)
        # 판에 남은 글자 자국(codex 판이 못 지운 획 — 판 자기 둘레 중앙값과 INK_MIN 넘게 다른 획 근처 픽셀, 글자보다 긴 선 뺌) — 그 자리는 판을 안 씀
        pm_n = np.clip(nc * na[..., None], 0, 255).astype(np.uint8)
        k = max(5, int(round(bh)) | 1)
        pt = (np.abs(pm_n.astype(float) - cv2.medianBlur(pm_n, min(k, 255)).astype(float)).max(axis=2) > dg.INK_MIN) & dg._dilate(g0, int(np.ceil(glow)) + 4)
        p8 = pt.astype(np.uint8)
        lh = cv2.morphologyEx(p8, cv2.MORPH_OPEN, np.ones((1, max(3, int(1.5 * bh))), np.uint8)) > 0
        lv = cv2.morphologyEx(p8, cv2.MORPH_OPEN, np.ones((max(3, int(1.05 * bh)), 1), np.uint8)) > 0
        marks = dg._dilate(pt & ~dg._dilate(lh | lv, 1), 1)
        # 판 픽셀은 지울 자리 밖으로 이어진 판 구조물(막대 · 트랙 — 판 알파 > 0.3 덩어리 중 Z 밖에도 있는 것)만 — Z 안에 갇힌 판 덩어리는 codex 판이 덜 지운 글자
        # [실측 파티 이름 · Lv — 판에 남은 'Lv 지크' 를 판 픽셀로 옮겨 유령 글자]
        n_p, lab_p = cv2.connectedComponents((na > 0.3).astype(np.uint8), connectivity=8)
        ids_p = np.unique(lab_p[(lab_p > 0) & ~Z])
        pcross = np.isin(lab_p, ids_p[ids_p > 0]) if len(ids_p) else np.zeros((h, w), bool)
        fixed = Z & dg._dilate(pcross, 1) & (na > CLEAR_PLATE_ANY) & ~marks
        vals = np.where(fixed[..., None], np.dstack([nc_t * na[..., None], na]), vals)
        rec.update(shift=[int(dx), int(dy)], plate_px=int(fixed.sum()), plate_marks_px=int((Z & marks).sum()), **({"tone": tone} if tone is not None else {}))
    # 띠 줄 — Z 를 가로지르는 줄 토막의 양끝 바로 밖이 둘 다 불투명이고 색이 같으면(ΔE00 < CLEAR_BAND_DE) 그 토막은 양끝 사이 직선 보간(미리 곱한 색 · 알파 — 진단 (나)
    # 띠 설명과 같은 뜻): 글자 빛에 물든 막대 윗선 · 띠를 곧게 잇는다. 판 띠 · 남김 · 사라짐 보간을 섞으면 띠가 거칠게 끊겼다 [실측 파티 HP 숫자 · 이름 — 오프라인 다섯째 판]
    band = np.zeros((h, w), bool)
    pm_b, a_b = pm_cur, aw_cur
    lab_b = color_mod.srgb_to_lab(np.clip(pm_b, 0, 255))
    for yy in np.nonzero(Z.any(axis=1))[0]:
        row = Z[yy]
        xs = np.nonzero(np.diff(np.concatenate([[0], row.astype(np.int8), [0]])))[0]
        for xa, xb in zip(xs[0::2], xs[1::2]):
            L, R = xa - 1, xb
            if L < 0 or R >= w or a_b[yy, L] <= 0.5 or a_b[yy, R] <= 0.5:
                continue
            if float(color_mod.delta_e00(lab_b[yy, L][None, None], lab_b[yy, R][None, None])[0, 0]) >= CLEAR_BAND_DE:
                continue
            t_ = (np.arange(xa, xb) - L) / float(R - L)
            vals[yy, xa:xb, :3] = pm_b[yy, L][None, :] * (1 - t_)[:, None] + pm_b[yy, R][None, :] * t_[:, None]
            vals[yy, xa:xb, 3] = a_b[yy, L] * (1 - t_) + a_b[yy, R] * t_
            band[yy, xa:xb] = True
    if band.any():
        fixed = fixed | band
        rec["band_px"] = int(band.sum())
    hole_h = Z & ~fixed
    u = _harmonic_fill(vals, hole_h, init=np.zeros_like(vals), screen=CLEAR_SCREEN) if hole_h.any() else vals
    out_a = np.where(Z, np.clip(u[..., 3], 0.0, 1.0), aw_cur)
    pm = np.where(Z[..., None], np.clip(u[..., :3], 0.0, 255.0), pm_cur)
    rec["hole_px"] = int(Z.sum())
    rec["background"] = _background_stats(cw_cur, aw_cur, Z, free)
    _put(col, a, win, Z, np.where(out_a[..., None] > 1e-4, np.clip(pm / np.maximum(out_a, 1e-4)[..., None], 0, 255), cw_cur), out_a)
    rec.update(_zone_rec(win, Z))
    return rec


def _fill_text_item(col, a, ntc_pad, nta_pad, item: dict, whole: bool = False, orig=None, others=None, inpaint=None) -> dict:
    """글자 한 자리 메움 — erase 표시가 없으면(또는 뺀 사본이면) 예전 좁은 길, 있으면 erase_method(lama · harmonic)로(_plate_item_fill 안 — 판 정합 길 ·
    판 중앙값 · 투명 위 글자 둘레 · 좁은 둘레 길 모두). 고르기는 refine 끝(_gate_erase_choice)."""
    return _plate_item_fill(col, a, ntc_pad, nta_pad, item, whole=whole, orig=orig, others=others, inpaint=inpaint)


def _plate_item_fill(col, a, ntc_pad, nta_pad, item: dict, whole: bool = False, orig=None, others=None, inpaint=None) -> dict:
    """정적 판의 한 글자(또는 게이지 막대) 자리를 글자 없는 판 픽셀로(제자리에서 고침) → 기록. used False 면 고치지 않음(이유).
    바꿀 자리 = 컨셉 ↔ 판이 다른 글자 획(gen/diagnose 와 같은 정의 — 가는 선 · 상자 밖 덩어리 · 가는 호 빼기) + PLATE_GLYPH_GROW + 빛 —
    글자 상자 사각형 전체를 바꾸면 codex 판이 몇 px 다르게 다시 그린 배지 테두리가 사각형 가장자리에서 어긋나 '배지 양옆 선'이 됐다
    [실측 J-a 오프라인 R20261117_154442 — E · T · R 배지 양옆 국소 ΔE00 최대 17.6]. whole(OCR 이 자국을 잡은 뒤) · 게이지 막대는 상자째.
    정합 = 획 둘레로 ±NOTEXT_SHIFT(cutout._notext_shift), 판 알파 수준 맞춤(_notext_alpha_gain) · 흐린 경계 섞기는 cutout.compose 와 같다.
    1b 후속 L 다음 — 판정(획 · 글자색 · 구조물 · 투명 위 글자 · 판 정합 · 메움 원천)은 모두 원래 컨셉(orig — 앞 글자 메움 전)에서 하고 결과만 col · a 에 쓴다:
    앞 글자 메움이 바꾼 그림으로 획을 찾으면 순서에 따라 결과가 갈렸다 [실측 L 다음 오프라인 단색 R20261118_124503 — 빛 여백으로 넓은 '4.2' 상자의 메움이 '2/4' 의
    '4' 를 먹고 발 끝만 남겨, '2/4' 는 남은 발을 작은 덩어리로 버려 텍스처 잔상 12 px(진단 E1 '4' 밑 잔상)]. others = 같은 판 · 조각의 다른 글자 상자 — 그 글자 몫
    획은 빼고(_drop_other_glyphs), 그 상자 안은 메움 원천 · 둘레에서 뺀다."""
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
    cw_cur, aw_cur = col[y0:y1, x0:x1], a[y0:y1, x0:x1]
    # 판정 · 원천 = 원래 컨셉(cw · aw), 결과 섞기 = 지금 그림(cw_cur · aw_cur)
    cw, aw = (orig[0][y0:y1, x0:x1], orig[1][y0:y1, x0:x1]) if orig is not None else (cw_cur.copy(), aw_cur.copy())
    ntc_w, nta_w = ntc_pad[y0:y1 + 2 * P, x0:x1 + 2 * P], nta_pad[y0:y1 + 2 * P, x0:x1 + 2 * P]
    h, w = aw.shape
    oth, oth_list = _other_text_mask(others, x0, y0, h, w) if not (item.get("gauge") or whole) else (None, [])
    free = ~dg._dilate(oth, 2) if oth is not None else np.ones((h, w), bool)
    own = np.zeros((h, w), bool)
    own[max(0, int(by) - y0):min(h, int(np.ceil(by + bh)) - y0), max(0, int(bx) - x0):min(w, int(np.ceil(bx + bw)) - x0)] = True
    rect = dg._dilate(own, 2)
    # 1b 후속 L 다음 — 글자 지우기 다음: V6 반복 보강 단계(erase_pad — 여백 · 꼬리 + ERASE_PAD_STEP × 단계) · V7 컨셉 OCR 상자(ocr_boxes — 이 글자 상자와 겹친 검출,
    # 다른 글자 상자 뺌)를 '지울 수 있는 범위'에 합침(획 찾기 범위 · rect_e — 상자째 지우지는 않음). 지우는 글자만
    erase_any = bool(item.get("erase")) and not (item.get("gauge") or whole)
    ca_only = erase_any and item.get("erase_method") == "clear_alpha"     # V5 후보 — 투명 바탕 길에서만(아니면 예전 판과 같게)
    pad_lv = int(item.get("erase_pad") or 0) if erase_any else 0
    ocr_own = np.zeros((h, w), bool)
    if erase_any and item.get("ocr_boxes"):
        for b_ in item["ocr_boxes"]:
            ocr_own |= dg._box_mask((h, w), [float(b_[0]) - x0, float(b_[1]) - y0, float(b_[2]), float(b_[3])])
        if oth is not None:
            ocr_own &= ~dg._dilate(oth, 2)
    ocr_r = dg._dilate(ocr_own, OCR_BOX_PAD) if ocr_own.any() else ocr_own
    own_x = own | ocr_own
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
        _put(col, a, (y0, y1, x0, x1), hole, nc, na)
        return {"used": True, "shift": [int(dx), int(dy)], "diff": sh.get("diff"), "hole_px": int(hole.sum()), "whole": True, "mask": "full gauge track",
                **_zone_rec((y0, y1, x0, x1), hole)}

    near = None
    if not (item.get("gauge") or whole):
        # 글자색에 가까운 픽셀만 획 — codex 판이 배지를 몇 px 크게 다시 그려 테두리 어긋남 덩어리도 '판과 다른 픽셀'이라 배지 전체가 판으로 바뀌었다
        # [실측 J-a 오프라인 154442 T 배지 — 획 상자 74 × 72, 'T' 는 30 × 36]. 글자색은 spec 이 아니라 컨셉에서 — 자기 상자 안에서 판과 가장 많이 다른
        # 픽셀(위 · 아래 반의 중앙값 — 그라데이션)로 잰다: analyze 색 파생이 '점프' 를 남색으로 잘못 잡자 띠의 어두운 면이 '글자색 근처'가 돼 판으로
        # 바뀌었다 [실측 J R20261117_174247 — 글자 오른쪽 국소 ΔE00 17.6]
        from core import color as color_mod
        d0 = np.abs(cw * aw[..., None] - ntc_w[P:P + h, P:P + w] * nta_w[P:P + h, P:P + w][..., None]).max(axis=2)
        strong = _drop_other_glyphs(own & (d0 > dg.INK_MIN), own, oth_list)
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

            def near_of(cs):
                return np.min([color_mod.delta_e00(lab, color_mod.srgb_to_lab(np.asarray(c, float).reshape(1, 1, 3))) for c in cs], axis=0) < PLATE_TEXT_DE
            near = near_of(cols)
            spec_cols = [np.asarray(c, float) for c in (item.get("colors") or [])]
            if spec_cols:
                # 1b 후속 L 다음 — 잰 글자색이 띠 · 바탕 색이면(그 색 근처 픽셀이 상자 테두리에 닿는 큰 면) 사양 글자색이 글자 같을 때 그것으로 [실측 controls_alpha
                # R20261119_004119 '돌진 공격' — 새 analyze 상자에서 획 후보 거르기가 띠 조각만 남겨 글자색 (44, 136, 192) → 글자가 텍스처에 남아 이중 글자].
                # 반대(사양색이 띠의 어두운 면 — J '점프')면 잰 색 그대로
                ns = near_of(spec_cols)
                gm_, gs_ = _glyph_like(near & own, own), _glyph_like(ns & own, own)
                if gm_ < GLYPH_LIKE_MIN and gs_ >= gm_ + GLYPH_LIKE_GAIN:
                    near = ns

    def plate_text(nc, na):
        """1b 후속 L-3b — 판에 남은 글자 자국(codex 판이 못 지운 획): 판 픽셀이 판 자기 둘레(미디언 — 글자 높이 크기 창)와 INK_MIN 넘게 다름 · 글자 상자 근처만.
        다시 그린 자국은 색이 컨셉 글자색과 달라(더 밝게) 글자색으로는 못 잡았다 [실측 L run R20261118_115506 단색 '2/']. 글자색 근처가 없으면 None."""
        if near is None:
            return None
        pm_n = np.clip(np.asarray(nc, float) * np.asarray(na, float)[..., None], 0, 255).astype(np.uint8)
        k = max(5, int(round(bh)) | 1)
        med_n = cv2.medianBlur(pm_n, min(k, 255)).astype(float)
        pt = (np.abs(pm_n.astype(float) - med_n).max(axis=2) > dg.INK_MIN) & dg._dilate(own, int(round(e)))
        # 1b 후속 L 다음 — 글자보다 긴 가로 · 세로 선(판의 테두리 금선 등 구조물)은 판에 남은 글자 자국이 아니다 — 판 정합이 1 px 어긋나면 금선이 '자국'이 돼
        # 획 근처 금선 자리를 둘레 메움으로 바꿔 혹 · 끊김 [실측 L 다음 오프라인 단색 R20261118_124503 '2/4' — 이동 (0, −1)]
        p8 = pt.astype(np.uint8)
        lh = cv2.morphologyEx(p8, cv2.MORPH_OPEN, np.ones((1, max(3, int(1.5 * bh))), np.uint8)) > 0
        lv = cv2.morphologyEx(p8, cv2.MORPH_OPEN, np.ones((max(3, int(1.05 * bh)), 1), np.uint8)) > 0
        return pt & ~dg._dilate(lh | lv, 1) if (lh.any() or lv.any()) else pt

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
        cand = (dg._dilate(own, int(round(e))) | ocr_r) & diff          # V7 — 컨셉 OCR 상자(+ OCR_BOX_PAD)도 획 찾기 범위(지우는 글자만 — 없으면 빈 마스크)
        if near is not None:
            cand &= near
            # 판에도 있는 구조물(장식 · 테두리선 — 판이 몇 px 어긋나고 밝기가 달라도)은 획이 아니다 [실측 L run R20261118_115506 단색 — 패널 폭 '2/4' 상자 안
            # 모서리 장식 하이라이트 · 아래 금선이 글자색 근처라 획으로 잡혀 얼룩]
            cand &= ~same_struct
        return dg._filter_glyph_parts(dg._drop_small(_drop_other_glyphs(cand, own_x, oth_list)), own_x)
    same_struct = _plate_same(cw, aw, ntc_w, nta_w, P, ratio=False) & (aw > 0.5) if near is not None else None

    def other_lama():
        """인페인팅 원천에서 가릴 같은 창 다른 글자 획(+ 빛 LAMA_OTHER_GROW) — 그 빛을 이 자리로 이어 그리지 않게."""
        if oth is None or near is None:
            return None
        return dg._dilate((d0 > dg.INK_MIN) & dg._dilate(oth, 3) & ~dg._dilate(g0, 2), LAMA_OTHER_GROW)
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
        cross_m = np.isin(lab_o, cross[cross > 0]) if len(cross) else np.zeros_like(rect)       # 상자 밖으로 이어진 불투명 구조물(넓히기 전 — V5 '정답 없음' 근거)
        protect = dg._dilate(cross_m, 3) if len(cross) else np.zeros_like(rect)
        protect_raw = protect.copy()
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
        # 1b 후속 L 다음 — 둘레 고리 · 메움 원천에서 다른 글자 상자(+2 px)는 뺀다: 이웃 글자 빛(컨셉 알파 0.7 ~ 0.9)이 고리 중앙값이 돼 투명 위 '100' 자리를
        # 불투명 남색 상자로 메웠다 [실측 L 다음 오프라인 파티 R20261118_130201 — LevelText 고리 알파 0.765, 그 상자 틈을 글자로 재 글자 맞춤이 검정 · 52]
        if int((r0 & free).sum()) >= 20:
            r0 &= free
        clear0 = float(np.median(aw[r0])) if int(r0.sum()) >= 20 else None

        def neigh_fill(why: str, plate_fill: bool = False, **extra) -> dict:
            hh, prot = h0, protect
            if plate_fill:
                # 판 메움 길은 글자 · 빛 반경 안에서 길고 가는 선(막대 윗선 — 판이 1 px 어긋나 다시 그림, J · K)만 지킨다: 컨셉 빛으로 상자 밖 트랙과 이어진 글자 빛 고리
                # (글자색에서 먼 주황 빛)가 '판도 밝다'(_plate_same 밝기 비)로 구조물이 돼 텍스처에 남았다 [실측 L 다음 오프라인 파티 130201 '0 %'] — 그 밑 트랙은
                # 판이 그린 트랙 끝(중앙값)으로
                # 빛 자리 = 획 + 빛 크기 + 5 px, 그 밖 빛 크기 × 2 + 6 px 까지는 판에 그만큼 밝은 것이 없는 픽셀(투명 위 빛 끝)만 — 컨셉 빛은 분석 빛 크기보다
                # 넓어 아래 끝이 막대 윗선 위 어두운 이빨로 남았고 [실측 같은 run HP 숫자], 바깥 고리를 '판과 다른 픽셀' 전부로 넓히자 '0 %' 둘레 트랙까지 판
                # 트랙으로 바뀌어 '0' 모양 자국이 났다
                gi = int(np.ceil(glow))
                zone = dg._dilate(g0, gi + PLATE_GLYPH_GROW + 2) | (dg._dilate(g0, 2 * gi + 6) & ~(_plate_same(cw, aw, ntc_w, nta_w, P) & (aw > 0.5)))
                # 판과 ±2 px 안에서 같은 구조물(사선 화살 끝 등 가는 선 판정 밖)도 지킨다 [실측 같은 run HP 최대치 오른쪽 화살 끝 자국]
                keep = dg._dilate(_thin_lines(cw, aw, bh), 1) | (_plate_same(cw, aw, ntc_w, nta_w, P, ratio=False) & (aw > 0.5))
                prot = protect & ~(zone & ~keep)
                hh = rect & ~prot
            if item.get("erase_method") in ERASE_METHODS:
                # 1b 후속 L 다음 H3 — 지우는 글자: 같은 자리(판 중앙값 길이면 판과 같은 구조물 중 글자 · 빛 자리를 가로지르는 것만 지킴)를 lama · harmonic 으로.
                # 판 중앙값은 '0' 테두리를 남기고 안쪽을 어둡게 비웠다 [실측 R20261119_003127 파티 '0 %' — S4 34.7 ~ 50]
                near_g = dg._dilate(g0, ERASE_PAD + ERASE_PAD_STEP * pad_lv)      # 상자 밖으로 나간 획 둘레도(_erase_zone 과 같은 ERASE_PAD — V6 단계마다 넓힘)
                prot_e = prot
                if plate_fill:
                    reach = dg._dilate(g0, int(np.ceil(glow)) + PLATE_GLYPH_GROW + 2 + ERASE_PAD_STEP * pad_lv)
                    keep_e = _struct_keep(cw, aw, _plate_same(cw, aw, ntc_w, nta_w, P, ratio=False) & (aw > 0.5), g0, reach, bh, free)
                    prot_e = protect & ~(zone & ~keep_e)
                hh_e = (rect | near_g) & ~prot_e
                nt_ = _no_truth(cw, aw, nta_w[P:P + h, P:P + w], g0, cross_m, glow, (y0, y1, x0, x1),
                                plate_de=_plate_min_de(cw, aw, ntc_w, nta_w, P)) if plate_fill else {}
                if ca_only:
                    # V5 — 투명 바탕 글자 후보(clear_alpha): 알파 꼬리로 자리 · 판이 그린 자리는 판 · 나머지는 가림 라플라스(아래 _clear_alpha_fill)
                    other_ca = ((d0 > dg.INK_MIN) & dg._dilate(oth, 2) & ~dg._dilate(g0, 2)) if oth is not None else None
                    return {**_clear_alpha_fill(col, a, (y0, y1, x0, x1), cw, aw, cw_cur, aw_cur, g0, rect | near_g, other_ca, free, glow, bh,
                                                pad_level=pad_lv, plate_pad=(ntc_w, nta_w)),
                            "alpha_from": why, "path": "plate_median" if plate_fill else "clear", **extra, **nt_}
                return {**_erase_fill(col, a, (y0, y1, x0, x1), cw_cur, aw_cur, hh_e, item["erase_method"], inpaint=inpaint, other_g=other_lama(), free=free,
                                      keep=prot_e),
                        "alpha_from": why, "path": "plate_median" if plate_fill else "clear", **extra, **nt_}
            blend, zone_b = _blend_band(hh, cutout.NOTEXT_GROW, cutout.NOTEXT_BLUR)
            blend = np.clip(np.where(hh, 1.0, np.where(prot, 0.0, blend)), 0.0, 1.0)     # 지킨 구조물은 흐린 경계로도 안 섞음(L-3b)
            zone_b = hh | (zone_b & ~prot)
            if plate_fill:
                # 1b 후속 L 다음 — 판만 투명하다고 본 글자(컨셉 둘레는 빛 · 이웃 막대로 불투명): 둘레 컨셉으로 메우면 그 막대 색이 상자를 덮었다 [실측 L 다음 오프라인
                # 파티 130201 NameText — 고리 알파 0.99, 이름 상자가 HP 막대 초록]. 판(이동 0)을 글자 높이 반 크기 중앙값으로 — 판에 남은 글자 자국 · 잔상은 뭉개고
                # 투명 · 옅은 막대 빛만 남는다(알파 이득 없음 — 유령 숫자 K 교훈)
                k = max(5, int(round(0.5 * bh)) | 1)
                pm8 = np.clip(nta_w[P:P + h, P:P + w][..., None] * ntc_w[P:P + h, P:P + w], 0, 255).astype(np.uint8)
                fpm = cv2.medianBlur(pm8, min(k, 255)).astype(float)
                fa = cv2.medianBlur(np.clip(nta_w[P:P + h, P:P + w] * 255, 0, 255).astype(np.uint8), min(k, 255)).astype(float) / 255.0
            else:
                # 원천 = 둘레 대표(미리 곱한 색 중앙값)에 가까운 픽셀만 — 줄 보간이 이웃 장식의 밝은 가장자리를 끌어와 회색 줄무늬가 됐다
                # [실측 J R20261117_205334 파티 HUD 이름 — 초상화 테두리 가장자리]
                pm_w = cw * aw[..., None]
                med = np.median(pm_w[r0], axis=0) if int(r0.sum()) else np.zeros(3)
                similar = np.abs(pm_w - med).max(axis=2) < PLATE_FILL_SOURCE_DIFF
                src_ok = ~h0 & (similar if int((similar & r0).sum()) >= 10 else True)
                if int((src_ok & free).sum()) >= 10:
                    src_ok &= free
                # 1b 후속 L-3b — 매끈한 메움(원천 가우스 가중 평균). 줄 보간은 줄마다 다른 양끝 원천을 이어 가로 줄무늬를 남겼다 [실측 K R20261118_092315 이름]
                fpm, fa = _smooth_fill(pm_w, aw, src_ok)
            out_a = blend * fa + (1 - blend) * aw_cur
            pm = blend[..., None] * fpm + (1 - blend)[..., None] * (cw_cur * aw_cur[..., None])
            _put(col, a, (y0, y1, x0, x1), zone_b, np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw_cur), out_a)
            return {"used": True, "shift": [0, 0], "hole_px": int(hh.sum()), "whole": False, "alpha_from": why, "path": "plate_median" if plate_fill else "clear",
                    **extra, **_zone_rec((y0, y1, x0, x1), zone_b)}
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
            if int((ring_g & free).sum()) >= 20:
                ring_g &= free
            clear_g = float(np.median(aw[ring_g])) if int(ring_g.sum()) >= 20 else 1.0
            # 1b 후속 L 다음 — 글자 없는 판이 글자 · 빛 자리(획 + 빛 반경, 지킨 구조물 빼고)를 투명하게 그렸으면 그것도 투명 위 글자: 컨셉 빛이 분석 빛 크기보다
            # 넓으면 획 둘레 고리도 빛 속이라 불투명으로 재 좁은 메움으로 갔고, 남은 빛 번짐 · 이웃 원천이 이름 둘레 회청 · 초록 얼룩이 됐다
            # [실측 L 다음 오프라인 파티 130201 NameText — 고리 알파 ≥ 0.35, 판 알파는 그 자리 거의 0]. 판 픽셀은 여기서도 안 쓴다(알파 판정만)
            zone_g = dg._dilate(g0, rg) & rect & ~protect
            plate_g = float(np.median(na0[zone_g])) if int(zone_g.sum()) >= 20 else 1.0
            zg = dg._dilate(g0, rg) & rect
            struct_g = float((protect_raw & zg).sum()) / max(1, int(zg.sum()))
            meas = {"alpha_mismatch": round(mism0, 3), "ring_alpha": round(clear0, 3), "glyph_ring_alpha": round(clear_g, 3), "plate_zone_alpha": round(plate_g, 3),
                    "struct_overlap": round(struct_g, 3)}
            concept_clear = clear_g < PLATE_CLEAR_ALPHA or (mism0 > PLATE_ALPHA_MISMATCH and clear0 < PLATE_CLEAR_ALPHA)
            if item.get("erase") and concept_clear and clear_g >= PLATE_CLEAR_ALPHA:
                # 1b 후속 L 다음 G1 — 지우는 글자는 획 둘레(빛 반경 밖)가 불투명하면 상자 둘레 알파로 '투명 위 글자'라 하지 않는다: analyze 가 빛 여백으로 상자를
                # 패널 밖까지 넓히면 상자 둘레가 투명이라 둘레 메움 길로 가 획을 놓쳤다 [실측 R20261119_143110 '4.2' — 상자 331 px, E1 잔상 8 · 오프라인 잔상 250 px]
                concept_clear = False
                meas["erase_opaque_glyph_ring"] = True
            # 판이 글자 · 빛 자리를 투명하게 그렸고, 컨셉 둘레가 불투명하거나(빛 · 이웃 막대 — 둘레 메움이 그 색이 됨) 글자 · 빛 자리가 상자 밖으로 이어진 불투명
            # 구조물(트랙 · 막대 — 빛으로 이어짐)과 겹치면 판(중앙값)으로 — 트랙 끝에 걸친 '0 %' 처럼 글자 밑 정답이 없는 자리는 판이 그린 트랙 끝이 유일한 근거.
            # 둘레가 투명하고 구조물과 안 겹치면 예전대로 둘레 컨셉 — 판(codex)이 컨셉의 옅은 바탕 빛(알파 0.1)까지 지운 단색 '오의 불가' 를 투명으로 만들었다
            # [실측 L 다음 오프라인 단색 120715 — 글자 구역 바탕 국소 최대 9.9 → 12.9]. 판이 거기를 불투명하게 그렸으면(J — codex 판의 투명 위 '오의 불가') 둘레 컨셉
            if plate_g < PLATE_CLEAR_ALPHA and (not concept_clear or struct_g >= PLATE_STRUCT_OVERLAP):
                return neigh_fill("text-free concept median (glyph-sized) — the text-free concept is transparent under the text", plate_fill=True, **meas)
            if concept_clear:
                return neigh_fill("concept neighbourhood — text on a (nearly) transparent concept (the text-free concept is not used)", **meas)
    else:
        neigh_fill = None
    ca_na = None
    if ca_only:
        # V5 clear_alpha 후보는 투명 바탕 길(위 neigh_fill)에서만 — 판 정합 · 좁은 둘레 길(불투명 바탕)에선 예전 판(좁은 메움)과 같게
        item = {k: v for k, v in item.items() if k not in ("erase", "erase_method", "erase_pad", "ocr_boxes")}
        ca_na = "n/a — not text on a transparent background"
        ocr_r, own_x = np.zeros_like(ocr_r), own                  # glyph_of 가 늦게 묶어 읽음 — 예전 판과 같은 획 찾기 범위
        g0 = glyph_of(ntc_w[P:P + h, P:P + w], nta_w[P:P + h, P:P + w])
    # 빛 글자는 정합 둘레를 빛 반경 밖으로 — 둘레가 빛 번짐 안이면 codex 판(빛까지 지움)과 늘 25 ~ 28 차이로 정합 실패였다
    # [실측 J R20261117_210351 파티 HUD 이름 · HP 숫자 — 둘레 보간으로 물러나 컨셉 획 측정이 깨짐]
    gr = int(np.ceil(glow))
    # 정합은 원래 컨셉에 대고(orig) — 앞 글자를 먼저 메운 결과가 둘레를 바꿔 같은 글자가 순서에 따라 정합 11 ↔ 30 으로 갈렸다 [실측 L 오프라인 092315 '0 %']
    sh = cutout._notext_shift(cw, aw, dg._dilate(g0, gr) if gr else g0, dg._dilate(g0, 3 + gr), ntc_w, nta_w, strokes=g0)
    if sh.get("diff") is None or sh["diff"] > cutout.NOTEXT_MAX_DIFF:
        if neigh_fill is not None and h0.any() and int(r0.sum()) >= 20:
            # 정합이 안 되면 둘레 컨셉으로 — 단 좁은 자리만(획 + 안티앨리어싱 + 획에 이어진 실제 빛 픽셀, 판 정합 길의 K (나) 와 같은 범위) · 매끈한 가우스 가중
            # 메움. 글자 상자 전체를 줄 보간으로 메우자 가로 줄무늬가 생기고 그 줄무늬가 컨셉 획 측정을 오염시켜 글자색까지 어둡게 맞췄다
            # [실측 K R20261118_092315 파티 HUD 이름 — 회청색 + 줄무늬 · 측정 불가]. 예전 물러남(cutout.compose 줄 상자 + 가로 여유)은 이웃 장식까지 팠다
            # [실측 J R20261117_204115 — 초상화 테두리 오른쪽 8 × 33 구멍]
            if item.get("erase_method") in ERASE_METHODS:
                # 1b 후속 L 다음 H3 — 지우는 글자: 획 + 빛 + 5 px(가로지르는 구조물 · 길고 가는 선 지킴)를 lama · harmonic 으로
                st_ = ERASE_PAD_STEP * pad_lv
                reach = dg._dilate(g0, max(ERASE_PAD, int(np.ceil(glow)) + PLATE_GLYPH_GROW + 2) + st_)
                keep_n = _struct_keep(cw, aw, same_struct, g0, reach, bh, free)
                return {**_erase_fill(col, a, (y0, y1, x0, x1), cw_cur, aw_cur, reach & (rect | dg._dilate(g0, ERASE_PAD + st_)) & ~keep_n, item["erase_method"],
                                      inpaint=inpaint, other_g=other_lama(), free=free, keep=keep_n), "path": "narrow", "line_up_diff": sh.get("diff")}
            return {**_narrow_neigh_fill(col, a, (y0, y1, x0, x1), cw_cur, aw_cur, g0, rect, glow, bh,
                                         f"concept neighbourhood around the glyphs — the text-free concept does not line up (ring diff {sh.get('diff')})",
                                         orig_w=(cw, aw), oth=oth, line_up_diff=sh.get("diff")), "path": "narrow",
                    **({"clear_alpha": ca_na} if ca_na else {})}
        return {"used": False, "reason": f"text-free concept does not line up here (ring diff {sh.get('diff')}, ring {sh.get('ring_px')} px)", **sh}
    dx, dy = sh["shift"]
    nc, na = ntc_w[P + dy:P + dy + h, P + dx:P + dx + w], nta_w[P + dy:P + dy + h, P + dx:P + dx + w]
    glyph = glyph_of(nc, na) | (g0 if not (item.get("gauge") or whole) else False)
    tone = None
    nc_raw = nc
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
            if not item.get("erase"):
                hole &= ~(same_struct & ~dg._dilate(glyph, 1))
            # 글자 지우기 마감 H2 — 지우는 글자는 여기서 안 지키고 아래 _erase_zone 의 지킴(둘레와 ΔE00 ERASE_STRUCT_DE 넘게 다르고 글자 · 빛 자리를 가로지르는 구조물 ·
            # 가는 선)만 뺀다: '판에도 있는 픽셀'은 평평한 바탕까지 한 덩어리라 그대로 지키면 자리 안에 갇힌 codex 판의 덜 지운 글자 흔적이 '4' 안쪽 윤곽으로
            # [실측 R20261119_190059 — 안쪽 윤곽 385 px 전부 이 지킴], 바탕 잡티가 harmonic 메움의 경계값(검은 점)으로 남았다 [실측 오프라인 같은 run 배너]
    erec: dict = {}
    if item.get("erase") and not (item.get("gauge") or whole):
        # 1b 후속 L 다음 G1 — 글자 흔적 지우기: 빛 꼬리까지 넓히고 색조 평면을 넓힌 자리 둘레로 다시 맞춘다(다른 글자 상자 · 판에도 있는 구조물은 그대로)
        # 다른 글자는 상자가 아니라 그 획(+2 px)만 지킨다 — 빛 여백으로 넓은 상자끼리 겹쳐('4.2' ↔ '체인' · '2/4') 상자째 빼면 그 안의 이 글자 빛이 남았다
        # [실측 오프라인 R20261119_144231 — '4' · '2' 아래 끝 밝은 덩어리]
        other_s = ((d0 > dg.INK_MIN) & dg._dilate(oth, 2) & ~dg._dilate(glyph, 2)) if oth is not None else np.zeros_like(hole)
        hole, erec = _erase_zone(cw, aw, nc, na, glyph, hole, own, glow, dg._dilate(other_s, 2), same=same_struct, bh=bh, pad_level=pad_lv, ocr_r=ocr_r,
                                 oth_box=oth)
        if erec.get("_struct") is not None:
            # 좁은 자리에서도 가로지르는 뚜렷한 구조물(금선 등)은 컨셉 그대로 — 가는 선 지킴은 넓힌 자리에서만(글자 빛 아랫줄이 '가는 선'으로 남았다 [실측 오프라인 190059 '2'])
            erec["struct_kept_px"] = int((hole & erec["_struct"]).sum())
            hole &= ~erec["_struct"]
        n0 = int(hole.sum())
        hole = _fill_enclosed(hole)
        erec["enclosed_px"] = int(hole.sum()) - n0
        nc2, tone2 = _tone_plane(cw, aw, nc_raw, na, hole)
        if tone2 is not None:
            nc, tone = nc2, tone2
        if item.get("erase_method") == "harmonic":
            # 글자 지우기 마감 — 판 정합 길의 harmonic 후보: 넓힌 자리를 둘레(지금 그림)에서 경계값 보간(판 색 · 인페인팅 없음)
            r_h = _erase_fill(col, a, (y0, y1, x0, x1), cw_cur, aw_cur, hole, "harmonic", free=free, keep=erec.get("_keep"))
            return {**r_h, "shift": [dx, dy], "diff": sh["diff"], "path": "plate", **{k: v for k, v in erec.items() if not k.startswith("_") and k != "background"}}
    glyph &= hole
    if inpaint is not None and item.get("erase") and not (item.get("gauge") or whole):
        # 1b 후속 L 다음 G2 (가) — 외부 인페인팅(LaMa): 넓힌 자리 색을 둘레 컨셉 결 · 장식에서 이어 그린다(같은 창의 다른 글자 획도 가려 원천에서 뺌).
        # 알파는 아래 판 · 둘레 규칙 그대로. 못 하면(모델 없음 · 추론 실패 · 창 넘침) 판 색 그대로 + 기록
        other_g = dg._dilate((d0 > dg.INK_MIN) & dg._dilate(oth, 3) & ~dg._dilate(glyph, 2), LAMA_OTHER_GROW) if oth is not None else np.zeros_like(hole)
        # 붙이는 자리 = 지울 자리 ∪ 원천 가림(획 + 빛 꼬리 × LAMA_CONTEXT_K + PAD, 지킬 것 빼고) — 지울 자리만 붙이면 그 밖 컨셉의 옅은 빛과 경계가 윤곽으로,
        # 마스크 밖 옅은 빛 기울기를 '가운데 광원'으로 이어 그려 따뜻한 아지랑이가 났다 [실측 오프라인 R20261119_144231 — S4 7.6]
        tail_e = int(erec.get("erase_tail") or 0)
        ctx = dg._dilate(glyph, LAMA_CONTEXT_K * tail_e + LAMA_CONTEXT_PAD) & dg._dilate(own, 2 + tail_e)
        keep_e = erec.get("_keep")
        paste = hole | (ctx & ~(keep_e if keep_e is not None else np.zeros_like(ctx)) & (aw > 0.5))
        # 인페인팅 마스크 = 지울 자리 + LAMA_MASK_GROW ∪ 원천 가림 전체 — 붙일 자리 + 4 px 로 바꾼 판은 오프라인 144231 S4 3.2 → 11.3 으로 나빠졌다
        run_m = dg._dilate(hole, LAMA_MASK_GROW) | ctx
        try:
            lam = inpaint(x0, y0, run_m, other_g)
        except Exception as exc:  # noqa: BLE001 — 기록하고 판으로 물러남
            lam, erec["lama_error"] = None, f"{type(exc).__name__}: {exc}"[:160]
        if lam is not None:
            erec["lama_paste_px"] = int((paste & ~hole).sum())
            hole = _fill_enclosed(paste) & (run_m | other_g)        # 갇힌 칠 안 된 픽셀도(인페인팅이 다시 그린 자리 안만)
            if LAMA_SEAM:
                # 매끈한 이음 — 테두리(붙일 자리 밖 · 인페인팅 원본 출력이 있는 LAMA_MASK_GROW px)의 (컨셉 − 인페인팅) 차를 경계값 보간으로 안쪽에 더한다(인페인팅의
                # 낮은 주파수 색조 치우침 — 단색 패널에서 어두운 실루엣). 다른 글자 가림 · 큰 차(구조물 — 채널 최대 > LAMA_SEAM_MAX)는 0
                resid = cw - lam
                bad = other_g | (np.abs(resid).max(axis=2) > LAMA_SEAM_MAX) | ~run_m
                corr = _harmonic_fill(np.where((hole | bad)[..., None], 0.0, resid), hole, wy=1.0)
                lam = lam + np.where(hole[..., None], corr, 0.0)
                erec["lama_seam"] = round(float(np.abs(corr[hole]).mean()), 2) if hole.any() else 0.0
            nc = np.where(hole[..., None], np.clip(lam, 0, 255), nc)
            erec["fill"] = "lama"
        else:
            erec.setdefault("fill", "plate (lama unavailable)")
    else:
        lam = None
    blend, zone_b = _blend_band(hole, cutout.NOTEXT_GROW, cutout.NOTEXT_BLUR)          # V1 — 섞임 띠는 바꿀 수 있는 자리 안에서 끝남
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
        fpm, fa = _smooth_fill(cw * aw[..., None], aw, ~hole & free if int((~hole & free).sum()) >= 10 else ~hole)
        low = hole & (na2 < fa - PLATE_ALPHA_MISMATCH)
        pt = plate_text(nc, na)
        if pt is not None:
            low |= hole & dg._dilate(pt & dg._dilate(glyph, 2), 1)      # 판에 남은 글자 자리(획 근처만)도 판 대신 둘레 메움(위 glyph_of)
        if int(low.sum()) >= 10:
            nc = np.where(low[..., None], fpm / np.maximum(fa, 1e-4)[..., None], nc)
            na2 = np.where(low, fa, na2)
            grec = {**grec, "alpha_from": grec.get("alpha_from") or "text-free concept — its transparent glyph holes from the concept neighbourhood",
                    "plate_clear_px": int(low.sum())}
            if lam is not None:
                # G2 (가) — 색은 인페인팅 그대로(판 자국 · 투명 구멍 자리도) — 매끈한 평균으로 덮으면 글자 모양 얼룩이 됐다 [실측 오프라인 R20261119_144231 '4.2']
                nc = np.where(hole[..., None], np.clip(lam, 0, 255), nc)
    if lam is not None and hole.any():
        # G2 (가) — 알파는 둘레 컨셉 알파의 경계값 보간(판 알파 · 수준 맞춤을 섞으면 옛 글자 자리가 옅은 윤곽으로 남았다 [실측 오프라인 R20261119_144231 '4'])
        na2 = np.where(hole, np.clip(_harmonic_fill(np.where(hole, 0.0, aw)[..., None], hole)[..., 0], 0.0, 1.0), na2)
        # 글자 지우기 마감 H2 — 섞임 띠(붙인 자리 밖 NOTEXT_GROW · 흐림)는 인페인팅 출력(인페인팅이 다시 그린 자리 — 마스크 · 다른 글자 가림, 그 밖은 지금 그림)과
        # 지금 그림을 섞는다. 판 색(색조 맞춤 판)을 섞으면 붙인 자리 경계가 '4' 바깥 윤곽으로 남았다 [실측 R20261119_190059 — 단계 그림: 섞임 띠 최대 ΔE00 80]
        gen_m = run_m | other_g
        nc = np.where(hole[..., None], nc, np.where(gen_m[..., None], np.clip(lam, 0, 255), cw_cur))
        na2 = np.where(hole, na2, aw_cur)
        blend = np.where(hole | gen_m, blend, 0.0)
        zone_b &= hole | gen_m
        erec["band"] = "inpaint"
    out_a = blend * na2 + (1 - blend) * aw_cur
    pm = blend[..., None] * nc * na2[..., None] + (1 - blend)[..., None] * cw_cur * aw_cur[..., None]
    out_c = np.where(out_a[..., None] > 1e-4, pm / np.maximum(out_a, 1e-4)[..., None], cw_cur)
    if item.get("erase") and not (item.get("gauge") or whole):
        erec["background"] = _background_stats(cw_cur, aw_cur, hole, free)            # V8 — 메우기 전 그림(창 보기)
    _put(col, a, (y0, y1, x0, x1), zone_b, out_c, out_a)
    return {"used": True, "shift": [dx, dy], "diff": sh["diff"], "hole_px": int(hole.sum()), "whole": bool(whole or item.get("gauge")), "path": "plate",
            **({"erase_method": item.get("erase_method")} if item.get("erase") else {}), **({"clear_alpha": ca_na} if ca_na else {}),
            **({"tone": tone} if tone is not None else {}), **{k: v for k, v in erec.items() if not k.startswith("_")},
            **{k: v for k, v in grec.items() if k in ("alpha_gain", "alpha_gain_applied", "alpha_from", "alpha_mismatch", "plate_clear_px")},
            **_zone_rec((y0, y1, x0, x1), zone_b)}


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
                      "colors": _font_colors(t), **({"hidden": True} if _starts_hidden(spec, t["id"]) else {})})
    if art_files(run):
        texts = []          # 1b 후속 K-a — 판 = 글자 없는 아트: 지울 글자가 없다
        log["art"] = "text-free art (generated concept) — no text fill"
    hook = _erase_setup(run, spec, texts, col0, log, aid=aid, origin=(x, y))
    items = texts + gauge_items
    M = PLATE_TEXT_MARGIN
    wins = _merge_windows([[max(0, int(it["box"][0]) - M), max(0, int(it["box"][1]) - M), min(w, int(np.ceil(it["box"][0] + it["box"][2])) + M),
                            min(h, int(np.ceil(it["box"][1] + it["box"][3])) + M)] for it in items])

    P = cutout.NOTEXT_SHIFT
    nt_pad = None
    if notext is not None:
        nt_pad = (_pad_crop(notext[0], x, y, x + w, y + h, P),
                  _pad_crop(notext[1], x, y, x + w, y + h, P) if notext[1] is not None else np.pad(a0, P, mode="edge"))

    def take(r: dict, zacc, tid) -> dict:
        """글자 메움 기록 → 바꿀 수 있는 자리(_zone)는 누적 마스크로, '정답 없음' 자리(_ntz)는 캔버스 상자로(판 텍스처 = 판 상자 1:1 — 좌표 + 판 상자 원점)."""
        _zone_add(zacc, r)
        nz = r.pop("_ntz", None)
        if nz is not None and isinstance(r.get("no_truth"), dict):
            wy0, _, wx0, _, _m = nz
            bw_ = r["no_truth"].get("box_win") or [0, 0, 0, 0]
            r["no_truth"]["box"] = [x + wx0 + bw_[0], y + wy0 + bw_[1], bw_[2], bw_[3]]
        return r

    def bake(whole: bool, use_nt: bool, erase: bool = True):
        col, a = col0.copy(), a0.copy()
        recs = []
        zacc = np.zeros((h, w), bool)          # V1 — 이 굽기가 바꿀 수 있는 자리(글자 메움 함수들이 돌려준 자리의 합)
        # 1b 후속 L 다음 F1 — 시작 때 숨는 글자 자리는 자리 전체 둘레 메움(_hidden_text_fill — 판 · 줄 보간 길 대신). 컨셉이 그 글자를 안 그렸으면 예전 길
        items_ = items
        if any(it.get("hidden") for it in items):
            items_ = []
            for it in items:
                if it.get("hidden"):
                    r = take(_hidden_text_fill(col, a, it, orig=(col0, a0), others=[o["box"] for o in texts if o is not it], mask=mask, nt_pad=nt_pad), zacc,
                             it["id"])
                    if r.get("used") or r.get("nothing"):
                        recs.append({"item": it["id"], **r})
                        continue
                    recs.append({"item": it["id"], "hidden_fill": r})
                items_.append(it)
        # 가득 찬 게이지(mask)는 요소 없는 판으로만 — 판이 없거나 못 쓰면 컨셉 그대로(채움이 같은 자리를 덮는다), 줄 보간 안 함
        left = items_ if not any(it.get("mask") is not None for it in items_) else [it for it in items_ if it.get("mask") is None]
        if use_nt and nt_pad is not None:
            # 글자 없는 판이 있으면 글자마다 '판과 다른 획'만 판 픽셀로(_plate_item_fill) — 못 맞춘 글자만 아래 줄 보간으로
            left = []
            for it in items_:
                on = bool(it.get("erase")) and erase
                it_ = it if on else {k: v for k, v in it.items() if k not in ("erase", "erase_method")}
                r = take(_fill_text_item(col, a, nt_pad[0], nt_pad[1], it_, whole=whole, orig=(col0, a0),
                                         others=[o["box"] for o in texts if o is not it], inpaint=hook if on else None), zacc, it["id"])
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
            zacc[wy0:wy1, wx0:wx1] = True        # V1 — 창 메움(cutout.compose 물러남)은 창 전체를 바꿀 수 있는 자리로(보수적)
            recs.append({"window": [x + wx0, y + wy0, wx1 - wx0, wy1 - wy0], "items": [it["id"] for it in loc],
                         "notext": (comp.get("notext") or {}).get("used") if isinstance(comp, dict) else None,
                         "shift": (comp.get("notext") or {}).get("shift") if isinstance(comp, dict) else None,
                         **({"fallback": comp["fallback"]} if isinstance(comp, dict) and comp.get("fallback") else {})})
        return col, a, recs, zacc

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
    # 1b 후속 L 다음 — 글자마다 지우기 방법은 run.erase_plan(_erase_setup 이 표시) — 고르기는 refine 끝 게이트와 같은 함수(_gate_erase_choice)
    col, a, recs, zacc = bake(False, True)
    erase_ok = True
    im = cutout.to_image(col, a, (tw, th))
    det = detect(im)
    baked, decor = baked_of(det)
    if any(t.get("erase") for t in texts):
        log["ocr_marks"] = _ocr_marks(baked, decor, spec)          # V6 — 지운 판 OCR: 글자 상자 근처 = 잔여물(반복 보강) · 먼 것 = 기록
    if baked and any(t.get("erase") for t in texts):
        # 글자 지우기 마감 — 지운 판 후보에선 상자째 · 판 없이 다시 굽는 물러남을 안 한다(기록만): 그 물러남이 다른 글자 · 게이지 트랙까지 바꿔 후보 점수를 오염시켰다
        # [실측 오프라인 R20261119_003127 파티 lama 후보 — LaMa 가 다시 그린 숫자 → 판 없이 다시 굽기 → 초록 막대 · 삼각 조각]. 남은 글자는 게이트 고르기(S4)가 거른다
        log["text_marks_erase"] = {"count": det["count"], "baked": baked}
        baked = []
    if baked and items:
        log["text_marks_first"] = {"count": det["count"], "baked": baked}
        col, a, recs, zacc = bake(True, True, erase_ok)
        im = cutout.to_image(col, a, (tw, th))
        det = detect(im)
        baked, decor = baked_of(det)
        if baked and notext is not None:
            log["text_marks_second"] = {"count": det["count"], "baked": baked}
            col, a, recs, zacc = bake(True, False, erase_ok)
            im = cutout.to_image(col, a, (tw, th))
            det = detect(im)
            baked, decor = baked_of(det)
    log["_zone"] = _zone_to_size(zacc, (tw, th))             # V1 — 텍스처 크기 바꿀 수 있는 자리(refine.run 이 꺼냄 — JSON 에 안 씀)
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


def _erase_rec(log: dict) -> dict:
    """에셋 기록의 글자 지우기 표시(판 = log.text_erase · 오리기 = log.cut.text_erase)."""
    return (log.get("text_erase") or (log.get("cut") or {}).get("text_erase") or {}) if isinstance(log, dict) else {}


def _boxes_from_spec(spec: dict) -> list[dict]:
    """refine 시점 상자(엔진 geometry 없음) — replay_refine.boxes_from_spec 과 같은 정의(bbox_intent, 없으면 화면 전체)."""
    cw, ch = (float(v) for v in spec.get("canvas", [1920, 1080]))
    return [{"id": w["id"], "x": float((w.get("bbox_intent") or [0, 0, cw, ch])[0]), "y": float((w.get("bbox_intent") or [0, 0, cw, ch])[1]),
             "w": float((w.get("bbox_intent") or [0, 0, cw, ch])[2]), "h": float((w.get("bbox_intent") or [0, 0, cw, ch])[3]), "visible": True}
            for w in spec.get("widgets", [])]


def _decode(png_bytes: bytes):
    import io
    import numpy as np
    from PIL import Image
    with Image.open(io.BytesIO(png_bytes)) as im:
        return np.asarray(im.convert("RGBA"), float)


def _erase_ok(sm: dict | None, sn: dict | None) -> bool:
    """지운 판 점수(sm)가 좁은 판(sn — 예전 판)보다 나빠지지 않음 — S4 국소 · 결함 수 · 가는 선 · 밝힌 검정(_gate_erase_choice)."""
    if sm is None:
        return False
    if sn is None:
        return sm["findings"] == 0
    if sm["local"] > max(sn["local"], ERASE_ACCEPT_FLOOR) + ERASE_ACCEPT_MARGIN or sm["findings"] > sn["findings"]:
        return False
    if sm.get("bg_px") is not None and sn.get("bg_px") is not None and sm["bg_px"] > sn["bg_px"] + ERASE_BG_MARGIN:
        # 글자 지우기 다음 — 컨셉 상태 글자 구역 바탕(진단 E1 자리)이 예전 판보다 결함 덩어리만큼 넘게 나빠지면 못 받음 — 빈 값 S4 만 보면 LaMa 가 두 톤 배지를 다시
        # 그린 방패 '10' · 넓은 컨셉 빛을 지운 Lv(clear_alpha)가 골라져 컨셉 상태 E1 이 새로 났다 [실측 R20261122_135359 · R20261120_142400]
        return False
    if sm["findings"] < sn["findings"]:
        # 예전 판의 게이트 오류(S4 · 가는 선)를 없애면 문턱 아래 부 지표(가는 선 길이 · 밝힌 검정 — 기록)는 보지 않는다 — 예전 판이 오류로 남았다
        # [실측 회귀 m_erase_1119 조작 안내 LinkLabelText — off 7.1(결함 1) ↔ harmonic 4.84(결함 0)가 밝힘 13.6 > 10.5 로 막힘]
        return True
    if sm["contour"] > max(sn["contour"], ERASE_CONTOUR_FLOOR):
        return False
    if sn["local"] > ERASE_ACCEPT_FLOOR and sm["local"] < sn["local"] - ERASE_ACCEPT_MARGIN:
        # 문턱 위 S4 가 뚜렷이 나아지면 밝힌 검정(기록 — 어두운 판의 낮은 대비)은 안 본다 [실측 회귀 m_erase_1119 파티 '0 %' — off 49.3 ↔ harmonic 22.7 이
        # 밝힘 24.3 > 23.0 으로 막힘]
        return True
    return sm["lift"] <= sn["lift"] + ERASE_LIFT_MARGIN


def _gate_scores(run, spec_c: dict, textures: dict, s: dict, gm=None, cache=None) -> tuple[dict, dict]:
    """게이트와 같은 함수(diagnose.composite_text_trace — text_glyph_masks + state_check.text_trace)로 캔버스 합성 S4 → (글자마다 점수, gm)."""
    from gen import diagnose as dg
    tt, ex = dg.composite_text_trace(run.path("spec.json").parent, spec_c, _boxes_from_spec(spec_c), textures, s, gm=gm, cache=cache)
    sc = dg.trace_scores(tt)
    for t, b in (ex.get("bg") or {}).items():
        if t in sc:
            sc[t].update(b)          # 글자 지우기 다음 — 컨셉 상태 글자 구역 바탕(bg_px · bg_max)도 고르기에
    return sc, ex["gm"]


def _text_recs(log: dict) -> dict:
    """에셋 기록의 글자마다 메움 기록(판 = log.windows 의 item · 오리기 = log.cut.glyph_fill 의 text) → {글자: 기록}."""
    out = {}
    for r in (log or {}).get("windows") or []:
        if isinstance(r, dict) and r.get("item"):
            out[r["item"]] = r
    for r in ((log or {}).get("cut") or {}).get("glyph_fill") or []:
        if isinstance(r, dict) and r.get("text"):
            out[r["text"]] = r
    return out


def _applied(log: dict) -> dict:
    """글자마다 실제로 쓴 지우기 방법(erase_method — 메움 기록에 있을 때만, 없으면 None — clear_alpha 는 투명 바탕 길에서만 씀)."""
    return {t: (r.get("erase_method") if r.get("used") else None) for t, r in _text_recs(log).items()}


def _better(a: dict | None, b: dict | None) -> bool:
    """V6 — 점수 a 가 b 보다 나은가((결함 수, S4 국소) 사전 순으로 작음)."""
    if a is None:
        return False
    if b is None:
        return True
    return (a["findings"], a["local"]) < (b["findings"], b["local"] - ERASE_ACCEPT_MARGIN)


def _iou(p, q) -> float:
    ix = max(0.0, min(p[0] + p[2], q[0] + q[2]) - max(p[0], q[0]))
    iy = max(0.0, min(p[1] + p[3], q[1] + q[3]) - max(p[1], q[1]))
    return ix * iy / max(1e-6, p[2] * p[3] + q[2] * q[3] - ix * iy)


def _ocr_marks_of(log: dict) -> list:
    return (log or {}).get("ocr_marks") or ((log or {}).get("cut") or {}).get("ocr_marks") or []


def _gate_erase_choice(run, spec_c: dict, base: dict, cands: dict, rebuild) -> dict:
    """1b 후속 L 다음 — 글자 지우기 마감: 글자마다 지운 판 후보(ERASE_METHODS)와 좁은 판(off — 예전 판)을 게이트와 같은 함수(캔버스 합성 S4 · 가는 선 · 숨는 묶음 ·
    밝힌 검정 기록)로 견주어 고른다. 결과 판은 예전보다 나빠지는 글자가 없어야 한다(사용자 결정 11-19 — 'all' 범위 + 이 고르기).
    base = 다른 에셋 텍스처 {aid: RGBA}, cands = {aid: {"vars": {방법: (info, log, png 바이트)}, "zones": {방법: 바꿀 수 있는 자리}, "texts": [...]}},
    rebuild(aid, plan) → (info, log, 바이트, 자리).
    ① (글자 지우기 다음 V1 검증 A) 후보마다 바꿀 수 있는 자리 밖이 예전 판과 RGBA 같은가 — 다르면 그 후보 버림 ② 방법마다 모든 후보 에셋을 그 방법으로 합성 →
    글자마다 점수 ③ 받을 수 있는(_erase_ok · 그 글자에 실제로 쓴 방법) 방법 중 (결함 수, S4, 밝힌 검정)이 가장 작은 것 ④ 계획대로 굽고(섞이면 다시 굽기) 합성 확인
    ⑤ (V6 반복 보강) 받은 후보에 결함이 남았거나 받은 후보가 없는데 예전 판에 결함 · OCR 잔여물이 있는 글자만 여백 단계(@1 · @2)를 올려 같은 고르기 ⑥ 고른 판 전체를
    다시 합성해 확인 — 나빠진 글자는 off 로 한 번 더, 그래도면 그 에셋 전부 off ⑦ 남은 결함이 '정답 없음' 근거가 있는 글자는 수동 확인 표시(사용자 결정 ③), 복잡 배경
    (V8) · OCR 먼 검출 기록.
    → {aid: {"choice": (info, log, 바이트), "plan", "scores", "verify", "outside", "retries", "manual_check", "background", "complex", "ocr_far"}}."""
    from gen import diagnose as dg
    s = dg.settings(run.cfg)
    cache: dict = {}
    methods = ["off"] + [m for m in ERASE_METHODS if any(m in c["vars"] for c in cands.values())]
    out: dict = {aid: {"outside": {}} for aid in cands}
    if "lama" not in erase_methods(run.cfg):
        # 첫 판(lama — 표시 없는 첫 굽기)은 늘 굽지만, 후보에서 뺐으면 견주지 않는다
        methods = [m for m in methods if m != "lama"]
    valid: dict = {}
    for aid, c in cands.items():
        valid[aid] = {"off"}
        for m, v in c["vars"].items():
            if m == "off":
                continue
            oc = _outside_changed(v[2], c["zones"].get(m), c["vars"]["off"][2], c["zones"].get("off"))
            out[aid]["outside"][m] = oc
            if oc["px"] == 0:
                valid[aid].add(m)
    applied = {aid: {m: _applied(v[1]) for m, v in c["vars"].items()} for aid, c in cands.items()}
    scores: dict = {}
    gm = None
    for m in methods:
        tex = dict(base)
        for aid, c in cands.items():
            v = c["vars"][m] if (m in c["vars"] and m in valid[aid]) else c["vars"]["off"]
            tex[aid] = _decode(v[2])
        sc, g_ = _gate_scores(run, spec_c, tex, s, gm=gm, cache=cache)
        gm = gm or g_                      # 글자 획 자리는 좁은 판(예전 판) 합성에서 한 번 — 후보끼리 같은 자리로 견줌
        scores[m] = sc

    def usable(aid, m, t, sc_m, sn) -> bool:
        return m in valid[aid] and applied[aid].get(m, {}).get(t) == _plan_method(m)[0] and _erase_ok(sc_m, sn)
    for aid, c in cands.items():
        plan = {}
        for t in c["texts"]:
            sn = scores["off"].get(t)
            ok = [m for m in methods if m != "off" and m in c["vars"] and usable(aid, m, t, scores[m].get(t), sn)]
            ok.sort(key=lambda m: (scores[m][t]["findings"], scores[m][t]["local"], scores[m][t]["lift"]))
            plan[t] = ok[0] if ok else "off"
        out[aid].update(plan=plan, scores={t: {m: scores[m].get(t) for m in methods} for t in c["texts"]})

    def choose(aid):
        """계획대로 — 한 방법뿐이면 그 판, 섞이면 다시 굽기(V1 확인 — 자리 밖이 다르면 그 에셋 전부 off)."""
        c, plan = cands[aid], out[aid]["plan"]
        ms = set(plan.values())
        if len(ms) == 1 and next(iter(ms)) in c["vars"]:
            out[aid]["choice"] = c["vars"][next(iter(ms))]
            return
        i_, l_, b_, z_ = rebuild(aid, plan)
        oc = _outside_changed(b_, z_, c["vars"]["off"][2], c["zones"].get("off"))
        out[aid]["outside"]["plan"] = oc
        if oc["px"]:
            out[aid]["plan"] = {t: "off" for t in plan}
            out[aid]["choice"] = c["vars"]["off"]
            out[aid]["outside_fallback"] = f"the mixed plan changed {oc['px']} px outside its zones — the whole asset kept the old plate"
            return
        out[aid]["choice"] = (i_, l_, b_)

    def composite_scores():
        tex = dict(base)
        for aid in cands:
            tex[aid] = _decode(out[aid]["choice"][2])
        return _gate_scores(run, spec_c, tex, s, gm=gm, cache=cache)[0]
    for aid in cands:
        choose(aid)
    sv = composite_scores()
    # ⑤ V6 반복 보강 — 결함이 남은 글자 · OCR 잔여물 글자만 여백 단계를 올려(ERASE_PAD_STEP) 다시 굽고 같은 고르기
    for lv in range(1, ERASE_RETRIES + 1):
        need = {}
        for aid, c in cands.items():
            near = {n for mk in _ocr_marks_of(out[aid]["choice"][1]) for n in mk.get("near") or []}
            ts = []
            for t in c["texts"]:
                cur, sn = sv.get(t), scores["off"].get(t)
                if (cur and cur["findings"] > 0) or (t in near and out[aid]["plan"].get(t) != "off") \
                        or (out[aid]["plan"].get(t) == "off" and sn and (sn["findings"] > 0 or t in near)):
                    ts.append(t)
            if ts:
                need[aid] = ts
        if not need:
            break
        tried = []
        for aid, ts in need.items():
            c = cands[aid]
            best = {t: (out[aid]["plan"][t], sv.get(t)) for t in ts}
            for m in [m for m in methods if m != "off"]:
                key = f"{m}@{lv}"
                plan_try = {t: (key if t in ts else out[aid]["plan"][t]) for t in c["texts"]}
                i_, l_, b_, z_ = rebuild(aid, plan_try)
                oc = _outside_changed(b_, z_, c["vars"]["off"][2], c["zones"].get("off"))
                ap = _applied(l_)
                row = {"level": lv, "method": m, "texts": ts, "outside_px": oc["px"]}
                if oc["px"]:
                    tried.append({**row, "skipped": "changed pixels outside its zones (V1)"})
                    continue
                tex = dict(base)
                for a2 in cands:
                    tex[a2] = _decode(b_ if a2 == aid else out[a2]["choice"][2])
                sc = _gate_scores(run, spec_c, tex, s, gm=gm, cache=cache)[0]
                row["scores"] = {t: sc.get(t) for t in ts}
                tried.append(row)
                for t in ts:
                    if ap.get(t) == m and _erase_ok(sc.get(t), scores["off"].get(t)) and _better(sc.get(t), best[t][1]):
                        best[t] = (key, sc.get(t))
            changed = {t: k for t, (k, _) in best.items() if k != out[aid]["plan"][t]}
            if changed:
                out[aid]["plan"] = {**out[aid]["plan"], **changed}
                choose(aid)
        for aid in need:
            out[aid].setdefault("retries", []).extend([r for r in tried if set(r["texts"]) <= set(cands[aid]["texts"])])
        sv = composite_scores()
    # ⑥ 고른 판 확인 — 나빠진 글자는 off 로 한 번 더, 그래도면 그 에셋 전부 off. 예전 판(off)으로 둔 글자가 나빠졌으면 그 원인은 상자가 겹친 이웃 글자의 지우기 —
    # 그 이웃을 off 로(글자 지우기 다음 — 회귀 o_next 첫 판: 단색 '2/4' · 파티 HP 숫자가 옆 글자를 넓게 지운 자리 탓에 예전 판보다 나빠졌는데 확인이 off 글자를 안 봤다)
    index_c = spec_mod.widget_index(spec_c)

    def overl(t1, t2) -> bool:
        b1, b2 = (index_c.get(t1) or {}).get("bbox_intent"), (index_c.get(t2) or {}).get("bbox_intent")
        if not b1 or not b2:
            return True
        return b1[0] < b2[0] + b2[2] and b2[0] < b1[0] + b1[2] and b1[1] < b2[1] + b2[3] and b2[1] < b1[1] + b1[3]
    for _round in range(2):
        bad = False
        for aid, c in cands.items():
            fails = [t for t, m in out[aid]["plan"].items() if m != "off" and not _erase_ok(sv.get(t), scores["off"].get(t))]
            off_bad = [t for t, m in out[aid]["plan"].items() if m == "off" and sv.get(t) and scores["off"].get(t) and not _erase_ok(sv.get(t), scores["off"].get(t))]
            for t in off_bad:
                fails += [u for u, m in out[aid]["plan"].items() if m != "off" and u not in fails and overl(t, u)]
            if off_bad:
                out[aid].setdefault("off_worse", []).append({"round": _round, "texts": off_bad})
            out[aid].setdefault("verify", []).append({"round": _round, "scores": {t: sv.get(t) for t in c["texts"]}, "failed": fails})
            if fails:
                bad = True
                if _round == 0:
                    out[aid]["plan"] = {t: ("off" if t in fails else m) for t, m in out[aid]["plan"].items()}
                    choose(aid)
                else:
                    out[aid]["plan"] = {t: "off" for t in out[aid]["plan"]}
                    out[aid]["choice"] = c["vars"]["off"]
        if not bad:
            break
        sv = composite_scores()
    else:
        # 마지막 판(둘째 판에서 에셋 전부 off 로 되돌린 뒤)의 점수도 남긴다 — 없으면 회귀 표가 되돌리기 직전 점수를 '고른 판'으로 읽었다 [실측 회귀 q_next_1120 단색 '4.2' 32.5]
        for aid, c in cands.items():
            out[aid].setdefault("verify", []).append({"round": "final", "scores": {t: sv.get(t) for t in c["texts"]}, "failed": []})
    # ⑦ 기록 — 정답 없음(사용자 결정 ③ — 근거 있는 글자의 남은 결함만 수동 확인) · 복잡 배경(V8) · OCR 먼 검출(V6)
    off_marks = {aid: [mk["box"] for mk in _ocr_marks_of(c["vars"]["off"][1])] for aid, c in cands.items()}
    for aid, c in cands.items():
        recs_all = [_text_recs(v[1]) for v in c["vars"].values()]
        final = _text_recs(out[aid]["choice"][1])
        bgs, cx, mc = {}, [], []
        for t in c["texts"]:
            fr = final.get(t) or {}
            bg = fr.get("background") or next((r.get(t, {}).get("background") for r in recs_all if r.get(t, {}).get("background")), None)
            if bg:
                bgs[t] = bg
                if complex_background(bg, run.cfg):
                    cx.append(t)
            nt = next((r.get(t, {}).get("no_truth") for r in recs_all if r.get(t, {}).get("no_truth")), None)
            rem = (sv.get(t) or {}).get("findings", 0)
            if nt and rem:
                mc.append({"widget": t, "reason": "no_truth", "box": nt.get("box"), "evidence": {k: nt.get(k) for k in ("px", "concept_alpha", "plate_alpha", "rule")},
                           "remaining_findings": rem, "plan": out[aid]["plan"].get(t)})
            if t in cx:
                mc.append({"widget": t, "reason": "complex_background", "background": bg, "backend": str(((run.cfg.get("extract") or {}).get("text_fill_complex")
                                                                                                        or "none"))})
        far = [mk for mk in _ocr_marks_of(out[aid]["choice"][1]) if not mk.get("near") and not any(_iou(mk["box"], o) >= 0.3 for o in off_marks[aid])]
        out[aid].update(background=bgs, complex=cx, manual_check=mc, **({"ocr_far": far} if far else {}))
    return out


def run(run, opts) -> str:
    import copy
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
    built: dict = {}                     # aid → (info, log, backend) — spec 에셋 순서
    prev_over: dict = {}
    if run.path("refine.json").is_file():
        for p in run.read_json("refine.json").get("passes", []):
            for o in p.get("overhang_updates", []):
                if o.get("size_new"):
                    prev_over[o["asset"]] = o
    dropped = []
    # 1b 후속 H3 — 넘침이 차지한 빈 자리(위젯 상자 밖) 장부: 앞 에셋(spec 순서)이 가져간 자리는 뒤 에셋의 넘침이 못 가져간다(_cut_entry)
    import numpy as np
    cw, ch = (int(v) for v in spec.get("canvas", [0, 0]))
    run.overhang_claims = np.zeros((ch, cw), bool) if cw > 0 and ch > 0 else None
    run.cut_ownership_cache = {}             # 1b 후속 I — 겹친 자리 물체 단위 소유 지도(_ownership — 이 spec 으로 한 번)
    run.toggle_own_masks = None              # L-2 기본 전환 ④ — 접히는 위젯의 자기 마스크(layer.json toggles — 다시 읽음)
    run.radial_ring_masks = None             # 전투 HUD 동작 — 고리 픽셀 마스크(layer.json radials — 다시 읽음)
    # 1b 후속 L 다음 — 글자 지우기 마감: 글자마다 지우기 방법(_erase_setup 이 읽음). 없으면 첫 판 = 표시한 글자 모두 lama
    run.erase_plan = {}
    gate = str(((run.cfg.get("extract") or {}).get("text_erase") or "off")) != "off"
    cands: dict = {}

    def build(asset, raw, backend):
        aid = asset["asset_id"]
        if asset.get("source_mode") == "plate":         # 1b 후속 J-a — 정적 판
            return _plate_entry(run, asset, spec)
        if backend == "procedural":
            return _procedural_entry(run, asset, raw, backend)
        return _generated_entry(run, asset, raw, backend, gen_recs.get(aid), spec)

    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if only and aid not in only and aid in previous:
            built[aid] = None
            _claim_previous_overhang(run, aid, prev_over.get(aid))
            continue
        dropped += drop_overhang(spec, aid, prev_over.get(aid))        # 1b 후속 H — 다시 다듬을 때는 지난 넘침 장식을 걷고 새로
        raw = run.path("assets", "raw", f"{aid}.png")
        if not raw.is_file() and asset.get("source_mode") != "plate":      # 판은 raw 를 쓰지 않는다(컨셉 · layer 마스크에서 굽는다)
            raise StageError("RAW_MISSING", f"{raw} was not generated", asset=aid)
        backend = backends.get(aid, asset["provenance"])
        if asset.get("source_mode") == "plate":
            backend = "concept_plate"
        claims0 = run.overhang_claims.copy() if run.overhang_claims is not None else None
        info, log = build(asset, raw, backend)
        z0 = log.pop("_zone", None)            # V1 — 바꿀 수 있는 자리(JSON 에 안 씀)
        te = _erase_rec(log)
        final = run.path("assets", "final", f"{aid}.png")
        if gate and te.get("texts"):
            # 글자 지우기 마감 — 같은 에셋을 방법마다(lama 첫 판 · harmonic · clear_alpha · off = 예전 판) 구워 두고 refine 끝에 게이트와 같은 함수로 글자마다 고른다
            vars_ = {"lama": (info, log, final.read_bytes())}
            zones = {"lama": z0}
            for m in [x for x in erase_methods(run.cfg) if x != "lama"] + ["off"]:
                run.erase_plan[aid] = {t: m for t in te["texts"]}
                if claims0 is not None:
                    run.overhang_claims[...] = claims0
                i_, l_ = build(asset, raw, backend)
                zones[m] = l_.pop("_zone", None)
                vars_[m] = (i_, l_, final.read_bytes())
            run.erase_plan.pop(aid, None)
            final.write_bytes(vars_["lama"][2])
            cands[aid] = {"vars": vars_, "zones": zones, "texts": list(te["texts"]), "claims": claims0, "asset": asset, "raw": raw, "backend": backend}
        built[aid] = (info, log, backend)
    erase_gate = None
    if cands:
        from gen import backdrop
        claims_end = run.overhang_claims.copy() if run.overhang_claims is not None else None
        # 합성용 spec = 지금 기록(첫 판)으로 margin · 브러시 · 넘침을 적용한 사본(넘침 텍스처 상자가 맞아야 캔버스 합성이 맞다)
        spec_c = copy.deepcopy(spec)
        _spec_changes(spec_c, {k: v for k, v in built.items() if v is not None}, run)
        base = {}
        for a in spec.get("assets", []):
            if a["asset_id"] in cands:
                continue
            f = run.path("assets", "final", f"{a['asset_id']}.png")
            if built.get(a["asset_id"]) is None and a["asset_id"] in previous:
                f = run.path(previous[a["asset_id"]]["file"])
            if f.is_file():
                base[a["asset_id"]] = backdrop._load(f)

        def rebuild(aid, plan):
            c = cands[aid]
            run.erase_plan[aid] = dict(plan)
            if c["claims"] is not None:
                run.overhang_claims[...] = c["claims"]
            i_, l_ = build(c["asset"], c["raw"], c["backend"])
            z_ = l_.pop("_zone", None)
            run.erase_plan.pop(aid, None)
            if claims_end is not None:
                run.overhang_claims[...] = claims_end
            return i_, l_, run.path("assets", "final", f"{aid}.png").read_bytes(), z_
        erase_gate = _gate_erase_choice(run, spec_c, base, cands, rebuild)
        for aid, r in erase_gate.items():
            info, log, data = r["choice"]
            run.path("assets", "final", f"{aid}.png").write_bytes(data)
            te = _erase_rec(log)
            te["gate"] = {k: r.get(k) for k in ("plan", "scores", "verify", "outside", "retries", "manual_check", "background", "complex", "ocr_far",
                                               "outside_fallback", "off_worse") if r.get(k) is not None}
            built[aid] = (info, log, cands[aid]["backend"])
    entries, logs, margin_updates, over_recs = [], [], {}, {}
    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if built.get(aid) is None:
            entries.append(previous[aid])
            continue
        info, log, backend = built[aid]
        if backend not in ("procedural", "concept_plate"):
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
                                   "brush_updates": brush_changes, "overhang_updates": over_changes, "overhang_dropped": dropped,
                                   **({"erase_gate": {aid: {"plan": r["plan"],
                                                            # V1 검증 A — 후보마다 바꿀 수 있는 자리 밖 다른 픽셀 수(0 이어야 그 후보를 견줌)
                                                            "outside_changed_px": {m: o.get("px") for m, o in (r.get("outside") or {}).items()},
                                                            **({"manual_check": r["manual_check"]} if r.get("manual_check") else {}),
                                                            **({"complex": r["complex"]} if r.get("complex") else {}),
                                                            **({"ocr_far": r["ocr_far"]} if r.get("ocr_far") else {}),
                                                            **({"retries": [{k: x.get(k) for k in ("level", "method", "texts", "outside_px", "skipped")}
                                                                            for x in r.get("retries") or []]} if r.get("retries") else {})}
                                                      for aid, r in erase_gate.items()}} if erase_gate else {})})
        run.write_json("refine.json", prev_log)
    comp = ", ".join(f"{e['asset_id']}={e['compression']}" for e in entries)
    texty = [e["asset_id"] for e in entries if e.get("ocr_text")]
    extracted = [l["asset_id"] for l in logs if l.get("source_mode") == "extract"]
    extra = (f"; margins from the images: {len(changes)} change(s)" if changes else "") + (f"; text-like marks in {texty}" if texty else "") \
        + (f"; extracted from the concept: {extracted} (compare: assets/compare/)" if extracted else "") \
        + (f"; fixed-size brushes drawn as image: {[c['widget'] for c in brush_changes]}" if brush_changes else "") \
        + (f"; overhang decorations: {[d['deco'] for c in over_changes for d in c['decos']]}" if over_changes else "") \
        + (f"; text erase (gate choice): {sum(1 for r in erase_gate.values() for m in r['plan'].values() if m != 'off')}/"
           f"{sum(len(r['plan']) for r in erase_gate.values())} erased" if erase_gate else "")
    return (f"{len(entries)} asset(s) in manifest ({comp}){extra}") if entries else "no assets"


def _spec_changes(spec: dict, built: dict, run) -> None:
    """refine 끝의 spec 바꿈(추정 margin · 크기 고정 브러시 image · 넘침 장식)을 제자리에서 — 글자 지우기 고르기의 합성용 사본에 먼저 적용."""
    margin_updates, over_recs = {}, {}
    for aid, (info, log, backend) in built.items():
        if backend in ("procedural", "concept_plate"):
            continue
        if (log.get("margin") or {}).get("source") in ("estimated", "mixed"):
            margin_updates[aid] = log["margin"]["used"]
        if log.get("overhang"):
            over_recs[aid] = log["overhang"]
    if margin_updates:
        _apply_margins(run, spec, margin_updates)
    extract_ids = {a["asset_id"] for a in spec.get("assets", []) if a.get("provenance") == "codex" and a.get("source_mode") == "extract"}
    if extract_ids and (run.cfg.get("extract") or {}).get("fixed_size_draw_as", "image") == "image":
        _extract_brushes_to_image(spec, extract_ids)
    for aid, over in over_recs.items():
        apply_overhang(spec, aid, over)
