"""Phase 9-4b — 손 부근 마무리(_finish_hands) · 파지 빈틈 잇기(U4-c) · 닫힌 손목 이어 받기(_open_start) · 팔 교차 · 주 손목 상한 순수 테스트."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import motion_metrics as mm

FINGERS = {"l": "middle_01_l", "r": "middle_01_r"}


def test_grip_gaps_are_filled_only_after_a_grip_frame():
    # U4-c — 짧은 빈틈(≤ GRIP_GAP_FRAMES)은 앞 프레임이 파지일 때만 잇는다. 8-4b 판은 긴 비파지 구간의 마지막 ≤ 2 프레임도 채워 구간 시작이 앞당겨졌다
    lead = [False] * 4 + [True] * 6
    assert bf._flag_weights(lead, 30.0, 0.0)[1] == [(4, 9)]
    gap = [True] * 5 + [False] * 2 + [True] * 5
    assert bf._flag_weights(gap, 30.0, 0.0)[1] == [(0, 11)]
    wide = [True] * 5 + [False] * 3 + [True] * 5
    assert bf._flag_weights(wide, 30.0, 0.0)[1] == [(0, 4), (8, 12)]


def test_open_start_keeps_closed_wrists_at_the_frame_value():
    # 본 풀이 첫 회는 앞 프레임 해를 이어 받는다 — 그 프레임에서 닫힌 손목(파지 밖)의 델타는 그 프레임 자신의 값(s27 f68 ~ f95 오른손 27° 이어 받기)
    model = bm.BodyModel(fx.make_model([fx.grip_front() for _ in range(3)] + [{} for _ in range(8)]))
    cfg = bf.normalize(True)
    s = bf.Solver(model, cfg, grip=bf.grip_weights(bf.Rig(model), cfg["grip"], model.scale))
    ix = model.index
    hl, ul = ix["hand_l"], ix["upperarm_l"]
    start = {"rot": {hl: (0.1, 0.0, 0.0), ul: (0.0, 0.2, 0.0)}, "trans": {}}
    zero = {"rot": {}, "trans": {}}
    assert s.grip["weights"][9] == 0.0 and hl not in s._joints(9) and hl in s._joints(0)
    out = s._open_start(9, start, zero)
    assert hl not in out["rot"] and out["rot"][ul] == (0.0, 0.2, 0.0) and start["rot"][hl] == (0.1, 0.0, 0.0)
    base = {"rot": {hl: (0.0, 0.05, 0.0)}, "trans": {}}
    assert s._open_start(9, start, base)["rot"][hl] == (0.0, 0.05, 0.0)
    assert s._open_start(0, start, zero) is start   # 손목을 연 파지 프레임은 그대로


def test_cross_floor_is_the_original_or_inside_the_threshold():
    model = bm.BodyModel(fx.make_model([{} for _ in range(4)]))
    s = bf.Solver(model, bf.normalize(True))
    thr = mm.CROSS_CM * model.scale
    for f in range(4):
        lat = s._lateral(f, model.poses[f])[0]
        assert s.cross_floor[f] == pytest.approx(min(-thr + bf.CROSS_MARGIN_CM * model.scale, lat))
    # 좌우 차가 허용보다 작으면(더 교차) 두 손목을 좌우로 미는 잔차 — 층 cross
    s.cross_floor = [s._lateral(f, model.poses[f])[0] + 5.0 for f in range(4)]
    zero = {"rot": {}, "trans": {}}
    ev = s.evaluate(1, zero, {"rot": {}, "trans": {}}, {"cross"}, [], s._joints(1))
    assert ev["info"]["cross_cm"] == pytest.approx(5.0) and ev["cost"] == pytest.approx((10.0 * bf.HAND_TIER["cross"] * 5.0) ** 2)
    st, _ = s.solve_frame(1, zero, {"rot": {}, "trans": {}, "pose": model.poses[1], "prev": None}, {"cross", "fid"}, [])
    assert s._lateral(1, s.pose(1, st)[0])[0] > s._lateral(1, model.poses[1])[0] + 1.0


def test_lead_wrist_cap_is_only_in_the_hand_finish_of_grip_frames():
    frames = [fx.grip_front() for _ in range(5)] + [{} for _ in range(5)]
    model = bm.BodyModel(fx.make_model(frames))
    cfg = bf.normalize(True)
    s = bf.Solver(model, cfg, grip=bf.grip_weights(bf.Rig(model), cfg["grip"], model.scale), fingers=FINGERS)
    lb = s.lead_br
    assert lb["side"] == "r" and lb["caps"][9] is None
    state = {"rot": {model.index["hand_r"]: (math.radians(12.0), 0.0, 0.0)}, "trans": {}}
    bend = bf.WeaponRig.bend(s.pose(0, state)[0], lb["elbow"], lb["wrist"], lb["middle"])
    over = bend - lb["caps"][0]
    assert over > 0.0
    assert s.evaluate(0, state, {"rot": {}, "trans": {}}, {"bend"}, [], s._joints(0))["cost"] == 0.0   # 본 풀이 · 무기 마무리는 보조 손만
    s.hand_mode = True
    ev = s.evaluate(0, state, {"rot": {}, "trans": {}}, {"bend"}, [], s._joints(0))
    assert ev["cost"] == pytest.approx((10.0 * bf.HAND_TIER["lead_bend"] * over * bf.ROT_CM) ** 2, rel=1e-4)


def test_hand_finish_holds_the_lead_hand_and_records_itself():
    # 보조 손목을 펴는 파지 — 손 부근 마무리가 처리한 프레임 · 주 손 붙들기 · 지난 상태와 같은 처리 밖 프레임
    frames = fx.bump(fx.grip_close(), fx.grip_close({"upperarm_l": (-30.0, 0.0, 35.0)}))
    model = bm.BodyModel(fx.make_model(frames))
    cfg = bf.normalize(True)
    grip = bf.grip_weights(bf.Rig(model), cfg["grip"], model.scale)
    res = bf.solve(model, cfg, grip=grip, fingers=FINGERS)
    hf = res["stats"]["hand_finish"]
    assert set(hf) == set(bf.HAND_FINISH_KEYS) and hf["frames"] and hf["cross"] == [] and res["wrist_bend"]["lead"]["tol_deg"] == bf.LEAD_BEND_TOL_DEG
    assert res["wrist_bend"]["over_cap_frames"] == 0 and res["wrist_bend"]["lead"]["over_cap_frames"] == 0
