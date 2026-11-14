"""게이트 계산 — 합성 geometry 로 (에디터 없이)."""
from __future__ import annotations

import pytest
from conftest import fixture_brief, fixture_spec, widget
from fake_editor import layout, painted_layout

from core import config
from core import geometry as geo
from core import spec as S
from stages import verify

GATES = config.load_profile("hud")["gates"]
STACK = config.load_profile("hud")["stacking_parents"]


def G(wid, x, y, w, h, parent="Root", type_="Image", visible=True):
    return {"id": wid, "type": type_, "parent": parent, "x": x, "y": y, "w": w, "h": h, "visible": visible}


def fixture_geometry(spec=None, res=(1920, 1080)):
    spec = spec or fixture_spec()
    types = {w["id"]: w["type"] for w in spec["widgets"]}
    parents = {w["id"]: w.get("parent", "") for w in spec["widgets"]}
    return [G(wid, *b, parent=parents[wid], type_=types[wid]) for wid, b in painted_layout(spec, *res).items()]


def test_fake_layout_matches_hand_bbox_intent():
    """손 spec 의 bbox_intent 는 박스 fill 비율로 계산한 값 — 가짜 배치 계산기와 0 px 로 같다(실제 렌더도 1a-2 에서 0 px)."""
    spec = fixture_spec()
    boxes = layout(spec, 1920, 1080)
    for w in spec["widgets"]:
        if w.get("bbox_intent"):
            assert [round(v, 3) for v in boxes[w["id"]]] == w["bbox_intent"], w["id"]


def test_iou_and_center():
    assert geo.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert geo.iou((0, 0, 10, 10), (10, 0, 10, 10)) == 0           # 맞닿음
    assert geo.iou((0, 0, 10, 10), (5, 0, 10, 10)) == pytest.approx(50 / 150)
    assert geo.center_distance((0, 0, 10, 10), (3, 4, 10, 10)) == 5


def test_offscreen_rules():
    g = [G("in", 0, 0, 1920, 1080), G("right", 1900, 0, 40, 10), G("hidden", -50, 0, 10, 10, visible=False),
         G("zero", -50, 0, 0, 10), G("eps", -0.4, 0, 10, 10), G("top", 10, -3, 10, 10), G("culled", 0, 0, 0, 0)]
    out = {o["id"]: o for o in geo.offscreen(g, (1920, 1080))}
    assert {k: v["out"] for k, v in out.items() if k != "culled"} == {"right": {"right": 20.0}, "top": {"top": 3.0}}
    assert out["culled"]["not_painted"] is True and out["culled"]["bbox"] is None   # 컬링 = (0, 0, 0, 0) [실측]


def test_culled_widgets_in_the_fake_render():
    spec = fixture_spec()
    widget(spec, "UltArea")["slot"]["position"] = [1920, -64]             # 완전히 밖 → 자기 · 자식 컬링
    widget(spec, "ChainPanel")["slot"]["position"] = [100, 140]           # 걸침 → 그려짐(실제 좌표)
    boxes = painted_layout(spec, 1920, 1080)
    assert boxes["UltArea"] == boxes["UltGauge"] == boxes["UltReadyGlow"] == (0, 0, 0, 0)
    assert boxes["ChainPanel"][0] == 1920 + 100 - 260 and not geo.painted({"x": 0, "y": 0, "w": 0, "h": 0}) and geo.painted(G("a", 0, 0, 1, 1))
    off = {o["id"] for o in geo.offscreen([G(k, *b) for k, b in boxes.items()], (1920, 1080))}
    assert {"UltArea", "UltGauge", "UltReadyGlow", "ChainPanel", "ChainBox"} <= off


def test_overlap_rules():
    spec = {"root": "Root", "widgets": [], "allow_overlap": [["A", "C"]]}
    g = [G("Root", 0, 0, 1920, 1080, parent="", type_="CanvasPanel"),
         G("A", 0, 0, 100, 100), G("B", 98, 0, 100, 100),           # 2 % — 통과
         G("C", 50, 50, 100, 100),                                    # A 와 25 % 지만 allow_overlap · B 와 48/100*50.. 겹침
         G("O", 500, 500, 100, 100, type_="Overlay"), G("O1", 500, 500, 100, 100, parent="O"), G("O2", 500, 500, 100, 100, parent="O")]
    res = geo.overlaps(g, spec, 0.04, ["Overlay"])
    pairs = {(v["a"], v["b"]) for v in res["violations"]}
    assert pairs == {("B", "C")} and res["allowed"] == 1 and res["skipped_stacking"] == 1


def test_placement_categories_and_small_rule():
    spec = fixture_spec()
    rows = geo.placement(spec, fixture_geometry(spec), GATES)
    assert {r["id"] for r in rows["region"]} == {"UltArea", "UltBlockedText", "ChainPanel", "BurstBanner"}
    assert {r["id"] for r in rows["inner"]} == {"ChainBox", "BurstRow"}
    assert "UltGauge" in {r["id"] for r in rows["leaf"]} and all(r["pass"] for c in rows.values() for r in c)
    rule = {r["id"]: r["rule"] for c in rows.values() for r in c}
    assert rule["UltBlockedText"] == "center" and rule["UltGauge"] == "center" and rule["ChainPanel"] == "iou" and rule["ChainTimerText"] == "iou"


def test_placement_failures_and_missing():
    spec = fixture_spec()
    geom = [g for g in fixture_geometry(spec) if g["id"] != "BurstCountText"]
    for g in geom:
        if g["id"] == "ChainPanel":
            g["x"] -= 65    # IoU 0.6
        if g["id"] == "UltBlockedText":
            g["y"] += 9     # 중심 9 px > 8
    rows = geo.placement(spec, geom, GATES)
    failed = {r["id"] for c in rows.values() for r in c if not r["pass"]}
    assert failed == {"ChainPanel", "UltBlockedText", "BurstCountText"}
    miss = next(r for r in rows["leaf"] if r["id"] == "BurstCountText")
    assert miss.get("missing") and miss["value"] is None


def test_render_gates_all_pass_on_fixture():
    spec = fixture_spec()
    renders = [{"resolution": list(r), "geometry": fixture_geometry(spec, r)} for r in ((1920, 1080), (2560, 1080), (1920, 1200))]
    gates, extra = verify.render_gates(spec, renders, [1920, 1080], GATES, STACK)
    assert [g["name"] for g in gates] == ["offscreen", "overlap", "iou_region", "iou_leaf"] and all(g["pass"] for g in gates)
    assert gates[2]["value"]["iou_min"] == 1 and gates[3]["value"]["center_max_px"] == 0


def test_texture_gate():
    manifest = {"assets": [{"asset_id": "a", "ue_path": "/Game/_AutoGen/R/T_a", "compression": "TC_BC7", "size": [8, 8]},
                           {"asset_id": "b", "ue_path": "/Game/_AutoGen/R/T_b", "compression": "TC_EditorIcon", "size": [8, 8]}]}
    tex = {"lod_group": "TEXTUREGROUP_UI", "mip_gen": "TMGS_NoMipmaps", "never_stream": True, "srgb": True}
    good = [{"asset_path": "/Game/_AutoGen/R/T_a.T_a", "compression": "TC_BC7", "size": [8, 8], **tex},
            {"asset_path": "/Game/_AutoGen/R/T_b.T_b", "compression": "TC_EditorIcon", "size": [8, 8], **tex}]
    assert verify.gate_textures(good, manifest, tex)["pass"]
    bad = [dict(good[0], compression="TC_EditorIcon"), dict(good[1], srgb=False), {"asset_path": "/Game/X/T_z.T_z", **tex}]
    g = verify.gate_textures(bad, manifest, tex)
    assert not g["pass"] and g["value"] == 3
    assert {m.get("asset_id") or m.get("texture") for m in g["details"]["mismatches"]} == {"a", "b", "/Game/X/T_z"}


def test_required_baked_text_and_samples():
    brief = fixture_brief()
    spec = fixture_spec()
    assert verify.gate_required(brief, spec)["pass"]
    spec["widgets"] = [w for w in spec["widgets"] if w["id"] != "BurstCountText"]
    assert verify.gate_required(brief, spec)["details"]["missing"] == ["BurstCountText"]
    g = verify.gate_baked_text({"assets": [{"asset_id": "x", "backend": "procedural"}]})
    assert g["pass"] and "procedural" in g["skipped"]
    g = verify.gate_baked_text({"assets": [{"asset_id": "x", "backend": "codex", "ocr_text": "HP"}]})
    assert not g["pass"]
    ov = verify.sample_overrides(brief)
    assert ov["UltGauge"] == {"percent": 0.7} and ov["ChainTimerText"] == {"text": "4.2"} and ov["BurstCountText"] == {"text": "3"}
    assert ov["ChainPanel"] == {"visible": True} and ov["BurstBanner"] == {"visible": False} and ov["ChainCountText"] == {"text": "2/4"}


def test_roundtrip_gate_uses_manifest_paths():
    spec = fixture_spec()
    norm = S.normalize(spec)
    manifest = {"assets": [{"asset_id": a["asset_id"], "ue_path": f"/Game/_AutoGen/R/T_{a['asset_id']}"} for a in spec["assets"]]}
    exported = {"root": norm["root"], "widgets": [dict(w) for w in norm["widgets"]], "locked": []}
    for w in exported["widgets"]:
        for key, brush in (w.get("style") or {}).items():
            if isinstance(brush, dict) and brush.get("asset"):
                w["style"] = {**w["style"], key: {**brush, "asset": f"/Game/_AutoGen/R/T_{brush['asset']}.T_{brush['asset']}"}}
    g, rt = verify.gate_roundtrip(spec, {"spec": exported, "guid_missing": []}, manifest)
    assert g["pass"] and rt["equal"]
    widget(exported, "UltGauge")["style"]["percent"] = 0.5
    g, rt = verify.gate_roundtrip(spec, {"spec": exported, "guid_missing": ["X"]}, manifest)
    assert not g["pass"] and rt["diffs"] and rt["guid_missing"] == ["X"]
