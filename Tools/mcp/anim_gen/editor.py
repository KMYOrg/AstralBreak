"""에디터 플러그인 Tool 호출 — anim_graph_mcp/bridge.py 를 그대로 쓴다(HTTP 재구현 금지, §3.1).

테스트는 call 함수를 바꿔 끼운다(FakeEditor). 봉투를 해석하지 않고 넘기며, 실패 봉투는 EditorCallError 로 올린다.
봉투의 diagnostics 는 collect() 안에서만 모은다 — Job 실행기가 단계마다 감싸 Job 에 남긴다(require 는 result 만 돌려주므로).
"""
from __future__ import annotations

import contextlib
import threading
from typing import Callable, Iterator

from anim_graph_mcp import bridge


def package_path(path: str | None) -> str | None:
    """"/Game/A/B.B" · "/Game/A/B/" → "/Game/A/B" — 스켈레톤·애셋 비교는 패키지 경로로 한다."""
    if not path:
        return path
    path = path.strip().rstrip("/")
    head, sep, last = path.rpartition("/")
    if "." in last:
        last = last.split(".", 1)[0]
    return f"{head}{sep}{last}"


def asset_name(path: str) -> str:
    return package_path(path).rsplit("/", 1)[-1]


def is_under(path: str, roots: list[str]) -> bool:
    """플러그인 IsOutputPathAllowed 와 같은 규칙 — 폴더 끝에 '/' 를 붙여 접두 비교(대소문자 무시)."""
    as_dir = package_path(path).lower() + "/"
    return any(as_dir.startswith(r.lower() if r.endswith("/") else r.lower() + "/") for r in roots)


class EditorCallError(Exception):
    def __init__(self, tool: str, envelope: dict):
        error = envelope.get("error") or {}
        super().__init__(f"{tool}: {error.get('code')} {error.get('message', '')}")
        self.tool = tool
        self.envelope = envelope
        self.code = error.get("code") or "UNKNOWN"
        self.details = error.get("details") or {}

    def summary(self) -> dict:
        error = dict(self.envelope.get("error") or {})
        details = error.get("details")
        if isinstance(details, dict) and "partial" in details:
            # 부분 결과는 크다 — 검증 상태만 남긴다
            partial = details["partial"]
            error["details"] = {k: v for k, v in details.items() if k != "partial"}
            error["details"]["partial_validation"] = (partial.get("validation") or {}).get("status") if isinstance(partial, dict) else None
        return {"tool": self.tool, **error}


class EditorClient:
    def __init__(self, call: Callable[..., dict] | None = None):
        self._call = call or bridge.call
        self._local = threading.local()  # 모으는 목록은 스레드마다 — 동시에 도는 Tool 호출끼리 섞이지 않게

    def call(self, tool: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        env = self._call(tool, params, timeout=bridge.COMPILE_TIMEOUT)
        sink = getattr(self._local, "sink", None)
        if sink is not None:
            sink += [{**d, "tool": tool} for d in env.get("diagnostics") or []]
        return env

    @contextlib.contextmanager
    def collect(self) -> Iterator[list[dict]]:
        """이 스레드의 Tool 호출이 돌려준 diagnostics(성공·실패 봉투 모두)를 모은다. 항목마다 tool 이름을 붙인다. 겹치면 바깥 목록에도 넘긴다."""
        outer = getattr(self._local, "sink", None)
        sink: list[dict] = []
        self._local.sink = sink
        try:
            yield sink
        finally:
            self._local.sink = outer
            if outer is not None:
                outer += sink

    def require(self, tool: str, **params) -> dict:
        env = self.call(tool, **params)
        if not env.get("ok"):
            raise EditorCallError(tool, env)
        return env.get("result") or {}

    def status(self) -> dict | None:
        """get_editor_status 결과, 닿지 않으면 None."""
        env = self._call("get_editor_status", {}, timeout=10.0)
        return env.get("result") if env.get("ok") else None
