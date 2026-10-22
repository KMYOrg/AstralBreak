"""Phase 6-1 상태머신 완성 — add_conduit · add_state_alias · set_alias_states · rename_node · graph:{ref} · result_of · conduit 규칙.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_1_test.py [--recheck]

대상: /Game/Animation/Test/ABP_McpTest (덮어쓰기). 운영 애셋은 건드리지 않는다.
검사 항목:
  A. 운영 애셋 `Locomotions` 와 같은 구조(상태 5 · conduit 2 · alias 4 · 전이 12 · 상태 내부)를 **배치 하나**로 구성 — 같은 배치 graph:{ref} · result_of · rename_node(상태머신) → 컴파일 0 에러
  B. 뷰 — kind · aliased_states · conduit rule_source · 상태머신 이름 · 전이 from/to 이름
  C. rename_node — 상태·conduit·alias·상태머신, 되돌리기, 중복 거부, 전이 거부
  D. set_alias_states — 전이 대상 alias 를 global 로 바꾸면 거부 · 소스 alias 대상 교체 · 롤백
  E. 거부 — conduit automatic · conduit 그래프에 add_node · conduit 를 alias 대상으로 · 빈 alias · 다중 alias 를 전이 대상으로 · global+states
  F. 중간 실패 롤백 — conduit·alias 추가 + rename + set_alias_states + 상태 삭제(연쇄) 섞인 배치 → rollback_verified
  G. 삭제 — conduit 삭제(전이 연쇄) · alias 삭제 → 컴파일
  H. 저장 → --recheck
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase6_1_state.json"
ASSETS = {
    "idle": "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle",
    "bs": "/Game/Animation/Hero/Vesper/Common/Locomotion/BS_Vesper_Locomotion1D",
    "jump": "/Game/Animation/Hero/Vesper/Common/Locomotion/AS_Vesper_Jump_Start",
    "fall": "/Game/Animation/Hero/Vesper/Common/Locomotion/AS_Vesper_Jump_FallLoop",
    "land": "/Game/Animation/Hero/Vesper/Common/Locomotion/AS_Vesper_Jump_Land",
}
FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:1500]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def structure(depth: int = -1) -> dict:
    return must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": depth}, timeout=bridge.COMPILE_TIMEOUT), "structure")


def apply(ops: list, expected: str | None = None, **kw) -> dict:
    params = {"asset_path": ABP, "operations": ops, **kw}
    if expected:
        params["expected_revision"] = expected
    return bridge.call("apply_graph_operations", params, timeout=bridge.COMPILE_TIMEOUT)


def preview(ops: list) -> dict:
    return bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops})


def planned_errors(env: dict) -> list[str]:
    return [p.get("error", {}).get("code", "") for p in env.get("result", {}).get("planned", []) if not p["ok"]]


def the_sm(struct: dict) -> dict:
    return struct["state_machines"][0]


def state_by_name(sm: dict, name: str) -> dict:
    return next(s for s in sm["states"] if s["name"] == name)


def var(n: str) -> dict:
    return {"var": n}


def cmp(op: str, left: dict, lit: float) -> dict:
    return {"compare": {"op": op, "left": left, "right": {"literal": lit}}}


# 운영 애셋 Locomotions 와 같은 구성 (phase5 비교 문서 §3 의 운영 표)
def locomotions_ops(root_guid: str) -> list[dict]:
    ops = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-600, 0]},
        {"op": "rename_node", "ref": "sm", "name": "Locomotions"},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"node": root_guid, "pin": "Result"}},
    ]
    for ref, name, pos in (("idle", "Idle", [0, 0]), ("move", "Move", [500, 0]), ("jumpstart", "JumpStart", [0, 500]), ("fallloop", "FallLoop", [500, 500]), ("fallland", "FallLand", [1000, 500])):
        ops.append({"op": "add_state", "ref": ref, "sm": {"ref": "sm"}, "name": name, "pos": pos})
    ops.append({"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}})
    # 상태 내부 — 같은 배치 graph:{ref} + result_of
    for ref, asset, loop in (("idle", ASSETS["idle"], True), ("jumpstart", ASSETS["jump"], False), ("fallloop", ASSETS["fall"], True), ("fallland", ASSETS["land"], False)):
        ops += [
            {"op": "add_node", "ref": f"{ref}_seq", "graph": {"ref": ref}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": asset, "properties": {"bLoopAnimation": loop}},
            {"op": "connect", "from": {"ref": f"{ref}_seq", "pin": "Pose"}, "to": {"result_of": {"ref": ref}, "pin": "Result"}},
        ]
    ops += [
        {"op": "add_node", "ref": "move_speed", "graph": {"ref": "move"}, "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-800, 120]},
        {"op": "add_node", "ref": "move_bs", "graph": {"ref": "move"}, "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 0], "asset": ASSETS["bs"]},
        {"op": "connect", "from": {"ref": "move_speed", "pin": "Speed"}, "to": {"ref": "move_bs", "pin": "X"}},
        {"op": "connect", "from": {"ref": "move_bs", "pin": "Pose"}, "to": {"result_of": {"ref": "move"}, "pin": "Result"}},
        # conduit 2 · alias 4
        {"op": "add_conduit", "ref": "jumpsel", "sm": {"ref": "sm"}, "name": "JumpSelector", "pos": [250, 250], "rule": {"literal": True}},
        {"op": "add_conduit", "ref": "endinair", "sm": {"ref": "sm"}, "name": "EndInAir", "pos": [1250, 250], "rule": {"literal": True}},
        {"op": "add_state_alias", "ref": "jumpsrc", "sm": {"ref": "sm"}, "name": "JumpSources", "pos": [-300, 250], "states": [{"ref": "idle"}, {"ref": "move"}]},
        {"op": "add_state_alias", "ref": "interrupt", "sm": {"ref": "sm"}, "name": "JumpFallInterruptSources", "pos": [800, 800], "states": [{"ref": "jumpstart"}, {"ref": "fallloop"}]},
        {"op": "add_state_alias", "ref": "idlealias", "sm": {"ref": "sm"}, "name": "IdleAlias", "pos": [1600, 150], "states": [{"ref": "idle"}]},
        {"op": "add_state_alias", "ref": "movealias", "sm": {"ref": "sm"}, "name": "MoveAlias", "pos": [1600, 350], "states": [{"ref": "move"}]},
    ]
    transitions = [
        ("t_idle_move", "idle", "move", 0.25, 1, var("bHasMovementInput")),
        ("t_move_idle", "move", "idle", 0.30, 1, {"and": [{"not": var("bHasMovementInput")}, cmp("<", var("Speed"), 10.0)]}),
        ("t_src_sel", "jumpsrc", "jumpsel", 0.20, 1, {"literal": True}),
        ("t_sel_jump", "jumpsel", "jumpstart", 0.20, 1, var("bIsJumping")),
        ("t_sel_fall", "jumpsel", "fallloop", 0.20, 2, var("bIsFalling")),
        ("t_jump_fall", "jumpstart", "fallloop", 0.20, 1, {"automatic": True, "trigger_time": -1.0}),
        ("t_fall_land", "fallloop", "fallland", 0.20, 1, cmp("<", var("GroundDistance"), 25.0)),
        ("t_land_end_auto", "fallland", "endinair", 0.20, 1, {"automatic": True, "trigger_time": -1.0}),
        ("t_land_end_ground", "fallland", "endinair", 0.20, 1, var("bIsOnGround")),
        ("t_interrupt_end", "interrupt", "endinair", 0.20, 1, var("bIsOnGround")),
        ("t_end_idle", "endinair", "idlealias", 0.20, 1, cmp(">=", var("Speed"), 20.0)),
        ("t_end_move", "endinair", "movealias", 0.20, 1, cmp("<", var("Speed"), 20.0)),
    ]
    for ref, src, dst, xfade, prio, rule in transitions:
        ops.append({"op": "add_transition", "ref": ref, "from": {"ref": src}, "to": {"ref": dst}, "properties": {"CrossfadeDuration": xfade, "PriorityOrder": prio}, "rule": rule})
    return ops


def main_sections() -> None:
    print("\n=== 준비 ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    s0 = structure(0)
    root = next(n for n in s0["nodes"] if n["class"] == "AnimGraphNode_Root")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== A. 운영 구조 1:1 — 배치 하나 ===")
    ops = locomotions_ops(root["node_guid"])
    pv = preview(ops)
    check(pv.get("ok") and pv["result"]["valid"], f"preview valid (create={pv.get('result', {}).get('would_create')} modify={pv.get('result', {}).get('would_modify')})")
    if not (pv.get("ok") and pv["result"]["valid"]):
        print(json.dumps([p for p in pv.get("result", {}).get("planned", []) if not p["ok"]], ensure_ascii=False, indent=1)[:4000])
        sys.exit(1)
    r1 = apply(ops, expected=s0["revision"], compile=True)
    if not r1.get("ok"):
        print(json.dumps(r1, ensure_ascii=False, indent=1)[:6000])
        sys.exit(1)
    refs = r1["result"]["refs"]
    for m in r1["result"]["compile"].get("messages", []):
        if m["level"] != "info":
            print(f"   compile[{m['level']}] {m['text']}")
    check(r1["result"]["compile"].get("num_errors") == 0, f"apply+compile 0 에러 (ops={len(ops)}, warnings={r1['result']['compile'].get('num_warnings')})")
    conduit_entry = next(o for o in r1["result"]["operations"] if o.get("ref") == "jumpsel")
    check(conduit_entry.get("rule_graph_guid") and conduit_entry.get("rule_source") == '{"literal":true}', f"add_conduit 응답: rule_graph_guid·rule_source ({conduit_entry.get('rule_source')})")
    alias_entry = next(o for o in r1["result"]["operations"] if o.get("ref") == "jumpsrc")
    check(sorted(alias_entry.get("aliased_states", [])) == sorted([refs["idle"], refs["move"]]), "add_state_alias 응답: aliased_states == [Idle, Move]")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== B. 뷰 ===")
    s1 = structure(-1)
    sm = the_sm(s1)
    check(sm["name"] == "Locomotions", f"상태머신 이름 == Locomotions ({sm['name']})")
    kinds = {s["name"]: s["kind"] for s in sm["states"]}
    check(len(sm["states"]) == 11 and len(sm["transitions"]) == 12, f"상태 11 · 전이 12: {len(sm['states'])}/{len(sm['transitions'])}")
    check(kinds.get("JumpSelector") == "conduit" and kinds.get("EndInAir") == "conduit", "conduit 2 (kind)")
    check([kinds.get(n) for n in ("JumpSources", "JumpFallInterruptSources", "IdleAlias", "MoveAlias")] == ["alias"] * 4, "alias 4 (kind)")
    js = state_by_name(sm, "JumpSources")
    check(sorted(js["aliased_state_names"]) == ["Idle", "Move"] and js["global"] is False, f"JumpSources.aliased_state_names == [Idle, Move]: {js['aliased_state_names']}")
    sel = state_by_name(sm, "JumpSelector")
    check(sel.get("rule_generated") and sel.get("rule_source") == {"literal": True} and sel.get("rule_node_count") == 0, f"conduit rule_source 복원: {sel.get('rule_source')}")
    names = {s["node_guid"]: s["name"] for s in sm["states"]}
    pairs = sorted(f"{names[t['from']]}->{names[t['to']]}" for t in sm["transitions"])
    expected_pairs = sorted(["Idle->Move", "Move->Idle", "JumpSources->JumpSelector", "JumpSelector->JumpStart", "JumpSelector->FallLoop", "JumpStart->FallLoop",
                             "FallLoop->FallLand", "FallLand->EndInAir", "FallLand->EndInAir", "JumpFallInterruptSources->EndInAir", "EndInAir->IdleAlias", "EndInAir->MoveAlias"])
    check(pairs == expected_pairs, f"전이 from->to 12 쌍 == 운영 ({pairs == expected_pairs})")
    move_inner = sorted(n["class"] for n in s1["nodes"] if n["graph_guid"] == state_by_name(sm, "Move")["bound_graph_guid"])
    check(move_inner == ["AnimGraphNode_BlendSpacePlayer", "AnimGraphNode_StateResult", "K2Node_VariableGet"], f"Move 내부(같은 배치 graph:{{ref}}): {move_inner}")
    rev1 = s1["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== C. rename_node ===")
    r_ren = apply([
        {"op": "rename_node", "node": refs["idle"], "name": "Stand"},
        {"op": "rename_node", "node": refs["jumpsel"], "name": "AirSelector"},
        {"op": "rename_node", "node": refs["jumpsrc"], "name": "GroundSources"},
        {"op": "rename_node", "node": refs["sm"], "name": "Locomotion2"},
    ], expected=rev1)
    check(r_ren.get("ok") and [o.get("old_name") for o in r_ren["result"]["operations"]] == ["Idle", "JumpSelector", "JumpSources", "Locomotions"], "상태·conduit·alias·상태머신 이름 변경 (old_name 보고)")
    s2 = structure(-1)
    sm2 = the_sm(s2)
    names2 = {s["name"] for s in sm2["states"]}
    check({"Stand", "AirSelector", "GroundSources"} <= names2 and sm2["name"] == "Locomotion2", f"뷰에 새 이름 반영: {sorted(names2)[:4]}… sm={sm2['name']}")
    t_idle_move = next(t for t in sm2["transitions"] if t["node_guid"] == refs["t_idle_move"])
    check(t_idle_move["from_name"] == "Stand", f"전이 from_name 갱신: {t_idle_move['from_name']}")
    r_back = apply([
        {"op": "rename_node", "node": refs["idle"], "name": "Idle"},
        {"op": "rename_node", "node": refs["jumpsel"], "name": "JumpSelector"},
        {"op": "rename_node", "node": refs["jumpsrc"], "name": "JumpSources"},
        {"op": "rename_node", "node": refs["sm"], "name": "Locomotions"},
    ], expected=s2["revision"])
    check(r_back.get("ok") and structure(0)["revision"] == rev1, "이름 되돌리면 revision == 처음")
    for name, ops_bad, code in (
        ("중복 이름", [{"op": "rename_node", "node": refs["move"], "name": "Idle"}], "BAD_REQUEST"),
        ("전이 이름 변경", [{"op": "rename_node", "node": refs["t_idle_move"], "name": "X"}], "BAD_REQUEST"),
        ("빈 이름", [{"op": "rename_node", "node": refs["idle"], "name": " "}], "BAD_REQUEST"),
    ):
        env = preview(ops_bad)
        errs = planned_errors(env)
        check(env.get("ok") and not env["result"]["valid"] and code in errs, f"거부: {name} → {errs}")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== D. set_alias_states ===")
    env = preview([{"op": "set_alias_states", "node": refs["idlealias"], "global": True}])
    check(env.get("ok") and not env["result"]["valid"] and "BAD_REQUEST" in planned_errors(env), "전이 대상 alias 를 global 로 → 거부")
    env = preview([{"op": "set_alias_states", "node": refs["idlealias"], "states": [{"node": refs["idle"]}, {"node": refs["move"]}]}])
    check(env.get("ok") and not env["result"]["valid"], "전이 대상 alias 에 상태 2개 → 거부")
    r_alias = apply([{"op": "set_alias_states", "node": refs["jumpsrc"], "states": [{"node": refs["idle"]}]}], expected=rev1, compile=True)
    check(r_alias.get("ok") and r_alias["result"]["compile"].get("num_errors") == 0, "소스 alias 대상 [Idle, Move] → [Idle] + 컴파일")
    s3 = structure(-1)
    check(state_by_name(the_sm(s3), "JumpSources")["aliased_state_names"] == ["Idle"], "뷰: JumpSources → [Idle]")
    r_alias2 = apply([{"op": "set_alias_states", "node": refs["jumpsrc"], "global": True}], expected=s3["revision"], compile=True)
    check(r_alias2.get("ok") and r_alias2["result"]["compile"].get("num_errors") == 0, "소스 alias global → 컴파일 0 에러")
    s3b = structure(-1)
    check(state_by_name(the_sm(s3b), "JumpSources")["global"] is True and state_by_name(the_sm(s3b), "JumpSources")["aliased_states"] == [], "뷰: global=true, aliased_states=[]")
    r_alias3 = apply([{"op": "set_alias_states", "node": refs["jumpsrc"], "states": [{"node": refs["idle"]}, {"node": refs["move"]}]}], expected=s3b["revision"])
    check(r_alias3.get("ok") and structure(0)["revision"] == rev1, "대상 되돌리면 revision == 처음")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== E. 거부 (preview) ===")
    cases = {
        "conduit automatic 규칙": ([{"op": "set_transition_rule", "node": refs["jumpsel"], "rule": {"automatic": True}}], "BAD_REQUEST"),
        "add_conduit 에 automatic": ([{"op": "add_conduit", "sm": {"node": refs["sm"]}, "name": "C2", "rule": {"automatic": True}}], "BAD_REQUEST"),
        "conduit 그래프에 add_node": ([{"op": "add_node", "graph": {"node": refs["jumpsel"]}, "class": "AnimGraphNode_SequencePlayer", "asset": ASSETS["idle"]}], "BAD_REQUEST"),
        "conduit 를 alias 대상으로": ([{"op": "add_state_alias", "sm": {"node": refs["sm"]}, "name": "A1", "states": [{"node": refs["jumpsel"]}]}], "BAD_REQUEST"),
        "빈 alias": ([{"op": "add_state_alias", "sm": {"node": refs["sm"]}, "name": "A2"}], "BAD_REQUEST"),
        "global + states": ([{"op": "add_state_alias", "sm": {"node": refs["sm"]}, "name": "A3", "global": True, "states": [{"node": refs["idle"]}]}], "BAD_REQUEST"),
        "다중 alias 를 전이 대상으로": ([{"op": "add_transition", "from": {"node": refs["fallland"]}, "to": {"node": refs["jumpsrc"]}}], "BAD_REQUEST"),
        "alias 이름 중복": ([{"op": "add_state_alias", "sm": {"node": refs["sm"]}, "name": "IdleAlias", "states": [{"node": refs["idle"]}]}], "BAD_REQUEST"),
        "result_of 가 conduit": ([{"op": "connect", "from": {"ref": "x", "pin": "Pose"}, "to": {"result_of": {"node": refs["jumpsel"]}, "pin": "Result"}}], "BAD_REQUEST"),
    }
    for name, (ops_bad, code) in cases.items():
        env = preview(ops_bad)
        errs = planned_errors(env)
        check(env.get("ok") and not env["result"]["valid"] and code in errs, f"거부: {name} → {errs}")
    check(structure(0)["revision"] == rev1, "거부 preview 들이 그래프를 바꾸지 않음")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== F. 중간 실패 롤백 ===")
    bad = apply([
        {"op": "add_conduit", "ref": "c_new", "sm": {"node": refs["sm"]}, "name": "NewConduit", "rule": var("bIsFalling")},
        {"op": "add_state_alias", "ref": "a_new", "sm": {"node": refs["sm"]}, "name": "NewAlias", "global": True},
        {"op": "add_transition", "ref": "t_new", "from": {"ref": "a_new"}, "to": {"ref": "c_new"}, "rule": {"literal": True}},
        {"op": "rename_node", "node": refs["idle"], "name": "Renamed"},
        {"op": "rename_node", "node": refs["sm"], "name": "SMRenamed"},
        {"op": "set_alias_states", "node": refs["jumpsrc"], "global": True},
        {"op": "set_transition_rule", "node": refs["endinair"], "rule": var("bIsOnGround")},
        {"op": "remove_node", "node": refs["fallland"]},   # 전이 3개 연쇄
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "asset": ASSETS["idle"]},
        {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ])
    det = bad.get("error", {}).get("details", {})
    check(not bad.get("ok") and det.get("failed_index") == 9 and det.get("rollback_verified") is True, f"index 9 실패 → rollback_verified ({det.get('rollback_verified')})")
    s5 = structure(-1)
    check(s5["revision"] == rev1, "롤백 후 revision == 처음")
    sm5 = the_sm(s5)
    check(len(sm5["states"]) == 11 and len(sm5["transitions"]) == 12 and sm5["name"] == "Locomotions", "상태 11 · 전이 12 · 이름 복원")
    check(sorted(state_by_name(sm5, "JumpSources")["aliased_state_names"]) == ["Idle", "Move"], "alias 대상 복원")
    check(state_by_name(sm5, "EndInAir")["rule_source"] == {"literal": True}, "conduit 규칙 복원")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== G. 삭제 ===")
    r_del = apply([{"op": "remove_node", "node": refs["jumpsel"]}, {"op": "remove_node", "node": refs["interrupt"]}], expected=rev1, compile=True)
    check(r_del.get("ok") and r_del["result"]["compile"].get("num_errors") == 0, "conduit + alias 삭제 → 컴파일 0 에러")
    sm6 = the_sm(structure(-1))
    check(len(sm6["states"]) == 9 and len(sm6["transitions"]) == 8, f"상태 9 · 전이 8 (conduit 전이 3 + alias 전이 1 연쇄): {len(sm6['states'])}/{len(sm6['transitions'])}")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== H. 저장 → 재조회 ===")
    final = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": True}, timeout=bridge.COMPILE_TIMEOUT), "compile+save")
    check(final.get("ok") and final.get("num_errors") == 0, f"최종 컴파일 0 에러 (warnings={final.get('num_warnings')})")
    s7 = structure(-1)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"revision": s7["revision"], "nodes": sorted(n["node_guid"] for n in s7["nodes"]), "state_machines": s7["state_machines"]}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE} (revision {s7['revision']})")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = structure(-1)
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(sorted(n["node_guid"] for n in s["nodes"]) == saved["nodes"], "노드 Guid 집합 동일")
    check(s["state_machines"] == saved["state_machines"], "state_machines 뷰 동일 (alias 대상 · conduit 규칙 · 이름)")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        main_sections()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
