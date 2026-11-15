"""analyze — reference.png + brief → spec.json (설계 §2-2 · §5 'analyze 주의' · §12-1 A8).

LLM(`claude -p`, prompts/analyze.md)이 판단하는 것은 배치 · 스타일 · 에셋뿐이다. 계약 필드는 코드가 채운다(`apply_contract`):
  - schema_version · canvas(= brief.resolution) · profile(= brief.screen_type)
  - 동적 데이터 위젯의 binding(data · kind · format) · 글자(dynamic · data · sample) · 게이지 percent(sample)
  - 고정 글자 위젯의 text(static · value) · TextBlock 의 font.family(= brief.font, 비어 있을 때)
  - (1b 후속 B ②) 샘플이 꺼짐(false)인 flag 위젯의 visibility = collapsed
그 뒤 검사(스키마 · 의미 · brief 맞물림 · 위젯 타입 · bbox · 에셋 · flag 위젯이 상자 패널 안 금지)를 하고, 실패하면 오류 목록과 앞 출력 파일을 주고 **1회** 다시 요청한다.
두 번째도 실패하면 ANALYZE_INVALID 로 멈춘다(§2-2 '스키마 위반 → 1회 재요청 후 중단').
통과하면 (1b 후속 B ① · F) 게이지 채움 · 배경을 컨셉에서 결정적으로 뽑는다(`derive_gauge_fills` → analyze/derived.json — 따온 프레임 위면 채움 모양 그대로).

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


ROLE_HINTS = {"body": "sans — body text, small labels, counters", "title": "serif — titles, banners, big numbers"}


def font_lines(cfg: dict, brief: dict) -> str:
    """프롬프트의 폰트 줄 — 역할마다 폰트 · 용도 · 줄 높이 표(1b 후속 D). 역할이 없으면(엔진 기본) 예전 문장."""
    roles = config.font_roles(cfg, brief.get("font"))
    if not roles:
        return "Project font: engine default (omit font.family). Line height in px per font size: about 1.6 × size."
    def glyphs(v):
        g = v.get("glyph_height") or {}
        parts = [f"{k} ≈ {float(x):g} × size" for k, x in g.items()]
        return f"; visible glyph height: {', '.join(parts)}" if parts else ""
    rows = [f"- `{r}` = {v['family'].rsplit('/', 1)[-1].split('.')[0]} ({ROLE_HINTS.get(r, r)}): line height in px per font size "
            f"{config.line_height_text(v['line_height']) or 'about 1.6 × size'}{glyphs(v)}" for r, v in roles.items()]
    # 1b 후속 F [실측 C1 렌더] Noto Serif KR 한글 획 높이 = 크기 × 1.32 ~ 1.35, 숫자 1.02 — '글자 높이 ≈ 크기'는 숫자에만 맞아 배너가 1.18 배로 컸다
    return ("Font roles (set font.role on every TextBlock, omit font.family):\n" + "\n".join(rows) + "\n"
            "Pick each size from the glyph height you see divided by that font's glyph-height ratio above (Hangul and digits differ — Hangul is taller "
            "at the same size), then make the TextBlock's bbox_intent that size's line box (height = the line height above, vertically centered on the glyphs).")


def build_prompt(run, brief: dict, cfg: dict, retry: dict | None = None) -> str:
    profile = config.load_profile(brief["screen_type"])
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
        font_lines(cfg, brief),
        f"Layout gates: region IoU ≥ {gates.get('iou_region_min')}, leaf IoU ≥ {gates.get('iou_leaf_min')}, "
        f"boxes thinner than {gates.get('small_px')} px by center distance ≤ {gates.get('small_center_max_px')} px, sibling overlap ≤ {gates.get('overlap_max_ratio')} "
        f"outside allow_overlap, nothing off-screen at {w}×{h}, 2560×1080 and 1920×1200.",
        "Return the complete spec through the structured output.",
    ]
    if retry:
        parts.append(f"Your previous answer (saved at {retry['file']}) failed these checks — fix every one and return the complete corrected spec:\n"
                     + "\n".join(f"- {e}" for e in retry["errors"][:40]))
    return "\n\n".join(parts)


def apply_contract(spec: dict, brief: dict, roles: dict[str, dict] | None = None) -> dict:
    """LLM 출력에 계약 필드를 채운 새 spec — 판단이 아니라 요청이 정한 값이다.
    roles(config.font_roles) — TextBlock 의 font.role 을 그 역할의 family 로 바꾸고 role 을 지운다(1b 후속 D). 모르는 역할 · 역할 없음은 body."""
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
    for w in out.get("widgets", []):
        if w.get("type") != "TextBlock":
            continue
        font = w.setdefault("font", {})
        role = font.pop("role", None)
        if roles and role in roles:
            font["family"] = roles[role]["family"]
        elif not font.get("family") and (brief.get("font") or (roles or {}).get("body")):
            font["family"] = brief.get("font") or roles["body"]["family"]
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
        elif a["provenance"] == "procedural" and a["procedural"].get("shape") == "concept_fill":
            errs.append(f"ASSET_PROCEDURAL: '{a['asset_id']}' — concept_fill is made by the pipeline from the concept; use gradient_bar or rounded_box for a gauge fill")
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


def _new_asset_id(w: dict, taken: set) -> str:
    aid, k = f"{_snake(w['id'])}_fill", 2
    while aid in taken:
        aid, k = f"{_snake(w['id'])}_fill_{k}", k + 1
    taken.add(aid)
    return aid


def _apply_concept_fill(spec: dict, w: dict, parent: dict, frame: dict, ref, taken: set, gcfg: dict) -> dict:
    """1b 후속 F — 따온 프레임 위 가로 게이지의 채움을 컨셉 모양 그대로(gen/concept_fill). 못 재면 ConceptFillError."""
    from gen import concept_fill
    st = w["style"]
    end = gcfg.get("end", "scale")
    m = concept_fill.measure(ref, frame["bbox_intent"], w["bbox_intent"], st["percent"], st.get("bar_fill_type", "left_to_right"), end=end)
    wx, wy, ww, wh = m["widget_box"]
    px, py, pw, ph = (float(v) for v in parent["bbox_intent"])
    pad = [wx - px, wy - py, (px + pw) - (wx + ww), (py + ph) - (wy + wh)]
    if min(pad) < -BBOX_TOLERANCE_PX:
        raise concept_fill.ConceptFillError(f"the measured track {m['widget_box']} sticks out of the parent '{parent['id']}' box {parent['bbox_intent']}")
    pad = [round(max(0.0, v), 1) for v in pad]
    pad = [int(v) if float(v).is_integer() else v for v in pad]
    aid = _new_asset_id(w, taken)
    asset = {"asset_id": aid, "kind": "fill", "provenance": "procedural", "size": [ww, wh], "procedural": {"shape": "concept_fill", **m["params"]},
             "source": f"concept fill shape inside frame '{frame['id']}' (track {m['widget_box']}, sample {st['percent']:g})"}
    rec = {"fill_asset": aid, "shape": "concept_fill", "end": end, "widget_box": m["widget_box"], "old_bbox": list(w["bbox_intent"]),
           "old_padding": (w.get("slot") or {}).get("padding"), "old_fill": st.get("fill"), "old_background": st.get("background"), **m["record"]}
    if m["margin"]:
        asset.update(nine_slice=True, margin=m["margin"])
        st["fill"] = {"draw_as": "box", "asset": aid, "margin": m["margin"]}
        st["bar_fill_style"] = "scale"
    else:
        st["fill"] = {"draw_as": "image", "asset": aid}
        st.pop("bar_fill_style", None)
    spec.setdefault("assets", []).append(asset)
    st["background"] = {"draw_as": "none"}
    w["bbox_intent"] = [wx, wy, ww, wh]
    slot = w.setdefault("slot", {"kind": "overlay"})
    slot.update(padding=pad, h_align="fill", v_align="fill")
    rec.update(padding=pad, fill=st["fill"], background_from=f"none — extracted frame '{frame['id']}' underneath")
    return rec


def derive_gauge_fills(spec: dict, reference, gauge_cfg: dict | None = None) -> list[dict]:
    """1b 후속 B ① · F — 게이지(ProgressBar) 채움 · 배경을 컨셉에서 결정적으로 뽑는다(LLM · codex 없음).

    (F, gauge_fill.mode shape — 기본) 같은 Overlay 의 앞(아래) 형제가 컨셉에서 따온 프레임인 가로 게이지: 컨셉 채움의 모양 그대로
          (gen/concept_fill — 왼쪽 '<' 끝 · 밝은 테두리 · 트랙 띠의 빛 · end scale 이면 진행 끝 테두리 · 번짐) → procedural concept_fill,
          막대 bbox_intent · slot.padding 을 잰 트랙 상자로, end scale 이면 style.bar_fill_style scale + 채움 box(양끝 여백). 못 재면 아래 B 방식(기록 shape_fallback).
    (B) 채움: bbox_intent 안 채워진 부분(샘플 percent — left_to_right / right_to_left 만, 양끝 4 % 뺌)의 줄마다 대표색(중앙값) →
          procedural gradient_bar(색 단계 ≤ 48) 에셋 `<위젯>_fill` → style.fill = image. Slate 는 채움 이미지를 바 전체 크기로 그리고
          진행률만큼 자른다([소스] SProgressBar.cpp:237-253) — 가로가 같은 색인 세로 그라데이션이면 그대로 맞다.
    배경: 같은 Overlay 의 앞(아래) 형제가 컨셉에서 따온 프레임이면 none(프레임의 트랙이 보이게), 아니면 안 채워진 부분의 대표색 rounded_box.
    → 바꾼 기록 목록(spec 은 제자리에서 바뀐다)."""
    import numpy as np
    from PIL import Image
    from gen import concept_fill
    gcfg = gauge_cfg or {}
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
        parent = index.get(w.get("parent"))
        under = [s for s in spec["widgets"] if s.get("parent") == w.get("parent") and order[s["id"]] < order[w["id"]]
                 and ((s.get("style") or {}).get("brush") or {}).get("asset") in extract_ids]
        if gcfg.get("mode", "shape") == "shape" and parent and parent.get("type") == "Overlay" and parent.get("bbox_intent") \
                and under and under[-1].get("bbox_intent"):
            try:
                rec.update(_apply_concept_fill(spec, w, parent, under[-1], ref, taken, gcfg))
                out.append(rec)
                continue
            except concept_fill.ConceptFillError as exc:
                rec["shape_fallback"] = str(exc)
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
        aid = _new_asset_id(w, taken)
        spec.setdefault("assets", []).append({"asset_id": aid, "kind": "fill", "provenance": "procedural", "size": [GAUGE_FILL_WIDTH, max(4, y1 - y0)],
                                              "procedural": {"shape": "gradient_bar", "stops": stops},
                                              "source": f"concept rows {y0}-{y1}, x {fx0}-{fx1} (filled part at sample {p:g})"})
        rec.update(fill_asset=aid, stops=len(stops), sampled=[fx0, y0, fx1 - fx0, y1 - y0], old_fill=st.get("fill"), old_background=st.get("background"))
        st["fill"] = {"draw_as": "image", "asset": aid}
        st.pop("bar_fill_style", None)
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


TEXT_GRADIENT_MIN_DE = 8.0   # 글자 위 · 아래 줄 대표색 ΔE00 이 이 이상이면 세로 그라데이션(잠정)
TEXT_BAND = 0.25             # 위 · 아래 대표색을 잡을 글자 줄 비율


def _hex(rgb, alpha: str = "FF") -> str:
    return "#%02X%02X%02X" % tuple(int(round(float(v))) for v in rgb[:3]) + alpha


def derive_text_fills(spec: dict, reference) -> list[dict]:
    """1b 후속 D — 글자색 · 세로 그라데이션을 컨셉에서 결정적으로 뽑는다(게이지 채움 B ① 과 같은 방식, LLM · codex 없음).

    TextBlock 의 bbox_intent 안에서 글자 획(fidelity.text_ink — L* Otsu 의 적은 쪽, 획 안쪽)을 찾아 줄마다 대표색을 보고,
    위 25 % 줄 ↔ 아래 25 % 줄의 ΔE00 이 8 이상이면 font.gradient{top_color, bottom_color} + font.color 흰색(틴트 없음 — 알파는 유지),
    아니면 font.color = 획 전체 대표색(그라데이션은 지움). 글자를 못 찾으면 LLM 값 그대로. → 바꾼 기록 목록(spec 은 제자리에서 바뀐다)."""
    import numpy as np
    from PIL import Image
    from core import color
    from gen import fidelity
    with Image.open(reference) as im:
        ref = np.asarray(im.convert("RGB"))
    H, W = ref.shape[:2]
    out = []
    for w in spec.get("widgets", []):
        if w.get("type") != "TextBlock" or not w.get("bbox_intent"):
            continue
        t = w.get("text") or {}
        if not (t.get("value") or t.get("sample")):
            continue
        x, y, bw, bh = (float(v) for v in w["bbox_intent"])
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(W, int(np.ceil(x + bw))), min(H, int(np.ceil(y + bh)))
        rec = {"widget": w["id"], "box": [x0, y0, x1 - x0, y1 - y0]}
        if x1 - x0 < 4 or y1 - y0 < 4:
            out.append({**rec, "skipped": "box too small"})
            continue
        crop = ref[y0:y1, x0:x1].astype(float)
        ink = fidelity.text_ink(crop)
        if ink is None:
            out.append({**rec, "skipped": "no glyph pixels found"})
            continue
        font = w.setdefault("font", {})
        alpha = spec_mod.canon_color(font.get("color") or "#FFFFFFFF")[7:9]
        rows = np.where(ink.sum(axis=1) >= 2)[0]
        whole = np.median(crop[ink], axis=0)
        rec.update(ink_pixels=int(ink.sum()), rows=int(len(rows)), old_color=font.get("color"), old_gradient=font.get("gradient"))
        n = max(1, int(round(len(rows) * TEXT_BAND)))
        if len(rows) >= 4:
            top_rows, bot_rows = rows[:n], rows[-n:]
            top = np.median(crop[top_rows][ink[top_rows]], axis=0)
            bot = np.median(crop[bot_rows][ink[bot_rows]], axis=0)
            de = float(color.delta_e00(color.srgb_to_lab(top), color.srgb_to_lab(bot)))
            rec["top_bottom_de00"] = round(de, 2)
        else:
            de = 0.0
        if de >= TEXT_GRADIENT_MIN_DE:
            font["gradient"] = {"top_color": _hex(top), "bottom_color": _hex(bot)}
            font["color"] = "#FFFFFF" + alpha
            rec["gradient"] = font["gradient"]
        else:
            font.pop("gradient", None)
            font["color"] = _hex(whole, alpha)
            rec["color"] = font["color"]
        out.append(rec)
    return out


GLOW_PAD = 16          # 글자 상자 밖으로 이만큼 넓혀 획 둘레 밝기를 잰다
GLOW_BG = (10, 14)     # 바탕 = 획에서 이 거리 띠의 밝기 중앙값
GLOW_PEAK = (2, 6)     # 빛 판정 = 이 거리 띠들 중 가장 밝은 띠의 (밝기 − 바탕)
GLOW_TAIL_L = 3.0      # 빛 끝 = 바탕보다 이만큼 밝은 마지막 거리
GLOW_MAX = 16
GLOW_GAMMA = 1.5       # WidgetMcpTextMaterials M_TextGlow 기본 Gamma 와 같게(불투명도 = 알파 × (1 − d / size)^Gamma)


def derive_text_glow(spec: dict, reference, roles: dict[str, dict], min_excess: float = 8.0) -> list[dict]:
    """1b 후속 F — 글자 둘레로 번지는 빛을 컨셉에서 결정적으로(LLM · codex 없음).

    TextBlock 마다 bbox_intent(+16 px) 안 글자 획(fidelity.text_ink)에서 거리별 밝기(L) 띠를 재 바탕(10 ~ 14 px 띠)과 비교한다.
    2 ~ 6 px 띠 중 가장 밝은 것이 바탕보다 min_excess 이상 밝으면 빛: size = 바탕보다 3 이상 밝은 마지막 거리 + 1,
    색 G = 바탕 B 에서 2 ~ 3 px 띠 색 C 쪽으로 한 채널이 255 에 닿을 때까지 민 색(k 배), 알파 = 1 / (k × (1 − 2.5 / size)^1.5)(0.15 ~ 1)
    → font.glow{size, color} + font.family = 그 역할의 sdf_family(빛은 거리장 글꼴의 외곽선 층으로 그린다 — WidgetMcpTextMaterials).
    빛이 없거나 SDF 폰트가 없으면 font.glow 를 지운다(LLM 값은 쓰지 않음). 외곽선과 같이 못 쓰므로 빛이면 outline 을 지운다(기록).
    → 기록 목록(spec 은 제자리에서 바뀐다)."""
    import cv2
    import numpy as np
    from PIL import Image
    from gen import fidelity
    from gen.concept_fill import luminance
    with Image.open(reference) as im:
        ref = np.asarray(im.convert("RGB")).astype(float)
    H, W = ref.shape[:2]
    by_family = {v["family"]: (r, v) for r, v in roles.items()}
    out = []
    for w in spec.get("widgets", []):
        if w.get("type") != "TextBlock" or not w.get("bbox_intent"):
            continue
        t = w.get("text") or {}
        if not (t.get("value") or t.get("sample")):
            continue
        font = w.setdefault("font", {})
        llm_glow = font.pop("glow", None)
        x, y, bw, bh = (float(v) for v in w["bbox_intent"])
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(W, int(np.ceil(x + bw))), min(H, int(np.ceil(y + bh)))
        rec = {"widget": w["id"], **({"llm_glow_dropped": llm_glow} if llm_glow else {})}
        if x1 - x0 < 4 or y1 - y0 < 4:
            out.append({**rec, "skipped": "box too small"})
            continue
        ink = fidelity.text_ink(ref[y0:y1, x0:x1])
        if ink is None:
            out.append({**rec, "skipped": "no glyph pixels found"})
            continue
        px0, py0, px1, py1 = max(0, x0 - GLOW_PAD), max(0, y0 - GLOW_PAD), min(W, x1 + GLOW_PAD), min(H, y1 + GLOW_PAD)
        crop = ref[py0:py1, px0:px1]
        m = np.zeros(crop.shape[:2], bool)
        m[y0 - py0:y1 - py0, x0 - px0:x1 - px0] = ink
        dist = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 5)
        L = luminance(crop)

        def band(lo, hi):
            return (dist > lo) & (dist <= hi)
        bgm = band(*GLOW_BG)
        if not bgm.any():
            out.append({**rec, "skipped": "no background ring"})
            continue
        bg = float(np.median(L[bgm]))
        excess = {d: (float(np.median(L[band(d - 1, d)])) - bg) if band(d - 1, d).any() else 0.0 for d in range(1, GLOW_MAX + 1)}
        peak = max(excess[d] for d in range(GLOW_PEAK[0], GLOW_PEAK[1] + 1))
        rec.update(background_L=round(bg, 1), excess={d: round(v, 1) for d, v in excess.items() if d <= 12}, peak=round(peak, 1))
        if peak < min_excess:
            out.append({**rec, "glow": None})
            continue
        size = 2
        while size + 1 <= GLOW_MAX and excess[size + 1] >= GLOW_TAIL_L:
            size += 1
        size = max(3, size + 1)
        role, info = by_family.get(font.get("family"), (None, {}))
        sdf = info.get("sdf_family")
        if not sdf:
            out.append({**rec, "glow": None, "skipped": f"no SDF font for role {role!r} (fonts.roles.<role>.sdf_family)"})
            continue
        C = np.median(crop[band(1, 3)], axis=0)
        B = np.median(crop[bgm], axis=0)
        v = C - B
        pos = v > 1e-6
        if not pos.any():
            out.append({**rec, "glow": None, "skipped": "the ring is not brighter in any channel"})
            continue
        k = max(1.0, float(np.min((255.0 - B[pos]) / v[pos])))
        G = np.clip(B + k * v, 0, 255)
        wgt = (1.0 - 2.5 / size) ** GLOW_GAMMA
        alpha = float(np.clip(1.0 / (k * max(wgt, 1e-3)), 0.15, 1.0))
        glow = {"size": int(size), "color": _hex(G, "%02X" % int(round(alpha * 255)))}
        if (font.get("outline") or {}).get("size"):
            rec["outline_dropped"] = font.pop("outline")
        rec.update(glow=glow, old_family=font.get("family"), family=sdf, layout=_glow_layout(w, int(size)))
        font["glow"] = glow
        font["family"] = sdf
        out.append(rec)
    return out


def _glow_layout(w: dict, s: int) -> dict:
    """빛(외곽선 층 s px)은 TextBlock 상자를 사방 s 만큼 키우고 글자를 그 안에서 s 만큼 들인다([실측 F 에디터 — 위쪽 정렬 상자에서 글자가 s 아래로],
    ElementBatcher.cpp:1673-1676 · SlateFontRenderer.cpp:205). 글자가 컨셉 자리에 그대로 있게: bbox_intent 를 사방 s 넓히고, 슬롯 padding 을
    사방 s 줄인다(음수 가능 — 형제 자리 그대로, 빛만 이웃 위로 번진다). 캔버스 점 앵커 슬롯은 위치 += s(2·alignment − 1), 크기(고정이면) += 2s."""
    before = {"bbox": list(w["bbox_intent"]), "slot": copy.deepcopy(w.get("slot"))}
    x, y, bw, bh = (float(v) for v in w["bbox_intent"])
    w["bbox_intent"] = [x - s, y - s, bw + 2 * s, bh + 2 * s]
    slot = w.get("slot")
    how = "bbox only"
    if isinstance(slot, dict):
        kind = slot.get("kind")
        if kind == "canvas":
            a, al = slot.get("anchors") or [0, 0, 0, 0], slot.get("alignment") or [0, 0]
            if a[0] == a[2] and a[1] == a[3]:
                pos = slot.get("position") or [0, 0]
                slot["position"] = [pos[0] + s * (2 * al[0] - 1), pos[1] + s * (2 * al[1] - 1)]
                if not slot.get("auto_size") and slot.get("size"):
                    slot["size"] = [slot["size"][0] + 2 * s, slot["size"][1] + 2 * s]
                how = "canvas position/size"
            else:
                how = "bbox only (stretching canvas anchors)"
        elif kind in ("overlay", "vertical_box", "horizontal_box", "border", "size_box", "button"):
            p = slot.get("padding") or spec_mod.SLOT_DEFAULTS.get(kind, {}).get("padding") or [0, 0, 0, 0]
            slot["padding"] = [p[0] - s, p[1] - s, p[2] - s, p[3] - s]
            how = "slot padding"
    return {"how": how, "before": before, "bbox": w["bbox_intent"], "slot": copy.deepcopy(slot)}


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
    roles = config.font_roles(run.cfg, brief.get("font"))
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
        spec = apply_contract(raw, brief, roles)
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
    derived = derive_gauge_fills(spec, run.path("reference.png"), run.cfg.get("gauge_fill"))
    text_fills = derive_text_fills(spec, run.path("reference.png")) if (run.cfg.get("text_fill") or {}).get("enabled", True) else []
    tg = run.cfg.get("text_glow") or {}
    text_glows = derive_text_glow(spec, run.path("reference.png"), roles, float(tg.get("min_excess", 8.0))) if tg.get("enabled", True) else []
    if derived or text_fills or text_glows:
        schema.require("spec", spec)
        run.write_json("analyze/derived.json", {"gauge_fills": derived, "text_fills": text_fills, "text_glows": text_glows})
    run.write_json("spec.json", spec)
    run.write_json("specs/000.json", spec)
    overlay = draw_overlay(run, spec)
    n_codex = sum(1 for a in spec.get("assets", []) if a["provenance"] == "codex")
    n_extract = sum(1 for a in spec.get("assets", []) if a["provenance"] == "codex" and a.get("source_mode") == "extract")
    gauges = [d["widget"] for d in derived if d.get("fill_asset")]
    grads = sum(1 for t in text_fills if t.get("gradient"))
    solids = sum(1 for t in text_fills if t.get("color") and not t.get("gradient"))
    glows = [t["widget"] for t in text_glows if t.get("glow")]
    return (f"{len(spec['widgets'])} widgets, {len(spec.get('assets', []))} assets ({n_codex} codex, {n_extract} extract"
            f"{', gauge fill from the concept: ' + ','.join(gauges) if gauges else ''}"
            f"{f', text fill from the concept: {grads} gradient · {solids} solid' if grads or solids else ''}"
            f"{', text glow from the concept: ' + ','.join(glows) if glows else ''}) in {len(calls)} call(s) — "
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
