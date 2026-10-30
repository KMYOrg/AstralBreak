"""Phase 8-4b — body_fit 파이프: 요청 fix.body · 계획(단계 위치 · 목표 풀어 보임 · 리타깃 관통 measure 전환) · 실행(새 애셋 · bone_deltas ·
C++ 재측정 · Job fix.body · 한계).

FakeEditor 를 이 파일 안에서만 감싼다: validate_animation body_clearance{parts all · model} 이면 합성 C++ 모델(body_fit_fixture — 애셋 키 수와 같은
프레임)과 그 모델로 잰 쌍(body_fit.measure = 같은 지도 규칙)을 돌려주고, apply_animation_edits bone_deltas 는 그 델타를 적용한 모델을 새 애셋에 단다."""
from __future__ import annotations

import pytest

import body_fit_fixture as fx
from anim_gen import body_model as bm
from anim_gen.editor import package_path
from conftest import HERO, KATANA, OUT, VESPER, VESPER_MESH, request
from test_blender import bl, plan as bl_plan  # noqa: F401 — bl 는 픽스처
from test_pose_from import INFO

ASSET = f"{HERO}/Sickle/Actions/AS_Vesper_Sickle_GripTest"
FRAMES = fx.bump(fx.grip_front(), fx.grip_close())   # 30 프레임 — 파지 · 두 아래팔 관통


@pytest.fixture
def body(fake, monkeypatch):
    fake.assets[ASSET] = {"class": "AnimSequence", "skeleton": VESPER, "length": round(29 / 30, 4), "frame_rate": 30.0, "loop": False, "root_motion": False}
    models = {ASSET: fx.make_model(FRAMES)}
    validate, apply = fake._validate_animation, fake._apply_animation_edits

    def fake_validate(p):
        out = validate(p)
        spec = p.get("body_clearance") if isinstance(p.get("body_clearance"), dict) else {}
        for item in out["assets"]:
            model = models.get(package_path(item["asset"]))
            if model is not None and spec.get("parts") == "all":
                bc = item["body_clearance"]
                bc["parts"] = fx.pairs_cpp(model)
                bc.pop("per_frame", None)
                if spec.get("model"):
                    bc["model"] = model
                else:
                    bc.pop("model", None)
        return out

    def fake_apply(p):
        out = apply(p)
        src = models.get(package_path(p["source"]))
        if src is not None:
            op = next((o for o in p["operations"] if o["op"] == "bone_deltas"), None)
            model = bm.BodyModel(src)
            poses = [model.apply_deltas(f, {b["bone"]: (b["rotation_deg"][f] if b["rotation_deg"] else None,
                                                        b["translation_cm"][f] if b["translation_cm"] else None) for b in op["bones"]})
                     if op else model.poses[f] for f in range(len(model.frames))]
            models[package_path(out["asset_path"])] = fx.make_model(poses=poses)
        return out
    monkeypatch.setattr(fake, "_validate_animation", fake_validate)
    monkeypatch.setattr(fake, "_apply_animation_edits", fake_apply)
    return models


def body_request(**overrides) -> dict:
    base = {"reference_animations": [ASSET], "search": ..., "edits": ..., "target_mesh": VESPER_MESH, "provider": "existing_motion",
            "motion_category": "weapon_action", "family": "Sickle", "animation_name": "AS_Vesper_Sickle_GripTest_Fit", "loop": False,
            "fix": {"body": True}}
    base.update(overrides)
    return request(**base)


def plan_of(service, **overrides) -> dict:
    env = service.plan_motion_generation(request=body_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


def run(service, **overrides) -> dict:
    p = plan_of(service, **overrides)
    assert p["candidates"], p["excluded"]
    return service.generate_motion(plan_id=p["plan_id"], save=False)["result"]


# ---- 요청 ----
def test_request_fix_body_defaults_and_errors(service, body):
    p = plan_of(service)
    cfg = p["request"]["fix"]["body"]
    assert cfg["mode"] == "auto" and cfg["clearance"]["hands"] and cfg["grip"]["lead_hand"] == "right" and cfg["targets"] == []
    env = service.plan_motion_generation(request=body_request(fix={"body": {"speed": 1}}))
    assert not env["ok"] and env["error"]["details"]["field"] == "fix.body.speed" and env["error"]["details"]["reason"] == "UNKNOWN_FIELD"
    env = service.plan_motion_generation(request=body_request(fix={"body": {"targets": [{"id": "a", "effector": "hand_r", "at": {"time": 0.1}}]}}))
    assert not env["ok"] and env["error"]["details"]["field"] == "fix.body.targets[0]"


# ---- 계획 ----
def test_existing_asset_plan_previews_the_body_and_the_targets(service, fake, body):
    tg = {"id": "fwd", "note": "오른손을 앞으로", "effector": "hand_r", "at": {"window": [0.4, 0.5]}, "position": {"offset_cm": [10, 0, 0]}, "ease_s": 0.1}
    p = plan_of(service, fix={"body": {"targets": [tg]}})
    cand = p["candidates"][0]
    assert [s["step"] for s in cand["steps"]] == ["resolve_source", "body_fit", "validate"] and cand["chain"] == ["existing_motion", "body_fit"]
    step = cand["steps"][1]
    assert step["provider"] == "body_fit" and step["inputs"]["produces"] and step["inputs"]["bones"]["hand_r"] == "hand_r"
    resolved = step["resolved"]
    assert resolved["source"] == ASSET and resolved["before"]["target_pen_pct_max"] > 0
    t = resolved["targets"][0]
    assert t["bone"] == "hand_r" and t["frames"] == [12, 15] and t["window_s"] == [0.4, 0.5] and t["position"]["to_cm"][1] > t["position"]["from_cm"][1]
    assert "BODY_FIT_RESOLVED_AT_RUN" in cand["risks"] and "TARGETS_RESOLVED_AT_RUN" not in cand["risks"]
    codes = [lm["code"] for lm in cand["expected_limitations"]]
    assert "BODY_FIT_APPROXIMATE" in codes and "REUSED_EXISTING" not in codes
    spec = [p_["body_clearance"] for t_, p_ in fake.calls if t_ == "validate_animation" and isinstance(p_.get("body_clearance"), dict)][-1]
    assert spec["parts"] == "all" and spec["hands"] and spec["model"] and spec["include_secondary"] and not fake.writes


def test_body_fit_comes_after_timing_and_before_edits(service, body):
    tg = {"id": "fwd", "effector": "hand_r", "at": {"time": 0.4}, "position": {"offset_cm": [5, 0, 0]}}
    p = plan_of(service, fix={"timing": True, "body": {"targets": [tg]}}, edits={"operations": [{"op": "mirror"}]})
    cand = p["candidates"][0]
    assert [s["step"] for s in cand["steps"]] == ["resolve_source", "timing", "body_fit", "edit", "validate"]
    assert cand["steps"][2]["resolved"] is None and "TARGETS_RESOLVED_AT_RUN" in cand["risks"] and cand["steps"][3]["preview"] is None


def test_generated_route_measures_at_retarget_and_fits_after_timing(bl):
    p = bl_plan(bl, fix={"timing": True, "body": True})
    cand = p["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    assert steps.index("body_fit") == steps.index("timing") + 1 == steps.index("retarget") + 2 and steps[-1] == "validate"
    retarget = next(s for s in cand["steps"] if s["step"] == "retarget")
    assert retarget["inputs"]["body_clearance"] == "measure" and retarget["inputs"]["body_clearance_from"] == "body_fit"
    assert "CLEARANCE_BY_BODY_FIT" in [lm["code"] for lm in cand["expected_limitations"]] and "BODY_FIT_RESOLVED_AT_RUN" in cand["risks"]
    p = bl_plan(bl, fix={"body": True}, retarget={"body_clearance": "resolve"})
    assert "CLEARANCE_DOUBLE_FIX" in p["candidates"][0]["risks"]


def test_without_target_mesh_the_candidate_is_blocked(service, body):
    p = plan_of(service, target_mesh=None)
    assert not p["candidates"] and p["excluded"][0]["reason"] == "BODY_FIT_NO_MESH"


def test_unknown_effector_and_missing_event_block_at_plan(service, body):
    p = plan_of(service, fix={"body": {"targets": [{"id": "x", "effector": "tail_01", "at": {"time": 0.2}, "position": {"offset_cm": [0, 0, 1]}}]}})
    assert not p["candidates"] and p["excluded"][0]["cause"] == "BAD_REQUEST" and p["excluded"][0]["reason"] == "UNKNOWN_EFFECTOR"
    p = plan_of(service, fix={"body": {"targets": [{"id": "x", "effector": "hand_r", "at": {"event": "swing_end"}, "position": {"offset_cm": [0, 0, 1]}}]}})
    assert not p["candidates"] and p["excluded"][0]["reason"] == "EVENT_NOT_FOUND"   # 합성 프로필에는 휘두름이 없다


# ---- 실행 ----
def test_body_fit_job_writes_a_new_asset_and_records_before_predicted_after(service, fake, body):
    job = run(service)
    assert job["status"] == "SUCCEEDED", job.get("error")
    final = f"{OUT}/AS_Vesper_Sickle_GripTest_Fit"
    assert job["generated_assets"] == [final] and not job["reused_assets"]
    applied = [p for t, p in fake.calls if t == "apply_animation_edits"]
    assert len(applied) == 1 and applied[0]["source"] == ASSET and applied[0]["operations"][0]["op"] == "bone_deltas"
    bones = applied[0]["operations"][0]["bones"]
    assert {b["bone"] for b in bones} >= {"upperarm_l", "upperarm_r"} and all(len(b["rotation_deg"]) == 30 for b in bones if b["rotation_deg"])
    rec = job["fix"]["body"]
    assert rec["source"] == ASSET and rec["asset"] == final and rec["before"]["target_pen_pct_max"] > 0
    # 맞닿음(≤ contact_cm 0.95)까지는 정상(allow_contact 기본) — + 잔차 허용 · 매끈화 0.2 cm
    assert rec["after"]["target_depth_max"] <= 1.15 and rec["predicted_vs_after"]["ok"] and rec["grip"]["frames"] == 30
    assert rec["loop"] == {"source": False, "seam_deg": rec["loop"]["seam_deg"], "boundary_max_deg": [None, None]}
    assert rec["grip"]["keep"]["pos_cm_max"] <= 1.0 and rec["deltas"]["frames_changed"] > 0 and rec["seconds"]["solve"] >= 0
    codes = [lm["code"] for lm in job["limitations"]]
    assert "BODY_FIT_APPROXIMATE" in codes and "BODY_PENETRATION_REMAINS" not in codes and "REUSED_EXISTING" not in codes
    assert package_path(ASSET) in fake.assets   # 원본은 그대로


def test_loop_source_is_fitted_as_a_cycle(service, fake, body):
    # 루프 여부는 원본 측정의 numeric.loop(C++ bLoop) 한 원천 — 요청 loop(None)가 아니다. 이음매를 걸친 관통 → 첫 · 끝 델타가 같다
    fake.assets[ASSET]["loop"] = True
    n = 30
    body[ASSET] = fx.make_model([fx.blend({}, fx.into_body(18.0), max(0.0, 1.0 - min((f - 27) % 29, (27 - f) % 29) / 5.0)) for f in range(n)])
    job = run(service, loop=None)
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]
    assert rec["loop"]["source"] and rec["loop"]["seam_deg"] == 0.0 and rec["after"]["target_depth_max"] <= 1.15
    bones = [p for t, p in fake.calls if t == "apply_animation_edits"][0]["operations"][0]["bones"]
    assert all(b["rotation_deg"][0] == b["rotation_deg"][-1] for b in bones if b["rotation_deg"])


def test_measure_mode_only_measures(service, fake, body):
    p = plan_of(service, fix={"body": {"mode": "measure"}})
    cand = p["candidates"][0]
    assert [s["step"] for s in cand["steps"]] == ["resolve_source", "body_fit", "validate"] and "BODY_FIT_RESOLVED_AT_RUN" not in cand["risks"]
    assert "REUSED_EXISTING" in [lm["code"] for lm in cand["expected_limitations"]]
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED" and job["reused_assets"] == [ASSET] and not job["generated_assets"]
    assert job["fix"]["body"]["mode"] == "measure" and job["fix"]["body"]["before"]["target_pen_pct_max"] > 0
    assert not [t for t, _ in fake.calls if t == "apply_animation_edits"]


def test_blocked_target_is_reported_with_its_blocker(service, body):
    body[ASSET] = fx.make_model([{} for _ in range(30)])
    tg = {"id": "in", "note": "오른손을 몸 쪽으로", "effector": "hand_r", "at": {"window": [0.3, 0.4]}, "position": {"offset_cm": [5, 15, 0]}, "ease_s": 0.1}
    job = run(service, fix={"body": {"targets": [tg]}})
    assert job["status"] == "SUCCEEDED", job.get("error")
    lim = next(lm for lm in job["limitations"] if lm["code"] == "TARGET_NOT_REACHED")
    assert lim["id"] == "in" and "clearance" in lim["blocked_by"]
    rec = job["fix"]["body"]
    assert rec["targets"][0]["note"] == "오른손을 몸 쪽으로" and not rec["targets"][0]["reached"] and rec["after"]["target_depth_max"] <= 1.15


def test_nothing_to_fix_still_makes_the_final_asset(service, fake, body):
    body[ASSET] = fx.make_model([{} for _ in range(30)])
    job = run(service)
    assert job["status"] == "SUCCEEDED" and job["generated_assets"] == [f"{OUT}/AS_Vesper_Sickle_GripTest_Fit"]
    assert [p for t, p in fake.calls if t == "apply_animation_edits"][0]["operations"] == [{"op": "trim"}]
    assert "BODY_FIT_NOT_APPLIED" in [lm["code"] for lm in job["limitations"]]


def test_plan_reads_the_finger_roots_for_the_off_wrist_bend_cap(service, fake, body):
    # 8-4c 후속 — 무기 없는 Job 도 대상 메시 손가락 체인 제안({Side}Middle 시작 — 이름 추측 없음)을 계획에서 받아 파지 프레임 보조 손목 상한에 쓴다
    chains = [{"name": n, "start": s, "end": s} for n, s in (("LeftMiddle", "middle_01_l"), ("RightMiddle", "middle_01_r"))]
    fake.mesh_inspect[VESPER_MESH] = {"finger_chain_suggestion": {"chains": chains}}
    p = plan_of(service)
    step = next(s for s in p["candidates"][0]["steps"] if s["step"] == "body_fit")
    assert step["inputs"]["fingers"] == {"l": "middle_01_l", "r": "middle_01_r"}
    assert any(q.get("skeletal_mesh") == VESPER_MESH and q.get("suggest_finger_chains") for t, q in fake.calls if t == "inspect_skeleton")
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    wb = job["fix"]["body"]["grip"]["wrist_bend"]
    assert wb["on"] and wb["middle"] == "middle_01_l" and wb["frames"] == 30 and wb["over_cap_frames"] == 0
    assert wb["increase_deg_max"] <= wb["tol_deg"] + 1.0 and "GRIP_WRIST_BEND_OFF" not in [d["code"] for d in job["diagnostics"]]
    # 체인이 없으면 그 제약을 끈다(경고 진단 · 기록)
    fake.mesh_inspect[VESPER_MESH] = {"finger_chain_suggestion": {"chains": []}}
    job = run(service, animation_name="AS_Vesper_Sickle_GripTest_FitNoFingers")
    rec = job["fix"]["body"]
    assert job["status"] == "SUCCEEDED" and rec["grip"]["fingers"] == {} and rec["grip"]["wrist_bend"]["on"] is False
    assert "GRIP_WRIST_BEND_OFF" in [d["code"] for d in job["diagnostics"]]


# ---- 무기(8-4c) ----
WEAPON_MESH = "/Game/Equipment/Weapon/Mesh/SKM_Test_Sickle"


def weapon_setup(fake, runtime_ik: bool = False) -> dict:
    """대상 메시(부착 소켓 · 손가락 체인) · 무기 메시(소켓 · 기하) inspect 흉내 + 요청 weapon — 손잡이 = 0 번 프레임 왼 손바닥 점에서 3 cm 옆 ±6 cm,
    회전 = 0 번 프레임 왼손의 무기 공간 회전(무기 = hand_r 항등 부착)."""
    model = bm.BodyModel(fx.make_model(FRAMES))
    p0 = model.poses[0]
    hr, hl, ml = (model.index[b] for b in ("hand_r", "hand_l", "middle_01_l"))
    palm = bm.qrot(bm.qconj(p0[hr][0]), bm._sub(bm._scale(bm._add(p0[hl][1], p0[ml][1]), 0.5), p0[hr][1]))
    rot = bm.qmul(bm.qconj(p0[hr][0]), p0[hl][0])
    fake.mesh_inspect[VESPER_MESH] = {"sockets": [{"name": "WeaponHandR", "bone": "hand_r", "owner": "skeleton", "location": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]}],
                                      "finger_chain_suggestion": {"chains": [{"name": "LeftMiddle", "start": "middle_01_l", "end": "middle_01_l"}]}}
    fake.mesh_inspect[WEAPON_MESH] = {"sockets": [{"name": "TraceEnd", "bone": "Root", "owner": "mesh", "location": [0.0, 0.0, -40.0], "rotation": [0.0, 0.0, 0.0]},
                                                  {"name": "LeftHandIK", "bone": "Root", "owner": "mesh", "location": list(palm), "rotation": [0.0, 0.0, 0.0]}],
                                      "bones": [{"name": "Root", "ref_component": {"t": [0.0, 0.0, 0.0], "r": [0.0, 0.0, 0.0]}}]}
    a, b = bm._add(palm, (-6.0, 3.0, 0.0)), bm._add(palm, (6.0, 3.0, 0.0))
    grip = {"hand": "left", "socket": "LeftHandIK", "runtime_ik": True} if runtime_ik else \
        {"hand": "left", "segment": {"from": list(a), "to": list(b)}, "rotation": list(rot)}
    return {"mesh": WEAPON_MESH, "attach": {"socket": "WeaponHandR"}, "grips": [grip], "tip": {"socket": "TraceEnd"}}


def test_weapon_plan_resolves_the_mesh_facts_and_the_capture_attaches_it(service, fake, body, tmp_path):
    fake.capture_roots = [tmp_path.as_posix()]
    weapon = weapon_setup(fake)
    p = plan_of(service, weapon=weapon, review={"capture": True}, fix={"body": {"grip": {"mode": "weapon"}}})
    cand = p["candidates"][0]
    step = next(s for s in cand["steps"] if s["step"] == "body_fit")
    res = step["inputs"]["weapon_resolved"]
    assert step["inputs"]["grip_mode"] == "weapon" and res["bone"] == "hand_r" and res["hand"]["middle"] == "middle_01_l" and res["tip"] == [0.0, 0.0, -40.0]
    assert res["grip"]["form"] == "segment" and "WEAPON_RESOLVED_AT_RUN" not in cand["risks"]
    cap = next(s for s in cand["steps"] if s["step"] == "capture")
    assert cap["inputs"]["attachments"] == [{"mesh": WEAPON_MESH, "socket": "WeaponHandR", "offset": {"location": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0],
                                                                                                      "scale": [1.0, 1.0, 1.0]}}]
    calls = [q for t, q in fake.calls if t == "inspect_skeleton" and q.get("skeletal_mesh")]
    assert {q["skeletal_mesh"] for q in calls} == {VESPER_MESH, WEAPON_MESH} and any(q.get("suggest_finger_chains") for q in calls) and not fake.writes


def test_weapon_job_grips_the_handle_and_records_the_weapon(service, fake, body):
    job = run(service, weapon=weapon_setup(fake), fix={"body": {"grip": {"mode": "weapon"}}})
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]
    grip = rec["grip"]["weapon"]
    assert rec["grip"]["mode"] == "weapon" and rec["grip"]["keep"]["frames"] == 0 and grip["before"]["dist_cm_max"] >= 2.5
    # 회전은 허용각 10° 를 조금 넘을 수 있다 — 합성 손은 곧아 손목 굽힘 상한 = 0°, 손 · 아래팔이 배를 뚫는 동작이라 관통이 앞선다(기준 1 축 15°)
    assert grip["after"]["dist_cm_p95"] <= 1.0 and grip["after"]["dist_cm_max"] <= 2.0 and grip["after"]["axis_deg_p95"] <= 15.0
    assert rec["weapon"]["mesh"] == WEAPON_MESH and rec["weapon"]["tip_from"] == "socket TraceEnd" and rec["weapon_body"] == {"before": None, "after": None}   # 기하 없음 → 기록 없음
    codes = [lm["code"] for lm in job["limitations"]]
    assert "GRIP_NOT_REACHED" not in codes and "GRIP_RELAXED" not in codes and "GRIP_RUNTIME_IK" not in codes


def test_runtime_ik_weapon_keeps_the_relation_with_a_limitation(service, fake, body):
    p = plan_of(service, weapon=weapon_setup(fake, runtime_ik=True))
    cand = p["candidates"][0]
    assert next(s for s in cand["steps"] if s["step"] == "body_fit")["inputs"]["grip_mode"] == "keep"
    assert "GRIP_RUNTIME_IK" in [lm["code"] for lm in cand["expected_limitations"]]
    job = service.generate_motion(plan_id=p["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED" and job["fix"]["body"]["grip"]["mode"] == "keep" and job["fix"]["body"]["grip"]["keep"]["frames"] == 30
    assert "GRIP_RUNTIME_IK" in [lm["code"] for lm in job["limitations"]]


def test_weapon_errors_block_the_plan(service, fake, body):
    weapon = weapon_setup(fake)
    p = plan_of(service, weapon={**weapon, "attach": {"socket": "Nope"}})
    assert not p["candidates"] and p["excluded"][0]["cause"] == "UNSUPPORTED_REQUEST" and p["excluded"][0]["reason"] == "WEAPON_ATTACH_UNKNOWN"
    tip = {"id": "tip", "effector": "weapon_tip", "at": {"time": 0.3}, "position": {"offset_cm": [5, 0, 0]}}
    p = plan_of(service, weapon={**weapon, "tip": None}, fix={"body": {"targets": [tip]}})
    assert not p["candidates"] and p["excluded"][0]["cause"] == "BAD_REQUEST" and p["excluded"][0]["reason"] == "WEAPON_TIP_UNKNOWN"
    p = plan_of(service, fix={"body": {"grip": {"mode": "weapon"}}})
    assert not p["candidates"] and p["excluded"][0]["reason"] == "WEAPON_GRIP_UNKNOWN"
    env = service.plan_motion_generation(request=body_request(weapon=weapon, fix={"body": {"grip": {"lead_hand": "left"}}}))
    assert not env["ok"] and env["error"]["details"]["reason"] == "CONFLICTING_FIELDS"


def test_far_weapon_grip_falls_back_to_keep_with_a_limitation(service, fake, body):
    weapon = weapon_setup(fake)
    g = weapon["grips"][0]
    weapon["grips"] = [{**g, "segment": {"from": bm._add(g["segment"]["from"], (0.0, 40.0, 0.0)), "to": bm._add(g["segment"]["to"], (0.0, 40.0, 0.0))}}]
    weapon["grips"][0]["segment"] = {k: list(v) for k, v in weapon["grips"][0]["segment"].items()}
    job = run(service, weapon=weapon, fix={"body": {"grip": {"mode": "weapon"}}})
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]
    assert rec["grip"]["mode"] == "weapon" and rec["grip"]["weapon_frames"] == 0 and rec["grip"]["band_far_frames"] == 30 and rec["grip"]["keep"]["frames"] == 30
    lim = next(lm for lm in job["limitations"] if lm["code"] == "GRIP_NOT_APPLICABLE")
    assert lim["reason"] == "OFF_HAND_FAR" and lim["frames"] == 30 and lim["dist_cm"]["p50"] >= 30.0


def test_weapon_without_opt_in_keeps_and_only_records(service, fake, body):
    # auto 는 무기가 있어도 keep — 풀이는 무기 없는 Job 과 같고 손잡이 관계 · 무기 끝만 기록(GRIP_NOT_APPLICABLE OPT_IN). 두 Job 은 같은 대상 메시
    # 사실(손가락 체인 — 보조 손목 굽힘 상한)을 본다
    weapon = weapon_setup(fake)
    plain = run(service)
    job = run(service, weapon=weapon, animation_name="AS_Vesper_Sickle_GripTest_FitW")
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]
    assert rec["grip"]["mode"] == "keep" and rec["grip"]["weapon"]["after"]["active"] is False and rec["grip"]["weapon"]["after"]["frames"] == 0
    assert rec["grip"]["weapon"]["before"]["all_frames"]["dist_cm_p50"] >= 2.5
    ops = [p_["operations"] for t, p_ in fake.calls if t == "apply_animation_edits"]
    assert ops[0] == ops[1]   # 같은 bone_deltas
    lim = next(lm for lm in job["limitations"] if lm["code"] == "GRIP_NOT_APPLICABLE")
    assert lim["reason"] == "OPT_IN" and plain["fix"]["body"]["grip"]["mode"] == "auto"


# ---- 8-4c c2 — 샘플 전이(pose_from) ----
SAMPLE_ASSET = f"{HERO}/Sickle/Actions/AS_Vesper_Sickle_SampleTest"


@pytest.fixture
def samples(fake, body, monkeypatch):
    """같은 스켈레톤 샘플(왼 손가락을 굽힌 같은 파지 자세) · 대상 메시 inspect(템플릿 체인 · 손 트리) · validate 의 스켈레톤 검사(플러그인처럼
    다른 스켈레톤이면 structural SKELETON_MISMATCH · skeleton 필드)."""
    fake.assets[SAMPLE_ASSET] = {"class": "AnimSequence", "skeleton": VESPER, "length": round(29 / 30, 4), "frame_rate": 30.0, "loop": False, "root_motion": False}
    body[SAMPLE_ASSET] = fx.make_model([fx.grip_front({"middle_01_l": (0.0, 40.0, 0.0)}) for _ in range(30)])
    fake.mesh_inspect[VESPER_MESH] = INFO
    validate = fake._validate_animation

    def with_skeleton(p):
        out = validate(p)
        for item in out["assets"]:
            skel = fake._source(item["asset"])["skeleton"]
            item["skeleton"] = skel
            if p.get("skeleton") and package_path(p["skeleton"]) != skel:
                item.setdefault("structural", []).append({"level": "error", "code": "SKELETON_MISMATCH"})
            if p.get("fingers"):
                item["fingers"] = {"issues": []}
        return out
    monkeypatch.setattr(fake, "_validate_animation", with_skeleton)
    return body


def pf(**kw) -> dict:
    base = {"id": "s1", "note": "왼손을 쥔 모양으로", "asset": SAMPLE_ASSET, "bones": "fingers_l", "mode": "pose", "source": {"time": 0.5},
            "target": {"window": [0.0, 0.9]}, "weight": 1.0}
    base.update(kw)
    return base


def test_pose_from_plan_resolves_the_bundle_and_previews_the_sample(service, fake, samples):
    p = plan_of(service, fix={"body": {"pose_from": [pf()]}})
    cand = p["candidates"][0]
    step = cand["steps"][1]
    item = step["inputs"]["pose_from"][0]
    assert item["resolved_bones"] == ["middle_01_l"] and item["resolved_presets"] == {"fingers_l": ["middle_01_l"]}
    prev = step["resolved"]["pose_from"][0]
    assert prev["frames"] == [0, 27] and prev["source_s"] == [0.5, 0.5] and prev["alignment"][0]["error_frames"] <= 1.0 and prev["bones"] == ["middle_01_l"]
    assert "POSE_FROM_RESOLVED_AT_RUN" not in cand["risks"] and not fake.writes
    sample_calls = [p_ for t, p_ in fake.calls if t == "validate_animation" and p_["assets"] == [SAMPLE_ASSET]]
    assert sample_calls and all(package_path(c["skeleton"]) == VESPER and not c.get("body_clearance") for c in sample_calls)


def test_pose_from_sample_on_another_skeleton_blocks_the_plan(service, fake, samples):
    p = plan_of(service, fix={"body": {"pose_from": [pf(asset=KATANA)]}})
    ex = p["excluded"][0]
    assert not p["candidates"] and ex["reason"] == "SAMPLE_SKELETON_MISMATCH" and ex["cause"] == "UNSUPPORTED_REQUEST"


def test_pose_from_unknown_bone_and_missing_event_block_the_plan(service, fake, samples):
    p = plan_of(service, fix={"body": {"pose_from": [pf(bones=["tail_01"])]}})
    assert not p["candidates"] and p["excluded"][0]["reason"] == "UNKNOWN_BONE" and p["excluded"][0]["cause"] == "BAD_REQUEST"
    p = plan_of(service, fix={"body": {"pose_from": [pf(target={"event": "still_start"})]}})
    assert not p["candidates"] and p["excluded"][0]["reason"] in ("EVENT_NOT_FOUND", "TARGET_OUT_OF_RANGE")


def test_pose_from_job_copies_the_fingers_and_records_the_transfer(service, fake, samples):
    job = run(service, fix={"body": {"pose_from": [pf()]}}, animation_name="AS_Vesper_Sickle_GripTest_FitS1")
    assert job["status"] == "SUCCEEDED", job.get("error")
    rec = job["fix"]["body"]
    r = rec["pose_from"][0]
    assert r["id"] == "s1" and r["bones"] == ["middle_01_l"] and r["frames"] == [0, 27] and r["achieved"]["deg_max"] < 1e-3 and r["partial"] == []
    assert r["fingers"]["bones"] == 1 and rec["fingers"]["warnings"] == {"before": [], "after": []} and rec["seconds"]["samples"] >= 0.0
    op = next(p_ for t, p_ in fake.calls if t == "apply_animation_edits")["operations"][0]
    finger = next(b for b in op["bones"] if b["bone"] == "middle_01_l")
    assert all(abs(finger["rotation_deg"][f][1] - 40.0) < 1e-3 for f in range(0, 28))
    finger_calls = [p_ for t, p_ in fake.calls if t == "validate_animation" and p_.get("fingers")]
    assert len(finger_calls) == 2 and all(c["fingers"] == {"mesh": VESPER_MESH} for c in finger_calls)
    sample_model_calls = [p_ for t, p_ in fake.calls if t == "validate_animation" and p_["assets"] == [SAMPLE_ASSET] and (p_.get("body_clearance") or {}).get("model")]
    assert len(sample_model_calls) == 1 and not any(lm["code"] == "POSE_FROM_PARTIAL" for lm in job["limitations"])


def test_pose_from_blocked_bones_are_a_limitation(service, fake, samples):
    # 샘플 왼팔이 오른손과 떨어진 자세 — 파지 keep 이 이겨 막힌 본을 POSE_FROM_PARTIAL 로
    samples[SAMPLE_ASSET] = fx.make_model([fx.grip_front({"upperarm_l": (60.0, 0.0, 0.0)}) for _ in range(30)])
    job = run(service, fix={"body": {"pose_from": [pf(bones="arm_l", target={"window": [0.3, 0.6]})]}}, animation_name="AS_Vesper_Sickle_GripTest_FitS3")
    assert job["status"] == "SUCCEEDED", job.get("error")
    lim = next(lm for lm in job["limitations"] if lm["code"] == "POSE_FROM_PARTIAL")
    assert lim["id"] == "s1" and "grip" in lim["blocked_by"] and lim["bones"]
