"""normalize — 입력을 brief · spec 으로 (설계 §2-2).

1a(hand_spec): 손으로 쓴 brief.json · spec.json 이 든 폴더를 받아 검사하고 run 폴더로 복사한다. analyze 는 건너뛴다(spec 이 이미 있다).
1b(concept): inputs.yaml(schemas/inputs) + 컨셉 PNG → reference.png(기준 해상도로 맞춤) · brief.json. spec 은 analyze 가 만든다.
  - 맞추기: 비율 차이 ≤ 1 % 면 늘림(stretch), 넘으면 가운데 맞춤 + 검은 띠(letterbox) — normalize.json 에 변환을 남긴다.
  - brief: 계약(바인딩 위젯 이름 · 위젯 타입 · 데이터 · 고정 글자)은 inputs 가 정한 그대로, 폰트 기본값은 pipeline.yaml fonts.default_family.
text · multi_ref 는 Phase 3.

검사: 스키마 · spec 의미 검사 · brief ↔ spec 맞물림(필수 요소 · 바인딩 계약 · 동적 데이터 · 고정 글자). 하나라도 어긋나면 run 을 시작하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from core import config
from core import schema
from core import spec as spec_mod
from stages import StageError

ASPECT_STRETCH_MAX = 0.01   # 비율 차이가 이보다 작으면 늘린다(컨셉 1672×941 → 1920×1080 은 0.06 %)


def _load(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError("INPUT_UNREADABLE", f"{path}: {exc}") from exc


def check_brief_vs_spec(brief: dict, spec: dict) -> list[str]:
    errs: list[str] = []
    index = spec_mod.widget_index(spec)
    if brief["screen_type"] != spec["profile"]:
        errs.append(f"PROFILE: brief.screen_type '{brief['screen_type']}' != spec.profile '{spec['profile']}'")
    if list(brief["resolution"]) != [int(v) for v in spec["canvas"]]:
        errs.append(f"CANVAS: brief.resolution {brief['resolution']} != spec.canvas {spec['canvas']}")
    for el in brief["required_elements"]:
        if el["id"] not in index:
            errs.append(f"REQUIRED_MISSING: '{el['id']}' ({el.get('desc', el['kind'])}) is not in the spec")
    bound = spec_mod.bound_widgets(spec)
    contract = brief.get("binding_contract")
    if contract and set(contract["bindings"]) != set(bound):
        errs.append(f"CONTRACT: binding_contract {sorted(contract['bindings'])} != spec bindings {sorted(bound)}")
    for d in brief["dynamic_data"]:
        b = bound.get(d["widget"])
        if not b:
            errs.append(f"DATA_UNBOUND: dynamic_data '{d['id']}' → '{d['widget']}' has no binding in the spec")
            continue
        if b["data"] != d["id"] or b["kind"] != d["type"]:
            errs.append(f"DATA_MISMATCH: '{d['widget']}' binding {b['data']}/{b['kind']} != brief {d['id']}/{d['type']}")
        if d["type"] == "number" and d.get("format") != b.get("format"):
            errs.append(f"DATA_FORMAT: '{d['widget']}' format {b.get('format')} != brief {d.get('format')}")
    data_ids = {d["id"] for d in brief["dynamic_data"]}
    for wid, b in bound.items():
        if b["data"] not in data_ids:
            errs.append(f"BINDING_NOT_IN_BRIEF: '{wid}' binds '{b['data']}' which brief.dynamic_data does not list")
    for st in brief.get("static_text", []):
        w = index.get(st["widget"])
        if not w or w.get("type") != "TextBlock":
            errs.append(f"STATIC_TEXT: '{st['widget']}' is not a TextBlock in the spec")
        elif (w.get("text") or {}).get("value") != st["value"]:
            errs.append(f"STATIC_TEXT: '{st['widget']}' text {(w.get('text') or {}).get('value')!r} != brief {st['value']!r}")
    for d in brief["dynamic_data"]:   # concept 모드 — 바인딩 위젯 타입은 요청이 고정한다(codegen 계약)
        w = index.get(d["widget"])
        if d.get("widget_type") and w and w.get("type") != d["widget_type"]:
            errs.append(f"WIDGET_TYPE: '{d['widget']}' is a {w.get('type')} in the spec, the request fixes {d['widget_type']} (BindWidget contract)")
    return errs


def run(run, opts) -> str:
    if getattr(opts, "inputs", None):
        return run_concept(run, opts)
    return run_hand_spec(run, opts)


def _inputs_errors(inputs: dict) -> list[str]:
    """스키마로 못 보는 inputs 의 맞물림 — 계약이 스스로 모순되면 run 을 시작하지 않는다."""
    errs: list[str] = []
    data = inputs["data"]
    for key in ("id", "widget"):
        vals = [d[key] for d in data]
        dup = sorted({v for v in vals if vals.count(v) > 1})
        if dup:
            errs.append(f"DATA_DUPLICATE: data[].{key} {dup}")
    req = [e["id"] for e in inputs["required_elements"]]
    if len(set(req)) != len(req):
        errs.append("REQUIRED_DUPLICATE: required_elements[].id")
    by_widget = {d["widget"]: d for d in data}
    for d in data:
        okay = spec_mod.BINDING_WIDGET_TYPES.get(d["type"])
        if okay is not None and d["widget_type"] not in okay:
            errs.append(f"DATA_WIDGET_TYPE: '{d['widget']}' {d['widget_type']} cannot take a '{d['type']}' binding")
        if d.get("format") and d["type"] != "number":
            errs.append(f"DATA_FORMAT: '{d['id']}' format is only for number data")
        if d["type"] == "number" and not d.get("format"):
            errs.append(f"DATA_FORMAT: number data '{d['id']}' needs format ('0' or '0.0…')")
    for st in inputs.get("static_text", []):
        d = by_widget.get(st["widget"])
        if d and (d["widget_type"] != "TextBlock" or d["type"] in ("text", "number")):
            errs.append(f"STATIC_TEXT_CONFLICT: '{st['widget']}' is static text but data '{d['id']}' makes it a {d['widget_type']}/{d['type']}")
    return errs


def _fit_reference(src: pathlib.Path, dst: pathlib.Path, size: list[int]) -> dict:
    """컨셉 → 기준 해상도 RGB PNG. 비율 차이 ≤ 1 % 면 늘리고, 넘으면 가운데 맞춤 + 검은 띠."""
    from PIL import Image   # rapidocr 와 함께 설치(1b-3) — normalize(concept) 만 쓴다
    with Image.open(src) as im:
        im = im.convert("RGB")
        sw, sh = im.size
        tw, th = int(size[0]), int(size[1])
        diff = abs((sw / sh) / (tw / th) - 1.0)
        if diff <= ASPECT_STRETCH_MAX:
            out = im.resize((tw, th), Image.Resampling.LANCZOS)
            mode, scale, offset = "stretch", [tw / sw, th / sh], [0, 0]
        else:
            s = min(tw / sw, th / sh)
            nw, nh = max(1, round(sw * s)), max(1, round(sh * s))
            out = Image.new("RGB", (tw, th), (0, 0, 0))
            offset = [(tw - nw) // 2, (th - nh) // 2]
            out.paste(im.resize((nw, nh), Image.Resampling.LANCZOS), tuple(offset))
            mode, scale = "letterbox", [s, s]
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, format="PNG")
    return {"src_size": [sw, sh], "dst_size": [tw, th], "mode": mode, "aspect_diff": round(diff, 5),
            "scale": [round(v, 6) for v in scale], "offset": offset}


def run_concept(run, opts) -> str:
    src = pathlib.Path(opts.inputs)
    try:
        inputs = config.load_yaml(src)
    except config.ConfigError as exc:
        raise StageError("INPUT_UNREADABLE", str(exc)) from exc
    errs = schema.errors("inputs", inputs)
    if errs:
        raise StageError("SCHEMA", "inputs.yaml: " + "; ".join(errs[:8]), kind="inputs", errors=errs)
    errs = _inputs_errors(inputs)
    if errs:
        raise StageError("INPUTS_INVALID", "; ".join(errs[:8]), errors=errs)
    concept = pathlib.Path(opts.concept) if getattr(opts, "concept", None) else pathlib.Path(inputs["concept"])
    if not concept.is_absolute():
        concept = (pathlib.Path.cwd() if getattr(opts, "concept", None) else src.parent) / concept
    if not concept.is_file():
        raise StageError("INPUT_UNREADABLE", f"concept image {concept} does not exist")
    screens = config.load_screens()
    screen = screens.get(inputs["screen_id"])
    if not screen:
        raise StageError("SCREEN_UNKNOWN", f"screen_id '{inputs['screen_id']}' is not in screens.yaml")
    resolution = list(inputs.get("resolution") or [1920, 1080])
    try:
        fit = _fit_reference(concept, run.path("reference.png"), resolution)
    except (OSError, ValueError) as exc:
        raise StageError("INPUT_UNREADABLE", f"{concept}: {exc}") from exc
    font = inputs.get("font") or (run.cfg.get("fonts") or {}).get("default_family")
    dynamic = []
    for d in inputs["data"]:
        e = {k: d[k] for k in ("id", "type", "widget", "widget_type") }
        for k in ("format", "sample", "desc"):
            if k in d:
                e[k] = d[k]
        dynamic.append(e)
    brief = {"schema_version": 1, "run_id": run.run_id, "mode": "concept", "screen_type": inputs["screen_type"], "screen_id": inputs["screen_id"],
             "resolution": resolution, "language": inputs.get("language", "ko"), "font": font, "text": inputs.get("text", ""),
             "required_elements": inputs["required_elements"], "dynamic_data": dynamic, "static_text": inputs.get("static_text", []),
             "style_keywords": inputs.get("style_keywords", []),
             "references": [{"path": "reference.png", "role": "layout", "role_source": "user"}], "conflicts": [],
             "binding_contract": {"class": f"U{screen['widget']}", "source": "new", "bindings": [d["widget"] for d in inputs["data"]]}}
    schema.require("brief", brief)
    run.write_json("brief.json", brief)
    run.write_json("inputs.json", inputs)
    raw = concept.read_bytes()
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", "inputs": src.as_posix(), "concept": concept.as_posix(),
                                      "concept_sha256": hashlib.sha256(raw).hexdigest(), "reference": "reference.png", **fit})
    return (f"concept {concept.name} {fit['src_size'][0]}x{fit['src_size'][1]} → reference {resolution[0]}x{resolution[1]} ({fit['mode']}) — "
            f"{len(dynamic)} bindings, {len(brief['static_text'])} static texts, font {font or 'engine default'}")


def run_hand_spec(run, opts) -> str:
    src = pathlib.Path(opts.spec_dir)
    brief, spec = _load(src / "brief.json"), _load(src / "spec.json")
    for kind, obj in (("brief", brief), ("spec", spec)):
        errs = schema.errors(kind, obj)
        if errs:
            raise StageError("SCHEMA", f"{kind}.json: " + "; ".join(errs[:8]), kind=kind, errors=errs)
    if brief["mode"] != "hand_spec":
        raise StageError("MODE", f"brief.mode '{brief['mode']}' — Phase 1a runs hand_spec only")
    errs = spec_mod.validate_semantics(spec)
    if errs:
        raise StageError("SPEC_INVALID", "; ".join(errs[:8]), errors=errs)
    errs = check_brief_vs_spec(brief, spec)
    if errs:
        raise StageError("BRIEF_SPEC_MISMATCH", "; ".join(errs[:8]), errors=errs)
    brief = {**brief, "run_id": run.run_id}
    run.write_json("brief.json", brief)
    run.write_json("spec.json", spec)
    run.write_json("specs/000.json", spec)
    return f"hand_spec from {src.as_posix()} — {len(spec['widgets'])} widgets, {len(spec.get('assets', []))} assets, {len(spec_mod.bound_widgets(spec))} bindings"
