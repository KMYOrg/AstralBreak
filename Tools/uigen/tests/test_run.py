from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from conftest import FIXTURE_DIR, FakeToolchain, fixture_brief, fixture_spec, widget, write_fixture

import run_pipeline
from core import metrics, schema
from core.run import LockBusy, RunLock, new_run_id
from stages import codegen

RUN_ID = "R20261114_120000_CombatHUD"


def _args(tmp_path, *extra, spec_dir=FIXTURE_DIR, run_id=RUN_ID):
    return ["--spec-dir", str(spec_dir), "--run-id", run_id, "--work-root", str(tmp_path / "work"),
            "--metrics", str(tmp_path / "metrics" / "uigen.jsonl"), "--module-root", str(tmp_path / "mod"), *extra]


@pytest.fixture
def fake_ue(tmp_path, monkeypatch):
    """codegen 의 에디터 · UBT 를 가짜로 — C++ 은 tmp_path/mod 에 쓴다."""
    (tmp_path / "mod").mkdir()
    tc = FakeToolchain(tmp_path / "mod")
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: tc)
    return tc


def test_new_run_id():
    assert new_run_id("CombatHUD", dt.datetime(2026, 11, 14, 15, 30, 0)) == "R20261114_153000_CombatHUD"


def test_lock_exclusive_and_stale(tmp_path):
    with RunLock(tmp_path, RUN_ID):
        with pytest.raises(LockBusy):
            with RunLock(tmp_path, "R20261114_120001_CombatHUD"):
                pass
    assert not (tmp_path / ".lock").exists()
    (tmp_path / ".lock").write_text(json.dumps({"pid": 0x7FFFFFF0, "run_id": "dead"}), encoding="utf-8")   # 없는 pid
    with RunLock(tmp_path, RUN_ID) as lock:
        assert lock.taken_over["run_id"] == "dead"
        assert json.loads((tmp_path / ".lock").read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_fixture_run_through_refine(tmp_path, capsys, fake_ue):
    code = run_pipeline.main(_args(tmp_path, "--until", "refine"))
    assert code == run_pipeline.EXIT_INCOMPLETE   # build 앞에서 멈춤 — 끝까지는 test_pipeline_retry
    rd = tmp_path / "work" / RUN_ID
    brief = json.loads((rd / "brief.json").read_text(encoding="utf-8"))
    assert brief["run_id"] == RUN_ID
    assert json.loads((rd / "specs" / "000.json").read_text(encoding="utf-8")) == fixture_spec()
    for aid in ("ult_frame", "chain_panel_bg", "ult_glow"):
        assert (rd / "assets" / "raw" / f"{aid}.png").is_file() and (rd / "assets" / "final" / f"{aid}.png").is_file()
    manifest = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    schema.require("manifest", manifest)
    comp = {a["asset_id"]: a["compression"] for a in manifest["assets"]}
    assert comp == {"ult_frame": "TC_EditorIcon", "chain_panel_bg": "TC_BC7", "ult_glow": "TC_EditorIcon"}   # 11-14 결정: 큰 배경만 BC7
    assert all(a["alpha"] and a["ocr_text"] is None and a["ocr"].startswith("n/a") for a in manifest["assets"])
    stages = {s["name"]: s["status"] for s in json.loads((rd / "run.json").read_text(encoding="utf-8"))["stages"]}
    assert stages == {"normalize": "ok", "analyze": "skipped", "codegen": "ok", "generate": "ok", "refine": "ok"}
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "incomplete" and "stopped after 'refine'" in report["message"] and report["finalize"] is None
    assert report["codegen"]["skipped"] is False and report["codegen"]["build"]["ok"] is True and report["codegen"]["verify_match"] is True
    assert fake_ue.calls[-1] == "list" and (tmp_path / "mod" / "UI" / "HUD" / "AutoGen" / "AstralCombatHUDViewBase.h").is_file()
    lines = metrics.read(tmp_path / "metrics" / "uigen.jsonl")
    assert [x["record"] for x in lines] == ["run", "asset", "asset", "asset"]
    assert lines[0]["run_id"] == RUN_ID and lines[0]["status"] == "incomplete" and lines[0]["verify"] is None and lines[0]["ok"] is False
    assert {x["asset_id"] for x in lines[1:]} == set(comp) and all(x["backend"] == "procedural" for x in lines[1:])
    assert all(x["style_sim_anchor"] is None for x in lines[1:])
    assert not (tmp_path / "work" / ".lock").exists()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(out)["status"] == "incomplete"


def test_until_stops_early(tmp_path):
    assert run_pipeline.main(_args(tmp_path, "--until", "normalize")) == run_pipeline.EXIT_INCOMPLETE
    rd = tmp_path / "work" / RUN_ID
    assert not (rd / "assets").exists()
    assert "stopped after 'normalize'" in json.loads((rd / "report.json").read_text(encoding="utf-8"))["message"]


def test_broken_spec_fails_and_records(tmp_path):
    spec = fixture_spec()
    widget(spec, "UltGauge")["slot"]["kind"] = "border"   # 스키마는 통과(같은 키 모양), 부모 Overlay 와 짝이 안 맞음 → 의미 검사
    src = write_fixture(tmp_path / "in", fixture_brief(), spec)
    assert run_pipeline.main(_args(tmp_path, spec_dir=src)) == run_pipeline.EXIT_FAIL
    rd = tmp_path / "work" / RUN_ID
    record = json.loads((rd / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "fail" and record["stages"][-1] == {**record["stages"][-1], "name": "normalize", "status": "fail", "code": "SPEC_INVALID"}
    assert json.loads((rd / "report.json").read_text(encoding="utf-8"))["status"] == "fail"
    line = metrics.read(tmp_path / "metrics" / "uigen.jsonl")[0]
    assert line["status"] == "fail" and line["verify"] is None          # verify 까지 가지 못함
    assert json.loads((rd / "report.json").read_text(encoding="utf-8"))["finalize"]["action"] == "none"   # build 전 실패 — finalize 단계 기록 없음


def test_brief_spec_mismatch(tmp_path):
    brief = fixture_brief()
    brief["binding_contract"]["bindings"].remove("UltBlockedText")
    src = write_fixture(tmp_path / "in", brief, fixture_spec())
    assert run_pipeline.main(_args(tmp_path, spec_dir=src)) == run_pipeline.EXIT_FAIL
    rd = tmp_path / "work" / RUN_ID
    assert json.loads((rd / "run.json").read_text(encoding="utf-8"))["stages"][-1]["code"] == "BRIEF_SPEC_MISMATCH"


def test_codex_asset_refused_in_1a(tmp_path, fake_ue):
    spec = fixture_spec()
    spec["assets"][0]["provenance"] = "codex"
    src = write_fixture(tmp_path / "in", fixture_brief(), spec)
    assert run_pipeline.main(_args(tmp_path, spec_dir=src)) == run_pipeline.EXIT_FAIL
    rd = tmp_path / "work" / RUN_ID
    assert json.loads((rd / "run.json").read_text(encoding="utf-8"))["stages"][-1]["code"] == "BACKEND_NOT_ALLOWED"


def test_run_id_never_reused(tmp_path, capsys):
    assert run_pipeline.main(_args(tmp_path, "--until", "normalize")) == run_pipeline.EXIT_INCOMPLETE
    assert run_pipeline.main(_args(tmp_path, "--until", "normalize")) == run_pipeline.EXIT_FAIL
    assert "RUN_EXISTS" in capsys.readouterr().err


def test_busy_lock_refuses(tmp_path, capsys):
    (tmp_path / "work").mkdir()
    with RunLock(tmp_path / "work", "R20261114_115959_CombatHUD"):
        assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_FAIL
    assert "RUN_LOCKED" in capsys.readouterr().err
