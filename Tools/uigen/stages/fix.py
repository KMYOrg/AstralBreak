"""fix — 실패 게이트 → 정정 spec patch (설계 §2-2 fix · §8-3).

모드(pipeline.yaml fix.mode):
  deterministic (1a, 11-14 사용자 결정) — 게이트 상세 · 기준 해상도 geometry · bbox_intent 만으로 계산한다. LLM 호출 0.
  llm (1b) — verifier(`claude -p`, fixes.json) → fix(`claude -p`, patch) 두 번. 이 파일에는 호출 틀만 있다(core/llm.py).

결정적 규칙(잠정):
  - 배치 게이트(offscreen · overlap · iou_region · iou_leaf)에서 실패한 위젯마다, 자기 자신 또는 가장 가까운 '캔버스 슬롯 조상'(루트 Canvas 의
    직계)을 고친다 — 그 아래 박스 칸은 비율로 따라온다. 점 앵커일 때만: 측정 bbox 와 bbox_intent 의 차이로
    position += d + alignment × dsize, size += dsize. 차이가 0.5 px 이하면 그 단계에서 고칠 것이 없다(안쪽 문제 — 1b).
    영역이 그려지지 않았으면(컬링 — geometry (0, 0, 0, 0), core/geometry.py [실측]) 측정값을 쓰지 않고 루트 bbox · 앵커 · 정렬로
    bbox_intent 자리를 계산한다(position = intent.xy − 루트.xy − anchor × 루트.wh + alignment × intent.wh, size = intent.wh).
  - 겹침 쌍은 bbox_intent 에서 벗어난 쪽만 고친다. 둘 다 의도대로인데 겹치면 bbox_intent 자체가 겹치는 것 — 제안만 남긴다.
  - texture_settings 불일치 → replace_asset(regenerate) — generate(그 에셋) → refine → build 가 새 이름으로 다시 임포트한다.
  - compile · bindings · required_elements · roundtrip 은 결정적으로 고칠 수 없다 — fixes 에 문제만 남기고 op 없음.
  op 가 하나도 없으면 patch 없음(None) → 오케스트레이터가 NO_FIX 로 멈춘다.
"""
from __future__ import annotations

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
    for name in ("compile", "bindings", "required_elements", "roundtrip"):
        g = gates.get(name) or {}
        if not g.get("pass", True):
            fixes.append({"widget": "*", "gate": name, "problem": f"gate '{name}' failed — no deterministic fix (1b LLM fix or a person)",
                          "evidence": str(g.get("details"))[:400]})
    return fixes, ops


def propose(run, attempt: int, verify_result: dict, mode: str | None = None) -> dict:
    """attempts/NNN/fixes.json · patches/NNN.json 을 쓴다. {fixes, patch(None 이면 고칠 것 없음), branch, assets} 를 돌려준다."""
    mode = mode or (run.cfg.get("fix") or {}).get("mode", "deterministic")
    spec = run.read_json("spec.json")
    if mode == "deterministic":
        geom_doc = run.read_json(f"attempts/{attempt:03d}/geometry.json") if run.path(f"attempts/{attempt:03d}/geometry.json").is_file() else None
        canvas = f"{int(spec['canvas'][0])}x{int(spec['canvas'][1])}"
        geometry = (geom_doc or {}).get("geometry", {}).get(canvas, [])
        fixes, ops = propose_deterministic(spec, verify_result["gates"], geometry)
        source = "deterministic"
    elif mode == "llm":
        fixes, ops = llm_propose(run, attempt, verify_result)
        source = "llm"
    else:
        raise StageError("FIX_MODE", f"pipeline.yaml fix.mode '{mode}' — deterministic | llm")
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
# LLM 모드 (1b) — 호출 틀. 1a 설정(deterministic)에서는 불리지 않는다.

FIXES_OUTPUT_SCHEMA = {
    "type": "object", "required": ["fixes"],
    "properties": {"fixes": {"type": "array", "items": {
        "type": "object", "required": ["widget", "problem"],
        "properties": {"widget": {"type": "string"}, "problem": {"type": "string"}, "gate": {"type": "string"},
                       "evidence": {"type": "string"}, "suggested_op": {"type": "object"}}}}}}
PATCH_OUTPUT_SCHEMA = {   # 모양만 — 엄격한 검사는 schemas/patch.schema.json(core.schema) 이 한다
    "type": "object", "required": ["ops"],
    "properties": {"ops": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["op"]}}, "note": {"type": "string"}}}


def llm_propose(run, attempt: int, verify_result: dict, cli: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """verifier → fix (설계 §8-3: 보는 눈과 고치는 손을 나눈다). 입력 파일은 절대 경로로 주고 출력은 structured_output 으로만 받는다."""
    adir = run.path("attempts", f"{attempt:03d}")
    failed = [g for g in verify_result["gates"] if not g["pass"]]
    files = {"render": run.path("render.png"), "spec": run.path("spec.json"), "brief": run.path("brief.json"), "gates": adir / "gates.json"}
    if run.path("reference.png").is_file():
        files["reference"] = run.path("reference.png")
    listing = "\n".join(f"- {k}: {p.resolve().as_posix()}" for k, p in files.items())
    v_prompt = (f"UI verifier for run {run.run_id}, attempt {attempt}. Read the files below, compare the render with the reference/spec and explain "
                f"each failed gate as fixes (widget id, problem, evidence, optional suggested spec-patch op). Do not write files.\n{listing}\n"
                f"Failed gates: {', '.join(g['name'] for g in failed)}")
    v = llm.run_stage("verifier", v_prompt, run.cfg, FIXES_OUTPUT_SCHEMA, cli=cli)
    fixes = v["structured_output"].get("fixes", [])
    schema.require("fixes", {"schema_version": 1, "source": "llm", "fixes": fixes})
    f_prompt = (f"UI fix for run {run.run_id}, attempt {attempt}. Turn these verifier fixes into a spec patch (ops: set/add_widget/remove_widget/move/"
                f"replace_asset — bound widgets cannot be removed, locked widgets cannot change). Spec: {files['spec'].resolve().as_posix()}\n"
                f"Fixes: {fixes}")
    f = llm.run_stage("fix", f_prompt, run.cfg, PATCH_OUTPUT_SCHEMA, cli=cli)
    ops = f["structured_output"].get("ops", [])
    errs = schema.errors("patch", {"schema_version": 1, "source": "fix", "ops": ops})
    if errs:
        raise StageError("LLM_PATCH_INVALID", "; ".join(errs[:5]), errors=errs)
    run.append_jsonl("llm.jsonl", {"attempt": attempt, "verifier": {k: v[k] for k in ("cost_usd", "num_turns", "duration_s")},
                                   "fix": {k: f[k] for k in ("cost_usd", "num_turns", "duration_s")}})
    return fixes, ops
