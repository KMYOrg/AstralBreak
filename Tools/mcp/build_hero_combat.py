"""히어로 전투 AnimBP(근접 낫 · 원거리 총) 를 도구만으로 구성한다 — Lyra 식 Linked Anim Layer (2026-10-19 사용자 확정).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/build_hero_combat.py [--overwrite] [--verify-only]

산출 (전부 /Game/Animation/Hero 아래, 저장):
  Anims/Locomotions/AO_Hero_Rifle       AimOffset 2D (Yaw -90..90 × Pitch -90..90, AS_Hero_AO_Rifle* 9샘플; CC 기준 포즈는 여기서 먼저 지정)
  Anims/Locomotions/BS_Hero_Rifle_Strafe 2D (Direction -180..180 × Speed 0..500) — 조준 중 8방향 Jog + Idle
  Anims/Locomotions/BS_Hero_Rifle_Jog    1D (Speed 0..500) — 비조준 라이플 이동 (Idle → JogFwd)
  ALI_HeroCombat                         레이어 인터페이스: Locomotion_Idle · Locomotion_Move (입력 없음) · Aim_UpperBody (입력 포즈 InPose)
  ABP_Hero_Combat                        베이스 ABP(부모 UAstralAnimInstance): 운영 ABP_Hero_Base 의 상태머신·슬롯·UpperBody 레이어 1:1 +
                                         Idle/Move 상태 내부는 레이어 노드, LayeredBoneBlend 뒤에 Aim_UpperBody 레이어. 기본 구현 = 근접(낫) 세트
  ABP_HeroLayers_Rifle                   원거리 공급자(인터페이스 구현; BlendListByBool 은 BlendPose_0 = True): Idle = AS_Hero_Rifle_Idle (조준 여부 무관 — AO 기준 포즈; 분기 노드는 유지) ·
                                         Move = bIsAiming ? BS_Hero_Rifle_Strafe(Direction,Speed) : BS_Hero_Rifle_Jog(Speed) ·
                                         Aim = InPose → AimOffset(AO_Hero_Rifle, X=AimYaw, Y=AimPitch, Alpha(bool)=bIsAiming)
런타임 배선(C++ 2026-10-19): DA_EF_Rifle.AnimLayerClass = ABP_HeroLayers_Rifle_C (장비 매니저가 스타일 활성 시 LinkAnimClassLayers) ·
DA_CD_Vesper.AnimInstanceClass = ABP_Hero_Combat_C — Tools/scripts/setup/hero_abp_wire_data (ue_exec) 또는 에디터에서.
운영 애셋 ABP_Hero_Base 는 읽기(비교)만 한다. 변수 bIsAiming/AimYaw/AimPitch 는 UAstralAnimInstance(C++) 가 매 프레임 쓴다.
"""
from __future__ import annotations

import json
import pathlib
import sys

from anim_graph_mcp import bridge

HERO = "/Game/Animation/Hero"
LOCO = f"{HERO}/Anims/Locomotions"
COMBAT = f"{HERO}/Anims/Combat"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
PROD = f"{HERO}/ABP_Hero_Base"

AO = f"{LOCO}/AO_Hero_Rifle"
BS_STRAFE = f"{LOCO}/BS_Hero_Rifle_Strafe"
BS_JOG = f"{LOCO}/BS_Hero_Rifle_Jog"
ALI = f"{HERO}/ALI_HeroCombat"
ABP = f"{HERO}/ABP_Hero_Combat"
PROV_RIFLE = f"{HERO}/ABP_HeroLayers_Rifle"
STATE_FILE = pathlib.Path("Tools/mcp/build_hero_combat_state.json")

IDLE_MELEE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
BS_MELEE = f"{LOCO}/BS_Hero_Locomotion1D"
RIFLE_IDLE = f"{LOCO}/AS_Hero_Rifle_Idle"
JUMP, FALL, LAND = f"{LOCO}/AS_Hero_Jump", f"{LOCO}/AS_Hero_FallLoop", f"{LOCO}/AS_Hero_Land"

# AO_Rifle 이름 규약: 첫 글자 = Yaw(L/C/R), 둘째 = Pitch(U/C/D)
AO_SAMPLES = {f"{LOCO}/AS_Hero_AO_Rifle{y}{p}": [yaw, pitch]
              for y, yaw in (("L", -90), ("C", 0), ("R", 90)) for p, pitch in (("U", 90), ("C", 0), ("D", -90))}
AO_CC = f"{LOCO}/AS_Hero_AO_RifleCC"
# AO 9샘플의 저작 기준 = AS_IdleRifleAiming_02 프레임 0 (2026-10-20 실측: CC 와 0.0도 일치). 조준 중 상체도 이것 — 기준이 다르면(총 내린 Rifle_Idle)
# 델타가 거대해져 Yaw 30~85 에서 두 손이 붙는다(제자리 회전에서 드러남). hero-combat-abp.md §7. 조준 가지 그래프는 build_hero_turninplace 가 고친다
AIM_IDLE = f"{COMBAT}/AS_IdleRifleAiming_02"
# strafe 방향(도) — MovementDirection 은 forward 기준 -180~180, 오른쪽이 양수 (AstralAnimInstance::CalculateDirectionAngle)
JOG = {0: "JogFwd", 45: "JogFwdRight", 90: "JogRight", 135: "JogBwdRight", 180: "JogBwd", -180: "JogBwd", -135: "JogBwdLeft", -90: "JogLeft", -45: "JogFwdLeft"}
SPEED_MAX = 500.0

# 운영 애셋 상태머신(phase5_build_hero 와 동일)
SPEED_STOP, SPEED_MOVE, GROUND_LAND = 10.0, 20.0, 25.0
UPPER_BODY_BONE, UPPER_BODY_SLOT, FULL_BODY_SLOT = "spine_01", "UpperBody", "DefaultSlot"

FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def call(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def apply(asset: str, ops: list, what: str, compile: bool = False, save: bool = False) -> dict:
    pv = bridge.call("preview_graph_operations", {"asset_path": asset, "operations": ops})
    if not (pv.get("ok") and pv["result"]["valid"]):
        print(f"[FAIL] preview {what}:\n" + json.dumps(pv, ensure_ascii=False, indent=1)[:5000])
        sys.exit(1)
    r = must(call("apply_graph_operations", asset_path=asset, operations=ops, compile=compile, save=save), f"apply {what}")
    print(f"   {what}: applied={r['applied']} revision={r['revision_after'][:16]}")
    if compile:
        for m in r["compile"].get("messages", []):
            print(f"   compile[{m['level']}] {m['text'][:200]}")
        check(r["compile"].get("num_errors") == 0, f"{what} 컴파일 0 에러 (warnings={r['compile'].get('num_warnings')})")
    return r


def root_of(asset: str, graph_guid: str | None = None) -> str:
    s = must(call("get_anim_graph_structure", asset_path=asset, graph_guid=graph_guid, depth=0), f"structure {asset}")
    return next(n["node_guid"] for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")


def input_pose_of(asset: str, graph_guid: str) -> str:
    s = must(call("get_anim_graph_structure", asset_path=asset, graph_guid=graph_guid, depth=0), f"structure {asset}")
    return next(n["node_guid"] for n in s["nodes"] if n["class"] == "AnimGraphNode_LinkedInputPose")


def layer_graphs(asset: str) -> dict[str, str]:
    info = must(call("get_anim_blueprint_info", asset_path=asset), f"info {asset}")
    return {l["name"]: l["graph_guid"] for l in info["layers"]}


def var(n: str) -> dict:
    return {"var": n}


def cmp(op: str, left: dict, lit: float) -> dict:
    return {"compare": {"op": op, "left": left, "right": {"literal": lit}}}


AUTO = {"automatic": True, "trigger_time": -1.0}
TRANSITIONS = [
    ("t_idle_move", "idle", "move", 0.25, 1, var("bHasMovementInput")),
    ("t_move_idle", "move", "idle", 0.30, 1, {"and": [{"not": var("bHasMovementInput")}, cmp("<", var("Speed"), SPEED_STOP)]}),
    ("t_src_sel", "jumpsrc", "jumpsel", 0.20, 1, {"literal": True}),
    ("t_sel_jump", "jumpsel", "jumpstart", 0.20, 1, var("bIsJumping")),
    ("t_sel_fall", "jumpsel", "fallloop", 0.20, 2, var("bIsFalling")),
    ("t_jump_fall", "jumpstart", "fallloop", 0.20, 1, AUTO),
    ("t_fall_land", "fallloop", "fallland", 0.20, 1, cmp("<", var("GroundDistance"), GROUND_LAND)),
    ("t_land_end_auto", "fallland", "endinair", 0.20, 1, AUTO),
    ("t_land_end_ground", "fallland", "endinair", 0.20, 1, var("bIsOnGround")),
    ("t_interrupt_end", "interrupt", "endinair", 0.20, 1, var("bIsOnGround")),
    ("t_end_idle", "endinair", "idlealias", 0.20, 1, cmp(">=", var("Speed"), SPEED_MOVE)),   # 운영 그대로 (방향이 반대로 보임 — phase5 비교 문서 §5)
    ("t_end_move", "endinair", "movealias", 0.20, 1, cmp("<", var("Speed"), SPEED_MOVE)),
]
STATES = [("idle", "Idle", [0, 0]), ("move", "Move", [500, 0]), ("jumpstart", "JumpStart", [0, 500]), ("fallloop", "FallLoop", [500, 500]), ("fallland", "FallLand", [1000, 500])]
CONDUITS = [("jumpsel", "JumpSelector", [250, 250]), ("endinair", "EndInAir", [1250, 250])]
ALIASES = [("jumpsrc", "JumpSources", [-300, 250], ["idle", "move"]), ("interrupt", "JumpFallInterruptSources", [800, 800], ["jumpstart", "fallloop"]),
           ("idlealias", "IdleAlias", [1600, 150], ["idle"]), ("movealias", "MoveAlias", [1600, 350], ["move"])]


# ----------------------------------------------------------------------------------------------------------------------
def build_content(overwrite: bool) -> None:
    print("\n=== 1. 콘텐츠 애셋 — AO_CC 기준 포즈 · AimOffset · BlendSpace 2개 ===")
    for path in AO_SAMPLES:
        r = must(call("set_sequence_additive", asset_path=path, additive_type="RotationOffsetMeshSpace", ref_pose_type="AnimFrame", ref_pose_sequence=AIM_IDLE, ref_frame_index=0, save=True), "AO base " + path.split("/")[-1])
        check(r["additive_valid"], path.split("/")[-1] + f" 기준 포즈 = AS_IdleRifleAiming_02 프레임 0 (changed={r['changed']})")

    ao = must(call("create_blendspace", asset_path=AO, skeleton=SKELETON, dimensions=2, aim_offset=True,
                   axes=[{"name": "Yaw", "min": -90, "max": 90, "grid": 4}, {"name": "Pitch", "min": -90, "max": 90, "grid": 4}],
                   samples=[{"animation": p, "value": v} for p, v in AO_SAMPLES.items()], preview_mesh=MESH, overwrite=overwrite, save=True), "create AO")
    check(ao["class"] == "AimOffsetBlendSpace" and ao["sample_count"] == 9 and ao["saved"], f"AO_Hero_Rifle 9샘플 ({ao['class']})")

    strafe_samples = [{"animation": RIFLE_IDLE, "value": [d, 0]} for d in (-180, -90, 0, 90, 180)]
    strafe_samples += [{"animation": f"{LOCO}/AS_Hero_Rifle_{name}", "value": [d, SPEED_MAX]} for d, name in JOG.items()]
    bs = must(call("create_blendspace", asset_path=BS_STRAFE, skeleton=SKELETON, dimensions=2,
                   axes=[{"name": "Direction", "min": -180, "max": 180, "grid": 8, "wrap": True}, {"name": "Speed", "min": 0, "max": SPEED_MAX, "grid": 2}],
                   samples=strafe_samples, preview_mesh=MESH, overwrite=overwrite, save=True), "create strafe BS")
    check(bs["class"] == "BlendSpace" and bs["sample_count"] == len(strafe_samples) and bs["saved"], f"BS_Hero_Rifle_Strafe {bs['sample_count']}샘플")

    jog = must(call("create_blendspace", asset_path=BS_JOG, skeleton=SKELETON, dimensions=1,
                    axes=[{"name": "Speed", "min": 0, "max": SPEED_MAX, "grid": 5}],
                    samples=[{"animation": RIFLE_IDLE, "value": [0]}, {"animation": f"{LOCO}/AS_Hero_Rifle_JogFwd", "value": [SPEED_MAX]}],
                    preview_mesh=MESH, overwrite=overwrite, save=True), "create jog BS")
    check(jog["class"] == "BlendSpace1D" and jog["sample_count"] == 2 and jog["saved"], "BS_Hero_Rifle_Jog 2샘플")


def build_interface(overwrite: bool) -> None:
    print("\n=== 2. 레이어 인터페이스 ALI_HeroCombat ===")
    ali = must(call("create_anim_layer_interface", asset_path=ALI, overwrite=overwrite, save=True,
                    layers=[{"name": "Locomotion_Idle"}, {"name": "Locomotion_Move"}, {"name": "Aim_UpperBody", "input_poses": ["InPose"]}]), "create ALI")
    check(ali["compile"]["num_errors"] == 0 and {l["name"] for l in ali["layers"]} == {"Locomotion_Idle", "Locomotion_Move", "Aim_UpperBody"}, "ALI 3 레이어 · 컴파일 0 에러")


def create_abp(path: str, overwrite: bool) -> None:
    created = bridge.call("create_animation_blueprint", {"asset_path": path, "skeleton": SKELETON, "parent_class": PARENT, "preview_mesh": MESH, "overwrite": overwrite})
    if not created.get("ok") and created.get("error", {}).get("code") == "ASSET_EXISTS":
        print(f"{path} 가 이미 있다 — 다시 만들려면 --overwrite (기존 애셋 삭제)")
        sys.exit(2)
    info = must(created, f"create {path}")
    missing = {"Speed", "MovementDirection", "bHasMovementInput", "bIsJumping", "bIsFalling", "bIsOnGround", "GroundDistance", "bIsAiming", "AimYaw", "AimPitch"} - {v["name"] for v in info["variables"]}
    # (bIsRangedStyle 은 2026-10-20 제거 — 그래프가 읽지 않는 값이었고 스타일 분기는 레이어 링크가 담당)
    check(not missing, f"{path.split('/')[-1]} 변수 (부모 UAstralAnimInstance) — 누락 {sorted(missing) or '없음'}")
    must(call("implement_anim_layer_interface", asset_path=path, interface=ALI), f"implement {path}")


def fill_melee_defaults(asset: str) -> None:
    """베이스 ABP 의 레이어 기본 구현 = 근접(낫) 세트. 공급자가 없을 때(낫 활성·무장비) 이 그래프가 돈다."""
    g = layer_graphs(asset)
    ops = [
        {"op": "add_node", "ref": "idle_seq", "graph": g["Locomotion_Idle"], "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": IDLE_MELEE, "properties": {"bLoopAnimation": True}},
        {"op": "connect", "from": {"ref": "idle_seq", "pin": "Pose"}, "to": {"node": root_of(asset, g["Locomotion_Idle"]), "pin": "Result"}},
        {"op": "add_node", "ref": "move_bs", "graph": g["Locomotion_Move"], "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 0], "asset": BS_MELEE, "properties": {"bLoop": True}},
        {"op": "bind_pin", "ref": "move_bs", "property": "X", "path": "Speed"},
        {"op": "connect", "from": {"ref": "move_bs", "pin": "Pose"}, "to": {"node": root_of(asset, g["Locomotion_Move"]), "pin": "Result"}},
        {"op": "connect", "from": {"node": input_pose_of(asset, g["Aim_UpperBody"]), "pin": "Pose"}, "to": {"node": root_of(asset, g["Aim_UpperBody"]), "pin": "Result"}},
    ]
    apply(asset, ops, "레이어 기본 구현(근접)")


def build_base(overwrite: bool) -> dict:
    print("\n=== 3. 베이스 ABP_Hero_Combat ===")
    create_abp(ABP, overwrite)
    fill_melee_defaults(ABP)

    root = root_of(ABP)
    ops_root = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-1800, 0]},
        {"op": "add_node", "ref": "slot_full", "class": "AnimGraphNode_Slot", "pos": [-1500, 0], "properties": {"SlotName": FULL_BODY_SLOT}},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"ref": "slot_full", "pin": "Source"}},
        # 전신 슬롯 출력(몽타주 포함)을 캐시해 두 갈래로 — 상체 슬롯이 비어 있으면 같은 포즈라 블렌드가 항등 (phase5 PIE 실측)
        {"op": "add_node", "ref": "save", "class": "AnimGraphNode_SaveCachedPose", "pos": [-1200, 0], "properties": {"CacheName": "FullBody"}},
        {"op": "connect", "from": {"ref": "slot_full", "pin": "Pose"}, "to": {"ref": "save", "pin": "Pose"}},
        {"op": "add_node", "ref": "use_base", "class": "AnimGraphNode_UseCachedPose", "pos": [-900, -150]},
        {"op": "set_property", "ref": "use_base", "property": "SaveCachedPoseNode", "value": {"ref": "save"}},
        {"op": "add_node", "ref": "use_upper", "class": "AnimGraphNode_UseCachedPose", "pos": [-1200, 250]},
        {"op": "set_property", "ref": "use_upper", "property": "SaveCachedPoseNode", "value": {"ref": "save"}},
        {"op": "add_node", "ref": "slot_upper", "class": "AnimGraphNode_Slot", "pos": [-900, 250], "properties": {"SlotName": UPPER_BODY_SLOT}},
        {"op": "connect", "from": {"ref": "use_upper", "pin": "Pose"}, "to": {"ref": "slot_upper", "pin": "Source"}},
        {"op": "add_node", "ref": "layer", "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-600, 0], "properties": {"bMeshSpaceRotationBlend": True}},
        {"op": "set_property", "ref": "layer", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": UPPER_BODY_BONE, "BlendDepth": 0}]}]},
        {"op": "connect", "from": {"ref": "use_base", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "slot_upper", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BlendPoses_0"}},
        # 조준 레이어 — 전신(몽타주·상체 슬롯 포함) 위에 AimOffset. 공급자가 없으면 기본 구현(통과)
        {"op": "add_node", "ref": "aim", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "Aim_UpperBody", "pos": [-300, 0]},
        {"op": "connect", "from": {"ref": "layer", "pin": "Pose"}, "to": {"ref": "aim", "pin": "InPose"}},
        {"op": "add_node", "ref": "inertia", "class": "AnimGraphNode_Inertialization", "pos": [0, 0]},
        {"op": "connect", "from": {"ref": "aim", "pin": "Pose"}, "to": {"ref": "inertia", "pin": "Source"}},
        {"op": "connect", "from": {"ref": "inertia", "pin": "Pose"}, "to": {"node": root, "pin": "Result"}},
    ]
    r_root = apply(ABP, ops_root, "루트")
    refs = dict(r_root["refs"])

    ops_sm: list[dict] = [{"op": "rename_node", "node": refs["sm"], "name": "Locomotions"}]
    ops_sm += [{"op": "add_state", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos} for ref, name, pos in STATES]
    ops_sm.append({"op": "set_entry_state", "sm": {"node": refs["sm"]}, "state": {"ref": "idle"}})
    # Idle/Move 상태 내부 = 레이어 노드 (무기 공급자가 갈아끼운다). 점프 3상태는 무기 무관이라 시퀀스 그대로
    ops_sm += [
        {"op": "add_node", "ref": "idle_layer", "graph": {"ref": "idle"}, "class": "AnimGraphNode_LinkedAnimLayer", "layer": "Locomotion_Idle", "pos": [-400, 0]},
        {"op": "connect", "from": {"ref": "idle_layer", "pin": "Pose"}, "to": {"result_of": {"ref": "idle"}, "pin": "Result"}},
        {"op": "add_node", "ref": "move_layer", "graph": {"ref": "move"}, "class": "AnimGraphNode_LinkedAnimLayer", "layer": "Locomotion_Move", "pos": [-400, 0]},
        {"op": "connect", "from": {"ref": "move_layer", "pin": "Pose"}, "to": {"result_of": {"ref": "move"}, "pin": "Result"}},
    ]
    for ref, asset, loop in (("jumpstart", JUMP, False), ("fallloop", FALL, True), ("fallland", LAND, False)):
        ops_sm += [
            {"op": "add_node", "ref": f"{ref}_seq", "graph": {"ref": ref}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": asset, "properties": {"bLoopAnimation": loop}},
            {"op": "connect", "from": {"ref": f"{ref}_seq", "pin": "Pose"}, "to": {"result_of": {"ref": ref}, "pin": "Result"}},
        ]
    ops_sm += [{"op": "add_conduit", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos, "rule": {"literal": True}} for ref, name, pos in CONDUITS]
    ops_sm += [{"op": "add_state_alias", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos, "states": [{"ref": s} for s in states]} for ref, name, pos, states in ALIASES]
    for ref, src, dst, xfade, prio, rule in TRANSITIONS:
        ops_sm.append({"op": "add_transition", "ref": ref, "from": {"ref": src}, "to": {"ref": dst}, "properties": {"CrossfadeDuration": xfade, "PriorityOrder": prio}, "rule": rule})
    r_sm = apply(ABP, ops_sm, "상태머신 Locomotions", compile=True, save=True)
    refs.update(r_sm["refs"])
    return refs


def build_rifle_provider(overwrite: bool) -> None:
    print("\n=== 4. 원거리 공급자 ABP_HeroLayers_Rifle ===")
    create_abp(PROV_RIFLE, overwrite)
    g = layer_graphs(PROV_RIFLE)
    ops = [
        # Idle: 조준 중이면 조준 Idle, 아니면 라이플 Idle
        {"op": "add_node", "ref": "idle_bl", "graph": g["Locomotion_Idle"], "class": "AnimGraphNode_BlendListByBool", "pos": [-300, 0], "properties": {"BlendTime": [0.2, 0.2]}},
        {"op": "bind_pin", "ref": "idle_bl", "property": "bActiveValue", "path": "bIsAiming"},
        {"op": "add_node", "ref": "idle_seq", "graph": g["Locomotion_Idle"], "class": "AnimGraphNode_SequencePlayer", "pos": [-700, -100], "asset": RIFLE_IDLE, "properties": {"bLoopAnimation": True}},
        # 조준 Idle = AS_IdleRifleAiming_02 = AO 기준 포즈(CC 항등). 10-19 에 "비틀림" 으로 Rifle_Idle 로 바꿨던 것은 AO 기준이 Rifle_Idle 로 잘못 잡혀 있던 탓(10-20 실측)
        # — build_hero_turninplace 가 이 가지를 IdleTurn 상태머신으로 바꾸고 Move 조준 가지에 상체 레이어를 얹는다
        {"op": "add_node", "ref": "aim_idle_seq", "graph": g["Locomotion_Idle"], "class": "AnimGraphNode_SequencePlayer", "pos": [-700, 150], "asset": AIM_IDLE, "properties": {"bLoopAnimation": True}},
        # ⚠️ BlendListByBool 은 BlendPose_0 = **True** Pose, BlendPose_1 = False Pose (AnimGraphNode_BlendListByBool.cpp:37 "intentionally flipped" —
        # 2026-10-19 PIE 에서 거꾸로 꽂혀 조준 중에 전진 Jog 가 나온 실수)
        {"op": "connect", "from": {"ref": "aim_idle_seq", "pin": "Pose"}, "to": {"ref": "idle_bl", "pin": "BlendPose_0"}},
        {"op": "connect", "from": {"ref": "idle_seq", "pin": "Pose"}, "to": {"ref": "idle_bl", "pin": "BlendPose_1"}},
        {"op": "connect", "from": {"ref": "idle_bl", "pin": "Pose"}, "to": {"node": root_of(PROV_RIFLE, g["Locomotion_Idle"]), "pin": "Result"}},
        # Move: 조준 중이면 strafe 2D(Direction×Speed), 아니면 전진 Jog 1D(Speed)
        {"op": "add_node", "ref": "move_bl", "graph": g["Locomotion_Move"], "class": "AnimGraphNode_BlendListByBool", "pos": [-300, 0], "properties": {"BlendTime": [0.2, 0.2]}},
        {"op": "bind_pin", "ref": "move_bl", "property": "bActiveValue", "path": "bIsAiming"},
        {"op": "add_node", "ref": "jog_bs", "graph": g["Locomotion_Move"], "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-700, -100], "asset": BS_JOG, "properties": {"bLoop": True}},
        {"op": "bind_pin", "ref": "jog_bs", "property": "X", "path": "Speed"},
        {"op": "add_node", "ref": "strafe_bs", "graph": g["Locomotion_Move"], "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-700, 150], "asset": BS_STRAFE, "properties": {"bLoop": True}},
        {"op": "bind_pin", "ref": "strafe_bs", "property": "X", "path": "MovementDirection"},
        {"op": "bind_pin", "ref": "strafe_bs", "property": "Y", "path": "Speed"},
        {"op": "connect", "from": {"ref": "strafe_bs", "pin": "Pose"}, "to": {"ref": "move_bl", "pin": "BlendPose_0"}},   # true(조준) = strafe
        {"op": "connect", "from": {"ref": "jog_bs", "pin": "Pose"}, "to": {"ref": "move_bl", "pin": "BlendPose_1"}},      # false = 전진 Jog
        {"op": "connect", "from": {"ref": "move_bl", "pin": "Pose"}, "to": {"node": root_of(PROV_RIFLE, g["Locomotion_Move"]), "pin": "Result"}},
        # Aim: 입력 포즈 위에 AimOffset — Alpha 는 bool 입력(bIsAiming), 켜고 끌 때 0.15초 블렌드
        {"op": "add_node", "ref": "ao", "graph": g["Aim_UpperBody"], "class": "AnimGraphNode_RotationOffsetBlendSpace", "pos": [-300, 0], "asset": AO,
         "properties": {"AlphaInputType": "Bool", "AlphaBoolBlend": {"BlendInTime": 0.15, "BlendOutTime": 0.15}}},
        {"op": "bind_pin", "ref": "ao", "property": "X", "path": "AimYaw"},
        {"op": "bind_pin", "ref": "ao", "property": "Y", "path": "AimPitch"},
        {"op": "bind_pin", "ref": "ao", "property": "bAlphaBoolEnabled", "path": "bIsAiming"},
        {"op": "connect", "from": {"node": input_pose_of(PROV_RIFLE, g["Aim_UpperBody"]), "pin": "Pose"}, "to": {"ref": "ao", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "ao", "pin": "Pose"}, "to": {"node": root_of(PROV_RIFLE, g["Aim_UpperBody"]), "pin": "Result"}},
    ]
    apply(PROV_RIFLE, ops, "라이플 레이어 3종", compile=True, save=True)


def verify() -> None:
    print("\n=== 5. 검증 — 스모크 · 운영 ABP 와 상태머신 비교 · PIE 진입 상태 ===")
    j = must(call("run_automation_tests", filter="AnimGraphMcp.Smoke.AnimBlueprint"), "smoke")
    mine = {t["name"].split(".")[-1]: t for t in j["tests"] if t["name"].split(".")[-1] in ("ABP_Hero_Combat", "ABP_HeroLayers_Rifle", "ABP_Hero_Base")}
    for name, t in mine.items():
        print(f"   smoke {name}: {t['state']} errors={t['errors'][:1]} warnings={[w[:90] for w in t['warnings'][:2]]}")
    check(all(t["state"] == "passed" for t in mine.values()) and len(mine) == 3, "스모크: ABP_Hero_Combat · ABP_HeroLayers_Rifle · ABP_Hero_Base passed")

    prod = must(call("get_anim_graph_structure", asset_path=PROD, depth=-1), "prod structure")
    mine_s = must(call("get_anim_graph_structure", asset_path=ABP, depth=-1), "combat structure")
    psm, msm = prod["state_machines"][0], mine_s["state_machines"][0]
    pnames = {s["node_guid"]: s["name"] for s in psm["states"]}
    mnames = {s["node_guid"]: s["name"] for s in msm["states"]}
    p_tr = sorted((pnames[t["from"]], pnames[t["to"]], round(t["crossfade_duration"], 3), t["priority_order"]) for t in psm["transitions"])
    m_tr = sorted((mnames[t["from"]], mnames[t["to"]], round(t["crossfade_duration"], 3), t["priority_order"]) for t in msm["transitions"])
    check(sorted(s["name"] for s in psm["states"]) == sorted(s["name"] for s in msm["states"]) and p_tr == m_tr, f"상태머신 상태 {len(msm['states'])} · 전이 {len(msm['transitions'])} 운영과 1:1")

    info = must(call("get_anim_blueprint_info", asset_path=ABP), "combat info")
    check(info["linked_anim_layer_count"] == 3 and {l["name"] for l in info["layers"]} == {"Locomotion_Idle", "Locomotion_Move", "Aim_UpperBody"}, "레이어 노드 3 · 구현 레이어 3")
    pinfo = must(call("get_anim_blueprint_info", asset_path=PROV_RIFLE), "rifle info")
    check(pinfo["implemented_interfaces"] and pinfo["implemented_interfaces"][0]["blueprint"].startswith(ALI), "공급자가 ALI_HeroCombat 구현")

    import time
    env = must(call("run_anim_scenario", asset_path=ABP, mesh=MESH, wait_frames=10, expect={"state_machines": {"Locomotions": "Idle"}}), "scenario")
    job = env
    deadline = time.time() + 240
    while not job.get("done") and time.time() < deadline:
        time.sleep(1.0)
        job = must(bridge.call("poll_automation_tests", {"job_id": job["job_id"]}), "poll")
    t = job["tests"][0] if job["tests"] else {}
    obs = t.get("observed") or {}
    print(f"   PIE: {t.get('state')} observed={json.dumps(obs, ensure_ascii=False)[:300]}")
    check(job["ok"] and t.get("state") == "passed", "PIE 에서 ABP_Hero_Combat 이 Locomotions=Idle 로 진입 (공급자 미링크 = 근접 기본 구현)")

    STATE_FILE.write_text(json.dumps({"combat_revision": info["revision"], "rifle_revision": pinfo["revision"], "transitions": m_tr}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"saved → {STATE_FILE}")


def main() -> int:
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check("set_sequence_additive" in names and "reassign_skeleton" in names, f"7-6 Tool 등록 (총 {len(names)})")
    overwrite = "--overwrite" in sys.argv
    if "--verify-only" not in sys.argv:
        build_content(overwrite)
        build_interface(overwrite)
        build_base(overwrite)
        build_rifle_provider(overwrite)
        # 제자리 회전(2026-10-20) — 베이스 RotateRootBone + 공급자 조준 Idle 상태머신. 별도 스크립트(멱등)라 기존 ABP 에도 단독 적용 가능
        import build_hero_turninplace
        build_hero_turninplace.patch()
    verify()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
