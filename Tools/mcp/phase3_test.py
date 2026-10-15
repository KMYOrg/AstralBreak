"""Phase 3 범용 AnimGraph 편집 — 신규 op 7종의 성공·거부·롤백과 revision 규칙을 검증한다.

    MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase3_test.py

대상: /Game/Animation/Test/ABP_McpTest (덮어쓰기). 운영 애셋 ABP_Hero_Base 는 depth=-1 전체 덤프(읽기)만 한다.
검사 항목(핸드오프 §14.4):
  A. 운영 애셋 전체 덤프 성공 + revision 계산 시간, 바인딩·Linked Layer 표기
  B. 신규 op 가 preview 에서 허용/거부로 갈린다 (허용 목록 외 프로퍼티 · 삭제 불가 노드 · 안 이어진 핀 disconnect · 잘못된 enum 요소)
  C. 속성만 바꾼 변경이 revision 을 바꾼다 / 같은 값 재적용은 revision 유지
  D. 중간 실패 배치의 rollback_verified=true (remove_node · expose_pin · set_property · add_blend_pose 가 포함된 배치)
  E. 같은 배치 2회 적용 → 2회째 REVISION_MISMATCH
  F. 컴파일 0 에러 + 저장 → 재조회 일치 (재시작 후 비교는 phase3_recheck.py 가 아니라 --recheck 인자)
"""
from __future__ import annotations

import json
import sys
import time

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpTest"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase3_state.json"

FAILS: list[str] = []


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    FAILS.append(msg)


def check(cond: bool, msg: str) -> bool:
    if cond:
        print(f"[ ok ] {msg}")
    else:
        fail(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:600]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def structure(depth: int = 0) -> dict:
    return must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": depth}), "structure")


def node_by_guid(struct: dict, guid: str) -> dict | None:
    return next((n for n in struct["nodes"] if n["node_guid"] == guid), None)


def apply(ops: list, expected: str | None = None, **kw) -> dict:
    params = {"asset_path": ABP, "operations": ops, **kw}
    if expected:
        params["expected_revision"] = expected
    return bridge.call("apply_graph_operations", params, timeout=bridge.COMPILE_TIMEOUT)


def preview(ops: list) -> dict:
    return bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops})


def planned_errors(env: dict) -> list[str]:
    return [p.get("error", {}).get("code", "") for p in env.get("result", {}).get("planned", []) if not p["ok"]]


# ---------------------------------------------------------------------------------------------------------------------

def section_a_production_dump() -> None:
    print("\n=== A. 운영 애셋 전체 덤프 (읽기만) ===")
    t0 = time.perf_counter()
    info = must(bridge.call("get_anim_blueprint_info", {"asset_path": PROD}), "prod info")
    t1 = time.perf_counter()
    full = must(bridge.call("get_anim_graph_structure", {"asset_path": PROD, "depth": -1}, timeout=bridge.COMPILE_TIMEOUT), "prod full dump")
    t2 = time.perf_counter()
    nodes = full["nodes"]
    bound = [n for n in nodes if n.get("has_binding")]
    layers = [n for n in nodes if n["class"] == "AnimGraphNode_LinkedAnimLayer"]
    print(f"graphs={len(full['graphs'])} nodes={len(nodes)} connections={len(full['connections'])} "
          f"linked_layers={len(layers)} (info says {info['linked_anim_layer_count']}) nodes_with_binding={len(bound)}")
    print(f"timing: info(revision 1회)={1000 * (t1 - t0):.0f}ms  full dump(revision 1회+직렬화)={1000 * (t2 - t1):.0f}ms")
    check(len(full["graphs"]) >= 1 and len(nodes) > 0, "운영 애셋 전체 덤프 성공")
    check(len(layers) == info["linked_anim_layer_count"], "Linked Layer 수가 info 와 일치")
    check(all("properties" in n for n in nodes), "모든 노드에 properties 존재")
    check(all("optional_pins" in n and "has_binding" in n for n in nodes if n["class"].startswith("AnimGraphNode_")),
          "AnimGraph 노드 전부에 optional_pins/has_binding 존재 (State·Transition·Entry 노드는 해당 없음)")
    check(info["revision"] == full["revision"], "info 와 structure 의 revision 일치 (조회가 상태를 바꾸지 않음)")
    # 두 번 계산해도 같아야 한다 (결정성)
    again = must(bridge.call("get_anim_blueprint_info", {"asset_path": PROD}), "prod info again")
    check(again["revision"] == info["revision"], "revision 결정적 (2회 계산 동일)")


def section_b_to_f() -> dict:
    print("\n=== 준비: 테스트 AnimBP 생성 ===")
    assets = must(bridge.call("list_animation_assets", {"skeleton": SKELETON, "class": "AnimSequence", "limit": 50}), "list assets")
    seqs = [a["asset_path"] for a in assets["assets"]]
    if len(seqs) < 2:
        print("[FAIL] need at least two AnimSequences for the skeleton")
        sys.exit(1)
    idle = next((s for s in seqs if "Idle" in s), seqs[0])
    other = next((s for s in seqs if s != idle), seqs[1])
    blendspaces = must(bridge.call("list_animation_assets", {"skeleton": SKELETON, "class": "BlendSpace", "limit": 10}), "list bs")["assets"]
    bs = blendspaces[0]["asset_path"] if blendspaces else None
    print(f"idle={idle}\nother={other}\nblendspace={bs}")

    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    s0 = structure()
    root = next(n for n in s0["nodes"] if n["class"] == "AnimGraphNode_Root")
    root_guid = root["node_guid"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 1. 노드 종류 확대 + properties 인라인 + 연결 ===")
    ops = [
        {"op": "add_node", "ref": "idle", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, -200], "asset": idle,
         "properties": {"bLoopAnimation": True, "PlayRate": 1.25}},
        {"op": "add_node", "ref": "walk", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 200], "asset": other},
        # 포즈 출력 핀은 단일 연결(스키마가 BREAK_OTHERS) — save 에는 별도 플레이어를 잇는다
        {"op": "add_node", "ref": "walk2", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 400], "asset": other},
        {"op": "add_node", "ref": "bybool", "class": "AnimGraphNode_BlendListByBool", "pos": [-600, 0]},
        {"op": "add_node", "ref": "slot", "class": "AnimGraphNode_Slot", "pos": [-300, 0], "properties": {"SlotName": "UpperBody"}},
        {"op": "add_node", "ref": "save", "class": "AnimGraphNode_SaveCachedPose", "pos": [-600, 400], "properties": {"CacheName": "McpCache"}},
        {"op": "add_node", "ref": "use", "class": "AnimGraphNode_UseCachedPose", "pos": [-300, 400]},
        {"op": "set_property", "ref": "use", "property": "SaveCachedPoseNode", "value": {"ref": "save"}},
        {"op": "add_node", "ref": "layered", "class": "AnimGraphNode_LayeredBoneBlend", "pos": [0, 400]},
        {"op": "add_blend_pose", "ref": "layered"},
        {"op": "add_node", "ref": "byenum", "class": "AnimGraphNode_BlendListByEnum", "pos": [0, 800], "enum": "/Script/Engine.EAlphaBlendOption"},
        {"op": "add_blend_pose", "ref": "byenum", "entry": "Linear"},
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [0, -400]},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"ref": "bybool", "pin": "BlendPose_0"}},
        {"op": "connect", "from": {"ref": "walk", "pin": "Pose"}, "to": {"ref": "bybool", "pin": "BlendPose_1"}},
        {"op": "connect", "from": {"ref": "bybool", "pin": "Pose"}, "to": {"ref": "slot", "pin": "Source"}},
        {"op": "connect", "from": {"ref": "slot", "pin": "Pose"}, "to": {"node": root_guid, "pin": "Result"}},
        {"op": "connect", "from": {"ref": "walk2", "pin": "Pose"}, "to": {"ref": "save", "pin": "Pose"}},
    ]
    if bs:
        ops.append({"op": "add_node", "ref": "bsp", "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-900, 600], "asset": bs,
                    "properties": {"bLoop": True, "PlayRate": 0.5}})
    pv = preview(ops)
    check(pv.get("ok") and pv["result"]["valid"], f"preview valid (would_create={pv.get('result', {}).get('would_create')} modify={pv.get('result', {}).get('would_modify')})")
    if not pv.get("ok") or not pv["result"]["valid"]:
        print(json.dumps(pv, ensure_ascii=False, indent=1)[:3000])
        sys.exit(1)
    check(pv["result"]["revision"] == s0["revision"], "preview 가 그래프를 바꾸지 않음")

    r1 = apply(ops, expected=s0["revision"], compile=True)
    if not r1.get("ok"):
        print(json.dumps(r1, ensure_ascii=False, indent=1)[:4000])
        sys.exit(1)
    refs = r1["result"]["refs"]
    comp = r1["result"]["compile"]
    check(comp.get("ok") and comp.get("num_errors") == 0, f"apply+compile ok (errors={comp.get('num_errors')} warnings={comp.get('num_warnings')})")
    for m in comp.get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")

    s1 = structure(depth=1)
    idle_n = node_by_guid(s1, refs["idle"])
    slot_n = node_by_guid(s1, refs["slot"])
    use_n = node_by_guid(s1, refs["use"])
    layered_n = node_by_guid(s1, refs["layered"])
    byenum_n = node_by_guid(s1, refs["byenum"])
    sm_n = node_by_guid(s1, refs["sm"])
    check(idle_n["properties"].get("bLoopAnimation") is True and abs(idle_n["properties"].get("PlayRate", 0) - 1.25) < 1e-6,
          f"add_node properties 반영: {idle_n['properties']}")
    check(slot_n["properties"].get("SlotName") == "UpperBody", f"Slot.SlotName 반영: {slot_n['properties']}")
    check(use_n["properties"].get("SaveCachedPoseNode") == refs["save"], "UseCachedPose.SaveCachedPoseNode = save 노드 guid")
    layered_pins = [p["name"] for p in layered_n["pins"] if p["dir"] == "in"]
    check("BlendPoses_1" in layered_pins, f"LayeredBoneBlend 포즈 2개: {layered_pins}")
    byenum_pins = [p["name"] for p in byenum_n["pins"] if p["dir"] == "in"]
    check("BlendPose_1" in byenum_pins, f"BlendListByEnum Linear 포즈 노출: {byenum_pins}")
    check("EAlphaBlendOption" in str(byenum_n["properties"].get("BoundEnum")), f"BlendListByEnum enum 바인딩: {byenum_n['properties'].get('BoundEnum')}")
    check(len(sm_n["sub_graphs"]) == 1 and any(g["graph_guid"] == sm_n["sub_graphs"][0] for g in s1["graphs"]),
          "StateMachine 생성 시 서브그래프(Entry 포함) 자동 생성")
    check(len(s1["connections"]) == 5, f"연결 5개: {len(s1['connections'])}")
    rev1 = s1["revision"]
    check(rev1 == r1["result"]["revision_after"], "재조회 revision == revision_after")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 2. preview 거부 케이스 ===")
    cases = {
        "허용 목록 외 프로퍼티": ([{"op": "set_property", "node": refs["idle"], "property": "PlayRateBasisX", "value": 1}], "PROPERTY_NOT_ALLOWED"),
        "읽기 전용 프로퍼티": ([{"op": "set_property", "node": refs["byenum"], "property": "BoundEnum", "value": "x"}], "PROPERTY_NOT_ALLOWED"),
        "타입 불일치(bool 에 숫자)": ([{"op": "set_property", "node": refs["idle"], "property": "bLoopAnimation", "value": 1}], "BAD_REQUEST"),
        "Output Pose 삭제": ([{"op": "remove_node", "node": root_guid}], "BAD_REQUEST"),
        "안 이어진 핀 disconnect": ([{"op": "disconnect", "from": {"node": refs["idle"], "pin": "Pose"}, "to": {"node": root_guid, "pin": "Result"}}], "BAD_REQUEST"),
        "없는 optional pin": ([{"op": "expose_pin", "node": refs["idle"], "property": "NoSuchPin"}], "PIN_NOT_FOUND"),
        "enum 요소 아님": ([{"op": "add_blend_pose", "node": refs["byenum"], "entry": "NotAnElement"}], "BAD_REQUEST"),
        "enum 요소 중복": ([{"op": "add_blend_pose", "node": refs["byenum"], "entry": "Linear"}], "BAD_REQUEST"),
        "set_asset 비플레이어": ([{"op": "set_asset", "node": refs["slot"], "asset": idle}], "BAD_REQUEST"),
        "삭제된 노드 참조": ([{"op": "remove_node", "node": refs["walk"]}, {"op": "set_property", "node": refs["walk"], "property": "PlayRate", "value": 2}], "NODE_NOT_FOUND"),
    }
    for name, (ops_bad, code) in cases.items():
        env = preview(ops_bad)
        errs = planned_errors(env)
        check(env.get("ok") and not env["result"]["valid"] and code in errs, f"거부: {name} → {errs}")
    s_after_preview = structure()
    check(s_after_preview["revision"] == rev1, "거부 preview 들이 그래프를 바꾸지 않음")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 3. 속성만 바꾼 변경이 revision 을 바꾼다 ===")
    r2 = apply([{"op": "set_property", "node": refs["idle"], "property": "PlayRate", "value": 2.0}], expected=rev1)
    check(r2.get("ok"), "set_property PlayRate=2.0 apply")
    rev2 = r2["result"]["revision_after"]
    check(rev2 != rev1, "속성 변경 → revision 변경")
    check(node_by_guid(structure(), refs["idle"])["properties"]["PlayRate"] == 2.0, "재조회 PlayRate == 2.0")
    r2b = apply([{"op": "set_property", "node": refs["idle"], "property": "PlayRate", "value": 2.0}], expected=rev2)
    check(r2b.get("ok") and r2b["result"]["revision_after"] == rev2, "같은 값 재적용 → revision 유지")

    print("\n=== 4. expose_pin · set_asset · disconnect · remove_node (성공 경로) ===")
    r3 = apply([
        {"op": "expose_pin", "node": refs["idle"], "property": "PlayRate", "visible": True},
        {"op": "set_asset", "node": refs["walk"], "asset": idle},
        {"op": "disconnect", "from": {"node": refs["walk2"], "pin": "Pose"}, "to": {"node": refs["save"], "pin": "Pose"}},
        {"op": "remove_node", "node": refs["use"]},
    ], expected=rev2, compile=True)
    check(r3.get("ok") and r3["result"]["compile"].get("ok"), "expose_pin/set_asset/disconnect/remove_node apply+compile")
    if not r3.get("ok"):
        print(json.dumps(r3, ensure_ascii=False, indent=1)[:3000])
    s3 = structure()
    idle3 = node_by_guid(s3, refs["idle"])
    check(any(p["name"] == "PlayRate" and p["dir"] == "in" and not p["hidden"] for p in idle3["pins"]), "PlayRate 핀 노출됨")
    check(any(o["property"] == "PlayRate" and o["shown"] for o in idle3["optional_pins"]), "optional_pins 에 shown=true")
    check(node_by_guid(s3, refs["walk"])["asset"] == idle, "set_asset 반영")
    check(node_by_guid(s3, refs["use"]) is None, "remove_node 로 use 노드 사라짐")
    check(len(s3["connections"]) == 4, f"disconnect 로 연결 4개: {len(s3['connections'])}")
    rev3 = s3["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 5. 중간 실패 배치 → 보상 롤백 검증 ===")
    bad = apply([
        {"op": "set_property", "node": refs["idle"], "property": "PlayRate", "value": 3.0},
        {"op": "expose_pin", "node": refs["idle"], "property": "PlayRate", "visible": False},
        {"op": "add_blend_pose", "node": refs["layered"]},
        {"op": "add_blend_pose", "node": refs["byenum"], "entry": "Cubic"},
        {"op": "remove_node", "node": refs["slot"]},
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "asset": idle},
        {"op": "connect", "from": {"ref": "tmp", "pin": "Pose"}, "to": {"node": root_guid, "pin": "Result"}},
        {"op": "set_asset", "node": refs["walk"], "asset": other},
        {"op": "disconnect", "from": {"node": refs["idle"], "pin": "Pose"}},
        # 마지막 op 가 apply 시점에 실패: 삭제된 slot 을 다시 가리킨다 (preview 는 통과 못 하므로 expected 없이 apply 만 — 사전 검증도 걸린다)
        {"op": "set_property", "node": refs["slot"], "property": "SlotName", "value": "X"},
    ])
    check(not bad.get("ok") and bad["error"]["code"] == "BAD_REQUEST", "사전 검증이 잡아 무변경 (삭제 노드 재참조)")
    check(structure()["revision"] == rev3, "사전 검증 실패 → revision 불변")

    # apply 단계 실패를 만들기: preview/사전 검증은 통과하지만 apply 에서 실패하는 케이스 = 미생성 ref 의 없는 핀
    bad2 = apply([
        {"op": "set_property", "node": refs["idle"], "property": "PlayRate", "value": 3.0},
        {"op": "expose_pin", "node": refs["idle"], "property": "PlayRate", "visible": False},
        {"op": "add_blend_pose", "node": refs["layered"]},
        {"op": "add_blend_pose", "node": refs["byenum"], "entry": "Cubic"},
        {"op": "remove_node", "node": refs["slot"]},
        {"op": "set_asset", "node": refs["walk"], "asset": other},
        {"op": "disconnect", "from": {"node": refs["idle"], "pin": "Pose"}},
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "asset": idle},
        {"op": "connect", "from": {"ref": "tmp", "pin": "Pose"}, "to": {"node": root_guid, "pin": "Result"}},
        {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root_guid, "pin": "Result"}},
    ])
    det = bad2.get("error", {}).get("details", {})
    print(f"bad2 code={bad2.get('error', {}).get('code')} failed_index={det.get('failed_index')} rollback_verified={det.get('rollback_verified')}")
    check(not bad2.get("ok") and det.get("failed_index") == 9, "apply 중간(index 9) 실패")
    check(det.get("rollback_verified") is True, "rollback_verified=true (set_property·expose_pin·add_blend_pose×2·remove_node·set_asset·disconnect·add_node·connect 되돌림)")
    s5 = structure()
    if s5["revision"] != rev3:
        # 어디가 달라졌는지 바로 보이게 — 노드별 핀 이름·기본값·연결과 프로퍼티를 비교
        before = {n["node_guid"]: n for n in s3["nodes"]}
        for n in s5["nodes"]:
            b = before.get(n["node_guid"])
            if b is None:
                print(f"   DIFF extra node {n['class']} {n['node_guid']}")
                continue
            pins_b = {p["name"]: (p["default"], tuple(p["linked"]), p["hidden"]) for p in b["pins"]}
            pins_a = {p["name"]: (p["default"], tuple(p["linked"]), p["hidden"]) for p in n["pins"]}
            if pins_a != pins_b or n["properties"] != b["properties"] or n["optional_pins"] != b["optional_pins"]:
                print(f"   DIFF {n['class']} {n['node_guid']}\n      before pins={pins_b}\n      after  pins={pins_a}\n      before props={b['properties']}\n      after  props={n['properties']}")
        for guid in set(before) - {n["node_guid"] for n in s5["nodes"]}:
            print(f"   DIFF missing node {before[guid]['class']} {guid}")
    check(s5["revision"] == rev3, "롤백 후 revision == 실패 전")
    check(node_by_guid(s5, refs["slot"]) is not None, "분리 보관된 slot 노드 복귀")
    check(node_by_guid(s5, refs["idle"])["properties"]["PlayRate"] == 2.0, "PlayRate 2.0 으로 복원")
    check(len(s5["connections"]) == 4, "연결 수 복원")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 6. 같은 배치 2회 → REVISION_MISMATCH ===")
    ops6 = [{"op": "set_property", "node": refs["idle"], "property": "StartPosition", "value": 0.1}]
    r6 = apply(ops6, expected=rev3)
    check(r6.get("ok"), "1회 적용")
    r6b = apply(ops6, expected=rev3)
    check(not r6b.get("ok") and r6b["error"]["code"] == "REVISION_MISMATCH", "2회째 REVISION_MISMATCH")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== 7. 컴파일 + 저장 → 재조회 ===")
    final = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": True}, timeout=bridge.COMPILE_TIMEOUT), "compile+save")
    check(final.get("ok") and final.get("num_errors") == 0, f"최종 컴파일 0 에러 (warnings={final.get('num_warnings')})")
    for m in final.get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")
    s7 = structure(depth=-1)
    state = {"revision": s7["revision"], "nodes": sorted(n["node_guid"] for n in s7["nodes"]),
             "connections": sorted(json.dumps(c, sort_keys=True) for c in s7["connections"]),
             "properties": {n["node_guid"]: n["properties"] for n in s7["nodes"]}}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    print(f"saved state for --recheck → {STATE_FILE} (revision {s7['revision']})")
    return state


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 비교 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": -1}), "structure after restart")
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(sorted(n["node_guid"] for n in s["nodes"]) == saved["nodes"], "노드 Guid 집합 동일")
    check(sorted(json.dumps(c, sort_keys=True) for c in s["connections"]) == saved["connections"], "연결 동일")
    props = {n["node_guid"]: n["properties"] for n in s["nodes"]}
    check(props == saved["properties"], "허용 목록 프로퍼티 값 동일")
    info = must(bridge.call("get_anim_blueprint_info", {"asset_path": ABP}), "info")
    print(f"status after restart: {info['status']}")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {sorted(t['name'] for t in status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        section_a_production_dump()
        section_b_to_f()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
