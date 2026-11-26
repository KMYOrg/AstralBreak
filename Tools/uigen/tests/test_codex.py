"""codex 생성기(gen/codex.py) · 컨셉 도구(make_concept.py) — 가짜 codex(tests/fake_codex.py)로만."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import sys

import pytest

import make_concept
from core import config
from gen import codex

FAKE = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
CFG = config.load_pipeline()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    log = tmp_path / "codex_calls_log.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-pass")
    monkeypatch.setenv("CODEX_API_KEY", "should-not-pass")
    for k in ("FAKE_CODEX_MODE", "FAKE_CODEX_LOGIN", "FAKE_CODEX_VERSION", "FAKE_CODEX_LOGIN_STDERR"):
        monkeypatch.delenv(k, raising=False)
    return log


def _calls(log):
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def _budget(tmp_path, limit=20):
    return codex.CallBudget(tmp_path / "run" / "codex_calls.jsonl", limit, 2)


def test_generate_finds_image_by_thread_id(tmp_path, fake):
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"\x89PNG fake ref")
    dest = tmp_path / "run" / "assets" / "raw" / "ult_frame.png"
    rec = codex.generate("ornate gold frame", dest, tmp_path / "run" / "gen" / "ult_frame", CFG, budget=_budget(tmp_path), refs=[ref],
                         meta={"asset_id": "ult_frame"}, cli=FAKE)
    assert rec["ok"] and rec["found_by"] == "thread_id" and dest.is_file() and rec["size"] == [8, 4]
    assert rec["has_alpha_channel"] and rec["transparent_ratio"] == 0.25 and rec["usage"]["output_tokens"] == 40
    call = _calls(fake)[0]
    argv = call["argv"]
    assert argv[0] == "exec" and "ornate gold frame" in argv[1] and "built-in image_gen" in argv[1]   # 프롬프트는 exec 바로 뒤
    assert argv[argv.index("-i") + 1:] == [str(ref.resolve())]                                       # 값이 여러 개인 -i 는 맨 끝
    assert argv[argv.index("-s") + 1] == "workspace-write" and "--json" in argv and "--skip-git-repo-check" in argv
    assert pathlib.Path(argv[argv.index("-C") + 1]) == pathlib.Path(call["cwd"])
    assert not call["has_openai_key"] and not call["has_codex_key"] and call["stdin_empty"]          # 유료 폴백 차단 · stdin 닫음
    assert not any(a in codex.FORBIDDEN_ARGS for a in argv)
    gen = tmp_path / "run" / "gen" / "ult_frame"
    assert (gen / "events.jsonl").is_file() and (gen / "prompt.txt").is_file() and json.loads((gen / "result.json").read_text())["ok"]
    assert _budget(tmp_path).used() == 1


@pytest.mark.parametrize("mode, how", [("other_dir", "generated_images_diff"), ("cwd", "cwd")])
def test_generate_fallbacks(tmp_path, fake, monkeypatch, mode, how):
    monkeypatch.setenv("FAKE_CODEX_MODE", mode)
    rec = codex.generate("x", tmp_path / "out.png", tmp_path / "gen", CFG, budget=_budget(tmp_path), cli=FAKE)
    assert rec["found_by"] == how and (tmp_path / "out.png").is_file()


def test_generate_quota_is_detected_and_recorded(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    b = _budget(tmp_path)
    with pytest.raises(codex.CodexQuota) as e:
        codex.generate("x", tmp_path / "out.png", tmp_path / "gen", CFG, budget=b, cli=FAKE)
    assert e.value.code == "CODEX_QUOTA" and "usage_limit_reached" in e.value.details["markers"] and e.value.details["exit_code"] == 1
    assert (tmp_path / "gen" / "events.jsonl").read_text(encoding="utf-8").count("usage_limit_reached") >= 1   # 이벤트 원문 채록
    assert b.used() == 1 and b.records()[0]["error"] == "CODEX_QUOTA"


def test_no_image_twice_is_suspected_quota(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_MODE", "no_image")
    b = _budget(tmp_path)
    with pytest.raises(codex.CodexError) as e1:
        codex.generate("x", tmp_path / "a.png", tmp_path / "g1", CFG, budget=b, cli=FAKE)
    assert e1.value.code == "CODEX_NO_IMAGE" and not isinstance(e1.value, codex.CodexQuota)
    with pytest.raises(codex.CodexQuota) as e2:
        codex.generate("x", tmp_path / "b.png", tmp_path / "g2", CFG, budget=b, cli=FAKE)
    assert e2.value.code == "CODEX_QUOTA_SUSPECTED" and b.consecutive_failures() == 2


def test_call_limit_stops_before_launch(tmp_path, fake):
    b = _budget(tmp_path, limit=1)
    codex.generate("x", tmp_path / "a.png", tmp_path / "g1", CFG, budget=b, cli=FAKE)
    with pytest.raises(codex.CodexError) as e:
        codex.generate("x", tmp_path / "b.png", tmp_path / "g2", CFG, budget=b, cli=FAKE)
    assert e.value.code == "CODEX_CALL_LIMIT" and len(_calls(fake)) == 1                         # 두 번째는 띄우지도 않음


def test_timeout_kills_and_counts(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_MODE", "sleep")
    cfg = copy.deepcopy(CFG)
    cfg["codex"]["timeout_s"] = 1
    b = _budget(tmp_path)
    with pytest.raises(codex.CodexError) as e:
        codex.generate("x", tmp_path / "a.png", tmp_path / "g", cfg, budget=b, cli=FAKE)
    assert e.value.code == "CODEX_TIMEOUT" and b.records()[0]["error"] == "CODEX_TIMEOUT"


def test_lock_is_exclusive_and_takes_over_dead_holder(tmp_path):
    with codex.CodexLock(tmp_path, "a"):
        with pytest.raises(codex.CodexError) as e:
            with codex.CodexLock(tmp_path, "b"):
                pass
        assert e.value.code == "CODEX_LOCKED"
    assert not (tmp_path / ".codex.lock").exists()
    (tmp_path / ".codex.lock").write_text(json.dumps({"pid": 999999, "owner": "dead"}), encoding="utf-8")
    with codex.CodexLock(tmp_path, "c") as lock:
        assert lock.taken_over["owner"] == "dead"


def test_preflight(fake, monkeypatch):
    info = codex.preflight(CFG, cli=FAKE)
    assert info["version"] == "0.166.0" and info["version_match"] and info["login"] == "Logged in using ChatGPT"
    monkeypatch.setenv("FAKE_CODEX_LOGIN_STDERR", "1")                                         # 로그인 문구가 stderr 로 와도
    assert codex.preflight(CFG, cli=FAKE)["login"] == "Logged in using ChatGPT"
    monkeypatch.setenv("FAKE_CODEX_LOGIN", "Logged in using an API key - sk-***")
    with pytest.raises(codex.CodexError) as e:
        codex.preflight(CFG, cli=FAKE)
    assert e.value.code == "CODEX_AUTH_METHOD"
    monkeypatch.setenv("FAKE_CODEX_LOGIN", "Not logged in")
    with pytest.raises(codex.CodexError) as e:
        codex.preflight(CFG, cli=FAKE)
    assert e.value.code == "CODEX_NOT_LOGGED_IN"


def test_resolve_cli_npm_wrapper_goes_through_node(tmp_path, monkeypatch):
    npm = tmp_path / "npm"
    js = npm / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    js.parent.mkdir(parents=True)
    js.write_text("// fake", encoding="utf-8")
    (npm / "codex.CMD").write_text("@echo off", encoding="utf-8")
    monkeypatch.setattr(codex.shutil, "which", lambda name: str(npm / "codex.CMD") if name == "codex" else "C:/nodejs/node.exe")
    assert codex.resolve_cli({"cli": "auto"}) == ["C:/nodejs/node.exe", str(js)]               # cmd.exe 를 거치지 않는다
    monkeypatch.setattr(codex.shutil, "which", lambda name: "C:/tools/codex.exe")
    assert codex.resolve_cli({"cli": "auto"}) == [str(pathlib.Path("C:/tools/codex.exe"))]
    assert codex.resolve_cli({"cli": ["X:/c.exe"]}) == ["X:/c.exe"]


def test_real_codex_is_refused_in_tests(tmp_path):
    with pytest.raises(AssertionError, match="real codex"):
        codex.generate("x", tmp_path / "a.png", tmp_path / "g", CFG, budget=_budget(tmp_path))
    assert pathlib.Path(os.environ["CODEX_HOME"]).name == "codex_home"


def test_make_concept_writes_fixture_and_refuses_overwrite(tmp_path, fake):
    out = tmp_path / "fixture"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a HUD concept", encoding="utf-8")
    argv = ["--out-dir", str(out), "--work-root", str(tmp_path / "work"), "--with-text"]
    assert make_concept.main(argv, cli=FAKE) == make_concept.EXIT_OK
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert (out / "concept.png").is_file() and meta["codex_version"] == "0.166.0" and meta["size"] == [8, 4] and meta["thread_id"]
    assert not pathlib.Path(meta["record"]).is_absolute()
    assert make_concept.main(argv, cli=FAKE) == make_concept.EXIT_FAIL                         # 있으면 --force 없이는 안 덮음
    assert not (tmp_path / "work" / ".codex.lock").exists()


def test_make_concept_quota_exit_code(tmp_path, fake, monkeypatch):
    out = tmp_path / "fixture"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a HUD concept", encoding="utf-8")
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    assert make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "work"), "--with-text"], cli=FAKE) == make_concept.EXIT_QUOTA
    assert not (out / "concept.png").exists()
