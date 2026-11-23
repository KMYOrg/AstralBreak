"""1b 후속 L-2 — 글자 없는 컨셉부터 + 글자 참고판: 참고판 프롬프트 · 정합 + 글자 획만 옮겨 붙이기 · 칸 밖 검사 · normalize(원본 아트 = 아트 ·
글자 없는 판) · 글자 그린 아트 물러남 · make_concept --text-free-first(가짜 codex)."""
from __future__ import annotations

import json
import pathlib
import types

import numpy as np
import pytest
import yaml
from PIL import Image

from core import config, ocr
from core.run import Run
from gen import codex, diagnose as dg, text_ref
from stages import normalize, refine

CFG = config.load_pipeline()
FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "m4_combat_hud_l2"
PANEL, GOLD, GLYPH = (40, 30, 60), (232, 181, 74), (240, 230, 200)


def _art(h=120, w=240):
    """투명 바탕 위 금테 패널(글자 없음) + 둘레 옅은 빛(반투명 4 px) → (곧은 색, 알파)."""
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    col[36:104, 26:214], a[36:104, 26:214] = GOLD, 0.3
    col[40:100, 30:210], a[40:100, 30:210] = PANEL, 1.0
    for y0, y1, x0, x1 in ((40, 42, 30, 210), (98, 100, 30, 210), (40, 100, 30, 32), (40, 100, 208, 210)):
        col[y0:y1, x0:x1] = GOLD
    return col, a


def _glyph(h=120, w=240, dy=0, dx=0):
    g = np.zeros((h, w), bool)
    g[60 + dy:80 + dy, 90 + dx:94 + dx] = g[60 + dy:64 + dy, 90 + dx:130 + dx] = g[60 + dy:80 + dy, 126 + dx:130 + dx] = True
    return g


def _ref(col, a, shift=(1, 2), tone=12.0, extra=False):
    """codex 참고판 흉내 — 그림 전체를 다시 그려 색조가 밝고(tone) (dy, dx) 어긋남 · 옅은 바깥 빛을 불투명 갈색 띠로 + 패널 가운데 글자 'П'
    (+ extra 면 아트가 비운 먼 자리에 새 덩어리)."""
    t_col = np.clip(col + tone * (a[..., None] > 0), 0, 255)
    t_a = a.copy()
    rim = (a > 0.05) & (a < 0.9)
    t_col[rim], t_a[rim] = (150, 110, 60), 1.0                                   # [실측 L-2 첫 참고판] 옅은 빛 → 불투명 띠
    g = _glyph(*a.shape)
    t_col[g] = GLYPH
    if extra:
        h, w = a.shape
        t_col[0:h // 7, 0:w // 9], t_a[0:h // 7, 0:w // 9] = (200, 60, 60), 1.0
    t_col = np.roll(t_col, shift, axis=(0, 1))
    t_a = np.roll(t_a, shift, axis=(0, 1))
    return t_col, t_a


def _fake_detect(scale=1):
    """참고판에만 글자 상자 — 상자 안 밝은 픽셀(글자색)이 있으면."""
    def detect(image, min_score=0.7, **kw):
        arr = np.asarray(image.convert("RGB") if hasattr(image, "convert") else Image.open(image).convert("RGB")).astype(float)
        y0, y1, x0, x1 = 55 * scale, 86 * scale, 85 * scale, 136 * scale
        hit = (np.abs(arr[y0:y1, x0:x1] - np.array(GLYPH)).max(axis=2) < 30).sum() > 10 * scale * scale
        boxes = [{"box": [x0, y0, x1 - x0, y1 - y0], "score": 0.9}] if hit else []
        return {"engine": "fake", "count": len(boxes), "max_score": 0.9 if boxes else 0.0, "boxes": boxes, "min_score": min_score, "min_area_px": 60}
    return detect


def test_text_ref_prompt_lists_the_inputs_texts_with_slot_descriptions_only():
    inputs = config.load_yaml(FIX / "inputs.yaml")
    items = text_ref.text_items(inputs)
    assert [it["value"] for it in items] == ["오의 불가", "체인", "체인 버스트", "4.2", "2/4", "3"]   # static_text 값 · sample(format 대로)
    p = text_ref.text_ref_prompt(inputs)
    assert '"4.2" — large cream-colored number' in p and "transparent" in p and " px" not in p                      # 칸은 설명만 — 좌표 없음
    assert text_ref.format_sample({"type": "number", "format": "0", "sample": 3}) == "3" and text_ref.format_sample({"type": "flag", "sample": True}) is None


def test_merge_pastes_only_the_glyph_strokes_onto_the_original_art():
    col, a = _art()
    t_col, t_a = _ref(col, a)
    c_col, c_a, (tw_col, _), rec = text_ref.merge(col, a, t_col, t_a, detect=_fake_detect())
    assert rec["used"] and np.abs(rec["shift_applied"]).tolist() == [2, 1] and rec["glyph_px"] > 150
    g = _glyph()
    assert np.abs(c_col[g] - np.array(GLYPH)).max() < 40                                        # 글자 획 = 참고판(정합 뒤 제자리)
    paste = rec["paste"]
    assert np.array_equal(c_col[~paste], col[~paste]) and np.array_equal(c_a[~paste], a[~paste])   # 그 밖은 원본 아트 픽셀 그대로
    assert np.allclose(c_col[72, 110], PANEL) and np.allclose(c_col[90, 50], PANEL)              # 글자 둘레 바탕도 아트(다시 그린 색조 안 섞임)
    assert rec["checks"]["outside_solid_big_frac"] == 0.0 and rec["ocr"]["art_boxes"] == []
    assert rec["checks"]["fringe_alpha_frac"] > 0.05 and not paste[(a > 0.05) & (a < 0.9)].any()   # 다시 그린 반투명 가장자리 — 기록만, 붙이지 않음


def test_merge_rejects_a_text_reference_that_changed_the_art_outside_the_slots():
    col, a = _art()
    t_col, t_a = _ref(col, a, extra=True)
    c_col, c_a, _, rec = text_ref.merge(col, a, t_col, t_a, detect=_fake_detect())
    assert not rec["used"] and "outside the text boxes" in rec["reason"] and rec["checks"]["outside_far_new_frac"] > text_ref.OUT_MAX
    assert np.array_equal(c_col, col) and np.array_equal(c_a, a)                                 # 참고판 안 씀 — 레퍼런스 = 원본 아트
    far = np.roll(t_col, (0, 40), axis=(0, 1)), np.roll(t_a, (0, 40), axis=(0, 1))
    assert not text_ref.merge(col, a, far[0], far[1], detect=_fake_detect())[3]["used"]


def _l2_inputs(tmp_path, with_ref=True, scale=4):
    """작은 원본 아트 · 참고판(16:9 — normalize 가 1920 × 1080 으로 늘림)과 fixture inputs 사본."""
    (tmp_path / "in").mkdir()
    col, a = _art(270, 480)
    Image.fromarray(np.dstack([col, a * 255]).astype(np.uint8), "RGBA").save(tmp_path / "in" / "concept.png")
    if with_ref:
        t_col, t_a = _ref(col, a, shift=(0, 0), tone=10.0)
        Image.fromarray(np.dstack([t_col, t_a * 255]).astype(np.uint8), "RGBA").save(tmp_path / "in" / "concept_text_ref.png")
    data = yaml.safe_load((FIX / "inputs.yaml").read_text(encoding="utf-8"))
    p = tmp_path / "in" / "inputs.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    run = Run("R20261118_200001_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    return run, p


def test_normalize_l2_uses_the_original_art_as_art_and_text_free_plate(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "detect", _fake_detect(scale=4))
    run, p = _l2_inputs(tmp_path)
    detail = normalize.run(run, types.SimpleNamespace(inputs=str(p), concept=None, spec_dir=None))
    bg = run.read_json("normalize.json")["background"]
    assert bg["concept_source"]["value"] == "generated_textfree" and "L-2 original text-free art, text reference aligned" in detail
    assert bg["art"] == {"used": True, "role": "original", "color": "reference_art_color.png", "alpha": "reference_art_alpha.png",
                         "element_free": False, "text_residue": False, "text_ref_used": True}
    assert bg["notext"]["used"] and bg["notext"]["text_residue"] is False and bg["text_ref"]["used"]
    assert dg.art_mode(bg) and dg.residue_free(bg["art"]) and not dg.art_element_free(bg) and refine.art_files(run) == ("reference_art_color.png",
                                                                                                                       "reference_art_alpha.png")
    ref = np.asarray(Image.open(run.path("reference_color.png")), float)
    art = np.asarray(Image.open(run.path("reference_art_color.png")), float)
    paste = np.asarray(Image.open(run.path("reference_textref_paste.png"))) > 127
    assert paste.any() and np.array_equal(ref[~paste], art[~paste])                             # 레퍼런스 = 원본 아트 + 참고판 글자 획
    assert np.abs(ref[280, 366] - np.array(GLYPH)).max() < 40 and np.allclose(art[280, 366], PANEL, atol=2)   # 'П' 왼쪽 획(× 4)
    assert np.array_equal(np.asarray(Image.open(run.path("reference_notext_color.png"))), np.asarray(Image.open(run.path("reference_art_color.png"))))


def test_normalize_l2_without_a_text_reference_keeps_the_art_as_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "detect", _fake_detect(scale=4))
    run, p = _l2_inputs(tmp_path, with_ref=False)
    normalize.run(run, types.SimpleNamespace(inputs=str(p), concept=None, spec_dir=None))
    bg = run.read_json("normalize.json")["background"]
    assert bg["art"]["used"] and not bg["art"]["text_ref_used"] and "does not exist" in bg["text_ref"]["reason"]
    assert np.array_equal(np.asarray(Image.open(run.path("reference_color.png"))), np.asarray(Image.open(run.path("reference_art_color.png"))))


def test_concept_source_falls_back_to_l1_when_codex_drew_text_twice(tmp_path):
    c = tmp_path / "concept.png"
    c.write_bytes(b"")
    side = tmp_path / "concept.json"
    side.write_text(json.dumps({"kind": "concept", "generator": "codex built-in image_gen", "text_free_first": {"status": "ok"}}), encoding="utf-8")
    assert normalize.concept_source({}, c)["value"] == "generated_textfree"
    side.write_text(json.dumps({"kind": "concept", "generator": "codex built-in image_gen", "text_free_first": {"status": "text_drawn"}}), encoding="utf-8")
    src = normalize.concept_source({"concept_source": "generated_textfree"}, c)
    assert src["value"] == "generated" and "L-1" in src["textfree_fallback"]


def test_glow_strength_is_fitted_with_the_glow_colour_alpha():
    """빛 세기 — 둘 다 빛나고 띠 밝기 비가 1.25 를 넘으면 알파를 띠 밝기 비로(엔진 빛은 알파에 거의 비례 — 30.8 ↔ 41.0 · 알파 0.957 → 0.72),
    비슷하면 그대로 · 끝이면 못 감."""
    from stages import style
    gl = {"size": 9, "color": "#FF1606F4"}
    assert abs(dg.glow_alpha({"glow": gl}) - 0xF4 / 255) < 1e-6 and dg.glow_alpha({"glow": {"size": 0}}) is None
    st = style._glow_strength(gl, {"peak": 30.8, "size": 9}, {"peak": 41.0, "size": 9, "bg_l": 0.0}, 8.0)
    assert st["color"].startswith("#FF1606") and 0.68 < st["alpha"][1] < 0.76
    assert style._glow_strength(gl, {"peak": 30.7}, {"peak": 33.0, "bg_l": 0.0}, 8.0) is None                    # 비 1.07 — 근사 안
    assert style._glow_strength({"size": 9, "color": "#FF160626"}, {"peak": 10.0}, {"peak": 30.0, "bg_l": 0.0}, 8.0) is None   # 알파 0.15 — 더 못 내림


def test_glyph_density_ignores_letter_spacing():
    """획 밀도는 잉크 있는 열만 — 자간(빈 열)이 늘어도 같다(굵기 판정이 위치 판 자간에 흔들리던 것). 상자 · 빈 열 수는 그대로 잰다."""
    img = np.zeros((40, 200, 3))
    tight, wide = np.zeros((40, 200), bool), np.zeros((40, 200), bool)
    for i in range(4):
        tight[10:30, 20 + i * 14:30 + i * 14] = True                 # 글자 폭 10 · 틈 4
        wide[10:30, 20 + i * 18:30 + i * 18] = True                  # 글자 폭 10 · 틈 8
    a, b = dg._stats(tight, img), dg._stats(wide, img)
    assert a["density"] == b["density"] == 1.0 and b["box"][2] > a["box"][2] and b["gap_cols"] > a["gap_cols"]


def test_finalize_hides_only_the_hidden_widgets_the_concept_does_not_draw_in_the_designer(tmp_path):
    """디자이너는 Visibility 를 무시한다 — 저장 직전 컨셉이 안 그린 숨은 위젯(진단 force_visible_extra)만 designer_hidden 을 켜 다시 적용."""
    from conftest import fixture_spec
    from core import spec as spec_mod
    from stages import build, finalize
    run = Run("R20261118_200002_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    spec = fixture_spec()
    for w in spec["widgets"]:
        if w["id"] in ("UltReadyGlow", "BurstBanner"):
            w["visibility"] = "collapsed"
    run.write_json("spec.json", spec)
    run.write_json("manifest.json", {"assets": [{"asset_id": a["asset_id"], "ue_path": f"/Game/T/{a['asset_id']}"} for a in spec.get("assets", [])]})
    run.write_json("diagnosis.json", {"state": {"force_visible_extra": ["UltReadyGlow"], "drawn_hidden_at_start": ["BurstBanner"]}})
    state = build.load_state(run)
    state.update(wbp={"asset_path": "/Game/_AutoGen/R/WBP_CombatHUD", "object_path": "/Game/_AutoGen/R/WBP_CombatHUD.WBP_CombatHUD",
                      "parent_class": "/Script/UMG.UserWidget", "created_attempt": 1}, revision="sha1:" + "1" * 40, session=1)
    calls = []

    class TC:
        def call(self, name, params):
            calls.append((name, params))
            return {"revision_after": "sha1:" + "2" * 40, "ops": [{"op": "set", "widget": "UltReadyGlow"}], "verified": True}
    rec = finalize._designer_hidden(run, TC(), state)
    assert rec["applied"] and rec["widgets"] == ["UltReadyGlow"] and state["revision"] == "sha1:" + "2" * 40           # 배너(컨셉이 그림)는 디자이너에 보임
    sent = {w["id"]: w for w in calls[0][1]["spec"]["widgets"]}
    assert sent["UltReadyGlow"]["designer_hidden"] is True and "designer_hidden" not in sent["BurstBanner"]
    assert calls[0][1]["expected_revision"] == "sha1:" + "1" * 40 and run.read_json("build.json")["revision"] == "sha1:" + "2" * 40
    assert finalize._designer_hidden(run, TC(), state)["applied"] is False and len(calls) == 1                # 이미 컨셉 상태 — 다시 적용 안 함
    assert "designer_hidden" not in spec_mod.normalize_widget({"id": "A", "type": "Image", "designer_hidden": False}, None, {})


@pytest.mark.parametrize("texty", [(True, False), (True, True)])
def test_make_concept_text_free_first_retries_once_then_falls_back(tmp_path, monkeypatch, texty):
    import make_concept
    out = tmp_path / "fx"
    out.mkdir()
    (out / "concept_prompt.md").write_text((FIX / "concept_prompt.md").read_text(encoding="utf-8"), encoding="utf-8")
    (out / "inputs.yaml").write_text((FIX / "inputs.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    calls = []
    col, a = _art()

    def fake_generate(prompt, dest, gen_dir, cfg, *, budget, refs=None, ref_purpose="", meta=None, cli=None, edit=False):
        calls.append({"prompt": prompt, "edit": edit, "meta": meta})
        img = _ref(col, a, shift=(0, 0), tone=6.0) if edit else (col, a)
        pathlib.Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.dstack([img[0], img[1] * 255]).astype(np.uint8), "RGBA").save(dest)
        return {"sha256": "x", "size": [240, 120], "thread_id": f"t{len(calls)}", "has_alpha_channel": True, "transparent_ratio": 0.5}
    monkeypatch.setattr(codex, "preflight", lambda cfg, cli=None: {"version": "0.166.0"})
    monkeypatch.setattr(codex, "generate", fake_generate)
    seen = iter(texty)
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [{"box": [1, 1, 20, 10], "score": 0.8}] if next(seen) else [])
    monkeypatch.setattr(ocr, "detect", _fake_detect())
    assert make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "w"), "--text-free-first"]) == make_concept.EXIT_OK
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert [c["meta"]["purpose"] for c in calls][:2] == ["concept_text_free_first", "concept_text_free_first"]
    assert "Draw NO text at all" in calls[0]["prompt"] and "absolutely no text" in calls[1]["prompt"]
    if texty[1]:                                                                                  # 두 번 다 글자 → 글자 든 컨셉(L-1), 참고판 없음
        assert len(calls) == 2 and meta["text_free_first"]["status"] == "text_drawn" and not (out / "concept_text_ref.png").exists()
    else:
        assert len(calls) == 3 and calls[2]["edit"] and '"체인 버스트"' in calls[2]["prompt"] and meta["text_free_first"]["status"] == "ok"
        rmeta = json.loads((out / "concept_text_ref.json").read_text(encoding="utf-8"))
        assert rmeta["kind"] == "concept_text_ref" and rmeta["edited_from"] == "concept.png" and rmeta["check"]["used"]


def test_make_concept_only_art_then_only_text_ref(tmp_path, monkeypatch):
    """--only art = 원본 아트까지만(후보 고르기 — inputs 없어도 됨) · --only text_ref = 그 아트에 참고판만. 아트가 기록과 다르면 거절."""
    import hashlib
    import make_concept
    out = tmp_path / "fx"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a gauge and a panel", encoding="utf-8")
    calls = []
    col, a = _art()

    def fake_generate(prompt, dest, gen_dir, cfg, *, budget, refs=None, ref_purpose="", meta=None, cli=None, edit=False):
        calls.append({"prompt": prompt, "edit": edit, "refs": refs, "limit": budget.limit})
        img = _ref(col, a, shift=(0, 0), tone=6.0) if edit else (col, a)
        pathlib.Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.dstack([img[0], img[1] * 255]).astype(np.uint8), "RGBA").save(dest)
        return {"sha256": hashlib.sha256(pathlib.Path(dest).read_bytes()).hexdigest(), "size": [240, 120], "thread_id": "t", "has_alpha_channel": True}
    monkeypatch.setattr(codex, "preflight", lambda cfg, cli=None: {"version": "0.166.0"})
    monkeypatch.setattr(codex, "generate", fake_generate)
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [])
    monkeypatch.setattr(ocr, "detect", _fake_detect())
    base = ["--out-dir", str(out), "--work-root", str(tmp_path / "w")]
    assert make_concept.main([*base, "--with-text", "--only", "art"]) == make_concept.EXIT_FAIL                   # 글자를 그리는 길과는 같이 못 씀
    assert make_concept.main([*base, "--transparent"]) == make_concept.EXIT_FAIL and not calls                    # 새 그림은 이미 투명 — 글자를 그리려면 --with-text
    assert make_concept.main([*base, "--only", "art"]) == make_concept.EXIT_OK                                    # L-2 가 기본(--text-free-first 는 옛 이름)
    art = (out / "concept.png").read_bytes()
    assert len(calls) == 1 and not calls[0]["edit"] and calls[0]["limit"] == 2 and not (out / "concept_text_ref.png").exists()
    (out / "inputs.yaml").write_text((FIX / "inputs.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    assert make_concept.main([*base, "--text-free-first", "--only", "text_ref"]) == make_concept.EXIT_OK
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert len(calls) == 2 and calls[1]["edit"] and calls[1]["limit"] == 1 and (out / "concept.png").read_bytes() == art
    assert meta["text_free_first"]["text_ref"] == "concept_text_ref.png" and (out / "concept_text_ref.json").is_file()
    (out / "concept.png").write_bytes(art + b"x")                                                                # 기록과 다른 아트
    assert make_concept.main([*base, "--text-free-first", "--only", "text_ref", "--force"]) == make_concept.EXIT_FAIL and len(calls) == 2
