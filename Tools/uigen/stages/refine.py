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


def extract_target_box(spec: dict | None, asset: dict, extract: dict) -> list[float]:
    """따온 텍스처를 되자를 상자(reference 좌표) — 이 에셋을 브러시로 쓰는 첫 위젯의 bbox_intent(텍스처가 그 위젯에 1:1 로 그려지게),
    없으면 ref_bbox, 그것도 없으면 입력의 요소 상자."""
    for w in (spec or {}).get("widgets", []):
        for key, brush in (w.get("style") or {}).items():
            if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset") == asset["asset_id"] and w.get("bbox_intent"):
                return [float(v) for v in w["bbox_intent"]]
    if asset.get("ref_bbox"):
        return [float(v) for v in asset["ref_bbox"]]
    rx, ry = extract["region"][:2]
    ex, ey, ew, eh = extract["element"]
    return [rx + ex, ry + ey, ew, eh]


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
    if extract and asset.get("kind") in ("frame", "panel_bg") and ext_cfg.get("interior_alpha") is not None:
        im, log["interior"] = pp.interior_fill(im, float(ext_cfg["interior_alpha"]), float(ext_cfg.get("interior_max_lightness", pp.INTERIOR_MAX_L)),
                                               flatten=bool(ext_cfg.get("interior_flatten", True)))
    st = pp.alpha_stats(im)
    log["alpha"] = st
    if asset.get("kind") in NEEDS_ALPHA and not st["has_alpha"]:
        raise StageError("NO_ALPHA", f"'{aid}' ({asset['kind']}) is still fully opaque after background removal", asset=aid)
    margin, est = None, None
    if asset.get("nine_slice"):
        est = pp.estimate_nine_slice(im)
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
    log["ocr"] = det
    if extract:
        log["fidelity"] = _extract_fidelity(run, aid, box, cropped, im)
    text = "" if det["count"] == 0 else f"{det['count']} text-like box(es), max score {det['max_score']}"
    return ({"alpha": st["has_alpha"], "nine_slice_margin": margin, "ocr_text": text,
             "ocr": f"{det['engine']} — detection boxes with score ≥ {det['min_score']} and area ≥ {det['min_area_px']} px", "size": [im.width, im.height]},
            log)


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
    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if only and aid not in only and aid in previous:
            entries.append(previous[aid])
            continue
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
    if changes or brush_changes:
        schema.require("spec", spec)
        run.write_json("spec.json", spec)
    manifest = {"schema_version": 1, "run_id": run.run_id, "assets": entries}
    schema.require("manifest", manifest)
    run.write_json("manifest.json", manifest)
    if any(l.get("backend") != "procedural" for l in logs) or changes or brush_changes:
        prev_log = run.read_json("refine.json") if run.path("refine.json").is_file() else {"passes": []}
        prev_log["passes"].append({"attempt": int(getattr(opts, "attempt", 0) or 0), "assets": logs, "margin_updates": changes,
                                   "brush_updates": brush_changes})
        run.write_json("refine.json", prev_log)
    comp = ", ".join(f"{e['asset_id']}={e['compression']}" for e in entries)
    texty = [e["asset_id"] for e in entries if e.get("ocr_text")]
    extracted = [l["asset_id"] for l in logs if l.get("source_mode") == "extract"]
    extra = (f"; margins from the images: {len(changes)} change(s)" if changes else "") + (f"; text-like marks in {texty}" if texty else "") \
        + (f"; extracted from the concept: {extracted} (compare: assets/compare/)" if extracted else "") \
        + (f"; fixed-size brushes drawn as image: {[c['widget'] for c in brush_changes]}" if brush_changes else "")
    return (f"{len(entries)} asset(s) in manifest ({comp}){extra}") if entries else "no assets"
