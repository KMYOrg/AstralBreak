"""Phase 8-1 순수 모듈 — 2차 생성 자동 제약(local_ai/refine.py) · 동작 수치(motion_metrics.py) · 후보 선별 점수(selection.py).

합성 팔(FK 로 위치를 만든 포즈)과 합성 궤적으로 시험한다 — 모델 · 에디터를 띄우지 않는다.
"""
from __future__ import annotations

import math
import random

import pytest

from anim_gen import motion_metrics as mm
from anim_gen import selection as sel
from anim_gen.local_ai import refine as rf

I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _axis_angle(axis, a):
    x, y, z = rf._unit(axis)
    c, s, v = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[c + x * x * v, x * y * v - z * s, x * z * v + y * s], [y * x * v + z * s, c + y * y * v, y * z * v - x * s],
            [z * x * v - y * s, z * y * v + x * s, c + z * z * v]]


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def mat_close(a, b, tol=1e-6):
    return all(abs(a[i][j] - b[i][j]) <= tol for i in range(3) for j in range(3))


# 팔 뼈 오프셋(부모 회전 공간, m) — SOMA 비슷: 위팔 28.7 · 아래팔 27.1 cm, 손 끝 9 cm, 엄지 6 cm
OFF_E, OFF_W = [0.0, -0.287, 0.0], [0.0, -0.271, 0.0]
OFF_MID, OFF_THUMB = [0.0, -0.09, 0.02], [0.03, -0.05, 0.03]


def arm_pose(shoulder, r_arm, r_fore, r_hand):
    e = rf._add(shoulder, rf._mv(r_arm, OFF_E))
    w = rf._add(e, rf._mv(r_fore, OFF_W))
    return {"Arm": (list(shoulder), r_arm), "ForeArm": (e, r_fore), "Hand": (w, r_hand),
            "HandMiddleEnd": (rf._add(w, rf._mv(r_hand, OFF_MID)), r_hand), "HandThumbEnd": (rf._add(w, rf._mv(r_hand, OFF_THUMB)), r_hand)}


def pose_frames(frames: list[dict]) -> dict:
    """frames[{Left: arm_pose, Right: arm_pose}] → {pos{name: [F]}, rot{name: [F]}}."""
    pos, rots = {}, {}
    for fr in frames:
        for side, joints in fr.items():
            for j, (p, r) in joints.items():
                pos.setdefault(f"{side}{j}", []).append(p)
                rots.setdefault(f"{side}{j}", []).append(r)
    return {"pos": pos, "rot": rots}


def sword_pose(n=4, wide=0.5):
    """오른손은 몸 앞 오른쪽, 왼손은 왼쪽 멀리(파지 없음 — 기준 시험처럼). 어깨 반폭 17 cm, y-up · +z 앞 · +x 왼쪽."""
    frames, knuckles = [], {"RightHandIndex2": [], "RightHandPinky2": [], "LeftHandIndex2": [], "LeftHandPinky2": []}
    for k in range(n):
        r_arm = _axis_angle([1, 0, 0], math.radians(-70 - 5 * k))   # 앞으로 들어 올림
        r_fore = rf._mm(_axis_angle([1, 0, 0], math.radians(-20)), r_arm)
        right = arm_pose([-0.17, 1.40, 0.0], r_arm, r_fore, r_fore)
        l_arm = _axis_angle([0, 0, 1], math.radians(70 + 10 * wide))   # 왼팔은 옆으로 벌림
        left = arm_pose([0.17, 1.40, 0.0], l_arm, rf._mm(_axis_angle([0, 0, 1], math.radians(10)), l_arm), l_arm)
        frames.append({"Left": left, "Right": right})
        w = right["Hand"][0]
        knuckles["RightHandIndex2"].append(rf._add(w, [0.03, 0.0, 0.08]))
        knuckles["RightHandPinky2"].append(rf._add(w, [-0.03, 0.0, 0.08]))
        lw = left["Hand"][0]
        knuckles["LeftHandIndex2"].append(rf._add(lw, [0.0, -0.08, 0.03]))
        knuckles["LeftHandPinky2"].append(rf._add(lw, [0.0, -0.08, -0.03]))
    return pose_frames(frames), knuckles


def local_wrist(r_fore, r_hand):
    return rf._mm(rf._t(r_fore), r_hand)


def bend_deg(elbow, wrist, tip):
    return rf._angle_deg(rf._sub(wrist, elbow), rf._sub(tip, wrist))


def fk_consistent(pose, changes, f, side):
    """바꾼 관절이 FK 와 맞는가 — 위치 = 부모 위치 + 부모 새 회전 · (1차 로컬 오프셋)."""
    pos, rot = pose["pos"], pose["rot"]
    g = {n: changes.get(f"{side}{n}", {"pos": pos[f"{side}{n}"][f], "rot": rot[f"{side}{n}"][f]}) for n in ("Arm", "ForeArm", "Hand", "HandMiddleEnd")}
    for child, parent in (("ForeArm", "Arm"), ("Hand", "ForeArm"), ("HandMiddleEnd", "Hand")):
        local = rf._mv(rf._t(rot[f"{side}{parent}"][f]), rf._sub(pos[f"{side}{child}"][f], pos[f"{side}{parent}"][f]))
        want = rf._add(g[parent]["pos"], rf._mv(g[parent]["rot"], local))
        if not close(g[child]["pos"], want, 1e-6):
            return False
    return True


# ---- refine: 프레임 ----
def test_keyframes_window_and_contact_runs():
    assert rf.keyframes(0, 10, 3) == [0, 3, 6, 9, 10] and rf.keyframes(0, 9, 3) == [0, 3, 6, 9] and rf.keyframes(5, 4, 3) == []
    assert rf.window(121, 30.0, None, None) == (0, 120) and rf.window(121, 30.0, 0.5, 1.0) == (15, 30)
    for bad in ((-0.1, None), (None, 4.1), (2.0, 1.0)):
        with pytest.raises(rf.RefineError) as e:
            rf.window(121, 30.0, *bad)
        assert e.value.code == "CONSTRAINT_OUT_OF_RANGE"
    flags = [True] * 3 + [False] + [True] * 4 + [False] + [True] * 6
    assert rf.contact_runs(flags) == [(4, 7), (9, 14)]   # 3프레임 스치기는 뺀다
    assert rf.foot_frames(flags, 3) == [4, 7, 9, 12, 14] and rf.foot_frames(flags, 3, skip={12}) == [4, 7, 9, 14]


def test_pinned_parts_from_requested_constraints():
    items = [{"type": "right-hand", "frame_indices": [0, 30]}, {"type": "fullbody", "frame_indices": [60]},
             {"type": "end-effector", "frame_indices": [90], "joint_names": ["LeftFoot", "Hips"]}, {"type": "root2d", "frame_indices": [120]}]
    p = rf.pinned(items)
    assert p["right_hand"] == {0, 30, 60} and p["left_hand"] == {60} and p["left_foot"] == {60, 90} and p["root"] == {60, 90, 120}


def test_plan_rules_show_flags_frames_and_target():
    cfg = {"mode": "auto", "grip": dict(rf.DEFAULTS["grip"]), "keyframe_step": 3}
    p = rf.plan({"two_hand_weapon_grip": True, "foot_contact": True}, cfg, frames=121, fps=30.0, requested_root=False)
    assert p["passes"] == 2 and [r["kimodo"] for r in p["rules"]] == [["end-effector[LeftHand, RightHand]"],
                                                                      ["end-effector[LeftFoot]", "end-effector[RightFoot]"], ["root2d"]]
    grip = p["rules"][0]
    assert grip["frames"] == {"from": 0, "to": 120, "step": 3, "count": 41} and grip["target"] == "meet" and grip["lead_hand"] == "right"
    assert "knuckle" in grip["spacing_from"] and grip["reach"] == {"support": 0.92, "lead": 0.98}
    assert grip["axis"].startswith("pass-1 lead wrist → support wrist") and f"< {rf.AXIS_MIN_CM:g} cm" in grip["axis"]
    assert p["smooth_sigma_frames"] == rf.SMOOTH_SIGMA_FRAMES == 1.0 and "pass-2 output" in p["smooth_target"]   # A — σ 의 단일 원천
    # 요청 root_path 가 있으면 자동 root2d 를 넣지 않는다 · 구간 · 간격 지정
    cfg["grip"].update(from_s=1.0, to_s=2.0, spacing_cm=8.0, target="lead")
    p = rf.plan({"two_hand_weapon_grip": True}, cfg, frames=121, fps=30.0, requested_root=True)
    assert [r["flag"] for r in p["rules"]] == ["two_hand_weapon_grip"] and p["rules"][0]["frames"]["count"] == 11
    assert p["rules"][0]["spacing_from"] == "request" and p["rules"][0]["target"] == "lead"
    assert rf.plan({}, cfg, frames=121, fps=30.0, requested_root=False)["passes"] == 1
    off = rf.plan({"foot_contact": True}, {**cfg, "mode": "off"}, frames=121, fps=30.0, requested_root=False)
    assert off["passes"] == 1 and off["smooth_sigma_frames"] is None   # 1차만이면 스무딩 없음
    # 계획이 푼 자루 무기 간격(motion_metrics.grip_spacing) — 규칙 spacing_cm = 생성 간격(러너가 쓴다), 대상 간격 · 두 띠 · 사상을 보인다
    m = {"source_shoulder_cm": 32.96, "target_shoulder_cm": 23.96, "arm_ratio": 0.8534}
    cfg["grip"].update(spacing_cm=None, target_spacing_cm=60.0)
    rule = rf.plan({"two_hand_weapon_grip": True}, cfg, frames=121, fps=30.0, requested_root=True,
                   spacing=mm.grip_spacing(m, target_cm=60.0))["rules"][0]
    assert (rule["spacing_cm"], rule["target_spacing_cm"], rule["band_cm"], rule["target_band_cm"]) == (75.19, 60.0, [62.19, 88.19], [48.91, 71.09])
    assert rule["spacing_map"] == m and rule["spacing_from"].startswith("request target_spacing_cm 60 cm → generation 75.19 cm — gap map")


# ---- refine: IK · 회전 ----
def test_rotation_between_maps_a_to_b():
    rnd = random.Random(3)
    for _ in range(50):
        a = [rnd.uniform(-1, 1) for _ in range(3)]
        b = [rnd.uniform(-1, 1) for _ in range(3)]
        assert close(rf._mv(rf.rotation_between(a, b), rf._unit(a)), rf._unit(b), 1e-9)
    flip = rf.rotation_between([0, 1, 0], [0, -1, 0])
    assert close(rf._mv(flip, [0, 1, 0]), [0, -1, 0], 1e-9)
    assert mat_close(rf.rotation_between([1, 2, 3], [2, 4, 6]), I3, 1e-9)


def test_two_bone_reaches_target_and_stays_fk_consistent():
    rnd = random.Random(11)
    for _ in range(30):
        shoulder = [rnd.uniform(-1, 1) for _ in range(3)]
        r_arm = _axis_angle([rnd.uniform(-1, 1) for _ in range(3)], rnd.uniform(-3, 3))
        r_fore = rf._mm(_axis_angle([1, 0, 0], rnd.uniform(0.2, 1.5)), r_arm)
        arm = arm_pose(shoulder, r_arm, r_fore, r_fore)
        target = rf._add(shoulder, rf._mul(rf._unit([rnd.uniform(-1, 1) for _ in range(3)]), rnd.uniform(0.15, 0.5)))
        ik = rf.two_bone(arm["Arm"][0], arm["ForeArm"][0], arm["Hand"][0], r_arm, r_fore, target)
        assert not ik["clamped"] and ik["error"] < 1e-9 and close(ik["wrist"], target, 1e-9)
        assert abs(rf.norm(rf._sub(ik["elbow"], shoulder)) - 0.287) < 1e-9
        assert close(rf._add(shoulder, rf._mv(ik["r_arm"], OFF_E)), ik["elbow"], 1e-9)          # FK = IK 결과
        assert close(rf._add(ik["elbow"], rf._mv(ik["r_fore"], OFF_W)), ik["wrist"], 1e-9)
    far = rf.two_bone(arm["Arm"][0], arm["ForeArm"][0], arm["Hand"][0], r_arm, r_fore, rf._add(shoulder, [2.0, 0, 0]))
    assert far["clamped"] and far["error"] > 1.0 and abs(rf.norm(rf._sub(far["wrist"], shoulder)) - 0.558) < 1e-5


# ---- refine: 파지 목표 ----
def test_meet_brings_both_hands_into_reach_with_the_spacing_on_the_handle_axis():
    pose, knuckles = sword_pose()
    out = rf.solve_grip(pose, knuckles, [0, 1, 2, 3], lead="right", target="meet")
    assert out["spacing_cm"] == pytest.approx(7.0, abs=1e-6) and out["knuckle_cm"] == pytest.approx(6.0, abs=1e-6)  # 너클 폭 6 + 1 cm
    assert out["stats"]["clamped"] == 0 and out["stats"]["ik_error_cm"]["max"] < 1e-6
    reach_l, reach_r = 0.92 * 0.558, 0.98 * 0.558
    for f in range(4):
        ch = out["frames"][f]
        lw, rw = ch["LeftHand"]["pos"], ch["RightHand"]["pos"]
        axis = rf._unit(rf._sub(pose["pos"]["LeftHand"][f], pose["pos"]["RightHand"][f]))   # 손잡이 축 = 1차 주 손목 → 보조 손목
        assert close(rf._sub(lw, rw), rf._mul(axis, 0.07), 1e-9)                        # 보조 손목 = 주 손목 + a·s (함께 옮김)
        assert rf.norm(rf._sub(lw, pose["pos"]["LeftArm"][f])) <= reach_l + 1e-9
        assert rf.norm(rf._sub(rw, pose["pos"]["RightArm"][f])) <= reach_r + 1e-9
        for side in ("Left", "Right"):   # keep — 손목 로컬 회전(아래팔⁻¹ · 손) = 1차, 두 팔 모두
            assert mat_close(local_wrist(ch[f"{side}ForeArm"]["rot"], ch[f"{side}Hand"]["rot"]),
                             local_wrist(pose["rot"][f"{side}ForeArm"][f], pose["rot"][f"{side}Hand"][f]), 1e-9)
        assert fk_consistent(pose, ch, f, "Left") and fk_consistent(pose, ch, f, "Right")
    assert out["stats"]["reach_ratio_before"]["max"] > 1.0 and out["stats"]["reach_ratio_after"]["max"] <= 0.92 + 1e-9
    assert out["stats"]["moved_cm"]["p50"] > 0


def test_lead_keeps_the_lead_hand_and_meet_is_zero_when_already_in_reach():
    pose, knuckles = sword_pose()
    out = rf.solve_grip(pose, knuckles, [0, 2], target="lead")
    for f in (0, 2):
        assert "RightHand" not in out["frames"][f] and out["targets"][f]["lead"] == pose["pos"]["RightHand"][f]
    assert out["stats"]["moved_cm"]["max"] == 0 and out["stats"]["directions"] == {"lead_fixed": 2}
    assert out["stats"]["clamped"] == 2   # 오른손 옆 목표는 왼팔로 닿지 않는다 — 기준 시험처럼(도달 0%) → 다 편 곳
    # 두 손목이 이미 닿으면 meet 도 옮기지 않는다 · 보조 어깨 쪽으로 안 되면 어깨 중점 쪽
    d, kind = rf.meet_offset([-0.2, 1.1, 0.3], [-0.13, 1.1, 0.3], [-0.17, 1.4, 0.0], [0.17, 1.4, 0.0], 0.55, 0.53)  # 보조 0.52 m
    assert (d, kind) == ([0.0, 0.0, 0.0], "inside")
    d, kind = rf.meet_offset([-0.4, 1.3, 0.6], [-0.47, 1.3, 0.6], [-0.17, 1.4, 0.0], [0.17, 1.4, 0.0], 0.55, 0.51)
    assert kind in ("support_shoulder", "shoulder_mid") and rf.norm(d) > 0
    assert rf.norm(rf._sub(rf._add([-0.47, 1.3, 0.6], d), [0.17, 1.4, 0.0])) <= 0.51 + 1e-9


def test_left_lead_hand_swaps_sides():
    pose, knuckles = sword_pose()
    out = rf.solve_grip(pose, knuckles, [1], lead="left", target="meet")
    assert (out["lead"], out["support"]) == ("Left", "Right") and "RightHand" in out["frames"][1]
    ch = out["frames"][1]
    axis = rf._unit(rf._sub(pose["pos"]["RightHand"][1], pose["pos"]["LeftHand"][1]))
    assert close(rf._sub(ch["RightHand"]["pos"], ch["LeftHand"]["pos"] if "LeftHand" in ch else pose["pos"]["LeftHand"][1]),
                 rf._mul(axis, out["spacing_cm"] / 100.0), 1e-9)
    assert out["knuckle_cm"] == pytest.approx(6.0, abs=1e-6)   # 간격은 주 손(왼손) 너클 폭 + 1 cm
    with pytest.raises(rf.RefineError):
        rf.solve_grip(pose, knuckles, [1], target="glue")


def _lateral(pose, f, p):
    """어깨 축(왼 − 오른) 위 좌표 — 클수록 몸의 왼쪽."""
    axis = rf._unit(rf._sub(pose["pos"]["LeftArm"][f], pose["pos"]["RightArm"][f]))
    return rf._dot(p, axis)


def test_handle_axis_is_the_pass1_wrist_line_so_a_polearm_spacing_keeps_each_hand_on_its_side():
    """축 정정(2026-10-26 밤 — 낫 '팔 꼬임') — 무기 없이 만든 1차의 펼친 손은 너클 축(Index2 → Pinky2)이 두 손목 방향과 크게 어긋난다(합성 포즈:
    오른손 너클 축이 몸 오른쪽을 가리킨다). 처음 규칙이면 60 cm 보조 손 목표가 주 손 오른쪽(몸 반대편)에 찍혔다 — 새 축이면 보조 손은 제 쪽에 남는다."""
    pose, knuckles = sword_pose()
    out = rf.solve_grip(pose, knuckles, [0, 1, 2, 3], target="meet", spacing_cm=60.0)
    st = out["stats"]
    assert st["axis_from"] == {"wrist_line": 4, "knuckle": 0} and st["knuckle_vs_wrist_line_deg"]["p50"] > 90.0
    assert st["crossed_pct"] == {"pass1": 0.0, "targets": 0.0} and out["spacing_cm"] == 60.0 and st["clamped"] == 0
    for f in range(4):
        t = out["targets"][f]
        assert _lateral(pose, f, t["support"]) - _lateral(pose, f, t["lead"]) > 0.3          # 왼(보조) 손목이 오른 손목보다 왼쪽
        assert rf.norm(rf._sub(t["support"], t["lead"])) == pytest.approx(0.60, abs=1e-6)
        old = rf._add(pose["pos"]["RightHand"][f], rf._mul(rf._unit(rf._sub(knuckles["RightHandPinky2"][f], knuckles["RightHandIndex2"][f])), 0.60))
        assert _lateral(pose, f, old) < _lateral(pose, f, pose["pos"]["RightHand"][f])      # 처음 규칙의 목표는 몸 반대편이었다


def test_handle_axis_falls_back_to_the_knuckles_when_the_wrists_overlap():
    """1차 두 손목이 AXIS_MIN_CM(2 cm) 안이면 방향이 잡음 — 주 손 너클 축."""
    pose, knuckles = sword_pose()
    p, r = pose["pos"], pose["rot"]
    for f in range(4):   # 두 팔을 IK 로 몸 앞 한 점(어깨 중점 앞 35 · 아래 20 cm)에 — 왼 손목은 0.5 cm 옆(FK 가 맞는 포즈)
        for side, dx in (("Right", 0.0), ("Left", 0.005)):
            ch, ik = rf._move_arm(p, r, side, f, [dx, 1.2, 0.35])
            assert not ik["clamped"]
            for name, v in ch.items():
                p[name][f], r[name][f] = v["pos"], v["rot"]
    out = rf.solve_grip(pose, knuckles, [0, 1, 2, 3], target="meet")
    assert out["stats"]["axis_from"] == {"wrist_line": 0, "knuckle": 4} and out["stats"]["knuckle_vs_wrist_line_deg"]["p50"] is None
    for f in range(4):
        t = out["targets"][f]
        axis = rf._unit(rf._sub(knuckles["RightHandPinky2"][f], knuckles["RightHandIndex2"][f]))
        assert close(rf._sub(t["support"], t["lead"]), rf._mul(axis, 0.07), 1e-9)


def test_keep_holds_the_pass1_wrist_bend_and_leaves_hand_alignment_to_8_4():
    """B (2026-10-26 소견 ③ 손 꺾임) — 손 회전 = 새 아래팔 × 1차 손목 로컬: 두 팔 모두 손목 굽힘(아래팔 → 손 vs 손 → MiddleEnd)이 IK 뒤에도
    1차와 같다. 보조 손 방향을 주 손에 맞추지 않으니 양손 방향 차가 남는다(나란히 쥐기는 8-4)."""
    pose, knuckles = sword_pose()
    out = rf.solve_grip(pose, knuckles, [0, 1, 2, 3], target="meet")
    p = pose["pos"]
    assert out["hand_rule"] == "keep"
    for f in range(4):
        ch = out["frames"][f]
        for side in ("Left", "Right"):
            before = bend_deg(p[f"{side}ForeArm"][f], p[f"{side}Hand"][f], p[f"{side}HandMiddleEnd"][f])
            after = bend_deg(ch[f"{side}ForeArm"]["pos"], ch[f"{side}Hand"]["pos"], ch[f"{side}HandMiddleEnd"]["pos"])
            assert after == pytest.approx(before, abs=1e-6) and before > 5.0
    first = [bend_deg(p["LeftForeArm"][f], p["LeftHand"][f], p["LeftHandMiddleEnd"][f]) for f in range(4)]
    assert out["stats"]["support_wrist_bend_deg"]["max"] == pytest.approx(max(first), abs=0.01)
    assert out["stats"]["hand_align_deg"]["p50"] > 1.0


# ---- refine: 2차 출력 스무딩 (A) ----
def _angle_of(m) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, (m[0][0] + m[1][1] + m[2][2] - 1.0) / 2.0))))


def test_gaussian_series_keeps_lines_damps_the_frame_zigzag_and_folds_the_ends():
    w = rf.gaussian_kernel(1.0)
    assert len(w) == 9 and sum(w) == pytest.approx(1.0) and all(abs(a - b) < 1e-15 for a, b in zip(w, reversed(w)))
    assert rf.gaussian_kernel(None) == [1.0] == rf.gaussian_kernel(0.0) and len(rf.gaussian_kernel(2.0)) == 17
    const = [[1.0, 2.0, 3.0]] * 20
    assert all(close(a, b, 1e-12) for a, b in zip(rf.smooth_series(const, 1.0), const))
    line = [[0.1 * t, -0.2 * t, 1.0] for t in range(30)]
    sm = rf.smooth_series(line, 1.0)
    assert all(close(sm[t], line[t], 1e-9) for t in range(4, 26))                     # 대칭 커널 — 안쪽 직선은 그대로
    zig = [[(-1.0) ** t, 0.0, 0.0] for t in range(40)]
    assert max(abs(v[0]) for v in rf.smooth_series(zig, 1.0)[4:36]) < 0.015          # 2프레임 지그재그 통과율 1.4 %(이산 커널 Σ w·(−1)^k)
    assert rf.smooth_series(zig, None) == zig
    step = [[1.0]] + [[0.0]] * 9                                                      # 끝은 대칭으로 접는다(d c b a | a b c d)
    assert rf.smooth_series(step, 1.0)[0][0] == pytest.approx(w[4] + w[3])


def test_quaternion_round_trip_and_sign_continuity_through_the_shepperd_branch_flip():
    rnd = random.Random(5)
    mats = [_axis_angle([rnd.uniform(-1, 1) for _ in range(3)], rnd.uniform(-math.pi, math.pi)) for _ in range(40)]
    mats += [I3, _axis_angle([1, 0, 0], math.pi), _axis_angle([0, 1, 1], math.pi - 1e-7), _axis_angle([0, 0, 1], 1e-9)]
    for m in mats:
        q = rf.quat_from_matrix(m)
        assert abs(sum(c * c for c in q) - 1.0) < 1e-12 and mat_close(rf.matrix_from_quat(q), m, 1e-9)
    # z 축 200° → 300°(5° 간격): Shepperd 는 240° 근처에서 −q 로 뛴다 — 잇지 않으면 평균이 무너진다. 등속이면 안쪽은 원래 회전 그대로
    seq = [[_axis_angle([0, 0, 1], math.radians(200 + 5 * t))] for t in range(21)]
    raw = [rf.quat_from_matrix(s[0]) for s in seq]
    assert any(sum(a * b for a, b in zip(raw[t], raw[t - 1])) < 0 for t in range(1, 21))
    out = rf.smooth_rotations(seq, 1.0)
    assert all(mat_close(out[t][0], seq[t][0], 1e-9) for t in range(4, 17))
    # 관절마다 ±5° 지그재그 → 0.1° 아래, 관절 수 · 프레임 수 그대로
    wobble = [[_axis_angle([1, 0, 0], math.radians(5.0 * (-1) ** t)), I3] for t in range(30)]
    sm = rf.smooth_rotations(wobble, 1.0)
    assert len(sm) == 30 and all(len(r) == 2 for r in sm)
    assert max(_angle_of(sm[t][0]) for t in range(4, 26)) < 0.1 and all(mat_close(sm[t][1], I3, 1e-12) for t in range(30))
    assert rf.smooth_rotations([], 1.0) == []


# ---- motion_metrics ----
def _line(n, start, step):
    return [[start[0] + step[0] * i, start[1] + step[1] * i, start[2] + step[2] * i] for i in range(n)]


def test_grip_gap_threshold_scales_and_windows():
    times = [i / 30 for i in range(10)]
    right = [[0.0, 0.0, 100.0]] * 10
    left = [[15.0, 0.0, 100.0]] * 5 + [[40.0, 0.0, 100.0]] * 5
    g = mm.grip(left, right, times)
    assert g["grip_pct"] == 50.0 and g["threshold_cm"] == 20.0 and g["gap_cm"]["min"] == 15.0 and g["gap_cm"]["max"] == 40.0
    assert mm.grip([[21.0, 0, 100]] * 10, right, times, scale=1.052)["grip_pct"] == 100.0       # 20 × 1.052 = 21.04 cm
    assert mm.grip(left, right, times, window=(0.2, None))["grip_pct"] == 0.0                     # 0.2초 뒤만
    assert mm.grip(left, right, times, window=(5.0, None))["grip_pct"] is None


def test_grip_band_follows_the_requested_spacing_for_polearms():
    """낫 기준 보정 — 간격 s 가 있으면 파지 = |간격 − s| ≤ 허용(그 골격 cm — 생성 13, 대상 13 × 팔 길이 비). 검 손잡이(간격 없음)만 × pelvis scale."""
    times = [i / 30 for i in range(10)]
    right = [[0.0, 0.0, 100.0]] * 10
    left = [[60.0, 0, 100.0]] * 4 + [[50.0, 0, 100.0]] * 3 + [[10.0, 0, 100.0]] * 3
    # 버전 5: 자루 무기 간격 · 허용은 이미 잰 골격의 cm — pelvis scale 을 곱하지 않는다(버전 4 는 (60 ± 13) × 1.05 = 49.35 ~ 76.65)
    assert mm.grip_band() == (0.0, 20.0) and mm.grip_band(1.05) == pytest.approx((0.0, 21.0)) and mm.grip_band(1.05, 60.0) == (47.0, 73.0)
    assert mm.grip_band(1.05, 47.04, 11.09) == pytest.approx((35.95, 58.13))
    g = mm.grip(left, right, times, spacing_cm=60.0)
    assert g["grip_pct"] == 70.0 and g["band_cm"] == [47.0, 73.0] and g["spacing_cm"] == 60.0 and g["tolerance_cm"] == 13.0   # 60 · 50 안, 10 cm 밖
    assert mm.grip(left, right, times)["grip_pct"] == 30.0 and mm.grip(left, right, times)["tolerance_cm"] is None   # 검 기준이면 반대로 10 cm 만
    assert mm.grip(left, right, times, spacing_cm=60.0, tolerance_cm=5.0)["grip_pct"] == 40.0                         # 허용 5 cm 면 60 만
    ng = mm.non_grip(left, right, times, 1.0, penetration_pct=50.0, worst_time=0.0, spacing_cm=60.0)
    assert ng["non_grip_frames_pct"] == 30.0 and ng["non_grip_penetration_pct_max"] == 30.0 and ng["worst_in_grip"] is True
    assert mm.measure({"hand_l": left, "hand_r": right}, times, up=2, spacing_cm=60.0)["grip"]["grip_pct"] == 70.0
    assert mm.measure({"hand_l": left, "hand_r": right}, times, up=2, spacing_cm=55.0, tolerance_cm=5.0)["grip"]["grip_pct"] == 70.0


# 기준 포즈(cm) — Kimodo SOMA77 BVH 표준 T 포즈 오프셋 · Vesper inspect_skeleton ref_component(2026-10-26 기록 Job f991aa 계측)
SOMA_REST = {"LeftArm": [16.528, 142.916, -1.288], "RightArm": [-16.431, 142.859, -1.231], "LeftForeArm": [45.267, 142.916, -1.291],
             "RightForeArm": [-45.168, 142.859, -1.234], "LeftHand": [72.361, 142.916, -1.288], "RightHand": [-72.301, 142.859, -1.231]}
SOMA_ROLES = {"shoulder_l": "LeftArm", "shoulder_r": "RightArm", "elbow_l": "LeftForeArm", "elbow_r": "RightForeArm", "hand_l": "LeftHand", "hand_r": "RightHand"}
VESPER_REST = {"upperarm_l": [11.982, -5.004, 145.66], "upperarm_r": [-11.982, -5.004, 145.66], "lowerarm_l": [27.48, -6.322, 126.884],
               "lowerarm_r": [-27.48, -6.322, 126.884], "hand_l": [42.557, -1.395, 109.848], "hand_r": [-42.557, -1.395, 109.848]}
VESPER_ROLES = {"shoulder_l": "upperarm_l", "shoulder_r": "upperarm_r", "elbow_l": "lowerarm_l", "elbow_r": "lowerarm_r", "hand_l": "hand_l", "hand_r": "hand_r"}


def test_gap_map_from_rest_dims_predicts_the_recorded_vesper_gap():
    """버전 5 — 두 골격의 어깨 관절 폭 · 팔 길이(arm_dims)로 간격 사상. 기록 Job f991aa(낫, 생성 간격 60): 소스 2차 손목 간격 p50 → Vesper p50 실측을
    1.1 cm 안으로 맞힌다(버전 4 의 × pelvis scale 1.052 는 +15 ~ +17 cm — 띠 [49.46, 76.83] 밖으로 FAIL). 사상은 단조 일차라 p50 이 그대로 옮겨진다."""
    soma, vesper = mm.arm_dims(SOMA_REST, SOMA_ROLES), mm.arm_dims(VESPER_REST, VESPER_ROLES)
    assert soma == {"shoulder_width_cm": 32.96, "arm_cm": 55.85} and vesper == {"shoulder_width_cm": 23.96, "arm_cm": 47.66}
    from anim_gen.providers import local_ai
    assert local_ai.SOMA_ARMS == soma   # 생성 골격 상수 = 같은 정의로 잰 값
    m = mm.gap_map(soma, vesper)
    assert m == {"source_shoulder_cm": 32.96, "target_shoulder_cm": 23.96, "arm_ratio": 0.8534}
    recorded = {"source_p50": [60.98, 61.81, 60.14, 62.74], "vesper_p50": [48.32, 48.57, 48.17, 49.28]}   # 4 seed (Vesper 표본 시각에 맞춘 소스)
    for s, v in zip(recorded["source_p50"], recorded["vesper_p50"]):
        assert abs(mm.map_gap(m, s) - v) <= 1.1 and abs(s * 1.0524 - v) > 15.0
        assert mm.map_gap(m, mm.map_gap(m, s), "source") == pytest.approx(s)   # 역사상
    band = mm.grip_spacing(m, source_cm=60.0)["target_band_cm"]
    assert band == [35.95, 58.13] and all(band[0] <= v <= band[1] for v in recorded["vesper_p50"])
    assert mm.arm_dims({k: v for k, v in VESPER_REST.items() if k != "lowerarm_r"}, VESPER_ROLES) is None   # 위치가 빠지면 사상 없음


def test_grip_spacing_resolves_one_request_into_both_skeletons():
    """대상 기준 요청(target_cm) → 생성 간격 · 두 띠. 대상 띠 = 생성 띠의 상(사상의 기울기 = 팔 길이 비 = 대상 허용 / 생성 허용)."""
    m = {"source_shoulder_cm": 32.96, "target_shoulder_cm": 23.96, "arm_ratio": 0.8534}
    g = mm.grip_spacing(m, target_cm=60.0)
    assert g["from"] == "target" and g["source_cm"] == 75.19 and g["target_cm"] == 60.0 and g["tolerance_cm"] == {"source": 13.0, "target": 11.09}
    assert g["source_band_cm"] == [62.19, 88.19] and g["target_band_cm"] == [48.91, 71.09] and g["map"] == m
    assert [round(mm.map_gap(m, x), 2) for x in g["source_band_cm"]] == pytest.approx(g["target_band_cm"], abs=0.01)
    s = mm.grip_spacing(m, source_cm=60.0)
    assert s["from"] == "source" and s["source_cm"] == 60.0 and s["target_cm"] == 47.04 and s["source_band_cm"] == [47.0, 73.0]
    for bad in ({}, {"source_cm": 60.0, "target_cm": 60.0}):
        with pytest.raises(mm.GripSpacingError):
            mm.grip_spacing(m, **bad)
    wide = {"source_shoulder_cm": 32.96, "target_shoulder_cm": 44.0, "arm_ratio": 1.04}
    with pytest.raises(mm.GripSpacingError):   # 어깨가 넓은 대상에 8 cm — 생성 골격에서 음수 간격
        mm.grip_spacing(wide, target_cm=8.0)


def _scaled_gap(src_pose: dict, k_sh: float, k_up: float, k_fore: float) -> float:
    """FK 리타깃(본 대 본 정렬) 모델 — 대상 본 벡터 = 소스 본 벡터 × 길이 비. 손목 차 = k_어깨·어깨 차 + k_위팔·위팔 차 + k_아래팔·아래팔 차."""
    def d(a, b):
        return rf._sub(src_pose[a], src_pose[b])
    v = rf._add(rf._add(rf._mul(d("sl", "sr"), k_sh), rf._mul(rf._sub(d("el", "sl"), d("er", "sr")), k_up)),
                rf._mul(rf._sub(d("wl", "el"), d("wr", "er")), k_fore))
    return rf.norm(v)


def _grip_pose(width: float, upper: float, fore: float, gap: float, tilt_deg: float = 0.0) -> dict:
    """어깨 관절 ±width/2(x — 왼쪽 +, y 위, z 앞), 두 손목이 어깨 10 cm 아래 · 40 cm 앞에서 간격 gap · 파지선이 어깨선에서 위아래로 tilt_deg 기운
    자세(팔꿈치는 아래로 굽힌 2본 해 — 닿는 자세만)."""
    t = math.radians(tilt_deg)
    center = [0.0, -10.0, 40.0]
    half = [0.5 * gap * math.cos(t), 0.5 * gap * math.sin(t), 0.0]
    pose = {"sl": [width / 2, 0.0, 0.0], "sr": [-width / 2, 0.0, 0.0], "wl": rf._add(center, half), "wr": rf._sub(center, half)}
    for s in ("l", "r"):
        sh, w = pose[f"s{s}"], pose[f"w{s}"]
        dist = rf.norm(rf._sub(w, sh))
        assert abs(upper - fore) < dist < upper + fore
        u = rf._unit(rf._sub(w, sh))
        cos_a = (upper ** 2 + dist ** 2 - fore ** 2) / (2 * upper * dist)
        pole = rf._unit(rf._sub([0.0, -1.0, 0.0], rf._mul(u, rf._dot([0.0, -1.0, 0.0], u))))
        pose[f"e{s}"] = rf._add(sh, rf._mul(rf._add(rf._mul(u, cos_a), rf._mul(pole, math.sqrt(max(0.0, 1 - cos_a ** 2)))), upper))
    return pose


@pytest.mark.parametrize("target", [{"name": "vesper", "width": 23.96, "upper": 24.38, "fore": 23.28},
                                    {"name": "wide shoulders", "width": 44.0, "upper": 30.0, "fore": 28.0},
                                    {"name": "narrow · long arms", "width": 20.0, "upper": 33.0, "fore": 31.0}])
def test_gap_map_holds_for_other_body_shapes(target):
    """다른 체형(합성 — 어깨가 넓은 메시 · 좁고 팔이 긴 메시)에서도 대상 띠가 맞는가: 대상 요청 60 cm → 생성 간격 → FK 리타깃 모델로 옮긴 대상 간격이
    요청에서 0.5 cm 안(파지선 ∥ 어깨선)이고, 파지선이 30° 기울어도 대상 띠 안(기울수록 사상이 대상 간격을 낮게 본다 — 오차는 몸통 비에 따라 커진다)."""
    soma = {"shoulder_width_cm": 32.96, "arm_cm": 55.85}
    dims = {"shoulder_width_cm": target["width"], "arm_cm": target["upper"] + target["fore"]}
    m = mm.gap_map(soma, dims)
    g = mm.grip_spacing(m, target_cm=60.0)
    k_sh, k_up, k_fore = target["width"] / 32.96, target["upper"] / 28.74, target["fore"] / 27.11
    lo, hi = g["target_band_cm"]
    for tilt in (0.0, 30.0):
        actual = _scaled_gap(_grip_pose(32.96, 28.74, 27.11, g["source_cm"], tilt), k_sh, k_up, k_fore)
        assert lo <= actual <= hi, (target["name"], tilt, actual, g)
        if tilt == 0.0:
            assert actual == pytest.approx(60.0, abs=0.5)
    # 생성 간격을 그대로 두면(버전 4 처럼 요청 = 생성 간격) 대상 간격은 체형마다 다른 곳에 떨어진다 — 사상이 그 자리를 맞힌다
    assert _scaled_gap(_grip_pose(32.96, 28.74, 27.11, 60.0), k_sh, k_up, k_fore) == pytest.approx(mm.map_gap(m, 60.0), abs=0.5)


def test_stance_ratio_is_lateral_only_and_turn_invariant():
    n = 4
    for yaw in (0.0, 90.0, 33.0):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

        def at(x, y, z):  # 몸 좌표(x 왼쪽 · y 앞) → z-up 세계, yaw 만큼 돌림
            return [c * x - s * y, s * x + c * y, z]
        hip_l, hip_r = [at(10, 0, 95)] * n, [at(-10, 0, 95)] * n
        foot_l, foot_r = [at(45, 30, 8)] * n, [at(-45, -30, 8)] * n          # 좌우 90 cm · 앞뒤 60 cm
        st = mm.stance(foot_l, foot_r, hip_l, hip_r, up=2)
        assert st["lateral_ratio"]["p50"] == pytest.approx(4.5) and st["hip_width_cm"] == pytest.approx(20.0)
        assert st["lateral_cm"]["p90"] == pytest.approx(90.0) and st["stride_leg_ratio"]["p50"] == pytest.approx(60 / st["leg_cm"], abs=1e-3)
    # y-up (Kimodo) 도 같은 값
    yup = mm.stance([[45, 8, 30]] * n, [[-45, 8, -30]] * n, [[10, 95, 0]] * n, [[-10, 95, 0]] * n, up=1)
    assert yup["lateral_ratio"]["p50"] == pytest.approx(4.5)


def test_swing_peak_time_and_active_share():
    times = [i / 30 for i in range(31)]
    hand_r = [[0.0, 0.0, 100.0]] * 31
    hand_r = [list(p) for p in hand_r]
    for i in range(10, 13):                     # 0.37 ~ 0.40초에 프레임당 15 cm(450 cm/s)
        for j in range(i, 31):
            hand_r[j][1] += 15.0
    hand_l = [[20.0, 0.0, 100.0]] * 31
    sw = mm.swing(hand_l, hand_r, times, scale=1.0)
    assert sw["hand"] == "hand_r" and sw["peak_cm_s"] == pytest.approx(450.0) and sw["peak_time"] == pytest.approx(10 / 30, abs=1e-4)
    assert sw["active_pct"] == pytest.approx(100 * 3 / 31, abs=0.1)
    assert mm.swing(hand_l, hand_r, times, scale=1.5)["peak_cm_s"] == pytest.approx(300.0)
    m = mm.measure({"hand_l": hand_l, "hand_r": hand_r}, times, up=2)
    assert m["stance"] is None and m["grip"]["grip_pct"] is not None and m["version"] == mm.VERSION


def test_non_grip_penetration_upper_bound():
    times = [i / 30 for i in range(10)]
    right = [[0.0, 0.0, 100.0]] * 10
    left = [[10.0, 0, 100.0]] * 3 + [[50.0, 0, 100.0]] * 7               # 파지 30 %
    ng = mm.non_grip(left, right, times, 1.0, penetration_pct=39.7, worst_time=0.05)
    assert ng["grip_pct"] == 30.0 and ng["non_grip_frames_pct"] == 70.0 and ng["non_grip_penetration_pct_max"] == 39.7 and ng["worst_in_grip"] is True
    ng = mm.non_grip(left, right, times, 1.0, penetration_pct=90.0, worst_time=0.25)
    assert ng["non_grip_penetration_pct_max"] == 70.0 and ng["worst_in_grip"] is False
    assert mm.non_grip(left, right, times, 1.0, penetration_pct=0, worst_time=0.0)["worst_in_grip"] is None


def _body(n, hand_mid, *, shoulder_up=140.0, hip_up=95.0):
    """z-up 몸 — 손목 중점 hand_mid(f) ± 5 cm(좌우), 어깨 ± 17 · 높이 shoulder_up, 팔꿈치 = 어깨와 손목 사이 위로 꺾인 곳(위팔 · 아래팔 길이 고정
    28 · 26 cm 가 아니어도 프레임 평균), 엉덩 ± 9 · 높이 hip_up(고정)."""
    tr = {k: [] for k in mm.ROLES}
    for f in range(n):
        m = hand_mid(f)
        for s, x in (("l", 1.0), ("r", -1.0)):
            hand = [m[0] + 5.0 * x, m[1], m[2]]
            sh = [17.0 * x, 0.0, shoulder_up]
            tr[f"hand_{s}"].append(hand)
            tr[f"shoulder_{s}"].append(sh)
            tr[f"elbow_{s}"].append([(hand[0] + sh[0]) / 2, (hand[1] + sh[1]) / 2 - 10.0, (hand[2] + sh[2]) / 2])
            tr[f"hip_{s}"].append([9.0 * x, 0.0, hip_up])
            tr[f"foot_{s}"].append([12.0 * x, 0.0, 8.0])
    return tr


def test_attack_width_is_the_hand_path_box_over_arm_length_and_raise_is_recorded():
    n = 31
    times = [i / 30 for i in range(n)]
    # 손목 중점이 앞 30 → 위 머리 위(어깨 + 30) → 아래 앞(엉덩 높이)으로: y 0 ~ 60 · z 95 ~ 170 cm
    path = lambda f: [0.0, 30.0 + 30.0 * math.sin(math.pi * f / (n - 1)), 170.0 - 75.0 * f / (n - 1)]  # noqa: E731
    tr = _body(n, path)
    a = mm.attack(tr, times, up=2)
    arm = mm.arm_length(tr["shoulder_l"], tr["elbow_l"], tr["hand_l"])
    assert a["arm_cm"] == pytest.approx(arm, abs=0.01) and a["box_cm"] == pytest.approx([0.0, 30.0, 75.0], abs=0.01)
    assert a["width_arm_ratio"] == pytest.approx(math.hypot(30.0, 75.0) / arm, abs=1e-3)
    assert a["raise_arm_ratio"] == pytest.approx(30.0 / arm, abs=1e-3) and a["raise_time"] == pytest.approx(0.0)
    # '양손 모아 서 있기' — 손이 엉덩 앞 30 cm 에 머물면 폭 0 · 손 들기 음수
    still = mm.attack(_body(n, lambda f: [0.0, 30.0, 110.0]), times, up=2)
    assert still["width_arm_ratio"] == 0.0 and still["raise_arm_ratio"] < 0
    # 몸 전체가 걸어가도(엉덩 · 손이 같이) 폭은 그대로 — 엉덩 기준
    walk = _body(n, path)
    for k in walk:
        walk[k] = [[p[0], p[1] + 3.0 * f, p[2]] for f, p in enumerate(walk[k])]
    assert mm.attack(walk, times, up=2)["width_arm_ratio"] == pytest.approx(a["width_arm_ratio"], abs=1e-3)
    m = mm.measure(tr, times, up=2)
    assert m["attack"]["width_arm_ratio"] == a["width_arm_ratio"] and m["wrist_bend"] is None and m["version"] == mm.VERSION == 5
    assert mm.measure({k: tr[k] for k in ("hand_l", "hand_r", "hip_l", "hip_r")}, times, up=2)["attack"] is None   # 어깨 · 팔꿈치 없으면 못 잰다


def test_attack_takes_the_wider_hand_so_a_one_handed_swing_is_not_halved():
    """버전 3 — 빈 손(왼손)이 엉덩 앞에 가만있고 오른손만 휘두르면 두 손 중점 폭은 절반, 손별 큰 쪽은 오른손 그대로."""
    n = 31
    times = [i / 30 for i in range(n)]
    swing = lambda f: [0.0, 30.0 + 30.0 * math.sin(math.pi * f / (n - 1)), 170.0 - 75.0 * f / (n - 1)]  # noqa: E731
    tr = _body(n, swing)
    tr["hand_l"] = [[5.0, 25.0, 100.0]] * n
    a = mm.attack(tr, times, up=2)
    right = math.hypot(30.0, 75.0)
    arm = a["arm_cm"]
    assert a["hand"] == "hand_r" and a["width_arm_ratio"] == pytest.approx(right / arm, abs=2e-3)
    assert a["width_by_hand"]["l"] == 0.0 and a["width_mid_arm_ratio"] < 0.6 * a["width_arm_ratio"]
    assert a["raise_arm_ratio"] == pytest.approx(30.0 / arm, abs=2e-3)   # 손별 큰 쪽 — 오른손 170 − 어깨 중점 140 (두 손 중점이면 −5)


def test_hand_contact_measures_bone_segment_overlap_between_the_hands():
    times = [i / 30 for i in range(4)]
    finger = lambda x0, x1, y: ([[x0, y, 100.0]] * 4, [[x1, y, 100.0]] * 4)  # noqa: E731
    left = [finger(0.0, 8.0, 0.0), finger(0.0, 8.0, 3.0)]
    right_far = [finger(0.0, 8.0, 10.0)]
    right_cross = [([[4.0, -2.0, 101.0]] * 2 + [[4.0, 20.0, 100.0]] * 2, [[4.0, 6.0, 99.0]] * 2 + [[12.0, 20.0, 100.0]] * 2)]   # 처음 두 프레임만 손가락을 가로지른다
    far = mm.hand_contact(left, right_far, times)
    assert far["contact_pct"] == 0.0 and far["min_cm"] == pytest.approx(7.0) and far["first_time"] is None and far["threshold_cm"] == 2.5
    cross = mm.hand_contact(left, right_cross, times, scale=1.05)
    assert cross["contact_pct"] == 50.0 and cross["first_time"] == 0.0 and cross["min_cm"] < 1.01 and cross["threshold_cm"] == pytest.approx(2.625, abs=0.01)
    assert mm.hand_contact([], right_far, times)["contact_pct"] is None
    assert mm._seg_dist([0, 0, 0], [0, 0, 0], [3, 4, 0], [3, 4, 0]) == pytest.approx(5.0)   # 점 · 점
    assert mm._seg_dist([0, 0, 0], [10, 0, 0], [5, 3, -1], [5, 3, 1]) == pytest.approx(3.0)  # 엇갈린 선분


def test_arm_cross_counts_wrists_swapped_beyond_a_hand_width_and_turns_with_the_body():
    """버전 4 — 엉덩 축 위 (왼 손목 − 오른 손목) 좌우 차. 10 cm × scale 넘게 넘어가야 꼬임(crossed_pct), 조금이라도 넘어가면 swapped_pct(기록 —
    검 손잡이처럼 손목을 포개면 흔하다)."""
    times = [i / 30 for i in range(5)]
    offsets = [20.0, 3.0, -5.0, -15.0, -30.0]            # 왼 손목 좌우 위치(오른 손목 = 0) — 제자리 · 제자리 · 살짝 · 꼬임 · 꼬임
    for yaw in (0.0, 90.0, 33.0):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

        def at(x, y, z):  # 몸 좌표(x 왼쪽 · y 앞) → z-up 세계, yaw 만큼 돌림
            return [c * x - s * y, s * x + c * y, z]
        hip_l, hip_r = [at(9, 0, 95)] * 5, [at(-9, 0, 95)] * 5
        hand_r = [at(0, 30, 120)] * 5
        hand_l = [at(x, 30, 125) for x in offsets]
        x = mm.arm_cross(hand_l, hand_r, hip_l, hip_r, times, up=2)
        assert x["crossed_pct"] == 40.0 and x["swapped_pct"] == 60.0 and x["threshold_cm"] == 10.0
        assert x["depth_cm"]["max"] == pytest.approx(30.0) and x["depth_cm"]["p50"] == pytest.approx(15.0) and x["first_time"] == pytest.approx(0.1)
    assert mm.arm_cross(hand_l, hand_r, hip_l, hip_r, times, up=2, scale=2.0)["crossed_pct"] == 20.0     # 20 cm 넘게만
    yup = mm.arm_cross([[x, 125, 30] for x in offsets], [[0, 120, 30]] * 5, [[9, 95, 0]] * 5, [[-9, 95, 0]] * 5, times, up=1)
    assert yup["crossed_pct"] == 40.0                                                                   # y-up (Kimodo) 도 같은 값
    assert mm.arm_cross(hand_l, hand_r, [[0, 0, 95]] * 5, [[0, 0, 95]] * 5, times, up=2)["crossed_pct"] is None   # 엉덩 폭 0 — 못 잰다


def test_head_near_takes_the_closest_hand_point_and_measure_wires_head_and_hand_points():
    times = [i / 30 for i in range(4)]
    head = [[0.0, 0.0, 160.0]] * 4
    wrist_l, wrist_r = [[30.0, 20.0, 120.0]] * 4, [[-30.0, 20.0, 120.0]] * 4
    finger = [[0.0, 6.0, 160.0], [0.0, 9.0, 160.0], [0.0, 12.0, 160.0], [0.0, 40.0, 160.0]]   # 6 · 9 · 12 · 40 cm
    h = mm.head_near([wrist_l, wrist_r, finger], head, times)
    assert h["near_pct"] == 50.0 and h["min_cm"] == pytest.approx(6.0) and h["first_time"] == 0.0 and h["threshold_cm"] == 10.0 and h["points"] == 3
    assert mm.head_near([wrist_l, wrist_r, finger], head, times, scale=1.3)["near_pct"] == 75.0   # 13 cm 안
    assert mm.head_near([wrist_l, wrist_r], head, times)["near_pct"] == 0.0 and mm.head_near([], head, times)["near_pct"] is None
    tracks = _body(4, lambda f: [0.0, 30.0, 120.0])
    tracks["head"] = head
    m = mm.measure(tracks, times, up=2, hand_points=[finger])
    assert m["head"]["near_pct"] == 50.0 and m["head"]["points"] == 3 and m["cross"]["crossed_pct"] == 0.0
    tracks["finger_l"] = finger                                                   # hand_points 가 없으면 finger 역할(Kimodo 중지 마디)
    assert mm.measure(tracks, times, up=2)["head"]["points"] == 3
    del tracks["head"]
    assert mm.measure(tracks, times, up=2)["head"] is None                         # 머리 본이 없으면 None(점수 밖)
    assert m["jitter"]["joints"] == 10                                             # 머리는 떨림에 안 쓴다


def test_zigzag_catches_frame_oscillation_by_part_and_ignores_smooth_motion():
    n = 61
    times = [i / 30 for i in range(n)]
    smooth = [[0.0, 0.5 * f * f / 30, 100.0] for f in range(n)]                                 # 등가속 — 지그재그 0
    zig = [[0.5 * (-1) ** f if f <= 15 else 0.0, 0.0, 100.0] for f in range(n)]                 # 처음 0.5 초만 ±0.5 cm
    z = mm.zigzag([smooth, zig], times)
    assert z["start"] == pytest.approx(2.0) and z["middle"] == 0.0 and z["end"] == 0.0 and z["max"] == pytest.approx(2.0) and z["joints"] == 2
    assert mm.zigzag([zig], times, scale=2.0)["start"] == pytest.approx(1.0)
    assert mm.zigzag([smooth], times[:3])["start"] is None


def test_wrist_bend_and_contact_slide():
    b = mm.wrist_bend([[0, 0, 0]] * 3, [[0, 0, -26]] * 3, [[0, 0, -36], [0, 10, -26], [0, 10, -36]])
    assert (b["p50"], b["max"]) == (45.0, 90.0)
    times = [i / 30 for i in range(6)]
    foot = [[0, 0, 8], [0, 1, 8], [0, 2, 9], [0, 2, 9], [0, 12, 9], [0, 22, 9]]
    s = mm.contact_slide(foot, [True, True, True, True, False, False], times, up=2)
    assert s["frames"] == 3 and s["max"] == pytest.approx(30.0) and s["p95"] == pytest.approx(30.0)   # 1 cm/프레임 = 30 cm/s, 접지 밖 이동은 안 센다


# ---- selection ----
def cand(index, *, grip=None, p90=None, peak=None, pen=None, status="PASSED", width=None, non_grip=None, scored=None, spacing=None, cross=None,
         head=None):
    metrics = {"grip": {"grip_pct": grip, "spacing_cm": spacing}, "stance": {"lateral_ratio": {"p90": p90}}, "swing": {"peak_cm_s": peak},
               "clearance": {"penetration_pct": pen}, "attack": {"width_arm_ratio": width}}
    if non_grip is not None:
        metrics["non_grip"] = {"non_grip_penetration_pct_max": non_grip}
    if scored is not None:
        metrics["breakage"] = {"scored_warnings": scored}
    if cross is not None:
        metrics["cross"] = {"crossed_pct": cross}
    if head is not None:
        metrics["head"] = {"near_pct": head}
    return {"index": index, "seed": 100 + index, "status": status, "metrics": metrics}


def test_penalties_follow_the_table():
    p = sel.penalties(cand(0, grip=75, p90=5.55, peak=300, pen=39.7, status="PASSED_WITH_WARNINGS")["metrics"], "PASSED_WITH_WARNINGS",
                      best_swing=400, grip_on=True, swing_on=True)
    assert p == {"grip": 0.25, "stance": 0.61, "swing": 0.25, "attack": None, "clearance": 0.397, "breakage": 0.5, "cross": None, "head": None}
    p = sel.penalties(cand(0, grip=75, p90=1.8, peak=400, pen=0, width=1.2)["metrics"], "PASSED", best_swing=400, best_width=1.5, grip_on=False,
                      swing_on=False)
    assert p == {"grip": None, "stance": 0.0, "swing": None, "attack": None, "clearance": 0.0, "breakage": 0.0, "cross": None, "head": None}
    assert sel.penalties(cand(0, p90=12.0)["metrics"], "PASSED", best_swing=None, grip_on=True, swing_on=True)["stance"] == 1.0


def test_attack_penalty_is_relative_with_an_absolute_floor():
    pen = lambda w, best: sel.penalties(cand(0, width=w)["metrics"], "PASSED", best_swing=None, best_width=best, grip_on=False, swing_on=True)["attack"]  # noqa: E731
    assert pen(1.65, 1.65) == 0.0 and pen(1.02, 1.65) == pytest.approx(1 - 1.02 / 1.65, abs=1e-4)
    assert pen(0.38, 1.65) == pytest.approx(1 - 0.38 / 1.65, abs=1e-4)          # 상대가 더 크면 상대
    assert pen(0.5, 0.5) == pytest.approx(0.5) and pen(0.0, None) == 1.0      # 최고여도 팔 길이 1.0 아래면 하한 · 혼자여도
    assert pen(None, 1.0) is None


def test_clearance_counts_non_grip_frames_with_the_grip_flag_and_breakage_drops_penetration_warnings():
    m = cand(0, pen=72.7, non_grip=0.0, scored=[])["metrics"]
    p = sel.penalties(m, "PASSED_WITH_WARNINGS", best_swing=None, grip_on=True, swing_on=False)
    assert p["clearance"] == 0.0 and p["breakage"] == 0.0                     # 파지 프레임 관통 · 관통 경고는 세지 않는다
    p = sel.penalties(m, "PASSED_WITH_WARNINGS", best_swing=None, grip_on=False, swing_on=False)
    assert p["clearance"] == 0.727                                            # 파지 플래그가 없으면 전체 관통
    assert sel.clearance_pct(cand(0, pen=40.0)["metrics"], True) == (40.0, "all")   # 손목 트랙이 없어 비파지를 못 재면 전체
    assert sel.breakage(cand(0, scored=["ROTATION_JUMP_INHERITED"])["metrics"], "PASSED_WITH_WARNINGS") == 0.5
    assert sel.breakage(cand(0, scored=[])["metrics"], "NEEDS_REVIEW") == 0.5
    assert sel.breakage(cand(0)["metrics"], "PASSED_WITH_WARNINGS") == 0.5   # 근거가 기록에 없으면 상태대로


def test_polearm_penetration_counts_every_frame():
    """낫 정정 — 요청 간격이 있으면(자루 무기, 측정 기록 grip.spacing_cm) 비파지만 세는 규칙을 쓰지 않는다: 기록 Job ad275a 의 몸 관통 75 % 를
    비파지 상한 0 으로 뺐다. 검 손잡이(간격 없음)는 그대로."""
    polearm = cand(0, grip=93.3, pen=75.2, non_grip=0.0, spacing=60.0)["metrics"]
    assert sel.clearance_pct(polearm, True) == (75.2, "all_polearm")
    assert sel.penalties(polearm, "PASSED_WITH_WARNINGS", best_swing=None, grip_on=True, swing_on=False)["clearance"] == 0.752
    assert sel.clearance_pct(cand(0, pen=75.2, non_grip=0.0)["metrics"], True) == (0.0, "non_grip")
    assert sel.clearance_pct(polearm, False) == (75.2, "all")


def test_cross_and_head_penalties_spare_the_operating_sickle_and_sink_the_broken_scythe():
    """버전 4 — 기준은 운영 낫 애니 4개(Vesper: 꼬임 2.7 / 7.4 / 16.3 / 0 % · 머리 10 cm 안 0 %)가 0 이 되게. 기록 Job ad275a 후보(꼬임 91.7 / 28.3 /
    12.5 / 82.5 · 머리 41.7 / 90 / 59.2 / 69.2 %). 꼬임은 파지 플래그일 때만(한손 베기 · 팔짱은 원래 교차), 머리는 언제나."""
    def pen(**kw):
        return sel.penalties(cand(0, **kw)["metrics"], "PASSED", best_swing=None, grip_on=True, swing_on=False)
    for cross in (2.7, 7.4, 16.3, 0.0):
        assert pen(cross=cross, head=0.0)["cross"] == 0.0 and pen(cross=cross, head=0.0)["head"] == 0.0
    assert [pen(cross=c)["cross"] for c in (91.7, 28.3, 12.5, 82.5)] == [1.0, 0.166, 0.0, 1.0]
    assert [pen(head=h)["head"] for h in (41.7, 90.0, 59.2, 69.2)] == [1.0, 1.0, 1.0, 1.0] and pen(head=6.7)["head"] == pytest.approx(0.068)
    off = sel.penalties(cand(0, cross=91.7, head=41.7)["metrics"], "PASSED", best_swing=None, grip_on=False, swing_on=False)
    assert off["cross"] is None and off["head"] == 1.0
    assert sel.WEIGHTS["cross"] == 2.0 and sel.WEIGHTS["head"] == 2.0 and sel.check_weights({"head": 5})["head"] == 5.0
    # 같은 점수에서 머리 근접 후보는 밀린다
    out = sel.rank([cand(0, grip=100, p90=3.0, cross=0.0, head=60.0), cand(1, grip=100, p90=3.0, cross=0.0, head=0.0)], grip_on=True, swing_on=False)
    assert out["picked"]["index"] == 1 and "head" in out["picked"]["reason"]


def test_recorded_job_c49a83_numbers_now_pick_seed_20261025():
    """기록 Job job_20261026_154723_c49a83(E2 ②)의 Vesper 원 수치 + 스파이크가 잰 궤적 폭 — 처음 점수는 seed 26('양손 모아 서 있기')을 골랐다.
    seed 28 의 깨짐 경고 코드는 기록에 없다(scored_warnings 없음 → 상태대로 0.5)."""
    rows = [cand(0, grip=100, p90=5.63, peak=330.6, pen=72.7, non_grip=0.0, width=1.65, scored=[], status="PASSED_WITH_WARNINGS"),
            cand(1, grip=100, p90=5.63, peak=210.7, pen=0, non_grip=0.0, width=0.38, scored=[]),
            cand(2, grip=100, p90=4.23, peak=217.4, pen=77.7, non_grip=0.0, width=1.02, scored=[], status="PASSED_WITH_WARNINGS"),
            cand(3, grip=100, p90=4.92, peak=278.0, pen=84.3, non_grip=0.0, width=1.08, status="PASSED_WITH_WARNINGS")]
    out = sel.rank(rows, grip_on=True, swing_on=True)
    by = {c["index"]: c for c in out["candidates"]}
    assert out["picked"]["index"] == 0 and [by[i]["rank"] for i in range(4)] == [1, 4, 2, 3]
    assert by[0]["score"] == pytest.approx(0.1138, abs=1e-4) and by[1]["score"] == pytest.approx(0.3197, abs=1e-4)
    assert by[1]["penalties"]["attack"] == pytest.approx(0.7697, abs=1e-4) and by[0]["clearance_basis"] == "non_grip"
    assert out["best_width_arm_ratio"] == 1.65 and "attack" in out["picked"]["reason"]


def test_rank_picks_lowest_score_excludes_failed_and_is_reproducible():
    cands = [cand(0, grip=0, p90=5.5, peak=540, pen=39.7), cand(1, grip=90, p90=3.0, peak=400, pen=5.0),
             cand(2, grip=100, p90=2.0, peak=100, pen=0, status="FAILED"), cand(3, grip=85, p90=3.5, peak=380, pen=0, status="PASSED_WITH_WARNINGS")]
    out = sel.rank(cands, grip_on=True, swing_on=True)
    by = {c["index"]: c for c in out["candidates"]}
    assert out["picked"]["index"] == 1 and by[1]["rank"] == 1 and by[2]["excluded"] == {"reason": "VALIDATION_FAILED"} and by[2]["rank"] is None
    assert out["best_swing_cm_s"] == 540 and "vs #3" in out["picked"]["reason"]
    again = sel.rank([{k: c[k] for k in ("index", "seed", "status", "metrics")} for c in out["candidates"]], out["weights"], grip_on=True, swing_on=True)
    assert again["picked"] == out["picked"] and [c["score"] for c in again["candidates"]] == [c["score"] for c in out["candidates"]]
    # 가중치를 바꾸면(파지 0) 다른 후보가 될 수 있다 — 키 검사
    assert sel.rank(cands, {"grip": 0, "swing": 0}, grip_on=True, swing_on=True)["picked"]["index"] in (1, 3)
    assert sel.rank([cand(0, status="FAILED")], grip_on=True, swing_on=False)["picked"] is None


def test_ties_go_to_the_lower_index_and_weights_are_checked():
    out = sel.rank([cand(4, p90=3.0, pen=0), cand(2, p90=3.0, pen=0)], grip_on=False, swing_on=False)
    assert out["picked"]["index"] == 2 and "tie broken by index" in out["picked"]["reason"]
    assert "only candidate" in sel.rank([cand(0, p90=3.0)], grip_on=False, swing_on=False)["picked"]["reason"]
    for bad in ({"grip": -1}, {"speed": 1}, {"stance": True}, "heavy"):
        with pytest.raises(sel.WeightError):
            sel.check_weights(bad)
    assert sel.check_weights({"grip": 5})["grip"] == 5.0 and sel.check_weights(None) == sel.WEIGHTS
