"""build → verify → (fix → 분기) → finalize — 가짜 에디터(FakeToolchain + FakeEditor)로 끝까지."""
from __future__ import annotations

import json

import pytest
from conftest import FakeToolchain, fixture_spec, widget
from test_run import RUN_ID, _args

import run_pipeline
from core import config, metrics, schema
from stages import codegen, fix


@pytest.fixture
def fake_ue(tmp_path, monkeypatch):
    (tmp_path / "mod").mkdir(exist_ok=True)
    tc = FakeToolchain(tmp_path / "mod")
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: tc)
    return tc


def _rd(tmp_path, run_id=RUN_ID):
    return tmp_path / "work" / run_id


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def _tools(tc):
    return [name for name, _ in tc.editor.log]


def test_normal_run_passes_and_saves(tmp_path, fake_ue):
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rd = _rd(tmp_path)
    report = _read(rd / "report.json")
    schema.require("report", report)
    assert report["status"] == "pass" and report["verify"] == "pass" and report["attempt"] == 1
    assert [g["name"] for g in report["gates"]] == ["compile", "bindings", "texture_settings", "offscreen", "overlap", "required_elements",
                                                    "iou_region", "iou_leaf", "baked_text", "roundtrip"]
    assert all(g["pass"] for g in report["gates"])
    assert next(g for g in report["gates"] if g["name"] == "baked_text")["skipped"]
    assert report["roundtrip"]["equal"] and report["roundtrip"]["revision_matches_build"]
    assert report["finalize"]["action"] == "saved" and report["finalize"]["content_dir"] == f"Content/_AutoGen/{RUN_ID}/"
    assert report["artifacts"] == {"render": "render.png", "geometry": "geometry.json", "render_dir": "attempts/001/render",
                                   "render_sample": "render_sample.png", "lineage": "lineage.json"}
    for f in ("render.png", "render_sample.png", "geometry.json", "build.json", "lineage.json", "specs/001.json", "attempts/001/gates.json"):
        assert (rd / f).is_file(), f
    assert not (rd / "patches").exists()
    build = _read(rd / "build.json")
    schema.require("build", build)
    assert build["wbp"]["asset_path"] == f"/Game/_AutoGen/{RUN_ID}/WBP_CombatHUD" and build["wbp"]["parent_class"] == "/Script/AstralBreak.AstralCombatHUDWidget"
    assert build["attempts"][0]["ops"] == ["import", "create", "apply"] and build["attempts"][0]["create"]["compile"]["ran"] is False
    manifest = _read(rd / "manifest.json")
    assert {a["asset_id"]: a["ue_path"] for a in manifest["assets"]} == {a: f"/Game/_AutoGen/{RUN_ID}/T_{a}" for a in ("ult_frame", "chain_panel_bg", "ult_glow")}
    lineage = _read(rd / "lineage.json")
    schema.require("lineage", lineage)
    assert lineage["status"] == "pass" and lineage["spec"]["file"] == "specs/001.json" and len(lineage["saved"]) == 4
    assert all(p["saved"] for p in fake_ue.editor.packages.values()) and len(fake_ue.editor.packages) == 4
    # 렌더 두 번(게이트 force_visible · 사람 눈용 sample) — sample 은 brief 의 값
    renders = [p for name, p in fake_ue.editor.log if name == "render_widget"]
    assert renders[0]["force_visible"] is True and len(renders[0]["resolutions"]) == 3
    assert renders[1]["force_visible"] is False and renders[1]["overrides"]["UltGauge"] == {"percent": 0.7}
    lines = metrics.read(tmp_path / "metrics" / "uigen.jsonl")
    assert lines[0]["record"] == "run" and lines[0]["status"] == "pass" and lines[0]["verify"] == "pass" and lines[0]["retries"] == 0
    assert lines[0]["failed_gates"] == [] and lines[0]["fault"] is None
    assert [x["verify"] for x in lines[1:]] == ["pass"] * 3 and all(x["retries"] == 0 for x in lines[1:])


@pytest.mark.parametrize("name", ["offscreen", "overlap", "drift"])
def test_injected_fault_is_fixed_by_a_build_retry(tmp_path, fake_ue, name):
    assert run_pipeline.main(_args(tmp_path, "--inject-fault", name)) == run_pipeline.EXIT_PASS
    rd = _rd(tmp_path)
    report = _read(rd / "report.json")
    assert report["status"] == "pass" and report["attempt"] == 2 and report["fault"]["name"] == name
    a1, a2 = report["attempts"]
    assert not a1["pass"] and a1["failed"] and a1["patch"] == "patches/001.json" and a1["branch"] == "build"
    assert a2["pass"] and a2["patch"] is None
    assert _read(rd / "patches/000.json")["source"] == "fault" and _read(rd / "patches/001.json")["source"] == "fix"
    # 정정 patch 가 손 spec 으로 되돌렸다
    fixed = _read(rd / "specs/002.json")
    assert [w.get("slot") for w in fixed["widgets"]] == [w.get("slot") for w in fixture_spec()["widgets"]]
    assert _read(rd / "specs/001.json") != fixed
    tools = _tools(fake_ue)
    assert tools.count("create_widget_blueprint") == 1 and tools.count("apply_widget_spec") == 2 and tools.count("import_ui_textures") == 1
    stages = [s["name"] for s in _read(rd / "run.json")["stages"]]
    assert stages == ["normalize", "inject_fault", "analyze", "codegen", "generate", "refine", "build", "verify", "fix", "build", "verify", "finalize"]
    assert (rd / "attempts/001/fixes.json").is_file() and report["fixes"]
    assert report["finalize"]["action"] == "saved" and _read(rd / "lineage.json")["patches"] == ["patches/000.json", "patches/001.json"]
    line = metrics.read(tmp_path / "metrics" / "uigen.jsonl")[0]
    assert line["verify"] == "pass" and line["retries"] == 1 and line["fault"] == name


def test_unfixable_failure_stops_and_discards(tmp_path, fake_ue):
    fake_ue.editor.drop_from_export = {"BurstCountText"}       # 역추출에서 위젯이 빠짐 → 필수 요소 · 왕복 실패(결정적 fix 없음)
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_FAIL
    rd = _rd(tmp_path)
    report = _read(rd / "report.json")
    assert report["status"] == "fail" and report["verify"] == "fail" and report["attempt"] == 1
    assert report["attempts"][0]["stop"] == "NO_FIX" and set(report["attempts"][0]["failed"]) == {"required_elements", "roundtrip"}
    assert report["finalize"]["action"] == "discarded" and len(report["finalize"]["discarded"]) == 4
    assert fake_ue.editor.packages == {} and not (rd / "lineage.json").exists()
    assert _read(rd / "run.json")["stages"][-2] == {**_read(rd / "run.json")["stages"][-2], "name": "fix", "status": "fail", "code": "NO_FIX"}
    line = metrics.read(tmp_path / "metrics" / "uigen.jsonl")[0]
    assert line["status"] == "fail" and line["verify"] == "fail" and set(line["failed_gates"]) == {"required_elements", "roundtrip"}


def test_keep_failed_saves_with_fail_lineage(tmp_path, fake_ue):
    fake_ue.editor.drop_from_export = {"BurstCountText"}
    assert run_pipeline.main(_args(tmp_path, "--keep-failed")) == run_pipeline.EXIT_FAIL
    rd = _rd(tmp_path)
    fin = _read(rd / "report.json")["finalize"]
    assert fin["action"] == "saved" and fin["kept_failed"] is True
    assert _read(rd / "lineage.json")["status"] == "fail"


def _useless_fix(monkeypatch):
    """게이트를 못 고치는 patch(글자색만 바꿈)를 내는 fixer."""
    real = fix.propose

    def propose(run, attempt, res, mode=None):
        out = real(run, attempt, res, mode)
        p = {"schema_version": 1, "base_revision": None, "source": "fix", "note": "useless",
             "ops": [{"op": "set", "widget": "ChainTitleText", "path": "font.color", "value": f"#C9B2{attempt:02d}"}]}
        run.write_json(f"patches/{attempt:03d}.json", p)
        return {**out, "patch": p, "patch_file": f"patches/{attempt:03d}.json", "branch": "build", "assets": []}

    monkeypatch.setattr(fix, "propose", propose)


def test_no_progress_stops_early(tmp_path, fake_ue, monkeypatch):
    _useless_fix(monkeypatch)
    assert run_pipeline.main(_args(tmp_path, "--inject-fault", "offscreen")) == run_pipeline.EXIT_FAIL
    report = _read(_rd(tmp_path) / "report.json")
    assert report["attempt"] == 3 and [a["stop"] for a in report["attempts"]] == [None, None, "NO_PROGRESS"]   # 2 · 3 번째가 줄지 않음
    assert "did not shrink 2 time(s)" in report["message"] and report["finalize"]["action"] == "discarded"


def test_retry_limit(tmp_path, fake_ue, monkeypatch):
    _useless_fix(monkeypatch)
    real = config.load_pipeline

    def load(path=None):
        cfg = real(path)
        cfg["limits"]["early_stop_no_progress"] = 99
        return cfg

    monkeypatch.setattr(config, "load_pipeline", load)
    assert run_pipeline.main(_args(tmp_path, "--inject-fault", "offscreen")) == run_pipeline.EXIT_FAIL
    report = _read(_rd(tmp_path) / "report.json")
    assert report["attempt"] == 4 and report["attempts"][-1]["stop"] == "RETRY_LIMIT"    # N = 3 → 시도 4 번
    assert [a["spec"] for a in report["attempts"]] == [f"specs/00{i}.json" for i in range(1, 5)]


def test_generate_branch_reimports_under_a_new_name(tmp_path, fake_ue):
    fake_ue.editor.texture_override = {"T_ult_glow": {"srgb": False}}   # 첫 임포트만 설정이 어긋남
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rd = _rd(tmp_path)
    report = _read(rd / "report.json")
    assert report["attempt"] == 2 and report["attempts"][0]["failed"] == ["texture_settings"] and report["attempts"][0]["branch"] == "generate"
    assert _read(rd / "patches/001.json")["ops"][0]["op"] == "replace_asset"
    stages = [s["name"] for s in _read(rd / "run.json")["stages"]]
    assert stages[-6:] == ["fix", "generate", "refine", "build", "verify", "finalize"]
    manifest = {a["asset_id"]: a for a in _read(rd / "manifest.json")["assets"]}
    assert manifest["ult_glow"]["ue_path"].endswith("/T_ult_glow_2") and manifest["ult_frame"]["ue_path"].endswith("/T_ult_frame")
    gen = [json.loads(x) for x in (rd / "gen.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [g["asset_id"] for g in gen].count("ult_glow") == 2 and gen[-1] == {**gen[-1], "asset_id": "ult_glow", "attempt": 2}
    build = _read(rd / "build.json")
    assert build["attempts"][1]["ops"] == ["import", "apply"] and [i["asset_id"] for i in build["attempts"][1]["imported"]] == ["ult_glow"]
    assets = {x["asset_id"]: x for x in metrics.read(tmp_path / "metrics" / "uigen.jsonl")[1:]}
    assert assets["ult_glow"]["retries"] == 1 and assets["ult_frame"]["retries"] == 0


def test_codegen_branch_restarts_and_rebuilds(tmp_path, fake_ue, monkeypatch):
    real = fix.propose

    def propose(run, attempt, res, mode=None):   # 정정 patch 에 바인딩 추가를 얹는다 → codegen 분기
        out = real(run, attempt, res, mode)
        p = dict(out["patch"])
        p["ops"] = p["ops"] + [{"op": "set", "widget": "ChainTitleText", "path": "binding", "value": {"data": "chain_title", "kind": "text"}}]
        run.write_json(out["patch_file"], p)
        return {**out, "patch": p, "branch": "codegen"}

    monkeypatch.setattr(fix, "propose", propose)
    assert run_pipeline.main(_args(tmp_path, "--inject-fault", "drift")) == run_pipeline.EXIT_PASS
    rd = _rd(tmp_path)
    report = _read(rd / "report.json")
    assert report["attempt"] == 2 and report["attempts"][0]["branch"] == "codegen"
    stages = [s["name"] for s in _read(rd / "run.json")["stages"]]
    assert stages[-5:] == ["fix", "codegen", "build", "verify", "finalize"]
    assert _read(rd / "attempts/002/codegen.json")["reason"] == "contract_changed"
    build = _read(rd / "build.json")
    assert "session changed" in build["attempts"][1]["reset"] and build["attempts"][1]["ops"] == ["import", "create", "apply"]
    assert _tools(fake_ue).count("create_widget_blueprint") == 2
    assert "ChainTitleText" in {b["name"] for b in fake_ue.binary}
    assert report["finalize"]["action"] == "saved"


def test_until_build_leaves_packages(tmp_path, fake_ue):
    assert run_pipeline.main(_args(tmp_path, "--until", "build")) == run_pipeline.EXIT_INCOMPLETE
    report = _read(_rd(tmp_path) / "report.json")
    assert report["status"] == "incomplete" and report["finalize"] is None and report["verify"] is None
    assert len(fake_ue.editor.packages) == 4 and not any(p.get("saved") for p in fake_ue.editor.packages.values())


def test_build_launches_the_editor_when_none_runs(tmp_path, monkeypatch):
    (tmp_path / "mod").mkdir()
    first = FakeToolchain(tmp_path / "mod")
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: first)
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS               # C++ 생성 · '빌드'
    second = FakeToolchain(tmp_path / "mod", running=False)                             # 같은 소스, 에디터 없음
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: second)
    run2 = "R20261114_120100_CombatHUD"
    assert run_pipeline.main(_args(tmp_path, run_id=run2)) == run_pipeline.EXIT_PASS
    rd = _rd(tmp_path, run2)
    assert _read(rd / "codegen.json")["skipped"] is True
    b = _read(rd / "build.json")["attempts"][0]
    assert b["editor"]["launched_pid"] == 5151 and b["editor"]["process_id"] == 5151
    assert second.calls.index("launch") < second.calls.index("import_ui_textures")


def test_compile_failure_fails_render_gates_without_fix(tmp_path, fake_ue):
    fake_ue.editor.compile_errors = 1
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_FAIL
    report = _read(_rd(tmp_path) / "report.json")
    failed = set(report["attempts"][0]["failed"])
    assert {"compile", "offscreen", "overlap", "iou_region", "iou_leaf"} <= failed
    off = next(g for g in report["gates"] if g["name"] == "offscreen")
    assert off["details"]["error"]["code"] == "NOT_COMPILED"
    assert report["attempts"][0]["stop"] == "NO_FIX"


def test_bridge_error_in_build_fails_and_discards(tmp_path, fake_ue, monkeypatch):
    spec = fixture_spec()
    real_call = fake_ue.editor.call

    def call(tool, params):
        if tool == "apply_widget_spec":
            from fake_editor import FakeBridgeError
            raise FakeBridgeError("APPLY_FAILED", "boom — the blueprint was left unchanged")
        return real_call(tool, params)

    monkeypatch.setattr(fake_ue.editor, "call", call)
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_FAIL
    rd = _rd(tmp_path)
    rec = _read(rd / "run.json")
    assert [s for s in rec["stages"] if s["name"] == "build"][0]["code"] == "APPLY_FAILED"
    report = _read(rd / "report.json")
    assert report["finalize"]["action"] == "discarded" and fake_ue.editor.packages == {}
    assert _read(rd / "build.json")["attempts"][0]["error"]["code"] == "APPLY_FAILED"
    assert widget(spec, "UltArea")   # 입력 spec 은 그대로
