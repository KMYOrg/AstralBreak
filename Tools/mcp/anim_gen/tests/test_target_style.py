"""Phase 9-5a — 대상별 기준값(U8-b)과 리타기터 구성(U7-c · U8-d). 지침서 §14 '9-5a'.

순수: 정책 style(기준 몸 · 프로필 검사) · 몸 비율(E0 치수) · 정점 목표 순서(요청 > 프로필 > 몸 비율 > 기준값) · 발 좌우 비 프로필 · 빠른 구간 기준.
계획 · 실행: 대상 = 기준 몸이면 계획이 그대로(비트 같음 — 기준 몸을 재지도 않는다), 다른 대상은 정점 목표 · 매끈화 기준을 옮기고 Job 에 남긴다 · 한계
TARGET_STYLE_FROM_REFERENCE · 기준 몸을 못 재면 경고 · 다리 op 는 이 Job 이 만드는 match_existing 리타기터만(FIX_LEGS_NEEDS_MATCH_EXISTING) · 임포트 경로의
재사용 · ops default 는 위험. 가짜 에디터의 대상은 Vesper 뿐이라 정책의 기준 몸을 팔이 짧은 다른 스켈레톤으로 바꿔 '다른 대상'을 만든다.
"""
from __future__ import annotations

import copy

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import policy as policy_mod
from anim_gen import target_style as ts
from anim_gen import timing
from anim_gen.envelope import AnimGenError
from conftest import KATANA, VESPER, VESPER_BONES, VESPER_MESH, request
from test_blender import bl, plan  # noqa: F401 — bl 는 픽스처
from test_body_fit_pipe import body, plan_of, run  # noqa: F401 — body 는 픽스처
from test_fix_legs import CMU_LEGS, LEG_OPS
from test_timing import slow_attack3, timed_request  # noqa: F401 — slow_attack3 는 픽스처

REF = "/Game/Test/SKEL_Reference"
OTHER = "/Game/Test/SKEL_Other"
RTG = "/Game/Animation/Hero/Vesper/Retarget/RTG_KatanaToH"
ARM_K = 1.25                 # 기준 몸의 팔 = Vesper 팔 ÷ 1.25 — Vesper 가 '팔이 상대적으로 긴 다른 대상'이 된다


def short_arms(bones: list[dict], k: float) -> list[dict]:
    out = copy.deepcopy(bones)
    pos = {b["name"]: b["ref_component"]["t"] for b in out}
    for side in "lr":
        up = pos[f"upperarm_{side}"]
        for name in (f"lowerarm_{side}", f"hand_{side}"):
            pos[name][:] = [u + (p - u) / k for u, p in zip(up, pos[name])]
    return out


def use_reference(service, fake, profiles: dict | None = None) -> None:
    fake.bones[REF] = short_arms(VESPER_BONES, ARM_K)
    assert service.set_generation_policy(patch={"style": {"reference_skeleton": REF, "profiles": profiles or {}}})["ok"]


def codes(cand: dict) -> list[str]:
    return [lm["code"] for lm in cand["expected_limitations"]]


def step_of(p: dict, name: str) -> dict:
    return next(s for s in p["candidates"][0]["steps"] if s["step"] == name)


def timed_plan(service, **overrides) -> dict:
    env = service.plan_motion_generation(request=timed_request(**overrides))
    assert env["ok"], env["error"]
    return env


# ---- 정책 ----
def test_default_policy_names_the_reference_body():
    assert policy_mod.load_default()["style"] == {"reference_skeleton": VESPER, "profiles": {}}


@pytest.mark.parametrize("profiles", [
    "x", {"SKEL": {}}, {OTHER: 3}, {OTHER: {"unknown": 1}}, {OTHER: {"stance_max_ratio": 0.5}}, {OTHER: {"stance_max_ratio": True}},
    {OTHER: {"timing_target_peak_cm_s": 10}}, {OTHER: {"timing_target_peak_cm_s": 9000}},
])
def test_policy_rejects_bad_profiles(profiles):
    with pytest.raises(AnimGenError) as exc:
        policy_mod.validate({"style": {"profiles": profiles}})
    assert exc.value.code == "BAD_REQUEST"


def test_policy_accepts_a_profile_and_merges_per_skeleton(service):
    env = service.set_generation_policy(patch={"style": {"profiles": {OTHER: {"stance_max_ratio": 2.5}}}})
    assert env["ok"], env["error"]
    env = service.set_generation_policy(patch={"style": {"profiles": {OTHER: {"timing_target_peak_cm_s": 1000}, REF: {"stance_max_ratio": 2.0}}}})
    style = env["result"]["effective"]["style"]
    assert style["reference_skeleton"] == VESPER and style["profiles"] == {OTHER: {"stance_max_ratio": 2.5, "timing_target_peak_cm_s": 1000}, REF: {"stance_max_ratio": 2.0}}


# ---- 순수 ----
def test_reference_and_profile_lookup():
    pol = {"style": {"reference_skeleton": f"{VESPER}.SKEL_UE5_F", "profiles": {f"{OTHER}.SKEL_Other": {"stance_max_ratio": 2.5}, VESPER: {"stance_max_ratio": 9.0}}}}
    assert ts.reference(pol) == VESPER and ts.is_reference(pol, VESPER) and not ts.is_reference(pol, OTHER)
    assert ts.is_reference(None, OTHER) and ts.is_reference({"style": {}}, OTHER)   # 기준 몸이 없으면 옮길 기준이 없다
    assert ts.profile(pol, OTHER) == {"stance_max_ratio": 2.5} and ts.profile(pol, "/Game/X") == {}
    assert ts.profile(pol, VESPER) == {}                                            # 기준 몸은 기준값 그 자체


def test_body_ratio_of_the_e0_targets():
    vesper = {"arm_dims": {"arm_cm": 47.66}, "leg_dims": {"pelvis_height_cm": 105.24}}
    ida = {"arm_dims": {"arm_cm": 52.49}, "leg_dims": {"pelvis_height_cm": 95.9}}
    manny = {"arm_dims": {"arm_cm": 55.02}, "leg_dims": {"pelvis_height_cm": 95.9}}
    assert ts.proportion(vesper) == pytest.approx(45.29, abs=0.01)
    assert ts.ratio(ida, vesper) == pytest.approx(1.2086, abs=1e-3) and ts.ratio(manny, vesper) == pytest.approx(1.2668, abs=1e-3)
    assert ts.ratio({}, vesper) is None and ts.ratio(ida, {"arm_dims": None, "leg_dims": None}) is None


def test_peak_order_request_profile_ratio_default():
    cfg = timing.normalize(True)
    assert ts.peak(cfg, {}, 1.25) == {"value": 1500.0, "from": "body_ratio", "factor": 1.25}
    assert ts.peak(cfg, {}, None) == {"value": 1200.0, "from": "default", "factor": None}
    assert ts.peak(cfg, {"timing_target_peak_cm_s": 900}, 1.25) == {"value": 900.0, "from": "profile", "factor": None}
    given = timing.normalize({"target_peak_cm_s": 700})
    assert ts.peak(given, {"timing_target_peak_cm_s": 900}, 1.25) == {"value": 700.0, "from": "request", "factor": None}


def test_timing_marks_a_requested_peak_only():
    assert "target_peak_given" not in timing.normalize(True) and "target_peak_given" not in timing.normalize({"max_rate": 1.5})
    assert timing.normalize({"target_peak_cm_s": 900})["target_peak_given"] is True
    with pytest.raises(timing.TimingError):
        timing.normalize({"target_peak_given": True})


def test_stance_profile_respects_the_request_and_the_minimum():
    ops = [{"op": "stance_width", "max_ratio": 3.0, "min_ratio": 1.2}, {"op": "foot_lock"}]
    ts.apply_stance(ops, [{"op": "stance_width"}], {"stance_max_ratio": 2.4})
    assert ops[0]["max_ratio"] == 2.4
    ops = [{"op": "stance_width", "max_ratio": 3.5, "min_ratio": 1.2}]
    ts.apply_stance(ops, [{"op": "stance_width", "max_ratio": 3.5}], {"stance_max_ratio": 2.4})
    assert ops[0]["max_ratio"] == 3.5
    ops = [{"op": "stance_width", "max_ratio": 3.0, "min_ratio": 2.0}]
    ts.apply_stance(ops, [{"op": "stance_width"}], {"stance_max_ratio": 1.5})
    assert ops[0]["max_ratio"] == 2.0


def test_reference_values_list_what_the_plan_borrows():
    req = {"fix": {"timing": timing.normalize(True), "ops": [{"op": "stance_width"}]}}
    steps = [{"step": "select"}, {"step": "timing"}]
    assert ts.reference_values(req, steps, {}) == ["fix.timing target_peak_cm_s", "stance_width max_ratio", "select thresholds"]
    assert ts.reference_values(req, [], {"timing_target_peak_cm_s": 900, "stance_max_ratio": 2.0}) == []
    assert ts.reference_values({"fix": {"timing": timing.normalize({"target_peak_cm_s": 900}), "ops": [{"op": "stance_width", "max_ratio": 3.0}]}}, [], {}) == []
    assert ts.reference_values({"fix": {"ops": [], "body": {}}}, [], {}) == []


def test_speed_reference_moves_the_fast_threshold():
    model = bm.BodyModel(fx.make_model(fx.bump(fx.grip_front(), fx.grip_close())))
    rig = bf.Rig(model)
    base = bf.speed_factors(rig, False)
    assert bf.speed_factors(rig, False, bf.SPEED_REF_CM) == base
    wider = bf.speed_factors(rig, False, bf.SPEED_REF_CM * 1.5)
    assert sum(k < 1.0 for k in wider) < sum(k < 1.0 for k in base)
    assert bf.speed_factors(rig, False, 1e9) is None
    assert bf.Solver(model, {**bf.normalize({"smooth_speed": "on"}), "speed_ref_cm": 1e9}).smooth_k is None
    assert bf.Solver(model, bf.normalize({"smooth_speed": "on"})).smooth_k == base


# ---- 시간 보정 계획 · 실행 ----
def test_reference_body_leaves_the_plan_alone(service, fake, slow_attack3):
    env = timed_plan(service)
    p = env["result"]
    step = step_of(p, "timing")
    assert step["inputs"]["target_peak_cm_s"] == 1200.0 and "target_peak" not in step["inputs"] and "target_peak_given" not in step["inputs"]
    assert "TARGET_STYLE_FROM_REFERENCE" not in codes(p["candidates"][0])
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED" and "target_peak" not in job["timing"]


def test_other_target_moves_the_peak_and_says_so(service, fake, slow_attack3):
    use_reference(service, fake)
    p = timed_plan(service)["result"]
    step = step_of(p, "timing")
    tp = step["inputs"]["target_peak"]
    assert tp["from"] == "body_ratio" and tp["factor"] == pytest.approx(ARM_K, abs=1e-3)
    assert step["inputs"]["target_peak_cm_s"] == tp["value"] == pytest.approx(1200.0 * ARM_K, abs=1.0)
    lim = next(lm for lm in p["candidates"][0]["expected_limitations"] if lm["code"] == "TARGET_STYLE_FROM_REFERENCE")
    assert lim["reference"] == REF and lim["values"] == ["fix.timing target_peak_cm_s"]
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert job["timing"]["target_peak"] == tp and "TARGET_STYLE_FROM_REFERENCE" in [lm["code"] for lm in job["limitations"]]


def test_faster_body_gets_the_same_rate_as_the_reference(service, fake):
    """같은 회전 → 손 속도 ∝ 팔 길이: 기준 몸 정점 600 이 ×1.5(목표 900)면, 팔이 1.25 배인 대상의 정점 750 도 ×1.5 — 정규화가 그대로면 ×1.2 다."""
    fake.assets["/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack3"]["frame_rate"] = 30.0
    from test_timing import FPS, series
    hand = series(head=12, peak=750.0 * 1.05, tail=45)
    fake.assets["/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack3"]["length"] = round(len(hand) / FPS, 4)
    fake.profiles["AS_Vesper_Sickle_Attack3"] = {"speeds": {"hand_r": hand, "hand_l": [x * 0.5 for x in hand]}}
    plain = timed_plan(service, fix={"timing": {"target_peak_cm_s": 900}})["result"]
    assert step_of(plain, "timing")["resolved"]["rate"] == pytest.approx(1.2, abs=0.01)
    use_reference(service, fake)
    moved = timed_plan(service, fix={"timing": {"max_rate": 4.0}})["result"]    # 1200 × 1.25 / 750 = 2.0
    assert step_of(moved, "timing")["resolved"]["rate"] == pytest.approx(2.0, abs=0.01)


def test_request_and_profile_win_over_the_body_ratio(service, fake, slow_attack3):
    use_reference(service, fake)
    p = timed_plan(service, fix={"timing": {"target_peak_cm_s": 900}})["result"]
    assert step_of(p, "timing")["inputs"]["target_peak"] == {"value": 900.0, "from": "request", "factor": None}
    assert "TARGET_STYLE_FROM_REFERENCE" not in codes(p["candidates"][0])
    use_reference(service, fake, {VESPER: {"timing_target_peak_cm_s": 1000}})
    p = timed_plan(service)["result"]
    assert step_of(p, "timing")["inputs"]["target_peak"] == {"value": 1000.0, "from": "profile", "factor": None}
    assert "TARGET_STYLE_FROM_REFERENCE" not in codes(p["candidates"][0])


def test_unmeasured_reference_keeps_the_value_and_warns(service, fake, slow_attack3):
    use_reference(service, fake)
    fake.bones[REF] = []
    env = timed_plan(service)
    assert step_of(env["result"], "timing")["inputs"]["target_peak"] == {"value": 1200.0, "from": "default", "factor": None}
    assert "STYLE_REFERENCE_UNMEASURED" in [d["code"] for d in env["diagnostics"]]


def test_editor_down_at_plan_moves_the_peak_at_run(service, fake, slow_attack3):
    use_reference(service, fake)
    fake.up = False
    p = timed_plan(service)["result"]
    step = step_of(p, "timing")
    assert step["inputs"]["bones"] is None and step["inputs"]["target_peak_cm_s"] == 1200.0 and "target_peak" not in step["inputs"]
    fake.up = True
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert job["timing"]["target_peak"]["from"] == "body_ratio" and job["timing"]["target_peak"]["value"] == pytest.approx(1200.0 * ARM_K, abs=1.0)


# ---- body_fit ----
def test_reference_body_has_no_speed_key(service, fake, body):
    step = step_of(plan_of(service), "body_fit")
    assert "speed_ref_cm" not in step["inputs"]
    job = run(service)
    assert job["status"] == "SUCCEEDED" and "speed_ref_cm" not in job["fix"]["body"]["smooth_speed"]


def test_other_target_moves_the_speed_reference(service, fake, body):
    use_reference(service, fake)
    step = step_of(plan_of(service), "body_fit")
    assert step["inputs"]["speed_ref_cm"] == pytest.approx(bf.SPEED_REF_CM * ARM_K, abs=0.01)
    job = run(service)
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]["smooth_speed"]
    assert rec["speed_ref_cm"] == step["inputs"]["speed_ref_cm"] and rec["factor"] == pytest.approx(ARM_K, abs=1e-3)
    # 손 속도 기준은 몸 비율이라 스타일 값이 아니다 — fix.body 만의 Job 은 한계가 없다
    assert "TARGET_STYLE_FROM_REFERENCE" not in [lm["code"] for lm in job["limitations"]]


def test_measure_mode_does_not_measure_the_reference(service, fake, body):
    use_reference(service, fake)
    p = plan_of(service, fix={"body": {"mode": "measure"}})
    assert "speed_ref_cm" not in step_of(p, "body_fit")["inputs"]
    assert not any(t == "inspect_skeleton" and q.get("skeleton") == REF for t, q in fake.calls)


# ---- 리타기터 구성 (U7-c) ----
@pytest.mark.parametrize("retarget", [{"ops": "default"}, {"existing_retargeter": RTG}], ids=["ops_default", "reuse"])
def test_leg_ops_need_the_retargeter_this_job_builds(bl, retarget):
    p = plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS, **retarget}, fix={"ops": LEG_OPS})
    assert not p["candidates"]
    ex = p["excluded"][0]
    assert ex["cause"] == "UNSUPPORTED_REQUEST" and ex["reason"] == "FIX_LEGS_NEEDS_MATCH_EXISTING"
    assert plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS})["candidates"]   # 기본 구성은 그대로
    assert plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS, **retarget}, fix={"ops": [{"op": "smooth"}]})["candidates"]   # 다리 op 가 아니면 돈다


def test_import_routes_flag_reuse_and_default_ops(bl):
    risks = lambda **rt: plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS, **rt})["candidates"][0]["risks"]  # noqa: E731
    assert "RETARGET_REUSE_SOURCE_UNCHECKED" in risks(existing_retargeter=RTG)
    assert "RETARGET_REUSE_SOURCE_UNCHECKED" in risks(existing_source_rig="/Game/Test/IK_Source")
    assert "RETARGET_OPS_DEFAULT_UNVERIFIED" in risks(ops="default")
    assert not {"RETARGET_REUSE_SOURCE_UNCHECKED", "RETARGET_OPS_DEFAULT_UNVERIFIED"} & set(risks())


def test_existing_route_is_not_flagged(service):
    env = service.plan_motion_generation(request=request(reference_animations=[KATANA], search=..., edits=..., provider="existing_motion", target_mesh=VESPER_MESH,
                                                         retarget={"ops": "default", "existing_retargeter": RTG}))
    assert env["ok"], env["error"]
    assert not {"RETARGET_REUSE_SOURCE_UNCHECKED", "RETARGET_OPS_DEFAULT_UNVERIFIED"} & set(env["result"]["candidates"][0]["risks"])


def test_stance_profile_reaches_the_convert_step(bl, fake):
    use_reference(bl.service, fake, {VESPER: {"stance_max_ratio": 2.4}})
    p = plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS})
    ops = step_of(p, "convert")["inputs"]["fix"]["ops"]
    assert next(o for o in ops if o["op"] == "stance_width")["max_ratio"] == 2.4
    assert "TARGET_STYLE_FROM_REFERENCE" not in codes(p["candidates"][0])
    p = plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS}, fix={"ops": [{"op": "foot_lock"}, {"op": "stance_width", "max_ratio": 3.5}]})
    assert next(o for o in step_of(p, "convert")["inputs"]["fix"]["ops"] if o["op"] == "stance_width")["max_ratio"] == 3.5


def test_stance_without_a_profile_is_a_reference_value(bl, fake):
    use_reference(bl.service, fake)
    p = plan(bl, provider="blender", retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS})
    assert next(o for o in step_of(p, "convert")["inputs"]["fix"]["ops"] if o["op"] == "stance_width")["max_ratio"] == 3.0
    lim = next(lm for lm in p["candidates"][0]["expected_limitations"] if lm["code"] == "TARGET_STYLE_FROM_REFERENCE")
    assert lim["values"] == ["stance_width max_ratio"]
