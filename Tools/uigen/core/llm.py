"""`claude -p` 호출 틀 (설계 §10-1) — LLM 단계(analyze · verifier · fix — 1b)의 명령 조립 · 실행 · 출력 해석.

pytest 는 가짜 CLI(tests/fake_claude.py)로만 돈다. 아래 [실측 1b-1] 은 11-15 claude 2.1.325 실제 호출 채록(설계 §11 '1b-1').

명령 규칙:
  - 프롬프트는 `-p` 바로 뒤 — `--allowedTools` · `--tools` 는 값을 여러 개 받아 뒤의 위치 인자를 삼킨다(§10-1 함정 [실측]).
  - `--permission-mode dontAsk` + `--allowedTools`(단계별, 기본 Read 만 — 출력은 --json-schema 로만 받는다) · Bash 없음.
  - `--tools <허용 도구 이름>` — 내장 도구 목록 자체를 줄인다. [실측 1b-1] 도구 정의가 빠져 첫 요청의 캐시 쓰기가 38,167 → 7,015 토큰
    (haiku 호출 0.0080 → 0.0014 USD 환산 · Opus 5.5 기본 비용 약 0.05 USD) — `--allowedTools` 만으로는 정의가 그대로 실린다.
  - `--strict-mcp-config --mcp-config <빈 MCP>` · `--setting-sources project --settings <claude_ctx 설정>`.
  - `--output-format json --json-schema <인라인 JSON>` → 결과의 `structured_output` 을 읽는다(§10-1 [P0 결과]).
    [실측 1b-1] 파일 경로는 안 받는다(`--json-schema is not valid JSON` · 종료 1 · stdout 없음). 최상위 `$schema`(2020-12 메타 스키마)는
    CLI 검사기가 몰라 거부하므로 빼고 넘긴다(`cli_schema`). 스키마는 StructuredOutput 도구의 input_schema 가 되어 최상위 allOf/anyOf/oneOf 는
    API 400 이다 — 호출 전에 거부한다. 안쪽 `$defs`/`$ref`/allOf-if-then 은 된다(spec 스키마 통째로 통과 · 로컬 검사 오류 0).
  - 상한: `--max-budget-usd`(단계별) + 숨은 `--max-turns`(보조 — `error_max_turns` 로 끊김) + 벽시계 타임아웃(이 코드).
    [실측 1b-1] 예산은 턴 사이에 검사한다 — 끊기면 subtype `error_max_budget_usd` · terminal_reason `budget_exhausted` · 종료 1, 이미 끝난
    턴만큼은 넘어 쓴다(0.0001 상한에 0.0019 사용). 상한은 '한 턴 더' 여유를 두고 정한다.
  - `--dangerously-skip-permissions` 류 · `--bare`(OAuth 를 안 읽음)는 어떤 경로로도 넣지 않는다.
  - cwd = claude_ctx · stdin 닫음 · 환경에서 ANTHROPIC_API_KEY 를 뺀다(구독 인증 — 토큰 과금 경로 차단, codex 의 OPENAI_API_KEY 규칙과 같다).
  - run 시작 검사(`preflight`): `claude --version` 기록 · `claude auth status` 로 로그인 · 구독 인증 확인. 계정 정보(이메일 · 조직)는 남기지 않는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

from core import config

FORBIDDEN_ARGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions", "--bare")
STRIP_ENV = ("ANTHROPIC_API_KEY",)
SCHEMA_META_KEYS = ("$schema", "$id")              # [실측 1b-1] "no schema with key or ref https://json-schema.org/draft/2020-12/schema"
TOP_LEVEL_COMBINATORS = ("allOf", "anyOf", "oneOf")  # [실측 1b-1] API 400 "input_schema does not support oneOf, allOf, or anyOf at the top level"
SUBSCRIPTION_AUTH = ("claude.ai",)                 # [실측 1b-1] `claude auth status` authMethod — 그 밖(API 키 · 콘솔)은 토큰 과금 경로


class LlmError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def default_cli(llm_cfg: dict) -> list[str]:
    """설정의 실제 CLI — pytest 는 conftest 가 이 함수를 막는다(가짜 CLI 만)."""
    cli = llm_cfg.get("cli") or ["claude"]
    return [cli] if isinstance(cli, str) else list(cli)


def cli_schema(output_schema: dict) -> dict:
    """--json-schema 로 넘길 모양 — 최상위 메타 키를 빼고, CLI · API 가 받지 않는 모양은 호출 전에 거부한다([실측 1b-1])."""
    if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
        raise LlmError("LLM_SCHEMA_UNSUPPORTED", "output schema must be a JSON object schema with type 'object' (it becomes a tool input_schema)")
    bad = [k for k in TOP_LEVEL_COMBINATORS if k in output_schema]
    if bad:
        raise LlmError("LLM_SCHEMA_UNSUPPORTED", f"top-level {bad} in the output schema — the API rejects them in a tool input_schema; "
                                                 "move the condition under a property")
    return {k: v for k, v in output_schema.items() if k not in SCHEMA_META_KEYS}


def tool_names(allowed: list[str]) -> list[str]:
    """허용 규칙(`Edit(work/**)` 등) → `--tools` 에 줄 내장 도구 이름."""
    return sorted({t.split("(", 1)[0].strip() for t in allowed})


def build_args(cli: list[str], stage: str, prompt: str, llm_cfg: dict, output_schema: dict) -> list[str]:
    st = (llm_cfg.get("stages") or {}).get(stage)
    if not isinstance(st, dict):
        raise LlmError("LLM_CONFIG", f"pipeline.yaml llm.stages has no '{stage}'")
    for key in ("max_budget_usd", "max_turns", "timeout_s"):
        if st.get(key) is None:
            raise LlmError("LLM_CONFIG", f"llm.stages.{stage}.{key} is required (stage limits — design §9)")
    allowed = list(st.get("allowed_tools") or ["Read"])
    if any(t == "Bash" or t.startswith("Bash(") for t in allowed):
        raise LlmError("LLM_CONFIG", f"llm.stages.{stage}.allowed_tools must not include Bash (design §9)")
    args = [*cli, "-p", prompt,
            "--permission-mode", "dontAsk",
            "--strict-mcp-config", "--mcp-config", str(config.repo_path(llm_cfg["mcp_config"])),
            "--setting-sources", "project", "--settings", str(config.repo_path(llm_cfg["settings"])),
            "--output-format", "json",
            "--json-schema", json.dumps(cli_schema(output_schema), ensure_ascii=False, separators=(",", ":")),
            "--max-budget-usd", f"{float(st['max_budget_usd']):g}",
            "--max-turns", str(int(st["max_turns"]))]
    if st.get("prompt_file"):
        args += ["--append-system-prompt-file", str(config.repo_path(st["prompt_file"]))]
    if st.get("model"):
        args += ["--model", str(st["model"])]
    # 값이 여러 개인 옵션은 맨 뒤 — 뒤에 위치 인자가 없다. --tools 는 쉼표 한 값(내장 도구 목록 자체를 줄임 — 입력 토큰 [실측 1b-1])
    args += ["--tools", ",".join(tool_names(allowed)), "--allowedTools", *allowed]
    bad = [a for a in args if a in FORBIDDEN_ARGS]
    if bad:
        raise LlmError("LLM_FORBIDDEN_ARG", f"refusing to run claude with {bad}")
    return args


def _result_event(stdout: str) -> dict | None:
    """--output-format json(객체 하나) · stream-json(줄마다 — 마지막 줄이 task_summary 일 수 있다) 모두에서 type:result 를 찾는다."""
    text = stdout.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
    except ValueError:
        pass
    found = None
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            found = obj
    return found


def run_stage(stage: str, prompt: str, cfg: dict, output_schema: dict, *, cli: list[str] | None = None, env_extra: dict | None = None) -> dict:
    """claude -p 한 번. 성공하면 {structured_output, cost_usd, num_turns, duration_s, session_id}. 실패는 LlmError."""
    llm_cfg = cfg.get("llm")
    if not isinstance(llm_cfg, dict):
        raise LlmError("LLM_CONFIG", "pipeline.yaml: 'llm' section is missing")
    args = build_args(cli or default_cli(llm_cfg), stage, prompt, llm_cfg, output_schema)
    timeout = float(llm_cfg["stages"][stage]["timeout_s"])
    env = _cli_env()
    env.update(env_extra or {})
    t0 = time.monotonic()
    try:
        proc = subprocess.run(args, cwd=str(config.repo_path(llm_cfg["cwd"])), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise LlmError("LLM_TIMEOUT", f"claude ({stage}) did not finish within {timeout:g}s", stage=stage) from exc
    except OSError as exc:
        raise LlmError("LLM_LAUNCH", f"{args[0]}: {exc}", stage=stage) from exc
    dur = round(time.monotonic() - t0, 3)
    ev = _result_event(proc.stdout)
    if ev is None:   # [실측 1b-1] 인자 오류(--json-schema 형식 등)는 stderr 'Error: …' · 종료 1 · stdout 없음
        raise LlmError("LLM_NO_RESULT", f"claude ({stage}) exit {proc.returncode} without a result event: {proc.stderr.strip()[:300]}",
                       stage=stage, exit_code=proc.returncode)
    base = {"stage": stage, "exit_code": proc.returncode, "duration_s": dur, "cost_usd": ev.get("total_cost_usd"),
            "num_turns": ev.get("num_turns"), "session_id": ev.get("session_id"), "subtype": ev.get("subtype"),
            "terminal_reason": ev.get("terminal_reason"), **usage_summary(ev)}
    if ev.get("is_error") or proc.returncode != 0:
        code = classify_error(ev)
        text = str(ev.get("result") or "") + " " + " ".join(map(str, ev.get("errors") or []))
        raise LlmError(code, f"claude ({stage}): {text.strip()[:300] or ev.get('subtype')}", **base)
    out = ev.get("structured_output")
    if not isinstance(out, dict):
        raise LlmError("LLM_NO_STRUCTURED_OUTPUT", f"claude ({stage}) returned no structured_output", **base)
    return {**base, "structured_output": out}


def classify_error(ev: dict) -> str:
    """오류 result 이벤트 → 코드. [실측 1b-1] 모양: 턴 상한 subtype `error_max_turns` · 예산 subtype `error_max_budget_usd`(terminal_reason
    `budget_exhausted`) · API 오류 subtype `success` + is_error + terminal_reason `api_error`(result 'API Error: 400 …') · 미로그인 result 'Not logged in'."""
    subtype, term = str(ev.get("subtype") or ""), str(ev.get("terminal_reason") or "")
    text = str(ev.get("result") or "") + " " + " ".join(map(str, ev.get("errors") or []))
    if subtype == "error_max_turns":
        return "LLM_MAX_TURNS"
    if "Not logged in" in text:
        return "LLM_NOT_LOGGED_IN"
    if subtype == "error_max_budget_usd" or term == "budget_exhausted" or "budget" in subtype.lower():
        return "LLM_BUDGET"
    if term == "api_error" or ev.get("api_error_status") or text.lstrip().startswith("API Error"):
        return "LLM_API_ERROR"
    return "LLM_ERROR"


def usage_summary(ev: dict) -> dict:
    """modelUsage → {model, tokens} (단계 기록 · 상한 보정용). 토큰은 모델 합계."""
    mu = ev.get("modelUsage") or {}
    if not isinstance(mu, dict) or not mu:
        return {"model": None, "tokens": None}
    keys = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "thinkingTokens")
    tokens = {k: sum(int((m or {}).get(k) or 0) for m in mu.values()) for k in keys}
    return {"model": ",".join(sorted(mu)), "tokens": tokens}


def _cli_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in STRIP_ENV}


def preflight(cfg: dict, *, cli: list[str] | None = None, timeout: float = 60.0) -> dict:
    """run 시작 검사 — CLI 버전 기록(기대 버전과 다르면 표시만, 자동 업데이트가 바꾼다) · 로그인 · 구독 인증.
    계정 정보(이메일 · 조직 id)는 돌려주지 않는다 — loggedIn · authMethod · subscriptionType 만."""
    llm_cfg = cfg.get("llm")
    if not isinstance(llm_cfg, dict):
        raise LlmError("LLM_CONFIG", "pipeline.yaml: 'llm' section is missing")
    cli = cli or default_cli(llm_cfg)
    cwd = str(config.repo_path(llm_cfg["cwd"]))

    def _run(extra: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([*cli, *extra], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  stdin=subprocess.DEVNULL, timeout=timeout, env=_cli_env())
        except subprocess.TimeoutExpired as exc:
            raise LlmError("LLM_TIMEOUT", f"claude {' '.join(extra)} did not finish within {timeout:g}s") from exc
        except OSError as exc:
            raise LlmError("LLM_LAUNCH", f"{cli[0]}: {exc}") from exc

    v = _run(["--version"])
    version = (v.stdout.strip().split() or [""])[0]
    if v.returncode != 0 or not version:
        raise LlmError("LLM_LAUNCH", f"claude --version failed (exit {v.returncode}): {v.stderr.strip()[:200]}")
    a = _run(["auth", "status"])
    try:
        st = json.loads(a.stdout)
    except ValueError as exc:
        raise LlmError("LLM_AUTH_STATUS", f"claude auth status did not print JSON (exit {a.returncode})") from exc
    expected = llm_cfg.get("expected_version")
    info = {"version": version, "expected_version": expected, "version_match": (expected is None or str(expected) == version),
            "logged_in": bool(st.get("loggedIn")), "auth_method": st.get("authMethod"), "subscription": st.get("subscriptionType")}
    if not info["logged_in"]:
        raise LlmError("LLM_NOT_LOGGED_IN", "the standalone claude CLI is not logged in — run `claude` once and /login (subscription account)", **info)
    if info["auth_method"] not in SUBSCRIPTION_AUTH:
        raise LlmError("LLM_AUTH_METHOD", f"claude is logged in with '{info['auth_method']}', not a subscription — refusing the token-billed path", **info)
    return info
