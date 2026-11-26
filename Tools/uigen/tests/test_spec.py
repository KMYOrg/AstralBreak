from __future__ import annotations

import copy

import pytest
from conftest import fixture_spec, widget

from core import spec as S


def codes(errs: list[str]) -> set[str]:
    return {e.split(":", 1)[0] for e in errs}


def test_fixture_is_semantically_valid():
    assert S.validate_semantics(fixture_spec()) == []


@pytest.mark.parametrize("mutate, code", [
    (lambda s: s["widgets"].append(copy.deepcopy(widget(s, "BurstRow"))), "DUPLICATE_ID"),
    (lambda s: widget(s, "UltGauge").update(parent="Nowhere"), "PARENT_NOT_FOUND"),
    (lambda s: widget(s, "UltGauge")["slot"].update(kind="canvas"), "SLOT_KIND"),
    (lambda s: s["widgets"].append({"id": "Extra", "type": "Spacer", "parent": "ChainPanel", "slot": {"kind": "border"}}), "TOO_MANY_CHILDREN"),
    (lambda s: widget(s, "ChainPanel")["style"].update(percent=0.5), "STYLE_KEY"),
    (lambda s: widget(s, "UltGauge").update(justification="center"), "TEXT_FIELD"),
    (lambda s: widget(s, "UltGauge").update(binding={"data": "ult_gauge", "kind": "text"}), "BINDING_TYPE"),
    (lambda s: widget(s, "UltGauge")["style"]["background"].update(asset="missing_asset"), "ASSET_NOT_FOUND"),
    (lambda s: widget(s, "ChainPanel").update(parent="ChainBox"), "UNREACHABLE"),
    (lambda s: widget(s, "ChainTimerText")["binding"].update(data="other"), "TEXT_DATA"),
    (lambda s: widget(s, "BurstBanner")["binding"].update(data="chain_panel"), "DUPLICATE_BINDING_DATA"),
    (lambda s: s["widgets"].append({"id": "Kid", "type": "Spacer", "parent": "UltGauge"}), "PARENT_IS_LEAF"),
    (lambda s: widget(s, "Root").update(slot={"kind": "canvas"}), "ROOT_HAS_SLOT"),
    (lambda s: s.update(locked=["Ghost"]), "LOCKED_NOT_FOUND"),
    (lambda s: s.update(allow_overlap=[["UltArea", "Ghost"]]), "ALLOW_OVERLAP_NOT_FOUND"),
    (lambda s: widget(s, "BurstBanner")["style"]["brush"].update(margin=[0.1, 0.1, 0.1, 0.1]), "BRUSH_MARGIN"),
])
def test_semantic_errors(mutate, code):
    s = fixture_spec()
    mutate(s)
    assert code in codes(S.validate_semantics(s))


def test_tree_order_is_depth_first_in_sibling_order():
    s = fixture_spec()
    s["widgets"].reverse()   # 목록 순서가 바뀌어도 형제끼리의 상대 순서만 본다 — 뒤집으면 형제 순서도 뒤집힌다
    order = S.tree_order(fixture_spec())
    assert order[0] == "Root"
    assert order.index("UltArea") < order.index("UltReadyGlow") < order.index("UltGauge") < order.index("UltBlockedText")
    assert order.index("ChainBox") < order.index("ChainTitleText") < order.index("ChainTimerText") < order.index("ChainCountText")


def test_normalize_fills_defaults_and_canonicalizes():
    n = S.normalize(fixture_spec())
    w = {x["id"]: x for x in n["widgets"]}
    assert [x["id"] for x in n["widgets"]] == S.tree_order(fixture_spec())
    assert "slot" not in w["Root"] and w["Root"]["visibility"] == "self_hit_test_invisible"
    assert w["UltReadyGlow"]["slot"] == {"kind": "overlay", "padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill"}
    assert w["UltBlockedText"]["slot"]["auto_size"] is False
    assert w["UltBlockedText"]["font"] == {"size": 22, "weight": "bold", "color": "#FF6B5EFF", "family": None}
    assert w["UltGauge"]["style"]["background"]["image_size"] == [200, 50]          # 기본 = 에셋 크기
    assert w["UltGauge"]["style"]["fill"] == {"draw_as": "rounded_box", "color": "#E8B54AFF", "radius": 6, "outline_color": "#00000000",
                                              "outline_width": 0, "image_size": [32, 32]}
    assert w["UltGauge"]["style"]["fill_color"] == "#FFFFFFFF"
    assert w["ChainTimerText"]["text"] == {"source": "dynamic", "data": "chain_remaining", "sample": "4.2"}
    assert w["ChainTimerText"]["binding"]["optional"] is False
    assert w["UltReadyGlow"]["visibility"] == "visible"


def test_normalize_is_idempotent():
    n = S.normalize(fixture_spec())
    assert S.normalize(n) == n
    assert S.canonical_json(S.normalize(n)) == S.canonical_json(n)


def test_numbers_and_colors():
    assert S.canon_number(4.0) == 4 and isinstance(S.canon_number(4.0), int)
    assert S.canon_number(0.08000000119) == 0.08
    assert S.canon_number(-0.0001) == 0
    assert S.canon_color("#e8b54a") == "#E8B54AFF"
    assert S.parse_color("#2A1A0ACC") == (42, 26, 10, 204)


def _fake_export(spec: dict, run_id: str = "R20261114_000000_CombatHUD") -> tuple[dict, dict]:
    """브리지 export_widget_spec 흉내 — 기본값 전부 명시 · UE 경로 · 소문자 색 · float 잡음 · 동적/정적 구분 없음 · 바인딩 · bbox 없음."""
    n = S.normalize(spec)
    ue = {a["asset_id"]: f"/Game/_AutoGen/{run_id}/T_{a['asset_id']}" for a in spec["assets"]}
    out = {"schema_version": 1, "canvas": n["canvas"], "profile": n["profile"], "root": n["root"], "widgets": []}
    for w in n["widgets"]:
        w = copy.deepcopy(w)
        w.pop("binding", None)
        w.pop("bbox_intent", None)
        for b in (w.get("style") or {}).values():
            if isinstance(b, dict):
                if b.get("asset"):
                    b["asset"] = f"{ue[b['asset']]}.T_{b['asset']}"
                b["color"] = b["color"].lower()
        if "slot" in w and "position" in w["slot"]:
            w["slot"]["position"] = [v + 1e-7 for v in w["slot"]["position"]]
        if "text" in w:
            t = w["text"]
            w["text"] = {"value": t.get("value", t.get("sample", ""))}
        out["widgets"].append(w)
    out["widgets"].append(out["widgets"].pop(0))   # 루트를 맨 뒤로 — 형제 순서는 그대로
    return out, {path: aid for aid, path in ue.items()}


def test_roundtrip_equal_for_faithful_export():
    s = fixture_spec()
    exported, ue_map = _fake_export(s)
    ok, d = S.roundtrip_equal(s, exported, ue_map)
    assert ok, d


def test_roundtrip_detects_change():
    s = fixture_spec()
    exported, ue_map = _fake_export(s)
    next(w for w in exported["widgets"] if w["id"] == "ChainCountText")["text"]["value"] = "3/4"
    next(w for w in exported["widgets"] if w["id"] == "UltArea")["slot"]["size"] = [470, 44]
    ok, d = S.roundtrip_equal(s, exported, ue_map)
    assert not ok
    assert any("ChainCountText" in x and "3/4" in x for x in d), d
    assert any("UltArea" in x and "size" in x for x in d), d


def test_roundtrip_detects_sibling_reorder():
    s = fixture_spec()
    exported, ue_map = _fake_export(s)
    ws = exported["widgets"]
    i, j = next(k for k, w in enumerate(ws) if w["id"] == "ChainTitleText"), next(k for k, w in enumerate(ws) if w["id"] == "ChainCountText")
    ws[i], ws[j] = ws[j], ws[i]
    ok, _ = S.roundtrip_equal(s, exported, ue_map)
    assert not ok


def test_roundtrip_view_drops_non_wbp_fields():
    v = S.roundtrip_view(fixture_spec())
    for w in v["widgets"]:
        assert "binding" not in w and "bbox_intent" not in w
    assert {"value": "4.2"} == next(w for w in v["widgets"] if w["id"] == "ChainTimerText")["text"]


def test_bound_widgets_match_contract(brief):
    assert sorted(S.bound_widgets(fixture_spec())) == sorted(brief["binding_contract"]["bindings"])
