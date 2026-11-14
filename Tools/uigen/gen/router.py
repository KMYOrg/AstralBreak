"""generate_ui_asset 라우터 (설계 §7) — 에셋마다 백엔드를 고른다.

순서: spec 에셋의 provenance(요청) → routing.yaml 의 그 종류 primary → fallback. pipeline.yaml backends.allowed 밖은 건너뛴다.
1a 는 allowed = [procedural] 이다. 요청한 provenance 가 허용 밖이면 대체하지 않고 실패한다 — 사람이 적은 출처를 몰래 바꾸지 않는다.
"""
from __future__ import annotations


class RouteError(ValueError):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def choose_backend(asset: dict, routing: dict, allowed: list[str]) -> str:
    requested = asset.get("provenance")
    if requested:
        if requested not in allowed:
            raise RouteError("BACKEND_NOT_ALLOWED", f"asset '{asset['asset_id']}' asks for '{requested}', allowed: {allowed}",
                             asset=asset["asset_id"], requested=requested, allowed=allowed)
        return requested
    rule = (routing.get("kinds") or {}).get(asset.get("kind")) or {}
    for backend in [rule.get("primary"), *(rule.get("fallback") or [])]:
        if backend and backend in allowed:
            return backend
    raise RouteError("NO_ALLOWED_BACKEND", f"asset '{asset['asset_id']}' ({asset.get('kind')}): no allowed backend in {rule}",
                     asset=asset["asset_id"], kind=asset.get("kind"), allowed=allowed)
