"""Phase 8-4f · 9-4b — 위팔 상한(clearance.upper_arm: cap): 위팔이 상한보다 깊이 몸에 든 프레임을 손 부근 마무리(_finish_hands — 쇄골 · 팔꿈치 궤도 ·
손목, 손 붙들기 · keep 과 같은 층)가 상한 쪽으로 뺀다. 궤도 격자(_upper_angle · _swivel_state — 8-4f)는 GN 이 못 맞춘 프레임의 둘째 출발점."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import motion_metrics as mm

FINGERS = {"l": "middle_01_l", "r": "middle_01_r"}


def _rv(a, b):
    """a → b 최소 회전(회전 벡터°)."""
    a, b = bf._unit(a), bf._unit(b)
    ax = bf._cross(a, b)
    return bf._scale(bf._unit(ax), math.degrees(math.atan2(bf._norm(ax), bf._dot(a, b))))


def cross_chest() -> dict:
    """왼 위팔이 가슴 앞을 가로질러(어깨 (18, 0, 140) → 팔꿈치 (−5, 11, 137)) 몸통 원통에 ≈ 4.9 cm 들고, 아래팔 · 손은 앞으로(+Y) 뻗어 몸 밖."""
    r_up = _rv((0.0, 0.0, -1.0), (-0.9, 0.44, -0.1))
    r_low = _rv((0.0, 0.0, -1.0), bm.qrot(bm.qconj(bm.from_rotvec_deg(r_up)), (0.0, 1.0, 0.0)))
    return {"upperarm_l": r_up, "lowerarm_l": r_low}


def run(mode: str, frames=None, fingers=FINGERS, **cfg):
    model = bm.BodyModel(fx.make_model(frames or fx.bump({}, cross_chest(), n=24, lo=8, hi=15, ramp=5)))
    raw = {"clearance": {"upper_arm": mode, **cfg}}
    solver = bf.Solver(model, bf.normalize(raw), fingers=fingers)
    return model, solver, solver.run()


def test_upper_arm_defaults_to_cap_and_rejects_bad_values():
    c = bf.normalize(True)["clearance"]
    assert c["upper_arm"] == "cap" and c["upper_cap_cm"] == 4.0
    with pytest.raises(bf.BodyFitError) as e:
        bf.normalize({"clearance": {"upper_arm": "target"}})
    assert e.value.field == "fix.body.clearance.upper_arm"
    for bad in (0.5, 25.0, "4"):
        with pytest.raises(bf.BodyFitError) as e:
            bf.normalize({"clearance": {"upper_cap_cm": bad}})
        assert e.value.field == "fix.body.clearance.upper_cap_cm"


def test_swivel_keeps_the_hand_and_turns_the_elbow_around_the_shoulder_wrist_line():
    model = bm.BodyModel(fx.make_model([cross_chest()] * 3))
    solver = bf.Solver(model, bf.normalize(True), fingers=FINGERS)
    arm = solver.rig.arms["l"]
    zero = {"rot": {}, "trans": {}}
    p0 = solver.pose(1, zero)[0]
    st = solver._swivel_state(1, zero, "l", 20.0)
    p1 = solver.pose(1, st)[0]
    s, w, e0, e1 = p0[arm["upper"]][1], p0[arm["wrist"]][1], p0[arm["elbow"]][1], p1[arm["elbow"]][1]
    assert bf._norm(bf._sub(p1[arm["wrist"]][1], w)) < 1e-6 and bf._norm(bf._sub(p1[arm["upper"]][1], s)) < 1e-6
    q0, q1 = p0[arm["wrist"]][0], p1[arm["wrist"]][0]
    assert abs(abs(bf._dot(q0[:3], q1[:3]) + q0[3] * q1[3]) - 1.0) < 1e-9                    # 손 회전 그대로
    mid = model.index["middle_01_l"]
    assert bf._norm(bf._sub(p1[mid][1], p0[mid][1])) < 1e-6
    u = bf._unit(bf._sub(w, s))
    off = lambda e: bf._norm(bf._sub(bf._sub(e, s), bf._scale(u, bf._dot(bf._sub(e, s), u))))  # noqa: E731
    assert abs(off(e1) - off(e0)) < 1e-6 and bf._norm(bf._sub(e1, e0)) > 1.0                    # 축에서 같은 거리 · 팔꿈치는 움직임
    # 상태로 넣은 회전 = 컴포넌트 자세에서 바로 돌린 것
    direct = solver._swivel_pose(p0, solver._upper_ctx("l")["bones"], s, u, 20.0)
    for b in solver._upper_ctx("l")["bones"]:
        assert bf._norm(bf._sub(direct[b][1], p1[b][1])) < 1e-6


def test_cap_pulls_the_upper_arm_toward_the_cap_with_the_hands_held():
    # 9-4b — 위팔 상한은 keep · 손 붙들기와 같은 층(사용자 결정 — 30 이면 검 선택 keep 위치 1.5 → 3.2 cm): 관절 충실도와 맞서 상한 쪽으로 줄이고, 다 못
    # 뺀 프레임은 blocked · remain_cm_max 로 남긴다(Job UPPER_ARM_REMAINS). 8-4f 의 손 고정 궤도는 이 장면을 상한까지 뺐다(4.26 → < 3.96)
    model, s_nw, r_nw = run("no_worse")
    _, s_cap, r_cap = run("cap")
    nw, cap = r_nw["predicted"]["pairs"]["l|upper_arm|chest"], r_cap["predicted"]["pairs"]["l|upper_arm|chest"]
    assert nw["depth_max"] > 4.0 * model.scale and cap["depth_max"] < nw["depth_max"] - 0.1
    assert "upper_finish" not in r_nw["stats"]
    uf = r_cap["stats"]["upper_finish"]
    deep = {f for f, d in enumerate(bf.measure(model, r_nw["poses"], s_nw)["series"][("l", "upper_arm", "chest")]) if d is not None and d > 4.0 * model.scale}
    assert deep and deep <= set(uf["frames"]) and 0.0 < uf["deg_max"] and uf["elbow_cm_max"] > 0.2
    assert set(uf["blocked"]) <= set(uf["frames"]) and uf["remain_cm_max"] == pytest.approx(cap["depth_max"], abs=0.05)
    # 손은 붙들린다(층 hold) · 손 부근 마무리가 처리하지 않은 프레임은 no_worse 와 같다 — 9-4c 마무리 매끈화의 꼬리(처리 프레임 ± 2·폭) 밖에서
    rig = s_cap.rig
    done = set(r_cap["stats"]["hand_finish"]["frames"])
    reach = 2.0 * bf.SPLINE_WIDTH * max(1, int(round(bf.FINISH_SMOOTH_S * model.fps)))
    for f in range(len(r_cap["poses"])):
        for side in ("l", "r"):
            wb = rig.arms[side]["wrist"]
            assert bf._norm(bf._sub(r_cap["poses"][f][wb][1], r_nw["poses"][f][wb][1])) < 0.3
        if all(abs(f - g) > reach for g in done):
            assert all(bf._norm(bf._sub(a[1], b[1])) < 1e-9 for a, b in zip(r_cap["poses"][f], r_nw["poses"][f]))
    # 손 · 아래팔 쌍은 관통이 생기지 않는다
    for key, st in r_cap["predicted"]["pairs"].items():
        if key.split("|")[1] in ("hand", "forearm"):
            assert st["frames_over_penetration_pct"] == r_nw["predicted"]["pairs"][key]["frames_over_penetration_pct"]


def test_cap_leaves_a_shallow_upper_arm_alone_and_off_modes_skip_the_finish():
    shallow = fx.bump({}, {"upperarm_l": (0.0, -10.0, 0.0)}, n=20, lo=7, hi=12, ramp=4)
    _, _, r_cap = run("cap", frames=shallow)
    _, _, r_nw = run("no_worse", frames=shallow)
    assert r_cap["stats"]["upper_finish"]["frames"] == [] and r_cap["deltas"] == r_nw["deltas"]
    _, _, r_off = run("off")
    assert "upper_finish" not in r_off["stats"]


def test_a_higher_cap_does_less_and_the_free_wrist_is_capped_at_the_state():
    _, _, r_nw = run("no_worse")
    _, _, r4 = run("cap")
    _, _, r45 = run("cap", upper_cap_cm=4.5)
    depth = lambda r: r["predicted"]["pairs"]["l|upper_arm|chest"]["depth_max"]  # noqa: E731
    assert r45["stats"]["upper_finish"]["deg_max"] <= r4["stats"]["upper_finish"]["deg_max"] + 1e-9 and depth(r45) >= depth(r4) - 1e-6
    # 손가락 뿌리가 없어도 위팔은 줄인다(손목 굽힘을 못 재 손목 상한만 꺼진다)
    _, _, r_nf = run("cap", fingers=None)
    assert depth(r_nf) < depth(r_nw) - 0.1
    # 손 부근 마무리가 연 상한 없는 손목(파지 밖)은 max(그 상태, 원래 + FREE_WRIST_DEG) 위로 굽히면 보조 손목 상한과 같은 층의 잔차
    model = bm.BodyModel(fx.make_model([cross_chest()] * 3))
    s = bf.Solver(model, bf.normalize(True), fingers=FINGERS)
    br = s.bend_rig
    assert br["side"] == "l" and br["caps"] == [None] * 3   # 파지 프레임 없음
    s.hand_mode = True
    s._state_cap = {"l": br["bend0"][1] + math.radians(bf.FREE_WRIST_DEG)}
    state = {"rot": {model.index["hand_l"]: (math.radians(12.0), 0.0, 0.0)}, "trans": {}}
    bend = bf.WeaponRig.bend(s.pose(1, state)[0], br["elbow"], br["wrist"], br["middle"])
    ev = s.evaluate(1, state, {"rot": {}, "trans": {}}, {"bend"}, [], s._joints(1))
    over = bend - s._state_cap["l"]
    assert over > 0.0 and ev["cost"] == pytest.approx((10.0 * bf.HAND_TIER["off_bend"] * over * bf.ROT_CM) ** 2, rel=1e-4)
    s.hand_mode = False
    assert s.evaluate(1, state, {"rot": {}, "trans": {}}, {"bend"}, [], s._joints(1))["cost"] == 0.0   # 본 풀이 · 무기 마무리는 파지 프레임만


def test_the_off_hand_wrist_cap_of_a_grip_frame_bounds_the_swivel_first():
    model = bm.BodyModel(fx.make_model([cross_chest()] * 3))
    solver = bf.Solver(model, bf.normalize(True), fingers=FINGERS)
    zero = {"rot": {}, "trans": {}}
    pose = solver.pose(1, zero)[0]
    cap = 4.0 * model.scale
    ctx = solver._upper_ctx("l")
    arm, mid = ctx["arm"], ctx["middle"]
    bend = lambda p: bf.WeaponRig.bend(p, arm["elbow"], arm["wrist"], mid)  # noqa: E731
    free = solver._upper_angle(1, pose, cap, ctx)
    assert free["over"] and free["wrist_cap"] == pytest.approx(bend(pose) + math.radians(bf.UPPER_FINISH_WRIST_DEG))
    # 보조 손목(왼손) 파지 프레임 — bend_cap(원래 + 2°)이 먼저, 고른 각도 그 상한 안
    solver.bend_rig = {"wrist": arm["wrist"]}
    solver.bend_cap = [None, bend(pose) + math.radians(bf.BEND_KEEP_TOL_DEG), None]
    held = solver._upper_angle(1, pose, cap, ctx)
    assert held["wrist_cap"] == pytest.approx(bend(pose) + math.radians(bf.BEND_KEEP_TOL_DEG))
    turned = lambda d: bend(solver._swivel_pose(pose, ctx["bones"], free["s"], free["u"], d))  # noqa: E731
    assert any(turned(free[sign]["deg"]) > held["wrist_cap"] + 1e-6 for sign in (1.0, -1.0))   # + 10° 로 고른 각은 상한을 넘는다
    for sign in (1.0, -1.0):
        assert turned(held[sign]["deg"]) <= held["wrist_cap"] + 1e-9
    # 상한이 없는 프레임 · 반대 팔은 그대로 원래 + UPPER_FINISH_WRIST_DEG
    assert solver._upper_angle(0, solver.pose(0, zero)[0], cap, ctx)["wrist_cap"] == pytest.approx(
        bend(solver.pose(0, zero)[0]) + math.radians(bf.UPPER_FINISH_WRIST_DEG))
    r = solver._upper_ctx("r")
    rb = bf.WeaponRig.bend(pose, r["arm"]["elbow"], r["arm"]["wrist"], r["middle"])
    assert solver._upper_angle(1, pose, cap, r)["wrist_cap"] == pytest.approx(rb + math.radians(bf.UPPER_FINISH_WRIST_DEG))


def test_the_elbow_path_stays_smooth():
    # 9-4b — 손 부근 마무리는 프레임마다 GN(시간 연속 = 앞 프레임 증분, 꼬리는 증분이 잦아들 때까지) — 8-4f 의 묶음 방향 · ±4 프레임 램프 대신. 팔꿈치
    # 궤적 떨림이 통합 기준(c4_zigzag — ≤ max(× 1.1, + 0.3)) 안이다(묶음마다 방향을 고르던 처음 판은 s25 떨림 2.17 → 3.00)
    model, _, r_nw = run("no_worse")
    _, _, r_cap = run("cap")
    eb = model.index["lowerarm_l"]
    zz = lambda r: mm.zigzag([[list(p[eb][1]) for p in r["poses"]]], model.times, model.scale)["max"]  # noqa: E731
    assert zz(r_cap) <= max(zz(r_nw) * 1.1, zz(r_nw) + 0.3)
