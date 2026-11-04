"""Job 상태 전이 · 실행 · 재호출 · 취소 · 재시작 복원 (지침서 §3.4)."""
from __future__ import annotations

import itertools
import threading

import pytest

from anim_gen.service import Service
from anim_gen.store import STATES, TERMINAL, TRANSITIONS, InvalidTransition, Store
from conftest import AIM_IDLE, OUT, VESPER_MESH, enable_paid, mock_paid, request


def run(service, save=False, **overrides) -> tuple[dict, dict]:
    p = service.plan_motion_generation(request=request(**overrides))
    assert p["ok"], p["error"]
    return p["result"], service.generate_motion(plan_id=p["result"]["plan_id"], save=save)


def statuses(job: dict) -> list[str]:
    return [e["to"] for e in job["events"]]


@pytest.mark.parametrize("current, to", list(itertools.product(STATES, STATES)))
def test_transition_table(state_dir, current, to):
    store = Store(state_dir)
    job = store.create_job({"job_id": f"job_{current}_{to}", "plan_id": "p", "status": current})
    allowed = to in TRANSITIONS.get(current, frozenset())
    if allowed:
        assert store.transition(job["job_id"], to)["status"] == to
    else:
        with pytest.raises(InvalidTransition):
            store.transition(job["job_id"], to)
        assert store.load_job(job["job_id"])["status"] == current
    if current in TERMINAL:
        assert not allowed


def test_latest_job_is_the_last_created_even_within_one_second(state_dir):
    """같은 초에 만든 Job 도 생성 순서대로 — 'latest' 가 무작위 id 로 정해지면 retry 뒤 이전 FAILED Job 을 돌려준다."""
    store = Store(state_dir)
    ids = [f"job_same_{suffix}" for suffix in ("zz", "aa", "mm", "00", "ff")]
    for job_id in ids:
        store.create_job({"job_id": job_id, "plan_id": "p"})
    assert [j["job_id"] for j in store.list_jobs("p", limit=0)] == list(reversed(ids))
    for suffix in ("zz", "aa", "mm"):
        store.save_approval({"approval_id": f"appr_{suffix}", "plan_id": "p", "provider": "x", "created_at": "same"})
    assert [a["approval_id"] for a in store.approvals_for("p")] == ["appr_zz", "appr_aa", "appr_mm"]


def test_status_change_only_through_transition(state_dir):
    store = Store(state_dir)
    store.create_job({"job_id": "job_a", "plan_id": "p"})
    with pytest.raises(ValueError):
        store.patch_job("job_a", status="SUCCEEDED")
    with pytest.raises(ValueError):
        store.update_job("job_a", lambda j: j.update(status="FAILED"))


def test_success_path(service, fake):
    plan, env = run(service, save=True)
    assert env["ok"], env["error"]
    job = env["result"]
    assert statuses(job) == ["QUEUED", "RUNNING", "SUCCEEDED"]
    final = f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"
    assert job["generated_assets"] == [final] and job["reused_assets"] == [] and job["intermediate_assets"] == []
    assert job["provider"] == "existing_motion" and job["chain"] == ["existing_motion", "direct_key"]
    assert job["validation"]["status"] == "PASSED" and job["attempt"] == 1 and job["fallback_history"] == []
    codes = [lim["code"] for lim in job["limitations"]]
    assert "EDIT_LIMITATION" in codes  # C++ 문자열 한계를 감싼 것
    assert all(set(lim) >= {"code", "message", "source"} for lim in job["limitations"])
    [(tool, params)] = fake.writes
    assert tool == "apply_animation_edits" and params["source"] == AIM_IDLE and params["asset_path"] == final
    assert params["save"] is True and params["loop"] is True


def test_same_plan_returns_same_job(service, fake):
    plan, env = run(service)
    again = service.generate_motion(plan_id=plan["plan_id"])
    assert again["ok"] and again["result"]["job_id"] == env["result"]["job_id"]
    assert "JOB_EXISTS" in [d["code"] for d in again["diagnostics"]]
    assert len(fake.writes) == 1
    assert len(service.get_generation_status(plan_id=plan["plan_id"])["result"]["jobs"]) == 1


def test_failed_job_needs_retry_for_a_new_job(service, fake):
    fake.fail["apply_animation_edits"] = [{"code": "VALIDATION_FAILED", "message": "FAILED"}]
    plan, env = run(service)
    assert not env["ok"] and env["error"]["code"] == "VALIDATION_FAILED"
    first = env["error"]["details"]["job"]
    assert statuses(first) == ["QUEUED", "RUNNING", "FAILED"] and first["left_assets"] == [f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"]
    same = service.generate_motion(plan_id=plan["plan_id"])
    assert same["error"]["details"]["job"]["job_id"] == first["job_id"]
    retry = service.generate_motion(plan_id=plan["plan_id"], retry=True)
    assert retry["ok"] and retry["result"]["job_id"] != first["job_id"] and retry["result"]["previous_job_id"] == first["job_id"]


def test_editor_diagnostics_reach_the_job(service, fake):
    """단계 안 에디터 Tool 의 diagnostics 는 tool · step 과 함께 Job 에 남는다. 계획 시점 호출(preview)은 Job 에 넣지 않는다."""
    fake.diags["apply_animation_edits"] = [{"level": "warning", "code": "NOTIFIES_DROPPED", "message": "1 notify dropped"}]
    fake.diags["preview_animation_edits"] = [{"level": "info", "code": "PREVIEW_NOTE", "message": "plan time"}]
    _, env = run(service)
    job = env["result"]
    assert env["ok"], env["error"]
    [d] = [d for d in job["diagnostics"] if d["code"] == "NOTIFIES_DROPPED"]
    assert (d["level"], d["tool"], d["step"]) == ("warning", "apply_animation_edits", "edit")
    assert "PREVIEW_NOTE" not in {d["code"] for d in job["diagnostics"]}


def test_editor_diagnostics_kept_when_the_step_fails(service, fake):
    fake.diags["apply_animation_edits"] = [{"level": "warning", "code": "SEAM_JUMP", "message": "seam"}]
    fake.fail["apply_animation_edits"] = [{"code": "VALIDATION_FAILED", "message": "FAILED"}]
    _, env = run(service)
    job = env["error"]["details"]["job"]
    assert job["status"] == "FAILED"
    assert {"code": "SEAM_JUMP", "tool": "apply_animation_edits", "step": "edit"}.items() <= next(d for d in job["diagnostics"] if d["code"] == "SEAM_JUMP").items()


def test_collect_is_per_thread(fake):
    """다른 스레드의 Tool 호출 진단은 섞이지 않고, 모으는 중이 아니면 쌓지 않는다."""
    client = fake.client()
    fake.diags["get_editor_status"] = [{"level": "info", "code": "X", "message": "x"}]
    client.call("get_editor_status")
    with client.collect() as mine:
        other = threading.Thread(target=lambda: client.call("get_editor_status"))
        other.start()
        other.join()
        client.call("get_editor_status")
    assert mine == [{"level": "info", "code": "X", "message": "x", "tool": "get_editor_status"}]


def test_reuse_without_edits(service, fake):
    _, env = run(service, edits=..., duration_seconds=2.0)
    job = env["result"]
    assert env["ok"] and job["reused_assets"] == [AIM_IDLE] and job["generated_assets"] == []
    assert not fake.writes and fake.count("validate_animation") == 1
    codes = {lim["code"]: lim for lim in job["limitations"]}
    assert "REUSED_EXISTING" in codes
    assert codes["DURATION_MISMATCH"]["source"] == "validation"  # 계획 값이 아니라 측정값으로 다시 적힌다


def test_measured_loop_and_duration(service):
    _, env = run(service, loop=None, duration_seconds=1.3333, frame_rate=24)
    codes = {lim["code"] for lim in env["result"]["limitations"]}
    assert "FRAME_RATE_MISMATCH" in codes and "DURATION_MISMATCH" not in codes and "LOOP_MISMATCH" not in codes


def test_cancel_queued_waiting_and_terminal(service, state_dir):
    store = service.store
    store.create_job({"job_id": "job_q", "plan_id": "p"})
    env = service.cancel_generation(job_id="job_q")
    assert env["ok"] and env["result"]["status"] == "CANCELLED" and not env["result"]["result_ignored"]
    store.create_job({"job_id": "job_w", "plan_id": "p", "status": "WAITING_FOR_APPROVAL"})
    assert service.cancel_generation(job_id="job_w")["result"]["status"] == "CANCELLED"
    env = service.cancel_generation(job_id="job_w")
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "ALREADY_TERMINAL"
    assert service.cancel_generation(job_id="job_none")["error"]["code"] == "JOB_NOT_FOUND"


def test_cancel_while_async_step_in_flight(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid(polls_needed=3)})
    enable_paid(service)
    p = service.plan_motion_generation(request=request(motion_category="full_body_new", target_mesh=VESPER_MESH, generation_policy="QUALITY_FIRST"))["result"]
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"] and job["status"] == "RUNNING" and job["pending"]["handle"] == {"task": "task1"}
    paid = registry.get("external.meshy")
    assert service.get_generation_status(job_id=job["job_id"])["result"]["status"] == "RUNNING" and paid.polls == 1
    env = service.cancel_generation(job_id=job["job_id"])
    assert env["result"]["status"] == "CANCELLED" and env["result"]["result_ignored"]
    assert "RESULT_IGNORED" in [d["code"] for d in env["diagnostics"]]
    assert service.get_generation_status(job_id=job["job_id"])["result"]["status"] == "CANCELLED"
    assert paid.polls == 1 and paid.submits == 1  # 취소 뒤에는 poll 하지 않는다
    assert service.store.ledger_totals() == {"spent_usd": 0.0, "reserved_usd": 0.5}  # 이미 낸 비용은 장부에 남는다


def test_restart_resumes_async_job_from_files(make_service, fake, state_dir):
    service, registry = make_service(**{"external.meshy": mock_paid(polls_needed=2)})
    enable_paid(service)
    p = service.plan_motion_generation(request=request(motion_category="full_body_new", target_mesh=VESPER_MESH, generation_policy="QUALITY_FIRST"))["result"]
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    job_id = service.generate_motion(plan_id=p["plan_id"])["result"]["job_id"]
    paid = registry.get("external.meshy")
    # 서버 재시작: 같은 상태 폴더 · 같은 Provider 인스턴스(외부 작업은 서버 밖에 있다)로 새 Service
    restarted = Service(store=Store(state_dir), registry=registry, editor=fake.client())
    assert restarted.get_generation_status(job_id=job_id)["result"]["status"] == "RUNNING" and paid.polls == 1  # 상태 조회 한 번 = poll 한 번
    env = restarted.get_generation_status(job_id=job_id)
    assert env["ok"] and env["result"]["status"] == "SUCCEEDED", env["result"].get("error")
    job = env["result"]
    assert paid.submits == 1 and paid.polls == 2
    assert [s for s in statuses(job)] == ["QUEUED", "RUNNING", "SUCCEEDED"]
    assert job["generated_assets"] == [f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"]
    assert any(a.endswith("/IK_Source") for a in job["intermediate_assets"]) and job["cost"]["actual_usd"] == 0.5
    assert restarted.store.ledger_totals() == {"spent_usd": 0.5, "reserved_usd": 0.0}


def test_plan_without_editor_resolves_at_run(service, fake):
    fake.up = False
    p = service.plan_motion_generation(request=request(target_mesh=VESPER_MESH))["result"]
    fake.up = True
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"], env["error"]
    assert job["generated_assets"] == [f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"]
    assert fake.count("retarget_animations") == 0 and fake.count("create_ik_rig") == 0  # 소스가 대상 스켈레톤 → 조건부 리타깃 건너뜀
    assert [t for t, _ in fake.writes] == ["apply_animation_edits"]


def test_status_lists_recent_jobs(service):
    run(service)
    env = service.get_generation_status()
    assert env["ok"] and len(env["result"]["jobs"]) == 1 and env["result"]["jobs"][0]["status"] == "SUCCEEDED"
    assert service.get_generation_status(job_id="job_nope")["error"]["code"] == "JOB_NOT_FOUND"
    assert service.generate_motion(plan_id="plan_nope")["error"]["code"] == "PLAN_NOT_FOUND"
