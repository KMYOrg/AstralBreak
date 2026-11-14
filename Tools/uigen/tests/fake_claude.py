"""가짜 claude CLI — core/llm.py 시험용. 받은 argv · cwd · 환경 일부를 FAKE_CLAUDE_LOG(JSON 줄)에 남기고 FAKE_CLAUDE_MODE 대로 답한다.

모드: ok(기본 — FAKE_CLAUDE_OUTPUT 의 JSON 을 structured_output 으로) · max_turns · not_logged_in · no_structured · garbage · sleep · stream
"""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
                            "stdin_empty": (sys.stdin.read() == "") if sys.stdin else None}) + "\n")   # DEVNULL 이면 바로 빈 문자열
out = json.loads(os.environ.get("FAKE_CLAUDE_OUTPUT", '{"fixes": []}'))
base = {"type": "result", "session_id": "fake-session", "num_turns": 2, "total_cost_usd": 0.0123, "duration_ms": 10}
if mode == "ok":
    print(json.dumps({**base, "subtype": "success", "is_error": False, "result": json.dumps(out), "structured_output": out}))
elif mode == "stream":
    print(json.dumps({"type": "system", "subtype": "init"}))
    print(json.dumps({**base, "subtype": "success", "is_error": False, "structured_output": out}))
    print(json.dumps({"type": "system", "subtype": "task_summary"}))
elif mode == "max_turns":
    print(json.dumps({**base, "subtype": "error_max_turns", "is_error": True, "errors": ["Reached maximum number of turns (1)"]}))
    sys.exit(1)
elif mode == "not_logged_in":
    print(json.dumps({**base, "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login", "total_cost_usd": 0}))
    sys.exit(1)
elif mode == "no_structured":
    print(json.dumps({**base, "subtype": "success", "is_error": False, "result": "plain text"}))
elif mode == "garbage":
    print("not json at all")
elif mode == "sleep":
    time.sleep(10)
