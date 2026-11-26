"""Phase 4 — 이어서 고치기 run(run_pipeline --from … --edit …): 가짜 에디터로 seed → base → patch → build → verify → finalize 끝까지, 거절 규칙."""
from __future__ import annotations

import json
import shutil

import pytest
from conftest import FakeToolchain, fixture_spec, widget
from test_run import RUN_ID, _args

import run_pipeline
from core import metrics, schema
from stages import StageError, codegen, edit, verify

EDIT_ID = "R20261124_220000_CombatHUD"
EDIT_ID2 = "R20261124_220100_CombatHUD"


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def ue(tmp_path, monkeypatch):
    (tmp_path / "mod").mkdir(exist_ok=True)
    tc = FakeToolchain(tmp_path / "mod")
    tc.editor.paint = True
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: tc)
    return tc


@pytest.fixture
def parent(tmp_path, ue):
    """통과 · 저장한 부모 run(손 spec — 컨셉이 없어 appearance 는 건너뜀)."""
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    ue.editor.log.clear()
    ue.calls.clear()
    return tmp_path / "work" / RUN_ID


def _patch(tmp_path, *ops, name="p.json", **extra):
    p = tmp_path / name
    p.write_text(json.dumps({"schema_version": 1, "source": "edit", "ops": list(ops), **extra}, ensure_ascii=False), encoding="utf-8")
    return p


def _set(w, path, value):
    return {"op": "set", "widget": w, "path": path, "value": value}


def _edit(tmp_path, patch, source=RUN_ID, run_id=EDIT_ID, *extra):
    return run_pipeline.main(["--from", source, "--edit", str(patch), "--run-id", run_id, "--work-root", str(tmp_path / "work"),
                              "--metrics", str(tmp_path / "metrics" / "uigen.jsonl"), "--module-root", str(tmp_path / "mod"),
                              "--promoted-root", str(tmp_path / "promoted"), "--content-root", str(tmp_path / "Content"), *extra])


def _fail(tmp_path, code, run_id=EDIT_ID):
    rep = _read(tmp_path / "work" / run_id / "report.json")
    assert rep["status"] == "fail" and code in rep["message"], rep["message"]
    return rep


def _gate(rep, name):
    return next(g for g in rep["gates"] if g["name"] == name)


# ---------------------------------------------------------------------------------------------------------------------

def test_edit_run_passes_and_keeps_the_parent_link(tmp_path, ue, parent):
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "slot.position", [0, -130]), note="위로 14 px")) == run_pipeline.EXIT_PASS
    rd = tmp_path / "work" / EDIT_ID
    rep = _read(rd / "report.json")
    schema.require("report", rep)
    assert rep["status"] == "pass" and rep["parent_run_id"] == RUN_ID and rep["attempt"] == 2
    assert [g["name"] for g in rep["gates"]] == [*verify.GATES, "edit_regression"] and all(g["pass"] for g in rep["gates"])
    assert [a["edit"] for a in rep["attempts"]] == ["base", "edit"]
    lin = _read(rd / "lineage.json")
    schema.require("lineage", lin)
    assert lin["parent_run_id"] == RUN_ID and lin["patches"] == ["patches/001.json"] and lin["spec"]["file"] == "specs/002.json"
    doc = _read(rd / "edit.json")
    schema.require("edit", doc)
    assert doc["targets"] == ["UltBlockedText"] and doc["source"] == {"kind": "run", "from": RUN_ID} and doc["base"]["failed"] == []
    assert doc["edits"] == [{"run_id": EDIT_ID, "parent_run_id": RUN_ID, "note": "위로 14 px", "patch": doc["patch"]}]
    assert doc["bbox_intent"] == [{"widget": "UltBlockedText", "was": [840, 932, 240, 32], "now": [840.0, 918.0, 240.0, 32.0]}]
    assert widget(_read(rd / "spec.json"), "UltBlockedText")["bbox_intent"] == [840.0, 918.0, 240.0, 32.0]
    reg = _gate(rep, "edit_regression")["details"]
    assert reg["problems"] == [] and reg["pixels"]["outside"] == {} and reg["pixels"]["changed"] > 0 and reg["geometry"]["outside"] == {}
    assert list(reg["geometry"]["moved_targets"]) == ["UltBlockedText"] and reg["scope"] == ["UltBlockedText"]
    assert (rd / "edit.png").is_file() and rep["artifacts"]["edit"] == "edit.png" and rep["recorded"]["edit"]["targets"] == ["UltBlockedText"]
    # LLM · codex · 생성 · 다듬기 · 재시도 없이, 새 run 폴더에만
    stages = [s["name"] for s in _read(rd / "run.json")["stages"]]
    assert stages == ["seed", "codegen", "build", "verify", "patch", "build", "intent", "verify", "finalize"]
    assert "build" not in ue.calls and "quit" not in ue.calls                                  # 계약이 같아 C++ 빌드 없음
    assert {k.rsplit("/", 1)[0] for k, p in ue.editor.packages.items()} == {f"/Game/_AutoGen/{RUN_ID}", f"/Game/_AutoGen/{EDIT_ID}"}
    apply = [p for n, p in ue.editor.log if n == "apply_widget_spec"]
    assert len(apply) == 2 and all(p["asset_path"].startswith(f"/Game/_AutoGen/{EDIT_ID}/") for p in apply)
    assert rep["finalize"]["designer_hidden"]["applied"] is False
    lines = [x for x in metrics.read(tmp_path / "metrics" / "uigen.jsonl") if x["run_id"] == EDIT_ID]
    assert [x["record"] for x in lines] == ["run"] and lines[0]["edit_of"] == RUN_ID            # 에셋 줄은 없다(만들지 않았다)


def test_a_normal_run_is_untouched_by_the_edit_code(tmp_path, ue, parent):
    rep = _read(parent / "report.json")
    assert [g["name"] for g in rep["gates"]] == list(verify.GATES) and len(verify.GATES) == 11 and rep["parent_run_id"] is None
    assert not list(parent.glob("edit*")) and not list(parent.glob("attempts/*/edit*")) and "edit" not in rep["recorded"]
    assert "edit_of" not in metrics.read(tmp_path / "metrics" / "uigen.jsonl")[0]


def test_a_text_that_overflows_its_box_is_measured_by_what_it_draws(tmp_path, ue, parent):
    """글자가 상자 밖으로 넘침 — 대상을 끈 렌더(앞 · 뒤)로 풀린다. WBP 는 잠깐 base 로 갔다가 같은 revision 으로 돌아온다."""
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "text.value", "오의를 아직 쓸 수 없음 — 게이지가 모자람"))) == run_pipeline.EXIT_PASS
    reg = _gate(_read(tmp_path / "work" / EDIT_ID / "report.json"), "edit_regression")["details"]
    assert reg["footprint"]["used"] and reg["pixels"]["footprint"] and reg["pixels"]["outside"] == {}
    st = _read(tmp_path / "work" / EDIT_ID / "build.json")
    applies = [p for n, p in ue.editor.log if n == "apply_widget_spec" and EDIT_ID in p["asset_path"]]
    assert len(applies) == 4 and st["attempts"][-1]["apply"]["revision_after"] == st["revision"]                     # base · edit · (되돌림 · 다시)
    assert ue.editor._revision(ue.editor.packages[st["wbp"]["asset_path"]]) == st["revision"]                        # noqa: SLF001 — 저장된 것 = 게이트가 본 것


def test_the_footprint_is_not_used_when_turning_the_target_off_moves_others(tmp_path, ue, parent):
    """세로 상자의 글자를 끄면 형제가 밀린다 — 발자국에 형제가 섞이므로 쓰지 않고 상자 기준으로 막는다(한계: 박스 안에서 넘치는 글자)."""
    assert _edit(tmp_path, _patch(tmp_path, _set("ChainTimerText", "font.size", 44))) == run_pipeline.EXIT_FAIL
    reg = _gate(_fail(tmp_path, "edit_regression"), "edit_regression")["details"]
    assert reg["footprint"]["used"] is False and "ChainTitleText" in reg["footprint"]["reason"] and reg["pixels"]["outside"] and reg["geometry"]["outside"] == {}


def test_an_edit_that_moves_its_siblings_is_refused_unless_they_are_named(tmp_path, ue, parent):
    """세로 상자에서 한 칸의 비율을 바꾸면 형제가 밀린다."""
    op = _set("ChainTitleText", "slot.fill", 5)
    assert _edit(tmp_path, _patch(tmp_path, op)) == run_pipeline.EXIT_FAIL
    rep = _fail(tmp_path, "edit_regression")
    reg = _gate(rep, "edit_regression")
    assert not reg["pass"] and set(reg["details"]["geometry"]["outside"]) == {"ChainTimerText", "ChainCountText"}
    assert rep["attempts"][-1]["stop"] == "EDIT_REJECTED" and len(rep["attempts"]) == 2                              # 재시도하지 않는다
    assert rep["finalize"]["action"] == "discarded" and not (tmp_path / "work" / EDIT_ID / "lineage.json").exists()
    assert not any(k.startswith(f"/Game/_AutoGen/{EDIT_ID}/") for k in ue.editor.packages)
    ok = _patch(tmp_path, op, name="q.json", affects=["ChainTimerText", "ChainCountText"])
    assert _edit(tmp_path, ok, run_id=EDIT_ID2) == run_pipeline.EXIT_PASS
    doc = _read(tmp_path / "work" / EDIT_ID2 / "edit.json")
    assert doc["affects"] == ["ChainCountText", "ChainTimerText"] and len(doc["bbox_intent"]) == 3


def test_pixels_outside_the_targets_fail_without_any_threshold(tmp_path, ue, parent):
    ue.editor.paint_bleed = {"ChainCountText": "UltBlockedText"}                    # 대상 밖 위젯의 그림이 대상을 따라 바뀌는 엔진 결함
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "font.color", "#00FF00FF"))) == run_pipeline.EXIT_FAIL
    reg = _gate(_fail(tmp_path, "edit_regression"), "edit_regression")["details"]
    assert set(reg["pixels"]["outside"]) >= {"render_1920x1080", "render_2560x1080", "render_1920x1200", "sample"}
    assert reg["footprint"]["used"] and reg["spec"]["diffs"] == [] and reg["geometry"]["outside"] == {}


def test_two_widgets_changed_but_one_named_is_caught(tmp_path, ue, parent, monkeypatch):
    """대상 목록이 실제로 바꾼 것보다 좁으면(도구 결함 흉내) spec · 픽셀이 잡는다."""
    real = edit.check_patch

    def narrow(spec, patch):
        out = real(spec, patch)
        return {**out, "targets": out["targets"][:1]}

    monkeypatch.setattr(edit, "check_patch", narrow)
    p = _patch(tmp_path, _set("BurstLabelText", "font.color", "#00FF00FF"), _set("UltBlockedText", "font.color", "#00FF00FF"))
    assert _edit(tmp_path, p) == run_pipeline.EXIT_FAIL
    reg = _gate(_fail(tmp_path, "edit_regression"), "edit_regression")["details"]
    assert reg["spec"]["touched_beyond"] == ["UltBlockedText"] and any(d.startswith("UltBlockedText.font.color") for d in reg["spec"]["diffs"])
    assert "render_1920x1080" in reg["pixels"]["outside"]


def test_covered_edit_has_no_effect(tmp_path, ue, parent):
    """그려지는 것이 하나도 안 변하는 수정 — 뒤에 깔린 위젯처럼."""
    assert _edit(tmp_path, _patch(tmp_path, _set("ChainBox", "designer_hidden", True))) == run_pipeline.EXIT_FAIL
    assert "NO_EFFECT" in _fail(tmp_path, "edit_regression")["message"]


def test_overlap_needs_a_named_pair(tmp_path, ue, parent):
    op = _set("UltBlockedText", "slot.position", [0, -80])                          # UltArea 와 겹친다
    assert _edit(tmp_path, _patch(tmp_path, op)) == run_pipeline.EXIT_FAIL
    rep = _fail(tmp_path, "overlap")
    assert "UltArea overlaps UltBlockedText" in rep["message"] or "UltBlockedText overlaps UltArea" in rep["message"]      # 어느 쌍인지 말해 준다
    assert not _gate(rep, "overlap")["pass"] and _gate(rep, "iou_region")["pass"]   # 옮긴 대상의 배치는 새 상자로 본다
    assert _edit(tmp_path, _patch(tmp_path, op, name="q.json", allow_overlap=[["UltBlockedText", "UltArea"]]), run_id=EDIT_ID2) == run_pipeline.EXIT_PASS
    assert ["UltBlockedText", "UltArea"] in _read(tmp_path / "work" / EDIT_ID2 / "spec.json")["allow_overlap"]


def test_add_move_and_remove_widgets(tmp_path, ue, parent):
    new = {"id": "HintText", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas", "position": [100, 100], "size": [200, 40]},
           "text": {"source": "static", "value": "hint"}, "font": {"size": 20, "weight": "bold", "color": "#FFFFFF"}}
    assert _edit(tmp_path, _patch(tmp_path, {"op": "add_widget", "widget": new})) == run_pipeline.EXIT_PASS
    assert _read(tmp_path / "work" / EDIT_ID / "edit.json")["targets"] == ["HintText"]
    # 이어서 지우기 — 쌓인 수정이 이어진다
    assert _edit(tmp_path, _patch(tmp_path, {"op": "remove_widget", "widget": "HintText"}, name="q.json"), EDIT_ID, EDIT_ID2) == run_pipeline.EXIT_PASS
    doc = _read(tmp_path / "work" / EDIT_ID2 / "edit.json")
    assert [(e["run_id"], e["parent_run_id"]) for e in doc["edits"]] == [(EDIT_ID, RUN_ID), (EDIT_ID2, EDIT_ID)]
    assert "HintText" not in {w["id"] for w in _read(tmp_path / "work" / EDIT_ID2 / "spec.json")["widgets"]}


# ---------------------------------------------------------------------------------------------------------------------
# 거절 — 에디터를 부르기 전에

@pytest.mark.parametrize("ops, extra, code", [
    ([{"op": "replace_asset", "asset": "ult_frame", "regenerate": True}], {}, "EDIT_OP_REFUSED"),
    ([_set("UltGauge", "binding.data", "other")], {}, "EDIT_OP_REFUSED"),
    ([_set("UltBlockedText", "bbox_intent", [0, 0, 10, 10])], {}, "EDIT_OP_REFUSED"),
    ([_set("Root", "visibility", "collapsed")], {}, "EDIT_OP_REFUSED"),
    ([{"op": "add_widget", "widget": {"id": "B2", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas"}, "binding": {"data": "x", "kind": "text"},
                                      "text": {"source": "dynamic", "data": "x", "sample": "a"}}}], {}, "EDIT_OP_REFUSED"),
    ([{"op": "remove_widget", "widget": "UltGauge"}], {}, "BINDING_REMOVAL"),
    ([_set("NoSuchWidget", "font.size", 10)], {}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", "big")], {}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.sparkle", 3)], {}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", 22)], {}, "NO_EFFECT"),                        # 지금과 같은 값
    ([_set("UltBlockedText", "font.size", 24)], {"affects": ["Nobody"]}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", 24)], {"affects": ["Root"]}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", 24)], {"allow_overlap": [["UltBlockedText", "Nobody"]]}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", 24)], {"base_revision": "sha1:0"}, "EDIT_PATCH_BAD"),
    ([_set("UltBlockedText", "font.size", 24)], {"source": "fix"}, "EDIT_PATCH_BAD"),
])
def test_refused_patches_never_reach_the_editor(tmp_path, ue, parent, ops, extra, code):
    assert _edit(tmp_path, _patch(tmp_path, *ops, **extra)) == run_pipeline.EXIT_FAIL
    rep = _fail(tmp_path, code)
    assert ue.calls == [] and rep["attempts"] == [] and rep["finalize"]["action"] == "none"
    line = metrics.read(tmp_path / "metrics" / "uigen.jsonl")[-1]
    assert line["run_id"] == EDIT_ID and line["edit_of"] == RUN_ID                       # seed 에서 막혀도 수정 run 으로 센다


def test_a_changed_contract_stops_before_any_code_is_written(tmp_path, ue, parent):
    """원천의 계약 ≠ 지금 생성 C++ — 쓰기 · 빌드 · 에디터 종료가 일어나면 안 된다."""
    h = tmp_path / "mod" / "UI" / "HUD" / "AutoGen" / "AstralCombatHUDViewBase.h"
    before = h.read_bytes()
    spec = _read(parent / "spec.json")
    widget(spec, "ChainCountText").pop("binding")
    widget(spec, "ChainCountText")["text"] = {"source": "static", "value": "2/4"}
    (parent / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "font.size", 24))) == run_pipeline.EXIT_FAIL
    _fail(tmp_path, "EDIT_CONTRACT_CHANGED")
    assert h.read_bytes() == before and "build" not in ue.calls and "quit" not in ue.calls and "create_widget_blueprint" not in ue.calls


def test_a_stale_editor_binary_stops_before_a_build(tmp_path, ue, parent):
    ue.binary = ue.binary[:-1]
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "font.size", 24))) == run_pipeline.EXIT_FAIL
    assert "stale binary" in _fail(tmp_path, "EDIT_CONTRACT_CHANGED")["message"]
    assert "build" not in ue.calls and "quit" not in ue.calls


def test_a_base_that_no_longer_passes_stops_before_the_edit(tmp_path, ue, parent):
    ue.editor.texture_override = {"T_ult_frame": {"srgb": False}}
    assert _edit(tmp_path, _patch(tmp_path, _set("UltBlockedText", "font.size", 24))) == run_pipeline.EXIT_FAIL
    rep = _fail(tmp_path, "does not pass the structural gates any more")
    assert rep["attempts"][0]["stop"] == "BASE_FAILED" and len(rep["attempts"]) == 1 and rep["finalize"]["action"] == "discarded"


def test_source_run_must_be_complete_passed_and_intact(tmp_path, ue, parent):
    p = _patch(tmp_path, _set("UltBlockedText", "font.size", 24))
    assert _edit(tmp_path, p, "R20261114_999999_CombatHUD") == run_pipeline.EXIT_FAIL
    _fail(tmp_path, "SOURCE_INCOMPLETE")
    tex = parent / "assets" / "final" / "ult_frame.png"
    tex.write_bytes(tex.read_bytes() + b"x")
    assert _edit(tmp_path, p, run_id=EDIT_ID2) == run_pipeline.EXIT_FAIL
    _fail(tmp_path, "SOURCE_CORRUPT", EDIT_ID2)
    rep = _read(parent / "report.json")
    (parent / "report.json").write_text(json.dumps({**rep, "status": "fail"}), encoding="utf-8")
    assert _edit(tmp_path, p, run_id="R20261124_220200_CombatHUD") == run_pipeline.EXIT_FAIL
    _fail(tmp_path, "SOURCE_NOT_PASSED", "R20261124_220200_CombatHUD")
    assert _edit(tmp_path, p, "CombatHUD", "R20261124_220300_CombatHUD") == run_pipeline.EXIT_FAIL
    _fail(tmp_path, "NOT_PROMOTED", "R20261124_220300_CombatHUD")


@pytest.mark.parametrize("argv", [["--from", RUN_ID], ["--edit", "p.json", "--inputs", "i.yaml"], ["--from", RUN_ID, "--edit", "p.json", "--until", "build"],
                                  ["--from", RUN_ID, "--edit", "p.json", "--inject-fault", "drift"], ["--from", RUN_ID, "--edit", "p.json", "--inputs", "i.yaml"]])
def test_bad_arguments(argv):
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(argv)


# ---------------------------------------------------------------------------------------------------------------------

def test_the_font_source_that_went_stale_is_named(tmp_path):
    """글꼴 단일 원천(참고판 배치 yaml) · 요청 외곽선 · 고정 글자 — 어느 줄이 낡았나."""
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "layout.yaml").write_text("# widget: A, 주석 줄은 아니다\ntexts:\n  - { widget: AB, pt: 9 }\n  - { widget: A, pt: 20, weight: semibold }\n", encoding="utf-8")
    (fx / "concept_text_ref.json").write_text(json.dumps({"layout_file": str(fx / "layout.yaml")}), encoding="utf-8")
    (fx / "inputs.yaml").write_text("data:\n  - { id: a, widget: A, outline: 2 }\n  - { widget: L, value: 표식 }\n", encoding="utf-8")

    class R:
        docs = {"brief.json": {"dynamic_data": [{"id": "a", "widget": "A", "font": {"size": 20, "weight": "semibold", "color": "#ECE5D6"}, "outline": {"size": 2, "color": "#0C0C0EDC"}}],
                               "static_text": [{"widget": "L", "value": "표식"}]},
                "normalize.json": {"inputs": str(fx / "inputs.yaml")}}

        def path(self, rel):
            return fx / "inputs.yaml"                    # is_file 만 본다

        def read_json(self, rel):
            return self.docs[rel]

    spec = {"widgets": [{"id": "A", "font": {"size": 22, "weight": "semibold", "color": "#ece5d6ff", "outline": {"size": 2, "color": "#0C0C0EDC"}}},
                        {"id": "L", "text": {"source": "static", "value": "인"}}]}
    notes = edit.source_notes(R(), spec, ["A", "L"])
    assert [(n["widget"], n["path"], n["source_value"], n["edited_value"], n["line"]) for n in notes] == [("A", "font.size", 20, 22, 4), ("L", "text.value", "표식", "인", 3)]
    assert notes[0]["file"].endswith("layout.yaml") and notes[1]["file"].endswith("inputs.yaml")
    spec["widgets"][0]["font"] = {"size": 20, "weight": "bold", "color": "#ECE5D6FF"}
    assert {n["path"] for n in edit.source_notes(R(), spec, ["A"])} == {"font.weight", "font.outline"}
    assert edit.source_notes(R(), spec, ["L"]) and not edit.source_notes(R(), spec, ["Z"])


def test_check_patch_keeps_the_given_spec_untouched():
    s = fixture_spec()
    out = edit.check_patch(s, {"schema_version": 1, "source": "edit", "ops": [_set("UltBlockedText", "font.size", 24)], "allow_overlap": [["UltArea", "UltBlockedText"]]})
    assert s == fixture_spec() and widget(out["spec"], "UltBlockedText")["font"]["size"] == 24 and out["targets"] == ["UltBlockedText"]
    assert ["UltArea", "UltBlockedText"] in out["spec"]["allow_overlap"]
    with pytest.raises(StageError) as e:
        edit.check_patch(s, {"schema_version": 1, "source": "edit", "ops": [_set("UltBlockedText", "font.size", 22)]})
    assert e.value.code == "NO_EFFECT"


def test_recorded_requests_come_from_the_attempt_when_kept(tmp_path):
    ad = tmp_path / "attempts" / "002"
    ad.mkdir(parents=True)
    assert edit.recorded_requests(tmp_path, 2, {}) == {}                                  # 손 spec — 상태 그림이 없다
    (ad / "edit_view.json").write_text(json.dumps({"requests": {"state": {}}}), encoding="utf-8")
    assert edit.recorded_requests(tmp_path, 2, {}) == {"state": {}}


def test_attempt_images_names(tmp_path):
    ad = tmp_path / "attempts" / "001"
    for rel in ("render/render_10x10.png", "sample/sample_10x10.png", "state/state_10x10.png", "state_x_single/state_x_10x10.png", "off_edit/state/x.png", "intent/intent_10x10.png"):
        (ad / rel).parent.mkdir(parents=True, exist_ok=True)
        (ad / rel).write_bytes(b"x")
    assert sorted(edit.attempt_images(tmp_path, 1)) == ["render_10x10", "sample", "state", "state_x"]
    assert edit.attempt_images(tmp_path, 9) == {}
    shutil.rmtree(ad)
