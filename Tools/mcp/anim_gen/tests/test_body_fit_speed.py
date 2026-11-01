"""Phase 8-4e — 빠른 구간 매끈화(fix.body.smooth_speed): 손이 빠른 프레임은 관통 몫 스플라인 폭 · 재검사 ±1 이웃 몫을 k 배로 줄인다. 순수 테스트.
on = 켬, auto = 같은 Job 에 fix.timing 이 있을 때만(Job 이 smooth_mode 로 정해 solve 에 넘긴다 — 요청만 보면 끔), off = 고정 폭.

합성 C++ 모델 = body_fit_fixture. grip_front → grip_close bump 는 위팔이 프레임마다 18° 씩 돌아 손이 SPEED_REF_CM 보다 빠르다."""
from __future__ import annotations

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm


def solve(frames, cfg=None):
    model = bm.BodyModel(fx.make_model(frames))
    cfg = cfg or bf.normalize(True)
    rig = bf.Rig(model)
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    return model, bf.solve(model, cfg, grip=grip)


def _spike(n=41, at=20):
    series, active = [(0.0, 0.0, 0.0)] * n, [False] * n
    series[at], active[at] = (0.0, 0.0, 1.0), True
    return series, active


def test_normalize_smooth_speed_and_the_auto_rule():
    assert bf.normalize(True)["smooth_speed"] == "auto" and all(bf.normalize({"smooth_speed": v})["smooth_speed"] == v for v in ("on", "off"))
    with pytest.raises(bf.BodyFitError) as exc:
        bf.normalize({"smooth_speed": "fast"})
    assert exc.value.field == "fix.body.smooth_speed" and exc.value.reason == "BAD_FIELD"
    assert bf.smooth_mode("auto", {"rate": None})["on"] and not bf.smooth_mode("auto", None)["on"]
    assert bf.smooth_mode("on", None) == {"mode": "on", "on": True, "reason": "requested on"} and not bf.smooth_mode("off", {"x": 1})["on"]


def test_unit_factors_match_the_fixed_width():
    # k = 1 은 고정 폭과 같은 풀이(포락선 거리를 폭 단위로 더해 가는 것만 다르다 — 부동소수 오차) — 열린 열 · 루프 · 목표 블록
    series, active = _spike()
    series[22], active[22] = (0.3, 0.0, 0.8), True
    ones = [1.0] * len(series)
    for a, b in ((bf.spline(series, active, 4), bf.spline(series, active, 4, k=ones)),
                 (bf.spline(series, active, 4, loop=True), bf.spline(series, active, 4, loop=True, k=ones)),
                 (bf.spline_block(series, active, 4, True, True), bf.spline_block(series, active, 4, True, True, k=ones))):
        assert max(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q)) < 1e-9


def test_narrow_factor_keeps_an_isolated_spike_and_stays_local():
    # 빠른 프레임(k 0.25 — 폭 6 → 1.5 프레임)은 고립 정점을 덜 묽히고 꼬리가 짧다(포락선 = 지나온 프레임 폭의 2 배에서 0)
    series, active = _spike()
    k = [0.25 if 14 <= f <= 26 else 1.0 for f in range(41)]
    fixed = bf.spline(series, active, 4)
    fast = bf.spline(series, active, 4, k=k)
    assert fast[20][2] > fixed[20][2] + 0.2
    assert all(fast[f] == (0.0, 0.0, 0.0) for f in range(41) if abs(f - 20) >= 3) and fixed[24][2] > 0.0


def test_speed_factors_none_when_slow_and_clamped_when_fast():
    slow = bm.BodyModel(fx.make_model(fx.bump({}, fx.into_body(18.0), n=40, lo=16, hi=21, ramp=6)))
    assert bf.speed_factors(bf.Rig(slow), False) is None   # 손 ≤ SPEED_REF_CM — 고정 폭(이전 풀이와 비트 같다)
    model = bm.BodyModel(fx.make_model(fx.bump(fx.grip_front(), fx.grip_close())))
    k = bf.speed_factors(bf.Rig(model), False)
    fast = [f for f, x in enumerate(k) if x < 1.0]
    assert fast and min(k) >= bf.SPEED_K_MIN and all(x == 1.0 for f, x in enumerate(k) if f < 6 or f > 23)


def test_neighbor_share_scales_on_fast_frames_only():
    model = bm.BodyModel(fx.make_model(fx.bump(fx.grip_front(), fx.grip_close())))
    solver = bf.Solver(model, bf.normalize({"smooth_speed": "on"}))
    inc = {"rot": {3: (0.1, 0.0, 0.0)}, "trans": {}}
    f = min(range(len(solver.smooth_k)), key=solver.smooth_k.__getitem__)
    assert solver._neighbor_share(f, inc)["rot"][3] == pytest.approx((0.1 * solver.smooth_k[f], 0.0, 0.0))
    assert solver._neighbor_share(0, inc) is inc   # 느린 프레임 — 같은 증분(지금 규칙)
    for cfg, flag in ((bf.normalize({"smooth_speed": "off"}), None), (bf.normalize(True), None), (bf.normalize(True), False)):
        off = bf.Solver(model, cfg, smooth_fast=flag)   # 끔 · Job 밖의 auto · Job 이 끈 auto
        assert off.smooth_k is None and off._neighbor_share(f, inc) is inc
    assert bf.Solver(model, bf.normalize(True), smooth_fast=True).smooth_k == solver.smooth_k   # Job 이 켠 auto(fix.timing)


def test_on_changes_only_fast_clips_and_off_auto_are_the_fixed_width(monkeypatch):
    frames = fx.bump(fx.grip_front(), fx.grip_close())
    _, off = solve(frames, bf.normalize({"smooth_speed": "off"}))
    _, auto = solve(frames)
    _, on = solve(frames, bf.normalize({"smooth_speed": "on"}))
    assert on["stats"]["smooth_fast"]["frames"] > 0 and "smooth_fast" not in off["stats"] and "smooth_fast" not in auto["stats"]
    assert on["deltas"] != off["deltas"] and auto["deltas"] == off["deltas"]
    monkeypatch.setattr(bf, "SPEED_REF_CM", 1e9)   # 어떤 프레임도 빠르지 않다 → 고정 폭 · 같은 이웃 몫
    _, never = solve(frames, bf.normalize({"smooth_speed": "on"}))
    assert never["deltas"] == off["deltas"] and "smooth_fast" not in never["stats"]
