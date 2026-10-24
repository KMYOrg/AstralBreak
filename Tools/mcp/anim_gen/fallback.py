"""폴백 원인 분류와 한계 기록 (지침서 §7).

에디터 Tool 오류 → §7 원인. 가드·요청 오류(FATAL_EDITOR_CODES)와 에디터 연결 실패는 폴백하지 않는다.
"""
from __future__ import annotations

from .editor import EditorCallError
from .envelope import EDITOR_TRANSPORT_CODES, FATAL_EDITOR_CODES, limitation
from .providers.base import StepFailed

_RETARGET_CODES = {"IKRIG_AUTO_FAILED", "RETARGET_FAILED", "RIG_MISMATCH", "BAD_CHAINS"}


def from_editor_error(step: str, err: EditorCallError, created: list[str] | None = None) -> StepFailed:
    code = err.code
    summary = err.summary()
    kw = {"editor_error": summary, "created": created}
    if code in EDITOR_TRANSPORT_CODES:
        return StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", f"Editor unreachable during {step}: {code}", fatal=True, **kw)
    if code in FATAL_EDITOR_CODES:
        return StepFailed(code, err.details.get("reason"), f"{err.tool} refused: {code} — the request or the asset guard blocks every path",
                          fatal=True, **kw)
    if code in _RETARGET_CODES or (step == "retarget" and code == "BAD_REQUEST"):
        return StepFailed("RETARGET_FAILED", code if code != "RETARGET_FAILED" else err.details.get("reason"), f"{err.tool} failed: {code}", **kw)
    if code == "VALIDATION_FAILED" or code.startswith("EXPECT_"):
        return StepFailed("VALIDATION_FAILED", code, f"{err.tool}: validation FAILED", **kw)
    if code == "IMPORT_FAILED":
        return StepFailed("IMPORT_FAILED", err.details.get("reason"), f"{err.tool} failed", **kw)
    if code in ("ASSET_NOT_FOUND", "SKELETON_MISMATCH", "NOT_A_SEQUENCE"):
        return StepFailed("UNSUPPORTED_REQUEST", "NO_MATCH" if code == "ASSET_NOT_FOUND" else code, f"{err.tool}: {code}", **kw)
    if code == "BAD_REQUEST":
        return StepFailed("UNSUPPORTED_REQUEST", "BAD_OPERATIONS" if step == "edit" else err.details.get("reason") or "BAD_REQUEST",
                          f"{err.tool} rejected the request", **kw)
    return StepFailed("GENERATION_FAILED", code, f"{err.tool} failed: {code}", **kw)


def history_entry(candidate: dict, attempt: int | None, cause: str, reason: str | None, message: str, *, step: str | None = None,
                  skipped: bool = False, editor_error: dict | None = None, at: str | None = None) -> dict:
    return {"candidate": candidate["index"], "provider": candidate["provider"], "chain": candidate["chain"], "attempt": attempt,
            "step": step, "cause": cause, "reason": reason, "message": message, "skipped": skipped, "editor_error": editor_error, "at": at}


def missing_vs_request(failed: dict, used: dict, request: dict, manifests: dict) -> str:
    """폴백 결과가 원 요청 대비 무엇을 잃었는지 — limitations[FALLBACK_USED].missing."""
    failed_new = manifests.get(failed["provider"], {}).get("supports_new_generation")
    used_new = manifests.get(used["provider"], {}).get("supports_new_generation")
    motion_file = (request.get("motion_file") or {}).get("path")
    if motion_file and "bvh" in manifests.get(failed["provider"], {}).get("input_types", []):
        return f"요청한 motion_file({motion_file.rsplit('/', 1)[-1]}) 이 아니라 {used['provider']} 결과다"
    if failed_new and not used_new:
        return (f"요청({request['motion_category']})의 새 동작 생성 대신 기존 모션을 썼다 — {failed['provider']} 결과가 아니다")
    if manifests.get(failed["provider"], {}).get("paid"):
        return f"유료 경로 {failed['provider']}(우선순위 {failed['index'] + 1}) 결과가 아니다"
    return f"우선순위 {failed['index'] + 1} 경로({' → '.join(failed['chain'])}) 결과가 아니다"


def fallback_limitations(history: list[dict], used: dict, plan: dict, manifests: dict) -> list[dict]:
    """성공한 후보보다 앞선 후보가 실패·건너뛰기 됐으면 그 하나하나를 FALLBACK_USED 로 적는다."""
    out = []
    seen = set()
    for h in history:
        if h["candidate"] >= used["index"] or h["candidate"] in seen:
            continue
        seen.add(h["candidate"])
        failed = plan["candidates"][h["candidate"]]
        out.append(limitation("FALLBACK_USED", f"{failed['provider']} → {used['provider']}: {h['cause']}", "fallback",
                              **{"from": failed["provider"], "cause": h["cause"], "reason": h["reason"],
                                 "missing": missing_vs_request(failed, used, plan["request"], manifests)}))
    return out
