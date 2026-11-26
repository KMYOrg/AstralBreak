"""normalize(concept) · analyze · run_pipeline --inputs (1b-4) — 가짜 claude CLI 로만."""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import types

import pytest
import yaml
from conftest import UIGEN, fixture_spec, widget

import run_pipeline
from core import config, llm, png
from core.run import Run
from stages import StageError, analyze, normalize

FAKE = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_claude.py"))]
CFG = config.load_pipeline()
CONCEPT_DIR = UIGEN / "fixtures" / "m4_combat_hud_concept"


def _png(path: pathlib.Path, w: int, h: int) -> pathlib.Path:
    return png.write_rgba(path, w, h, bytes((40, 30, 60, 255)) * (w * h))


def _inputs(tmp_path: pathlib.Path, w: int = 320, h: int = 180, **override) -> pathlib.Path:
    data = yaml.safe_load((CONCEPT_DIR / "inputs.yaml").read_text(encoding="utf-8"))
    _png(tmp_path / "in" / "concept.png", w, h)
    data.update({"screen_id": "CombatHUD", **override})     # 이 입력은 이제 검증 화면(ProbeCombatHUD) — 여기선 실제 화면의 계약 줄을 본다
    p = tmp_path / "in" / "inputs.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def llm_spec() -> dict:
    """LLM 이 낼 법한 spec — 1a 손 spec 에서 계약 필드(binding · 바인딩 위젯 글자 · font.family)를 뺀 것."""
    spec = fixture_spec()
    for w in spec["widgets"]:
        w.pop("binding", None)
        if w["id"] in ("ChainTimerText", "ChainCountText", "BurstCountText", "UltBlockedText", "ChainTitleText", "BurstLabelText"):
            w.pop("text", None)
        (w.get("font") or {}).pop("family", None)
    for k in ("schema_version", "canvas", "profile", "note"):
        spec.pop(k, None)
    spec["schema_version"] = 1
    spec["canvas"] = [1920, 1080]
    spec["profile"] = "hud"
    spec["note"] = "scene: courtyard, characters; UI: four HUD regions"
    return spec


@pytest.fixture
def fake_llm(tmp_path, monkeypatch):
    log = tmp_path / "claude_calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_COUNTER", str(tmp_path / "claude_counter.txt"))
    for k in ("FAKE_CLAUDE_MODE", "FAKE_CLAUDE_OUTPUT", "FAKE_CLAUDE_OUTPUTS", "FAKE_CLAUDE_AUTH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "default_cli", lambda cfg: FAKE)
    return log


def _calls(log):
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def _run(tmp_path, inputs: pathlib.Path) -> Run:
    run = Run("R20261115_120000_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    normalize.run(run, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None))
    return run


# ---- normalize(concept) ---------------------------------------------------------------------------------------------

def test_normalize_concept_writes_reference_and_brief(tmp_path):
    run = _run(tmp_path, _inputs(tmp_path, 1672, 941))
    w, h, _ = png.read_rgba(run.path("reference.png"))
    assert (w, h) == (1920, 1080)
    n = run.read_json("normalize.json")
    assert n["mode"] == "stretch" and n["src_size"] == [1672, 941] and n["aspect_diff"] < 0.01
    brief = run.read_json("brief.json")
    assert brief["mode"] == "concept" and brief["font"] == CFG["fonts"]["default_family"]
    assert brief["binding_contract"] == {"class": "UAstralCombatHUDWidget", "source": "new",
                                         "bindings": ["UltGauge", "UltReadyGlow", "ChainPanel", "ChainTimerText", "ChainCountText", "BurstBanner", "BurstCountText", "UltBlockedText"]}
    assert {d["widget"]: d["widget_type"] for d in brief["dynamic_data"]}["ChainPanel"] == "Border"
    assert brief["references"][0] == {"path": "reference.png", "role": "layout", "role_source": "user"}


def test_normalize_concept_letterboxes_other_aspects(tmp_path):
    run = _run(tmp_path, _inputs(tmp_path, 400, 300))
    n = run.read_json("normalize.json")
    assert n["mode"] == "letterbox" and n["offset"][0] > 0 and n["offset"][1] == 0
    w, h, rgba = png.read_rgba(run.path("reference.png"))
    assert (w, h) == (1920, 1080) and rgba[:4] == bytes((0, 0, 0, 255))      # 왼쪽 띠는 검정


@pytest.mark.parametrize("bad, code", [
    ({"data": [{"id": "x", "type": "number", "widget": "X", "widget_type": "TextBlock"}]}, "INPUTS_INVALID"),       # number 에 format 없음
    ({"data": [{"id": "x", "type": "progress", "widget": "X", "widget_type": "TextBlock"}]}, "INPUTS_INVALID"),     # progress 는 ProgressBar 만
    ({"static_text": [{"widget": "ChainTimerText", "value": "x"}]}, "INPUTS_INVALID"),                              # 동적 숫자 위젯에 고정 글자
    ({"screen_id": "NoSuchScreen"}, "SCREEN_UNKNOWN"),
    ({"concept": "missing.png"}, "INPUT_UNREADABLE"),
    ({"mode": "text"}, "SCHEMA"),
])
def test_normalize_concept_refuses_bad_inputs(tmp_path, bad, code):
    with pytest.raises(StageError) as e:
        _run(tmp_path, _inputs(tmp_path, **bad))
    assert e.value.code == code


# ---- analyze --------------------------------------------------------------------------------------------------------

def test_analyze_fills_contract_and_writes_spec(tmp_path, fake_llm, monkeypatch):
    run = _run(tmp_path, _inputs(tmp_path, 1672, 941))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps(llm_spec(), ensure_ascii=False))
    detail = analyze.run(run, types.SimpleNamespace(llm_cli=None))
    spec = run.read_json("spec.json")
    assert run.read_json("specs/000.json") == spec and "1 call(s)" in detail
    assert widget(spec, "ChainTimerText")["text"] == {"source": "dynamic", "data": "chain_remaining", "sample": "4.2"}
    assert widget(spec, "BurstCountText")["text"]["sample"] == "3" and widget(spec, "BurstCountText")["binding"] == {"data": "burst_count", "kind": "number", "format": "0"}
    assert widget(spec, "UltBlockedText")["text"] == {"source": "static", "value": "오의 불가"} and widget(spec, "UltBlockedText")["binding"]["kind"] == "flag"
    assert widget(spec, "UltGauge")["style"]["percent"] == 0.7 and widget(spec, "ChainPanel")["binding"] == {"data": "chain_panel", "kind": "flag"}
    assert all(w["font"]["family"] == CFG["fonts"]["default_family"] for w in spec["widgets"] if w["type"] == "TextBlock")
    assert run.path("analyze", "overlay.png").is_file() and run.path("analyze", "attempt_001.json").is_file()
    summary = run.read_json("analyze.json")
    assert summary["ok"] and summary["calls"] == 1 and summary["model"] == "claude-haiku-5-5" and summary["retry_reasons"] == []
    call = _calls(fake_llm)[0]
    prompt = call["argv"][1]
    assert run.path("reference.png").resolve().as_posix() in prompt and "- ChainPanel: Border" in prompt and "16→26" in prompt
    assert call["argv"][call["argv"].index("--append-system-prompt-file") + 1].replace("\\", "/").endswith("prompts/analyze.md")
    sent = json.loads(call["argv"][call["argv"].index("--json-schema") + 1])
    assert "$schema" not in sent and "widgets" in sent["properties"]
    assert json.loads(run.path("llm.jsonl").read_text(encoding="utf-8").splitlines()[0])["stage"] == "analyze"


def test_analyze_retries_once_with_errors(tmp_path, fake_llm, monkeypatch):
    run = _run(tmp_path, _inputs(tmp_path, 1672, 941))
    bad = llm_spec()
    widget(bad, "ChainPanel")["type"] = "Overlay"                                   # 요청이 고정한 Border 와 다름
    widget(bad, "ChainBox")["slot"]["kind"] = "overlay"
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([bad, llm_spec()], ensure_ascii=False))
    analyze.run(run, types.SimpleNamespace(llm_cli=None))
    summary = run.read_json("analyze.json")
    assert summary["ok"] and summary["calls"] == 2 and any("WIDGET_TYPE" in e for e in summary["retry_reasons"])
    second = _calls(fake_llm)[1]["argv"][1]
    assert "failed these checks" in second and run.path("analyze", "attempt_001.json").resolve().as_posix() in second and "WIDGET_TYPE" in second
    assert widget(run.read_json("spec.json"), "ChainPanel")["type"] == "Border"


def test_analyze_gives_up_after_two_invalid_answers(tmp_path, fake_llm, monkeypatch):
    run = _run(tmp_path, _inputs(tmp_path, 1672, 941))
    bad = llm_spec()
    bad["widgets"] = [w for w in bad["widgets"] if w["id"] != "BurstCountText"]       # 필수 요소 빠짐
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps(bad, ensure_ascii=False))
    with pytest.raises(StageError) as e:
        analyze.run(run, types.SimpleNamespace(llm_cli=None))
    assert e.value.code == "ANALYZE_INVALID" and len(_calls(fake_llm)) == 2 and not run.path("spec.json").exists()
    assert run.read_json("analyze.json")["ok"] is False


def test_analyze_llm_error_is_a_stage_error(tmp_path, fake_llm, monkeypatch):
    run = _run(tmp_path, _inputs(tmp_path, 1672, 941))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "budget")
    with pytest.raises(StageError) as e:
        analyze.run(run, types.SimpleNamespace(llm_cli=None))
    assert e.value.code == "LLM_BUDGET" and run.read_json("analyze.json")["attempts"][0]["error"] == "LLM_BUDGET"


def test_check_catches_layout_and_asset_mistakes():
    brief = json.loads((UIGEN / "fixtures" / "m4_combat_hud" / "brief.json").read_text(encoding="utf-8"))
    spec = analyze.apply_contract(llm_spec(), {**brief, "font": None})
    assert analyze.check(spec, brief) == []
    s = copy.deepcopy(spec)
    widget(s, "ChainPanel")["slot"]["position"] = [-48, 300]                         # 슬롯이 bbox_intent 와 어긋남
    s["assets"].append({"asset_id": "unused_frame", "kind": "frame", "provenance": "codex", "size": [64, 64]})
    widget(s, "ChainBox")["binding"] = {"data": "extra", "kind": "flag"}
    errs = analyze.check(s, brief)
    for code in ("SLOT_VS_BBOX: region 'ChainPanel'", "ASSET_UNUSED: 'unused_frame'", "ASSET_PROMPT: codex asset 'unused_frame'", "EXTRA_BINDING: 'ChainBox'"):
        assert any(code in e for e in errs), code


# ---- run_pipeline --inputs ------------------------------------------------------------------------------------------

def test_pipeline_concept_until_analyze(tmp_path, fake_llm, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps(llm_spec(), ensure_ascii=False))
    args = ["--inputs", str(_inputs(tmp_path, 1672, 941)), "--until", "analyze", "--work-root", str(tmp_path / "work"),
            "--metrics", str(tmp_path / "m.jsonl"), "--run-id", "R20261115_120000_CombatHUD"]
    assert run_pipeline.main(args) == run_pipeline.EXIT_INCOMPLETE
    d = tmp_path / "work" / "R20261115_120000_CombatHUD"
    rec = json.loads((d / "run.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in rec["stages"]] == ["preflight", "normalize", "analyze", "layer"]   # 1b 후속 J-a — analyze 뒤 기능 단위 레이어
    assert rec["llm_cli"]["auth_method"] == "claude.ai" and "example.com" not in json.dumps(rec)
    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "incomplete" and report["analyze"]["calls"] == 1 and report["artifacts"]["overlay"] == "analyze/overlay.png"
    assert (d / "spec.json").is_file()


def test_pipeline_concept_stops_on_logged_out_cli(tmp_path, fake_llm, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", json.dumps({"loggedIn": False}))
    args = ["--inputs", str(_inputs(tmp_path)), "--work-root", str(tmp_path / "work"), "--metrics", str(tmp_path / "m.jsonl"),
            "--run-id", "R20261115_120001_CombatHUD"]
    assert run_pipeline.main(args) == run_pipeline.EXIT_FAIL
    rec = json.loads((tmp_path / "work" / "R20261115_120001_CombatHUD" / "run.json").read_text(encoding="utf-8"))
    assert rec["stages"][0]["name"] == "preflight" and rec["stages"][0]["code"] == "LLM_NOT_LOGGED_IN" and len(_calls(fake_llm)) == 0


def test_concept_flag_needs_inputs():
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--spec-dir", "x", "--concept", "c.png"])
