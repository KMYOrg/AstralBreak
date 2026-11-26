"""가짜 claude CLI — core/llm.py 시험용. 받은 argv · cwd · 환경 일부를 FAKE_CLAUDE_LOG(JSON 줄)에 남기고 FAKE_CLAUDE_MODE 대로 답한다.

출력 모양은 1b-1 실제 호출 채록(claude 2.1.325, 설계 §11 '1b-1')을 따른다.
모드: ok(기본 — FAKE_CLAUDE_OUTPUT 의 JSON 을 structured_output 으로) · max_turns · not_logged_in · no_structured · garbage · sleep · stream ·
      budget(예산 끊김) · api_error(최상위 조합자 400) · bad_schema_arg(--json-schema 인자 오류 — stderr 만)
`--version` · `auth status` 는 FAKE_CLAUDE_VERSION · FAKE_CLAUDE_AUTH(JSON — 기본은 구독 로그인, 이메일 포함)로 답한다.
"""
import json
import os
import sys
import time

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print(f"{os.environ.get('FAKE_CLAUDE_VERSION', '2.1.325')} (Claude Code)")
    sys.exit(0)
if argv[:2] == ["auth", "status"]:
    auth = json.loads(os.environ.get("FAKE_CLAUDE_AUTH", "{}") or "{}")
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "email": "someone@example.com",
                      "orgId": "org-fake", "subscriptionType": "max", **auth}, indent=2))
    sys.exit(0)

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
                            "stdin_empty": (sys.stdin.read() == "") if sys.stdin else None}) + "\n")   # DEVNULL 이면 바로 빈 문자열
out = json.loads(os.environ.get("FAKE_CLAUDE_OUTPUT", '{"fixes": []}'))
if os.environ.get("FAKE_CLAUDE_OUTPUTS"):   # 연속 응답 — n 번째 호출에 n 번째 출력(넘치면 마지막), 카운터는 FAKE_CLAUDE_COUNTER 파일
    outs = json.loads(os.environ["FAKE_CLAUDE_OUTPUTS"])
    counter = os.environ["FAKE_CLAUDE_COUNTER"]
    n = int(open(counter, encoding="utf-8").read() or 0) if os.path.exists(counter) else 0
    with open(counter, "w", encoding="utf-8") as f:
        f.write(str(n + 1))
    out = outs[min(n, len(outs) - 1)]
usage = {"claude-haiku-5-5": {"inputTokens": 2, "outputTokens": 74, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 7015, "thinkingTokens": 0,
                              "costUSD": 0.0123}}
base = {"type": "result", "session_id": "fake-session", "num_turns": 2, "total_cost_usd": 0.0123, "duration_ms": 10, "modelUsage": usage,
        "credential_expires_at": "2099-01-01T00:00:00Z"}
if mode == "ok":
    print(json.dumps({**base, "subtype": "success", "is_error": False, "terminal_reason": "completed", "result": json.dumps(out), "structured_output": out}))
elif mode == "stream":
    print(json.dumps({"type": "system", "subtype": "init"}))
    print(json.dumps({**base, "subtype": "success", "is_error": False, "terminal_reason": "completed", "structured_output": out}))
    print(json.dumps({"type": "system", "subtype": "task_summary"}))
elif mode == "max_turns":
    print(json.dumps({**base, "subtype": "error_max_turns", "is_error": True, "errors": ["Reached maximum number of turns (1)"]}))
    sys.exit(1)
elif mode == "budget":
    print(json.dumps({**base, "subtype": "error_max_budget_usd", "is_error": True, "terminal_reason": "budget_exhausted",
                      "errors": ["Reached maximum budget ($0.0001)"], "total_cost_usd": 0.0019}))
    sys.exit(1)
elif mode == "api_error":
    print(json.dumps({**base, "subtype": "success", "is_error": True, "terminal_reason": "api_error", "api_error_status": 400, "total_cost_usd": 0,
                      "result": "API Error: 400 tools.9.custom.input_schema: input_schema does not support oneOf, allOf, or anyOf at the top level"}))
    sys.exit(1)
elif mode == "bad_schema_arg":
    print('Error: --json-schema is not valid JSON: JSON Parse error: Unexpected identifier "C"', file=sys.stderr)
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
