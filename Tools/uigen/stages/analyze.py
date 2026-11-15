"""analyze — reference.png + brief → spec.json (설계 §2-2 · §5 'analyze 주의' · §12-1 A8).

LLM(`claude -p`, prompts/analyze.md)이 판단하는 것은 배치 · 스타일 · 에셋뿐이다. 계약 필드는 코드가 채운다(`apply_contract`):
  - schema_version · canvas(= brief.resolution) · profile(= brief.screen_type)
  - 동적 데이터 위젯의 binding(data · kind · format) · 글자(dynamic · data · sample) · 게이지 percent(sample)
  - 고정 글자 위젯의 text(static · value) · TextBlock 의 font.family(= brief.font, 비어 있을 때)
  - (1b 후속 B ②) 샘플이 꺼짐(false)인 flag 위젯의 visibility = collapsed
그 뒤 검사(스키마 · 의미 · brief 맞물림 · 위젯 타입 · bbox · 에셋 · flag 위젯이 상자 패널 안 금지)를 하고, 실패하면 오류 목록과 앞 출력 파일을 주고 **1회** 다시 요청한다.
두 번째도 실패하면 ANALYZE_INVALID 로 멈춘다(§2-2 '스키마 위반 → 1회 재요청 후 중단').
통과하면 (1b 후속 B ①) 게이지 채움 · 배경을 컨셉에서 결정적으로 뽑는다(`derive_gauge_fills` → analyze/derived.json).

출력: spec.json · specs/000.json · analyze/attempt_NNN.json(LLM 원본) · analyze/attempt_NNN_errors.json · analyze/overlay.png(bbox_intent 를
reference 위에 그린 사람 눈용) · analyze.json(요약) · llm.jsonl(호출마다 한 줄).
"""
from __future__ import annotations

import copy
import json

from core import config
from core import llm
from core import schema
from core import spec as spec_mod
from stages import StageError
from stages.normalize import check_brief_vs_spec

MAX_CALLS = 2
BBOX_TOLERANCE_PX = 2
MAX_CODEX_ASSETS = 6
# 1b 후속 B — 런타임 setter 가 flag 를 Collapsed 로 접으므로(core/cppgen.py SETTERS flag) 상자 패널 안의 flag 위젯은 형제를 움직인다
BOX_PANELS = {"VerticalBox", "HorizontalBox", "UniformGridPanel"}
GAUGE_EDGE_FRAC = 0.04     # 채움 색을 뽑을 때 채워진 부분 양끝에서 뺄 비율(끝 캡 · 경계 번짐)
GAUGE_MIN_PX = 8
GAUGE_MAX_STOPS = 48
GAUGE_FILL_WIDTH = 64      # 채움 텍스처 폭(가로는 같은 색이라 작아도 된다)


def output_schema() -> dict:
    """spec 스키마 그대로(`--json-schema` 로 — llm.cli_schema 가 $schema · $id 를 뺀다, [실측 1b-1] spec 스키마 통째로 통과)."""
    return copy.deepcopy(schema.schema("spec"))


def _contract_lines(brief: dict) -> list[str]:
    statics = {s["widget"]: s["value"] for s in brief.get("static_text", [])}
    lines = []
    for d in brief["dynamic_data"]:
        extra = f", format {d['format']}" if d.get("format") else ""
        st = f", static text {statics[d['widget']]!r}" if d["widget"] in statics else ""
        desc = f" — {d['desc']}" if d.get("desc") else ""
        lines.append(f"- {d['widget']}: {d.get('widget_type') or '?'} — data '{d['id']}' ({d['type']}{extra}), sample {json.dumps(d.get('sample'), ensure_ascii=False)}{st}{desc}")
    bound = {d["widget"] for d in brief["dynamic_data"]}
    for w, v in statics.items():
        if w not in bound:
            lines.append(f"- {w}: TextBlock — static text {v!r}")
    return lines


def build_prompt(run, brief: dict, cfg: dict, retry: dict | None = None) -> str:
    profile = config.load_profile(brief["screen_type"])
    fonts = cfg.get("fonts") or {}
    lh = fonts.get("line_height") or {}
    lh_text = ", ".join(f"{k}→{v}" for k, v in sorted(((int(k), v) for k, v in lh.items()))) or "about 1.6 × size"
    req = "\n".join(f"- {e['id']} ({e['kind']}){': ' + e['desc'] if e.get('desc') else ''}" for e in brief["required_elements"])
    w, h = brief["resolution"]
    gates = profile.get("gates") or {}
    parts = [
        f"Analyze the UI concept for run {run.run_id} into a widget spec.",
        f"Files (absolute paths — Read them):\n- reference: {run.path('reference.png').resolve().as_posix()} ({w}×{h}, the concept fitted to the canvas)\n"
        f"- brief: {run.path('brief.json').resolve().as_posix()}",
        f"Screen: {brief['screen_id']} — screen_type '{brief['screen_type']}' (background {profile.get('background', '?')}; the scene behind the HUD is not UI). "
        f"Canvas {w}×{h}. Description: {brief.get('text') or '-'}",
        "Contract (exact ids and widget types; the pipeline fills binding/text of these after you answer):\n" + "\n".join(_contract_lines(brief)),
        "Required elements:\n" + req,
        f"Style keywords: {', '.join(brief.get('style_keywords') or []) or '-'}",
        f"Project font: {brief.get('font') or 'engine default'} (omit font.family). Line height in px per font size: {lh_text}.",
        f"Layout gates: region IoU ≥ {gates.get('iou_region_min')}, leaf IoU ≥ {gates.get('iou_leaf_min')}, "
        f"boxes thinner than {gates.get('small_px')} px by center distance ≤ {gates.get('small_center_max_px')} px, sibling overlap ≤ {gates.get('overlap_max_ratio')} "
        f"outside allow_overlap, nothing off-screen at {w}×{h}, 2560×1080 and 1920×1200.",
        "Return the complete spec through the structured output.",
    ]
    if retry:
        parts.append(f"Your previous answer (saved at {retry['file']}) failed these checks — fix every one and return the complete corrected spec:\n"
                     + "\n".join(f"- {e}" for e in retry["errors"][:40]))
    return "\n\n".join(parts)


def apply_contract(spec: dict, brief: dict) -> dict:
    """LLM 출력에 계약 필드를 채운 새 spec — 판단이 아니라 요청이 정한 값이다."""
    out = copy.deepcopy(spec)
    out["schema_version"] = 1
    out["canvas"] = list(brief["resolution"])
    out["profile"] = brief["screen_type"]
    index = spec_mod.widget_index(out)
    for d in brief["dynamic_data"]:
        w = index.get(d["widget"])
        if not w:
            continue
        b = {"data": d["id"], "kind": d["type"]}
        if d.get("format") and d["type"] == "number":
            b["format"] = d["format"]
        w["binding"] = b
        if d["type"] in ("text", "number") and w.get("type") == "TextBlock":
            w["text"] = {"source": "dynamic", "data": d["id"], "sample": _sample_text(d)}
        if d["type"] == "progress" and w.get("type") == "ProgressBar" and isinstance(d.get("sample"), (int, float)):
            w.setdefault("style", {})["percent"] = max(0.0, min(1.0, float(d["sample"])))
        if d["type"] == "flag" and d.get("sample") is False:
            w["visibility"] = "collapsed"      # 1b 후속 B ② — 샘플이 꺼짐이면 WBP 도 처음엔 접힘(게이트 렌더는 force_visible 이라 영향 없음)
    for st in brief.get("static_text", []):
        w = index.get(st["widget"])
        if w and w.get("type") == "TextBlock":
            w["text"] = {"source": "static", "value": st["value"]}
    if brief.get("font"):
        for w in out.get("widgets", []):
            if w.get("type") == "TextBlock":
                font = w.setdefault("font", {})
                if not font.get("family"):
                    font["family"] = brief["font"]
    return out


def _sample_text(d: dict) -> str:
    s = d.get("sample")
    if d["type"] == "number" and isinstance(s, (int, float)) and not isinstance(s, bool):
        digits = len(d["format"].split(".", 1)[1]) if "." in (d.get("format") or "") else 0
        return f"{s:.{digits}f}"
    return "" if s is None else str(s)


def check(spec: dict, brief: dict) -> list[str]:
    errs = schema.errors("spec", spec)
    if errs:
        return [f"SCHEMA {e}" for e in errs]
    errs = spec_mod.validate_semantics(spec)
    errs += check_brief_vs_spec(brief, spec)
    w, h = brief["resolution"]
    index = spec_mod.widget_index(spec)
    for wd in spec["widgets"]:
        if wd["id"] == spec["root"]:
            continue
        bb = wd.get("bbox_intent")
        if not bb:
            errs.append(f"BBOX_MISSING: '{wd['id']}' has no bbox_intent")
            continue
        x, y, bw, bh = bb
        if bw <= 0 or bh <= 0 or x < -BBOX_TOLERANCE_PX or y < -BBOX_TOLERANCE_PX or x + bw > w + BBOX_TOLERANCE_PX or y + bh > h + BBOX_TOLERANCE_PX:
            errs.append(f"BBOX_OUTSIDE: '{wd['id']}' bbox_intent {bb} is empty or outside the {w}x{h} canvas")
        if wd.get("parent") == spec["root"] and wd.get("slot", {}).get("kind") == "canvas":
            slot = wd["slot"]
            a, al = slot.get("anchors") or [0, 0, 0, 0], slot.get("alignment") or [0, 0]
            if a[0] == a[2] and a[1] == a[3] and slot.get("size") and slot.get("position") is not None and not slot.get("auto_size"):
                px = slot["position"][0] - al[0] * slot["size"][0] + a[0] * w
                py = slot["position"][1] - al[1] * slot["size"][1] + a[1] * h
                if max(abs(px - x), abs(py - y), abs(slot["size"][0] - bw), abs(slot["size"][1] - bh)) > BBOX_TOLERANCE_PX:
                    errs.append(f"SLOT_VS_BBOX: region '{wd['id']}' canvas slot places it at [{px:g}, {py:g}, {slot['size'][0]:g}, {slot['size'][1]:g}] "
                                f"but bbox_intent is {bb} (position = x + alignment·w − anchor·canvas)")
    used = {b["asset"] for wd in spec["widgets"] for k, b in (wd.get("style") or {}).items()
            if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")}
    codex = 0
    for a in spec.get("assets", []):
        if a["asset_id"] not in used:
            errs.append(f"ASSET_UNUSED: '{a['asset_id']}' is not used by any brush")
        if a.get("source_mode") and a["provenance"] != "codex":
            errs.append(f"ASSET_SOURCE_MODE: '{a['asset_id']}' source_mode is only for codex assets (provenance '{a['provenance']}')")
        if a.get("source_mode") == "extract" and not a.get("ref_bbox"):
            errs.append(f"ASSET_REF_BBOX: '{a['asset_id']}' is source_mode extract — give ref_bbox, the tight reference box of the element to extract")
        if a["provenance"] == "codex":
            codex += 1
            if not (a.get("prompt") or "").strip():
                errs.append(f"ASSET_PROMPT: codex asset '{a['asset_id']}' needs a prompt")
            rb = a.get("ref_bbox")
            if rb and (rb[2] <= 0 or rb[3] <= 0 or rb[0] < 0 or rb[1] < 0 or rb[0] + rb[2] > w + BBOX_TOLERANCE_PX or rb[1] + rb[3] > h + BBOX_TOLERANCE_PX):
                errs.append(f"ASSET_REF_BBOX: '{a['asset_id']}' ref_bbox {rb} is outside the canvas")
        elif a["provenance"] == "procedural" and not a.get("procedural"):
            errs.append(f"ASSET_PROCEDURAL: procedural asset '{a['asset_id']}' needs procedural{{shape, …}}")
        elif a["provenance"] not in ("codex", "procedural"):
            errs.append(f"ASSET_PROVENANCE: '{a['asset_id']}' provenance '{a['provenance']}' — Phase 1b uses codex or procedural")
        if max(a["size"]) > 1024:
            errs.append(f"ASSET_SIZE: '{a['asset_id']}' size {a['size']} — keep textures ≤ 1024 px")
    if codex > MAX_CODEX_ASSETS:
        errs.append(f"ASSET_CODEX_COUNT: {codex} codex assets — at most {MAX_CODEX_ASSETS} (prefer procedural / rounded_box)")
    for wid in index:
        if wid in {d["widget"] for d in brief["dynamic_data"]}:
            continue
        if index[wid].get("binding"):
            errs.append(f"EXTRA_BINDING: '{wid}' has a binding the request does not list")
    for d in brief["dynamic_data"]:
        w = index.get(d["widget"])
        parent = index.get(w.get("parent")) if w else None
        if d["type"] == "flag" and parent and parent.get("type") in BOX_PANELS:
            errs.append(f"FLAG_IN_BOX: '{d['widget']}' is a flag widget (the game collapses it) inside {parent['type']} '{parent['id']}' — toggling it "
                        f"moves or stretches its siblings; put it in an Overlay or give it its own canvas region")
    return errs


def _snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def derive_gauge_fills(spec: dict, reference) -> list[dict]:
    """1b 후속 B ① — 게이지(ProgressBar) 채움 · 배경을 컨셉에서 결정적으로 뽑는다(LLM · codex 없음).

    채움: bbox_intent 안 채워진 부분(샘플 percent — left_to_right / right_to_left 만, 양끝 4 % 뺌)의 줄마다 대표색(중앙값) →
          procedural gradient_bar(색 단계 ≤ 48) 에셋 `<위젯>_fill` → style.fill = image. Slate 는 채움 이미지를 바 전체 크기로 그리고
          진행률만큼 자른다([소스] SProgressBar.cpp:237-253) — 가로가 같은 색인 세로 그라데이션이면 그대로 맞다.
    배경: 같은 Overlay 의 앞(아래) 형제가 컨셉에서 따온 프레임이면 none(프레임의 트랙이 보이게), 아니면 안 채워진 부분의 대표색 rounded_box.
    → 바꾼 기록 목록(spec 은 제자리에서 바뀐다)."""
    import numpy as np
    from PIL import Image
    with Image.open(reference) as im:
        ref = np.asarray(im.convert("RGB"))
    H, W = ref.shape[:2]
    index = spec_mod.widget_index(spec)
    extract_ids = {a["asset_id"] for a in spec.get("assets", []) if a.get("provenance") == "codex" and a.get("source_mode") == "extract"}
    taken = {a["asset_id"] for a in spec.get("assets", [])}
    order = {w["id"]: i for i, w in enumerate(spec.get("widgets", []))}
    out = []
    for w in spec.get("widgets", []):
        if w.get("type") != "ProgressBar" or not w.get("bbox_intent"):
            continue
        st = w.setdefault("style", {})
        p, ftype = st.get("percent"), st.get("bar_fill_type", "left_to_right")
        rec = {"widget": w["id"], "percent": p, "bar_fill_type": ftype}
        if not isinstance(p, (int, float)) or ftype not in ("left_to_right", "right_to_left"):
            out.append({**rec, "skipped": "needs a sample percent and a horizontal fill"})
            continue
        x, y, bw, bh = (float(v) for v in w["bbox_intent"])
        y0, y1 = max(0, int(round(y))), min(H, int(round(y + bh)))
        e = GAUGE_EDGE_FRAC
        filled, empty = ((x + e * bw, x + (p - e) * bw), (x + (p + e) * bw, x + (1 - e) * bw)) if ftype == "left_to_right" else \
            ((x + (1 - p + e) * bw, x + (1 - e) * bw), (x + e * bw, x + (1 - p - e) * bw))
        fx0, fx1 = max(0, int(round(filled[0]))), min(W, int(round(filled[1])))
        if fx1 - fx0 < GAUGE_MIN_PX or y1 - y0 < 2:
            out.append({**rec, "skipped": f"filled part too small ({fx1 - fx0} px)"})
            continue
        prof = np.median(ref[y0:y1, fx0:fx1].astype(float), axis=1)
        if len(prof) > GAUGE_MAX_STOPS:
            prof = prof[np.linspace(0, len(prof) - 1, GAUGE_MAX_STOPS).round().astype(int)]
        stops = ["#%02X%02X%02XFF" % tuple(int(round(v)) for v in c) for c in prof]
        aid, k = f"{_snake(w['id'])}_fill", 2
        while aid in taken:
            aid, k = f"{_snake(w['id'])}_fill_{k}", k + 1
        taken.add(aid)
        spec.setdefault("assets", []).append({"asset_id": aid, "kind": "fill", "provenance": "procedural", "size": [GAUGE_FILL_WIDTH, max(4, y1 - y0)],
                                              "procedural": {"shape": "gradient_bar", "stops": stops},
                                              "source": f"concept rows {y0}-{y1}, x {fx0}-{fx1} (filled part at sample {p:g})"})
        rec.update(fill_asset=aid, stops=len(stops), sampled=[fx0, y0, fx1 - fx0, y1 - y0], old_fill=st.get("fill"), old_background=st.get("background"))
        st["fill"] = {"draw_as": "image", "asset": aid}
        parent = index.get(w.get("parent"))
        under = [s for s in spec["widgets"] if s.get("parent") == w.get("parent") and order[s["id"]] < order[w["id"]]
                 and ((s.get("style") or {}).get("brush") or {}).get("asset") in extract_ids]
        if parent and parent.get("type") == "Overlay" and under:
            st["background"] = {"draw_as": "none"}
            rec["background_from"] = f"none — extracted frame '{under[-1]['id']}' underneath"
        else:
            ux0, ux1 = max(0, int(round(empty[0]))), min(W, int(round(empty[1])))
            if ux1 - ux0 >= GAUGE_MIN_PX:
                c = np.median(ref[y0:y1, ux0:ux1].reshape(-1, 3).astype(float), axis=0)
                old = st.get("background") or {}
                st["background"] = {"draw_as": "rounded_box", "color": "#%02X%02X%02XFF" % tuple(int(round(v)) for v in c),
                                    "radius": old.get("radius", 0) if old.get("draw_as") == "rounded_box" else 0}
                rec["background_from"] = f"concept empty part x {ux0}-{ux1}"
        rec.update(fill=st["fill"], background=st.get("background"))
        out.append(rec)
    return out


def draw_overlay(run, spec: dict) -> str | None:
    """bbox_intent 를 reference 위에 그린 그림(사람 눈 — A8 장면/UI 가르기 확인). Pillow 가 없으면 건너뛴다."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:   # pragma: no cover
        return None
    index = spec_mod.widget_index(spec)
    depth = {}
    for wid in spec_mod.tree_order(spec):
        p = index[wid].get("parent")
        depth[wid] = 0 if p is None else depth.get(p, 0) + 1
    colors = [(255, 80, 80), (80, 220, 255), (255, 210, 60), (120, 255, 120), (230, 120, 255)]
    with Image.open(run.path("reference.png")) as im:
        canvas = im.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    for wid in spec_mod.tree_order(spec):
        bb = index[wid].get("bbox_intent")
        if not bb:
            continue
        c = colors[(depth[wid] - 1) % len(colors)]
        x, y, w, h = bb
        draw.rectangle([x, y, x + w, y + h], outline=c, width=2 if depth[wid] == 1 else 1)
        draw.text((x + 3, y + 2), wid, fill=c)
    for a in spec.get("assets", []):
        rb = a.get("ref_bbox")
        if rb:
            x, y, w, h = rb
            draw.rectangle([x, y, x + w, y + h], outline=(255, 255, 255))
            draw.text((x + 3, y + h - 12), f"ref:{a['asset_id']}", fill=(255, 255, 255))
    out = run.path("analyze", "overlay.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG")
    return "analyze/overlay.png"


def run(run, opts) -> str:
    brief = run.read_json("brief.json")
    if not run.path("reference.png").is_file():
        raise StageError("NO_REFERENCE", "analyze needs reference.png (normalize concept)")
    out_schema = output_schema()
    cli = getattr(opts, "llm_cli", None)
    calls, errors, retry, spec, retry_reasons = [], [], None, None, []
    for k in range(1, MAX_CALLS + 1):
        prompt = build_prompt(run, brief, run.cfg, retry)
        try:
            res = llm.run_stage("analyze", prompt, run.cfg, out_schema, cli=cli)
        except llm.LlmError as exc:
            calls.append({"attempt": k, "error": exc.code, **{x: exc.details.get(x) for x in ("cost_usd", "num_turns", "duration_s", "model", "tokens")}})
            _record(run, calls, errors, retry_reasons)
            raise StageError(exc.code, f"analyze: {exc}", **{x: exc.details.get(x) for x in ("cost_usd", "num_turns", "subtype")}) from exc
        raw = res["structured_output"]
        rel = f"analyze/attempt_{k:03d}.json"
        run.write_json(rel, raw)
        spec = apply_contract(raw, brief)
        errors = check(spec, brief)
        run.write_json(f"analyze/attempt_{k:03d}_errors.json", {"errors": errors})
        calls.append({"attempt": k, "errors": len(errors), **{x: res.get(x) for x in ("cost_usd", "num_turns", "duration_s", "model", "tokens", "session_id")}})
        run.append_jsonl("llm.jsonl", {"stage": "analyze", "attempt": k, **{x: res.get(x) for x in ("cost_usd", "num_turns", "duration_s", "model", "tokens")},
                                       "errors": len(errors)})
        if not errors:
            break
        retry = {"file": run.path(rel).resolve().as_posix(), "errors": errors}
        retry_reasons = list(errors)
    summary = _record(run, calls, errors, retry_reasons)
    if errors:
        raise StageError("ANALYZE_INVALID", f"analyze output failed {len(errors)} check(s) after {len(calls)} call(s): " + "; ".join(errors[:6]), errors=errors)
    derived = derive_gauge_fills(spec, run.path("reference.png"))
    if derived:
        schema.require("spec", spec)
        run.write_json("analyze/derived.json", {"gauge_fills": derived})
    run.write_json("spec.json", spec)
    run.write_json("specs/000.json", spec)
    overlay = draw_overlay(run, spec)
    n_codex = sum(1 for a in spec.get("assets", []) if a["provenance"] == "codex")
    n_extract = sum(1 for a in spec.get("assets", []) if a["provenance"] == "codex" and a.get("source_mode") == "extract")
    gauges = [d["widget"] for d in derived if d.get("fill_asset")]
    return (f"{len(spec['widgets'])} widgets, {len(spec.get('assets', []))} assets ({n_codex} codex, {n_extract} extract"
            f"{', gauge fill from the concept: ' + ','.join(gauges) if gauges else ''}) in {len(calls)} call(s) — "
            f"API list-price equivalent {summary['cost_usd']:.3f} USD (subscription login — plan usage, not billed), model {summary['model']}"
            f"{', overlay ' + overlay if overlay else ''}")


def _record(run, calls: list[dict], errors: list[str], retry_reasons: list[str]) -> dict:
    summary = {"calls": len(calls), "cost_usd": round(sum(float(c.get("cost_usd") or 0) for c in calls), 4),
               "duration_s": round(sum(float(c.get("duration_s") or 0) for c in calls), 2),
               "model": next((c.get("model") for c in reversed(calls) if c.get("model")), None),
               "retry_reasons": retry_reasons[:20], "final_errors": errors[:20], "attempts": calls,
               "ok": not errors and bool(calls) and all("error" not in c for c in calls)}
    run.write_json("analyze.json", summary)
    return summary
