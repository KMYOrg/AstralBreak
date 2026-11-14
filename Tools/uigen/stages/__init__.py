"""파이프라인 단계 (설계 §2-2) — 각 모듈의 run(run, opts) 가 work/<run_id>/ 파일을 읽고 쓴다."""
from __future__ import annotations


class StageError(Exception):
    """단계 실패 — code 는 report · run.json 에 남는다."""

    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def ue_toolchain(run):
    """build · verify · finalize 가 쓰는 UE 도구 사슬 — codegen.default_toolchain 하나를 같이 쓴다(pytest 는 그것만 가짜로 바꾼다)."""
    from stages import codegen
    return codegen.default_toolchain(run)


def toolchain_error(exc, prefix: str = "") -> StageError:
    """core.ue.ToolchainError → StageError (코드 · 브리지 오류 그대로)."""
    msg = str(exc).split(": ", 1)[-1]
    return StageError(exc.code, f"{prefix}{msg}", **exc.details)
