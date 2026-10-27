"""흐느적 보정(fix.timing) — 지침서 §14 Phase 8 '8-3'.

순수(timing.py): 요청 정규화 · 구간 탐지(핵심 · 휘두름 · 정지 머리 / 꼬리) · rate(목표 정점 · 상한 · 이미 빠름) · 배율 곡선(연속 — 속도 단차
없음, 새 길이 정수 프레임) · op = trim 하나 + time_warp 하나 · 계획 warp = C++ trim · time_warp 의미로 다시 돈 결과(simulate) · Hermite 사상과 역.
계획(재사용 경로 = 미리보기까지 · 에디터 없음 · 생성 경로 = 실행 때 · 편집 앞) · 실행(Job timing · 최종 이름 · TIMING_CHANGED_LENGTH ·
DURATION_MISMATCH 없음 · 휘두름 없음 = 항등 trim · 캡처 비교 생략).
8-3 후속(2026-10-27) 기대된 변화: retime 조각 · ramp_pieces 테스트 → 배율 곡선 · time_warp 테스트.
"""
from __future__ import annotations

import pytest

from anim_gen import timing
from conftest import AIM_IDLE, ATTACK3, OUT, VESPER_MESH, request
from test_blender import bl, bvh_request, generate, plan, status  # noqa: F401 — bl 는 픽스처

FPS = 30.0
HANDS = ("hand_l", "hand_r")
BODY = ["foot_l", "foot_r", "hand_l", "hand_r", "thigh_l", "thigh_r"]


def series(head=12, rise=6, peak=300.0, core=10, fall=6, recovery=0, tail=45, second=None):
    """1/30 초 표본의 손 속도: 정지 머리 → 오름 → 정점 유지 → 내림 → (복귀 60 cm/s) → 정지 꼬리. second = (틈, 길이)면 두 번째 정점."""
    hand = [0.0] * head
    hand += [peak * (k + 1) / (rise + 1) for k in range(rise)]
    hand += [peak] * core
    if second:
        gap, length = second
        hand += [peak * 0.3] * gap + [peak] * length
    hand += [peak * (fall - k) / (fall + 1) for k in range(fall)]
    hand += [60.0] * recovery
    hand += [2.0] * tail
    return hand


def profile_of(hand: list[float], body_extra: float = 0.0) -> dict:
    n = len(hand)
    speeds = {"hand_r": hand, "hand_l": [x * 0.5 for x in hand]}
    for b in BODY:
        speeds.setdefault(b, [body_extra] * n)
    return {"times": [round((i + 1) / FPS, 4) for i in range(n)], "frames_per_sample": 1, "speed_cm_s": speeds}


def run_plan(hand, params=None, scale=1.0, **kw):
    params = params or timing.normalize(True)
    return timing.plan(profile_of(hand, **kw), hands=HANDS, body=BODY, scale=scale, fps=FPS, length=len(hand) / FPS, params=params)


# ---- 순수 ----
def test_normalize_defaults_and_off():
    cfg = timing.normalize(True)
    assert cfg == {**timing.DEFAULTS, "target_peak_cm_s": 1200.0, "max_rate": 2.0, "recovery_rate": 1.5}
    assert cfg["still"]["trim_head"] is True and cfg["still"]["keep_head_s"] == 0.2 and cfg["still"]["keep_tail_s"] == 0.3
    assert timing.normalize({"mode": "off"}) is None and timing.normalize(None) is None and timing.normalize(False) is None
    assert cfg["antialias"] == 1.0 and cfg["swing"] == {"core_ratio": 0.5, "edge_ratio": 0.2}
    assert timing.normalize({"max_rate": 1.5, "antialias": 0})["antialias"] == 0.0


@pytest.mark.parametrize("raw, field", [
    ({"speed": 2}, "fix.timing.speed"),
    ({"max_rate": 5}, "fix.timing.max_rate"),
    ({"recovery_rate": 0.5}, "fix.timing.recovery_rate"),
    ({"antialias": 2}, "fix.timing.antialias"),
    ({"swing": {"edge_ratio": 0.6}}, "fix.timing.swing.edge_ratio"),
    ({"swing": {"ramp_pieces": 3}}, "fix.timing.swing.ramp_pieces"),   # 계단 램프 조각 수 — 연속 램프로 바꿔 없어졌다
    ({"still": {"keep": 1}}, "fix.timing.still.keep"),
    ({"still": {"trim_tail": "yes"}}, "fix.timing.still.trim_tail"),
    ({"mode": "on"}, "fix.timing.mode"),
    ("fast", "fix.timing"),
])
def test_normalize_rejects(raw, field):
    with pytest.raises(timing.TimingError) as info:
        timing.normalize(raw)
    assert info.value.args[0] == field


def test_one_swing_is_sped_up_and_still_ends_are_trimmed():
    hand = series(head=12, peak=300.0, tail=45)
    p = run_plan(hand)
    assert p["applied"] and p["reason"] is None
    assert p["signal"]["peak_raw_cm_s"] == 300.0 and p["rate"] == 2.0     # 1200 / ≈300 → 상한 2.0
    w = p["windows"]
    assert w["head"][0] == 0.0 and w["tail"][1] == round(len(hand) / FPS, 4)
    assert w["swing"][0] <= w["core"][0] < w["core"][1] <= w["swing"][1]
    # 머리 0.4초 → 0.2초만(휘두름 시작을 넘지 않게), 꼬리 → 0.3초만
    assert p["cut"]["head_s"] == pytest.approx(min(w["head"][1] - 0.2, w["swing"][0]), abs=1e-3) and p["cut"]["head_s"] > 0
    assert p["cut"]["tail_s"] == pytest.approx(w["tail"][0] + 0.3, abs=1e-3)
    # op = 머리 · 꼬리 trim 하나 → 자른 타임라인 기준 time_warp 하나(antialias 실음)
    ops = p["ops"]
    assert ops[0] == {"op": "trim", "start": p["cut"]["head_s"], "end": p["cut"]["tail_s"]} and [o["op"] for o in ops] == ["trim", "time_warp"]
    warp = ops[1]
    assert warp["knots"][0] == [0.0, 0.0] and warp["knots"][-1][0] == pytest.approx(p["cut"]["tail_s"] - p["cut"]["head_s"], abs=1e-4)
    assert warp["antialias"] == 1.0 and len(warp["rates"]) == len(warp["knots"]) and warp["knots"] == p["knots"]
    core = next(m for m in p["profile"] if m["kind"] == "core_start")
    assert core["rate"] == pytest.approx(2.0, rel=0.05) and core["rate"] <= 2.0   # 정수 프레임 올림 — 짧은 합성 클립은 몇 % 낮다


def test_rate_profile_is_continuous_whole_frames_and_capped():
    for hand in (series(), series(peak=400.0, core=29, recovery=20, tail=40), series(head=3, rise=1, fall=1, tail=5)):
        p = run_plan(hand)
        warp = p["ops"][-1]
        assert warp["op"] == "time_warp"
        # 새 길이 = 정수 프레임(올림 — 배율이 상한을 넘지 않는다)
        assert abs(warp["knots"][-1][1] * FPS - round(warp["knots"][-1][1] * FPS)) < 1e-3
        assert max(warp["rates"]) <= 2.0 + 1e-6 and min(warp["rates"]) > 0.9
        # 매듭 사이 할선 = 두 끝 배율 평균(선형 램프 — Hermite 가 2차 이하) · 단조 조건 여유
        for (s0, d0), (s1, d1), r0, r1 in zip(warp["knots"], warp["knots"][1:], warp["rates"], warp["rates"][1:]):
            assert (s1 - s0) / (d1 - d0) == pytest.approx((r0 + r1) / 2, rel=1e-4)
        # 출력 프레임 사이 배율 변화 — 램프가 최소 1 프레임이라도 상한 안(계단 retime 은 조각 경계에서 0.3 ~ 1.0 씩 튀었다)
        sim = timing.simulate(p["ops"], len(hand) / FPS, FPS)
        assert timing.max_rate_step(sim["source_times"], FPS) <= 1.0 + 1e-6
    p = run_plan(series(peak=400.0, core=29, recovery=20, tail=40))   # 복귀 60 cm/s < 휘두름 끝 기준 0.2 × 400
    assert p["rate"] == 2.0 and p["recovery_rate"] == 1.5 and [m["kind"] for m in p["profile"]][-2:] == ["recovery_end", "end"]
    sim = timing.simulate(p["ops"], len(series(peak=400.0, core=29, recovery=20, tail=40)) / FPS, FPS)
    # 램프 인 4 원 프레임(1 → 2, 출력 ≈ 2.7 프레임) — 출력 프레임마다 ≈ (2 − 1) / 2.7
    ramp = (0.5 - 0.3667) * FPS / 1.5
    assert timing.max_rate_step(sim["source_times"], FPS) <= (p["rate"] - 1.0) / ramp + 0.05


def test_old_retime_pieces_had_speed_steps():
    """처음 판(구간 등속 retime 조각)의 속도 단차 — 같은 배율을 계단으로 내면 조각 경계에서 배율이 한 프레임에 크게 바뀐다(비교 기준)."""
    ops = [{"op": "retime", "start": 0.6, "end": 1.0, "rate": 2.0}, {"op": "retime", "start": 0.4, "end": 0.6, "rate": 1.5}]
    sim = timing.simulate(ops, 2.0, FPS)
    assert timing.max_rate_step(sim["source_times"], FPS) >= 0.5


def test_warp_curve_is_the_cpp_hermite():
    curve = timing.WarpCurve([[0.0, 0.0], [0.2, 0.2 / 1.5], [1.0, 0.2 / 1.5 + 0.4]], [1.0, 2.0, 2.0])
    assert curve.rate(0.0) == pytest.approx(1.0) and curve.rate(0.2 / 1.5) == pytest.approx(2.0) and curve.rate(0.5) == pytest.approx(2.0)
    assert curve.rate(0.1 / 1.5) == pytest.approx(1.5, abs=0.02)            # 램프 가운데 — 배율이 출력 시각에 선형
    for u in (0.0, 0.05, 0.13, 0.3, 0.5333):
        assert curve.forward(curve.map(u)) == pytest.approx(u, abs=1e-9)
    pchip = timing.WarpCurve([[0.0, 0.0], [0.5, 0.4], [1.0, 0.5]])          # 기울기 없이 — 단조
    xs = [pchip.map(k / 100) for k in range(51)]
    assert all(b >= a - 1e-12 for a, b in zip(xs, xs[1:])) and xs[-1] == pytest.approx(1.0)


def test_simulate_checks_time_warp_knots():
    with pytest.raises(timing.TimingError):
        timing.simulate([{"op": "time_warp", "knots": [[0.0, 0.0], [0.5, 0.5]]}], 1.0, FPS)    # 끝 ≠ 길이
    sim = timing.simulate([{"op": "time_warp", "knots": [[0.0, 0.0], [1.0, 0.5]], "rates": [2.0, 2.0]}], 1.0, FPS)
    assert sim["length"] == pytest.approx(0.5) and sim["source_times"][5] == pytest.approx(10 / FPS)


def test_plan_warp_matches_the_cpp_semantics():
    """계획의 warp(원 시각 → 새 시각, Hermite) = op 를 C++ trim · time_warp 의미로 차례로 돈 결과의 키별 원 시각."""
    for hand in (series(), series(peak=400.0, recovery=20), series(head=3, tail=5), series(second=(8, 6))):
        p = run_plan(hand)
        sim = timing.simulate(p["ops"], len(hand) / FPS, FPS)
        assert sim["length"] == pytest.approx(p["length"]["after"], abs=1e-4)
        for key, source_t in enumerate(sim["source_times"]):
            assert timing.warp_time(p["warp"], source_t) == pytest.approx(key / FPS, abs=2e-3)


def test_two_strikes_make_one_core():
    p = run_plan(series(second=(8, 6)))
    one = run_plan(series())
    assert p["windows"]["core"][1] - p["windows"]["core"][0] > one["windows"]["core"][1] - one["windows"]["core"][0] + 0.4


def test_fast_swing_without_still_ends_is_left_alone():
    p = run_plan(series(head=2, peak=1500.0, tail=4))
    assert not p["applied"] and p["reason"] == "ALREADY_FAST" and p["ops"] == [{"op": "trim"}]
    assert p["length"]["after"] == p["length"]["before"]


def test_fast_swing_still_trims_a_long_tail_but_keeps_the_recovery():
    p = run_plan(series(head=2, peak=1500.0, recovery=20, tail=40))
    assert p["applied"] and p["rate"] == 1.0 and p["knots"] is None
    assert [o["op"] for o in p["ops"]] == ["trim"] and "end" in p["ops"][0]


def test_no_swing_gives_an_identity_trim():
    p = run_plan([10.0] * 60)
    assert not p["applied"] and p["reason"] == "NO_SWING" and p["ops"] == [{"op": "trim"}] and p["windows"]["swing"] is None


def test_scale_divides_the_signal():
    p = run_plan(series(peak=630.0), scale=1.05)   # 대상 600 cm/s 상당 — 1200 / 600 = 2.0
    assert p["signal"]["peak_raw_cm_s"] == 600.0 and p["rate"] == 2.0


def test_options_turn_trims_off():
    cfg = timing.normalize({"still": {"trim_head": False, "trim_tail": False}, "recovery_rate": 1.0})
    p = run_plan(series(), params=cfg)
    assert [o["op"] for o in p["ops"]] == ["time_warp"] and p["cut"] == {"head_s": 0.0, "tail_s": round(len(series()) / FPS, 4)}


def test_moving_body_is_not_still():
    p = run_plan(series(), body_extra=80.0)   # 손은 멈춰도 발 · 엉덩이 움직이면 정지가 아니다
    assert p["windows"]["head"] is None and p["windows"]["tail"] is None


def test_summary_reports_peak_and_still_ends():
    hand = series(head=12, tail=45)
    s = timing.summary(profile_of(hand), hands=HANDS, body=BODY, scale=1.0, fps=FPS, length=len(hand) / FPS, params=timing.normalize(True))
    assert s["peak_cm_s"] == 300.0 and s["head_still_s"] == pytest.approx(0.4, abs=1e-3) and s["tail_still_s"] == pytest.approx(1.5, abs=1e-3)


# ---- 요청 · 계획 · 실행 ----
def timed_request(**overrides) -> dict:
    base = {"reference_animations": [ATTACK3], "search": ..., "edits": ..., "target_mesh": VESPER_MESH, "provider": "existing_motion",
            "motion_category": "weapon_action", "family": "Sickle", "animation_name": "AS_Vesper_Sickle_Attack3_Timed", "loop": False,
            "duration_seconds": 1.6, "fix": {"timing": True}}
    base.update(overrides)
    return request(**base)


@pytest.fixture
def slow_attack3(fake):
    fake.assets[ATTACK3]["frame_rate"] = 30.0
    hand = series(head=12, peak=300.0, tail=45)
    fake.assets[ATTACK3]["length"] = round(len(hand) / FPS, 4)
    fake.profiles["AS_Vesper_Sickle_Attack3"] = {"speeds": {"hand_r": hand, "hand_l": [x * 0.5 for x in hand]}}
    return hand


def test_request_keeps_fix_shape_without_timing(service):
    env = service.plan_motion_generation(request=request(reference_animations=[AIM_IDLE], search=..., provider="existing_motion"))
    assert env["ok"] and env["result"]["request"]["fix"] == {"ops": []}
    env = service.plan_motion_generation(request=timed_request(fix={"timing": {"max_rate": 9}}))
    assert not env["ok"] and env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == "fix.timing.max_rate"


def test_plan_previews_the_timing_ops_on_a_target_asset(service, fake, slow_attack3):
    env = service.plan_motion_generation(request=timed_request())
    assert env["ok"], env["error"]
    cand = env["result"]["candidates"][0]
    assert [s["step"] for s in cand["steps"]] == ["resolve_source", "timing", "validate"]
    step = cand["steps"][1]
    assert step["provider"] == "direct_key" and step["inputs"]["bones"]["hands"] == ["hand_l", "hand_r"]
    resolved = step["resolved"]
    assert resolved["applied"] and resolved["rate"] == 2.0 and resolved["preview"]["length"] is not None
    previews = [p for t, p in fake.calls if t == "preview_animation_edits"]
    assert previews and previews[-1]["operations"] == resolved["ops"]
    assert "TIMING_RESOLVED_AT_RUN" not in cand["risks"] and "REUSED_EXISTING" not in [lm["code"] for lm in cand["expected_limitations"]]
    assert not fake.writes


def test_plan_without_editor_resolves_at_run(service, fake, slow_attack3):
    fake.up = False
    env = service.plan_motion_generation(request=timed_request())
    cand = env["result"]["candidates"][0]
    step = next(s for s in cand["steps"] if s["step"] == "timing")
    assert step["resolved"] is None and step["inputs"]["bones"] is None and "TIMING_RESOLVED_AT_RUN" in cand["risks"]


def test_timing_comes_before_edits(service, fake, slow_attack3):
    env = service.plan_motion_generation(request=timed_request(edits={"operations": [{"op": "mirror"}]}))
    steps = [s["step"] for s in env["result"]["candidates"][0]["steps"]]
    assert steps == ["resolve_source", "timing", "edit", "validate"]
    assert env["result"]["candidates"][0]["steps"][2]["preview"] is None


def test_timing_job_writes_the_final_asset(service, fake, slow_attack3):
    env = service.plan_motion_generation(request=timed_request())
    planned_ops = env["result"]["candidates"][0]["steps"][1]["resolved"]["ops"]
    job = service.generate_motion(plan_id=env["result"]["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    final = f"{OUT}/AS_Vesper_Sickle_Attack3_Timed"
    assert job["generated_assets"] == [final]
    apply = [p for t, p in fake.calls if t == "apply_animation_edits"]
    assert len(apply) == 1 and apply[0]["operations"] == planned_ops and apply[0]["source"] == ATTACK3 and apply[0]["asset_path"] == final
    tm = job["timing"]
    assert tm["applied"] and tm["source"] == ATTACK3 and tm["asset"] == final and tm["before"]["peak_cm_s"] == round(300.0 / 1.05, 1)
    assert tm["length"]["after"] == pytest.approx(fake.assets[final]["length"], abs=2e-3)
    codes = [lm["code"] for lm in job["limitations"]]
    assert "TIMING_CHANGED_LENGTH" in codes and "DURATION_MISMATCH" not in codes
    assert any(d["code"] == "TIMING_APPLIED" for d in job["diagnostics"])


def test_no_swing_still_makes_the_final_asset(service, fake):
    fake.profiles["AS_Vesper_Rifle_AimIdle"] = {"speeds": {"hand_r": [5.0] * 40, "hand_l": [5.0] * 40}}
    env = service.plan_motion_generation(request=timed_request(reference_animations=[AIM_IDLE], animation_name="AS_Vesper_Rifle_AimIdle_Timed",
                                                               motion_category="idle", loop=True, duration_seconds=None))
    job = service.generate_motion(plan_id=env["result"]["plan_id"], save=False)["result"]
    assert job["status"] == "SUCCEEDED" and job["generated_assets"] == [f"{OUT}/AS_Vesper_Rifle_AimIdle_Timed"]
    assert [p for t, p in fake.calls if t == "apply_animation_edits"][0]["operations"] == [{"op": "trim"}]
    lim = next(lm for lm in job["limitations"] if lm["code"] == "TIMING_NOT_APPLIED")
    assert lim["reason"] == "NO_SWING" and not job["timing"]["applied"]


def test_timing_skips_capture_compare(service, fake, slow_attack3, tmp_path):
    root = tmp_path / "Capture"
    root.mkdir()
    fake.capture_roots = [root.as_posix() + "/"]
    env = service.plan_motion_generation(request=timed_request(review={"capture": True}))
    cap = env["result"]["candidates"][0]["steps"][-1]
    assert cap["step"] == "capture" and cap["inputs"]["rows_from"] == "request" and not cap["inputs"]["compare"]


def test_generated_route_measures_at_run(bl):
    p = plan(bl, fix={"timing": True})
    cand = p["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    assert steps.index("timing") == steps.index("retarget") + 1 and steps[-1] == "validate"
    assert "TIMING_RESOLVED_AT_RUN" in cand["risks"]
