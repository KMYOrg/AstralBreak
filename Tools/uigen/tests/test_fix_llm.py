"""1b-6 — hybrid fix(결정적 먼저 → LLM verifier → fix) · 가드 · 결함 주입 shrink_text — 가짜 claude CLI 와 가짜 에디터로."""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest
from conftest import fixture_brief, fixture_spec, widget
from test_geometry import GATES, STACK, fixture_geometry
from test_pipeline_retry import fake_ue  # noqa: F401 — pytest fixture
from test_run import RUN_ID, _args

import run_pipeline
from core import config, llm
from core import patch as patch_mod
from core.run import Run
from stages import fault, fix, verify

FAKE = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_claude.py"))]
CFG = config.load_pipeline()
RESTORE = {"op": "set", "widget": "ChainTimerText", "path": "font.size", "value": 34, "reason": "line height 24 vs bbox 50 — back to 34"}
VERIFIER = {"fixes": [{"widget": "ChainTimerText", "gate": "iou_leaf", "problem": "font too small for its box",
                       "evidence": "measured h 24 vs intent 50", "suggested_op": RESTORE}]}


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


def _broken(name: str) -> dict:
    spec = fixture_spec()
    return patch_mod.apply_patch(spec, fault.fault_patch(name, spec))


def _gates(spec: dict) -> list[dict]:
    gates, _ = verify.render_gates(spec, [{"resolution": [1920, 1080], "geometry": fixture_geometry(spec)}], [1920, 1080], GATES, STACK)
    return gates


def _run(tmp_path, spec: dict, attempt: int = 1) -> tuple[Run, dict]:
    cfg = copy.deepcopy(CFG)
    cfg["fix"]["mode"] = "hybrid"
    run = Run("R20261115_140000_CombatHUD", tmp_path / "work", cfg, tmp_path / "m.jsonl")
    run.create()
    run.write_json("spec.json", spec)
    run.write_json("brief.json", fixture_brief())
    run.path("render.png").write_bytes(b"png")
    gates = _gates(spec)
    run.write_json(f"attempts/{attempt:03d}/gates.json", {"gates": gates})
    run.write_json(f"attempts/{attempt:03d}/geometry.json", {"geometry": {"1920x1080": fixture_geometry(spec)}})
    return run, {"gates": gates, "failed": [g["name"] for g in gates if not g["pass"]], "revision": None}


def test_hybrid_keeps_the_deterministic_patch_when_it_has_ops(tmp_path, fake_llm):
    run, res = _run(tmp_path, _broken("drift"))
    prop = fix.propose(run, 1, res)
    assert prop["patch"] and run.read_json("attempts/001/fixes.json")["source"] == "deterministic" and _calls(fake_llm) == []


def test_hybrid_asks_the_llm_when_the_failure_is_inside_a_region(tmp_path, fake_llm, monkeypatch):
    run, res = _run(tmp_path, _broken("shrink_text"))
    assert res["failed"] == ["iou_leaf"]
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([VERIFIER, {"ops": [RESTORE]}]))
    prop = fix.propose(run, 1, res)
    assert prop["patch"]["ops"] == [RESTORE] and prop["branch"] == "build" and run.read_json("attempts/001/fixes.json")["source"] == "llm"
    calls = _calls(fake_llm)
    stages = [c["argv"][c["argv"].index("--append-system-prompt-file") + 1].replace("\\", "/").rsplit("/", 1)[-1] for c in calls]
    assert stages == ["verifier.md", "fix.md"]
    assert "ChainTimerText intent" in calls[0]["argv"][1] and "geometry" in calls[0]["argv"][1] and "1.6 x font size" in calls[0]["argv"][1]
    assert "Contract widgets" in calls[1]["argv"][1] and run.path("spec.json").resolve().as_posix() in calls[1]["argv"][1]
    rows = [json.loads(x) for x in run.path("llm.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["stage"] for r in rows] == ["verifier", "fix"] and rows[1]["errors"] == 0
    assert run.path("attempts/001/llm_verifier.json").is_file() and run.path("attempts/001/llm_fix_1.json").is_file()


def test_guard_rejects_moving_the_target_then_accepts_the_retry(tmp_path, fake_llm, monkeypatch):
    run, res = _run(tmp_path, _broken("shrink_text"))
    cheat = {"op": "set", "widget": "ChainTimerText", "path": "bbox_intent", "value": [1628, 193, 228, 24]}
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([VERIFIER, {"ops": [cheat]}, {"ops": [RESTORE]}]))
    prop = fix.propose(run, 1, res)
    assert prop["patch"]["ops"] == [RESTORE]
    second = _calls(fake_llm)[2]["argv"][1]
    assert "rejected" in second and "bbox_intent is the target" in second


def test_unusable_patch_or_llm_failure_gives_no_fix(tmp_path, fake_llm, monkeypatch):
    run, res = _run(tmp_path, _broken("shrink_text"))
    bad = {"op": "set", "widget": "ChainTimerText", "path": "text.value", "value": "9.9"}       # 계약 위젯의 글자
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([VERIFIER, {"ops": [bad]}, {"ops": [bad]}]))
    prop = fix.propose(run, 1, res)
    assert prop["patch"] is None and prop["fixes"][-1]["problem"] == "LLM fix produced no usable patch"
    run2, res2 = _run(tmp_path / "b", _broken("shrink_text"))
    monkeypatch.delenv("FAKE_CLAUDE_OUTPUTS")
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "budget")
    prop2 = fix.propose(run2, 1, res2)
    assert prop2["patch"] is None and "LLM_BUDGET" in prop2["fixes"][-1]["problem"]


def test_stalled_deterministic_patch_hands_over_to_the_llm(tmp_path, fake_llm, monkeypatch):
    run, res = _run(tmp_path, _broken("drift"), attempt=2)
    run.write_json("attempts/001/fixes.json", {"schema_version": 1, "source": "deterministic", "fixes": []})
    run.write_json("attempts/001/gates.json", {"gates": res["gates"]})                         # 같은 실패 집합 = 진전 없음
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([VERIFIER, {"ops": [RESTORE]}]))
    prop = fix.propose(run, 2, res)
    assert run.read_json("attempts/002/fixes.json")["source"] == "llm" and len(_calls(fake_llm)) == 2 and prop["patch"]


def test_guard_ops_rules():
    brief = fixture_brief()
    ops = [{"op": "set", "widget": "UltArea", "path": "binding.data", "value": "x"}, {"op": "remove_widget", "widget": "BurstBanner"},
           {"op": "add_widget", "widget": {"id": "X", "type": "Image", "parent": "Root", "binding": {"data": "x", "kind": "flag"}}},
           {"op": "set", "widget": "ChainTitleText", "path": "text.value", "value": "x"}, {"op": "set", "widget": "UltArea", "path": "slot.size", "value": [1, 1]}]
    errs = fix.guard_ops(ops, fixture_spec(), brief)
    assert len(errs) == 4 and all(not e.startswith("op 4") for e in errs)


def test_shrink_text_fault_targets_the_tallest_text():
    p = fault.fault_patch("shrink_text", fixture_spec())
    assert p["ops"] == [{"op": "set", "widget": "ChainTimerText", "path": "font.size", "value": 15, "reason": "fault shrink_text — 34 → 15"}]


def test_pipeline_shrink_text_is_fixed_by_the_llm(tmp_path, fake_ue, fake_llm, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([VERIFIER, {"ops": [RESTORE]}]))
    assert run_pipeline.main(_args(tmp_path, "--inject-fault", "shrink_text", "--fix-mode", "hybrid")) == run_pipeline.EXIT_PASS
    rd = tmp_path / "work" / RUN_ID
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "pass" and report["attempt"] == 2 and report["attempts"][0]["failed"] == ["iou_leaf"]
    stages = [s["name"] for s in json.loads((rd / "run.json").read_text(encoding="utf-8"))["stages"]]
    assert stages[0] == "preflight" and stages.count("verify") == 2 and "fix" in stages
    assert widget(json.loads((rd / "specs/002.json").read_text(encoding="utf-8")), "ChainTimerText")["font"]["size"] == 34
