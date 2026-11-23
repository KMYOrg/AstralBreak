"""전투 HUD 동작(11-23 — 설계 §11) — 원형 진행(고리): 재기 · 픽셀 나누기 · 닦기 식(gen/radial), progress 의 Image 계약(spec · codegen · analyze), 레이어 · 오리기 마스크,
상태 검사 radial_states(일부러 틀린 렌더를 잡는가) · 접히는 상자 속 그림 넓히기(layer.fill_toggles) · 요청이 정한 글자 외곽선."""
from __future__ import annotations

import copy
import json
import types

import numpy as np
import pytest
from PIL import Image

from core import config, cppgen, schema
from core import spec as spec_mod
from core.run import Run
from gen import backdrop, radial, state_check
from gen import diagnose as dg
from stages import StageError, analyze, fix, layer, normalize, refine, style

W, H = 400, 300
CX, CY, R = 200.0, 150.0, 120.0


def ring_alpha(band: bool = True, cx=CX, cy=CY):
    """초승달 둘(옆 12 px · 위아래 끝 0) + 고리 안 아래쪽 띠(안쪽 모서리까지 닿음)."""
    rr, a = radial.angles((H, W), (cx, cy))
    rin = R - 12.0 * np.abs(np.sin(a))
    ring = np.clip(R - rr + 0.5, 0, 1) * np.clip(rr - rin + 0.5, 0, 1)
    yy, xx = np.mgrid[0:H, 0:W]
    b = ((yy >= 195) & (yy < 235) & (rr < rin)).astype(float) * 0.8 if band else np.zeros((H, W))
    col = np.zeros((H, W, 3))
    col[ring > 0] = (220, 215, 200)
    col[(b > 0) & (ring <= b)] = (14, 14, 16)
    return np.maximum(ring, b), col, ring, b


# ---------------------------------------------------------------------------------------------------------------------
# 닦기 식 · 재기

def test_wipe_factor_ends_direction_and_track():
    c = (CX, CY)
    assert (radial.wipe_factor((H, W), c, 1.0, "clockwise", 0.18) == 1).all()
    assert np.allclose(radial.wipe_factor((H, W), c, 0.0, "clockwise", 0.18), 0.18)
    k = radial.wipe_factor((H, W), c, 0.75, "clockwise", 0.0)              # 12시 → 3시가 지워짐
    assert k[60, 260] == 0 and k[240, 260] == 1 and k[240, 140] == 1 and k[60, 140] == 1
    m = radial.wipe_factor((H, W), c, 0.5, "mirror", 0.25)                 # 위 반쪽이 좌우 같이
    assert m[60, 260] == 0.25 and m[60, 140] == 0.25 and m[240, 260] == 1 and m[240, 140] == 1
    soft = radial.wipe_factor((H, W), c, 0.4, "clockwise", 0.0)
    assert ((soft > 0) & (soft < 1)).sum() > 50                            # 끝이 계단이 아니다
    with pytest.raises(radial.RadialError):
        radial.wipe_factor((H, W), c, 0.5, "spiral")


def test_measure_finds_the_circle_and_leaves_the_band_out_of_the_ring():
    al, col, ring, band = ring_alpha()
    m = radial.measure(al, [75, 25, 250, 250])
    assert abs(m["center"][0] - CX) < 0.3 and abs(m["center"][1] - CY) < 0.3 and abs(m["radius"] - R) < 0.5
    assert m["record"]["touched_deg"] > 20                                  # 띠가 닿은 각도를 거울 자리로 고쳤다
    only_band, only_ring = band > 0.5, (ring > 0.5) & (band <= 0)
    assert (m["mask"] & only_band).sum() / only_band.sum() < 0.03           # 띠 조각을 고리가 거의 안 가져간다
    assert (m["mask"] & only_ring).sum() / only_ring.sum() > 0.99
    x, y, w, h = m["box"]
    assert x <= CX - R and y <= CY - R and x + w >= CX + R and y + h >= CY + R and max(w, h) <= 2 * R + 10


def test_measure_refuses_what_is_not_a_ring():
    sq = np.zeros((H, W))
    sq[40:260, 90:310] = 1
    with pytest.raises(radial.RadialError):
        radial.measure(sq, [90, 40, 220, 220])
    rr, _ = radial.angles((H, W), (CX, CY))
    with pytest.raises(radial.RadialError):                                 # 꽉 찬 원판 — 안쪽 모서리가 없다
        radial.measure((rr <= R).astype(float), [80, 30, 240, 240])
    with pytest.raises(radial.RadialError):
        radial.measure(np.zeros((H, W)), [80, 30, 240, 240])


# ---------------------------------------------------------------------------------------------------------------------
# 계약 — spec · codegen · 입력

def ring_spec(band_asset="band", ring_asset="ring"):
    return {"schema_version": 1, "canvas": [W, H], "profile": "hud", "root": "Root", "allow_overlap": [], "locked": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Panel", "type": "Border", "parent": "Root", "bbox_intent": [75, 25, 250, 250], "binding": {"data": "panel", "kind": "flag"},
         "slot": {"kind": "canvas", "anchors": [0.5, 0.5, 0.5, 0.5], "alignment": [0.5, 0.5], "position": [0, 0], "size": [250, 250], "z": 1},
         "style": {"brush": {"draw_as": "image", "asset": band_asset}}},
        {"id": "Layer", "type": "Overlay", "parent": "Panel", "bbox_intent": [75, 25, 250, 250], "slot": {"kind": "border", "padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill"}},
        {"id": "Ring", "type": "Image", "parent": "Layer", "bbox_intent": [78, 28, 244, 244], "binding": {"data": "left", "kind": "progress"},
         "slot": {"kind": "overlay", "padding": [3, 3, 3, 3], "h_align": "fill", "v_align": "fill"},
         "style": {"brush": {"draw_as": "image", "asset": ring_asset, "wipe": {"kind": "radial", "mode": "clockwise", "center": [122, 122], "track_alpha": 0.18}}, "percent": 1}},
        {"id": "Num", "type": "TextBlock", "parent": "Layer", "bbox_intent": [180, 200, 40, 30], "slot": {"kind": "overlay", "padding": [105, 175, 105, 45], "h_align": "fill", "v_align": "fill"},
         "text": {"source": "static", "value": "4"}, "font": {"size": 18, "weight": "bold", "color": "#FFFFFF"}}],
        "assets": [{"asset_id": band_asset, "kind": "frame", "provenance": "codex", "source_mode": "extract", "size": [250, 250], "prompt": "band", "ref_bbox": [75, 25, 250, 250]},
                   {"asset_id": ring_asset, "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [244, 244], "prompt": "ring", "ref_bbox": [78, 28, 244, 244]}]}


def test_spec_rules_for_the_wipe():
    s = ring_spec()
    assert schema.errors("spec", s) == [] and spec_mod.validate_semantics(s) == []
    n = spec_mod.widget_index(spec_mod.normalize({**copy.deepcopy(s)}))["Ring"]
    assert n["style"]["percent"] == 1 and n["style"]["brush"]["wipe"]["track_alpha"] == 0.18
    bare = copy.deepcopy(s)
    spec_mod.widget_index(bare)["Ring"]["style"] = {"brush": {"draw_as": "image", "asset": "ring", "wipe": {"center": [1, 2]}}}
    nb = spec_mod.widget_index(spec_mod.normalize(bare))["Ring"]["style"]
    assert nb["percent"] == 1 and nb["brush"]["wipe"] == {"kind": "radial", "mode": "clockwise", "track_alpha": 0, "center": [1, 2]}
    for edit, code in ((lambda w: w["style"]["brush"].pop("wipe"), "STYLE_PERCENT"), (lambda w: (w["style"]["brush"].pop("wipe"), w["style"].pop("percent")), "PROGRESS_IMAGE"),
                       (lambda w: w["style"]["brush"].update(draw_as="box"), "BRUSH_WIPE")):
        bad = copy.deepcopy(s)
        edit(spec_mod.widget_index(bad)["Ring"])
        assert any(e.startswith(code) for e in spec_mod.validate_semantics(bad)), code
    onborder = copy.deepcopy(s)
    spec_mod.widget_index(onborder)["Panel"]["style"]["brush"]["wipe"] = {"center": [1, 1]}
    assert any(e.startswith("BRUSH_WIPE") for e in spec_mod.validate_semantics(onborder))


def test_codegen_moves_the_material_percent_and_the_flag_moves_to_its_new_box():
    prev = [{"name": "Glow", "widget_class": "Image", "data": "ready", "kind": "flag", "optional": False, "setter": "SetReadyVisible"}]
    new = [{"name": "Ring", "widget_class": "Image", "data": "left", "kind": "progress", "optional": False},
           {"name": "ReadyPanel", "widget_class": "Overlay", "data": "ready", "kind": "flag", "optional": False},
           {"name": "Gauge", "widget_class": "ProgressBar", "data": "gauge", "kind": "progress", "optional": False}]
    merged, ch = cppgen.merge(new, prev)
    by = {m["name"]: m for m in merged}
    assert by["ReadyPanel"]["setter"] == "SetReadyVisible" and by["Glow"]["optional"] and by["Glow"]["setter"] is None     # 부르는 곳(SetReadyVisible)은 그대로
    assert ch["demoted"] == ["Glow"] and by["Ring"]["setter"] == "SetLeft"
    doc = cppgen.contract_doc("X", {"feature": "HUD", "view_base": "XViewBase", "widget": "XWidget"}, {"module": "M", "api_macro": "M_API", "ui_dir": "UI"}, merged)
    cpp = cppgen.render(doc, cppgen.contract_hash(doc))["view_base_cpp"]
    assert 'Ring->GetDynamicMaterial()' in cpp and 'SetScalarParameterValue(FName(TEXT("Percent")), FMath::Clamp(Percent, 0.0f, 1.0f))' in cpp
    assert '#include "Materials/MaterialInstanceDynamic.h"' in cpp and "Gauge->SetPercent(" in cpp and "ReadyPanel->SetVisibility(" in cpp


def test_inputs_rules_for_radial_inside_and_outline():
    base = {"required_elements": [{"id": "Ring", "kind": "progress"}], "data": [{"id": "left", "type": "progress", "widget": "Ring", "widget_type": "Image", "radial": {"mode": "clockwise"}}]}
    assert normalize._inputs_errors(base) == []
    no = copy.deepcopy(base)
    no["data"][0].pop("radial")
    assert any("DATA_RADIAL" in e for e in normalize._inputs_errors(no))
    bar = copy.deepcopy(base)
    bar["data"][0]["widget_type"] = "ProgressBar"
    assert any("DATA_RADIAL" in e for e in normalize._inputs_errors(bar))
    ol = copy.deepcopy(base)
    ol["data"][0]["outline"] = {"size": 2, "color": "#000000"}
    assert any("DATA_OUTLINE" in e for e in normalize._inputs_errors(ol))
    self_in = copy.deepcopy(base)
    self_in["data"][0]["inside"] = "Ring"
    assert any("DATA_INSIDE" in e for e in normalize._inputs_errors(self_in))


BRIEF = {"resolution": [W, H], "screen_type": "hud", "required_elements": [], "static_text": [], "dynamic_data": [
    {"id": "panel", "type": "flag", "widget": "Panel", "widget_type": "Border", "sample": True},
    {"id": "left", "type": "progress", "widget": "Ring", "widget_type": "Image", "sample": 1.0, "inside": "Panel", "radial": {"mode": "mirror", "track_alpha": 0.2}}]}


def test_analyze_writes_the_wipe_from_the_request_and_checks_the_structure():
    raw = ring_spec()
    idx = spec_mod.widget_index(raw)
    idx["Ring"]["style"] = {"brush": {"draw_as": "image", "asset": "ring", "wipe": {"center": [1, 1], "track_alpha": 0.9}}, "percent": 0.3}     # LLM 이 적은 것은 걷는다
    idx["Panel"]["style"]["brush"]["wipe"] = {"center": [3, 3]}
    out = analyze.apply_contract(raw, BRIEF)
    o = spec_mod.widget_index(out)
    assert o["Ring"]["style"]["brush"]["wipe"] == {"kind": "radial", "mode": "mirror", "track_alpha": 0.2, "center": [122.0, 122.0]} and o["Ring"]["style"]["percent"] == 1.0
    assert "wipe" not in o["Panel"]["style"]["brush"]
    errs = [e for e in analyze.check(out, BRIEF) if e.startswith(("NOT_INSIDE", "RADIAL"))]
    assert errs == []
    away = copy.deepcopy(out)
    spec_mod.widget_index(away)["Ring"].update(parent="Root", slot={"kind": "canvas", "position": [78, 28], "size": [244, 244]})
    e2 = analyze.check(away, BRIEF)
    assert any(e.startswith("NOT_INSIDE: 'Ring'") for e in e2) and any(e.startswith("RADIAL_PARENT") for e in e2)
    shared = copy.deepcopy(out)
    spec_mod.widget_index(shared)["Ring"]["style"]["brush"]["asset"] = "band"
    assert any(e.startswith("RADIAL_ASSET") for e in analyze.check(shared, BRIEF))
    assert any("empties by angle" in ln and "must be inside Panel" in ln for ln in analyze._contract_lines(BRIEF))


def test_derive_radial_puts_the_ring_on_its_circle_or_stops():
    s = ring_spec()
    al, *_ = ring_alpha()
    idx = spec_mod.widget_index(s)
    idx["Ring"]["bbox_intent"] = [84, 33, 230, 236]                          # LLM 이 조금 어긋나게 잡은 상자
    rec = analyze.derive_radial_fills(s, al)
    assert len(rec) == 1 and abs(rec[0]["radius"] - R) < 0.5
    x, y, w, h = idx["Ring"]["bbox_intent"]
    c = idx["Ring"]["style"]["brush"]["wipe"]["center"]
    assert abs(x + c[0] - CX) < 0.5 and abs(y + c[1] - CY) < 0.5 and idx["Ring"]["slot"]["padding"] == [x - 75, y - 25, 325 - x - w, 275 - y - h]
    assert spec_mod.widget_index(s)["Ring"]["style"]["brush"]["wipe"]["track_alpha"] == 0.18 and s["assets"][1]["size"] == [w, h]
    for bad in (None, np.zeros((H, W))):
        with pytest.raises(StageError) as e:
            analyze.derive_radial_fills(ring_spec(), bad)
        assert e.value.code == "RADIAL_MEASURE"


# ---------------------------------------------------------------------------------------------------------------------
# 레이어 · 오리기 — 픽셀마다 주인 하나

def _run_dir(tmp_path, al, col, spec, rid="R20261123_220001_Ring"):
    run = Run(rid, tmp_path / "work", config.load_pipeline(), tmp_path / "m.jsonl")
    run.create()
    a8 = np.clip(np.round(al * 255), 0, 255).astype(np.uint8)
    c8 = np.clip(np.round(col), 0, 255).astype(np.uint8)
    Image.fromarray(c8, "RGB").save(run.path("reference_color.png"))
    Image.fromarray(a8, "L").save(run.path("reference_alpha.png"))
    Image.fromarray(np.clip(np.round(col * al[..., None]), 0, 255).astype(np.uint8), "RGB").save(run.path("reference.png"))
    run.write_json("normalize.json", {"background": {"kind": "transparent"}})
    run.write_json("brief.json", {**BRIEF, "screen_id": "Ring"})
    run.write_json("spec.json", spec)
    return run


def test_layer_splits_the_ring_and_refine_gives_each_pixel_one_owner(tmp_path):
    al, col, ring, band = ring_alpha()
    s = ring_spec()
    analyze.derive_radial_fills(s, al)
    run = _run_dir(tmp_path, al, col, s)
    detail = layer.run(run, types.SimpleNamespace())
    lay = run.read_json("layer.json")
    assert lay["radials"][0]["widget"] == "Ring" and run.path(lay["radials"][0]["mask"]).is_file(), detail
    spec = run.read_json("spec.json")
    rm, pm = refine.own_mask(run, spec, "ring"), refine.own_mask(run, spec, "band")
    assert rm.any() and not (rm & pm).any()                                  # 서로 겹치지 않는다
    vis = al > 0.02
    assert (vis & ~(rm | pm)).sum() == 0                                     # 빠진 픽셀도 없다
    # 텍스처로 다시 합치면 나누기 전 그림
    tex = {}
    for aid, m in (("ring", rm), ("band", pm)):
        x, y, w, h = (int(v) for v in spec_mod.widget_index(spec)[{"ring": "Ring", "band": "Panel"}[aid]]["bbox_intent"])
        t = np.zeros((h, w, 4))
        t[..., :3] = col[y:y + h, x:x + w]
        t[..., 3] = np.where(m, al, 0)[y:y + h, x:x + w] * 255
        tex[aid] = t
    boxes = [{"id": w["id"], "x": b[0], "y": b[1], "w": b[2], "h": b[3], "visible": True} for w in spec["widgets"] for b in [w.get("bbox_intent") or [0, 0, W, H]]]
    for bg in (0, 128, 255):
        got = backdrop.compose(spec, boxes, tex, [W, H], (bg, bg, bg))[0]
        want = col * al[..., None] + bg * (1 - al[..., None])
        assert np.abs(got - want).max() < 1.0
    # 같은 폴더의 마스크가 없으면 조용히 통째로 그리지 않는다
    run2 = _run_dir(tmp_path, al, col, spec, "R20261123_220002_Ring")
    run2.write_json("layer.json", {})
    with pytest.raises(StageError) as e:
        refine.own_mask(run2, spec, "ring")
    assert e.value.code == "RADIAL_MASK"


def _toggle_spec():
    return {"schema_version": 1, "canvas": [400, 300], "profile": "hud", "root": "Root", "allow_overlap": [], "locked": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Ready", "type": "Overlay", "parent": "Root", "bbox_intent": [100, 200, 200, 80], "binding": {"data": "ready", "kind": "flag"}, "visibility": "collapsed",
         "slot": {"kind": "canvas", "anchors": [0.5, 1, 0.5, 1], "alignment": [0.5, 1], "position": [0, -20], "size": [200, 80]}},
        {"id": "Sign", "type": "Image", "parent": "Ready", "bbox_intent": [100, 200, 200, 40], "slot": {"kind": "overlay", "padding": [0, 0, 0, 40], "h_align": "fill", "v_align": "fill"},
         "style": {"brush": {"draw_as": "image", "asset": "sign"}}},
        {"id": "Key", "type": "TextBlock", "parent": "Ready", "bbox_intent": [185, 245, 30, 30], "slot": {"kind": "overlay", "padding": [85, 45, 85, 5], "h_align": "fill", "v_align": "fill"},
         "text": {"source": "static", "value": "R"}, "font": {"size": 16, "weight": "bold", "color": "#FFFFFF"}}],
        "assets": [{"asset_id": "sign", "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [200, 40], "prompt": "sign", "ref_bbox": [100, 200, 200, 40]}]}


def test_fill_toggles_grows_the_only_picture_of_a_collapsing_box():
    s = _toggle_spec()
    assert layer._carrier(s, s["widgets"][1])[1] is not None
    rec = layer.fill_toggles(s)
    sign = spec_mod.widget_index(s)["Sign"]
    assert len(rec) == 1 and sign["bbox_intent"] == [100, 200, 200, 80] and sign["slot"]["padding"] == [0, 0, 0, 0] and s["assets"][0]["size"] == [200, 80]
    assert layer._carrier(s, s["widgets"][1])[1] is None and layer.fill_toggles(s) == []                         # 이제 영역의 빛을 이 그림이 가질 수 있다
    two = _toggle_spec()
    two["widgets"].append({**copy.deepcopy(two["widgets"][2]), "id": "Sign2", "bbox_intent": [100, 240, 200, 40], "style": {"brush": {"draw_as": "image", "asset": "sign2"}}})
    two["assets"].append({**copy.deepcopy(two["assets"][0]), "asset_id": "sign2"})
    assert layer.fill_toggles(two) == []                                     # 그림이 둘이면 안 바꾼다
    box = _toggle_spec()
    spec_mod.widget_index(box)["Sign"]["style"]["brush"]["draw_as"] = "box"
    assert layer.fill_toggles(box) == []


# ---------------------------------------------------------------------------------------------------------------------
# 합성 · 상태 검사

def _ring_scene():
    al, col, ring, band = ring_alpha()
    s = ring_spec()
    analyze.derive_radial_fills(s, al)
    idx = spec_mod.widget_index(s)
    m = radial.measure(al, idx["Ring"]["bbox_intent"])["mask"]
    tex = {}
    for wid, aid, mm in (("Ring", "ring", m), ("Panel", "band", ~m)):
        x, y, w, h = (int(v) for v in idx[wid]["bbox_intent"])
        t = np.zeros((h, w, 4))
        t[..., :3] = col[y:y + h, x:x + w]
        t[..., 3] = np.where(mm, al, 0)[y:y + h, x:x + w] * 255
        tex[aid] = t
    boxes = [{"id": w["id"], "x": b[0], "y": b[1], "w": b[2], "h": b[3], "visible": True} for w in s["widgets"] for b in [w.get("bbox_intent") or [0, 0, W, H]]]
    return s, tex, boxes, {**dg.DEFAULTS}


def test_compose_wipes_the_ring_only():
    s, tex, boxes, _ = _ring_scene()
    full = backdrop.compose(s, boxes, tex, [W, H], (0, 0, 0))[0]
    half = backdrop.compose(state_check._with_percent(s, "Ring", 0.5), boxes, tex, [W, H], (0, 0, 0))[0]
    assert np.abs(full - half)[:, :195].max() < 1e-6                         # 왼쪽 반 그대로
    d = np.abs(full - half).max(axis=2)
    assert d[130:170, 305:325].max() > 100 and d[205:225, 150:250].max() == 0      # 오른쪽 고리는 흔적만, 띠는 그대로


@pytest.mark.parametrize("fault,check", [
    (None, None), ("center", "radial_arc"), ("mode", "radial_arc"), ("track", "radial_zero"), ("still", "radial_zero"), ("band", "radial_outside"), ("color", "radial_full")])
def test_radial_states_catch_wrong_renders(fault, check):
    s, tex, boxes, st = _ring_scene()
    base = backdrop.compose(s, boxes, tex, [W, H], (0, 0, 0))[0]

    def render(wid, p):
        sp = state_check._with_percent(s, wid, 1.0 if fault == "still" else p)
        wp = spec_mod.widget_index(sp)[wid]["style"]["brush"]["wipe"]
        if fault == "center":
            wp["center"] = [wp["center"][0] + 8, wp["center"][1]]
        if fault == "mode":
            wp["mode"] = "mirror"
        if fault == "track":
            wp["track_alpha"] = 0.6
        img = backdrop.compose(sp, boxes, tex, [W, H], (0, 0, 0))[0]
        if fault == "band":                                                  # 닦기가 띠까지 자른다
            k = radial.wipe_factor((H, W), (CX, CY), p, "clockwise", 0.18)
            z = np.zeros((H, W), bool)
            z[195:235, 110:290] = True
            img = np.where(z[..., None], img * k[..., None] + (1 - k[..., None]) * 90, img)
        if fault == "color" and p >= 1:                                       # 감마 · 색 공간을 틀린 머티리얼
            img = img * 0.6
        return img
    r = state_check.radial_states(s, boxes, tex, [W, H], st, base, render_pct=render)
    found = {f["check"] for f in r["findings"]}
    assert (found == set()) if fault is None else (check in found), (fault, found)
    assert set(r["images"]["Ring"]) == set(state_check.RADIAL_STATES) and r["gauges"][0]["renderer"][0.0] == "engine"
    offline = state_check.radial_states(s, boxes, tex, [W, H], st, base)
    assert offline["findings"] == [] and offline["gauges"][0]["renderer"][0.0] == "composite"


# ---------------------------------------------------------------------------------------------------------------------
# 요청이 정한 글자 외곽선

def test_requested_outline_goes_in_after_the_measured_effects_and_stays():
    s = _toggle_spec()
    brief = {"dynamic_data": [{"id": "key", "type": "text", "widget": "Key", "outline": {"size": 2, "color": "#0C0C0EDC"}}], "static_text": [], "required_elements": []}
    spec_mod.widget_index(s)["Key"]["font"]["glow"] = {"size": 4, "color": "#FFFFFF80"}
    rec = analyze.apply_requested_outlines(s, brief)
    k = spec_mod.widget_index(s)["Key"]
    assert k["font"]["outline"] == {"size": 2, "color": "#0C0C0EDC"} and "glow" not in k["font"] and rec[0]["glow_dropped"]["size"] == 4
    assert k["bbox_intent"] == [183, 243, 34, 34] and k["slot"]["padding"] == [83, 43, 83, 3]       # 글자 자리는 그대로, 상자만 외곽선만큼
    assert analyze.requested_outlines(brief) == {"Key": {"size": 2, "color": "#0C0C0EDC"}} and spec_mod.validate_semantics(s) == []
    assert "outline_locked" in style.text_fit.__code__.co_varnames
    ring = {"dynamic_data": [{"id": "l", "type": "progress", "widget": "Ring", "radial": {"mode": "clockwise"}}] + brief["dynamic_data"], "required_elements": [], "static_text": []}
    ops = [{"op": "set", "widget": "Key", "path": "font.outline", "value": None}, {"op": "set", "widget": "Ring", "path": "slot.padding", "value": [0, 0, 0, 0]},
           {"op": "set", "widget": "Ring", "path": "style.brush.wipe", "value": {}}, {"op": "set", "widget": "Key", "path": "slot.padding", "value": [0, 0, 0, 0]}]
    errs = fix.guard_ops(ops, s, ring)
    assert len(errs) == 3 and errs[0].startswith("op 0") and errs[1].startswith("op 1") and errs[2].startswith("op 2")


def test_test_inputs_cannot_rewrite_the_real_screen_contract():
    """시험용 옛 전투 HUD 입력은 검증 화면(C++ 없음) — 실제 화면으로 돌리면 새 바인딩이 선택으로 내려가고 재빌드된다."""
    screens = config.load_screens()
    fx = config.UIGEN_DIR / "fixtures"
    for name in ("m4_combat_hud_concept", "m4_combat_hud_flat", "m4_combat_hud_l2"):
        assert screens[config.load_yaml(fx / name / "inputs.yaml")["screen_id"]].get("probe") is True, name
    real = config.load_yaml(fx / "combat_hud_blade" / "inputs.yaml")
    assert real["screen_id"] == "CombatHUD" and schema.errors("inputs", real) == [] and normalize._inputs_errors(real) == []
    ref = json.loads((fx / "combat_hud_blade" / "concept_text_ref.json").read_text(encoding="utf-8"))
    assert {t["widget"] for t in ref["texts"]} >= {"UltKeyText"} and ref["lineage"][-1]["step"] == "pixels"
