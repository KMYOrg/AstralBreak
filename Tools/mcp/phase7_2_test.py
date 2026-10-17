"""Phase 7-2 — set_property 허용 목록 확장(노드 10종) · 오브젝트 참조 값 · 본 이름/스켈레톤 검증.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_2_test.py [--recheck]

Tool 추가 없음 — MCP 재시작 불필요. 대상(생성·덮어쓰기): /Game/Animation/Test/ABP_McpPropTest.
검사 항목:
  A. 생성 — 루트: Seq → ApplyAdditive → LocalToComponent → TwoBoneIK → ModifyBone → ComponentToLocal → Mirror → Inertialization → Root
     + 비연결: AimOffset(RotationOffsetBlendSpace) · SequenceEvaluator · BlendListByBool · LayeredBoneBlend. info.skeleton_blend_profiles 출력
  B. 설정 — 노드별 허용 목록 값(본 참조·enum·벡터·로테이터·중첩 구조체·배열·오브젝트 참조·null) 배치 하나 → 컴파일 0 에러 → 재조회 값 일치
  C. 거부 — 없는 본(IKBone·FilteredBones[]·EffectorTarget.BoneReference) · 없는 애셋 · 클래스 불일치 · BlendMasks(모드·개수) · 잘못된 enum · 허용 목록 밖 · 비오브젝트에 null
  D. 롤백 — 유효 set + 무효 set 한 배치 → 무변경 (revision)
  E. 저장 → --recheck: 값·revision 동일 · 컴파일 0 에러
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpPropTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
CURVE = "/Game/Assets/IdaFaber/Blueprints/Curve_CameraZoomMultiplier"
STATE_FILE = "Tools/mcp/phase7_2_state.json"
FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:2000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def code(env: dict) -> str:
    """오류 코드 — 배치 사전 검증 실패는 바깥이 BAD_REQUEST 이고 op 별 코드는 details.planned[i].error.code 에 있다"""
    if env.get("ok"):
        return "OK"
    err = env.get("error", {}) or {}
    d = err.get("details", {}) or {}
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        if (p.get("error") or {}).get("code"):
            return p["error"]["code"]
    return err.get("code", "")


def reason(env: dict) -> str:
    d = env.get("error", {}).get("details", {}) or {}
    if d.get("reason"):
        return d["reason"]
    if (d.get("cause") or {}).get("reason"):
        return d["cause"]["reason"]
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        r = (p.get("error") or {}).get("details", {}) or {}
        if r.get("reason"):
            return r["reason"]
    return ""


def msg(env: dict) -> str:
    err = env.get("error", {}) or {}
    d = err.get("details", {}) or {}
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        if (p.get("error") or {}).get("message"):
            return p["error"]["message"][:200]
    if (d.get("cause") or {}).get("message"):
        return d["cause"]["message"][:200]
    return err.get("message", "")[:200]


def info() -> dict:
    return must(bridge.call("get_anim_blueprint_info", {"asset_path": ABP}, timeout=bridge.COMPILE_TIMEOUT), "info")


def structure(depth: int = 0) -> dict:
    return must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": depth}, timeout=bridge.COMPILE_TIMEOUT), "structure")


def apply(ops: list, **kw) -> dict:
    return bridge.call("apply_graph_operations", {"asset_path": ABP, "operations": ops, **kw}, timeout=bridge.COMPILE_TIMEOUT)


def preview(ops: list) -> dict:
    return bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops}, timeout=bridge.COMPILE_TIMEOUT)


def compile_(save: bool = False) -> dict:
    return must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": save}, timeout=bridge.COMPILE_TIMEOUT), "compile")


def sp(node: str, prop: str, value) -> dict:
    return {"op": "set_property", "node": node, "property": prop, "value": value}


def node_of(s: dict, cls: str) -> dict:
    return next(n for n in s["nodes"] if n["class"] == cls)


def props(cls: str) -> dict:
    return node_of(structure(), cls)["properties"]


def close(a, b, eps=1e-4) -> bool:
    return abs(float(a) - float(b)) <= eps


def main_sections() -> None:
    print("=== A. 생성 ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    i = info()
    profiles = i.get("skeleton_blend_profiles", [])
    check(isinstance(profiles, list), f"skeleton_blend_profiles: {[(p['name'], p['mode']) for p in profiles]}")
    mask = next((p["path"] for p in profiles if p["is_blend_mask"]), None)
    profile = next((p["path"] for p in profiles if not p["is_blend_mask"]), None)
    s = structure()
    root = node_of(s, "AnimGraphNode_Root")["node_guid"]
    ops = [
        {"op": "add_node", "ref": "idle", "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-2400, 0]},
        {"op": "add_node", "ref": "idle2", "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-2400, 200]},
        {"op": "add_node", "ref": "add", "class": "AnimGraphNode_ApplyAdditive", "pos": [-2000, 0]},
        {"op": "add_node", "ref": "l2c", "class": "AnimGraphNode_LocalToComponentSpace", "pos": [-1700, 0]},
        {"op": "add_node", "ref": "ik", "class": "AnimGraphNode_TwoBoneIK", "pos": [-1400, 0]},
        {"op": "add_node", "ref": "mb", "class": "AnimGraphNode_ModifyBone", "pos": [-1100, 0]},
        {"op": "add_node", "ref": "c2l", "class": "AnimGraphNode_ComponentToLocalSpace", "pos": [-800, 0]},
        {"op": "add_node", "ref": "mirror", "class": "AnimGraphNode_Mirror", "pos": [-400, 600]},
        {"op": "add_node", "ref": "inert", "class": "AnimGraphNode_Inertialization", "pos": [-300, 0]},
        {"op": "add_node", "ref": "aim", "class": "AnimGraphNode_RotationOffsetBlendSpace", "pos": [-2000, 600]},
        {"op": "add_node", "ref": "eval", "class": "AnimGraphNode_SequenceEvaluator", "asset": IDLE, "pos": [-1600, 600]},
        {"op": "add_node", "ref": "bl", "class": "AnimGraphNode_BlendListByBool", "pos": [-1200, 600]},
        {"op": "add_node", "ref": "lbb", "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-800, 600]},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"ref": "add", "pin": "Base"}},
        {"op": "connect", "from": {"ref": "idle2", "pin": "Pose"}, "to": {"ref": "add", "pin": "Additive"}},
        {"op": "connect", "from": {"ref": "add", "pin": "Pose"}, "to": {"ref": "l2c", "pin": "LocalPose"}},
        {"op": "connect", "from": {"ref": "l2c", "pin": "ComponentPose"}, "to": {"ref": "ik", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "ik", "pin": "Pose"}, "to": {"ref": "mb", "pin": "ComponentPose"}},
        {"op": "connect", "from": {"ref": "mb", "pin": "Pose"}, "to": {"ref": "c2l", "pin": "ComponentPose"}},
        # Mirror 는 MirrorDataTable 없이는 컴파일 오류("does not have a mirror data table selected") — 프로젝트에 테이블이 없어 비연결로 둔다
        {"op": "connect", "from": {"ref": "c2l", "pin": "Pose"}, "to": {"ref": "inert", "pin": "Source"}},
        {"op": "connect", "from": {"ref": "inert", "pin": "Pose"}, "to": {"node": root, "pin": "Result"}},
    ]
    p = preview(ops)
    if not (p.get("ok") and p["result"].get("valid")):
        print("   preview:", json.dumps([x for x in (p.get("result") or {}).get("planned", []) if not x.get("ok")], ensure_ascii=False)[:1500], msg(p))
    a = must(apply(ops, compile=True), "create nodes")
    check(a["compile"]["num_errors"] == 0, f"노드 13개 + 연결(Mirror 제외) → 컴파일 0 에러 ({a['compile']['num_errors']}/{a['compile']['num_warnings']})")
    for m in a["compile"].get("messages", []):
        if m["level"] != "info":
            print(f"   compile[{m['level']}] {m['text'][:160]}")
    refs = a["refs"]
    allowed = {n["class"]: sorted(n["properties"].keys()) for n in structure()["nodes"]}
    check("IKBone" in allowed["AnimGraphNode_TwoBoneIK"] and "Alpha" in allowed["AnimGraphNode_TwoBoneIK"] and "BoneToModify" in allowed["AnimGraphNode_ModifyBone"] and "X" in allowed["AnimGraphNode_RotationOffsetBlendSpace"] and "GroupName" in allowed["AnimGraphNode_SequencePlayer"] and "BlendProfile" in allowed["AnimGraphNode_BlendListByBool"] and "BlendMasks" in allowed["AnimGraphNode_LayeredBoneBlend"], "허용 목록이 조회 properties 에 반영")
    rev0 = info()["revision"]

    print("\n=== B. 설정 ===")
    sets = [
        sp(refs["add"], "Alpha", 0.5), sp(refs["add"], "LODThreshold", 2), sp(refs["add"], "AlphaInputType", "Float"),
        sp(refs["add"], "AlphaScaleBias", {"Scale": 2.0, "Bias": 0.1}), sp(refs["add"], "AlphaBoolBlend", {"BlendInTime": 0.2, "BlendOption": "Cubic"}),
        sp(refs["ik"], "IKBone", {"BoneName": "hand_r"}), sp(refs["ik"], "EffectorLocationSpace", "BCS_ComponentSpace"),
        sp(refs["ik"], "EffectorLocation", {"X": 10, "Y": 20, "Z": 30}), sp(refs["ik"], "EffectorTarget", {"bUseSocket": False, "BoneReference": {"BoneName": "hand_l"}}),
        sp(refs["ik"], "JointTargetLocationSpace", "BCS_ParentBoneSpace"), sp(refs["ik"], "bAllowStretching", True), sp(refs["ik"], "MaxStretchScale", 1.5),
        sp(refs["ik"], "Alpha", 0.8), sp(refs["ik"], "TwistAxis", {"bInLocalSpace": False}),
        sp(refs["mb"], "BoneToModify", {"BoneName": "head"}), sp(refs["mb"], "Rotation", {"Pitch": 0, "Yaw": 45, "Roll": 0}),
        sp(refs["mb"], "RotationMode", "BMM_Additive"), sp(refs["mb"], "RotationSpace", "BCS_BoneSpace"), sp(refs["mb"], "TranslationMode", "BMM_Ignore"),
        sp(refs["mirror"], "bMirror", False), sp(refs["mirror"], "BlendTime", 0.3), sp(refs["mirror"], "bCurveMirroring", False), sp(refs["mirror"], "MirrorDataTable", None),
        sp(refs["inert"], "FilteredCurves", ["Foo", "Bar"]), sp(refs["inert"], "FilteredBones", [{"BoneName": "spine_01"}]), sp(refs["inert"], "bResetOnBecomingRelevant", True),
        sp(refs["idle"], "GroupName", "Loco"), sp(refs["idle"], "GroupRole", "TransitionLeader"), sp(refs["idle"], "Method", "SyncGroup"),
        sp(refs["eval"], "ExplicitTime", 0.25), sp(refs["eval"], "bShouldLoop", False), sp(refs["eval"], "ReinitializationBehavior", "StartPosition"), sp(refs["eval"], "StartPosition", 0.1),
        sp(refs["aim"], "X", 10), sp(refs["aim"], "Y", -5), sp(refs["aim"], "Alpha", 0.7), sp(refs["aim"], "bLoop", True), sp(refs["aim"], "GroupName", "Aim"),
        sp(refs["bl"], "BlendType", "Cubic"), sp(refs["bl"], "TransitionType", "Inertialization"), sp(refs["bl"], "CustomBlendCurve", CURVE),
        sp(refs["lbb"], "CurveBlendOption", "UseMaxValue"),
    ]
    # BlendMasks 는 노드의 현재 BlendMode 를 보므로(사전 검증은 같은 배치의 앞선 op 를 모른다) 모드 변경은 별도 배치로
    must(apply([sp(refs["lbb"], "BlendMode", "BlendMask")]), "set BlendMode")
    if profile:
        sets.append(sp(refs["bl"], "BlendProfile", profile))
        sets.append(sp(refs["inert"], "DefaultBlendProfile", profile))
    sets.append(sp(refs["lbb"], "BlendMasks", [mask]))
    p = preview(sets)
    if not (p.get("ok") and p["result"].get("valid")):
        print("   preview:", json.dumps([x for x in (p.get("result") or {}).get("planned", []) if not x.get("ok")], ensure_ascii=False)[:2000])
    b = must(apply(sets, compile=True), "set properties")
    check(b["compile"]["num_errors"] == 0, f"set_property {len(sets)}개 → 컴파일 0 에러 ({b['compile']['num_errors']}/{b['compile']['num_warnings']})")
    for m in b["compile"].get("messages", []):
        if m["level"] != "info":
            print(f"   compile[{m['level']}] {m['text'][:160]}")
    st = structure()
    by = {n["node_guid"]: n["properties"] for n in st["nodes"]}
    ad, ik, mb, mi, ine, idle, ev, aim, bl, lbb = (by[refs[k]] for k in ("add", "ik", "mb", "mirror", "inert", "idle", "eval", "aim", "bl", "lbb"))
    check(close(ad["Alpha"], 0.5) and ad["LODThreshold"] == 2 and ad["AlphaInputType"] == "Float" and close(ad["AlphaScaleBias"]["Scale"], 2.0) and close(ad["AlphaScaleBias"]["Bias"], 0.1) and close(ad["AlphaBoolBlend"]["BlendInTime"], 0.2) and ad["AlphaBoolBlend"]["BlendOption"] == "Cubic", f"ApplyAdditive 값 일치 {ad}")
    check(ik["IKBone"]["BoneName"] == "hand_r" and ik["EffectorLocationSpace"] == "BCS_ComponentSpace" and close(ik["EffectorLocation"]["Y"], 20) and ik["EffectorTarget"]["BoneReference"]["BoneName"] == "hand_l" and ik["EffectorTarget"]["bUseSocket"] is False and ik["bAllowStretching"] is True and close(ik["MaxStretchScale"], 1.5) and close(ik["Alpha"], 0.8), f"TwoBoneIK 값 일치 {json.dumps(ik)[:300]}")
    check(mb["BoneToModify"]["BoneName"] == "head" and close(mb["Rotation"]["Yaw"], 45) and mb["RotationMode"] == "BMM_Additive" and mb["RotationSpace"] == "BCS_BoneSpace" and mb["TranslationMode"] == "BMM_Ignore", f"ModifyBone 값 일치 {json.dumps(mb)[:300]}")
    check(mi["bMirror"] is False and close(mi["BlendTime"], 0.3) and mi["bCurveMirroring"] is False and mi["MirrorDataTable"] is None, f"Mirror 값 일치 {mi}")
    check(ine["FilteredCurves"] == ["Foo", "Bar"] and ine["FilteredBones"] == [{"BoneName": "spine_01"}] and ine["bResetOnBecomingRelevant"] is True and (not profile or ine["DefaultBlendProfile"] == profile), f"Inertialization 값 일치 {ine}")
    check(idle["GroupName"] == "Loco" and idle["GroupRole"] == "TransitionLeader" and idle["Method"] == "SyncGroup", f"SequencePlayer 싱크 그룹 {idle['GroupName']}/{idle['GroupRole']}/{idle['Method']}")
    check(close(ev["ExplicitTime"], 0.25) and ev["bShouldLoop"] is False and ev["ReinitializationBehavior"] == "StartPosition" and close(ev["StartPosition"], 0.1), f"SequenceEvaluator 값 일치 {ev}")
    check(close(aim["X"], 10) and close(aim["Y"], -5) and close(aim["Alpha"], 0.7) and aim["bLoop"] is True and aim["GroupName"] == "Aim", f"AimOffset 값 일치 {json.dumps(aim)[:200]}")
    # 조회는 오브젝트 경로("/Game/.../Asset.Asset")로 돌려준다 — 입력은 패키지 경로도 받는다
    check(bl["BlendType"] == "Cubic" and bl["TransitionType"] == "Inertialization" and (bl["CustomBlendCurve"] or "").startswith(CURVE) and (not profile or bl["BlendProfile"] == profile), f"BlendListByBool 값 일치 {bl}")
    check(lbb["BlendMode"] == "BlendMask" and lbb["CurveBlendOption"] == "UseMaxValue" and lbb["BlendMasks"] == [mask], f"LayeredBoneBlend BlendMasks {lbb['BlendMasks']}")
    pins = {p["name"]: p for p in node_of(st, "AnimGraphNode_TwoBoneIK")["pins"]}
    check("Alpha" in pins and pins["Alpha"]["default"].startswith("0.8"), f"노출 핀 Alpha 기본값 동기화 ({pins.get('Alpha', {}).get('default')})")
    rev1 = info()["revision"]
    check(rev1 != rev0, "revision 변화")

    print("\n=== C. 거부 ===")
    r = apply([sp(refs["ik"], "IKBone", {"BoneName": "no_such_bone"})]); check(code(r) == "BAD_REQUEST" and reason(r) == "BONE_NOT_FOUND", f"없는 본(IKBone) → BONE_NOT_FOUND ({reason(r)})")
    r = apply([sp(refs["inert"], "FilteredBones", [{"BoneName": "spine_01"}, {"BoneName": "nope"}])]); check(code(r) == "BAD_REQUEST" and reason(r) == "BONE_NOT_FOUND" and "FilteredBones[1]" in msg(r), f"없는 본(배열) → BONE_NOT_FOUND ({msg(r)})")
    r = apply([sp(refs["ik"], "EffectorTarget", {"BoneReference": {"BoneName": "nope"}})]); check(code(r) == "BAD_REQUEST" and reason(r) == "BONE_NOT_FOUND" and "EffectorTarget.BoneReference" in msg(r), f"없는 본(중첩) → BONE_NOT_FOUND ({msg(r)})")
    r = apply([sp(refs["bl"], "CustomBlendCurve", "/Game/Nope/Curve")]); check(code(r) == "BAD_REQUEST" and reason(r) == "OBJECT_NOT_FOUND", f"없는 애셋 → OBJECT_NOT_FOUND ({reason(r)})")
    r = apply([sp(refs["bl"], "BlendProfile", IDLE)]); check(code(r) == "BAD_REQUEST" and reason(r) == "OBJECT_CLASS_MISMATCH", f"클래스 불일치(BlendProfile ← AnimSequence) → OBJECT_CLASS_MISMATCH ({reason(r)})")
    r = apply([sp(refs["mirror"], "MirrorDataTable", CURVE)]); check(code(r) == "BAD_REQUEST" and reason(r) == "OBJECT_CLASS_MISMATCH", f"클래스 불일치(MirrorDataTable ← Curve) → OBJECT_CLASS_MISMATCH ({reason(r)})")
    r = apply([sp(refs["lbb"], "BlendMasks", [mask, mask])]); check(code(r) == "BAD_REQUEST" and reason(r) == "COUNT_MISMATCH", f"BlendMasks 개수 불일치 → COUNT_MISMATCH ({reason(r)})")
    r = apply([sp(refs["lbb"], "BlendMode", "BranchFilter"), sp(refs["lbb"], "BlendMasks", [mask])]); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_BLEND_MODE", f"BranchFilter 모드에서 BlendMasks → BAD_BLEND_MODE ({reason(r)})")
    if profile:
        r = apply([sp(refs["lbb"], "BlendMasks", [profile])]); check(code(r) == "BAD_REQUEST" and reason(r) == "BLEND_PROFILE_NOT_MASK", f"마스크가 아닌 프로파일 → BLEND_PROFILE_NOT_MASK ({reason(r)})")
    r = apply([sp(refs["mb"], "RotationSpace", "BCS_Nope")]); check(code(r) == "BAD_REQUEST" and "enum" in msg(r), f"잘못된 enum → BAD_REQUEST ({msg(r)})")
    r = apply([sp(refs["idle"], "Alpha", 1.0)]); check(code(r) == "PROPERTY_NOT_ALLOWED", f"허용 목록 밖(SequencePlayer.Alpha) → PROPERTY_NOT_ALLOWED ({code(r)})")
    r = apply([sp(refs["ik"], "Alpha", None)]); check(code(r) == "BAD_REQUEST" and "null" in msg(r), f"비오브젝트에 null → BAD_REQUEST ({msg(r)})")
    r = apply([sp(refs["ik"], "IKBone", "hand_r")]); check(code(r) == "BAD_REQUEST" and "object" in msg(r), f"구조체에 문자열 → BAD_REQUEST ({msg(r)})")
    check(info()["revision"] == rev1, "거부 뒤 revision 불변")

    print("\n=== D. 롤백 ===")
    r = apply([sp(refs["mb"], "BoneToModify", {"BoneName": "spine_01"}), sp(refs["add"], "Alpha", 0.9), sp(refs["ik"], "IKBone", {"BoneName": "nope"})])
    check(code(r) == "BAD_REQUEST" and reason(r) == "BONE_NOT_FOUND", f"혼합 배치 → 사전 검증 거부 ({reason(r)})")
    check(props("AnimGraphNode_ModifyBone")["BoneToModify"]["BoneName"] == "head" and info()["revision"] == rev1, "무변경 (사전 검증이 전부 막음)")

    print("\n=== E. 저장 ===")
    c = compile_(save=True)
    check(c["num_errors"] == 0, "컴파일 0 에러 + 저장")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"revision": info()["revision"], "ik": ik, "mb": mb, "bl": bl, "lbb": lbb, "profile": profile, "mask": mask}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    check(info()["revision"] == saved["revision"], "revision 동일")
    ik = props("AnimGraphNode_TwoBoneIK")
    mb = props("AnimGraphNode_ModifyBone")
    bl = props("AnimGraphNode_BlendListByBool")
    lbb = props("AnimGraphNode_LayeredBoneBlend")
    check(ik["IKBone"] == saved["ik"]["IKBone"] and ik["EffectorTarget"] == saved["ik"]["EffectorTarget"] and mb["RotationMode"] == saved["mb"]["RotationMode"], "본 참조·enum 값 유지")
    check(bl["CustomBlendCurve"] == saved["bl"]["CustomBlendCurve"] and bl.get("BlendProfile") == saved["bl"].get("BlendProfile") and lbb["BlendMasks"] == saved["lbb"]["BlendMasks"], f"오브젝트 참조 값 유지 ({bl['CustomBlendCurve']})")
    c = compile_()
    check(c["num_errors"] == 0, f"컴파일 0 에러 ({c['num_errors']}/{c['num_warnings']})")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        main_sections()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
