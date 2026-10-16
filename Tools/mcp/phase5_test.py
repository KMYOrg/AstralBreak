"""Phase 5 — LayeredBoneBlend.LayerSetup(본 필터) set_property 와 구조체 배열 JSON 변환을 검증한다.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase5_test.py [--recheck]

대상: /Game/Animation/Test/ABP_McpLayerTest (덮어쓰기). 운영 애셋은 건드리지 않는다.
K2Node_VariableGet · 상태 내부 채우기는 phase4_test.py B2 절이 덮는다.
검사 항목:
  A. 루트에 Base(Sequence) + Upper(Sequence) + LayeredBoneBlend(1 포즈) → set_property LayerSetup [{BranchFilters:[{spine_01, 0}]}]
     → 연결 → 컴파일 0 에러 · properties.LayerSetup 이 JSON 객체 배열로 돌아온다 · BlendMode 조회
  B. add_blend_pose → 2 포즈 → LayerSetup 2 항목(둘째는 필터 없음 {}) → 컴파일 0 에러
  C. 거부 — 항목 수 불일치 · 없는 본 · 없는 필드 · 다른 노드 클래스 · 잘못된 BlendMode 값 · 배열 아님
  D. 롤백 — LayerSetup 변경 + 실패 op 배치 → rollback_verified · properties 원복
  E. 저장 → --recheck 재조회 일치
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpLayerTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase5_state.json"
UPPER_BONE = "spine_01"

FAILS: list[str] = []


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


def structure(depth: int = 0) -> dict:
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


def node_by_guid(struct: dict, guid: str) -> dict:
    return next(n for n in struct["nodes"] if n["node_guid"] == guid)


LAYER_1 = [{"BranchFilters": [{"BoneName": UPPER_BONE, "BlendDepth": 0}]}]
LAYER_2 = [{"BranchFilters": [{"BoneName": UPPER_BONE, "BlendDepth": 0}]}, {}]


def main_sections() -> None:
    print("\n=== 준비: 테스트 AnimBP ===")
    assets = must(bridge.call("list_animation_assets", {"skeleton": SKELETON, "class": "AnimSequence", "limit": 50}), "list")["assets"]
    seqs = [a["asset_path"] for a in assets]
    idle = next((s for s in seqs if "Idle" in s), seqs[0])
    other = next((s for s in seqs if s != idle), seqs[1])
    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    s0 = structure(0)
    root = next(n for n in s0["nodes"] if n["class"] == "AnimGraphNode_Root")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== A. LayerSetup 1 포즈 ===")
    ops = [
        {"op": "add_node", "ref": "base", "class": "AnimGraphNode_SequencePlayer", "pos": [-700, -100], "asset": idle, "properties": {"bLoopAnimation": True}},
        {"op": "add_node", "ref": "upper", "class": "AnimGraphNode_SequencePlayer", "pos": [-700, 200], "asset": other, "properties": {"bLoopAnimation": True}},
        {"op": "add_node", "ref": "layer", "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-300, 0]},
        {"op": "set_property", "ref": "layer", "property": "LayerSetup", "value": LAYER_1},
        {"op": "connect", "from": {"ref": "base", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "upper", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BlendPoses_0"}},
        {"op": "connect", "from": {"ref": "layer", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]
    pv = preview(ops)
    check(pv.get("ok") and pv["result"]["valid"], f"preview valid (modify={pv.get('result', {}).get('would_modify')})")
    if not (pv.get("ok") and pv["result"]["valid"]):
        print(json.dumps(pv, ensure_ascii=False, indent=1)[:3000])
        sys.exit(1)
    r1 = apply(ops, expected=s0["revision"], compile=True)
    if not r1.get("ok"):
        print(json.dumps(r1, ensure_ascii=False, indent=1)[:4000])
        sys.exit(1)
    refs = r1["result"]["refs"]
    for m in r1["result"]["compile"].get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")
    check(r1["result"]["compile"].get("num_errors") == 0, f"apply+compile 0 에러 (warnings={r1['result']['compile'].get('num_warnings')})")
    s1 = structure(0)
    layer = node_by_guid(s1, refs["layer"])
    print(f"properties: {json.dumps(layer['properties'], ensure_ascii=False)}")
    check(layer["properties"].get("LayerSetup") == LAYER_1, "properties.LayerSetup 이 넣은 JSON 과 같다 (구조체 배열 → 객체 배열)")
    check("BranchFilter" in str(layer["properties"].get("BlendMode")), f"BlendMode 조회: {layer['properties'].get('BlendMode')}")
    rev1 = s1["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== B. add_blend_pose → 2 포즈 → LayerSetup 2 항목 ===")
    r2 = apply([
        {"op": "add_blend_pose", "node": refs["layer"]},
        {"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": LAYER_2},
    ], expected=rev1, compile=True)
    if not r2.get("ok"):
        print(json.dumps(r2, ensure_ascii=False, indent=1)[:4000])
    check(r2.get("ok") and r2["result"]["compile"].get("num_errors") == 0, "2 포즈 LayerSetup 컴파일 0 에러")
    s2 = structure(0)
    layer2 = node_by_guid(s2, refs["layer"])
    pins = [p["name"] for p in layer2["pins"]]
    check("BlendPoses_1" in pins, f"BlendPoses_1 핀 생성: {pins}")
    ls2 = layer2["properties"].get("LayerSetup")
    check(isinstance(ls2, list) and len(ls2) == 2 and ls2[0] == LAYER_2[0] and ls2[1].get("BranchFilters") == [], f"LayerSetup 2 항목 조회 (둘째 필터 없음): {ls2}")
    rev2 = s2["revision"]

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== C. 거부 (preview) ===")
    cases = {
        "항목 수 불일치 (2 포즈에 1 항목)": ([{"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": LAYER_1}], "BAD_REQUEST"),
        "없는 본": ([{"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": "spine_99", "BlendDepth": 0}]}, {}]}], "BAD_REQUEST"),
        "없는 필드": ([{"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": [{"BranchFilters": [{"Bone": UPPER_BONE}]}, {}]}], "BAD_REQUEST"),
        "배열 아님": ([{"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": {"BranchFilters": []}}], "BAD_REQUEST"),
        "다른 노드 클래스": ([{"op": "set_property", "node": refs["base"], "property": "LayerSetup", "value": LAYER_1}], "PROPERTY_NOT_ALLOWED"),
        "잘못된 BlendMode": ([{"op": "set_property", "node": refs["layer"], "property": "BlendMode", "value": "NoSuchMode"}], "BAD_REQUEST"),
    }
    for name, (ops_bad, code) in cases.items():
        env = preview(ops_bad)
        errs = planned_errors(env)
        check(env.get("ok") and not env["result"]["valid"] and code in errs, f"거부: {name} → {errs}")
    check(structure(0)["revision"] == rev2, "거부 preview 들이 그래프를 바꾸지 않음")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== D. 롤백 ===")
    bad = apply([
        {"op": "set_property", "node": refs["layer"], "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": "spine_03", "BlendDepth": 1}]}, {"BranchFilters": [{"BoneName": "neck_01", "BlendDepth": 0}]}]},
        {"op": "set_property", "node": refs["layer"], "property": "bMeshSpaceRotationBlend", "value": True},
        # 기존 노드의 없는 핀은 사전 검증에서 걸려 apply 에 못 들어간다 — 같은 배치의 ref 노드라야 검증이 apply 로 미뤄진다 (phase4 F 와 같은 구성)
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "asset": idle},
        {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ])
    det = bad.get("error", {}).get("details", {})
    check(not bad.get("ok") and det.get("failed_index") == 3 and det.get("rollback_verified") is True, f"중간 실패(index 3) → rollback_verified ({det.get('rollback_verified')})")
    s4 = structure(0)
    check(s4["revision"] == rev2, "롤백 후 revision == 실패 전")
    check(node_by_guid(s4, refs["layer"])["properties"] == layer2["properties"], "LayerSetup · bMeshSpaceRotationBlend 원복")

    # -------------------------------------------------------------------------------------------------------------
    print("\n=== E. 저장 → 재조회 ===")
    final = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": True}, timeout=bridge.COMPILE_TIMEOUT), "compile+save")
    check(final.get("ok") and final.get("num_errors") == 0, f"최종 컴파일 0 에러 (warnings={final.get('num_warnings')})")
    s5 = structure(0)
    state = {"revision": s5["revision"], "nodes": sorted(n["node_guid"] for n in s5["nodes"]),
             "layer": node_by_guid(s5, refs["layer"])["properties"], "layer_guid": refs["layer"]}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE} (revision {s5['revision']})")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = structure(0)
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(sorted(n["node_guid"] for n in s["nodes"]) == saved["nodes"], "노드 Guid 집합 동일")
    check(node_by_guid(s, saved["layer_guid"])["properties"] == saved["layer"], "LayerSetup 디스크 왕복 동일")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {sorted(t['name'] for t in status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        main_sections()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
