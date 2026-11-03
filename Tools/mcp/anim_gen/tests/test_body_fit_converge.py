"""Phase 9-4c — 국소 수렴 패스(_converge · _bump · spline_fixed — U5-c) · 손 부근 마무리 증분 매끈화(_smooth_finish — U5-a) · smooth_speed 기본 켬 순수 테스트.

합성 C++ 모델 = body_fit_fixture. into_body 는 왼 위팔을 몸통 쪽으로 돌려 손 · 아래팔이 몸통 · 넓적다리에 든다."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm

ZERO = (0.0, 0.0, 0.0)


def _state(n):
    return [{"rot": {}, "trans": {}} for _ in range(n)]


def test_normalize_new_switches_and_smooth_speed_auto_is_on():
    cfg = bf.normalize(True)
    assert cfg["converge"] is True and cfg["finish_smooth"] is True and cfg["smooth_speed"] == "auto"
    for key in ("converge", "finish_smooth"):
        assert bf.normalize({key: False})[key] is False
        with pytest.raises(bf.BodyFitError) as exc:
            bf.normalize({key: 1})
        assert exc.value.field == f"fix.body.{key}"
    assert bf.smooth_mode("auto", None) == {"mode": "auto", "on": True, "reason": "default (9-4c — every clip)"}
    assert bf.smooth_mode("auto", {"rate": None})["reason"] == "fix.timing" and not bf.smooth_mode("off", None)["on"]


def test_spline_fixed_holds_pins_and_joins_free_frames_smoothly():
    n = 21
    series = [ZERO] * n
    series[10] = (0.0, 0.0, 1.0)
    act = [f == 10 for f in range(n)]
    fixed = [f == 10 or abs(f - 10) > 3 for f in range(n)]
    out = bf.spline_fixed(series, act, 4, bf.CONVERGE_FREE_WEIGHT, fixed)
    assert out[10][2] == pytest.approx(1.0, abs=1e-3) and all(abs(out[f][2]) < 1e-3 for f in range(n) if abs(f - 10) > 3)
    z = [out[f][2] for f in range(7, 14)]
    assert z[0] < z[1] < z[2] < z[3] and z[3] > z[4] > z[5] > z[6]   # 혹 — 고정값에서 양쪽으로 잦아든다
    # 루프 — 끝 근처 고정이 처음 쪽으로 감아 돈다 · 앞뒤 0 고정(블록)
    series = [ZERO] * n
    series[0] = (1.0, 0.0, 0.0)
    act = [f == 0 for f in range(n)]
    fixed = [f == 0 or min(f, n - f) > 3 for f in range(n)]
    loop = bf.spline_fixed(series, act, 4, bf.CONVERGE_FREE_WEIGHT, fixed, loop=True)
    assert loop[n - 1][0] > 0.1 and loop[1][0] == pytest.approx(loop[n - 1][0], abs=1e-6)
    series = [(0.5, 0.0, 0.0)] * 6
    pinned = bf.spline_fixed(series, [True] * 6, 2, None, [False] * 6, pins=(True, True))
    free = bf.spline_fixed(series, [True] * 6, 2, None, [False] * 6)
    assert pinned[0][0] < free[0][0] - 0.05 and pinned[-1][0] < free[-1][0] - 0.05


def _depth(solver, f, state):
    pose = solver.pose(f, state)[0]
    cand = sorted(set(solver._candidates(f, solver.model.poses[f])) | set(solver._candidates(f, pose)))
    return max((c[2] for c in solver._violations(f, state, cand)["clear"] if c[1] not in bf.HAND_MAPS), default=-math.inf)


def _spike_model(lo, hi):
    """한 구간(lo ~ hi)만 몸에 든 왼팔 — 관통 판정보다 깊고 마무리 상한(4 cm × scale)보다 얕은 각을 고른다."""
    for deg in (5.0, 4.5, 5.5):   # 합성 몸: 4° 2.1 · 5° 3.0 · 6° 4.1 cm(넓적다리)
        model = bm.BodyModel(fx.make_model(fx.bump({}, fx.into_body(deg), n=40, lo=lo, hi=hi, ramp=1)))
        s = bf.Solver(model, bf.normalize(True))
        d = _depth(s, lo, {"rot": {}, "trans": {}})
        if model.penetration_cm + 0.3 < d < bf.CONVERGE_MAX_CM * model.scale - 0.3:
            return model, s
    raise AssertionError("no angle gives a short, shallow penetration")


def test_converge_pins_a_short_penetration_and_tapers_the_neighbours():
    model, s = _spike_model(20, 20)
    out = s._converge(_state(40))
    cs = s.stats["converge"]
    assert cs["frames"] == [20] and cs["skipped"] == [] and cs["rounds"] >= 1
    assert _depth(s, 20, out[20]) <= model.penetration_cm
    width = int(round(bf.CONVERGE_TAPER_S * model.fps))
    moved = [s._size(out[f]) for f in range(40)]
    assert all(moved[f] > 0.0 for f in range(20 - width, 20 + width + 1))
    assert all(moved[f] == 0.0 for f in range(40) if abs(f - 20) > width)
    assert moved[20 - width] < moved[19] < moved[20] and moved[20 + width] < moved[21] < moved[20]


def test_converge_skips_long_runs_and_can_be_switched_off():
    model, s = _spike_model(14, 22)
    state = _state(40)
    out = s._converge(state)
    assert s.stats["converge"]["frames"] == [] and s.stats["converge"]["skipped"] and all(s._size(x) == 0.0 for x in out)
    off = bf.Solver(model, bf.normalize({"converge": False}))
    assert off._converge(state) is state


def test_smooth_finish_damps_alternating_finish_increments():
    # 마무리가 프레임마다 다른 몫으로 나눈 증분(+ − 번갈아) → 매끈화하면 진폭이 준다 · 처리 밖은 0 쪽으로 잦아든다 · 끄면 그대로
    model = bm.BodyModel(fx.make_model([fx.grip_front() for _ in range(30)]))
    s = bf.Solver(model, bf.normalize(True))
    cl = model.index["clavicle_l"]
    state = _state(30)
    out = [{"rot": {cl: (0.0, 0.0, math.radians(3.0 + (1.5 if f % 2 else -1.5)))}, "trans": {}} if 8 <= f <= 22 else {"rot": {}, "trans": {}}
           for f in range(30)]
    hs = {k: [] for k in bf.HAND_FINISH_KEYS}
    res = s._smooth_finish(state, out, [range(30)], set(range(8, 23)), None, hs)
    z = [res[f]["rot"].get(cl, ZERO)[2] for f in range(30)]
    swing_in = max(abs(out[f]["rot"][cl][2] - out[f + 1]["rot"][cl][2]) for f in range(10, 20))
    swing_out = max(abs(z[f] - z[f + 1]) for f in range(10, 20))
    assert swing_out < 0.3 * swing_in and all(abs(z[f] - math.radians(3.0)) < math.radians(1.0) for f in range(11, 20))
    assert hs["smooth_pinned"] == []   # 손가락 뿌리가 없으면(손목 상한 없음) 고정할 프레임이 없다


def test_hand_finish_smoothing_keeps_the_wrist_caps():
    frames = fx.bump(fx.grip_close(), fx.grip_close({"upperarm_l": (-30.0, 0.0, 35.0)}))
    model = bm.BodyModel(fx.make_model(frames))
    fingers = {"l": "middle_01_l", "r": "middle_01_r"}
    out = {}
    for flag in (True, False):
        cfg = bf.normalize({"finish_smooth": flag})
        out[flag] = bf.solve(model, cfg, grip=bf.grip_weights(bf.Rig(model), cfg["grip"], model.scale), fingers=fingers)
    on = out[True]
    assert "smooth_pinned" in on["stats"]["hand_finish"] and on["deltas"] != out[False]["deltas"]
    assert on["wrist_bend"]["over_cap_frames"] == 0 and on["wrist_bend"]["lead"]["over_cap_frames"] == 0
