"""Phase 6-4b Linked Anim Layer — create_anim_layer_interface · implement_anim_layer_interface · add_node layer · set_linked_layer · 조회.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_4b_test.py [--recheck]

새 Tool 2개는 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출(bridge)로 검증한다.
대상(생성·덮어쓰기): /Game/Animation/Test/ALI_McpTest (인터페이스) · ABP_McpLayerBase (Lyra 의 ABP_Mannequin_Base 역) · ABP_McpLayerProvider (ABP_ItemAnimLayersBase 역).
검사 항목:
  A. 인터페이스 생성 — 레이어 2(FullBody_Idle · UpperBody_Additive[group Body, input InPose]) → BPTYPE_Interface · layers[] · 컴파일 0 에러 · 저장
  B. 구현 — ABP_McpLayerBase 에 구현 → implemented_interfaces 1 · layers 2(interface 설정 · interface_guid) · UpperBody 그래프에 LinkedInputPose "InPose" 자동 생성 · 컴파일 0 에러
  C. 노드 — AnimGraph 에 LinkedAnimLayer(FullBody_Idle) → LinkedAnimLayer(UpperBody_Additive).InPose → Root → 컴파일 0 에러 · linked_layer 조회 · InPose 핀 존재
  D. 레이어 그래프 채우기 — FullBody_Idle: SequencePlayer → Root · UpperBody_Additive: InPose → Root(통과) → 컴파일 0 에러
  E. 공급자 ABP — 같은 인터페이스 구현 + FullBody_Idle 채움 → 컴파일 0 에러 (런타임 LinkAnimClassLayers 대상)
  F. set_linked_layer — upper 노드를 FullBody_Idle 로(InPose 핀 사라짐) → 되돌리기 · 롤백(같은 배치 ref 실패) · old_layer
  G. 거부 — 없는 레이어 · 다른 클래스에 layer · set_linked_layer 를 다른 노드에 · 이미 구현 · 인터페이스가 아닌 애셋 · 인터페이스를 대상으로 · 중복/예약 레이어 이름 · 보호 애셋 overwrite
  H. 저장 → --recheck: 인터페이스 layers · base/provider revision · 컴파일 0 에러
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ALI = "/Game/Animation/Test/ALI_McpTest"
BASE = "/Game/Animation/Test/ABP_McpLayerBase"
PROVIDER = "/Game/Animation/Test/ABP_McpLayerProvider"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
STATE_FILE = "Tools/mcp/phase6_4b_state.json"
LAYERS = [{"name": "FullBody_Idle"}, {"name": "UpperBody_Additive", "group": "Body", "input_poses": ["InPose"]}, {"name": "Extra_Layer"}]
FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:1500]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def code(env: dict) -> str:
    return env.get("error", {}).get("code", "") if not env.get("ok") else "OK"


def reason(env: dict) -> str:
    d = env.get("error", {}).get("details", {}) or {}
    if d.get("reason"):
        return d["reason"]
    # 사전 검증 실패는 details.planned[i].error, 적용 중 실패는 details.cause(= 실패 op 의 details) · details.applied[i].error
    if (d.get("cause") or {}).get("reason"):
        return d["cause"]["reason"]
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        r = (p.get("error") or {}).get("details", {}) or {}
        if r.get("reason"):
            return r["reason"]
    return ""


def info(path: str) -> dict:
    return must(bridge.call("get_anim_blueprint_info", {"asset_path": path}, timeout=bridge.COMPILE_TIMEOUT), f"info {path}")


def structure(path: str, graph: str | None = None, depth: int = 0) -> dict:
    p = {"asset_path": path, "depth": depth}
    if graph:
        p["graph_guid"] = graph
    return must(bridge.call("get_anim_graph_structure", p, timeout=bridge.COMPILE_TIMEOUT), f"structure {path}")


def apply(path: str, ops: list, expected: str | None = None, **kw) -> dict:
    params = {"asset_path": path, "operations": ops, **kw}
    if expected:
        params["expected_revision"] = expected
    return bridge.call("apply_graph_operations", params, timeout=bridge.COMPILE_TIMEOUT)


def compile_(path: str, save: bool = False) -> dict:
    return must(bridge.call("compile_animation_blueprint", {"asset_path": path, "save_on_success": save}, timeout=bridge.COMPILE_TIMEOUT), f"compile {path}")


def layer_of(i: dict, name: str) -> dict | None:
    return next((l for l in i.get("layers", []) if l["name"] == name), None)


def node_of(s: dict, cls: str) -> dict:
    return next(n for n in s["nodes"] if n["class"] == cls)


def nodes_of(s: dict, cls: str) -> list[dict]:
    return [n for n in s["nodes"] if n["class"] == cls]


def main_sections() -> None:
    print("=== A. 인터페이스 생성 ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check({"create_anim_layer_interface", "implement_anim_layer_interface"} <= names, f"Tool 2개 등록 (총 {len(names)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": ALI, "layers": LAYERS, "overwrite": True, "save": True}, timeout=bridge.COMPILE_TIMEOUT)
    a = must(r, "create interface")
    check(a.get("created") and a.get("saved") and a.get("blueprint_type") == "BPTYPE_Interface", f"created · saved · {a.get('blueprint_type')}")
    check(a["compile"].get("num_errors") == 0, f"인터페이스 컴파일 0 에러 (warnings={a['compile'].get('num_warnings')})")
    check(a.get("anim_graph_guid") is None, "인터페이스에는 루트 AnimGraph 없음")
    la = layer_of(a, "FullBody_Idle"); lb = layer_of(a, "UpperBody_Additive")
    # 그룹 기본값은 엔진의 FAnimNode_Root::DefaultSharedGroup ("DefaultSharedGroup", AnimNode_Root.cpp:13)
    check(la is not None and la["interface"] is None and la["input_poses"] == [] and la["group"] == "DefaultSharedGroup", f"FullBody_Idle: {la}")
    check(lb is not None and lb["input_poses"] == ["InPose"] and lb["group"] == "Body", f"UpperBody_Additive: {lb}")
    sb = structure(ALI, lb["graph_guid"])
    check(len(nodes_of(sb, "AnimGraphNode_LinkedInputPose")) == 1 and len(nodes_of(sb, "AnimGraphNode_Root")) == 1, "인터페이스 레이어 그래프: Root 1 · LinkedInputPose 1")

    print("\n=== B. 구현 (ABP_McpLayerBase) ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": BASE, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create base")
    r = bridge.call("implement_anim_layer_interface", {"asset_path": BASE, "interface": ALI}, timeout=bridge.COMPILE_TIMEOUT)
    b = must(r, "implement")
    check(b.get("implemented") and b["compile"].get("num_errors") == 0, f"implemented · 컴파일 0 에러 (warnings={b['compile'].get('num_warnings')})")
    ii = b.get("implemented_interfaces", [])
    check(len(ii) == 1 and ii[0]["blueprint"].startswith(ALI) and len(ii[0]["graphs"]) == 3, f"implemented_interfaces: {ii}")
    bl_full = layer_of(b, "FullBody_Idle"); bl_up = layer_of(b, "UpperBody_Additive")
    check(bl_full is not None and bl_up is not None and bl_full["interface"] and bl_up["interface_guid"] and len(b["layers"]) == 3, "layers 3 · interface · interface_guid")
    check(bl_up["input_poses"] == ["InPose"] and bl_up["group"] == "Body", f"구현 그래프 입력 포즈·그룹 전파: {bl_up}")
    s_up = structure(BASE, bl_up["graph_guid"])
    check(len(nodes_of(s_up, "AnimGraphNode_LinkedInputPose")) == 1 and len(nodes_of(s_up, "AnimGraphNode_Root")) == 1, "구현 그래프: Root + LinkedInputPose 자동 생성 (CreateFunctionGraphTerminators)")
    graphs_by_guid = {g["graph_guid"]: g for g in b["graphs"]}
    check(bl_up["graph_guid"] in graphs_by_guid and graphs_by_guid[bl_up["graph_guid"]]["interface_guid"], "graphs[] 에 인터페이스 그래프 포함 · interface_guid")

    print("\n=== C. LinkedAnimLayer 노드 ===")
    s0 = structure(BASE)
    root = node_of(s0, "AnimGraphNode_Root")
    r = apply(BASE, [
        {"op": "add_node", "ref": "full", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "FullBody_Idle", "pos": [-900, 0]},
        {"op": "add_node", "ref": "upper", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "UpperBody_Additive", "pos": [-450, 0]},
        {"op": "connect", "from": {"ref": "full", "pin": "Pose"}, "to": {"ref": "upper", "pin": "InPose"}},
        {"op": "connect", "from": {"ref": "upper", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ], expected=s0["revision"], compile=True)
    c = must(r, "layer nodes")
    check(c["compile"].get("num_errors") == 0, f"레이어 노드 2 + 연결 → 컴파일 0 에러 (warnings={c['compile'].get('num_warnings')})")
    full, upper = c["refs"]["full"], c["refs"]["upper"]
    check(c["operations"][1].get("linked_layer", {}).get("layer") == "UpperBody_Additive", f"op 응답 linked_layer: {c['operations'][1].get('linked_layer')}")
    s1 = structure(BASE)
    un = next(n for n in s1["nodes"] if n["node_guid"] == upper)
    check(un["linked_layer"]["layer"] == "UpperBody_Additive" and (un["linked_layer"]["interface"] or "").startswith(ALI) and un["linked_layer"]["instance_class"] is None, f"조회 linked_layer: {un['linked_layer']}")
    check(any(p["name"] == "InPose" and p["dir"] == "in" for p in un["pins"]), "upper 노드에 InPose 입력 핀")
    check(info(BASE)["linked_anim_layer_count"] == 2, "linked_anim_layer_count 2")

    print("\n=== D. 레이어 그래프 채우기 ===")
    sf = structure(BASE, bl_full["graph_guid"])
    froot = node_of(sf, "AnimGraphNode_Root")
    r = apply(BASE, [
        {"op": "add_node", "ref": "idle", "graph": bl_full["graph_guid"], "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": IDLE, "properties": {"bLoopAnimation": True}},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"node": froot["node_guid"], "pin": "Result"}},
    ], compile=True)
    check(must(r, "fill full")["compile"].get("num_errors") == 0, "FullBody_Idle 그래프: SequencePlayer → Root 컴파일 0 에러")
    s_up = structure(BASE, bl_up["graph_guid"])
    uroot = node_of(s_up, "AnimGraphNode_Root"); uin = node_of(s_up, "AnimGraphNode_LinkedInputPose")
    in_pin = next(p["name"] for p in uin["pins"] if p["dir"] == "out")
    r = apply(BASE, [{"op": "connect", "from": {"node": uin["node_guid"], "pin": in_pin}, "to": {"node": uroot["node_guid"], "pin": "Result"}}], compile=True)
    check(must(r, "fill upper")["compile"].get("num_errors") == 0, f"UpperBody_Additive 그래프: InPose({in_pin}) → Root 통과 컴파일 0 에러")

    print("\n=== E. 공급자 ABP ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": PROVIDER, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create provider")
    p = must(bridge.call("implement_anim_layer_interface", {"asset_path": PROVIDER, "interface": ALI}, timeout=bridge.COMPILE_TIMEOUT), "implement provider")
    pf = layer_of(p, "FullBody_Idle")
    spf = structure(PROVIDER, pf["graph_guid"])
    r = apply(PROVIDER, [
        {"op": "add_node", "ref": "idle", "graph": pf["graph_guid"], "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": IDLE},
        {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"node": node_of(spf, "AnimGraphNode_Root")["node_guid"], "pin": "Result"}},
    ], compile=True)
    check(must(r, "fill provider")["compile"].get("num_errors") == 0 and p["compile"].get("num_errors") == 0, "공급자: 구현 + FullBody_Idle 채움 → 컴파일 0 에러")

    print("\n=== F. set_linked_layer ===")
    # 엔진 규칙(실측): ① 링크된 입력 포즈 핀은 재구성 뒤 고아로 남아 컴파일 오류 → 먼저 끊어야 한다 ② 한 레이어는 ABP 당 노드 하나만 쓸 수 있다
    s2 = structure(BASE)
    r = apply(BASE, [{"op": "set_linked_layer", "node": upper, "layer": "Extra_Layer"}], expected=s2["revision"])
    check(code(r) == "BAD_REQUEST" and reason(r) == "PINS_LINKED", f"InPose 링크 중 재지정 → PINS_LINKED ({code(r)}/{reason(r)})")
    must(apply(BASE, [{"op": "disconnect", "from": {"node": full, "pin": "Pose"}, "to": {"node": upper, "pin": "InPose"}}], expected=s2["revision"]), "unlink")
    s2b = structure(BASE)
    r = apply(BASE, [{"op": "set_linked_layer", "node": upper, "layer": "Extra_Layer"}], expected=s2b["revision"], compile=True)
    f = must(r, "retarget")
    check(f["operations"][0].get("old_layer") == "UpperBody_Additive" and f["compile"].get("num_errors") == 0, f"upper → Extra_Layer (old_layer 보고 · 컴파일 0 에러, warnings={f['compile'].get('num_warnings')})")
    s3 = structure(BASE)
    un3 = next(n for n in s3["nodes"] if n["node_guid"] == upper)
    check(un3["linked_layer"]["layer"] == "Extra_Layer" and not any(p["name"] == "InPose" for p in un3["pins"]), "InPose 핀 사라짐")
    check(s3["revision"] != s2b["revision"], "revision 변경")
    must(apply(BASE, [{"op": "set_linked_layer", "node": upper, "layer": "UpperBody_Additive"}], expected=s3["revision"]), "retarget back")
    s4 = structure(BASE)
    un4 = next(n for n in s4["nodes"] if n["node_guid"] == upper)
    check(any(p["name"] == "InPose" for p in un4["pins"]), "되돌리면 InPose 핀 복귀")
    must(apply(BASE, [{"op": "connect", "from": {"node": full, "pin": "Pose"}, "to": {"node": upper, "pin": "InPose"}}], expected=s4["revision"], compile=True), "relink")
    # 롤백 — 링크를 끊은 상태에서 재지정 + 같은 배치 ref 실패 op
    must(apply(BASE, [{"op": "disconnect", "from": {"node": full, "pin": "Pose"}, "to": {"node": upper, "pin": "InPose"}}]), "unlink 2")
    s5 = structure(BASE)
    bad = apply(BASE, [
        {"op": "set_linked_layer", "node": upper, "layer": "Extra_Layer"},
        {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 600]},
        {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ], expected=s5["revision"])
    det = bad.get("error", {}).get("details", {})
    check(not bad.get("ok") and det.get("failed_index") == 2 and det.get("rollback_verified") is True, f"set_linked_layer + 실패 op → rollback_verified ({det.get('rollback_verified')})")
    s6 = structure(BASE)
    un6 = next(n for n in s6["nodes"] if n["node_guid"] == upper)
    check(un6["linked_layer"]["layer"] == "UpperBody_Additive" and s6["revision"] == s5["revision"], "롤백 뒤 레이어·revision 복원")
    must(apply(BASE, [{"op": "connect", "from": {"node": full, "pin": "Pose"}, "to": {"node": upper, "pin": "InPose"}}], expected=s6["revision"]), "relink 2")
    s6b = structure(BASE)
    # 같은 배치 ref 에 set_linked_layer (pending)
    r = apply(BASE, [
        {"op": "add_node", "ref": "l3", "class": "AnimGraphNode_LinkedAnimLayer", "pos": [-900, 400]},
        {"op": "set_linked_layer", "ref": "l3", "layer": "Extra_Layer"},
        {"op": "remove_node", "ref": "l3"},
    ], expected=s6b["revision"])
    check(r.get("ok"), f"같은 배치 ref 에 set_linked_layer 뒤 제거 ({code(r)})")

    print("\n=== G. 거부 ===")
    r = apply(BASE, [{"op": "add_node", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "NoSuchLayer"}]); check(code(r) == "BAD_REQUEST" and reason(r) == "UNKNOWN_LAYER", f"없는 레이어 → UNKNOWN_LAYER ({code(r)}/{reason(r)})")
    r = apply(BASE, [{"op": "add_node", "class": "AnimGraphNode_SequencePlayer", "layer": "FullBody_Idle"}]); check(code(r) == "BAD_REQUEST", f"다른 클래스에 layer → BAD_REQUEST ({code(r)})")
    r = apply(BASE, [{"op": "set_linked_layer", "node": root["node_guid"], "layer": "FullBody_Idle"}]); check(code(r) == "BAD_REQUEST", f"Root 에 set_linked_layer → BAD_REQUEST ({code(r)})")
    r = apply(BASE, [{"op": "set_linked_layer", "node": upper, "layer": "AnimGraph"}]); check(code(r) == "BAD_REQUEST", f"AnimGraph 를 레이어로 → BAD_REQUEST ({code(r)})")
    r = apply(BASE, [{"op": "add_node", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "FullBody_Idle"}]); check(code(r) == "BAD_REQUEST" and reason(r) == "LAYER_IN_USE", f"이미 쓰는 레이어로 add_node → LAYER_IN_USE ({code(r)}/{reason(r)})")
    r = apply(BASE, [{"op": "set_linked_layer", "node": upper, "layer": "FullBody_Idle"}]); check(code(r) == "BAD_REQUEST" and reason(r) == "LAYER_IN_USE", f"이미 쓰는 레이어로 재지정 → LAYER_IN_USE ({code(r)}/{reason(r)})")
    r = bridge.call("implement_anim_layer_interface", {"asset_path": BASE, "interface": ALI}); check(code(r) == "BAD_REQUEST" and reason(r) == "ALREADY_IMPLEMENTED", f"이미 구현 → ALREADY_IMPLEMENTED ({code(r)}/{reason(r)})")
    r = bridge.call("implement_anim_layer_interface", {"asset_path": BASE, "interface": PROVIDER}); check(code(r) == "BAD_REQUEST" and reason(r) == "NOT_LAYER_INTERFACE", f"인터페이스가 아닌 애셋 → NOT_LAYER_INTERFACE ({code(r)}/{reason(r)})")
    r = bridge.call("implement_anim_layer_interface", {"asset_path": ALI, "interface": ALI}); check(code(r) == "BAD_REQUEST", f"인터페이스를 대상으로 → BAD_REQUEST ({code(r)}/{reason(r)})")
    r = bridge.call("implement_anim_layer_interface", {"asset_path": BASE, "interface": "/Game/Animation/Test/ALI_Nope"}); check(code(r) == "ASSET_NOT_FOUND", f"없는 인터페이스 → ASSET_NOT_FOUND ({code(r)})")
    probe = "/Game/Animation/Test/ALI_McpProbe"
    r = bridge.call("create_anim_layer_interface", {"asset_path": probe, "layers": [{"name": "A"}, {"name": "A"}]}); check(code(r) == "BAD_REQUEST" and reason(r) == "DUPLICATE_NAME", f"중복 레이어 이름 → DUPLICATE_NAME ({code(r)}/{reason(r)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": probe, "layers": [{"name": "AnimGraph"}]}); check(code(r) == "BAD_REQUEST" and reason(r) == "RESERVED_NAME", f"AnimGraph 예약 이름 → RESERVED_NAME ({code(r)}/{reason(r)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": probe, "layers": [{"name": "Bad Name!"}]}); check(code(r) == "BAD_REQUEST" and reason(r) == "INVALID_NAME", f"잘못된 이름 → INVALID_NAME ({code(r)}/{reason(r)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": probe, "layers": []}); check(code(r) == "BAD_REQUEST", f"빈 layers → BAD_REQUEST ({code(r)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": ALI, "layers": LAYERS}); check(code(r) == "ASSET_EXISTS", f"overwrite 없이 재생성 → ASSET_EXISTS ({code(r)})")
    r = bridge.call("create_anim_layer_interface", {"asset_path": PROD, "layers": LAYERS, "overwrite": True}); check(code(r) == "ASSET_PROTECTED", f"운영 애셋 overwrite → ASSET_PROTECTED ({code(r)})")
    check(not bridge.call("get_anim_blueprint_info", {"asset_path": probe}).get("ok"), "거부된 생성은 애셋을 남기지 않음")

    print("\n=== H. 저장 ===")
    for path in (BASE, PROVIDER):
        c = compile_(path, save=True)
        check(c.get("num_errors") == 0 and c.get("saved"), f"{path.rsplit('/', 1)[1]} 최종 컴파일 0 에러 · 저장")
    must(bridge.call("save_animation_blueprint", {"asset_path": ALI}), "save ali")
    ia = info(ALI)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ali_layers": ia["layers"], "ali_revision": ia["revision"],
                   "base_revision": info(BASE)["revision"], "provider_revision": info(PROVIDER)["revision"], "upper": upper}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    ia = info(ALI)
    check(ia["layers"] == saved["ali_layers"] and ia["revision"] == saved["ali_revision"], "인터페이스 layers·revision 동일")
    ib = info(BASE)
    check(ib["revision"] == saved["base_revision"] and len(ib["implemented_interfaces"]) == 1 and ib["linked_anim_layer_count"] == 2, f"base revision·구현·레이어 노드 동일 ({ib['revision']})")
    check(info(PROVIDER)["revision"] == saved["provider_revision"], "provider revision 동일")
    s = structure(BASE)
    un = next(n for n in s["nodes"] if n["node_guid"] == saved["upper"])
    check(un["linked_layer"]["layer"] == "UpperBody_Additive" and any(p["name"] == "InPose" for p in un["pins"]), "upper 노드 레이어·InPose 핀 유지")
    for path in (BASE, PROVIDER):
        check(compile_(path).get("num_errors") == 0, f"{path.rsplit('/', 1)[1]} 컴파일 0 에러")


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
