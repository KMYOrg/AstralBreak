from __future__ import annotations

import copy

import pytest
from conftest import fixture_spec, widget

from core import spec as S
from core.patch import PatchError, apply_patch, branch_for, regenerate_assets


def P(*ops, source="fix"):
    return {"schema_version": 1, "source": source, "ops": list(ops)}


def test_set_changes_copy_only():
    s = fixture_spec()
    before = copy.deepcopy(s)
    out = apply_patch(s, P({"op": "set", "widget": "UltArea", "path": "slot.position", "value": [0, -72]}))
    assert widget(out, "UltArea")["slot"]["position"] == [0, -72]
    assert s == before


def test_set_creates_and_clears_nested():
    out = apply_patch(fixture_spec(), P({"op": "set", "widget": "UltReadyGlow", "path": "slot.padding", "value": [2, 2, 2, 2]}))
    assert widget(out, "UltReadyGlow")["slot"]["padding"] == [2, 2, 2, 2]
    out2 = apply_patch(out, P({"op": "set", "widget": "UltReadyGlow", "path": "slot.padding", "value": None}))
    assert "padding" not in widget(out2, "UltReadyGlow")["slot"]


@pytest.mark.parametrize("path", ["id", "type", "parent", "slot.kind"])
def test_set_forbidden_paths(path):
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "set", "widget": "UltArea", "path": path, "value": "x"}))
    assert e.value.code == "BAD_OP"


def test_add_widget_at_index_sets_sibling_order():
    out = apply_patch(fixture_spec(), P({"op": "add_widget", "index": 0, "widget": {
        "id": "ChainIcon", "type": "Spacer", "parent": "ChainBox", "slot": {"kind": "vertical_box"}}}))
    kids = S.children_map(out)["ChainBox"]
    assert kids == ["ChainIcon", "ChainTitleText", "ChainTimerText", "ChainCountText"]


def test_add_duplicate_and_missing_parent():
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "add_widget", "widget": {"id": "UltGauge", "type": "Spacer", "parent": "Root"}}))
    assert e.value.code == "DUPLICATE_ID"
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "add_widget", "widget": {"id": "New", "type": "Spacer", "parent": "Ghost"}}))
    assert e.value.code == "NOT_FOUND"


def test_remove_unbound_ok_bound_refused():
    out = apply_patch(fixture_spec(), P({"op": "remove_widget", "widget": "ChainTitleText"}))
    assert "ChainTitleText" not in S.widget_index(out)
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "remove_widget", "widget": "UltGauge"}))
    assert e.value.code == "BINDING_REMOVAL"
    with pytest.raises(PatchError) as e:   # 묶인 자손이 있는 부모
        apply_patch(fixture_spec(), P({"op": "remove_widget", "widget": "UltArea"}))
    assert e.value.code == "BINDING_REMOVAL"


def test_clearing_binding_refused_adding_allowed():
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "set", "widget": "UltGauge", "path": "binding", "value": None}))
    assert e.value.code == "BINDING_REMOVAL"
    out = apply_patch(fixture_spec(), P({"op": "set", "widget": "ChainTitleText", "path": "binding",
                                         "value": {"data": "chain_title", "kind": "text"}}))
    assert widget(out, "ChainTitleText")["binding"]["data"] == "chain_title"


def test_move_cycle_and_slot_reset():
    with pytest.raises(PatchError) as e:
        apply_patch(fixture_spec(), P({"op": "move", "widget": "ChainPanel", "parent": "ChainBox"}))
    assert e.value.code == "CYCLE"
    out = apply_patch(fixture_spec(), P({"op": "move", "widget": "ChainCountText", "parent": "BurstRow", "index": 1}))
    w = widget(out, "ChainCountText")
    assert w["parent"] == "BurstRow" and w["slot"] == {"kind": "horizontal_box"}
    assert S.children_map(out)["BurstRow"] == ["BurstLabelText", "ChainCountText", "BurstCountText"]


def test_locked_refused():
    s = fixture_spec()
    s["locked"] = ["UltArea"]
    with pytest.raises(PatchError) as e:
        apply_patch(s, P({"op": "set", "widget": "UltArea", "path": "slot.position", "value": [0, 0]}))
    assert e.value.code == "LOCKED"
    with pytest.raises(PatchError) as e:   # 잠긴 부모 아래로 추가
        apply_patch(s, P({"op": "add_widget", "widget": {"id": "New", "type": "Spacer", "parent": "UltArea"}}))
    assert e.value.code == "LOCKED"


def test_atomic_on_later_failure():
    s = fixture_spec()
    before = copy.deepcopy(s)
    with pytest.raises(PatchError) as e:
        apply_patch(s, P({"op": "set", "widget": "UltArea", "path": "slot.position", "value": [0, 0]},
                         {"op": "remove_widget", "widget": "UltGauge"}))
    assert e.value.index == 1
    assert s == before


def test_invalid_result_refused():
    with pytest.raises(PatchError) as e:   # Border 는 자식 하나
        apply_patch(fixture_spec(), P({"op": "add_widget", "widget": {"id": "Second", "type": "Spacer", "parent": "ChainPanel"}}))
    assert e.value.code == "INVALID_RESULT"
    assert any("TOO_MANY_CHILDREN" in x for x in e.value.details["errors"])


def test_replace_asset():
    out = apply_patch(fixture_spec(), P({"op": "replace_asset", "asset": "ult_glow", "regenerate": True,
                                         "procedural": {"shape": "soft_glow", "color": "#FFAA00", "falloff": 0.4}}))
    assert next(a for a in out["assets"] if a["asset_id"] == "ult_glow")["procedural"]["falloff"] == 0.4
    with pytest.raises(PatchError):
        apply_patch(fixture_spec(), P({"op": "replace_asset", "asset": "nope"}))


def test_branch_for_precedence():
    layout = {"op": "set", "widget": "UltArea", "path": "slot.position", "value": [0, 0]}
    asset = {"op": "replace_asset", "asset": "ult_glow", "regenerate": True}
    bind = {"op": "set", "widget": "ChainTitleText", "path": "binding", "value": {"data": "x", "kind": "text"}}
    add_bound = {"op": "add_widget", "widget": {"id": "N", "type": "TextBlock", "parent": "Root", "binding": {"data": "n", "kind": "text"}}}
    assert branch_for(P(layout)) == "build"
    assert branch_for(P(layout, asset)) == "generate"
    assert branch_for(P(asset, bind)) == "codegen"
    assert branch_for(P(add_bound)) == "codegen"
    assert regenerate_assets(P(layout, asset)) == ["ult_glow"]
