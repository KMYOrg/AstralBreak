"""에디터 브리지가 응답할 때까지 폴링 — 에디터 기동 직후 스모크 테스트 앞에 쓴다.

    Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_bridge.py [timeout_sec=420] [interval_sec=10]
"""
from __future__ import annotations

import sys
import time

from anim_graph_mcp import bridge


def main() -> int:
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        env = bridge.call("get_editor_status", timeout=5.0)
        if env.get("ok"):
            r = env["result"]
            print(f"BRIDGE_READY after {attempt} attempts: engine {r.get('engine_version')} project {r.get('project')} "
                  f"port {r.get('port')} tools {[t['name'] for t in r.get('tools', [])]}")
            return 0
        code = env.get("error", {}).get("code")
        print(f"[{attempt}] not ready ({code}); retry in {interval:.0f}s", flush=True)
        time.sleep(interval)
    print("BRIDGE_TIMEOUT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
