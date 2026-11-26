"""Phase 3-2 — 버튼 칸 파이프라인: 요청 검사 · spec(LLM 0) · 파생 상태 그림 · 손으로 쓴 부모 · build → verify → finalize(가짜 에디터) · 이어서 고치기,
그리고 바꾸지 않기로 한 것(두 HUD 의 계약 해시 · LLM 이 보는 스키마). 에디터 · codex · claude 없음."""
from __future__ import annotations

import hashlib
import json
import pathlib
import types

import numpy as np
import pytest
import yaml
from conftest import FakeToolchain
from PIL import Image
from test_analyze import fake_llm  # noqa: F401 — 시작 검사(claude CLI)만 쓴다(버튼 칸은 LLM 호출 0)
from test_button_states import H, LABEL, W, art, strokes

import make_concept
import run_pipeline
from core import button, config, cppgen, schema
from core import spec as spec_mod
from core.run import Run
from gen import diagnose, text_ref, theme
from stages import StageError, analyze, build, codegen, normalize, refine, verify

CFG = config.load_pipeline()
RUN_ID = "R20261125_120000_ButtonLarge"
LABEL_FONT = {"size": 18, "weight": "semibold", "color": "#ECE5D6FF"}
BINDINGS = [{"name": "ButtonLabel", "widget_class": "TextBlock", "optional": False}, {"name": "InputActionWidget", "widget_class": "CommonActionWidget", "optional": True}]


def inputs(tmp: pathlib.Path, label_color="#ECE5D6FF", **over) -> pathlib.Path:
    d = tmp / "in"
    d.mkdir(parents=True, exist_ok=True)
    Image.fromarray(art(), "RGBA").save(d / "concept.png")
    ref = art().copy()
    ref[strokes()] = (0xEC, 0xE5, 0xD6, 255)
    Image.fromarray(ref, "RGBA").save(d / "concept_text_ref.png")
    (d / "concept_text_ref.json").write_text(json.dumps({"drawn": [{"widget": "ButtonLabel", "value": "준비", "box": LABEL, "font": {**LABEL_FONT, "color": label_color}}]}),
                                             encoding="utf-8")
    doc = {"schema_version": 1, "mode": "concept", "screen_type": "cell", "screen_id": "ButtonLarge", "concept": "concept.png", "concept_source": "generated_textfree",
           "concept_text_ref": "concept_text_ref.png", "resolution": [W, H], "language": "ko", "font": None, "text": "큰 버튼",
           "button": {"art": "ButtonArt", "label": "ButtonLabel", "theme": "blade"},
           "required_elements": [{"id": "ButtonArt", "kind": "image"}, {"id": "ButtonLabel", "kind": "text"}],
           "data": [{"id": "button_text", "type": "text", "widget": "ButtonLabel", "widget_type": "TextBlock", "sample": "준비"}], **over}
    p = d / "inputs.yaml"
    p.write_text(yaml.safe_dump({k: v for k, v in doc.items() if v is not None or k == "font"}, allow_unicode=True), encoding="utf-8")
    return p


def make_run(tmp_path, **over) -> Run:
    run = Run(RUN_ID, tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    normalize.run(run, types.SimpleNamespace(inputs=str(inputs(tmp_path, **over)), concept=None, spec_dir=None))
    return run


def analyzed(tmp_path, **over) -> Run:
    run = make_run(tmp_path, **over)
    analyze.run(run, types.SimpleNamespace(llm_cli=None))
    return run


# ---------------------------------------------------------------------------------------------------------------------
# 요청

def test_request_becomes_a_brief_with_the_theme_text(tmp_path):
    run = make_run(tmp_path)
    brief = run.read_json("brief.json")
    schema.require("brief", brief)
    assert brief["button"] == {"art": "ButtonArt", "label": "ButtonLabel", "theme": "blade"} and brief["resolution"] == [W, H]
    assert brief["binding_contract"] == {"class": "UAstralButtonBase", "source": "existing", "bindings": ["ButtonLabel"]}
    d = brief["dynamic_data"][0]
    assert d["font"] == LABEL_FONT and d["outline"] == {"size": 2, "color": "#0C0C0EDC"}        # 글꼴 = 참고판 배치, 외곽선 = 테마
    tf = run.read_json("normalize.json")["background"]["text_ref"]
    assert tf["used"] and tf["shift_px"] == [0.0, 0.0]                                          # 우리가 그린 참고판은 어긋날 수 없다


@pytest.mark.parametrize("over, code, word", [
    ({"screen_type": "menu"}, "INPUTS_INVALID", "only for screen_type cell"),
    ({"required_elements": [{"id": "ButtonArt", "kind": "image"}]}, "INPUTS_INVALID", "required_elements"),
    ({"data": [{"id": "button_text", "type": "text", "widget": "ButtonLabel", "widget_type": "TextBlock"}]}, "INPUTS_INVALID", "sample"),
    ({"static_text": [{"widget": "X", "value": "y"}]}, "INPUTS_INVALID", "static_text"),
    ({"data": [{"id": "button_text", "type": "text", "widget": "ButtonLabel", "widget_type": "TextBlock", "sample": "준비", "outline": {"size": 1, "color": "#000000FF"}}]},
     "INPUTS_INVALID", "theme"),
    ({"concept_text_ref": None}, "INPUTS_INVALID", "concept_text_ref"),
    ({"button": {"art": "ButtonArt", "label": "ButtonLabel", "theme": "nope"}}, "THEME", "nope"),
    ({"label_color": "#FF0000FF"}, "THEME_TEXT", "one source"),
])
def test_bad_button_requests_stop_before_the_run(tmp_path, over, code, word):
    with pytest.raises(StageError) as e:
        make_run(tmp_path, **over)
    assert e.value.code == code and word in str(e.value), str(e.value)


# ---------------------------------------------------------------------------------------------------------------------
# spec — LLM 0

def test_the_spec_is_fixed_by_the_request(tmp_path):
    run = analyzed(tmp_path)
    spec = run.read_json("spec.json")
    schema.require("spec", spec)
    assert spec_mod.validate_semantics(spec) == [] and [w["id"] for w in spec["widgets"]] == ["Root", "ButtonArt", "ButtonLabel"]
    assert set(spec["button"]["states"]) == set(button.DERIVED) and spec["button"]["theme"]["sha256"] == theme.load("blade")["sha256"]
    assert spec["button"]["pressed_offset"] == [0, 1]
    label = spec["widgets"][2]
    assert label["slot"]["anchors"] == [0.5, 0.5, 0.5, 0.5] and label["slot"]["auto_size"] and label["font"]["size"] == 18
    assert label["font"]["outline"]["size"] == 2 and label["text"]["sample"] == "준비"
    assert {a["provenance"] for a in spec["assets"]} == {"codex", "derived"} and len(spec["assets"]) == 7
    assert run.read_json("analyze.json")["skipped"].startswith("button cell")
    # 에디터로 가는 트리에는 기본 그림이 없고 클래스 기본값의 스타일이 있다
    target = button.editor_target(spec, "/Game/_AutoGen/R/BS_ButtonLarge")
    assert [w["id"] for w in target["widgets"]] == ["Root", "ButtonLabel"] and target["defaults"] == {"Style": "/Game/_AutoGen/R/BS_ButtonLarge"}
    with pytest.raises(spec_mod.SpecError, match="BUTTON_STYLE"):
        button.editor_target(spec)


def _art(spec):
    return next(w for w in spec["widgets"] if w["id"] == "ButtonArt")


@pytest.mark.parametrize("break_it, word", [
    (lambda s: s["button"]["states"].pop("disabled"), "BUTTON_STATES"),
    (lambda s: s["button"]["states"].update(disabled="button_art_normal_hovered"), "BUTTON_STATES"),
    (lambda s: s["assets"][1].update(size=[W, H - 1]), "BUTTON_STATES"),
    (lambda s: s["assets"][1]["derived"].update(brush="normal_pressed"), "BUTTON_STATES"),
    (lambda s: _art(s).update(bbox_intent=[0, 0, W, H - 4]), "BUTTON_ART"),
    (lambda s: _art(s)["style"]["brush"].update(draw_as="box", margin=[0.2] * 4), "BUTTON_ART"),
    (lambda s: s["widgets"][2].update(parent="ButtonArt"), "BUTTON_ART"),
    (lambda s: s.pop("button"), "DERIVED"),
])
def test_broken_button_specs_are_refused(tmp_path, break_it, word):
    spec = analyzed(tmp_path).read_json("spec.json")
    break_it(spec)
    assert any(word in e for e in spec_mod.validate_semantics(spec)), spec_mod.validate_semantics(spec)


def test_cells_only_take_class_and_props():
    base = {"schema_version": 1, "canvas": [400, 200], "profile": "hud", "root": "Root", "assets": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"}, {"id": "Ready", "type": "UserWidget", "parent": "Root", "slot": {"kind": "canvas", "size": [100, 50]}}]}
    assert any("CELL_CLASS" in e for e in spec_mod.validate_semantics(base))
    base["widgets"][1]["class"] = "/Game/UI/Common/ButtonLarge/WBP_ButtonLarge.WBP_ButtonLarge_C"
    base["widgets"][1]["props"] = {"ButtonText": "준비"}
    assert spec_mod.validate_semantics(base) == []
    assert spec_mod.normalize(base)["widgets"][1]["class"] == "/Game/UI/Common/ButtonLarge/WBP_ButtonLarge"
    base["widgets"].append({"id": "T", "type": "TextBlock", "parent": "Ready", "slot": {"kind": "canvas"}})
    assert spec_mod.validate_semantics(base) != []                      # 칸 안에 자식을 둘 수 없다
    base["widgets"].pop()
    base["widgets"].append({"id": "B", "type": "Image", "parent": "Root", "slot": {"kind": "canvas"}, "class": "/Game/X"})
    assert any("CELL_CLASS" in e for e in spec_mod.validate_semantics(base))


# ---------------------------------------------------------------------------------------------------------------------
# 파생 상태 그림

def refined(tmp_path) -> Run:
    run = analyzed(tmp_path)
    for f in ("raw", "final"):
        run.path("assets", f).mkdir(parents=True, exist_ok=True)
    Image.fromarray(art(), "RGBA").save(run.path("assets", "final", "button_art.png"))
    return run


def test_derived_pictures_record_their_source_and_theme(tmp_path):
    run = refined(tmp_path)
    spec = run.read_json("spec.json")
    a = next(x for x in spec["assets"] if x["asset_id"] == "button_art_normal_hovered")
    info, log = refine._derived_entry(run, a, spec)
    out = run.path("assets", "final", "button_art_normal_hovered.png")
    src = run.path("assets", "final", "button_art.png")
    assert info["derived"] == {"from": "button_art", "brush": "normal_hovered", "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "theme": "blade",
                               "theme_sha256": spec["button"]["theme"]["sha256"]} and log["backend"] == "derived"
    assert (np.asarray(Image.open(out)) == theme.state(art(), "normal_hovered", theme.load("blade"))).all()


def test_a_theme_changed_during_the_run_stops_it(tmp_path):
    run = refined(tmp_path)
    spec = run.read_json("spec.json")
    spec["button"]["theme"]["sha256"] = "0" * 64
    with pytest.raises(StageError) as e:
        refine._derived_entry(run, spec["assets"][1], spec)
    assert e.value.code == "THEME_CHANGED"
    run.path("assets", "final", "button_art.png").unlink()
    with pytest.raises(StageError) as e:
        refine._derived_entry(run, spec["assets"][1], run.read_json("spec.json"))
    assert e.value.code == "DERIVED_SOURCE"


# ---------------------------------------------------------------------------------------------------------------------
# 손으로 쓴 부모

def test_hand_written_contract_comes_from_the_class(tmp_path):
    want = [{"name": "ButtonLabel", "widget_class": "TextBlock", "optional": False}]
    assert cppgen.hand_written_diff(want, BINDINGS) == []                                     # 클래스의 선택 바인딩은 없어도 된다
    assert cppgen.hand_written_diff(want + [{"name": "X", "widget_class": "Image"}], BINDINGS) == ["X: the class has no such binding"]
    assert "required by the class" in cppgen.hand_written_diff([], BINDINGS)[0]
    assert "binds it as TextBlock" in cppgen.hand_written_diff([{"name": "ButtonLabel", "widget_class": "Image"}], BINDINGS)[0]
    screens = config.load_screens()
    for sid in ("ButtonLarge", "ButtonSmall"):
        assert cppgen.hand_written(screens[sid]) and cppgen.parent_class(screens[sid]) == "AstralButtonBase" and cppgen.validate_screen(sid, screens[sid]) == []
    assert not cppgen.hand_written(screens["CombatHUD"])
    assert cppgen.validate_screen("ButtonLarge", {**screens["ButtonLarge"], "widget": "X"}) != []


def test_codegen_writes_no_cpp_for_a_hand_written_parent(tmp_path):
    run = analyzed(tmp_path)
    (tmp_path / "mod").mkdir()
    tc = FakeToolchain(tmp_path / "mod")
    tc.binary = list(BINDINGS)
    opts = types.SimpleNamespace(module_root=str(tmp_path / "mod"), no_build=False)
    assert "hand-written parent" in codegen.run(run, opts, toolchain=tc)
    rec = run.read_json("codegen.json")
    assert rec["reason"] == "hand_written" and rec["files"] == [] and not rec["build"]["ran"] and rec["verify"]["match"] is True
    assert not list((tmp_path / "mod").rglob("*.h")) and "build" not in tc.calls and "quit" not in tc.calls
    tc.binary = [{"name": "OtherLabel", "widget_class": "TextBlock", "optional": False}]
    with pytest.raises(StageError) as e:
        codegen.run(run, opts, toolchain=tc)
    assert e.value.code == "CONTRACT_MISMATCH" and "OtherLabel" in str(e.value)


# ---------------------------------------------------------------------------------------------------------------------
# 끝까지(가짜 에디터)

@pytest.fixture
def ue(tmp_path, monkeypatch, fake_llm):  # noqa: F811
    (tmp_path / "mod").mkdir(exist_ok=True)
    tc = FakeToolchain(tmp_path / "mod")
    tc.binary = list(BINDINGS)
    monkeypatch.setattr(codegen, "default_toolchain", lambda run: tc)
    return tc


def go(tmp_path, *extra, run_id=RUN_ID):
    return run_pipeline.main(["--inputs", str(inputs(tmp_path)), "--run-id", run_id, "--work-root", str(tmp_path / "work"), "--metrics", str(tmp_path / "m.jsonl"),
                              "--module-root", str(tmp_path / "mod"), *extra])


def report(tmp_path, run_id=RUN_ID):
    return json.loads((tmp_path / "work" / run_id / "report.json").read_text(encoding="utf-8"))


def failed(rep):
    return sorted(g["name"] for g in rep["gates"] if not g["pass"])


@pytest.fixture
def no_ocr(monkeypatch):
    """OCR 은 이 시험의 대상이 아니다(글자 없는 그림) — 없는 것으로."""
    monkeypatch.setattr(text_ref, "detect_boxes", lambda *a, **k: [])


def test_a_button_cell_runs_to_the_end(tmp_path, ue, no_ocr):
    code = go(tmp_path)
    rep = report(tmp_path)
    assert code == run_pipeline.EXIT_PASS, rep["message"]
    assert failed(rep) == [] and rep["finalize"]["action"] == "saved"
    rd = tmp_path / "work" / RUN_ID
    run_path = f"/Game/_AutoGen/{RUN_ID}"
    saved = {k.rsplit("/", 1)[1] for k in ue.editor.packages}
    assert saved == {"WBP_ButtonLarge", "BS_ButtonLarge", "T_button_art", *(f"T_button_art_{b}" for b in button.DERIVED)}
    style = ue.editor.packages[f"{run_path}/BS_ButtonLarge"]
    assert style["parent"] == "/Script/AstralBreak.AstralButtonStyle" and style["min_size"] == [W, H] and style["props"] == {"PressedTextOffset": [0, 1]}
    assert {k: b["asset"].rsplit("/", 1)[1] for k, b in style["brushes"].items()}["disabled"] == "T_button_art_disabled"
    wbp = ue.editor.packages[f"{run_path}/WBP_ButtonLarge"]
    assert wbp["parent"] == "/Script/AstralBreak.AstralButtonBase" and [w["id"] for w in wbp["spec"]["widgets"]] == ["Root", "ButtonLabel"]
    geo = json.loads((rd / "geometry.json").read_text(encoding="utf-8"))["geometry"]
    assert list(geo) == [f"{W}x{H}"]                                                   # 칸은 캔버스 크기 하나만 그린다
    assert next(g for g in geo[f"{W}x{H}"] if g["id"] == "ButtonArt")["w"] == W
    man = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    schema.require("manifest", man)
    assert sum(1 for a in man["assets"] if a.get("derived")) == 6
    lin = json.loads((rd / "lineage.json").read_text(encoding="utf-8"))
    assert lin["parent_class"] == "/Script/AstralBreak.AstralButtonBase"


@pytest.mark.parametrize("knob, gate", [
    (lambda e: e.style_override.update(min_size=[W, H - 2]), "roundtrip"),
    (lambda e: e.style_override.update(props={"PressedTextOffset": [0, 3]}), "roundtrip"),
    (lambda e: setattr(e, "desired_override", [W + 8, H]), "iou_region"),
])
def test_a_style_that_is_not_the_request_fails_a_gate(tmp_path, ue, no_ocr, knob, gate):
    knob(ue.editor)
    assert go(tmp_path) == run_pipeline.EXIT_FAIL
    assert gate in failed(report(tmp_path))


def test_a_lost_or_swapped_brush_fails_the_roundtrip(tmp_path, ue, no_ocr):
    """비활성이 빠짐 · 올림 ↔ 누름 바뀜 — 그림을 보기 전에 역추출이 먼저 잡는다."""
    real = ue.editor.t_export_widget_spec

    def swapped(p):
        out = real(p)
        b = out["button_style"]["brushes"]
        b["normal_hovered"], b["normal_pressed"] = b["normal_pressed"], b["normal_hovered"]
        return out
    ue.editor.t_export_widget_spec = swapped
    assert go(tmp_path) == run_pipeline.EXIT_FAIL
    rep = report(tmp_path)
    diffs = next(g for g in rep["gates"] if g["name"] == "roundtrip")["details"]["diffs"]
    assert "roundtrip" in failed(rep) and any("normal_hovered" in d for d in diffs) and any("normal_pressed" in d for d in diffs)

    def lost(p):
        out = real(p)
        out["button_style"]["brushes"]["disabled"] = {"draw_as": "none"}
        return out
    ue.editor.t_export_widget_spec = lost
    assert go(tmp_path, run_id="R20261125_120100_ButtonLarge") == run_pipeline.EXIT_FAIL
    diffs = next(g for g in report(tmp_path, "R20261125_120100_ButtonLarge")["gates"] if g["name"] == "roundtrip")["details"]["diffs"]
    assert any("disabled" in d for d in diffs)


def test_a_class_without_the_label_fails_the_bindings_gate(tmp_path, ue, no_ocr):
    real = ue.editor.t_list_bind_widgets
    ue.editor.t_list_bind_widgets = lambda p: {**real(p), "bindings": [{"name": "ButtonLabel", "widget_class": "RichTextBlock", "optional": False}]}
    assert go(tmp_path) == run_pipeline.EXIT_FAIL
    assert "bindings" in failed(report(tmp_path))


def test_the_style_is_made_again_only_when_its_pictures_change(tmp_path, ue, no_ocr):
    assert go(tmp_path) == run_pipeline.EXIT_PASS
    run = Run(RUN_ID, tmp_path / "work", CFG, tmp_path / "m.jsonl")
    spec, man, state = run.read_json("spec.json"), run.read_json("manifest.json"), run.read_json("build.json")
    screen = config.load_screens()["ButtonLarge"]
    rpath = f"/Game/_AutoGen/{RUN_ID}"
    n = sum(1 for t, _ in ue.editor.log if t == "create_button_style")
    assert build._button_style(ue, run, state, spec, man, "ButtonLarge", screen, rpath)["written"] is False
    man["assets"][1]["ue_path"] += "_2"
    ue.editor.packages[man["assets"][1]["ue_path"]] = {"kind": "texture"}
    out = build._button_style(ue, run, state, spec, man, "ButtonLarge", screen, rpath)
    assert out["written"] and out["replaced"] and sum(1 for t, _ in ue.editor.log if t == "create_button_style") == n + 1


def test_editing_a_promoted_cell_keeps_its_style(tmp_path, ue, no_ocr):
    """이어서 고치기(--from … --edit …) — 글자 크기만 바꾼 자식 run: 스타일 · 상태 그림은 부모 것 그대로."""
    assert go(tmp_path) == run_pipeline.EXIT_PASS
    ue.editor.paint = True
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"schema_version": 1, "source": "edit", "ops": [{"op": "set", "widget": "ButtonLabel", "path": "font.size", "value": 20}]}), encoding="utf-8")
    child = "R20261125_130000_ButtonLarge"
    code = run_pipeline.main(["--from", RUN_ID, "--edit", str(p), "--run-id", child, "--work-root", str(tmp_path / "work"), "--metrics", str(tmp_path / "m.jsonl"),
                              "--module-root", str(tmp_path / "mod"), "--promoted-root", str(tmp_path / "promoted"), "--content-root", str(tmp_path / "Content")])
    rep = report(tmp_path, child)
    assert code == run_pipeline.EXIT_PASS, rep["message"]
    style = ue.editor.packages[f"/Game/_AutoGen/{child}/BS_ButtonLarge"]
    assert {b["asset"].rsplit("/", 1)[0] for b in style["brushes"].values()} == {f"/Game/_AutoGen/{child}"}


# ---------------------------------------------------------------------------------------------------------------------
# 컨셉 오리기 · 글자 배치

def test_cut_from_crops_one_cell(tmp_path, monkeypatch):
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [])
    sheet = np.zeros((540, 960, 4), np.uint8)
    sheet[100:100 + H, 300:300 + W] = art()
    Image.fromarray(sheet, "RGBA").save(tmp_path / "sheet.png")
    out = tmp_path / "cell"
    args = ["--out-dir", str(out), "--cut-from", str(tmp_path / "sheet.png"), "--keep", f"{600},{200},{2 * W},{2 * H}", "--crop"]
    assert make_concept.main(args) == make_concept.EXIT_OK
    got = np.asarray(Image.open(out / "concept.png"))
    assert got.shape[:2] == (H, W) and (got == art()).all()
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert meta["cut_from"]["crop_px"] == [300, 100, W, H] and meta["cut_from"]["size_1920"] == [2 * W, 2 * H] and meta["text_free_first"]["status"] == "ok"
    bad = make_concept.parse_args(["--out-dir", str(out), "--cut-from", "x.png", "--keep", "0,0,1,1", "--keep", "2,2,1,1", "--crop"])
    assert "exactly one" in make_concept._mode_error(bad)
    with pytest.raises(AssertionError):
        assert make_concept._mode_error(make_concept.parse_args(["--out-dir", str(out), "--crop"])) is None


@pytest.mark.skipif(not (make_concept.FONT_DIR / text_ref.FONT_FILES["semibold"]).is_file(), reason="Pretendard TTF is not on this machine")
def test_text_layout_of_a_cell_uses_its_own_width():
    """칸의 배치 좌표는 칸 폭 기준 — 시안에서 오린 작은 그림에서도 글자 크기는 화면 px(pt × 4/3 × 그림 폭 / 칸 폭)."""
    pic = Image.fromarray(art(), "RGBA")
    items = [{"widget": "ButtonLabel", "value": "준비"}]
    lay = [{"widget": "ButtonLabel", "pos": [W, H], "anchor": "mm", "pt": 26, "weight": "semibold", "color": "#ECE5D6"}]
    _, full = text_ref.draw_items(pic, [{**lay[0], "pos": [W / 2, H / 2]}], items, make_concept.FONT_DIR, base_width=W)
    _, half = text_ref.draw_items(pic, lay, items, make_concept.FONT_DIR, base_width=2 * W)
    assert abs(half[0]["box"][2] * 2 - full[0]["box"][2]) <= 3
    cx = half[0]["box"][0] + half[0]["box"][2] / 2
    assert abs(cx - W / 2) <= 2


def test_a_word_with_thin_bottom_rows_is_measured_whole_when_the_font_is_declared():
    """같은 글꼴로 그린 글자는 '가는 꼬리' 자르기를 쓰지 않는다 — 받침 아래 세로획만 있는 줄이 문턱에 걸리면 한쪽만 잘렸다 [실측 R20261125_155731 '목적지' 높이 비 1.304]."""
    def word(stem):
        m = np.zeros((60, 120), bool)
        for x in (10, 45, 80):
            m[10:33, x:x + 28:2] = True                     # 몸통 23 줄
            m[33:40, x + 20:x + 20 + stem] = True           # 아래 7 줄은 세로획만
        return m
    img = np.zeros((60, 120, 3))
    thin, thick = word(3), word(4)                          # 안티앨리어싱 한 픽셀 차이
    img[thin | thick] = (236, 229, 214)
    cut = [diagnose._stats(m, img)["box"][3] for m in (thin, thick)]
    whole = [diagnose._stats(m, img, same_font=True)["box"][3] for m in (thin, thick)]
    assert cut == [23, 30] and min(whole) >= 29                                # 같은 글자 — 한쪽만 7 줄 잘리던 것이 1 줄(백분위) 안


# ---------------------------------------------------------------------------------------------------------------------
# 바꾸지 않은 것

def test_the_committed_hud_contracts_still_reproduce():
    """손으로 쓴 부모 · 칸 어휘를 더해도 두 HUD 의 생성 헤더는 그대로 — generator_id 와 커밋된 해시를 지금 코드로 다시 낸다."""
    assert cppgen.generator_id() == "1:49a7a94ed467"
    root = config.repo_path(CFG["codegen"]["module_root"])
    for sid in ("CombatHUD", "StatusHUD"):
        screen = config.load_screens()[sid]
        head = cppgen.read_generated(cppgen.target_paths(root, CFG["codegen"]["ui_dir"], screen)["view_base_h"])
        assert head["exists"] and head["owned"] and not head["corrupt"]
        doc = head["contract"]
        assert cppgen.contract_hash(cppgen.contract_doc(sid, screen, CFG["codegen"], doc["bindings"])) == head["hash"], sid


def test_the_llm_still_sees_the_old_vocabulary():
    s = analyze.output_schema()
    text = json.dumps(s)
    assert "UserWidget" not in text and "derived" not in json.dumps(s["$defs"]["asset"]) and "button" not in s["properties"] and "cell" not in s["properties"]["profile"]["enum"]
    assert "class" not in s["$defs"]["widget"]["properties"] and "props" not in s["$defs"]["widget"]["properties"]


def test_verify_uses_the_canvas_only_for_cells():
    prof = config.load_profile("cell")
    assert verify.render_resolutions(CFG, prof, [W, H]) == [[W, H]]
    assert [1920, 1080] in verify.render_resolutions(CFG, config.load_profile("hud"), [1920, 1080])
