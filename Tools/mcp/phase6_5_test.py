"""Phase 6-5 검증 자동화 — run_automation_tests · poll_automation_tests · AnimGraphMcp.Smoke.AnimBlueprint 스모크 테스트.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_5_test.py [--recheck]

새 Tool 2개는 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출로 검증한다. 에디터를 종료하지 않는다.
검사 항목:
  A. dry_run — "AnimGraphMcp.Smoke" 에 SmokeTestPaths 아래 AnimBP 마다 테스트 1개 (ABP_Hero_Base · 테스트 ABP 들 포함)
  B. 스모크 실행 — done=true(동기) · 운영 애셋 ABP_Hero_Base passed · 전부 passed(실패가 있으면 어떤 애셋·오류인지 출력)
     · 레이어 제공자 ABP_McpLayerProvider(루트 미연결)는 passed + 경고
  C. 프로젝트 테스트 — "AstralBreak." 전부 passed (18개) · duration 기록 · poll 로 같은 결과
  D. 거부 — filter 누락 · 모르는 job_id · 매칭 0 (NO_TESTS 진단, done)
  E. 스모크 음성 — 빈 상태를 가진 ABP 를 만들어(ABP_McpSmokeNeg) 스모크가 그 애셋만 failed 로 잡는지 → 삭제
  R. --recheck — 스모크 재실행 결과 동일(passed 수)
"""
from __future__ import annotations

import json
import sys
import time

from anim_graph_mcp import bridge

PROD = "/Game/Animation/Hero/ABP_Hero_Base"
NEG = "/Game/Animation/Test/ABP_McpSmokeNeg"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase6_5_state.json"
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


def run(filter_: str, **kw) -> dict:
    return bridge.call("run_automation_tests", {"filter": filter_, **kw}, timeout=bridge.COMPILE_TIMEOUT)


def wait_job(job: dict, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while not job.get("done") and time.time() < deadline:
        time.sleep(1.0)
        job = must(bridge.call("poll_automation_tests", {"job_id": job["job_id"]}), "poll")
    return job


def by_state(job: dict, state: str) -> list[str]:
    return [t["name"] for t in job["tests"] if t["state"] == state]


def main_sections() -> None:
    print("=== A. dry_run ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check({"run_automation_tests", "poll_automation_tests"} <= names, f"Tool 2개 등록 (총 {len(names)})")
    d = must(run("AnimGraphMcp.Smoke", dry_run=True), "dry_run")
    smoke_names = [t["name"] for t in d["tests"]]
    check(d.get("dry_run") and d["total"] >= 5 and any(n.endswith("ABP_Hero_Base") for n in smoke_names), f"스모크 테스트 {d['total']}개 (운영 애셋 포함): {[n.split('.')[-1] for n in smoke_names]}")

    print("\n=== B. 스모크 실행 ===")
    j = must(run("AnimGraphMcp.Smoke"), "smoke")
    j = wait_job(j)
    check(j["done"] and j["completed"] == j["total"] == d["total"], f"done · completed {j['completed']}/{j['total']}")
    failed = [t for t in j["tests"] if t["state"] != "passed"]
    for t in failed:
        print(f"   !! {t['name']} {t['state']}: {t['errors'][:3]}")
    check(j["ok"] and not failed, f"전부 passed ({j['passed']}) · elapsed {j['elapsed']:.2f}s")
    check(any(t["name"].endswith("ABP_Hero_Base") and t["state"] == "passed" for t in j["tests"]), "운영 애셋 ABP_Hero_Base passed")
    prov = [t for t in j["tests"] if t["name"].endswith("ABP_McpLayerProvider")]
    check(bool(prov) and prov[0]["state"] == "passed" and any("layer provider" in w for w in prov[0]["warnings"]), f"레이어 제공자(루트 미연결) → passed + 경고: {prov[0]['warnings'][:1] if prov else None}")
    smoke_passed = j["passed"]

    print("\n=== C. 프로젝트 테스트 ===")
    p = must(run("AstralBreak."), "project tests")
    p = wait_job(p)
    check(p["done"] and p["ok"] and p["total"] >= 18 and p["failed"] == 0, f"AstralBreak.* {p['passed']}/{p['total']} passed · elapsed {p['elapsed']:.2f}s")
    q = must(bridge.call("poll_automation_tests", {"job_id": p["job_id"]}), "poll same")
    check(q["job_id"] == p["job_id"] and q["passed"] == p["passed"] and q["done"], "poll 로 같은 결과")
    sub = must(run("AstralBreak.Targeting"), "subset")
    check(sub["done"] and 0 < sub["total"] < p["total"] and sub["failed"] == 0, f"부분 필터 AstralBreak.Targeting {sub['total']}개 passed")

    print("\n=== D. 거부 ===")
    r = bridge.call("run_automation_tests", {}); check(code(r) == "BAD_REQUEST", f"filter 누락 → BAD_REQUEST ({code(r)})")
    r = bridge.call("poll_automation_tests", {"job_id": "nope"}); check(code(r) == "BAD_REQUEST", f"모르는 job_id → BAD_REQUEST ({code(r)})")
    r = run("NoSuchTest.Zzz"); z = must(r, "no match")
    check(z["done"] and z["total"] == 0 and any(x.get("code") == "NO_TESTS" for x in r.get("diagnostics", [])), "매칭 0 → done · NO_TESTS 진단")

    print("\n=== E. 스모크 음성 ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": NEG, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create neg")
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": NEG, "depth": 0}), "structure")
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    must(bridge.call("apply_graph_operations", {"asset_path": NEG, "operations": [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-400, 0]},
        {"op": "add_state", "ref": "empty", "sm": {"ref": "sm"}, "name": "EmptyState"},
        {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "empty"}},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ], "save": True, "compile": True}, timeout=bridge.COMPILE_TIMEOUT), "neg graph")
    n = must(run("AnimGraphMcp.Smoke"), "smoke with neg")
    n = wait_job(n)
    neg_tests = [t for t in n["tests"] if t["name"].endswith("ABP_McpSmokeNeg")]
    check(len(neg_tests) == 1 and neg_tests[0]["state"] == "failed" and any("EmptyState" in e for e in neg_tests[0]["errors"]), f"빈 상태 ABP 만 failed: {neg_tests[0]['errors'][:2] if neg_tests else None}")
    check(n["failed"] == 1 and n["passed"] == smoke_passed, f"나머지는 passed ({n['passed']}) · failed 1")
    rd = must(bridge.call("delete_animation_blueprint", {"asset_path": NEG, "confirm": True}), "delete neg")
    check(rd.get("deleted"), "음성 애셋 삭제")
    m = wait_job(must(run("AnimGraphMcp.Smoke"), "smoke after delete"))
    check(m["ok"] and m["total"] == smoke_passed, f"삭제 뒤 스모크 전부 passed ({m['total']})")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"smoke_total": smoke_passed, "project_total": p["total"]}, f, indent=1)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    # 6-2 recheck 전에 돌면 ABP_McpDup 가 하나 더 잡힌다 → total 은 ≥ 로 본다
    j = wait_job(must(run("AnimGraphMcp.Smoke"), "smoke"))
    check(j["ok"] and j["total"] >= saved["smoke_total"], f"스모크 {j['passed']}/{j['total']} passed (이전 {saved['smoke_total']})")
    p = wait_job(must(run("AstralBreak."), "project"))
    check(p["ok"] and p["total"] == saved["project_total"], f"프로젝트 테스트 {p['passed']}/{p['total']} passed")


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
