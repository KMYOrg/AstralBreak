"""fix — 실패 게이트 → 정정 spec patch (설계 §2-2 fix · §8-3).

모드(pipeline.yaml fix.mode · `--fix-mode`):
  deterministic (1a, 11-14 사용자 결정) — 게이트 상세 · 기준 해상도 geometry · bbox_intent 만으로 계산한다. LLM 호출 0.
  llm — verifier(`claude -p`, 보는 눈 → fixes) → fix(`claude -p`, 고치는 손 → patch) 두 번(§8-3 — 둘을 나눠 verifier 가 자기 수정안을 변호하지 않게).
  hybrid (1b 기본, 11-15 사용자 결정) — 결정적 fixer 를 먼저 돌려 op 가 있으면 그것을 쓰고, op 가 없거나 **직전 시도의 결정적 patch 가
    실패 게이트 집합을 줄이지 못했으면** LLM 으로 넘긴다(결정적 fixer 가 같은 자리를 맴도는 것 — 1b-5 실측: OCR 오검출 재생성 반복).
LLM patch 는 적용 전에 검사한다 — patch 스키마 · 가드(`guard_ops`: bbox_intent · binding · note 는 못 고침, 계약 위젯의 text 는 못 고침, 필수 요소
제거 · 바인딩 추가 금지) · 사본 적용(apply_patch). 실패하면 오류를 붙여 fix 를 1회 다시 부르고, 또 실패하거나 LLM 이 실패하면 op 없음(NO_FIX)으로
끝낸다 — run 은 finalize 까지 간다.

결정적 규칙(잠정):
  - 배치 게이트(offscreen · overlap · iou_region · iou_leaf)에서 실패한 위젯마다, 자기 자신 또는 가장 가까운 '캔버스 슬롯 조상'(루트 Canvas 의
    직계)을 고친다 — 그 아래 박스 칸은 비율로 따라온다. 점 앵커일 때만: 측정 bbox 와 bbox_intent 의 차이로
    position += d + alignment × dsize, size += dsize. 차이가 0.5 px 이하면 그 단계에서 고칠 것이 없다(안쪽 문제 — 1b).
    영역이 그려지지 않았으면(컬링 — geometry (0, 0, 0, 0), core/geometry.py [실측]) 측정값을 쓰지 않고 루트 bbox · 앵커 · 정렬로
    bbox_intent 자리를 계산한다(position = intent.xy − 루트.xy − anchor × 루트.wh + alignment × intent.wh, size = intent.wh).
  - 겹침 쌍은 bbox_intent 에서 벗어난 쪽만 고친다. 둘 다 의도대로인데 겹치면 bbox_intent 자체가 겹치는 것 — 제안만 남긴다.
  - texture_settings 불일치 → replace_asset(regenerate) — generate(그 에셋) → refine → build 가 새 이름으로 다시 임포트한다.
  - baked_text(생성 에셋 OCR 검출) → 그 에셋 replace_asset(regenerate) — 같은 분기(1b-5).
  - compile · bindings · required_elements · roundtrip 은 결정적으로 고칠 수 없다 — fixes 에 문제만 남기고 op 없음.
  op 가 하나도 없으면 patch 없음(None) → 오케스트레이터가 NO_FIX 로 멈춘다.
"""
from __future__ import annotations

import json

from core import config
from core import geometry as geo
from core import llm
from core import patch as patch_mod
from core import schema
from core import spec as spec_mod
from stages import StageError

LAYOUT_GATES = ("offscreen", "overlap", "iou_region", "iou_leaf")
TOL = 0.5


def _failing_widgets(gates: dict[str, dict]) -> tuple[dict[str, set[str]], list[dict]]:
    """배치 게이트에서 실패한 위젯 → {게이트 …}, 겹침 위반 목록."""
    out: dict[str, set[str]] = {}
    off = gates.get("offscreen") or {}
    if not off.get("pass", True):
        for o in (off.get("details") or {}).get("offscreen", []):   # 해상도마다 한 줄 — 위젯으로 모은다
            out.setdefault(o["id"], set()).add("offscreen")
    for name in ("iou_region", "iou_leaf"):
        g = gates.get(name) or {}
        if not g.get("pass", True):
            for wid in (g.get("details") or {}).get("failed", []):
                out.setdefault(wid, set()).add(name)
    ov = gates.get("overlap") or {}
    violations = [] if ov.get("pass", True) else (ov.get("details") or {}).get("violations", [])
    return out, violations


def _canvas_target(index: dict, root: str, wid: str) -> str | None:
    """wid 자신 또는 조상 중 부모가 루트인 것(= 캔버스 슬롯 영역)."""
    cur = index.get(wid)
    while cur is not None:
        if cur.get("parent") == root:
            return cur["id"]
        cur = index.get(cur.get("parent"))
    return None


def _deviation(intent, g) -> tuple[float, float, float, float]:
    b = geo.box(g)
    return float(intent[0]) - b[0], float(intent[1]) - b[1], float(intent[2]) - b[2], float(intent[3]) - b[3]


def _deviates(intent, g) -> bool:
    if g is None:
        return False
    return not geo.painted(g) or any(abs(v) > TOL for v in _deviation(intent, g))


def _slot_from_intent(intent, anchors, alignment, frame) -> tuple[list, list]:
    """점 앵커 캔버스 슬롯이 bbox_intent 에 놓이는 position · size — frame = 루트 Canvas 의 bbox(그려진 값, 없으면 [0, 0, canvas])."""
    x, y, w, h = (float(v) for v in intent)
    pos = [x - frame[0] - anchors[0] * frame[2] + alignment[0] * w, y - frame[1] - anchors[1] * frame[3] + alignment[1] * h]
    return [spec_mod.canon_number(v) for v in pos], [spec_mod.canon_number(w), spec_mod.canon_number(h)]


def propose_deterministic(spec: dict, gates_list: list[dict], geometry: list[dict]) -> tuple[list[dict], list[dict]]:
    """(fixes, ops) — fixes 는 fixes.schema 의 항목들, ops 는 spec patch op."""
    gates = {g["name"]: g for g in gates_list}
    norm = spec_mod.normalize(spec)
    index = spec_mod.widget_index(norm)
    root = norm["root"]
    gi = geo.by_id(geometry)
    fixes: list[dict] = []
    ops: list[dict] = []

    failing, violations = _failing_widgets(gates)
    candidates: dict[str, set[str]] = {wid: set(gs) for wid, gs in failing.items()}
    for v in violations:
        movers = [w for w in (v["a"], v["b"]) if index.get(w, {}).get("bbox_intent") and _deviates(index[w]["bbox_intent"], gi.get(w))]
        if not movers:
            fixes.append({"widget": v["a"], "gate": "overlap", "problem": f"'{v['a']}' and '{v['b']}' overlap {v['ratio']:.0%} although both sit on their bbox_intent",
                          "evidence": "bbox_intent itself overlaps — add the pair to allow_overlap or change the layout (needs a person or the 1b LLM fix)"})
        for w in movers:
            candidates.setdefault(w, set()).add("overlap")

    targets: dict[str, set[str]] = {}
    for wid, gs in candidates.items():
        t = _canvas_target(index, root, wid)
        if t is None:
            fixes.append({"widget": wid, "gate": sorted(gs)[0], "problem": "no canvas-slot ancestor to move", "evidence": "the widget is the root"})
            continue
        targets.setdefault(t, set()).update(gs)
    for t in [w for w in spec_mod.tree_order(norm) if w in targets]:
        w, gs = index[t], sorted(targets[t])
        slot, intent, g = w.get("slot") or {}, w.get("bbox_intent"), gi.get(t)
        a = slot.get("anchors") or [0, 0, 0, 0]
        if not intent or g is None:
            fixes.append({"widget": t, "gate": gs[0], "problem": "no bbox_intent or no geometry for the region", "evidence": f"gates {gs}"})
            continue
        if a[0] != a[2] or a[1] != a[3] or slot.get("auto_size"):
            fixes.append({"widget": t, "gate": gs[0], "problem": "stretch anchors or auto_size — not fixed deterministically",
                          "evidence": f"anchors {a}, auto_size {slot.get('auto_size')}"})
            continue
        al, pos, size = slot.get("alignment") or [0, 0], slot.get("position") or [0, 0], slot.get("size") or [100, 30]
        if geo.painted(g):
            dx, dy, dw, dh = _deviation(intent, g)
            if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= TOL:
                fixes.append({"widget": t, "gate": gs[0], "problem": "the region already sits on its bbox_intent — the failure is inside it (box ratios · padding)",
                              "evidence": f"gates {gs}; region deviation ≤ {TOL} px"})
                continue
            new_pos = [spec_mod.canon_number(pos[0] + dx + al[0] * dw), spec_mod.canon_number(pos[1] + dy + al[1] * dh)]
            new_size = [spec_mod.canon_number(size[0] + dw), spec_mod.canon_number(size[1] + dh)]
            why = f"{', '.join(gs)} — measured {[geo.r3(v) for v in geo.box(g)]} vs bbox_intent {intent}"
        else:   # 컬링(그려지지 않음) — 측정값이 없으니 루트 bbox · 앵커 · 정렬로 bbox_intent 자리를 계산한다
            rg = gi.get(root)
            frame = geo.box(rg) if geo.painted(rg) else (0.0, 0.0, float(norm["canvas"][0]), float(norm["canvas"][1]))
            new_pos, new_size = _slot_from_intent(intent, a, al, frame)
            dx, dy, dw, dh = (new_pos[0] - pos[0], new_pos[1] - pos[1], new_size[0] - size[0], new_size[1] - size[1])
            why = f"{', '.join(gs)} — not painted (culled off the draw area); placed from bbox_intent {intent} with anchors {a} · alignment {al}"
        made = []
        if new_pos != [spec_mod.canon_number(v) for v in pos]:
            made.append({"op": "set", "widget": t, "path": "slot.position", "value": new_pos, "reason": why})
        if new_size != [spec_mod.canon_number(v) for v in size]:
            made.append({"op": "set", "widget": t, "path": "slot.size", "value": new_size, "reason": why})
        for op in made:
            fixes.append({"widget": t, "gate": gs[0], "problem": f"region off its bbox_intent by ({geo.r3(dx)}, {geo.r3(dy)}, {geo.r3(dw)}, {geo.r3(dh)}) px",
                          "evidence": why, "suggested_op": op})
        ops.extend(made)

    tex = gates.get("texture_settings") or {}
    if not tex.get("pass", True):
        for m in (tex.get("details") or {}).get("mismatches", []):
            if m.get("asset_id"):
                op = {"op": "replace_asset", "asset": m["asset_id"], "regenerate": True, "reason": f"texture settings differ from the manifest: {m.get('diff')}"}
                fixes.append({"widget": m["asset_id"], "gate": "texture_settings", "problem": "imported texture settings differ from the manifest",
                              "evidence": str(m.get("diff")), "suggested_op": op})
                ops.append(op)
            else:
                fixes.append({"widget": str(m.get("texture")), "gate": "texture_settings", "problem": m.get("problem", "unknown texture")})
    bt = gates.get("baked_text") or {}
    if not bt.get("pass", True):   # 1b-5 — 생성 에셋에 글자 같은 자국 → 그 에셋만 다시 만든다(generate 가 '글씨 금지'를 더 세게 붙인다)
        for f in (bt.get("details") or {}).get("found", []):
            op = {"op": "replace_asset", "asset": f["asset_id"], "regenerate": True, "reason": f"OCR found text-like marks: {f.get('text')}"}
            fixes.append({"widget": f["asset_id"], "gate": "baked_text", "problem": "the generated asset has baked text-like marks",
                          "evidence": str(f.get("text")), "suggested_op": op})
            ops.append(op)
        for aid in (bt.get("details") or {}).get("not_checked", []):
            fixes.append({"widget": aid, "gate": "baked_text", "problem": "the asset was never OCR-checked", "evidence": "manifest ocr_text is null"})
    for name in ("compile", "bindings", "required_elements", "roundtrip"):
        g = gates.get(name) or {}
        if not g.get("pass", True):
            fixes.append({"widget": "*", "gate": name, "problem": f"gate '{name}' failed — no deterministic fix (1b LLM fix or a person)",
                          "evidence": str(g.get("details"))[:400]})
    return fixes, ops


def _geometry(run, spec: dict, attempt: int) -> list[dict]:
    p = f"attempts/{attempt:03d}/geometry.json"
    geom_doc = run.read_json(p) if run.path(p).is_file() else None
    canvas = f"{int(spec['canvas'][0])}x{int(spec['canvas'][1])}"
    return (geom_doc or {}).get("geometry", {}).get(canvas, [])


def _deterministic_stalled(run, attempt: int, failed_now: list[str]) -> bool:
    """직전 시도의 patch 가 결정적이었고 실패 게이트 집합이 줄지 않았나(진부분집합이 아님)."""
    if attempt <= 1:
        return False
    prev_fix, prev_gates = f"attempts/{attempt - 1:03d}/fixes.json", f"attempts/{attempt - 1:03d}/gates.json"
    if not (run.path(prev_fix).is_file() and run.path(prev_gates).is_file()):
        return False
    if run.read_json(prev_fix).get("source") != "deterministic":
        return False
    prev_failed = {g["name"] for g in run.read_json(prev_gates).get("gates", []) if not g.get("pass", True)}
    return not set(failed_now) < prev_failed


def propose(run, attempt: int, verify_result: dict, mode: str | None = None) -> dict:
    """attempts/NNN/fixes.json · patches/NNN.json 을 쓴다. {fixes, patch(None 이면 고칠 것 없음), branch, assets} 를 돌려준다."""
    mode = mode or (run.cfg.get("fix") or {}).get("mode", "deterministic")
    spec = run.read_json("spec.json")
    if mode == "deterministic":
        fixes, ops = propose_deterministic(spec, verify_result["gates"], _geometry(run, spec, attempt))
        source = "deterministic"
    elif mode == "llm":
        fixes, ops = llm_propose(run, attempt, verify_result)
        source = "llm"
    elif mode == "hybrid":
        fixes, ops = propose_deterministic(spec, verify_result["gates"], _geometry(run, spec, attempt))
        source = "deterministic"
        stalled = _deterministic_stalled(run, attempt, verify_result["failed"])
        if not ops or stalled:
            why = "the deterministic fixer has no op" if not ops else "the previous deterministic patch did not shrink the failing gate set"
            run.log(f"fix: hybrid → LLM ({why})")
            l_fixes, ops = llm_propose(run, attempt, verify_result)
            fixes = fixes + l_fixes
            source = "llm"
    else:
        raise StageError("FIX_MODE", f"pipeline.yaml fix.mode '{mode}' — deterministic | hybrid | llm")
    fixes_doc = {"schema_version": 1, "source": source, "fixes": fixes}
    schema.require("fixes", fixes_doc)
    run.write_json(f"attempts/{attempt:03d}/fixes.json", fixes_doc)
    if not ops:
        return {"fixes": fixes, "patch": None, "patch_file": None, "branch": None, "assets": []}
    patch = {"schema_version": 1, "base_revision": verify_result.get("revision"), "source": "fix",
             "note": f"attempt {attempt} — {source} fixer for {', '.join(verify_result['failed'])}", "ops": ops}
    schema.require("patch", patch)
    rel = f"patches/{attempt:03d}.json"
    run.write_json(rel, patch)
    return {"fixes": fixes, "patch": patch, "patch_file": rel, "branch": patch_mod.branch_for(patch), "assets": patch_mod.regenerate_assets(patch)}


# ---------------------------------------------------------------------------------------------------------------------
# LLM 모드 (1b-6) — verifier(보는 눈) → fix(고치는 손). 입력 파일은 절대 경로로 주고 출력은 structured_output 으로만 받는다.

FIXES_OUTPUT_SCHEMA = {
    "type": "object", "required": ["fixes"],
    "properties": {"fixes": {"type": "array", "items": {
        "type": "object", "required": ["widget", "problem"],
        "properties": {"widget": {"type": "string"}, "problem": {"type": "string"}, "gate": {"type": "string"},
                       "evidence": {"type": "string"}, "suggested_op": {"type": "object"}}}}}}
PATCH_OUTPUT_SCHEMA = {   # 모양만 — 엄격한 검사는 schemas/patch.schema.json(core.schema) · guard_ops · apply_patch 가 한다
    "type": "object", "required": ["ops"],
    "properties": {"ops": {"type": "array", "items": {"type": "object", "required": ["op"]}}, "note": {"type": "string"}}}
FIX_CALLS = 2
GUARDED_SET_ROOTS = {"bbox_intent": "bbox_intent is the target measured from the reference — move/resize the widget instead",
                     "binding": "bindings are fixed by the request (contract)", "note": "note is not layout"}


def _contract_widgets(brief: dict) -> set[str]:
    return {d["widget"] for d in brief.get("dynamic_data", [])} | {s["widget"] for s in brief.get("static_text", [])}


def guard_ops(ops: list[dict], spec: dict, brief: dict) -> list[str]:
    """LLM patch 가 넘으면 안 되는 선 — 게이트를 속이는 수정(bbox_intent) · 계약 바꾸기 · 필수 요소 지우기."""
    errs: list[str] = []
    contract = _contract_widgets(brief)
    required = {e["id"] for e in brief.get("required_elements", [])}
    for i, op in enumerate(ops):
        kind = op.get("op")
        if kind == "set":
            root = str(op.get("path", "")).split(".")[0]
            if root in GUARDED_SET_ROOTS:
                errs.append(f"op {i}: set {op.get('widget')}.{op.get('path')} — {GUARDED_SET_ROOTS[root]}")
            if root == "text" and op.get("widget") in contract:
                errs.append(f"op {i}: set {op.get('widget')}.{op.get('path')} — the text of contract widgets comes from the request")
        elif kind == "remove_widget" and op.get("widget") in required:
            errs.append(f"op {i}: remove_widget {op.get('widget')} — it is a required element")
        elif kind == "add_widget" and isinstance(op.get("widget"), dict) and op["widget"].get("binding"):
            errs.append(f"op {i}: add_widget with a binding — bindings are fixed by the request")
    return errs


def _gate_summary(gates: list[dict]) -> str:
    """실패 게이트를 짧게 — 배치 게이트는 실패 위젯의 의도 · 측정 상자, 나머지는 상세 앞부분."""
    lines = []
    for g in gates:
        if g.get("pass", True):
            continue
        d = g.get("details") or {}
        if g["name"] in ("iou_leaf", "iou_region"):
            rows = [w for w in d.get("widgets", []) if not w.get("pass", True)]
            body = "; ".join(f"{w['id']} intent {w.get('intent')} measured {w.get('bbox')} {w.get('rule')} {w.get('value')} "
                             f"(need {'>=' if w.get('rule') == 'iou' else '<='} {w.get('threshold')})" for w in rows) or str(d)[:400]
        elif g["name"] == "offscreen":
            body = "; ".join(f"{o.get('id')} at {o.get('resolution')}: {o.get('reason', o)}" for o in d.get("offscreen", [])[:8])
        elif g["name"] == "overlap":
            body = "; ".join(f"{v['a']} x {v['b']} {v.get('ratio')}" for v in d.get("violations", [])[:8])
        else:
            body = str(d)[:500]
        lines.append(f"- {g['name']}: {body}")
    return "\n".join(lines)


def _line_height_note(cfg: dict, spec: dict) -> str:
    """spec 의 TextBlock 이 쓰는 폰트마다 줄 높이 표(1b 후속 D — 역할별 폰트). 표가 없는 폰트(엔진 기본)는 1.6 배 문장."""
    used = {(w.get("font") or {}).get("family") for w in spec.get("widgets", []) if w.get("type") == "TextBlock"}
    notes = []
    for role, r in config.font_roles(cfg).items():
        fams = [f for f in (r["family"], r.get("sdf_family")) if f and f in used]     # 1b 후속 F — SDF 사본(빛 글자)은 같은 줄 높이
        if fams and r["line_height"]:
            notes.append(f"Text with font.family {' or '.join(fams)} (role {role}): TextBlock height per font size "
                         f"{config.line_height_text(r['line_height'], '->')} (scale proportionally beyond).")
            used.difference_update(fams)
    if used:
        notes.append("Text with other fonts (engine default): TextBlock height is about 1.6 x font size (16->26, 18->29, 22->35, 26->42, 30->48, 34->54).")
    return " ".join(notes)


def _llm_row(run, stage: str, attempt: int, res: dict | None, err: str | None = None, extra: dict | None = None) -> None:
    keep = ("cost_usd", "num_turns", "duration_s", "model", "tokens")
    run.append_jsonl("llm.jsonl", {"stage": stage, "attempt": attempt, **({k: res.get(k) for k in keep} if res else {}),
                                   **({"error": err} if err else {}), **(extra or {})})


def llm_propose(run, attempt: int, verify_result: dict, cli: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """verifier → fix (설계 §8-3). LLM 실패 · 쓸 수 없는 patch 는 예외가 아니라 op 없음 + fixes 에 이유(run 은 NO_FIX 로 finalize 까지)."""
    adir = run.path("attempts", f"{attempt:03d}")
    spec = run.read_json("spec.json")
    brief = run.read_json("brief.json")
    files = {"render": run.path("render.png"), "spec": run.path("spec.json"), "brief": run.path("brief.json"), "gates": adir / "gates.json"}
    if (adir / "geometry.json").is_file():
        files["geometry"] = adir / "geometry.json"
    if run.path("reference.png").is_file():
        files["reference"] = run.path("reference.png")
    listing = "\n".join(f"- {k}: {p.resolve().as_posix()}" for k, p in files.items())
    summary = _gate_summary(verify_result["gates"])
    canvas = spec.get("canvas", [1920, 1080])
    v_prompt = (f"UI verifier for run {run.run_id}, attempt {attempt}. Canvas {canvas[0]}x{canvas[1]}. Read the files below (render first, then the "
                f"reference if listed), compare, and explain every failed gate as fixes.\n{listing}\nFailed gates:\n{summary}\n"
                f"{_line_height_note(run.cfg, spec)}")
    try:
        v = llm.run_stage("verifier", v_prompt, run.cfg, FIXES_OUTPUT_SCHEMA, cli=cli)
    except llm.LlmError as exc:
        _llm_row(run, "verifier", attempt, exc.details, exc.code)
        return [{"widget": "*", "gate": "llm", "problem": f"LLM verifier failed: {exc.code}", "evidence": str(exc)[:300]}], []
    raw_fixes = v["structured_output"].get("fixes", [])
    run.write_json(f"attempts/{attempt:03d}/llm_verifier.json", v["structured_output"])
    fixes = [f for f in raw_fixes if not schema.errors("fixes", {"schema_version": 1, "fixes": [f]})]
    _llm_row(run, "verifier", attempt, v, extra={"fixes": len(fixes)})
    base = (f"UI fix for run {run.run_id}, attempt {attempt}. Turn the verifier's fixes into ONE minimal spec patch that makes the failed gates pass.\n"
            f"Spec (current, absolute path — Read it): {files['spec'].resolve().as_posix()}\n"
            + (f"Measured geometry of this attempt: {files['geometry'].resolve().as_posix()}\n" if "geometry" in files else "")
            + f"Failed gates:\n{summary}\nVerifier fixes:\n{json.dumps(fixes, ensure_ascii=False)}\n{_line_height_note(run.cfg, spec)}\n"
            f"Contract widgets (their binding and text are fixed): {', '.join(sorted(_contract_widgets(brief)))}.")
    prompt, errs, ops = base, [], []
    for k in range(1, FIX_CALLS + 1):
        try:
            f = llm.run_stage("fix", prompt, run.cfg, PATCH_OUTPUT_SCHEMA, cli=cli)
        except llm.LlmError as exc:
            _llm_row(run, "fix", attempt, exc.details, exc.code, {"call": k})
            return fixes + [{"widget": "*", "gate": "llm", "problem": f"LLM fix failed: {exc.code}", "evidence": str(exc)[:300]}], []
        ops = f["structured_output"].get("ops", [])
        run.write_json(f"attempts/{attempt:03d}/llm_fix_{k}.json", f["structured_output"])
        errs = guard_ops(ops, spec, brief)
        if not ops:
            errs.append("the patch has no ops")
        if not errs:
            try:
                patch_mod.apply_patch(spec, {"schema_version": 1, "source": "fix", "ops": ops})
            except patch_mod.PatchError as exc:
                errs = [str(exc)] + [str(e) for e in (exc.details.get("errors") or [])[:8]]
        _llm_row(run, "fix", attempt, f, extra={"call": k, "ops": len(ops), "errors": len(errs)})
        if not errs:
            return fixes, ops
        prompt = base + "\n\nYour previous patch was rejected — fix every problem and return the complete corrected patch:\n" + "\n".join(f"- {e}" for e in errs[:20])
    return fixes + [{"widget": "*", "gate": "llm", "problem": "LLM fix produced no usable patch", "evidence": "; ".join(errs[:5])[:500]}], []


