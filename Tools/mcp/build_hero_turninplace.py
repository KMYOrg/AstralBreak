"""히어로 제자리 회전(TurnInPlace, 2026-10-20) — Lyra 식: RotateRootBone(RootYawOffset) + 조준 Idle 상태머신(Idle → Rotation → Recovery) + 턴 클립 4개.
베이스 ABP_Hero_Combat 과 공급자 ABP_HeroLayers_Rifle 을 **제자리에서** 고친다(삭제·재생성 금지 — DA_CD_Vesper·BP_Hero_Vesper·DA_EF_Rifle 이 클래스를 참조).
멱등: 이미 패치된 그래프는 건너뛴다. build_hero_combat.main 도 공급자 생성 뒤 이 patch() 를 부른다.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/build_hero_turninplace.py [--verify-only]

선행:
  - C++ 빌드 — Animation/AstralTurnInPlace(순수 계산) · UAstralAnimInstance 출력(RootYawOffset · bWantsTurnInPlace · bTurnInPlaceRotationFinished ·
    TurnInPlaceKind · TurnInPlaceAnimTime) · GetMainAnimInstance()(BlueprintThreadSafe) · 플러그인 허용 목록 LogicType
  - 턴 클립 4개: reassign_skeleton 으로 스켈레톤 A(/Game/Assets/IdaFaber/...) 재할당 → Tools/scripts/setup/hero_abp_move_turn_assets(ue_exec) 로
    /Game/Animation/Hero/Vesper/Rifle/TurnInPlace/ 이동 (커브 TurnYawWeight · RemainingTurnYaw 확인 로그)
그래프:
  베이스 루트: LayeredBoneBlend → Aim_UpperBody 레이어 → RotateRootBone(Yaw ← RootYawOffset) → [L2C → Astral Aim Correction → C2L] → Inertialization → Output
     (최종 조준 보정 — RotateRootBone 뒤 최종 컴포넌트 공간에서 총열이 조준점을 향하도록 척추 spine_03~05 를 마저 돌린다: patch_aim_correction)
     (AimOffset 은 루트 회전 **앞** — AO 가산은 루트 회전까지 포함한 메시 공간에서 앞곱되므로(ConvertPoseToMeshRotation) 루트 0 기준으로 저작된
      샘플은 루트를 돌리기 전에 얹어야 한다. 그 뒤 RotateRootBone 이 합성 포즈를 통째로 돌려 AimYaw(= −RootYawOffset) 가 정확히 상쇄된다.
      2026-10-21 PIE: 반대 순서에선 오프셋 −45 · Pitch 0 에서 총이 30° 숙여지고 Pitch +40 에서 두 손이 14.7cm 로 붙었다 — patch_aim_before_root)
  공급자 Locomotion_Idle 의 조준(true = BlendPose_0) 가지: 상태머신 IdleTurn
     Idle(Rifle_Idle 루프)
       ─ GetMainAnimInstance.bWantsTurnInPlace ─▶ TurnInPlaceRotation: BlendListByEnum(EAstralTurnInPlaceKind ← GetMainAnimInstance.TurnInPlaceKind),
                                                   기본(None)=Rifle_Idle, Left90/Left180/Right90/Right180 = 턴 클립(루프 없음), bAlwaysResetOnEntry
       ─ GetMainAnimInstance.bTurnInPlaceRotationFinished ─▶ TurnInPlaceRecovery: 같은 구성 + 각 클립 StartPosition ← GetMainAnimInstance.TurnInPlaceAnimTime
                                                   (회전이 끝난 지점부터 이어 재생) ─ 자동(클립 끝) ─▶ Idle,  Recovery ─ bWantsTurnInPlace ─▶ Rotation
  무기 포즈 오버레이(2026-10-22, patch_weapon_overlay): 베이스 루트 Locomotions → LinkedAnimLayer Locomotion_WeaponOverlay → Slot DefaultSlot —
     라이플은 조준 상체(AS_Vesper_Rifle_AimIdle)를 AimPoseAlpha 로 덮는다. 상태와 무관한 한 곳이라 점프·낙하에도 조준 자세(지상 상태별 덮기는 지웠다).
     그 앞에 휴대 팔(오른팔 ← Rifle_Idle, HandsFreeAlpha — 무기 무관 클립이 손을 뗀 동안 총을 휴대 자세로, patch_weapon_carry).
     왼손 IK 알파 = LeftHandIKAlpha(C++ — 클립 커브 DisableLHandIK 와 조준 오버레이로, patch_left_hand_alpha)
  전이는 전부 LogicType = Inertialization (Lyra 와 같다). 표준 크로스페이드면 클립↔클립 블렌드 중 두 클립의 커브가 가중 합산되어
  "남은 각이 커지는" 가짜 델타가 RootYawOffset 을 반대로 민다. 관성 블렌드는 새 상태 가중치가 즉시 1 이라 첫 프레임 건너뛰기만으로 충분.
  관성 요청은 베이스 루트의 Inertialization 노드가 받는다(링크된 레이어 → 메인 그래프로 전파).
  공급자는 값을 GetMainAnimInstance.* Property Access 경로로 베이스에서 읽는다 — 제자리 회전은 메인 인스턴스 하나만 계산.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

from anim_graph_mcp import bridge
import build_hero_combat as hc
from build_hero_combat import ABP, HERO, MESH, PROV_RIFLE, RIFLE_IDLE, apply, call, check, layer_graphs, must

TURN_DIR = f"{HERO}/Vesper/Rifle/TurnInPlace"
# 순서 = BlendListByEnum 노출 순서 = BlendPose_1..4
CLIPS = {"Left90": "AS_Vesper_Rifle_TurnLeft_90", "Left180": "AS_Vesper_Rifle_TurnLeft_180", "Right90": "AS_Vesper_Rifle_TurnRight_90", "Right180": "AS_Vesper_Rifle_TurnRight_180"}
ENUM = "/Script/AstralBreak.EAstralTurnInPlaceKind"
MAIN = "GetMainAnimInstance"
SM_NAME = "IdleTurn"
XFADE = 0.2
OUTPUTS = {"RootYawOffset", "bWantsTurnInPlace", "bTurnInPlaceRotationFinished", "TurnInPlaceKind", "TurnInPlaceAnimTime", "TurnYawCurveValue"}
STATE_FILE = pathlib.Path("Tools/mcp/build_hero_turninplace_state.json")


def structure(asset: str, graph: str | None = None, depth: int = 0) -> dict:
    return must(call("get_anim_graph_structure", asset_path=asset, graph_guid=graph, depth=depth), f"structure {asset.split('/')[-1]}")


def one(nodes: list[dict], cls: str, what: str) -> dict:
    found = [n for n in nodes if n["class"] == cls]
    if len(found) != 1:
        print(f"[FAIL] {what}: {cls} 노드가 {len(found)}개 (1개 기대)")
        sys.exit(1)
    return found[0]


def acc(name: str) -> dict:
    return {"access": f"{MAIN}.{name}"}


def bound_path(node: dict, prop: str) -> list[str] | None:
    """노드의 핀 바인딩 경로 (없으면 None)."""
    e = next((o for o in node.get("optional_pins", []) if o["property"] == prop), None)
    return e["binding"]["path"] if e and e.get("bound") else None


def layer_node(s: dict, layer: str) -> dict:
    """그래프의 LinkedAnimLayer 노드 중 그 레이어 것 — 베이스 루트에는 Locomotion_WeaponOverlay · Aim_UpperBody 두 개가 있다."""
    found = [n for n in s["nodes"] if n["class"] == "AnimGraphNode_LinkedAnimLayer" and (n.get("linked_layer") or {}).get("layer") == layer]
    if len(found) != 1:
        print(f"[FAIL] LinkedAnimLayer({layer}) 노드가 {len(found)}개 (1개 기대)")
        sys.exit(1)
    return found[0]


# ----------------------------------------------------------------------------------------------------------------------
def patch_base() -> bool:
    print("\n=== A. 베이스 ABP_Hero_Combat — Aim_UpperBody → RotateRootBone(Yaw ← RootYawOffset) → Inertialization ===")
    info = must(call("get_anim_blueprint_info", asset_path=ABP), "combat info")
    missing = OUTPUTS - {v["name"] for v in info["variables"]}
    check(not missing, f"C++ 출력 변수 — 누락 {sorted(missing) or '없음'} (있으면 빌드가 안 됐거나 에디터가 옛 바이너리)")
    if missing:
        sys.exit(1)
    s = structure(ABP)
    if any(n["class"] == "AnimGraphNode_RotateRootBone" for n in s["nodes"]):
        print("   이미 있음 — 건너뜀")
        return False
    aim = layer_node(s, "Aim_UpperBody")
    inert = one(s["nodes"], "AnimGraphNode_Inertialization", "베이스 루트")
    link = next((c for c in s["connections"] if c["from"]["node"] == aim["node_guid"] and c["to"]["node"] == inert["node_guid"]), None)
    check(link is not None and link["to"]["pin"] == "Source", "Aim_UpperBody.Pose → Inertialization.Source 연결 확인")
    ops = [
        {"op": "disconnect", "from": {"node": aim["node_guid"], "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
        {"op": "add_node", "ref": "rrb", "class": "AnimGraphNode_RotateRootBone", "pos": [-150, 0]},
        {"op": "connect", "from": {"node": aim["node_guid"], "pin": "Pose"}, "to": {"ref": "rrb", "pin": "BasePose"}},
        # Pitch 는 0 고정(핀 기본값). Yaw 만 바인딩 — 메인 인스턴스가 매 프레임 쓰는 값
        {"op": "bind_pin", "ref": "rrb", "property": "Yaw", "path": "RootYawOffset"},
        {"op": "connect", "from": {"ref": "rrb", "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
    ]
    apply(ABP, ops, "베이스 RotateRootBone", compile=True, save=True)
    return True


def patch_aim_before_root() -> bool:
    """기존 애셋 이행 — 10-20 판은 LayeredBoneBlend → RotateRootBone → Aim_UpperBody 순서였다. AimOffset 노드는 가산 회전을 루트 회전까지 포함한
    메시 공간에서 앞곱하므로(AnimationRuntime ConvertPoseToMeshRotation · AccumulateWithAdditiveScale) 루트를 돌린 뒤 얹으면 샘플 델타의 Yaw 외 성분
    (Pitch · 팔 보정)이 RootYawOffset 만큼 틀어진 축으로 들어간다 — 2026-10-21 사용자 PIE "목 꺾임 · 왼손이 총열에서 떨어짐", 프로브(오프셋 −45:
    Pitch 0 인데 총 −29.5°, Pitch +40 에서 두 손 14.7cm). 노드를 지우고 Aim_UpperBody 와 Inertialization 사이에 새로 만든다(새 빌드의 patch_base 와 같은 결과)."""
    print("\n=== A1. 베이스 — AimOffset(Aim_UpperBody) 을 RotateRootBone 앞으로 ===")
    s = structure(ABP)
    layer = one(s["nodes"], "AnimGraphNode_LayeredBoneBlend", "베이스 루트")
    rrb = one(s["nodes"], "AnimGraphNode_RotateRootBone", "베이스 루트")
    aim = layer_node(s, "Aim_UpperBody")
    inert = one(s["nodes"], "AnimGraphNode_Inertialization", "베이스 루트")
    order = {c["from"]["node"]: c["to"]["node"] for c in s["connections"] if c["from"]["pin"] == "Pose"}
    # RotateRootBone 뒤는 Inertialization 이거나 최종 조준 보정(A4: L2C → 보정 → C2L)
    if order.get(layer["node_guid"]) == aim["node_guid"] and order.get(aim["node_guid"]) == rrb["node_guid"]:
        print("   이미 Aim_UpperBody → RotateRootBone — 건너뜀")
        return False
    old = order.get(layer["node_guid"]) == rrb["node_guid"] and order.get(rrb["node_guid"]) == aim["node_guid"] and order.get(aim["node_guid"]) == inert["node_guid"]
    check(old, "이행 전 순서 LayeredBoneBlend → RotateRootBone → Aim_UpperBody → Inertialization")
    if not old:
        sys.exit(1)
    ops = [
        {"op": "remove_node", "node": rrb["node_guid"]},
        {"op": "disconnect", "from": {"node": aim["node_guid"], "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
        {"op": "connect", "from": {"node": layer["node_guid"], "pin": "Pose"}, "to": {"node": aim["node_guid"], "pin": "InPose"}},
        {"op": "add_node", "ref": "rrb", "class": "AnimGraphNode_RotateRootBone", "pos": [-150, 0]},
        {"op": "connect", "from": {"node": aim["node_guid"], "pin": "Pose"}, "to": {"ref": "rrb", "pin": "BasePose"}},
        {"op": "bind_pin", "ref": "rrb", "property": "Yaw", "path": "RootYawOffset"},
        {"op": "connect", "from": {"ref": "rrb", "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
    ]
    apply(ABP, ops, "베이스 AimOffset → RotateRootBone 순서", compile=True, save=True)
    return True


def turn_state_ops(ref: str, recovery: bool) -> list[dict]:
    """한 상태의 포즈 그래프: BlendListByEnum(TurnInPlaceKind) ← 기본 Rifle_Idle + 턴 클립 4개."""
    p = f"{ref}_"
    ops: list[dict] = [{"op": "add_node", "ref": p + "sel", "graph": {"ref": ref}, "class": "AnimGraphNode_BlendListByEnum", "enum": ENUM, "pos": [-300, 0]}]
    ops += [{"op": "add_blend_pose", "ref": p + "sel", "entry": k} for k in CLIPS]
    ops.append({"op": "bind_pin", "ref": p + "sel", "property": "ActiveEnumValue", "path": f"{MAIN}.TurnInPlaceKind"})
    ops += [
        # 기본(None) 포즈는 관련 플레이어에서 제외 — 자동 전이(Recovery → Idle)가 턴 클립의 남은 시간을 봐야 한다
        {"op": "add_node", "ref": p + "none", "graph": {"ref": ref}, "class": "AnimGraphNode_SequencePlayer", "pos": [-800, -300], "asset": AIM_IDLE,
         "properties": {"bLoopAnimation": True, "bIgnoreForRelevancyTest": True}},
        {"op": "connect", "from": {"ref": p + "none", "pin": "Pose"}, "to": {"ref": p + "sel", "pin": "BlendPose_0"}},
    ]
    for i, (kind, clip) in enumerate(CLIPS.items(), 1):
        ops.append({"op": "add_node", "ref": p + kind, "graph": {"ref": ref}, "class": "AnimGraphNode_SequencePlayer", "pos": [-800, -300 + i * 150],
                    "asset": f"{TURN_DIR}/{clip}", "properties": {"bLoopAnimation": False}})
        if recovery:
            # Rotation 에서 흐른 시간부터 이어서 — 상태 진입 때 한 번 읽힌다(SequencePlayer 초기화)
            ops.append({"op": "bind_pin", "ref": p + kind, "property": "StartPosition", "path": f"{MAIN}.TurnInPlaceAnimTime"})
        ops.append({"op": "connect", "from": {"ref": p + kind, "pin": "Pose"}, "to": {"ref": p + "sel", "pin": f"BlendPose_{i}"}})
    ops.append({"op": "connect", "from": {"ref": p + "sel", "pin": "Pose"}, "to": {"result_of": {"ref": ref}, "pin": "Result"}})
    return ops


def patch_provider() -> bool:
    print("\n=== B. 공급자 ABP_HeroLayers_Rifle — 조준 Idle 상태머신 IdleTurn ===")
    g = layer_graphs(PROV_RIFLE)
    idle_g = g["Locomotion_Idle"]
    s = structure(PROV_RIFLE, idle_g)
    if any(n["class"] == "AnimGraphNode_StateMachine" for n in s["nodes"]):
        print("   이미 있음 — 건너뜀")
        return False
    bl = one(s["nodes"], "AnimGraphNode_BlendListByBool", "공급자 Idle")
    feed = next((c for c in s["connections"] if c["to"]["node"] == bl["node_guid"] and c["to"]["pin"] == "BlendPose_0"), None)
    check(feed is not None, "BlendListByBool.BlendPose_0(true = 조준) 입력 확인")
    tr = {"CrossfadeDuration": XFADE, "LogicType": "TLT_Inertialization"}
    ops: list[dict] = [
        # 조준 Idle 시퀀스(aim_idle_seq) 자리를 상태머신으로
        {"op": "remove_node", "node": feed["from"]["node"]},
        {"op": "add_node", "ref": "sm", "graph": idle_g, "class": "AnimGraphNode_StateMachine", "pos": [-700, 150]},
        {"op": "rename_node", "ref": "sm", "name": SM_NAME},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"node": bl["node_guid"], "pin": "BlendPose_0"}},
        {"op": "add_state", "ref": "idle", "sm": {"ref": "sm"}, "name": "Idle", "pos": [0, 0]},
        {"op": "add_state", "ref": "rot", "sm": {"ref": "sm"}, "name": "TurnInPlaceRotation", "pos": [500, 0]},
        {"op": "add_state", "ref": "rec", "sm": {"ref": "sm"}, "name": "TurnInPlaceRecovery", "pos": [500, 400]},
        {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}},
        # Recovery 중 다시 돌면 Rotation 으로 재진입 — 아직 블렌드 아웃 중이어도 클립을 처음부터
        {"op": "set_property", "ref": "rot", "property": "bAlwaysResetOnEntry", "value": True},
        {"op": "add_node", "ref": "idle_seq", "graph": {"ref": "idle"}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": AIM_IDLE, "properties": {"bLoopAnimation": True}},
        {"op": "connect", "from": {"ref": "idle_seq", "pin": "Pose"}, "to": {"result_of": {"ref": "idle"}, "pin": "Result"}},
    ]
    ops += turn_state_ops("rot", recovery=False)
    ops += turn_state_ops("rec", recovery=True)
    ops += [
        {"op": "add_transition", "ref": "t_idle_rot", "from": {"ref": "idle"}, "to": {"ref": "rot"}, "properties": {**tr, "PriorityOrder": 1}, "rule": acc("bWantsTurnInPlace")},
        {"op": "add_transition", "ref": "t_rot_rec", "from": {"ref": "rot"}, "to": {"ref": "rec"}, "properties": {**tr, "PriorityOrder": 1}, "rule": acc("bTurnInPlaceRotationFinished")},
        {"op": "add_transition", "ref": "t_rec_rot", "from": {"ref": "rec"}, "to": {"ref": "rot"}, "properties": {**tr, "PriorityOrder": 1}, "rule": acc("bWantsTurnInPlace")},
        # 클립이 끝나면 Idle — 재회전 요청이 우선(PriorityOrder 2)
        {"op": "add_transition", "ref": "t_rec_idle", "from": {"ref": "rec"}, "to": {"ref": "idle"}, "properties": {**tr, "PriorityOrder": 2}, "rule": hc.AUTO},
    ]
    apply(PROV_RIFLE, ops, "공급자 IdleTurn 상태머신", compile=True, save=True)
    return True


# ----------------------------------------------------------------------------------------------------------------------
def verify() -> None:
    print("\n=== C. 검증 — 구조 · 스모크 · C++ 단위 테스트 · PIE 진입 ===")
    s = structure(ABP)
    rrb = one(s["nodes"], "AnimGraphNode_RotateRootBone", "베이스 루트")
    # 바인딩은 pins[] 가 아니라 optional_pins[] 에 실린다 (bound · binding{path, path_text, type, context, promotion})
    yaw = bound_path(rrb, "Yaw")
    check(yaw == ["RootYawOffset"], f"베이스 RotateRootBone.Yaw ← RootYawOffset ({yaw})")
    layer = one(s["nodes"], "AnimGraphNode_LayeredBoneBlend", "베이스 루트")
    seq = pose_chain(s, layer["node_guid"])
    print(f"   베이스 루트: LayeredBoneBlend → {' → '.join(seq)}")
    check(seq == ["LinkedAnimLayer", "RotateRootBone", "LocalToComponentSpace", AIM_FIX_CLASS.replace("AnimGraphNode_", ""), "ComponentToLocalSpace", "Inertialization", "Root"],
          "베이스 순서 LayeredBoneBlend → Aim_UpperBody(AimOffset) → RotateRootBone → L2C → Aim Correction → C2L → Inertialization (AO 가산은 루트 회전 전, 보정은 최종 공간)")
    fix = one(s["nodes"], AIM_FIX_CLASS, "베이스 루트")
    fix_bind = {prop: bound_path(fix, prop) for prop in AIM_FIX_BINDINGS}
    check(all(fix_bind[p] == [v] for p, v in AIM_FIX_BINDINGS.items()) and str(fix["properties"].get("AlphaInputType")).endswith("Bool"),
          f"Aim Correction 바인딩 {fix_bind} · 알파 bool ({fix['properties'].get('AlphaInputType')})")
    # 무기 포즈 오버레이 — Locomotions → 오버레이 레이어 → Slot DefaultSlot (슬롯 앞)
    sm_node = one(s["nodes"], "AnimGraphNode_StateMachine", "베이스 루트")
    head = pose_chain(s, sm_node["node_guid"], limit=2)
    ov = layer_node(s, OVERLAY_LAYER)
    nxt = {c["from"]["node"]: c["to"]["node"] for c in s["connections"] if c["from"]["pin"] == "Pose"}
    check(nxt.get(sm_node["node_guid"]) == ov["node_guid"] and head == ["LinkedAnimLayer", "Slot"], f"베이스 루트 Locomotions → {OVERLAY_LAYER} → DefaultSlot ({head})")
    bs_ov = structure(ABP, layer_graphs(ABP)[OVERLAY_LAYER])
    check([n["class"] for n in bs_ov["nodes"] if n["class"] not in ("AnimGraphNode_Root", "AnimGraphNode_LinkedInputPose")] == [] and len(bs_ov["connections"]) == 1,
          "베이스 오버레이 기본 구현 = 통과 (입력 포즈 → Output)")

    g = layer_graphs(PROV_RIFLE)
    # 라이플 오버레이 = InPose → 휴대 팔(clavicle_r↓ ← Rifle_Idle 정지, HandsFreeAlpha) → 조준 상체(spine_01↑ ← AimingIdle, AimPoseAlpha) → Output
    ov_s = structure(PROV_RIFLE, g[OVERLAY_LAYER])
    cls = {n["node_guid"]: n for n in ov_s["nodes"]}
    feeds_of = lambda node: {c["to"]["pin"]: c["from"] for c in ov_s["connections"] if c["to"]["node"] == node["node_guid"]}

    def lbb_ok(node: dict | None, bone: str, asset_suffix: str, weight: str, base_cls: str) -> bool:
        if not node or node["class"] != "AnimGraphNode_LayeredBoneBlend":
            return False
        lp, feeds = node["properties"], feeds_of(node)
        pose_src = cls.get(feeds.get("BlendPoses_0", {}).get("node"), {})
        return (lp.get("bMeshSpaceRotationBlend") is True and str(lp.get("CurveBlendOption")).endswith("UseBasePose")
                and lp.get("LayerSetup") == [{"BranchFilters": [{"BoneName": bone, "BlendDepth": 0}]}]
                and (pose_src.get("asset") or "").endswith(asset_suffix) and feeds.get("BlendWeights_0", {}).get("pin") == weight
                and cls.get(feeds.get("BasePose", {}).get("node"), {}).get("class") == base_cls)

    ov_root = one(ov_s["nodes"], "AnimGraphNode_Root", "라이플 오버레이 레이어")
    aim_lbb = cls.get(feeds_of(ov_root).get("Result", {}).get("node"))
    carry_lbb = cls.get(feeds_of(aim_lbb).get("BasePose", {}).get("node")) if aim_lbb else None
    aim_pose = cls.get(feeds_of(aim_lbb).get("BlendPoses_0", {}).get("node"), {}) if aim_lbb else {}
    check(lbb_ok(aim_lbb, UPPER_BODY_BONE, "AS_Vesper_Rifle_AimIdle", "AimPoseAlpha", "AnimGraphNode_LayeredBoneBlend")
          and aim_pose.get("properties", {}).get("bIgnoreForRelevancyTest") is True,
          "라이플 오버레이 조준 상체 = spine_01↑ ← AS_Vesper_Rifle_AimIdle (메시 공간 · 커브 베이스 · 관련 플레이어 제외) · 가중치 ← AimPoseAlpha · 아래는 휴대 팔")
    check(lbb_ok(carry_lbb, CARRY_BONE, "AS_Vesper_Rifle_Idle", "HandsFreeAlpha", "AnimGraphNode_LinkedInputPose")
          and cls.get(feeds_of(carry_lbb).get("BlendPoses_0", {}).get("node"), {}).get("class") == "AnimGraphNode_SequenceEvaluator",
          f"라이플 오버레이 휴대 팔 = InPose 위 {CARRY_BONE}↓ ← AS_Vesper_Rifle_Idle 정지 프레임 (메시 공간 · 커브 베이스) · 가중치 ← HandsFreeAlpha")
    ps = structure(PROV_RIFLE, g["Locomotion_Idle"], depth=-1)
    sm = next((m for m in ps["state_machines"] if m.get("name") == SM_NAME), None)
    check(sm is not None, f"공급자 Idle 상태머신 {SM_NAME} 존재")
    if sm:
        names = {st["node_guid"]: st["name"] for st in sm["states"]}
        trs = sorted((names[t["from"]], names[t["to"]], t["priority_order"], t.get("logic_type") or t.get("properties", {}).get("LogicType")) for t in sm["transitions"])
        print(f"   states={sorted(names.values())} transitions={trs}")
        check(sorted(names.values()) == ["Idle", "TurnInPlaceRecovery", "TurnInPlaceRotation"] and len(trs) == 4, "상태 3 · 전이 4")
    byenum = [n for n in ps["nodes"] if n["class"] == "AnimGraphNode_BlendListByEnum"]
    check(len(byenum) == 2 and all("EAstralTurnInPlaceKind" in str(n["properties"].get("BoundEnum")) for n in byenum), f"BlendListByEnum 2개 · EAstralTurnInPlaceKind ({len(byenum)})")
    bound = [bound_path(n, "ActiveEnumValue") for n in byenum]
    check(all(b == [MAIN, "TurnInPlaceKind"] for b in bound), f"ActiveEnumValue ← GetMainAnimInstance.TurnInPlaceKind (2개) {bound}")
    players = [n for n in ps["nodes"] if n["class"] == "AnimGraphNode_SequencePlayer"]
    aim_graphs = {st["bound_graph_guid"] for st in (sm["states"] if sm else [])}
    aim_players = [n for n in players if n["graph_guid"] in aim_graphs and not (n.get("asset") or "").startswith(TURN_DIR)]
    # 조준 가지 Idle 플레이어 3 = IdleTurn Idle + Rotation/Recovery 기본(None) 포즈 — 상태별 상체 블렌드는 오버레이로 옮겨 없다(2026-10-22)
    check(len(aim_players) == 3 and all((n.get("asset") or "").endswith("AS_Vesper_Rifle_AimIdle") for n in aim_players), f"조준 가지 Idle 플레이어 3개 = AS_Vesper_Rifle_AimIdle ({len(aim_players)})")
    mv = structure(PROV_RIFLE, g["Locomotion_Move"])
    mv_lbb = [n for n in mv["nodes"] if n["class"] == "AnimGraphNode_LayeredBoneBlend"]
    check(not mv_lbb, f"Move 조준 가지 상체 블렌드 없음 — 오버레이가 덮는다 ({len(mv_lbb)})")
    # 왼손 IK — Aim_UpperBody: AimOffset → L2C → CopyBone(hand_r → ik_hand_gun) → ModifyBone(ik_hand_l ← 무기 파지점) → TwoBoneIK(hand_l → ik_hand_l, 회전 포함) → C2L
    aim_s = structure(PROV_RIFLE, g["Aim_UpperBody"])
    by_cls = {}
    for n in aim_s["nodes"]:
        by_cls.setdefault(n["class"], []).append(n)
    ik_ok = all(len(by_cls.get("AnimGraphNode_" + c, [])) == 1 for c in ("CopyBone", "ModifyBone", "TwoBoneIK"))
    if ik_ok:
        cp = by_cls["AnimGraphNode_CopyBone"][0]["properties"]
        mb_n = by_cls["AnimGraphNode_ModifyBone"][0]
        mb = mb_n["properties"]
        ik_n = by_cls["AnimGraphNode_TwoBoneIK"][0]
        p = ik_n["properties"]
        ik_ok = (cp["SourceBone"]["BoneName"] == GRIP_REF_BONE and cp["TargetBone"]["BoneName"] == IK_GUN_BONE and cp["bCopyTranslation"] is True and cp["bCopyRotation"] is True
                 and mb["BoneToModify"]["BoneName"] == IK_LEFT_BONE and mb["TranslationMode"] == "BMM_Replace" and mb["RotationMode"] == "BMM_Replace"
                 and mb["TranslationSpace"] == "BCS_ParentBoneSpace" and mb["RotationSpace"] == "BCS_ParentBoneSpace"
                 and bound_path(mb_n, "Translation") == [MAIN, "LeftHandGripLocation"] and bound_path(mb_n, "Rotation") == [MAIN, "LeftHandGripRotation"]
                 and p["IKBone"]["BoneName"] == "hand_l" and p["EffectorTarget"]["BoneReference"]["BoneName"] == IK_LEFT_BONE and p["EffectorLocationSpace"] == "BCS_BoneSpace"
                 and p["bTakeRotationFromEffectorSpace"] is True and str(p.get("AlphaInputType")).endswith("Float") and bound_path(ik_n, "Alpha") == ["LeftHandIKAlpha"]
                 and not bound_path(ik_n, "bAlphaBoolEnabled")
                 and all((abs(p.get(k, 0) - v) < 1e-4) if isinstance(v, float) else p.get(k) == v for k, v in IK_STRETCH.items()))
        chain = {c["from"]["node"]: c["to"]["node"] for c in aim_s["connections"] if c["from"]["pin"] in ("Pose", "ComponentPose")}
        cls = {n["node_guid"]: n["class"] for n in aim_s["nodes"]}
        seq, cur = [], by_cls["AnimGraphNode_RotationOffsetBlendSpace"][0]["node_guid"]
        while cur in chain and len(seq) < 8:
            cur = chain[cur]
            seq.append(cls[cur].replace("AnimGraphNode_", ""))
        print(f"   Aim_UpperBody: AimOffset → {' → '.join(seq)}")
        ik_ok = ik_ok and seq == ["LayeredBoneBlend", "LocalToComponentSpace", "CopyBone", "ModifyBone", "TwoBoneIK", "ComponentToLocalSpace", "Root"]
        fl = by_cls.get("AnimGraphNode_LayeredBoneBlend", [])
        fp = fl[0]["properties"] if len(fl) == 1 else {}
        ik_ok = ik_ok and fp.get("bMeshSpaceRotationBlend") is False and str(fp.get("CurveBlendOption")).endswith("UseBasePose")             and fp.get("LayerSetup") == [{"BranchFilters": [{"BoneName": "hand_l", "BlendDepth": 0}]}]
        # 손가락 가중치 = 왼손 IK 알파 — 놓으면 손가락도 클립 그대로
        w = next((c["from"] for c in aim_s["connections"] if fl and c["to"]["node"] == fl[0]["node_guid"] and c["to"]["pin"] == "BlendWeights_0"), {})
        ik_ok = ik_ok and w.get("pin") == "LeftHandIKAlpha"
    check(ik_ok, f"공급자 왼손 손가락 LBB(hand_l 이하 ← AimingIdle, 로컬, 커브 베이스, 가중치 ← LeftHandIKAlpha) · 왼손 IK — CopyBone({GRIP_REF_BONE}→{IK_GUN_BONE}) · ModifyBone({IK_LEFT_BONE} ← {MAIN}.LeftHandGripLocation/Rotation) · TwoBoneIK(hand_l → {IK_LEFT_BONE}, 회전 포함, Alpha(float) ← LeftHandIKAlpha) · AimOffset 뒤")
    lbb = [n for n in ps["nodes"] if n["class"] == "AnimGraphNode_LayeredBoneBlend"]
    check(not lbb, f"Rotation/Recovery 상체 블렌드 없음 — 오버레이가 덮는다 ({len(lbb)})")
    turn_graphs = {st["bound_graph_guid"] for st in (sm["states"] if sm else []) if st["name"] != "Idle"}
    idle_in_turn = [n for n in players if (n.get("asset") or "").endswith("AS_Vesper_Rifle_AimIdle") and n["graph_guid"] in turn_graphs]
    check(len(idle_in_turn) == 2 and all(n["properties"].get("bIgnoreForRelevancyTest") is True for n in idle_in_turn), f"Rotation/Recovery 기본(None) Idle 플레이어 2개 전부 bIgnoreForRelevancyTest ({len(idle_in_turn)})")
    starts = [n for n in players if bound_path(n, "StartPosition") == [MAIN, "TurnInPlaceAnimTime"]]
    # 플레이어 12 = 비조준 가지 Rifle_Idle 1 + 상태머신 Idle 1 + Rotation/Recovery 각 (기본 1 + 클립 4)
    check(len(starts) == 4 and len(players) == 12, f"Recovery 클립 4개 StartPosition ← TurnInPlaceAnimTime ({len(starts)} / 플레이어 {len(players)})")

    j = must(call("run_automation_tests", filter="AnimGraphMcp.Smoke.AnimBlueprint"), "smoke")
    mine = {t["name"].split(".")[-1]: t for t in j["tests"] if t["name"].split(".")[-1] in ("ABP_Hero_Combat", "ABP_HeroLayers_Rifle")}
    for name, t in mine.items():
        print(f"   smoke {name}: {t['state']} errors={t['errors'][:1]} warnings={[w[:100] for w in t['warnings'][:3]]}")
    check(len(mine) == 2 and all(t["state"] == "passed" for t in mine.values()), "스모크 ABP_Hero_Combat · ABP_HeroLayers_Rifle passed")

    for flt, want in (("AstralBreak.TurnInPlace", 6), ("AstralBreak.AimCorrection", 5)):
        u = must(call("run_automation_tests", filter=flt), "unit")
        for t in u["tests"]:
            print(f"   unit {t['name']}: {t['state']} {t['errors'][:1]}")
        check(len(u["tests"]) == want and all(t["state"] == "passed" for t in u["tests"]), f"C++ 단위 테스트 {flt} {want}/{want} ({len(u['tests'])})")

    env = must(call("run_anim_scenario", asset_path=ABP, mesh=MESH, wait_frames=10, expect={"state_machines": {"Locomotions": "Idle"}}), "scenario")
    job, deadline = env, time.time() + 240
    while not job.get("done") and time.time() < deadline:
        time.sleep(1.0)
        job = must(bridge.call("poll_automation_tests", {"job_id": job["job_id"]}), "poll")
    t = job["tests"][0] if job["tests"] else {}
    print(f"   PIE: {t.get('state')} observed={json.dumps(t.get('observed') or {}, ensure_ascii=False)[:300]}")
    check(job["ok"] and t.get("state") == "passed", "PIE 에서 ABP_Hero_Combat(RotateRootBone 포함) 이 Locomotions=Idle 진입")

    info = must(call("get_anim_blueprint_info", asset_path=ABP), "combat info")
    pinfo = must(call("get_anim_blueprint_info", asset_path=PROV_RIFLE), "rifle info")
    STATE_FILE.write_text(json.dumps({"combat_revision": info["revision"], "rifle_revision": pinfo["revision"]}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"saved → {STATE_FILE}")


UPPER_BODY_BONE = "spine_01"
# 왼손 IK — 파지점 값은 무기 메시 소켓(C++ 이 장착 때 hand_r 공간으로 환산해 메인 AnimInstance 에 넣는다), 그래프는 그 값을 IK 본 체인으로 옮긴다
GRIP_REF_BONE = "hand_r"      # UAstralAnimInstance::WeaponReferenceBone 과 같아야 한다
IK_GUN_BONE = "ik_hand_gun"   # UE5 스켈레톤 관례 — 무기(오른손) 기준 IK 본, 자식 ik_hand_l = 왼손 목표
IK_LEFT_BONE = "ik_hand_l"
# 팔 늘이기 — 상체가 오른쪽으로 비틀리고(AO Yaw +45) 숙이면 왼어깨에서 핸드가드 파지점까지가 팔 길이를 넘어 손이 최대 3.7cm(AO 범위 밖 빠른 회전 5.6cm) 덜 닿았다
# (2026-10-21 프로브: 목표 29.2 → 28.2/26.2/25.5). 팔이 다 펴진 뒤에만 최대 10% 늘인다
IK_STRETCH = {"bAllowStretching": True, "StartStretchRatio": 1.0, "MaxStretchScale": 1.1}
AIM_IDLE = hc.AIM_IDLE
AO_SAMPLES = list(hc.AO_SAMPLES)


def upper_body_ops(graph: str, src_node: str, src_pin: str, dst_node: str, dst_pin: str, prefix: str) -> list[dict]:
    """src 포즈의 상체(spine_01↑)를 AS_Vesper_Rifle_AimIdle 로 덮어 dst 에 꽂는다 — LayeredBoneBlend(메시 공간, 커브는 베이스)."""
    return [
        {"op": "disconnect", "from": {"node": src_node, "pin": src_pin}, "to": {"node": dst_node, "pin": dst_pin}},
        {"op": "add_node", "ref": prefix + "ub_idle", "graph": graph, "class": "AnimGraphNode_SequencePlayer", "pos": [-300, 300], "asset": AIM_IDLE,
         "properties": {"bLoopAnimation": True, "bIgnoreForRelevancyTest": True}},
        {"op": "add_node", "ref": prefix + "lbb", "graph": graph, "class": "AnimGraphNode_LayeredBoneBlend", "pos": [100, 0],
         "properties": {"bMeshSpaceRotationBlend": True, "CurveBlendOption": "UseBasePose"}},
        {"op": "set_property", "ref": prefix + "lbb", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": UPPER_BODY_BONE, "BlendDepth": 0}]}]},
        {"op": "connect", "from": {"node": src_node, "pin": src_pin}, "to": {"ref": prefix + "lbb", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": prefix + "ub_idle", "pin": "Pose"}, "to": {"ref": prefix + "lbb", "pin": "BlendPoses_0"}},
        {"op": "connect", "from": {"ref": prefix + "lbb", "pin": "Pose"}, "to": {"node": dst_node, "pin": dst_pin}},
    ]


def patch_aim_base() -> bool:
    """AimOffset 기준 포즈 · 조준 중 상체 = AS_Vesper_Rifle_AimIdle (2026-10-20 2차 PIE: 팔 무너짐의 진짜 원인).
    AO 9샘플은 AS_Vesper_Rifle_AimIdle 기준으로 저작된 포즈(CC = 그 클립 프레임 0 과 0.0도)인데 기준이 총 내린 AS_Vesper_Rifle_Idle 이라
    델타가 "총 들기 + 회전" 으로 거대해지고 그 중간(Yaw 30~85)에서 두 손이 5cm 까지 붙었다(정상 23). 평소엔 몸이 카메라를 따라 Yaw 가 작아 안 보였고
    턴 중엔 Yaw 가 ±80 까지 가서 드러났다. 기준을 저작 기준으로 되돌리고, 조준 중엔 어디서나(IdleTurn 상태머신 Idle · Rotation/Recovery 기본·상체 · strafe 이동)
    상체가 그 클립이도록: 상태머신 Idle 클립 교체 + Move 조준 가지에 LayeredBoneBlend. 비조준 가지(Rifle_Idle · Jog, 총 내린 자세)는 그대로."""
    print("\n=== A0. AimOffset 기준 포즈 · 조준 상체 = AS_Vesper_Rifle_AimIdle ===")
    changed = False
    for path in AO_SAMPLES:
        r = must(call("set_sequence_additive", asset_path=path, additive_type="RotationOffsetMeshSpace", ref_pose_type="AnimFrame", ref_pose_sequence=AIM_IDLE, ref_frame_index=0, save=True), "additive " + path.split("/")[-1])
        check(r["additive_valid"], path.split("/")[-1] + f" 기준 = AS_Vesper_Rifle_AimIdle 프레임 0 (changed={r['changed']})")
        changed |= bool(r["changed"])
    g = layer_graphs(PROV_RIFLE)
    ps = structure(PROV_RIFLE, g["Locomotion_Idle"], depth=-1)
    sm = next((m for m in ps["state_machines"] if m.get("name") == SM_NAME), None)
    if sm is not None:
        aim_graphs = {st["bound_graph_guid"] for st in sm["states"]}   # Idle · Rotation · Recovery (조준 가지 전체)
        targets = [n for n in ps["nodes"] if n["class"] == "AnimGraphNode_SequencePlayer" and n["graph_guid"] in aim_graphs and (n.get("asset") or "").endswith("AS_Vesper_Rifle_Idle")]
        if targets:
            apply(PROV_RIFLE, [{"op": "set_asset", "node": n["node_guid"], "asset": AIM_IDLE} for n in targets], f"조준 가지 Rifle_Idle → AimingIdle ({len(targets)}개)", compile=True, save=True)
            changed = True
        else:
            print("   조준 가지 Idle 클립 이미 AimingIdle — 건너뜀")
    # Move 조준 가지(strafe): 상체를 AimingIdle 로 — Jog 클립은 총 내린 자세라 AO 를 그대로 얹으면 총이 안 올라간다
    # (2026-10-22 부터는 무기 포즈 오버레이(A5)가 같은 일을 상태와 무관하게 한다 — 있으면 건너뛴다)
    ms = structure(PROV_RIFLE, g["Locomotion_Move"])
    if has_weapon_overlay():
        print("   Move 조준 상체 — 무기 포즈 오버레이가 덮는다, 건너뜀")
    elif any(n["class"] == "AnimGraphNode_LayeredBoneBlend" for n in ms["nodes"]):
        print("   Move 조준 가지 상체 LayeredBoneBlend 이미 있음 — 건너뜀")
    else:
        bl = one(ms["nodes"], "AnimGraphNode_BlendListByBool", "공급자 Move")
        feed = next((c for c in ms["connections"] if c["to"]["node"] == bl["node_guid"] and c["to"]["pin"] == "BlendPose_0"), None)
        check(feed is not None, "Move BlendListByBool.BlendPose_0(true = 조준 strafe) 입력 확인")
        apply(PROV_RIFLE, upper_body_ops(g["Locomotion_Move"], feed["from"]["node"], feed["from"]["pin"], bl["node_guid"], "BlendPose_0", "mv_"), "Move 조준 가지 상체 AimingIdle", compile=True, save=True)
        changed = True
    return changed


def patch_left_hand_ik() -> bool:
    """라이플을 든 동안 왼손을 총 파지점에 고정 — 위치와 회전 모두, 조준·비조준 전부 (2026-10-21 사용자 결정 A: 무기 소켓 단일 원천).
    값: 무기 메시 소켓(BP_Weapon_Rifle.LeftHandGripSocket = HandGripTransformLeft)을 장비 매니저가 부착·외형·AnimBP 가 바뀔 때 hand_r 공간으로 환산해
    메인 AnimInstance 에 넣는다(LeftHandGripLocation/Rotation · bHasLeftHandGrip — 이벤트, 매 프레임 조회 없음). 무기는 손 본에 붙은 강체라 상수.
    그래프(공급자 Aim_UpperBody, AimOffset 뒤): CopyBone(hand_r → ik_hand_gun, 컴포넌트 공간) → ModifyBone(ik_hand_l, 부모(ik_hand_gun) 공간 Replace ← 파지점)
    → TwoBoneIK(hand_l, 목표 = ik_hand_l 본, 회전도 목표에서) → 왼손 = hand_r × 파지점. UE5 스켈레톤의 ik_hand_gun/ik_hand_l 관례를 그대로 쓴다.
    TwoBoneIK 단독으로는 회전 오프셋을 못 준다(목표 공간 회전 = 기준 본 회전뿐, AnimNode_TwoBoneIK.cpp:181) — 비조준 애니(Rifle_Idle·Jog)는 hand_r 기준
    왼손 회전이 조준과 ~70° 달라 위치만으로는 손목이 꺾인다. 팔꿈치 평면 = 현재 팔꿈치(lowerarm_l 본 공간 원점). Alpha bool ← GetMainAnimInstance.bHasLeftHandGrip 0.15초.
    이전 판(조준 중에만 · AS_Vesper_Rifle_AimIdle 파지점 상수 · 위치만)이 있으면 지우고 새로 만든다.
    남은 것: 장전 몽타주(AS_Vesper_Rifle_Reload — 손이 총을 떠난다)를 연결하면 IK 를 끄는 커브가 필요하다."""
    print("\n=== A2. 공급자 Aim_UpperBody — 왼손 IK (CopyBone → ModifyBone(ik_hand_l ← 무기 파지점) → TwoBoneIK) ===")
    g = layer_graphs(PROV_RIFLE)["Aim_UpperBody"]
    s = structure(PROV_RIFLE, g)
    if any(n["class"] == "AnimGraphNode_CopyBone" for n in s["nodes"]):
        # 이미 있음 — 팔 늘이기 설정만 맞춘다(2026-10-21 추가)
        ik = one(s["nodes"], "AnimGraphNode_TwoBoneIK", "공급자 Aim_UpperBody")
        want = {k: v for k, v in IK_STRETCH.items() if ik["properties"].get(k) != v}
        if want:
            apply(PROV_RIFLE, [{"op": "set_property", "node": ik["node_guid"], "property": k, "value": v} for k, v in want.items()], f"왼손 IK 팔 늘이기 {want}", compile=True, save=True)
            return True
        print("   이미 있음 — 건너뜀")
        return False
    ao = one(s["nodes"], "AnimGraphNode_RotationOffsetBlendSpace", "공급자 Aim_UpperBody")
    root = one(s["nodes"], "AnimGraphNode_Root", "공급자 Aim_UpperBody")
    # 이전 판 제거 — AimOffset 과 Output 사이의 공간 변환·IK 노드 (연결은 노드와 함께 사라진다)
    # 사전 검증은 같은 배치 앞선 op 를 모르므로(단일 연결 포즈 핀) 제거는 따로 한 배치
    old = [n["node_guid"] for n in s["nodes"] if n["class"] in ("AnimGraphNode_LocalToComponentSpace", "AnimGraphNode_TwoBoneIK", "AnimGraphNode_ComponentToLocalSpace")]
    if old:
        apply(PROV_RIFLE, [{"op": "remove_node", "node": n} for n in old], f"이전 판 왼손 IK 노드 {len(old)}개 제거")
        ops: list[dict] = []
    else:
        link = next((c for c in s["connections"] if c["from"]["node"] == ao["node_guid"] and c["to"]["node"] == root["node_guid"]), None)
        check(link is not None, "AimOffset.Pose → Output 연결 확인")
        ops = [{"op": "disconnect", "from": {"node": ao["node_guid"], "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}}]
    ops += [
        {"op": "add_node", "ref": "l2c", "graph": g, "class": "AnimGraphNode_LocalToComponentSpace", "pos": [-250, 200]},
        {"op": "add_node", "ref": "copy", "graph": g, "class": "AnimGraphNode_CopyBone", "pos": [-200, 200],
         "properties": {"SourceBone": {"BoneName": GRIP_REF_BONE}, "TargetBone": {"BoneName": IK_GUN_BONE}, "bCopyTranslation": True, "bCopyRotation": True,
                        "bCopyScale": False, "ControlSpace": "BCS_ComponentSpace"}},
        {"op": "add_node", "ref": "grip", "graph": g, "class": "AnimGraphNode_ModifyBone", "pos": [-150, 200],
         "properties": {"BoneToModify": {"BoneName": IK_LEFT_BONE}, "TranslationMode": "BMM_Replace", "TranslationSpace": "BCS_ParentBoneSpace",
                        "RotationMode": "BMM_Replace", "RotationSpace": "BCS_ParentBoneSpace", "ScaleMode": "BMM_Ignore"}},
        {"op": "bind_pin", "ref": "grip", "property": "Translation", "path": f"{MAIN}.LeftHandGripLocation"},
        {"op": "bind_pin", "ref": "grip", "property": "Rotation", "path": f"{MAIN}.LeftHandGripRotation"},
        {"op": "add_node", "ref": "lhik", "graph": g, "class": "AnimGraphNode_TwoBoneIK", "pos": [-100, 200],
         "properties": {"IKBone": {"BoneName": "hand_l"},
                        "EffectorLocationSpace": "BCS_BoneSpace", "EffectorTarget": {"bUseSocket": False, "BoneReference": {"BoneName": IK_LEFT_BONE}},
                        "EffectorLocation": {"X": 0, "Y": 0, "Z": 0}, "bTakeRotationFromEffectorSpace": True, "bMaintainEffectorRelRot": False,
                        "JointTargetLocationSpace": "BCS_BoneSpace", "JointTarget": {"bUseSocket": False, "BoneReference": {"BoneName": "lowerarm_l"}},
                        "JointTargetLocation": {"X": 0, "Y": 0, "Z": 0}, **IK_STRETCH,
                        "AlphaInputType": "Bool", "AlphaBoolBlend": {"BlendInTime": 0.15, "BlendOutTime": 0.15}}},
        {"op": "bind_pin", "ref": "lhik", "property": "bAlphaBoolEnabled", "path": f"{MAIN}.bHasLeftHandGrip"},
        {"op": "add_node", "ref": "c2l", "graph": g, "class": "AnimGraphNode_ComponentToLocalSpace", "pos": [-50, 200]},
        {"op": "connect", "from": {"node": ao["node_guid"], "pin": "Pose"}, "to": {"ref": "l2c", "pin": "LocalPose"}},
        {"op": "connect", "from": {"ref": "l2c", "pin": "ComponentPose"}, "to": {"ref": "copy", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "copy", "pin": "Pose"}, "to": {"ref": "grip", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "grip", "pin": "Pose"}, "to": {"ref": "lhik", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "lhik", "pin": "Pose"}, "to": {"ref": "c2l", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "c2l", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]
    apply(PROV_RIFLE, ops, "공급자 왼손 IK (무기 파지점)", compile=True, save=True)
    return True


def patch_left_hand_fingers() -> bool:
    """왼손 손가락 = 쥔 모양(AS_Vesper_Rifle_AimIdle) — 라이플을 든 모든 상태 (2026-10-21, 왼손 IK 조정 중 스크린샷). IK 는 손목(hand_l)의 위치·회전만 총에 붙이고
    손가락은 입력 포즈 그대로라, 비조준 애니(Rifle_Idle · Jog — 왼손이 총에서 떨어져 있다)에선 펴진 손가락이 핸드가드 위에 놓였다.
    AimOffset 뒤·IK 앞에 LayeredBoneBlend(hand_l 이하, 로컬 공간): 손가락 로컬 회전은 AO 샘플이 바꾸지 않으므로(쥔 손 그대로) 조준 상태는 무변화.
    hand_l 자체의 회전도 덮이지만 뒤의 TwoBoneIK(목표 회전 사용)가 다시 정한다. 커브는 베이스(UseBasePose) — 턴 클립 커브(TurnYawWeight)가 이 레이어를 지나 메인으로 간다."""
    print("\n=== A3. 공급자 Aim_UpperBody — 왼손 손가락 쥔 모양 (LayeredBoneBlend hand_l 이하 ← AimingIdle, 로컬) ===")
    g = layer_graphs(PROV_RIFLE)["Aim_UpperBody"]
    s = structure(PROV_RIFLE, g)
    if any(n["class"] == "AnimGraphNode_LayeredBoneBlend" for n in s["nodes"]):
        print("   이미 있음 — 건너뜀")
        return False
    ao = one(s["nodes"], "AnimGraphNode_RotationOffsetBlendSpace", "공급자 Aim_UpperBody")
    l2c = one(s["nodes"], "AnimGraphNode_LocalToComponentSpace", "공급자 Aim_UpperBody")
    link = next((c for c in s["connections"] if c["from"]["node"] == ao["node_guid"] and c["to"]["node"] == l2c["node_guid"]), None)
    check(link is not None, "AimOffset.Pose → LocalToComponent 연결 확인 (A2 왼손 IK 선행)")
    ops = [
        {"op": "disconnect", "from": {"node": ao["node_guid"], "pin": "Pose"}, "to": {"node": l2c["node_guid"], "pin": "LocalPose"}},
        {"op": "add_node", "ref": "fing_idle", "graph": g, "class": "AnimGraphNode_SequencePlayer", "pos": [-450, 400], "asset": AIM_IDLE,
         "properties": {"bLoopAnimation": True, "bIgnoreForRelevancyTest": True}},
        {"op": "add_node", "ref": "fing_lbb", "graph": g, "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-300, 300],
         "properties": {"bMeshSpaceRotationBlend": False, "CurveBlendOption": "UseBasePose"}},
        {"op": "set_property", "ref": "fing_lbb", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": "hand_l", "BlendDepth": 0}]}]},
        {"op": "connect", "from": {"node": ao["node_guid"], "pin": "Pose"}, "to": {"ref": "fing_lbb", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "fing_idle", "pin": "Pose"}, "to": {"ref": "fing_lbb", "pin": "BlendPoses_0"}},
        {"op": "connect", "from": {"ref": "fing_lbb", "pin": "Pose"}, "to": {"node": l2c["node_guid"], "pin": "LocalPose"}},
    ]
    apply(PROV_RIFLE, ops, "공급자 왼손 손가락 쥔 모양", compile=True, save=True)
    return True


def patch_turn_upperbody() -> bool:
    """회전·Recovery 상태의 상체(spine_01↑)를 Rifle_Idle 로 — 턴 클립(Lyra 라이플 자세)은 AimOffset 기준 포즈(Rifle_Idle)와 상체가 40° 쯤 달라
    그 위에 AimOffset ±90 을 얹으면 상체가 접힌다(2026-10-20 사용자 스크린샷). 하체·골반은 턴 클립(발 디딤), 상체는 기준 포즈 → AO 가 평소 조준과 같다.
    커브는 베이스(턴 클립) 것을 써야 TurnYawWeight 가 살아남는다(CurveBlendOption=UseBasePose). 보조 Idle 플레이어는 자동 전이의 관련 플레이어 선정에서 뺀다.
    2026-10-22 부터는 무기 포즈 오버레이(A5)가 조준 상체를 상태와 무관하게 한 곳에서 덮는다 — 오버레이가 있으면 건너뛴다(A5 가 이 블렌드를 지운다)."""
    print("\n=== B2. 공급자 Rotation/Recovery — 상체 Rifle_Idle (LayeredBoneBlend spine_01, 메시 공간) ===")
    if has_weapon_overlay():
        print("   무기 포즈 오버레이가 조준 상체를 덮는다 — 건너뜀")
        return False
    info = must(call("get_anim_blueprint_info", asset_path=PROV_RIFLE), "rifle info")
    changed = False
    for st in ("TurnInPlaceRotation", "TurnInPlaceRecovery"):
        g = next(x["graph_guid"] for x in info["graphs"] if x["name"] == st)
        s = structure(PROV_RIFLE, g)
        if any(n["class"] == "AnimGraphNode_LayeredBoneBlend" for n in s["nodes"]):
            print(f"   {st}: 이미 있음 — 건너뜀")
            continue
        sel = one(s["nodes"], "AnimGraphNode_BlendListByEnum", st)
        root = one(s["nodes"], "AnimGraphNode_StateResult", st)   # 상태 그래프의 출력은 StateResult (루트 AnimGraph 의 Root 가 아니다)
        idle_players = [n["node_guid"] for n in s["nodes"] if n["class"] == "AnimGraphNode_SequencePlayer" and (n.get("asset") or "").endswith("AS_Vesper_Rifle_Idle")]
        ops = [
            {"op": "disconnect", "from": {"node": sel["node_guid"], "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
            {"op": "add_node", "ref": "ub_idle", "graph": g, "class": "AnimGraphNode_SequencePlayer", "pos": [-300, 300], "asset": AIM_IDLE,
             "properties": {"bLoopAnimation": True, "bIgnoreForRelevancyTest": True}},
            {"op": "add_node", "ref": "lbb", "graph": g, "class": "AnimGraphNode_LayeredBoneBlend", "pos": [100, 0],
             "properties": {"bMeshSpaceRotationBlend": True, "CurveBlendOption": "UseBasePose"}},
            {"op": "set_property", "ref": "lbb", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": UPPER_BODY_BONE, "BlendDepth": 0}]}]},
            {"op": "connect", "from": {"node": sel["node_guid"], "pin": "Pose"}, "to": {"ref": "lbb", "pin": "BasePose"}},
            {"op": "connect", "from": {"ref": "ub_idle", "pin": "Pose"}, "to": {"ref": "lbb", "pin": "BlendPoses_0"}},
            {"op": "connect", "from": {"ref": "lbb", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
        ]
        # 기본(None) 포즈의 Rifle_Idle 도 관련 플레이어에서 제외 — 자동 전이(Recovery → Idle)가 턴 클립의 남은 시간을 봐야 한다
        ops += [{"op": "set_property", "node": n, "property": "bIgnoreForRelevancyTest", "value": True} for n in idle_players]
        apply(PROV_RIFLE, ops, f"{st} 상체 Rifle_Idle", compile=True, save=True)
        changed = True
    return changed


AIM_FIX_CLASS = "AnimGraphNode_AstralAimCorrection"   # C++ FAnimNode_AstralAimCorrection (그래프 노드는 AstralBreakEditor 모듈)
# 노드 핀 ← 베이스(메인 인스턴스) 자기 변수 — 체인(spine_03·04·05 = 0.25·0.35·0.4)·무기 본(hand_r)·최대각 30·반복 3 은 C++ 노드 기본값
AIM_FIX_BINDINGS = {"AimTarget": "AimCorrectionTarget", "MuzzleLocation": "MuzzleLocation", "MuzzleRotation": "MuzzleRotation", "bAlphaBoolEnabled": "bAimCorrectionActive"}


def pose_chain(s: dict, start: str, limit: int = 12) -> list[str]:
    """start 노드의 포즈 출력을 따라간 노드 클래스 순서 (AnimGraphNode_ 접두 생략)."""
    nxt = {c["from"]["node"]: c["to"]["node"] for c in s["connections"] if c["from"]["pin"] in ("Pose", "ComponentPose")}
    cls = {n["node_guid"]: n["class"] for n in s["nodes"]}
    seq, cur = [], start
    while cur in nxt and len(seq) < limit:
        cur = nxt[cur]
        seq.append(cls[cur].replace("AnimGraphNode_", ""))
    return seq


def patch_aim_correction() -> bool:
    """최종 조준 보정 (2026-10-21 총구 프로브 → 사용자 추천안 승인). AimOffset 은 각도 입력으로 저작 포즈를 섞을 뿐이라 총열이 발사 방향과
    어긋난 채 남는다 — 무기 배치 교정(setup/rifle_weapon_grip) 뒤에도 AO 대각(±45,±40) 8~10° · Pitch 극단 3~6° · 가까운 표적 시차.
    베이스 루트의 RotateRootBone 과 Inertialization 사이(최종 컴포넌트 공간)에 L2C → Astral Aim Correction → C2L: 총구(무기 소켓 → 장비 매니저 →
    MuzzleLocation/Rotation)의 +X 가 조준점(AimCorrectionTarget — 발사와 같은 카메라 조준점, 관찰자는 BaseAimRotation)을 향하도록 척추 3본에 나눠 돌린다.
    척추는 두 팔의 공통 조상이라 손·총·왼손 IK 결과가 강체로 함께 돈다. 알파 bool ← bAimCorrectionActive(조준 중 ∧ 총구 있음) 0.15초."""
    print("\n=== A4. 베이스 — 최종 조준 보정 (RotateRootBone → L2C → Astral Aim Correction → C2L → Inertialization) ===")
    s = structure(ABP)
    if any(n["class"] == AIM_FIX_CLASS for n in s["nodes"]):
        print("   이미 있음 — 건너뜀")
        return False
    rrb = one(s["nodes"], "AnimGraphNode_RotateRootBone", "베이스 루트")
    inert = one(s["nodes"], "AnimGraphNode_Inertialization", "베이스 루트")
    link = next((c for c in s["connections"] if c["from"]["node"] == rrb["node_guid"] and c["to"]["node"] == inert["node_guid"]), None)
    check(link is not None, "RotateRootBone.Pose → Inertialization.Source 연결 확인")
    if link is None:
        sys.exit(1)
    ops: list[dict] = [
        {"op": "disconnect", "from": {"node": rrb["node_guid"], "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
        {"op": "add_node", "ref": "fix_l2c", "class": "AnimGraphNode_LocalToComponentSpace", "pos": [-120, 150]},
        {"op": "add_node", "ref": "fix", "class": AIM_FIX_CLASS, "pos": [-90, 150],
         "properties": {"AlphaInputType": "Bool", "AlphaBoolBlend": {"BlendInTime": 0.15, "BlendOutTime": 0.15}}},
        {"op": "add_node", "ref": "fix_c2l", "class": "AnimGraphNode_ComponentToLocalSpace", "pos": [-60, 150]},
    ]
    ops += [{"op": "bind_pin", "ref": "fix", "property": prop, "path": var} for prop, var in AIM_FIX_BINDINGS.items()]
    ops += [
        {"op": "connect", "from": {"node": rrb["node_guid"], "pin": "Pose"}, "to": {"ref": "fix_l2c", "pin": "LocalPose"}},
        {"op": "connect", "from": {"ref": "fix_l2c", "pin": "ComponentPose"}, "to": {"ref": "fix", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "fix", "pin": "Pose"}, "to": {"ref": "fix_c2l", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "fix_c2l", "pin": "Pose"}, "to": {"node": inert["node_guid"], "pin": "Source"}},
    ]
    apply(ABP, ops, "베이스 최종 조준 보정", compile=True, save=True)
    return True


OVERLAY_LAYER = "Locomotion_WeaponOverlay"
OVERLAY_OUTPUTS = {"AimPoseAlpha", "LeftHandIKAlpha"}   # UAstralAnimInstance (C++ 2026-10-22) — 메인이 계산, 링크 인스턴스는 복사


def has_weapon_overlay() -> bool:
    """베이스 루트에 무기 포즈 오버레이 레이어 노드가 있는가 (A5 적용 여부)."""
    s = structure(ABP)
    return any(n["class"] == "AnimGraphNode_LinkedAnimLayer" and (n.get("linked_layer") or {}).get("layer") == OVERLAY_LAYER for n in s["nodes"])


def patch_weapon_overlay() -> bool:
    """무기 포즈 오버레이 (2026-10-22 사용자 PIE "조준 중 점프하면 상체가 조준 자세를 유지하지 않는다" → 추천안 승인).
    조준 상체(AS_Vesper_Rifle_AimIdle = AimOffset 기준 포즈)를 지상 상태마다(IdleTurn 회전·Recovery · Move strafe) 따로 덮던 것을 한 곳으로 —
    점프 3상태는 무기 무관 클립 상체 그대로라 AO 가산이 엉뚱한 팔에 얹혔다(PIE: 상체 편차 평균 83cm, 총열↔카메라 하강 중 45° — 보정 노드 30° 초과).
    인터페이스에 레이어 Locomotion_WeaponOverlay(InPose) 를 더하고 베이스 루트 Locomotions → [오버레이] → Slot DefaultSlot 에 둔다(슬롯 앞 — 몽타주가 계속 이긴다).
    베이스 기본 구현 = 통과(근접·맨손). 라이플 = LayeredBoneBlend(spine_01↑ ← AimingIdle, 메시 공간, 커브는 베이스 — 턴 클립 TurnYawWeight · 점프 클립
    DisableLHandIK 가 지나간다) · 가중치 ← AimPoseAlpha(bIsAiming 을 0.2초에 걸쳐 따라감, C++). 무기마다 이 레이어 하나에 자기 포즈를 둔다.
    기존 상태별 덮기(Move strafe LBB · Rotation/Recovery LBB 와 그 보조 플레이어)는 같은 결과의 중복이라 지운다(단일 원천)."""
    print(f"\n=== A5. 무기 포즈 오버레이 — 인터페이스 {OVERLAY_LAYER}(InPose) · 베이스 Locomotions → 오버레이 → DefaultSlot · 라이플 = 조준 상체 ===")
    info = must(call("get_anim_blueprint_info", asset_path=ABP), "combat info")
    missing = OVERLAY_OUTPUTS - {v["name"] for v in info["variables"]}
    check(not missing, f"C++ 오버레이·왼손 알파 변수 — 누락 {sorted(missing) or '없음'} (있으면 빌드가 안 됐거나 에디터가 옛 바이너리)")
    if missing:
        sys.exit(1)
    changed = False

    # 1) 인터페이스 레이어 — 구현 ABP(베이스·공급자)는 도구가 conform 해 빈 레이어 그래프(Root + 입력 포즈)를 얻는다
    ali = must(call("get_anim_blueprint_info", asset_path=hc.ALI), "ALI info")
    if OVERLAY_LAYER not in {l["name"] for l in ali["layers"]}:
        r = must(call("add_anim_layers", asset_path=hc.ALI, layers=[{"name": OVERLAY_LAYER, "input_poses": ["InPose"]}], compile=True, save=True, conform_implementers=True), "ALI add layer")
        print(f"   implementers={[i.get('asset_path') or i for i in r.get('implementers', [])]}")
        changed = True

    # 2) 베이스 기본 구현 = 통과
    g = layer_graphs(ABP)[OVERLAY_LAYER]
    s = structure(ABP, g)
    root = one(s["nodes"], "AnimGraphNode_Root", "베이스 오버레이 레이어")
    if not s["connections"]:
        inp = one(s["nodes"], "AnimGraphNode_LinkedInputPose", "베이스 오버레이 레이어")
        apply(ABP, [{"op": "connect", "from": {"node": inp["node_guid"], "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}}], "베이스 오버레이 기본 구현(통과)",
              compile=True, save=True)
        changed = True

    # 3) 베이스 루트 — Locomotions 와 DefaultSlot 사이
    s = structure(ABP)
    if not has_weapon_overlay():
        sm = one(s["nodes"], "AnimGraphNode_StateMachine", "베이스 루트")
        slot = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Slot" and n["properties"].get("SlotName") == hc.FULL_BODY_SLOT)
        ops = [
            {"op": "disconnect", "from": {"node": sm["node_guid"], "pin": "Pose"}, "to": {"node": slot["node_guid"], "pin": "Source"}},
            {"op": "add_node", "ref": "ov", "class": "AnimGraphNode_LinkedAnimLayer", "layer": OVERLAY_LAYER, "pos": [-1620, 150]},
            {"op": "connect", "from": {"node": sm["node_guid"], "pin": "Pose"}, "to": {"ref": "ov", "pin": "InPose"}},
            {"op": "connect", "from": {"ref": "ov", "pin": "Pose"}, "to": {"node": slot["node_guid"], "pin": "Source"}},
        ]
        apply(ABP, ops, "베이스 루트 Locomotions → 오버레이 → DefaultSlot", compile=True, save=True)
        changed = True

    # 4) 라이플 — 조준 상체
    g = layer_graphs(PROV_RIFLE)[OVERLAY_LAYER]
    s = structure(PROV_RIFLE, g)
    if not any(n["class"] == "AnimGraphNode_LayeredBoneBlend" for n in s["nodes"]):
        root = one(s["nodes"], "AnimGraphNode_Root", "라이플 오버레이 레이어")
        inp = one(s["nodes"], "AnimGraphNode_LinkedInputPose", "라이플 오버레이 레이어")
        ops = [
            {"op": "add_node", "ref": "aim_pose", "graph": g, "class": "AnimGraphNode_SequencePlayer", "pos": [-500, 250], "asset": AIM_IDLE,
             "properties": {"bLoopAnimation": True, "bIgnoreForRelevancyTest": True}},
            {"op": "add_node", "ref": "ov_lbb", "graph": g, "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-200, 0],
             "properties": {"bMeshSpaceRotationBlend": True, "CurveBlendOption": "UseBasePose"}},
            {"op": "set_property", "ref": "ov_lbb", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": UPPER_BODY_BONE, "BlendDepth": 0}]}]},
            {"op": "add_node", "ref": "ov_w", "graph": g, "class": "K2Node_VariableGet", "variable": "AimPoseAlpha", "pos": [-500, 450]},
            {"op": "connect", "from": {"node": inp["node_guid"], "pin": "Pose"}, "to": {"ref": "ov_lbb", "pin": "BasePose"}},
            {"op": "connect", "from": {"ref": "aim_pose", "pin": "Pose"}, "to": {"ref": "ov_lbb", "pin": "BlendPoses_0"}},
            {"op": "connect", "from": {"ref": "ov_w", "pin": "AimPoseAlpha"}, "to": {"ref": "ov_lbb", "pin": "BlendWeights_0"}},
            {"op": "connect", "from": {"ref": "ov_lbb", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
        ]
        apply(PROV_RIFLE, ops, "라이플 오버레이 = 조준 상체 (AimPoseAlpha)", compile=True, save=True)
        changed = True

    # 5) 중복 정리 — 상태별 조준 상체 블렌드와 그 보조 AimingIdle 플레이어 (오버레이가 같은 일을 한다). 사전 검증은 같은 배치의 앞선 제거를 모르므로
    #    (단일 연결 포즈 핀) 제거와 재연결은 두 배치
    pinfo = must(call("get_anim_blueprint_info", asset_path=PROV_RIFLE), "rifle info")
    targets = [("Locomotion_Move", layer_graphs(PROV_RIFLE)["Locomotion_Move"], "AnimGraphNode_BlendListByBool", "BlendPose_0")]
    targets += [(st, next(x["graph_guid"] for x in pinfo["graphs"] if x["name"] == st), "AnimGraphNode_StateResult", "Result") for st in ("TurnInPlaceRotation", "TurnInPlaceRecovery")]
    for name, gg, dst_cls, dst_pin in targets:
        s = structure(PROV_RIFLE, gg)
        lbbs = [n for n in s["nodes"] if n["class"] == "AnimGraphNode_LayeredBoneBlend"]
        if not lbbs:
            continue
        lbb = one(s["nodes"], "AnimGraphNode_LayeredBoneBlend", name)
        dst = one(s["nodes"], dst_cls, name)
        base_src = next(c["from"] for c in s["connections"] if c["to"]["node"] == lbb["node_guid"] and c["to"]["pin"] == "BasePose")
        helper = [c["from"]["node"] for c in s["connections"] if c["to"]["node"] == lbb["node_guid"] and c["to"]["pin"] == "BlendPoses_0"]
        apply(PROV_RIFLE, [{"op": "remove_node", "node": n} for n in [lbb["node_guid"], *helper]], f"{name} 상체 블렌드 제거 (중복)")
        apply(PROV_RIFLE, [{"op": "connect", "from": base_src, "to": {"node": dst["node_guid"], "pin": dst_pin}}], f"{name} 직결", compile=True, save=True)
        changed = True
    return changed


def patch_left_hand_alpha() -> bool:
    """왼손 IK 조건 (2026-10-22 사용자 PIE "비조준 점프에서 왼손이 계속 총을 잡아 부자연스럽다" → 추천안 승인).
    TwoBoneIK 알파 bool(bHasLeftHandGrip) → float LeftHandIKAlpha(C++): 파지점 × (1 − DisableLHandIK 커브 × (1 − AimPoseAlpha)), 0.15초 등속 보간.
    커브는 클립이 "왼손이 비었다" 고 표시(점프 3클립 — setup/hero_jump_lhand_curve, 이후 장전 몽타주) · 조준 오버레이가 상체를 두 손 조준 자세로 덮는 만큼 지운다.
    왼손 손가락(쥔 모양) LayeredBoneBlend 가중치도 같은 값 — 놓으면 손가락도 클립 그대로 펴진다."""
    print("\n=== A6. 공급자 Aim_UpperBody — 왼손 IK 알파 · 손가락 가중치 ← LeftHandIKAlpha ===")
    g = layer_graphs(PROV_RIFLE)["Aim_UpperBody"]
    s = structure(PROV_RIFLE, g)
    ik = one(s["nodes"], "AnimGraphNode_TwoBoneIK", "공급자 Aim_UpperBody")
    fing = one(s["nodes"], "AnimGraphNode_LayeredBoneBlend", "공급자 Aim_UpperBody")
    changed = False
    if bound_path(ik, "Alpha") != ["LeftHandIKAlpha"]:
        ops: list[dict] = []
        if bound_path(ik, "bAlphaBoolEnabled"):
            ops.append({"op": "unbind_pin", "node": ik["node_guid"], "property": "bAlphaBoolEnabled"})
        ops += [{"op": "set_property", "node": ik["node_guid"], "property": "AlphaInputType", "value": "Float"}]
        apply(PROV_RIFLE, ops, "왼손 IK 알파 입력 bool → float")
        apply(PROV_RIFLE, [{"op": "bind_pin", "node": ik["node_guid"], "property": "Alpha", "path": "LeftHandIKAlpha"}], "왼손 IK Alpha ← LeftHandIKAlpha", compile=True, save=True)
        changed = True
    if not any(c["to"]["node"] == fing["node_guid"] and c["to"]["pin"] == "BlendWeights_0" for c in s["connections"]):
        ops = [
            {"op": "add_node", "ref": "lh_w", "graph": g, "class": "K2Node_VariableGet", "variable": "LeftHandIKAlpha", "pos": [-450, 550]},
            {"op": "connect", "from": {"ref": "lh_w", "pin": "LeftHandIKAlpha"}, "to": {"node": fing["node_guid"], "pin": "BlendWeights_0"}},
        ]
        apply(PROV_RIFLE, ops, "왼손 손가락 가중치 ← LeftHandIKAlpha", compile=True, save=True)
        changed = True
    if not changed:
        print("   이미 있음 — 건너뜀")
    return changed


CARRY_BONE = "clavicle_r"   # 무기 든 팔 — 무기는 hand_r 에 붙는다(WeaponReferenceBone)


def patch_weapon_carry() -> bool:
    """비조준 공중의 무기 든 팔 = 휴대 자세 (2026-10-22 사용자 "후속안도 구현" — A5·A6 뒤 PIE: 왼손을 놓자 총이 오른손 혼자 점프 클립 팔을 따라
    최대 +48° 들렸다). 라이플 오버레이에서 조준 상체 블렌드 앞에 LayeredBoneBlend(clavicle_r↓ ← AS_Vesper_Rifle_Idle 프레임 0, 메시 공간 — 몸통이 숙여도
    총은 휴대 방향 그대로, 커브는 베이스) · 가중치 ← HandsFreeAlpha(클립이 무기에서 손을 뗀 정도 = DisableLHandIK × (1 − AimPoseAlpha) — 왼손 IK 를 끄는 것과
    같은 신호). 조준 중엔 0 이고 조준 블렌드가 상체를 통째로 덮는다. 상태 규칙이 아니라 클립 표시라 무기 전용 두 손 점프 클립이 생기면 커브만 빼면 된다.
    휴대 포즈는 정지 프레임(SequenceEvaluator) — Rifle_Idle 은 8.9초 대기 클립이라 공중 1초 안에 몸짓이 섞이지 않게."""
    print(f"\n=== A7. 라이플 오버레이 — 비조준 공중 오른팔 휴대 자세 ({CARRY_BONE}↓ ← Rifle_Idle, 가중치 ← HandsFreeAlpha) ===")
    info = must(call("get_anim_blueprint_info", asset_path=ABP), "combat info")
    check("HandsFreeAlpha" in {v["name"] for v in info["variables"]}, "C++ HandsFreeAlpha 변수 (없으면 빌드가 안 됐거나 에디터가 옛 바이너리)")
    g = layer_graphs(PROV_RIFLE)[OVERLAY_LAYER]
    s = structure(PROV_RIFLE, g)
    lbbs = [n for n in s["nodes"] if n["class"] == "AnimGraphNode_LayeredBoneBlend"]
    if len(lbbs) >= 2:
        print("   이미 있음 — 건너뜀")
        return False
    aim_lbb = one(s["nodes"], "AnimGraphNode_LayeredBoneBlend", "라이플 오버레이 레이어")
    inp = one(s["nodes"], "AnimGraphNode_LinkedInputPose", "라이플 오버레이 레이어")
    ops = [
        {"op": "disconnect", "from": {"node": inp["node_guid"], "pin": "Pose"}, "to": {"node": aim_lbb["node_guid"], "pin": "BasePose"}},
        {"op": "add_node", "ref": "carry_pose", "graph": g, "class": "AnimGraphNode_SequenceEvaluator", "pos": [-800, 250], "asset": RIFLE_IDLE,
         "properties": {"ExplicitTime": 0.0}},
        {"op": "add_node", "ref": "carry_lbb", "graph": g, "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-500, 0],
         "properties": {"bMeshSpaceRotationBlend": True, "CurveBlendOption": "UseBasePose"}},
        {"op": "set_property", "ref": "carry_lbb", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": CARRY_BONE, "BlendDepth": 0}]}]},
        {"op": "add_node", "ref": "carry_w", "graph": g, "class": "K2Node_VariableGet", "variable": "HandsFreeAlpha", "pos": [-800, 450]},
        {"op": "connect", "from": {"node": inp["node_guid"], "pin": "Pose"}, "to": {"ref": "carry_lbb", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "carry_pose", "pin": "Pose"}, "to": {"ref": "carry_lbb", "pin": "BlendPoses_0"}},
        {"op": "connect", "from": {"ref": "carry_w", "pin": "HandsFreeAlpha"}, "to": {"ref": "carry_lbb", "pin": "BlendWeights_0"}},
        {"op": "connect", "from": {"ref": "carry_lbb", "pin": "Pose"}, "to": {"node": aim_lbb["node_guid"], "pin": "BasePose"}},
    ]
    apply(PROV_RIFLE, ops, "라이플 오버레이 휴대 팔 (HandsFreeAlpha)", compile=True, save=True)
    return True


def patch() -> None:
    if not patch_base():
        patch_aim_before_root()
    patch_provider()
    patch_turn_upperbody()
    patch_aim_base()
    patch_left_hand_ik()
    patch_left_hand_fingers()
    patch_aim_correction()
    patch_weapon_overlay()
    patch_left_hand_alpha()
    patch_weapon_carry()


def main() -> int:
    must(bridge.call("get_editor_status"), "status")
    if "--verify-only" not in sys.argv:
        patch()
    verify()
    print("\n" + ("PASS" if not hc.FAILS else f"FAIL ({len(hc.FAILS)}):\n  - " + "\n  - ".join(hc.FAILS)))
    return 0 if not hc.FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
