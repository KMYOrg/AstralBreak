"""Phase 7 — 포장(package) · AnimBP 연결(anim_bp) · 승격 제안 (지침서 §9 · §12 · §14 Phase 7). FakeEditor 로 에디터 없이 돈다.

요청 규칙(integrate/anim_bp 조합 · 자리표시 · 이름 · 슬롯 형식) · 계획(integrate false → anim_bp 단계 · AnimBP 호출 0 / true → 단계 · revision 고정 ·
SKELETON_MISMATCH · SLOT_NOT_IN_SKELETON) · 실행(포장 → generated_assets · 시나리오 비동기 poll · 실패 → INTEGRATION_FAILED 폴백 없음 · 시퀀스 보존 ·
취소 · 독립 재사용 경로 · 승격 제안 · 모든 포장 · 연결 쓰기에 generation_guard · 운영 AnimBP 무변경).
"""
from __future__ import annotations

import pytest

from anim_gen.request import bind_placeholders, normalize, placeholder_uses
from conftest import (ABP_TOOLS, AIM_IDLE, COMBAT_ABP, INTEGRATION_WRITE_TOOLS, KATANA, OTHER_ABP, OUT, RUNTIME_ABP, VESPER, VESPER_MESH, WALK,
                      err, mock_ai, request)

SEQ = f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"
MONTAGE = f"{OUT}/AM_Vesper_Rifle_AimIdle_TwistP3"
BS = f"{OUT}/BS_Vesper_Rifle_TwistP3"
UPPER_LOOP = {"slot": "UpperBody", "sections": [{"name": "Loop", "start": 0.0, "next": "Loop"}]}
BS_SPEC = {"name": "BS_Vesper_Rifle_TwistP3", "dimensions": 1, "axes": [{"name": "Speed", "min": 0, "max": 500}],
           "samples": [{"animation": "$asset", "value": [300]}, {"animation": WALK, "value": [0]}]}
SCENARIO_MONTAGE = {"montage": "$montage", "expect": {"slots_active": ["UpperBody"]}, "wait_frames": 10}


def anim_bp(asset=COMBAT_ABP, operations=None, scenario=None, smoke=True) -> dict:
    return {"asset_path": asset, "operations": operations or [], "scenario": scenario, "smoke": smoke}


def plan_env(service, **over) -> dict:
    return service.plan_motion_generation(request=request(**over))


def plan(service, **over) -> dict:
    env = plan_env(service, **over)
    assert env["ok"], env["error"]
    return env["result"]


def bad(service, **over) -> dict:
    env = plan_env(service, **over)
    assert not env["ok"]
    return env["error"]


def steps_of(p: dict) -> list[str]:
    return [s["step"] for s in p["candidates"][0]["steps"]]


def excluded(p: dict) -> dict:
    return {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}


def run(service, p: dict, save: bool = False) -> dict:
    return service.generate_motion(plan_id=p["plan_id"], save=save)


def finish(service, env: dict) -> dict:
    """RUNNING(시나리오 대기)이면 poll 로 끝까지."""
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    for _ in range(10):
        if job["status"] != "RUNNING":
            return job
        job = service.get_generation_status(job_id=job["job_id"])["result"]
    return job


# ---- 요청 규칙 ----
def test_integrate_true_needs_anim_bp_and_false_refuses_it(service):
    e = bad(service, integrate_anim_bp=True)
    assert (e["details"]["field"], e["details"]["reason"]) == ("anim_bp", "MISSING_FIELD")
    e = bad(service, anim_bp=anim_bp())
    assert e["details"]["reason"] == "CONFLICTING_FIELDS"


def test_package_shape_rules(service):
    assert bad(service, package={})["details"]["reason"] == "MISSING_FIELD"
    assert bad(service, package={"notify": {}})["details"]["reason"] == "UNKNOWN_FIELD"
    assert bad(service, package={"montage": {"slot": "Upper Body"}})["details"]["field"] == "package.montage.slot"
    assert bad(service, package={"montage": {"sections": [{"name": "Loop"}]}})["details"]["field"] == "package.montage.sections[0]"
    e = bad(service, package={"blendspace": {**BS_SPEC, "samples": [{"animation": "$asset", "value": [900]}]}})
    assert e["details"]["reason"] == "OUT_OF_RANGE"
    assert bad(service, package={"blendspace": {**BS_SPEC, "name": None}})["details"]["reason"] == "MISSING_FIELD"


def test_montage_name_defaults_from_animation_name_and_names_are_unique():
    req, _ = normalize(request(package={"montage": {}}))
    assert req["package"]["montage"]["name"] == "AM_Vesper_Rifle_AimIdle_TwistP3" and req["package"]["montage"]["slot"] == "DefaultSlot"
    with pytest.raises(Exception) as exc:
        normalize(request(package={"montage": {"name": "BS_X"}, "blendspace": {**BS_SPEC, "name": "BS_X"}}))
    assert exc.value.details["reason"] == "DUPLICATE_NAME"


def test_additive_defaults_and_base_pose_rule():
    req, _ = normalize(request(package={"additive": {}}))
    assert req["package"]["additive"] == {"additive_type": "LocalSpaceBase", "ref_pose_type": "LocalAnimFrame", "ref_frame_index": 0, "ref_pose_sequence": None}
    with pytest.raises(Exception) as exc:
        normalize(request(package={"additive": {"ref_pose_type": "AnimFrame"}}))  # AnimFrame 은 기준 시퀀스가 있어야 유효(IsValidAdditive)
    assert exc.value.details["reason"] == "MISSING_FIELD"
    req, _ = normalize(request(package={"additive": {"ref_pose_type": "AnimFrame", "ref_pose_sequence": "$asset"}}))
    assert req["package"]["additive"]["ref_pose_sequence"] == "$asset"


def test_placeholders_must_be_bound_and_known(service):
    e = bad(service, integrate_anim_bp=True, anim_bp=anim_bp(scenario={"montage": "$montage"}))
    assert (e["details"]["reason"], e["details"]["field"]) == ("PLACEHOLDER_UNBOUND", "anim_bp.scenario.montage")
    e = bad(service, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "set_asset", "node": "n1", "asset": "$blendspce"}]))
    assert e["details"]["reason"] == "UNKNOWN_PLACEHOLDER"
    e = bad(service, package={"montage": {}}, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "set_asset", "node": "n1", "asset": "$blendspace"}]))
    assert e["details"]["reason"] == "PLACEHOLDER_UNBOUND"


def test_placeholders_replace_whole_string_values_only():
    ops = [{"op": "set_asset", "node": "n1", "asset": "$blendspace"}, {"op": "rename_node", "node": "n2", "name": "keep $blendspace text"}]
    assert placeholder_uses(ops) == [("[0].asset", "$blendspace")]
    bound = bind_placeholders(ops, {"$blendspace": BS})
    assert bound[0]["asset"] == BS and bound[1]["name"] == "keep $blendspace text"


# ---- 계획 ----
def test_assets_only_plan_has_package_steps_and_never_touches_an_anim_bp(service, fake):
    p = plan(service, package={"montage": UPPER_LOOP, "blendspace": BS_SPEC})
    assert steps_of(p) == ["resolve_source", "edit", "validate", "package_montage", "package_blendspace"]
    assert p["candidates"][0]["chain"] == ["existing_motion", "direct_key", "package"]
    assert not fake.abp_calls and not fake.writes  # 애셋만 요청하면 AnimBP 를 읽지도 않는다 · 계획은 쓰지 않는다
    montage_step = p["candidates"][0]["steps"][3]
    assert montage_step["inputs"]["asset_path"] == MONTAGE and montage_step["checked"]["skeleton_slots"] == ["DefaultSlot", "UpperBody"]
    assert "NOTIFIES_NOT_ADDED" in {lim["code"] for lim in p["candidates"][0]["expected_limitations"]}
    assert p["promotion_paths"] == ["/Game/Animation/Hero/"]


def test_integrate_plan_pins_revision_and_previews_on_the_production_bp(service, fake):
    ops = [{"op": "set_property", "node": "n1", "property": "PlayRate", "value": 1.2}]
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(operations=ops, scenario=SCENARIO_MONTAGE))
    assert steps_of(p)[-3:] == ["package_montage", "anim_bp_test", "anim_bp_prepare"]
    test = p["candidates"][0]["steps"][-2]
    assert test["operational"] == {"asset_path": COMBAT_ABP, "revision": "sha1:combat", "skeleton": VESPER}
    assert test["preview"]["valid"] and fake.count("preview_graph_operations") == 1
    assert "ANIM_BP_APPLY_PENDING" in {lim["code"] for lim in p["candidates"][0]["expected_limitations"]}
    assert not fake.writes  # 미리보기 · 정보 조회만


def test_ops_with_placeholders_are_previewed_at_run_time(service, fake):
    ops = [{"op": "set_asset", "node": "n1", "asset": "$montage"}]
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(operations=ops))
    cand = p["candidates"][0]
    assert "ANIM_BP_OPS_RESOLVED_AT_RUN" in cand["risks"] and cand["steps"][-2]["preview"] is None
    assert fake.count("preview_graph_operations") == 0


@pytest.mark.parametrize("asset, reason", [(OTHER_ABP, "SKELETON_MISMATCH"), ("/Game/Animation/Test/ABP_Missing", "ANIM_BP_NOT_FOUND")])
def test_wrong_or_missing_anim_bp_excludes_the_candidate(service, asset, reason):
    p = plan(service, integrate_anim_bp=True, anim_bp=anim_bp(asset=asset))
    assert not p["executable"] and excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", reason)


def test_invalid_preview_excludes_the_candidate(service):
    p = plan(service, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "bad_op"}]))
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "PREVIEW_INVALID")


def test_slot_missing_from_the_skeleton_blocks_the_plan(service, fake):
    p = plan(service, package={"montage": {"slot": "Weapon"}})
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "SLOT_NOT_IN_SKELETON")
    assert not fake.count("add_skeleton_slot")  # 공유 스켈레톤 편집은 별도 승인 — 계획이 등록하지 않는다


def test_additive_on_a_reused_asset_is_refused(service):
    p = plan(service, reference_animations=[WALK], search=None, edits=..., package={"additive": {}})
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "ADDITIVE_ON_REUSED")


def test_blendspace_fixed_samples_are_checked(service):
    p = plan(service, package={"blendspace": {**BS_SPEC, "samples": [{"animation": "$asset", "value": [300]}, {"animation": KATANA, "value": [0]}]}})
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "SKELETON_MISMATCH")
    p = plan(service, package={"blendspace": {**BS_SPEC, "samples": [{"animation": f"{OUT}/AS_Nope", "value": [0]}]}})
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "NO_MATCH")


def test_existing_package_output_is_refused_like_the_final_asset(service, fake):
    fake.assets[MONTAGE] = {"class": "AnimMontage", "skeleton": VESPER}
    e = bad(service, package={"montage": {}})
    assert e["code"] == "ASSET_EXISTS" and e["details"]["asset"] == MONTAGE


def test_integration_plan_is_computed_once_for_every_candidate(make_service, fake):
    service, _ = make_service(local_ai=mock_ai())
    p = plan(service, target_mesh=VESPER_MESH, prompt="A person stands still.", integrate_anim_bp=True, anim_bp=anim_bp())
    assert [c["provider"] for c in p["candidates"]] == ["existing_motion", "local_ai"]
    assert all(c["chain"][-1] == "anim_bp" for c in p["candidates"])
    assert fake.count("get_anim_blueprint_info") == 1


# ---- 실행 ----
def test_package_runs_and_packaged_assets_are_deliverables(service, fake):
    p = plan(service, package={"montage": UPPER_LOOP, "blendspace": BS_SPEC})
    job = run(service, p, save=True)["result"]
    assert job["status"] == "SUCCEEDED"
    assert job["generated_assets"] == [SEQ, MONTAGE, BS]
    assert job["package"]["montage"]["asset"] == MONTAGE and job["package"]["montage"]["sections"] == [{"name": "Loop", "start": 0.0, "next": "Loop"}]
    assert job["package"]["blendspace"]["samples"][0]["animation"] == SEQ  # $asset → 최종 시퀀스
    assert fake.assets[MONTAGE]["animation"] == SEQ and fake.assets[MONTAGE]["slot"] == "UpperBody"


def test_every_package_and_anim_bp_write_uses_generation_guard(service, fake):
    p = plan(service, package={"additive": {}, "montage": UPPER_LOOP, "blendspace": BS_SPEC}, integrate_anim_bp=True,
             anim_bp=anim_bp(operations=[{"op": "set_asset", "node": "n1", "asset": "$blendspace"}], scenario=SCENARIO_MONTAGE))
    finish(service, run(service, p))
    writes = [(t, q) for t, q in fake.calls if t in INTEGRATION_WRITE_TOOLS]
    assert {t for t, _ in writes} == INTEGRATION_WRITE_TOOLS
    assert all(q.get("generation_guard") is True for _, q in writes)


def test_additive_runs_on_the_new_sequence(service, fake):
    job = run(service, plan(service, package={"additive": {"additive_type": "RotationOffsetMeshSpace"}}))["result"]
    assert job["status"] == "SUCCEEDED" and job["package"]["additive"]["asset"] == SEQ
    assert fake.assets[SEQ]["additive_type"] == "RotationOffsetMeshSpace" and fake.assets[AIM_IDLE].get("additive_type") is None


def test_scenario_is_asynchronous_and_polled(service, fake):
    fake.scenario_polls = 2
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(scenario=SCENARIO_MONTAGE))
    env = run(service, p)
    assert env["ok"] and env["result"]["status"] == "RUNNING" and env["result"]["stage"] == "anim_bp_test"
    copy = env["result"]["pending"]["handle"]["copy"]
    assert copy in env["result"]["intermediate_assets"]  # 기다리기 전에 만든 복제본도 Job 에 남는다
    job = finish(service, env)
    assert job["status"] == "SUCCEEDED"
    scenario = job["anim_bp"]["test"]["scenario"]
    assert scenario["ok"] and scenario["observed"]["slots"] == {"UpperBody": True}
    assert scenario["params"]["montage"] == MONTAGE  # $montage → 포장한 몽타주
    assert job["anim_bp"]["test_copy"] == copy and copy.startswith(f"{OUT}/Work/{job['job_id']}/A1/ABP_Hero_Combat_Test_")
    assert copy in job["intermediate_assets"] and copy not in job["generated_assets"]


def test_blendspace_transition_scenario_on_a_runtime_test_bp(service, fake):
    """예시 B — Run 상태 플레이어에 $blendspace, Speed 300 → Run."""
    ops = [{"op": "set_asset", "node": "run-player", "asset": "$blendspace"}]
    p = plan(service, package={"blendspace": BS_SPEC}, integrate_anim_bp=True,
             anim_bp=anim_bp(asset=RUNTIME_ABP, operations=ops, scenario={"set_variables": {"Speed": 300}, "expect": {"state_machines": {"Locomotion": "Run"}}}))
    job = finish(service, run(service, p))
    assert job["status"] == "SUCCEEDED"
    test = job["anim_bp"]["test"]
    assert test["apply"]["compile"] == {"ok": True, "num_errors": 0, "num_warnings": 0}
    assert test["scenario"]["observed"]["state_machines"]["Locomotion"]["state"] == "Run"
    assert [s["filter"] for s in test["smoke"]] == [f"AnimGraphMcp.Smoke.AnimBlueprint.{job['anim_bp']['test_copy'].rsplit('/', 1)[-1]}"]
    applied = [q for t, q in fake.calls if t == "apply_graph_operations"]
    assert applied[0]["operations"][0]["asset"] == BS and applied[0]["asset_path"] == job["anim_bp"]["test_copy"]


def test_scenario_failure_is_integration_failed_without_fallback_and_keeps_the_sequence(make_service, fake):
    service, _ = make_service(local_ai=mock_ai())
    p = plan(service, target_mesh=VESPER_MESH, prompt="A person stands still.", integrate_anim_bp=True,
             anim_bp=anim_bp(asset=RUNTIME_ABP, scenario={"set_variables": {"Speed": 0}, "expect": {"state_machines": {"Locomotion": "Run"}}}))
    job = finish(service, run(service, p))
    assert job["status"] == "FAILED" and job["error"]["code"] == "INTEGRATION_FAILED" and job["error"]["reason"] == "SCENARIO_FAILED"
    assert job["error"]["details"]["observed"]["state_machines"]["Locomotion"]["state"] == "Idle"
    assert job["generated_assets"] == [SEQ]  # 이미 만든 시퀀스는 남긴다
    assert [h["provider"] for h in job["fallback_history"]] == ["existing_motion"]  # local_ai 로 넘어가지 않는다
    assert job["anim_bp"] is None and any("ABP_McpRuntimeTest_Test_" in a for a in job["left_assets"])


@pytest.mark.parametrize("setup, reason", [
    (lambda f: setattr(f, "compile_ok", False), "COMPILE_FAILED"),
    (lambda f: f.smoke_fail.add("Smoke.AnimBlueprint"), "SMOKE_FAILED"),
    (lambda f: f.smoke_missing.add("Smoke.AnimBlueprint"), "SMOKE_NOT_FOUND"),
])
def test_compile_and_smoke_failures(service, fake, setup, reason):
    p = plan(service, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "set_property", "node": "n1", "property": "PlayRate", "value": 1.0}]))
    setup(fake)
    job = finish(service, run(service, p))
    assert (job["status"], job["error"]["code"], job["error"]["reason"]) == ("FAILED", "INTEGRATION_FAILED", reason)


def test_montage_smoke_also_runs(service, fake):
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp())
    job = finish(service, run(service, p))
    assert [s["filter"].split(".")[2] for s in job["anim_bp"]["test"]["smoke"]] == ["AnimBlueprint", "AnimMontage"]
    assert job["anim_bp"]["test"]["smoke"][1]["filter"].endswith(".AM_Vesper_Rifle_AimIdle_TwistP3")


def test_slot_refused_at_run_time_is_integration_failed(service, fake):
    p = plan(service, package={"montage": UPPER_LOOP})
    fake.slots[VESPER] = ["DefaultSlot"]  # 계획 뒤 스켈레톤이 바뀌었다
    job = run(service, p)["error"]["details"]["job"]
    assert (job["error"]["code"], job["error"]["reason"]) == ("INTEGRATION_FAILED", "SLOT_NOT_IN_SKELETON") and job["generated_assets"] == [SEQ]


def test_guard_errors_stop_the_job_unchanged(service, fake):
    p = plan(service, package={"montage": {}})
    fake.fail["create_anim_montage"] = [err("UNEXPECTED_DIRTY", "outside dirty", unexpected=["/Game/Assets/X"])]
    job = run(service, p)["error"]["details"]["job"]
    assert job["error"]["code"] == "UNEXPECTED_DIRTY"  # 가드 오류는 INTEGRATION_FAILED 로 바꾸지 않는다


def test_production_anim_bp_is_only_read_and_the_payload_carries_its_revision(service, fake):
    ops = [{"op": "set_asset", "node": "n1", "asset": "$montage"}]
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(operations=ops, scenario=SCENARIO_MONTAGE))
    job = finish(service, run(service, p))
    assert job["status"] == "SUCCEEDED"
    on_production = {t for t, q in fake.calls if COMBAT_ABP in (q.get("asset_path"), q.get("dest_path"))}
    assert on_production == {"get_anim_blueprint_info", "preview_graph_operations"}  # 운영 AnimBP 는 읽기 · 미리보기뿐
    assert fake.abps[COMBAT_ABP]["revision"] == "sha1:combat"
    payload = job["anim_bp"]["apply_payload"]
    assert payload["asset_path"] == COMBAT_ABP and payload["expected_revision"] == "sha1:combat" and payload["compile"]
    assert payload["operations"][0]["asset"] == MONTAGE and payload["rebind_after_promotion"]
    assert job["anim_bp"]["operational"]["preview"]["valid"]
    assert "ANIM_BP_APPLY_PENDING" in {lim["code"] for lim in job["limitations"]}


def test_stale_expected_revision_is_refused_without_changes(service, fake):
    """적용 메커니즘(복제본) — 낡은 expected_revision 은 REVISION_MISMATCH, 그래프는 그대로(운영 적용과 같은 경로)."""
    p = plan(service, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "set_property", "node": "n1", "property": "PlayRate", "value": 1.0}]))
    job = finish(service, run(service, p))
    copy = job["anim_bp"]["test_copy"]
    before = fake.abps[copy]["revision"]
    env = fake.client().call("apply_graph_operations", asset_path=copy, operations=job["anim_bp"]["operations"], expected_revision="sha1:stale",
                             compile=True)
    assert env["error"]["code"] == "REVISION_MISMATCH" and fake.abps[copy]["revision"] == before


def test_production_revision_change_after_planning_is_reported(service, fake):
    p = plan(service, integrate_anim_bp=True, anim_bp=anim_bp(operations=[{"op": "set_property", "node": "n1", "property": "PlayRate", "value": 1.0}]))
    fake.abps[COMBAT_ABP]["revision"] = "sha1:edited-by-someone"
    job = finish(service, run(service, p))
    assert job["anim_bp"]["apply_payload"]["expected_revision"] == "sha1:edited-by-someone"
    assert "ANIM_BP_CHANGED_SINCE_PLAN" in {d["code"] for d in job["diagnostics"]}


def test_empty_operations_check_playback_only(service, fake):
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(scenario=SCENARIO_MONTAGE))
    assert "ANIM_BP_APPLY_PENDING" not in {lim["code"] for lim in p["candidates"][0]["expected_limitations"]}
    job = finish(service, run(service, p))
    assert job["status"] == "SUCCEEDED" and job["anim_bp"]["test"]["apply"] is None and job["anim_bp"]["test"]["compile"]["ok"]
    assert "apply_payload" not in job["anim_bp"] and not fake.count("apply_graph_operations")


def test_independent_path_packages_an_existing_asset_without_a_new_sequence(service, fake):
    p = plan(service, reference_animations=[WALK], search=None, edits=..., animation_name="AS_Vesper_Rifle_WalkPkg",
             package={"montage": {"slot": "DefaultSlot"}}, integrate_anim_bp=True,
             anim_bp=anim_bp(scenario={"montage": "$montage", "expect": {"slots_active": ["DefaultSlot"]}}))
    assert steps_of(p) == ["resolve_source", "validate", "package_montage", "anim_bp_test", "anim_bp_prepare"]
    job = finish(service, run(service, p))
    montage = f"{OUT}/AM_Vesper_Rifle_WalkPkg"
    assert job["status"] == "SUCCEEDED" and job["reused_assets"] == [WALK] and job["generated_assets"] == [montage]
    assert fake.assets[montage]["animation"] == WALK and not fake.count("apply_animation_edits")
    assert job["promotion"]["assets"] == [{"source": montage, "dest": f"/Game/Animation/Hero/Vesper/Rifle/Locomotion/AM_Vesper_Rifle_WalkPkg"}]


def test_assets_only_job_calls_no_anim_bp_tool(service, fake):
    job = run(service, plan(service, package={"montage": {}}))["result"]
    assert job["status"] == "SUCCEEDED" and not fake.abp_calls and job["anim_bp"] is None


@pytest.mark.parametrize("category, hero, family, folder", [
    ("idle", "Vesper", "Rifle", "/Game/Animation/Hero/Vesper/Rifle/Locomotion"),
    ("weapon_action", "Vesper", None, "/Game/Animation/Hero/Vesper/Common/Actions"),
])
def test_promotion_proposal_follows_the_naming_rule(service, category, hero, family, folder):
    p = plan(service, motion_category=category, hero=hero, family=family, package={"montage": {}})
    job = run(service, p)["result"]
    assert job["promotion"]["folder"] == folder
    assert [a["dest"].rsplit("/", 1)[0] for a in job["promotion"]["assets"]] == [folder, folder]
    assert {a["source"] for a in job["promotion"]["assets"]} == set(job["generated_assets"])


def test_no_promotion_proposal_without_a_hero(service):
    job = run(service, plan(service, hero=None, family=None, animation_name="AS_Generic_TwistP3"))["result"]
    assert job["promotion"]["assets"] == [] and job["promotion"]["note"]


def test_cancel_while_the_scenario_runs_keeps_the_copy(service, fake):
    fake.scenario_polls = 5
    p = plan(service, package={"montage": UPPER_LOOP}, integrate_anim_bp=True, anim_bp=anim_bp(scenario=SCENARIO_MONTAGE))
    job = run(service, p)["result"]
    assert job["status"] == "RUNNING"
    env = service.cancel_generation(job_id=job["job_id"])
    assert env["ok"] and env["result"]["status"] == "CANCELLED" and env["result"]["result_ignored"]
    assert any("ABP_Hero_Combat_Test_" in a for a in env["result"]["intermediate_assets"])
    assert service.get_generation_status(job_id=job["job_id"])["result"]["status"] == "CANCELLED"  # poll 해도 다시 돌지 않는다


def test_explicit_pipe_provider_is_refused(service):
    for name in ("package", "anim_bp"):
        e = bad(service, provider=name)
        assert e["details"]["reason"] == "PIPE_NOT_PROVIDER"


def test_abp_tools_only_when_integrating(service, fake):
    plan(service, package={"blendspace": BS_SPEC})
    assert not [t for t, _ in fake.calls if t in ABP_TOOLS]
    plan(service, integrate_anim_bp=True, anim_bp=anim_bp())
    assert fake.count("get_anim_blueprint_info") == 1
