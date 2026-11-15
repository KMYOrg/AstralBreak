"""1b 후속 B — 게이지 채움 · 배경을 컨셉에서 결정적으로(derive_gauge_fills) · procedural gradient_bar · 꺼진 flag 초기 접힘 ·
flag 위젯 상자 패널 금지(FLAG_IN_BOX) · 게이지 렌더 지표."""
from __future__ import annotations

import pytest
from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw

from core import schema
from gen import fidelity, procedural
from stages import analyze

BOX = [742, 982, 436, 24]             # 손 spec UltGauge bbox_intent
TOP, BOTTOM, EMPTY = (250, 200, 90), (180, 120, 40), (30, 20, 15)


def concept(tmp_path, percent=0.7):
    im = Image.new("RGB", (1920, 1080), (60, 50, 70))
    d = ImageDraw.Draw(im)
    x, y, w, h = BOX
    split = x + int(round(percent * w))
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=EMPTY)
    d.rectangle([x, y, split - 1, y + h // 2 - 1], fill=TOP)
    d.rectangle([x, y + h // 2, split - 1, y + h - 1], fill=BOTTOM)
    p = tmp_path / "reference.png"
    im.save(p)
    return p


def gauge_spec(with_extract_frame=False):
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    if with_extract_frame:
        spec["assets"].append({"asset_id": "ult_gauge_frame", "kind": "frame", "provenance": "codex", "source_mode": "extract", "size": [920, 88],
                               "prompt": "gauge frame", "ref_bbox": [730, 972, 460, 44]})
        i = next(k for k, w in enumerate(spec["widgets"]) if w["id"] == "UltGauge")
        spec["widgets"].insert(i, {"id": "UltGaugeFrame", "type": "Image", "parent": "UltArea", "slot": {"kind": "overlay", "h_align": "fill", "v_align": "fill"},
                                   "bbox_intent": [730, 972, 460, 44], "style": {"brush": {"draw_as": "image", "asset": "ult_gauge_frame"}}})
    return spec


def test_gradient_bar_interpolates_stops_top_to_bottom():
    w, h, rgba = procedural.render({"asset_id": "f", "size": [4, 10], "procedural": {"shape": "gradient_bar", "stops": ["#FF0000FF", "#0000FFFF"]}})
    top, bottom = rgba[0:4], rgba[(9 * 4) * 4:(9 * 4) * 4 + 4]
    assert (w, h) == (4, 10) and top[0] > 230 and top[2] < 25 and bottom[2] > 230 and bottom[0] < 25 and rgba[4:8] == top    # 가로는 같은 색
    with pytest.raises(procedural.ProceduralError):
        procedural.render({"asset_id": "f", "size": [4, 4], "procedural": {"shape": "gradient_bar", "stops": ["#FFFFFFFF"]}})


def test_derive_samples_the_filled_rows_and_the_empty_color(tmp_path):
    spec = gauge_spec()
    recs = analyze.derive_gauge_fills(spec, concept(tmp_path))
    rec = next(r for r in recs if r["widget"] == "UltGauge")
    assert rec["fill_asset"] == "ult_gauge_fill" and rec["stops"] == 24 and rec["background_from"].startswith("concept empty part")
    a = next(x for x in spec["assets"] if x["asset_id"] == "ult_gauge_fill")
    stops = a["procedural"]["stops"]
    assert a["provenance"] == "procedural" and a["size"] == [64, 24] and stops[0] == "#FAC85AFF" and stops[-1] == "#B47828FF"
    st = widget(spec, "UltGauge")["style"]
    assert st["fill"] == {"draw_as": "image", "asset": "ult_gauge_fill"} and st["background"]["color"] == "#1E140FFF" and st["background"]["draw_as"] == "rounded_box"
    assert schema.errors("spec", spec) == []


def test_derive_leaves_the_track_to_an_extracted_frame_underneath(tmp_path):
    spec = gauge_spec(with_extract_frame=True)
    rec = analyze.derive_gauge_fills(spec, concept(tmp_path))[0]
    assert widget(spec, "UltGauge")["style"]["background"] == {"draw_as": "none"} and "UltGaugeFrame" in rec["background_from"]


def test_derive_right_to_left_and_skips(tmp_path):
    spec = gauge_spec()
    st = widget(spec, "UltGauge")["style"]
    st["bar_fill_type"] = "right_to_left"
    rec = analyze.derive_gauge_fills(spec, concept(tmp_path, percent=0.7))[0]
    x, _, w, _ = BOX
    assert rec["sampled"][0] >= x + round(0.3 * w)                      # 오른쪽 70 % 에서 뽑음
    spec2 = gauge_spec()
    widget(spec2, "UltGauge")["style"]["percent"] = 0.02
    assert "too small" in analyze.derive_gauge_fills(spec2, concept(tmp_path))[0]["skipped"]


def test_sample_off_flags_start_collapsed():
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    assert widget(spec, "UltReadyGlow")["visibility"] == "collapsed" and widget(spec, "BurstBanner")["visibility"] == "collapsed"
    assert widget(spec, "UltBlockedText")["visibility"] == "collapsed" and "visibility" not in widget(spec, "ChainPanel")     # 샘플 true


def test_flag_widget_inside_a_box_panel_is_rejected():
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    assert not [e for e in analyze.check(spec, fixture_brief()) if e.startswith("FLAG_IN_BOX")]
    w = widget(spec, "UltBlockedText")
    w["parent"], w["slot"] = "ChainBox", {"kind": "vertical_box"}
    errs = [e for e in analyze.check(spec, fixture_brief()) if e.startswith("FLAG_IN_BOX")]
    assert len(errs) == 1 and "'UltBlockedText'" in errs[0] and "VerticalBox 'ChainBox'" in errs[0]


def test_gauge_vs_concept_rows(tmp_path):
    ref = concept(tmp_path)
    same = fidelity.gauge_vs_concept(ref, ref, BOX, 0.7)
    assert same["filled"]["rows"]["mean"] == 0.0 and same["empty"]["representative"] == 0.0
    flat = Image.open(ref).convert("RGB")
    ImageDraw.Draw(flat).rectangle([BOX[0], BOX[1], BOX[0] + int(0.7 * BOX[2]) - 1, BOX[1] + BOX[3] - 1], fill=(242, 181, 68))     # 단색 채움
    p = tmp_path / "flat.png"
    flat.save(p)
    assert fidelity.gauge_vs_concept(ref, p, BOX, 0.7)["filled"]["rows"]["max"] > 8
