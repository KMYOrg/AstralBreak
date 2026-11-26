"""L-2 기본 전환(11-23) — OCR 로 길 고르기(gen/concept_route · normalize.concept_source) · 참고 그림(--style-ref) · 시안에서 오리기(--cut-from) ·
접히는 위젯의 빛 · 넘침 옮기기(stages/layer.grow_toggles) · 검사 hidden_halo · 반투명 면 위 참고판 글자(gen/text_ref)."""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import types

import numpy as np
import pytest
from PIL import Image

from core import config, ocr, schema
from core import spec as spec_mod
from core.run import Run
from gen import codex, concept_route, state_check, text_ref
from gen import diagnose as dg
from stages import layer, normalize

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "m4_combat_hud_l2"


# ---------------------------------------------------------------------------------------------------------------------
# ② OCR 로 길 고르기

def _detector(rows):
    """rows = [(원본 좌표 상자, 1 배 점수, 2 배 점수 | None)] — 그림 폭으로 배율을 안다."""
    def detect(im, *, min_score=0.0, max_boxes=20, **kw):
        k = im.width / 400.0
        out = [{"box": [round(v * k) for v in b], "score": (s1 if k < 1.5 else s2)} for b, s1, s2 in rows if (s1 if k < 1.5 else s2) is not None]
        return {"boxes": [b for b in out if b["score"] >= min_score]}
    return detect


@pytest.mark.parametrize("rows,decision,score", [
    ([([40, 40, 80, 20], 0.88, 0.85)], "text", 0.85),                          # 글자 — 배율을 바꿔도 그대로
    ([([40, 40, 80, 20], 0.76, 0.64)], "text_free", 0.64),                     # 장식 — 흔들림(낮은 쪽)
    ([([40, 40, 80, 20], 0.9, None)], "text_free", 0.0),                       # 2 배에서 다시 안 잡힘
    ([([40, 40, 80, 20], 0.8, 0.74)], "ambiguous", 0.74),
    ([([10, 10, 300, 120], 0.95, 0.95)], "text_free", 0.0),                    # 글줄로 보기엔 너무 높은 상자(막대 여러 줄)
])
def test_route_score_is_what_stays_across_scales(rows, decision, score):
    r = concept_route.judge(Image.new("RGB", (400, 300)), detect=_detector(rows))
    assert r["decision"] == decision and r["score"] == score
    assert set(r["per_backdrop"]) == {"opaque"}                                # 불투명 그림은 바탕을 바꿔 보지 않는다
    r2 = concept_route.judge(Image.new("RGBA", (400, 300), (10, 10, 10, 0)), detect=_detector(rows))
    assert set(r2["per_backdrop"]) == {"gray", "black", "white"} and r2["decision"] == decision and len(r2["boxes"]) <= 1


def test_concept_source_inputs_win_then_our_record_then_ocr(tmp_path, monkeypatch):
    c = tmp_path / "concept.png"
    Image.new("RGB", (16, 16)).save(c)
    seen = []

    def stub(decision):
        def judge(p):
            seen.append(p)
            return {"decision": decision, "score": 0.1, "boxes": []}
        monkeypatch.setattr(normalize, "concept_route", types.SimpleNamespace(judge=judge, FREE_MAX=0.7))
    stub("text_free")
    for v in ("external", "generated", "external_textfree"):
        assert normalize.concept_source({"concept_source": v}, c)["value"] == v
    assert seen == []                                                          # 입력이 언제나 먼저 — OCR 을 부르지 않는다
    r = normalize.concept_source({}, c)
    assert r["value"] == "external_textfree" and r["ocr"]["decision"] == "text_free" and "OCR finds no text" in r["from"]
    stub("ambiguous")
    assert normalize.concept_source({}, c)["value"] == "external"              # 모호는 L-1(글자 든 그림을 정답으로 굽는 쪽이 더 위험)
    stub("text")
    assert normalize.concept_source({}, c)["value"] == "external"
    n = len(seen)
    (tmp_path / "concept.json").write_text(json.dumps({"kind": "concept", "generator": "codex", "text_free_first": {"status": "ok"}}), encoding="utf-8")
    assert normalize.concept_source({}, c)["value"] == "generated_textfree" and len(seen) == n     # 우리가 글자 없이 만든 기록 — OCR 없이
    (tmp_path / "concept.json").write_text(json.dumps({"kind": "concept", "generator": "codex image_gen"}), encoding="utf-8")
    stub("text_free")
    assert normalize.concept_source({}, c)["value"] == "generated_textfree"

    def boom(p):
        raise RuntimeError("no model")
    monkeypatch.setattr(normalize, "concept_route", types.SimpleNamespace(judge=boom, FREE_MAX=0.7))
    r = normalize.concept_source({}, c)
    assert r["value"] == "generated" and r["ocr"]["decision"] == "failed"      # 판정 실패도 L-1


def _panel_rgba(h=240, w=427):
    arr = np.zeros((h, w, 4), np.uint8)
    arr[80:160, 100:330] = (30, 28, 34, 230)
    arr[80:83, 100:330] = arr[157:160, 100:330] = (232, 228, 214, 255)
    return arr


def test_normalize_text_free_picture_without_a_reference_goes_l2_spec_only(tmp_path, monkeypatch):
    """받은 글자 없는 그림(출처 기록 없음) → OCR text_free → L-2(원본 아트 = 정답), 참고판이 없으니 글자는 사양만."""
    monkeypatch.setattr(normalize, "concept_route", types.SimpleNamespace(judge=lambda p: {"decision": "text_free", "score": 0.0, "boxes": []}, FREE_MAX=0.7))
    Image.fromarray(_panel_rgba(), "RGBA").save(tmp_path / "got.png")
    inputs = config.load_yaml(FIX / "inputs.yaml")
    inputs["concept"] = "got.png"
    inputs.pop("concept_source")
    inputs.pop("concept_text_ref")
    p = tmp_path / "inputs.yaml"
    p.write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
    run = Run("R20261123_000000_CombatHUD", tmp_path / "work", config.load_pipeline(), tmp_path / "m.jsonl")
    run.create()
    detail = normalize.run(run, types.SimpleNamespace(inputs=str(p), concept=None, spec_dir=None))
    bg = run.read_json("normalize.json")["background"]
    assert bg["concept_source"]["value"] == "external_textfree" and bg["concept_source"]["text_style"] == "spec_only"
    assert bg["art"]["role"] == "original" and dg.art_mode(bg) and "no text reference" in detail
    assert schema.errors("inputs", {**inputs, "concept_source": "external_textfree"}) == []


# ---------------------------------------------------------------------------------------------------------------------
# ① · ③ 컨셉 도구

def _fake_codex(monkeypatch, calls):
    def fake_generate(prompt, dest, gen_dir, cfg, *, budget, refs=None, ref_purpose="", meta=None, cli=None, edit=False):
        calls.append({"prompt": prompt, "refs": refs, "ref_purpose": ref_purpose, "edit": edit})
        pathlib.Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(_panel_rgba(), "RGBA").save(dest)
        budget.add({"ok": True})
        return {"sha256": hashlib.sha256(pathlib.Path(dest).read_bytes()).hexdigest(), "size": [427, 240], "thread_id": "t", "has_alpha_channel": True}
    monkeypatch.setattr(codex, "preflight", lambda cfg, cli=None: {"version": "0.166.0"})
    monkeypatch.setattr(codex, "generate", fake_generate)


def test_style_ref_takes_only_ours_or_user_pictures_and_never_probe_screens(tmp_path, monkeypatch):
    import make_concept
    calls: list = []
    _fake_codex(monkeypatch, calls)
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [])
    out = tmp_path / "fx"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a gauge", encoding="utf-8")
    ours = tmp_path / "ours"
    ours.mkdir()
    Image.fromarray(_panel_rgba(), "RGBA").save(ours / "concept.png")
    base = ["--out-dir", str(out), "--work-root", str(tmp_path / "w"), "--only", "art", "--style-ref", str(ours / "concept.png")]
    assert make_concept.main(base) == make_concept.EXIT_FAIL and not calls                           # 출처를 모르는 그림
    sha = hashlib.sha256((ours / "concept.png").read_bytes()).hexdigest()
    (ours / "concept.json").write_text(json.dumps({"generator": "codex built-in image_gen", "sha256": sha}), encoding="utf-8")
    assert make_concept.main(base) == make_concept.EXIT_OK
    assert calls[0]["refs"] and "mood" in calls[0]["ref_purpose"] and not calls[0]["edit"]
    with Image.open(calls[0]["refs"][0]) as im:                                                      # 투명 그림은 어두운 중립 바탕에 얹은 사본
        assert im.mode == "RGB" and im.getpixel((0, 0)) == make_concept.STYLE_REF_BG
    assert json.loads((out / "concept.json").read_text(encoding="utf-8"))["style_refs"][0]["source"] == "ours"
    probe = tmp_path / "work" / "_probe"
    probe.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(probe / "shot.png")
    n = len(calls)
    assert make_concept.main(["--out-dir", str(out), "--only", "art", "--force", "--style-ref", str(probe / "shot.png"), "--style-ref-from-user"]) == make_concept.EXIT_FAIL
    user = tmp_path / "given.png"
    Image.new("RGB", (8, 8)).save(user)
    assert make_concept.main([*base[:4], "--force", "--style-ref", str(user), "--style-ref-from-user", "--only", "art"]) == make_concept.EXIT_OK
    assert len(calls) == n + 1 and json.loads((out / "concept.json").read_text(encoding="utf-8"))["style_refs"][0]["source"] == "user"


def test_text_free_retry_stops_at_the_call_limit_and_keeps_the_picture(tmp_path, monkeypatch):
    import make_concept
    calls: list = []
    _fake_codex(monkeypatch, calls)
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [{"box": [1, 1, 20, 10], "score": 0.8}])
    out = tmp_path / "fx"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a gauge", encoding="utf-8")
    assert make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "w"), "--only", "art", "--max-calls", "1"]) == make_concept.EXIT_OK
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert len(calls) == 1 and (out / "concept.png").is_file() and meta["text_free_first"]["status"] == "text_drawn"


def test_cut_from_keeps_the_boxes_pixel_for_pixel_and_refuses_to_cut_through(tmp_path, monkeypatch):
    import make_concept
    monkeypatch.setattr(make_concept, "_ocr_boxes", lambda p: [])
    sheet = np.zeros((108, 192, 4), np.uint8)
    sheet[10:30, 20:80] = (200, 190, 170, 255)
    sheet[60:90, 100:180] = (20, 20, 24, 180)
    src = tmp_path / "sheet.png"
    Image.fromarray(sheet, "RGBA").save(src)
    out = tmp_path / "fx"
    ok = ["--out-dir", str(out), "--cut-from", str(src), "--keep", "100,50,800,300"]                  # 1920 기준 → 192 폭에서 10 배 작게
    assert make_concept.main(ok) == make_concept.EXIT_OK
    with Image.open(out / "concept.png") as im:
        got = np.asarray(im)
    assert (got[5:35, 10:90] == sheet[5:35, 10:90]).all() and not got[40:].any()
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert meta["text_free_first"]["status"] == "ok" and meta["cut_from"]["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert normalize.concept_source({}, out / "concept.png")["value"] == "generated_textfree"
    assert make_concept.main(["--out-dir", str(tmp_path / "fx2"), "--cut-from", str(src), "--keep", "100,50,400,300"]) == make_concept.EXIT_FAIL   # 요소를 가른다
    assert not (tmp_path / "fx2" / "concept.png").exists()
    assert make_concept.main(["--out-dir", str(tmp_path / "fx3"), "--cut-from", str(src)]) == make_concept.EXIT_FAIL


# ---------------------------------------------------------------------------------------------------------------------
# ④ 접히는 위젯의 빛 · 넘침

W, H = 600, 400
BANNER = [100, 60, 300, 60]


def _toggle_spec():
    def canvas(bb, z=1):
        return {"kind": "canvas", "anchors": [0.5, 0, 0.5, 0], "alignment": [0.5, 0], "position": [bb[0] + bb[2] / 2 - W / 2, bb[1]], "size": [bb[2], bb[3]], "z": z}
    return {"schema_version": 1, "profile": "hud", "canvas": [W, H], "root": "Root",
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Banner", "type": "Border", "parent": "Root", "bbox_intent": list(BANNER), "slot": canvas(BANNER), "visibility": "collapsed",
                         "binding": {"kind": "flag", "data": "b"}, "style": {"brush": {"draw_as": "box", "asset": "banner", "margin": [0.1, 0.2, 0.1, 0.2]}}},
                        {"id": "BannerOverlay", "type": "Overlay", "parent": "Banner", "bbox_intent": list(BANNER),
                         "slot": {"kind": "border", "padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill"}},
                        {"id": "Label", "type": "TextBlock", "parent": "BannerOverlay", "bbox_intent": [120, 70, 80, 40],
                         "slot": {"kind": "overlay", "padding": [20, 0, 0, 0], "h_align": "left", "v_align": "center"}, "text": {"source": "static", "value": "체인"}},
                        {"id": "Frame", "type": "Image", "parent": "Root", "bbox_intent": [100, 300, 300, 40], "slot": canvas([100, 300, 300, 40]),
                         "style": {"brush": {"draw_as": "image", "asset": "frame"}}}],
            "assets": [{"asset_id": a, "kind": "frame", "provenance": "codex", "source_mode": "extract", "size": [300, 60 if a == "banner" else 40],
                        "ref_bbox": [0, 0, 8, 8], "prompt": "p", **({"nine_slice": True, "margin": [0.1, 0.2, 0.1, 0.2]} if a == "banner" else {})} for a in ("banner", "frame")]}


def _toggle_alpha():
    a = np.zeros((H, W))
    a[44:136, 80:420] = 0.3                 # 배너 둘레 빛(위아래 16 · 양옆 20 px)
    a[60:120, 100:400] = 0.9
    a[290:350, 90:410] = 0.4                # 정적 프레임 + 빛
    a[300:340, 100:400] = 1.0
    a[10:13, 500:503] = 0.5                 # 잡티
    return a


def test_grow_moves_the_glow_of_a_collapsible_region_into_its_own_box():
    spec = _toggle_spec()
    a = _toggle_alpha()
    omap = layer.territory.owner_map(spec, a.shape)
    g = layer.grow_toggles(spec, a)
    assert [t["widget"] for t in g] == ["Banner"] and g[0]["grow"] == [20, 16, 20, 16] and g[0]["px"] == int((a[44:136, 80:420] == 0.3).sum())
    idx = spec_mod.widget_index(spec)
    assert idx["Banner"]["bbox_intent"] == [80, 44, 340, 92] and idx["Banner"]["slot"]["size"] == [340, 92] and idx["Banner"]["slot"]["position"] == [-50, 44]
    assert idx["BannerOverlay"]["slot"]["padding"] == [20, 16, 20, 16] and idx["BannerOverlay"]["bbox_intent"] == BANNER     # 글자 묶음은 화면 자리 그대로
    assert idx["Label"]["slot"]["padding"] == [20, 0, 0, 0] and idx["Label"]["bbox_intent"] == [120, 70, 80, 40]
    asset = next(x for x in spec["assets"] if x["asset_id"] == "banner")
    assert asset["size"] == [340, 92] and asset["margin"][0] == pytest.approx((0.1 * 300 + 20) / 340, abs=1e-3)
    assert idx["Frame"]["bbox_intent"] == [100, 300, 300, 40]                    # 정적 장식은 그대로
    fn = layer.classify(spec, {})
    st = layer.static_widgets(spec, fn)
    pl = layer.plan(spec, a, fn, st, own={"Banner": g[0]["mask"]}, omap=omap)
    assert len(pl["plates"]) == 1 and pl["plates"][0]["region"] == "Frame"       # 배너 빛은 판이 아니다
    assert not pl["plates"][0]["mask"][:140].any() and pl["plates"][0]["mask"][290:350, 90:410].all()
    layer.apply(spec, fn, st, pl["plates"])
    assert schema.errors("spec", spec) == [] and spec_mod.validate_semantics(spec) == []


def test_grow_keeps_neighbour_pixels_inside_the_grown_box_out_of_the_mask():
    """넓힌 네모 안에 든 이웃 영역의 픽셀은 자기 마스크가 아니다 — 판이 그대로 그린다."""
    spec = _toggle_spec()
    spec["widgets"].append({"id": "Deco", "type": "Image", "parent": "Root", "bbox_intent": [70, 30, 24, 24],
                            "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [70, 30], "size": [24, 24], "z": 1},
                            "style": {"brush": {"draw_as": "image", "asset": "deco"}}})
    spec["assets"].append({"asset_id": "deco", "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [24, 24], "ref_bbox": [0, 0, 8, 8], "prompt": "p"})
    a = _toggle_alpha()
    a[30:54, 70:94] = 1.0
    omap = layer.territory.owner_map(spec, a.shape)
    g = layer.grow_toggles(spec, a)
    m = g[0]["mask"]
    assert not m[30:54, 70:94].any() and m[60:120, 100:400].all() and ["Banner", "Deco"] in spec["allow_overlap"]
    fn = layer.classify(spec, {})
    pl = layer.plan(spec, a, fn, layer.static_widgets(spec, fn), own={"Banner": m}, omap=omap)
    assert any(p["mask"][30:54, 70:94].all() for p in pl["plates"])


def test_grow_is_refused_with_a_reason_when_children_cannot_keep_their_place():
    spec = _toggle_spec()
    idx = spec_mod.widget_index(spec)
    idx["Banner"]["slot"]["anchors"] = [0, 0, 1, 0]                              # 화면 따라 늘어나는 영역
    before = copy.deepcopy(spec)
    g = layer.grow_toggles(spec, _toggle_alpha())
    assert "skipped" in g[0] and "changes size" in g[0]["skipped"] and spec == before
    spec2 = _toggle_spec()
    spec2["assets"] = [x for x in spec2["assets"] if x["asset_id"] != "banner"] + [{"asset_id": "banner", "kind": "frame", "provenance": "procedural", "size": [300, 60]}]
    assert "no brush cut from the concept" in layer.grow_toggles(spec2, _toggle_alpha())[0]["skipped"]


def _halo_scene(in_plate: bool):
    """배너(접힘) + 둘레 빛 — 빛이 정적 판에 있거나(예전) 배너 텍스처에 있다(고침)."""
    a = np.zeros((H, W, 4), float)
    a[44:136, 80:420, :3], a[44:136, 80:420, 3] = (230, 200, 120), 0.3 * 255
    a[60:120, 100:400, :3], a[60:120, 100:400, 3] = (40, 30, 30), 0.9 * 255
    box = list(BANNER) if in_plate else [80, 44, 340, 92]
    x, y, w, h = box
    tex = {"banner": a[y:y + h, x:x + w].copy()}
    ws = [{"id": "Root", "type": "CanvasPanel"}]
    if in_plate:
        plate = a[44:136, 80:420].copy()
        plate[16:76, 20:320] = 0
        tex["static_plate1"] = plate
        ws.append({"id": "StaticPlate1", "type": "Image", "parent": "Root", "bbox_intent": [80, 44, 340, 92], "slot": {"kind": "canvas", "z": 0},
                   "style": {"brush": {"draw_as": "image", "asset": "static_plate1"}}})
    ws.append({"id": "Banner", "type": "Border", "parent": "Root", "bbox_intent": box, "slot": {"kind": "canvas", "z": 1}, "visibility": "collapsed",
               "binding": {"kind": "flag", "data": "b"}, "style": {"brush": {"draw_as": "image", "asset": "banner"}}})
    spec = {"canvas": [W, H], "root": "Root", "widgets": ws, "assets": []}
    boxes = [{"id": w_["id"], **dict(zip("xywh", w_.get("bbox_intent") or [0, 0, W, H])), "visible": True} for w_ in ws]
    return spec, boxes, tex, a[..., 3] / 255.0


def test_hidden_halo_finds_the_glow_left_in_the_plate_and_nothing_after_the_move():
    states = [{"widget": "Banner", "subtree": ["Banner"], "drawn_in_concept": True}]
    spec, boxes, tex, ca = _halo_scene(in_plate=True)
    r = state_check.hidden_halo(spec, boxes, tex, [W, H], ca, states, dg.settings(None))
    assert r["findings"] and r["findings"][0]["check"] == "hidden_halo" and r["findings"][0]["widgets"] == ["Banner"] and r["toggles"] == ["Banner"]
    assert r["roots"][0]["plate_px"] == int((ca > 0).sum()) - BANNER[2] * BANNER[3] and max(r["roots"][0]["local_max"].values()) > 5
    spec, boxes, tex, ca = _halo_scene(in_plate=False)
    r = state_check.hidden_halo(spec, boxes, tex, [W, H], ca, states, dg.settings(None))
    assert r["findings"] == [] and r["roots"][0]["plate_px"] == 0
    spec["widgets"][1]["visibility"] = "visible"                                 # flag 만 — 시작 때 보여도 대상(체인 패널)
    assert state_check.hidden_halo(spec, boxes, tex, [W, H], ca, [], dg.settings(None))["roots"][0]["widget"] == "Banner"
    spec["widgets"][1]["visibility"] = "collapsed"                               # 컨셉이 안 그린 숨은 위젯은 건너뜀
    assert "skipped" in state_check.hidden_halo(spec, boxes, tex, [W, H], ca, [{"widget": "Banner", "drawn_in_concept": False}], dg.settings(None))["roots"][0]


# ---------------------------------------------------------------------------------------------------------------------
# 반투명 면 위 참고판 글자

def test_merge_takes_glyphs_that_sit_on_a_translucent_surface():
    """끝이 사라지는 반투명 띠(알파 0.4 ~ 0.85) 위 글자도 획으로 가져온다 — 띠 자체를 다시 그린 차(상자 가장자리까지 이어짐)는 안 가져온다."""
    h, w = 120, 240
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    rng = np.random.default_rng(3)                                                # 정합이 잡을 단단한 무늬(띠 위아래 — 글자와 떨어짐)
    for y0, y1 in ((4, 32), (98, 116)):
        col[y0:y1, 8:232], a[y0:y1, 8:232] = rng.integers(60, 250, (y1 - y0, 224, 3)), 1.0
    col[40:90, 20:220] = (14, 14, 16)
    a[40:90, 20:220] = np.clip(np.minimum(np.arange(200), np.arange(200)[::-1]) / 40.0, 0.2, 0.85)[None, :]
    t_col, t_a = col.copy(), np.where(a > 0, 1.0, 0.0)                          # codex 가 띠를 더 불투명하게 다시 그림
    glyph = np.zeros((h, w), bool)
    glyph[55:75, 60:64] = glyph[55:75, 80:84] = glyph[63:67, 60:84] = True
    t_col[glyph] = (240, 235, 220)

    def detect(im, **kw):
        arr = np.asarray(im.convert("RGB"))
        return {"boxes": [{"box": [58, 53, 28, 24], "score": 0.9}] if (arr[50:80, 55:90].max(axis=2) > 220).any() else []}
    c_col, c_a, _, rec = text_ref.merge(col, a, t_col, t_a, detect=detect)
    assert rec["used"] and rec["glyph_on_translucent_px"] >= int(glyph.sum()) * 0.9
    assert np.abs(c_col[glyph] - np.array([240, 235, 220])).max() < 1 and not rec["paste"][:, 130:].any()
    assert (c_a[45:85, 140:200] == a[45:85, 140:200]).all()                      # 글자 밖 띠는 원본 아트 그대로


@pytest.mark.parametrize("states, oks, keys, resizes", [
    # 크기 → 굵기가 차례로 드러나도 나아지는 동안 이어 간다(R20261123_170301 '2/4' 크기 · '오의 불가' 굵기)
    ([{"Count": ["size"], "Blocked": ["weight"]}, {"Count": ["weight"]}, {}], [True, True], ["text_fit_size_final", "text_fit_size_final_2"], [{"Count"}, set()]),
    # 굵기만 결함 — 크기는 안 바꾼다(R20261123_161929 '오의 불가' 27 ↔ 29)
    ([{"Blocked": ["weight"]}, {}], [True], ["text_fit_size_final"], [set()]),
    # 못 받은 판에서 멈춘다 · 고칠 수 없는 원인은 판을 열지 않는다
    ([{"Blocked": ["weight"]}, {"Blocked": ["weight"]}], [False], ["text_fit_size_final"], [set()]),
    ([{"Blocked": ["unmeasured"]}], [], [], []),
])
def test_final_text_fit_repeats_only_for_the_flagged_texts(monkeypatch, states, oks, keys, resizes):
    import run_pipeline
    calls = []

    def fake_pass(run, opts, ctx, rec, rep, attempt, mode, key, only=None, resize=None, partial=False):
        if not key.startswith("text_fit_size_final"):
            return rep, attempt, False
        calls.append((key, set(only), set(resize)))
        run.n += 1
        return rep, attempt + 1, oks[len(calls) - 1]
    monkeypatch.setattr(run_pipeline, "_text_fit_pass", fake_pass)

    class FakeRun:
        n = 0
        cfg: dict = {}

        def read_json(self, name):
            assert name == "diagnosis.json"
            return {"defects": [{"stage": "text", "fixable": True, "widgets": [w], "causes": c} for w, c in states[self.n].items()]}
    monkeypatch.setattr(run_pipeline.style, "text_fit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("residual only")))
    rec = {"text_fit": {}}
    run_pipeline._text_fit_round(FakeRun(), None, {}, rec, {}, 1)
    assert [c[0] for c in calls] == keys and [c[2] for c in calls] == resizes
    assert [c[1] for c in calls] == [set(states[i]) for i in range(len(calls))]


def test_ocr_module_is_not_needed_for_the_score():
    assert concept_route.text_score(Image.new("RGB", (10, 10)), detect=lambda im, **k: {"boxes": []})["score"] == 0.0 and ocr.DEFAULT_MIN_SCORE == 0.7
