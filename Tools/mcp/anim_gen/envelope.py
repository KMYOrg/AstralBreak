"""응답 봉투와 오류 코드 — 에디터 플러그인과 같은 모양 {ok, tool, request_id, result, error, diagnostics} (지침서 §3.2).

세부 사유는 기존 Tool 처럼 error.details.reason 에 둔다.
"""
from __future__ import annotations

import uuid

# §7 폴백 원인 분류 (개정 6: COST_UNKNOWN 추가)
CAUSES = (
    "PROVIDER_UNAVAILABLE", "AUTHENTICATION_FAILED", "APPROVAL_REQUIRED", "BUDGET_EXCEEDED", "COST_UNKNOWN", "RATE_LIMITED",
    "LICENSE_RESTRICTED", "UNSUPPORTED_REQUEST", "GENERATION_FAILED", "IMPORT_FAILED", "RETARGET_FAILED", "VALIDATION_FAILED",
    "QUALITY_INSUFFICIENT",
)

# 다른 Provider 로 넘어가지 않고 Job 을 끝내는 에디터 가드 코드 — 요청·보호 문제라 어느 경로든 같다 (§7)
FATAL_EDITOR_CODES = frozenset({
    "UNEXPECTED_DIRTY", "OUTPUT_PATH_NOT_ALLOWED", "ASSET_EXISTS", "ASSET_PROTECTED", "IMPORT_SOURCE_NOT_ALLOWED",
})
# 에디터 자체에 닿지 못함 — 모든 경로가 리타깃·저장에 에디터를 쓰므로 중단
EDITOR_TRANSPORT_CODES = frozenset({"EDITOR_GONE", "TIMEOUT", "TRANSPORT", "BAD_RESPONSE", "UNAUTHORIZED"})


class AnimGenError(Exception):
    """Tool 이 봉투의 error 로 돌려줄 오류. reason · details 는 error.details 에 들어간다."""

    def __init__(self, code: str, message: str, reason: str | None = None, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)
        if reason:
            self.details["reason"] = reason

    @property
    def reason(self) -> str | None:
        return self.details.get("reason")

    def to_error(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.details:
            err["details"] = self.details
        return err


def diag(level: str, code: str, message: str, **extra) -> dict:
    item = {"level": level, "code": code, "message": message}
    item.update(extra)
    return item


def ok(tool: str, result, diagnostics: list[dict] | None = None) -> dict:
    return {"ok": True, "tool": tool, "request_id": str(uuid.uuid4()), "result": result, "error": None,
            "diagnostics": list(diagnostics or [])}


def fail(tool: str, error: AnimGenError, diagnostics: list[dict] | None = None) -> dict:
    return {"ok": False, "tool": tool, "request_id": str(uuid.uuid4()), "result": None, "error": error.to_error(),
            "diagnostics": list(diagnostics or [])}


def limitation(code: str, message: str, source: str, **extra) -> dict:
    """limitations[] 항목 {code, message, source} (개정 6 §3.2). source = router · provider · direct_key · validation · fallback."""
    item = {"code": code, "message": message, "source": source}
    item.update(extra)
    return item
