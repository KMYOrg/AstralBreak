"""Phase 9-4d — body_fit 다리 블록(U6): 접지 고정 pins hold(발목 수평 · 발끝 접지 발볼 잇기 — U6-a · U6-d) · 바닥 하한(U6-b) · 루프 이음매(루트 모션) ·
다리 샘플 전이(pose_from legs — U6-c) · 발 회전 목표(디딘 발은 발볼 둘레 — U6-c) · 발볼 오프셋(대상 메시 기준 포즈).

합성 모델 = body_fit_fixture(발볼 본이 없다 — 실제 C++ 몸 모델처럼, 발볼은 balls 로 준다). 걸음 = test_body_fit_legs.step_frames."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
import test_body_fit_legs as legs
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import motion_metrics as mm
from test_pose_from import INFO, SAMPLE

LEGS_ONLY = legs.LEGS_ONLY
BALLS = {"l": {"offset_cm": (0.0, 12.0, -6.0)}, "r": {"offset_cm": (0.0, 12.0, -6.0)}}   # 발 로컬(고정물 기준 포즈 회전 = 항등 — 앞 = +Y)


# 무릎을 굽힌 선 자세 — 고정물 기준 포즈는 다리가 다 펴져 있어(엉덩 → 발목 = 다리 길이) 발목을 옮기면 IK 가 닿지 못한다
BENT = {"thigh_l": (20.0, 0.0, 0.0), "calf_l": (-40.0, 0.0, 0.0), "thigh_r": (20.0, 0.0, 0.0), "calf_r": (-40.0, 0.0, 0.0)}
LIFT = {**BENT, "thigh_l": (50.0, 0.0, 0.0), "calf_l": (-100.0, 0.0, 0.0)}


def slide_frames(n: int = 40) -> list[dict]:
    """굽힌 걸음(왼다리 듦) + 골반이 앞으로 0.15 cm/프레임 미끄러짐 — 디딘 발이 따라 미끄러진다(시간 보정 antialias 흉내)."""
    return [dict(f, pelvis_t=(0.0, 0.15 * (i - n // 2), 0.0)) for i, f in enumerate(fx.bump(BENT, LIFT, n=n, lo=16, hi=21, ramp=6))]


def foot_track(poses, model, side: str) -> list:
    i = model.index[f"foot_{side}"]
    return [p[i][1] for p in poses]


# ---- 요청 · 모드 ----
def test_pins_request_and_modes():
    assert bf.normalize({"legs": {"pins": "hold"}})["legs"]["pins"] == "hold" and bf.normalize({"legs": {"pins": "keep"}})["legs"]["pins"] == "keep"
    for raw in ({"legs": {"pins": "off"}}, {"legs": {"pins": "hold", "swing_path": "off"}}):
        with pytest.raises(bf.BodyFitError) as exc:
            bf.normalize(raw)
        assert exc.value.field == "fix.body.legs.pins"
    legs_cfg = bf.normalize(True)["legs"]
    ops = [{"op": "stance_width"}, {"op": "foot_lock"}]
    # auto = fix.timing 과 다리 op 가 함께일 때만 hold(사용자 결정 ①) — hold 는 공중 경로도 켠다
    assert bf.leg_modes(legs_cfg, ops, True) == {"swing": {"mode": "auto", "on": True, "reason": "fix.ops ['foot_lock', 'stance_width']"},
                                                 "pins": {"mode": "auto", "on": True, "reason": "fix.timing + fix.ops ['foot_lock', 'stance_width']"}}
    assert bf.pins_mode(legs_cfg, ops, None) == {"mode": "auto", "on": False, "reason": "no fix.timing"}
    assert not bf.pins_mode(legs_cfg, [], True)["on"] and "pins hold" in bf.pins_mode(legs_cfg, [], True)["reason"]
    m = bf.leg_modes({**legs_cfg, "pins": "hold"}, None, None)
    assert m["pins"]["on"] and m["swing"] == {"mode": "auto", "on": True, "reason": "pins hold"}
    assert not bf.leg_modes({**legs_cfg, "pins": "keep"}, ops, True)["pins"]["on"]


def test_ball_offsets_read_the_foot_child_in_foot_space():
    # 발 기준 포즈가 수직축 90° 돈 자리 — 컴포넌트 +Y 쪽 발볼은 발 로컬 +X
    info = {"bones": [{"name": "foot_l", "parent": "calf_l", "ref_component": {"t": [10.0, 0.0, 8.0], "r": [0.0, 90.0, 0.0]}},
                      {"name": "ball_l", "parent": "foot_l", "ref_component": {"t": [10.0, 13.0, 2.0], "r": [0.0, 0.0, 0.0]}},
                      {"name": "foot_ik_l", "parent": "foot_l", "ref_component": {"t": [10.0, 1.0, 8.0], "r": [0.0, 0.0, 0.0]}},
                      {"name": "foot_r", "parent": "calf_r", "ref_component": {"t": [-10.0, 0.0, 8.0], "r": [0.0, 0.0, 0.0]}}]}
    rig = bf.Rig(bm.BodyModel(fx.make_model([{}] * 4)))
    out = bf.ball_offsets(info, rig)
    assert set(out) == {"l"} and out["l"]["bone"] == "ball_l"   # 가장 먼 자식 · 자식 없는 발은 뺀다
    assert all(abs(a - b) < 1e-3 for a, b in zip(out["l"]["offset_cm"], (13.0, 0.0, -6.0)))


# ---- 접지 고정 (U6-a · U6-d) ----
def test_hold_pins_the_contact_ankles_horizontally_and_keeps_height_and_foot_rotation():
    model = bm.BodyModel(fx.make_model(slide_frames()))
    rig = bf.Rig(model)
    cfg = bf.normalize({**LEGS_ONLY, "legs": {"pins": "hold"}})
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    base_lp = bf.swing_paths(rig, cfg["legs"])
    lp = bf.swing_paths(rig, cfg["legs"], hold=True)
    res = bf.solve(model, cfg, grip=grip, leg_path=lp)
    assert lp["hold"]["sides"][0]["runs"] == 2 and lp["hold"]["sides"][1]["runs"] == 1 and res["leg_path"]["hold"]["pin_error_cm_max"] < 1e-6
    for side in "lr":
        contacts = lp["contacts"][side]
        before = mm.contact_slide(foot_track(model.poses, model, side), contacts, model.times, 2, model.scale)["p95"]
        after = mm.contact_slide(foot_track(res["poses"], model, side), contacts, model.times, 2, model.scale)["p95"]
        assert before > 4.0 and after < 0.05
        fi = model.index[f"foot_{side}"]
        for f in (f for f in range(len(contacts)) if contacts[f]):
            assert abs(res["poses"][f][fi][1][2] - model.poses[f][fi][1][2]) < 1e-6                           # 높이 그대로(뒤꿈치 듦을 누르지 않는다)
            assert abs(sum(a * b for a, b in zip(res["poses"][f][fi][0], model.poses[f][fi][0]))) > 1.0 - 1e-6   # 발 회전 그대로(피벗을 지우지 않는다)
        for a, b in mm.runs(contacts, 1):
            xy = [(lp["targets"][side][f][0], lp["targets"][side][f][1]) for f in range(a, b + 1)]
            assert max(math.dist(p, xy[0]) for p in xy) < 1e-9
    # 공중 구간은 고정값을 경계로 다시 풀었다(공중 프레임 = hold 가 아닌 목표) · 8-4d 경로와 같은 구간
    assert [w["frames"] for w in lp["windows"]] == [w["frames"] for w in base_lp["windows"]] and res["leg_path"]["frames"] == sorted(base_lp["targets"]["l"])


def test_hold_toe_frames_keep_the_ball_where_the_flat_contact_left_it():
    # 발목 접지 0 ~ 5 → 뒤꿈치 듦 6 ~ 8(발볼만 접지 — 발목이 들리며 앞으로) → 공중 9. 발볼은 미끄러진다(+0.1 cm/프레임)
    A = [(0.0, 0.2 * f, 8.0) for f in range(6)] + [(0.0, 1.0 + (f - 5), 8.0 + 2.0 * (f - 5)) for f in range(6, 10)]
    B = [(0.0, 12.0 + 0.1 * f, 2.0) for f in range(10)]
    ca = [f <= 5 for f in range(10)]
    cb = [f <= 8 for f in range(10)]
    pos, rec = bf._hold_targets("l", A, B, ca, cb, False, None)
    assert rec == {"side": "l", "runs": 1, "frames": 9, "toe_frames": 3, "moved_cm_max": rec["moved_cm_max"]}
    # 발목 접지 = 구간 중앙값 수평, 발끝 접지 = 5 번 프레임(고친 자세)의 발볼 수평 · 발 평행 이동 · 높이 원래
    mid = sorted(0.2 * f for f in range(6))[3] / 2 + sorted(0.2 * f for f in range(6))[2] / 2
    assert all(abs(pos[f][1] - mid) < 1e-9 and pos[f][2] == 8.0 for f in range(6))
    pin = B[5][1] + pos[5][1] - A[5][1]
    for f in (6, 7, 8):
        assert abs(B[f][1] + pos[f][1] - A[f][1] - pin) < 1e-9 and pos[f][2] == A[f][2]
    assert 9 not in pos


# ---- 바닥 (U6-b) ----
def test_floor_levels_are_the_lowest_planted_heights():
    tracks = {"l": ([(0, 0, 9.0), (0, 0, 8.0), (0, 0, 12.0)], [(0, 0, 3.0), (0, 0, 2.5), (0, 0, 1.0)]), "r": ([(0, 0, 8.5)] * 3, None)}
    out = bf._floor_levels(tracks, {"l": [True, True, False], "r": [True, False, False]}, {"l": [True, True, False], "r": None}, 3)
    assert out == {"ankle": 8.0, "ball": 2.5}
    assert bf._floor_levels(tracks, {"l": [False] * 3, "r": [False] * 3}, {"l": [False] * 3, "r": None}, 3) is None


def test_floor_keeps_the_swing_from_dipping_below_its_own_height():
    model = bm.BodyModel(fx.make_model(legs.step_frames()))
    rig = bf.Rig(model)
    cfg = bf.normalize(LEGS_ONLY)
    lp = bf.swing_paths(rig, cfg["legs"])
    w = next(x for x in lp["windows"] if x["side"] == "l")
    win = list(range(w["frames"][0], w["frames"][1] + 1))
    soft, contacts = cfg["legs"]["soft_knee"], lp["contacts"]["l"]
    fi = model.index["foot_l"]
    free, _ = bf._swing_window(rig, "l", win, contacts, False, soft)
    # 바닥이 아주 높으면 하한 = min(바닥, 원래 높이) = 원래 — 원래보다 내려가지 않는다(올리지는 않는다)
    held, rep = bf._swing_window(rig, "l", win, contacts, False, soft, floor={"ankle": 1000.0, "ball": None})
    dip = lambda got: min(got[f][2] - model.poses[f][fi][1][2] for f in win)  # noqa: E731
    assert dip(free) < -1.0 and dip(held) > -0.05 and rep["floor_frames"] > 0
    assert w["floor_margin_cm"]["ankle"][1] > 0.0 and w["floor_frames"] == 0   # 기본 바닥(접지 최저)에는 닿지 않는다 — 8-4d 경로 그대로


# ---- 루프 이음매 (루트 모션) ----
def _loop(root_cm: float) -> list[dict]:
    base = legs.step_frames(n=40, kink=False)
    frames = [dict(base[(i + 20) % 39]) for i in range(39)]
    frames.append(dict(frames[0]))
    return [dict(f, root_t=(0.0, root_cm * i, 0.0)) for i, f in enumerate(frames)]


def test_loop_seam_moves_the_wrapped_frames_with_the_root():
    still, moving = (bm.BodyModel(fx.make_model(_loop(c))) for c in (0.0, 0.25))
    cfg = bf.normalize(LEGS_ONLY)
    assert bf._loop_seam(bf.Rig(still)) is None
    seam = bf._loop_seam(bf.Rig(moving))
    assert abs(seam["d"][1] - 9.75) < 1e-6 and abs(seam["yaw"]) < 1e-9
    assert bf._cycles([37, 38, 0, 1]) == [0, 0, 1, 1] and bf._seam(seam, bf._seam(seam, (1.0, 2.0, 3.0), 1), -1) == pytest.approx((1.0, 2.0, 3.0))
    a, b = (bf.swing_paths(bf.Rig(m), cfg["legs"], loop=True) for m in (still, moving))
    wins = [w for w in a["windows"] if w["side"] == "l"]
    assert len(wins) == 1 and wins[0]["frames"][0] > wins[0]["frames"][1]   # 공중 구간이 이음매를 넘는다
    assert [w["frames"] for w in a["windows"]] == [w["frames"] for w in b["windows"]]
    # 루트 기준으로 보면 같은 경로(8-4d 는 이음매 너머 프레임에 9.75 cm 를 이었다)
    for f, p in a["targets"]["l"].items():
        q = b["targets"]["l"][f]
        assert math.dist(p, (q[0], q[1] - 0.25 * f, q[2])) < 1e-6
    assert b["windows"][0]["ankle_moved_cm_max"] == pytest.approx(a["windows"][0]["ankle_moved_cm_max"], abs=1e-6)


# ---- 다리 샘플 전이 (U6-c) ----
SAMPLE_PEAK = {"thigh_l": (45.0, 0.0, 0.0), "calf_l": (-85.0, 0.0, 0.0)}


def _sample_solve(window, extra=None):
    frames = legs.step_frames(kink=False)
    sample = fx.bump({}, SAMPLE_PEAK, n=40, lo=16, hi=21, ramp=6)
    model, sm = bm.BodyModel(fx.make_model(frames)), bm.BodyModel(fx.make_model(sample))
    cfg = bf.normalize({**LEGS_ONLY, "pose_from": [{"id": "legs", "asset": SAMPLE, "bones": "leg_l", "mode": "motion", "source": {"window": window},
                                                    "target": {"window": window}, "ease_s": 0.1}], **(extra or {})})
    res_b = bf.bundle_bones(cfg["pose_from"][0]["bones"], INFO)
    cfg["pose_from"][0]["resolved_bones"], cfg["pose_from"][0]["resolved_presets"] = res_b["bones"], res_b["presets"]
    rig = bf.Rig(model)
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    pf = bf.resolve_pose_from(rig, cfg["pose_from"], None, {SAMPLE: {"model": sm, "events": None}})
    res = bf.solve(model, cfg, grip=grip, pose_from=pf, balls=BALLS)
    return model, sm, res, pf


def test_leg_sample_pins_the_planted_frames_and_follows_the_sample_in_the_air():
    model, sm, res, pf = _sample_solve([0.3, 1.0])
    fi = model.index["foot_l"]
    p = pf[0]
    ground = mm.detect_contacts(foot_track(model.poses, model, "l"), model.times, 2, sum(bf.Rig(model).leg_len.values()) / 2.0)
    on = [f for f in range(len(ground)) if p["ramp"][f] > 0.0]
    planted = [f for f in on if ground[f]]
    air = [f for f in on if not ground[f]]
    assert planted and air
    for f in planted:
        assert math.dist(res["poses"][f][fi][1], model.poses[f][fi][1]) < 1e-3                     # 발 pin 이 이긴다
    peak = 18
    s_ankle = sm.poses[peak][fi][1]
    assert math.dist(res["poses"][peak][fi][1], s_ankle) < 0.5 * math.dist(model.poses[peak][fi][1], s_ankle)   # 공중은 샘플 발 경로 쪽
    # 덮지 않은 프레임 · 오른 다리 · 팔은 그대로
    for f in range(len(ground)):
        if p["ramp"][f] == 0.0:
            assert res["poses"][f] == model.poses[f] or all(res["poses"][f][b] == model.poses[f][b] for b in range(len(model.bones)))
    for b in ("foot_r", "calf_r", "hand_l", "hand_r", "head"):
        i = model.index[b]
        assert all(math.dist(res["poses"][f][i][1], model.poses[f][i][1]) < 1e-9 for f in range(len(ground)))
    ls = res["leg_samples"][0]
    # 접지 = 발목 또는 발볼(발볼 접지가 발목보다 2 프레임 길다) — 그 프레임도 pin
    assert ls["side"] == "l" and ls["ground"] + ls["air"] == len(on) and ls["ground"] >= len(planted) and ls["windows"]
    assert "pins" in res["pose_from"][0]["blocked_by"]


# ---- 발 회전 목표 (U6-c · 결정 ③) ----
def _foot_target(balls):
    frames = fx.bump(BENT, LIFT, n=40, lo=16, hi=21, ramp=6)
    model = bm.BodyModel(fx.make_model(frames))
    cfg = bf.normalize({**LEGS_ONLY, "targets": [{"id": "turn", "effector": "foot_r", "at": {"window": [0.3, 0.8]}, "rotation": {"offset_deg": [0.0, 20.0, 0.0]},
                                                  "ease_s": 0.1}]})
    rig = bf.Rig(model)
    targets = bf.resolve_targets(rig, cfg["targets"], None, cfg["joints"])
    res = bf.solve(model, cfg, grip=bf.grip_weights(rig, cfg["grip"], model.scale), targets=targets, balls=balls)
    return model, res, targets[0]


def test_foot_rotation_target_turns_the_planted_foot_about_the_ball():
    model, res, t = _foot_target(BALLS)
    rec = res["targets"][0]
    assert rec["reached"] and rec["achieved"]["error_deg_max"] < 0.5
    assert rec["pivot"]["point"] == "ball" and rec["pivot"]["planted_frames"] == len(t["rot"]) and rec["pivot"]["ball_cm_max"] < 1e-3
    fi = model.index["foot_r"]
    off = BALLS["r"]["offset_cm"]
    peak = t["frames"][0] + 2
    assert math.dist(res["poses"][peak][fi][1], model.poses[peak][fi][1]) > 1.0                                   # 발목은 발볼 둘레로 쓸린다
    assert math.dist(bm.transform_point(res["poses"][peak][fi], off), bm.transform_point(model.poses[peak][fi], off)) < 1e-3
    out = [f for f in range(len(model.frames)) if f not in t["rot"]]
    assert all(res["poses"][f][fi] == model.poses[f][fi] for f in out)                                          # 구간 ± 완급 밖 그대로


def test_foot_rotation_without_a_ball_turns_about_the_ankle():
    model, res, t = _foot_target(None)
    rec = res["targets"][0]
    assert rec["pivot"]["point"] == "ankle" and rec["pivot"]["ankle_cm_max"] < 1e-3 and rec["achieved"]["error_deg_max"] < 0.5
