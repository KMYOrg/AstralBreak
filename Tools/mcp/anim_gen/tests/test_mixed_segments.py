"""섞은 세그먼트 (Phase 9-3c — 후속 로드맵 U2-b, 지침서 §14 Phase 9 '9-3c') — 기존 애셋 구간 + 생성 덩어리: 순수 함수(segments.py — 배치 · 겹침 ·
이음매 자동 키 · 몸 방향 · 겹친 구간 자세 차) · 요청 검사 · local_ai 계획(생성 덩어리 프레임 · 자동 키 · join · seams 단계) · join 실행(골반 맞춤 op ·
이음매 수치 · 몽타주 섹션) · Kimodo 인자. Kimodo · Blender 는 가짜 실행기(test_local_ai)."""
from __future__ import annotations

import json
import math
import pathlib

import pytest

from anim_gen import segments as seg
from anim_gen import timing
from anim_gen.editor import asset_name
from anim_gen.envelope import AnimGenError
from anim_gen.providers import key_pose as kp_step
from anim_gen.request import normalize
from conftest import ATTACK3, IDLE, KATANA

from test_key_pose import SOMA_BONES, TREE, make_kimodo_package
from test_local_ai import KimodoProc, ai_request, ka, run_to_end  # noqa: F401 — ka 픽스처

NAME = "AS_Vesper_Sickle_MixJoin"
MIXED = [{"source": "existing", "asset": ATTACK3, "name": "Attack"},
         {"prompt": "The person spins around and slashes the scythe horizontally.", "duration_seconds": 1.0, "name": "Follow", "swing": True},
         {"source": "existing", "asset": IDLE, "start": 0.0, "end": 1.0, "name": "Recover"}]


def mix_request(**overrides) -> dict:
    base = {"animation_name": NAME, "family": "Sickle", "prompt": None, "duration_seconds": None, "segments": MIXED}
    base.update(overrides)
    return ai_request(**base)


@pytest.fixture
def kpa(ka):
    make_kimodo_package(ka.python.parents[1])
    return ka


def plan_mix(kpa, **overrides) -> dict:
    env = kpa.service.plan_motion_generation(request=mix_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


# ---- segments.py ----
def test_layout_overlap_and_chunk_frames():
    lay = seg.layout([{"source": "existing"}, {"source": "generate"}, {"source": "generate"}, {"source": "existing"}])
    assert lay == {"generated": [1, 2], "lead": 0, "trail": 3}
    assert seg.layout([{"source": "generate"}, {"source": "existing"}]) == {"generated": [0], "lead": None, "trail": 1}
    assert seg.overlap_frames(5) == 4 and seg.overlap_frames(2) == 1
    p = seg.mixed_frames([1.0, 0.7], True, True, 4, 30.0)
    # 앞 · 뒤 이웃이 있으면 처음 · 끝 세그먼트가 겹침 4 프레임씩 길다 — 요청 길이 = 새 동작
    assert p["frames"] == [34, 26] and p["total_frames"] == 60 and p["boundaries_s"] == [round(34 / 30, 4)]
    assert seg.mixed_frames([1.0], False, False, 4, 30.0)["total_frames"] == 31


def test_seam_key_constraints_put_the_neighbour_poses_on_the_overlap():
    lead = {"index": 0, "asset": "/Game/A", "start": 0.0, "end": 1.6}
    trail = {"index": 2, "asset": "/Game/B", "start": 0.5, "end": 1.5}
    a, b = seg.seam_key_constraints(lead, trail, 39, 4, 30.0)
    assert a["source"] == "segments[0].seam" and a["placement"] == "origin" and a["part"] == "full"
    assert a["at"] == [round(i / 30, 6) for i in range(5)] and a["times"][-1] == 1.6 and a["times"][0] == round(1.6 - 4 / 30, 6)
    assert b["source"] == "segments[2].seam" and b["placement"] == "pass1"
    assert b["times"] == [round(0.5 + i / 30, 6) for i in range(5)] and b["at"][0] == round(34 / 30, 6) and b["at"][-1] == round(38 / 30, 6)
    assert seg.seam_key_constraints(None, None, 39, 4, 30.0) == []


def test_heading_and_overlap_gap():
    assert seg.heading_deg([0.0, 0.0, 90.0], [10.0, 0.0, 90.0]) == 0.0
    assert seg.heading_deg([0.0, 0.0, 90.0], [0.0, 10.0, 90.0]) == 90.0
    assert seg.wrap_deg(190.0) == -170.0 and seg.wrap_deg(-190.0) == 170.0
    times = [round((i + 1) / 30, 4) for i in range(30)]
    a = {"times": times, "pos": {"pelvis": [[float(i), 0.0, 90.0] for i in range(30)]}, "shift": [0.0, 0.0]}
    # 뒤 조각이 앞 끝 궤적을 그대로 이어받으면(앞 프레임 26 + f = 뒤 프레임 f, 좌표는 10 cm 옮긴 것 + shift) 차 0. 뒤 프레임 0 은 표본이 없어 빠진다
    b = {"times": times, "pos": {"pelvis": [[float(i) + 16.0, 0.0, 90.0] for i in range(30)]}, "shift": [10.0, 0.0]}
    gap = seg.overlap_gap(a, b, 1.0, 0.0, 4 / 30, 4, roles=("pelvis",))
    assert gap is not None and gap["max"] < 1e-6 and gap["samples"] == 4
    b["shift"] = [13.0, 0.0]
    assert seg.overlap_gap(a, b, 1.0, 0.0, 4 / 30, 4, roles=("pelvis",))["p50"] == 3.0


def test_overlap_fit_averages_heading_and_pelvis_over_the_window():
    times = [round((i + 1) / 30, 4) for i in range(30)]
    hips = lambda h: ([-9.0 * math.cos(math.radians(h)), -9.0 * math.sin(math.radians(h)), 95.0],  # noqa: E731
                      [9.0 * math.cos(math.radians(h)), 9.0 * math.sin(math.radians(h)), 95.0])
    # 앞: 방향 10° 고정 · 골반 x 가 프레임마다 +1 / 뒤: 방향이 170 → 179° 로 돈다(±180 경계 근처 — 원형 평균) · 골반 (0, 5) 고정
    a = {"times": times, "shift": [0.0, 0.0], "pos": {"pelvis": [[float(i), 0.0, 100.0] for i in range(30)],
                                                       "hip_l": [hips(10.0)[0]] * 30, "hip_r": [hips(10.0)[1]] * 30}}
    b = {"times": times, "shift": [0.0, 0.0], "pos": {"pelvis": [[0.0, 5.0, 100.0]] * 30,
                                                       "hip_l": [hips(170.0 + 3 * i)[0] for i in range(30)], "hip_r": [hips(170.0 + 3 * i)[1] for i in range(30)]}}
    pairs = seg.overlap_pairs(a, b, 1.0, 0.0, 4 / 30, 4)
    assert pairs == [(26, 0), (27, 1), (28, 2), (29, 3)]                     # 뒤 프레임 0 은 표본이 없다
    fit = seg.overlap_fit(a, b, pairs)
    assert fit["samples"] == 4 and abs(fit["yaw_deg"] - (10.0 - (170.0 + 4.5))) < 1e-6
    assert fit["shift"] == [27.5, -5.0]                                      # 앞 골반 x 26 ~ 29 평균 − 0, 0 − 5
    assert seg.overlap_fit(a, b, []) is None


def test_timing_keeps_the_seam_overlaps_at_rate_one():
    """M1 첫 실행 재현 — 휘두름이 생성 덩어리 끝까지(정점이 끝 근처)면 핵심 ×2 가 뒤 겹침 키 구간까지 이어진다. seam_keep_s 면 그 구간은 배율 1."""
    n, fps = 53, 30.0
    hands = [100.0] * n
    for k in range(30, n):
        hands[k] = 100.0 + 25.0 * (k - 29)
    prof = {"times": [round((i + 1) / fps, 4) for i in range(n)], "frames_per_sample": 1,
            "speed_cm_s": {"hand_l": hands, "hand_r": hands, "pelvis": [100.0] * n}}
    params = timing.normalize(True)
    params["still"] = {**params["still"], "trim_head": False, "trim_tail": False}
    args = {"hands": ("hand_l", "hand_r"), "body": ["pelvis", "hand_l", "hand_r"], "scale": 1.05, "fps": fps, "length": n / fps}
    plain = timing.plan(prof, params=params, **args)
    assert plain["applied"] and plain["profile"][-1]["rate"] > 1.5    # 뒤 겹침까지 빨라진다(M1 첫 실행의 원인)
    kept = timing.plan(prof, params={**params, "seam_keep_s": [4 / 30, 4 / 30]}, **args)
    assert kept["applied"] and kept["seam_keep_s"] == [4 / 30, 4 / 30]
    tail = [m for m in kept["profile"] if m["kind"] in ("seam_tail", "end")]
    assert [m["kind"] for m in tail] == ["seam_tail", "end"] and all(abs(m["rate"] - 1.0) < 0.05 for m in tail)
    assert kept["windows_kept"]["swing"][1] <= round((n - 4) / fps, 4) and kept["profile"][0]["rate"] < 1.05
    # 뒤 키 구간의 새 길이 = 원 길이(배율 1)
    (src0, dst0, _), (src1, dst1, _) = kept["warp"][-2], kept["warp"][-1]
    assert abs((dst1 - dst0) - (src1 - src0)) < 0.01
    # seam_keep_s 가 없으면 계획은 그대로(9-2 · 8-3 과 비트 같은 경로)
    assert "seam_keep_s" not in plain and "windows_kept" not in plain


# ---- 요청 ----
def test_mixed_request_normalizes():
    req, _ = normalize(mix_request())
    assert [s["source"] for s in req["segments"]] == ["existing", "generate", "existing"]
    assert req["segments"][0] == {"name": "Attack", "source": "existing", "asset": ATTACK3, "start": 0.0, "end": None}
    assert req["segments"][2]["end"] == 1.0 and req["duration_seconds"] is None
    assert req["generation"]["seam_keys"] is True and req["generation"]["transition_frames"] == 5
    req, _ = normalize(mix_request(generation={"seed": 7, "seam_keys": False, "transition_frames": 3}))
    assert req["generation"]["seam_keys"] is False and req["generation"]["transition_frames"] == 3


def test_request_without_existing_segments_gets_no_new_keys():
    segs = [{"prompt": "A.", "duration_seconds": 1.0}, {"prompt": "B.", "duration_seconds": 1.0}]
    req, _ = normalize(ai_request(prompt=None, duration_seconds=None, segments=segs))
    assert all("source" not in s for s in req["segments"]) and "seam_keys" not in req["generation"]
    # 생성만인 세그먼트에 source generate 를 적어도 9-2 모양 그대로
    req2, _ = normalize(ai_request(prompt=None, duration_seconds=None, segments=[{**s, "source": "generate"} for s in segs]))
    assert req2["segments"] == req["segments"]


@pytest.mark.parametrize("overrides, field, reason", [
    ({"segments": [MIXED[0], MIXED[2]]}, "segments", "BAD_FIELD"),                                          # 생성 없음
    ({"segments": [MIXED[1], MIXED[0], {**MIXED[1], "name": "Again", "swing": False}]}, "segments", "GENERATION_NOT_CONTIGUOUS"),
    ({"duration_seconds": 3.0}, "duration_seconds", "CONFLICTING_FIELDS"),
    ({"edits": {"operations": [{"op": "trim"}]}}, "segments", "CONFLICTING_FIELDS"),
    ({"generation": {"seed": 7, "transition_frames": 1}}, "generation.transition_frames", "BAD_FIELD"),
    ({"generation": {"seed": 7, "seam_keys": "yes"}}, "generation.seam_keys", "BAD_FIELD"),
    ({"segments": [{**MIXED[0], "prompt": "x"}, MIXED[1]]}, "segments[0].prompt", "UNKNOWN_FIELD"),
    ({"segments": [{**MIXED[0], "swing": True}, MIXED[1]]}, "segments[0].swing", "UNKNOWN_FIELD"),
    ({"segments": [{**MIXED[0], "asset": "AS_X"}, MIXED[1]]}, "segments[0].asset", "BAD_FIELD"),
    ({"segments": [{**MIXED[0], "start": 0.5, "end": 0.8}, MIXED[1]]}, "segments[0].end", "BAD_FIELD"),
    ({"segments": [{**MIXED[0], "source": "meshy"}, MIXED[1]]}, "segments[0].source", "BAD_FIELD"),
])
def test_mixed_request_rejected(overrides, field, reason):
    with pytest.raises(AnimGenError) as exc:
        normalize(mix_request(**overrides))
    assert exc.value.details.get("field") == field and exc.value.reason == reason


def test_seam_keys_needs_existing_segments():
    with pytest.raises(AnimGenError) as exc:
        normalize(ai_request(generation={"seed": 7, "seam_keys": True}))
    assert exc.value.reason == "REQUIRES_SEGMENTS"
    segs = [{"prompt": "A.", "duration_seconds": 1.0}, {"prompt": "B.", "duration_seconds": 1.0}]
    with pytest.raises(AnimGenError) as exc:
        normalize(ai_request(prompt=None, duration_seconds=None, segments=segs, generation={"seed": 7, "seam_keys": False}))
    assert exc.value.reason == "REQUIRES_SEGMENTS"


# ---- 계획 ----
def test_plan_mixed_keys_the_seams_and_joins_after_the_generated_part(kpa):
    p = plan_mix(kpa)
    cand = p["candidates"][0]
    assert cand["provider"] == "local_ai"
    assert [s["step"] for s in cand["steps"]] == ["key_pose", "generate", "convert", "import", "retarget", "join", "seams", "validate"]
    g = cand["steps"][1]["inputs"]
    # 생성 1.0초 + 앞 · 뒤 겹침 4 프레임씩 → 31 + 8 = 39 프레임, 생성 세그먼트 하나(Kimodo 안 전이 없음)
    assert g["frames"] == 39 and g["prompt"] is None and [s["name"] for s in g["segments"]] == ["Follow"] and g["segments"][0]["frames"] == 39
    assert g["boundaries_s"] == [] and g["swing_window_s"] == [0.0, round(round(38 / 30, 4) + 5 / 30, 4)]
    m = g["mixed"]
    assert m["names"] == ["Attack", "Follow", "Recover"] and m["overlap_frames"] == 4 and m["blend_s"] == round(4 / 30, 6) and m["seam_keys"]
    assert [p_["source"] for p_ in m["pieces"]] == ["existing", "generated", "existing"]
    assert m["pieces"][0]["end"] == 1.6 and m["pieces"][2]["end"] == 1.0 and m["pieces"][1]["lead_overlap_frames"] == 4
    assert m["joined_length_s"] == round(1.6 + 38 / 30 + 1.0 - 2 * 4 / 30, 4)
    # 자동 키: 앞(Attack3 끝 5 프레임 → 생성 0 ~ 4, origin) · 뒤(Idle 첫 5 프레임 → 생성 34 ~ 38, pass1) — 2 패스
    keys = {s["source"]: s for s in g["constraints"] if s["kind"] == "key_pose"}
    assert set(keys) == {"segments[0].seam", "segments[2].seam"}
    assert keys["segments[0].seam"]["frame_indices"] == [0, 1, 2, 3, 4] and keys["segments[0].seam"]["placement"] == "origin"
    assert keys["segments[2].seam"]["frame_indices"] == [34, 35, 36, 37, 38] and keys["segments[2].seam"]["placement"] == "pass1"
    assert g["key_pose"]["passes"] == 2 and "hold_free_hands" not in g["key_pose"]
    items = {i["source"]: i for i in cand["steps"][0]["inputs"]["items"]}
    assert items["segments[0].seam"]["source_frames"] == [88, 90, 92, 94, 96] and items["segments[2].seam"]["source_frames"] == [0, 1, 2, 3, 4]
    j = cand["steps"][5]
    assert j["provider"] == "direct_key" and j["inputs"]["align"] == "pelvis" and j["inputs"]["bones"]["hip_l"] == "thigh_l"
    assert j["inputs"]["bones"]["pelvis"] == "pelvis" and j["inputs"]["bones"]["root"] == "root"
    s = cand["steps"][6]["inputs"]
    assert s["mixed"] == {"names": ["Attack", "Follow", "Recover"], "generated": ["Follow"]} and s["map"] == "join"
    codes = {lm["code"] for lm in cand["expected_limitations"]}
    assert "SEGMENTS_JOINED" in codes and "SEGMENT_TRANSITIONS" not in codes and "DURATION_MISMATCH" not in codes
    assert "DURATION_DEFAULTED" not in {d["code"] for d in p.get("diagnostics", [])}
    excluded = {e["provider"]: e for e in p["excluded"]}
    assert excluded["existing_motion"]["reason"] == "SEGMENTS_UNSUPPORTED" and "join step" in excluded["existing_motion"]["message"]
    assert not kpa.launcher.procs and not kpa.fake.writes


def test_plan_without_seam_keys_has_the_same_frames_and_no_key_step(kpa):
    p = plan_mix(kpa, generation={"seed": 7, "seam_keys": False})
    cand = p["candidates"][0]
    assert [s["step"] for s in cand["steps"]][:2] == ["generate", "convert"] and "join" in [s["step"] for s in cand["steps"]]
    g = cand["steps"][0]["inputs"]
    assert g["frames"] == 39 and "key_pose" not in g and not g["mixed"]["seam_keys"]


def test_plan_mixed_with_timing_keeps_the_seam_ends(kpa):
    p = plan_mix(kpa, fix={"timing": True})
    steps = {s["step"]: s for s in p["candidates"][0]["steps"]}
    t = steps["timing"]["inputs"]
    assert t["still"]["trim_head"] is False and t["still"]["trim_tail"] is False and t["seam_trim_off"] == ["trim_head", "trim_tail"]
    assert t["seam_keep_s"] == [round(4 / 30, 6), round(4 / 30, 6)]
    assert steps["seams"]["inputs"]["map"] == "join + fix.timing warp"
    # 앞 이웃만 — 머리만 트림을 끈다
    p = plan_mix(kpa, fix={"timing": True}, segments=MIXED[:2])
    t = next(s for s in p["candidates"][0]["steps"] if s["step"] == "timing")["inputs"]
    assert t["still"]["trim_head"] is False and t["still"]["trim_tail"] is True and t["seam_trim_off"] == ["trim_head"]
    assert t["seam_keep_s"] == [round(4 / 30, 6), 0.0]
    g = next(s for s in p["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]
    assert g["frames"] == 35 and g["key_pose"]["passes"] == 1   # 앞 키만(origin) — 한 패스


@pytest.mark.parametrize("segments, reason", [
    ([{**MIXED[0], "asset": KATANA}, MIXED[1]], "SAMPLE_SKELETON_MISMATCH"),
    ([{**MIXED[0], "start": 1.0, "end": 9.0}, MIXED[1]], "CONSTRAINT_OUT_OF_RANGE"),
])
def test_plan_mixed_blocks_what_it_cannot_join(kpa, segments, reason):
    p = plan_mix(kpa, segments=segments)
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == reason


def test_plan_mixed_needs_the_editor(kpa):
    kpa.fake.up = False
    p = plan_mix(kpa)
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == "EDITOR"


# ---- 실행 ----
def vtracks(n: int, pelvis, heading_deg: float, hips_half: float = 9.0) -> dict:
    """Vesper 측정 본 궤적(표본 n, 1/30 초) — 골반 xy = pelvis(i), 엉덩 관절 = 골반 ± hips_half 를 heading 방향(왼 → 오른)으로."""
    h = math.radians(heading_deg)
    out = {b: {"pos": [], "rot": [[0.0, 0.0, 0.0, 1.0]] * n} for b in ("root", "pelvis", "thigh_l", "thigh_r", "hand_l", "hand_r", "foot_l", "foot_r", "head")}
    for i in range(n):
        x, y = pelvis(i)
        dx, dy = hips_half * math.cos(h), hips_half * math.sin(h)
        rows = {"root": [x, y, 0.0], "pelvis": [x, y, 100.0], "thigh_l": [x - dx, y - dy, 95.0], "thigh_r": [x + dx, y + dy, 95.0],
                "hand_l": [x - 20.0, y, 110.0], "hand_r": [x + 20.0, y, 110.0], "foot_l": [x - 10.0, y, 8.0], "foot_r": [x + 10.0, y, 8.0],
                "head": [x, y, 170.0]}
        for b, v in rows.items():
            out[b]["pos"].append(v)
    return out


def test_join_lines_up_pelvis_and_heading_and_measures_the_seams(kpa):
    fake = kpa.fake
    # 앞 Attack3 끝 골반 (40, 20) · 방향 0° / 생성 덩어리는 (0, 0) 에서 방향 30° 로 시작 / 뒤 Idle 은 (5, −3) · 방향 0°
    fake.profiles[asset_name(ATTACK3)] = {"tracks": vtracks(48, lambda i: (40.0 * i / 47, 20.0), 0.0)}
    fake.profiles[f"{NAME}_Retarget"] = {"tracks": vtracks(60, lambda i: (0.0 + i, 0.0), 30.0)}
    fake.profiles[f"{NAME}_JoinP1"] = {"tracks": vtracks(60, lambda i: (2.0 + i, 1.0), 0.0)}     # 돌린 복사본(흉내) — 30° 를 0° 로
    fake.profiles[asset_name(IDLE)] = {"tracks": vtracks(60, lambda i: (5.0, -3.0), 0.0)}
    p = plan_mix(kpa, generation={"seed": 7, "seam_keys": False}, package={"montage": {"sections": "segments"}})
    job = run_to_end(kpa, p)
    assert job["status"] == "SUCCEEDED", job.get("error")
    join = job["join"]
    blend = round(round(4 / 30 * 60) / 60, 6)   # 이은 시퀀스 fps = 첫 조각(Attack3 60 fps)
    assert join["fps"] == 60.0 and join["blend_s"] == blend and join["align"] == "pelvis" and not join["seam_keys"]
    first, second = join["seams"]
    # 생성 덩어리: 몸 방향 30° → 0° (−30°) — 돌린 복사본(JoinP1)을 만들고, 골반을 앞 끝 (40, 20) 에 맞춘다
    assert first["from"] == "Attack" and first["to"] == "Follow" and first["yaw_deg"] == -30.0 and first["piece_asset"].endswith(f"{NAME}_JoinP1")
    # 겹친 구간 표본 짝(뒤 프레임 0 은 표본이 없어 4 짝 — 앞 표본 44 ~ 47 ↔ 뒤 0 ~ 3)의 골반 차 평균
    dx = sum(40.0 * j / 47 for j in range(44, 48)) / 4 - (2.0 + 1.5)
    assert first["fit"] == "overlap mean" and first["fit_samples"] == 4 and first["shift_cm"] == [round(dx, 3), 19.0]
    assert first["pelvis_target_cm"] == [round(5.0 + round(dx, 3), 3), 20.0] and first["yaw_residual_deg"] == 0.0
    assert not first["keyed"] and first["overlap_gap_cm"] is not None
    # 뒤 Idle: 방향 같음 — 복사하지 않고 구간(start · end)으로 붙인다
    assert second["yaw_deg"] == 0.0 and second["piece_asset"] == IDLE
    calls = [q for t, q in fake.calls if t == "apply_animation_edits"]
    rot = next(q for q in calls if q["asset_path"].endswith("_JoinP1"))
    assert rot["source"].endswith(f"{NAME}_Retarget") and rot["operations"] == [{"op": "rotate_root", "yaw": -30.0, "start": 0.0, "end": round(1 / 30, 6),
                                                                                    "ease": "linear"}]
    final = next(q for q in calls if q["asset_path"].endswith(f"/{NAME}"))
    ops = final["operations"]
    assert final["source"] == ATTACK3 and [o["op"] for o in ops] == ["concat", "offset_bone", "concat", "offset_bone"]
    assert ops[0]["asset"].endswith("_JoinP1") and ops[0]["align_root"] is False and ops[0]["blend"] == blend
    assert ops[2] == {"op": "concat", "asset": IDLE, "blend": blend, "align_root": False, "start": 0.0, "end": 1.0}
    off = ops[1]
    assert off["targets"] == [{"bone": "root", "translation": [first["shift_cm"][0], first["shift_cm"][1], 0.0]}] and off["space"] == "component"
    assert off["blend_in"] == blend and off["blend_out"] == 0.0 and off["start"] == round(1.6 - blend, 4)
    # 이음매: 겹침 시작 · 끝 두 줄씩(생성 덩어리 안 경계 없음), 섹션 = 세그먼트 셋(기존 포함)
    segs = job["segments"]
    assert [r["kind"] for r in segs["seams"]] == ["join_start", "join_end", "join_start", "join_end"] and segs["chunk_start_s"] == round(1.6 - blend, 4)
    [secs] = [q["sections"] for t, q in fake.calls if t == "set_montage_sections"]
    assert [s["name"] for s in secs] == ["Attack", "Follow", "Recover"] and secs[0]["start"] == 0.0
    assert secs[1]["start"] == round(1.6 - blend, 4) and secs[2]["start"] == second["anchor_s"]
    assert job["generated_assets"][0].endswith(f"/{NAME}") and any(a.endswith("_JoinP1") for a in job["intermediate_assets"])


def test_join_with_the_generated_part_first(kpa):
    fake = kpa.fake
    fake.profiles[f"{NAME}_Retarget"] = {"tracks": vtracks(60, lambda i: (float(i), 0.0), 0.0)}
    fake.profiles[asset_name(IDLE)] = {"tracks": vtracks(60, lambda i: (5.0, -3.0), 0.0)}
    p = plan_mix(kpa, generation={"seed": 7, "seam_keys": False}, segments=MIXED[1:])
    g = next(s for s in p["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]
    assert g["frames"] == 35 and g["mixed"]["lead"] is None and g["mixed"]["trail"] == 1
    job = run_to_end(kpa, p)
    assert job["status"] == "SUCCEEDED", job.get("error")
    final = next(q for t, q in fake.calls if t == "apply_animation_edits" and q["asset_path"].endswith(f"/{NAME}"))
    # 첫 조각 = 생성 덩어리(30 fps) — 그 시퀀스에 기존 Idle 구간을 붙인다, 방향이 같아 복사본 없음
    assert final["source"].endswith(f"{NAME}_Retarget") and [o["op"] for o in final["operations"]] == ["concat", "offset_bone"]
    [seam] = job["join"]["seams"]
    assert job["join"]["fps"] == 30.0 and seam["from"] == "Follow" and seam["to"] == "Recover" and seam["yaw_deg"] == 0.0
    # 겹친 구간 앞 표본 56 ~ 59(골반 x 평균 57.5) ↔ 뒤 (5, −3) → 이동 (52.5, 3), 겹침 끝 골반 = (5, −3) + 이동
    assert seam["shift_cm"] == [52.5, 3.0] and seam["pelvis_target_cm"] == [57.5, 0.0] and seam["pelvis_end_gap_cm"] == 1.5
    assert job["segments"]["chunk_start_s"] == 0.0


def test_seam_keys_reach_kimodo_through_the_key_pose_file(kpa, monkeypatch):
    def fake_blender(ctx, bvh_path, out_dir):
        fbx = out_dir / "SOMA_TPose_Rest.fbx"
        fbx.write_bytes(b"fbx")
        return fbx
    monkeypatch.setattr(kp_step, "run_blender", fake_blender)
    kpa.fake.default_bones = SOMA_BONES
    n = 100
    tracks = {b: {"pos": [[0.0, 0.0, 90.0]] * n, "rot": [[0.0, 0.0, 0.0, 1.0]] * n} for b in TREE}
    tracks["LeftLeg"]["pos"] = [[10.0, 0.0, 90.0]] * n
    tracks["RightLeg"]["pos"] = [[-10.0, 0.0, 90.0]] * n
    kpa.fake.profiles[f"KP0_{asset_name(ATTACK3)}_Hold"] = {"tracks": tracks}
    kpa.fake.profiles[f"KP1_{asset_name(IDLE)}_Hold"] = {"tracks": tracks}
    p = plan_mix(kpa)
    env = kpa.service.generate_motion(plan_id=p["plan_id"], save=True)
    job = env["result"]
    assert job["status"] == "RUNNING" and job["stage"] == "generate", job.get("error")
    data = json.loads(pathlib.Path(job["key_pose"]["file"]).read_text(encoding="utf-8"))
    by = {i["source"]: i for i in data["items"]}
    assert [k["frame"] for k in by["segments[0].seam"]["keys"]] == [0, 1, 2, 3, 4] and by["segments[0].seam"]["placement"] == "origin"
    assert [k["source_frame"] for k in by["segments[2].seam"]["keys"]] == [0, 1, 2, 3, 4] and by["segments[2].seam"]["placement"] == "pass1"
    args = kpa.launcher.of(KimodoProc)[-1].args
    assert args["prompts"] == [MIXED[1]["prompt"]] and args["segment_frames"] == [39] and args["frames"] == 39
    assert {c["source"] for c in args["constraints"] if c["kind"] == "key_pose"} == {"segments[0].seam", "segments[2].seam"}
    assert args["key_pose_smooth"] == 1.0 and "key_pose_hold" not in args
