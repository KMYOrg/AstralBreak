"""Phase 8-4b — body_fit 파이프: 요청 fix.body · 계획(단계 위치 · 목표 풀어 보임 · 리타깃 관통 measure 전환) · 실행(새 애셋 · bone_deltas ·
C++ 재측정 · Job fix.body · 한계).

FakeEditor 를 이 파일 안에서만 감싼다: validate_animation body_clearance{parts all · model} 이면 합성 C++ 모델(body_fit_fixture — 애셋 키 수와 같은
프레임)과 그 모델로 잰 쌍(body_fit.measure = 같은 지도 규칙)을 돌려주고, apply_animation_edits bone_deltas 는 그 델타를 적용한 모델을 새 애셋에 단다."""
from __future__ import annotations

import pytest

import body_fit_fixture as fx
from anim_gen import body_model as bm
from anim_gen.editor import package_path
from conftest import HERO, OUT, VESPER, VESPER_MESH, request
from test_blender import bl, plan as bl_plan  # noqa: F401 — bl 는 픽스처

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
