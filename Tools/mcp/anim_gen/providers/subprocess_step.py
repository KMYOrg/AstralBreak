"""로컬 서브프로세스 단계 공통 — blender(Phase 4) · local_ai(Phase 5) (지침서 §3.4 · §16-14).

run 이 Popen 으로 자식을 띄우고 pending 핸들을 돌려주면, get_generation_status 의 poll 이 끝났는지(report 파일) · 기한을 본다.
게임 스레드 · 백그라운드 스레드는 쓰지 않는다. 자식은 stdin 을 막고 출력을 로그 파일로 보낸다(anim-gen-mcp 는 stdio MCP 라 상속하면
프로토콜이 깨진다), 키 · 토큰 이름의 환경 변수는 넘기지 않는다. 취소는 프로세스를 실제로 끝낸다(외부 API 의 '결과 무시'와 다르다).
서버가 다시 뜨면 프로세스 핸들이 없어 report 파일로만 판정하고, 기한까지 report 가 없으면 멈추지 못한 채 TIMEOUT 으로 적는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

from ..store import PROJECT_DIR
from .base import Provider, StepFailed

DEFAULT_TIMEOUT_S = 300
LOG_TAIL_LINES = 3
_SECRET_ENV = re.compile(r"(API_KEY|APIKEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)


def import_roots(settings: dict | None) -> list[pathlib.Path]:
    """get_editor_status.generation.import_source_roots — ini 가 유일한 기준(§3.1-6). 상대 경로는 프로젝트 기준."""
    raw = ((settings or {}).get("generation") or {}).get("import_source_roots") or []
    return [p if p.is_absolute() else PROJECT_DIR / p for p in map(pathlib.Path, raw)]


def is_under(path: str | os.PathLike, root: str | os.PathLike) -> bool:
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:  # 다른 드라이브
        return False


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def child_env(extra: dict | None = None) -> dict:
    """키 · 토큰 이름의 환경 변수는 넘기지 않는다(§16-16). extra 는 그 뒤에 더한다(같은 규칙으로 거른다)."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}
    env.update({k: v for k, v in (extra or {}).items() if not _SECRET_ENV.search(k)})
    return env


def launch(cmd: list[str], **kwargs):
    """실제 서브프로세스 — 테스트는 Provider 에 popen 을 주거나 이 함수를 막는다."""
    return subprocess.Popen(cmd, **kwargs)


def read_json(path: str) -> dict | None:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class SubprocessProvider(Provider):
    """report.json 을 쓰는 자식 프로세스 하나를 돌리는 단계. 하위 클래스는 명령 · 인자와 report 해석만 정한다."""

    label = "process"        # 메시지 속 이름 (Blender · Kimodo)
    exit_prefix = "PROCESS"  # 보고 없이 끝난 종료 코드의 reason 접두사 (BLENDER_EXIT_3)

    def __init__(self, manifest: dict, *, popen=None, clock=None):
        super().__init__(manifest)
        self._popen = popen
        self._clock = clock or time.time
        self._procs: dict[str, object] = {}  # 출력 폴더 → Popen. 이 서버 프로세스 안에서만 — 다시 뜨면 report 파일로 판정한다

    @staticmethod
    def timeout_s(policy: dict | None) -> float:
        return float(((policy or {}).get("execution") or {}).get("subprocess_timeout_seconds", DEFAULT_TIMEOUT_S))

    def start(self, cmd: list[str], out_dir: pathlib.Path, log: pathlib.Path, policy: dict | None, env: dict, *, extra_timeout_s: float = 0.0,
              **handle) -> dict:
        """자식을 띄우고 pending 핸들을 만든다. handle 에는 report · log 경로와 하위 클래스가 poll 때 쓸 값을 넣는다. 기한 = 정책 + extra_timeout_s
        (한 실행이 일을 여러 번 하는 단계 — Kimodo 후보 · 2차 생성)."""
        kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "cwd": str(out_dir), "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        with log.open("wb") as out:
            try:
                proc = (self._popen or launch)(cmd, stdout=out, **kwargs)
            except OSError as exc:
                raise StepFailed("PROVIDER_UNAVAILABLE", "LAUNCH_FAILED", f"could not start {self.label}: {exc}") from None
        timeout = self.timeout_s(policy) + extra_timeout_s
        started = self._clock()
        handle = {"pid": proc.pid, "started_at": started, "deadline": started + timeout, "timeout_s": timeout, "dir": out_dir.as_posix(),
                  "log": log.as_posix(), **handle}
        self._procs[handle["dir"]] = proc
        return handle

    def await_report(self, handle: dict) -> dict | None:
        """끝났으면 report(dict), 아직이면 None. 기한 초과 · 재시작 뒤 기한 초과 · 보고 없이 종료는 StepFailed."""
        key = handle["dir"]
        proc = self._procs.get(key)
        code = proc.poll() if proc is not None else None
        if proc is not None and code is None:
            if self._clock() > handle["deadline"]:
                self._stop(key)
                raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"{self.label} ran over {handle['timeout_s']:.0f}s and was stopped{self.tail(handle)}")
            return None
        report = read_json(handle["report"])
        if proc is None and report is None:
            # 서버가 다시 떴다 — 이 프로세스의 핸들이 없어 끝났는지는 report 로만 안다
            if self._clock() <= handle["deadline"]:
                return None
            raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"no {self.label} report by the deadline and the process (pid {handle['pid']}) is not "
                             f"tracked after a server restart — it was not stopped{self.tail(handle)}")
        self._procs.pop(key, None)
        if report is None:
            raise StepFailed("GENERATION_FAILED", f"{self.exit_prefix}_EXIT_{code}", f"{self.label} exited ({code}) without a report{self.tail(handle)}")
        return report

    def cancel(self, handle: dict) -> dict | None:
        pid = handle.get("pid")
        if handle.get("dir") not in self._procs:
            return {"stopped": False, "reason": "NOT_TRACKED", "pid": pid}
        return {"stopped": self._stop(handle["dir"]), "pid": pid}

    def _stop(self, key: str) -> bool:
        proc = self._procs.pop(key, None)
        if proc is None or proc.poll() is not None:
            return False
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return True

    @staticmethod
    def tail(handle: dict) -> str:
        try:
            lines = [ln for ln in pathlib.Path(handle["log"]).read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        except OSError:
            return f" (log: {handle['log']})"
        tail = " | ".join(lines[-LOG_TAIL_LINES:])
        return f" (log: {handle['log']}{' — ' + tail if tail else ''})"
