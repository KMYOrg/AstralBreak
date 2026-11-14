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
    assert not any(a in llm.FORBIDDEN_ARGS for a in args)
    for p in ("--mcp-config", "--settings", "--append-system-prompt-file"):
        assert pathlib.Path(args[args.index(p) + 1]).is_file(), p


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
    call = _calls(fake_env)[0]
    assert call["argv"][:2] == ["-p", "look"]
    assert pathlib.Path(call["cwd"]).resolve() == config.repo_path(CFG["llm"]["cwd"]).resolve()
    assert call["has_api_key"] is False and call["stdin_empty"] is True     # 토큰 과금 경로 차단 · stdin 닫음(DEVNULL)


@pytest.mark.parametrize("mode, code", [("max_turns", "LLM_MAX_TURNS"), ("not_logged_in", "LLM_NOT_LOGGED_IN"),
                                        ("no_structured", "LLM_NO_STRUCTURED_OUTPUT"), ("garbage", "LLM_NO_RESULT")])
def test_run_stage_errors(fake_env, monkeypatch, mode, code):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(llm.LlmError) as e:
        llm.run_stage("verifier", "look", CFG, SCHEMA, cli=FAKE)
    assert e.value.code == code


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
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps({"fixes": [], "ops": [{"op": "set", "widget": "UltArea"}]}))
    run = _run_with_files(tmp_path)
    with pytest.raises(StageError) as e:
        fix.llm_propose(run, 1, {"gates": [], "failed": [], "revision": None}, cli=FAKE)
    assert e.value.code == "LLM_PATCH_INVALID"
