"""Phase 9-5b — 비표준 대상(U8-c): 대상 IK Rig(retarget.existing_target_rig)가 체인 · 측정 본의 한 원천이고, 기준 스케일이 있는 스켈레톤은 풀이가 스케일 없이 돈다.
지침서 §14 '9-5b'.

측정 본: 이름 없이 리그 체인에서(발목 = 다리 체인 셋째 본 — C++ 몸 지도 규칙, 골반 = 리그 펠비스) · 리그가 없으면 템플릿 경로 그대로(비트 같음) · 체인도 기본 이름도
없으면 TARGET_CHAINS_UNKNOWN(엉뚱한 본을 재지 않는다). 전달: body_fit 측정 · 샘플 묶음 · validate_animation 크기 보정. 기준 스케일: BodyModel · 무기 부착.
"""
from __future__ import annotations

import base64
import copy
import struct

import pytest

import model_fixture as mf
from anim_gen import body_fit as bf
from anim_gen import body_model as bm
from anim_gen import weapon as wp
from anim_gen.providers.base import StepFailed
from anim_gen.providers.body_fit import BodyFitPipe
from anim_gen.providers.builtin import RetargetPipe, pelvis_arg
from conftest import VESPER, _bone
from test_body_fit_pipe import body, body_request, plan_of  # noqa: F401 — body 는 픽스처
from test_weapon import SICKLE, target_info, weapon_info

NAR = "/Game/Test/SKEL_Nar"
NAR_MESH = "/Game/Test/SK_Nar"
RIG = "/Game/Animation/Test/IK_Nar"
ARMS = {"cl": (2, 2, 111), "up": (10, 1, 109), "el": (24, -2, 100), "wr": (40, 3, 88)}
LEGS = {"th": (7, 2, 78), "kn": (8, 1, 46), "an": (9, -1, 11), "ba": (9, 6, 2)}
NAR_BONES = [_bone("r", None, (0, 0, 0)), _bone("n", "r", (0, 0, 0)), _bone("_p", "n", (0, 2, 82)), _bone("_s", "_p", (0, 3, 97)), _bone("_nk", "_s", (0, 0, 113)),
             _bone("_h", "_nk", (0, 1, 121))]
for side, sign in (("l", 1), ("r", -1)):
    for (name, t), parent in zip(ARMS.items(), ("_s", f"_cl{side}", f"_up{side}", f"_el{side}")):
        NAR_BONES.append(_bone(f"_{name}{side}", parent, (sign * t[0], t[1], t[2])))
    for (name, t), parent in zip(LEGS.items(), ("_p", f"_th{side}", f"_kn{side}", f"_an{side}")):
        NAR_BONES.append(_bone(f"_{name}{side}", parent, (sign * t[0], t[1], t[2])))
CHAINS = [{"name": "Spine", "start": "_s", "end": "_s"}, {"name": "Neck", "start": "_nk", "end": "_nk"}, {"name": "Head", "start": "_h", "end": "_h"},
          {"name": "LeftArm", "start": "_upl", "end": "_wrl"}, {"name": "RightArm", "start": "_upr", "end": "_wrr"},
          {"name": "LeftClavicle", "start": "_cll", "end": "_cll"}, {"name": "RightClavicle", "start": "_clr", "end": "_clr"},
          {"name": "LeftLeg", "start": "_thl", "end": "_bal"}, {"name": "RightLeg", "start": "_thr", "end": "_bar"}]


@pytest.fixture
def nar(fake):
    fake.meshes[NAR] = NAR_MESH
    fake.bones[NAR] = NAR_BONES
    fake.rigs[RIG] = {"asset_path": f"{RIG}.IK_Nar", "pelvis": "_p", "chains": CHAINS}
    return {"rig": RIG, "mesh": NAR_MESH}


# ---- 측정 본 ----
def test_rig_chains_give_every_role_without_a_name(fake, nar):
    diags = []
    b = RetargetPipe.selection_bones(fake.client(), NAR, diags, "select", nar)
    assert b["from"] == "ik_rig" and not diags
    assert (b["hand_l"], b["elbow_l"], b["shoulder_l"]) == ("_wrl", "_ell", "_upl") and (b["hip_r"], b["head"]) == ("_thr", "_h")
    assert (b["foot_l"], b["foot_r"]) == ("_anl", "_anr") and b["knees"] == ["_knl", "_knr"]   # 체인 끝은 발볼 — 발목은 셋째 본(C++ 몸 지도 Feet)
    assert b["pelvis"] == "_p" and pelvis_arg(b) == {"pelvis": "_p"}
    assert b["arm_dims"]["arm_cm"] > 30 and b["leg_dims"]["pelvis_height_cm"] == 82


def test_leg_chain_ending_at_the_ankle_keeps_the_ankle(fake, nar):
    fake.rigs[RIG]["chains"] = [c if not c["name"].endswith("Leg") else {**c, "end": c["end"].replace("_ba", "_an")} for c in CHAINS]
    assert RetargetPipe.selection_bones(fake.client(), NAR, [], "select", nar)["foot_l"] == "_anl"


def test_rig_pelvis_wins_when_the_hip_hangs_from_the_spine(fake, nar):
    # SB(Biped) — 넓적다리의 부모가 Spine 이라 '엉덩의 부모 = 골반'이 틀린다
    fake.bones[NAR] = [{**b, "parent": "_s"} if b["name"].startswith("_th") else b for b in NAR_BONES]
    b = RetargetPipe.selection_bones(fake.client(), NAR, [], "select", nar)
    assert b["pelvis"] == "_p" and b["leg_dims"]["pelvis_height_cm"] == 82 and b["leg_dims"]["rest"]["pelvis"] == [0, 2, 82]


def test_without_a_rig_the_template_path_is_untouched(fake):
    b = RetargetPipe.selection_bones(fake.client(), VESPER, [], "select")
    assert fake.count("create_ik_rig") == 0 and "pelvis" not in b and pelvis_arg(b) == {} and b["from"] in ("default", "template_chains")


def test_no_chain_and_no_default_name_is_refused(fake, nar):
    with pytest.raises(StepFailed) as exc:
        RetargetPipe.selection_bones(fake.client(), NAR, [], "select")
    assert exc.value.reason == "TARGET_CHAINS_UNKNOWN" and "existing_target_rig" in exc.value.message


def test_a_chain_missing_from_the_rig_is_refused_too(fake, nar):
    fake.rigs[RIG]["chains"] = [c for c in CHAINS if c["name"] != "RightArm"]
    with pytest.raises(StepFailed) as exc:
        RetargetPipe.selection_bones(fake.client(), NAR, [], "select", nar)
    assert exc.value.reason == "TARGET_CHAINS_UNKNOWN" and "hand_r" in exc.value.message


# ---- 전달 ----
def test_rig_of_needs_the_rig_and_the_mesh():
    assert RetargetPipe.rig_of({"retarget": {"existing_target_rig": RIG}, "target_mesh": NAR_MESH}) == {"rig": RIG, "mesh": NAR_MESH}
    assert RetargetPipe.rig_of({"retarget": {}, "target_mesh": NAR_MESH}) is None and RetargetPipe.rig_of({"retarget": {"existing_target_rig": RIG}}) is None


def test_plan_without_a_rig_excludes_the_candidate(service, fake, nar, body):
    p = plan_of(service, target_skeleton=NAR, target_mesh=NAR_MESH)
    assert not p["candidates"] and p["excluded"][0]["reason"] == "TARGET_CHAINS_UNKNOWN"


def test_plan_with_a_rig_carries_it_to_the_measurement(service, fake, nar, body):
    p = plan_of(service, target_skeleton=NAR, target_mesh=NAR_MESH, retarget={"existing_target_rig": RIG})
    assert p["candidates"], p["excluded"]
    step = next(s for s in p["candidates"][0]["steps"] if s["step"] == "body_fit")
    assert step["inputs"]["ik_rig"] == RIG and step["inputs"]["bones"]["from"] == "ik_rig"


def test_a_target_rig_leaves_the_ankles_out_of_the_auto_pose(service, fake, nar, body):
    p = plan_of(service, target_skeleton=NAR, target_mesh=NAR_MESH, retarget={"existing_target_rig": RIG})
    service.generate_motion(plan_id=p["plan_id"], save=False)
    rtg = next(prm for tool, prm in fake.calls if tool == "create_ik_retargeter")
    assert rtg["exclude_bones"] == ["_anl", "_anr"] and rtg["target_rig"] == RIG


def test_plan_on_the_reference_body_has_no_rig_keys(service, body):
    step = next(s for s in plan_of(service)["candidates"][0]["steps"] if s["step"] == "body_fit")
    assert "ik_rig" not in step["inputs"] and "pelvis" not in step["inputs"]["bones"]


def test_body_spec_takes_the_rig_of_the_plan_and_the_step_value_first():
    inputs = {"mesh": NAR_MESH, "ik_rig": RIG, "clearance": {"hands": True, "legs": False, "secondary": "off", "map_rule": 2}}
    assert BodyFitPipe.spec(inputs)["ik_rig"] == RIG and BodyFitPipe.spec(inputs, ik_rig="/Game/Other")["ik_rig"] == "/Game/Other"
    assert "ik_rig" not in BodyFitPipe.spec({k: v for k, v in inputs.items() if k != "ik_rig"})


def test_target_info_reads_chains_from_the_rig_for_sample_presets(fake, nar):
    info = BodyFitPipe.inspect_target(fake.client(), {"target_mesh": NAR_MESH, "retarget": {"existing_target_rig": RIG}})
    assert info["template_match"]["pelvis"] == "_p"
    assert bf.bundle_bones(["arm_r"], info)["presets"]["arm_r"] == ["_clr", "_upr", "_elr", "_wrr"]


# ---- 기준 스케일 ----
def scaled_model(k: float) -> dict:
    """C++ 모델의 스케일 스켈레톤 모양 — 컴포넌트 포즈 스케일 k · 본 공간 값 ÷ k(C++ InverseTransformPosition)."""
    raw = copy.deepcopy(mf.make_model())
    data = base64.b64decode(raw["poses"]["b64"])
    flat = list(struct.unpack(f"<{len(data) // 4}f", data))
    for i in range(7, len(flat), 10):
        flat[i:i + 3] = [k, k, k]
    raw["poses"]["b64"] = mf.f32(flat)
    for pt in raw["points"]:
        pt["influences"] = [[i[0], i[1], i[2] / k, i[3] / k, i[4] / k] for i in pt["influences"]]
    return raw


def test_unit_model_is_not_touched():
    model = bm.BodyModel(mf.make_model())
    assert model.bone_scale is None and model.local_translation(1, (1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)


def test_model_scale_within_export_noise_is_unit():
    assert bm.BodyModel(scaled_model(1.0 + bm.SCALE_EPS / 2)).bone_scale is None


def test_scaled_model_solves_in_plain_centimetres():
    plain, scaled = bm.BodyModel(mf.make_model()), bm.BodyModel(scaled_model(100.0))
    assert scaled.bone_scale[0] == pytest.approx((100.0, 100.0, 100.0))
    assert all(s == (1.0, 1.0, 1.0) for row in scaled.poses for _, _, s in row)
    for a, b in zip(plain.local_pose(1), scaled.local_pose(1)):
        assert a[1] == pytest.approx(b[1], abs=1e-3)
    for a, b in zip(plain.points, scaled.points):
        assert plain.skin(plain.poses[1], a) == pytest.approx(scaled.skin(scaled.poses[1], b), abs=1e-3)


def test_solved_translation_goes_back_to_track_units():
    model = bm.BodyModel(scaled_model(100.0))
    assert model.local_translation(0, (5.0, 0.0, 0.0)) == (5.0, 0.0, 0.0)   # 루트 — 부모 스케일이 없다
    assert model.local_translation(1, (5.0, 0.0, 0.0)) == pytest.approx((0.05, 0.0, 0.0))


def test_attachment_on_a_scaled_bone_is_in_centimetres_for_the_solver():
    info = {**target_info(), "bones": [{"name": "_wrr", "ref_component": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [100, 100, 100]}}]}
    off = {"location": [0.01, 0.02, 0.03], "rotation": [0.0, 0.0, 0.0], "scale": [0.01, 0.01, 0.01]}
    scaled = wp.resolve(wp.normalize({**SICKLE, "attach": {"bone": "_wrr", "offset": off}, "grips": []}), info, weapon_info())
    assert scaled["local"][1] == pytest.approx([1.0, 2.0, 3.0]) and scaled["local"][2] == pytest.approx([1.0, 1.0, 1.0])
    plain = wp.resolve(wp.normalize({**SICKLE, "attach": {"bone": "hand_r", "offset": off}, "grips": []}), target_info(), weapon_info())
    assert plain["local"][1] == pytest.approx([0.01, 0.02, 0.03])   # 스케일 없는 본은 그대로
