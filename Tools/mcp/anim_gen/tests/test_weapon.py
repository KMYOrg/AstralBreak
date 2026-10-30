"""Phase 8-4c — 무기 파지(weapon 모드): 요청 weapon · 메시 사실 풀기(weapon.resolve) · 풀이(손잡이 선분 · 미끄러짐 · 무기 공간 회전 · 손목 굽힘 상한 ·
구간 블렌드 · 마무리) · weapon_tip · 런타임 IK(keep) · 무기-몸 기록.

합성 장면: body_fit_fixture 의 grip_front(두 손 가슴 앞) 동작에 무기를 오른손(hand_r)에 항등으로 붙인다(무기 메시 공간 = hand_r 로컬). 손잡이 = 0 번
프레임 왼 손바닥 점(손목 · 가운데 손가락 뿌리 중점)에서 4 cm 옆을 지나는 ±6 cm 선분, 회전 = 0 번 프레임 왼손의 무기 공간 회전을 25° 돌린 것 — 원래
왼손은 손잡이에서 4 cm · 29° 떨어져 있다."""
from __future__ import annotations

import math

import pytest

import body_fit_fixture as fx
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import weapon as wp

FRAMES = fx.bump(fx.grip_front(), fx.grip_front({"lowerarm_l": (75.0, 0.0, 0.0)}))


@pytest.fixture(autouse=True)
def no_lead_clear(monkeypatch):
    # 합성 두 손은 8 cm 간격(실제 양손 파지보다 가깝다)이라 손잡이에서 주 손 자리(± WEAPON_LEAD_CLEAR_CM)를 빼면 장면이 달라진다 — 그 규칙은
    # test_lead_hand_zone_is_cut_out_of_the_handle 에서만 본다
    monkeypatch.setattr(bf, "WEAPON_LEAD_CLEAR_CM", 0.0)


def scene(frames=None, *, rot_deg=25.0, rot_axis=(0.0, 0.0, 1.0), offset=(0.0, 4.0, 0.0), half=6.0, tol=10.0, tip=(0.0, 0.0, -40.0), points=None, grip=None,
          mode="weapon", runtime_ik=False):
    model = bm.BodyModel(fx.make_model(frames or FRAMES))
    rig = bf.Rig(model)
    p0 = model.poses[0]
    hr, hl, ml = (model.index[b] for b in ("hand_r", "hand_l", "middle_01_l"))
    palm = bm.qrot(bm.qconj(p0[hr][0]), bm._sub(bm._scale(bm._add(p0[hl][1], p0[ml][1]), 0.5), p0[hr][1]))
    mid = bm._add(palm, offset)
    rot_w = bm.qmul(bm.qmul(bm.qconj(p0[hr][0]), p0[hl][0]), bf.qexp(bm._scale(rot_axis, math.radians(rot_deg))))
    resolved = {"mesh": "/Game/W/SKM_Test", "bone": "hand_r", "local": [[0, 0, 0, 1], [0, 0, 0], [1, 1, 1]], "lead": "r", "tip": list(tip) if tip else None,
                "points": points or [], "grip": {"hand": "l", "from": list(bm._add(mid, (-half, 0.0, 0.0))), "to": list(bm._add(mid, (half, 0.0, 0.0))),
                                                  "rotation": list(rot_w), "tol_deg": tol, "runtime_ik": runtime_ik, "form": "segment"},
                "hand": {"middle": "middle_01_l"}}
    cfg = bf.normalize({"grip": {"wrist_bend_max_deg": 40.0, **(grip or {})}})
    w = bf.WeaponRig(rig, resolved, mode=mode, wrist_bend_max_deg=cfg["grip"]["wrist_bend_max_deg"])
    g = bf.grip_weights(rig, {**cfg["grip"], "mode": mode}, model.scale, w)
    return model, rig, cfg, w, g


def solve(model, cfg, w, g, targets=None):
    return bf.solve(model, cfg, grip=g, targets=targets, weapon=w)


def weapon_turn_deg(w, before, after) -> float:
    return max(math.degrees(bm._norm(bf.qlog(bm.qmul(w.frame(a)[0], bm.qconj(w.frame(b)[0]))))) for a, b in zip(after, before))


# ---- 요청 ----
SICKLE = {"mesh": "/Game/Equipment/Weapon/Mesh/SKM_Hero_Sickle", "attach": {"socket": "WeaponHandR", "offset": {"location": [-8.582, 3.961, 56.356]}},
          "grips": [{"hand": "left", "segment": {"from": [9.93, -1.78, -70.26], "to": [9.72, -1.78, -36.67]}, "rotation": [0, 0, 0, 1]}],
          "tip": {"socket": "TraceEnd"}}


def test_weapon_request_fills_defaults():
    w = wp.normalize(SICKLE)
    assert w["lead_hand"] == "right" and w["attach"]["offset"]["rotation"] == [0.0, 0.0, 0.0] and w["attach"]["offset"]["scale"] == [1.0, 1.0, 1.0]
    g = w["grips"][0]
    assert g["form"] == "segment" and g["rotation_tol_deg"] == 10.0 and g["runtime_ik"] is False and wp.off_grip(w) is g
    assert wp.attachment(w) == {"mesh": SICKLE["mesh"], "socket": "WeaponHandR", "offset": w["attach"]["offset"]}
    assert wp.normalize(None) is None


@pytest.mark.parametrize("patch, field, reason", [
    ({"mesh": None}, "weapon.mesh", "MISSING_FIELD"),
    ({"color": 1}, "weapon.color", "UNKNOWN_FIELD"),
    ({"attach": {"socket": "A", "bone": "hand_r"}}, "weapon.attach", "BAD_FIELD"),
    ({"lead_hand": "both"}, "weapon.lead_hand", "BAD_FIELD"),
    ({"grips": [{"hand": "right", "socket": "G"}]}, "weapon.grips[0].hand", "BAD_FIELD"),
    ({"grips": [{"hand": "left", "socket": "G", "segment": {"from": [0, 0, 0], "to": [0, 0, 1]}}]}, "weapon.grips[0]", "CONFLICTING_FIELDS"),
    ({"grips": [{"hand": "left"}]}, "weapon.grips[0]", "MISSING_FIELD"),
    ({"grips": [{"hand": "left", "socket": "G", "rotation": [0, 0, 0]}]}, "weapon.grips[0].rotation", "BAD_FIELD"),
    ({"tip": {"socket": "A", "point_cm": [0, 0, 1]}}, "weapon.tip", "BAD_FIELD"),
])
def test_weapon_request_rejects(patch, field, reason):
    with pytest.raises(wp.WeaponError) as exc:
        wp.normalize({**SICKLE, **patch})
    assert exc.value.field == field and exc.value.reason == reason


def test_grip_mode_weapon_is_opt_in():
    # 무기 파지는 옵트인(사용자 결정 2026-10-29) — auto 는 무기가 있어도 keep(손잡이 관계만 기록), weapon 은 요청이 줄 때만
    w = wp.normalize(SICKLE)
    auto = bf.normalize(True)["grip"]
    assert bf.grip_mode(auto, None) == "auto" and bf.grip_mode(auto, w) == "keep" and bf.grip_mode({**auto, "mode": "weapon"}, w) == "weapon"
    rifle = wp.normalize({**SICKLE, "grips": [{"hand": "left", "socket": "LeftHandIK", "runtime_ik": True}]})
    assert bf.grip_mode(auto, rifle) == "keep"
    with pytest.raises(bf.BodyFitError) as exc:
        bf.grip_mode({**auto, "mode": "weapon"}, rifle)
    assert exc.value.reason == "WEAPON_GRIP_UNKNOWN"
    with pytest.raises(bf.BodyFitError):
        bf.grip_mode({**auto, "mode": "weapon"}, None)
    assert bf.grip_mode({**auto, "mode": "off"}, w) == "off"


# ---- 메시 사실 ----
def target_info(chains=("LeftMiddle", "LeftIndex", "LeftPinky")):
    return {"sockets": [{"name": "WeaponHandR", "bone": "hand_r", "owner": "skeleton", "location": [-3.5, 3.4, -1.0], "rotation": [0.0, 90.0, 0.0]}],
            "finger_chain_suggestion": {"chains": [{"name": c, "start": f"{c[4:].lower()}_01_l", "end": f"{c[4:].lower()}_03_l"} for c in chains]}}


def weapon_info():
    slices = [{"from_cm": -10.0 + 10 * i, "to_cm": 10 * i, "vertices": 10, "width_cm": [4.0, 4.0], "center_cm": [0.0, 0.0]} for i in range(4)]
    slices.append({"from_cm": 30.0, "to_cm": 40.0, "vertices": 30, "width_cm": [40.0, 2.0], "center_cm": [10.0, 0.0]})
    return {"sockets": [{"name": "TraceEnd", "bone": "Root", "owner": "mesh", "location": [0.0, 0.0, 5.0], "rotation": [0.0, 0.0, 0.0]},
                        {"name": "GripA", "bone": "Root", "owner": "mesh", "location": [1.0, 0.0, 0.0], "rotation": [0.0, 0.0, 90.0]},
                        {"name": "GripB", "bone": "Root", "owner": "mesh", "location": [1.0, 0.0, 20.0], "rotation": [0.0, 0.0, 0.0]}],
            "bones": [{"name": "Root", "ref_component": {"t": [0.0, 0.0, 10.0], "r": [0.0, 0.0, 0.0]}}],
            "geometry": {"principal_axes": [{"axis": [0, 0, 1]}, {"axis": [1, 0, 0]}, {"axis": [0, 1, 0]}], "centroid": [0.0, 0.0, 0.0],
                         "slices": {"items": slices}}}


def test_resolve_reads_sockets_chains_and_geometry():
    w = wp.normalize({**SICKLE, "grips": [{"hand": "left", "sockets": ["GripA", "GripB"]}]})
    r = wp.resolve(w, target_info(), weapon_info())
    assert r["bone"] == "hand_r" and r["lead"] == "r" and r["hand"]["middle"] == "middle_01_l" and r["tip"] == [0.0, 0.0, 15.0]
    assert r["grip"]["from"] == [1.0, 0.0, 10.0] and r["grip"]["to"] == [1.0, 0.0, 30.0] and r["grip"]["rotation"] is None
    # 무기 메시 → 부착 본 공간 = compose(offset, 소켓) — E0 와 같은 식(무기 메시 = offset · 소켓 · 손 본)
    hand = (bm.qnormalize((0.1, 0.2, 0.3, 0.9)), (5.0, 6.0, 7.0), (1.0, 1.0, 1.0))
    off = wp.transform_of([-8.582, 3.961, 56.356], [0, 0, 0])
    sock = wp.transform_of([-3.5, 3.4, -1.0], [0.0, 90.0, 0.0])
    p = (2.0, -1.0, 30.0)
    e0 = bm.transform_point(bm.compose(off, bm.compose(sock, hand)), p)
    ours = bm.transform_point(hand, bm.transform_point(tuple(tuple(x) for x in r["local"]), p))
    assert bm._norm(bm._sub(e0, ours)) < 1e-6
    # 자루 = 좁은 단면 4개 중심선(반경 2), 날 단면은 둘째 축 격자
    assert r["handle"]["radius_cm"] == 2.0 and r["handle"]["extent_cm"] == [-20.0, 20.0]
    parts = {p["part"] for p in r["points"]}
    assert parts == {"handle", "head"} and all(p["r"] == 1.0 for p in r["points"] if p["part"] == "head")
    single = wp.resolve(wp.normalize({**SICKLE, "grips": [{"hand": "left", "socket": "GripA"}]}), target_info(), weapon_info())
    assert single["grip"]["from"] == single["grip"]["to"] and single["grip"]["rotation"] == list(wp.quat_from_rotator([0.0, 0.0, 90.0]))


@pytest.mark.parametrize("weapon, target, reason", [
    ({**SICKLE, "attach": {"socket": "Nope"}}, target_info(), "WEAPON_ATTACH_UNKNOWN"),
    ({**SICKLE, "grips": [{"hand": "left", "socket": "Nope"}]}, target_info(), "WEAPON_GRIP_UNKNOWN"),
    (SICKLE, target_info(chains=("LeftIndex",)), "WEAPON_GRIP_UNKNOWN"),
    ({**SICKLE, "tip": {"socket": "Nope"}}, target_info(), "WEAPON_TIP_UNKNOWN"),
])
def test_resolve_refuses_missing_mesh_facts(weapon, target, reason):
    with pytest.raises(wp.WeaponError) as exc:
        wp.resolve(wp.normalize(weapon), target, weapon_info())
    assert exc.value.reason == reason


def test_runtime_ik_grip_needs_no_finger_chains():
    rifle = wp.normalize({**SICKLE, "grips": [{"hand": "left", "socket": "GripA", "runtime_ik": True}]})
    r = wp.resolve(rifle, target_info(chains=()), weapon_info())
    assert r["grip"]["runtime_ik"] and r["hand"] is None


# ---- 풀이 ----
def test_weapon_grip_brings_the_palm_to_the_handle():
    model, rig, cfg, w, g = scene()
    assert len(g["frames"]) == 30 and w.grip["cap"] == pytest.approx(math.radians(40.0))
    res = solve(model, cfg, w, g)
    before, after = res["weapon"]["grip"]["before"], res["weapon"]["grip"]["after"]
    assert before["dist_cm_p95"] >= 3.5 and before["rot_deg_max"] >= 25.0
    # 기준 1 — 손바닥 점 ↔ 손잡이 p95 ≤ 1 · 최대 ≤ 2 cm(합성은 마무리로 0.02 안), 회전은 허용각(10°)까지만
    assert after["dist_cm_max"] <= 0.05 and after["rot_deg_max"] <= 10.0 + 0.5 and after["wrist_bend_deg_max"] <= 40.0
    # 무기 = 주 손의 강체 — 주 손 방향 충실도(keep 층)로 무기는 거의 돌지 않는다, keep 기록은 없다(weapon 모드)
    assert weapon_turn_deg(w, model.poses, res["poses"]) <= 2.0 and res["keep"]["frames"] == 0


def test_the_palm_slides_along_the_handle():
    model, rig, cfg, w, g = scene(offset=(3.0, 4.0, 0.0))
    res = solve(model, cfg, w, g)
    after = res["weapon"]["grip"]["after"]
    lo, hi = after["along_cm"]
    # 가장 가까운 점이 동작을 따라 미끄러진다(선분 12 cm 안) — 고정 점에 묶지 않는다
    assert 0.0 <= lo < hi <= 12.0 and hi - lo >= 1.0 and after["dist_cm_max"] <= 0.05


def test_requested_window_blends_without_a_seam():
    # 60 프레임 — 요청 구간 0.9 ~ 1.2 s(27 ~ 36), 블렌드 0.2 s(6), 매끈화 꼬리(보정 프레임 ± 2·폭 = 12 — 8-4b 와 같다) 밖은 그대로
    frames = fx.bump(fx.grip_front(), fx.grip_front({"lowerarm_l": (75.0, 0.0, 0.0)}), n=60, lo=27, hi=33)
    model, rig, cfg, w, g = scene(frames, grip={"window": [0.9, 1.2]})
    res = solve(model, cfg, w, g)
    hl = model.index["hand_l"]
    blend = int(round(bf.GRIP_BLEND_WEAPON_S * model.fps))
    inside = [f for f in range(60) if g["weights"][f] > 0.0]
    # 요청 구간 27 ~ 36 — 앞의 짧은 빈틈 잇기(GRIP_GAP_FRAMES — 8-4b 그대로)가 시작을 ≤ 2 프레임 앞당긴다
    assert 25 <= g["frames"][0] <= 27 and g["frames"][-1] == 36 and inside == list(range(g["frames"][0] - blend, 36 + blend + 1))
    tail = int(2 * bf.SPLINE_WIDTH * round(cfg["smooth_s"] * model.fps))
    moved = [bm._norm(bm._sub(res["poses"][f][hl][1], model.poses[f][hl][1])) for f in range(60)]
    # 꼬리 밖 ≤ 0.1 cm(8-4b 기준 4 '보정 구간 밖' 값) — 블렌드 아웃이 원래 손을 따르면서(8-4c 후속) 꼬리 프레임(f45 · f46)의 손끼리 맞닿음을 재검사가
    # 한 번 더 풀어 그 꼬리가 0.08 cm 남는다(처음 판은 꼬리 안 이동 5.2 cm · 밖 0)
    assert max(moved[f] for f in range(60) if f < inside[0] - tail or f > inside[-1] + tail) <= 0.1
    assert res["weapon"]["grip"]["after"]["dist_cm_max"] <= 0.05
    # 이음매 — 왼손목 프레임 걸음이 원래 걸음에서 '옮긴 거리 / (블렌드 프레임 수 + 1)' × 목표 보간 최대 기울기(smootherstep 1.875 × 가중 smoothstep 1.5
    # — 8-4c 후속) 안만 달라진다(튀지 않는다 — 합성 옮김 ≈ 5.7 cm, 한 프레임에 옮기면 걸음 차 ≈ 5.7)
    steps = [abs(bm._norm(bm._sub(res["poses"][f + 1][hl][1], res["poses"][f][hl][1])) - bm._norm(bm._sub(model.poses[f + 1][hl][1], model.poses[f][hl][1])))
             for f in range(59)]
    assert max(steps) <= max(moved) / (blend + 1) * 1.875 * 1.5


def test_blend_out_follows_the_original_hand_off_the_handle():
    # 8-4c 후속(사용자 Persona — 운영 Attack2 옵트인 f63 ~ f75 손 겹침): 요청 구간 0.9 ~ 1.2 s(27 ~ 36) 뒤 원래 왼손이 위팔을 내려 손잡이를 떠난다
    # (37 ~ 42 — 4 → 34 cm). 블렌드 프레임의 목표 = 원래 손바닥(무기 강체) → 손잡이 점 smootherstep(가중) 보간 · 가득 가중 — 가중만 줄이던 처음 판은
    # 블렌드 끝까지 손을 손잡이에 붙였다(f40 ~ f42 원래 22 ~ 34 cm 에 0.05 ~ 2.2, 블렌드 뒤 매끈화 꼬리까지 5 ~ 9 cm)
    frames = fx.bump(fx.grip_front(), fx.grip_front({"upperarm_l": (20.0, 0.0, 22.0)}), n=60, lo=42, hi=50)
    model, rig, cfg, w, g = scene(frames, grip={"window": [0.9, 1.2]})
    res = solve(model, cfg, w, g)
    after = res["weapon"]["grip"]["after"]
    assert g["frames"][-1] == 36 and after["dist_cm_max"] <= 0.05
    out = [f for f in range(37, 60) if 0.0 < g["weapon_weights"][f] < 1.0]
    assert out and after["blend"]["frames"] >= len(out) and after["blend"]["target_err_cm_max"] <= 0.3
    sb, sa = bf.measure(model, None)["series"], res["predicted"]["series"]
    hands = [k for k in sb if k[2].startswith(("hand_", "forearm_"))]
    for f in out:
        s = bf._smootherstep(g["weapon_weights"][f])
        d0, d1 = (w.grip_state(f, p[f])["dist"] for p in (model.poses, res["poses"]))
        # 손바닥 ↔ 손잡이 = 원래 거리 × (1 − s) 근처 — 원래 손을 따라 떠난다(손잡이에 남지 않는다)
        assert d1 >= 0.8 * (1.0 - s) * d0 - 0.3, (f, s, d0, d1)
        depth = lambda series: max((series[k][f] for k in hands if series[k][f] is not None), default=-99.0)  # noqa: E731
        assert depth(sa) <= max(depth(sb), model.contact_cm) + 0.2   # 손끼리 새 겹침 없음


def test_wrist_bend_cap_pushes_the_rotation_to_the_arm():
    # 손 로컬 x 둘레 40° — 손목을 굽혀 맞출 수 있는 회전. 상한 40° 면 손목이 굽고, 상한 = max(원래 최대 0(합성 손은 곧다), 요청 0) 이면 손목은 그대로
    # 팔이 대신 돈다(회전 · 파지는 맞는다)
    out = {}
    for cap in (40.0, 0.0):
        model, rig, cfg, w, g = scene(grip={"wrist_bend_max_deg": cap}, rot_deg=40.0, rot_axis=(1.0, 0.0, 0.0))
        out[cap] = solve(model, cfg, w, g)["weapon"]["grip"]["after"]
    assert out[40.0]["wrist_bend_deg_max"] >= 5.0 and out[0.0]["wrist_bend_deg_max"] <= bf.BEND_TOL_DEG + 0.5
    assert all(a["rot_deg_max"] <= 10.0 + 1.0 and a["dist_cm_max"] <= 0.05 for a in out.values())


def test_weapon_tip_target_moves_the_weapon_point():
    model, rig, cfg, w, g = scene()
    tg = bf.normalize({"targets": [{"id": "tip", "effector": "weapon_tip", "at": {"window": [0.3, 0.5]}, "position": {"offset_cm": [6.0, 0.0, 0.0]},
                                    "ease_s": 0.1}]})["targets"]
    targets = bf.resolve_targets(rig, tg, {}, cfg["joints"], w)
    t = targets[0]
    assert t["kind"] == "arm" and t["side"] == "r" and t["bone_name"] == "hand_r" and t["point_local"] == w.tip_local
    res = solve(model, cfg, w, g, targets)
    rep = res["targets"][0]
    assert rep["reached"] and rep["achieved"]["error_cm_p95"] <= 1.0
    assert res["weapon"]["grip"]["after"]["dist_cm_max"] <= 0.5   # 기준 8 — 파지 기준 1 그대로
    with pytest.raises(bf.BodyFitError) as exc:
        bf.resolve_targets(rig, tg, {}, cfg["joints"], None)
    assert exc.value.reason == "WEAPON_TIP_UNKNOWN"


def test_far_off_hand_keeps_the_relation_instead_of_moving():
    # 사용자 결정 '가' — 원래 보조 손이 손잡이에서 WEAPON_NEAR_CM × scale 밖이면 붙이지 않는다(재배치가 된다): 무기 파지 0 프레임 · 띠 프레임은 keep,
    # 해는 keep 모드와 같다(무기 끝 · 기록만 더해진다)
    model, rig, cfg, w, g = scene(offset=(0.0, 30.0, 0.0))
    assert g["weapon_frames"] == [] and g["band_far_frames"] == 30 and g["dist_cm"]["p50"] >= 25.0 and g["keep_weights"] == g["weights"]
    res = solve(model, cfg, w, g)
    model, rig, cfg, wk, gk = scene(offset=(0.0, 30.0, 0.0), mode="keep")
    assert solve(model, cfg, wk, gk)["deltas"] == res["deltas"] and res["keep"]["frames"] == 30 and res["weapon"]["grip"]["after"]["frames"] == 0


def test_rotation_target_defaults_to_the_original_relation():
    # 요청 회전이 없으면 프레임마다 원래 상대 회전(± 허용각) — 원래 오차 0, 붙인 뒤에도 허용각 안
    model, rig, cfg, w, g = scene()
    w.grip["rot"] = None
    res = solve(model, cfg, w, g)
    before, after = res["weapon"]["grip"]["before"], res["weapon"]["grip"]["after"]
    assert before["rot_deg_max"] <= 1e-3 and after["rot_deg_max"] <= 10.0 + 0.5 and after["dist_cm_max"] <= 0.05
    assert after["rotation_target"] == "original_relative" and after["all_frames"]["hands_line_deg_p50"] is not None


def test_lead_hand_zone_is_cut_out_of_the_handle(monkeypatch):
    # 결정 ③ — 손잡이에서 주 손목 자리(± 7 cm × scale)를 뺀 조각 위 가장 가까운 점으로 간다(주 손 위로 끌지 않는다)
    monkeypatch.setattr(bf, "WEAPON_LEAD_CLEAR_CM", 7.0)
    model, rig, cfg, w, g = scene(offset=(0.0, 0.0, 0.0), half=12.0)
    pieces = w.grip["pieces"]
    assert len(pieces) == 2 and pieces[0][1] < pieces[1][0]
    st = w.grip_state(0, model.poses[0])
    lo, hi = pieces[0][1], pieces[1][0]
    assert not (lo < st["s"] < hi) and st["dist"] > 0.5   # 원래 손바닥(주 손 7 cm 안)은 뺀 구간 밖 조각 끝까지 떨어져 있다
    assert set(w.grip["pass_f"]) == {1.0}   # 한쪽에 머무는 자리 안 프레임(두 손이 가까운 파지)은 그대로 조각 끝으로 끈다


def test_crossing_the_lead_hand_zone_follows_the_original_hand(monkeypatch):
    # 8-4c 후속 — 원래 왼손이 손잡이를 따라 주 손 자리를 건너간다(위팔을 안으로 22 → 60°). 가장 가까운 조각 점은 한 프레임에 자리 폭을 건너뛰지만
    # (운영 Attack2 f60 → f61 의 14.7 cm — 손이 반대 손을 꿰뚫거나 순간 이동, 오프라인 떨림 8.2 → 21.8), 그 구간은 통과 비만큼 원래 손바닥을 목표로 잇는다
    monkeypatch.setattr(bf, "WEAPON_LEAD_CLEAR_CM", 7.0)
    frames = [fx.blend(fx.grip_front(), fx.grip_front({"upperarm_l": (60.0, 0.0, 60.0)}), i / 29) for i in range(30)]
    model, rig, cfg, w, g = scene(frames, half=20.0)
    gr = w.grip
    assert len(gr["pieces"]) == 2 and len(set(gr["piece_f"])) == 2 and min(gr["pass_f"]) <= 0.01 and gr["pass_f"][-1] == 1.0
    st = [w.grip_state(f, model.poses[f]) for f in range(30)]
    step = lambda key: max(bm._norm(bm._sub(st[f + 1][key], st[f][key])) for f in range(29))  # noqa: E731
    assert step("closest") >= 8.0 and step("target") <= 2.0 * step("palm")


def test_fast_lead_hand_zone_crossing_is_widened_in_time(monkeypatch):
    # 8-4c 후속 2차 — 원래 왼손이 자리를 3 프레임에 건넌다(운영 Attack2 f59 ~ f61). 위치만 본 통과 비는 한 프레임에 0.86 → 0.09 → 1 로 바뀌어 목표가
    # 손잡이 → 원래 손 → 손잡이로 튀었다(옵트인 f58 ~ f64 팔 튐) → ± GRIP_BLEND_WEAPON_S 로 넓혀 블렌드 폭으로 드나든다(하나의 골 · 프레임 변화 ≤ 0.3)
    monkeypatch.setattr(bf, "WEAPON_LEAD_CLEAR_CM", 7.0)
    frames = [fx.blend(fx.grip_front(), fx.grip_front({"upperarm_l": (60.0, 0.0, 60.0)}), min(1.0, max(0.0, (i - 18) / 3))) for i in range(40)]
    model, rig, cfg, w, g = scene(frames, half=20.0)
    p = w.grip["pass_f"]
    b = round(bf.GRIP_BLEND_WEAPON_S * model.fps)
    low = min(range(40), key=lambda f: p[f])
    assert p[low] <= 0.1 and all(p[f] < 1.0 for f in range(low, low + b)) and p[-1] == 1.0
    assert max(abs(p[f + 1] - p[f]) for f in range(39)) <= 0.3
    assert all(p[f] >= p[f + 1] for f in range(low)) and all(p[f] <= p[f + 1] for f in range(low, 39))


def test_runtime_ik_weapon_keeps_the_keep_path():
    model, rig, cfg, w, g = scene(mode="keep", runtime_ik=True)
    assert w.grip is None and w.tip_local is not None
    res = solve(model, cfg, w, g)
    assert res["weapon"]["grip"] is None and res["keep"]["frames"] == 30
    plain = bf.solve(model, cfg, grip=g)
    assert plain["deltas"] == res["deltas"]   # 무기가 keep 풀이를 바꾸지 않는다(무기 끝 · 기록만)


def test_weapon_body_is_recorded_not_constrained():
    # 무기 점 하나를 몸통 축 위(엉덩 중점 ~ 척추 끝 — 손 기준 로컬)에 둔다 → 관통 기록, 풀이(델타)는 기록 점이 없을 때와 같다
    model0 = bm.BodyModel(fx.make_model(FRAMES))
    p0 = model0.poses[0]
    hr = model0.index["hand_r"]
    inside = bm.qrot(bm.qconj(p0[hr][0]), bm._sub((0.0, 0.0, 110.0), p0[hr][1]))
    pts = [{"p": list(inside), "r": 1.0, "part": "handle"}]
    model, rig, cfg, w, g = scene(points=pts)
    res = solve(model, cfg, w, g)
    body = res["weapon"]["body"]["before"]
    assert body["pairs"] and max(v["depth_max"] for v in body["pairs"].values()) >= 5.0 and body["worst"]["part"] == "handle"
    model, rig, cfg, w2, g = scene()
    assert solve(model, cfg, w2, g)["deltas"] == res["deltas"] and res["weapon"]["body"]["after"] is not None
