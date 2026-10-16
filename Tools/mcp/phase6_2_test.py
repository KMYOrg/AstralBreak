"""Phase 6-2 애셋 수명 — duplicate_animation_blueprint · delete_animation_blueprint · quit_editor · 보호 목록.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_2_test.py [--recheck] [--no-quit]

새 Tool 3개는 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출(bridge)로 검증한다.
대상: /Game/Animation/Test/ABP_McpTest (phase6_1 이 만든 저장본, 읽기만) → 복제본 ABP_McpDup · 자식 ABP_McpChild (생성·삭제).
운영 애셋 ABP_Hero_Base 는 읽기만 — 보호 목록이 거부하는지 확인하고 revision 이 그대로인지 본다.
검사 항목:
  A. 상태 — Tool 12개 · process_id · protection(ini) · dirty_package_count
  B. 복제 — 노드 Guid 보존(기본) → revision·Guid 집합이 원본과 같다 · 보존 안 함 → Guid 다름 · 거부 4종(ASSET_EXISTS · 자기 자신 · 없는 원본 · 보호 덮어쓰기)
  C. 복제본 편집·컴파일·저장 — 원본 revision 불변 · create overwrite 도 보호 거부
  D. 삭제 — confirm 없음 · 보호 · AnimBP 아님 · 없는 애셋 · 참조 중(자식 ABP) force 없이 거부 → force 삭제 · 자식 삭제
  E. quit — 더티 패키지가 있으면 DIRTY_PACKAGES 거부(에디터 유지) → save_dirty 로 저장 후 종료 → 프로세스 소멸 대기 (--no-quit 으로 생략)
  R. --recheck (재시작 뒤) — ABP_McpDup revision·Guid 집합 · ABP_McpTest/ABP_Hero_Base revision 불변 · 정리 삭제 · quit(더티 없음)
"""
from __future__ import annotations

import json
import os
import sys
import time

from anim_graph_mcp import bridge
from wait_for_exit import wait_for_exit

SRC = "/Game/Animation/Test/ABP_McpTest"
DUP = "/Game/Animation/Test/ABP_McpDup"
CHILD = "/Game/Animation/Test/ABP_McpChild"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
NOT_ABP = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
DEMO_ABP = "/Game/Assets/IdaFaber/Blueprints/ABP_UE5_Demo_F"   # ProtectedPaths=/Game/Assets/ 아래의 기존 ABP (읽기만)
STATE_FILE = "Tools/mcp/phase6_2_state.json"
NEW_TOOLS = {"duplicate_animation_blueprint", "delete_animation_blueprint", "quit_editor"}
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


def code(env: dict) -> str:
    return env.get("error", {}).get("code", "") if not env.get("ok") else "OK"


def info(path: str) -> dict:
    return must(bridge.call("get_anim_blueprint_info", {"asset_path": path}, timeout=bridge.COMPILE_TIMEOUT), f"info {path}")


def guids(path: str) -> list[str]:
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": path, "depth": -1}, timeout=bridge.COMPILE_TIMEOUT), f"structure {path}")
    return sorted(n["node_guid"] for n in s["nodes"])


def shape(path: str) -> dict:
    """revision 을 뺀 구조 비교용 — 그래프 Guid · 노드 Guid · 연결 · 상태머신 뷰.
    revision 자체는 복제본과 원본이 다르다: 노드 프로퍼티의 오브젝트 참조(예: StateMachine 의 EditorStateMachineGraph)가
    애셋 경로를 포함해 ExportText 되므로 패키지 이름이 해시에 들어간다."""
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": path, "depth": -1}, timeout=bridge.COMPILE_TIMEOUT), f"structure {path}")
    return {
        "graphs": sorted((g["graph_guid"], g["name"], g["class"]) for g in s["graphs"]),
        "nodes": sorted((n["node_guid"], n["class"], n["graph_guid"]) for n in s["nodes"]),
        "connections": sorted((c["from"]["node"], c["from"]["pin"], c["to"]["node"], c["to"]["pin"]) for c in s["connections"]),
        "sm": [(sm["name"], sorted(st["name"] for st in sm["states"]), len(sm["transitions"])) for sm in s["state_machines"]],
    }


def exists(path: str) -> bool:
    return bridge.call("get_anim_blueprint_info", {"asset_path": path}).get("ok", False)


def delete(path: str, **kw) -> dict:
    return bridge.call("delete_animation_blueprint", {"asset_path": path, **kw})


def cleanup() -> None:
    for p in (CHILD, DUP):
        if exists(p):
            r = delete(p, confirm=True, force=True)
            print(f"   cleanup {p}: {code(r)}")


def main_sections(do_quit: bool) -> None:
    print("=== A. 상태 ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check(NEW_TOOLS <= names, f"새 Tool 3개 등록 (총 {len(names)})")
    check(int(st.get("process_id", 0)) > 0, f"process_id {st.get('process_id')}")
    prot = st.get("protection", {})
    check(PROD in prot.get("assets", []), f"protection.assets 에 운영 애셋: {prot.get('assets')}")
    check(any(p.startswith("/Game/Assets/") for p in prot.get("paths", [])), f"protection.paths: {prot.get('paths')}")
    check("dirty_package_count" in st, f"dirty_package_count {st.get('dirty_package_count')}")
    cleanup()

    prod_rev0 = info(PROD)["revision"]
    src_info = info(SRC)
    src_rev0 = src_info["revision"]
    src_guids = guids(SRC)
    src_shape = shape(SRC)
    print(f"   source {SRC} revision {src_rev0} nodes {len(src_guids)} · prod revision {prod_rev0}")

    print("\n=== B. 복제 ===")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DUP}, timeout=bridge.COMPILE_TIMEOUT)
    d = must(r, "duplicate")
    check(d.get("duplicated") and d.get("node_guids_preserved") is True and d.get("saved") is False, "duplicated · guids preserved · unsaved")
    check(d.get("source_revision") == src_rev0, "source_revision == 원본 revision")
    check(d.get("target_skeleton") == src_info.get("target_skeleton") and d.get("parent_class") == src_info.get("parent_class"), "스켈레톤·부모 클래스 동일")
    dup_guids = guids(DUP)
    check(dup_guids == src_guids, f"노드 Guid 집합 동일 ({len(dup_guids)})")
    check(shape(DUP) == src_shape, "그래프 Guid · 노드 · 연결 · 상태머신 뷰 동일 (revision 은 패키지 이름이 섞여 다름)")
    check(d["revision"] != src_rev0, f"revision 은 원본과 다름 — 오브젝트 참조 프로퍼티에 애셋 경로 포함 ({d['revision'][:16]}…)")
    check(info(SRC)["revision"] == src_rev0, "원본 revision 불변")

    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DUP})
    check(code(r) == "ASSET_EXISTS", f"overwrite 없이 재복제 → ASSET_EXISTS ({code(r)})")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": SRC, "overwrite": True})
    check(code(r) == "BAD_REQUEST", f"자기 자신으로 복제 → BAD_REQUEST ({code(r)})")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": "/Game/Animation/Test/ABP_Nope", "dest_path": DUP})
    check(code(r) == "ASSET_NOT_FOUND", f"없는 원본 → ASSET_NOT_FOUND ({code(r)})")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": PROD, "overwrite": True})
    check(code(r) == "ASSET_PROTECTED", f"운영 애셋 덮어쓰기 → ASSET_PROTECTED ({code(r)}: {r.get('error', {}).get('message')})")
    check(info(PROD)["revision"] == prod_rev0, "운영 애셋 revision 불변")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DEMO_ABP, "overwrite": True})
    check(code(r) == "ASSET_PROTECTED" and "ProtectedPaths" in r.get("error", {}).get("details", {}).get("rule", ""), f"보호 경로(ProtectedPaths) 애셋 덮어쓰기 → ASSET_PROTECTED ({code(r)})")

    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DUP, "overwrite": True, "preserve_node_guids": False}, timeout=bridge.COMPILE_TIMEOUT)
    d2 = must(r, "duplicate overwrite no-preserve")
    check(any(x.get("code") == "ASSET_REPLACED" for x in r.get("diagnostics", [])), "overwrite → ASSET_REPLACED 진단")
    g2 = guids(DUP)
    check(len(g2) == len(src_guids) and g2 != src_guids, f"Guid 재생성: 수 {len(g2)} 같고 집합 다름")
    check(d2["revision"] != d["revision"], "revision 이 Guid 보존 복제본과도 다름 (노드 Guid 포함 해시)")

    print("\n=== C. 복제본 편집·저장 ===")
    r = bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DUP, "overwrite": True, "save": True}, timeout=bridge.COMPILE_TIMEOUT)
    d3 = must(r, "duplicate overwrite save")
    check(d3.get("saved") is True and shape(DUP) == src_shape, "저장 복제(Guid 보존) 구조 == 원본 · saved")
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": DUP, "depth": 0}), "dup root")
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    ap = bridge.call("apply_graph_operations", {"asset_path": DUP, "expected_revision": d3["revision"], "compile": True, "operations": [
        {"op": "add_node", "ref": "x", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 400], "asset": NOT_ABP},
    ]}, timeout=bridge.COMPILE_TIMEOUT)
    a = must(ap, "edit dup")
    check(a["compile"].get("num_errors") == 0 and a["revision_after"] != d3["revision"], "복제본 편집 → 컴파일 0 에러 · revision 변경")
    check(info(SRC)["revision"] == src_rev0, "원본 revision 불변 (복제본 편집 뒤)")
    sv = must(bridge.call("save_animation_blueprint", {"asset_path": DUP}), "save dup")
    dup_rev_saved = sv["revision"]
    dup_guids_saved = guids(DUP)
    r = bridge.call("create_animation_blueprint", {"asset_path": PROD, "skeleton": SKELETON, "overwrite": True})
    check(code(r) == "ASSET_PROTECTED", f"create overwrite 운영 애셋 → ASSET_PROTECTED ({code(r)})")
    check(info(PROD)["revision"] == prod_rev0, "운영 애셋 revision 불변 (create overwrite 뒤)")

    print("\n=== D. 삭제 ===")
    r = delete(DUP)
    check(code(r) == "BAD_REQUEST", f"confirm 없음 → BAD_REQUEST ({code(r)})")
    r = delete(PROD, confirm=True, force=True)
    check(code(r) == "ASSET_PROTECTED", f"운영 애셋 → ASSET_PROTECTED ({code(r)})")
    r = delete(DEMO_ABP, confirm=True, force=True)
    check(code(r) == "ASSET_PROTECTED" and exists(DEMO_ABP), f"보호 경로 애셋 → ASSET_PROTECTED · 그대로 존재 ({code(r)})")
    r = delete(NOT_ABP, confirm=True, force=True)
    check(code(r) == "BAD_REQUEST", f"AnimBP 아님 → BAD_REQUEST ({code(r)})")
    r = delete("/Game/Animation/Test/ABP_Nope", confirm=True)
    check(code(r) == "ASSET_NOT_FOUND", f"없는 애셋 → ASSET_NOT_FOUND ({code(r)})")

    # 참조자: 복제본의 생성 클래스를 부모로 하는 자식 ABP (저장해야 레지스트리 의존성에 잡힌다)
    ch = must(bridge.call("create_animation_blueprint", {"asset_path": CHILD, "skeleton": SKELETON, "parent_class": f"{DUP}.ABP_McpDup_C", "overwrite": True}), "create child")
    # 자식 ABP 는 루트 AnimGraph 를 갖지 않는다(부모 그래프 상속) — info 의 NO_ANIM_GRAPH 진단은 정상
    check(ch.get("parent_anim_blueprint") in (DUP, f"{DUP}.ABP_McpDup") or (ch.get("parent_class") or "").startswith(DUP), f"자식 ABP 부모 = 복제본 ({ch.get('parent_class')} / {ch.get('parent_anim_blueprint')})")
    must(bridge.call("save_animation_blueprint", {"asset_path": CHILD}), "save child")
    r = delete(DUP, confirm=True)
    refs = r.get("error", {}).get("details", {}).get("referencers", [])
    check(code(r) == "ASSET_REFERENCED" and CHILD in refs, f"참조 중 force 없이 → ASSET_REFERENCED {refs}")
    check(exists(DUP), "거부 뒤 복제본 그대로 존재")
    r = delete(DUP, confirm=True, force=True)
    dd = must(r, "force delete")
    check(dd.get("deleted") and dd.get("forced") and CHILD in dd.get("referencers", []), "force 삭제 → deleted · referencers 보고")
    check(any(x.get("code") == "REFERENCES_BROKEN" for x in r.get("diagnostics", [])), "REFERENCES_BROKEN 진단")
    check(not exists(DUP), "복제본 사라짐 (ASSET_NOT_FOUND)")
    r = delete(CHILD, confirm=True)
    check(r.get("ok") and r["result"].get("referencers") == [], f"자식 삭제 (참조자 없음) ({code(r)})")
    check(not exists(CHILD), "자식 사라짐")
    check(os.path.exists("Content/Animation/Test/ABP_McpTest.uasset") and not os.path.exists("Content/Animation/Test/ABP_McpDup.uasset") and not os.path.exists("Content/Animation/Test/ABP_McpChild.uasset"), "디스크: 원본 있음 · 복제본/자식 파일 없음")

    # recheck 재료 — 복제본을 다시 만들어 저장 (재시작 뒤 Guid·revision 비교)
    d4 = must(bridge.call("duplicate_animation_blueprint", {"source_path": SRC, "dest_path": DUP, "overwrite": True, "save": True}, timeout=bridge.COMPILE_TIMEOUT), "duplicate for recheck")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"dup_revision": d4["revision"], "dup_nodes": guids(DUP), "src_revision": src_rev0, "prod_revision": prod_rev0}, f, indent=1)
    print(f"saved → {STATE_FILE} (dup revision {d4['revision']})")

    print("\n=== E. quit ===")
    # 더티 만들기 — 저장 안 한 편집
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": DUP, "depth": 0}), "dup root 2")
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    must(bridge.call("apply_graph_operations", {"asset_path": DUP, "operations": [
        {"op": "add_node", "ref": "y", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 600], "asset": NOT_ABP},
    ]}, timeout=bridge.COMPILE_TIMEOUT), "dirty edit")
    st2 = must(bridge.call("get_editor_status"), "status 2")
    check(int(st2.get("dirty_package_count", 0)) >= 1, f"dirty_package_count ≥ 1 ({st2.get('dirty_package_count')})")
    r = bridge.call("quit_editor", {}, timeout=bridge.COMPILE_TIMEOUT)
    dirty = [p["package"] for p in r.get("error", {}).get("details", {}).get("dirty_packages", [])]
    check(code(r) == "DIRTY_PACKAGES" and DUP in dirty, f"더티 상태 quit → DIRTY_PACKAGES {dirty}")
    time.sleep(2)
    check(bridge.call("get_editor_status").get("ok"), "거부 뒤 에디터 계속 동작")
    if not do_quit:
        print("   --no-quit: 종료 생략 (더티 복제본은 저장하지 않음)")
        return
    r = bridge.call("quit_editor", {"save_dirty": True}, timeout=bridge.COMPILE_TIMEOUT)
    q = must(r, "quit save_dirty")
    check(q.get("quit_requested") and DUP in q.get("saved_packages", []) and q.get("discarded_packages") == [], f"save_dirty quit → saved {q.get('saved_packages')}")
    # 저장된 복제본의 최종 상태를 recheck 재료로 갱신 (편집 y 포함) — 에디터가 아직 응답하면 읽는다
    pid = int(q.get("process_id") or 0)
    with open(STATE_FILE, encoding="utf-8") as f:
        saved_state = json.load(f)
    saved_state["dup_dirty_edit_saved"] = True
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(saved_state, f, indent=1)
    check(wait_for_exit(pid, timeout=180.0, interval=5.0), f"프로세스 {pid} 소멸")
    check(os.path.exists("Content/Animation/Test/ABP_McpDup.uasset"), "디스크: 저장된 복제본 파일 존재")


def recheck(do_quit: bool) -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    d = info(DUP)
    if saved.get("dup_dirty_edit_saved"):
        # quit(save_dirty) 가 편집 y 를 저장했으므로 revision 은 D 절 저장본과 다르고 노드는 1개 많다
        check(d["revision"] != saved["dup_revision"] and len(guids(DUP)) == len(saved["dup_nodes"]) + 1, "save_dirty 로 저장된 편집이 디스크에 남음 (노드 +1)")
    else:
        check(d["revision"] == saved["dup_revision"] and guids(DUP) == saved["dup_nodes"], "복제본 revision·Guid 집합 동일")
    check(info(SRC)["revision"] == saved["src_revision"], "원본 revision 동일")
    check(info(PROD)["revision"] == saved["prod_revision"], "운영 애셋 revision 동일")
    r = delete(DUP, confirm=True)
    check(r.get("ok"), f"정리: 복제본 삭제 ({code(r)})")
    check(not os.path.exists("Content/Animation/Test/ABP_McpDup.uasset"), "디스크: 복제본 파일 없음")
    if do_quit:
        r = bridge.call("quit_editor", {}, timeout=bridge.COMPILE_TIMEOUT)
        q = must(r, "quit clean")
        check(q.get("quit_requested") and q.get("saved_packages") == [] and q.get("discarded_packages") == [], "더티 없는 quit")
        check(wait_for_exit(int(q.get("process_id") or 0), timeout=180.0, interval=5.0), "프로세스 소멸")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(status['tools'])}")
    do_quit = "--no-quit" not in sys.argv
    if "--recheck" in sys.argv:
        recheck(do_quit)
    else:
        main_sections(do_quit)
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
