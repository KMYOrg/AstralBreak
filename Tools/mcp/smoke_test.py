"""브리지 스모크 테스트 — 에디터가 떠 있을 때 바깥 Python 에서 실행.

    Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py [asset_path]

확인 항목: 상태 조회(토큰 면제) · 토큰 없는 호출의 401 · 토큰 있는 조회 · 같은 request_id 재전송의 캐시 응답 · 잘못된 경로의 404.
"""
from __future__ import annotations

import json
import sys
import uuid

import httpx

from anim_graph_mcp import bridge


def show(title: str, envelope: dict) -> None:
    print(f"\n== {title}")
    print(json.dumps(envelope, indent=2, ensure_ascii=False)[:2000])


def main() -> int:
    asset = sys.argv[1] if len(sys.argv) > 1 else "/Game/Animation/Hero/ABP_Hero_Base"
    failures = 0

    status = bridge.call("get_editor_status")
    show("get_editor_status", status)
    if not status.get("ok"):
        print("\n[FAIL] 에디터 브리지에 닿지 않음 — 이후 검사 생략")
        return 1

    # 토큰 없는 호출 → 401 UNAUTHORIZED (토큰이 요구되는 설정일 때)
    r = httpx.post(f"{bridge.BASE_URL}/get_anim_blueprint_info", json={"asset_path": asset}, timeout=10)
    print(f"\n== no-token call: HTTP {r.status_code}")
    token_required = status["result"].get("token_required", True)
    if token_required and r.status_code != 401:
        print("[FAIL] 토큰 없는 호출이 401 이 아님")
        failures += 1

    info = bridge.call("get_anim_blueprint_info", {"asset_path": asset})
    show(f"get_anim_blueprint_info {asset}", info)
    if not info.get("ok"):
        print("[FAIL] 조회 실패")
        failures += 1

    # request_id 멱등 — 같은 id 두 번 → 두 번째는 캐시 (내용 동일)
    rid = str(uuid.uuid4())
    a = bridge.call("get_anim_blueprint_info", {"asset_path": asset, "request_id": rid})
    b = bridge.call("get_anim_blueprint_info", {"asset_path": asset, "request_id": rid})
    a.pop("http_status", None); b.pop("http_status", None)
    print(f"\n== idempotent replay identical: {a == b}")
    if a != b:
        failures += 1

    missing = bridge.call("get_anim_blueprint_info", {"asset_path": "/Game/Does/Not/Exist"})
    show("missing asset", missing)
    if missing.get("ok") or missing.get("error", {}).get("code") != "ASSET_NOT_FOUND":
        print("[FAIL] 없는 애셋이 ASSET_NOT_FOUND 가 아님")
        failures += 1

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
