"""claude -p 호출 틀(core/llm.py) · LLM fix 경로 — 가짜 CLI(tests/fake_claude.py)로만."""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest
from conftest import fixture_brief, fixture_spec

from core import config, llm
from core.run import Run
from stages import StageError, fix

FAKE = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_claude.py"))]
CFG = config.load_pipeline()
SCHEMA = {"type": "object", "required": ["fixes"], "properties": {"fixes": {"type": "array"}}}


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    log = tmp_path / "claude_calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-pass")
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    return log


def _calls(log):
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def test_build_args_shape():
    args = llm.build_args(["claude"], "verifier", "PROMPT TEXT", CFG["llm"], SCHEMA)
    assert args[:3] == ["claude", "-p", "PROMPT TEXT"]                      # 프롬프트는 -p 바로 뒤
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in args and args[args.index("--setting-sources") + 1] == "project"
    assert args[args.index("--output-format") + 1] == "json" and json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
    assert float(args[args.index("--max-budget-usd") + 1]) == CFG["llm"]["stages"]["verifier"]["max_budget_usd"]
    assert int(args[args.index("--max-turns") + 1]) == CFG["llm"]["stages"]["verifier"]["max_turns"]
    assert args[args.index("--allowedTools"):] == ["--allowedTools", "Read"]   # 값이 여러 개인 옵션은 맨 뒤
    assert args[args.index("--tools") + 1] == "Read" and args.index("--tools") < args.index("--allowedTools")   # 내장 도구 목록 자체를 줄임 [실측 1b-1]
    assert not any(a in llm.FORBIDDEN_ARGS for a in args)
    for p in ("--mcp-config", "--settings", "--append-system-prompt-file"):
        assert pathlib.Path(args[args.index(p) + 1]).is_file(), p


def test_cli_schema_strips_meta_and_refuses_top_level_combinators():
    spec_schema = json.loads((config.UIGEN_DIR / "schemas" / "spec.schema.json").read_text(encoding="utf-8"))
    args = llm.build_args(["claude"], "verifier", "p", CFG["llm"], spec_schema)
    sent = json.loads(args[args.index("--json-schema") + 1])
    assert "$schema" not in sent and "$id" not in sent                     # CLI 검사기가 2020-12 메타 스키마를 모른다 [실측 1b-1]
    assert sent["$defs"] == spec_schema["$defs"] and "$schema" in spec_schema   # 안쪽($defs · $ref · if-then)은 그대로, 원본은 안 바뀜
    for bad in ({"type": "object", "allOf": [{"required": ["a"]}]}, {"type": "object", "oneOf": []}, {"type": "array"}, ["x"]):
        with pytest.raises(llm.LlmError) as e:
            llm.build_args(["claude"], "verifier", "p", CFG["llm"], bad)
        assert e.value.code == "LLM_SCHEMA_UNSUPPORTED"


def test_tool_names_from_permission_rules():
    assert llm.tool_names(["Read", "Edit(work/**)", "Read"]) == ["Edit", "Read"]


def test_build_args_refuses_bash_and_missing_limits():
    cfg = copy.deepcopy(CFG["llm"])
    cfg["stages"]["verifier"]["allowed_tools"] = ["Read", "Bash(ls)"]
    with pytest.raises(llm.LlmError) as e:
        llm.build_args(["claude"], "verifier", "p", cfg, SCHEMA)
    assert e.value.code == "LLM_CONFIG"
    cfg = copy.deepcopy(CFG["llm"])
    del cfg["stages"]["fix"]["max_budget_usd"]
    with pytest.raises(llm.LlmError):
        llm.build_args(["claude"], "fix", "p", cfg, SCHEMA)
    with pytest.raises(llm.LlmError) as e:
        llm.build_args(["claude", "--dangerously-skip-permissions"], "verifier", "p", CFG["llm"], SCHEMA)
    assert e.value.code == "LLM_FORBIDDEN_ARG"


def test_run_stage_ok(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps({"fixes": [{"widget": "UltArea", "problem": "too low"}]}))
    out = llm.run_stage("verifier", "look", CFG, SCHEMA, cli=FAKE)
    assert out["structured_output"]["fixes"][0]["widget"] == "UltArea" and out["cost_usd"] == 0.0123 and out["num_turns"] == 2
    assert out["model"] == "claude-haiku-5-5" and out["tokens"]["cacheCreationInputTokens"] == 7015 and out["terminal_reason"] == "completed"
    assert "credential_expires_at" not in out                                # 결과 이벤트의 나머지 필드는 옮기지 않는다
    call = _calls(fake_env)[0]
    assert call["argv"][:2] == ["-p", "look"]
    assert pathlib.Path(call["cwd"]).resolve() == config.repo_path(CFG["llm"]["cwd"]).resolve()
    assert call["has_api_key"] is False and call["stdin_empty"] is True     # 토큰 과금 경로 차단 · stdin 닫음(DEVNULL)


@pytest.mark.parametrize("mode, code", [("max_turns", "LLM_MAX_TURNS"), ("not_logged_in", "LLM_NOT_LOGGED_IN"),
                                        ("no_structured", "LLM_NO_STRUCTURED_OUTPUT"), ("garbage", "LLM_NO_RESULT"),
                                        ("budget", "LLM_BUDGET"), ("api_error", "LLM_API_ERROR"), ("bad_schema_arg", "LLM_NO_RESULT")])
def test_run_stage_errors(fake_env, monkeypatch, mode, code):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(llm.LlmError) as e:
        llm.run_stage("verifier", "look", CFG, SCHEMA, cli=FAKE)
    assert e.value.code == code
    if mode == "budget":
        assert e.value.details["terminal_reason"] == "budget_exhausted" and e.value.details["cost_usd"] == 0.0019


def test_preflight_records_version_and_subscription_only(monkeypatch):
    monkeypatch.delenv("FAKE_CLAUDE_AUTH", raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_VERSION", "2.1.325")
    info = llm.preflight(CFG, cli=FAKE)
    assert info == {"version": "2.1.325", "expected_version": CFG["llm"]["expected_version"], "version_match": True,
                    "logged_in": True, "auth_method": "claude.ai", "subscription": "max"}
    assert "example.com" not in json.dumps(info) and "org-fake" not in json.dumps(info)   # 계정 정보는 남기지 않는다
    monkeypatch.setenv("FAKE_CLAUDE_VERSION", "9.9.9")
    assert llm.preflight(CFG, cli=FAKE)["version_match"] is False                          # 다르면 표시만(자동 업데이트)


@pytest.mark.parametrize("auth, code", [({"loggedIn": False}, "LLM_NOT_LOGGED_IN"), ({"authMethod": "console"}, "LLM_AUTH_METHOD")])
def test_preflight_refuses_logged_out_and_token_billing(monkeypatch, auth, code):
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", json.dumps(auth))
    with pytest.raises(llm.LlmError) as e:
        llm.preflight(CFG, cli=FAKE)
    assert e.value.code == code and "example.com" not in str(e.value.details)


def test_run_stage_stream_and_timeout(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "stream")
    assert llm.run_stage("fix", "p", CFG, SCHEMA, cli=FAKE)["structured_output"] == {"fixes": []}
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    cfg = copy.deepcopy(CFG)
    cfg["llm"]["stages"]["fix"]["timeout_s"] = 1
    with pytest.raises(llm.LlmError) as e:
        llm.run_stage("fix", "p", cfg, SCHEMA, cli=FAKE)
    assert e.value.code == "LLM_TIMEOUT"


def test_real_cli_is_refused_in_tests():
    with pytest.raises(AssertionError, match="real claude"):
        llm.run_stage("verifier", "p", CFG, SCHEMA)


def _run_with_files(tmp_path) -> Run:
    run = Run("R20261114_120000_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    run.write_json("spec.json", fixture_spec())
    run.write_json("brief.json", fixture_brief())
    run.path("render.png").write_bytes(b"png")
    run.write_json("attempts/001/gates.json", {"gates": []})
    return run


def test_llm_fix_path_with_fake_cli(tmp_path, fake_env, monkeypatch):
    op = {"op": "set", "widget": "UltArea", "path": "slot.position", "value": [0, -72], "reason": "IoU"}
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps({"fixes": [{"widget": "UltArea", "problem": "low", "suggested_op": op}], "ops": [op]}))
    run = _run_with_files(tmp_path)
    res = {"gates": [{"name": "iou_region", "pass": False}], "failed": ["iou_region"], "revision": "sha1:" + "0" * 40}
    fixes, ops = fix.llm_propose(run, 1, res, cli=FAKE)
    assert fixes[0]["widget"] == "UltArea" and ops == [op]
    calls = _calls(fake_env)
    assert [c["argv"][c["argv"].index("--append-system-prompt-file") + 1].replace("\\", "/").rsplit("/", 1)[-1] for c in calls] == ["verifier.md", "fix.md"]
    assert run.path("render.png").resolve().as_posix() in calls[0]["argv"][1]       # 입력 파일은 절대 경로로
    assert (run.dir / "llm.jsonl").is_file()


def test_llm_fix_rejects_invalid_patch(tmp_path, fake_env, monkeypatch):
    """스키마에 안 맞는 patch — 오류를 붙여 fix 를 1회 다시 부르고, 또 안 되면 예외 대신 op 없음(1b-6: run 은 NO_FIX 로 finalize 까지)."""
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps({"fixes": [], "ops": [{"op": "set", "widget": "UltArea"}]}))
    run = _run_with_files(tmp_path)
    fixes, ops = fix.llm_propose(run, 1, {"gates": [], "failed": [], "revision": None}, cli=FAKE)
    assert ops == [] and fixes[-1]["problem"] == "LLM fix produced no usable patch" and "BAD_PATCH" in fixes[-1]["evidence"]
    assert len(_calls(fake_env)) == 3                                          # verifier 1 + fix 2
