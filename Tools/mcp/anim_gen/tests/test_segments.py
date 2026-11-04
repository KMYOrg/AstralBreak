"""세그먼트 생성 (Phase 9-2 — 후속 로드맵 U2-a, 지침서 §14 Phase 9 '9-2') — 프레임 · 경계 · 시각 사상 · 이음매 수치(segments.py) · 요청 검증 ·
local_ai 계획 · Kimodo 인자 · 이음매 단계 · 몽타주 섹션 · fix.timing swing 창. Kimodo · Blender 는 가짜 실행기(test_local_ai)."""
from __future__ import annotations

import pytest

from anim_gen import segments as seg
from anim_gen import timing
from anim_gen.envelope import AnimGenError
from anim_gen.local_ai import kimodo_run
from anim_gen.local_ai.kimodo_run import RunError
from anim_gen.request import normalize

from test_local_ai import KimodoProc, ai_request, ka, run_to_end  # noqa: F401 — ka 픽스처

SEGS = [{"prompt": "A person raises a sword over the right shoulder with both hands.", "duration_seconds": 1.0, "name": "Windup"},
        {"prompt": "The person slashes the sword diagonally down to the left.", "duration_seconds": 0.7, "name": "Slash", "swing": True},
        {"prompt": "The person returns to a fighting stance.", "duration_seconds": 1.3, "name": "Recover"}]


def seg_request(**overrides) -> dict:
    base = {"prompt": None, "duration_seconds": None, "segments": SEGS}
    base.update(overrides)
    return ai_request(**base)


def plan_seg(ka, **overrides) -> dict:
    env = ka.service.plan_motion_generation(request=seg_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


# ---- segments.py ----
def test_plan_frames_sum_to_the_single_prompt_length():
    p = seg.plan_frames([1.0, 0.7, 1.3], 30.0)
    assert p["frames"] == [30, 21, 40] and p["start_frame"] == [0, 30, 51] and p["total_frames"] == 91
    assert p["boundaries_s"] == [1.0, 1.7] and p["length_s"] == 3.0 and p["starts_s"] == [0.0, 1.0, 1.7] and p["ends_s"] == [1.0, 1.7, 3.0]
    # 한 프롬프트 3초와 같은 프레임 수(round(3 × 30) + 1)
    assert p["total_frames"] == int(round(3.0 * 30)) + 1


def test_swing_window_pads_by_the_transition():
    p = seg.plan_frames([1.0, 0.7, 1.3], 30.0)
    segs = [{"swing": False}, {"swing": True}, {"swing": False}]
    assert seg.swing_window(segs, p["starts_s"], p["ends_s"], 5, 30.0) == [round(1.0 - 5 / 30, 4), round(1.7 + 5 / 30, 4)]
    assert seg.swing_window([{"swing": False}] * 3, p["starts_s"], p["ends_s"], 5, 30.0) is None


def test_map_times_follows_the_timing_warp():
    assert seg.map_times([1.0, 1.7], None) == [1.0, 1.7]
    # 머리 0.5초를 자르고(원 0.5 → 새 0) 나머지 그대로
    warp = [[0.5, 0.0, 1.0], [3.0, 2.5, 1.0]]
    assert seg.map_times([1.0, 1.7, 0.2], warp) == [0.5, 1.2, 0.0]


def test_sections_chain_and_skip_collapsed():
    secs, skipped = seg.sections(["A", "B", "C"], [0.0, 1.0, 1.7], 3.0, 30.0)
    assert secs == [{"name": "A", "start": 0.0, "next": "B"}, {"name": "B", "start": 1.0, "next": "C"}, {"name": "C", "start": 1.7, "next": None}]
    assert not skipped
    secs, skipped = seg.sections(["A", "B", "C"], [0.0, 0.0, 1.2], 2.0, 30.0)   # 트림이 B 를 지웠다
    assert [s["name"] for s in secs] == ["A", "C"] and secs[0]["next"] == "C" and skipped[0]["name"] == "B"


def test_step_ratio_matches_the_cpp_formula():
    steps = [1.0] * 20
    assert seg.step_ratio(steps, 10) == 1.0
    steps[9] = 5.0   # 프레임 9 → 10 이 튐(이음매 프레임 10)
    assert seg.step_ratio(steps, 10) == 5.0
    assert seg.step_ratio(steps, 15) == 1.0


def test_speed_seams_flag_a_jump_but_not_a_smooth_change():
    times = [round((i + 1) / 30, 4) for i in range(90)]
    smooth = [100.0 + 5.0 * i for i in range(90)]           # 고르게 빨라짐 — 이음매가 아니다
    jump = [100.0] * 90
    jump[29] = 400.0                                          # 단계 29 → 30 끝(시각 1.0) 하나만 튐
    rows = seg.speed_seams(times, {"hand_r": jump, "hand_l": smooth}, [1.0, 1.7])
    first, second = rows
    assert first["roles"]["hand_r"]["speed_step_ratio"] > seg.SEAM_RATIO_MAX and first["speed_step_ratio_max"] == first["roles"]["hand_r"]["speed_step_ratio"]
    assert first["roles"]["hand_l"]["speed_step_ratio"] <= 1.0 and first["roles"]["hand_r"]["speed_ratio"] == 1.0
    assert second["speed_step_ratio_max"] <= 1.0
    assert seg.speed_seams(times, {"hand_r": jump}, [9.0])[0]["reason"] == "OUT_OF_RANGE"


# ---- 요청 ----
def _norm(**overrides) -> dict:
    req, _ = normalize(seg_request(**overrides))
    return req


def test_request_without_segments_gets_no_new_keys():
    req, _ = normalize(ai_request())
    assert "segments" not in req and "transition_frames" not in req["generation"]
    req, _ = normalize(ai_request(segments=None))
    assert "segments" not in req


def test_request_segments_normalize():
    req = _norm()
    assert req["duration_seconds"] == 3.0 and req["generation"]["transition_frames"] == 5 and req["prompt"] is None
    assert [s["name"] for s in req["segments"]] == ["Windup", "Slash", "Recover"] and [s["swing"] for s in req["segments"]] == [False, True, False]
    req = _norm(segments=[{k: v for k, v in s.items() if k != "name"} for s in SEGS], duration_seconds=3.0, generation={"seed": 7, "transition_frames": 10})
    assert [s["name"] for s in req["segments"]] == ["Seg1", "Seg2", "Seg3"] and req["generation"]["transition_frames"] == 10


@pytest.mark.parametrize("overrides, field, reason", [
    ({"prompt": "A person swings a sword."}, "segments", "CONFLICTING_FIELDS"),
    ({"segments": SEGS[:1]}, "segments", "BAD_FIELD"),
    ({"segments": SEGS * 3}, "segments", "BAD_FIELD"),
    ({"segments": [SEGS[0], {**SEGS[1], "duration_seconds": 0.4}]}, "segments[1].duration_seconds", "BAD_FIELD"),
    ({"segments": [SEGS[0], {**SEGS[1], "name": "Windup"}]}, "segments[1].name", "DUPLICATE_NAME"),
    ({"segments": [{**SEGS[0], "swing": True}, SEGS[1]]}, "segments", "CONFLICTING_FIELDS"),
    ({"segments": [{**SEGS[0], "duration_seconds": 6.0}, {**SEGS[1], "duration_seconds": 4.5}]}, "segments", "DURATION_OVER_MAX"),
    ({"duration_seconds": 4.0}, "duration_seconds", "CONFLICTING_FIELDS"),
    ({"generation": {"transition_frames": 11}}, "generation.transition_frames", "BAD_FIELD"),
    ({"segments": [SEGS[0], {**SEGS[1], "bad": 1}]}, "segments[1].bad", "UNKNOWN_FIELD"),
])
def test_request_segments_rejected(overrides, field, reason):
    with pytest.raises(AnimGenError) as exc:
        normalize(seg_request(**overrides))
    assert exc.value.details.get("field") == field and exc.value.reason == reason


def test_transition_frames_only_with_segments_and_sections_rules():
    with pytest.raises(AnimGenError) as exc:
        normalize(ai_request(generation={"seed": 7, "transition_frames": 5}))
    assert exc.value.reason == "REQUIRES_SEGMENTS"
    with pytest.raises(AnimGenError) as exc:
        normalize(ai_request(package={"montage": {"sections": "segments"}}))
    assert exc.value.reason == "REQUIRES_SEGMENTS"
    with pytest.raises(AnimGenError) as exc:
        normalize(seg_request(package={"montage": {"sections": "segments"}}, edits={"operations": [{"op": "trim"}]}))
    assert exc.value.reason == "CONFLICTING_FIELDS"
    assert _norm(package={"montage": {"sections": "segments"}})["package"]["montage"]["sections"] == "segments"


# ---- Kimodo 호출 인자 ----
def test_call_inputs_single_prompt_is_unchanged_and_segments_pass_lists():
    assert kimodo_run.call_inputs({"prompt": "A person walks.", "frames": 121}) == (["A person walks."], [121], 5)
    args = {"prompts": ["a", "b"], "segment_frames": [30, 31], "frames": 61, "transition_frames": 8}
    assert kimodo_run.call_inputs(args) == (["a", "b"], [30, 31], 8)
    with pytest.raises(RunError) as exc:
        kimodo_run.call_inputs({**args, "frames": 60})
    assert exc.value.code == "BAD_SEGMENTS"


# ---- 계획 ----
def test_plan_segments_pins_prompts_frames_boundaries_and_a_seams_step(ka):
    p = plan_seg(ka)
    cand = p["candidates"][0]
    assert cand["provider"] == "local_ai"
    kinds = [s["step"] for s in cand["steps"]]
    assert kinds == ["generate", "convert", "import", "retarget", "seams", "validate"]
    g = cand["steps"][0]["inputs"]
    assert g["prompt"] is None and g["frames"] == 91 and g["transition_frames"] == 5 and g["boundaries_s"] == [1.0, 1.7]
    assert [(s["name"], s["frames"], s["start_frame"], s["start_s"], s["end_s"]) for s in g["segments"]] == \
        [("Windup", 30, 0, 0.0, 1.0), ("Slash", 21, 30, 1.0, 1.7), ("Recover", 40, 51, 1.7, 3.0)]
    assert g["swing_window_s"] == [round(1.0 - 5 / 30, 4), round(1.7 + 5 / 30, 4)] and g["duration_seconds"] == 3.0
    assert cand["steps"][1]["expected"]["frames"] == 91   # 변환 단계가 받는 BVH 프레임 = 합
    s = cand["steps"][4]["inputs"]
    assert s["names"] == ["Windup", "Slash", "Recover"] and s["boundaries_s"] == [1.0, 1.7] and s["map"] == "identity" and not s["sections"]
    assert s["bones"]["pelvis"] == "pelvis" and s["bones"]["root"] == "root" and s["bones"]["hand_r"] == "hand_r"
    codes = {lim["code"] for lim in cand["expected_limitations"]}
    assert "SEGMENT_TRANSITIONS" in codes and "DURATION_MISMATCH" not in codes
    excluded = {e["provider"]: e["reason"] for e in p["excluded"]}
    assert excluded["existing_motion"] == "SEGMENTS_UNSUPPORTED"
    assert not ka.launcher.procs and not ka.fake.writes


def test_plan_segments_with_timing_passes_the_swing_window(ka):
    p = plan_seg(ka, fix={"timing": True})
    steps = {s["step"]: s for s in p["candidates"][0]["steps"]}
    assert steps["timing"]["inputs"]["swing_window_s"] == [round(1.0 - 5 / 30, 4), round(1.7 + 5 / 30, 4)]
    assert steps["seams"]["inputs"]["map"] == "fix.timing warp"
    # segments 가 없으면 timing inputs 에 창이 없다(9-1 과 같은 계획)
    p = ka.service.plan_motion_generation(request=ai_request(fix={"timing": True}))["result"]
    t = next(s for s in p["candidates"][0]["steps"] if s["step"] == "timing")
    assert "swing_window_s" not in t["inputs"] and not any(s["step"] == "seams" for s in p["candidates"][0]["steps"])


def test_plan_segments_deadline_counts_a_diffusion_per_segment(ka):
    g = plan_seg(ka)["candidates"][0]["steps"][0]["inputs"]
    assert g["timeout_extra_s"] == 2 * 25.0   # 세그먼트 3 → 확산 3
    p = plan_seg(ka, motion_category="weapon_action", constraints={"two_hand_weapon_grip": True}, generation={"seed": 7, "candidates": 4})
    g = next(s for s in p["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]
    assert g["diffusions"] == 4 * 2 * 3 and g["timeout_extra_s"] == 25.0 * 23
    # segments 없는 후보 계획은 그대로(후보 × 패스)
    p = ka.service.plan_motion_generation(request=ai_request(motion_category="weapon_action", constraints={"two_hand_weapon_grip": True},
                                                             generation={"seed": 7, "candidates": 4}))["result"]
    assert next(s for s in p["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]["diffusions"] == 8


def test_plan_segments_over_300_frames_is_blocked(ka):
    long = [{"prompt": f"Move {i}.", "duration_seconds": 2.5} for i in range(4)]
    p = plan_seg(ka, segments=long)
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == "DURATION_OVER_MAX"


# ---- 실행 ----
def _speeds(n: int, jump_at: int | None) -> list[float]:
    v = [100.0] * n
    if jump_at is not None:
        v[jump_at] = 500.0
    return v


def test_run_segments_passes_lists_and_records_seams_and_sections(ka):
    p = plan_seg(ka, package={"montage": {"sections": "segments"}})
    final = p["final_asset"].rsplit("/", 1)[-1]
    ka.fake.profiles[final] = {"speeds": {"hand_r": _speeds(90, 29), "hand_l": _speeds(90, None), "foot_l": _speeds(90, None),
                                          "foot_r": _speeds(90, None), "pelvis": _speeds(90, None), "root": _speeds(90, None)}, "seam_ratio": 1.4}
    job = run_to_end(ka, p)
    [proc] = ka.launcher.of(KimodoProc)
    a = proc.args
    assert a["prompts"] == [s["prompt"] for s in SEGS] and a["segment_frames"] == [30, 21, 40] and a["frames"] == 91
    assert a["transition_frames"] == 5 and a["boundaries_s"] == [1.0, 1.7] and a["prompt"] is None
    assert job["status"] == "SUCCEEDED", job.get("error")
    segs = job["segments"]
    assert segs["boundaries_s"] == [1.0, 1.7] and segs["map"] == "identity" and segs["names"] == ["Windup", "Slash", "Recover"]
    first, second = segs["seams"]
    assert first["rotation_step_ratio"] == 1.4 and first["roles"]["hand_r"]["speed_step_ratio"] > seg.SEAM_RATIO_MAX
    assert second["speed_step_ratio_max"] <= 1.0 and segs["speed_step_ratio_max"] == first["speed_step_ratio_max"]
    assert "SEGMENT_SEAM_JUMP" in {d["code"] for d in job["diagnostics"]}
    [val] = [q for t, q in ka.fake.calls if t == "validate_animation" and q.get("seams")]
    assert val["seams"] == [1.0, 1.7] and val["profile_positions"] and set(val["profile_bones"]) == {"hand_l", "hand_r", "foot_l", "foot_r", "pelvis", "root"}
    [secs] = [q["sections"] for t, q in ka.fake.calls if t == "set_montage_sections"]
    assert secs == [{"name": "Windup", "start": 0.0, "next": "Slash"}, {"name": "Slash", "start": 1.0, "next": "Recover"},
                    {"name": "Recover", "start": 1.7, "next": None}]
    assert segs["sections"] == secs


def test_run_without_segments_passes_the_same_kimodo_args(ka):
    p = ka.service.plan_motion_generation(request=ai_request())["result"]
    ka.service.generate_motion(plan_id=p["plan_id"], save=True)
    [proc] = ka.launcher.of(KimodoProc)
    assert not {"prompts", "segment_frames", "transition_frames", "boundaries_s"} & set(proc.args)


# ---- fix.timing swing 창 ----
def test_timing_detect_searches_only_the_swing_window():
    """달리기 팔 흔들기(앞, 600 cm/s) > 공격(뒤, 450 cm/s) — 창이 없으면 달리기를, swing 창이면 공격을 휘두름으로 잡는다."""
    n = 90
    hands = [50.0] * n
    for k in range(5, 25):
        hands[k] = 600.0 if k % 6 == 0 else 300.0
    for k in range(60, 70):
        hands[k] = 450.0
    spans = [(k, k + 1) for k in range(n)]
    sig = {"spans": spans, "hands": hands, "hands_raw": hands, "body": [100.0] * n}
    params = timing.normalize(True)
    whole = timing.detect(sig, params, n, 30.0)
    assert whole["peak"]["time_frame"] < 30 and "search" not in whole
    windowed = timing.detect(sig, {**params, "swing_window_s": [1.8, 2.5]}, n, 30.0)
    assert 60 <= windowed["peak"]["time_frame"] <= 70 and windowed["search"][0] >= 54 and windowed["swing"][0] >= 54
    # fps 가 없으면(옛 호출) 창을 쓰지 않는다
    assert timing.detect(sig, {**params, "swing_window_s": [1.8, 2.5]}, n)["peak"] == whole["peak"]
