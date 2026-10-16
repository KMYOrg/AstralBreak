"""quit_editor 뒤 에디터 프로세스가 사라질 때까지 폴링 — 재시작 recheck 앞에 쓴다. (taskkill 절차 대체, Phase 6-2)

    Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_exit.py [pid] [timeout_sec=180] [interval_sec=5]

pid 를 주지 않으면 먼저 get_editor_status 로 읽는다 (브리지가 이미 죽었으면 EXITED 로 간주).
종료 판정 = 브리지가 EDITOR_GONE 이고 (pid 를 알면) tasklist 에 그 pid 가 없다.
tasklist 는 Python subprocess 로 직접 부른다 — Git Bash 의 MSYS 경로 변환(//FI) 문제를 피한다.
"""
from __future__ import annotations

import subprocess
import sys
import time

from anim_graph_mcp import bridge


def pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f",\"{pid}\"," in out


def wait_for_exit(pid: int | None, timeout: float, interval: float) -> bool:
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        env = bridge.call("get_editor_status", timeout=5.0)
        bridge_gone = not env.get("ok") and env.get("error", {}).get("code") in ("EDITOR_GONE", "TIMEOUT", "TRANSPORT")
        alive = pid_alive(pid) if pid else False
        if bridge_gone and not alive:
            print(f"EXITED after {attempt} attempts (pid {pid})")
            return True
        print(f"[{attempt}] bridge {'gone' if bridge_gone else 'up'} · pid {pid} {'alive' if alive else 'gone'}; retry in {interval:.0f}s", flush=True)
        time.sleep(interval)
    print("EXIT_TIMEOUT")
    return False


def main() -> int:
    pid = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 180.0
    interval = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    if pid is None:
        env = bridge.call("get_editor_status", timeout=5.0)
        if env.get("ok"):
            pid = int(env["result"].get("process_id") or 0) or None
        else:
            print(f"bridge not reachable ({env.get('error', {}).get('code')}); nothing to wait for")
            return 0
    return 0 if wait_for_exit(pid, timeout, interval) else 1


if __name__ == "__main__":
    sys.exit(main())
