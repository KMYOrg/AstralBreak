"""Phase 8-4d — body_fit 다리 블록(③ 펴진 다리 무릎 떨림): 요청 fix.body.legs · clearance.mode · swing_path auto 규칙 · 소프트 무릎 · 공중 구간
(접지 경계 · 루프 감아 돎 · 경계 없음) · 저크 풀이(떨림 감소 · 접지 pin 정확 · 다리 본만) · 한 풀이(팔 블록과 같은 Solver — 팔 결과 불변).

합성 모델 = body_fit_fixture. 걸음 = 왼다리를 들었다 내림(bump — 넓적다리 앞으로 · 무릎 굽힘), 꺾임 = 착지 직전 한 프레임 넓적다리가 튐(8-3 접지
블렌드 흉내)."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import motion_metrics as mm

LEGS_ONLY = {"clearance": {"mode": "off"}, "grip": {"mode": "off"}, "legs": {"swing_path": "on"}}
PEAK = {"thigh_l": (30.0, 0.0, 0.0), "calf_l": (-60.0, 0.0, 0.0)}


def step_frames(n: int = 40, kink: bool = True) -> list[dict]:
    frames = fx.bump({}, PEAK, n=n, lo=16, hi=21, ramp=6)
    if kink:
        f = dict(frames[24])
        f["thigh_l"] = tuple(a + b for a, b in zip(f["thigh_l"], (6.0, 0.0, 0.0)))
        frames[24] = f
    return frames


def setup(frames: list[dict], raw=None, loop: bool = False):
    model = bm.BodyModel(fx.make_model(frames))
    cfg = bf.normalize(raw if raw is not None else LEGS_ONLY)
    rig = bf.Rig(model)
    lp = bf.swing_paths(rig, cfg["legs"], loop=loop)
    return model, cfg, rig, lp


def track(poses, model, bone):
    i = model.index[bone]
    return [list(p[i][1]) for p in poses]


# ---- 요청 ----
def test_legs_defaults_and_clearance_mode():
    cfg = bf.normalize(True)
    assert cfg["legs"] == {"pins": "auto", "swing_path": "auto", "soft_knee": {"start": 0.97, "softness": 0.03}} and cfg["clearance"]["mode"] == "auto"
    cfg = bf.normalize({"legs": {"swing_path": "on", "soft_knee": {"start": 0.95}}, "clearance": {"mode": "off"}})
    assert cfg["legs"]["soft_knee"] == {"start": 0.95, "softness": 0.03} and cfg["clearance"]["mode"] == "off"
    assert bf.normalize({"legs": {"soft_knee": None}})["legs"]["soft_knee"] is None
    assert bf.normalize({"legs": {"soft_knee": True}})["legs"]["soft_knee"] == {"start": 0.97, "softness": 0.03}


@pytest.mark.parametrize("raw, field, reason", [
    ({"legs": {"pins": "off"}}, "fix.body.legs.pins", "BAD_FIELD"),
    ({"legs": {"swing_path": "always"}}, "fix.body.legs.swing_path", "BAD_FIELD"),
    ({"legs": {"soft_knee": {"start": 0.5}}}, "fix.body.legs.soft_knee.start", "BAD_FIELD"),
    ({"legs": {"soft_knee": {"start": 0.99, "softness": 0.05}}}, "fix.body.legs.soft_knee.softness", "BAD_FIELD"),
    ({"legs": {"soft_knee": {"width": 1}}}, "fix.body.legs.soft_knee.width", "UNKNOWN_FIELD"),
    ({"legs": {"soft_knee": 0.97}}, "fix.body.legs.soft_knee", "BAD_FIELD"),
    ({"legs": {"stride": 1}}, "fix.body.legs.stride", "UNKNOWN_FIELD"),
    ({"clearance": {"mode": "measure"}}, "fix.body.clearance.mode", "BAD_FIELD"),
])
def test_legs_rejects(raw, field, reason):
    with pytest.raises(bf.BodyFitError) as exc:
        bf.normalize(raw)
    assert exc.value.field == field and exc.value.reason == reason


def test_swing_mode_auto_follows_the_leg_fix_ops():
    legs = bf.normalize(True)["legs"]
    assert bf.swing_mode(legs, [{"op": "stance_width"}, {"op": "foot_lock"}]) == {"mode": "auto", "on": True, "reason": "fix.ops ['foot_lock', 'stance_width']"}
    off = bf.swing_mode(legs, [{"op": "smooth"}])
    assert not off["on"] and "swing_path on" in off["reason"]
    assert not bf.swing_mode(legs, None)["on"]
    assert bf.swing_mode({**legs, "swing_path": "on"}, None)["on"] and not bf.swing_mode({**legs, "swing_path": "off"}, [{"op": "foot_lock"}])["on"]


def test_soft_reach_is_monotone_continuous_and_bounded():
    soft = {"start": 0.97, "softness": 0.03}
    assert bf.soft_reach(80.0, 100.0, soft) == 80.0 and bf.soft_reach(99.0, 100.0, None) == 99.0
    xs = [96.0 + 0.05 * k for k in range(200)]
    ys = [bf.soft_reach(x, 100.0, soft) for x in xs]
    assert all(b >= a for a, b in zip(ys, ys[1:])) and max(ys) < 100.0
    # 시작점에서 값 · 기울기가 이어진다(기울기 1)
    assert abs(bf.soft_reach(97.0001, 100.0, soft) - 97.0001) < 1e-6
    assert ys[-1] < xs[-1] and bf.soft_reach(98.3, 100.0, soft) < 98.3


# ---- 공중 구간 ----
def test_air_windows_open_loop_and_no_contact():
    c = [True] * 5 + [False] * 4 + [True] * 5 + [False] * 3
    assert bf._air_windows(c, False) == ([[5, 6, 7, 8], [14, 15, 16]], [])
    # 루프 — 끝 프레임(= 첫)은 빼고 감아 돈다: 끝의 공중 · 처음의 공중이 한 구간
    c = [False] * 2 + [True] * 6 + [False] * 3 + [False]
    windows, skipped = bf._air_windows(c, True)
    assert windows == [[8, 9, 10, 0, 1]] and skipped == []
    assert bf._air_windows([False] * 8, False) == ([], [{"frames": [0, 7], "reason": "NO_CONTACT"}])
    assert bf._air_windows([True] * 8, False) == ([], [])


def test_swing_path_reduces_the_kink_and_leaves_contacts_alone():
    model, cfg, rig, lp = setup(step_frames())
    side_l = [w for w in lp["windows"] if w["side"] == "l"]
    assert len(side_l) == 1 and side_l[0]["bounded"] == [True, True] and lp["skipped"] == []
    w = side_l[0]
    # 꺾인 넓적다리(한 프레임)가 만든 무릎 · 발목 떨림을 줄이고, 발목은 몇 cm 안에서만 옮긴다
    assert w["zigzag_model"][1] < 0.1 * w["zigzag_model"][0] and 1.0 < w["ankle_moved_cm_max"] < 10.0
    contacts = lp["contacts"]["l"]
    assert not any(contacts[f] for f in lp["targets"]["l"]) and lp["targets"]["r"] == {}
    fa, fb = w["frames"]
    assert all(not contacts[f] for f in range(fa, fb + 1)) and contacts[fa - 1] and contacts[fb + 1]


def test_solver_moves_only_the_leg_and_pins_the_contacts():
    frames = step_frames()
    model, cfg, rig, lp = setup(frames)
    grip = bf.grip_weights(rig, cfg["grip"], model.scale)
    res = bf.solve(model, cfg, grip=grip, leg_path=lp)
    assert {b["bone"] for b in res["deltas"]["bones"]} == {"thigh_l", "calf_l", "foot_l"}
    contacts = lp["contacts"]["l"]
    foot0, foot1 = track(model.poses, model, "foot_l"), track(res["poses"], model, "foot_l")
    for f, c in enumerate(contacts):
        if c:
            assert math.dist(foot0[f], foot1[f]) < 1e-9          # pin — 접지 프레임은 원래 키 그대로
        else:
            assert math.dist(foot1[f], lp["targets"]["l"][f]) < 1e-3   # 공중 프레임은 짠 경로대로
    # 발 컴포넌트 회전은 그대로(발볼 · 발끝이 발목과 함께 옮겨진다)
    fi = model.index["foot_l"]
    assert all(abs(sum(a * b for a, b in zip(res["poses"][f][fi][0], model.poses[f][fi][0]))) > 1.0 - 1e-6 for f in range(len(frames)))
    # 떨림(무릎 · 발목 트랙)이 준다 — 다리 블록이 bone_deltas · 예측과 같은 풀이에 들어 있다
    tr = lambda poses: [track(poses, model, b) for b in ("calf_l", "foot_l")]  # noqa: E731
    before, after = mm.zigzag(tr(model.poses), model.times, model.scale)["max"], mm.zigzag(tr(res["poses"]), model.times, model.scale)["max"]
    assert after < 0.5 * before
    assert res["leg_path"]["frames"] == sorted(lp["targets"]["l"]) and res["leg_path"]["windows"][0]["side"] == "l"
    # 팔 · 몸통은 그대로
    for b in ("hand_l", "hand_r", "head", "pelvis", "foot_r"):
        assert track(res["poses"], model, b) == track(model.poses, model, b)


def _fit_pair(extra: dict):
    frames = [{**f, **extra} for f in step_frames(kink=True)]
    model = bm.BodyModel(fx.make_model(frames))
    rig = bf.Rig(model)
    with_legs = bf.normalize({"legs": {"swing_path": "on"}})
    grip = bf.grip_weights(rig, with_legs["grip"], model.scale)
    a = bf.solve(model, with_legs, grip=grip, leg_path=bf.swing_paths(rig, with_legs["legs"]))
    b = bf.solve(model, bf.normalize(True), grip=grip)
    return a, b


def _arms(r: dict) -> dict:
    return {e["bone"]: e["rotation_deg"] for e in r["deltas"]["bones"] if not e["bone"].startswith(("thigh", "calf", "foot"))}


def test_legs_and_arms_are_one_solve_and_independent_when_the_hands_are_away_from_the_legs():
    # 두 아래팔이 배를 뚫고(grip_close — 손은 엉덩 위) 왼다리가 걷는다 — 골반이 고정이면 다리와 팔은 따로라 팔 결과 = 다리 없이 푼 것
    a, b = _fit_pair(fx.grip_close())
    assert _arms(a) == _arms(b) and _arms(a)
    assert {"thigh_l", "calf_l", "foot_l"} <= {e["bone"] for e in a["deltas"]["bones"]}


def test_the_arm_block_sees_the_new_thigh_in_the_same_solve():
    # 왼손이 왼 넓적다리 옆(위팔 10° 안으로) — 넓적다리가 새 경로로 움직이면 팔 블록이 같은 풀이에서 그 넓적다리를 보고 피한다(부위별 순차 보정이면
    # 다리를 나중에 고친 만큼 새 관통이 남는다)
    a, b = _fit_pair(fx.into_body(10.0))
    assert _arms(a) != _arms(b)
    for key, st in a["predicted"]["pairs"].items():
        if key.split("|")[1] in ("hand", "forearm") and key.endswith("thigh_l"):
            assert st["depth_max"] <= 1.15, (key, st)


def test_clearance_off_measures_but_does_not_move_the_arms():
    frames = [fx.into_body(18.0) for _ in range(30)]
    model = bm.BodyModel(fx.make_model(frames))
    rig = bf.Rig(model)
    cfg = bf.normalize({"clearance": {"mode": "off"}})
    res = bf.solve(model, cfg, grip=bf.grip_weights(rig, cfg["grip"], model.scale))
    assert res["deltas"]["bones"] == [] and res["predicted"]["pairs"] and max(v["depth_max"] for v in res["predicted"]["pairs"].values()) > 2.0


def test_loop_window_wraps_and_the_seam_matches():
    n = 41   # 끝 프레임 = 첫 프레임(루프 애셋 관례)
    m = n - 1

    def w(f):
        d = min(f % m, m - f % m)
        return 1.0 if d <= 3 else max(0.0, 1.0 - (d - 3) / 6.0)
    frames = [fx.blend({}, PEAK, w(f)) for f in range(n)]
    frames[2] = dict(frames[2], thigh_l=tuple(a + b for a, b in zip(frames[2]["thigh_l"], (6.0, 0.0, 0.0))))
    model, cfg, rig, lp = setup(frames, loop=True)
    wins = [x for x in lp["windows"] if x["side"] == "l"]
    assert len(wins) == 1 and wins[0]["frames"][0] > wins[0]["frames"][1]   # 이음매를 건너는 구간(시작 > 끝)
    t = lp["targets"]["l"]
    assert 0 in t and t[n - 1] == t[0] and wins[0]["zigzag_model"][1] < wins[0]["zigzag_model"][0]


def test_without_legs_in_the_model_the_path_is_skipped():
    model, cfg, rig, _ = setup(step_frames(kink=False))
    rig.legs = {"l": rig.legs["l"]}
    lp = bf.swing_paths(rig, cfg["legs"])
    assert lp["targets"] == {} and lp["skipped"] == [{"side": None, "reason": "NO_LEGS"}]


def test_swing_path_is_deterministic():
    _, _, _, a = setup(step_frames())
    _, _, _, b = setup(step_frames())
    assert a["targets"] == b["targets"] and a["windows"] == b["windows"]
