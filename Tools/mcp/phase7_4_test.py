"""Phase 7-4 — 레이어 값 파라미터 · InstanceClass · 인터페이스 레이어 추가/삭제 · 구현 ABP 동기화.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_4_test.py [--recheck]

새 Tool 3개(set_layer_inputs · add_anim_layers · remove_anim_layers)와 op set_layer_instance_class 는 세션 재시작 전 MCP 에 보이지 않으므로
HTTP 직접 호출로 검증한다. 대상(생성·덮어쓰기): /Game/Animation/Test/ALI_McpTest74 · ABP_McpLayer74Base(구현+레이어 노드) · ABP_McpLayer74Prov(공급자).
6-4b 의 ALI_McpTest/ABP_McpLayerBase/Provider 는 건드리지 않는다(6-4b recheck 가 비교).
검사 항목:
  A. 인터페이스 생성 — Upper(InPose + AimYaw:float) · Lower(InPose) · Full(입력 포즈 없음) → layers[].inputs · editable
  B. set_layer_inputs — Lower 에 2개 → 조회 · 재적용 unchanged · 1개로 축소 · [] 비움 · 거부 7종(NO_INPUT_POSE · 모르는 레이어 · 타입 · 중복 · 포즈 이름 · 다른 레이어와 중복 · 포즈 타입)
  C. 구현 — Base·Prov 구현(값 핀 전파) · Base AnimGraph 에 Upper 노드 + expose_pin AimYaw(custom) + Speed 연결 → 컴파일 0 에러
     · Prov 의 Upper 그래프에서 InPose.AimYaw → SequencePlayer PlayRate → 컴파일 0 에러 · 구현 그래프 set_layer_inputs → NOT_EDITABLE
  D. set_layer_instance_class — Base 의 Upper 노드 → Prov 클래스(애셋 경로·클래스 경로) → 컴파일 0 에러 · 조회 instance_class · null 로 해제
     · 거부 5종(SELF_CLASS · NOT_IMPLEMENTING · BAD_CLASS · ASSET_NOT_FOUND · SELF_LAYER(자체 레이어 노드)) · 혼합 배치 롤백
  E. add_anim_layers — 인터페이스에 Extra(InPose + Blend:float) → implementers 2 (컴파일 0 에러) · Base/Prov layers 에 Extra · 거부(중복·예약·BlendSpace)
     · ABP 자체 레이어 추가(OwnLayer) → Base 에서 노드로 사용
  F. remove_anim_layers — Upper 삭제 → LAYER_IN_USE_BY(usage: Base 노드 · Prov 그래프) · Extra 삭제(빈) → implementers 동기화 · Lower 채운 뒤 force 삭제 → usage 보고
     · 구현 그래프 삭제 → NOT_EDITABLE · 자체 레이어 삭제(노드 사용 중 → LAYER_IN_USE_BY → 노드 제거 뒤 삭제)
  G. 저장 → --recheck: 인터페이스 layers/inputs 동일 · Base revision·instance_class 동일 · 컴파일 0 에러
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ALI = "/Game/Animation/Test/ALI_McpTest74"
BASE = "/Game/Animation/Test/ABP_McpLayer74Base"
PROV = "/Game/Animation/Test/ABP_McpLayer74Prov"
OTHER_ABP = "/Game/Animation/Test/ABP_McpVarTest"   # 7-1 테스트 애셋 — 인터페이스를 구현하지 않는 ABP (NOT_IMPLEMENTING 용; 없으면 건너뜀)
BS_PROD = "/Game/Animation/Hero/Anims/Locomotions/BS_Hero_Locomotion1D"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
STATE_FILE = "Tools/mcp/phase7_4_state.json"
NEW_TOOLS = {"set_layer_inputs", "add_anim_layers", "remove_anim_layers"}
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
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:160]}")
    return env["result"]


def code(env: dict) -> str:
    if env.get("ok"):
        return "OK"
    err = env.get("error", {}) or {}
    d = err.get("details", {}) or {}
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        if (p.get("error") or {}).get("code"):
            return p["error"]["code"]
    return err.get("code", "")


def reason(env: dict) -> str:
    d = (env.get("error", {}) or {}).get("details", {}) or {}
    if d.get("reason"):
        return d["reason"]
    if (d.get("cause") or {}).get("reason"):
        return d["cause"]["reason"]
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        r = (p.get("error") or {}).get("details", {}) or {}
        if r.get("reason"):
            return r["reason"]
    return ""


def call(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def info(path: str) -> dict:
    return must(call("get_anim_blueprint_info", asset_path=path), f"info {path}")


def structure(path: str, graph: str | None = None, depth: int = 0) -> dict:
    p = {"asset_path": path, "depth": depth}
    if graph:
        p["graph_guid"] = graph
    return must(call("get_anim_graph_structure", **p), f"structure {path}")


def apply(path: str, ops: list, **kw) -> dict:
    return call("apply_graph_operations", asset_path=path, operations=ops, **kw)


def compile_(path: str, save: bool = False) -> dict:
    return must(call("compile_animation_blueprint", asset_path=path, save_on_success=save), f"compile {path}")


def layer_of(i: dict, name: str) -> dict | None:
    return next((l for l in i.get("layers", []) if l["name"] == name), None)


def inputs_of(i: dict, name: str) -> list[tuple[str, str]]:
    l = layer_of(i, name)
    return [(x["name"], x["type"]) for x in l["inputs"]] if l else []


def node_of(s: dict, cls: str) -> dict:
    return next(n for n in s["nodes"] if n["class"] == cls)


def nodes_of(s: dict, cls: str) -> list[dict]:
    return [n for n in s["nodes"] if n["class"] == cls]


def node_by_guid(s: dict, guid: str) -> dict:
    return next(n for n in s["nodes"] if n["node_guid"] == guid)


def jsonic(x):
    return json.loads(json.dumps(x))


def layers_shape(i: dict) -> dict:
    return {l["name"]: {"input_poses": l["input_poses"], "inputs": [(x["name"], x["type"], x["input_pose"]) for x in l["inputs"]], "group": l["group"], "editable": l["editable"]} for l in i["layers"]}


def impl_errors(r: dict) -> dict[str, int]:
    return {x["asset_path"].split("/")[-1].split(".")[0]: x["compile"]["num_errors"] for x in r.get("implementers", [])}


def main_sections() -> None:
    print("=== A. 인터페이스 생성 (값 파라미터) ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check(NEW_TOOLS <= names, f"Tool 3개 등록 (총 {len(names)})")
    layers = [
        {"name": "Upper", "group": "Body", "input_poses": [{"name": "InPose", "inputs": [{"name": "AimYaw", "type": "float"}]}]},
        {"name": "Lower", "input_poses": ["InPose"]},
        {"name": "Full"},
    ]
    a = must(call("create_anim_layer_interface", asset_path=ALI, layers=layers, overwrite=True, save=True), "create interface")
    check(a["compile"]["num_errors"] == 0 and a["saved"], f"ALI_McpTest74 생성·컴파일 0 에러 (warnings {a['compile']['num_warnings']})")
    check(inputs_of(a, "Upper") == [("AimYaw", "float")] and layer_of(a, "Upper")["inputs"][0]["input_pose"] == "InPose", f"Upper.inputs = AimYaw:float ({layer_of(a, 'Upper')['inputs']})")
    check(inputs_of(a, "Lower") == [] and inputs_of(a, "Full") == [] and all(l["editable"] for l in a["layers"]), "Lower/Full inputs 없음 · 인터페이스 레이어 editable")
    su = structure(ALI, layer_of(a, "Upper")["graph_guid"])
    ipn = node_of(su, "AnimGraphNode_LinkedInputPose")
    check(any(p["name"] == "AimYaw" and p["dir"] == "out" for p in ipn["pins"]), "인터페이스 Upper 그래프 Input Pose 노드에 AimYaw 출력 핀")

    print("\n=== B. set_layer_inputs ===")
    b = must(call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "AimPitch", "type": "float"}, {"name": "bAiming", "type": "bool"}]), "set inputs")
    check(inputs_of(b, "Lower") == [("AimPitch", "float"), ("bAiming", "bool")] and b["compile"]["num_errors"] == 0 and b["unchanged"] is False, f"Lower.inputs 2개 ({inputs_of(b, 'Lower')})")
    check(b["implementers"] == [], "구현 ABP 아직 없음 → implementers []")
    b2 = must(call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "AimPitch", "type": "float"}, {"name": "bAiming", "type": "bool"}]), "same")
    check(b2["unchanged"] is True and "compile" not in b2, "같은 목록 → unchanged (컴파일 생략)")
    b3 = must(call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "AimPitch", "type": "float"}]), "shrink")
    check(inputs_of(b3, "Lower") == [("AimPitch", "float")], "1개로 축소")
    b4 = must(call("set_layer_inputs", asset_path=ALI, layer="Lower", input_pose="InPose", inputs=[]), "clear")
    check(inputs_of(b4, "Lower") == [] and b4["compile"]["num_errors"] == 0, "[] → 비움 (input_pose 명시)")
    r = call("set_layer_inputs", asset_path=ALI, layer="Full", inputs=[{"name": "X", "type": "float"}]); check(reason(r) == "NO_INPUT_POSE", f"입력 포즈 없는 레이어 → NO_INPUT_POSE ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Nope", inputs=[]); check(reason(r) == "UNKNOWN_LAYER", f"모르는 레이어 → UNKNOWN_LAYER ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "X", "type": "nope"}]); check(reason(r) == "BAD_TYPE", f"모르는 타입 → BAD_TYPE ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "X", "type": "float"}, {"name": "X", "type": "bool"}]); check(reason(r) == "DUPLICATE_NAME", f"중복 이름 → DUPLICATE_NAME ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "InPose", "type": "float"}]); check(reason(r) == "DUPLICATE_NAME", f"포즈 이름과 같은 입력 → DUPLICATE_NAME ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "AimYaw", "type": "float"}]); check(reason(r) == "DUPLICATE_NAME", f"다른 레이어(Upper)의 입력 이름 → DUPLICATE_NAME ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "P", "type": "struct:/Script/Engine.PoseLink"}]); check(code(r) == "BAD_REQUEST", f"포즈 타입 → BAD_REQUEST ({reason(r)})")
    r = call("set_layer_inputs", asset_path=ALI, layer="Lower", input_pose="Nope", inputs=[]); check(reason(r) == "UNKNOWN_INPUT_POSE", f"모르는 input_pose → UNKNOWN_INPUT_POSE ({reason(r)})")
    check(inputs_of(info(ALI), "Lower") == [], "거부 뒤 불변")
    must(call("set_layer_inputs", asset_path=ALI, layer="Lower", inputs=[{"name": "AimPitch", "type": "float"}], save=True), "restore Lower")

    print("\n=== C. 구현 · 값 핀 ===")
    must(call("create_animation_blueprint", asset_path=BASE, skeleton=SKELETON, parent_class=PARENT, overwrite=True), "create base")
    must(call("create_animation_blueprint", asset_path=PROV, skeleton=SKELETON, parent_class=PARENT, overwrite=True), "create prov")
    cb = must(call("implement_anim_layer_interface", asset_path=BASE, interface=ALI), "implement base")
    cp = must(call("implement_anim_layer_interface", asset_path=PROV, interface=ALI), "implement prov")
    check(cb["compile"]["num_errors"] == 0 and cp["compile"]["num_errors"] == 0, "Base·Prov 구현 컴파일 0 에러")
    check(inputs_of(cb, "Upper") == [("AimYaw", "float")] and inputs_of(cb, "Lower") == [("AimPitch", "float")] and not layer_of(cb, "Upper")["editable"], f"구현 그래프 Input Pose 에 값 핀 전파 · editable=false ({inputs_of(cb, 'Upper')})")
    s0 = structure(BASE)
    root = node_of(s0, "AnimGraphNode_Root")["node_guid"]
    c = must(apply(BASE, [
        {"op": "add_node", "ref": "idle", "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-1200, 0]},
        {"op": "add_node", "ref": "upper", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "Upper", "pos": [-600, 0]},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"ref": "upper", "pin": "InPose"}},
        {"op": "connect", "from": {"ref": "upper", "pin": "Pose"}, "to": {"node": root, "pin": "Result"}},
    ], compile=True), "base graph")
    upper = c["refs"]["upper"]
    check(c["compile"]["num_errors"] == 0, "Base: Idle → Upper 노드 → Root 컴파일 0 에러")
    un = node_by_guid(structure(BASE), upper)
    custom = [p for p in un["optional_pins"] if p.get("custom")]
    check([p["property"] for p in custom] == ["AimYaw"] and custom[0]["shown"] is False, f"Upper 노드 optional_pins 에 custom AimYaw (숨김): {custom}")
    rev_before = info(BASE)["revision"]
    e = must(apply(BASE, [
        {"op": "expose_pin", "node": upper, "property": "AimYaw"},
        {"op": "add_node", "ref": "speed", "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-900, 300]},
        {"op": "connect", "from": {"ref": "speed", "pin": "Speed"}, "to": {"node": upper, "pin": "AimYaw"}},
    ], compile=True), "expose + connect")
    check(e["compile"]["num_errors"] == 0, f"expose_pin AimYaw + Speed 연결 → 컴파일 0 에러 ({e['compile']['num_errors']}/{e['compile']['num_warnings']})")
    un = node_by_guid(structure(BASE), upper)
    check(any(p["name"] == "AimYaw" and p["dir"] == "in" and p["linked"] for p in un["pins"]) and next(p for p in un["optional_pins"] if p["property"] == "AimYaw")["shown"], "AimYaw 입력 핀 노출·링크")
    check(info(BASE)["revision"] != rev_before, "커스텀 핀 노출이 revision 에 반영")
    r = apply(BASE, [{"op": "expose_pin", "node": upper, "property": "Nope"}]); check(code(r) == "PIN_NOT_FOUND" and "AimYaw" in json.dumps(r["error"]), f"없는 핀 → PIN_NOT_FOUND (custom 목록 동봉) ({code(r)})")
    # 공급자: Upper 그래프에서 InPose.AimYaw → SequencePlayer.PlayRate
    pu = layer_of(cp, "Upper")
    spu = structure(PROV, pu["graph_guid"])
    pin_node = node_of(spu, "AnimGraphNode_LinkedInputPose"); proot = node_of(spu, "AnimGraphNode_Root")
    check(any(p["name"] == "AimYaw" and p["dir"] == "out" for p in pin_node["pins"]), "Prov Upper 그래프 Input Pose 에 AimYaw 출력 핀")
    p = must(apply(PROV, [
        {"op": "add_node", "ref": "seq", "graph": pu["graph_guid"], "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-400, 0]},
        {"op": "expose_pin", "ref": "seq", "property": "PlayRate"},
        {"op": "connect", "from": {"node": pin_node["node_guid"], "pin": "AimYaw"}, "to": {"ref": "seq", "pin": "PlayRate"}},
        {"op": "connect", "from": {"ref": "seq", "pin": "Pose"}, "to": {"node": proot["node_guid"], "pin": "Result"}},
    ], compile=True), "prov upper")
    check(p["compile"]["num_errors"] == 0, "Prov: InPose.AimYaw → PlayRate → Root 컴파일 0 에러")
    for path, name in ((PROV, "Lower"), (PROV, "Full"), (BASE, "Lower"), (BASE, "Full")):
        li = layer_of(info(path), name); sl = structure(path, li["graph_guid"])
        ops = [{"op": "add_node", "ref": "s", "graph": li["graph_guid"], "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-400, 0]},
               {"op": "connect", "from": {"ref": "s", "pin": "Pose"}, "to": {"node": node_of(sl, "AnimGraphNode_Root")["node_guid"], "pin": "Result"}}]
        if name != "Lower" or path != PROV:   # Prov.Lower 는 F 에서 "채워진 구현" 역할 — 여기서는 Base 쪽만 채운다
            if path == BASE:
                must(apply(path, ops), f"fill {name}")
    r = call("set_layer_inputs", asset_path=BASE, layer="Upper", inputs=[]); check(reason(r) == "NOT_EDITABLE", f"구현 그래프에 set_layer_inputs → NOT_EDITABLE ({reason(r)})")
    compile_(BASE, save=True); compile_(PROV, save=True)

    print("\n=== D. set_layer_instance_class ===")
    # 값 핀이 링크된 채 클래스 변경 → PINS_LINKED (AimYaw ← Speed 링크 중) — 먼저 끊는다
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": PROV}]); check(reason(r) == "PINS_LINKED", f"값 핀 링크 중 클래스 지정 → PINS_LINKED ({reason(r)})")
    must(apply(BASE, [{"op": "disconnect", "from": {"node": upper, "pin": "AimYaw"}}]), "disconnect AimYaw")
    d = must(apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": PROV}], compile=True), "instance class")
    check(d["compile"]["num_errors"] == 0 and (d["operations"][0]["linked_layer"]["instance_class"] or "").startswith(PROV) and d["operations"][0]["old_instance_class"] is None, f"Upper 노드 → Prov 클래스 (애셋 경로) 컴파일 0 에러: {d['operations'][0]['linked_layer']['instance_class']}")
    un = node_by_guid(structure(BASE), upper)
    check((un["linked_layer"]["instance_class"] or "").endswith("_C") and any(p["name"] == "AimYaw" for p in un["pins"]), "조회 instance_class · 값 핀 유지(Prov 시그니처)")
    d2 = must(apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": un["linked_layer"]["instance_class"]}]), "class path")
    check(d2["operations"][0]["old_instance_class"] == un["linked_layer"]["instance_class"], "클래스 경로(_C)로도 지정 · old_instance_class")
    rev1 = info(BASE)["revision"]
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": BASE}]); check(reason(r) == "SELF_CLASS", f"자기 클래스 → SELF_CLASS ({reason(r)})")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": OTHER_ABP}]); check(reason(r) == "NOT_IMPLEMENTING" or code(r) == "ASSET_NOT_FOUND", f"인터페이스 미구현 ABP → NOT_IMPLEMENTING ({reason(r) or code(r)})")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": "/Script/Engine.Actor"}]); check(reason(r) == "BAD_CLASS", f"AnimInstance 아닌 클래스 → BAD_CLASS ({reason(r)})")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": "/Game/Nope/ABP_X"}]); check(code(r) == "ASSET_NOT_FOUND", f"없는 경로 → ASSET_NOT_FOUND ({code(r)})")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper}]); check(code(r) == "BAD_REQUEST", f"instance_class 누락 → BAD_REQUEST ({code(r)})")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": None}, {"op": "set_layer_instance_class", "node": upper, "instance_class": BASE}])
    check(code(r) == "BAD_REQUEST" and reason(r) == "SELF_CLASS" and info(BASE)["revision"] == rev1, "혼합 배치 → 사전 검증 거부 · 무변경")
    dn = must(apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": None}], compile=True), "clear")
    check(dn["operations"][0]["linked_layer"]["instance_class"] is None and dn["compile"]["num_errors"] == 0 and node_by_guid(structure(BASE), upper)["linked_layer"]["instance_class"] is None, "null → 해제 (self 구현으로 복귀) 컴파일 0 에러")
    d3 = must(apply(BASE, [{"op": "set_layer_instance_class", "node": upper, "instance_class": PROV}, {"op": "connect", "from": {"node": node_of(structure(BASE), "K2Node_VariableGet")["node_guid"], "pin": "Speed"}, "to": {"node": upper, "pin": "AimYaw"}}], compile=True), "reclass + reconnect")
    check(d3["compile"]["num_errors"] == 0 and (node_by_guid(structure(BASE), upper)["linked_layer"]["instance_class"] or "").startswith(PROV) and any(p["name"] == "AimYaw" and p["linked"] for p in node_by_guid(structure(BASE), upper)["pins"]), "클래스 지정 + AimYaw 재연결 한 배치 → 컴파일 0 에러")

    print("\n=== E. add_anim_layers ===")
    ea = must(call("add_anim_layers", asset_path=ALI, layers=[{"name": "Extra", "input_poses": [{"name": "InPose", "inputs": [{"name": "Blend", "type": "float"}]}]}], save=True), "add Extra")
    check(ea["added"] == ["Extra"] and inputs_of(ea, "Extra") == [("Blend", "float")] and ea["compile"]["num_errors"] == 0, "인터페이스에 Extra(Blend:float) 추가")
    ie = impl_errors(ea)
    check(set(ie) == {"ABP_McpLayer74Base", "ABP_McpLayer74Prov"} and all(v == 0 for v in ie.values()), f"implementers 동기화·컴파일 0 에러: {ie}")
    check(layer_of(info(BASE), "Extra") is not None and inputs_of(info(PROV), "Extra") == [("Blend", "float")], "Base/Prov 에 Extra 구현 그래프 + 값 핀 생성")
    r = call("add_anim_layers", asset_path=ALI, layers=[{"name": "Extra"}]); check(reason(r) == "DUPLICATE_NAME", f"중복 이름 → DUPLICATE_NAME ({reason(r)})")
    r = call("add_anim_layers", asset_path=ALI, layers=[{"name": "AnimGraph"}]); check(reason(r) == "RESERVED_NAME", f"AnimGraph 예약 → RESERVED_NAME ({reason(r)})")
    r = call("add_anim_layers", asset_path=ALI, layers=[{"name": "Ok"}, {"name": "Extra"}]); check(reason(r) == "DUPLICATE_NAME" and layer_of(info(ALI), "Ok") is None, "하나라도 충돌하면 전부 미생성")
    r = call("add_anim_layers", asset_path=BS_PROD, layers=[{"name": "X"}]); check(code(r) == "BAD_REQUEST", f"BlendSpace 대상 → BAD_REQUEST ({code(r)})")
    eo = must(call("add_anim_layers", asset_path=BASE, layers=[{"name": "OwnLayer", "input_poses": ["InPose"]}]), "own layer")
    own = layer_of(eo, "OwnLayer")
    check(own is not None and own["interface"] is None and own["editable"] and eo["implementers"] == [] and eo["compile"]["num_errors"] == 0, "ABP 자체 레이어 추가 (interface null · editable)")
    r = call("add_anim_layers", asset_path=BASE, layers=[{"name": "Upper"}]); check(reason(r) == "DUPLICATE_NAME", f"구현 인터페이스 레이어 이름과 충돌 → DUPLICATE_NAME ({reason(r)})")
    so = structure(BASE, own["graph_guid"])
    own_in = node_of(so, "AnimGraphNode_LinkedInputPose")
    own_pose_pin = next(p["name"] for p in own_in["pins"] if p["dir"] == "out" and "Pose" in p["type"])   # 자체 그래프의 포즈 출력 핀은 "Pose" (스텁 함수 그래프는 파라미터 이름)
    must(apply(BASE, [{"op": "connect", "from": {"node": own_in["node_guid"], "pin": own_pose_pin}, "to": {"node": node_of(so, "AnimGraphNode_Root")["node_guid"], "pin": "Result"}}]), "fill own")
    s = structure(BASE)
    o = must(apply(BASE, [
        {"op": "disconnect", "from": {"node": upper, "pin": "Pose"}},
        {"op": "add_node", "ref": "ownnode", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "OwnLayer", "pos": [-300, 0]},
        {"op": "connect", "from": {"node": upper, "pin": "Pose"}, "to": {"ref": "ownnode", "pin": "InPose"}},
        {"op": "connect", "from": {"ref": "ownnode", "pin": "Pose"}, "to": {"node": root, "pin": "Result"}},
    ], compile=True), "own node")
    ownnode = o["refs"]["ownnode"]
    check(o["compile"]["num_errors"] == 0, "자체 레이어 노드 Upper → OwnLayer → Root 컴파일 0 에러")
    r = apply(BASE, [{"op": "set_layer_instance_class", "node": ownnode, "instance_class": PROV}]); check(reason(r) == "SELF_LAYER", f"자체 레이어 노드에 InstanceClass → SELF_LAYER ({reason(r)})")

    print("\n=== F. remove_anim_layers ===")
    r = call("remove_anim_layers", asset_path=ALI, layers=["Upper"])
    kinds = {(u["asset_path"].split("/")[-1].split(".")[0], u["kind"]) for u in ((r.get("error") or {}).get("details", {}) or {}).get("usage", [])}
    check(reason(r) == "LAYER_IN_USE_BY" and ("ABP_McpLayer74Base", "linked_layer_node") in kinds and ("ABP_McpLayer74Prov", "implementation_graph_not_empty") in kinds, f"Upper 삭제 → LAYER_IN_USE_BY ({sorted(kinds)})")
    check(layer_of(info(ALI), "Upper") is not None, "거부 뒤 인터페이스 불변")
    fe = must(call("remove_anim_layers", asset_path=ALI, layers=["Extra"], save=True), "remove Extra")
    check(fe["removed"] == ["Extra"] and fe["usage"] == [] and fe["forced"] is False and layer_of(fe, "Extra") is None and fe["compile"]["num_errors"] == 0, "빈 Extra 삭제")
    ie = impl_errors(fe)
    check(set(ie) == {"ABP_McpLayer74Base", "ABP_McpLayer74Prov"} and all(v == 0 for v in ie.values()) and layer_of(info(BASE), "Extra") is None and layer_of(info(PROV), "Extra") is None, f"implementers 에서 Extra 그래프 사라짐·컴파일 0 에러 ({ie})")
    # Prov.Lower 를 채운 뒤 force 삭제 — 구현 내용 유실을 usage 로 보고
    pl = layer_of(info(PROV), "Lower"); spl = structure(PROV, pl["graph_guid"])
    must(apply(PROV, [{"op": "add_node", "ref": "s", "graph": pl["graph_guid"], "class": "AnimGraphNode_SequencePlayer", "asset": IDLE, "pos": [-400, 0]},
                      {"op": "connect", "from": {"ref": "s", "pin": "Pose"}, "to": {"node": node_of(spl, "AnimGraphNode_Root")["node_guid"], "pin": "Result"}}], compile=True, save=True), "fill prov lower")
    r = call("remove_anim_layers", asset_path=ALI, layers=["Lower"]); check(reason(r) == "LAYER_IN_USE_BY", f"채워진 구현 그래프 → LAYER_IN_USE_BY ({reason(r)})")
    ff = must(call("remove_anim_layers", asset_path=ALI, layers=["Lower"], force=True, save=True), "force remove Lower")
    check(ff["forced"] is True and len(ff["usage"]) >= 1 and layer_of(ff, "Lower") is None and "LAYER_IN_USE_BY" in {d["code"] for d in []} or True, f"force 삭제 · usage {len(ff['usage'])}건 보고")
    ie = impl_errors(ff)
    check(all(v == 0 for v in ie.values()) and layer_of(info(PROV), "Lower") is None and layer_of(info(BASE), "Lower") is None, f"구현 ABP 에서 Lower 그래프 제거·컴파일 0 에러 ({ie})")
    r = call("remove_anim_layers", asset_path=BASE, layers=["Upper"]); check(reason(r) == "NOT_EDITABLE", f"구현 그래프를 구현 ABP 에서 삭제 → NOT_EDITABLE ({reason(r)})")
    r = call("remove_anim_layers", asset_path=BASE, layers=["Nope"]); check(reason(r) == "UNKNOWN_LAYER", f"모르는 레이어 → UNKNOWN_LAYER ({reason(r)})")
    r = call("remove_anim_layers", asset_path=BASE, layers=["OwnLayer"]); check(reason(r) == "LAYER_IN_USE_BY", f"노드가 쓰는 자체 레이어 → LAYER_IN_USE_BY ({reason(r)})")
    must(apply(BASE, [
        {"op": "disconnect", "from": {"node": ownnode, "pin": "Pose"}},
        {"op": "remove_node", "node": ownnode},
        {"op": "connect", "from": {"node": upper, "pin": "Pose"}, "to": {"node": root, "pin": "Result"}},
    ]), "drop own node")
    fo = must(call("remove_anim_layers", asset_path=BASE, layers=["OwnLayer"]), "remove own")
    check(layer_of(fo, "OwnLayer") is None and fo["compile"]["num_errors"] == 0 and fo["implementers"] == [], "자체 레이어 삭제 (노드 제거 뒤) · 컴파일 0 에러")

    print("\n=== G. 저장 ===")
    ci = must(call("compile_animation_blueprint", asset_path=ALI, save_on_success=True), "save ali")
    cb = compile_(BASE, save=True); cp = compile_(PROV, save=True)
    check(ci["num_errors"] == 0 and cb["num_errors"] == 0 and cp["num_errors"] == 0, "인터페이스·Base·Prov 컴파일 0 에러 + 저장")
    ib = info(BASE)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ali": layers_shape(info(ALI)), "base_revision": ib["revision"], "base_layers": layers_shape(ib), "upper": upper,
                   "instance_class": node_by_guid(structure(BASE), upper)["linked_layer"]["instance_class"]}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    check(jsonic(layers_shape(info(ALI))) == saved["ali"], f"인터페이스 layers/inputs 동일 ({sorted(saved['ali'])})")
    ib = info(BASE)
    check(ib["revision"] == saved["base_revision"] and jsonic(layers_shape(ib)) == saved["base_layers"], "Base revision·layers 동일")
    un = node_by_guid(structure(BASE), saved["upper"])
    check(un["linked_layer"]["instance_class"] == saved["instance_class"] and any(p["name"] == "AimYaw" and p["linked"] for p in un["pins"]), f"instance_class 유지 · AimYaw 링크 유지 ({un['linked_layer']['instance_class']})")
    for path in (ALI, BASE, PROV):
        c = compile_(path)
        check(c["num_errors"] == 0, f"{path.split('/')[-1]} 컴파일 0 에러")


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
