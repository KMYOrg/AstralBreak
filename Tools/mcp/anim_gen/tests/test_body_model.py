"""Phase 8-4a — body_model(C++ body_clearance model 읽기 · FK · LBS · 반경 지도 조회 · 쌍 통계 · 대조) 테스트. 합성 모델은 model_fixture."""
from __future__ import annotations

import base64
import copy
import math
import struct

import pytest

import model_fixture as mf
from anim_gen import body_model as bm


def _close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.fixture
def model():
    return bm.BodyModel(mf.make_model())


def test_decode_matches_the_cpp_layout():
    assert bm.decode_f32(mf.f32([1.5, -2.25])) == [1.5, -2.25]
    # int16 LE 0.01 cm, −32768 = 빈 칸(−1) — C++ EncodeI16 와 같은 값
    raw = base64.b64encode(struct.pack("<4h", 123, -32768, 32767, 0)).decode()
    assert bm.decode_i16(raw, 0.01) == pytest.approx([1.23, -1.0, 327.67, 0.0])


def test_quaternion_helpers_round_trip():
    v = (10.0, -20.0, 35.0)
    q = bm.from_rotvec_deg(v)
    assert _close(bm.to_rotvec_deg(q), v, 1e-9)
    assert bm.from_rotvec_deg((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0, 1.0)
    # 위(+Z) 축 90° — +X → +Y (UE FQuat::RotateVector 와 같은 오른손 규칙)
    assert _close(bm.qrot(bm.from_rotvec_deg((0.0, 0.0, 90.0)), (1.0, 0.0, 0.0)), (0.0, 1.0, 0.0), 1e-12)
    # a ⊗ b = b 먼저
    a, b = bm.from_rotvec_deg((0.0, 0.0, 90.0)), bm.from_rotvec_deg((90.0, 0.0, 0.0))
    assert _close(bm.qrot(bm.qmul(a, b), (0.0, 1.0, 0.0)), bm.qrot(a, bm.qrot(b, (0.0, 1.0, 0.0))), 1e-12)


def test_version_and_shape_are_checked():
    raw = mf.make_model()
    raw["version"] = 2
    with pytest.raises(bm.ModelError):
        bm.BodyModel(raw)
    raw = mf.make_model()
    raw["poses"]["b64"] = mf.f32([0.0] * 10)
    with pytest.raises(bm.ModelError):
        bm.BodyModel(raw)


def test_fk_round_trip_reproduces_the_exported_component_pose(model):
    for f in range(len(model.frames)):
        rebuilt = model.component_from_local(model.local_pose(f))
        for got, want in zip(rebuilt, model.poses[f]):
            assert _close(got[1], want[1], 1e-3) and _close(got[0], want[0], 1e-5)


def test_skin_with_the_exported_pose_is_the_point_position(model):
    hand = next(p for p in model.points if p["side"] == "l" and p["part"] == "hand")
    assert _close(model.skin(model.poses[0], hand), mf.rest_position("hand_l"), 1e-4)
    assert _close(model.skin(model.poses[0], hand), hand["ref"], 1e-4)
    # 20° 프레임 — 위팔 길이 52 cm 를 앞 축 둘레로: 손 x = 18 − 52 sin 20°
    moved = model.skin(model.poses[1], hand)
    assert moved[0] == pytest.approx(18.0 - 52.0 * math.sin(math.radians(20.0)), abs=1e-3)


def test_map_depth_sign_neighbour_and_range(model):
    torso = model.maps["torso"]
    # 반경 10 원통 — 축에서 6 cm 안 = +4, 15 cm 밖 = −5
    d, _ = torso.depth(0, (6.0, 0.0, 120.0))
    assert d == pytest.approx(4.0, abs=0.01)
    d, _ = torso.depth(0, (0.0, 15.0, 120.0))
    assert d == pytest.approx(-5.0, abs=0.01)
    # 빈 칸은 이웃 3×3 최대
    t_bin, a_bin = mf.HOLE
    t = -0.25 + (t_bin + 0.5) / 40 * 1.3
    angle = -math.pi + (a_bin + 0.5) * 2 * math.pi / 36
    p = (8.0 * math.cos(angle), 8.0 * math.sin(angle), 95.0 + 50.0 * t)
    assert torso.locate(0, p)[:2] == (t_bin, a_bin)
    assert torso.depth(0, p)[0] == pytest.approx(2.0, abs=0.01)
    # 축 위 t 범위 밖 · 축 없는 지도
    assert torso.depth(0, (0.0, 0.0, 200.0)) is None
    assert model.maps["thigh_l"].depth(0, (0.0, 0.0, 50.0)) is None
    # min_t — 칸 가운데 t 가 그보다 작으면 안 본다
    assert torso.depth(0, (6.0, 0.0, 96.0), min_t=0.2) is None


def test_torso_parts_follow_the_t_bounds(model):
    torso = model.maps["torso"]
    for z, part in ((96.0, "pelvis"), (110.0, "belly"), (130.0, "chest")):
        t_bin = torso.locate(0, (1.0, 0.0, z))[0]
        assert model.torso_part(t_bin) == part
        assert torso.part_of_t_bin[t_bin] == part   # C++ 가 내보낸 칸 이름과 같다


def test_pair_depths_follow_the_arm(model):
    rest, inward = model.pair_depths(0), model.pair_depths(1)
    # 손이 몸통 옆(축에서 18 cm) → 반경 10 지도에서 −8 cm(틈), 20° 들어오면 축 0.2 cm 앞 → +9.8 cm(관통)
    assert rest[("l", "hand", "pelvis")] == pytest.approx(-8.0, abs=0.01)
    assert inward[("l", "hand", "pelvis")] == pytest.approx(10.0 - abs(18.0 - 52.0 * math.sin(math.radians(20.0))), abs=0.01)
    assert ("l", "hand", "thigh_l") not in rest          # 축 없는 지도는 쌍이 비었다
    assert rest[("r", "hand", "pelvis")] == pytest.approx(-8.0, abs=0.01)


def test_apply_deltas_moves_only_the_bone_and_its_children(model):
    hand = next(p for p in model.points if p["side"] == "l" and p["part"] == "hand")
    right = next(p for p in model.points if p["side"] == "r" and p["part"] == "hand")
    pose = model.apply_deltas(0, {"upperarm_l": ((0.0, 20.0, 0.0), None)})
    # 델타 20° = 프레임 1 의 포즈
    assert _close(model.skin(pose, hand), model.skin(model.poses[1], hand), 1e-3)
    i = model.index
    assert _close(pose[i["upperarm_l"]][1], model.poses[0][i["upperarm_l"]][1], 1e-6)       # 관절 그대로
    for bone in ("root", "pelvis", "spine_05", "upperarm_r", "hand_r"):
        assert _close(pose[i[bone]][1], model.poses[0][i[bone]][1], 1e-6)
    assert _close(model.skin(pose, right), model.skin(model.poses[0], right), 1e-6)
    # 이동 — 골반을 5 cm 내리면 모든 자손이 같이
    lowered = model.apply_deltas(0, {"pelvis": (None, (0.0, 0.0, -5.0))})
    assert model.skin(lowered, hand)[2] == pytest.approx(model.skin(model.poses[0], hand)[2] - 5.0, abs=1e-4)
    # 0 델타 = 원래 포즈(FK 왕복 오차만)
    same = model.apply_deltas(2, {"upperarm_l": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))})
    assert _close(model.skin(same, hand), model.skin(model.poses[2], hand), 1e-3)


def test_pair_stats_match_the_cpp_definition():
    s = bm.pair_stats([None, -3.0, 0.5, 2.5, 4.0], contact_cm=1.0, penetration_cm=2.0)
    assert s["frames_over_contact_pct"] == 40.0 and s["frames_over_penetration_pct"] == 40.0
    assert s["depth_max"] == 4.0 and s["located_pct"] == 80.0
    assert s["depth_p50"] == 0.5 and s["depth_p95"] == pytest.approx(3.7, abs=0.01)   # [0, 0, 0.5, 2.5, 4.0] 선형 보간
    assert bm.percentile([], 50.0) == 0.0


def test_compare_with_cpp_per_frame(model):
    series = model.series()
    per_frame = mf.per_frame_from(model.raw, series)
    same = bm.compare(model, per_frame, series)
    assert same["diff_max"] <= 0.001 and same["located_mismatch"] == 0 and same["penetration_pct_equal"]
    bad = copy.deepcopy(per_frame)
    item = next(s for s in bad["series"] if (s["side"], s["arm_part"], s["body_part"]) == ("l", "hand", "pelvis"))
    item["depth"][1] = item["depth"][1] - 9.0
    other = bm.compare(model, bad, series)
    assert other["diff_max"] == pytest.approx(9.0, abs=0.01) and not other["penetration_pct_equal"]
    assert other["pairs"]["l|hand|pelvis"]["penetration_pct"][0] != other["pairs"]["l|hand|pelvis"]["penetration_pct"][1]


def test_leg_pairs_use_the_opposite_leg_and_the_thigh_t_min():
    raw = mf.make_model()
    # 왼 넓적다리 점 하나 · 오른 넓적다리 지도(엉덩 (−9,0,92) → 무릎 (−9,0,50), 반경 8)
    axis = []
    for _ in raw["frames"]:
        axis += [-9.0, 0.0, 92.0, 0.0, 0.0, -1.0, 1.0, 0.0, 0.0, 42.0]
    raw["maps"][2] = {"part": "thigh_r", "t_min": -0.15, "t_max": 1.0, "t_bins": 30, "angle_bins": 36, "axis_b64": mf.f32(axis),
                      "radius_unit_cm": 0.01, "radius_b64": mf.i16([8.0] * (30 * 36) * len(raw["frames"]))}
    pelvis = mf.BONES.index("pelvis")
    raw["points"].append({"side": "l", "part": "thigh", "dominant": pelvis, "ref_cm": [-3.0, 0.0, 70.0], "influences": [[pelvis, 1.0, -3.0, 0.0, -25.0]]})
    raw["points"].append({"side": "l", "part": "thigh", "dominant": pelvis, "ref_cm": [-3.0, 0.0, 91.0], "influences": [[pelvis, 1.0, -3.0, 0.0, -4.0]]})
    model = bm.BodyModel(raw)
    d = model.pair_depths(0)
    # 70 cm 점: t ≈ 0.52 → 축에서 6 cm → +2. 91 cm 점(t ≈ 0.02 — 사타구니 쪽)은 leg_thigh_t_min 0.2 아래라 안 본다
    assert d[("l", "thigh", "thigh_r")] == pytest.approx(2.0, abs=0.01)
    series = model.series()
    assert ("l", "thigh", "thigh_r") in series and ("r", "calf", "calf_l") in series


def test_hand_pairs_probe_the_other_arm_maps():
    """8-4b hands — 손 · 아래팔 지도가 있으면 팔 점 × 반대 팔 지도(C++ parts.hands 와 같은 키). 지도는 원래 포즈 그대로 = body_fit.measure(기준 본이
    안 움직인 포즈)와 같은 값."""
    import body_fit_fixture as fx
    from anim_gen import body_fit as bf
    # 오른손을 왼손 쪽으로 — 위팔을 앞 축 둘레로 돌려 오른 손 · 아래팔이 몸 앞을 가로질러 왼손 지도에 들어간다
    frames = [{}, fx.grip_front({"upperarm_r": (60.0, 0.0, -40.0)})]
    model = bm.BodyModel(fx.make_model(frames))
    assert model.has_hands() and not bm.BodyModel(fx.make_model(frames, hands=False)).has_hands()
    series = model.series()
    assert ("r", "hand", "hand_l") in series and ("l", "upper_arm", "forearm_r") in series
    assert len([k for k in series if k[2].startswith(("hand_", "forearm_"))]) == 12
    measured = bf.measure(model)["series"]
    for key, values in series.items():
        if key in measured:
            assert all((a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9) for a, b in zip(values, measured[key])), key
    rest = [vs[0] for k, vs in series.items() if k[2].startswith(("hand_", "forearm_")) and vs[0] is not None]
    assert rest and max(rest) < -20.0           # 내려뜨린 두 손은 서로 떨어져 있다(음수 틈)
    assert series[("r", "hand", "forearm_l")][1] > 2.0   # 가로지른 오른손이 왼 아래팔 지도 안


# ---- FakeEditor 흉내 (Phase 8-4a — anim_gen 코드가 에디터 없이 부르는 모양) ----
def test_fake_editor_profile_rotations_and_body_model(fake):
    from conftest import ATTACK3, VESPER
    ed = fake.client()
    item = ed.require("validate_animation", assets=[ATTACK3], skeleton=VESPER, profile_bones=["hand_r", "hand_l"], profile_positions=True,
                      profile_rotations=True)["assets"][0]
    prof = item["numeric"]["profile"]
    assert len(prof["rotations"]["hand_r"]) == len(prof["times"]) == len(prof["position_cm"]["hand_r"])
    item = ed.require("validate_animation", assets=[ATTACK3], body_clearance={"mesh": "/Game/M", "parts": "all", "per_frame": True, "model": True})["assets"][0]
    bc = item["body_clearance"]
    model = bm.BodyModel(bc["model"])
    assert bm.compare(model, bc["per_frame"])["diff_max"] <= 0.001
    assert any(p["body_part"] == "pelvis" for p in bc["parts"]["pairs"])
    plain = ed.require("validate_animation", assets=[ATTACK3], body_clearance=True)["assets"][0]["body_clearance"]
    assert "parts" not in plain and "model" not in plain      # 옵트인 — 기본 결과에는 없다
    # 8-4b hands — 받아서 parts.hands 로(이 합성 모델엔 손 지도가 없어 빈 쌍), 없으면 parts.hands 도 없다
    hands = ed.require("validate_animation", assets=[ATTACK3], body_clearance={"parts": "all", "hands": True})["assets"][0]["body_clearance"]
    assert hands["parts"]["hands"] == {"pairs": []} and "hands" not in bc["parts"]


def test_fake_editor_bone_deltas_checks_the_key_count(fake):
    from conftest import ATTACK3, OUT
    from anim_gen.editor import EditorCallError
    ed = fake.client()
    keys = int(round(1.6 * 60.0)) + 1   # ATTACK3 — 1.6초 · 60 fps
    good = {"op": "bone_deltas", "space": "parent", "bones": [{"bone": "upperarm_l", "rotation_deg": [[0.0, 0.0, 0.0]] * keys}]}
    res = ed.require("apply_animation_edits", source=ATTACK3, asset_path=f"{OUT}/AS_Deltas", operations=[good])
    assert res["length"] == 1.6
    short = {"op": "bone_deltas", "bones": [{"bone": "upperarm_l", "rotation_deg": [[0.0, 0.0, 0.0]] * (keys - 1)}]}
    with pytest.raises(EditorCallError) as caught:
        ed.require("apply_animation_edits", source=ATTACK3, asset_path=f"{OUT}/AS_Short", operations=[short])
    assert caught.value.code == "BAD_REQUEST" and caught.value.details["planned"][0]["error"]["code"] == "BAD_OP"
    assert f"{OUT}/AS_Short" not in fake.assets
