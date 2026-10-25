"""external.meshy Provider — Meshy Text-to-Motion API (지침서 §2.4 · §4 · §6 · §14 Phase 6).

계획: 프롬프트 · 길이(2~10초, 0.5초 단위로 맞춤) · 모드로 보낼 본문을 계획에 고정한다 — 네트워크를 쓰지 않는다(보이는 것이 보내는 것).
실행: executor 가 승인 · 장부 예약을 마친 유료 단계 안에서만 부른다. 잔액 조회(무료) → POST 제출 → pending{task_id}.
poll: GET 태스크(Retry-After 전에는 부르지 않는다) → SUCCEEDED 면 결과 파일을 인증 헤더 없이 받아
<ImportSourceRoots[0]>/Meshy/<job_id>/A<n>/ 에 쓴다. 취소: 외부 호출 없음 — Meshy 에 취소가 없어 결과만 무시하고 비용은 장부에 남는다.

사슬: prime(FBX) = generate → import → retarget → validate. swift(BVH) = generate → convert(blender) → import → retarget → validate.
출력 리그(본 이름 · 기준 포즈 · 단위 · 축 · fps)는 문서에 없다 — 리타깃은 자동 IK Rig 부터 시도하고 정면은 실행 때 잰다.

키: 환경 변수(매니페스트 auth_env = MESHY_API_KEY)를 요청 직전에 읽어 Authorization 헤더에만 넣는다 — 요청 로그 · Job · 장부 · 진단 ·
오류 메시지 어디에도 남기지 않는다. 기본 URL 은 고정이다(정책으로 바꿀 수 없다 — 키가 다른 호스트로 가지 않게). 결과 다운로드는
서명된 URL 이라 헤더 없는 별도 클라이언트로 받는다. 요청 로그 <state>/external/meshy_requests.jsonl = 메서드 · 경로 · 상태 · 시간뿐.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from ..envelope import diag, limitation
from ..store import default_state_dir, now_iso
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult
from .subprocess_step import import_roots

API_BASE = "https://api.meshy.ai"
CREATE = "/openapi/v1/text-to-motion"
TASK = "/openapi/v1/text-to-motion/{id}"
BALANCE = "/openapi/v1/balance"
DEFAULT_DURATION_S = 5.0
POST_TIMEOUT_S = 60.0         # Meshy 권장 타임아웃(task-lifecycle): POST 60초 · GET 30초
GET_TIMEOUT_S = 30.0
DOWNLOAD_TIMEOUT_S = 120.0
DEFAULT_POLL_S = 5.0          # Retry-After 가 없을 때 poll 간격(Meshy 권장)
RATE_WAIT_MAX_S = 5.0         # 초당 한도 429 의 Retry-After 가 이 안이면 같은 시도에서 기다렸다 한 번 더 제출한다
DEFAULT_TIMEOUT_S = 3600.0
DOWNLOAD_MAX_BYTES = 200 << 20
LOG_NAME = "meshy_requests.jsonl"
# task_error — 다시 만들면 될 수 있는 실패(errors 페이지의 재시도 안내). invalid_input · moderation_blocked 는 같은 입력으로 다시 내지 않는다
RETRYABLE_TYPES = frozenset({"timeout", "service_unavailable", "server_error"})
RETRYABLE_CODES = frozenset({"queue_timeout", "moderation_unavailable", "format_conversion_failed"})
_FBX_BINARY = b"Kaydara FBX Binary"
_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LEAD = b"\xef\xbb\xbf \t\r\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_query(url: str) -> str:
    """서명 쿼리를 뺀 URL — 기록용(서명은 3일 동안 그 파일을 받을 수 있는 자격이다)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def format_ok(head: bytes, fmt: str) -> bool:
    """받은 파일의 앞부분이 그 형식인가 — 오류 페이지(HTML · JSON)를 동작 파일로 넘기지 않는다."""
    if fmt == "fbx":
        return head.startswith(_FBX_BINARY) or head.lstrip(_LEAD).startswith(b";")  # 바이너리 매직 · ASCII FBX 는 '; FBX' 주석으로 시작
    if fmt == "bvh":
        return head.lstrip(_LEAD).upper().startswith(b"HIERARCHY")
    return False


class _Transport(Exception):
    """응답을 못 받았다(타임아웃 · 연결) — 제출이면 됐는지 모른다."""


class _Expired(Exception):
    """결과 URL 이 더 이상 받히지 않는다(403 · 404 · 410)."""


class MeshyProvider(Provider):
    def __init__(self, manifest: dict, *, transport: httpx.BaseTransport | None = None, clock=None, sleep=None):
        super().__init__(manifest)
        self._transport = transport          # 테스트: httpx.MockTransport. None 이면 실제 네트워크
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self._next_poll: dict[str, float] = {}  # task_id → 다음 GET 가능 시각 (Retry-After). 서버가 다시 뜨면 비어 바로 poll 한다

    # ---- 매니페스트 · 정책 ----
    @property
    def model(self) -> dict:
        return self.manifest["model"]

    @property
    def auth_env(self) -> str:
        return self.manifest.get("auth_env") or "MESHY_API_KEY"

    def options(self, request: dict) -> dict:
        return (((request or {}).get("generation") or {}).get("options") or {}).get(self.name) or {}

    def mode(self, request: dict) -> str:
        return self.options(request).get("mode", self.model["default_mode"])

    @staticmethod
    def settings(policy: dict | None) -> dict:
        return ((policy or {}).get("external") or {}).get("meshy") or {}

    def estimate(self, request: dict, policy: dict | None = None) -> dict:
        """크레딧은 공식 가격표(매니페스트 model.modes), 돈은 정책 usd_per_credit(사용자의 요금제) — 없으면 비용 미확인."""
        mode = self.mode(request)
        spec = self.model["modes"].get(mode) or self.model["modes"][self.model["default_mode"]]
        credits = spec["credits"]
        rate = self.settings(policy).get("usd_per_credit")
        if rate is None:
            return {"cost_known": False, "estimate_usd": None, "credits": credits, "mode": mode,
                    "basis": f"{credits} credits ({mode}, official price list) — the money value of a credit depends on the Meshy plan and is "
                             "not set (policy external.meshy.usd_per_credit), so the cost is unconfirmed"}
        return {"cost_known": True, "estimate_usd": round(credits * float(rate), 4), "credits": credits, "mode": mode, "usd_per_credit": rate,
                "basis": f"{credits} credits ({mode}, official price list) × ${rate:g}/credit (policy external.meshy.usd_per_credit)"}

    # ---- 계획 (네트워크 없음) ----
    def plan_generate(self, request: dict, pctx: PlanContext) -> dict:
        prompt = request["prompt"]
        if not prompt:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "external.meshy needs request.prompt — the motion description sent to Meshy "
                              "(description is only recorded)", missing=["prompt"])
        if len(prompt) > self.model["prompt_max"]:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "PROMPT_TOO_LONG", f"Meshy takes up to {self.model['prompt_max']} characters (prompt has {len(prompt)})")
        opts = self.options(request)
        unknown = sorted(set(opts) - {"mode"})
        if unknown or opts.get("mode", self.model["default_mode"]) not in self.model["modes"]:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "BAD_OPTION", f"generation.options['{self.name}'] takes mode {sorted(self.model['modes'])} only "
                              f"(got {opts})", allowed={"mode": sorted(self.model["modes"])})
        mode = self.mode(request)
        spec = self.model["modes"][mode]
        span = self.model["duration"]
        duration = request["duration_seconds"] or DEFAULT_DURATION_S
        if not request["duration_seconds"]:
            pctx.diagnostics.append(diag("info", "DURATION_DEFAULTED", f"duration_seconds not given — {DEFAULT_DURATION_S:g}s sent to Meshy"))
        sent = round(duration / span["step"]) * span["step"]
        if sent < span["min"] - 1e-9:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "DURATION_TOO_SHORT", f"Meshy clips are {span['min']:g} to {span['max']:g}s (asked {duration:g}s)")
        sent = min(sent, span["max"])
        if abs(sent - duration) > 1e-9:
            pctx.diagnostics.append(diag("info", "DURATION_SNAPPED", f"Meshy takes {span['step']:g}s steps — {duration:g}s is sent as {sent:g}s"))
        gen = request["generation"]
        lims = [limitation("NOT_REPRODUCIBLE", "Meshy 는 seed 를 받지 않는다 — 같은 계획을 다시 실행해도(재시도 · 새 승인) 다른 동작이 나온다", "provider")]
        ignored = [k for k, default in (("seed", None), ("samples", 1), ("steps", 100), ("postprocess", "auto"), ("pick", 0)) if gen[k] != default]
        if ignored:
            lims.append(limitation("GENERATION_SETTINGS_IGNORED", f"generation 의 {ignored} 는 로컬 모델(local_ai) 설정이다 — Meshy 는 한 건만 만들고 이 값을 쓰지 "
                                   "않는다", "provider", fields=ignored))
        for kind in sorted({c["type"] for c in gen["constraints"]}):
            lims.append(limitation("CONSTRAINT_UNSUPPORTED", f"생성 제약 '{kind}' 은 Meshy 에 보낼 수 없다 — 결과가 따르지 않는다", "provider", constraint=kind))
        body = {"prompt": prompt, "duration": sent, "mode": mode}
        risks = ["SOURCE_RIG_UNVERIFIED", "PROMPT_SENT_EXTERNALLY"]
        if pctx.settings is None:
            risks.append("IMPORT_ROOTS_UNCHECKED")
        step = {"step": "generate", "provider": self.name, "tool": f"Meshy POST {CREATE}",
                "inputs": {"request_body": body, "mode": mode, "format": spec["format"], "credits": spec["credits"], "prompt_sha256": sha256_text(prompt)},
                "risks": risks, "expected_limitations": lims, "measured": {"length": sent, "frame_rate": None}}
        if spec["format"] == "bvh":
            # swift — BVH 를 Phase 4 · 5 blender 변환으로(더미 스킨 메시 · 대상 정면 · 바닥). 단위 · 정면 · 관절은 문서에 없어 실행 때 잰다
            step["output"] = "bvh"
            step["bvh"] = {"unit": "auto"}
        return step

    # ---- HTTP ----
    def _key(self) -> str | None:
        value = os.environ.get(self.auth_env)
        return value.strip() if value and value.strip() else None

    def _mask(self, text: str) -> str:
        key = self._key()
        return text.replace(key, "***") if key and key in text else text

    def _log(self, state_dir, entry: dict) -> None:
        path = pathlib.Path(state_dir or default_state_dir()) / "external" / LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": now_iso(), **entry}, ensure_ascii=False) + "\n")

    def _api(self, method: str, endpoint: str, path: str, *, key: str, state_dir, job_id: str, attempt: int, task_id: str | None = None,
             body: dict | None = None, timeout: float = GET_TIMEOUT_S) -> httpx.Response:
        """API 호스트 요청 하나. 리다이렉트는 따르지 않는다(POST 가 GET 으로 바뀌고, 키가 다른 곳으로 갈 수 있다). 로그에 헤더 · 본문 · 쿼리는 없다."""
        started = time.monotonic()
        entry = {"job_id": job_id, "attempt": attempt, "method": method, "endpoint": endpoint, "task_id": task_id}
        if body is not None:
            entry["body"] = {"duration": body.get("duration"), "mode": body.get("mode"), "prompt_sha256": sha256_text(body.get("prompt", ""))}
        try:
            with httpx.Client(base_url=API_BASE, transport=self._transport, timeout=timeout, follow_redirects=False) as client:
                resp = client.request(method, path, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as exc:
            self._log(state_dir, {**entry, "status": None, "ms": round((time.monotonic() - started) * 1000), "error": type(exc).__name__})
            raise _Transport(self._mask(f"{type(exc).__name__}: {exc}")) from None
        self._log(state_dir, {**entry, "status": resp.status_code, "ms": round((time.monotonic() - started) * 1000)})
        return resp

    def _message(self, resp: httpx.Response) -> str:
        try:
            text = (resp.json() or {}).get("message") or ""
        except ValueError:
            text = resp.text[:200]
        return self._mask(str(text))

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        try:
            return float(resp.headers["Retry-After"])
        except (KeyError, ValueError):
            return None

    def _refused(self, resp: httpx.Response, stage: str) -> StepFailed:
        """제출 · 잔액 조회가 거부됐다 — 태스크가 만들어지지 않았으니 과금 없음(charged=False → 장부 예약 해제)."""
        code, message = resp.status_code, self._message(resp)
        what = f"Meshy {stage} {code}: {message}"
        if code == 401:
            return StepFailed("AUTHENTICATION_FAILED", "UNAUTHORIZED", f"{what} — check {self.auth_env}", charged=False)
        if code == 402:
            return StepFailed("BUDGET_EXCEEDED", "INSUFFICIENT_CREDITS", f"{what} — not enough credits, a credit limit, or a free plan (the API needs "
                              "a paid plan)", charged=False)
        if code == 403:
            # 403 = 모더레이션(text-to-motion) · IP 허용 목록(ip_not_authorized) · 요금제에 없는 엔드포인트(errors)
            low = message.lower()
            if "moderat" in low:
                return StepFailed("UNSUPPORTED_REQUEST", "MODERATION_BLOCKED", f"{what} — content moderation refused the prompt", charged=False)
            if "ip_not_authorized" in low or "allowlist" in low or re.search(r"\bip\b", low):
                return StepFailed("AUTHENTICATION_FAILED", "IP_NOT_AUTHORIZED", f"{what} — the key's IP allowlist", charged=False)
            return StepFailed("AUTHENTICATION_FAILED", "FORBIDDEN", f"{what} — the key may not use this endpoint (plan)", charged=False)
        if code == 429:
            concurrent = message.startswith(("NoMorePendingTasks", "NoMoreConcurrentTasks"))
            return StepFailed("RATE_LIMITED", "CONCURRENT_TASKS" if concurrent else "REQUESTS_PER_SECOND", what, retryable=True, charged=False,
                              retry_after=self._retry_after(resp))
        if code == 400:
            return StepFailed("UNSUPPORTED_REQUEST", "BAD_REQUEST", what, charged=False)
        return StepFailed("GENERATION_FAILED", f"HTTP_{code}", what, charged=False)

    # ---- 실행: 잔액 → 제출 ----
    def run(self, ctx: RunContext) -> StepResult:
        key = self._key()
        if key is None:
            raise StepFailed("AUTHENTICATION_FAILED", "API_KEY_MISSING", f"environment variable {self.auth_env} is not set", charged=False)
        settings = ctx.editor.status()
        if settings is None:
            raise StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", "Editor unreachable — import roots come from get_editor_status and the next steps need it",
                             fatal=True, charged=False)
        inputs = ctx.step["inputs"]
        body = inputs["request_body"]
        credits = inputs["credits"]
        rate = self.settings(ctx.policy).get("usd_per_credit")
        if rate is None:  # 승인 게이트를 지난 뒤 정책이 바뀌었다 — 금액을 모르면 제출하지 않는다(§6)
            raise StepFailed("COST_UNKNOWN", "USD_PER_CREDIT_UNSET", "policy external.meshy.usd_per_credit is not set — not submitted", charged=False)
        call = {"key": key, "state_dir": ctx.state_dir, "job_id": ctx.job_id, "attempt": ctx.attempt}
        balance = self._balance(call, credits)
        out_dir = import_roots(settings)[0] / "Meshy" / ctx.job_id / f"A{ctx.attempt}"
        out_dir.mkdir(parents=True, exist_ok=True)
        task_id = None
        for tries in (1, 2):
            try:
                resp = self._api("POST", CREATE, CREATE, body=body, timeout=POST_TIMEOUT_S, **call)
            except _Transport as exc:
                # 응답을 못 받았다 — 만들어졌을 수 있으니 다시 내지 않는다(중복 과금). 장부 예약은 남는다
                raise StepFailed("GENERATION_FAILED", "SUBMISSION_UNCERTAIN", f"Meshy submit got no response ({exc}) — not resubmitted; check the "
                                 "Meshy dashboard / GET /openapi/v1/text-to-motion for a task created now", fatal=True) from None
            if resp.status_code in (200, 201, 202):
                try:
                    task_id = str((resp.json() or {}).get("result") or "")
                except ValueError:
                    task_id = ""
                break
            wait = self._retry_after(resp)
            if resp.status_code == 429 and tries == 1 and wait is not None and wait <= RATE_WAIT_MAX_S:
                self._sleep(wait)  # 초당 한도 — 태스크가 만들어지지 않았으니 같은 시도로 한 번 더
                continue
            if resp.status_code >= 500:
                raise StepFailed("GENERATION_FAILED", "SUBMISSION_UNCERTAIN", f"Meshy submit {resp.status_code}: {self._message(resp)} — whether a task "
                                 "was created is unknown, so it is not resubmitted", fatal=True)
            raise self._refused(resp, "submit")
        if not task_id or not _TASK_ID.match(task_id):
            raise StepFailed("GENERATION_FAILED", "BAD_TASK_ID", f"Meshy accepted the submission but returned task id {task_id!r} — cannot poll it",
                             fatal=True)
        now = self._clock()
        timeout = float(self.settings(ctx.policy).get("timeout_seconds") or DEFAULT_TIMEOUT_S)
        handle = {"task_id": task_id, "mode": inputs["mode"], "format": inputs["format"], "credits": credits, "usd_per_credit": rate,
                  "submitted_at": now, "deadline": now + timeout, "timeout_s": timeout, "dir": out_dir.as_posix(), "job_id": ctx.job_id,
                  "attempt": ctx.attempt, "balance_before": balance}
        (out_dir / "submission.json").write_text(json.dumps({**handle, "request_body": body}, ensure_ascii=False, indent=1), encoding="utf-8")
        self._next_poll[task_id] = now + DEFAULT_POLL_S
        return StepResult(pending=handle)

    def _balance(self, call: dict, credits: int) -> int | None:
        """잔액(무료 엔드포인트) — 부족하면 제출하지 않는다. 조회 자체가 막히면(429 · 5xx · 연결) 건너뛴다 — 제출이 402 로 알려 준다."""
        try:
            resp = self._api("GET", BALANCE, BALANCE, **call)
        except _Transport:
            return None
        if resp.status_code in (401, 402, 403):
            raise self._refused(resp, "balance")
        if resp.status_code != 200:
            return None
        try:
            balance = int((resp.json() or {}).get("balance"))
        except (TypeError, ValueError):
            return None
        if balance < credits:
            raise StepFailed("BUDGET_EXCEEDED", "INSUFFICIENT_CREDITS", f"Meshy balance {balance} credits < {credits} needed — not submitted",
                             charged=False, balance=balance)
        return balance

    # ---- poll: 태스크 → 결과 다운로드 ----
    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        task_id = handle["task_id"]
        now = self._clock()
        if now < self._next_poll.get(task_id, 0.0):
            return None  # Retry-After 전 — 요청을 보내지 않는다(poll 도 초당 한도에 든다)
        key = self._key()
        if key is None:
            raise StepFailed("AUTHENTICATION_FAILED", "API_KEY_MISSING", f"{self.auth_env} is gone while Meshy task {task_id} is in flight — its cost "
                             "stays reserved")
        call = {"key": key, "state_dir": ctx.state_dir, "job_id": ctx.job_id, "attempt": ctx.attempt, "task_id": task_id}
        try:
            resp = self._api("GET", TASK, TASK.format(id=quote(task_id, safe="")), **call)
        except _Transport:
            return self._wait(handle, now, None)
        if resp.status_code == 429 or resp.status_code >= 500:
            return self._wait(handle, now, self._retry_after(resp))  # 실패한 poll 은 태스크 실패가 아니다(task-lifecycle)
        if resp.status_code == 404:
            raise StepFailed("GENERATION_FAILED", "TASK_NOT_FOUND", f"Meshy task {task_id} is gone (deleted or past retention) — its cost stays reserved")
        if resp.status_code in (401, 403):
            raise StepFailed("AUTHENTICATION_FAILED", "UNAUTHORIZED", f"Meshy task {task_id} poll {resp.status_code}: {self._message(resp)}")
        if resp.status_code != 200:
            raise StepFailed("GENERATION_FAILED", f"HTTP_{resp.status_code}", f"Meshy task {task_id} poll {resp.status_code}: {self._message(resp)}")
        try:
            task = resp.json() or {}
        except ValueError:
            return self._wait(handle, now, None)
        status = task.get("status")
        if status == "SUCCEEDED":
            self._next_poll.pop(task_id, None)
            return self._finish(ctx, handle, task, call)
        if status in ("FAILED", "CANCELED"):
            self._next_poll.pop(task_id, None)
            err = task.get("task_error") or {}
            reason = err.get("code") or err.get("type") or status
            raise StepFailed("GENERATION_FAILED", reason, f"Meshy task {task_id} {status}: {self._mask(str(err.get('message') or ''))}",
                             retryable=err.get("type") in RETRYABLE_TYPES or err.get("code") in RETRYABLE_CODES, **self._charge(handle, task),
                             task_error={k: err.get(k) for k in ("type", "code", "message", "doc_url") if err.get(k)})
        return self._wait(handle, now, self._retry_after(resp), progress=task.get("progress"))

    def _wait(self, handle: dict, now: float, retry_after: float | None, progress=None) -> None:
        if now > handle["deadline"]:
            self._next_poll.pop(handle["task_id"], None)
            raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"Meshy task {handle['task_id']} did not finish in {handle['timeout_s']:.0f}s "
                             f"(last progress {progress}) — it may still finish; its cost stays reserved")
        self._next_poll[handle["task_id"]] = now + (retry_after if retry_after and retry_after > 0 else DEFAULT_POLL_S)
        return None

    @staticmethod
    def _charge(handle: dict, task: dict) -> dict:
        """태스크가 알려 준 실제 크레딧 → StepFailed/StepResult 의 과금 값. 0 이면 환불(장부 해제), 모르면 예약으로 남긴다."""
        consumed = task.get("consumed_credits")
        if isinstance(consumed, bool) or not isinstance(consumed, (int, float)):
            return {}
        if consumed == 0:
            return {"charged": False, "actual_credits": 0, "actual_cost_usd": 0.0}
        return {"actual_credits": consumed, "actual_cost_usd": round(consumed * float(handle["usd_per_credit"]), 4)}

    def _finish(self, ctx: RunContext, handle: dict, task: dict, call: dict) -> StepResult:
        charge = self._charge(handle, task)
        result = task.get("result") or {}
        fmt = result.get("motion_format") or handle["format"]
        task_id = handle["task_id"]
        if fmt != handle["format"]:
            # 계획은 모드별 사슬(prime → import, swift → blender)로 고정됐다 — 다른 형식은 다음 단계가 받지 못한다
            raise StepFailed("GENERATION_FAILED", "FORMAT_MISMATCH", f"Meshy task {task_id} returned {fmt}, the plan expects {handle['format']} "
                             f"({handle['mode']})", **charge)
        expires = task.get("expires_at") or 0
        if expires and self._clock() * 1000 > expires:
            raise StepFailed("GENERATION_FAILED", "RESULT_EXPIRED", f"Meshy task {task_id} result expired at {expires} (kept 3 days)", **charge)
        out_dir = pathlib.Path(handle["dir"])
        dest = out_dir / f"meshy_motion.{fmt}"
        url = result.get("motion_url")
        if not url:
            raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Meshy task {task_id} SUCCEEDED without motion_url", **charge)
        try:
            size = self._download(url, dest, fmt, ctx.state_dir, handle)
        except _Expired:
            # motion_url 은 읽을 때마다 다시 서명된다 — 태스크를 다시 읽어 새 URL 로 한 번 더
            try:
                again = self._api("GET", TASK, TASK.format(id=quote(task_id, safe="")), **call)
                url = ((again.json() or {}).get("result") or {}).get("motion_url") if again.status_code == 200 else None
            except (_Transport, ValueError):
                url = None
            try:
                if not url:
                    raise _Expired()
                size = self._download(url, dest, fmt, ctx.state_dir, handle)
            except _Expired:
                raise StepFailed("GENERATION_FAILED", "RESULT_EXPIRED", f"Meshy task {task_id} result URL no longer downloads (also after "
                                 "re-reading the task)", **charge) from None
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        kept = {**task, "result": {**result, "motion_url": strip_query(url or "")}}
        (out_dir / "task.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        seconds = None
        if task.get("finished_at") and task.get("created_at"):
            seconds = round((task["finished_at"] - task["created_at"]) / 1000.0, 1)
        generated = {"task_id": task_id, "mode": handle["mode"], "format": fmt, "duration_ms": result.get("duration_ms"), "file": dest.as_posix(),
                     "bytes": size, "sha256": digest, "consumed_credits": task.get("consumed_credits"), "seconds": seconds,
                     "expires_at": task.get("expires_at")}
        note = diag("info", "MESHY_GENERATED", f"Meshy task {task_id} ({handle['mode']}) → {dest.name} {size} B, {result.get('duration_ms')} ms, "
                    f"{task.get('consumed_credits')} credits, {seconds}s on Meshy", task=generated)
        return StepResult(values={"file": dest.as_posix(), "generated": generated}, diagnostics=[note],
                          actual_cost_usd=charge.get("actual_cost_usd"), actual_credits=charge.get("actual_credits"))

    def _download(self, url: str, dest: pathlib.Path, fmt: str, state_dir, handle: dict) -> int:
        """서명된 결과 URL — 인증 헤더 없이(키를 저장소 호스트에 보내지 않는다) https 로만, 크기 상한 · 형식 바이트 확인."""
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise StepFailed("GENERATION_FAILED", "INSECURE_URL", f"Meshy motion_url is not https ({parts.scheme})")
        entry = {"job_id": handle["job_id"], "attempt": handle["attempt"], "method": "GET", "endpoint": "download", "task_id": handle["task_id"],
                 "host": parts.netloc, "path": parts.path}
        started = time.monotonic()
        part = dest.with_name(dest.name + ".part")
        size = 0
        try:
            with httpx.Client(transport=self._transport, timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    self._log(state_dir, {**entry, "status": resp.status_code, "ms": round((time.monotonic() - started) * 1000)})
                    if resp.status_code in (403, 404, 410):
                        raise _Expired()
                    if resp.status_code != 200:
                        raise StepFailed("GENERATION_FAILED", f"DOWNLOAD_HTTP_{resp.status_code}", f"Meshy result download {resp.status_code}")
                    if resp.url.scheme != "https":
                        raise StepFailed("GENERATION_FAILED", "INSECURE_URL", "Meshy result download was redirected off https")
                    with part.open("wb") as out:
                        for chunk in resp.iter_bytes():
                            size += len(chunk)
                            if size > DOWNLOAD_MAX_BYTES:
                                raise StepFailed("GENERATION_FAILED", "DOWNLOAD_TOO_LARGE", f"Meshy result is over {DOWNLOAD_MAX_BYTES >> 20} MB")
                            out.write(chunk)
        except httpx.HTTPError as exc:
            part.unlink(missing_ok=True)
            self._log(state_dir, {**entry, "status": None, "error": type(exc).__name__})
            raise StepFailed("GENERATION_FAILED", "DOWNLOAD_FAILED", f"Meshy result download failed: {type(exc).__name__}") from None
        except (StepFailed, _Expired):
            part.unlink(missing_ok=True)
            raise
        with part.open("rb") as f:
            head = f.read(64)
        if not format_ok(head, fmt):
            part.unlink(missing_ok=True)
            raise StepFailed("GENERATION_FAILED", "BAD_FORMAT", f"Meshy result is not a {fmt.upper()} file (starts {head[:16]!r})")
        os.replace(part, dest)
        return size

    def cancel(self, handle: dict) -> dict | None:
        """Meshy 에는 text-to-motion 취소가 없다 — 외부 호출 없이 결과만 무시한다(§3.4). 비용은 장부 예약으로 남는다."""
        self._next_poll.pop(handle.get("task_id"), None)
        return None
