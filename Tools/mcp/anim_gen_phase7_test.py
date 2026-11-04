"""AI 애니 생성 Phase 7 — AnimBP 연결 · 승격 에디터 통합 테스트 (Docs/AIAnimation/DevelopmentGuide.md §14 Phase 7 · §15 F).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase7_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인)를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는 Saved/AnimGen/TestRuns/P7Run<시각>/ 에 격리한다.
출력은 /Game/Animation/Test/AIAnimation/P7Run<시각>/, 승격 실제 이동은 /Game/Animation/Hero/Vesper/_P7PromoteTest/P7Run<시각>/ 에만(사용자 승인).
운영 AnimBP(ABP_Hero_Combat · ABP_HeroLayers_Rifle · ABP_Hero_Base · ALI_HeroCombat)와 스켈레톤에는 쓰지 않는다 — 읽기 · 미리보기만.
섹션:
  hashes        — (맨 앞) 운영 AnimBP 4개 · 스켈레톤 · 런타임 테스트 ABP · 소스 시퀀스 .uasset SHA-256 · 운영 revision · Content/ git 상태 · 미저장 수
  plan          — 애셋만 요청 = anim_bp 단계 없음 · 운영 revision 불변 / 연결 요청 = anim_bp_test · anim_bp_prepare · revision 고정 / 차단 사유
                  (SLOT_NOT_IN_SKELETON · SKELETON_MISMATCH · PREVIEW_INVALID)
  chain_bs      — 연속(예시 B · 전이): Vesper 걷기 direct_key 리타임 → BS1D(생성물 300 + 기존 Idle 0) → ABP_McpRuntimeTest 복제본 Run 상태 플레이어를
                  BlendSpacePlayer($blendspace, X ← Speed)로 → 컴파일 0 · 스모크 · 시나리오 Speed 300 → Run (+ 복제본에 Speed 0 → Idle)
  chain_montage — 연속(예시 C): AS_Vesper_Rifle_Recoil concat ×3 → additive(LocalSpaceBase) · UpperBody 루프 몽타주 → ABP_Hero_Combat 복제본
                  slots_active[UpperBody] + 운영 미리보기 valid · revision · 적용 페이로드
  independent   — 독립: KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash 재사용 → DefaultSlot 몽타주 → ABP_Hero_Combat 복제본 slots_active[DefaultSlot]
                  (원본 Kimodo 애셋 무변경 · 새 시퀀스 없음)
  guard         — generation_guard 켬 = 허용 목록 밖 · 덮어쓰기 거부(운영 ABP 포함), 꺼짐 = 기존 동작 + Automation AnimGraphMcp.Generation
  apply_mech    — 복제본에 낡은 expected_revision → REVISION_MISMATCH 무변경, 맞는 revision → 적용(운영 적용과 같은 메커니즘)
  promote       — dry_run 거부 사유 → 실제 이동(BS → 샘플 시퀀스(후보 밖 참조자 거부 → allow_referencers) → 몽타주 + 시퀀스 한 배치):
                  옛 경로 애셋 · 리디렉터 0 · 옛 파일 없음 · 내용 해시 같음 · 참조자(복제본 ABP · BS · 몽타주)가 새 경로
  dirty         — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 실행 폴더 + 승격 테스트 폴더뿐
요약은 Tools/mcp/anim_gen_phase7_state.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

from anim_graph_mcp import bridge

STAMP = time.strftime("%m%d_%H%M%S")
ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P7Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P7Run{STAMP}"
PROMO = f"/Game/Animation/Hero/Vesper/_P7PromoteTest/P7Run{STAMP}"
COMBAT = "/Game/Animation/Hero/ABP_Hero_Combat"
LAYERS = "/Game/Animation/Hero/ABP_HeroLayers_Rifle"
BASE = "/Game/Animation/Hero/ABP_Hero_Base"
ALI = "/Game/Animation/Hero/ALI_HeroCombat"
RUNTIME = "/Game/Animation/Test/ABP_McpRuntimeTest"
WALK = "/Game/Animation/Hero/Vesper/Common/Locomotion/AS_Vesper_Neutral_Walk_Loop_F"
IDLE = "/Game/Animation/Hero/Vesper/Rifle/Locomotion/AS_Vesper_Rifle_Idle"
RECOIL = "/Game/Animation/Hero/Vesper/Rifle/Actions/AS_Vesper_Rifle_Recoil"
KIMODO = "/Game/Animation/Test/AIAnimation/KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash"
HASHED = [COMBAT, LAYERS, BASE, ALI, VESPER, RUNTIME, WALK, IDLE, RECOIL, KIMODO]
FAILS: list[str] = []
STATE: dict = {"run": RUN, "promote_folder": PROMO, "state_dir": STATE_DIR.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        FAILS.append(what)
        raise SystemExit(finish())
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def code_of(env: dict) -> tuple[str | None, str | None]:
    err = env.get("error") or {}
    return err.get("code"), (err.get("details") or {}).get("reason")


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def uasset(path: str) -> pathlib.Path:
    return ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")


def sha256(path: str) -> str:
    return hashlib.sha256(uasset(path).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def revision(abp: str) -> str:
    return must(editor("get_anim_blueprint_info", asset_path=abp), f"info {abp}")["revision"]


def wait_job(job: dict, limit: float = 600.0) -> tuple[dict, float]:
    t0 = time.time()
    last = None
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(2.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
        note = (job.get("stage"), job["status"])
        if note != last:
            print(f"   {round(time.time() - t0)}s · stage {job.get('stage')} · {job['status']}")
            last = note
    return job, round(time.time() - t0, 2)


def run_plan(request: dict, what: str, save: bool = True) -> tuple[dict, dict, float]:
    plan = must(SERVICE.plan_motion_generation(request=request), f"plan {what}")
    if not check(plan["executable"], f"{what}: plan executable"):
        print(json.dumps(plan["excluded"], ensure_ascii=False)[:2000])
        raise SystemExit(finish())
    t0 = time.time()
    env = SERVICE.generate_motion(plan_id=plan["plan_id"], save=save)
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    job, _ = wait_job(job)
    seconds = round(time.time() - t0, 2)
    if not check(job["status"] == "SUCCEEDED", f"{what}: job SUCCEEDED ({seconds}s)"):
        print(json.dumps(job.get("error"), ensure_ascii=False)[:3000])
        raise SystemExit(finish())
    return plan, job, seconds


def scenario(asset: str, **params) -> dict:
    env = editor("run_anim_scenario", asset_path=asset, **params)
    res = must(env, f"run_anim_scenario {asset}")
    while res.get("job_id") and not res.get("done"):
        time.sleep(2.0)
        res = must(editor("poll_automation_tests", job_id=res["job_id"]), "poll scenario")
    return res


def run_tests(flt: str) -> dict:
    res = must(editor("run_automation_tests", filter=flt, timeout=300), f"run_automation_tests {flt}")
    while not res.get("done"):
        time.sleep(3.0)
        res = must(editor("poll_automation_tests", job_id=res["job_id"]), "poll tests")
    return res


def find_runtime_ops() -> tuple[list[dict], dict]:
    """ABP_McpRuntimeTest 의 Locomotion · Run 상태 → 그 상태의 SequencePlayer 를 BlendSpacePlayer($blendspace, X ← Speed)로 바꾸는 op.
    (Run 상태 플레이어는 SequencePlayer 라 set_asset 으로 BlendSpace 를 끼울 수 없다 — 노드를 바꾼다)"""
    s = must(editor("get_anim_graph_structure", asset_path=RUNTIME, depth=0), "runtime structure")
    full = must(editor("get_anim_graph_structure", asset_path=RUNTIME, depth=-1), "runtime structure (state machines)")  # 상태머신 뷰는 depth -1
    sm = next(m for m in full["state_machines"] if m["name"] == "Locomotion")
    run_state = next(st for st in sm["states"] if st["name"] == "Run")
    g = must(editor("get_anim_graph_structure", asset_path=RUNTIME, graph_guid=run_state["bound_graph_guid"], depth=0), "run state graph")
    player = next(n for n in g["nodes"] if n["class"] == "AnimGraphNode_SequencePlayer")
    root_slot = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Slot")
    ops = [{"op": "remove_node", "node": player["node_guid"]},
           {"op": "add_node", "ref": "bs", "graph": run_state["bound_graph_guid"], "class": "AnimGraphNode_BlendSpacePlayer", "asset": "$blendspace"},
           {"op": "add_node", "ref": "spd", "graph": run_state["bound_graph_guid"], "class": "K2Node_VariableGet", "variable": "Speed"},
           {"op": "connect", "from": {"ref": "spd", "pin": "Speed"}, "to": {"ref": "bs", "pin": "X"}},
           {"op": "connect", "from": {"ref": "bs", "pin": "Pose"}, "to": {"result_of": {"node": run_state["node_guid"]}, "pin": "Result"}}]
    return ops, {"run_state": run_state["node_guid"], "old_player": player["node_guid"], "root_slot": root_slot["node_guid"],
                 "root_slot_always_update": bool((root_slot.get("properties") or {}).get("bAlwaysUpdateSourcePose"))}


def combat_upper_slot() -> str:
    s = must(editor("get_anim_graph_structure", asset_path=COMBAT, depth=0), "combat structure")
    return next(n["node_guid"] for n in s["nodes"] if n["class"] == "AnimGraphNode_Slot" and (n.get("properties") or {}).get("SlotName") == "UpperBody")


def base(**over) -> dict:
    req = {"target_skeleton": VESPER, "target_mesh": MESH, "hero": "Vesper", "output_path": RUN, "description": "Phase 7 통합 테스트"}
    req.update(over)
    return {k: v for k, v in req.items() if v is not ...}


def bs_request(**over) -> dict:
    ops, _ = find_runtime_ops()
    fields = dict(family="Common", animation_name="AS_Vesper_Common_WalkFastP7", motion_category="locomotion", loop=True,
                  reference_animations=[WALK], edits={"operations": [{"op": "retime", "rate": 1.25}]},
                  package={"blendspace": {"name": "BS_Vesper_Common_WalkFastP7", "dimensions": 1, "axes": [{"name": "Speed", "min": 0, "max": 500}],
                                          "samples": [{"animation": "$asset", "value": [300]}, {"animation": IDLE, "value": [0]}]}},
                  integrate_anim_bp=True,
                  anim_bp={"asset_path": RUNTIME, "operations": ops,
                           "scenario": {"set_variables": {"Speed": 300}, "expect": {"state_machines": {"Locomotion": "Run"}}, "wait_frames": 10}})
    fields.update(over)
    return base(**fields)


# ---- 섹션 ----
def section_hashes() -> None:
    print("== production AnimBPs · skeleton · sources hashes · revisions · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["revisions"] = {p: revision(p) for p in (COMBAT, LAYERS, BASE, RUNTIME)}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    st = must(editor("get_editor_status"), "status")
    # Phase 7 은 40개였다 — 뒤 Phase 가 Tool 을 더한다(8-2 capture_animation → 41)
    check("promote_animation" in {t["name"] for t in st["tools"]} and len(st["tools"]) >= 40, f"≥ 40 tools incl. promote_animation ({len(st['tools'])})")
    check(st["generation"].get("promotion_paths") == ["/Game/Animation/Hero/"], f"promotion_paths {st['generation'].get('promotion_paths')}")
    print(f"   {len(HASHED)} files hashed · revisions {STATE['revisions']} · Content changes before {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_plan() -> None:
    print("== plan: assets only vs connect · blocks")
    rev_before = revision(COMBAT)
    req = bs_request(integrate_anim_bp=False, anim_bp=None, animation_name="AS_Vesper_Common_WalkFastP7Plan")
    p = must(SERVICE.plan_motion_generation(request=req), "plan assets only")
    steps = [s["step"] for s in p["candidates"][0]["steps"]]
    check("anim_bp_test" not in steps and "anim_bp_prepare" not in steps and steps[-1] == "package_blendspace",
          f"assets-only plan has no AnimBP step ({steps})")
    check(revision(COMBAT) == rev_before and revision(RUNTIME) == STATE["revisions"][RUNTIME], "production revisions unchanged by planning")
    p = must(SERVICE.plan_motion_generation(request=bs_request(animation_name="AS_Vesper_Common_WalkFastP7Plan2")), "plan connect")
    cand = p["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    test = cand["steps"][-2]
    check(steps[-3:] == ["package_blendspace", "anim_bp_test", "anim_bp_prepare"], f"connect plan steps {steps}")
    check(test["operational"]["revision"] == STATE["revisions"][RUNTIME] and test["operational"]["skeleton"] == VESPER, "revision · skeleton pinned")
    check("ANIM_BP_OPS_RESOLVED_AT_RUN" in cand["risks"], "placeholder ops → risk ANIM_BP_OPS_RESOLVED_AT_RUN")
    blocks = {}
    req = base(family="Rifle", animation_name="AS_Vesper_Rifle_PlanBlockP7", motion_category="weapon_action", reference_animations=[RECOIL],
               edits={"operations": [{"op": "concat"}]}, package={"montage": {"slot": "WeaponP7"}})
    blocks["slot"] = must(SERVICE.plan_motion_generation(request=req), "plan slot")["excluded"]
    other = None
    for abp in ("/Game/Animation/Test/ABP_McpTest", "/Game/Animation/Test/ABP_McpBsTest", "/Game/Animation/Test/ABP_McpVarTest"):
        env = editor("get_anim_blueprint_info", asset_path=abp)
        if env.get("ok") and not (env["result"].get("target_skeleton") or "").startswith(VESPER):
            other = abp
            break
    if other:
        req = base(family="Rifle", animation_name="AS_Vesper_Rifle_PlanBlockP7", motion_category="weapon_action", reference_animations=[RECOIL],
                   edits={"operations": [{"op": "concat"}]}, integrate_anim_bp=True, anim_bp={"asset_path": other})
        blocks["skeleton"] = must(SERVICE.plan_motion_generation(request=req), "plan skeleton")["excluded"]
    req = base(family="Rifle", animation_name="AS_Vesper_Rifle_PlanBlockP7", motion_category="weapon_action", reference_animations=[RECOIL],
               edits={"operations": [{"op": "concat"}]}, integrate_anim_bp=True,
               anim_bp={"asset_path": COMBAT, "operations": [{"op": "set_property", "node": "00000000000000000000000000000000", "property": "Alpha", "value": 1}]})
    blocks["preview"] = must(SERVICE.plan_motion_generation(request=req), "plan preview")["excluded"]
    # existing_motion 후보의 차단 사유(local_ai 는 프롬프트가 없어 · meshy 는 유료 차단으로 따로 빠진다)
    reasons = {k: next((e["reason"] for e in v if e["provider"] == "existing_motion"), None) for k, v in blocks.items()}
    check(reasons["slot"] == "SLOT_NOT_IN_SKELETON", f"unregistered slot → SLOT_NOT_IN_SKELETON ({reasons['slot']})")
    if other:
        check(reasons["skeleton"] == "SKELETON_MISMATCH", f"AnimBP on another skeleton ({other}) → SKELETON_MISMATCH ({reasons['skeleton']})")
    else:
        print("   (no test AnimBP on another skeleton found — SKELETON_MISMATCH covered by pytest)")
    check(reasons["preview"] == "PREVIEW_INVALID", f"invalid op on the production AnimBP → PREVIEW_INVALID ({reasons['preview']})")
    check(revision(COMBAT) == rev_before, "production revision unchanged after preview")
    STATE["plan"] = {"blocks": reasons, "other_skeleton_abp": other}


def section_chain_bs() -> None:
    print("== chain_bs (example B — transition): walk retime → BS1D → RuntimeTest copy Run state → Speed 300 Run · Speed 0 Idle")
    plan, job, seconds = run_plan(bs_request(), "chain_bs")
    seq, bs = f"{RUN}/AS_Vesper_Common_WalkFastP7", f"{RUN}/BS_Vesper_Common_WalkFastP7"
    check(job["generated_assets"] == [seq, bs], f"generated_assets = sequence + BlendSpace ({job['generated_assets']})")
    abp = job["anim_bp"]
    test = abp["test"]
    check(test["apply"]["compile"]["ok"] and test["apply"]["compile"]["num_errors"] == 0, f"copy compiles 0 errors ({test['apply']['compile']})")
    check(all(s["failed"] == 0 and s["total"] >= 1 for s in test["smoke"]), f"smoke passed {[(s['filter'], s['passed'], s['failed']) for s in test['smoke']]}")
    check(test["scenario"]["ok"] and test["scenario"]["observed"]["state_machines"]["Locomotion"]["state"] == "Run",
          f"scenario Speed 300 → Run ({test['scenario']['observed']['state_machines']})")
    idle = scenario(abp["test_copy"], set_variables={"Speed": 0}, expect={"state_machines": {"Locomotion": "Idle"}}, wait_frames=10, mesh=MESH)
    observed = idle["tests"][0].get("observed") or {}
    check(idle["ok"] and observed.get("state_machines", {}).get("Locomotion", {}).get("state") == "Idle", f"copy Speed 0 → Idle ({observed.get('state_machines')})")
    detail = must(editor("list_animation_assets", path_prefix=RUN, details=True, **{"class": "BlendSpace"}), "bs details")["assets"]
    samples = next(a["blendspace"]["samples"] for a in detail if a["asset_path"].startswith(bs + "."))
    check(samples[0]["animation"].startswith(seq + "."), "BlendSpace sample 0 = the generated sequence")
    check(abp["apply_payload"]["expected_revision"] == STATE["revisions"][RUNTIME] and abp["apply_payload"]["asset_path"] == RUNTIME,
          "apply payload targets the original with its revision")
    check(revision(RUNTIME) == STATE["revisions"][RUNTIME], "RuntimeTest AnimBP itself unchanged (only the copy was edited)")
    check(abp["test_copy"] in job["intermediate_assets"], "the copy is an intermediate asset")
    STATE["chain_bs"] = {"job_id": job["job_id"], "seconds": seconds, "sequence": seq, "blendspace": bs, "copy": abp["test_copy"],
                         "scenario_run": test["scenario"]["observed"], "scenario_idle": observed, "promotion": job["promotion"],
                         "limitations": [lim["code"] for lim in job["limitations"]]}


def section_chain_montage() -> None:
    print("== chain_montage (example C): recoil concat ×3 → additive · UpperBody loop montage → ABP_Hero_Combat copy · production preview")
    slot = combat_upper_slot()
    req = base(family="Rifle", animation_name="AS_Vesper_Rifle_FireLoopP7", motion_category="weapon_action", loop=True, reference_animations=[RECOIL],
               edits={"operations": [{"op": "concat"}, {"op": "concat"}]},
               package={"additive": {"additive_type": "LocalSpaceBase", "ref_pose_type": "LocalAnimFrame", "ref_frame_index": 0},
                        "montage": {"slot": "UpperBody", "blend_in": 0.1, "blend_out": 0.15, "sections": [{"name": "Loop", "start": 0, "next": "Loop"}]}},
               integrate_anim_bp=True,
               anim_bp={"asset_path": COMBAT, "operations": [{"op": "set_property", "node": slot, "property": "bAlwaysUpdateSourcePose", "value": True}],
                        "scenario": {"montage": "$montage", "expect": {"slots_active": ["UpperBody"]}, "wait_frames": 10}})
    plan, job, seconds = run_plan(req, "chain_montage")
    test_step = plan["candidates"][0]["steps"][-2]
    check(test_step["preview"]["valid"] and test_step["operational"]["revision"] == STATE["revisions"][COMBAT],
          "plan: ops previewed valid on the production AnimBP · revision pinned")
    seq, montage = f"{RUN}/AS_Vesper_Rifle_FireLoopP7", f"{RUN}/AM_Vesper_Rifle_FireLoopP7"
    check(job["generated_assets"] == [seq, montage], f"generated_assets = sequence + montage ({job['generated_assets']})")
    add = job["package"]["additive"]
    check(add["additive_valid"] and add["additive_type"] == "AAT_LocalSpaceBase", f"additive {add['additive_type']} / {add['ref_pose_type']} valid")
    mon = job["package"]["montage"]
    check(mon["slot"] == "UpperBody" and mon["sections"] == [{"name": "Loop", "start": 0, "next": "Loop"}], f"montage UpperBody loop ({mon['sections']})")
    scn = job["anim_bp"]["test"]["scenario"]
    check(scn["ok"] and scn["observed"]["slots"].get("UpperBody") is True, f"copy: UpperBody active ({scn['observed']['slots']})")
    op = job["anim_bp"]["operational"]
    check(op["preview"]["valid"] and op["revision"] == STATE["revisions"][COMBAT], "run: production preview valid · revision unchanged")
    payload = job["anim_bp"]["apply_payload"]
    check(payload["asset_path"] == COMBAT and payload["expected_revision"] == STATE["revisions"][COMBAT] and payload["compile"],
          "apply payload {asset_path, operations, expected_revision, compile}")
    codes = {lim["code"] for lim in job["limitations"]}
    check({"ANIM_BP_APPLY_PENDING", "NOTIFIES_NOT_ADDED"} <= codes, f"limitations ANIM_BP_APPLY_PENDING · NOTIFIES_NOT_ADDED ({sorted(codes)})")
    check(sha256(COMBAT) == STATE["hashes"][COMBAT] and revision(COMBAT) == STATE["revisions"][COMBAT], "ABP_Hero_Combat .uasset · revision unchanged")
    STATE["chain_montage"] = {"job_id": job["job_id"], "seconds": seconds, "sequence": seq, "montage": montage, "copy": job["anim_bp"]["test_copy"],
                              "observed": scn["observed"], "apply_payload": payload, "limitations": sorted(codes), "promotion": job["promotion"]}


def section_independent() -> None:
    print("== independent: reuse the kept Kimodo slash → DefaultSlot montage → ABP_Hero_Combat copy")
    req = base(family="Sword", animation_name="AS_Vesper_Sword_KimodoSlash", motion_category="weapon_action", reference_animations=[KIMODO],
               package={"montage": {"slot": "DefaultSlot", "name": "AM_Vesper_Sword_KimodoSlashP7"}}, integrate_anim_bp=True,
               anim_bp={"asset_path": COMBAT, "operations": [], "scenario": {"montage": "$montage", "expect": {"slots_active": ["DefaultSlot"]}, "wait_frames": 10}})
    plan, job, seconds = run_plan(req, "independent")
    montage = f"{RUN}/AM_Vesper_Sword_KimodoSlashP7"
    check(job["reused_assets"] == [KIMODO] and job["generated_assets"] == [montage], f"reused {job['reused_assets']} · generated {job['generated_assets']}")
    check(not uasset(f"{RUN}/AS_Vesper_Sword_KimodoSlash").exists(), "no new sequence")
    scn = job["anim_bp"]["test"]["scenario"]
    check(scn["ok"] and scn["observed"]["slots"].get("DefaultSlot") is True, f"copy: DefaultSlot active ({scn['observed']['slots']})")
    check("apply_payload" not in job["anim_bp"], "no operations → no apply payload")
    check(sha256(KIMODO) == STATE["hashes"][KIMODO], "Kimodo source .uasset unchanged")
    STATE["independent"] = {"job_id": job["job_id"], "seconds": seconds, "montage": montage, "observed": scn["observed"]}


def section_guard() -> None:
    print("== guard: generation_guard on = allow list · no overwrite / off = unchanged")
    outside = "/Game/Animation/Hero/Vesper/__P7GuardProbe"
    env = editor("create_anim_montage", asset_path=f"{outside}/AM_X", animation=WALK, generation_guard=True)
    check(code_of(env)[0] == "OUTPUT_PATH_NOT_ALLOWED" and not (ROOT / "Content" / outside.removeprefix("/Game/")).exists(),
          f"montage outside the allow list refused ({code_of(env)})")
    env = editor("set_sequence_additive", asset_path=WALK, additive_type="LocalSpaceBase", generation_guard=True)
    check(code_of(env)[0] == "OUTPUT_PATH_NOT_ALLOWED", f"additive on a production sequence refused ({code_of(env)})")
    env = editor("apply_graph_operations", asset_path=COMBAT, generation_guard=True,
                 operations=[{"op": "set_property", "node": combat_upper_slot(), "property": "bAlwaysUpdateSourcePose", "value": True}])
    check(code_of(env)[0] == "OUTPUT_PATH_NOT_ALLOWED" and revision(COMBAT) == STATE["revisions"][COMBAT], f"apply on the production AnimBP refused ({code_of(env)})")
    env = editor("set_montage_sections", asset_path="/Game/Animation/Hero/Vesper/Sickle/Actions/AM_Vesper_Sickle_Attack1", generation_guard=True,
                 sections=[{"name": "Default", "start": 0}])
    check(code_of(env)[0] == "OUTPUT_PATH_NOT_ALLOWED", f"sections on a production montage refused ({code_of(env)})")
    env = editor("create_blendspace", asset_path=f"{RUN}/Guard/BS_X", skeleton=VESPER, dimensions=1, axes=[{"name": "Speed", "min": 0, "max": 100}],
                 overwrite=True, generation_guard=True)
    check(code_of(env) == ("BAD_REQUEST", "OVERWRITE_NOT_ALLOWED"), f"overwrite refused ({code_of(env)})")
    env = editor("duplicate_animation_blueprint", source_path=COMBAT, dest_path=f"{RUN}/Guard/ABP_X", overwrite=True, generation_guard=True)
    check(code_of(env) == ("BAD_REQUEST", "OVERWRITE_NOT_ALLOWED"), f"duplicate overwrite refused ({code_of(env)})")
    on = must(editor("create_anim_montage", asset_path=f"{RUN}/Guard/AM_GuardOn", animation=WALK, save=True, generation_guard=True), "guard on")
    check(on["guard"]["newly_dirty"] == [f"{RUN}/Guard/AM_GuardOn"] and on["saved"], f"guard on inside: guard.newly_dirty {on['guard']}")
    off = must(editor("create_anim_montage", asset_path=f"{RUN}/Guard/AM_GuardOff", animation=WALK, save=True), "guard off")
    check("guard" not in off and off["saved"], "guard off (default): same result shape as before (no guard field)")
    env = editor("create_anim_montage", asset_path=f"{outside}/AM_Y", animation=f"{RUN}/Guard/AS_Missing")
    check(code_of(env)[0] == "ASSET_NOT_FOUND", f"guard off: no path check (fails later on the missing animation — {code_of(env)})")
    res = run_tests("AnimGraphMcp.Generation")
    names = {t["name"].rsplit(".", 1)[-1]: t["state"] for t in res["tests"]}
    check(res["failed"] == 0 and {"Guard", "Promote", "WriteGuard"} <= set(names), f"Automation AnimGraphMcp.Generation {res['passed']}/{res['total']} ({names})")
    STATE["guard"] = {"automation": names}


def section_apply_mech() -> None:
    print("== apply_mech: stale expected_revision → REVISION_MISMATCH (copy) · right revision → applied")
    copy = STATE["chain_bs"]["copy"]
    _, ids = find_runtime_ops()
    rev, file_hash = revision(copy), sha256(copy)
    # 실제로 바뀌는 값이어야 revision 이 바뀐다 — 원본 Slot 의 현재 값을 뒤집는다(복제본만)
    op = [{"op": "set_property", "node": ids["root_slot"], "property": "bAlwaysUpdateSourcePose", "value": not ids["root_slot_always_update"]}]
    env = editor("apply_graph_operations", asset_path=copy, operations=op, expected_revision="sha1:0000000000000000000000000000000000000000", compile=True)
    check(code_of(env)[0] == "REVISION_MISMATCH" and revision(copy) == rev and sha256(copy) == file_hash, f"stale revision refused, copy unchanged ({code_of(env)})")
    res = must(editor("apply_graph_operations", asset_path=copy, operations=op, expected_revision=rev, compile=True, save=False, generation_guard=True), "apply copy")
    check(res["revision_before"] == rev and res["revision_after"] != rev and res["compile"]["num_errors"] == 0 and not res["saved"],
          "right revision applies (compile 0 errors, left unsaved for the promote dirty check)")
    STATE["apply_mech"] = {"copy": copy, "revision_before": rev, "revision_after": res["revision_after"]}


def section_promote() -> None:
    print("== promote: dry_run refusals → real moves into _P7PromoteTest (no redirectors, references kept)")
    bs, seq, copy = STATE["chain_bs"]["blendspace"], STATE["chain_bs"]["sequence"], STATE["chain_bs"]["copy"]
    seq2, montage = STATE["chain_montage"]["sequence"], STATE["chain_montage"]["montage"]
    dest = {p: f"{PROMO}/{p.rsplit('/', 1)[-1]}" for p in (bs, seq, seq2, montage)}
    refusals = {
        "MISSING_CONFIRM": editor("promote_animation", assets=[{"source": bs, "dest": dest[bs]}]),
        "SOURCE_NOT_CANDIDATE": editor("promote_animation", assets=[{"source": WALK, "dest": f"{PROMO}/AS_Walk"}], dry_run=True),
        "UNSUPPORTED_CLASS": editor("promote_animation", assets=[{"source": copy, "dest": f"{PROMO}/ABP_Copy"}], dry_run=True),
        "DEST_IS_CANDIDATE_PATH": editor("promote_animation", assets=[{"source": bs, "dest": f"{RUN}/Moved/BS"}], dry_run=True),
        "OUTSIDE_PROMOTION_PATHS": editor("promote_animation", assets=[{"source": bs, "dest": "/Game/Animation/P7Outside/BS"}], dry_run=True),
        "DEST_PROTECTED": editor("promote_animation", assets=[{"source": bs, "dest": BASE}], dry_run=True),
        "DEST_EXISTS": editor("promote_animation", assets=[{"source": bs, "dest": WALK}], dry_run=True),
        "DEST_NOT_ASSET_PATH": editor("promote_animation", assets=[{"source": bs, "dest": PROMO + "/"}], dry_run=True),
        "DUPLICATE_DEST": editor("promote_animation", assets=[{"source": bs, "dest": dest[bs]}, {"source": seq, "dest": dest[bs]}], dry_run=True),
        "REFERENCER_DIRTY": editor("promote_animation", assets=[{"source": bs, "dest": dest[bs]}], dry_run=True),  # apply_mech 가 복제본을 미저장으로 남겼다
    }
    got = {k: code_of(v) for k, v in refusals.items()}
    for reason, (code, actual) in got.items():
        check(actual == reason, f"dry_run refused: {reason} ({code} {actual})")
    must(editor("save_animation_blueprint", asset_path=copy), "save copy")
    planned = must(editor("promote_animation", assets=[{"source": bs, "dest": dest[bs]}], dry_run=True), "dry_run bs")["planned"][0]
    check(planned["referencers"] == [{"package": copy, "candidate": True, "allowed": True}] or
          {r["package"] for r in planned["referencers"]} == {copy}, f"dry_run lists the copy as a candidate referencer ({planned['referencers']})")
    check(uasset(bs).exists() and not uasset(dest[bs]).exists(), "dry_run changed nothing")
    t0 = time.time()
    moved_bs = must(editor("promote_animation", assets=[{"source": bs, "dest": dest[bs]}], confirm=True), "promote bs")
    t_bs = round(time.time() - t0, 2)
    refused = editor("promote_animation", assets=[{"source": seq, "dest": dest[seq]}], confirm=True)
    check(code_of(refused) == ("ASSET_REFERENCED", "REFERENCED_OUTSIDE_CANDIDATES") and uasset(seq).exists(),
          f"sample referenced by the promoted BS (outside candidates) refused ({code_of(refused)})")
    moved_seq = must(editor("promote_animation", assets=[{"source": seq, "dest": dest[seq]}], confirm=True, allow_referencers=[dest[bs]]), "promote seq")
    moved_pair = must(editor("promote_animation", assets=[{"source": montage, "dest": dest[montage]}, {"source": seq2, "dest": dest[seq2]}], confirm=True),
                      "promote montage + sequence")
    results = [moved_bs, moved_seq, moved_pair]
    for res in results:
        for m in res["moved"]:
            check(m["same_content"], f"same content hash {m['dest'].rsplit('.', 1)[-1]}")
        check(res["redirectors"] == 0, f"redirectors 0 ({[m['dest'].rsplit('/', 1)[-1] for m in res['moved']]})")
    for old, new in dest.items():
        check(not uasset(old).exists() and uasset(new).exists(), f"old file gone · new file present: {old.rsplit('/', 1)[-1]}")
    found = must(editor("search_animations", path_prefix=RUN, limit=200, **{"class": "all"}), "search old")["items"]
    check(not [i for i in found if any(i["asset_path"].startswith(o + ".") for o in dest)], "no asset left at the old paths (registry)")
    copy_bytes = uasset(copy).read_bytes()
    check(dest[bs].encode() in copy_bytes and bs.encode() not in copy_bytes, "the copy AnimBP now references the new BlendSpace path on disk")
    check(copy in moved_bs["fixed_referencers"] and dest[bs] in moved_seq["fixed_referencers"], "fixed_referencers: copy (BS) · BS (sample)")
    detail = must(editor("list_animation_assets", path_prefix=PROMO, details=True), "promoted details")["assets"]
    by = {a["asset_path"].split(".")[0]: a for a in detail}
    check(by[dest[bs]]["blendspace"]["samples"][0]["animation"].startswith(dest[seq] + "."), "BS sample → promoted sequence")
    check(by[dest[montage]]["montage"]["slots"][0]["segments"][0]["animation"].startswith(dest[seq2] + "."), "montage segment → promoted sequence (same batch)")
    comp = must(editor("compile_animation_blueprint", asset_path=copy, save_on_success=True), "compile copy")
    check(comp["ok"] and comp["num_errors"] == 0, "copy still compiles with the promoted BlendSpace")
    STATE["promote"] = {"refusals": got, "dest": dest, "seconds_bs": t_bs, "saved": [r["saved_packages"] for r in results],
                        "fixed": [r["fixed_referencers"] for r in results], "removed_files": [r["removed_files"] for r in results]}


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"production AnimBPs · skeleton · RuntimeTest · sources .uasset SHA-256 unchanged ({len(STATE['hashes'])} files, changed {changed})")
        STATE["hashes_changed"] = changed
    if "revisions" in STATE:
        now = {p: revision(p) for p in STATE["revisions"]}
        check(now == STATE["revisions"], "production revisions unchanged")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        allowed = ("Content/" + RUN.removeprefix("/Game/") + "/", "Content/" + PROMO.removeprefix("/Game/") + "/")
        outside = [p for p in new if not p.startswith(allowed)]
        print(f"   new Content changes {len(new)} (outside the run · promote folders: {outside})")
        check(not outside, "Content/ changes are only this run's folder and the promote test folder")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "plan": section_plan, "chain_bs": section_chain_bs, "chain_montage": section_chain_montage,
            "independent": section_independent, "guard": section_guard, "apply_mech": section_apply_mech, "promote": section_promote,
            "dirty": section_dirty}


def finish() -> int:
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase7_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    for name in args.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    return finish()


if __name__ == "__main__":
    sys.exit(main())
