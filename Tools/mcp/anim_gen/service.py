"""anim-gen-mcp Tool 구현 — 봉투 생성과 저장소 · 라우터 · 실행기 연결 (지침서 §14 Phase 3 시그니처).

server.py 는 이 클래스의 메서드를 그대로 부른다. 테스트는 Store(임시 폴더) · Registry(Mock) · EditorClient(FakeEditor) 를 주입한다.
"""
from __future__ import annotations

import traceback

from . import policy as policy_mod
from .editor import EditorClient
from .envelope import AnimGenError, diag, fail, ok
from .executor import Executor
from .registry import Registry
from .request import normalize
from .router import build_plan
from .store import CANCELLED, FAILED, QUEUED, RUNNING, SUCCEEDED, TERMINAL, WAITING_FOR_APPROVAL, Store, new_id, now_iso


def _tool(fn):
    """AnimGenError → 실패 봉투, 그 밖의 예외 → INTERNAL. 성공은 (result, diagnostics) 또는 완성된 봉투."""
    name = fn.__name__

    def wrapper(self, *args, **kwargs):
        diagnostics: list[dict] = []
        try:
            out = fn(self, diagnostics, *args, **kwargs)
        except AnimGenError as err:
            return fail(name, err, diagnostics)
        except Exception as exc:  # noqa: BLE001 — Tool 은 항상 봉투를 돌려준다
            return fail(name, AnimGenError("INTERNAL", f"{type(exc).__name__}: {exc}", trace=traceback.format_exc(limit=6)), diagnostics)
        if isinstance(out, dict) and "ok" in out and "tool" in out:
            out["tool"] = name
            out["diagnostics"] = diagnostics + out.get("diagnostics", [])
            return out
        return ok(name, out, diagnostics)

    wrapper.__name__ = name
    wrapper.__doc__ = fn.__doc__
    return wrapper


class Service:
    def __init__(self, store: Store | None = None, registry: Registry | None = None, editor: EditorClient | None = None):
        self.store = store or Store()
        self.registry = registry or Registry()
        self.editor = editor or EditorClient()
        self.executor = Executor(self.store, self.registry, self.editor, self.policy)

    def policy(self) -> dict:
        return policy_mod.effective(self.store.root)

    def _plan(self, plan_id: str) -> dict:
        plan = self.store.load_plan(plan_id)
        if plan is None:
            raise AnimGenError("PLAN_NOT_FOUND", f"No plan '{plan_id}' in {self.store.root / 'plans'}", plan_id=plan_id)
        return plan

    # ---- Provider · 정책 ----
    @_tool
    def list_motion_providers(self, diagnostics, include_inactive: bool = True) -> dict:
        policy = self.policy()
        items = []
        for provider in self.registry.all():
            manifest = provider.manifest
            state = provider.state(policy)
            if not include_inactive and not state["available"]:
                continue
            capabilities = {k: v for k, v in manifest.items() if k not in ("name", "role", "phase", "description")}
            pricing = "free" if not provider.paid else ("confirmed" if provider.estimate({}).get("cost_known") else "unconfirmed")
            items.append({"name": provider.name, "role": manifest.get("role", "provider"), "phase": manifest.get("phase"),
                          "description": manifest.get("description"), "capabilities": capabilities, "pricing": pricing, "state": state})
        return {"providers": items, "router": "rule table (DevelopmentGuide §5)"}

    @_tool
    def get_generation_policy(self, diagnostics) -> dict:
        local = policy_mod.local_path(self.store.root)
        return {"effective": self.policy(),
                "sources": {"default": str(policy_mod.DEFAULT_FILE), "local": str(local), "local_exists": local.exists()},
                "ledger": self.store.ledger_totals()}

    @_tool
    def set_generation_policy(self, diagnostics, patch: dict | None = None, reset: bool = False) -> dict:
        effective = policy_mod.set_local(self.store.root, patch, reset)
        if effective["billing"]["paid_api_enabled"]:
            diagnostics.append(diag("warning", "PAID_API_ENABLED", "Paid providers can now be planned — each still needs approve_generation"))
        return {"effective": effective, "local": str(policy_mod.local_path(self.store.root))}

    # ---- 계획 · 비용 · 승인 ----
    @_tool
    def plan_motion_generation(self, diagnostics, request: dict) -> dict:
        normalized, req_diags = normalize(request)
        diagnostics += req_diags
        plan = build_plan(normalized, self.policy(), self.registry, self.editor, diagnostics)
        plan["diagnostics"] = list(diagnostics)
        self.store.save_plan(plan)
        if not plan["executable"]:
            diagnostics.append(diag("warning", "PLAN_NOT_EXECUTABLE", "No candidate can run — see excluded[]"))
        return plan

    def _estimates(self, plan: dict, policy: dict) -> list[dict]:
        mode, _ = policy_mod.resolve_mode(policy, plan["request"]["generation_policy"])
        block = policy_mod.paid_block_reason(policy, mode)
        out = []
        for cand in plan["candidates"]:
            provider = self.registry.get(cand["provider"])
            est = provider.estimate(plan["request"])
            item = {"candidate": cand["index"], "provider": provider.name, "paid": provider.paid, "cost_known": est["cost_known"],
                    "estimate_usd": est["estimate_usd"], "basis": est.get("basis")}
            if not provider.paid:
                item["verdict"] = "free"
            elif block:
                item.update(verdict="blocked", reason=block)
            elif not est["cost_known"]:
                item.update(verdict="blocked", reason="COST_UNKNOWN")
            else:
                approval = self.executor.usable_approval(plan["plan_id"], provider.name)
                if approval and approval["committed_usd"] + est["estimate_usd"] <= approval["max_cost_usd"] + 1e-9:
                    item.update(verdict="approved", approval_id=approval["approval_id"],
                                remaining_attempts=approval["max_attempts"] - approval["used_attempts"],
                                remaining_usd=round(approval["max_cost_usd"] - approval["committed_usd"], 4))
                else:
                    item["verdict"] = "needs_approval"
            out.append(item)
        for ex in plan["excluded"]:
            if self.registry.has(ex["provider"]) and self.registry.get(ex["provider"]).paid:
                out.append({"candidate": None, "provider": ex["provider"], "paid": True, "verdict": "blocked", "reason": ex["reason"] or ex["cause"],
                            "cause": ex["cause"]})
        return out

    @_tool
    def estimate_generation_cost(self, diagnostics, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        policy = self.policy()
        totals = self.store.ledger_totals()
        billing = policy["billing"]
        return {"plan_id": plan_id, "candidates": self._estimates(plan, policy), "ledger": totals,
                "caps": {"max_cost_per_job_usd": billing["max_cost_per_job_usd"], "max_total_cost_usd": billing["max_total_cost_usd"],
                         "remaining_usd": round(billing["max_total_cost_usd"] - totals["spent_usd"] - totals["reserved_usd"], 4)}}

    @_tool
    def approve_generation(self, diagnostics, plan_id: str, max_cost_usd: float, max_attempts: int = 1, provider: str | None = None) -> dict:
        plan = self._plan(plan_id)
        policy = self.policy()
        mode, _ = policy_mod.resolve_mode(policy, plan["request"]["generation_policy"])
        block = policy_mod.paid_block_reason(policy, mode)
        if block:
            raise AnimGenError("BAD_REQUEST", f"The policy blocks paid providers ({block}) — change it with set_generation_policy first",
                               reason=block)
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise AnimGenError("BAD_REQUEST", "max_attempts must be an integer in [1, 10]", reason="BAD_VALUE")
        if isinstance(max_cost_usd, bool) or not isinstance(max_cost_usd, (int, float)) or max_cost_usd <= 0:
            raise AnimGenError("BAD_REQUEST", "max_cost_usd must be a positive number", reason="BAD_VALUE")
        paid = sorted({c["provider"] for c in plan["candidates"] if c["paid"]})
        if provider is None:
            if len(paid) > 1:
                raise AnimGenError("BAD_REQUEST", f"The plan has several paid providers {paid} — name one", reason="AMBIGUOUS_PROVIDER", paid=paid)
            provider = paid[0] if paid else None
        if provider is None or provider not in paid:
            excluded_paid = [e for e in plan["excluded"] if self.registry.has(e["provider"]) and self.registry.get(e["provider"]).paid]
            raise AnimGenError("BAD_REQUEST", f"Plan {plan_id} has no runnable paid step{' for ' + provider if provider else ''}"
                               + (" — paid providers were excluded when planning; plan again after changing the policy" if excluded_paid else ""),
                               reason="NO_PAID_STEP", excluded=excluded_paid)
        est = self.registry.get(provider).estimate(plan["request"])
        if not est["cost_known"]:
            raise AnimGenError("COST_UNKNOWN", f"{provider}: the cost cannot be confirmed — not approvable (§6)", basis=est.get("basis"))
        estimate = float(est["estimate_usd"])
        billing = policy["billing"]
        totals = self.store.ledger_totals()
        if estimate > max_cost_usd + 1e-9:
            raise AnimGenError("BUDGET_EXCEEDED", f"estimate ${estimate:.2f} > max_cost_usd ${max_cost_usd:.2f}", reason="ESTIMATE_OVER_APPROVAL",
                               estimate_usd=estimate)
        if max_cost_usd > billing["max_cost_per_job_usd"] + 1e-9:
            raise AnimGenError("BUDGET_EXCEEDED", f"max_cost_usd ${max_cost_usd:.2f} > policy max_cost_per_job_usd {billing['max_cost_per_job_usd']}",
                               reason="MAX_COST_PER_JOB")
        if totals["spent_usd"] + totals["reserved_usd"] + max_cost_usd > billing["max_total_cost_usd"] + 1e-9:
            raise AnimGenError("BUDGET_EXCEEDED", f"spent+reserved ${totals['spent_usd'] + totals['reserved_usd']:.2f} + ${max_cost_usd:.2f} > "
                               f"policy max_total_cost_usd {billing['max_total_cost_usd']}", reason="MAX_TOTAL", ledger=totals)
        approval = {"approval_id": new_id("appr"), "plan_id": plan_id, "provider": provider, "max_cost_usd": float(max_cost_usd),
                    "max_attempts": max_attempts, "used_attempts": 0, "committed_usd": 0.0, "estimate_usd": estimate, "created_at": now_iso()}
        self.store.save_approval(approval)
        resumed = None
        for job in self.store.list_jobs(plan_id, limit=0):
            if job["status"] == WAITING_FOR_APPROVAL and (job.get("approval_needed") or {}).get("provider") == provider:
                self.store.transition(job["job_id"], QUEUED, f"approved {approval['approval_id']}", error=None)
                resumed = job["job_id"]
        if resumed:
            diagnostics.append(diag("info", "JOB_RESUMABLE", f"{resumed} is QUEUED — call generate_motion(plan_id) to continue"))
        return {**approval, "resumed_job_id": resumed}

    # ---- 실행 · 상태 · 취소 ----
    def _job_envelope(self, job: dict) -> dict:
        status = job["status"]
        if status in (SUCCEEDED, RUNNING):
            return ok("generate_motion", job)
        error = job.get("error") or {}
        if status == WAITING_FOR_APPROVAL:
            err = AnimGenError("APPROVAL_REQUIRED", error.get("message", "approval required"), reason=error.get("reason"), job=job)
        elif status == CANCELLED:
            err = AnimGenError("CANCELLED", "The job was cancelled", job=job)
        else:
            extra = {k: v for k, v in error.items() if k not in ("code", "message", "reason")}
            err = AnimGenError(error.get("code", "GENERATION_FAILED"), error.get("message", "generation failed"), reason=error.get("reason"),
                               job=job, **extra)
        return fail("generate_motion", err)

    @_tool
    def generate_motion(self, diagnostics, plan_id: str, save: bool = False, retry: bool = False):
        plan = self._plan(plan_id)
        if not plan["executable"]:
            first = plan["excluded"][0] if plan["excluded"] else {"cause": "UNSUPPORTED_REQUEST", "reason": "NO_CANDIDATE"}
            raise AnimGenError(first["cause"], f"Plan {plan_id} has no runnable candidate — nothing was called", reason=first.get("reason"),
                               plan_id=plan_id, excluded=plan["excluded"])
        jobs = self.store.list_jobs(plan_id, limit=0)
        latest = jobs[0] if jobs else None
        if latest and not (retry and latest["status"] in (FAILED, CANCELLED)):
            if latest["status"] in TERMINAL:
                diagnostics.append(diag("info", "JOB_EXISTS", f"{latest['job_id']} is {latest['status']} — the same plan returns the same job"
                                        + ("; pass retry=true for a new job" if latest["status"] != SUCCEEDED else "")))
                return self._job_envelope(latest)
            if latest["status"] == WAITING_FOR_APPROVAL:
                return self._job_envelope(latest)
            if latest["save"] != save:
                diagnostics.append(diag("warning", "SAVE_IGNORED", f"{latest['job_id']} continues with save={latest['save']}"))
            return self._job_envelope(self.executor.run(latest["job_id"]))
        job = self.store.create_job({
            "job_id": new_id("job"), "plan_id": plan_id, "status": QUEUED, "save": bool(save), "provider": None, "chain": None, "stage": None,
            "attempt": 0, "retry_count": 0, "cursor": None, "pending": None, "work_path": None,
            "request_summary": {k: plan["request"][k] for k in ("animation_name", "output_path", "motion_category", "description")},
            "generated_assets": [], "reused_assets": [], "intermediate_assets": [], "left_assets": [], "validation": None,
            "limitations": [], "fallback_history": [], "preserved_candidates": [], "diagnostics": [],
            "cost": {"estimated_usd": 0.0, "actual_usd": None, "confirmed": True},
            "approval_id": None, "idempotency_key": None, "error": None, "result_ignored": False,
            "previous_job_id": latest["job_id"] if latest else None,
        })
        return self._job_envelope(self.executor.run(job["job_id"]))

    @_tool
    def get_generation_status(self, diagnostics, job_id: str | None = None, plan_id: str | None = None, limit: int = 20) -> dict:
        if job_id:
            job = self.store.load_job(job_id)
            if job is None:
                raise AnimGenError("JOB_NOT_FOUND", f"No job '{job_id}'", job_id=job_id)
            if job["status"] == RUNNING and job.get("pending"):
                job = self.executor.run(job_id)  # 비동기 단계 poll
            return job
        jobs = self.store.list_jobs(plan_id, limit=limit)
        return {"jobs": [{k: j.get(k) for k in ("job_id", "plan_id", "status", "provider", "stage", "attempt", "generated_assets",
                                                "reused_assets", "error", "created_at", "updated_at")} for j in jobs]}

    @_tool
    def cancel_generation(self, diagnostics, job_id: str) -> dict:
        job = self.store.load_job(job_id)
        if job is None:
            raise AnimGenError("JOB_NOT_FOUND", f"No job '{job_id}'", job_id=job_id)
        if job["status"] in TERMINAL:
            raise AnimGenError("BAD_REQUEST", f"{job_id} is already {job['status']}", reason="ALREADY_TERMINAL", status=job["status"])
        pending = job.get("pending")
        ignored = bool(pending)
        job = self.store.transition(job_id, CANCELLED, "cancel_generation", result_ignored=ignored)
        if ignored:
            diagnostics.append(diag("warning", "RESULT_IGNORED", "A provider step was in flight — its result will be ignored; any cost stays in the ledger"))
            # 로컬 서브프로세스(blender)는 실제로 멈춘다. 외부 작업은 Provider 가 아무것도 안 한다(None)
            stopped = self.registry.get(pending["provider"]).cancel(pending["handle"]) if pending.get("handle") else None
            if stopped is not None:
                job = self.store.patch_job(job_id, cancel_effect=stopped)
                diagnostics.append(diag("info", "PROCESS_STOPPED" if stopped.get("stopped") else "PROCESS_NOT_STOPPED",
                                        f"{pending['provider']} step: {stopped}"))
        if job.get("intermediate_assets") or job.get("generated_assets"):
            diagnostics.append(diag("info", "ASSETS_LEFT", "Assets made before the cancel are kept (listed in the job)"))
        return job
