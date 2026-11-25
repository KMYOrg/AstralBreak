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
from stages import request
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
    """spec 스키마(`--json-schema` 로 — llm.cli_schema 가 $schema · $id 를 뺀다, [실측 1b-1] spec 스키마 통째로 통과)에서 파이프라인만 쓰는 것(버튼 칸 · 놓인 칸 ·
    파생 에셋 — Phase 3-2)을 뺀 것 — LLM 이 보는 어휘는 예전 그대로다."""
    s = copy.deepcopy(schema.schema("spec"))
    defs = s["$defs"]
    s["properties"].pop("button")
    s["properties"]["profile"]["enum"].remove("cell")
    defs.pop("button")
    wp = defs["widget"]["properties"]
    wp["type"]["enum"].remove(spec_mod.CELL_TYPE)
    wp.pop("class")
    wp.pop("props")
    wp.pop("overflow")
    bp = defs["binding"]["properties"]
    bp["kind"]["enum"] = [k for k in bp["kind"]["enum"] if k not in ("cell", "action")]
    bp["kind"].pop("description")
    bp.pop("selectable")
    ap = defs["asset"]["properties"]
    ap["provenance"]["enum"].remove("derived")
    ap.pop("derived")
    return s


def _contract_lines(brief: dict) -> list[str]:
    statics = {s["widget"]: s["value"] for s in brief.get("static_text", [])}
    lines = []
    placed = {c["widget"] for c in request.cells(brief)}
    for d in brief["dynamic_data"]:
        if d["widget"] in placed:                  # 놓인 칸은 파이프라인이 넣는다
            continue
        extra = f", format {d['format']}" if d.get("format") else ""
        st = f", static text {statics[d['widget']]!r}" if d["widget"] in statics else ""
        desc = f" — {d['desc']}" if d.get("desc") else ""
        if d.get("inside"):
            desc += f" — must be inside {d['inside']} (a descendant of it: they show and hide together)"
        if d["type"] == "progress" and d.get("widget_type") == "Image":
            desc += (" — a ring that the game empties by angle: an Image with its OWN source_mode extract asset (kind ornament, draw_as image, no nine_slice) whose box is "
                     "the outer circle of the ring; anything else drawn inside the ring (a band, a plate) belongs to the parent's own asset. The pipeline splits the "
                     "pixels between the two and adds the wipe itself — do not set brush.wipe or percent")
        if d.get("bar") is not None:
            desc += (" — a shaped bar: the drawn bar itself is this ProgressBar (a direct child of an Overlay), bbox_intent = the whole drawn bar including its tip. The "
                     "pipeline cuts the bar's own pixels and makes fill and empty part from them — set no background / fill / percent on it, and do not put any "
                     "Image, Border or extract asset over the bar (a frame Image is only for the drawing beside the bar)")
        if d.get("over"):
            desc += (f" — a small mark drawn on top of {d['over']}: an Image with its OWN source_mode extract asset (kind icon, draw_as image, no nine_slice) in the same "
                     f"Overlay, after {d['over']}; its box covers only the mark's strokes with 2-4 px around them and no other drawing. The pipeline splits the mark from the "
                     "drawing under it")
        if d.get("text_box"):
            desc += (f" — its text box is fixed by the request {[int(v) for v in d['text_box']]}: put it directly in an Overlay (or a CanvasPanel), justification left or right; the pipeline sets its slot")
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


def background_line(run) -> str:
    """1b 후속 H — normalize 의 배경 판정을 프롬프트로(ⓐ ⓑ 는 장면이 없다 — 보이는 것은 전부 UI)."""
    p = run.path("normalize.json")
    bg = ((run.read_json("normalize.json").get("background")) or {}) if p.is_file() else {}
    kind = bg.get("kind")
    if kind == "transparent":
        return "Concept background: transparent (a layered UI export) — there is no game scene; everything visible is UI."
    if kind == "flat":
        return (f"Concept background: one flat color {bg.get('key_color', '')} (UI drawn alone, shown here over black) — there is no game scene; "
                "everything visible is UI, including soft glows that fade into the background.")
    return "Concept background: a game scene behind the UI (a screenshot composite) — only the screen-space UI becomes widgets and assets."


def build_prompt(run, brief: dict, cfg: dict, retry: dict | None = None) -> str:
    profile = config.load_profile(brief["screen_type"])
    req = "\n".join(f"- {e['id']} ({e['kind']}){': ' + e['desc'] if e.get('desc') else ''}" for e in brief["required_elements"])
    w, h = brief["resolution"]
    gates = profile.get("gates") or {}
    note = profile.get("analyze_note") or "the scene behind the HUD is not UI"
    sizes = f"{w}×{h}" if profile.get("resolutions") == "canvas" else f"{w}×{h}, 2560×1080 and 1920×1200"
    cells = request.cell_lines(brief)
    parts = [
        f"Analyze the UI concept for run {run.run_id} into a widget spec.",
        f"Files (absolute paths — Read them):\n- reference: {run.path('reference.png').resolve().as_posix()} ({w}×{h}, the concept fitted to the canvas)\n"
        f"- brief: {run.path('brief.json').resolve().as_posix()}",
        f"Screen: {brief['screen_id']} — screen_type '{brief['screen_type']}' (background {profile.get('background', '?')}; {note}). "
        f"Canvas {w}×{h}. Description: {brief.get('text') or '-'}",
        background_line(run),
        "Contract (exact ids and widget types; the pipeline fills binding/text of these after you answer):\n" + "\n".join(_contract_lines(brief)),
        "Required elements:\n" + req,
        *(["Placed cells (the reference shows them; the pipeline puts them there itself — make no widget, region, text or asset for these boxes, and no region that spans them):\n"
           + "\n".join(cells)] if cells else []),
        f"Style keywords: {', '.join(brief.get('style_keywords') or []) or '-'}",
        font_lines(cfg, brief),
        f"Layout gates: region IoU ≥ {gates.get('iou_region_min')}, leaf IoU ≥ {gates.get('iou_leaf_min')}, "
        f"boxes thinner than {gates.get('small_px')} px by center distance ≤ {gates.get('small_center_max_px')} px, sibling overlap ≤ {gates.get('overlap_max_ratio')} "
        f"outside allow_overlap, nothing off-screen at {sizes}.",
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
    rules = spec_mod.input_rules(out["profile"])
    for w in out.get("widgets", []):                # 닦기는 파이프라인만 쓴다 — LLM 이 적은 것은 걷는다
        if rules and w.get("visibility") not in ("collapsed", "hidden"):      # 클릭을 받는 화면 — 보이기는 코드가 정한다(core/spec.default_visibility)
            w.pop("visibility", None)
        st = w.get("style") or {}
        for k in spec_mod.BRUSH_KEYS:
            if isinstance(st.get(k), dict):
                st[k].pop("wipe", None)
        if w.get("type") == "Image":
            st.pop("percent", None)
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
        if d["type"] == "progress" and w.get("type") == "Image" and isinstance((w.get("style") or {}).get("brush"), dict):
            # 원형 진행(고리, 11-23) — 닦기는 요청이 정한다. 중심은 자리 가운데로 두고 derive_radial_fills 가 컨셉에서 잰 원으로 바꾼다
            rad = d.get("radial") or {"mode": "clockwise"}
            bb = w.get("bbox_intent") or [0, 0, 2, 2]
            s = d.get("sample")
            w["style"]["brush"]["wipe"] = {"kind": "radial", "mode": rad["mode"], "track_alpha": float(rad.get("track_alpha", 0)),
                                           "center": [float(bb[2]) / 2, float(bb[3]) / 2]}
            w["style"]["percent"] = max(0.0, min(1.0, float(s))) if isinstance(s, (int, float)) and not isinstance(s, bool) else 1.0
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
            # 1b 후속 H — extract 에셋은 컨셉 픽셀을 오리므로(ⓐ ⓑ · 작은 요소는 codex 호출 없음, ⓒ 는 실루엣 시드 한 번) 상한은 generate 에만.
            # run 전체 codex 호출은 limits.codex_calls_per_run 이 막는다
            codex += int((a.get("source_mode") or "generate") != "extract")
            if not (a.get("prompt") or "").strip():
                errs.append(f"ASSET_PROMPT: codex asset '{a['asset_id']}' needs a prompt")
            rb = a.get("ref_bbox")
            if rb and (rb[2] <= 0 or rb[3] <= 0 or rb[0] < 0 or rb[1] < 0 or rb[0] + rb[2] > w + BBOX_TOLERANCE_PX or rb[1] + rb[3] > h + BBOX_TOLERANCE_PX):
                errs.append(f"ASSET_REF_BBOX: '{a['asset_id']}' ref_bbox {rb} is outside the canvas")
        elif a["provenance"] == "procedural" and not a.get("procedural"):
            errs.append(f"ASSET_PROCEDURAL: procedural asset '{a['asset_id']}' needs procedural{{shape, …}}")
        elif a["provenance"] == "procedural" and a["procedural"].get("shape") in ("concept_fill", "concept_end_cap"):
            errs.append(f"ASSET_PROCEDURAL: '{a['asset_id']}' — concept_fill is made by the pipeline from the concept; use gradient_bar or rounded_box for a gauge fill")
        elif a["provenance"] not in ("codex", "procedural"):
            errs.append(f"ASSET_PROVENANCE: '{a['asset_id']}' provenance '{a['provenance']}' — Phase 1b uses codex or procedural")
        if max(a["size"]) > 1024:
            errs.append(f"ASSET_SIZE: '{a['asset_id']}' size {a['size']} — keep textures ≤ 1024 px")
    if codex > MAX_CODEX_ASSETS:
        errs.append(f"ASSET_CODEX_COUNT: {codex} codex generate assets — at most {MAX_CODEX_ASSETS} (extract assets do not count; prefer procedural / rounded_box)")
    for wid in index:
        if wid in {d["widget"] for d in brief["dynamic_data"]}:
            continue
        if index[wid].get("binding"):
            errs.append(f"EXTRA_BINDING: '{wid}' has a binding the request does not list")
    users: dict[str, list[str]] = {}
    for wd in spec["widgets"]:
        for k, b in (wd.get("style") or {}).items():
            if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset"):
                users.setdefault(b["asset"], []).append(wd["id"])
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    for d in brief["dynamic_data"]:
        w = index.get(d["widget"])
        if w and d.get("inside"):
            p, chain = w.get("parent"), []
            while p and p in index and p not in chain:
                chain.append(p)
                p = index[p].get("parent")
            if d["inside"] not in chain:
                errs.append(f"NOT_INSIDE: '{d['widget']}' must be a descendant of '{d['inside']}' (they show and hide together) — its ancestors are {chain}")
        if w and d["type"] == "progress" and w.get("type") == "Image":
            brush = (w.get("style") or {}).get("brush") or {}
            a = assets.get(brush.get("asset"))
            if not a or a.get("source_mode") != "extract" or brush.get("draw_as", "image") != "image" or a.get("nine_slice"):
                errs.append(f"RADIAL_ASSET: '{d['widget']}' needs its own source_mode extract asset drawn as image (no nine_slice) — the ring is cut from the concept")
            elif users.get(brush["asset"], []) != [d["widget"]]:
                errs.append(f"RADIAL_ASSET: asset '{brush['asset']}' is shared by {users.get(brush['asset'])} — the ring '{d['widget']}' needs its own asset")
            if (index.get(w.get("parent")) or {}).get("type") != "Overlay":
                errs.append(f"RADIAL_PARENT: '{d['widget']}' must sit in an Overlay (layers on top of each other), its parent is {w.get('parent')!r}")
    errs += _bar_errors(spec, brief, index, assets)
    errs += request.cell_errors(spec, brief) + request.text_box_errors(spec, brief) + request.mark_errors(spec, brief)
    for d in brief["dynamic_data"]:
        w = index.get(d["widget"])
        parent = index.get(w.get("parent")) if w else None
        if d["type"] == "flag" and parent and parent.get("type") in BOX_PANELS:
            errs.append(f"FLAG_IN_BOX: '{d['widget']}' is a flag widget (the game collapses it) inside {parent['type']} '{parent['id']}' — toggling it "
                        f"moves or stretches its siblings; put it in an Overlay or give it its own canvas region")
    return errs


BAR_COVER = 0.6            # 컨셉에서 오리는 그림 상자의 이만큼이 모양 막대들이면 막대를 다시 그리는 그림


def _bar_errors(spec: dict, brief: dict, index: dict, assets: dict) -> list[str]:
    """모양 막대(메인 HUD, 11-24) — 막대는 Overlay 의 직계여야 하고(자리 = 여백), 막대 픽셀을 그리는 다른 그림이 있으면 안 된다(픽셀마다 주인 하나)."""
    want = [d["widget"] for d in brief["dynamic_data"] if d.get("bar") is not None]
    errs = []
    boxes = {}
    for wid in want:
        w = index.get(wid)
        if not w:
            continue
        if (index.get(w.get("parent")) or {}).get("type") != "Overlay":
            errs.append(f"BAR_PARENT: '{wid}' must be a direct child of an Overlay, its parent is {w.get('parent')!r}")
        if w.get("bbox_intent"):
            boxes[wid] = [float(v) for v in w["bbox_intent"]]
    if not boxes:
        return errs
    for w in spec["widgets"]:
        bb = w.get("bbox_intent")
        if w["id"] in want or not bb or float(bb[2]) * float(bb[3]) <= 0:
            continue
        used = [b["asset"] for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")]
        if not any((assets.get(a) or {}).get("source_mode") == "extract" for a in used):
            continue
        x, y, bw, bh = (float(v) for v in bb)
        cov = sum(max(0.0, min(x + bw, b[0] + b[2]) - max(x, b[0])) * max(0.0, min(y + bh, b[1] + b[3]) - max(y, b[1])) for b in boxes.values()) / (bw * bh)
        if cov >= BAR_COVER:
            errs.append(f"BAR_FRAME: '{w['id']}' draws an extract asset mostly over shaped bars ({cov:.0%} of its box) — remove it (the bars cut their own pixels)")
    return errs


def derive_bars(spec: dict, brief: dict, alpha) -> list[dict]:
    """메인 HUD(11-24) — 요청의 모양 막대(bar): 컨셉 알파에서 막대 자리 · 모양을 재(gen/silhouette.measure) 위젯 상자 · 슬롯 여백을 맞추고, 막대 텍스처(컨셉에서 오림)
    하나를 채움과 물들인 배경(빈 자리 = track 색)으로 넣는다. LLM 이 적은 브러시 · 그 에셋은 걷는다. 못 재면 StageError BAR_MEASURE(조용히 물러나지 않는다).
    픽셀 나누기는 layer · refine 이 같은 함수로. spec 은 제자리에서 바뀐다. → 기록."""
    from gen import silhouette
    want = {d["widget"]: d for d in brief.get("dynamic_data", []) if d.get("bar") is not None}
    if not want:
        return []
    if alpha is None:
        raise StageError("BAR_MEASURE", "the concept alpha is unknown (a scene composite) — shaped bars cannot be cut from it")
    index = spec_mod.widget_index(spec)
    try:
        ms = silhouette.measure(alpha, {wid: index[wid]["bbox_intent"] for wid in want})
    except silhouette.BarError as exc:
        raise StageError("BAR_MEASURE", str(exc), widget=exc.widget, box=index[exc.widget].get("bbox_intent")) from exc
    taken = {a["asset_id"] for a in spec.get("assets", [])}
    out = []
    for wid, d in want.items():
        w, m = index[wid], ms[wid]
        parent = index.get(w.get("parent")) or {}
        pb = parent.get("bbox_intent")
        if not pb:
            raise StageError("BAR_MEASURE", f"'{wid}': parent '{w.get('parent')}' has no bbox_intent", widget=wid)
        x, y, bw, bh = m["box"]
        pad = [x - pb[0], y - pb[1], pb[0] + pb[2] - (x + bw), pb[1] + pb[3] - (y + bh)]
        pad = [int(v) if float(v).is_integer() else round(float(v), 2) for v in pad]
        st = w.setdefault("style", {})
        rec = {"widget": wid, "old_bbox": list(w["bbox_intent"]), "old_slot": copy.deepcopy(w.get("slot")), "old_style": copy.deepcopy(st), "padding": pad, **m["record"]}
        aid, k = silhouette.asset_id(wid), 2
        while aid in taken:
            aid, k = f"{silhouette.asset_id(wid)}_{k}", k + 1
        taken.add(aid)
        track = spec_mod.canon_color((d.get("bar") or {}).get("track") or silhouette.DEFAULT_TRACK)
        w["bbox_intent"] = [x, y, bw, bh]
        w["slot"] = {"kind": "overlay", "padding": pad, "h_align": "fill", "v_align": "fill"}
        w["style"] = {"background": {"draw_as": "image", "asset": aid, "color": track}, "fill": {"draw_as": "image", "asset": aid},
                      "percent": st.get("percent", 1), "bar_fill_type": "left_to_right"}
        spec.setdefault("assets", []).append({"asset_id": aid, "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [bw, bh],
                                              "prompt": f"the shaped bar {wid} exactly as drawn", "ref_bbox": [x, y, bw, bh]})
        rec.update(asset=aid, track=track)
        out.append(rec)
    used = {b["asset"] for w in spec["widgets"] for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")}
    gone = [a["asset_id"] for a in spec["assets"] if a["asset_id"] not in used]
    if gone:                                    # LLM 이 막대에 준 에셋(이제 아무도 안 씀)
        spec["assets"] = [a for a in spec["assets"] if a["asset_id"] not in gone]
        out[0]["dropped_assets"] = gone
    return out


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
    canvas_slot = None
    if parent.get("type") == "CanvasPanel":
        # 1b 후속 J — 캔버스 부모(점 앵커만): 위치 · 크기를 잰 트랙 상자로(fixer 와 같은 식 — position += d + alignment × dsize)
        # [실측 J R20261117_201408 파티 HUD — analyze 가 HP 게이지를 Overlay 대신 PlayerArea 캔버스에 둬 컨셉 모양 채움을 건너뜀]
        slot = w.get("slot") or {}
        an, al = slot.get("anchors") or [0, 0, 0, 0], slot.get("alignment") or [0, 0]
        if slot.get("kind") != "canvas" or an[0] != an[2] or an[1] != an[3] or "position" not in slot or "size" not in slot:
            raise concept_fill.ConceptFillError(f"gauge '{w['id']}' canvas slot is not a point-anchored position/size slot")
        ox_, oy_, ow_, oh_ = (float(v) for v in w["bbox_intent"])
        d = [wx - ox_, wy - oy_]
        ds = [ww - ow_, wh - oh_]
        canvas_slot = {**slot, "position": [round(float(slot["position"][i]) + d[i] + float(al[i]) * ds[i], 1) for i in (0, 1)],
                       "size": [ww, wh]}
    aid = _new_asset_id(w, taken)
    tsize = list(m.get("texture_size") or [ww, wh])
    asset = {"asset_id": aid, "kind": "fill", "provenance": "procedural", "size": tsize, "procedural": {"shape": "concept_fill", **m["params"]},
             "source": f"concept fill shape inside frame '{frame['id']}' (track {m['widget_box']}, sample {st['percent']:g})"}
    rec = {"fill_asset": aid, "shape": "concept_fill", "end": end, "widget_box": m["widget_box"], "old_bbox": list(w["bbox_intent"]),
           "old_padding": (w.get("slot") or {}).get("padding"), "old_fill": st.get("fill"), "old_background": st.get("background"), **m["record"]}
    if m.get("percent") is not None:
        # 1b 후속 J — 미리보기 진행률 = 컨셉이 그린 진행률(채움 구간 ÷ 막대 폭) — 렌더가 컨셉 상태와 1:1(진단 비교). 런타임 값은 게임이 넣는다
        rec["sample_percent"] = st["percent"]
        st["percent"] = m["percent"]
        rec["preview_percent"] = m["percent"]
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
    if canvas_slot is not None:
        canvas_slot = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in canvas_slot.items()}
        canvas_slot["position"] = [int(v) if float(v).is_integer() else v for v in canvas_slot["position"]]
        w["slot"] = canvas_slot
        rec.update(canvas_slot={"position": canvas_slot["position"], "size": canvas_slot["size"]}, fill=st["fill"],
                   background_from=f"none — extracted frame '{frame['id']}' underneath")
    else:
        slot = w.setdefault("slot", {"kind": "overlay"})
        slot.update(padding=pad, h_align="fill", v_align="fill")
        rec.update(padding=pad, fill=st["fill"], background_from=f"none — extracted frame '{frame['id']}' underneath")
    if m.get("end_cap") and gcfg.get("end_cap", True):
        rec["end_cap"] = _add_end_cap(spec, w, parent, m, taken)
    return rec


END_CAP_SUFFIX = "EndCap"


def _add_end_cap(spec: dict, w: dict, parent: dict, m: dict, taken: set) -> dict:
    """1b 후속 L 다음 — 글자 지우기 마감 H4 (나)(사용자 결정 11-19): 가득 찬 게이지 끝 덮개 — 채움 위(같은 부모 · 게이지 바로 다음)에 Image 하나
    (<게이지>EndCap · procedural concept_end_cap — 컨셉 끝 장식 안쪽 호부터 바깥, 가장자리 분수 알파). 채움은 곧은 끝이라 중간 진행률은 컨셉 70 % 끝과 같고,
    100 % 에서 호를 넘는 부분을 이 덮개가 덮는다. 덮개 픽셀 = 판이 그리는 그림이라 중간 진행률엔 안 보인다. C++ · 바인딩 없음(넘침 장식 Image 와 같은 틀) —
    게이지가 런타임에 접히는(flag · 숨김) 위젯이면 덮개가 같이 안 접혀 만들지 않는다(기록). → 기록."""
    from gen import concept_fill
    if (w.get("binding") or {}).get("kind") == "flag" or w.get("visibility") in ("collapsed", "hidden"):
        return {"skipped": "the gauge itself can collapse at runtime — an end cap would stay visible"}
    es = m["end_cap"]
    box = concept_fill.end_cap_box(m["params"], es)
    c0, c1 = concept_fill.end_cap_cols(m["params"], es)
    aid = f"{_snake(w['id'])}_end_cap"
    k = 2
    while aid in taken:
        aid, k = f"{_snake(w['id'])}_end_cap_{k}", k + 1
    taken.add(aid)
    asset = {"asset_id": aid, "kind": "ornament", "provenance": "procedural", "size": [int(box[2]), int(box[3])],
             "procedural": {"shape": "concept_end_cap", **m["params"], "end_cap": es, "cap_cols": [int(c0), int(c1)]},
             "source": f"end cap of the concept gauge fill '{w['id']}' (end ornament arc depth {es['depth']}) — covers the straight fill end at 100%"}
    x, y, bw, bh = (int(v) for v in box)
    wid = f"{w['id']}{END_CAP_SUFFIX}"
    deco = {"id": wid, "type": "Image", "parent": w.get("parent"), "bbox_intent": [x, y, bw, bh], "style": {"brush": {"draw_as": "image", "asset": aid}}}
    if parent.get("type") == "CanvasPanel":
        slot = dict(w.get("slot") or {})
        al = slot.get("alignment") or [0, 0]
        gx, gy, gw, gh = (float(v) for v in w["bbox_intent"])
        pos = [round(float(slot["position"][0]) + (x - gx) + float(al[0]) * (bw - gw), 1), round(float(slot["position"][1]) + (y - gy) + float(al[1]) * (bh - gh), 1)]
        deco["slot"] = {**slot, "position": [int(v) if float(v).is_integer() else v for v in pos], "size": [bw, bh]}
        pairs = spec.setdefault("allow_overlap", [])
        for s_ in spec.get("widgets", []):
            sb = s_.get("bbox_intent")
            if s_.get("parent") == w.get("parent") and s_["id"] != wid and sb and \
                    min(x + bw, sb[0] + sb[2]) > max(x, sb[0]) and min(y + bh, sb[1] + sb[3]) > max(y, sb[1]):
                pr = sorted([wid, s_["id"]])
                if pr not in pairs:
                    pairs.append(pr)
    else:
        px, py, pw, ph = (float(v) for v in parent["bbox_intent"])
        pad = [x - px, y - py, (px + pw) - (x + bw), (py + ph) - (y + bh)]
        deco["slot"] = {"kind": "overlay", "padding": [int(v) if float(v).is_integer() else round(v, 1) for v in pad], "h_align": "fill", "v_align": "fill"}
    idx = next(i for i, x_ in enumerate(spec["widgets"]) if x_["id"] == w["id"])
    spec["widgets"].insert(idx + 1, deco)
    spec.setdefault("assets", []).append(asset)
    return {"widget": wid, "asset": aid, "box": [x, y, bw, bh], "depth": int(es["depth"]), "cols": [int(c0), int(c1)]}


GLOW_WORDS = ("glow", "halo", "aura", "bloom", "shine", "radian", "빛", "광채", "후광")
HIDDEN_GLOW_FALLOFF = 0.6      # [실측] 지난 컨셉 run 9 번 중 LLM 이 procedural 로 고른 8 번이 모두 0.6
HIDDEN_GLOW_ALPHA = 0xCC       # G 끝 run 4(사람 눈 — 게이지 빛이 가장 나음)의 값


def derive_hidden_glows(spec: dict, brief: dict, reference) -> list[dict]:
    """1b 후속 G2 — 컨셉에 안 보이는 빛(flag 이미지 · 시작값 false)을 codex 로 새로 그리면 run 마다 모양이 달라진다
    [실측 G 크기 끝 run 2] 지난 9 run 중 8 run 은 LLM 이 procedural soft_glow 를 골랐는데 이번 run 만 codex generate(2172×724 캡슐 후광) — 사용자 눈:
    G 끝 run 4 의 빛이 낫다. → 그런 에셋(codex · source_mode generate · 빛 낱말이 프롬프트 · 위젯 이름 · 요청 설명에 있음)은 결정적으로
    procedural soft_glow(falloff HIDDEN_GLOW_FALLOFF) — 크기 = 위젯 상자(긴 변 ≤ 1024), 색 = 그 자리 컨셉에서 밝고 채도 높은 픽셀의 중앙값
    (게이지 빛이면 채움 금색) + 알파 HIDDEN_GLOW_ALPHA. LLM 이 처음부터 procedural soft_glow 를 고른 숨은 빛도 같은 값으로 맞춘다(색 · 알파가 run 마다
    달랐다). spec 은 제자리에서 바뀐다. → 기록."""
    import numpy as np
    from PIL import Image
    hidden = {d["widget"]: d for d in brief.get("dynamic_data", []) if d.get("type") == "flag" and d.get("sample") is False}
    descs = {e["id"]: e.get("desc", "") for e in brief.get("required_elements", [])}
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    ref = None
    out = []
    for w in spec.get("widgets", []):
        if w.get("type") != "Image" or w["id"] not in hidden or not w.get("bbox_intent"):
            continue
        for key, brush in (w.get("style") or {}).items():
            a = assets.get(brush.get("asset")) if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) else None
            if not a:
                continue
            words = " ".join([str(a.get("prompt", "")), w["id"], str(hidden[w["id"]].get("desc", "")), descs.get(w["id"], "")]).lower()
            codex_glow = (a.get("provenance") == "codex" and a.get("source_mode") == "generate" and a.get("kind") != "icon"
                          and any(g in words for g in GLOW_WORDS))
            # LLM 이 procedural soft_glow 를 골라도 색 · 알파가 run 마다 다르다 — [실측 G2 전투 HUD run] #FFC45A(알파 1.0) → 게이지 둘레 번짐이 진함
            proc_glow = a.get("provenance") == "procedural" and (a.get("procedural") or {}).get("shape") == "soft_glow"
            if not (codex_glow or proc_glow):
                continue
            if ref is None:
                ref = np.asarray(Image.open(reference).convert("RGB")).astype(float)
            x, y, bw, bh = (float(v) for v in (a.get("ref_bbox") or w["bbox_intent"]))
            H, W = ref.shape[:2]
            crop = ref[max(0, int(y)):min(H, int(np.ceil(y + bh))), max(0, int(x)):min(W, int(np.ceil(x + bw)))].reshape(-1, 3)
            color = "#FFFFFF"
            if len(crop):
                mx, mn = crop.max(axis=1), crop.min(axis=1)
                sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
                pick = crop[(sat > 0.35) & (mx >= np.percentile(mx, 90))]
                if len(pick):
                    color = "#" + "".join("%02X" % int(round(v)) for v in np.median(pick, axis=0))
            ww, wh = float(w["bbox_intent"][2]), float(w["bbox_intent"][3])
            k = min(1.0, 1024.0 / max(ww, wh, 1.0))
            new = {"asset_id": a["asset_id"], "kind": a.get("kind", "ornament"), "provenance": "procedural",
                   "size": [max(4, int(round(ww * k))), max(4, int(round(wh * k)))],
                   "procedural": {"shape": "soft_glow", "color": color + "%02X" % HIDDEN_GLOW_ALPHA, "falloff": HIDDEN_GLOW_FALLOFF}}
            spec["assets"] = [new if s is a else s for s in spec["assets"]]
            assets[a["asset_id"]] = new
            out.append({"widget": w["id"], "asset": a["asset_id"], "was": {k2: a.get(k2) for k2 in ("provenance", "source_mode", "size", "prompt")},
                        "procedural": new["procedural"], "size": new["size"]})
    return out


def derive_gauge_fills(spec: dict, reference, gauge_cfg: dict | None = None, skip=()) -> list[dict]:
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
    for w in list(spec.get("widgets", [])):          # 끝 덮개(_add_end_cap)가 위젯을 끼워 넣는다 — 사본으로 돈다
        if w.get("type") != "ProgressBar" or not w.get("bbox_intent") or w["id"] in skip:      # skip = 모양 막대(derive_bars)
            continue
        st = w.setdefault("style", {})
        p, ftype = st.get("percent"), st.get("bar_fill_type", "left_to_right")
        rec = {"widget": w["id"], "percent": p, "bar_fill_type": ftype}
        if not isinstance(p, (int, float)) or ftype not in ("left_to_right", "right_to_left"):
            out.append({**rec, "skipped": "needs a sample percent and a horizontal fill"})
            continue
        parent = index.get(w.get("parent"))
        under = [s for s in spec["widgets"] if s.get("parent") == w.get("parent") and order.get(s["id"], 10 ** 9) < order[w["id"]]
                 and ((s.get("style") or {}).get("brush") or {}).get("asset") in extract_ids]
        frame = None
        if parent and parent.get("type") in ("Overlay", "CanvasPanel") and under:
            # 프레임 = 게이지 상자의 80 % 이상을 덮는 앞 형제 중 마지막(가장 위) — '바로 앞 형제'는 패널 전체 Overlay 에서 배지였다
            # [실측 J R20261117_203005 파티 HUD — PlayerPanel Overlay 의 앞 형제 = PortraitBadge → 막대가 측정 상자 밖]
            gx, gy, gw, gh = (float(v) for v in w["bbox_intent"])

            def cover(s):
                sx, sy, sw, sh = (float(v) for v in s["bbox_intent"])
                ix_ = max(0.0, min(gx + gw, sx + sw) - max(gx, sx)) * max(0.0, min(gy + gh, sy + sh) - max(gy, sy))
                return ix_ / max(1.0, gw * gh)
            fr = [s for s in under if s.get("bbox_intent") and cover(s) >= 0.8]
            frame = fr[-1] if fr else None
        if frame is None and parent and parent.get("type") in ("Overlay", "CanvasPanel") and float(p) >= concept_fill.FULL_MIN:
            frame = w     # 가득 찬 게이지는 둘레 프레임 선이 필요 없다 — 자기 상자를 넓혀 잰다(_measure_full FULL_PAD)
        if gcfg.get("mode", "shape") == "shape" and parent and parent.get("bbox_intent") and frame and frame.get("bbox_intent"):
            try:
                rec.update(_apply_concept_fill(spec, w, parent, frame, ref, taken, gcfg))
                out.append(rec)
                continue
            except concept_fill.ConceptFillError as exc:
                rec["shape_fallback"] = str(exc)
            except (ValueError, IndexError) as exc:      # 측정 결함이 analyze 를 죽이지 않게 — 예전 방식으로 물러남(기록)
                rec["shape_fallback"] = f"{type(exc).__name__}: {exc}"
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


def derive_radial_fills(spec: dict, alpha) -> list[dict]:
    """전투 HUD 동작(11-23) — progress 바인딩 Image(고리): 컨셉 알파에서 원을 재(gen/radial.measure) 위젯 상자 · 슬롯 여백 · 에셋 크기를 원 상자로 맞추고
    닦는 중심을 넣는다. 못 재면 StageError RADIAL_MEASURE(조용히 물러나지 않는다 — 고리가 안 닦이면 요청과 다르다). 픽셀 나누기는 layer · refine 이 같은 함수로.
    spec 은 제자리에서 바뀐다. → 기록."""
    from gen import radial
    index = spec_mod.widget_index(spec)
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    out = []
    for w in spec.get("widgets", []):
        wipe = ((w.get("style") or {}).get("brush") or {}).get("wipe")
        if w.get("type") != "Image" or not wipe or not w.get("bbox_intent"):
            continue
        if alpha is None:
            raise StageError("RADIAL_MEASURE", f"'{w['id']}': the concept alpha is unknown (a scene composite) — a ring cannot be split from it")
        parent = index.get(w.get("parent")) or {}
        pb = parent.get("bbox_intent")
        try:
            m = radial.measure(alpha, w["bbox_intent"])
        except radial.RadialError as exc:
            raise StageError("RADIAL_MEASURE", f"'{w['id']}': {exc}", widget=w["id"], box=w["bbox_intent"]) from exc
        x, y, bw, bh = m["box"]
        if not pb:
            raise StageError("RADIAL_MEASURE", f"'{w['id']}': parent '{w.get('parent')}' has no bbox_intent", widget=w["id"])
        pad = [x - pb[0], y - pb[1], pb[0] + pb[2] - (x + bw), pb[1] + pb[3] - (y + bh)]
        rec = {"widget": w["id"], "old_bbox": list(w["bbox_intent"]), "old_slot": copy.deepcopy(w.get("slot")), "box": list(m["box"]),
               "padding": [round(float(v), 2) for v in pad], **m["record"]}
        w["bbox_intent"] = [x, y, bw, bh]
        w["slot"] = {"kind": "overlay", "padding": [int(v) if float(v).is_integer() else round(float(v), 2) for v in pad], "h_align": "fill", "v_align": "fill"}
        brush = w["style"]["brush"]
        brush.pop("image_size", None)
        brush["wipe"] = {**wipe, "center": [round(m["center"][0] - x, 2), round(m["center"][1] - y, 2)]}
        a = assets[brush["asset"]]
        rec["asset"] = {"id": a["asset_id"], "size_old": list(a["size"])}
        a["size"] = [bw, bh]
        a["ref_bbox"] = [x, y, bw, bh]
        out.append(rec)
    return out


def apply_requested_outlines(spec: dict, brief: dict) -> list[dict]:
    """전투 HUD 동작(11-23) — 요청이 정한 글자 외곽선(data · static_text 의 outline): 글자 상자를 사방 그만큼 넓혀(_glow_layout — 글자 자리는 그대로) font.outline 에
    넣는다. 컨셉에서 잰 글자 효과를 정리한 뒤(strip_llm_text_effects) 부른다. 빛은 외곽선 층을 쓰므로 빼고 기록한다. → 기록."""
    index = spec_mod.widget_index(spec)
    out = []
    for wid, o in requested_outlines(brief).items():
        w = index.get(wid)
        if not w or w.get("type") != "TextBlock":
            continue
        f = w.setdefault("font", {})
        rec = {"widget": wid, "outline": dict(o)}
        if f.get("glow"):
            rec["glow_dropped"] = f.pop("glow")
        f["outline"] = dict(o)
        rec["layout"] = _glow_layout(w, int(o["size"]))
        pairs = _glow_overlap_pairs(spec, w, rec["layout"]["before"]["bbox"])
        if pairs:
            rec["allow_overlap_added"] = pairs
        out.append(rec)
    return out


def apply_declared_fonts(spec: dict, brief: dict, cfg: dict) -> list[dict]:
    """메인 HUD(11-24) — 글꼴로 그린 참고판이 정한 글꼴 값(declared_fonts)을 그대로 넣는다: 크기 · 굵기 · 색 · 본문 family, 자간 · 그라데이션 · 빛 없음(그릴 때 없었다).
    크기가 바뀌면 글자 상자를 가운데 기준으로 따라가게 한다(style.follow_text_boxes — 글자 맞춤 크기 판과 같음). 컨셉에서 잰 글자 값을 정리한 뒤, 요청 외곽선 앞에 부른다. → 기록."""
    from core import config as config_mod
    from stages import style
    index = spec_mod.widget_index(spec)
    before = copy.deepcopy(spec)
    family = config_mod.font_roles(cfg, brief.get("font"))["body"]["family"]
    out = []
    for wid, d in declared_fonts(brief).items():
        w = index.get(wid)
        if not w or w.get("type") != "TextBlock":
            continue
        f = w.setdefault("font", {})
        out.append({"widget": wid, "old": {k: f.get(k) for k in ("size", "weight", "color", "gradient", "glow", "letter_spacing") if f.get(k) is not None}, "font": dict(d)})
        for k in ("gradient", "glow", "letter_spacing", "shadow"):
            f.pop(k, None)
        f.update(size=d["size"], weight=d["weight"], color=d["color"], family=family)
    if out:
        followed = {r["widget"]: r for r in style.follow_text_boxes(before, spec, cfg)}
        for r in out:
            if r["widget"] in followed:
                r["box"] = followed[r["widget"]].get("bbox") or followed[r["widget"]].get("skipped")
    return out


def declared_fonts(brief: dict) -> dict[str, dict]:
    """글꼴로 그린 참고판이 정한 글꼴 값 — 위젯 id → {size, weight, color}."""
    return {x["widget"]: x["font"] for x in (*brief.get("dynamic_data", []), *brief.get("static_text", [])) if x.get("font")}


def requested_outlines(brief: dict) -> dict[str, dict]:
    """요청이 정한 외곽선 — 위젯 id → {size, color}."""
    return {**{d["widget"]: d["outline"] for d in brief.get("dynamic_data", []) if d.get("outline")},
            **{s["widget"]: s["outline"] for s in brief.get("static_text", []) if s.get("outline")}}


def _art_layers(run):
    """컨셉의 (곧은 색, 알파) — 글자 없는 아트(layer · refine 과 같은 것, 표시를 걷기 전). 장면 합성이면 (None, None)."""
    from stages import generate
    from stages.refine import _reference_layers
    bg = generate.background_kind(run)
    if bg not in ("transparent", "flat") or not run.path("reference_alpha.png").is_file():
        return None, None
    return _reference_layers(run, bg, marks=False)


def _art_alpha(run):
    """컨셉 알파 또는 None(장면 합성)."""
    return _art_layers(run)[1]


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


def snap_weights(spec: dict, cfg: dict) -> list[dict]:
    """1b 후속 K — 글자 굵기를 그 family 가 가진 굵기로(fonts.weight_density — 밀도가 가장 가까운 것). 없는 굵기를 고르면 엔진이 첫 타입페이스로
    바꿔 그려 글자 맞춤이 고칠 수 없었다. → 기록(바꾼 것만)."""
    from gen import diagnose
    out = []
    for w in spec.get("widgets", []):
        f = w.get("font") if isinstance(w.get("font"), dict) else None
        if w.get("type") != "TextBlock" or not f:
            continue
        table = diagnose.weight_table(cfg, f.get("family"))
        cur = f.get("weight") or "bold"
        if not table or cur in table:
            continue
        ref = {"light": 0.85, "regular": 1.0, "medium": 1.18, "semibold": 1.33, "bold": 1.49, "extrabold": 1.63, "black": 1.7,
               "italic": 1.0, "bold_italic": 1.49}.get(cur, 1.0)
        import math
        new = min(table, key=lambda k: abs(math.log(table[k] / ref)))
        f["weight"] = new
        out.append({"widget": w["id"], "weight_snapped": [cur, new]})
    return out


def _notext_black(run, spec: dict | None = None):
    """normalize 가 컨셉에 정합한 글자 없는 판(곧은 색 × 알파 — reference.png 와 같은 검정 위) 또는 None (1b 후속 K — 빛 바탕)."""
    import numpy as np
    from PIL import Image
    try:
        nt = (run.read_json("normalize.json").get("background") or {}).get("notext") or {}
    except (OSError, ValueError):
        return None
    if not nt.get("used") or not run.path(str(nt.get("color"))).is_file() or not run.path(str(nt.get("alpha"))).is_file():
        return None
    with Image.open(run.path(nt["color"])) as c, Image.open(run.path(nt["alpha"])) as a:
        col, alpha = np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0
    from gen import diagnose
    if spec is not None and not diagnose.residue_free(nt) and run.path("reference_alpha.png").is_file() and run.path("reference_color.png").is_file():
        # 투명 위 글자 자리의 판 잔상은 지우고 잰다(진단 · refine 과 같은 함수) — 잔상이 바탕이면 그 글자의 빛을 못 잰다 [실측 K R20261117_234013 '오의 불가']
        # (L-2 원본 아트는 글자를 그린 적 없어 건너뜀 — diagnose.residue_free)
        with Image.open(run.path("reference_color.png")) as c, Image.open(run.path("reference_alpha.png")) as a:
            col, alpha, _ = diagnose.clear_text_residue(col, alpha, np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0, spec)
    return col * alpha[..., None]


def derive_text_glow(spec: dict, reference, roles: dict[str, dict], min_excess: float = 8.0, background=None) -> list[dict]:
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
        # 1b 후속 K E7 — 빛은 진단 · 글자 맞춤과 같은 함수(diagnose.glow_measure)로: 바탕 = 같은 자리의 글자 없는 판(있으면) — 예전 '획 10 ~ 14 px 밖
        # 띠 밝기' 바탕은 두 톤 띠 위 글자에서 띠 밝기를 빛으로 봤다 [실측 J 남은 일 사람 눈 — '돌진 공격' · '공격' 컨셉에 없는 청록 빛]
        from gen import diagnose
        bgc = background[py0:py1, px0:px1] if background is not None else None
        gmz = diagnose.glow_measure(crop, bgc, m, min_excess)
        if gmz is None:
            out.append({**rec, "skipped": "no glyph pixels found"})
            continue
        peak, size = gmz["peak"], gmz["size"]
        rec.update(background_L=round(bg, 1), excess=gmz["excess"], peak=peak, glow_background="text-free plate" if bgc is not None else "ring 10-14 px")
        if not gmz["present"]:
            out.append({**rec, "glow": None})
            continue
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
        pairs = _glow_overlap_pairs(spec, w, rec["layout"]["before"]["bbox"])
        if pairs:
            rec["allow_overlap_added"] = pairs
        out.append(rec)
    return out


def _glow_overlap_pairs(spec: dict, w: dict, before) -> list[list[str]]:
    """빛 여백(투명)으로 넓힌 글자 상자가 원래 줄 상자로는 안 겹치던 형제와 겹치면 그 쌍을 allow_overlap 에 넣는다 — 빛이 이웃 위로 번지는 것은
    배치 충돌이 아니다. [실측 J R20261117_185327 · 185828 · 190342 — 단색 컨셉 '오의 불가' 줄 상자 871 ~ 929 ↔ 게이지 영역 930 ~, 빛 8 px 로 넓힌
    상자가 10 % 겹쳐 overlap 게이트에서 세 번 연속 멈춤]. → 더한 쌍."""
    def inter(a, b):
        return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])
    out = []
    bb = w.get("bbox_intent")
    for o in spec.get("widgets", []):
        ob = o.get("bbox_intent")
        if o["id"] == w["id"] or o.get("parent") != w.get("parent") or not ob or not bb:
            continue
        if inter(bb, ob) and not inter(before, ob):
            pair = sorted([w["id"], o["id"]])
            if pair not in spec.setdefault("allow_overlap", []):
                spec["allow_overlap"].append(pair)
                out.append(pair)
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


BUTTON_LABEL_FONT_DIR = config.UIGEN_DIR / "work" / "_fonts" / "pretendard"      # make_concept.FONT_DIR 와 같은 곳(엔진 폰트를 임포트한 원본 TTF)


def _label_size(cfg: dict, font: dict, value: str) -> list[int]:
    """버튼 글자의 예상 상자(px) — 폭 = 같은 TTF 로 잰 글자 폭(없으면 크기로 어림), 높이 = 줄 높이 표. 자동 크기 글자라 배치 게이트의 기준 상자로만 쓴다(외곽선 몫은
    apply_requested_outlines 가 넓힌다)."""
    from stages import style
    px = float(font["size"]) * 4.0 / 3.0
    w = None
    try:
        from PIL import ImageFont

        from gen import text_ref
        f = BUTTON_LABEL_FONT_DIR / text_ref.FONT_FILES[font["weight"]]
        if f.is_file():
            w = float(ImageFont.truetype(str(f), px).getlength(value))
    except (ImportError, OSError, KeyError):
        pass
    w = w if w is not None else len(value) * px * 0.9
    h = style._line_height(cfg, (cfg.get("fonts") or {}).get("default_family"), float(font["size"])) or px * 1.2
    return [int(round(w)), int(round(h))]


def button_spec(brief: dict, cfg: dict) -> dict:
    """버튼 칸의 spec(Phase 3-2) — 구조가 요청으로 다 정해져 있어 LLM 이 판단할 것이 없다: 기본 그림 하나(칸 전체 — 컨셉에서 오림) + 가운데 글자 하나 + 파생 상태 그림 여섯.
    글자 값은 글꼴 단일 원천(참고판)과 공용 테마가 정하고, 자리는 칸 가운데에 자동 크기로 둔다(글자 길이가 달라져도 가운데) — 미세한 자리는 글자 맞춤이 컨셉 획에서 잰다."""
    from core import button as button_mod
    from gen import theme as theme_mod
    b = brief["button"]
    t = theme_mod.load(b["theme"])
    w, h = (int(v) for v in brief["resolution"])
    d = next(x for x in brief["dynamic_data"] if x["widget"] == b["label"])
    base = _snake(b["art"])
    lw, lh = _label_size(cfg, d["font"], _sample_text(d))
    spec = {"schema_version": 1, "canvas": [w, h], "profile": brief["screen_type"], "root": "Root",
            "widgets": [
                {"id": "Root", "type": "CanvasPanel"},
                {"id": b["art"], "type": "Image", "parent": "Root", "bbox_intent": [0, 0, w, h],
                 "slot": {"kind": "canvas", "anchors": [0, 0, 1, 1], "position": [0, 0], "size": [0, 0]}, "style": {"brush": {"draw_as": "image", "asset": base}}},
                {"id": b["label"], "type": "TextBlock", "parent": "Root", "bbox_intent": [(w - lw) // 2, (h - lh) // 2, lw, lh],
                 "slot": {"kind": "canvas", "anchors": [0.5, 0.5, 0.5, 0.5], "alignment": [0.5, 0.5], "position": [0, 0], "size": [lw, lh], "z": 1, "auto_size": True},
                 "justification": "center", "font": {"size": d["font"]["size"], "weight": d["font"]["weight"], "color": d["font"]["color"]}}],
            "assets": [{"asset_id": base, "kind": "panel_bg", "provenance": "codex", "source_mode": "extract", "size": [w, h], "prompt": "the whole button exactly as drawn",
                        "ref_bbox": [0, 0, w, h], "compression": "TC_EditorIcon"}],
            # 글자는 기본 그림 위에 놓인다(둘 다 루트 직계 — 그림은 에디터 트리에 없다)
            "allow_overlap": [sorted([b["art"], b["label"]])],
            "button": {"art": b["art"], "states": {}, "theme": {"id": t["id"], "sha256": t["sha256"]}, "pressed_offset": list(t["text"]["pressed_offset"])}}
    for k in button_mod.DERIVED:
        aid = button_mod.derived_asset_id(base, k)
        spec["button"]["states"][k] = aid
        spec["assets"].append({"asset_id": aid, "kind": "panel_bg", "provenance": "derived", "derived": {"from": base, "brush": k}, "size": [w, h],
                               "compression": "TC_EditorIcon", "source": f"theme '{t['id']}' state {k} of {base}"})
    return apply_contract(spec, brief, config.font_roles(cfg, brief.get("font")))


def _run_button(run, brief: dict) -> str:
    """버튼 칸 — LLM 0(요약 기록은 호출 0 번으로 남긴다)."""
    spec = button_spec(brief, run.cfg)
    errors = schema.errors("spec", spec) or (spec_mod.validate_semantics(spec) + check_brief_vs_spec(brief, spec))
    run.write_json("analyze.json", {**_record(run, [], errors, []), "ok": not errors, "skipped": "button cell — the request fixes the structure, no LLM call"})
    if errors:
        raise StageError("ANALYZE_INVALID", f"the button spec failed {len(errors)} check(s): " + "; ".join(errors[:6]), errors=errors)
    fonts = apply_declared_fonts(spec, brief, run.cfg)
    outlines = apply_requested_outlines(spec, brief)
    schema.require("spec", spec)
    run.write_json("analyze/derived.json", {"gauge_fills": [], "text_fills": [], "text_glows": [], "hidden_glows": [], "text_effects_dropped": [], "fonts": fonts,
                                            "outlines": outlines})
    run.write_json("spec.json", spec)
    run.write_json("specs/000.json", spec)
    overlay = draw_overlay(run, spec)
    b = spec["button"]
    return (f"button cell — {len(spec['widgets'])} widgets, {len(spec['assets'])} assets ({len(b['states'])} states from theme '{b['theme']['id']}' {b['theme']['sha256'][:8]}), "
            f"no LLM call (the request fixes the structure){', overlay ' + overlay if overlay else ''}")


def run(run, opts) -> str:
    brief = run.read_json("brief.json")
    if not run.path("reference.png").is_file():
        raise StageError("NO_REFERENCE", "analyze needs reference.png (normalize concept)")
    if brief.get("button"):
        return _run_button(run, brief)
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
        spec = request.place_cells(apply_contract(raw, brief, roles), brief)
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
    anchors = request.apply_anchor_regions(spec, brief)
    marks = request.derive_marks(spec, brief, *_art_layers(run)) if request.marks(brief) else []
    bars = derive_bars(spec, brief, _art_alpha(run)) if any(d.get("bar") is not None for d in brief["dynamic_data"]) else []
    hidden_glows = derive_hidden_glows(spec, brief, run.path("reference.png"))
    derived = derive_gauge_fills(spec, run.path("reference.png"), run.cfg.get("gauge_fill"), skip={b["widget"] for b in bars})
    text_fills = derive_text_fills(spec, run.path("reference.png")) if (run.cfg.get("text_fill") or {}).get("enabled", True) else []
    tg = run.cfg.get("text_glow") or {}
    text_glows = derive_text_glow(spec, run.path("reference.png"), roles, float(tg.get("min_excess", 8.0)), background=_notext_black(run, spec)) \
        if tg.get("enabled", True) else []
    text_effects = strip_llm_text_effects(spec) if (run.cfg.get("text_style") or {}).get("deterministic_only", True) else []
    text_effects += snap_weights(spec, run.cfg)
    radials = derive_radial_fills(spec, _art_alpha(run)) if any(((w.get("style") or {}).get("brush") or {}).get("wipe") for w in spec["widgets"]) else []
    fonts = apply_declared_fonts(spec, brief, run.cfg)
    outlines = apply_requested_outlines(spec, brief)
    boxes = request.apply_text_boxes(spec, brief, run.cfg)
    if derived or text_fills or text_glows or hidden_glows or text_effects or radials or outlines or bars or fonts or anchors or marks or boxes or request.cells(brief):
        schema.require("spec", spec)
        run.write_json("analyze/derived.json", {"gauge_fills": derived, "text_fills": text_fills, "text_glows": text_glows, "hidden_glows": hidden_glows,
                                                "text_effects_dropped": text_effects, **({"radials": radials} if radials else {}),
                                                **({"bars": bars} if bars else {}),
                                                **({"fonts": fonts} if fonts else {}),
                                                **({"outlines": outlines} if outlines else {}),
                                                **({"anchors": anchors} if anchors else {}), **({"marks": marks} if marks else {}),
                                                **({"text_boxes": boxes} if boxes else {})})
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
            f"{', ring measured: ' + ','.join(r['widget'] + ' r ' + str(r['radius']) for r in radials) if radials else ''}"
            f"{', bars cut from the concept: ' + ','.join(b['widget'] for b in bars) if bars else ''}"
            f"{f', {len(request.cells(brief))} cell(s) placed by the request' if request.cells(brief) else ''}"
            f"{', mark split from its background: ' + ','.join(m['widget'] for m in marks) if marks else ''}"
            f"{f', fonts declared by the drawn text reference: {len(fonts)}' if fonts else ''}"
            f"{f', text fill from the concept: {grads} gradient · {solids} solid' if grads or solids else ''}"
            f"{', text glow from the concept: ' + ','.join(glows) if glows else ''}"
            f"{', hidden glow → procedural soft_glow: ' + ','.join(h['asset'] for h in hidden_glows) if hidden_glows else ''}) in {len(calls)} call(s) — "
            f"API list-price equivalent {summary['cost_usd']:.3f} USD (subscription login — plan usage, not billed), model {summary['model']}"
            f"{', overlay ' + overlay if overlay else ''}")


def strip_llm_text_effects(spec: dict) -> list[dict]:
    """1b 후속 J-c — 글자 스타일은 결정적 측정만: LLM(analyze)이 고른 글자 외곽선 · 그림자는 걷는다(색 · 그라데이션 · 빛은 derive_text_fills ·
    derive_text_glow 가 컨셉에서 재고, 크기 · 굵기 · 자리는 글자 맞춤이 잰다). [실측 J-b 기준선 R20261117_095249 · 120813] analyze 가 넣은 남색 외곽선
    1 px 가 진단에서 획 안 어두운 비율 0.17 ~ 0.5(컨셉 0 ~ 0.07)로 남았다. → 기록."""
    out = []
    for w in spec.get("widgets", []):
        f = w.get("font")
        if w.get("type") not in ("TextBlock", "RichTextBlock") or not isinstance(f, dict):
            continue
        rec = {k: f.pop(k) for k in ("outline", "shadow") if f.get(k)}
        if rec:
            out.append({"widget": w["id"], **rec})
    return out


def _record(run, calls: list[dict], errors: list[str], retry_reasons: list[str]) -> dict:
    summary = {"calls": len(calls), "cost_usd": round(sum(float(c.get("cost_usd") or 0) for c in calls), 4),
               "duration_s": round(sum(float(c.get("duration_s") or 0) for c in calls), 2),
               "model": next((c.get("model") for c in reversed(calls) if c.get("model")), None),
               "retry_reasons": retry_reasons[:20], "final_errors": errors[:20], "attempts": calls,
               "ok": not errors and bool(calls) and all("error" not in c for c in calls)}
    run.write_json("analyze.json", summary)
    return summary
