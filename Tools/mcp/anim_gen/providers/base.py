"""Provider 인터페이스 (지침서 §4).

Provider 는 계획에서 자기 단계를 만들고(plan_*), 실행에서 자기 단계를 돈다(run). 단계 사슬의 조립·승인·장부·폴백은
router · executor 가 맡는다. 비동기 Provider 는 run 이 pending 을 돌려주고 executor 가 poll 로 이어 간다(§3.4).
"""
from __future__ import annotations

import dataclasses
import os

from ..envelope import limitation


class PlanBlocked(Exception):
    """계획 단계에서 이 후보를 만들 수 없다 → excluded[{provider, cause, reason}]."""

    def __init__(self, cause: str, reason: str, message: str, **details):
        super().__init__(message)
        self.cause = cause
        self.reason = reason
        self.message = message
        self.details = details


class StepFailed(Exception):
    """실행 단계 실패. cause 는 §7 분류, fatal 이면 폴백하지 않고 Job 을 끝낸다."""

    def __init__(self, cause: str, reason: str | None, message: str, *, fatal: bool = False, retryable: bool = False,
                 editor_error: dict | None = None, created: list[str] | None = None, **details):
        super().__init__(message)
        self.cause = cause
        self.reason = reason
        self.message = message
        self.fatal = fatal
        self.retryable = retryable
        self.editor_error = editor_error
        self.created = list(created or [])
        self.details = details


@dataclasses.dataclass
class StepResult:
    values: dict = dataclasses.field(default_factory=dict)       # 다음 단계로 넘길 값 (asset · skeleton · mesh · file · validation · measured)
    created: list[str] = dataclasses.field(default_factory=list)  # 이 단계가 만든 애셋
    limitations: list[dict] = dataclasses.field(default_factory=list)
    diagnostics: list[dict] = dataclasses.field(default_factory=list)
    pending: dict | None = None                                   # 비동기 제출 핸들 (외부 작업 id 등)
    actual_cost_usd: float | None = None                          # Provider 가 알려 준 실제 금액 (없으면 미확정)


@dataclasses.dataclass
class PlanContext:
    editor: object        # EditorClient
    editor_ok: bool       # 계획 시점에 에디터에 닿았는가 — 아니면 단계를 미해결로 둔다
    request: dict
    diagnostics: list
    settings: dict | None = None  # get_editor_status 결과 (generation.output_paths · import_source_roots) — 에디터가 없으면 None


@dataclasses.dataclass
class RunContext:
    editor: object        # EditorClient
    job_id: str
    request: dict
    step: dict
    values: dict
    work_path: str        # <output_path>/Work/<job_id>/A<attempt>
    output_folder: str    # 이 단계의 결과 폴더 (최종이면 output_path, 아니면 work_path)
    output_name: str      # 이 단계의 결과 애셋 이름
    is_final: bool
    save: bool
    attempt: int
    policy: dict | None = None  # 실행 시점의 정책 (경로 · 타임아웃)


class Provider:
    implemented = True

    def __init__(self, manifest: dict):
        self.manifest = manifest
        self.name = manifest["name"]

    @property
    def paid(self) -> bool:
        return bool(self.manifest.get("paid"))

    @property
    def generates(self) -> bool:
        return bool(self.manifest.get("supports_new_generation"))

    def installed(self, policy: dict) -> tuple[bool, str | None]:
        return True, None

    def state(self, policy: dict) -> dict:
        """설치·인증·라이선스·가용 상태 — 매니페스트가 아니라 지금 계산한다. 키 값은 내보내지 않는다(있는지만)."""
        installed, note = self.installed(policy)
        auth_env = self.manifest.get("auth_env")
        auth = {"env": auth_env, "present": bool(os.environ.get(auth_env))} if auth_env else None
        license_status = self.manifest.get("license", "ok")
        cause = reason = None
        if not self.implemented:
            cause, reason = "PROVIDER_UNAVAILABLE", "NOT_IMPLEMENTED"
        elif not installed:
            cause, reason = "PROVIDER_UNAVAILABLE", "NOT_INSTALLED"
        elif license_status != "ok":
            cause, reason = "LICENSE_RESTRICTED", f"LICENSE_{license_status.upper()}"
        elif auth is not None and not auth["present"]:
            cause, reason = "AUTHENTICATION_FAILED", "API_KEY_MISSING"
        return {"implemented": self.implemented, "installed": installed, "install_note": note, "auth": auth,
                "license": license_status, "available": cause is None,
                "unavailable_reason": {"cause": cause, "reason": reason} if cause else None}

    def estimate(self, request: dict) -> dict:
        """{cost_known, estimate_usd, basis}. 무료 Provider 는 0. 유료 Provider 는 확인된 가격표가 있을 때만 cost_known."""
        if self.paid:
            return {"cost_known": False, "estimate_usd": None, "basis": "pricing not confirmed"}
        return {"cost_known": True, "estimate_usd": 0.0, "basis": "free"}

    # AI 계열(새 동작 생성)만 쓴다: 생성 단계 계획 · 실행
    def plan_generate(self, request: dict, pctx) -> dict:
        return {"step": "generate", "provider": self.name, "tool": None,
                "inputs": {k: request.get(k) for k in ("description", "duration_seconds", "frame_rate", "loop", "motion_category")}}

    def run(self, ctx: RunContext) -> StepResult:
        raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_IMPLEMENTED", f"{self.name} has no implementation yet")

    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        """비동기 단계: 끝났으면 StepResult, 아직이면 None."""
        raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_IMPLEMENTED", f"{self.name} has no asynchronous step")

    def cancel(self, handle: dict) -> dict | None:
        """Job 취소 때 진행 중인 단계를 멈춘다. 기본은 아무것도 안 한다(외부 작업은 결과만 무시 — §3.4). 멈췄으면 그 기록."""
        return None


def wrap_limitations(items, source: str) -> list[dict]:
    """C++ Tool 이 돌려준 문자열 한계를 {code, message, source} 로 감싼다."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append({"source": source, **item})
        else:
            out.append(limitation("EDIT_LIMITATION", str(item), source))
    return out
