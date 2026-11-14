"""UE 도구 사슬 — 에디터 브리지 · 종료 · 프로세스 확인 · UBT 빌드 · 에디터 기동 (설계 §2-1 · §2-3).

CLAUDE.md 의 에디터 주기를 코드로 옮긴 것이다: quit_editor(discard 는 /Game/_AutoGen/ 만) → 프로세스 소멸 확인 → Build.bat →
'Result: Succeeded' 줄 확인 → DebugGame 에디터 백그라운드 기동 → 브리지 대기 + settle 초. 값은 pipeline.yaml 의 editor · build 절.
단계 코드는 이 클래스의 메서드만 부른다 — pytest 는 같은 메서드를 가진 가짜로 바꾼다(에디터 · UBT 없이).
"""
from __future__ import annotations

import csv
import io
import pathlib
import re
import subprocess
import sys
import time

from core.config import REPO_ROOT
from core.proc import pid_alive

sys.path.insert(0, str(REPO_ROOT / "Tools" / "mcp"))
from editor_bridge import bridge  # noqa: E402

GONE_CODES = ("EDITOR_GONE", "TIMEOUT", "TRANSPORT")
RESULT_RE = re.compile(r"^Result:\s*(.+?)\s*$", re.MULTILINE)
ERROR_LINE_RE = re.compile(r"(: (fatal )?error\b|\berror [A-Z]+\d+:|^ERROR:|UnrealHeaderTool failed)", re.IGNORECASE)

# Windows 프로세스 생성 플래그 — 에디터는 파이프라인 프로세스보다 오래 산다
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


class ToolchainError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


class Toolchain:
    def __init__(self, cfg: dict, log=print):
        self.editor = cfg["editor"]
        self.build_cfg = cfg["build"]
        self.log = log

    # -- 브리지 ---------------------------------------------------------------------------------------------------------

    def _call(self, tool: str, params: dict | None = None, timeout: float = 180.0) -> dict:
        return bridge.call(tool, params or {}, timeout=timeout)

    def editor_status(self) -> dict | None:
        """떠 있으면 get_editor_status 결과, 브리지가 없으면 None. 그 밖의 오류(UNAUTHORIZED — 에디터 두 개 등)는 예외."""
        env = self._call("get_editor_status", timeout=5.0)
        if env.get("ok"):
            return env["result"]
        err = env.get("error") or {}
        if err.get("code") in GONE_CODES:
            return None
        raise ToolchainError("BRIDGE_ERROR", f"get_editor_status: {err.get('code')} {err.get('message', '')}", error=err)

    def call(self, tool: str, params: dict | None = None, timeout: float = 180.0) -> dict:
        """WidgetMcp 등 브리지 Tool 을 부르고 result 를 돌려준다. 실패하면 ToolchainError(code = 브리지 오류 코드, details.error = 오류 전체).
        봉투의 diagnostics(경고 등)가 있으면 result['diagnostics'] 로 붙인다."""
        env = self._call(tool, params, timeout)
        if not env.get("ok"):
            err = env.get("error") or {}
            raise ToolchainError(err.get("code") or "BRIDGE_ERROR", f"{tool}: {err.get('message', '')}", error=err, tool=tool)
        result = env.get("result") or {}
        if env.get("diagnostics"):
            result = {**result, "diagnostics": env["diagnostics"]}
        return result

    def list_bind_widgets(self, class_path: str) -> list[dict]:
        env = self._call("list_bind_widgets", {"class": class_path}, timeout=60.0)
        if not env.get("ok"):
            err = env.get("error") or {}
            raise ToolchainError("LIST_BIND_WIDGETS", f"{class_path}: {err.get('code')} {err.get('message', '')}", error=err)
        return env["result"]["bindings"]

    def quit_editor(self) -> dict:
        params = {"discard_dirty": True, "discard_only_under": list(self.editor["quit_discard_only_under"])}
        env = self._call("quit_editor", params, timeout=180.0)
        if not env.get("ok"):
            err = env.get("error") or {}
            raise ToolchainError("QUIT_REFUSED", f"quit_editor: {err.get('code')} {err.get('message', '')}", error=err)
        return env["result"]

    def wait_exit(self, pid: int | None) -> float:
        """브리지가 사라지고 pid 가 없어질 때까지(wait_for_exit.py 와 같은 판정)."""
        t0 = time.monotonic()
        deadline = t0 + float(self.editor["exit_wait_s"])
        while time.monotonic() < deadline:
            gone = self.editor_status() is None
            if gone and not (pid and pid_alive(pid)):
                return round(time.monotonic() - t0, 1)
            time.sleep(3.0)
        raise ToolchainError("EXIT_TIMEOUT", f"editor (pid {pid}) still alive after {self.editor['exit_wait_s']}s")

    # -- 프로세스 -------------------------------------------------------------------------------------------------------

    def editor_processes(self) -> list[dict]:
        """떠 있는 UnrealEditor*.exe — tasklist 를 직접 부른다(Git Bash 경로 변환을 피함 · OEM 코드 페이지)."""
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor*", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                                 encoding="oem", errors="replace", timeout=30, stdin=subprocess.DEVNULL).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToolchainError("TASKLIST", str(exc)) from exc
        procs = []
        for row in csv.reader(io.StringIO(out or "")):
            if len(row) >= 2 and row[0].lower().startswith("unrealeditor") and row[1].isdigit():
                procs.append({"image": row[0], "pid": int(row[1])})
        return procs

    # -- 빌드 -----------------------------------------------------------------------------------------------------------

    def build(self, log_path: pathlib.Path) -> dict:
        """Build.bat <target> <platform> <config> -Project=… + args. 성공 = 종료 코드 0 이고 'Result: Succeeded' 줄."""
        b = self.build_cfg
        cmd = [b["bat"], b["target"], b["platform"], b["configuration"], f"-Project={self.editor['project']}", *b.get("args", [])]
        log_path = pathlib.Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        self.log(f"codegen: build — {' '.join(cmd[1:])}")
        try:
            with open(log_path, "wb") as f:
                code = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=float(b["timeout_s"])).returncode
        except subprocess.TimeoutExpired:
            return {"ok": False, "exit_code": None, "result_line": None, "duration_s": round(time.monotonic() - t0, 1), "command": cmd,
                    "errors": [f"build timed out after {b['timeout_s']}s"]}
        text = log_path.read_text(encoding="utf-8", errors="replace")
        results = RESULT_RE.findall(text)
        result = results[-1] if results else None
        errors = [ln.strip() for ln in text.splitlines() if ERROR_LINE_RE.search(ln)][:30]
        ok = code == 0 and bool(result) and result.startswith("Succeeded")
        return {"ok": ok, "exit_code": code, "result_line": f"Result: {result}" if result else None,
                "duration_s": round(time.monotonic() - t0, 1), "command": cmd, "errors": errors}

    # -- 에디터 기동 ----------------------------------------------------------------------------------------------------

    def launch_editor(self, log_path: pathlib.Path) -> int:
        """에디터를 떼어 내 띄운다(표준 입출력은 로그 파일 — 부른 쪽 파이프를 물지 않게). pid 를 돌려준다."""
        e = self.editor
        cmd = [e["exe"], e["project"], *e.get("args", [])]
        log_path = pathlib.Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_path, "wb")  # noqa: SIM115 — 에디터가 들고 있는다
        base = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            for flags in ((base | _CREATE_BREAKAWAY_FROM_JOB, base) if sys.platform == "win32" else (0,)):
                try:
                    proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, close_fds=True, creationflags=flags)
                    break
                except OSError:
                    if flags == base:
                        raise
            else:  # pragma: no cover
                raise ToolchainError("LAUNCH", "could not start the editor")
        except OSError as exc:
            raise ToolchainError("LAUNCH", f"{cmd[0]}: {exc}") from exc
        finally:
            f.close()
        self.log(f"ue: editor launched (pid {proc.pid}) — log {log_path.as_posix()}")
        return proc.pid

    def wait_bridge(self, pid: int | None = None) -> float:
        """브리지가 응답할 때까지(bridge_wait_s · bridge_poll_s) + settle_s. 그 사이 에디터가 죽으면 바로 실패."""
        e = self.editor
        t0 = time.monotonic()
        deadline = t0 + float(e["bridge_wait_s"])
        while time.monotonic() < deadline:
            if self.editor_status() is not None:
                ready = round(time.monotonic() - t0, 1)
                self.log(f"ue: bridge ready after {ready}s — settling {e['settle_s']}s")
                time.sleep(float(e["settle_s"]))
                return ready
            if pid and not pid_alive(pid):
                raise ToolchainError("EDITOR_DIED", f"editor pid {pid} exited before the bridge came up")
            time.sleep(float(e["bridge_poll_s"]))
        raise ToolchainError("BRIDGE_TIMEOUT", f"bridge not ready after {e['bridge_wait_s']}s")
