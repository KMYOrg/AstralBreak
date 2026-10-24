"""BVH 헤더 · 단위 추정 · 정면 방향 · 축 변환 (지침서 §14 Phase 4) — Blender 없이 돈다."""
from __future__ import annotations

import pytest

from anim_gen import bvh
from conftest import make_bvh


def write(tmp_path, text: str, name: str = "clip.bvh"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_read_header_and_summary(tmp_path):
    info = bvh.read(write(tmp_path, make_bvh(frames=121)))
    assert [j.name for j in info.joints][:5] == ["Hips", "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"]
    assert len(info.joints) == 11 and info.channel_count == 36 and info.frames == info.rows == 121
    assert info.fps == pytest.approx(120.0, rel=1e-4) and info.duration == pytest.approx(1.0, rel=1e-4)
    s = bvh.summary(info)
    assert s["root"] == "Hips" and s["end_sites"] == 3 and s["joints"][1] == {"name": "LeftUpLeg", "parent": "Hips"}
    assert s["warnings"] == []


@pytest.mark.parametrize("text, reason", [
    ("HIERARCHY\nROOT A\n{\nOFFSET 0 0 0\nCHANNELS 3 Xposition Yposition Zposition\n}\n", "NO_MOTION"),
    (make_bvh(frames=5, rows=3), "TRUNCATED"),
    (make_bvh().replace("Frames: 3", "Frames: x"), "BAD_MOTION_HEADER"),
    (make_bvh().replace("Frame Time: 0.00833333", "Frame Time: 0"), "BAD_MOTION_HEADER"),
    (make_bvh(extra="JOINT Spine\n{\nOFFSET 0 1 0\nCHANNELS 3 Zrotation Xrotation Yrotation\n}\n"), "DUPLICATE_JOINT"),
    (make_bvh() + "", "OK"),
    ("FOO\nMOTION\nFrames: 1\nFrame Time: 0.1\n0\n", "NO_HIERARCHY"),
    (make_bvh().replace("OFFSET 0 0 0\nCHANNELS 6", "OFFSET 0 zero 0\nCHANNELS 6"), "BAD_HIERARCHY"),
])
def test_read_errors(tmp_path, text, reason):
    path = write(tmp_path, text)
    if reason == "OK":
        assert bvh.read(path).frames == 3
        return
    with pytest.raises(bvh.BvhError) as exc:
        bvh.read(path)
    assert exc.value.reason == reason


def test_bad_row_and_multiple_roots(tmp_path):
    text = make_bvh().replace("\n0 0 0 0", "\n0 0 0", 1)
    with pytest.raises(bvh.BvhError) as exc:
        bvh.read(write(tmp_path, text))
    assert exc.value.reason == "BAD_ROW" and exc.value.details["channels"] == 36
    two = make_bvh().replace("MOTION", "ROOT Other\n{\nOFFSET 0 0 0\nCHANNELS 3 Xposition Yposition Zposition\n}\nMOTION")
    with pytest.raises(bvh.BvhError) as exc:
        bvh.read(write(tmp_path, two, "two.bvh"))
    assert exc.value.reason == "MULTIPLE_ROOTS"


def test_warnings(tmp_path):
    extra = "JOINT ns:Tail\n{\nOFFSET 0 -5 -5\nCHANNELS 3 Xposition Yposition Zposition\n}\n"
    info = bvh.read(write(tmp_path, make_bvh(extra=extra, rows=4)))
    codes = {w["code"]: w for w in info.warnings}
    assert codes["JOINT_POSITION_CHANNELS"]["joints"] == ["ns:Tail"]
    assert codes["NAMESPACED_NAMES"]["joints"] == ["ns:Tail"] and "EXTRA_ROWS" in codes


@pytest.mark.parametrize("scale, mode, factor, normalized", [
    (1.0, "auto:cm", 1.0, False),
    (0.01, "auto:m", 100.0, False),
    (1 / 2.54, "auto:inch", 2.54, False),
    (10.0, "auto:mm", 0.1, False),
    (30 / 183, "auto:normalized", 170 / 30, True),
])
def test_unit_auto(tmp_path, scale, mode, factor, normalized):
    info = bvh.read(write(tmp_path, make_bvh(scale=scale)))
    unit = bvh.resolve_unit("auto", bvh.height(bvh.rest_segments(info)))
    assert unit["mode"] == mode and unit["cm_per_unit"] == pytest.approx(factor, rel=1e-4) and unit["normalized"] is normalized
    if not normalized:
        assert 120 <= unit["rest_height_cm"] <= 230
    else:
        assert unit["rest_height_cm"] == pytest.approx(170.0, abs=0.1)


def test_unit_explicit_and_bad():
    assert bvh.resolve_unit("m", 1.8)["cm_per_unit"] == 100.0
    assert bvh.resolve_unit(5.644, 30.0) == {"mode": "explicit", "cm_per_unit": 5.644, "normalized": False, "rest_height_units": 30.0,
                                             "rest_height_cm": 169.32}
    for bad in ("km", -1, 0, True):
        with pytest.raises(bvh.BvhError):
            bvh.resolve_unit(bad, 30.0)


@pytest.mark.parametrize("toe, axis", [
    ((0.0, -8.0, 12.0), "+Y"),   # BVH +Z → Blender -Y → UE +Y
    ((0.0, -8.0, -12.0), "-Y"),
    ((12.0, -8.0, 0.0), "+X"),
    ((-12.0, -8.0, 0.0), "-X"),
    ((3.0, -8.0, 12.0), "+Y"),   # 14° 기울어도 같은 축
])
def test_facing_from_feet(tmp_path, toe, axis):
    info = bvh.read(write(tmp_path, make_bvh(toe=toe)))
    f = bvh.facing(bvh.rest_segments(info))
    assert f["axis"] == axis and f["deviation_deg"] < 30


def test_facing_off_axis_and_missing(tmp_path):
    info = bvh.read(write(tmp_path, make_bvh(toe=(12.0, -8.0, 12.0))))
    f = bvh.facing(bvh.rest_segments(info))
    assert f["axis"] is None and f["reason"] == "OFF_AXIS" and f["deviation_deg"] == pytest.approx(45.0, abs=0.1)
    flat = [((0, 0, 100), (0, 0, 160)), ((0, 0, 100), (0, 0, 0))]  # 발 영역에 선분이 없다
    assert bvh.facing(flat)["reason"] == "NO_FOOT_SEGMENTS"


def test_facing_of_ue_skeleton_cancels_symmetric_ik_bones():
    """UE 마네킹류: ik_foot_root(원점) → ik_foot_l/r 은 좌우로 상쇄되고 foot → ball 만 남는다."""
    def bone(name, parent, t):
        return {"name": name, "parent": parent, "ref_component": {"t": list(t), "r": [0, 0, 0]}}
    bones = [bone("root", None, (0, 0, 0)), bone("pelvis", "root", (0, 0, 95)), bone("head", "pelvis", (0, 0, 165)),
             bone("thigh_l", "pelvis", (10, 0, 90)), bone("calf_l", "thigh_l", (10, 0, 50)), bone("foot_l", "calf_l", (10, 2, 9)),
             bone("ball_l", "foot_l", (11, -12, 2)), bone("thigh_r", "pelvis", (-10, 0, 90)), bone("calf_r", "thigh_r", (-10, 0, 50)),
             bone("foot_r", "calf_r", (-10, 2, 9)), bone("ball_r", "foot_r", (-11, -12, 2)),
             bone("ik_foot_root", "root", (0, 0, 0)), bone("ik_foot_l", "ik_foot_root", (10, 2, 9)), bone("ik_foot_r", "ik_foot_root", (-10, 2, 9))]
    segments = bvh.skeleton_segments(bones)
    f = bvh.facing(segments)
    assert f["axis"] == "-Y" and bvh.height(segments) == 165


def _bone(name, parent, t):
    return {"name": name, "parent": parent, "ref_component": {"t": list(t), "r": [0, 0, 0]}}


# SB(3ds Max Biped) 축소판: 정면 +X · 왼쪽 −Y, FX 본 하나가 z −2217cm (실측 2026-10-24 — 예전 facing 은 발 선분 0개였다)
SB_BONES = [_bone("Root", None, (0, 0, 0)), _bone("Bip001-Pelvis", "Root", (1, 0, 99)), _bone("Bip001-Head", "Bip001-Pelvis", (0, 0, 152)),
            _bone("Bip001-L-Thigh", "Bip001-Pelvis", (1, -9, 99)), _bone("Bip001-L-Calf", "Bip001-L-Thigh", (0, -12, 55)),
            _bone("Bip001-L-Foot", "Bip001-L-Calf", (-5, -15, 15)), _bone("Bip001-L-Toe0", "Bip001-L-Foot", (-2.4, -15.3, 4)),
            _bone("Bip001-R-Thigh", "Bip001-Pelvis", (1, 9, 99)), _bone("Bip001-R-Calf", "Bip001-R-Thigh", (0, 12, 55)),
            _bone("Bip001-R-Foot", "Bip001-R-Calf", (-5, 15, 15)), _bone("Bip001-R-Toe0", "Bip001-R-Foot", (-2.4, 15.3, 4)),
            _bone("Bip001-L-UpperArm", "Bip001-Pelvis", (2, -15, 140)), _bone("Bip001-R-UpperArm", "Bip001-Pelvis", (2, 15, 140)),
            _bone("FX_GunFire_Rail_End", "Bip001-Pelvis", (300, 0, -2217))]
SB_CHAINS = [{"name": "LeftLeg", "start": "Bip001-L-Thigh", "end": "Bip001-L-Toe0"}, {"name": "RightLeg", "start": "Bip001-R-Thigh", "end": "Bip001-R-Toe0"},
             {"name": "LeftArm", "start": "Bip001-L-UpperArm", "end": "Bip001-L-UpperArm"},
             {"name": "RightArm", "start": "Bip001-R-UpperArm", "end": "Bip001-R-UpperArm"}, {"name": "Spine", "start": "Bip001-Pelvis", "end": "Bip001-Head"}]


def test_facing_ignores_outlier_bones():
    f = bvh.facing(bvh.skeleton_segments(SB_BONES))
    assert f["axis"] == "+X" and f["outliers"] == 1


def test_lateral_facing_from_left_right_chains():
    f = bvh.lateral_facing(bvh.bone_positions(SB_BONES), SB_CHAINS)
    assert f["axis"] == "+X" and f["pairs"] == ["LeftArm", "LeftLeg"]
    vesper = {"thigh_l": (9, -1, 102), "thigh_r": (-9, -1, 102)}  # 왼쪽 +X → 정면 +Y
    assert bvh.lateral_facing(vesper, [{"name": "LeftLeg", "start": "thigh_l"}, {"name": "RightLeg", "start": "thigh_r"}])["axis"] == "+Y"
    assert bvh.lateral_facing(vesper, [{"name": "Spine", "start": "thigh_l"}])["reason"] == "NO_LEFT_RIGHT_CHAINS"


@pytest.mark.parametrize("source, target, deg", [("+X", "+Y", 90.0), ("+Y", "+X", -90.0), ("+Y", "+Y", 0.0), ("-Y", "+Y", 180.0),
                                                 ("+Y", "-Y", 180.0), ("-X", "+Y", -90.0)])
def test_ue_yaw_is_fquat_sign(source, target, deg):
    """FQuat(UpVector, +90°) 는 +X 를 +Y 로 — Blender 회전(y 뒤집기)과 부호가 반대다."""
    assert bvh.ue_yaw_deg(source, target) == pytest.approx(deg)


@pytest.mark.parametrize("source, target, deg", [("+Y", "+Y", 0.0), ("+Y", "-Y", 180.0), ("-Y", "+Y", 180.0), ("+X", "-X", 180.0),
                                                 ("+X", "+Y", -90.0), ("+Y", "+X", 90.0), ("-X", "+Y", 90.0), ("-Y", "+X", -90.0)])
def test_blender_rotation(source, target, deg):
    assert bvh.blender_rotation_deg(source, target) == pytest.approx(deg)


def test_axis_matrix():
    assert bvh.axis_matrix("-Z", "Y") == ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))
    assert bvh.to_ue((0, 0, 1), bvh.axis_matrix("-Z", "Y")) == (0.0, 1.0, 0.0)   # BVH +Z → UE +Y
    assert bvh.to_ue((0, 1, 0), bvh.axis_matrix("-Z", "Y"))[2] == 1.0              # BVH 위 → UE 위
    assert bvh.to_ue((0, 0, 1), bvh.axis_matrix("Y", "Z"))[2] == 1.0               # Z-up BVH
    for bad in (("Y", "Y"), ("-Z", "W")):
        with pytest.raises(bvh.BvhError):
            bvh.axis_matrix(*bad)


@pytest.mark.parametrize("first, last, fps, rate, expect_last, trimmed", [
    (0, 2751, 120.0, 30, 2748, 3),     # CMU 01_01: 22.925초 × 30 = 687.75 → 끝 3프레임 당김
    (0, 120, 120.0, 30, 120, 0),       # 이미 경계
    (0, 2751, 120.0, 24, 2750, 1),     # 120 → 24: 5프레임 단위
    (10, 47, 30.0, 24, 45, 2),         # 30 → 24: gcd 6 → 5프레임 단위
    (0, 99, 120.0, 120, 99, 0),        # 같은 rate
])
def test_align_to_rate(first, last, fps, rate, expect_last, trimmed):
    out = bvh.align_to_rate({"first": first, "last": last, "frames": last - first + 1, "duration": (last - first) / fps}, fps, rate)
    assert out["last"] == expect_last and out["trimmed_frames"] == trimmed and not out["unaligned"]
    assert ((out["last"] - first) * rate / fps).is_integer()


def test_align_to_rate_unaligned_and_too_short():
    frames = {"first": 0, "last": 100, "frames": 101, "duration": 1.0}
    assert bvh.align_to_rate(frames, 120.0048, 30)["unaligned"] is True and bvh.align_to_rate(frames, 120.0, None)["aligned_to"] is None
    with pytest.raises(bvh.BvhError) as exc:
        bvh.align_to_rate({"first": 0, "last": 2, "frames": 3, "duration": 0.0167}, 120.0, 30)
    assert exc.value.reason == "BAD_RANGE"


def test_frame_range(tmp_path):
    info = bvh.read(write(tmp_path, make_bvh(frames=241)))  # 2초
    assert bvh.frame_range(info, None) == {"first": 0, "last": 240, "frames": 241, "duration": 2.0}
    assert bvh.frame_range(info, {"start": 0.5, "end": 1.0}) == {"first": 60, "last": 120, "frames": 61, "duration": 0.5}
    assert bvh.frame_range(info, {"start": 1.5, "end": 9.0})["last"] == 240
    for bad in ({"start": 1.0, "end": 0.5}, {"start": -1, "end": 1}, {"start": 2.5, "end": 3.0}, {"start": "0", "end": 1}):
        with pytest.raises(bvh.BvhError):
            bvh.frame_range(info, bad)
