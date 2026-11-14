"""`claude -p` 호출 틀 (설계 §10-1) — LLM 단계(verifier · fix — 1b 부터)의 명령 조립 · 실행 · 출력 해석.

1a 는 fix.mode = deterministic 이라 실제 호출이 0 이다(11-14 사용자 결정). 이 모듈은 틀만 두고 pytest 는 가짜 CLI 로만 돈다.

명령 규칙:
  - 프롬프트는 `-p` 바로 뒤 — `--allowedTools` 는 값을 여러 개 받아 뒤의 위치 인자를 삼킨다(§10-1 함정 [실측]).
  - `--permission-mode dontAsk` + `--allowedTools`(단계별, 기본 Read 만 — 출력은 --json-schema 로만 받는다) · Bash 없음.
  - `--strict-mcp-config --mcp-config <빈 MCP>` · `--setting-sources project --settings <claude_ctx 설정>`.
  - `--output-format json --json-schema <인라인 JSON>` → 결과의 `structured_output` 을 읽는다(§10-1 [P0 결과]).
  - 상한: `--max-budget-usd`(단계별) + 숨은 `--max-turns`(보조 — `error_max_turns` 로 끊김) + 벽시계 타임아웃(이 코드).
  - `--dangerously-skip-permissions` 류 · `--bare`(OAuth 를 안 읽음)는 어떤 경로로도 넣지 않는다.
  - cwd = claude_ctx · stdin 닫음 · 환경에서 ANTHROPIC_API_KEY 를 뺀다(구독 인증 — 토큰 과금 경로 차단, codex 의 OPENAI_API_KEY 규칙과 같다).
"""
from __future__ import annotations

import json
import os
import subprocess
import time

from core import config

FORBIDDEN_ARGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions", "--bare")
STRIP_ENV = ("ANTHROPIC_API_KEY",)


class LlmError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def default_cli(llm_cfg: dict) -> list[str]:
    """설정의 실제 CLI — pytest 는 conftest 가 이 함수를 막는다(가짜 CLI 만)."""
    cli = llm_cfg.get("cli") or ["claude"]
    return [cli] if isinstance(cli, str) else list(cli)


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
            "--json-schema", json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")),
            "--max-budget-usd", f"{float(st['max_budget_usd']):g}",
            "--max-turns", str(int(st["max_turns"]))]
    if st.get("prompt_file"):
        args += ["--append-system-prompt-file", str(config.repo_path(st["prompt_file"]))]
    if st.get("model"):
        args += ["--model", str(st["model"])]
    args += ["--allowedTools", *allowed]   # 값이 여러 개인 옵션은 맨 뒤 — 뒤에 위치 인자가 없다
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
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
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
    if ev is None:
        raise LlmError("LLM_NO_RESULT", f"claude ({stage}) exit {proc.returncode} without a result event: {proc.stderr.strip()[:300]}",
                       stage=stage, exit_code=proc.returncode)
    base = {"stage": stage, "exit_code": proc.returncode, "duration_s": dur, "cost_usd": ev.get("total_cost_usd"),
            "num_turns": ev.get("num_turns"), "session_id": ev.get("session_id"), "subtype": ev.get("subtype")}
    if ev.get("is_error") or proc.returncode != 0:
        text = str(ev.get("result") or "") + " " + " ".join(map(str, ev.get("errors") or []))
        if ev.get("subtype") == "error_max_turns":
            code = "LLM_MAX_TURNS"
        elif "Not logged in" in text:
            code = "LLM_NOT_LOGGED_IN"
        elif "budget" in str(ev.get("subtype", "")).lower() or "budget" in text.lower():
            code = "LLM_BUDGET"
        else:
            code = "LLM_ERROR"
        raise LlmError(code, f"claude ({stage}): {text.strip()[:300] or ev.get('subtype')}", **base)
    out = ev.get("structured_output")
    if not isinstance(out, dict):
        raise LlmError("LLM_NO_STRUCTURED_OUTPUT", f"claude ({stage}) returned no structured_output", **base)
    return {**base, "structured_output": out}
