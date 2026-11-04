"""§15 테스트 E(Mock) — 비용 통제: FREE_ONLY · 승인 · 상한 · 비용 미확인 · 멱등 키 · 외부 호출 0 (지침서 §6)."""
from __future__ import annotations

import json

import pytest

from anim_gen.providers.base import StepFailed
from anim_gen.store import ledger_key
from conftest import VESPER_MESH, enable_paid, mock_paid, request


def plan_paid(service, **overrides) -> dict:
    """유료 Mock 이 1순위인 계획 (full_body_new + QUALITY_FIRST)."""
    req = request(motion_category="full_body_new", target_mesh=VESPER_MESH, generation_policy="QUALITY_FIRST")
    req.update(overrides)
    env = service.plan_motion_generation(request=req)
    assert env["ok"], env["error"]
    return env["result"]


def reason(env) -> str | None:
    return ((env.get("error") or {}).get("details") or {}).get("reason")


def test_E_free_only_blocks_paid_with_zero_external_calls(make_service, fake):
    service, registry = make_service(**{"external.meshy": mock_paid()})
    enable_paid(service)
    service.set_generation_policy(patch={"mode": "FREE_ONLY"})
    p = plan_paid(service, provider="external.meshy")
    assert not p["executable"] and p["excluded"][0]["cause"] == "APPROVAL_REQUIRED" and p["excluded"][0]["reason"] == "POLICY_FREE_ONLY"
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "APPROVAL_REQUIRED" and reason(env) == "POLICY_FREE_ONLY"
    env = service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    assert env["error"]["code"] == "BAD_REQUEST" and reason(env) == "POLICY_FREE_ONLY"
    assert registry.get("external.meshy").external_calls == 0
    assert not fake.writes and service.store.ledger_entries() == []


def test_E_paid_disabled_by_default(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid()})
    p = plan_paid(service)
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["external.meshy"] == "PAID_API_DISABLED"
    assert p["candidates"][0]["provider"] == "existing_motion"  # 무료 근사만 남는다
    est = service.estimate_generation_cost(plan_id=p["plan_id"])["result"]
    assert {c["provider"]: c["verdict"] for c in est["candidates"]} == {"existing_motion": "free", "external.meshy": "blocked"}
    assert registry.get("external.meshy").external_calls == 0


def test_E_no_approval_waits_and_calls_nothing(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid()})
    enable_paid(service)
    p = plan_paid(service)
    assert p["candidates"][0]["provider"] == "external.meshy" and p["candidates"][0]["needs_approval"]
    est = service.estimate_generation_cost(plan_id=p["plan_id"])["result"]
    assert est["candidates"][0]["verdict"] == "needs_approval" and est["caps"]["remaining_usd"] == 5.0
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "APPROVAL_REQUIRED" and reason(env) == "NO_APPROVAL"
    job = env["error"]["details"]["job"]
    assert job["status"] == "WAITING_FOR_APPROVAL" and job["approval_needed"]["estimate_usd"] == 0.5
    assert service.generate_motion(plan_id=p["plan_id"])["error"]["details"]["job"]["job_id"] == job["job_id"]
    assert registry.get("external.meshy").external_calls == 0 and service.store.ledger_entries() == []


@pytest.mark.parametrize("max_cost, billing, code, why", [
    (0.4, {}, "BUDGET_EXCEEDED", "ESTIMATE_OVER_APPROVAL"),
    (3.0, {}, "BUDGET_EXCEEDED", "MAX_COST_PER_JOB"),
    (1.0, {"max_total_cost_usd": 0.8}, "BUDGET_EXCEEDED", "MAX_TOTAL"),
    (0, {}, "BAD_REQUEST", "BAD_VALUE"),
])
def test_E_approval_caps(make_service, max_cost, billing, code, why):
    service, registry = make_service(**{"external.meshy": mock_paid()})
    enable_paid(service, **billing)
    p = plan_paid(service)
    env = service.approve_generation(plan_id=p["plan_id"], max_cost_usd=max_cost)
    assert env["error"]["code"] == code and reason(env) == why
    assert service.store.approvals_for(p["plan_id"]) == [] and registry.get("external.meshy").external_calls == 0


def test_E_cost_unknown_is_never_run(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid()})
    enable_paid(service)
    p = plan_paid(service)
    paid = registry.get("external.meshy")
    paid.cost_known = False  # 계획 뒤 가격을 확인할 수 없게 됐다
    env = service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    assert env["error"]["code"] == "COST_UNKNOWN"
    env = service.generate_motion(plan_id=p["plan_id"])
    job = env["result"]
    assert env["ok"] and job["provider"] == "existing_motion"  # 건너뛰고 무료 근사로
    assert job["fallback_history"][0]["cause"] == "COST_UNKNOWN" and job["fallback_history"][0]["skipped"]
    assert paid.external_calls == 0


def test_E_other_approval_refusals(make_service):
    service, _ = make_service(**{"external.meshy": mock_paid()})
    enable_paid(service)
    free = service.plan_motion_generation(request=request())["result"]
    env = service.approve_generation(plan_id=free["plan_id"], max_cost_usd=1.0)
    assert env["error"]["code"] == "BAD_REQUEST" and reason(env) == "NO_PAID_STEP"
    assert service.approve_generation(plan_id="plan_nope", max_cost_usd=1.0)["error"]["code"] == "PLAN_NOT_FOUND"
    p = plan_paid(service)
    env = service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0, max_attempts=0)
    assert reason(env) == "BAD_VALUE"


def test_E_approved_run_submits_once_and_is_idempotent(make_service, fake):
    service, registry = make_service(**{"external.meshy": mock_paid(actual=0.45)})
    enable_paid(service)
    p = plan_paid(service)
    waiting = service.generate_motion(plan_id=p["plan_id"])["error"]["details"]["job"]
    env = service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    assert env["ok"] and env["result"]["resumed_job_id"] == waiting["job_id"]
    assert service.estimate_generation_cost(plan_id=p["plan_id"])["result"]["candidates"][0]["verdict"] == "approved"
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"], env["error"]
    job = env["result"]
    assert job["job_id"] == waiting["job_id"] and job["provider"] == "external.meshy"
    assert [e["to"] for e in job["events"]] == ["QUEUED", "RUNNING", "WAITING_FOR_APPROVAL", "QUEUED", "RUNNING", "SUCCEEDED"]
    paid = registry.get("external.meshy")
    assert paid.submits == 1
    assert job["idempotency_key"] == ledger_key(p["plan_id"], 1) and job["approval_id"] == env["result"]["approval_id"]
    assert job["cost"] == {"estimated_usd": 0.5, "actual_usd": 0.45, "confirmed": True}
    assert service.store.ledger_totals() == {"spent_usd": 0.45, "reserved_usd": 0.0}
    assert "DRAFT_NEEDS_CLEANUP" not in {lim["code"] for lim in job["limitations"]}  # 무기 동작이 아니면 없다
    # 같은 계획으로 다시 → 같은 Job, 외부 호출 그대로
    again = service.generate_motion(plan_id=p["plan_id"])
    assert again["result"]["job_id"] == job["job_id"] and paid.submits == 1
    approval = service.store.approvals_for(p["plan_id"])[0]
    assert approval["used_attempts"] == 1 and approval["committed_usd"] == 0.5


def test_E_retry_needs_a_new_approval(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid(failures=[StepFailed("GENERATION_FAILED", None, "provider 500")])})
    enable_paid(service)
    service.set_generation_policy(patch={"execution": {"allow_fallback": False}})
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "GENERATION_FAILED"
    paid = registry.get("external.meshy")
    assert paid.submits == 1
    env = service.generate_motion(plan_id=p["plan_id"], retry=True)
    assert env["error"]["code"] == "APPROVAL_REQUIRED" and reason(env) == "ATTEMPTS_EXHAUSTED"
    assert paid.submits == 1
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"] and env["result"]["idempotency_key"] == ledger_key(p["plan_id"], 2) and paid.submits == 2
    # 첫 제출은 실패했지만 과금 여부를 모르므로 예약으로 남는다 (임의로 확정·해제하지 않는다)
    assert service.store.ledger_totals() == {"spent_usd": 0.5, "reserved_usd": 0.5}


def test_E_failed_submission_known_uncharged_is_released(make_service):
    service, _ = make_service(**{"external.meshy": mock_paid(failures=[StepFailed("RATE_LIMITED", "429", "slow", retryable=True, charged=False)])})
    enable_paid(service)
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0, max_attempts=2)
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"] and env["result"]["retry_count"] == 1 and env["result"]["idempotency_key"] == ledger_key(p["plan_id"], 2)
    assert service.store.ledger_totals() == {"spent_usd": 0.5, "reserved_usd": 0.0}


def test_E_resume_adopts_recorded_handle_without_resubmitting(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid(polls_needed=1)})
    enable_paid(service)
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    job = service.generate_motion(plan_id=p["plan_id"])["result"]
    assert job["status"] == "RUNNING" and registry.get("external.meshy").submits == 1
    # 제출은 됐는데 Job 에 핸들을 쓰기 전에 서버가 죽었다 — 장부(submitted)에는 핸들이 있다
    service.store.patch_job(job["job_id"], pending={**job["pending"], "handle": None})
    env = service.get_generation_status(job_id=job["job_id"])
    assert env["result"]["status"] == "SUCCEEDED"
    assert registry.get("external.meshy").submits == 1 and registry.get("external.meshy").polls == 1


def test_E_uncertain_submission_is_not_resubmitted(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid(polls_needed=1)})
    enable_paid(service)
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    job = service.generate_motion(plan_id=p["plan_id"])["result"]
    # 예약만 적히고 제출 결과(핸들)가 어디에도 없다 → 중복 과금을 피해 다시 제출하지 않는다
    key = job["pending"]["key"]
    entries = [e for e in service.store.ledger_entries() if not (e["kind"] == "submitted" and e["key"] == key)]
    (service.store.root / "ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    service.store.patch_job(job["job_id"], pending={**job["pending"], "handle": None})
    env = service.get_generation_status(job_id=job["job_id"])
    assert env["result"]["status"] == "FAILED" and env["result"]["error"]["reason"] == "SUBMISSION_UNCERTAIN"
    assert registry.get("external.meshy").submits == 1 and registry.get("external.meshy").polls == 0


def test_E_unconfirmed_actual_cost_stays_reserved(make_service):
    service, _ = make_service(**{"external.meshy": mock_paid(actual=None)})
    enable_paid(service)
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    job = service.generate_motion(plan_id=p["plan_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["cost"] == {"estimated_usd": 0.5, "actual_usd": None, "confirmed": False}
    assert service.store.ledger_totals() == {"spent_usd": 0.0, "reserved_usd": 0.5}
    est = service.estimate_generation_cost(plan_id=p["plan_id"])["result"]
    assert est["caps"]["remaining_usd"] == 4.5


def test_E_total_cap_counts_reserved_costs(make_service):
    service, registry = make_service(**{"external.meshy": mock_paid(actual=None)})
    enable_paid(service, max_total_cost_usd=1.0)
    first = plan_paid(service)
    service.approve_generation(plan_id=first["plan_id"], max_cost_usd=0.5)
    assert service.generate_motion(plan_id=first["plan_id"])["ok"]
    second = plan_paid(service, animation_name="AS_Vesper_Rifle_AimIdle_TwistP3b")
    env = service.approve_generation(plan_id=second["plan_id"], max_cost_usd=0.6)
    assert env["error"]["code"] == "BUDGET_EXCEEDED" and reason(env) == "MAX_TOTAL"
    assert registry.get("external.meshy").submits == 1


def test_E_api_key_never_reaches_state_files(make_service, monkeypatch, state_dir):
    sentinel = "sk-SENTINEL-0123456789"
    monkeypatch.setenv("MOCK_PAID_API_KEY", sentinel)
    service, registry = make_service(**{"external.meshy": mock_paid(auth_env="MOCK_PAID_API_KEY")})
    enable_paid(service)
    listed = service.list_motion_providers()
    assert {p["name"]: p for p in listed["result"]["providers"]}["external.meshy"]["state"]["auth"] == {"env": "MOCK_PAID_API_KEY", "present": True}
    p = plan_paid(service)
    service.approve_generation(plan_id=p["plan_id"], max_cost_usd=1.0)
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"]
    texts = [f.read_text(encoding="utf-8") for f in state_dir.rglob("*") if f.is_file()]
    assert texts and not any(sentinel in t for t in texts)
    assert sentinel not in str(listed) and sentinel not in str(env)
    monkeypatch.delenv("MOCK_PAID_API_KEY")
    p2 = plan_paid(service, animation_name="AS_Vesper_Rifle_AimIdle_TwistP3c")
    assert {e["provider"]: e["cause"] for e in p2["excluded"]}["external.meshy"] == "AUTHENTICATION_FAILED"
    assert registry.get("external.meshy").submits == 1
