"""Phase 6 — external.meshy 어댑터 (지침서 §14 Phase 6 · §6 · §15 테스트 E 실제 어댑터).

진짜 네트워크 없이 httpx.MockTransport 로 Meshy API(잔액 · 제출 · 태스크 · 결과 다운로드)를 흉내 낸다 — 키 없음 · 인증 실패 · Rate Limit ·
생성 실패 · 결과 만료 · 취소 · 재제출 멱등 · 장부 · 요청 로그 · 키가 어디에도 남지 않음. 실제 HTTPTransport 는 conftest 가 막는다.
"""
from __future__ import annotations

import json
import types

import httpx
import pytest

from anim_gen.providers.blender import BlenderProvider
from anim_gen.providers.meshy import BALANCE, CREATE, LOG_NAME, MeshyProvider
from anim_gen.registry import Registry
from anim_gen.service import Service
from anim_gen.store import Store, ledger_key
from conftest import VESPER_MESH, request

KEY = "msy_SENTINEL-meshy-key-0123456789"
RATE = 0.02
FBX = b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 200
BVH = b"HIERARCHY\nROOT Hips\n{\n}\nMOTION\nFrames: 1\nFrame Time: 0.0333\n0\n"
ASSETS = "assets.meshy.test"


class FakeClock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeMeshy:
    """Meshy API 흉내. script[엔드포인트] 에 응답(또는 예외)을 넣으면 앞에서부터 쓴다. requests = 받은 요청 전부(헤더 포함)."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.requests: list[httpx.Request] = []
        self.script: dict[str, list] = {"balance": [], "create": [], "task": [], "download": []}
        self.balance = 1000
        self.polls_until_done = 1     # IN_PROGRESS 를 몇 번 보인 뒤 끝나는가
        self.final = "SUCCEEDED"
        self.task_error = None
        self.consumed = None          # None = 모드 가격
        self.motion_format = None     # None = 모드 형식
        self.expires_in_ms = 3 * 86400 * 1000
        self.body = FBX
        self.tasks: dict[str, dict] = {}
        self.retry_after = "5"

    def count(self, kind: str) -> int:
        return sum(1 for r in self.requests if self.kind(r) == kind)

    @staticmethod
    def kind(r: httpx.Request) -> str:
        if r.url.host == ASSETS:
            return "download"
        if r.url.path == BALANCE:
            return "balance"
        return "create" if r.method == "POST" else "task"

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        kind = self.kind(request)
        if self.script[kind]:
            item = self.script[kind].pop(0)
            if isinstance(item, Exception):
                raise item
            if item is not None:
                return item
        return getattr(self, f"_{kind}")(request)

    def _balance(self, r):
        return httpx.Response(200, json={"balance": self.balance, "monthly_credits": self.balance, "permanent_credits": 0, "monthly_resets_at": None})

    def _create(self, r):
        body = json.loads(r.content)
        task_id = f"tm-{len(self.tasks) + 1:04d}"
        self.tasks[task_id] = {"body": body, "polls": 0, "created_at": int(self.clock() * 1000)}
        return httpx.Response(202, json={"result": task_id})

    def _task(self, r):
        task_id = r.url.path.rsplit("/", 1)[-1]
        t = self.tasks.get(task_id)
        if t is None:
            return httpx.Response(404, json={"message": "Task not found"})
        t["polls"] += 1
        mode = t["body"]["mode"]
        base = {"id": task_id, "type": "text-to-motion", "created_at": t["created_at"], "started_at": t["created_at"], "task_error": None,
                "result": {"motion_url": "", "motion_format": "", "duration_ms": 0, "mode": ""}}
        if t["polls"] <= self.polls_until_done:
            return httpx.Response(200, json={**base, "status": "IN_PROGRESS", "progress": 40, "finished_at": 0, "expires_at": 0,
                                             "consumed_credits": 10 if mode == "prime" else 3}, headers={"Retry-After": self.retry_after})
        finished = int(self.clock() * 1000)
        credits = self.consumed if self.consumed is not None else (10 if mode == "prime" else 3)
        fmt = self.motion_format or ("fbx" if mode == "prime" else "bvh")
        task = {**base, "status": self.final, "progress": 100, "finished_at": finished, "expires_at": finished + self.expires_in_ms,
                "consumed_credits": credits if self.final == "SUCCEEDED" else 0}
        if self.final == "SUCCEEDED":
            task["result"] = {"motion_url": f"https://{ASSETS}/motions/{task_id}.{fmt}?Signature=secret-sig-{t['polls']}&Expires=1",
                              "motion_format": fmt, "duration_ms": int(t["body"]["duration"] * 1000), "mode": mode}
        else:
            task["task_error"] = self.task_error or {"type": "server_error", "message": "An internal error occurred. Please retry."}
        return httpx.Response(200, json=task)

    def _download(self, r):
        return httpx.Response(200, content=self.body)


@pytest.fixture
def mz(make_service, fake, tmp_path, state_dir, monkeypatch):
    """가짜 Meshy + 키(센티널) + 유료 허용 정책(크레딧당 $0.02 · 상한) + ImportSourceRoots(tmp)."""
    roots = tmp_path / "Import"
    roots.mkdir()
    fake.import_roots = [roots.as_posix() + "/"]
    monkeypatch.setenv("MESHY_API_KEY", KEY)
    clock = FakeClock()
    api = FakeMeshy(clock)
    sleeps: list[float] = []

    def factory(registry):
        return MeshyProvider(registry.get("external.meshy").manifest, transport=httpx.MockTransport(api.handle), clock=clock, sleep=sleeps.append)

    service, registry = make_service(**{"external.meshy": factory})
    env = service.set_generation_policy(patch={"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 1.0, "max_total_cost_usd": 2.0},
                                               "external": {"meshy": {"usd_per_credit": RATE}}})
    assert env["ok"], env
    ns = types.SimpleNamespace(service=service, registry=registry, api=api, clock=clock, sleeps=sleeps, roots=roots, fake=fake, tmp=tmp_path,
                               state_dir=state_dir, factory=factory, make_service=make_service)
    return ns


def mz_request(**overrides) -> dict:
    base = {"animation_name": "AS_Vesper_Meshy_SpinKickP6", "family": "Meshy", "motion_category": "full_body_new", "loop": False, "edits": ...,
            "target_mesh": VESPER_MESH, "description": "돌려차기", "duration_seconds": 4.0, "frame_rate": 30, "generation_policy": "QUALITY_FIRST",
            "prompt": "A person does a spinning kick."}
    base.update(overrides)
    return request(**base)


def plan(mz, **overrides) -> dict:
    env = mz.service.plan_motion_generation(request=mz_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


def approve(mz, p: dict, max_cost: float = 0.5, attempts: int = 1) -> dict:
    env = mz.service.approve_generation(plan_id=p["plan_id"], max_cost_usd=max_cost, max_attempts=attempts)
    assert env["ok"], env["error"]
    return env["result"]


def generate(mz, p: dict, **kw) -> dict:
    env = mz.service.generate_motion(plan_id=p["plan_id"], **kw)
    return env["result"] if env["ok"] else env["error"]["details"].get("job", env["error"])


def status(mz, job_id: str) -> dict:
    return mz.service.get_generation_status(job_id=job_id)["result"]


def run_to_end(mz, p: dict, polls: int = 10) -> dict:
    job = generate(mz, p)
    for _ in range(polls):
        if job["status"] != "RUNNING":
            break
        mz.clock.advance(5)
        job = status(mz, job["job_id"])
    return job


def ledger(mz) -> list[dict]:
    return mz.service.store.ledger_entries()


def request_log(mz) -> list[dict]:
    path = mz.state_dir / "external" / LOG_NAME
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def meshy_first(p: dict) -> dict:
    cand = p["candidates"][0]
    assert cand["provider"] == "external.meshy", p["excluded"]
    return cand


# ---- 계획 (네트워크 없음) ----
def test_plan_pins_the_body_and_the_credit_estimate_without_calls(mz):
    p = plan(mz)
    cand = meshy_first(p)
    assert cand["chain"] == ["external.meshy", "retarget"]
    assert [s["step"] for s in cand["steps"]] == ["generate", "import", "retarget", "validate"]
    gen = cand["steps"][0]
    assert gen["inputs"]["request_body"] == {"prompt": "A person does a spinning kick.", "duration": 4.0, "mode": "prime"}
    assert gen["inputs"]["format"] == "fbx" and gen["inputs"]["credits"] == 10
    assert cand["estimated_credits"] == 10 and cand["estimated_cost_usd"] == 0.2 and cand["needs_approval"]
    assert {"SOURCE_RIG_UNVERIFIED", "PROMPT_SENT_EXTERNALLY", "FACING_UNRESOLVED_AT_PLAN"} <= set(cand["risks"])
    lims = {lim["code"] for lim in cand["expected_limitations"]}
    assert "NOT_REPRODUCIBLE" in lims and "DURATION_MISMATCH" not in lims
    # 소스 체인을 채우지 않는다 — 리그를 모르니 자동 IK Rig 부터
    assert not cand["steps"][2]["inputs"].get("source_chains") and "defaults_from" not in cand["steps"][2]["inputs"]
    est = mz.service.estimate_generation_cost(plan_id=p["plan_id"])["result"]["candidates"][0]
    assert est["verdict"] == "needs_approval" and est["credits"] == 10 and est["usd_per_credit"] == RATE and est["estimate_usd"] == 0.2
    assert "official price list" in est["basis"]
    assert mz.api.requests == [] and request_log(mz) == []


def test_swift_chains_the_blender_converter(mz, monkeypatch):
    monkeypatch.setattr(BlenderProvider, "installed", lambda self, policy: (True, "fake"))
    p = plan(mz, generation={"options": {"external.meshy": {"mode": "swift"}}})
    cand = meshy_first(p)
    assert cand["chain"] == ["external.meshy", "blender", "retarget"]
    assert [s["step"] for s in cand["steps"]] == ["generate", "convert", "import", "retarget", "validate"]
    assert cand["steps"][0]["inputs"]["request_body"]["mode"] == "swift" and cand["estimated_credits"] == 3 and cand["estimated_cost_usd"] == 0.06
    assert cand["steps"][1]["inputs"]["unit"] == "auto" and cand["steps"][1]["inputs"]["facing"] == "auto"
    assert cand["steps"][3]["inputs"]["facing"]["mode"] == "converted"  # blender 가 대상 정면으로 돌린다
    assert mz.api.requests == []


def test_swift_without_blender_is_excluded(mz):
    p = plan(mz, generation={"options": {"external.meshy": {"mode": "swift"}}})
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["external.meshy"] == "DEPENDS_ON_BLENDER"


def test_duration_is_snapped_or_defaulted(mz):
    p = plan(mz, duration_seconds=3.2)
    cand = meshy_first(p)
    assert cand["steps"][0]["inputs"]["request_body"]["duration"] == 3.0
    assert "DURATION_SNAPPED" in [d["code"] for d in p["diagnostics"]]
    assert "DURATION_MISMATCH" in {lim["code"] for lim in cand["expected_limitations"]}
    p = plan(mz, duration_seconds=None)
    assert meshy_first(p)["steps"][0]["inputs"]["request_body"]["duration"] == 5.0 and "DURATION_DEFAULTED" in [d["code"] for d in p["diagnostics"]]


@pytest.mark.parametrize("overrides, cause, reason", [
    ({"duration_seconds": 1.5}, "UNSUPPORTED_REQUEST", "DURATION_TOO_SHORT"),
    ({"duration_seconds": 12.0}, "UNSUPPORTED_REQUEST", "DURATION_OVER_MAX"),
    ({"prompt": "x" * 401}, "UNSUPPORTED_REQUEST", "PROMPT_TOO_LONG"),
    ({"prompt": None}, "UNSUPPORTED_REQUEST", "MISSING_INPUT"),
    ({"generation": {"options": {"external.meshy": {"mode": "ultra"}}}}, "UNSUPPORTED_REQUEST", "BAD_OPTION"),
    ({"generation": {"options": {"external.meshy": {"seed": 3}}}}, "UNSUPPORTED_REQUEST", "BAD_OPTION"),
])
def test_meshy_exclusions(mz, overrides, cause, reason):
    p = plan(mz, **overrides)
    assert {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}["external.meshy"] == (cause, reason)
    assert mz.api.requests == []


def test_unknown_provider_in_options_is_refused(mz):
    env = mz.service.plan_motion_generation(request=mz_request(generation={"options": {"external.nope": {}}}))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "UNKNOWN_PROVIDER"


def test_local_model_settings_and_constraints_become_limitations(mz):
    p = plan(mz, generation={"seed": 5, "samples": 2, "constraints": [{"type": "root_path", "points": [{"t": 1.0, "forward_cm": 100, "left_cm": 0}]}]})
    lims = {lim["code"]: lim for lim in meshy_first(p)["expected_limitations"]}
    assert lims["GENERATION_SETTINGS_IGNORED"]["fields"] == ["seed", "samples"]
    assert lims["CONSTRAINT_UNSUPPORTED"]["constraint"] == "root_path" and "NOT_REPRODUCIBLE" in lims


# ---- 비용 게이트: 외부 호출 0 ----
def test_unset_rate_is_cost_unknown_and_never_called(mz):
    mz.service.set_generation_policy(patch={"external": {"meshy": {"usd_per_credit": None}}})
    p = plan(mz)
    ex = {e["provider"]: e for e in p["excluded"]}["external.meshy"]
    assert ex["cause"] == "COST_UNKNOWN" and "10 credits" in ex["reason"]
    env = mz.service.approve_generation(plan_id=p["plan_id"], max_cost_usd=0.5, provider="external.meshy")
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "NO_PAID_STEP"
    assert {p_["name"]: p_ for p_ in mz.service.list_motion_providers()["result"]["providers"]}["external.meshy"]["pricing"] == "unconfirmed"
    assert mz.api.requests == [] and request_log(mz) == []


@pytest.mark.parametrize("patch, reason", [({"mode": "FREE_ONLY"}, "POLICY_FREE_ONLY"), ({"billing": {"paid_api_enabled": False}}, "PAID_API_DISABLED")])
def test_free_only_or_paid_disabled_make_zero_requests(mz, patch, reason):
    mz.service.set_generation_policy(patch=patch)
    p = plan(mz, provider="external.meshy")
    assert not p["executable"] and p["excluded"][0]["reason"] == reason
    env = mz.service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "APPROVAL_REQUIRED"
    assert mz.service.approve_generation(plan_id=p["plan_id"], max_cost_usd=0.5)["error"]["details"]["reason"] == reason
    assert mz.api.requests == [] and request_log(mz) == [] and ledger(mz) == []


def test_no_approval_waits_with_zero_requests(mz):
    p = plan(mz)
    job = generate(mz, p)
    assert job["status"] == "WAITING_FOR_APPROVAL" and job["approval_needed"]["estimate_usd"] == 0.2
    assert mz.api.requests == [] and request_log(mz) == [] and ledger(mz) == []


# ---- 성공 · 장부 · 요청 로그 · 키 ----
def test_approved_run_submits_once_downloads_and_retargets(mz):
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    assert job["status"] == "RUNNING" and job["stage"] == "generate"
    assert [mz.api.kind(r) for r in mz.api.requests] == ["balance", "create"]
    assert json.loads(mz.api.requests[1].content) == {"prompt": "A person does a spinning kick.", "duration": 4.0, "mode": "prime"}
    # Retry-After(첫 poll 5초) 전에는 요청하지 않는다
    assert status(mz, job["job_id"])["status"] == "RUNNING" and len(mz.api.requests) == 2
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert [mz.api.kind(r) for r in mz.api.requests] == ["balance", "create", "task", "task", "download"]
    # 인증 헤더는 API 호스트에만 — 서명된 결과 URL(저장소 호스트)에는 보내지 않는다
    for r in mz.api.requests:
        assert ("authorization" in r.headers) == (r.url.host == "api.meshy.ai")
        if r.url.host == "api.meshy.ai":
            assert r.headers["authorization"] == f"Bearer {KEY}"
    key = ledger_key(p["plan_id"], 1)
    entries = [(e["kind"], e["key"]) for e in ledger(mz)]
    assert entries == [("reserve", key), ("submitted", key), ("charge", key)]
    reserve, submitted, charge = ledger(mz)
    assert reserve["credits"] == 10 and reserve["usd"] == 0.2 and submitted["handle"]["task_id"] == "tm-0001"
    assert charge["credits"] == 10 and charge["usd"] == 0.2
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.2, "reserved_usd": 0.0}
    assert job["cost"] == {"estimated_usd": 0.2, "actual_usd": 0.2, "confirmed": True, "credits": {"estimated": 10, "actual": 10}}
    # 결과 파일은 ImportSourceRoots 아래 — import 단계가 그 파일을 받았다
    out = mz.roots / "Meshy" / job["job_id"] / "A1"
    assert (out / "meshy_motion.fbx").read_bytes() == FBX
    imports = [prm for t, prm in mz.fake.calls if t == "import_animation_file"]
    assert imports[0]["file"] == (out / "meshy_motion.fbx").as_posix()
    kept = json.loads((out / "task.json").read_text(encoding="utf-8"))
    assert kept["result"]["motion_url"] == f"https://{ASSETS}/motions/tm-0001.fbx"  # 서명 쿼리는 남기지 않는다
    gen = next(d for d in job["diagnostics"] if d["code"] == "MESHY_GENERATED")
    assert gen["task"]["task_id"] == "tm-0001" and gen["task"]["consumed_credits"] == 10 and gen["task"]["bytes"] == len(FBX)
    assert job["generated_assets"] == [f"{p['request']['output_path']}/AS_Vesper_Meshy_SpinKickP6"]
    assert "NOT_REPRODUCIBLE" in {lim["code"] for lim in job["limitations"]}
    log = request_log(mz)
    assert [(e["method"], e["endpoint"], e["status"]) for e in log] == [
        ("GET", BALANCE, 200), ("POST", CREATE, 202), ("GET", "/openapi/v1/text-to-motion/{id}", 200),
        ("GET", "/openapi/v1/text-to-motion/{id}", 200), ("GET", "download", 200)]
    assert log[1]["body"] == {"duration": 4.0, "mode": "prime", "prompt_sha256": p["candidates"][0]["steps"][0]["inputs"]["prompt_sha256"]}
    assert log[-1]["host"] == ASSETS and "Signature" not in json.dumps(log)
    # 같은 계획 다시 → 같은 Job, 요청 그대로
    again = mz.service.generate_motion(plan_id=p["plan_id"])["result"]
    assert again["job_id"] == job["job_id"] and len(mz.api.requests) == 5


def test_api_key_never_reaches_files_logs_or_envelopes(mz):
    p = plan(mz)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED"
    texts = [f.read_text(encoding="utf-8", errors="replace") for root in (mz.state_dir, mz.roots) for f in root.rglob("*") if f.is_file()]
    assert texts and not any(KEY in t for t in texts) and not any("secret-sig" in t for t in texts)
    assert KEY not in json.dumps(job) and KEY not in str(mz.service.list_motion_providers())


# ---- 키 · 인증 · 크레딧 ----
def test_key_missing_at_run_falls_back_without_requests(mz, monkeypatch):
    p = plan(mz)
    approve(mz, p)
    monkeypatch.delenv("MESHY_API_KEY")
    job = generate(mz, p)
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion"
    h = job["fallback_history"][0]
    assert h["provider"] == "external.meshy" and h["cause"] == "AUTHENTICATION_FAILED" and h["reason"] == "API_KEY_MISSING"
    assert mz.api.requests == []
    assert [e["kind"] for e in ledger(mz)] == []  # 게이트가 막았다(키 없음 = 사용 불가) — 예약도 없다


@pytest.mark.parametrize("where, response, cause, reason", [
    ("balance", httpx.Response(401, json={"message": "Invalid API key"}), "AUTHENTICATION_FAILED", "UNAUTHORIZED"),
    ("create", httpx.Response(401, json={"message": "Invalid API key"}), "AUTHENTICATION_FAILED", "UNAUTHORIZED"),
    ("create", httpx.Response(402, json={"message": "Insufficient credits"}), "BUDGET_EXCEEDED", "INSUFFICIENT_CREDITS"),
    ("create", httpx.Response(403, json={"message": "Content moderation flagged the prompt"}), "UNSUPPORTED_REQUEST", "MODERATION_BLOCKED"),
    ("create", httpx.Response(403, json={"message": "ip_not_authorized"}), "AUTHENTICATION_FAILED", "IP_NOT_AUTHORIZED"),
    ("create", httpx.Response(400, json={"message": "duration must be a multiple of 0.5"}), "UNSUPPORTED_REQUEST", "BAD_REQUEST"),
])
def test_refused_submission_is_released_and_falls_back(mz, where, response, cause, reason):
    mz.api.script[where].append(response)
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion"
    h = job["fallback_history"][0]
    assert (h["cause"], h["reason"]) == (cause, reason) and KEY not in h["message"]
    assert [e["kind"] for e in ledger(mz)] == ["reserve", "release"] and mz.service.store.ledger_totals()["reserved_usd"] == 0.0
    assert mz.api.count("create") == (0 if where == "balance" else 1)
    assert "FALLBACK_USED" in {lim["code"] for lim in job["limitations"]}


def test_low_balance_is_not_submitted(mz):
    mz.api.balance = 5
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    h = job["fallback_history"][0]
    assert (h["cause"], h["reason"]) == ("BUDGET_EXCEEDED", "INSUFFICIENT_CREDITS") and mz.api.count("create") == 0
    assert [e["kind"] for e in ledger(mz)] == ["reserve", "release"]


def test_balance_lookup_failure_does_not_block_submission(mz):
    mz.api.script["balance"].append(httpx.ConnectError("down"))
    p = plan(mz)
    approve(mz, p)
    assert run_to_end(mz, p)["status"] == "SUCCEEDED" and mz.api.count("create") == 1


# ---- Rate Limit ----
def test_per_second_rate_limit_waits_and_resubmits_in_the_same_attempt(mz):
    mz.api.script["create"].append(httpx.Response(429, json={"message": "Rate limit exceeded"}, headers={"Retry-After": "1"}))
    p = plan(mz)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED" and mz.sleeps == [1.0] and mz.api.count("create") == 2
    assert job["idempotency_key"] == ledger_key(p["plan_id"], 1) and job["attempt"] == 1


def test_concurrent_task_limit_is_retried_only_within_the_approval(mz):
    mz.api.script["create"].append(httpx.Response(429, json={"message": "NoMorePendingTasks: too many tasks"}))
    p = plan(mz, search=None)
    approve(mz, p, attempts=1)
    job = generate(mz, p)
    assert job["status"] == "WAITING_FOR_APPROVAL" and job["approval_needed"]["reason"] == "ATTEMPTS_EXHAUSTED"
    assert job["fallback_history"][0]["reason"] == "CONCURRENT_TASKS" and mz.sleeps == []
    approve(mz, p, attempts=1)
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED" and job["idempotency_key"] == ledger_key(p["plan_id"], 2) and mz.api.count("create") == 2
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.2, "reserved_usd": 0.0}  # 첫 시도는 만들어지지 않았다 — 해제


def test_poll_errors_are_not_failures_and_retry_after_is_respected(mz):
    mz.api.script["task"] += [httpx.Response(500, json={"message": "oops"}), httpx.Response(429, json={"message": "Rate limit exceeded"},
                                                                                               headers={"Retry-After": "30"})]
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    mz.clock.advance(5)
    assert status(mz, job["job_id"])["status"] == "RUNNING" and mz.api.count("task") == 1      # 500 → 다음 poll
    mz.clock.advance(5)
    assert status(mz, job["job_id"])["status"] == "RUNNING" and mz.api.count("task") == 2      # 429 Retry-After 30
    mz.clock.advance(10)
    assert status(mz, job["job_id"])["status"] == "RUNNING" and mz.api.count("task") == 2      # 30초 전 — 요청 없음
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED" and mz.api.count("create") == 1


# ---- 생성 실패 · 만료 · 형식 ----
def test_failed_task_is_refunded_and_falls_back(mz):
    mz.api.final = "FAILED"
    mz.api.task_error = {"type": "invalid_input", "code": "moderation_blocked", "message": "blocked"}
    p = plan(mz)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion"
    h = job["fallback_history"][0]
    assert (h["cause"], h["reason"], h["step"]) == ("GENERATION_FAILED", "moderation_blocked", "generate")
    assert [e["kind"] for e in ledger(mz)] == ["reserve", "submitted", "release"]
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.0, "reserved_usd": 0.0}
    assert job["cost"]["credits"] == {"estimated": 10, "actual": 0}


def test_retryable_task_failure_needs_a_new_approval(mz):
    mz.api.final = "FAILED"  # server_error — 다시 만들면 될 수 있다
    p = plan(mz, search=None)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "WAITING_FOR_APPROVAL" and job["approval_needed"]["reason"] == "ATTEMPTS_EXHAUSTED"
    assert job["fallback_history"][0]["reason"] == "server_error" and mz.api.count("create") == 1


def test_expired_result_is_charged_and_not_downloaded(mz):
    mz.api.expires_in_ms = -1000
    p = plan(mz)
    approve(mz, p)
    job = run_to_end(mz, p)
    h = job["fallback_history"][0]
    assert h["reason"] == "RESULT_EXPIRED" and mz.api.count("download") == 0
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.2, "reserved_usd": 0.0}  # 크레딧은 이미 썼다


def test_download_403_rereads_the_task_for_a_new_signature(mz):
    mz.api.script["download"].append(httpx.Response(403, text="<Error>Request has expired</Error>"))
    p = plan(mz)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "SUCCEEDED" and mz.api.count("download") == 2 and mz.api.count("task") == 3
    urls = [str(r.url) for r in mz.api.requests if mz.api.kind(r) == "download"]
    assert urls[0] != urls[1]  # 다시 서명된 URL


def test_download_failing_twice_is_expired(mz):
    mz.api.script["download"] += [httpx.Response(403), httpx.Response(404)]
    p = plan(mz, search=None)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "FAILED" and job["error"]["reason"] == "RESULT_EXPIRED"
    assert mz.service.store.ledger_totals()["spent_usd"] == 0.2


def test_non_motion_download_is_rejected(mz):
    mz.api.body = b"<html><body>Access denied</body></html>"
    p = plan(mz, search=None)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "FAILED" and job["error"]["reason"] == "BAD_FORMAT"
    out = mz.roots / "Meshy" / job["job_id"] / "A1"
    assert not (out / "meshy_motion.fbx").exists() and not (out / "meshy_motion.fbx.part").exists()


def test_unexpected_format_is_refused(mz):
    mz.api.motion_format = "bvh"
    p = plan(mz, search=None)
    approve(mz, p)
    job = run_to_end(mz, p)
    assert job["status"] == "FAILED" and job["error"]["reason"] == "FORMAT_MISMATCH" and mz.api.count("download") == 0


def test_timeout_keeps_the_cost_reserved(mz):
    mz.service.set_generation_policy(patch={"external": {"meshy": {"timeout_seconds": 60}}})
    mz.api.polls_until_done = 100
    p = plan(mz, search=None)
    approve(mz, p)
    job = generate(mz, p)
    mz.clock.advance(61)
    job = status(mz, job["job_id"])
    assert job["status"] == "FAILED" and job["error"]["reason"] == "TIMEOUT"
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.0, "reserved_usd": 0.2}  # 끝날 수도 있다 — 임의로 해제하지 않는다


def test_task_not_found(mz):
    p = plan(mz, search=None)
    approve(mz, p)
    job = generate(mz, p)
    mz.api.tasks.clear()
    mz.clock.advance(5)
    job = status(mz, job["job_id"])
    assert job["status"] == "FAILED" and job["error"]["reason"] == "TASK_NOT_FOUND"


# ---- 취소 · 멱등 · 재시작 · 불확실 제출 ----
def test_cancel_ignores_the_result_without_calls(mz):
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    calls = len(mz.api.requests)
    env = mz.service.cancel_generation(job_id=job["job_id"])
    assert env["ok"] and env["result"]["status"] == "CANCELLED" and env["result"]["result_ignored"]
    assert "cancel_effect" not in env["result"] and "RESULT_IGNORED" in [d["code"] for d in env["diagnostics"]]
    mz.clock.advance(30)
    assert status(mz, job["job_id"])["status"] == "CANCELLED" and len(mz.api.requests) == calls
    assert mz.service.store.ledger_totals() == {"spent_usd": 0.0, "reserved_usd": 0.2}


def test_server_restart_continues_the_same_task(mz):
    p = plan(mz)
    approve(mz, p)
    job = generate(mz, p)
    restarted = Registry()
    restarted.replace(mz.factory(restarted))
    service = Service(store=Store(mz.state_dir), registry=restarted, editor=mz.fake.client())
    for _ in range(4):
        mz.clock.advance(5)
        job = service.get_generation_status(job_id=job["job_id"])["result"]
        if job["status"] != "RUNNING":
            break
    assert job["status"] == "SUCCEEDED" and mz.api.count("create") == 1 and mz.api.count("task") == 2


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("timed out"), httpx.Response(502, json={"message": "bad gateway"})])
def test_uncertain_submission_is_not_resubmitted(mz, failure):
    mz.api.script["create"].append(failure)
    p = plan(mz)
    approve(mz, p, attempts=2)
    job = generate(mz, p)
    assert job["status"] == "FAILED" and job["error"]["reason"] == "SUBMISSION_UNCERTAIN"  # 폴백 없이 멈춘다(어디선가 돌고 있을 수 있다)
    assert mz.api.count("create") == 1 and mz.service.store.ledger_totals()["reserved_usd"] == 0.2
    assert KEY not in json.dumps(job)
