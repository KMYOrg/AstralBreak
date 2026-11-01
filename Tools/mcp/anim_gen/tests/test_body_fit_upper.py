"""Phase 8-4f — 위팔 마무리(clearance.upper_arm: cap): 위팔이 상한보다 깊이 몸에 든 프레임만 팔꿈치를 어깨 ↔ 손목 축으로 돌린다(손 고정)."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm

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


def test_cap_pulls_the_upper_arm_out_with_the_hands_untouched():
    model, s_nw, r_nw = run("no_worse")
    _, s_cap, r_cap = run("cap")
    nw, cap = r_nw["predicted"]["pairs"]["l|upper_arm|chest"], r_cap["predicted"]["pairs"]["l|upper_arm|chest"]
    assert nw["depth_max"] > 4.0 * model.scale and cap["depth_max"] < nw["depth_max"] - 0.3
    assert "upper_finish" not in r_nw["stats"]
    uf = r_cap["stats"]["upper_finish"]
    assert uf["frames"] and not uf["blocked"] and 0.0 < uf["deg_max"] <= bf.UPPER_FINISH_MAX_DEG and uf["elbow_cm_max"] > 0.5
    rig = s_cap.rig
    for f in range(len(r_cap["poses"])):
        for side in ("l", "r"):
            wb = rig.arms[side]["wrist"]
            assert bf._norm(bf._sub(r_cap["poses"][f][wb][1], r_nw["poses"][f][wb][1])) < 1e-6
    # 램프 밖(필요 프레임 ± UPPER_FINISH_RAMP 밖)은 그대로 — 바뀐 프레임은 위팔이 든 구간 둘레만
    changed = set(uf["frames"])
    deep = {f for f, d in enumerate(bf.measure(model, r_nw["poses"], s_nw)["series"][("l", "upper_arm", "chest")]) if d is not None and d > 4.0 * model.scale}
    assert deep and changed <= {g for f in deep for g in range(f - bf.UPPER_FINISH_RAMP, f + bf.UPPER_FINISH_RAMP + 1)}
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


def test_a_higher_cap_does_less_and_the_wrist_rule_bounds_the_angle(monkeypatch):
    _, _, r4 = run("cap")
    _, _, r45 = run("cap", upper_cap_cm=4.5)
    assert r45["stats"]["upper_finish"]["deg_max"] <= r4["stats"]["upper_finish"]["deg_max"]
    # 손가락 뿌리가 없으면 손목 굽힘을 못 재니 각 ≤ UPPER_FINISH_WRIST_DEG
    _, _, r_nf = run("cap", fingers=None)
    assert r_nf["stats"]["upper_finish"]["deg_max"] <= bf.UPPER_FINISH_WRIST_DEG + 1e-9
    # 손목 허용 0 이면 각이 줄거나 막힌다
    monkeypatch.setattr(bf, "UPPER_FINISH_WRIST_DEG", 0.0)
    _, _, r_w0 = run("cap")
    uf = r_w0["stats"]["upper_finish"]
    assert uf["deg_max"] <= r4["stats"]["upper_finish"]["deg_max"] and (uf["blocked"] or uf["deg_max"] < r4["stats"]["upper_finish"]["deg_max"] + 1e-9)


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


def test_one_direction_per_group_so_the_ramp_never_flips_sign():
    seen = []
    orig = bf.Solver._swivel_state

    def spy(self, f, state, side, deg):
        seen.append((side, f, deg))
        return orig(self, f, state, side, deg)

    bf.Solver._swivel_state = spy
    try:
        run("cap")
    finally:
        bf.Solver._swivel_state = orig
    signs = {math.copysign(1.0, d) for side, f, d in seen if side == "l"}
    assert seen and len(signs) == 1
