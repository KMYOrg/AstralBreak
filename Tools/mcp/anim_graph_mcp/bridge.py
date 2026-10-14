"""에디터 플러그인(AnimGraphMcp) HTTP 브리지 클라이언트.

MCP 서버와 테스트 스크립트가 공유한다. 로직은 없다 — 요청을 전달하고 봉투를 그대로 돌려준다.
오류도 봉투 모양({"ok": False, "error": {"code", "message"}})으로 정규화해 호출자가 분기 하나로 처리하게 한다.
"""
from __future__ import annotations

import json
import os
import pathlib
import uuid

import httpx

PROJECT_DIR = pathlib.Path(
    os.environ.get("ANIMGRAPH_MCP_PROJECT_DIR")
    or pathlib.Path(__file__).resolve().parents[3]
)
PORT = int(os.environ.get("ANIMGRAPH_MCP_PORT", "18765"))
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
TOKEN_FILE = PROJECT_DIR / "Saved" / "AnimGraphMcp" / "token"
TOKEN_HEADER = "X-AnimMcp-Token"

DEFAULT_TIMEOUT = 60.0
COMPILE_TIMEOUT = 180.0


def read_token() -> str:
    """플러그인이 기동 시 기록한 토큰. 파일이 없으면 빈 문자열 (서버가 401 로 알려준다)."""
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _error(code: str, message: str, **details) -> dict:
    err = {"code": code, "message": message}
    if details:
        err["details"] = details
    return {"ok": False, "tool": None, "request_id": None, "result": None, "error": err, "diagnostics": []}


def call(tool: str, params: dict | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """POST /v1/<tool>. 항상 봉투 dict 를 돌려준다 (네트워크 오류 포함)."""
    body = dict(params or {})
    body.setdefault("request_id", str(uuid.uuid4()))
    headers = {"Content-Type": "application/json"}
    token = read_token()
    if token:
        headers[TOKEN_HEADER] = token

    try:
        response = httpx.post(f"{BASE_URL}/{tool}", content=json.dumps(body), headers=headers, timeout=timeout)
    except httpx.ConnectError:
        return _error(
            "EDITOR_GONE",
            f"Cannot reach the editor bridge at {BASE_URL}. Is the Unreal Editor running with the AnimGraphMcp plugin enabled?",
            base_url=BASE_URL,
        )
    except httpx.TimeoutException:
        return _error("TIMEOUT", f"{tool} did not respond within {timeout:.0f}s", timeout=timeout)
    except httpx.HTTPError as exc:  # 기타 전송 오류
        return _error("TRANSPORT", str(exc))

    try:
        envelope = response.json()
    except ValueError:
        return _error("BAD_RESPONSE", response.text[:500], http_status=response.status_code)

    if not isinstance(envelope, dict) or "ok" not in envelope:
        return _error("BAD_RESPONSE", "Response is not an AnimGraphMcp envelope", http_status=response.status_code)
    envelope.setdefault("http_status", response.status_code)
    return envelope
