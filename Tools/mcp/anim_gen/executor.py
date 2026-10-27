"""Job 실행기 — 후보 순회 · 승인/멱등 키 · 폴백 · limitations (지침서 §3.4 · §6 · §7).

- 에디터 단계는 동기로 끝난다. 비동기 단계(외부 제출)는 pending 을 남기고, get_generation_status 가 다시 부르면 poll 한다.
- 진행 위치(cursor: 후보 · 단계 · 단계 값)를 Job 에 써 두므로 승인 대기 · 비동기 · 서버 재시작 뒤에도 같은 자리에서 잇는다.
- 다른 스레드가 Job 을 취소하면 다음 단계 전에 멈추고, 끝 전이가 거부되면(InvalidTransition) 결과를 버린다.
- 단계 안 에디터 Tool 의 diagnostics(LENGTH_SNAPPED · UNMAPPED_TARGET_CHAINS …)는 성공·실패 모두 Job diagnostics 에 tool · step 과 함께 남긴다.
"""
from __future__ import annotations

import contextlib
from typing import Callable, Iterator

from .editor import EditorCallError
from .envelope import limitation
from .fallback import fallback_limitations, from_editor_error, history_entry
from .policy import paid_block_reason, resolve_mode
from .providers.base import RunContext, StepFailed, StepResult
from .providers.integrate import promotion_proposal
from .store import (CANCELLED, FAILED, QUEUED, RUNNING, SUCCEEDED, WAITING_FOR_APPROVAL, InvalidTransition, Store, ledger_key,
                    now_iso)

# 계획 시점의 길이·fps 한계는 실행 뒤 측정값으로 다시 적는다
_MEASURED_CODES = {"DURATION_MISMATCH", "FRAME_RATE_MISMATCH"}
_PRODUCING = ("retarget", "edit", "timing")   # timing — Phase 8-3 흐느적 보정(apply_animation_edits retime · trim)


class _Cancelled(Exception):
    pass


class Executor:
    def __init__(self, store: Store, registry, editor, policy_loader: Callable[[], dict]):
        self.store = store
        self.registry = registry
        self.editor = editor
        self.policy = policy_loader

    # ---- 진입 ----
    def run(self, job_id: str) -> dict:
        job = self.store.load_job(job_id)
        plan = self.store.load_plan(job["plan_id"])
        if job["status"] == QUEUED:
            resumed = job.get("cursor") is not None
            self.store.transition(job_id, RUNNING, "resume" if resumed else "start")
        elif not (job["status"] == RUNNING and job.get("pending")):
            return job
        try:
            return self._loop(job_id, plan)
        except InvalidTransition:
            # 실행 중에 다른 호출이 상태를 바꿨다(취소) — 결과를 버린다
            return self.store.load_job(job_id)

    def _cancelled(self, job_id: str) -> bool:
        return self.store.load_job(job_id)["status"] == CANCELLED

    # ---- 후보 순회 ----
    def _loop(self, job_id: str, plan: dict) -> dict:
        policy = self.policy()
        request = plan["request"]
        mode, _ = resolve_mode(policy, request["generation_policy"])
        max_attempts = policy["execution"]["max_generation_attempts"]
        allow_fallback = policy["execution"]["allow_fallback"] and plan["fallback"]
        candidates = plan["candidates"]
        job = self.store.load_job(job_id)
        cs = job.get("cursor") or {"candidate": 0, "step": 0, "values": {}, "limitations": []}
        last = None
        while cs["candidate"] < len(candidates):
            if self._cancelled(job_id):
                return self.store.load_job(job_id)
            cand = candidates[cs["candidate"]]
            if cs["step"] == 0 and not self.store.load_job(job_id).get("pending"):
                gate = self._gate(cand, plan, policy, mode)
                if gate is not None:
                    kind, cause, reason, message, extra = gate
                    if kind == "wait":
                        return self._wait(job_id, cs, cand, cause, reason, message, extra)
                    self._append(job_id, "fallback_history", history_entry(cand, None, cause, reason, message, skipped=True, at=now_iso()))
                    last = {"code": cause, "reason": reason, "message": message}
                    if not allow_fallback:
                        break
                    cs = self._next(cs)
                    continue
                job = self.store.load_job(job_id)
                if job["attempt"] >= max_attempts:
                    return self._fail(job_id, last, attempts_exhausted=True)
                attempt = job["attempt"] + 1
                self.store.patch_job(job_id, attempt=attempt, retry_count=job["retry_count"] + (1 if cs.get("retry") else 0),
                                     provider=cand["provider"], chain=cand["chain"],
                                     work_path=f"{request['output_path']}/Work/{job_id}/A{attempt}", cursor=cs)
            try:
                outcome = self._run_steps(job_id, plan, cand, cs, policy)
            except _Cancelled:
                return self.store.load_job(job_id)
            except StepFailed as failed:
                job = self.store.load_job(job_id)
                step = cand["steps"][min(cs["step"], len(cand["steps"]) - 1)]["step"]
                self._append(job_id, "fallback_history", history_entry(cand, job["attempt"], failed.cause, failed.reason, failed.message,
                                                                         step=step, editor_error=failed.editor_error, at=now_iso()))
                if failed.created:
                    self._append(job_id, "left_assets", *failed.created)
                    if policy["execution"]["preserve_intermediate_results"] and failed.cause == "VALIDATION_FAILED":
                        self._append(job_id, "preserved_candidates", {"candidate": cand["index"], "provider": cand["provider"],
                                                                      "assets": failed.created, "note": "validation FAILED — kept unsaved"})
                last = {"code": failed.cause, "reason": failed.reason, "message": failed.message}
                if failed.cause == "INTEGRATION_FAILED" and failed.details:
                    last["details"] = failed.details  # 포장 · 연결 실패의 근거(시나리오 observed · 컴파일 메시지 · 스모크 결과)
                if self._cancelled(job_id):
                    return self.store.load_job(job_id)
                if failed.fatal:
                    return self._fail(job_id, last)
                if failed.retryable and job["attempt"] < max_attempts:
                    cs = {"candidate": cs["candidate"], "step": 0, "values": {}, "limitations": [], "retry": True}
                    self.store.patch_job(job_id, cursor=cs, pending=None)
                    continue
                if not allow_fallback:
                    return self._fail(job_id, last)
                cs = self._next(cs)
                self.store.patch_job(job_id, cursor=cs, pending=None)
                continue
            if outcome == "pending":
                return self.store.load_job(job_id)
            return self._succeed(job_id, plan, cand, cs)
        return self._fail(job_id, last)

    @staticmethod
    def _next(cs: dict) -> dict:
        return {"candidate": cs["candidate"] + 1, "step": 0, "values": {}, "limitations": []}

    # ---- 게이트: 정책 · 가용성 · 비용 · 승인 (§6 · §7 "넘어가기 조건") ----
    def _gate(self, cand: dict, plan: dict, policy: dict, mode: str):
        provider = self.registry.get(cand["provider"])
        if provider.paid:
            block = paid_block_reason(policy, mode)
            if block:
                return ("skip", "APPROVAL_REQUIRED", block, f"{provider.name} is paid and the policy blocks it ({block})", {})
        state = provider.state(policy)
        if not state["available"]:
            why = state["unavailable_reason"]
            return ("skip", why["cause"], why["reason"], f"{provider.name} is not available now", {})
        if not provider.paid:
            return None
        estimate = provider.estimate(plan["request"], policy)
        if not estimate["cost_known"]:
            return ("skip", "COST_UNKNOWN", estimate.get("basis"), f"{provider.name}: cost cannot be confirmed — never run (§6)", {})
        cost = float(estimate["estimate_usd"])
        approval = self.usable_approval(plan["plan_id"], provider.name)
        if approval is None:
            exhausted = bool(self.store.approvals_for(plan["plan_id"], provider.name))
            reason = "ATTEMPTS_EXHAUSTED" if exhausted else "NO_APPROVAL"
            return ("wait", "APPROVAL_REQUIRED", reason, f"{provider.name} needs approve_generation (estimate ${cost:.2f})",
                    {"provider": provider.name, "estimate_usd": cost})
        if approval["committed_usd"] + cost > approval["max_cost_usd"] + 1e-9:
            return ("skip", "BUDGET_EXCEEDED", "APPROVAL_CAP", f"approval {approval['approval_id']} has ${approval['max_cost_usd'] - approval['committed_usd']:.2f} left, "
                    f"estimate ${cost:.2f}", {})
        billing = policy["billing"]
        if cost > billing["max_cost_per_job_usd"] + 1e-9:
            return ("skip", "BUDGET_EXCEEDED", "MAX_COST_PER_JOB", f"estimate ${cost:.2f} > max_cost_per_job_usd {billing['max_cost_per_job_usd']}", {})
        totals = self.store.ledger_totals()
        if totals["spent_usd"] + totals["reserved_usd"] + cost > billing["max_total_cost_usd"] + 1e-9:
            return ("skip", "BUDGET_EXCEEDED", "MAX_TOTAL", f"spent+reserved ${totals['spent_usd'] + totals['reserved_usd']:.2f} + ${cost:.2f} "
                    f"> max_total_cost_usd {billing['max_total_cost_usd']}", {})
        return None

    def usable_approval(self, plan_id: str, provider: str) -> dict | None:
        usable = [a for a in self.store.approvals_for(plan_id, provider) if a["used_attempts"] < a["max_attempts"]]
        return usable[-1] if usable else None

    # ---- 단계 실행 ----
    def _run_steps(self, job_id: str, plan: dict, cand: dict, cs: dict, policy: dict) -> str:
        request = plan["request"]
        target = request["target_skeleton"]
        steps = cand["steps"]
        job = self.store.load_job(job_id)
        attempt = job["attempt"]
        work = job["work_path"]
        values = cs["values"]
        for j in range(cs["step"], len(steps)):
            if self._cancelled(job_id):
                raise _Cancelled()
            step = steps[j]
            kind = step["step"]
            self.store.patch_job(job_id, stage=kind)
            with self._editor_diagnostics(job_id, kind):
                if kind == "validate":
                    self._validate(request, values)
                elif kind == "retarget" and step.get("conditional") and values.get("skeleton") == target:
                    pass  # 계획 시점에 몰랐던 소스가 대상 스켈레톤에 있었다 — 리타깃 불필요
                else:
                    provider = self.registry.get(step["provider"])
                    final = kind in _PRODUCING and self._is_final(steps, j, values, target)
                    folder, name = (request["output_path"], self._final_name(job_id, request, attempt)) if final else (work, f"{request['animation_name']}_{kind.title()}")
                    ctx = RunContext(editor=self.editor, job_id=job_id, request=request, step=step, values=values, work_path=work,
                                     output_folder=folder, output_name=name, is_final=final, save=bool(job["save"]), attempt=attempt, policy=policy,
                                     state_dir=self.store.root, steps=steps)
                    if provider.paid:
                        result = self._paid_step(job_id, plan, provider, ctx, j)
                        if result is None:
                            cs["step"] = j
                            self.store.patch_job(job_id, cursor=cs)
                            return "pending"
                    else:
                        pending = self.store.load_job(job_id).get("pending")
                        if pending and pending["step"] == j:
                            result = self._poll_step(job_id, provider, ctx, pending)
                        else:
                            result = provider.run(ctx)
                            if result.pending is not None:  # 무료 비동기 단계(Blender · 로컬 AI · AnimBP 시나리오) — 장부 없이 핸들만
                                if result.created:  # 기다리기 전에 만든 애셋(AnimBP 복제본) — 취소 · 실패해도 Job 에 남는다
                                    self._append(job_id, "intermediate_assets", *result.created)
                                self.store.patch_job(job_id, pending={"key": None, "provider": provider.name, "handle": result.pending, "step": j})
                                result = None
                        if result is None:
                            cs["step"] = j
                            self.store.patch_job(job_id, cursor=cs)
                            return "pending"
                    self._absorb(job_id, cs, result, final)
            cs["step"] = j + 1
            self.store.patch_job(job_id, cursor=cs)
        return "done"

    @contextlib.contextmanager
    def _editor_diagnostics(self, job_id: str, step: str) -> Iterator[None]:
        """단계 안 에디터 Tool 의 diagnostics 를 Job 에 남긴다 — 단계가 실패해도(앞 Tool 의 경고가 원인 단서일 수 있다)."""
        with self.editor.collect() as found:
            try:
                yield
            finally:
                if found:
                    self._append(job_id, "diagnostics", *({**d, "step": step} for d in found))

    @staticmethod
    def _is_final(steps: list[dict], j: int, values: dict, target: str) -> bool:
        for later in steps[j + 1:]:
            if later["step"] in ("edit", "timing"):
                return False
            if later["step"] == "retarget" and not (later.get("conditional") and values.get("skeleton") == target):
                return False
        return True

    def _final_name(self, job_id: str, request: dict, attempt: int) -> str:
        """이 Job 의 앞선 시도가 최종 이름으로 애셋을 남겼으면(검증 실패 — 미저장) 겹치지 않게 _Try<N> 을 붙인다."""
        name = request["animation_name"]
        final = f"{request['output_path']}/{name}"
        job = self.store.load_job(job_id)
        if final in job.get("left_assets", []) or final in job.get("generated_assets", []):
            return f"{name}_Try{attempt}"
        return name

    def _absorb(self, job_id: str, cs: dict, result: StepResult, final: bool) -> None:
        cs["values"].update(result.values)
        cs["limitations"] = cs.get("limitations", []) + result.limitations

        def mutate(job):
            for asset in result.created:
                # 최종 결과물: 마지막 생성 단계의 시퀀스 · 포장 단계의 몽타주 · BlendSpace (deliverables). 그 밖(IK Rig · RTG · ABP 복제본)은 중간
                deliverable = (final and asset == result.values.get("asset")) or asset in result.deliverables
                bucket = "generated_assets" if deliverable else "intermediate_assets"
                if asset not in job[bucket]:
                    job[bucket].append(asset)
            job["diagnostics"] += result.diagnostics
            if "review" in result.values:
                # 변환 단계의 프레임 렌더 비교 — 뒤 단계가 실패하거나 폴백해도 Job 에 남긴다(무엇이 변환됐는지 보는 근거). 후보면 select 가 고른 후보 것으로
                job["review"] = result.values["review"]
            if "review_capture" in result.values:
                # Phase 8-2 — 대상 메시 캡처(시트 · 비교 시트 · APNG). 맨 위(소스 골격 렌더)는 그대로 두고 review.capture 에 둔다
                job["review"] = {**(job.get("review") or {}), "capture": result.values["review_capture"]}
            if "selection" in result.values:
                # Phase 8-1 — 후보 선별 근거(후보별 수치 · 벌점 · 순위 · 고른 이유). 뒤 단계가 실패해도 남긴다
                job["selection"] = result.values["selection"]
            if "timing" in result.values:
                # Phase 8-3 — 흐느적 보정 근거(신호 · 구간 · op · warp · 전후 수치)
                job["timing"] = result.values["timing"]
            for key, field in (("fix_source", "source"), ("fix_target", "target")):
                if key in result.values:
                    # Phase 8-3 — 다리 보정: 소스 골격(Blender 보고) · 대상(리타깃 뒤 측정)
                    job["fix"] = {**(job.get("fix") or {}), field: result.values[key]}
        self.store.update_job(job_id, mutate)

    def _validate(self, request: dict, values: dict) -> None:
        """생성 단계의 검증 결과를 쓰고, 생성 단계가 없으면(재사용) 그 애셋을 지금 검증한다."""
        if "asset" not in values:
            asset = values["source"]
            try:
                res = self.editor.require("validate_animation", assets=[asset], skeleton=request["target_skeleton"])
            except EditorCallError as err:
                raise from_editor_error("validate", err)
            item = res["assets"][0]
            values["reused"] = asset
            values["validation"] = {"status": item["status"], "assets": [item]}
            numeric = item.get("numeric") or {}
            values["measured"] = {k: numeric.get(k) for k in ("length", "frame_rate", "frames", "loop") if k in numeric}
            if item["status"] == "FAILED":
                raise StepFailed("VALIDATION_FAILED", "FAILED", f"reused asset {asset} fails validation")

    # ---- 유료 단계: 승인 · 장부 · 멱등 키 (§6) ----
    def _paid_step(self, job_id: str, plan: dict, provider, ctx: RunContext, j: int) -> StepResult | None:
        job = self.store.load_job(job_id)
        pending = job.get("pending")
        if pending and pending["step"] == j:
            return self._poll_step(job_id, provider, ctx, pending)
        estimate = provider.estimate(plan["request"], ctx.policy)
        cost = float(estimate["estimate_usd"])
        credits = estimate.get("credits")  # 크레딧으로 과금하는 Provider(Meshy) — 장부 · Job 비용에 같이 적는다
        approval = self.usable_approval(plan["plan_id"], provider.name)
        if approval is None:  # 게이트를 지난 뒤 다른 호출이 승인을 다 썼다
            raise StepFailed("APPROVAL_REQUIRED", "ATTEMPTS_EXHAUSTED", f"no approval left for {provider.name}")
        key = ledger_key(plan["plan_id"], self.store.paid_attempts(plan["plan_id"]) + 1)
        self.store.patch_job(job_id, pending={"key": key, "provider": provider.name, "handle": None, "step": j}, idempotency_key=key,
                             approval_id=approval["approval_id"])
        self.store.ledger_append({"kind": "reserve", "key": key, "plan_id": plan["plan_id"], "job_id": job_id, "provider": provider.name, "usd": cost,
                                  **({"credits": credits} if credits is not None else {})})
        approval["used_attempts"] += 1
        approval["committed_usd"] = round(approval["committed_usd"] + cost, 4)
        self.store.save_approval(approval)

        def reserve(jb):
            jb["cost"].update(estimated_usd=round(jb["cost"]["estimated_usd"] + cost, 4))
            if credits is not None:
                jb["cost"].setdefault("credits", {"estimated": 0, "actual": None})["estimated"] += credits
        self.store.update_job(job_id, reserve)
        try:
            result = provider.run(ctx)
        except StepFailed as failed:
            self._settle_failure(job_id, key, failed)
            self.store.patch_job(job_id, pending=None)
            raise
        if result.pending is not None:
            self.store.ledger_append({"kind": "submitted", "key": key, "handle": result.pending})
            self.store.patch_job(job_id, pending={"key": key, "provider": provider.name, "handle": result.pending, "step": j})
            return None
        self._settle(job_id, key, result)
        return result

    def _poll_step(self, job_id: str, provider, ctx: RunContext, pending: dict) -> StepResult | None:
        handle = pending.get("handle")
        if handle is None and pending.get("key"):
            # 예약은 했지만 제출 결과를 못 적었다 — 장부에 핸들이 있으면 그것을 잇고, 없으면 다시 제출하지 않는다(중복 과금 방지)
            handle = self.store.ledger_by_key().get(pending["key"], {}).get("handle")
            if handle is None:
                self.store.patch_job(job_id, pending=None)
                raise StepFailed("GENERATION_FAILED", "SUBMISSION_UNCERTAIN", f"{pending['key']} was reserved but its submission is unknown — "
                                 "not resubmitted (check the provider dashboard)", fatal=True)
            self.store.patch_job(job_id, pending={**pending, "handle": handle})
        try:
            result = provider.poll(ctx, handle)
        except StepFailed as failed:
            # 외부 작업이 실패로 끝났다 — Provider 가 환불(charged=False)이나 실제 과금을 알려 주면 장부에 반영, 모르면 예약으로 남긴다
            self._settle_failure(job_id, pending.get("key"), failed)
            self.store.patch_job(job_id, pending=None)
            raise
        self.store.patch_job(job_id, polled_at=now_iso())
        if result is None:
            return None
        self._settle(job_id, pending["key"], result)
        self.store.patch_job(job_id, pending=None)
        return result

    def _settle(self, job_id: str, key: str | None, result: StepResult) -> None:
        """실제 금액을 알려 주면 확정, 아니면 미확정(추정액이 예약으로 남는다 — 임의로 확정하지 않는다)."""
        if key is None:
            return  # 무료 단계
        self._charge(job_id, key, result.actual_cost_usd, result.actual_credits)

    def _charge(self, job_id: str, key: str, usd: float | None, credits: float | None) -> None:
        if usd is not None:
            self.store.ledger_append({"kind": "charge", "key": key, "usd": float(usd), **({"credits": credits} if credits is not None else {})})

        def mutate(job):
            cost = job["cost"]
            if usd is not None:
                cost["actual_usd"] = round((cost["actual_usd"] or 0.0) + float(usd), 4)
            else:
                cost["confirmed"] = False
            if credits is not None and "credits" in cost:
                cost["credits"]["actual"] = (cost["credits"]["actual"] or 0) + credits
        self.store.update_job(job_id, mutate)

    def _settle_failure(self, job_id: str, key: str | None, failed: StepFailed) -> None:
        """실패한 유료 단계의 장부 — 과금 없음이 확인되면(charged=False) 예약 해제, 실제 금액을 알면 확정, 그 밖에는 예약 유지(미확정)."""
        if key is None:
            return
        if failed.details.get("charged") is False:
            self.store.ledger_append({"kind": "release", "key": key})
            if failed.details.get("actual_credits") == 0:
                def refunded(job):  # Provider 가 0 크레딧(환불)을 알려 줬다 — 실제 크레딧을 0 으로 확정
                    if "credits" in job["cost"]:
                        job["cost"]["credits"]["actual"] = job["cost"]["credits"]["actual"] or 0
                self.store.update_job(job_id, refunded)
        elif failed.details.get("actual_cost_usd") is not None:
            self._charge(job_id, key, failed.details["actual_cost_usd"], failed.details.get("actual_credits"))

    # ---- 끝 ----
    def _wait(self, job_id: str, cs: dict, cand: dict, cause: str, reason: str, message: str, extra: dict) -> dict:
        return self.store.transition(job_id, WAITING_FOR_APPROVAL, f"{cause} {reason}", cursor=cs,
                                     approval_needed={"candidate": cand["index"], **extra, "reason": reason},
                                     error={"code": cause, "reason": reason, "message": message})

    def _fail(self, job_id: str, last: dict | None, attempts_exhausted: bool = False) -> dict:
        error = dict(last or {"code": "UNSUPPORTED_REQUEST", "reason": "NO_CANDIDATE", "message": "no candidate could run"})
        if attempts_exhausted:
            error["attempts_exhausted"] = True
            error["message"] = f"max_generation_attempts reached — last: {error['message']}"
        return self.store.transition(job_id, FAILED, error["code"], error=error, stage=None)

    def _succeed(self, job_id: str, plan: dict, cand: dict, cs: dict) -> dict:
        request = plan["request"]
        values = cs["values"]
        job = self.store.load_job(job_id)
        lims = [lim for lim in cand["expected_limitations"] if lim["code"] not in _MEASURED_CODES]
        lims += cs.get("limitations", [])
        lims += measured_limitations(request, values.get("measured") or {})
        if (values.get("timing") or {}).get("applied"):
            # 흐느적 보정이 길이를 바꿨다 — 요청 길이와 다른 것은 의도(TIMING_CHANGED_LENGTH 가 대신 적는다)
            lims = [lim for lim in lims if lim["code"] != "DURATION_MISMATCH"]
        final = values.get("asset")
        if final and final != f"{request['output_path']}/{request['animation_name']}":
            lims.append(limitation("OUTPUT_RENAMED", f"앞선 시도가 같은 이름을 남겨 {final} 로 만들었다", "fallback", asset=final))
        lims += fallback_limitations(job["fallback_history"], cand, plan, self.registry.manifests())
        lims = [lim for i, lim in enumerate(lims) if lim not in lims[:i]]  # 계획의 예상 한계와 단계가 다시 적은 같은 한계는 하나로
        # Phase 7 — 포장 · 연결 결과와 승격 제안(만든 애셋만 — 재사용 애셋은 옮기지 않는다)
        promotion = promotion_proposal(request, job["generated_assets"], plan.get("promotion_paths")) if job["generated_assets"] else None
        return self.store.transition(
            job_id, SUCCEEDED, f"{cand['provider']} ok", stage=None, cursor=cs, error=None, pending=None,
            reused_assets=[values["reused"]] if values.get("reused") else [], validation=values.get("validation"), limitations=lims,
            measured=values.get("measured"), package=values.get("package"), anim_bp=values.get("anim_bp"), promotion=promotion,
            selection=values.get("selection"))

    def _append(self, job_id: str, field: str, *items) -> None:
        def mutate(job):
            job.setdefault(field, [])
            job[field] += [i for i in items if i not in job[field]]
        self.store.update_job(job_id, mutate)


def measured_limitations(request: dict, measured: dict) -> list[dict]:
    out = []
    frame_rate = measured.get("frame_rate")
    length = measured.get("length")
    if request["duration_seconds"] and length is not None and abs(length - request["duration_seconds"]) > 1.0 / (frame_rate or 30.0) + 1e-6:
        out.append(limitation("DURATION_MISMATCH", f"결과 길이 {length}초 (요청 {request['duration_seconds']}초)", "validation",
                              length=length, requested=request["duration_seconds"]))
    if request["frame_rate"] and frame_rate and abs(frame_rate - request["frame_rate"]) > 0.01:
        out.append(limitation("FRAME_RATE_MISMATCH", f"결과 fps {frame_rate} (요청 {request['frame_rate']}) — 출력 fps 는 주 소스를 따른다", "validation"))
    loop = measured.get("loop")
    if request["loop"] is not None and loop is not None and loop != request["loop"]:
        out.append(limitation("LOOP_MISMATCH", f"결과 루프 {loop} (요청 {request['loop']})", "validation"))
    return out
