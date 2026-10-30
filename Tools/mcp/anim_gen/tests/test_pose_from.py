"""Phase 8-4c c2 — 샘플 전이(fix.body.pose_from) 순수 테스트: 요청 · 묶음(템플릿 체인 · 손 트리) · 사건 정렬 · pose/motion 블렌드 · 손가락 덮기 ·
하드 제약 우선(관통 · keep) · 막힌 본 보고 · 다른 스켈레톤 거부 · 루프.

합성 C++ 모델 = body_fit_fixture(양팔 · 쇄골 · 척추 3 · 목 · 머리 · 다리 · 손가락 한 마디). 샘플도 같은 골격의 다른 동작이다."""
from __future__ import annotations

import copy
import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm

SAMPLE = "/Game/Test/AS_Sample"
_CHAINS = [("Spine", "spine_01", "spine_05"), ("Neck", "neck_01", "neck_01"), ("Head", "head", "head"), ("LeftClavicle", "clavicle_l", "clavicle_l"),
           ("LeftArm", "upperarm_l", "hand_l"), ("RightClavicle", "clavicle_r", "clavicle_r"), ("RightArm", "upperarm_r", "hand_r"),
           ("LeftLeg", "thigh_l", "foot_l"), ("RightLeg", "thigh_r", "foot_r")]
# 대상 메시 inspect_skeleton(details · template_match · suggest_finger_chains) 흉내 — 합성 골격 그대로
INFO = {"bones": [{"name": n, "parent": fx.BONES[p] if p >= 0 else None} for n, p in zip(fx.BONES, fx.PARENTS)],
        "template_match": {"pelvis": "pelvis", "chains": [{"name": n, "start": a, "end": b} for n, a, b in _CHAINS]},
        "finger_chain_suggestion": {"chains": [{"name": f"{s}Middle", "start": f"middle_01_{x}", "end": f"middle_01_{x}"} for s, x in (("Left", "l"), ("Right", "r"))]}}


def pose_item(**kw) -> dict:
    base = {"id": "p", "asset": SAMPLE, "bones": "fingers_l", "mode": "pose", "source": {"time": 0.5}, "target": {"window": [0.4, 0.5]}, "ease_s": 0.1}
    base.update(kw)
    return base


def pf_solve(frames, sample_frames, items, *, extra: dict | None = None, events=None, s_events=None, loop=False, sample_model=None):
    """같은 모델 · cfg 로 샘플 전이 있는 풀이와 없는 풀이(= 샘플 없는 Job)."""
    model = bm.BodyModel(fx.make_model(frames))
    sm = bm.BodyModel(sample_model or fx.make_model(sample_frames))
    cfg = bf.normalize({"pose_from": items, **(extra or {})})
    for p in cfg["pose_from"]:
        res = bf.bundle_bones(p["bones"], INFO)
        p["resolved_bones"], p["resolved_presets"] = res["bones"], res["presets"]
    rig = bf.Rig(model)
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    targets = bf.resolve_targets(rig, cfg["targets"], events, cfg["joints"])
    pf = bf.resolve_pose_from(rig, cfg["pose_from"], events, {SAMPLE: {"model": sm, "events": s_events}})
    res = bf.solve(model, cfg, grip=grip, targets=targets, loop=loop, pose_from=pf)
    base = bf.solve(model, {**cfg, "pose_from": []}, grip=grip, targets=targets, loop=loop)
    return model, res, base, pf


def local(res: dict, model: bm.BodyModel, f: int, bone: str):
    b = model.index[bone]
    p = model.parents[b]
    return res["poses"][f][b][0] if p < 0 else bm.relative(res["poses"][f][b], res["poses"][f][p])[0]


def angle(a, b) -> float:
    return math.degrees(bm._norm(bf.qlog(bm.qmul(a, bm.qconj(b)))))


# ---- 요청 ----
def test_normalize_defaults():
    p = bf.normalize({"pose_from": [{"id": "a", "asset": SAMPLE, "bones": "spine", "mode": "pose", "source": {"event": "swing_peak"},
                                     "target": {"event": "swing_peak"}}]})["pose_from"][0]
    assert p["bones"] == ["spine"] and p["weight"] == 1.0 and p["ease_s"] == 0.15 and p["hold_s"] == 0.0 and p["space"] == "local"
    assert bf.normalize(True)["pose_from"] == [] and bf.normalize(True)["weights"]["pose_from"] == 3.0
    m = bf.normalize({"pose_from": [pose_item(bones=["arm_l", "arm_r", "arm_l"], mode="motion", source={"window": ["swing_end", "end"]},
                                              target={"event": "swing"}, weight=0.5)]})["pose_from"][0]
    assert m["bones"] == ["arm_l", "arm_r"] and m["source"] == {"window": ["swing_end", "end"]}


@pytest.mark.parametrize("item, field, reason", [
    ({"asset": None}, "fix.body.pose_from[0].asset", "MISSING_FIELD"),
    ({"bones": "legs"}, "fix.body.pose_from[0].bones", "NOT_SUPPORTED"),
    ({"bones": []}, "fix.body.pose_from[0].bones", "BAD_FIELD"),
    ({"mode": "copy"}, "fix.body.pose_from[0].mode", "BAD_FIELD"),
    ({"source": {"window": [0.1, 0.3]}}, "fix.body.pose_from[0].source", "BAD_FIELD"),           # pose = 샘플 한 시각
    ({"mode": "motion", "target": {"time": 0.4}, "source": {"window": [0, 1]}}, "fix.body.pose_from[0].target", "BAD_FIELD"),   # motion = 구간 → 구간
    ({"target": {"window": ["impact", "end"]}}, "fix.body.pose_from[0].target.window", "BAD_FIELD"),
    ({"target": {"window": [0.5, 0.4]}}, "fix.body.pose_from[0].target.window", "BAD_FIELD"),
    ({"weight": 1.5}, "fix.body.pose_from[0].weight", "BAD_FIELD"),
    ({"space": "component"}, "fix.body.pose_from[0].space", "NOT_SUPPORTED"),
    ({"speed": 1}, "fix.body.pose_from[0].speed", "UNKNOWN_FIELD"),
])
def test_normalize_rejects(item, field, reason):
    with pytest.raises(bf.BodyFitError) as exc:
        bf.normalize({"pose_from": [pose_item(**item)]})
    assert exc.value.field == field and exc.value.reason == reason


def test_ids_are_shared_with_targets():
    with pytest.raises(bf.BodyFitError) as exc:
        bf.normalize({"targets": [{"id": "p", "effector": "hand_r", "at": {"time": 0.1}, "position": {"offset_cm": [0, 0, 1]}}], "pose_from": [pose_item()]})
    assert exc.value.field == "fix.body.pose_from" and exc.value.reason == "DUPLICATE_ID"


# ---- 묶음 ----
def test_presets_follow_the_template_chains_and_the_hand_tree():
    info = copy.deepcopy(INFO)
    # 위팔 · 아래팔의 체인 밖 잎 자식(트위스트) — 자식이 있는 가지(옷 자락)는 빠진다 · 손 아래 메타카팔(손가락 체인 시작의 부모 — 빠진다)
    info["bones"] += [{"name": "upperarm_twist_01_l", "parent": "upperarm_l"}, {"name": "upperarm_twist_02_l", "parent": "upperarm_l"},
                      {"name": "jacket_01", "parent": "upperarm_l"}, {"name": "jacket_02", "parent": "jacket_01"},
                      {"name": "lowerarm_twist_01_l", "parent": "lowerarm_l"}, {"name": "middle_metacarpal_l", "parent": "hand_l"},
                      {"name": "middle_02_l", "parent": "middle_01_l"}]
    out = bf.bundle_bones(["spine", "neck_head", "arm_l", "fingers_l"], info)
    assert out["presets"]["spine"] == ["spine_01", "spine_02", "spine_05"] and out["presets"]["neck_head"] == ["neck_01", "head"]
    assert out["presets"]["arm_l"] == ["clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_twist_01_l", "upperarm_twist_02_l", "lowerarm_twist_01_l"]
    assert out["presets"]["fingers_l"] == ["middle_01_l", "middle_02_l"] and "middle_metacarpal_l" not in out["bones"]
    up = bf.bundle_bones(["upper_body", "spine_02"], INFO)
    assert set(up["bones"]) == {"spine_01", "spine_02", "spine_05", "neck_01", "head", "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
                                "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r"} and len(up["bones"]) == 13


@pytest.mark.parametrize("names, reason", [(["calf_l"], "NOT_SUPPORTED"), (["pelvis"], "NOT_SUPPORTED"), (["root"], "NOT_SUPPORTED"),
                                           (["tail_01"], "UNKNOWN_BONE")])
def test_legs_pelvis_and_unknown_bones_are_refused(names, reason):
    with pytest.raises(bf.BodyFitError) as exc:
        bf.bundle_bones(names, INFO)
    assert exc.value.reason == reason


def test_missing_chain_or_finger_chains_are_unresolved_presets():
    info = copy.deepcopy(INFO)
    info["template_match"]["chains"] = [c for c in info["template_match"]["chains"] if c["name"] != "Spine"]
    with pytest.raises(bf.BodyFitError) as exc:
        bf.bundle_bones(["spine"], info)
    assert exc.value.reason == "POSE_FROM_PRESET_UNKNOWN"
    with pytest.raises(bf.BodyFitError) as exc:
        bf.bundle_bones(["fingers_r"], {**INFO, "finger_chain_suggestion": {"chains": []}})
    assert exc.value.reason == "POSE_FROM_PRESET_UNKNOWN"


# ---- 시각 ----
def test_pose_aligns_the_sample_event_on_the_target_event():
    p = bf.normalize({"pose_from": [pose_item(source={"event": "swing_peak"}, target={"event": "swing_peak"}, hold_s=0.2)]})["pose_from"][0]
    sp = bf.pose_from_spans(p, {"swing_peak": 1.9333}, 4.0, 30.0, {"swing_peak": 0.3333}, 1.25, 60.0)
    assert sp["window_s"] == [1.9333, 2.1333] and sp["frames"] == [58, 64] and sp["source_s"] == [0.3333, 0.3333] and sp["ease_frames"] == 3
    assert sp["alignment"][0]["anchor"] == "swing_peak" and sp["alignment"][0]["error_frames"] <= 1.0


def test_motion_maps_windows_through_shared_events_monotonically():
    p = bf.normalize({"pose_from": [pose_item(mode="motion", source={"window": ["swing_start", "end"]}, target={"window": ["swing_start", "end"]})]})["pose_from"][0]
    ev, s_ev = {"swing_start": 1.0, "swing_peak": 1.5, "swing_end": 2.5}, {"swing_start": 0.1, "swing_peak": 0.3, "swing_end": 0.6}
    sp = bf.pose_from_spans(p, ev, 4.0, 30.0, s_ev, 1.25, 60.0)
    assert [a[2] for a in sp["anchors"]] == ["swing_start", "swing_peak", "swing_end", "end"] and sp["source_s"] == [0.1, 1.25]
    times = [bf._map_time(sp["anchors"], f / 30.0) for f in range(30, 121)]
    assert all(b >= a for a, b in zip(times, times[1:])) and abs(bf._map_time(sp["anchors"], 1.5) - 0.3) < 1e-9
    assert max(a["error_frames"] for a in sp["alignment"]) <= 1.0


@pytest.mark.parametrize("item, s_events, reason", [
    (pose_item(source={"event": "swing_peak"}), {"swing_peak": None, "reason": "NO_SWING"}, "EVENT_NOT_FOUND"),
    (pose_item(source={"time": 5.0}), {}, "TARGET_OUT_OF_RANGE"),
    (pose_item(target={"time": 9.0}), {}, "TARGET_OUT_OF_RANGE"),
])
def test_missing_events_and_out_of_range_items_are_skipped(item, s_events, reason):
    model = bm.BodyModel(fx.make_model([{} for _ in range(30)]))
    cfg = bf.normalize({"pose_from": [item]})
    cfg["pose_from"][0]["resolved_bones"], cfg["pose_from"][0]["resolved_presets"] = ["middle_01_l"], {"fingers_l": ["middle_01_l"]}
    out = bf.resolve_pose_from(bf.Rig(model), cfg["pose_from"], None, {SAMPLE: {"model": model, "events": s_events}})
    assert out[0]["skipped"]["reason"] == reason


def test_a_sample_on_another_skeleton_is_refused():
    raw = fx.make_model([{} for _ in range(30)])
    raw["bones"]["parents"][fx.BONES.index("hand_l")] = fx.BONES.index("upperarm_l")
    model = bm.BodyModel(fx.make_model([{} for _ in range(30)]))
    cfg = bf.normalize({"pose_from": [pose_item(bones="arm_l")]})
    res = bf.bundle_bones(["arm_l"], INFO)
    cfg["pose_from"][0]["resolved_bones"], cfg["pose_from"][0]["resolved_presets"] = res["bones"], res["presets"]
    with pytest.raises(bf.BodyFitError) as exc:
        bf.resolve_pose_from(bf.Rig(model), cfg["pose_from"], None, {SAMPLE: {"model": bm.BodyModel(raw), "events": {}}})
    assert exc.value.reason == "SAMPLE_SKELETON_MISMATCH"


# ---- 풀이 ----
def test_fingers_take_the_sample_local_exactly_and_nothing_else_moves():
    # 기준 5 — 참조 프레임(샘플 0.5 초) 손가락 로컬 = 결과(0°), 묶음 밖 본 불변
    model, res, base, _ = pf_solve([{} for _ in range(30)], [{"middle_01_l": (0.0, 3.0 * f, 0.0)} for f in range(30)],
                                   [pose_item(target={"window": [0.0, 29 / 30]}, ease_s=0.0)])
    want = bm.from_rotvec_deg((0.0, 45.0, 0.0))
    assert max(angle(local(res, model, f, "middle_01_l"), want) for f in range(30)) < 1e-6
    assert [b["bone"] for b in res["deltas"]["bones"]] == ["middle_01_l"] and max(res["moved_cm"]) < 1e-9
    r = res["pose_from"][0]
    assert r["achieved"]["deg_max"] < 1e-6 and r["fingers"] == {"bones": 1, "deg_max": r["achieved"]["deg_max"]} and r["partial"] == []


def test_pose_blends_by_weight_only_inside_its_window():
    sample = [{b: (0.0, 0.0, 10.0) for b in ("spine_01", "spine_02", "spine_05")} for _ in range(30)]
    model, res, base, _ = pf_solve([{} for _ in range(30)], sample, [pose_item(bones="spine", weight=0.5)])
    half = bm.from_rotvec_deg((0.0, 0.0, 5.0))
    assert all(angle(local(res, model, f, b), half) <= bf.POSE_FROM_TOL_DEG for f in range(12, 16) for b in ("spine_01", "spine_02", "spine_05"))
    assert all(res["poses"][f] == base["poses"][f] for f in range(30) if f < 9 or f > 18)
    assert res["region"]["blocks"] == [[9, 18]] and res["pose_from"][0]["partial"] == [] and res["pose_from"][0]["ease_frames"] == 3
    # 팔은 척추를 따라간다(묶음 밖 본의 로컬은 그대로)
    assert local(res, model, 13, "upperarm_l") == local(base, model, 13, "upperarm_l") and res["poses"][13][model.index["hand_l"]][1] != base["poses"][13][model.index["hand_l"]][1]


def test_motion_follows_the_mapped_sample_time():
    # 샘플 왼팔이 프레임마다 2° 씩 몸 밖으로 — 샘플 [0, 0.5] 초를 대상 [0.2, 0.7] 초로(배속 1), 대상 프레임 f 의 위팔 = 샘플 프레임 f − 6
    sample = [{"upperarm_l": (0.0, -2.0 * f, 0.0)} for f in range(30)]
    model, res, _, _ = pf_solve([{} for _ in range(30)], sample, [pose_item(bones="arm_l", mode="motion", source={"window": [0.0, 0.5]},
                                                                            target={"window": [0.2, 0.7]})])
    assert all(angle(local(res, model, f, "upperarm_l"), bm.from_rotvec_deg((0.0, -2.0 * (f - 6), 0.0))) <= bf.POSE_FROM_TOL_DEG for f in range(6, 22))
    r = res["pose_from"][0]
    assert r["frames"] == [6, 21] and r["achieved"]["deg_max"] <= bf.POSE_FROM_TOL_DEG and max(a["error_frames"] for a in r["alignment"]) <= 1.0
    # ease 프레임은 구간 끝 자세(샘플 0.5 초 = −30°)를 완급만큼
    assert angle(local(res, model, 23, "upperarm_l"), bm.from_rotvec_deg((0.0, 0.0, 0.0))) < 30.0


def test_clearance_beats_the_sample_and_reports_the_blocked_bones():
    # 샘플 왼팔은 몸 안 ≈ 10 cm — 관통 몫은 목표 없는 풀이처럼 블록 안 스플라인(마지막 재검사만 새 깊은 관통을 그 프레임 값으로)이라 관통은 0, 완급
    # 가장자리에 맞닿음 위 조금(≈ 0.4 cm — 관통 판정 밑)이 남는다
    model, res, _, _ = pf_solve([{} for _ in range(30)], [fx.into_body(18.0) for _ in range(30)],
                                [pose_item(bones="arm_l", target={"window": [0.3, 0.6]})])
    series = {k: v for k, v in res["predicted"]["series"].items() if k[1] in ("hand", "forearm") and not k[2].startswith(("hand_", "forearm_"))}
    window = max((d for s in series.values() for f, d in enumerate(s) if d is not None and 9 <= f <= 18), default=0.0)
    worst = max((d for s in series.values() for d in s if d is not None), default=0.0)
    r = res["pose_from"][0]
    assert window <= model.contact_cm + 0.5 and worst < model.penetration_cm and r["partial"] and "clearance" in r["blocked_by"]
    assert any(row["bone"] in ("clavicle_l", "upperarm_l", "lowerarm_l") for row in r["partial"])


def test_the_grip_relation_beats_a_one_arm_sample():
    target = [fx.grip_front() for _ in range(30)]
    sample = [fx.grip_front({"upperarm_l": (60.0, 0.0, 0.0)}) for _ in range(30)]
    model, res, base, _ = pf_solve(target, sample, [pose_item(bones="arm_l", target={"window": [0.3, 0.6]})])
    r = res["pose_from"][0]
    assert r["partial"] and "grip" in r["blocked_by"] and res["keep"]["pos_cm_max"] <= model.scale


def test_loop_pose_from_at_the_seam_wraps_around():
    n = 31
    sample = [{"spine_05": (0.0, 0.0, 12.0)} for _ in range(n)]
    model, res, base, _ = pf_solve([{} for _ in range(n)], sample, [pose_item(bones=["spine_05"], target={"window": [0.0, 0.05]})], loop=True)
    assert res["region"]["blocks"] == [[27, 5]] and res["state"][0] == res["state"][-1] and res["loop"]["seam_deg"] == 0.0
    assert res["poses"][15] == base["poses"][15] and angle(local(res, model, 28, "spine_05"), bm.from_rotvec_deg((0.0, 0.0, 0.0))) > 0.5


def test_no_pose_from_leaves_the_solve_untouched():
    frames = fx.bump({}, fx.into_body(18.0))
    model = bm.BodyModel(fx.make_model(frames))
    cfg = bf.normalize(True)
    grip = bf.grip_weights(bf.Rig(model), cfg["grip"], model.scale)
    a = bf.solve(model, cfg, grip=grip)
    b = bf.solve(model, cfg, grip=grip, pose_from=[])
    assert a["state"] == b["state"] and "pose_from" not in a and "region" not in b
