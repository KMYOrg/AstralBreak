"""결정적 fixer · 결함 주입 — 합성 geometry 로."""
from __future__ import annotations

import pytest
from conftest import fixture_spec, widget
from test_geometry import GATES, STACK, fixture_geometry

from core import patch as patch_mod
from stages import StageError, fault, verify
from stages.fix import propose_deterministic


def renders_for(spec):
    return [{"resolution": list(r), "geometry": fixture_geometry(spec, r)} for r in ((1920, 1080), (2560, 1080), (1920, 1200))]


def gates_for(spec):
    gates, _ = verify.render_gates(spec, renders_for(spec), [1920, 1080], GATES, STACK)
    return gates


@pytest.mark.parametrize("name, failing, target", [
    ("offscreen", {"offscreen", "iou_region", "iou_leaf"}, "UltArea"),
    ("overlap", {"overlap", "iou_region"}, "UltBlockedText"),
    ("drift", {"iou_region", "iou_leaf"}, "ChainPanel"),
])
def test_fault_then_fix_restores_the_hand_spec(name, failing, target):
    good = fixture_spec()
    broken = patch_mod.apply_patch(good, fault.fault_patch(name, good))
    gates = gates_for(broken)
    assert {g["name"] for g in gates if not g["pass"]} == failing
    fixes, ops = propose_deterministic(broken, gates, fixture_geometry(broken))
    assert ops and {op["widget"] for op in ops} == {target} and all(op["path"] == "slot.position" for op in ops)
    assert all("suggested_op" in f for f in fixes if f["widget"] == target)
    # offscreen 은 컬링(geometry 0) — 측정값 대신 bbox_intent · 앵커로 계산(1a-4 실측: 0 을 측정값으로 쓰면 크기가 두 배가 됐다)
    assert ("not painted" in ops[0]["reason"]) == (name == "offscreen")
    fixed = patch_mod.apply_patch(broken, {"schema_version": 1, "source": "fix", "ops": ops})
    assert widget(fixed, target)["slot"] == widget(good, target)["slot"]
    assert all(g["pass"] for g in gates_for(fixed))
    assert patch_mod.branch_for({"ops": ops}) == "build"


def test_fault_targets_are_generic():
    s = fixture_spec()
    regs = [r["id"] for r in fault.regions(s)]
    assert regs == ["UltArea", "UltBlockedText", "ChainPanel", "BurstBanner"]
    assert fault.fault_patch("overlap", s)["ops"][0]["value"] == [0, -70]          # 작은 쪽(UltBlockedText)을 UltArea 중심으로
    assert fault.fault_patch("offscreen", s)["ops"][0]["value"] == [1920, -64]
    assert fault.fault_patch("drift", s)["ops"][0]["value"] == [-113, 140]
    with pytest.raises(StageError) as e:
        fault.fault_patch("nope", s)
    assert e.value.code == "FAULT_UNKNOWN"


def test_size_and_alignment_are_compensated():
    good = fixture_spec()
    broken = patch_mod.apply_patch(good, {"schema_version": 1, "source": "fault", "ops": [
        {"op": "set", "widget": "BurstBanner", "path": "slot.size", "value": [300, 60]},
        {"op": "set", "widget": "BurstBanner", "path": "slot.position", "value": [17, 120]}]})
    gates = gates_for(broken)
    _, ops = propose_deterministic(broken, gates, fixture_geometry(broken))
    fixed = patch_mod.apply_patch(broken, {"schema_version": 1, "source": "fix", "ops": ops})
    assert widget(fixed, "BurstBanner")["slot"]["size"] == [420, 72] and widget(fixed, "BurstBanner")["slot"]["position"] == [0, 96]


def test_inside_failure_and_stretch_anchor_give_no_op():
    spec = fixture_spec()
    geom = fixture_geometry(spec)
    for g in geom:
        if g["id"] == "ChainTimerText":
            g["y"] += 20                                  # 영역은 제자리, 안쪽 칸만 어긋남
    gates, _ = verify.render_gates(spec, [{"resolution": [1920, 1080], "geometry": geom}], [1920, 1080], GATES, STACK)
    fixes, ops = propose_deterministic(spec, gates, geom)
    assert not ops and any("inside" in f["problem"] for f in fixes)

    spec2 = fixture_spec()
    widget(spec2, "ChainPanel")["slot"]["anchors"] = [0.8, 0, 1, 0]
    geom2 = fixture_geometry(fixture_spec())
    for g in geom2:
        if g["id"] == "ChainPanel":
            g["x"] -= 65
    gates2, _ = verify.render_gates(spec2, [{"resolution": [1920, 1080], "geometry": geom2}], [1920, 1080], GATES, STACK)
    fixes2, ops2 = propose_deterministic(spec2, gates2, geom2)
    assert not ops2 and any("stretch" in f["problem"] for f in fixes2)


def test_intent_overlap_is_reported_not_moved():
    spec = fixture_spec()
    widget(spec, "UltBlockedText")["bbox_intent"] = [840, 980, 240, 32]        # 의도 자체가 UltArea 와 겹침
    widget(spec, "UltBlockedText")["slot"]["position"] = [0, -68]
    gates = gates_for(spec)
    assert [g["name"] for g in gates if not g["pass"]] == ["overlap"]
    fixes, ops = propose_deterministic(spec, gates, fixture_geometry(spec))
    assert not ops and any("allow_overlap" in f.get("evidence", "") for f in fixes)


def test_texture_mismatch_regenerates_and_other_gates_have_no_fix():
    spec = fixture_spec()
    gates = [verify.gate("texture_settings", False, details={"mismatches": [{"asset_id": "ult_glow", "diff": {"srgb": {"want": True, "got": False}}}]}),
             verify.gate("compile", False, details={"status": "error"}), verify.gate("roundtrip", False, details={"diffs": ["x"]})]
    fixes, ops = propose_deterministic(spec, gates, fixture_geometry(spec))
    assert ops == [{"op": "replace_asset", "asset": "ult_glow", "regenerate": True, "reason": ops[0]["reason"]}]
    assert patch_mod.branch_for({"ops": ops}) == "generate" and patch_mod.regenerate_assets({"ops": ops}) == ["ult_glow"]
    assert {f["gate"] for f in fixes} == {"texture_settings", "compile", "roundtrip"}
