"""§15 테스트 D(Mock) — Provider 실패 → 다른 Provider · 경로 기록 · limitations (지침서 §7)."""
from __future__ import annotations

from anim_gen.providers.base import StepFailed
from conftest import OUT, VESPER_MESH, err, mock_ai, request

FINAL = f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"


def generate(service, **overrides):
    p = service.plan_motion_generation(request=request(**overrides))
    assert p["ok"], p["error"]
    return p["result"], service.generate_motion(plan_id=p["result"]["plan_id"])


def test_D_local_ai_failure_falls_back_to_existing_motion(make_service, fake):
    service, registry = make_service(local_ai=mock_ai(failures=[StepFailed("GENERATION_FAILED", "MOCK", "mock model crashed")]))
    plan, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert [c["provider"] for c in plan["candidates"]] == ["local_ai", "existing_motion"]
    assert env["ok"], env["error"]
    job = env["result"]
    assert job["provider"] == "existing_motion" and job["generated_assets"] == [FINAL]
    [h] = job["fallback_history"]
    assert (h["provider"], h["cause"], h["reason"], h["step"], h["skipped"]) == ("local_ai", "GENERATION_FAILED", "MOCK", "generate", False)
    lims = {lim["code"]: lim for lim in job["limitations"]}
    assert lims["FALLBACK_USED"]["from"] == "local_ai" and lims["FALLBACK_USED"]["cause"] == "GENERATION_FAILED"
    assert "새 동작 생성" in lims["FALLBACK_USED"]["missing"]
    assert "NOT_NEW_MOTION" in lims and lims["FALLBACK_USED"]["source"] == "fallback"
    assert registry.get("local_ai").submits == 1 and job["attempt"] == 2
    assert not any(t == "import_animation_file" for t, _ in fake.writes)  # 실패한 생성 뒤 단계는 돌지 않는다


def test_D_skipped_candidates_are_recorded(make_service):
    """실행 시점 정책으로 다시 검사한다 — 계획 뒤 비활성이 된 Provider 는 건너뛰고 기록한다."""
    service, registry = make_service(local_ai=mock_ai())
    p = service.plan_motion_generation(request=request(motion_category="full_body_new", target_mesh=VESPER_MESH))["result"]
    registry.get("local_ai").implemented = False
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"] and job["provider"] == "existing_motion" and job["attempt"] == 1
    [h] = job["fallback_history"]
    assert h["skipped"] and h["cause"] == "PROVIDER_UNAVAILABLE" and h["reason"] == "NOT_IMPLEMENTED"
    assert "FALLBACK_USED" in {lim["code"] for lim in job["limitations"]}


def test_guard_error_stops_without_fallback(make_service, fake):
    service, registry = make_service(local_ai=mock_ai())
    fake.fail["retarget_animations"] = [err("UNEXPECTED_DIRTY", "outside allow list", packages=["/Game/Assets/X"])]
    _, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert not env["ok"] and env["error"]["code"] == "UNEXPECTED_DIRTY"
    job = env["error"]["details"]["job"]
    assert [h["provider"] for h in job["fallback_history"]] == ["local_ai"]
    assert fake.count("apply_animation_edits") == 0  # existing_motion 후보로 넘어가지 않았다


def test_editor_gone_during_run_is_fatal(service, fake):
    p = service.plan_motion_generation(request=request())["result"]
    fake.up = False
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "PROVIDER_UNAVAILABLE" and env["error"]["details"]["reason"] == "EDITOR"


def test_retarget_failure_keeps_bones_and_falls_back(make_service, fake):
    service, _ = make_service(local_ai=mock_ai())
    p = service.plan_motion_generation(request=request(motion_category="full_body_new", target_mesh=VESPER_MESH))["result"]
    fake.fail["create_ik_rig"] = [err("IKRIG_AUTO_FAILED", "no template", bones=[{"name": "root", "parent": None}])]
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"] and job["provider"] == "existing_motion"
    [h] = job["fallback_history"]
    assert h["cause"] == "RETARGET_FAILED" and h["reason"] == "IKRIG_AUTO_FAILED" and h["step"] == "retarget"
    assert h["editor_error"]["details"]["bones"] == [{"name": "root", "parent": None}]
    assert any(a.endswith("/Import/Mock_Anim") for a in job["intermediate_assets"])  # 앞 단계 산출물은 남는다


def test_validation_failure_renames_the_next_attempt(make_service, fake):
    service, _ = make_service(local_ai=mock_ai())
    p = service.plan_motion_generation(request=request(motion_category="full_body_new", target_mesh=VESPER_MESH))["result"]
    # local_ai 경로의 최종 편집이 검증 실패 — C++ 은 그 이름의 애셋을 미저장으로 남기므로 다음 시도는 같은 이름을 쓸 수 없다
    fake.fail["apply_animation_edits"] = [err("VALIDATION_FAILED", "FAILED")]
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"] and job["provider"] == "existing_motion"
    assert job["left_assets"] == [FINAL] and job["generated_assets"] == [f"{FINAL}_Try2"]
    assert "OUTPUT_RENAMED" in {lim["code"] for lim in job["limitations"]}
    assert job["preserved_candidates"][0]["assets"] == [FINAL]


def test_rate_limited_retries_same_candidate(make_service):
    service, registry = make_service(local_ai=mock_ai(failures=[StepFailed("RATE_LIMITED", "429", "slow down", retryable=True)]))
    _, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    job = env["result"]
    assert env["ok"] and job["provider"] == "local_ai" and job["retry_count"] == 1 and job["attempt"] == 2
    assert registry.get("local_ai").submits == 2
    assert [h["cause"] for h in job["fallback_history"]] == ["RATE_LIMITED"]
    assert "FALLBACK_USED" not in {lim["code"] for lim in job["limitations"]}  # 같은 후보 재시도는 폴백이 아니다


def test_max_attempts_stops_the_job(make_service):
    service, _ = make_service(local_ai=mock_ai(failures=[StepFailed("GENERATION_FAILED", None, "boom")]))
    service.set_generation_policy(patch={"execution": {"max_generation_attempts": 1}})
    _, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert env["error"]["code"] == "GENERATION_FAILED" and env["error"]["details"]["attempts_exhausted"] is True
    assert env["error"]["details"]["job"]["attempt"] == 1


def test_fallback_disabled_by_policy(make_service, fake):
    service, _ = make_service(local_ai=mock_ai(failures=[StepFailed("GENERATION_FAILED", None, "boom")]))
    service.set_generation_policy(patch={"execution": {"allow_fallback": False}})
    _, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert env["error"]["code"] == "GENERATION_FAILED" and fake.count("apply_animation_edits") == 0


def test_explicit_provider_never_falls_back(make_service, fake):
    service, _ = make_service(local_ai=mock_ai(failures=[StepFailed("GENERATION_FAILED", None, "boom")]))
    _, env = generate(service, motion_category="full_body_new", target_mesh=VESPER_MESH, provider="local_ai")
    assert env["error"]["code"] == "GENERATION_FAILED"
    assert len(env["error"]["details"]["job"]["fallback_history"]) == 1 and not fake.writes
