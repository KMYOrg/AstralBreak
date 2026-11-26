"""1b 후속 J-a — 기능 단위 레이어(stages/layer) · 정적 판 글자 메우기(refine._plate_item_fill) · 요소 없는 판 프롬프트(gen/concept_convert)."""
from __future__ import annotations

import copy

import numpy as np

from core import schema
from core import spec as spec_mod
from gen import concept_convert
from stages import layer
from stages import refine

W, H = 400, 240


def _spec():
    an = {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [10, 10], "size": [380, 220], "z": 1}
    return {"schema_version": 1, "profile": "hud", "canvas": [W, H], "root": "Root",
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Area", "type": "Overlay", "parent": "Root", "bbox_intent": [10, 10, 380, 220], "slot": an},
                        {"id": "BandA", "type": "Image", "parent": "Area", "bbox_intent": [20, 20, 200, 60], "slot": {"kind": "overlay"},
                         "style": {"brush": {"draw_as": "image", "asset": "band_a"}}},
                        {"id": "Emblem", "type": "Image", "parent": "Area", "bbox_intent": [180, 40, 120, 120], "slot": {"kind": "overlay"},
                         "style": {"brush": {"draw_as": "image", "asset": "emblem"}}},
                        {"id": "Flag", "type": "Border", "parent": "Area", "bbox_intent": [300, 150, 80, 60], "slot": {"kind": "overlay"},
                         "binding": {"kind": "flag", "data": "f"}, "style": {"brush": {"draw_as": "image", "asset": "flag_frame"}}},
                        {"id": "FlagIcon", "type": "Image", "parent": "Flag", "bbox_intent": [310, 160, 30, 30], "slot": {"kind": "border"},
                         "style": {"brush": {"draw_as": "image", "asset": "flag_icon"}}},
                        {"id": "Label", "type": "TextBlock", "parent": "Area", "bbox_intent": [40, 30, 100, 40], "slot": {"kind": "overlay"},
                         "text": {"source": "static", "value": "공격"}}],
            "assets": [{"asset_id": a, "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [32, 32], "ref_bbox": [0, 0, 32, 32],
                        "prompt": "p"} for a in ("band_a", "emblem", "flag_frame", "flag_icon")]}


def _alpha():
    a = np.zeros((H, W))
    a[20:80, 20:220] = 0.95          # 띠
    a[40:160, 180:300] = 0.9         # 엠블럼(띠와 겹침 — 한 덩어리)
    a[150:210, 300:380] = 1.0        # flag 패널(기능 요소)
    a[5:7, 5:7] = 0.5                # 잡티
    return a


def test_classify_keeps_bindings_flags_and_their_children_functional():
    spec = _spec()
    fn = layer.classify(spec, {"separate": []})
    assert fn["Flag"].startswith("binding flag") and fn["FlagIcon"].startswith("inside Flag") and "Label" not in fn
    assert sorted(layer.static_widgets(spec, fn)) == ["BandA", "Emblem"]
    fn2 = layer.classify(spec, {"separate": ["Emblem"]})
    assert fn2["Emblem"] == "inputs separate" and layer.static_widgets(spec, fn2) == ["BandA"]


def test_plan_and_apply_bake_static_decorations_into_one_plate():
    spec = _spec()
    fn = layer.classify(spec, {})
    st = layer.static_widgets(spec, fn)
    pl = layer.plan(spec, _alpha(), fn, st)
    assert len(pl["plates"]) == 1 and pl["specks_px"] == 4                     # 띠 + 엠블럼 한 덩어리, 잡티는 판 아님
    p = pl["plates"][0]
    assert p["box"] == [20, 20, 280, 140] and p["region"] == "Area"
    assert not p["mask"][150:210, 302:378].any()                             # flag 패널 자리는 판이 아니다(기능 요소가 그린다)
    rec = layer.apply(spec, fn, st, pl["plates"])
    idx = spec_mod.widget_index(spec)
    assert idx["BandA"]["style"]["brush"] == {"draw_as": "none"} and idx["Emblem"]["style"]["brush"] == {"draw_as": "none"}
    assert sorted(rec["removed_assets"]) == ["band_a", "emblem"] and {a["asset_id"] for a in spec["assets"]} >= {"flag_frame", "flag_icon", "static_plate1"}
    plate = idx["StaticPlate1"]
    root_kids = [w["id"] for w in spec["widgets"] if w.get("parent") == "Root"]
    assert root_kids[0] == "StaticPlate1" and plate["slot"]["z"] == 1 and plate["slot"]["position"] == [20.0, 20.0]
    assert ["Area", "StaticPlate1"] in spec["allow_overlap"]
    a = next(x for x in spec["assets"] if x["asset_id"] == "static_plate1")
    assert a["source_mode"] == "plate" and a["provenance"] == "provided" and a["size"] == [280, 140]
    assert schema.errors("spec", spec) == [] and spec_mod.validate_semantics(spec) == []


def test_text_only_blob_and_unfixed_region_are_not_plates():
    spec = _spec()
    a = np.zeros((H, W))
    a[35:65, 45:135] = 1.0           # 글자 획만(투명 위)
    fn = layer.classify(spec, {})
    assert layer.plan(spec, a, fn, layer.static_widgets(spec, fn))["plates"] == []
    spec2 = copy.deepcopy(spec)
    spec2["widgets"][1]["slot"]["anchors"] = [0, 0, 1, 0]                       # 늘어나는 영역 — 안의 장식은 기능 요소 길
    fn2 = layer.classify(spec2, {})
    assert fn2["BandA"] == "region changes size with the screen" and layer.static_widgets(spec2, fn2) == []


def test_plate_item_fill_replaces_only_the_glyph_strokes():
    """판 메우기는 '판과 다른 글자 획'만 — 판이 테두리를 2 px 옆에 다시 그려도 글자 밖 테두리는 컨셉 그대로(배지 양옆 선이 안 생김)."""
    h, w = 80, 160
    col = np.zeros((h, w, 3))
    col[...] = (40, 110, 200)
    col[:, 120:123] = (240, 240, 240)                                          # 컨셉 테두리선(글자 상자 밖)
    a = np.full((h, w), 0.95)
    nt = col.copy()
    nt[:, 120:123] = (40, 110, 200)
    nt[:, 122:125] = (240, 240, 240)                                           # 판은 테두리를 2 px 옆에
    glyph = np.zeros((h, w), bool)
    glyph[30:36, 40:100] = True
    glyph[30:60, 40:46] = True
    col[glyph] = (250, 250, 250)
    P = 6
    nt_pad, a_pad = np.pad(nt, ((P, P), (P, P), (0, 0)), mode="edge"), np.pad(a, P, mode="edge")
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, nt_pad, a_pad, {"id": "T", "box": [36, 24, 70, 42], "glow": 0, "colors": [[250, 250, 250]]})
    assert r["used"] and np.abs(c2[glyph] - np.array([40, 110, 200])).max() < 3      # 획 자리 = 판(띠 색)
    assert (c2[:, 120:123] == col[:, 120:123]).all()                                # 글자 밖 테두리는 컨셉 그대로


def test_plate_item_fill_text_on_transparency_and_full_gauge_mask():
    """1b 후속 J — 투명 위 빛 글자: 판이 불투명 바탕(0.9)이라 정합 없이 둘레 컨셉으로 메워 투명하게 · 가득 찬 게이지 mask: 그 자리만 판 픽셀로."""
    h, w = 80, 200
    col = np.zeros((h, w, 3))
    a = np.zeros((h, w))
    glyph = np.zeros((h, w), bool)
    for gx in (60, 82, 104):                                                    # 글자 셋('ㅁ' 모양 — 글자 하나보다 긴 가는 선은 획에서 빠지므로 짧게)
        glyph[30:50, gx:gx + 4] = glyph[30:50, gx + 14:gx + 18] = glyph[30:34, gx:gx + 18] = glyph[46:50, gx:gx + 18] = True
    from gen import diagnose as dg
    halo = dg._dilate(glyph, 6) & ~glyph
    col[glyph], a[glyph] = (250, 70, 30), 1.0
    col[halo], a[halo] = (230, 40, 20), 0.35                                    # 빛 번짐
    nt = np.full((h, w, 3), 20.0)
    nta = np.full((h, w), 0.9)                                                  # codex 판은 글자 둘레를 불투명 바탕으로
    P = 6
    nt_pad, a_pad = np.pad(nt, ((P, P), (P, P), (0, 0)), mode="edge"), np.pad(nta, P, mode="edge")
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, nt_pad, a_pad, {"id": "T", "box": [50, 20, 82, 40], "glow": 6, "colors": [[250, 70, 30]]})
    assert r["used"] and "transparent" in r["alpha_from"] and a2[glyph].max() < 0.1     # 글자 · 빛은 판에서 빠지고(엔진이 그림) 투명
    # 가득 찬 게이지 — mask 자리만 판 픽셀, 넓히거나 섞지 않음
    col = np.full((h, w, 3), 100.0)
    a = np.ones((h, w))
    col[30:50, 20:180] = (120, 240, 60)
    nt = np.full((h, w, 3), 30.0)
    m = np.zeros((h, w), bool)
    m[30:50, 20:180] = True
    nt_pad, a_pad = np.pad(nt, ((P, P), (P, P), (0, 0)), mode="edge"), np.pad(np.ones((h, w)), P, mode="edge")
    c3, a3 = col.copy(), a.copy()
    r = refine._plate_item_fill(c3, a3, nt_pad, a_pad, {"id": "G", "box": [20, 30, 160, 20], "glow": 0, "gauge": True, "mask": m})
    assert r["used"] and r["mask"] and (c3[m] == 30).all() and (c3[~m] == 100).all()


def test_element_free_prompt_adds_gauges_and_runtime_pictures_only():
    import make_concept
    plain = make_concept.TEXT_FREE_PROMPT.strip() + "\n" + make_concept.TEXT_FREE_TRANSPARENT.strip()
    assert concept_convert.notext_prompt({"data": [], "required_elements": []}) == plain                # 지울 기능 요소 없음 → 예전 판(캐시 그대로)
    inputs = {"required_elements": [{"id": "Hp", "desc": "HP bar"}, {"id": "Face", "desc": "portrait"}, {"id": "Panel", "desc": "panel"}],
              "data": [{"id": "hp", "type": "progress", "widget": "Hp"}, {"id": "face", "type": "image", "widget": "Face"},
                       {"id": "p", "type": "flag", "widget": "Panel"}, {"id": "n", "type": "text", "widget": "Name"}],
              "separate": ["Panel"]}
    lines = concept_convert.element_free_lines(inputs)
    assert len(lines) == 3 and "HP bar" in lines[0] and "portrait" in lines[1] and "panel" in lines[2]
    assert concept_convert.notext_prompt(inputs).startswith(make_concept.TEXT_FREE_PROMPT.strip()) and "HP bar" in concept_convert.notext_prompt(inputs)
