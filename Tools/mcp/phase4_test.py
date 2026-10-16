"""Phase 4 State Machine — add_state · add_transition · set_entry_state · set_transition_rule 과 상태머신 뷰를 검증한다.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase4_test.py [--recheck]

대상: /Game/Animation/Test/ABP_McpTest (덮어쓰기). 운영 애셋 ABP_Hero_Base 는 state_machines 뷰 덤프(읽기)만.
검사 항목(핸드오프 최종 지시):
  A. 운영 애셋 state_machines 뷰 (상태·전이·rule_generated=false 표기)
  B. 상태머신 구성 — 상태 3개 · Entry · 전이 4개(규칙: var / compare(float var vs literal, 첫 실측) / and·or·not / automatic / call) → 컴파일 0 에러
  C. 뷰: entry_state · from/to · rule_source 복원 · rule_modified=false
  D. 멱등 — 같은 AST 재적용 → unchanged, revision 동일. 다른 AST → 교체(replaced_nodes)
  E. 거부 — 없는 변수 · 타입 불일치 · 리터럴끼리 비교 · 화이트리스트 외 함수 · 전이 아닌 노드 · Entry 를 전이 끝점으로 · 이름 중복
  F. 롤백 — 상태 삭제(전이 연쇄) + 규칙 교체 + 전이 추가가 섞인 배치의 중간 실패 → rollback_verified, 전이 수 복원
  G. 저장 → --recheck 재조회 일치
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpTest"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase4_state.json"

FAILS: list[str] = []


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    FAILS.append(msg)


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:800]}")
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


def the_sm(struct: dict, sm_guid: str) -> dict:
    return next(sm for sm in struct["state_machines"] if sm["node_guid"] == sm_guid)


def transition_by_guid(sm: dict, guid: str) -> dict:
    return next(t for t in sm["transitions"] if t["node_guid"] == guid)


RULE_SPEED = {"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 10.0}}}
RULE_BOOL = {"var": "bIsFalling"}
RULE_LOGIC = {"and": [{"var": "bIsOnGround"}, {"not": {"var": "bIsJumping"}},
                      {"or": [{"compare": {"op": "<=", "left": {"var": "Speed"}, "right": {"literal": 1.0}}}, {"var": "bHasMovementInput"}]}]}
RULE_AUTO = {"automatic": True, "trigger_time": -1.0}
RULE_CALL = {"compare": {"op": ">", "left": {"call": {"function": "FMax", "args": {"A": {"var": "Speed"}, "B": {"literal": 0.0}}}},
                         "right": {"literal": 300.0}}}


def section_a() -> None:
    print("\n=== A. 운영 애셋 state_machines 뷰 ===")
    full = must(bridge.call("get_anim_graph_structure", {"asset_path": PROD, "depth": -1}, timeout=bridge.COMPILE_TIMEOUT), "prod dump")
    sms = full.get("state_machines", [])
    print(f"state machines: {len(sms)}")
    for sm in sms:
        print(f"  {sm['name']}: states={[s['name'] for s in sm['states']]} transitions={len(sm['transitions'])} entry={sm['entry_state']}")
    check("state_machines" in full, "structure 응답에 state_machines 존재")
    if sms:
        check(all(not t["rule_generated"] for sm in sms for t in sm["transitions"]), "운영 애셋 전이는 전부 rule_generated=false (도구가 만든 것 없음)")
        check(all(sm["entry_state"] for sm in sms), "모든 상태머신에 entry_state 있음")


def section_b_to_f() -> None:
    print("\n=== 준비: 테스트 AnimBP + StateMachine ===")
    assets = must(bridge.call("list_animation_assets", {"skeleton": SKELETON, "class": "AnimSequence", "limit": 50}), "list")["assets"]
    seqs = [a["asset_path"] for a in assets]
    idle = next((s for s in seqs if "Idle" in s), seqs[0])
    other = next((s for s in seqs if s != idle), seqs[1])
    info = must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    s0 = structure(0)
    root = next(n for n in s0["nodes"] if n["class"] == "AnimGraphNode_Root")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== B. 상태머신 구성 (상태 3 · Entry · 전이 4 · 규칙 4종) ===")
    ops = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-400, 0]},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
        {"op": "add_state", "ref": "idle", "sm": {"ref": "sm"}, "name": "Idle", "pos": [0, 0]},
        {"op": "add_state", "ref": "run", "sm": {"ref": "sm"}, "name": "Run", "pos": [400, 0]},
        {"op": "add_state", "ref": "fall", "sm": {"ref": "sm"}, "name": "Fall", "pos": [200, 300]},
        {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}},
        {"op": "add_transition", "ref": "t_idle_run", "from": {"ref": "idle"}, "to": {"ref": "run"},
         "properties": {"CrossfadeDuration": 0.15, "PriorityOrder": 2}, "rule": RULE_SPEED},
        {"op": "add_transition", "ref": "t_run_idle", "from": {"ref": "run"}, "to": {"ref": "idle"}, "rule": RULE_LOGIC},
        {"op": "add_transition", "ref": "t_any_fall", "from": {"ref": "idle"}, "to": {"ref": "fall"}, "rule": RULE_BOOL},
        {"op": "add_transition", "ref": "t_fall_idle", "from": {"ref": "fall"}, "to": {"ref": "idle"}},
        {"op": "set_transition_rule", "ref": "t_fall_idle", "rule": RULE_AUTO},
    ]
    pv = preview(ops)
    check(pv.get("ok") and pv["result"]["valid"], f"preview valid (create={pv.get('result', {}).get('would_create')} modify={pv.get('result', {}).get('would_modify')})")
    if not (pv.get("ok") and pv["result"]["valid"]):
        print(json.dumps(pv, ensure_ascii=False, indent=1)[:4000])
        sys.exit(1)
    r1 = apply(ops, expected=s0["revision"], compile=True)
    if not r1.get("ok"):
        print(json.dumps(r1, ensure_ascii=False, indent=1)[:5000])
        sys.exit(1)
    refs = r1["result"]["refs"]
    comp = r1["result"]["compile"]
    for m in comp.get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")
    check(comp.get("ok") and comp.get("num_errors") == 0, f"apply+compile 0 에러 (warnings={comp.get('num_warnings')})")
    t_entry = next(o for o in r1["result"]["operations"] if o["op"] == "add_transition" and o["ref"] == "t_idle_run")
    print(f"t_idle_run rule_nodes={t_entry.get('rule_nodes')} source={t_entry.get('rule_source')}")
    check(t_entry.get("rule_nodes") == 2, "float 변수 > literal 규칙 = VariableGet + Greater_DoubleDouble 2 노드 (float→double 핀 호환 실측)")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== C. 상태머신 뷰 ===")
    s1 = structure(-1)
    sm = the_sm(s1, refs["sm"])
    names = {s["node_guid"]: s["name"] for s in sm["states"]}
    check(sorted(names.values()) == ["Fall", "Idle", "Run"], f"상태 3개 이름: {sorted(names.values())}")
    check(sm["entry_state"] == refs["idle"], "entry_state == Idle")
    check(len(sm["transitions"]) == 4, f"전이 4개: {len(sm['transitions'])}")
    t1 = transition_by_guid(sm, refs["t_idle_run"])
    check(t1["from"] == refs["idle"] and t1["to"] == refs["run"], "t_idle_run from/to")
    check(abs(t1["crossfade_duration"] - 0.15) < 1e-6 and t1["priority_order"] == 2, f"add_transition properties 반영: crossfade={t1['crossfade_duration']} priority={t1['priority_order']}")
    check(t1["rule_generated"] and t1["rule_source"] == RULE_SPEED and not t1["rule_modified"], f"rule_source 복원: {t1['rule_source']}")
    t2 = transition_by_guid(sm, refs["t_run_idle"])
    check(t2["rule_source"] == RULE_LOGIC and t2["rule_node_count"] == 9, f"and/or/not 규칙 복원, 노드 {t2['rule_node_count']}개 (var×4 + compare + not + and×2 + or)")
    t4 = transition_by_guid(sm, refs["t_fall_idle"])
    check(t4["automatic"] and t4["rule_generated"] and t4["rule_node_count"] == 0, "automatic 규칙: 플래그 on, 규칙 노드 0, 원문 기록")
    rev1 = s1["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== D. 멱등 / 교체 / call ===")
    r2 = apply([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": RULE_SPEED}], expected=rev1)
    check(r2.get("ok") and r2["result"]["operations"][0].get("unchanged") is True, "같은 AST 재적용 → unchanged")
    check(r2.get("ok") and r2["result"]["revision_after"] == rev1, "같은 AST 재적용 → revision 동일")
    r3 = apply([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": RULE_CALL}], expected=rev1, compile=True)
    if not r3.get("ok"):
        print(json.dumps(r3, ensure_ascii=False, indent=1)[:3000])
    check(r3.get("ok") and r3["result"]["compile"].get("ok"), "call(FMax, KismetMathLibrary) 규칙으로 교체 + 컴파일 0 에러")
    check(r3.get("ok") and r3["result"]["operations"][0].get("replaced_nodes") == 3, f"교체 시 이전 규칙 노드 2 + 주석 1 = 3 분리: {r3.get('result', {}).get('operations', [{}])[0].get('replaced_nodes')}")
    s3 = structure(-1)
    t1b = transition_by_guid(the_sm(s3, refs["sm"]), refs["t_idle_run"])
    check(t1b["rule_source"] == RULE_CALL and not t1b["rule_modified"], "교체 후 rule_source == call AST")
    rev3 = s3["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== E. 거부 케이스 (preview) ===")
    cases = {
        "없는 변수": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"var": "NoSuchVar"}}], "BAD_REQUEST"),
        "최상위가 bool 아님": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"var": "Speed"}}], "BAD_REQUEST"),
        "리터럴끼리 비교": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"compare": {"op": "==", "left": {"literal": 1}, "right": {"literal": 1}}}}], "BAD_REQUEST"),
        "bool 에 순서 비교": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"compare": {"op": ">", "left": {"var": "bIsFalling"}, "right": {"literal": True}}}}], "BAD_REQUEST"),
        "화이트리스트 외 함수(비 ThreadSafe)": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"call": {"function": "PrintString", "class": "/Script/Engine.KismetSystemLibrary", "args": {}}}}], "PROPERTY_NOT_ALLOWED"),
        "전이 아닌 노드에 규칙": ([{"op": "set_transition_rule", "node": refs["idle"], "rule": RULE_BOOL}], "BAD_REQUEST"),
        "Entry 를 전이 끝점으로": ([{"op": "add_transition", "from": {"node": sm["entry_node_guid"]}, "to": {"node": refs["run"]}}], "BAD_REQUEST"),
        "상태 이름 중복": ([{"op": "add_state", "sm": {"node": refs["sm"]}, "name": "Idle"}], "BAD_REQUEST"),
        "자동 규칙 중첩": ([{"op": "set_transition_rule", "node": refs["t_idle_run"], "rule": {"not": {"automatic": True}}}], "BAD_REQUEST"),
    }
    for name, (ops_bad, code) in cases.items():
        env = preview(ops_bad)
        errs = planned_errors(env)
        check(env.get("ok") and not env["result"]["valid"] and code in errs, f"거부: {name} → {errs}")
    check(structure(0)["revision"] == rev3, "거부 preview 들이 그래프를 바꾸지 않음")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== F. 중간 실패 배치 → 롤백 (상태 삭제 연쇄 · 규칙 교체 · 전이 추가 · Entry 변경) ===")
    bad = apply([
        {"op": "set_transition_rule", "node": refs["t_run_idle"], "rule": RULE_BOOL},
        {"op": "set_entry_state", "sm": {"node": refs["sm"]}, "state": {"node": refs["run"]}},
        {"op": "add_state", "ref": "jump", "sm": {"node": refs["sm"]}, "name": "Jump", "pos": [600, 300]},
        {"op": "add_transition", "ref": "t_run_jump", "from": {"node": refs["run"]}, "to": {"ref": "jump"}, "rule": RULE_BOOL},
        {"op": "remove_node", "node": refs["fall"]},   # t_any_fall · t_fall_idle 연쇄 분리
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "asset": idle},
        {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ])
    det = bad.get("error", {}).get("details", {})
    print(f"bad code={bad.get('error', {}).get('code')} failed_index={det.get('failed_index')} rollback_verified={det.get('rollback_verified')}")
    check(not bad.get("ok") and det.get("failed_index") == 6, "apply 중간(index 6) 실패")
    check(det.get("rollback_verified") is True, "rollback_verified=true")
    s5 = structure(-1)
    check(s5["revision"] == rev3, "롤백 후 revision == 실패 전")
    sm5 = the_sm(s5, refs["sm"])
    check(len(sm5["transitions"]) == 4 and len(sm5["states"]) == 3, f"상태 3 · 전이 4 복원: {len(sm5['states'])}/{len(sm5['transitions'])}")
    check(sm5["entry_state"] == refs["idle"], "Entry 복원 == Idle")
    check(transition_by_guid(sm5, refs["t_run_idle"])["rule_source"] == RULE_LOGIC, "t_run_idle 규칙 복원")
    if s5["revision"] != rev3:
        before = {n["node_guid"]: n for n in s3["nodes"]}
        after = {n["node_guid"]: n for n in s5["nodes"]}
        for g in set(before) - set(after):
            print(f"   DIFF missing {before[g]['class']} {g}")
        for g in set(after) - set(before):
            print(f"   DIFF extra {after[g]['class']} {g}")
        for g in set(before) & set(after):
            pb = {p["name"]: (p["default"], tuple(p["linked"])) for p in before[g]["pins"]}
            pa = {p["name"]: (p["default"], tuple(p["linked"])) for p in after[g]["pins"]}
            if pb != pa or before[g]["properties"] != after[g]["properties"]:
                print(f"   DIFF {before[g]['class']} {g}\n     before {pb} {before[g]['properties']}\n     after  {pa} {after[g]['properties']}")

    # 성공 경로: 상태 삭제 연쇄
    r6 = apply([{"op": "remove_node", "node": refs["fall"]}], expected=rev3, compile=True)
    check(r6.get("ok") and r6["result"]["compile"].get("ok"), "Fall 상태 삭제 + 컴파일")
    sm6 = the_sm(structure(-1), refs["sm"])
    check(len(sm6["states"]) == 2 and len(sm6["transitions"]) == 2, f"상태 2 · 전이 2 (Fall 의 전이 2개 연쇄 삭제): {len(sm6['states'])}/{len(sm6['transitions'])}")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== G. 저장 → 재조회 ===")
    final = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": True}, timeout=bridge.COMPILE_TIMEOUT), "compile+save")
    for m in final.get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")
    check(final.get("ok") and final.get("num_errors") == 0, f"최종 컴파일 0 에러 (warnings={final.get('num_warnings')})")
    s7 = structure(-1)
    state = {"revision": s7["revision"], "nodes": sorted(n["node_guid"] for n in s7["nodes"]),
             "state_machines": s7["state_machines"]}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE} (revision {s7['revision']})")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = structure(-1)
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(sorted(n["node_guid"] for n in s["nodes"]) == saved["nodes"], "노드 Guid 집합 동일")
    check(s["state_machines"] == saved["state_machines"], "state_machines 뷰 동일 (rule_source · entry · 전이)")
    info = must(bridge.call("get_anim_blueprint_info", {"asset_path": ABP}), "info")
    print(f"status after restart: {info['status']}")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {sorted(t['name'] for t in status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        section_a()
        section_b_to_f()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
