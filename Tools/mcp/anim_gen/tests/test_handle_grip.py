"""Phase 9-3b — 생성 파지 규칙의 운영 부착 자루(refine.solve_handle_grip · grip.handle weapon) · 키 2차 자유 손 고정 계획.

합성 팔(test_refine 의 FK 포즈)로 시험한다 — 모델 · 에디터를 띄우지 않는다.
"""
from __future__ import annotations

import math

import pytest

from anim_gen.local_ai import refine as rf
from anim_gen.providers import key_pose as kp_step
from conftest import VESPER_MESH
from test_key_pose import _key, kpa, plan_with  # noqa: F401 — kpa 는 fixture
from test_local_ai import KimodoProc, ka  # noqa: F401 — ka 는 fixture
from test_refine import sword_pose

IDENTITY_Q = [0.0, 0.0, 0.0, 1.0]
SICKLE_MESH = "/Game/Equipment/Weapon/Mesh/SKM_Test_Sickle"
GRIP = {"two_hand_weapon_grip": True, "foot_contact": True}
WEAPON = {"mesh": SICKLE_MESH, "attach": {"socket": "WeaponHandR"}, "grips": [{"hand": "left", "segment": {"from": [0, 0, 0], "to": [0, 0, 20]}}]}


def handle(dir_bone, anchor_cm=(0.0, 0.0, 0.0), extent=(-80.0, 80.0), ratio=1.0, q=IDENTITY_Q, cap=None) -> dict:
    out = {"from": "weapon", "bone": "hand_r", "dir_bone": list(dir_bone), "anchor_bone_cm": list(anchor_cm), "extent_cm": list(extent),
           "arm_ratio": ratio, "basis": {"rotation": list(q)}}
    if cap is not None:
        out["wrist_cap_deg"] = cap
    return out


def palms_of(pose: dict) -> dict:
    """보조 손바닥 ≈ 손목 · 손 끝 중점(77 관절 중지 너클 대신 — 합성 팔)."""
    return {s: [rf._mul(rf._add(w, t), 0.5) for w, t in zip(pose["pos"][f"{s}Hand"], pose["pos"][f"{s}HandMiddleEnd"])] for s in ("Left", "Right")}


def test_handle_in_hand_swaps_ue_axes_and_scales_the_offset_to_soma():
    """부착 본 공간 x → 손 공간 S·R_T·x(S = y ↔ z) — 방향은 단위, 오프셋은 cm → m 에 체형 비(대상 / SOMA)로 나눈다."""
    h, o = rf.handle_in_hand(handle([0.0, 0.0, 1.0], anchor_cm=(0.0, 8.53, 0.0), ratio=0.853))
    assert h == pytest.approx([0.0, 1.0, 0.0]) and o == pytest.approx([0.0, 0.0, 0.1])
    q = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]   # UE z 축 90° — x → y
    h, _ = rf.handle_in_hand(handle([1.0, 0.0, 0.0], q=q))
    assert h == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)


def test_the_support_palm_goes_onto_the_attached_handle_and_the_lead_turn_respects_the_caps():
    """자루가 보조 손 쪽을 가리키면 주 손은 거의 그대로, 보조 손바닥이 자루 위(간격 60 cm)로 — 목표의 두 손 선 ∠ 자루 · 손바닥 ↔ 자루 ≈ 0."""
    pose, _ = sword_pose()
    palms = palms_of(pose)
    # 1차 주 손 → 보조 손바닥 방향을 손 공간으로 옮긴 자루(첫 프레임 기준) — 다른 프레임은 몇 도 어긋난다
    g0, w0 = pose["rot"]["RightHand"][0], pose["pos"]["RightHand"][0]
    want = rf._mv(rf._t(g0), rf._unit(rf._sub(palms["Left"][0], w0)))
    out = rf.solve_handle_grip(pose, palms, [0, 1, 2, 3], spacing_cm=60.0, handle=handle(rf._swap(want)))
    hs = out["stats"]["handle"]
    assert out["handle_frame"]["sign"] == 1.0 and hs["turn_needed_deg"]["max"] < 20.0
    assert hs["targets_angle_deg"]["max"] < 1.0 and hs["targets_palm_line_cm"]["max"] < 0.5, hs
    for f, t in out["targets"].items():
        assert rf.norm(rf._sub(t["support"], t["lead"])) * 100.0 == pytest.approx(60.0, abs=3.0)
    # 보조 손은 keep(1차 손목 로컬), 주 손 회전 = 돌린 전역 회전 — 손 끝 관절도 함께
    ch = out["frames"][0]
    assert set(ch) >= {"LeftHand", "LeftArm", "LeftForeArm", "RightHand", "RightHandMiddleEnd"} and out["hand_rule"].startswith("keep")


def test_a_handle_pointing_away_is_turned_only_to_the_wrist_caps_and_the_support_hand_follows_it():
    """자루가 보조 손 반대(뒤)로 향하면 필요한 회전이 크다 — 주 손목 굽힘 ≤ max(1차, 상한) · 비틀기 ≤ 상한까지만 돌리고, 보조 손은 돌린 자루 위로 간다."""
    pose, _ = sword_pose()
    palms = palms_of(pose)
    g0, w0 = pose["rot"]["RightHand"][0], pose["pos"]["RightHand"][0]
    away = rf._mv(rf._t(g0), rf._unit(rf._cross(rf._sub(palms["Left"][0], w0), [0.0, 1.0, 0.0])))   # 두 손 선에 수직
    out = rf.solve_handle_grip(pose, palms, [0, 1, 2, 3], spacing_cm=60.0, handle=handle(rf._swap(away), cap=30.0))
    hs = out["stats"]["handle"]
    assert hs["turn_needed_deg"]["p50"] > 60.0 and hs["capped_pct"] > 0.0
    assert hs["turn_applied_deg"]["max"] < hs["turn_needed_deg"]["max"]
    assert hs["lead_wrist_bend_deg"]["targets"]["max"] <= max(hs["lead_wrist_bend_deg"]["pass1"]["max"], 30.0) + 0.5
    assert hs["lead_twist_deg"]["max"] <= rf.HANDLE_TWIST_CAP_DEG + 0.5
    # 손이 닿으면 목표는 여전히 자루 위(닿지 못한 프레임만 남는다)
    if out["stats"]["clamped"] == 0:
        assert hs["targets_palm_line_cm"]["max"] < 0.5


def test_plan_carries_the_handle_only_when_asked():
    """refine.plan — handle 이 있으면 파지 규칙에 싣고(축 · 포즈 설명), 없으면 지금 규칙 그대로(비트 같다)."""
    flags = {"two_hand_weapon_grip": True}
    cfg = {"mode": "auto", "grip": {"lead_hand": "right", "target": "meet", "spacing_cm": 75.0, "target_spacing_cm": None, "from_s": None, "to_s": None},
           "keyframe_step": 3}
    plain = rf.plan(flags, cfg, frames=91, fps=30.0, requested_root=False)
    assert plain == rf.plan(flags, cfg, frames=91, fps=30.0, requested_root=False, handle=None)
    h = handle([0.0, 0.0, 1.0])
    with_h = rf.plan(flags, cfg, frames=91, fps=30.0, requested_root=False, handle=h)
    rule = next(r for r in with_h["rules"] if r["flag"] == "two_hand_weapon_grip")
    assert rule["handle"] == h and "attached handle" in rule["axis"] and "handle" not in next(r for r in plain["rules"] if r["flag"])


# ---- ⓪ 키 2차의 자유 손 고정 (계획) ----
def test_hand_and_foot_keys_hold_the_free_hand_around_the_keys(kpa):
    """오른손 · 왼발 키(pass1) — 2차가 왼손을 1차에 묶는다(키 ± 15 프레임). 전신 키 · origin 키 · 파지 2차가 손을 맡으면 묶지 않는다(9-3a 계획 그대로)."""
    p = plan_with(kpa, [_key(at=[1.0], part="right_hand"), _key(at=[1.0], part="left_foot")])
    gen = p["candidates"][0]["steps"][1]["inputs"]["key_pose"]
    assert gen["hold_free_hands"]["hands"] == ["left_hand"] and gen["hold_free_hands"]["window_frames"] == 15 and gen["hold_free_hands"]["around_frames"] == [30]
    assert "KEY_POSE_HANDS_HELD" in {lm["code"] for lm in p["candidates"][0]["expected_limitations"]}
    for constraints in ([_key(at=[1.0])], [_key(at=[0.0], part="right_hand")]):
        assert "hold_free_hands" not in plan_with(kpa, constraints)["candidates"][0]["steps"][1]["inputs"]["key_pose"]
    env = kpa.service.plan_motion_generation(request=_grip_request([_key(at=[1.0], part="right_hand")]))
    gen = next(s for s in env["result"]["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]["key_pose"]
    assert "hold_free_hands" not in gen


# ---- ① 운영 부착 자루 (계획 · 실행) ----
def _grip_request(constraints=None, grip=None, **over) -> dict:
    from test_local_ai import ai_request
    req = ai_request(motion_category="weapon_action", constraints=GRIP, weapon=WEAPON, animation_name="AS_Vesper_Sickle_HandleP93b",
                     generation={"seed": 7, "candidates": 2, "constraints": constraints or [],
                                 "refine": {"grip": {"target_spacing_cm": 60.0, **(grip or {})}}})
    req.update(over)
    return req


@pytest.fixture
def hka(kpa):
    from test_weapon import target_info, weapon_info
    kpa.fake.mesh_inspect[VESPER_MESH] = {**target_info(), "finger_chain_suggestion": {"chains": [{"name": f"{s}Middle", "start": f"middle_01_{x}", "end": f"middle_03_{x}"}
                                                                                                  for s, x in (("Left", "l"), ("Right", "r"))]}}
    kpa.fake.mesh_inspect[SICKLE_MESH] = weapon_info()
    return kpa


def test_plan_puts_the_hand_basis_step_and_the_handle_on_the_grip_rule(hka):
    env = hka.service.plan_motion_generation(request=_grip_request(grip={"handle": "weapon"}))
    assert env["ok"], env["error"]
    cand = env["result"]["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    assert steps[:2] == ["hand_basis", "generate"]
    basis = cand["steps"][0]["inputs"]
    assert basis["items"] == [] and basis["hand_basis"]["bone"] == "hand_r" and basis["align_mode"] == "per_bone"
    rule = next(r for r in cand["steps"][1]["inputs"]["refine"]["rules"] if r["flag"] == "two_hand_weapon_grip")
    h = rule["handle"]
    assert h["bone"] == "hand_r" and abs(math.sqrt(sum(x * x for x in h["dir_bone"])) - 1.0) < 1e-5 and h["extent_cm"][0] < h["extent_cm"][1]
    assert 0.5 < h["arm_ratio"] < 1.2 and h["wrist_cap_deg"] == rf.HANDLE_WRIST_CAP_DEG and "GRIP_HANDLE_BASIS" in {lm["code"] for lm in cand["expected_limitations"]}
    # handle 없는 같은 요청 — 단계 · 규칙이 지금 그대로
    env = hka.service.plan_motion_generation(request=_grip_request())
    cand = env["result"]["candidates"][0]
    assert cand["steps"][0]["step"] == "generate" and all("handle" not in r for r in cand["steps"][0]["inputs"]["refine"]["rules"])
    # 키 포즈와 함께면 key_pose 단계 하나가 둘 다
    env = hka.service.plan_motion_generation(request=_grip_request([_key(at=[1.0])], grip={"handle": "weapon"}))
    first = env["result"]["candidates"][0]["steps"][0]
    assert first["step"] == "key_pose" and first["inputs"]["hand_basis"]["bone"] == "hand_r" and first["inputs"]["items"]


@pytest.mark.parametrize("over, reason", [
    ({"weapon": None}, "GRIP_HANDLE_NEEDS_WEAPON"),
    ({"constraints": {"foot_contact": True}}, "GRIP_HANDLE_NEEDS_GRIP"),
    ({"grip_spacing": None}, "GRIP_HANDLE_NEEDS_SPACING"),
])
def test_the_handle_rule_blocks_what_it_cannot_follow(hka, over, reason):
    req = _grip_request(grip={"handle": "weapon"})
    if over.pop("grip_spacing", "x") is None:
        req["generation"]["refine"]["grip"].pop("target_spacing_cm")
    req.update(over)
    env = hka.service.plan_motion_generation(request=req)
    assert {e["provider"]: e["reason"] for e in env["result"]["excluded"]}.get("local_ai") == reason


def test_request_checks_the_handle_value(service):
    from conftest import request
    env = service.plan_motion_generation(request=request(prompt="x", generation={"refine": {"grip": {"handle": "blade"}}}))
    assert not env["ok"] and env["error"]["details"]["field"] == "generation.refine.grip.handle"


def test_hand_basis_step_measures_the_attach_bone_and_kimodo_gets_it_on_the_rule(hka, monkeypatch):
    def fake_blender(ctx, bvh_path, out_dir):
        fbx = out_dir / "SOMA_TPose_Rest.fbx"
        fbx.write_bytes(b"fbx")
        return fbx
    monkeypatch.setattr(kp_step, "run_blender", fake_blender)
    q = [0.1, 0.2, 0.3, math.sqrt(1.0 - 0.14)]
    hka.fake.profiles["KPB_Mock_Anim"] = {"tracks": {"hand_r": {"pos": [[0.0, 0.0, 0.0]] * 2, "rot": [q] * 2}}}
    env = hka.service.plan_motion_generation(request=_grip_request(grip={"handle": "weapon"}))
    job = hka.service.generate_motion(plan_id=env["result"]["plan_id"], save=True)["result"]
    assert job["status"] == "RUNNING" and job["stage"] == "generate", job.get("error")
    assert job["hand_basis"]["bone"] == "hand_r" and job["hand_basis"]["rotation"] == pytest.approx(q) and "key_pose" not in job
    rtg = [prm for tool, prm in hka.fake.calls if tool == "create_ik_retargeter"]
    assert len(rtg) == 1 and rtg[0]["asset_path"].endswith("/KeyPose/RTG_Basis") and rtg[0]["target_mesh"] == VESPER_MESH   # 정방향 SOMA → 대상
    args = hka.launcher.of(KimodoProc)[-1].args
    rule = next(r for r in args["refine"]["rules"] if r["flag"] == "two_hand_weapon_grip")
    assert rule["handle"]["basis"]["rotation"] == pytest.approx(q) and "key_pose_file" not in args
