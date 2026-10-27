"""blender 보정 op(fix.ops — smooth · stance_width · foot_lock) — 지침서 §14 Phase 8 '8-3'.

순수: op 사전(기본값 · 범위 · 순서 · 중복) · 다리 본(retarget 체인) · 접지 판정 · 다리 치수 사상(E0 수치로 확인) · 다리 풀이(접지 구간마다 상수 오프셋 →
디딘 발 안 미끄러짐 · 두 발 디딘 최대 간격 ≤ 상한 · 최소 간격 · 고정 한 점) · 다리 IK(먼저 엉덩 둘레로 돌려 무릎이 발을 따라 안으로).
계획 · 실행: SOMA BVH(motion_file) = local_ai 리타깃 기본값 · 다리 본 계획 고정 · 대상 다리 치수, 체인 없는 BVH = FIX_LEGS_UNKNOWN, args.json
(fix · fix_legs), 가짜 Blender 보고 → Job fix.source · 리타깃 뒤 대상 측정 → Job fix.target, 변환 없는 경로 = UNSUPPORTED_FIX_OP(그대로).
"""
from __future__ import annotations

import math

import pytest

from anim_gen import fix_ops, foot_fix
from anim_gen import motion_metrics as mm
from anim_gen.local_ai import refine
from anim_gen.soma import REQUIRED_JOINTS, SOMA_CHAINS
from conftest import _ROT
from test_blender import bl, bvh_request, generate, plan, status  # noqa: F401 — bl 는 픽스처

CMU_LEGS = [{"name": "LeftLeg", "start": "LeftUpLeg", "end": "LeftToeBase"}, {"name": "RightLeg", "start": "RightUpLeg", "end": "RightToeBase"}]
_SIX = "CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"


def soma_named_bvh(frames: int = 31) -> str:
    """SOMA77 이름(REQUIRED_JOINTS 전부)을 가진 합성 BVH — 다리는 Leg → Shin → Foot → ToeBase, 나머지 이름은 척추 아래 사슬."""
    def leg(side: str, x: float) -> str:
        return (f"JOINT {side}Leg\n{{\nOFFSET {x} -5 0\n{_ROT}\nJOINT {side}Shin\n{{\nOFFSET 0 -45 0\n{_ROT}\nJOINT {side}Foot\n{{\nOFFSET 0 -45 0\n"
                f"{_ROT}\nJOINT {side}ToeBase\n{{\nOFFSET 0 -5 12\n{_ROT}\n}}\n}}\n}}\n}}\n")
    legs = {f"{s}{p}" for s in ("Left", "Right") for p in ("Leg", "Shin", "Foot", "ToeBase")}
    rest = sorted(REQUIRED_JOINTS - legs - {"Hips"})
    chain = "".join(f"JOINT {n}\n{{\nOFFSET 0 1 0\n{_ROT}\n" for n in rest) + "}\n" * len(rest)
    body = f"HIERARCHY\nROOT Root\n{{\nOFFSET 0 0 0\n{_SIX}\nJOINT Hips\n{{\nOFFSET 0 100 0\n{_SIX}\n" + leg("Left", 10) + leg("Right", -10) + chain + "}\n}\n"
    channels = 12 + 3 * (len(rest) + 8)
    return f"{body}MOTION\nFrames: {frames}\nFrame Time: 0.03333333\n" + "\n".join([" ".join(["0"] * channels)] * frames) + "\n"


# ---- op 사전 ----
def test_ops_defaults_and_order():
    ops = [fix_ops.normalize_op({"op": "foot_lock"}), fix_ops.normalize_op({"op": "smooth", "sigma_frames": 2}, 1),
           fix_ops.normalize_op({"op": "stance_width"}, 2)]
    out, moved = fix_ops.ordered(ops)
    assert moved and [o["op"] for o in out] == ["smooth", "stance_width", "foot_lock"]
    assert out[1] == {"op": "stance_width", "max_ratio": 3.0, "min_ratio": 1.2, "max_shift_cm": 25.0, "blend_s": 0.2, "keep_knee_bend": True}
    assert out[2]["height_ratio"] == mm.CONTACT_HEIGHT_RATIO and out[2]["feet"] == ["left", "right"] and out[2]["lock_rotation"] is False
    assert out[0]["sigma_frames"] == 2.0


@pytest.mark.parametrize("raw, field", [
    ({"op": "smooth", "sigma": 1}, "fix.ops[0].sigma"),
    ({"op": "smooth", "sigma_frames": 9}, "fix.ops[0].sigma_frames"),
    ({"op": "smooth", "bones": []}, "fix.ops[0].bones"),
    ({"op": "smooth", "from_s": 2, "to_s": 1}, "fix.ops[0].from_s"),
    ({"op": "stance_width", "max_ratio": 0.5}, "fix.ops[0].max_ratio"),
    ({"op": "stance_width", "min_ratio": 4}, "fix.ops[0].min_ratio"),
    ({"op": "stance_width", "keep_knee_bend": "yes"}, "fix.ops[0].keep_knee_bend"),
    ({"op": "foot_lock", "feet": ["middle"]}, "fix.ops[0].feet"),
    ({"op": "foot_lock", "contacts": "labels"}, "fix.ops[0].contacts"),
    ({"op": "foot_lock", "min_frames": 2.5}, "fix.ops[0].min_frames"),
])
def test_ops_reject(raw, field):
    with pytest.raises(fix_ops.FixOpError) as info:
        fix_ops.normalize_op(raw)
    assert info.value.args[0] == field


def test_ops_duplicate():
    with pytest.raises(fix_ops.FixOpError):
        fix_ops.ordered([{"op": "foot_lock"}, {"op": "foot_lock"}])


def test_legs_from_chains():
    joints = [{"name": n, "parent": p} for n, p in [("Hips", None), ("LeftUpLeg", "Hips"), ("LeftLeg", "LeftUpLeg"), ("LeftFoot", "LeftLeg"),
                                                     ("LeftToeBase", "LeftFoot"), ("RightUpLeg", "Hips"), ("RightLeg", "RightUpLeg"),
                                                     ("RightFoot", "RightLeg"), ("RightToeBase", "RightFoot")]]
    legs = fix_ops.legs_from(joints, CMU_LEGS, None)
    assert legs == {"left": {"hip": "LeftUpLeg", "knee": "LeftLeg", "ankle": "LeftFoot"}, "right": {"hip": "RightUpLeg", "knee": "RightLeg", "ankle": "RightFoot"}}
    with pytest.raises(fix_ops.FixOpError):
        fix_ops.legs_from(joints, None, None)
    with pytest.raises(fix_ops.FixOpError):   # 발목을 엉덩 관절로 잘못 주면 2본 사슬이 아니다
        fix_ops.legs_from(joints, CMU_LEGS, ["LeftLeg", "RightLeg"])


# ---- 접지 · 치수 ----
def test_detect_contacts_low_and_slow():
    times = [i / 30 for i in range(30)]
    track = [[0.0, 0.0, 10.0]] * 10 + [[i * 3.0, 0.0, 30.0] for i in range(10)] + [[30.0, 0.0, 10.2]] * 10
    flags = mm.detect_contacts(track, times, 2, leg_cm=90.0)
    assert flags[:10] == [True] * 10 and not any(flags[10:20]) and flags[20:] == [True] * 10
    short = [[0.0, 0.0, 10.0]] * 3 + [[0.0, 0.0, 40.0]] * 27
    assert not any(mm.detect_contacts(short, times, 2, 90.0))   # 4 프레임 미만은 접지가 아니다


def test_stance_map_matches_e0():
    """E0(2026-10-27): SOMA 엉덩 폭 20.09 · 다리 85.58, Vesper 18.24 · 93.01 — 검 시험 대상 소스 p50 89.4 cm → Vesper 92.6 cm(실측)."""
    m = mm.stance_map({"hip_width_cm": 20.09, "leg_cm": 85.58}, {"hip_width_cm": 18.24, "leg_cm": 93.01})
    assert m["leg_ratio"] == pytest.approx(1.0868, abs=1e-4)
    assert mm.map_stance(m, 89.4, "target") == pytest.approx(92.6, abs=1.0)
    assert mm.map_stance(m, mm.map_stance(m, 54.7, "source"), "target") == pytest.approx(54.7, abs=1e-6)


def test_leg_dims_from_rest():
    rest = {"thigh_l": [9, 0, 100], "thigh_r": [-9, 0, 100], "calf_l": [9, 0, 55], "calf_r": [-9, 0, 55], "foot_l": [9, 0, 10], "foot_r": [-9, 0, 10]}
    roles = {"hip_l": "thigh_l", "hip_r": "thigh_r", "knee_l": "calf_l", "knee_r": "calf_r", "foot_l": "foot_l", "foot_r": "foot_r"}
    assert mm.leg_dims(rest, roles) == {"hip_width_cm": 18.0, "leg_cm": 90.0, "thigh_cm": 45.0, "shin_cm": 45.0}
    assert mm.leg_dims({**rest, "pelvis": [0, 0, 104]}, {**roles, "pelvis": "pelvis"})["pelvis_height_cm"] == 104.0
    assert mm.leg_dims(rest, {**roles, "knee_l": None}) is None


# ---- 다리 풀이 ----
def wide_stance(n=40, half=45.0, step_at=None):
    """엉덩 관절 ±10 cm, 발목 ±half(넓은 자세) — step_at = (시작, 끝)이면 그동안 왼발이 들려 앞으로 20 cm 옮긴다."""
    hip = {"left": [[10.0, 0.0, 95.0]] * n, "right": [[-10.0, 0.0, 95.0]] * n}
    left = []
    for f in range(n):
        if step_at and step_at[0] <= f <= step_at[1]:
            k = (f - step_at[0]) / (step_at[1] - step_at[0])
            left.append([half, 20.0 * k, 10.0 + 15.0 * math.sin(math.pi * k)])
        else:
            left.append([half, 20.0 if step_at and f > step_at[1] else 0.0, 10.0])
    ankle = {"left": left, "right": [[-half, 0.0, 10.0]] * n}
    times = [f / 30 for f in range(n)]
    contacts = {s: mm.detect_contacts(ankle[s], times, 2, 90.0) for s in ("left", "right")}
    return ankle, hip, contacts


def test_stance_reaches_the_cap_and_planted_feet_stay_put():
    ankle, hip, contacts = wide_stance(step_at=(12, 20))
    out = foot_fix.solve(ankle, hip, contacts, up=2, stance_cfg={"cap_cm": 50.0, "min_cm": 20.0, "max_shift_cm": 25.0, "blend_frames": 6})
    st = out["stance"]
    assert st["planted_max_cm"]["before"] == pytest.approx(90.0) and st["reached"] and st["planted_max_cm"]["after"] <= 50.5
    for side in ("left", "right"):
        for a, b in mm.runs(contacts[side]):
            pts = out["targets"][side][a:b + 1]
            assert max(mm._dist(p, pts[0]) for p in pts) < 1e-6   # 접지 구간 안에서 오프셋은 상수 — 디딘 발이 미끄러지지 않는다
    assert all(out["changed"]["left"]) and all(out["changed"]["right"])


def test_stance_keeps_the_minimum_gap():
    ankle, hip, contacts = wide_stance(half=45.0)
    out = foot_fix.solve(ankle, hip, contacts, up=2, stance_cfg={"cap_cm": 10.0, "min_cm": 30.0, "max_shift_cm": 50.0, "blend_frames": 6})
    assert out["stance"]["planted_min_cm"]["after"] >= 29.5 and not out["stance"]["reached"]


def test_narrow_stance_is_left_alone():
    ankle, hip, contacts = wide_stance(half=20.0)
    out = foot_fix.solve(ankle, hip, contacts, up=2, stance_cfg={"cap_cm": 50.0, "min_cm": 20.0, "max_shift_cm": 25.0, "blend_frames": 6})
    assert out["stance"]["multiplier"] == 1.0 and not any(out["changed"]["left"]) and not any(out["changed"]["right"])


def test_lock_pins_each_contact_to_one_point():
    ankle, hip, contacts = wide_stance(half=30.0)
    ankle["left"] = [[30.0 + 0.1 * f, 0.0, 10.0] for f in range(40)]   # 디딘 채 3 cm/s 미끄러짐
    contacts = {s: mm.detect_contacts(ankle[s], [f / 30 for f in range(40)], 2, 90.0) for s in ("left", "right")}
    out = foot_fix.solve(ankle, hip, contacts, up=2, lock_cfg={"feet": ["left"], "blend_frames": 3})
    pts = out["targets"]["left"]
    assert max(mm._dist(p, pts[0]) for p in pts) < 1e-6 and len(out["pins"]["left"]) == 1 and "right" not in out["pins"]
    assert not any(out["changed"]["right"])


def _fk(hip, r_thigh, r_shin, thigh_off, shin_off):
    knee = [hip[i] + refine._mv(r_thigh, thigh_off)[i] for i in range(3)]
    return knee, [knee[i] + refine._mv(r_shin, shin_off)[i] for i in range(3)]


def test_swing_ik_brings_the_knee_in_with_the_foot():
    """넓게 벌린 다리(무릎 약간 굽힘, 무릎은 다리 선보다 바깥) — 발목을 안으로 옮기면 무릎도 안으로 들어온다(원래 굽힘 평면만 쓰면 밖으로 빠진다)."""
    ident = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    hip, knee, ankle = [10.0, 0.0, 95.0], [33.0, 4.0, 52.0], [45.0, 0.0, 10.0]
    thigh_off, shin_off = [knee[i] - hip[i] for i in range(3)], [ankle[i] - knee[i] for i in range(3)]
    target = [25.0, 0.0, 10.0]
    res = foot_fix.swing_two_bone(hip, knee, ankle, ident, ident, target)
    k2, a2 = _fk(hip, res["r_arm"], res["r_fore"], thigh_off, shin_off)
    assert mm._dist(a2, target) < 1e-6 and not res["clamped"]
    assert mm._dist(k2, hip) == pytest.approx(mm._dist(knee, hip)) and mm._dist(a2, k2) == pytest.approx(mm._dist(ankle, knee))
    plain = refine.two_bone(hip, knee, ankle, ident, ident, target)
    assert k2[0] < knee[0] and k2[0] < plain["elbow"][0]   # 무릎 x(바깥쪽)가 원래보다 · 굽힘 평면 고정보다 안쪽


def test_target_model_predicts_the_retargeted_hips_and_legs():
    """대상 모델 = 리타기터 Pelvis Motion op(골반 위치 × s · 회전 변화) + FK(소스 뼈 방향 · 대상 길이). UE → Blender 축 (x, −y, z)."""
    target = {"hip_width_cm": 18.0, "thigh_cm": 45.0, "shin_cm": 48.0, "rest": {"pelvis": [0, 2, 105], "hip_l": [9, 2, 102], "hip_r": [-9, 2, 102]}}
    model = foot_fix.target_model([0.0, 0.0, 100.0], 2, target, axes=(1.0, -1.0, 1.0))
    assert model["scale"] == pytest.approx(1.05) and model["hip_offset"]["left"] == [9.0, 0.0, -3.0]
    ident = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert foot_fix.predict_hip(model, "left", [0.0, 10.0, 100.0], ident) == pytest.approx([9.0, 10.5, 102.0])
    yaw90 = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]   # 골반이 90° 돌면 엉덩 오프셋도 돈다
    assert foot_fix.predict_hip(model, "left", [0.0, 0.0, 100.0], yaw90) == pytest.approx([0.0, 9.0, 102.0])
    knee, ankle = foot_fix.target_leg([9.0, 0.0, 102.0], [10.0, 0.0, 95.0], [10.0, 0.0, 55.0], [10.0, 5.0, 15.0], model)
    assert knee == pytest.approx([9.0, 0.0, 57.0]) and mm._dist(knee, ankle) == pytest.approx(48.0)
    assert foot_fix.target_model([0.0, 0.0, 100.0], 2, {"thigh_cm": 45.0}) is None   # 기준 포즈가 없으면 소스 공간


def test_legs_report_counts_planted_frames():
    ankle, hip, contacts = wide_stance(half=45.0)
    times = [f / 30 for f in range(40)]
    rep = mm.legs_report({"foot_l": ankle["left"], "foot_r": ankle["right"], "hip_l": hip["left"], "hip_r": hip["right"]}, times, 2, 90.0)
    assert rep["ratio"]["p50"] == pytest.approx(4.5) and rep["ratio"]["planted_max"] == pytest.approx(4.5)
    assert rep["contact_pct"] == {"l": 100.0, "r": 100.0} and rep["slide_p95"] == {"l": 0.0, "r": 0.0}
    knees = ([[27.5, 0.0, 52.5]] * 40, [[-27.5, 0.0, 52.5]] * 40)   # 엉덩 · 발목의 가운데 — 곧은 다리
    rep = mm.legs_report({"foot_l": ankle["left"], "foot_r": ankle["right"], "hip_l": hip["left"], "hip_r": hip["right"]}, times, 2, 90.0, knees=knees)
    assert rep["knee_bend"]["l"]["p50"] == pytest.approx(0.0, abs=0.1) and rep["knee_bend"]["r"]["max"] == pytest.approx(0.0, abs=0.1)


# ---- 무릎 굽힘 유지(stance_width keep_knee_bend — 8-3 후속) ----
def test_knee_bend_angle():
    assert mm.knee_bend([[0, 0, 100]], [[0, 0, 55]], [[0, 0, 10]])["p50"] == pytest.approx(0.0)
    assert mm.knee_bend([[0, 0, 100]], [[0, 0, 55]], [[45, 0, 55]])["max"] == pytest.approx(90.0)


def test_pelvis_raise_restores_the_hip_to_ankle_distance():
    """엉덩 ±10 · 높이 95, 발목 ±45 · 높이 10 → 상한 50 cm 로 모으면 발목 ±25: 엉덩 → 발목 거리 √(35² + 85²) = 91.9 를 지키려면 골반을
    √(91.9² − 15²) − 85 = 5.67 cm 올려야 한다. 올린 엉덩 관절에서 목표 발목까지 = 원래 거리(무릎 굽힘 그대로), 발목 목표는 그대로."""
    ankle, hip, contacts = wide_stance(half=45.0)
    cfg = {"cap_cm": 50.0, "min_cm": 20.0, "max_shift_cm": 25.0, "blend_frames": 6}
    plain = foot_fix.solve(ankle, hip, contacts, up=2, stance_cfg=cfg)
    out = foot_fix.solve(ankle, hip, contacts, up=2, stance_cfg={**cfg, "keep_knee_bend": True})
    assert plain["pelvis_raise"] is None and out["targets"] == plain["targets"]
    pr = out["pelvis_raise"]
    expect = math.sqrt(35.0 ** 2 + 85.0 ** 2 - 15.0 ** 2) - 85.0
    assert pr["max"] == pytest.approx(expect, abs=0.05) and pr["p50"] == pytest.approx(expect, abs=0.05) and pr["frames"] == 40
    up = foot_fix.raised(hip, pr["dz"], 2)
    for side in ("left", "right"):
        for f in range(40):
            assert mm._dist(up[side][f], out["targets"][side][f]) == pytest.approx(mm._dist(hip[side][f], ankle[side][f]), abs=0.05)
    assert all(out["changed"]["left"]) and all(out["changed"]["right"])


def test_pelvis_raise_takes_the_smaller_leg_and_never_lowers():
    n = 20
    hip = {"left": [[10.0, 0.0, 95.0]] * n, "right": [[-10.0, 0.0, 95.0]] * n}
    before = {"left": [[45.0, 0.0, 10.0]] * n, "right": [[-45.0, 0.0, 10.0]] * n}
    one = foot_fix.pelvis_raise(hip, before, {"left": [[25.0, 0.0, 10.0]] * n, "right": before["right"]}, 2)
    assert one["max"] == 0.0                     # 한 다리만 모으면 다른 다리가 원래보다 펴져야 한다 — 올리지 않는다(작은 쪽)
    wider = foot_fix.pelvis_raise(hip, before, {"left": [[55.0, 0.0, 10.0]] * n, "right": [[-55.0, 0.0, 10.0]] * n}, 2)
    assert wider["max"] == 0.0                   # 넓히면 내리지 않는다(0)
    # 프레임마다 다른 좁힘 — 스무딩 뒤에도 프레임별 상한(작은 쪽) 이하
    after = {"left": [[45.0 - 20.0 * (f % 2), 0.0, 10.0] for f in range(n)], "right": [[-25.0, 0.0, 10.0]] * n}
    pr = foot_fix.pelvis_raise(hip, before, after, 2)
    cap = math.sqrt(35.0 ** 2 + 85.0 ** 2 - 15.0 ** 2) - 85.0
    assert all(d <= (cap if f % 2 else 1e-9) + 1e-9 for f, d in enumerate(pr["dz"]))


def test_zigzag_at_rate_is_the_uniform_speedup_reference():
    """프레임마다 ±1 cm 지그재그 — 보폭 1 이면 떨림 4(가속 ±4), 보폭 2 면 같은 쪽만 골라 0. 보폭 1 = zigzag 와 같다."""
    track = [[(1.0 if f % 2 else -1.0), 0.0, 0.0] for f in range(30)]
    times = [f / 30 for f in range(30)]
    assert mm.zigzag_at_rate([track], times, 1.0) == pytest.approx(mm.zigzag([track], times, edge_s=0.0)["max"]) == pytest.approx(4.0)
    assert mm.zigzag_at_rate([track], times, 2.0) == pytest.approx(0.0)
    flick = [[0.0, 0.0, 0.0]] * 10 + [[float(k), 0.0, 0.0] for k in range(1, 4)] + [[3.0, 0.0, 0.0]] * 17   # 세 프레임 움직였다 멈춤
    assert mm.zigzag([flick], times, edge_s=0.0)["max"] == pytest.approx(0.0) and mm.zigzag_at_rate([flick], times, 2.0) > 0.5


# ---- 계획 · 실행 ----
LEG_OPS = [{"op": "foot_lock"}, {"op": "stance_width"}]


def test_plan_resolves_legs_from_request_chains(bl):
    p = plan(bl, retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS})
    cand = p["candidates"][0]
    fix = cand["steps"][0]["inputs"]["fix"]
    assert [o["op"] for o in fix["ops"]] == ["stance_width", "foot_lock"]           # 순서 정규화
    assert fix["legs"]["left"] == {"hip": "LeftUpLeg", "knee": "LeftLeg", "ankle": "LeftFoot"}
    assert fix["target_dims"]["hip_width_cm"] == 18.0 and fix["target_dims"]["leg_cm"] == pytest.approx(92.71, abs=0.01)   # 가짜 Vesper 기준 포즈(conftest)
    assert fix["target_dims"]["pelvis_height_cm"] == 105.0
    assert "FIX_RESOLVED_AT_RUN" in cand["risks"] and "FIX_ON_SOURCE_SKELETON" in [lm["code"] for lm in cand["expected_limitations"]]
    env = bl.service.plan_motion_generation(request=bvh_request(bl, retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS}))
    assert any(d["code"] == "FIX_OPS_REORDERED" for d in env["diagnostics"])
    assert not bl.launcher.procs


def test_plan_blocks_legs_without_chains(bl):
    p = plan(bl, fix={"ops": [{"op": "foot_lock"}]})
    assert not p["executable"]
    [blocked] = [e for e in p["excluded"] if e["provider"] == "blender"]
    assert (blocked["cause"], blocked["reason"]) == ("UNSUPPORTED_REQUEST", "FIX_LEGS_UNKNOWN")


def test_smooth_alone_needs_no_legs(bl):
    p = plan(bl, fix={"ops": [{"op": "smooth"}]})
    assert p["executable"] and "legs" not in p["candidates"][0]["steps"][0]["inputs"]["fix"]


def test_bad_op_argument_is_a_request_error(bl):
    env = bl.service.plan_motion_generation(request=bvh_request(bl, fix={"ops": [{"op": "smooth"}, {"op": "foot_lock", "feet": ["middle"]}]}))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == "fix.ops[1].feet"


def test_soma_bvh_gets_the_local_ai_defaults(bl):
    clip = bl.roots / "Sources" / "kimodo_03.bvh"
    clip.write_text(soma_named_bvh(), encoding="utf-8")
    p = plan(bl, motion_file={"path": clip.as_posix()}, fix={"ops": LEG_OPS})
    cand = p["candidates"][0]
    rt = next(s for s in cand["steps"] if s["step"] == "retarget")["inputs"]
    assert rt["source_pelvis"] == "Hips" and rt["source_chains"] == SOMA_CHAINS and rt["source_feet"] == ["LeftFoot", "RightFoot"]
    assert rt["defaults_from"] == {"provider": "blender", "keys": ["source_pelvis", "source_chains", "source_feet"]}
    assert cand["steps"][0]["inputs"]["fix"]["legs"]["right"] == {"hip": "RightLeg", "knee": "RightShin", "ankle": "RightFoot"}


def test_args_and_job_carry_the_fix(bl):
    bl.fake.profiles["AS_Vesper_Mocap_WalkP4"] = {"stance": 2.0}
    _, env = generate(bl, retarget={"source_chains": CMU_LEGS}, fix={"ops": LEG_OPS})
    args = bl.launcher.last.args
    assert [o["op"] for o in args["fix"]] == ["stance_width", "foot_lock"] and args["fix_legs"]["legs"]["left"]["ankle"] == "LeftFoot"
    assert args["fix_legs"]["target_dims"]["hip_width_cm"] == 18.0
    legs_report = {"op": "legs", "ops": ["stance_width", "foot_lock"], "ik": {"error_max_cm": 0.0},
                   "before": {"ratio": {"p90": 4.6}, "slide_p95": {"l": 1.6, "r": 1.5}}, "after": {"ratio": {"p90": 2.8}, "slide_p95": {"l": 0.0, "r": 0.0}}}
    original = bl.launcher.last.complete

    def complete(kind="ok"):
        original(kind)
        import json
        import pathlib
        path = pathlib.Path(args["report"])
        report = json.loads(path.read_text(encoding="utf-8"))
        report["fix"] = {"applied": [legs_report]}
        path.write_text(json.dumps(report), encoding="utf-8")
    complete()
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert job["fix"]["source"] == [legs_report]
    target = job["fix"]["target"]
    assert target["ratio"]["p50"] == pytest.approx(2.0) and target["bones"]["foot_l"] == "foot_l" and target["leg_dims"]["hip_width_cm"] == 18.0
    assert "FIX_ON_SOURCE_SKELETON" in [lm["code"] for lm in job["limitations"]]
    assert any(d["code"] == "FIX_LEGS_APPLIED" for d in job["diagnostics"])


def test_route_without_conversion_still_blocks(bl):
    p = plan(bl, motion_file=None, search={"query": "rifle aim idle"}, fix={"ops": [{"op": "smooth"}]})
    [blocked] = [e for e in p["excluded"] if e["provider"] == "existing_motion"]
    assert blocked["reason"] == "UNSUPPORTED_FIX_OP" and "fix.timing" in blocked["message"]
