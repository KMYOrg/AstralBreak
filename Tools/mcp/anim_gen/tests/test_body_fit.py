"""Phase 8-4b — body_fit(몸 전체 한 풀이: 관통 · 파지 keep · 손끼리 · 위팔 안 깊어짐 · 지시 목표 · 골반 + 다리 IK) 순수 테스트.

합성 C++ 모델 = body_fit_fixture(양팔 · 쇄골 · 다리 · 손 · 아래팔 지도). 동작은 이어지는 꼴(bump — 실제 애니처럼 프레임 사이가 매끈)."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import timing


def solve(frames, cfg=None, events=None, poses=None, loop=False):
    model = bm.BodyModel(fx.make_model(frames, poses=poses))
    cfg = cfg or bf.normalize(True)
    rig = bf.Rig(model)
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    targets = bf.resolve_targets(rig, cfg["targets"], events, cfg["joints"])
    return model, bf.solve(model, cfg, grip=grip, targets=targets, loop=loop), grip


def worst(pairs: dict, parts=("hand", "forearm")) -> float:
    return max((v["depth_max"] for k, v in pairs.items() if k.split("|")[1] in parts and not k.split("|")[2].startswith(("hand_", "forearm_"))), default=0.0)


def bone_deg(res: dict, bone: str) -> float:
    entry = next((b for b in res["deltas"]["bones"] if b["bone"] == bone), None)
    return max((math.sqrt(sum(c * c for c in v)) for v in entry["rotation_deg"]), default=0.0) if entry and entry["rotation_deg"] else 0.0


# ---- 요청 ----
def test_normalize_defaults_and_off():
    cfg = bf.normalize(True)
    assert cfg["mode"] == "auto" and cfg["clearance"] == {"margin_cm": 0.5, "allow_contact": True, "hands": True, "upper_arm": "no_worse", "secondary": "record",
                                                          "legs": False}
    assert cfg["grip"]["mode"] == "auto" and cfg["joints"]["clavicle_deg"] == 10.0 and cfg["joints"]["spine_deg"] == 0.0 and cfg["targets"] == []
    assert bf.normalize(None) is None and bf.normalize(False) is None and bf.normalize({"mode": "off"}) is None
    t = bf.normalize({"targets": [{"id": "a", "effector": "hand_r", "at": {"event": "swing_end"}, "position": {"offset_cm": [0, 0, -15]}}]})["targets"][0]
    assert t["ease_s"] == 0.15 and t["priority"] == "soft" and t["position"]["space"] == "body" and t["hold_s"] == 0.0


@pytest.mark.parametrize("raw, field, reason", [
    ({"speed": 1}, "fix.body.speed", "UNKNOWN_FIELD"),
    ({"clearance": {"margin_cm": 9}}, "fix.body.clearance.margin_cm", "BAD_FIELD"),
    ({"clearance": {"upper_arm": "target"}}, "fix.body.clearance.upper_arm", "BAD_FIELD"),
    ({"clearance": {"allow_contact": "yes"}}, "fix.body.clearance.allow_contact", "BAD_FIELD"),
    ({"grip": {"mode": "weapon"}}, "fix.body.grip.mode", "BAD_FIELD"),
    ({"grip": {"window": [2, 1]}}, "fix.body.grip.window", "BAD_FIELD"),
    ({"joints": {"spine_deg": 5}}, "fix.body.joints.spine_deg", "NOT_SUPPORTED"),
    ({"passes": 0}, "fix.body.passes", "BAD_FIELD"),
    ({"targets": [{"id": "a", "effector": "hand_r", "at": {"event": "swing_end"}}]}, "fix.body.targets[0]", "MISSING_FIELD"),
    ({"targets": [{"id": "a", "effector": "hand_r", "at": {"event": "impact"}, "position": {"offset_cm": [0, 0, 1]}}]}, "fix.body.targets[0].at.event", "BAD_FIELD"),
    ({"targets": [{"id": "a", "effector": "hand_r", "at": {"time": 1, "window": [0, 1]}, "position": {"offset_cm": [0, 0, 1]}}]}, "fix.body.targets[0].at", "BAD_FIELD"),
    ({"targets": [{"id": "a", "effector": "foot_l", "at": {"time": 1}, "rotation": {"offset_deg": [0, 5, 0]}}]}, "fix.body.targets[0].rotation", "NOT_SUPPORTED"),
    ({"targets": [{"id": "a", "effector": "hand_r", "at": {"time": 1}, "position": {"offset_cm": [0, 0, 1]}},
                  {"id": "a", "effector": "hand_l", "at": {"time": 1}, "position": {"offset_cm": [0, 0, 1]}}]}, "fix.body.targets", "DUPLICATE_ID"),
])
def test_normalize_rejects(raw, field, reason):
    with pytest.raises(bf.BodyFitError) as exc:
        bf.normalize(raw)
    assert exc.value.field == field and exc.value.reason == reason


# ---- 매끈화 · 조회 · 델타 ----
def test_spline_keeps_corrected_frames_and_stays_local():
    series = [(0.0, 0.0, 0.0)] * 40
    active = [False] * 40
    for f, v in ((18, 1.0), (19, 1.2), (20, 1.0)):
        series[f], active[f] = (0.0, 0.0, v), True
    out = bf.spline(series, active, 4)
    # 보정 프레임 둘레를 넓게(폭 = SPLINE_WIDTH × radius) 가속 연속으로 잇는다 — 고립된 뾰족한 정점은 덜 남고(바깥 프레임 가중 10 이라 절반쯤 —
    # 모자란 만큼은 재검사가 채운다), 보정 구간 ± 2·폭 밖은 0
    width = int(bf.SPLINE_WIDTH * 4)
    assert out[19][2] >= 0.45 * 1.2 and out[19][2] == max(v[2] for v in out)
    assert all(out[f][2] <= out[f + 1][2] for f in range(9, 19)) and all(out[f][2] >= out[f + 1][2] for f in range(19, 30))
    assert all(v == (0.0, 0.0, 0.0) for f, v in enumerate(out) if f < 18 - 2 * width or f > 20 + 2 * width)


def test_spline_quiet_frames_return_toward_the_original(monkeypatch):
    # 걷기처럼 보정 프레임이 흩어져 있으면(10 프레임마다) 그 사이 프레임은 원래(증분 0) 쪽으로 돌아와야 한다 — 바깥 가중 1(처음 판)은 사이를
    # 보정 값 그대로 이었다(운영 걷기 손목 이동 p50 13.9 cm)
    series, active = [(0.0, 0.0, 0.0)] * 60, [False] * 60
    for f in (10, 20, 30, 40, 50):
        series[f], active[f] = (0.0, 0.0, 1.0), True
    mid = lambda out: max(out[f][2] for f in (15, 25, 35, 45))  # noqa: E731
    quiet = mid(bf.spline(series, active, 4))
    monkeypatch.setattr(bf, "SPLINE_QUIET_WEIGHT", 1.0)
    old = mid(bf.spline(series, active, 4))
    assert old > 0.7 and quiet < 0.4 * old   # 사이 프레임 0.79 → 0.24


def test_spline_loop_wraps_the_seam():
    # 루프(끝 프레임 = 첫 프레임) — 끝 근처 보정이 첫 프레임 쪽으로 감아 돌고, 결과 첫 = 끝(이음매 0). 열린 열이면 첫 프레임은 0 그대로
    n = 41
    series, active = [(0.0, 0.0, 0.0)] * n, [False] * n
    for f in (37, 38, 39):
        series[f], active[f] = (0.0, 0.0, 1.0), True
    out = bf.spline(series, active, 4, loop=True)
    assert out[0] == out[-1] and out[0][2] > 0.1 and out[2][2] > 0.0
    assert out[20] == (0.0, 0.0, 0.0)
    # 같은 원을 보정에서 먼 곳(20)에서 자른 열린 열과 같다 — 감아 붙인 끝의 영향이 남지 않는다
    core = n - 1
    rotated = bf.spline(series[20:core] + series[:20], active[20:core] + active[:20], 4)
    assert max(abs(a[2] - b[2]) for a, b in zip(out[20:core] + out[:20], rotated)) < 1e-2
    opened = bf.spline(series, active, 4)
    assert opened[0] == (0.0, 0.0, 0.0) and abs(opened[-1][2] - out[-1][2]) > 0.05


def test_probe_equals_the_cpp_rule_when_nothing_moves():
    model = bm.BodyModel(fx.make_model(fx.bump({}, fx.into_body(18.0), n=10, lo=4, hi=5, ramp=2)))
    s = bf.Solver(model, bf.normalize(True))
    for f in range(len(model.frames)):
        for pt in model.points:
            p = model.skin(model.poses[f], pt)
            for name in ("torso", "thigh_l", "head_neck", "hand_r"):
                ref = model.maps[name].depth(f, p)
                hit = s.probe(name, f, p, model.poses[f])
                assert (ref is None) == (hit is None) and (ref is None or ref[0] == pytest.approx(hit[0], abs=1e-9))


def test_rest_motion_is_left_alone():
    _, res, _ = solve([{} for _ in range(12)])
    assert res["deltas"]["frames_changed"] == 0 and bf.bone_deltas_op(res) is None and max(res["moved_cm"]) == 0.0


def test_bone_deltas_reproduce_the_solved_pose():
    model, res, _ = solve(fx.bump({}, fx.into_body(18.0)))
    op = bf.bone_deltas_op(res)
    assert op["space"] == "parent" and all(len(b["rotation_deg"]) == len(model.frames) for b in op["bones"] if b["rotation_deg"])
    deltas = {b["bone"]: b for b in op["bones"]}
    for f in (0, 12, 15, 29):
        pose = model.apply_deltas(f, {name: (b["rotation_deg"][f] if b["rotation_deg"] else None,
                                             b["translation_cm"][f] if b["translation_cm"] else None) for name, b in deltas.items()})
        assert max(bm._norm(bm._sub(a[1], b[1])) for a, b in zip(pose, res["poses"][f])) < 1e-3


# ---- 관통 ----
def test_arm_into_the_body_is_pushed_out_locally():
    frames = fx.bump({}, fx.into_body(18.0))
    model, res, _ = solve(frames)
    before = bf.measure(model)["pairs"]
    # 맞닿음(≤ contact_cm)까지는 정상(allow_contact 기본) — + 잔차 허용 · 매끈화가 남기는 0.2 cm
    assert worst(before) > 9.0 and worst(res["predicted"]["pairs"]) <= model.contact_cm + 0.2
    radius = int(round(0.13 * model.fps))
    changed = res["changed_frames"]
    assert changed and all(res["moved_cm"][f] < 0.1 for f in range(len(frames)) if all(abs(f - c) > 2 * radius for c in changed))
    assert bone_deg(res, "clavicle_l") <= 10.0 + 1e-3 and bone_deg(res, "upperarm_r") == 0.0


def test_body_contact_is_left_alone_unless_turned_off():
    # 손 · 아래팔이 넓적다리에 0.57 cm 닿은 자세(접촉 0.95 아래) — 기본(allow_contact)은 그대로, 끄면 margin 만큼 떼어 둔다(처음 판)
    frames = fx.bump({}, fx.into_body(2.0))
    model, res, _ = solve(frames)
    assert 0.3 < worst(bf.measure(model)["pairs"]) <= model.contact_cm and res["deltas"]["frames_changed"] == 0
    _, off, _ = solve(frames, bf.normalize({"clearance": {"allow_contact": False}}))
    assert off["deltas"]["frames_changed"] > 0 and worst(off["predicted"]["pairs"]) <= 0.0
    # 머리목은 하드 기준이라 맞닿음도 margin 만큼 뗀다(몸통 · 넓적다리만 허용)
    allow = bf.Solver(model, bf.normalize(True)).body_allow
    margin = 0.5 * model.scale
    assert allow["torso"] == allow["thigh_l"] == model.contact_cm and allow["head_neck"] == -margin
    assert set(bf.Solver(model, bf.normalize({"clearance": {"allow_contact": False}})).body_allow.values()) == {-margin}


def test_upper_arm_is_never_pushed_deeper():
    model, res, _ = solve(fx.bump({}, fx.into_body(18.0)))
    before, after = bf.measure(model)["pairs"], res["predicted"]["pairs"]
    for key, v in after.items():
        if key.split("|")[1] == "upper_arm":
            assert v["depth_max"] <= (before.get(key) or {"depth_max": 0.0})["depth_max"] + 0.1


def test_upper_arm_rows_are_soft_and_never_rechecked():
    # 위팔 '안 깊어짐'은 keep 층(TIER upper — 관통의 1/3)이고 재검사 위반이 아니다 — 하드 층이던 처음 판은 사이 프레임의 작은 위팔 깊어짐까지 다시 풀며
    # 팔을 벌렸다(운영 걷기 주기마다 손목 바깥 10 / 13.6 / 13.4 / 7 cm)
    model = bm.BodyModel(fx.make_model([{} for _ in range(3)]))
    s = bf.Solver(model, bf.normalize(True))
    s._candidates(1, model.poses[1])
    upper = [i for i, p in enumerate(model.points) if p["part"] == "upper_arm"]
    state = {"rot": {model.index["upperarm_l"]: (0.0, math.radians(30.0), 0.0)}, "trans": {}}   # 위팔을 몸통 쪽으로
    ev = s.evaluate(1, state, {"rot": {}, "trans": {}}, {"upper"}, upper, s._joints(1), jac=False)
    tier = bf.TIER["upper"]
    assert ev["info"]["clear"] and tier < bf.TIER["clearance"]
    assert ev["cost"] == pytest.approx(sum((10.0 * tier * c[4]) ** 2 for c in ev["info"]["clear"]))
    assert s._violations(1, state, upper)["clear"] == []


def test_two_hand_grip_moves_both_arms_and_keeps_the_grip():
    frames = fx.bump(fx.grip_front(), fx.grip_close())
    model, res, grip = solve(frames)
    assert len(grip["frames"]) == len(frames) and grip["lead"] == "r" and grip["band_cm"] == [0.0, 19.0]
    assert worst(bf.measure(model)["pairs"]) > 2.0 and worst(res["predicted"]["pairs"]) <= model.contact_cm + 0.2
    keep = res["keep"]
    assert keep["pos_cm_max"] <= model.scale and keep["deg_max"] <= 5.0   # 기준 2 = 1 cm × scale · 5°
    assert bone_deg(res, "upperarm_r") > 1.0 and bone_deg(res, "upperarm_l") > 1.0   # 두 팔이 함께(§10 C안)


def test_hands_passing_through_each_other_are_separated():
    frames = fx.bump(fx.grip_front(), fx.grip_front({"upperarm_l": (60.0, 0.0, 27.0)}))
    model, res, _ = solve(frames)
    hands = lambda pairs: max((v["depth_max"] for k, v in pairs.items() if k.split("|")[2].startswith(("hand_", "forearm_"))), default=0.0)  # noqa: E731
    # 손끼리는 맞닿음(≤ contact_cm)까지 허용하고 keep 과 겨루므로 접촉 근처에서 멈춘다 — 기준은 관통(> penetration_cm) 0
    assert hands(bf.measure(model)["pairs"]) > model.penetration_cm and hands(res["predicted"]["pairs"]) <= model.penetration_cm


def test_hands_touching_in_a_grip_are_left_alone():
    _, res, _ = solve([fx.grip_front() for _ in range(10)])
    assert res["deltas"]["frames_changed"] == 0


def test_loop_motion_closes_its_seam():
    # 루프(끝 프레임 = 첫 프레임) — 관통이 이음매를 걸쳐 있다(정점 f28, f24 ~ 30 · f0 ~ 2). 순환이면 첫 · 끝 델타가 같고(이음매 0) 관통은 양쪽 다
    # 풀린다, 열린 열로 풀면 첫 · 끝 델타가 다르다(운영 걷기 15.3°)
    n = 31
    frames = [fx.blend({}, fx.into_body(18.0), max(0.0, 1.0 - min((f - 28) % 30, (28 - f) % 30) / 5.0)) for f in range(n)]
    assert frames[0] == frames[-1]
    model, res, _ = solve(frames, loop=True)
    assert res["loop"] == {"on": True, "seam_deg": 0.0} and res["state"][0] == res["state"][-1]
    assert worst(bf.measure(model)["pairs"]) > 9.0 and worst(res["predicted"]["pairs"]) <= model.penetration_cm
    _, opened, _ = solve(frames)
    assert not opened["loop"]["on"] and opened["loop"]["seam_deg"] > 0.5


def test_solve_is_deterministic():
    frames = fx.bump(fx.grip_front(), fx.grip_close())
    _, a, _ = solve(frames)
    _, b, _ = solve(frames)
    assert a["deltas"]["bones"] == b["deltas"]["bones"]


# ---- 사건 · 지시 목표 ----
def test_events_come_from_the_timing_signals():
    n, fps = 60, 30.0
    times = [(i + 1) / fps for i in range(n)]
    speed = [0.0] * 20 + [100.0, 300.0, 600.0, 300.0, 100.0] + [0.0] * 35
    pos = {"foot_l": [[9.0, 0.0, 8.0]] * n, "foot_r": [[-9.0, 0.0, 8.0]] * n}
    prof = {"times": times, "frames_per_sample": 1, "speed_cm_s": {"hand_l": speed, "hand_r": speed, "hip_l": speed}, "position_cm": pos}
    ev = timing.events(prof, hands=("hand_l", "hand_r"), body=["hip_l"], feet=("foot_l", "foot_r"), scale=1.0, fps=fps, length=n / fps, leg_cm=90.0)
    assert ev["swing_start"] < ev["swing_peak"] < ev["swing_end"] and ev["swing_peak"] == pytest.approx(23 / fps, abs=1 / fps)
    assert ev["swing"] == [ev["swing_start"], ev["swing_end"]] and ev["both_planted"] and ev["still_end"] is not None


def target(**kw):
    base = {"id": "t", "effector": "hand_r", "at": {"window": [0.4, 0.5]}, "ease_s": 0.1}
    base.update(kw)
    return bf.normalize({"targets": [base]})


def test_reachable_hand_target_is_met_and_stays_in_its_window():
    cfg = target(position={"offset_cm": [10, 0, 0]})
    model, res, _ = solve([{} for _ in range(30)], cfg)
    t = res["targets"][0]
    assert t["reached"] and t["achieved"]["error_cm_p95"] <= model.scale and t["frames"] == [12, 15] and t["ease_frames"] == 3
    assert all(res["moved_cm"][f] == 0.0 for f in range(30) if f < 12 - 3 or f > 15 + 3)


def test_target_into_the_body_is_blocked_by_clearance():
    # 오른손을 앞 · 몸 왼쪽(몸통 안)으로. [0, 15, 0](옆으로만)은 이 합성 몸에서 몸통 맞닿음 자리(축에서 9.05 cm)가 오른 넓적다리 축(x −9)과
    # 겹쳐, 넓적다리 바깥 방향이 몸 안쪽을 가리키는 함정(정중앙 관통 한계와 같은 꼴 — 4.7 cm 남음)이라 목표 시험에 쓰지 않는다
    cfg = target(position={"offset_cm": [5, 15, 0]})
    model, res, _ = solve([{} for _ in range(30)], cfg)
    t = res["targets"][0]
    # 맞닿음까지 다가가면 팔꿈치가 다 펴지고 쇄골이 상한에 닿는 프레임도 있다(joint_limit 함께)
    assert not t["reached"] and "clearance" in t["blocked_by"] and worst(res["predicted"]["pairs"]) <= model.contact_cm + 0.2


def test_hard_target_beats_clearance():
    cfg = target(position={"offset_cm": [0, 15, 0]}, priority="hard")
    model, res, _ = solve([{} for _ in range(30)], cfg)
    assert res["targets"][0]["achieved"]["error_cm_p95"] < 1.0 and worst(res["predicted"]["pairs"]) > 5.0


def test_unreachable_target_reports_the_joint_limit():
    cfg = target(position={"offset_cm": [0, 0, -10]})   # 다 편 팔을 더 아래로
    _, res, _ = solve([{} for _ in range(30)], cfg)
    assert not res["targets"][0]["reached"] and "joint_limit" in res["targets"][0]["blocked_by"]


def test_pelvis_target_bends_the_knees_and_pins_the_feet():
    cfg = target(effector="pelvis", position={"offset_cm": [0, 0, -5]})
    model, res, _ = solve([{} for _ in range(30)], cfg)
    t = res["targets"][0]
    assert t["reached"] and t["achieved"]["error_cm_p95"] <= model.scale
    for side in ("l", "r"):
        foot, knee = model.index[f"foot_{side}"], model.index[f"calf_{side}"]
        assert all(bm._norm(bm._sub(res["poses"][f][foot][1], model.poses[f][foot][1])) < 1e-3 for f in range(30))
        assert res["poses"][13][knee][1][1] > 1.0   # 곧은 다리는 몸 앞(+Y)으로 굽힌다
    assert res["legs"][13] and all(not v["clamped"] for v in res["legs"][13].values())


def test_spine_rotation_target_turns_only_its_window():
    cfg = target(effector="spine_05", rotation={"offset_deg": [0, 15, 0]})
    _, res, _ = solve([{} for _ in range(30)], cfg)
    t = res["targets"][0]
    assert t["reached"] and t["achieved"]["error_deg_p95"] <= 3.0
    assert bone_deg(res, "spine_05") <= 20.0 / 3 + 1e-3 and all(res["moved_cm"][f] == 0.0 for f in range(30) if f < 9 or f > 18)


def test_missing_event_and_out_of_range_targets_are_skipped():
    model = bm.BodyModel(fx.make_model([{} for _ in range(10)]))
    rig = bf.Rig(model)
    cfg = bf.normalize({"targets": [{"id": "a", "effector": "hand_r", "at": {"event": "swing_end"}, "position": {"offset_cm": [0, 0, -5]}},
                                    {"id": "b", "effector": "hand_r", "at": {"time": 9.0}, "position": {"offset_cm": [0, 0, -5]}},
                                    {"id": "c", "effector": "hand_r", "at": {"event": "both_planted", "index": 2}, "position": {"offset_cm": [0, 0, -5]}}]})
    out = bf.resolve_targets(rig, cfg["targets"], {"swing_end": None, "reason": "NO_SWING", "both_planted": [[0.0, 0.1]]}, cfg["joints"])
    assert [t["skipped"]["reason"] for t in out] == ["EVENT_NOT_FOUND", "TARGET_OUT_OF_RANGE", "EVENT_NOT_FOUND"]


def test_unknown_effector_is_a_request_error():
    model = bm.BodyModel(fx.make_model([{} for _ in range(30)]))
    cfg = target(effector="tail_01", position={"offset_cm": [0, 0, 1]})
    with pytest.raises(bf.BodyFitError) as exc:
        bf.resolve_targets(bf.Rig(model), cfg["targets"], None, cfg["joints"])
    assert exc.value.reason == "UNKNOWN_EFFECTOR"
