"""Phase 4 — 승격 기록 · 원천 묶음 · 재승격 · 되돌리기(core/promotion · promote_screen): 임시 폴더 + 가짜 에디터(파일이 곧 애셋)."""
from __future__ import annotations

import json
import os
import pathlib

import pytest
from conftest import FakeToolchain, widget
from test_run import RUN_ID, _args

import promote_screen
import run_pipeline
from core import promotion as promo
from core import schema
from core.ue import ToolchainError
from fake_editor import FakeBridgeError
from stages import codegen

DEST = "/Game/UI/HUD/CombatHUD"
EDIT_ID, EDIT_ID2 = "R20261124_220000_CombatHUD", "R20261124_220100_CombatHUD"


def _read(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


@pytest.fixture
def ue(tmp_path, monkeypatch):
    (tmp_path / "mod").mkdir(exist_ok=True)
    tc = FakeToolchain(tmp_path / "mod")
    tc.editor.paint = True
    tc.editor.content_root = tmp_path / "Content"
    tc.report_process = True
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: tc)
    monkeypatch.setattr(promote_screen, "make_toolchain", lambda cfg: tc)
    monkeypatch.setattr(promote_screen, "READY_WAIT_S", 0.0)
    monkeypatch.setattr(promote_screen, "GONE_WAIT_S", 0.0)
    return tc


@pytest.fixture
def store(tmp_path):
    return promo.Store(tmp_path / "promoted", tmp_path / "Content", tmp_path / "work")


def _cli(tmp_path, *argv):
    return promote_screen.main([*argv, "--promoted-root", str(tmp_path / "promoted"), "--content-root", str(tmp_path / "Content"),
                                "--work-root", str(tmp_path / "work"), "--module-root", str(tmp_path / "mod")])


def _edit(tmp_path, ops, source="CombatHUD", run_id=EDIT_ID, **extra):
    p = tmp_path / f"{run_id}.json"
    p.write_text(json.dumps({"schema_version": 1, "source": "edit", "ops": ops, **extra}, ensure_ascii=False), encoding="utf-8")
    return run_pipeline.main(["--from", source, "--edit", str(p), "--run-id", run_id, "--work-root", str(tmp_path / "work"),
                              "--metrics", str(tmp_path / "metrics" / "uigen.jsonl"), "--module-root", str(tmp_path / "mod"),
                              "--promoted-root", str(tmp_path / "promoted"), "--content-root", str(tmp_path / "Content")])


MOVE = [{"op": "set", "widget": "UltBlockedText", "path": "slot.position", "value": [0, -130]}]


@pytest.fixture
def promoted(tmp_path, ue, store):
    """전체 run → 손 승격(promote_widget) → record — 소급한 것과 같은 모양."""
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    ue.editor.call("promote_widget", {"run_path": f"/Game/_AutoGen/{RUN_ID}", "dest_path": DEST, "confirm": True})
    assert _cli(tmp_path, "record", "CombatHUD", "--run", RUN_ID) == promote_screen.EXIT_OK
    ue.calls.clear()
    ue.editor.log.clear()
    return store.require("CombatHUD")


def _close(ue):
    ue.quit_editor()
    ue.calls.clear()


def _snapshot(*roots):
    return {str(p): p.read_bytes() for r in roots for p in sorted(pathlib.Path(r).rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------------------------------------------------
# 파일 판정 · 묶음

def test_files_and_changes(tmp_path):
    d = tmp_path / "x"
    (d / "sub").mkdir(parents=True)
    (d / "a.uasset").write_bytes(b"abc")
    (d / "sub" / "b.uasset").write_bytes(b"def")
    rec = promo.list_files(d)
    assert sorted(rec) == ["a.uasset", "sub/b.uasset"] and rec["a.uasset"]["size"] == 3 and promo.diff_files(rec, promo.list_files(d)) is None
    (d / "a.uasset").write_bytes(b"abd")                                   # 1 바이트
    assert promo.diff_files(rec, promo.list_files(d)) == {"changed": ["a.uasset"], "missing": [], "added": []}
    (d / "a.uasset").unlink()
    (d / "c.uasset").write_bytes(b"")
    assert promo.diff_files(rec, promo.list_files(d)) == {"changed": [], "missing": ["a.uasset"], "added": ["c.uasset"]}
    assert promo.list_files(tmp_path / "none") == {}


def test_json_hash_ignores_newlines_and_order_but_not_values(tmp_path):
    a, b, c = (tmp_path / f"{n}.json" for n in "abc")
    a.write_bytes(b'{"x": 1, "y": "\xed\x91\x9c"}\n')
    b.write_bytes(b'{\r\n  "y": "\xed\x91\x9c",\r\n  "x": 1\r\n}\r\n')
    c.write_bytes(b'{"x": 2, "y": "\xed\x91\x9c"}\n')
    assert promo.canonical_hash(a) == promo.canonical_hash(b) != promo.canonical_hash(c)
    ja, jb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    ja.write_bytes(b'{"a":1,"b":2}\n{"c":3}\n')
    jb.write_bytes(b'{"b":2,"a":1}\r\n{"c":3}\r\n')
    assert promo.canonical_hash(ja) == promo.canonical_hash(jb) and promo.canonical_hash(ja)[0] == "jsonl"
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(promo.PromotionError):
        promo.canonical_hash(bad)


def test_source_bundle_leaves_the_rest_of_the_run_out(tmp_path):
    for rel in ("spec.json", "specs/000.json", "specs/003.json", "brief.json", "manifest.json", "lineage.json", "reference.png", "reference_art_color.png", "reference_textref_color.png",
                "assets/final/a.png", "assets/raw/a.png", "layer/plate_1.png", "attempts/003/render/x.png", "compare.png", "llm.jsonl", "gen.jsonl", "edit.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"{}")
    assert promo.source_files(tmp_path) == ["assets/final/a.png", "brief.json", "edit.json", "gen.jsonl", "layer/plate_1.png", "lineage.json", "manifest.json",
                                            "reference.png", "reference_art_color.png", "spec.json", "specs/000.json"]


def test_child_rule():
    e = lambda r, p: {"run_id": r, "parent_run_id": p, "patch": {"ops": []}}      # noqa: E731
    rec = {"run_id": "R1", "edits": []}
    assert promo.is_child(rec, {"edits": [e("R2", "R1")]})[0]
    assert promo.is_child(rec, {"edits": [e("R2", "R1"), e("R3", "R2")]})[0]                        # 승격 안 한 수정 위의 수정
    assert not promo.is_child(rec, None)[0] and not promo.is_child(rec, {"edits": []})[0]
    assert not promo.is_child(rec, {"edits": [e("R2", "R0")]})[0]
    rec2 = {"run_id": "R2", "edits": [e("R2", "R1")]}
    assert promo.is_child(rec2, {"edits": [e("R2", "R1"), e("R3", "R2")]})[0]
    assert not promo.is_child(rec2, {"edits": [e("R9", "R1")]})[0]                                   # 옛 승격본에서 갈라진 것 — 쌓인 수정이 사라진다
    assert not promo.is_child(rec2, {"edits": [e("R2", "R1")]})[0]


# ---------------------------------------------------------------------------------------------------------------------
# record · status

def test_record_and_status(tmp_path, ue, promoted, store, capsys):
    schema.require("promotion", promoted)
    assert promoted["run_id"] == RUN_ID and promoted["parent_run_id"] is None and promoted["edits"] == [] and promoted["dest"] == DEST
    assert sorted(promoted["files"]) == ["T_chain_panel_bg.uasset", "T_ult_frame.uasset", "T_ult_glow.uasset", "WBP_CombatHUD.uasset"]
    assert promoted["textures"]["ult_frame"] == f"{DEST}/T_ult_frame" and promoted["wbp"] == f"{DEST}/WBP_CombatHUD"
    assert promoted["verified"]["roundtrip_equal"] and promoted["verified"]["same_bytes"] == promoted["verified"]["pictures"] == 4
    assert promoted["contract_hash"] == _read(tmp_path / "work" / RUN_ID / "lineage.json")["contract_hash"]
    assert set(promoted["source"]) >= {"spec.json", "brief.json", "manifest.json", "lineage.json", "assets/final/ult_frame.png"}
    assert _cli(tmp_path, "status") == promote_screen.EXIT_OK and "as recorded" in capsys.readouterr().out
    assert _cli(tmp_path, "record", "CombatHUD", "--run", RUN_ID) == promote_screen.EXIT_FAIL                       # 이미 있다
    f = store.content_dir(DEST) / "WBP_CombatHUD.uasset"
    old = f.read_bytes()
    f.write_bytes(old + b" ")
    assert _cli(tmp_path, "status", "CombatHUD") == promote_screen.EXIT_FAIL and "CHANGED" in capsys.readouterr().out
    f.write_bytes(old)
    (store.source_dir("CombatHUD") / "spec.json").write_text("{}", encoding="utf-8")
    assert _cli(tmp_path, "status") == promote_screen.EXIT_FAIL
    assert _cli(tmp_path, "status", "StatusHUD") == promote_screen.EXIT_FAIL                                        # 기록 없음


def test_record_refuses_what_is_not_the_run(tmp_path, ue, store):
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    assert _cli(tmp_path, "record", "CombatHUD", "--run", RUN_ID) == promote_screen.EXIT_FAIL                       # 승격한 적 없음
    ue.editor.call("promote_widget", {"run_path": f"/Game/_AutoGen/{RUN_ID}", "dest_path": DEST, "confirm": True})
    w = ue.editor.packages[f"{DEST}/WBP_CombatHUD"]
    widget(w["spec"], "UltBlockedText")["font"]["size"] = 30                                                          # 사람이 고친 승격본
    assert _cli(tmp_path, "record", "CombatHUD", "--run", RUN_ID) == promote_screen.EXIT_FAIL
    assert store.load("CombatHUD") is None and not store.screen_dir("CombatHUD").exists()


def test_record_starts_and_stops_its_own_editor(tmp_path, ue, store):
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    ue.editor.call("promote_widget", {"run_path": f"/Game/_AutoGen/{RUN_ID}", "dest_path": DEST, "confirm": True})
    _close(ue)
    assert _cli(tmp_path, "record", "CombatHUD", "--run", RUN_ID) == promote_screen.EXIT_OK
    assert ue.calls.count("launch") == 1 and ue.calls.count("quit") == 1 and ue.running is False


# ---------------------------------------------------------------------------------------------------------------------
# --from <ScreenId>

def test_edit_from_the_promoted_screen_checks_that_the_base_is_it(tmp_path, ue, promoted):
    assert _edit(tmp_path, MOVE, note="위로") == run_pipeline.EXIT_PASS
    rd = tmp_path / "work" / EDIT_ID
    doc = _read(rd / "edit.json")
    assert doc["source"] == {"kind": "promoted", "from": "CombatHUD"} and doc["parent_run_id"] == RUN_ID
    pr = doc["base"]["promoted"]
    assert pr["roundtrip_equal"] and pr["renders"] == {"n": 4, "same_bytes": 4, "same_pixels": 4, "different": {}}
    assert "base_drift" in [s["name"] for s in _read(rd / "run.json")["stages"]]


def test_base_drift_when_the_editor_shows_something_else(tmp_path, ue, promoted):
    """파일은 그대로인데 그려 보면 다르다(코드 · 폰트가 바뀐 때)."""
    widget(ue.editor.packages[f"{DEST}/WBP_CombatHUD"]["spec"], "UltBlockedText")["font"]["color"] = "#FF0000FF"
    assert _edit(tmp_path, MOVE) == run_pipeline.EXIT_FAIL
    rep = _read(tmp_path / "work" / EDIT_ID / "report.json")
    assert "BASE_DRIFT" in rep["message"] and rep["attempt"] == 1 and rep["finalize"]["action"] == "discarded"


def test_base_drift_when_a_person_changed_the_promoted_files(tmp_path, ue, promoted, store):
    f = store.content_dir(DEST) / "T_ult_glow.uasset"
    f.write_bytes(f.read_bytes() + b"\n")
    assert _edit(tmp_path, MOVE) == run_pipeline.EXIT_FAIL
    assert "BASE_DRIFT" in _read(tmp_path / "work" / EDIT_ID / "report.json")["message"] and ue.calls == []
    (store.source_dir("CombatHUD") / "brief.json").write_text("{}", encoding="utf-8")
    f.write_bytes(f.read_bytes()[:-1])
    assert _edit(tmp_path, MOVE, run_id=EDIT_ID2) == run_pipeline.EXIT_FAIL
    assert "SOURCE_CHANGED" in _read(tmp_path / "work" / EDIT_ID2 / "report.json")["message"]


# ---------------------------------------------------------------------------------------------------------------------
# apply · revert

@pytest.fixture
def edited(tmp_path, ue, promoted):
    assert _edit(tmp_path, MOVE, note="위로") == run_pipeline.EXIT_PASS
    _close(ue)
    return promoted


def test_apply_then_revert_gives_back_the_same_bytes(tmp_path, ue, edited, store, capsys):
    before = _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD"))
    assert _cli(tmp_path, "plan", "CombatHUD", "--run", EDIT_ID) == promote_screen.EXIT_OK
    out = capsys.readouterr().out
    assert "1 edit(s) on top of" in out and "UltBlockedText.slot.position" in out and "edit.png" in out
    assert ue.calls == [] and _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == before                # plan 은 아무것도 안 바꾼다
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_OK
    rec = store.require("CombatHUD")
    assert rec["run_id"] == EDIT_ID and rec["parent_run_id"] == RUN_ID and [e["run_id"] for e in rec["edits"]] == [EDIT_ID] and "replaced_edits" not in rec
    assert rec["verified"]["roundtrip_equal"] and rec["verified"]["same_pixels"] == rec["verified"]["pictures"] == 4
    assert store.check_files(rec) is None and store.check_source(rec) is None and ue.running is False
    assert widget(_read(store.content_dir(DEST) / "WBP_CombatHUD.uasset")["spec"], "UltBlockedText")["slot"]["position"] == [0, -130]
    assert widget(_read(store.source_dir("CombatHUD") / "spec.json"), "UltBlockedText")["slot"]["position"] == [0, -130]
    assert _read(store.source_dir("CombatHUD") / "edit.json")["run_id"] == EDIT_ID
    j = _read(next(store.backup_root("CombatHUD").glob("*/journal.json")))
    assert j["state"] == "done" and [s["state"] for s in j["steps"]] == ["copying", "copied", "cleared", "promoting", "promoted", "verified", "done"]
    assert _cli(tmp_path, "status") == promote_screen.EXIT_OK
    # 되돌리기 — 에디터 없이, 바이트까지 처음과 같음
    ue.calls.clear()
    assert _cli(tmp_path, "revert", "CombatHUD", "--yes") == promote_screen.EXIT_OK
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == before
    assert "launch" not in ue.calls and store.require("CombatHUD")["run_id"] == RUN_ID
    assert _cli(tmp_path, "revert", "CombatHUD", "--yes") == promote_screen.EXIT_FAIL and "NOTHING_TO_REVERT" in capsys.readouterr().err
    # 되돌린 뒤 다시 올릴 수 있다
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_OK


def test_edits_pile_up_and_a_side_branch_is_refused(tmp_path, ue, edited, store, capsys):
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_OK
    # 승격본 위의 다음 수정
    color = [{"op": "set", "widget": "UltBlockedText", "path": "font.color", "value": "#00FF00FF"}]
    assert _edit(tmp_path, color, run_id=EDIT_ID2) == run_pipeline.EXIT_PASS
    assert [e["run_id"] for e in _read(tmp_path / "work" / EDIT_ID2 / "edit.json")["edits"]] == [EDIT_ID, EDIT_ID2]
    # 옛 전체 run 에서 갈라진 수정 — 거절
    side = "R20261124_220300_CombatHUD"
    assert _edit(tmp_path, color, source=RUN_ID, run_id=side) == run_pipeline.EXIT_PASS
    _close(ue)
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", side, "--yes") == promote_screen.EXIT_FAIL and "NOT_A_CHILD" in capsys.readouterr().err
    # 전체 run 도 그냥은 거절 — 사라질 수정을 보여 준다
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", RUN_ID, "--yes") == promote_screen.EXIT_FAIL and EDIT_ID in capsys.readouterr().err
    assert store.require("CombatHUD")["run_id"] == EDIT_ID
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID2, "--yes") == promote_screen.EXIT_OK
    assert [e["run_id"] for e in store.require("CombatHUD")["edits"]] == [EDIT_ID, EDIT_ID2]
    # 갈아타기(--unrelated) — 사라진 수정이 기록에 남는다
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", RUN_ID, "--yes", "--unrelated") == promote_screen.EXIT_OK
    rec = store.require("CombatHUD")
    assert rec["run_id"] == RUN_ID and rec["edits"] == [] and [e["run_id"] for e in rec["replaced_edits"]] == [EDIT_ID, EDIT_ID2]
    assert not (store.source_dir("CombatHUD") / "edit.json").exists()                                                   # 옛 묶음의 것이 남지 않는다
    for want in (EDIT_ID2, EDIT_ID, RUN_ID):                                                                            # 차례로 되돌린다
        assert _cli(tmp_path, "revert", "CombatHUD", "--yes") == promote_screen.EXIT_OK
        assert store.require("CombatHUD")["run_id"] == want


def test_apply_refuses_before_touching_anything(tmp_path, ue, edited, store, capsys):
    before = _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD"))

    def refused(code, *argv):
        assert _cli(tmp_path, *argv) == promote_screen.EXIT_FAIL
        assert code in capsys.readouterr().err
        assert "launch" not in ue.calls

    refused("MISSING_YES", "apply", "CombatHUD", "--run", EDIT_ID)
    refused("ALREADY_PROMOTED", "apply", "CombatHUD", "--run", RUN_ID, "--yes")
    refused("RUN_INCOMPLETE", "apply", "CombatHUD", "--run", "R20261124_999999_CombatHUD", "--yes")
    refused("NOT_PROMOTED", "apply", "StatusHUD", "--run", EDIT_ID, "--yes")
    ue.running = True
    refused("EDITOR_RUNNING", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    ue.running = False
    # 사람이 고친 승격본 — 1 바이트 · 빠진 파일 · 더해진 파일
    f = store.content_dir(DEST) / "WBP_CombatHUD.uasset"
    old = f.read_bytes()
    f.write_bytes(bytes([old[0] ^ 1]) + old[1:])
    refused("PROMOTED_CHANGED", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    f.unlink()
    refused("PROMOTED_CHANGED", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    f.write_bytes(old)
    extra = store.content_dir(DEST) / "T_mine.uasset"
    extra.write_bytes(b"mine")
    refused("PROMOTED_CHANGED", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    assert extra.read_bytes() == b"mine"
    extra.unlink()
    # run 이 통과 · 저장된 것이 아님 · 저장한 파일이 다름 · 계약이 다름
    rd = tmp_path / "work" / EDIT_ID
    rep, lin = _read(rd / "report.json"), _read(rd / "lineage.json")
    (rd / "report.json").write_text(json.dumps({**rep, "status": "fail"}), encoding="utf-8")
    refused("RUN_NOT_PASSED", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    (rd / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    (rd / "lineage.json").write_text(json.dumps({**lin, "saved": lin["saved"][:-1]}), encoding="utf-8")
    refused("RUN_FILES", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    (rd / "lineage.json").write_text(json.dumps({**lin, "contract_hash": "sha1:0"}), encoding="utf-8")
    refused("CONTRACT_CHANGED", "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    (rd / "lineage.json").write_text(json.dumps(lin), encoding="utf-8")
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == before
    assert not list(store.backup_root("CombatHUD").glob("*/journal.json"))


class Boom(Exception):
    pass


@pytest.mark.parametrize("where", ["launch", "promote", "promote_half", "wrong_copy", "quit", "record"])
def test_a_failed_apply_puts_the_old_files_back(tmp_path, ue, edited, store, monkeypatch, capsys, where):
    before = _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD"))
    if where == "launch":
        monkeypatch.setattr(ue, "wait_bridge", lambda pid=None: (_ for _ in ()).throw(ToolchainError("BRIDGE_TIMEOUT", "no bridge")))
    elif where == "promote":
        real = ue.editor.t_promote_widget
        monkeypatch.setattr(ue.editor, "t_promote_widget", lambda p: real(p) if p.get("dry_run") else (_ for _ in ()).throw(FakeBridgeError("PROMOTE_FAILED", "x")))
    elif where == "promote_half":
        ue.editor.promote_error = FakeBridgeError("PROMOTE_FAILED", "copied 1 of 4")
    elif where == "wrong_copy":
        real = ue.editor.t_promote_widget

        def wrong(p):
            out = real(p)
            if p.get("confirm"):
                widget(ue.editor.packages[f"{DEST}/WBP_CombatHUD"]["spec"], "ChainTitleText")["font"]["size"] = 99
            return out

        monkeypatch.setattr(ue.editor, "t_promote_widget", wrong)
    elif where == "quit":
        real_quit, n = ue.quit_editor, []

        def once():
            n.append(1)
            if len(n) == 1:
                raise ToolchainError("QUIT_REFUSED", "dirty")
            return real_quit()

        monkeypatch.setattr(ue, "quit_editor", once)
    else:
        monkeypatch.setattr(promo.Store, "make_record", lambda *a, **k: (_ for _ in ()).throw(Boom("record")))
    raised = False
    try:
        code = _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    except Boom:
        raised, code = True, promote_screen.EXIT_FAIL
    assert code == promote_screen.EXIT_FAIL and raised == (where == "record")
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == before and store.require("CombatHUD")["run_id"] == RUN_ID
    j = _read(next(store.backup_root("CombatHUD").glob("*/journal.json")))
    assert j["state"] == "reverted" and j["error"] and ue.running is False
    assert "as recorded again" in capsys.readouterr().out and _cli(tmp_path, "status") == promote_screen.EXIT_OK
    assert store.last_apply("CombatHUD", EDIT_ID) is None


@pytest.mark.parametrize("cut", ["cleared", "promoting", "promoted", "verified"])
def test_recover_after_the_process_died(tmp_path, ue, edited, store, monkeypatch, cut):
    """전원이 나간 것처럼 그 단계에서 끊김(되돌리기도 못 함) — recover 가 사본으로."""
    before = _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD"))
    real = promo.Journal.step

    def step(self, state, **extra):
        real(self, state, **extra)
        if state == cut:
            raise KeyboardInterrupt

    monkeypatch.setattr(promo.Journal, "step", step)
    monkeypatch.setattr(promo.Store, "restore", lambda self, j: (_ for _ in ()).throw(OSError("power off")))
    with pytest.raises(KeyboardInterrupt):
        _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes")
    monkeypatch.undo()
    monkeypatch.setattr(promote_screen, "make_toolchain", lambda cfg: ue)
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: ue)
    ue.running = False
    assert len(store.unfinished("CombatHUD")) == 1
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) != before
    assert _edit(tmp_path, MOVE, run_id=EDIT_ID2) == run_pipeline.EXIT_FAIL                                              # 끊긴 채로는 시작하지 않는다
    assert "PROMOTION_UNFINISHED" in _read(tmp_path / "work" / EDIT_ID2 / "report.json")["message"]
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_FAIL
    assert _cli(tmp_path, "recover", "CombatHUD") == promote_screen.EXIT_OK
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == before and store.unfinished("CombatHUD") == []
    assert _cli(tmp_path, "recover", "CombatHUD") == promote_screen.EXIT_OK                                              # 더 할 일 없음


def test_restore_never_deletes_a_file_it_does_not_know(tmp_path, ue, edited, store, monkeypatch, capsys):
    """재승격 도중 사람이 넣은 파일 — 되돌리기는 거절하고 일지를 열린 채 둔다(파일은 그대로)."""
    real = promo.Store.clear

    def clear(self, rec):
        real(self, rec)
        (self.content_dir(DEST) / "T_mine.uasset").write_bytes(b"{}")

    monkeypatch.setattr(promo.Store, "clear", clear)
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_FAIL
    assert "NOT back" in capsys.readouterr().out and (store.content_dir(DEST) / "T_mine.uasset").read_bytes() == b"{}"
    assert _cli(tmp_path, "recover", "CombatHUD") == promote_screen.EXIT_FAIL and "UNKNOWN_FILES" in capsys.readouterr().err
    os.remove(store.content_dir(DEST) / "T_mine.uasset")
    assert _cli(tmp_path, "recover", "CombatHUD") == promote_screen.EXIT_OK and store.check_files(store.require("CombatHUD")) is None


def test_stop_waits_until_the_process_is_really_gone(ue, monkeypatch):
    """브리지도 종료 코드도 끝났는데 프로세스가 목록에 남은 에디터(실측) — 사라질 때까지 기다리고, 끝내 안 사라지면 실패."""
    ue.running, left = True, [3]

    def processes():
        left[0] -= 1
        return [{"image": "UnrealEditor.exe", "pid": 1}] if left[0] > 0 else []

    monkeypatch.setattr(ue, "editor_processes", processes)
    promote_screen.stop_editor(ue)
    assert left[0] == 0 and ue.running is False
    ue.running, left[0] = True, 10 ** 6
    with pytest.raises(ToolchainError) as e:
        promote_screen.stop_editor(ue)
    assert e.value.code == "EXIT_TIMEOUT"


def test_revert_refuses_a_hand_edited_screen(tmp_path, ue, edited, store, capsys):
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_OK
    f = store.content_dir(DEST) / "WBP_CombatHUD.uasset"
    f.write_bytes(f.read_bytes() + b"\n")
    assert _cli(tmp_path, "revert", "CombatHUD", "--yes") == promote_screen.EXIT_FAIL and "PROMOTED_CHANGED" in capsys.readouterr().err
    assert f.read_bytes().endswith(b"\n") and store.require("CombatHUD")["run_id"] == EDIT_ID
    assert _cli(tmp_path, "revert", "CombatHUD") == promote_screen.EXIT_FAIL and "MISSING_YES" in capsys.readouterr().err


def test_a_failed_revert_keeps_the_current_screen(tmp_path, ue, edited, store, monkeypatch, capsys):
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_OK
    now = _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD"))
    real, n = promo.Store.restore, []

    def restore(self, j):
        n.append(1)
        if len(n) == 1:                                                   # 옛 것으로 바꾸다가 중간에 실패
            (self.content_dir(DEST) / "WBP_CombatHUD.uasset").unlink()
            raise OSError("disk")
        return real(self, j)

    monkeypatch.setattr(promo.Store, "restore", restore)
    with pytest.raises(OSError):
        _cli(tmp_path, "revert", "CombatHUD", "--yes")
    assert _snapshot(store.content_dir(DEST), store.screen_dir("CombatHUD")) == now and store.unfinished("CombatHUD") == []
    monkeypatch.undo()


def test_bad_dest_and_lock(tmp_path, store, capsys):
    with pytest.raises(promo.PromotionError):
        store.content_dir("/Game/../x")
    with pytest.raises(promo.PromotionError):
        store.content_dir("/Engine/x")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / ".lock").write_text(json.dumps({"pid": os.getpid(), "run_id": "R"}), encoding="utf-8")
    assert _cli(tmp_path, "apply", "CombatHUD", "--run", EDIT_ID, "--yes") == promote_screen.EXIT_FAIL and "RUN_LOCKED" in capsys.readouterr().err
