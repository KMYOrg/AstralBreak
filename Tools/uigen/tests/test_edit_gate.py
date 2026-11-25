"""Phase 4 — 수정 회귀 게이트의 순수 계산(gen/edit_gate): 자리 · 픽셀 · spec · geometry · 외형 나누기 · edit.png. 합성 입력."""
from __future__ import annotations

import copy

import numpy as np
import pytest
from conftest import fixture_spec, widget
from PIL import Image

from core import spec as spec_mod
from gen import edit_gate


def g(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def test_scope_is_target_and_descendants_in_either_spec():
    a = fixture_spec()
    b = copy.deepcopy(a)
    b["widgets"].append({"id": "New", "type": "TextBlock", "parent": "ChainBox", "slot": {"kind": "vertical_box"}, "text": {"source": "static", "value": "x"}})
    assert edit_gate.scope(a, b, ["ChainPanel"]) == {"ChainPanel", "ChainBox", "ChainTitleText", "ChainTimerText", "ChainCountText", "New"}
    assert edit_gate.scope(a, b, ["New"]) == {"New"}
    assert edit_gate.scope(a, b, ["UltBlockedText"]) == {"UltBlockedText"}


def test_effect_pad_takes_the_larger_of_before_and_after():
    a = {"font": {"outline": {"size": 2}, "shadow": {"offset": [1, -5]}}}
    b = {"font": {"glow": {"size": 9}}}
    assert edit_gate.effect_pad(a) == 5 and edit_gate.effect_pad(a, b) == 9 and edit_gate.effect_pad({}, None) == 0
    s = fixture_spec()
    t = copy.deepcopy(s)
    widget(t, "UltBlockedText")["font"]["outline"] = {"size": 3, "color": "#000000FF"}
    assert edit_gate.pads(s, t, {"UltBlockedText", "ChainPanel"}) == {"UltBlockedText": 5, "ChainPanel": 2}


def test_zone_is_the_union_of_before_and_after_with_the_pad_and_is_clipped():
    z = edit_gate.zone_mask((50, 60), [{"A": g(10.4, 10.6, 5, 5)}, {"A": g(40, 10, 5, 5), "B": g(0, 0, 60, 50)}], ["A"], {"A": 2})
    assert z[8, 8] and z[17, 17] and not z[18, 18] and not z[7, 10]           # 10.4 − 2 → 8, 10.6 + 5 + 2 → 18(미만)
    assert z[12, 40] and not z[12, 30]                                          # 사이는 자리가 아니다 · 대상 아닌 B 는 안 든다
    z = edit_gate.zone_mask((50, 60), [{"A": g(-10, -10, 12, 12), "C": g(0, 0, 0, 0)}], ["A", "C"], {})
    assert z[0, 0] and z[3, 3] and not z[5, 5]                                  # 화면 밖은 자르고 크기 0 은 뺀다


def test_image_row_has_no_threshold():
    a = np.zeros((20, 30, 3), np.uint8)
    b = a.copy()
    b[5, 5] = (1, 0, 0)                     # 채널 하나 1 단계도 '다름'
    z = np.zeros((20, 30), bool)
    z[4:7, 4:7] = True
    assert edit_gate.image_row(a, b, z) == {"px": 1, "outside": 0, "box": [5, 5, 1, 1]}
    b[10, 20] = (0, 2, 0)
    r = edit_gate.image_row(a, b, z)
    assert (r["px"], r["outside"], r["outside_box"]) == (2, 1, [20, 10, 1, 1])
    fp = np.zeros((20, 30), bool)
    fp[10, 20] = True
    assert edit_gate.image_row(a, b, z, fp)["outside"] == 0                      # 대상이 실제로 그린 픽셀
    assert edit_gate.image_row(a, b[:10], z)["px"] == 600                        # 크기가 다르면 전부 다름
    assert edit_gate.image_row(a, b[:10], z[:10])["outside"] == 600              # 자리의 크기가 그림과 다르면 전부 밖


def test_compare_sets_counts_bytes_and_pixels(tmp_path):
    a = np.zeros((4, 4, 3), np.uint8)
    Image.fromarray(a).save(tmp_path / "a.png")
    Image.fromarray(a).save(tmp_path / "b.png", compress_level=0)                 # 바이트는 다르고 픽셀은 같다
    b = a.copy()
    b[1, 2] = 7
    Image.fromarray(b).save(tmp_path / "c.png")
    p = {k: str(tmp_path / f"{k}.png") for k in "abc"}
    r = edit_gate.compare_sets({"x": p["a"], "y": p["a"], "z": p["a"], "w": p["a"]}, {"x": p["a"], "y": p["b"], "z": p["c"], "extra": p["a"]})
    assert (r["n"], r["same_bytes"], r["same_pixels"]) == (4, 1, 2)
    assert r["different"] == {"z": {"px": 1, "box": [2, 1, 1, 1]}, "w": "missing", "extra": "extra"}


def _export(spec, textures=None):
    return {"spec": {"schema_version": 1, **spec_mod.roundtrip_view(spec)}, "textures": textures or []}


def test_spec_changes_only_looks_outside_the_targets():
    a = fixture_spec()
    b = copy.deepcopy(a)
    widget(b, "UltBlockedText")["font"]["size"] = 30
    res = edit_gate.spec_changes(_export(a), _export(b), {"UltBlockedText"}, touched=["UltBlockedText"])
    assert res["diffs"] == [] and res["touched_beyond"] == []
    widget(b, "ChainTitleText")["font"]["color"] = "#000000"
    res = edit_gate.spec_changes(_export(a), _export(b), {"UltBlockedText"}, touched=["UltBlockedText", "ChainTitleText"])
    assert len(res["diffs"]) == 1 and res["diffs"][0].startswith("ChainTitleText.font.color") and res["touched_beyond"] == ["ChainTitleText"]


def test_spec_changes_sees_added_removed_reordered_and_texture_settings():
    a = fixture_spec()
    b = copy.deepcopy(a)
    b["widgets"] = [w for w in b["widgets"] if w["id"] != "ChainCountText"]
    assert "ChainCountText: removed" in edit_gate.spec_changes(_export(a), _export(b), {"UltBlockedText"})["diffs"]
    assert "ChainCountText: added" in edit_gate.spec_changes(_export(b), _export(a), {"UltBlockedText"})["diffs"]
    c = copy.deepcopy(a)
    i, j = (next(k for k, w in enumerate(c["widgets"]) if w["id"] == n) for n in ("ChainTimerText", "ChainCountText"))
    c["widgets"][i], c["widgets"][j] = c["widgets"][j], c["widgets"][i]
    assert any(d.startswith("order:") for d in edit_gate.spec_changes(_export(a), _export(c), set())["diffs"])
    assert not edit_gate.spec_changes(_export(a), _export(c), {"ChainCountText"})["diffs"]          # 옮긴 것이 대상이면 나머지 순서는 같다
    t = {"asset_path": "/Game/x/T_a.T_a", "compression": "TC_EditorIcon", "lod_group": "g", "mip_gen": "m", "never_stream": True, "srgb": True, "size": [4, 4]}
    res = edit_gate.spec_changes(_export(a, [t]), _export(a, [{**t, "srgb": False}, {**t, "asset_path": "/Game/x/T_b.T_b"}]), set())
    assert len(res["diffs"]) == 1 and res["diffs"][0].startswith("texture /Game/x/T_a") and res["textures_added"] == ["/Game/x/T_b"]


def test_geometry_changes_split_by_scope():
    a = {"1x1": {"A": g(0, 0, 10, 10), "B": g(5, 5, 1, 1), "C": g(0, 0, 1, 1)}}
    b = {"1x1": {"A": g(0, 2, 10, 10), "B": g(5.005, 5, 1, 1), "D": g(0, 0, 1, 1)}}
    r = edit_gate.geometry_changes(a, b, {"A"})
    assert r["inside"] == {"A": {"1x1": 2.0}} and r["outside"] == {"C": {"1x1": None}, "D": {"1x1": None}}      # 0.005 px 는 같음
    assert edit_gate.geometry_changes(a, b, set())["outside"]["A"] == {"1x1": 2.0}


def _defect(code="E9", stage="text", widgets=("A",), box=(10, 10, 5, 5), check=None, n=1):
    return {"n": n, "code": code, "stage": stage, "widgets": list(widgets), "box": list(box), "cause": "size", **({"check": check} if check else {})}


def test_defects_are_split_into_inherited_intended_and_errors():
    z = np.zeros((100, 100), bool)
    z[10:30, 10:30] = True
    base = [_defect(widgets=("X",), box=(80, 80, 5, 5))]
    new = [_defect(widgets=("X",), box=(81, 80, 5, 5), n=1),                                     # base 에도 있음
           _defect(widgets=("A",), box=(90, 90, 5, 5), n=2),                                     # 대상 글자 자체의 측정
           _defect("E1", "texture", ("Plate",), (12, 12, 5, 5), n=3),                            # 자리 안
           _defect("E1", "texture", ("Plate",), (8, 12, 5, 5), n=4),                             # 자리 밖 2 px — 진단 창(7 × 7) 번짐 안
           _defect("E1", "texture", ("Plate",), (5, 12, 5, 5), n=5),                             # 자리 밖 5 px
           _defect("E8", "state", ("A",), (12, 12, 5, 5), check="gauge_end_gap", n=6),           # 엔진 그림끼리 견준 검사
           _defect("E8", "state", ("A",), (12, 12, 5, 5), check="text_trace", n=7),
           _defect("E9", "text", ("A", "Y"), (90, 90, 5, 5), n=8)]                               # 대상 밖 글자가 섞임
    r = edit_gate.split_defects(base, new, z, {"A"})
    assert [d["n"] for d in r["inherited"]] == [1]
    assert [d["n"] for d in r["intended"]] == [2, 3, 4, 7]
    assert [d["n"] for d in r["errors"]] == [5, 6, 8]
    ag = edit_gate.appearance({"name": "appearance", "pass": False, "value": 8, "details": {"errors": 8}}, r)
    assert not ag["pass"] and ag["value"] == 3 and ag["details"]["counts"] == {"inherited": 1, "intended": 4, "errors": 3}
    assert ag["details"]["diagnosis"] == {"errors": 8}
    assert edit_gate.appearance({"name": "appearance"}, {"inherited": [], "intended": r["intended"], "errors": []})["pass"]


def test_an_inherited_defect_is_matched_once():
    z = np.zeros((10, 10), bool)
    base = [_defect(widgets=("X",), box=(1, 1, 5, 5))]
    two = [_defect(widgets=("X",), box=(1, 1, 5, 5), n=1), _defect(widgets=("X",), box=(2, 2, 5, 5), n=2)]
    r = edit_gate.split_defects(base, two, z, {"A"})
    assert [d["n"] for d in r["inherited"]] == [1] and [d["n"] for d in r["errors"]] == [2]


def test_inside_needs_the_whole_box():
    z = np.zeros((40, 40), bool)
    z[10:20, 10:20] = True
    assert edit_gate.inside([10, 10, 10, 10], z) and edit_gate.inside([7, 10, 16, 10], z)        # + DEFECT_PAD(3) — 모서리는 둥글게 넓어진다
    assert not edit_gate.inside([6, 10, 5, 5], z) and not edit_gate.inside([10, 10, 30, 5], z) and not edit_gate.inside(None, z)
    assert not edit_gate.inside([-1, -1, 3, 3], np.ones((40, 40), bool)) and not edit_gate.inside([1, 1, 1, 1], np.zeros((40, 40), bool))


SPEC_OK = {"diffs": [], "touched_beyond": []}
GEO_OK = {"outside": {}, "inside": {}}


@pytest.mark.parametrize("spec, geo, images, ok, word", [
    (SPEC_OK, GEO_OK, {"a": {"px": 4, "outside": 0}}, True, None),
    (SPEC_OK, {"outside": {}, "inside": {"A": {"r": 3.0}}}, {"a": {"px": 0, "outside": 0}}, True, None),        # 그림이 안 변해도 옮겼으면 효과 있음
    (SPEC_OK, GEO_OK, {"a": {"px": 0, "outside": 0}}, False, "NO_EFFECT"),
    (SPEC_OK, GEO_OK, {}, False, "NO_EFFECT"),
    (SPEC_OK, GEO_OK, {"a": {"px": 4, "outside": 1}}, False, "pixels"),
    (SPEC_OK, {"outside": {"B": {"r": 0.5}}, "inside": {}}, {"a": {"px": 4, "outside": 0}}, False, "geometry"),
    ({"diffs": ["B.font: 1 != 2"], "touched_beyond": []}, GEO_OK, {"a": {"px": 4, "outside": 0}}, False, "spec"),
    ({"diffs": [], "touched_beyond": ["B"]}, GEO_OK, {"a": {"px": 4, "outside": 0}}, False, "reconciler"),
])
def test_regression_gate(spec, geo, images, ok, word):
    r = edit_gate.regression_gate(spec, geo, images, {"A"})
    assert r["name"] == "edit_regression" and r["pass"] is ok and r["threshold"] == 0
    assert ok == (not r["details"]["problems"]) and (word is None or any(word in p for p in r["details"]["problems"]))


def test_clusters_keep_far_targets_apart():
    z = np.zeros((300, 400), bool)
    z[10:30, 10:30] = True
    z[35:45, 10:20] = True                # 가까움 — 한 묶음
    z[200:260, 300:380] = True
    assert edit_gate.clusters(z) == [[300, 200, 80, 60], [10, 10, 20, 35]]
    assert edit_gate.clusters(np.zeros((5, 5), bool)) == []


def test_picture_shows_before_after_and_changed(tmp_path):
    a = np.zeros((200, 300, 3), np.uint8)
    b = a.copy()
    b[50:60, 50:60] = 200
    b[150:152, 250:252] = 9               # 자리 밖 — 묶음 그림 밖이라 이 장에는 안 보인다
    z = np.zeros((200, 300), bool)
    z[45:65, 45:65] = True
    rec = edit_gate.picture(tmp_path / "edit.png", [{"name": "state", "before": a, "after": b}, {"name": "small", "before": a[:9], "after": b[:9]}], z)
    assert rec["spots"] == [[45, 45, 20, 20]] and (tmp_path / "edit.png").is_file()
    im = np.asarray(Image.open(tmp_path / "edit.png"))
    assert (im == (255, 60, 60)).all(axis=2).any() and (im == (200, 200, 200)).all(axis=2).any()      # 달라진 픽셀(빨강) · 고친 뒤
    twice = edit_gate.picture(tmp_path / "twice.png", [{"name": "state", "before": a, "after": b}, {"name": "same", "before": a, "after": b.copy()}], z)
    assert twice["size"] == rec["size"]                                                               # 같은 그림은 한 번만
    assert edit_gate.picture(tmp_path / "none.png", [], z) is None and edit_gate.picture(tmp_path / "none.png", [], np.zeros((5, 5), bool)) is None
