"""normalize — 입력을 brief · spec 으로 (설계 §2-2).

1a(hand_spec): 손으로 쓴 brief.json · spec.json 이 든 폴더를 받아 검사하고 run 폴더로 복사한다. analyze 는 건너뛴다(spec 이 이미 있다).
concept · text · multi_ref 는 1b · 3.

검사: 스키마 · spec 의미 검사 · brief ↔ spec 맞물림(필수 요소 · 바인딩 계약 · 동적 데이터 · 고정 글자). 하나라도 어긋나면 run 을 시작하지 않는다.
"""
from __future__ import annotations

import json
import pathlib

from core import schema
from core import spec as spec_mod
from stages import StageError


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
    return errs


def run(run, opts) -> str:
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
