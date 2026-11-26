"""메인 HUD(11-24 — 설계 §11 '메인 HUD 설계') — 모양 막대: 재기 · 나누기(gen/silhouette), 요청 계약(inputs · analyze · fix 가드), 레이어 · 오리기 마스크(픽셀마다 주인 하나),
상태 검사 bar_*(일부러 틀린 렌더를 잡는가), 글꼴로 그린 글자 참고판(글꼴 값의 단일 원천), StatusHUD 입력 · codegen 계약."""
from __future__ import annotations

import copy
import json
import types

import numpy as np
import pytest
from PIL import Image, ImageDraw

import make_concept
from core import config, cppgen, schema
from core import spec as spec_mod
from core.run import Run
from gen import backdrop, silhouette, state_check, text_ref
from gen import diagnose as dg
from stages import StageError, analyze, fix, layer, normalize, refine, style

W, H = 420, 200
TRACK = "#404144CC"


def bars_art(joined: bool = True):
    """칼끝 막대(위) + 얇은 막대(아래) + 왼쪽 초승달 + 옅은 빛. joined 면 두 막대 사이가 알파 0.4 로 이어진다."""
    a = np.zeros((H, W))
    col = np.zeros((H, W, 3))
    xx = np.arange(W)
    tip = np.clip((360 - xx) / 60.0, 0, 1)                         # 오른쪽 60 px 은 칼끝
    for y in range(60, 78):
        on = (xx >= 100) & (xx < 360) & ((y - 60) < 18 * tip + 0.01)
        a[y, on] = 0.98
        col[y, on] = (210, 206, 198)
    a[81:91, 100:300] = 0.96
    col[81:91, 100:300] = (20, 20, 22)
    col[83:89, 103:297] = (228, 222, 200)
    if joined:
        a[78:81, 110:290] = 0.4
        col[78:81, 110:290] = (60, 60, 62)
    yy, xg = np.mgrid[0:H, 0:W]
    rr = np.hypot(yy - 75.5, xg - 60.5)
    ring = (np.abs(rr - 25) < 2) & (xg < 72)
    a[ring] = 0.9
    col[ring] = (200, 196, 188)
    halo = (a == 0) & (np.abs(yy - 69) < 11) & (xg >= 96) & (xg < 364)      # 막대 둘레 옅은 빛
    a[halo & (yy < 60)] = 0.05
    return a, col


BOXES = {"Hp": [100, 60, 260, 18], "Thin": [99, 80, 202, 12]}


def test_measure_splits_joined_bars_and_gives_each_pixel_one_owner():
    a, _ = bars_art()
    m = silhouette.measure(a, BOXES)
    hp, th = m["Hp"], m["Thin"]
    assert not (hp["mask"] & th["mask"]).any()
    assert hp["record"]["split_rows"] and 77 <= hp["record"]["split_rows"][0] <= 81
    assert hp["mask"][60:77, 101:298].all() and th["mask"][82:90, 101:299].all()
    core = a > silhouette.ON_ALPHA
    ring = np.zeros((H, W), bool)
    ring[:, :90] = True
    assert (core & ~ring & ~(hp["mask"] | th["mask"])).sum() == 0              # 막대 픽셀은 빠짐없이 어느 막대의 것
    assert not (hp["mask"] | th["mask"])[:, :90].any()                          # 초승달은 안 가져간다
    x, y, w, h = hp["box"]
    assert abs(x - 100) <= silhouette.GROW and abs(x + w - 360) <= silhouette.GROW + 1 and y <= 60
    # 떨어진 막대는 나누지 않는다
    m2 = silhouette.measure(bars_art(joined=False)[0], BOXES)
    assert "split_rows" not in m2["Hp"]["record"]
    # 잰 상자로 다시 재도 같은 나눔(analyze → layer)
    m3 = silhouette.measure(a, {k: v["box"] for k, v in m.items()})
    assert all((m3[k]["mask"] == m[k]["mask"]).all() for k in m)


def test_measure_refuses_what_is_not_the_bar():
    a, _ = bars_art()
    for boxes, word in (({"Hp": [100, 120, 260, 18]}, "no drawn pixels"), ({"Hp": [100, 60, 130, 18]}, "far outside"), ({"Hp": [36, 50, 40, 50]}, "not a horizontal bar"),
                        ({"Hp": [100, 60, 260, 60]}, "of the box"), ({"Hp": [500, 60, 10, 10]}, "outside")):
        with pytest.raises(silhouette.BarError) as e:
            silhouette.measure(a, boxes)
        assert word in str(e.value), (boxes, str(e.value))
    b = a.copy()
    b[60:78, 30:100] = 0.9                                                       # 초승달과 이어짐
    with pytest.raises(silhouette.BarError):
        silhouette.measure(b, {"Hp": [140, 60, 220, 18]})


# ---------------------------------------------------------------------------------------------------------------------
# 계약

def bar_spec():
    return {"schema_version": 1, "canvas": [W, H], "profile": "hud", "root": "Root", "allow_overlap": [], "locked": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Row", "type": "Overlay", "parent": "Root", "bbox_intent": [30, 40, 340, 70], "binding": {"data": "row", "kind": "flag"},
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [30, 40], "size": [340, 70], "z": 1}},
        {"id": "Frame", "type": "Image", "parent": "Row", "bbox_intent": [34, 50, 50, 54], "slot": {"kind": "overlay", "padding": [4, 10, 286, 6], "h_align": "fill", "v_align": "fill"},
         "style": {"brush": {"draw_as": "image", "asset": "frame"}}},
        {"id": "Hp", "type": "ProgressBar", "parent": "Row", "bbox_intent": [100, 60, 260, 18], "binding": {"data": "hp", "kind": "progress"},
         "slot": {"kind": "overlay", "padding": [70, 20, 10, 32], "h_align": "fill", "v_align": "fill"}, "style": {"percent": 1}},
        {"id": "Thin", "type": "ProgressBar", "parent": "Row", "bbox_intent": [99, 80, 202, 12], "binding": {"data": "thin", "kind": "progress"},
         "slot": {"kind": "overlay", "padding": [69, 40, 69, 18], "h_align": "fill", "v_align": "fill"},
         "style": {"percent": 1, "fill": {"draw_as": "image", "asset": "llm_fill"}}}],
        "assets": [{"asset_id": "frame", "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [50, 54], "prompt": "crescent", "ref_bbox": [34, 50, 50, 54]},
                   {"asset_id": "llm_fill", "kind": "fill", "provenance": "procedural", "size": [64, 12], "procedural": {"shape": "gradient_bar", "stops": ["#FFFFFFFF", "#FFFFFFFF"]}}]}


BRIEF = {"resolution": [W, H], "screen_type": "hud", "required_elements": [], "static_text": [], "dynamic_data": [
    {"id": "row", "type": "flag", "widget": "Row", "widget_type": "Overlay", "sample": True},
    {"id": "hp", "type": "progress", "widget": "Hp", "widget_type": "ProgressBar", "sample": 1, "inside": "Row", "bar": {"track": TRACK}},
    {"id": "thin", "type": "progress", "widget": "Thin", "widget_type": "ProgressBar", "sample": 1, "inside": "Row", "bar": {}}]}


def test_inputs_rules_for_bar():
    base = {"required_elements": [{"id": "Hp", "kind": "progress"}], "data": [{"id": "hp", "type": "progress", "widget": "Hp", "widget_type": "ProgressBar", "sample": 1, "bar": {}}]}
    assert normalize._inputs_errors(base) == []
    for edit in (lambda d: d.update(sample=0.5), lambda d: d.pop("sample"), lambda d: d.update(type="flag", widget_type="Image")):
        bad = copy.deepcopy(base)
        edit(bad["data"][0])
        assert any("DATA_BAR" in e for e in normalize._inputs_errors(bad)), bad


def test_analyze_contract_checks_and_derives_the_bars():
    a, _ = bars_art()
    assert any("a shaped bar" in ln and "must be inside Row" in ln for ln in analyze._contract_lines(BRIEF))
    s = analyze.apply_contract(bar_spec(), BRIEF)
    assert [e for e in analyze.check(s, BRIEF) if e.startswith("BAR")] == []
    bad = copy.deepcopy(s)
    spec_mod.widget_index(bad)["Hp"].update(parent="Root", slot={"kind": "canvas", "position": [100, 60], "size": [260, 18]})
    spec_mod.widget_index(bad)["Frame"]["bbox_intent"] = [98, 58, 264, 36]        # 막대 둘을 다시 그리는 그림
    errs = analyze.check(bad, BRIEF)
    assert any(e.startswith("BAR_PARENT: 'Hp'") for e in errs) and any(e.startswith("BAR_FRAME: 'Frame'") for e in errs)
    rec = analyze.derive_bars(s, BRIEF, a)
    idx = spec_mod.widget_index(s)
    assert [r["widget"] for r in rec] == ["Hp", "Thin"] and rec[0]["dropped_assets"] == ["llm_fill"]
    for wid, aid, track in (("Hp", "hp", TRACK), ("Thin", "thin", silhouette.DEFAULT_TRACK)):
        w = idx[wid]
        assert w["style"]["fill"] == {"draw_as": "image", "asset": aid} and w["style"]["background"] == {"draw_as": "image", "asset": aid, "color": track}
        x, y, bw, bh = w["bbox_intent"]
        assert w["slot"]["padding"] == [x - 30, y - 40, 370 - x - bw, 110 - y - bh] and next(a_ for a_ in s["assets"] if a_["asset_id"] == aid)["size"] == [bw, bh]
    assert silhouette.bars(s) == {"Hp": "hp", "Thin": "thin"}
    assert schema.errors("spec", s) == [] and spec_mod.validate_semantics(s) == []
    assert analyze.derive_gauge_fills(s, _png(a), None, skip={"Hp", "Thin"}) == []
    for bad_alpha in (None, np.zeros((H, W))):
        with pytest.raises(StageError) as e:
            analyze.derive_bars(analyze.apply_contract(bar_spec(), BRIEF), BRIEF, bad_alpha)
        assert e.value.code == "BAR_MEASURE"


_TMP: list = []


def _png(a):
    import tempfile
    d = tempfile.TemporaryDirectory()
    _TMP.append(d)
    p = d.name + "/ref.png"
    Image.fromarray(np.dstack([(a * 255).astype(np.uint8)] * 3), "RGB").save(p)
    return p


def test_fix_and_style_rounds_cannot_touch_the_bars():
    a, _ = bars_art()
    s = analyze.apply_contract(bar_spec(), BRIEF)
    analyze.derive_bars(s, BRIEF, a)
    ops = [{"op": "set", "widget": "Hp", "path": "style.background", "value": {"draw_as": "none"}}, {"op": "set", "widget": "Thin", "path": "slot.padding", "value": [0, 0, 0, 0]},
           {"op": "replace_asset", "asset": "hp", "regenerate": True}, {"op": "set", "widget": "Frame", "path": "slot.padding", "value": [0, 0, 0, 0]}]
    errs = fix.guard_ops(ops, s, BRIEF)
    assert len(errs) == 3 and [e.split(":")[0] for e in errs] == ["op 0", "op 1", "op 2"]


# ---------------------------------------------------------------------------------------------------------------------
# 레이어 · 오리기

def _run_dir(tmp_path, a, col, spec, rid="R20261124_220001_Bar"):
    run = Run(rid, tmp_path / "work", config.load_pipeline(), tmp_path / "m.jsonl")
    run.create()
    Image.fromarray(np.clip(np.round(col), 0, 255).astype(np.uint8), "RGB").save(run.path("reference_color.png"))
    Image.fromarray(np.clip(np.round(a * 255), 0, 255).astype(np.uint8), "L").save(run.path("reference_alpha.png"))
    Image.fromarray(np.clip(np.round(col * a[..., None]), 0, 255).astype(np.uint8), "RGB").save(run.path("reference.png"))
    run.write_json("normalize.json", {"background": {"kind": "transparent"}})
    run.write_json("brief.json", {**BRIEF, "screen_id": "Bar"})
    run.write_json("spec.json", spec)
    return run


def test_layer_and_refine_split_the_row_into_frame_and_bars(tmp_path):
    a, col = bars_art()
    s = analyze.apply_contract(bar_spec(), BRIEF)
    analyze.derive_bars(s, BRIEF, a)
    run = _run_dir(tmp_path, a, col, s)
    layer.run(run, types.SimpleNamespace())
    lay = run.read_json("layer.json")
    assert {b["widget"] for b in lay["bars"]} == {"Hp", "Thin"} and all(run.path(b["mask"]).is_file() for b in lay["bars"])
    spec = run.read_json("spec.json")
    assert [t["widget"] for t in lay.get("filled", [])] == ["Frame"]                 # 막대는 영역의 빛을 가질 그림이 아니다 — 초승달 그림이 줄 전체로 넓어진다
    masks = {aid: refine.own_mask(run, spec, aid) for aid in ("hp", "thin", "frame")}
    assert not (masks["hp"] & masks["thin"]).any()
    assert not (masks["frame"] & (masks["hp"] | masks["thin"])).any()
    x, y, w, h = (int(v) for v in spec_mod.widget_index(spec)["Row"]["bbox_intent"])
    vis = np.zeros((H, W), bool)
    vis[y:y + h, x:x + w] = (a > 0.02)[y:y + h, x:x + w]
    assert (vis & ~(masks["hp"] | masks["thin"] | masks["frame"])).sum() == 0         # 빠진 픽셀도 없다
    texts, excl, skip, gauges = refine.concept_pixel_inputs(spec, next(x_ for x_ in spec["assets"] if x_["asset_id"] == "frame"), [30, 40, 340, 70], gauge_holes=True)
    assert excl == [] and gauges == [] and skip is None                               # 막대는 줄 그림에서 메울 구멍이 아니다
    run2 = _run_dir(tmp_path, a, col, spec, "R20261124_220002_Bar")
    run2.write_json("layer.json", {})
    with pytest.raises(StageError) as e:
        refine.own_mask(run2, spec, "hp")
    assert e.value.code == "BAR_MASK"


def test_plate_leaves_the_bars_out_when_the_row_never_collapses(tmp_path):
    a, col = bars_art()
    s = bar_spec()
    spec_mod.widget_index(s)["Row"].pop("binding")
    brief = {**BRIEF, "dynamic_data": BRIEF["dynamic_data"][1:]}
    s = analyze.apply_contract(s, brief)
    analyze.derive_bars(s, brief, a)
    run = _run_dir(tmp_path, a, col, s, "R20261124_220003_Bar")
    layer.run(run, types.SimpleNamespace())
    lay = run.read_json("layer.json")
    assert lay["applied"] and lay["static"] == ["Frame"]
    plate = np.zeros((H, W), bool)
    for m in lay["masks"]:
        plate |= np.asarray(Image.open(run.path(m)).convert("L")) > 127
    bar = np.zeros((H, W), bool)
    for b in lay["bars"]:
        bar |= np.asarray(Image.open(run.path(b["mask"])).convert("L")) > 127
    assert plate.any() and not (plate & bar).any()


# ---------------------------------------------------------------------------------------------------------------------
# 상태 검사

def _scene():
    a, col = bars_art()
    s = analyze.apply_contract(bar_spec(), BRIEF)
    analyze.derive_bars(s, BRIEF, a)
    idx = spec_mod.widget_index(s)
    ms = silhouette.measure(a, {k: idx[k]["bbox_intent"] for k in ("Hp", "Thin")})
    rest = ~(ms["Hp"]["mask"] | ms["Thin"]["mask"])
    tex = {}
    for wid, aid, mm in (("Hp", "hp", ms["Hp"]["mask"]), ("Thin", "thin", ms["Thin"]["mask"]), ("Frame", "frame", rest)):
        x, y, w, h = (int(v) for v in idx[wid]["bbox_intent"])
        t = np.zeros((h, w, 4))
        t[..., :3] = col[y:y + h, x:x + w]
        t[..., 3] = np.where(mm, a, 0)[y:y + h, x:x + w] * 255
        tex[aid] = t
    boxes = [{"id": w["id"], "x": b[0], "y": b[1], "w": b[2], "h": b[3], "visible": True} for w in s["widgets"] for b in [w.get("bbox_intent") or [0, 0, W, H]]]
    return s, tex, boxes


@pytest.mark.parametrize("fault,check", [(None, None), ("reverse", "bar_cut"), ("untinted", "bar_track"), ("wide", "bar_cut"), ("neighbour", "bar_outside"), ("still", "bar_track"),
                                         ("color", "bar_full"), ("nofill_zero", "gauge_zero_fill")])
def test_gauge_states_catch_wrong_bars(fault, check):
    s, tex, boxes = _scene()
    st = {**dg.DEFAULTS}
    base = backdrop.compose(s, boxes, tex, [W, H], (0, 0, 0))[0]

    def render(wid, p):
        sp = state_check._with_percent(s, wid, 1.0 if fault == "still" else 0.05 if fault == "nofill_zero" and p == 0 else p)
        w = spec_mod.widget_index(sp)[wid]
        if fault == "reverse":
            w["style"]["bar_fill_type"] = "right_to_left"
        if fault == "untinted":
            w["style"]["background"].pop("color")
        if fault == "wide" and 0.05 < p < 1:
            w["style"]["percent"] = min(1.0, p + 0.1)
        if fault == "nofill_zero" and p == 0:
            w["style"]["percent"] = 0.3
        img = backdrop.compose(sp, boxes, tex, [W, H], (0, 0, 0))[0]
        if fault == "neighbour" and wid == "Hp" and p < 1:
            img = img.copy()
            img[84:88, 120:280] *= 0.3                                             # 이웃 막대를 건드림
        if fault == "color" and p >= 1:
            img = img * 0.6
        return img
    r = state_check.gauge_states(s, boxes, tex, [W, H], st, base, render_pct=render)
    found = {f["check"] for f in r["findings"]}
    assert (found == set()) if fault is None else (check in found), (fault, found)
    if fault is None:
        assert set(r["images"]["Hp"]) == set(state_check.BAR_STATES) and all(g["track_contrast"] > st["local_de"] for g in r["gauges"])
        off = state_check.gauge_states(s, boxes, tex, [W, H], st, base)
        assert off["findings"] == [] and off["gauges"][0]["renderer"][0.0] == "composite"


# ---------------------------------------------------------------------------------------------------------------------
# 글꼴로 그린 글자 참고판

def test_draw_items_uses_the_given_places_and_the_boxes_replace_ocr():
    if not (make_concept.FONT_DIR / "Pretendard-Medium.ttf").is_file():
        pytest.skip("the Pretendard TTF is not in work/_fonts")
    art = Image.new("RGBA", (960, 540), (0, 0, 0, 0))
    art.paste((200, 190, 170, 255), (60, 400, 700, 430))
    art.paste((90, 90, 96, 200), (500, 40, 900, 90))
    items = [{"widget": "A", "value": "표식"}, {"widget": "B", "value": "3"}]
    layout = [{"widget": "A", "pos": [200, 300], "anchor": "ms", "pt": 26, "weight": "medium", "color": "#ECE5D6"}, {"widget": "B", "pos": [600, 300], "pt": 45, "weight": "semibold"}]
    pic, drawn = text_ref.draw_items(art, layout, items, make_concept.FONT_DIR)
    assert [d["widget"] for d in drawn] == ["A", "B"] and drawn[0]["value"] == "표식"
    x, y, w, h = drawn[0]["box"]
    assert abs(x + w / 2 - 100) < 2 and y + h <= 154 and 6 < h < 20                  # 1920 기준 자리를 그림 크기로
    arr = np.asarray(pic, float)
    base = np.asarray(art, float)
    a_col, a_a = base[..., :3], base[..., 3] / 255.0
    boom = lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("OCR must not run"))   # noqa: E731
    c_col, c_a, _, rec = text_ref.merge(a_col, a_a, arr[..., :3], arr[..., 3] / 255.0, detect=boom, boxes=[d["box"] for d in drawn])
    assert rec["used"] and rec["ocr"]["from"] == "drawn" and (c_a[y:y + h, x:x + w] > 0.5).any()
    assert drawn[0]["font"] == {"size": 26, "weight": "medium", "color": "#ECE5D6FF"} and drawn[1]["font"]["size"] == 45
    for bad in (layout[:1], layout + [layout[0]], [{**layout[0], "weight": "thin"}, layout[1]], [{**layout[0], "pt": 25.5}, layout[1]], [{**layout[0], "color": "ivory"}, layout[1]]):
        with pytest.raises(ValueError):
            text_ref.draw_items(art, bad, items, make_concept.FONT_DIR)


# ---------------------------------------------------------------------------------------------------------------------
# 글꼴 값의 단일 원천 — 글꼴로 그린 참고판의 크기 · 굵기 · 색을 그대로 쓰고 다시 재지 않는다

PRET = "/Game/UI/Fonts/Pretendard/F_Pretendard_W.F_Pretendard_W"
FONT = {"size": 15, "weight": "medium", "color": "#ECE5D6FF"}


def _text_spec(font=None):
    return {"root": "Root", "profile": "hud", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Name", "type": "TextBlock", "parent": "Root", "bbox_intent": [100, 60, 120, 36], "justification": "left",
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [100, 60], "auto_size": True}, "text": {"source": "static", "value": "Player"},
         "font": font or {"size": 22, "weight": "regular", "color": "#CFC9BCFF", "family": PRET, "letter_spacing": 40, "gradient": {"top_color": "#FFFFFFFF", "bottom_color": "#000000FF"}}}]}


def _text_brief():
    return {"dynamic_data": [], "static_text": [{"widget": "Name", "value": "Player", "font": FONT}], "required_elements": []}


def test_declared_fonts_replace_the_measured_values_and_nothing_may_change_them():
    s = _text_spec()
    rec = analyze.apply_declared_fonts(s, _text_brief(), config.load_pipeline())
    n = spec_mod.widget_index(s)["Name"]
    assert n["font"] == {"size": 15, "weight": "medium", "color": "#ECE5D6FF", "family": PRET}                 # 자간 · 그라데이션은 그릴 때 없었다
    assert rec[0]["old"]["size"] == 22 and abs((n["bbox_intent"][1] + n["bbox_intent"][3] / 2) - 78) < 0.2     # 글자 상자는 가운데 기준으로 작아진다
    assert analyze.declared_fonts(_text_brief()) == {"Name": FONT} and analyze.apply_declared_fonts(_text_spec(), {"dynamic_data": []}, config.load_pipeline()) == []
    ops = [{"op": "set", "widget": "Name", "path": p, "value": 1} for p in ("font.size", "font.weight", "font.color", "font", "slot.padding")]
    errs = fix.guard_ops(ops, s, _text_brief())
    assert [e.split(":")[0] for e in errs] == ["op 0", "op 1", "op 2", "op 3"]                                 # 자리는 고칠 수 있다


def test_declared_font_weight_is_compared_by_value_not_by_small_strokes():
    H, W = 60, 200
    ref, ren = np.zeros((H, W, 3)), np.zeros((H, W, 3))
    mc, mr = np.zeros((H, W), bool), np.zeros((H, W), bool)
    for i in range(6):                                                                                        # 같은 자리 · 높이 — 렌더 획이 두 배 굵다
        mc[20:34, 40 + 14 * i:42 + 14 * i] = True
        mr[20:34, 40 + 14 * i:44 + 14 * i] = True
    mc[20:22, 40:114] = mr[20:22, 40:114] = True
    ref[mc] = ren[mr] = (236, 229, 214)
    masks = {"concept": mc, "concept_cand": mc, "render": mr, "render_cand": mr}
    st = dg.settings(None)
    table = {"regular": 1.0, "medium": 1.12, "semibold": 1.25, "bold": 1.36, "extrabold": 1.48}
    w = {"id": "Name", "font": {**FONT, "family": PRET}}
    bg = np.zeros((H, W, 3))
    plain = dg.compare_text(w, masks, ref, ren, bg, st, weights=table)
    assert plain["causes"] == ["weight"] and plain["fixable"]                                                  # 값을 모르면 획 밀도로 굵기를 바꾸려 한다
    decl = dg.compare_text(w, masks, ref, ren, bg, st, weights=table, declared=FONT)
    assert decl["causes"] == [] and decl["approx"][0]["declared"] is True
    for k, bad in (("weight", "regular"), ("size", 14), ("color", "#CFC9BCFF")):                              # 값이 다르면 오류(맞춤 판이 못 고침)
        r = dg.compare_text({"id": "Name", "font": {**w["font"], k: bad}}, masks, ref, ren, bg, st, weights=table, declared=FONT)
        assert r["causes"] == [k] and r["fixable"] is False
    tall = mr.copy()
    for i in range(6):
        tall[20:38, 40 + 14 * i:44 + 14 * i] = True
    big = np.zeros((H, W, 3))
    big[tall] = (236, 229, 214)
    r = dg.compare_text(w, {**masks, "render": tall, "render_cand": tall}, ref, big, bg, st, weights=table, declared=FONT)
    assert "size" in r["causes"] and r["fixable"] is False                                                     # 실제로 그려진 높이가 다르면 여전히 오류


def test_text_fit_leaves_a_declared_font_alone_but_still_moves_it(tmp_path):
    ref, ren = Image.new("RGB", (400, 200), (20, 15, 10)), Image.new("RGB", (400, 200), (20, 15, 10))
    for i in range(6):
        ImageDraw.Draw(ref).rectangle([112 + 16 * i, 70, 116 + 16 * i, 89], fill=(236, 229, 214))
        ImageDraw.Draw(ren).rectangle([105 + 14 * i, 66, 111 + 14 * i, 83], fill=(160, 150, 140))
    ref.save(tmp_path / "reference.png")
    ren.save(tmp_path / "render.png")
    s = _text_spec({**FONT, "family": PRET})
    cfg = config.load_pipeline()
    free, _ = style.text_fit(s, tmp_path / "reference.png", tmp_path / "render.png", cfg, mode="size")
    assert spec_mod.widget_index(free)["Name"]["font"] != spec_mod.widget_index(s)["Name"]["font"]             # 고정하지 않으면 바꾼다
    fit, rec = style.text_fit(s, tmp_path / "reference.png", tmp_path / "render.png", cfg, mode="size", font_locked={"Name"})
    assert fit == s and "declared" in rec[0]["skipped"] and style.text_fit_changed(rec) == []
    moved, rec = style.text_fit(s, tmp_path / "reference.png", tmp_path / "render.png", cfg, mode="place", font_locked={"Name"})
    m = spec_mod.widget_index(moved)["Name"]
    assert rec[0].get("shift") and "letter_spacing" not in rec[0] and m["font"] == spec_mod.widget_index(s)["Name"]["font"] and m["slot"]["position"] != [100, 60]


def test_drawn_fonts_come_from_the_record_next_to_the_picture(tmp_path):
    p = tmp_path / "concept_text_ref.png"
    assert text_ref.drawn_fonts(p) == {}
    p.with_suffix(".json").write_text(json.dumps({"drawn": [{"widget": "A", "box": [0, 0, 1, 1], "font": FONT}, {"widget": "B", "box": [0, 0, 1, 1]}]}), encoding="utf-8")
    assert text_ref.drawn_fonts(p) == {"A": FONT}                                                              # 글꼴 기록이 없는 옛 기록은 재는 길 그대로
    real = text_ref.drawn_fonts(config.UIGEN_DIR / "fixtures" / "status_hud_blade" / "concept_text_ref.png")
    layout = config.load_yaml(config.UIGEN_DIR / "fixtures" / "status_hud_blade" / "text_ref_layout.yaml")["texts"]
    assert real == {t["widget"]: {"size": t["pt"], "weight": t["weight"], "color": t["color"] + "FF"} for t in layout} and len(real) == 6
    assert len({json.dumps(real[f"Ally{i}NameText"]) for i in (1, 2, 3)}) == 1                                 # 동료 이름 세 줄은 같은 글꼴
    brief = {"schema_version": 1, "mode": "concept", "screen_type": "hud", "screen_id": "StatusHUD", "resolution": [1920, 1080], "required_elements": [],
             "dynamic_data": [{"id": "n", "type": "text", "widget": "Ally1NameText", "font": real["Ally1NameText"]}], "static_text": [{"widget": "SelfMarkLabel", "value": "표식", "font": real["SelfMarkLabel"]}]}
    assert schema.errors("brief", brief) == []


def test_make_concept_draw_needs_only_text_ref(capsys):
    assert make_concept.main(["--out-dir", "x", "--draw", "y.yaml"]) == make_concept.EXIT_FAIL
    assert "--draw needs --only text_ref" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------------------------------
# StatusHUD 입력 · 계약

def test_status_hud_inputs_and_contract():
    fx = config.UIGEN_DIR / "fixtures" / "status_hud_blade"
    inp = config.load_yaml(fx / "inputs.yaml")
    assert inp["screen_id"] == "StatusHUD" and schema.errors("inputs", inp) == [] and normalize._inputs_errors(inp) == []
    scr = config.load_screens()["StatusHUD"]
    assert scr["view_base"] == "AstralStatusHUDViewBase" and not scr.get("probe")
    ids = [d["id"] for d in inp["data"]]
    assert len(ids) == 16 and sum(1 for d in inp["data"] if d.get("bar")) == 8 and sum(1 for d in inp["data"] if d["type"] == "flag") == 3
    new = [{"name": d["widget"], "widget_class": d["widget_type"], "data": d["id"], "kind": d["type"], "optional": False, **({"format": d["format"]} if d.get("format") else {})} for d in inp["data"]]
    merged, _ = cppgen.merge(new, [])
    setters = {m["setter"] for m in merged}
    assert {"SetSelfHp", "SetSelfHpValue", "SetSelfStamina", "SetSelfMark", "SetAlly1PanelVisible", "SetAlly2Name", "SetAlly3Hp", "SetAlly1Ult"} <= setters
    ref = json.loads((fx / "concept_text_ref.json").read_text(encoding="utf-8"))
    assert {t["widget"] for t in ref["texts"]} == {t["widget"] for t in text_ref.text_items(inp)} and len(ref["drawn"]) == len(ref["texts"])
    side = json.loads((fx / "concept.json").read_text(encoding="utf-8"))
    assert side["lineage"][-1]["step"] == "pixels" and len(side["lineage"][-1]["boxes"]) == 4
    # 시안 픽셀 — 막대 여덟을 다 잴 수 있다
    with Image.open(fx / "concept.png") as im:
        al = np.asarray(im.convert("RGBA"), np.float32)[..., 3] / 255.0
    al = np.asarray(Image.fromarray(al, mode="F").resize((1920, 1080), Image.Resampling.LANCZOS)).clip(0, 1)
    boxes = {"SelfHpBar": [158, 98, 384, 18], "SelfStaminaBar": [157, 122, 300, 13], "Ally1HpBar": [115, 204, 254, 16], "Ally1UltBar": [115, 221, 205, 11],
             "Ally2HpBar": [115, 274, 254, 17], "Ally2UltBar": [115, 291, 205, 11], "Ally3HpBar": [115, 344, 254, 17], "Ally3UltBar": [115, 362, 205, 10]}
    ms = silhouette.measure(al, boxes)
    tot = sum(m["mask"].astype(int) for m in ms.values())
    assert len(ms) == 8 and tot.max() == 1
