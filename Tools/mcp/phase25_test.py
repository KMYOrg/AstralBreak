"""Phase 2.5 최소 수직 통합 — 생성 → SequencePlayer → Root 연결 → 컴파일 → 저장 → 재조회.

    MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase25_test.py

운영 애셋은 건드리지 않는다. 대상은 /Game/Animation/Test/ABP_McpTest (덮어쓰기).
검사: preview valid · apply ok · 연결 1개 · 컴파일 0 에러 · 저장 · 재조회 revision 동일 · 실패 배치의 롤백 검증.
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    tools = sorted(t["name"] for t in status["tools"])
    print(f"tools: {tools}")

    # 1. 스켈레톤에 맞는 시퀀스 하나 고르기
    assets = must(bridge.call("list_animation_assets", {"skeleton": SKELETON, "class": "AnimSequence", "limit": 20}), "list assets")
    print(f"sequences for skeleton: {assets['total']} (showing {assets['returned']})")
    if assets["total"] == 0:
        print("[FAIL] no AnimSequence for the skeleton")
        return 1
    preferred = [a for a in assets["assets"] if "Idle" in a["name"]]
    sequence = (preferred or assets["assets"])[0]["asset_path"]
    print(f"using sequence: {sequence}")

    # 2. 테스트 AnimBP 생성 (덮어쓰기)
    info = must(bridge.call("create_animation_blueprint", {
        "asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    root_graph = info["anim_graph_guid"]
    print(f"created {info['asset_path']} anim_graph={root_graph} revision={info['revision']}")

    # 3. 루트 그래프 조회 → Output Pose(Root) 노드 guid
    structure = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "structure")
    roots = [n for n in structure["nodes"] if n["class"] == "AnimGraphNode_Root"]
    if len(roots) != 1:
        print(f"[FAIL] expected 1 root node, got {len(roots)}")
        return 1
    root = roots[0]
    print(f"root node {root['node_guid']} pins {[p['name'] for p in root['pins']]}")

    ops = [
        {"op": "add_node", "ref": "idle", "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": sequence},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]

    # 4. preview → 유효해야 함, 그래프 불변
    preview = must(bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops}), "preview")
    print(f"preview valid={preview['valid']} create={preview['would_create']} connect={preview['would_connect']}")
    if not preview["valid"] or preview["revision"] != structure["revision"]:
        print("[FAIL] preview invalid or preview changed the graph")
        return 1

    # 5. apply (+컴파일 +저장)
    applied = must(bridge.call("apply_graph_operations", {
        "asset_path": ABP, "operations": ops, "expected_revision": structure["revision"], "compile": True, "save": True},
        timeout=bridge.COMPILE_TIMEOUT), "apply")
    comp = applied["compile"]
    print(f"applied={applied['applied']} refs={applied['refs']} compile ok={comp.get('ok')} "
          f"errors={comp.get('num_errors')} warnings={comp.get('num_warnings')} saved={applied['saved']}")
    for m in comp.get("messages", []):
        print(f"   compile[{m['level']}] {m['text']}")
    if not comp.get("ok") or not applied["saved"]:
        print("[FAIL] compile or save failed")
        return 1

    # 6. 재조회 — 연결 1개, revision 일치
    after = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "re-inspect")
    conns = after["connections"]
    print(f"after: nodes={len(after['nodes'])} connections={conns}")
    ok = (len(conns) == 1 and conns[0]["to"]["node"] == root["node_guid"] and conns[0]["to"]["pin"] == "Result"
          and conns[0]["from"]["node"] == applied["refs"]["idle"] and after["revision"] == applied["revision_after"])
    if not ok:
        print("[FAIL] re-inspection does not match applied result")
        return 1

    # 7. 실패 배치 → 롤백 검증 (존재하지 않는 핀으로 연결)
    bad = bridge.call("apply_graph_operations", {"asset_path": ABP, "operations": [
        {"op": "add_node", "ref": "x", "class": "AnimGraphNode_SequencePlayer", "asset": sequence},
        {"op": "connect", "from": {"ref": "x", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "NoSuchPin"}},
    ]})
    print(f"bad batch ok={bad.get('ok')} code={bad.get('error', {}).get('code')} "
          f"details={ {k: v for k, v in bad.get('error', {}).get('details', {}).items() if k in ('failed_index', 'rolled_back', 'rollback_verified')} }")
    details = bad.get("error", {}).get("details", {})
    if bad.get("ok") or not details.get("rollback_verified"):
        print("[FAIL] failed batch was not rolled back (or rollback unverified)")
        return 1
    after2 = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "re-inspect after rollback")
    if after2["revision"] != after["revision"]:
        print("[FAIL] revision changed after rolled-back batch")
        return 1

    # 8. 중복 ref 등 검증 오류는 아무것도 바꾸지 않아야 함
    dup = bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": [
        {"op": "add_node", "ref": "a", "class": "AnimGraphNode_SequencePlayer"},
        {"op": "add_node", "ref": "a", "class": "AnimGraphNode_SequencePlayer"},
    ]})
    print(f"duplicate ref preview valid={dup.get('result', {}).get('valid')}")
    if dup.get("result", {}).get("valid"):
        print("[FAIL] duplicate ref accepted")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
