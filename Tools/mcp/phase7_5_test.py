"""Phase 7-5 — PIE 런타임 검증 (run_anim_scenario · AnimGraphMcp.Runtime.AnimBlueprint).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_5_test.py [--recheck]

새 Tool run_anim_scenario 는 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출로 검증한다. 테스트가 PIE 를 열고 닫는다 —
바깥에서 PIE 를 켜 두면 안 된다(StartTestByName 이 거부). 에디터를 종료하지 않는다.
대상(생성·덮어쓰기): /Game/Animation/Test/ABP_McpRuntimeTest — 부모 UAnimInstance(네이티브 AnimInstance 가 변수를 매 프레임 덮어쓰지 않게),
BP 변수 Speed(float), 상태머신 Locomotion(Idle ⇄ Run, Speed > 150) → Slot UpperBody → Root. 몽타주는 7-3 의 AM_McpTest(슬롯 UpperBody, 같은 스켈레톤).
검사 항목:
  A. 준비 — Tool 등록 · dry_run "AnimGraphMcp.Runtime" 테스트 1개 · 시나리오 없이 직접 돌리면 passed+경고 · 테스트 ABP 생성·컴파일·저장
  B. 양성 — Speed 0 → Idle · Speed 300 → Run + 몽타주 → UpperBody 슬롯 활성(observed 로 관측값 확인) · 끝나면 PIE 닫힘
  C. 음성 — Speed 0 인데 Run 기대 → failed(오류에 두 상태 이름) · 몽타주 없이 슬롯 기대 → NO_MONTAGE 진단 + failed · PIE 닫힘
  D. 거부·타임아웃 — 없는 ABP · 인터페이스 · 없는 상태머신/상태/변수 · wait_frames 0 · 빈 슬롯 · 다른 스켈레톤 몽타주 · 본 이름이 호환되는
     다른 스켈레톤 메시는 통과(엔진 기준) · 잡 진행 중 재호출 · timeout 3초 → state timeout 뒤 러너가 PIE 를 닫음
  E. 운영 애셋 — ABP_Hero_Base 를 변수 없이 돌려 Locomotions 가 Idle 로 진입하는지 (읽기만, 변경 없음)
  R. --recheck — 에디터 재시작 뒤 B 의 두 시나리오 관측(상태·슬롯) 동일
"""
from __future__ import annotations

import json
import sys
import time

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpRuntimeTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
# 메시 호환은 USkeleton::IsCompatibleMesh(Skeleton.cpp:640-670, 본 이름·부모 사슬 비교) — 본 이름이 같은 메시는 통과한다.
# 몽타주 거부(IsCompatibleForEditor)는 본이 다른 UEFN 마네킹 스켈레톤의 몽타주로 본다 — 7-6 에서 히어로 애셋을 한 스켈레톤으로 통합해
# /Game/IdaFaber 쪽 몽타주가 더는 없으므로, UEFN 시퀀스로 테스트 몽타주를 만든다(A 절)
OTHER_MESH = "/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin"   # SK_UEFN_Mannequin 은 스켈레톤
OTHER_SEQ = "/Game/Characters/UEFN_Mannequin/Animations/Walk/M_Neutral_Walk_Loop_F"
OTHER_MONTAGE = "/Game/Animation/Test/AM_McpOtherSkel"
PARENT = "/Script/Engine.AnimInstance"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
RUN = "/Game/Animation/Hero/Vesper/Common/Locomotion/AS_Vesper_Jump_Start"
MONTAGE = "/Game/Animation/Test/AM_McpTest"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
ALI = "/Game/Animation/Test/ALI_McpTest"
STATE_FILE = "Tools/mcp/phase7_5_state.json"
FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:2000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:160]}")
    return env["result"]


def code(env: dict) -> str:
    return (env.get("error") or {}).get("code", "") if not env.get("ok") else "OK"


def reason(env: dict) -> str:
    return ((env.get("error") or {}).get("details") or {}).get("reason", "")


def diag_codes(env: dict) -> set[str]:
    return {d.get("code") for d in env.get("diagnostics", [])}


def call(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def status() -> dict:
    return must(bridge.call("get_editor_status"), "status")


def wait_job(job: dict, timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    while not job.get("done") and time.time() < deadline:
        time.sleep(1.0)
        job = must(bridge.call("poll_automation_tests", {"job_id": job["job_id"]}), "poll")
    return job


def pie_closed(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not status()["is_pie"]:
            return True
        time.sleep(0.5)
    return False


def scenario(what: str, **params) -> tuple[dict, dict, dict]:
    """run_anim_scenario → (봉투, 완료된 잡, 테스트 결과 1개)"""
    env = call("run_anim_scenario", **params)
    first = must(env, what)
    job = wait_job(first)
    test = job["tests"][0] if job["tests"] else {}
    obs = test.get("observed") or {}
    print(f"   {what}: {test.get('state')} · {job['elapsed']:.1f}s · observed={json.dumps(obs, ensure_ascii=False)[:300]}")
    for e in test.get("errors", [])[:3]:
        print(f"      err: {e[:200]}")
    return env, job, test


def shape(test: dict) -> dict:
    obs = test.get("observed") or {}
    return {"state": test.get("state"),
            "machines": {k: v.get("state") for k, v in (obs.get("state_machines") or {}).items()},
            "slots": obs.get("slots") or {},
            "montage_playing": obs.get("montage_playing")}


def build_test_abp() -> None:
    must(call("create_animation_blueprint", asset_path=ABP, skeleton=SKELETON, parent_class=PARENT, preview_mesh=MESH, overwrite=True), "create")
    must(call("add_blueprint_variable", asset_path=ABP, name="Speed", type="float", default="0.0"), "add Speed")
    s = must(call("get_anim_graph_structure", asset_path=ABP, depth=0), "structure")
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    gt = lambda lit: {"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": lit}}}
    le = lambda lit: {"compare": {"op": "<=", "left": {"var": "Speed"}, "right": {"literal": lit}}}
    ops = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-700, 0]},
        {"op": "rename_node", "ref": "sm", "name": "Locomotion"},
        # bAlwaysUpdateSourcePose: 몽타주가 슬롯을 가중치 1 로 덮으면 슬롯 노드가 Source(상태머신)를 갱신하지 않는다(AnimNode_Slot.cpp:67) —
        # 첫 실측에서 Speed 300 인데 Idle·elapsed 0 으로 남은 원인. 전신 슬롯 뒤의 상태머신을 몽타주 중에도 보려면 켜야 한다
        {"op": "add_node", "ref": "slot", "class": "AnimGraphNode_Slot", "pos": [-350, 0], "properties": {"SlotName": "UpperBody", "bAlwaysUpdateSourcePose": True}},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"ref": "slot", "pin": "Source"}},
        {"op": "connect", "from": {"ref": "slot", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
        {"op": "add_state", "ref": "idle", "sm": {"ref": "sm"}, "name": "Idle", "pos": [0, 0]},
        {"op": "add_state", "ref": "run", "sm": {"ref": "sm"}, "name": "Run", "pos": [500, 0]},
        {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}},
        {"op": "add_node", "ref": "idle_seq", "graph": {"ref": "idle"}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": IDLE, "properties": {"bLoopAnimation": True}},
        {"op": "connect", "from": {"ref": "idle_seq", "pin": "Pose"}, "to": {"result_of": {"ref": "idle"}, "pin": "Result"}},
        {"op": "add_node", "ref": "run_seq", "graph": {"ref": "run"}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": RUN, "properties": {"bLoopAnimation": True}},
        {"op": "connect", "from": {"ref": "run_seq", "pin": "Pose"}, "to": {"result_of": {"ref": "run"}, "pin": "Result"}},
        {"op": "add_transition", "ref": "t_idle_run", "from": {"ref": "idle"}, "to": {"ref": "run"}, "properties": {"CrossfadeDuration": 0.1}, "rule": gt(150.0)},
        {"op": "add_transition", "ref": "t_run_idle", "from": {"ref": "run"}, "to": {"ref": "idle"}, "properties": {"CrossfadeDuration": 0.1}, "rule": le(150.0)},
    ]
    r = must(call("apply_graph_operations", asset_path=ABP, operations=ops, compile=True, save=True), "build graph")
    check(r["compile"]["num_errors"] == 0 and r["saved"], f"테스트 ABP 구성 · 컴파일 0 에러 · 저장 (warnings={r['compile']['num_warnings']})")


def main_sections() -> None:
    print("=== A. 준비 ===")
    st = status()
    names = {t["name"] for t in st["tools"]}
    check("run_anim_scenario" in names, f"Tool run_anim_scenario 등록 (총 {len(names)})")
    check(not st["is_pie"], "시작 시 PIE 아님")
    d = must(call("run_automation_tests", filter="AnimGraphMcp.Runtime", dry_run=True), "dry_run")
    check(d["total"] == 1 and d["tests"][0]["name"] == "AnimGraphMcp.Runtime.AnimBlueprint", f"dry_run 에 런타임 테스트 1개: {[t['name'] for t in d['tests']]}")
    bare = wait_job(must(call("run_automation_tests", filter="AnimGraphMcp.Runtime"), "bare run"))
    bt = bare["tests"][0] if bare["tests"] else {}
    check(bare["ok"] and bt.get("state") == "passed" and any("No scenario" in w for w in bt.get("warnings", [])), "시나리오 없이 직접 돌리면 passed + 경고")
    build_test_abp()
    om = must(call("create_anim_montage", asset_path=OTHER_MONTAGE, animation=OTHER_SEQ, overwrite=True, save=True), "create other-skeleton montage")
    check("UEFN" in om["skeleton"], f"다른 스켈레톤 몽타주 생성 ({om['skeleton'].split('/')[-1]})")

    print("\n=== B. 양성 ===")
    env, j, t_idle = scenario("Speed 0 → Idle", asset_path=ABP, mesh=MESH, set_variables={"Speed": 0}, wait_frames=10,
                              expect={"state_machines": {"Locomotion": "Idle"}})
    first = env["result"]
    check(not first["done"] and first["total"] == 1 and first.get("running", "").endswith("ABP_McpRuntimeTest") and first["scenario"]["asset_path"].startswith(ABP), "첫 응답: done=false · running · scenario 정규화")
    check(j["done"] and j["ok"] and t_idle.get("state") == "passed", "Idle 시나리오 passed")
    obs = t_idle.get("observed") or {}
    check(obs.get("state_machines", {}).get("Locomotion", {}).get("state") == "Idle" and obs.get("frames_waited") == 10, f"observed: Locomotion=Idle · frames_waited=10")
    check(obs.get("variables_applied", {}).get("Speed") is not None, f"변수 적용 기록: {obs.get('variables_applied')}")
    check(pie_closed(), "시나리오 뒤 PIE 닫힘")

    env, j, t_run = scenario("Speed 300 + 몽타주 → Run · UpperBody", asset_path=ABP, mesh=MESH, set_variables={"Speed": 300}, montage=MONTAGE, wait_frames=10,
                             expect={"state_machines": {"Locomotion": "Run"}, "slots_active": ["UpperBody"]})
    check(j["ok"] and t_run.get("state") == "passed", "Run + 슬롯 시나리오 passed")
    obs = t_run.get("observed") or {}
    check(obs.get("state_machines", {}).get("Locomotion", {}).get("state") == "Run", "observed: Locomotion=Run")
    check(obs.get("slots", {}).get("UpperBody") is True and obs.get("montage_playing") is True and obs.get("montage_length", 0) > 0, f"observed: UpperBody 활성 · 몽타주 재생 중 (length {obs.get('montage_length')})")
    check(pie_closed(), "시나리오 뒤 PIE 닫힘")

    print("\n=== C. 음성 ===")
    env, j, t = scenario("Speed 0 인데 Run 기대", asset_path=ABP, mesh=MESH, set_variables={"Speed": 0}, wait_frames=10, expect={"state_machines": {"Locomotion": "Run"}})
    check(j["done"] and not j["ok"] and t.get("state") == "failed" and any("'Run'" in e and "'Idle'" in e for e in t.get("errors", [])), "상태 불일치 → failed (오류에 기대·실제 상태)")
    check((t.get("observed") or {}).get("state_machines", {}).get("Locomotion", {}).get("state") == "Idle", "실패해도 observed 는 남는다")
    env, j, t = scenario("몽타주 없이 슬롯 기대", asset_path=ABP, mesh=MESH, wait_frames=5, expect={"slots_active": ["UpperBody"]})
    check("NO_MONTAGE" in diag_codes(env), "NO_MONTAGE 진단")
    check(t.get("state") == "failed" and any("UpperBody" in e for e in t.get("errors", [])), "슬롯 비활성 → failed")
    check(pie_closed(), "음성 뒤 PIE 닫힘")

    print("\n=== D. 거부 · 타임아웃 ===")
    r = call("run_anim_scenario", asset_path="/Game/Animation/Test/ABP_NoSuch"); check(code(r) == "ASSET_NOT_FOUND", f"없는 ABP → {code(r)}")
    r = call("run_anim_scenario", asset_path=ALI); check(code(r) == "BAD_REQUEST" and reason(r) == "NOT_ANIM_BLUEPRINT", f"인터페이스 → {code(r)}/{reason(r)}")
    r = call("run_anim_scenario", asset_path=ABP, expect={"state_machines": {"Nope": "Idle"}}); check(reason(r) == "STATE_MACHINE_NOT_FOUND" and "Locomotion" in (r["error"]["details"].get("state_machines") or []), f"없는 상태머신 → {reason(r)}")
    r = call("run_anim_scenario", asset_path=ABP, expect={"state_machines": {"Locomotion": "Fly"}}); check(reason(r) == "STATE_NOT_FOUND" and set(r["error"]["details"].get("states") or []) == {"Idle", "Run"}, f"없는 상태 → {reason(r)} (states={r['error']['details'].get('states')})")
    r = call("run_anim_scenario", asset_path=ABP, set_variables={"Nope": 1}); check(reason(r) == "VARIABLE_NOT_FOUND" and "Speed" in (r["error"]["details"].get("variables") or []), f"없는 변수 → {reason(r)}")
    r = call("run_anim_scenario", asset_path=ABP, wait_frames=0); check(reason(r) == "BAD_WAIT_FRAMES", f"wait_frames 0 → {reason(r)}")
    r = call("run_anim_scenario", asset_path=ABP, expect={"slots_active": [""]}); check(reason(r) == "BAD_SLOT", f"빈 슬롯 이름 → {reason(r)}")
    r = call("run_anim_scenario", asset_path=ABP, montage=OTHER_MONTAGE); check(reason(r) == "SKELETON_MISMATCH" and ((r.get("error") or {}).get("details") or {}).get("field") == "montage", f"다른 스켈레톤 몽타주 → {code(r)}/{reason(r)}")
    check(not status()["is_pie"], "거부는 PIE 를 열지 않는다")
    # 메시 호환은 엔진이 인스턴스를 만드는 기준 그대로(USkeleton::IsCompatibleMesh(mesh, false) — 본 이름 집합, SkeletalMeshComponent.cpp:883):
    # 본 이름이 같은 UEFN 마네킹도 통과해 인스턴스가 생긴다(실측 — 처음엔 거부를 기대했음). 본 이름이 다른 메시는 프로젝트에 없어 SKELETON_MISMATCH(mesh) 는 미검증
    _, oj, ot = scenario("UEFN 마네킹 메시(본 이름 호환)", asset_path=ABP, mesh=OTHER_MESH, set_variables={"Speed": 0}, wait_frames=5, expect={"state_machines": {"Locomotion": "Idle"}})
    check(oj["ok"] and (ot.get("observed") or {}).get("anim_instance_class", "").endswith("ABP_McpRuntimeTest_C"), "본 이름이 호환되는 다른 스켈레톤 메시 → 인스턴스 생성·Idle (엔진 IsCompatibleMesh 기준)")
    check(pie_closed(), "PIE 닫힘")

    long_ = must(call("run_anim_scenario", asset_path=ABP, mesh=MESH, wait_frames=300, timeout=120), "long scenario")
    r = call("run_automation_tests", filter="AstralBreak.Targeting"); check(code(r) == "BAD_REQUEST" and "running" in r["error"]["message"], f"잡 진행 중 run_automation_tests → {code(r)}")
    r = call("run_anim_scenario", asset_path=ABP, mesh=MESH); check(code(r) == "BAD_REQUEST", f"잡 진행 중 run_anim_scenario → {code(r)}/{reason(r)}")
    lj = wait_job(long_)
    check(lj["ok"] and (lj["tests"][0].get("observed") or {}).get("frames_waited") == 300, f"긴 시나리오 완료 (frames_waited {(lj['tests'][0].get('observed') or {}).get('frames_waited')} · {lj['elapsed']:.1f}s)")
    check(pie_closed(), "PIE 닫힘")

    tj = wait_job(must(call("run_anim_scenario", asset_path=ABP, mesh=MESH, wait_frames=100000, timeout=3), "timeout scenario"), timeout=60)
    tt = tj["tests"][0] if tj["tests"] else {}
    check(tj["done"] and tt.get("state") == "timeout" and not tj["ok"], f"timeout 3초 → state {tt.get('state')} ({tj['elapsed']:.1f}s)")
    check(pie_closed(), "타임아웃 뒤 러너가 PIE 를 닫음")
    after = wait_job(must(call("run_anim_scenario", asset_path=ABP, mesh=MESH, set_variables={"Speed": 0}, wait_frames=5, expect={"state_machines": {"Locomotion": "Idle"}}), "after timeout"))
    check(after["ok"], "타임아웃 뒤 다음 시나리오 정상")

    print("\n=== E. 운영 애셋 (읽기만) ===")
    env, j, tp = scenario("ABP_Hero_Base 변수 없이 → Locomotions Idle", asset_path=PROD, mesh=MESH, wait_frames=10, expect={"state_machines": {"Locomotions": "Idle"}})
    check(j["ok"] and tp.get("state") == "passed", "운영 ABP 가 PIE 에서 Idle 로 진입")
    machines = (tp.get("observed") or {}).get("state_machines") or {}
    check("Locomotions" in machines and all(m.get("state") for m in machines.values()), f"운영 상태머신 {len(machines)}개 모두 상태 보고: { {k: v.get('state') for k, v in machines.items()} }")
    check(pie_closed(), "PIE 닫힘")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"idle": shape(t_idle), "run": shape(t_run), "prod": shape(tp)}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재실행 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    check(not status()["is_pie"], "시작 시 PIE 아님")
    _, _, t = scenario("Idle", asset_path=ABP, mesh=MESH, set_variables={"Speed": 0}, wait_frames=10, expect={"state_machines": {"Locomotion": "Idle"}})
    check(shape(t) == saved["idle"], f"Idle 시나리오 관측 동일: {shape(t)}")
    _, _, t = scenario("Run", asset_path=ABP, mesh=MESH, set_variables={"Speed": 300}, montage=MONTAGE, wait_frames=10,
                       expect={"state_machines": {"Locomotion": "Run"}, "slots_active": ["UpperBody"]})
    check(shape(t) == saved["run"], f"Run 시나리오 관측 동일: {shape(t)}")
    _, _, t = scenario("Prod", asset_path=PROD, mesh=MESH, wait_frames=10, expect={"state_machines": {"Locomotions": "Idle"}})
    check(shape(t) == saved["prod"], "운영 ABP 관측 동일")
    check(pie_closed(), "PIE 닫힘")


def main() -> int:
    st = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(st['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        main_sections()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
