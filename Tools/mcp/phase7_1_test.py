"""Phase 7-1 — BP 변수 · 규칙 AST access/param · set_update_function(BlueprintThreadSafeUpdateAnimation 재생성).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_1_test.py [--recheck]

새 Tool 3개는 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출(bridge)로 검증한다. 대상(생성·덮어쓰기): /Game/Animation/Test/ABP_McpVarTest.
검사 항목:
  A. 변수 추가 — float·bool·vector·object:Actor·int(기본값·카테고리) → variables[] source=blueprint · declaration · 컴파일 0 에러 · revision 변화
  B. 변수 거부 — 중복 · 네이티브 이름(Speed) · 잘못된 타입 · 잘못된 기본값 · 점 포함 이름 · 네이티브 삭제 · 없는 변수 삭제
  C. access 경로 탐색 + 규칙 — 상태머신 전이 규칙에 {"call": VSize(access <vector path>)} > 20 · {"access": "GetDeltaSeconds"} · 컴파일 0 에러 · rule_source 복원 · param 은 규칙에서 거부
  D. set_update_function — 대입 4개(VSize(access) · compare(var) · access vector · param DeltaTime) → 컴파일 0 에러·경고 0 · update_function 조회 · 멱등(unchanged) · 스펙 변경 → 재생성 · 거부 7종
  E. 변수 삭제 — 사용 중 VARIABLE_IN_USE → force 삭제(노드 제거 · update_function.modified) → 재적용
  F. 저장 → --recheck: 변수 선언 · update_function source 동일 · 컴파일 0 에러
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpVarTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
STATE_FILE = "Tools/mcp/phase7_1_state.json"
# 벡터를 돌려주는 Property Access 경로 후보 — 에디터에서 첫 번째로 해석되는 것을 쓴다 (프로젝트의 AnimInstance 에 폰 참조 프로퍼티가 없다)
VECTOR_PATH_CANDIDATES = ["GetOwningComponent.ComponentVelocity", "TryGetPawnOwner.GetVelocity", "GetOwningActor.GetVelocity", "GetOwningComponent.GetComponentVelocity"]
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
    if (d.get("cause") or {}).get("reason"):
        return d["cause"]["reason"]
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        r = (p.get("error") or {}).get("details", {}) or {}
        if r.get("reason"):
            return r["reason"]
    return ""


def msg(env: dict) -> str:
    """오류 메시지 — 배치 사전 검증 실패는 details.planned[i].error.message, 적용 중 실패는 details.cause.message 에 있다."""
    err = env.get("error", {}) or {}
    d = err.get("details", {}) or {}
    for p in (d.get("planned", []) or []) + (d.get("applied", []) or []):
        if (p.get("error") or {}).get("message"):
            return p["error"]["message"][:200]
    if (d.get("cause") or {}).get("message"):
        return d["cause"]["message"][:200]
    return err.get("message", "")[:200]


def info(path: str = ABP) -> dict:
    return must(bridge.call("get_anim_blueprint_info", {"asset_path": path}, timeout=bridge.COMPILE_TIMEOUT), f"info {path}")


def structure(path: str = ABP, graph: str | None = None, depth: int = 0) -> dict:
    p = {"asset_path": path, "depth": depth}
    if graph:
        p["graph_guid"] = graph
    return must(bridge.call("get_anim_graph_structure", p, timeout=bridge.COMPILE_TIMEOUT), f"structure {path}")


def apply(ops: list, **kw) -> dict:
    return bridge.call("apply_graph_operations", {"asset_path": ABP, "operations": ops, **kw}, timeout=bridge.COMPILE_TIMEOUT)


def preview(ops: list) -> dict:
    return bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops}, timeout=bridge.COMPILE_TIMEOUT)


def compile_(save: bool = False) -> dict:
    return must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": save}, timeout=bridge.COMPILE_TIMEOUT), "compile")


def add_var(name: str, type_: str, **kw) -> dict:
    return bridge.call("add_blueprint_variable", {"asset_path": ABP, "name": name, "type": type_, **kw}, timeout=bridge.COMPILE_TIMEOUT)


def remove_var(name: str, **kw) -> dict:
    return bridge.call("remove_blueprint_variable", {"asset_path": ABP, "name": name, **kw}, timeout=bridge.COMPILE_TIMEOUT)


def set_update(assignments: list | None = None, **kw) -> dict:
    p = {"asset_path": ABP, **kw}
    if assignments is not None:
        p["assignments"] = assignments
    return bridge.call("set_update_function", p, timeout=bridge.COMPILE_TIMEOUT)


def var_of(i: dict, name: str) -> dict | None:
    return next((v for v in i["variables"] if v["name"] == name), None)


def vsize(path: str) -> dict:
    return {"call": {"function": "VSize", "args": {"A": {"access": path}}}}


def main_sections() -> None:
    print("=== A. 변수 추가 ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check({"add_blueprint_variable", "remove_blueprint_variable", "set_update_function"} <= names, f"Tool 3개 등록 (총 {len(names)})")
    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    rev0 = info()["revision"]
    a = must(add_var("McpSpeed", "float", default="0.5", category="Mcp"), "add McpSpeed")
    v = var_of(a, "McpSpeed")
    check(a.get("added") == "McpSpeed" and v and v["source"] == "blueprint" and v["pin_category"] == "real" and (v.get("declaration") or {}).get("default_value") == "0.5" and v["declaration"]["category"] == "Mcp", f"McpSpeed float 기본 0.5 카테고리 Mcp → variables[] {v and v.get('declaration')}")
    must(add_var("bMcpFalling", "bool", default="false"), "add bool")
    must(add_var("McpVelocity", "vector"), "add vector")
    must(add_var("McpTarget", "object:/Script/Engine.Actor"), "add object")
    must(add_var("McpCount", "int", default="3", instance_editable=True), "add int")
    must(add_var("McpDelta", "float"), "add McpDelta")
    i = info()
    check(all(var_of(i, n) and var_of(i, n)["source"] == "blueprint" for n in ("McpSpeed", "bMcpFalling", "McpVelocity", "McpTarget", "McpCount", "McpDelta")), "변수 6개 모두 source=blueprint")
    check(var_of(i, "McpVelocity")["declaration"]["type"] == "vector" and var_of(i, "McpTarget")["declaration"]["type"].startswith("object:") and var_of(i, "McpCount")["declaration"]["instance_editable"] is True, "declaration type/instance_editable")
    check(var_of(i, "Speed")["source"] == "native" and var_of(i, "Speed").get("declaration") is None, "네이티브 변수는 declaration null")
    check(i["revision"] != rev0, "변수 추가로 revision 변화")
    c = compile_()
    check(c["num_errors"] == 0, f"컴파일 0 에러 ({c['num_errors']}/{c['num_warnings']})")

    print("\n=== B. 변수 거부 ===")
    r = add_var("McpSpeed", "float"); check(code(r) == "BAD_REQUEST" and reason(r) == "VARIABLE_EXISTS", f"중복 이름 → VARIABLE_EXISTS ({reason(r)})")
    r = add_var("Speed", "float"); check(code(r) == "BAD_REQUEST" and reason(r) == "VARIABLE_EXISTS", f"네이티브 이름 → VARIABLE_EXISTS ({reason(r)})")
    r = add_var("McpBad", "quaternion"); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_TYPE", f"잘못된 타입 → BAD_TYPE ({reason(r)})")
    r = add_var("McpBad", "object:/Script/Engine.NoSuchClass"); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_TYPE", f"없는 클래스 → BAD_TYPE ({reason(r)})")
    r = add_var("McpBad", "bool", default="maybe"); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_DEFAULT", f"bool 기본값 maybe → BAD_DEFAULT ({reason(r)})")
    r = add_var("McpBad", "int", default="abc"); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_DEFAULT", f"int 기본값 abc → BAD_DEFAULT ({reason(r)})")
    r = add_var("Mcp.Bad", "bool"); check(code(r) == "BAD_REQUEST" and reason(r) == "BAD_NAME", f"점 포함 이름 → BAD_NAME ({reason(r)})")
    r = add_var("", "bool"); check(code(r) == "BAD_REQUEST", f"빈 이름 → BAD_REQUEST ({reason(r)})")
    r = remove_var("Speed"); check(code(r) == "BAD_REQUEST" and reason(r) == "NOT_BLUEPRINT_VARIABLE", f"네이티브 삭제 → NOT_BLUEPRINT_VARIABLE ({reason(r)})")
    r = remove_var("McpNope"); check(code(r) == "BAD_REQUEST" and reason(r) == "NOT_BLUEPRINT_VARIABLE", f"없는 변수 삭제 → NOT_BLUEPRINT_VARIABLE ({reason(r)})")
    check(len(info()["variables"]) == len(i["variables"]), "거부 뒤 변수 수 불변")

    print("\n=== C. access 경로 탐색 + 규칙 ===")
    s = structure()
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    base = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-400, 0]},
        {"op": "add_state", "ref": "idle", "sm": {"ref": "sm"}, "name": "Idle", "pos": [0, 0]},
        {"op": "add_state", "ref": "move", "sm": {"ref": "sm"}, "name": "Move", "pos": [400, 0]},
        {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}},
        {"op": "add_node", "ref": "seq1", "graph": {"ref": "idle"}, "class": "AnimGraphNode_SequencePlayer", "asset": IDLE},
        {"op": "connect", "from": {"ref": "seq1", "pin": "Pose"}, "to": {"result_of": {"ref": "idle"}, "pin": "Result"}},
        {"op": "add_node", "ref": "seq2", "graph": {"ref": "move"}, "class": "AnimGraphNode_SequencePlayer", "asset": IDLE},
        {"op": "connect", "from": {"ref": "seq2", "pin": "Pose"}, "to": {"result_of": {"ref": "move"}, "pin": "Result"}},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]
    vector_path = None
    tried = {}
    for cand in VECTOR_PATH_CANDIDATES:
        p = preview(base + [{"op": "add_transition", "ref": "t", "from": {"ref": "idle"}, "to": {"ref": "move"}, "rule": {"compare": {"op": ">", "left": vsize(cand), "right": {"literal": 20.0}}}}])
        tried[cand] = "valid" if p.get("ok") and p["result"].get("valid") else f"{code(p)}/{reason(p)}"
        if tried[cand] == "valid":
            vector_path = cand
            break
    print(f"   vector path probe: {json.dumps(tried, ensure_ascii=False)}")
    check(vector_path is not None, f"벡터 access 경로 해석 성공: {vector_path}")
    if vector_path is None:
        vector_path = VECTOR_PATH_CANDIDATES[0]
    r = apply(base + [
        {"op": "add_transition", "ref": "t1", "from": {"ref": "idle"}, "to": {"ref": "move"}, "rule": {"compare": {"op": ">", "left": vsize(vector_path), "right": {"literal": 20.0}}}},
        {"op": "add_transition", "ref": "t2", "from": {"ref": "move"}, "to": {"ref": "idle"}, "rule": {"compare": {"op": "<", "left": {"access": "GetDeltaSeconds"}, "right": {"literal": 100.0}}}},
    ], compile=True)
    a = must(r, "apply sm + access rules")
    check(a["compile"]["num_errors"] == 0, f"access 규칙 2개 컴파일 0 에러 ({a['compile']['num_errors']}/{a['compile']['num_warnings']})")
    for m in a["compile"].get("messages", []):
        if m["level"] != "info":
            print(f"   compile[{m['level']}] {m['text'][:160]}")
    sm = structure(depth=-1)["state_machines"][0]
    t1 = next(t for t in sm["transitions"] if t["from_name"] == "Idle")
    check(t1["rule_generated"] and not t1["rule_modified"] and (t1["rule_source"] or {}).get("compare", {}).get("left", {}).get("call", {}).get("args", {}).get("A", {}).get("access") == vector_path.split("."), f"rule_source 에 access 경로 복원: {t1['rule_source']}")
    r = apply([{"op": "set_transition_rule", "node": t1["node_guid"], "rule": {"compare": {"op": ">", "left": {"param": "DeltaTime"}, "right": {"literal": 0.0}}}}])
    check(code(r) == "BAD_REQUEST" and "param" in msg(r), f"규칙에 param → BAD_REQUEST ({msg(r)})")
    r = apply([{"op": "set_transition_rule", "node": t1["node_guid"], "rule": {"compare": {"op": ">", "left": {"access": "NoSuch.Path"}, "right": {"literal": 0.0}}}}])
    check(code(r) == "BAD_REQUEST" and reason(r) == "PATH_UNRESOLVED", f"없는 access 경로 → PATH_UNRESOLVED ({reason(r)})")
    r = apply([{"op": "set_transition_rule", "node": t1["node_guid"], "rule": {"compare": {"op": ">", "left": {"access": vector_path}, "right": {"literal": 0.0}}}}])
    check(code(r) == "BAD_REQUEST" and "not supported for other" in msg(r), f"벡터 직접 비교 → 거부 ({msg(r)})")

    print("\n=== D. set_update_function ===")
    spec = [
        {"variable": "McpVelocity", "value": {"access": vector_path}},
        {"variable": "McpSpeed", "value": vsize(vector_path)},
        {"variable": "bMcpFalling", "value": {"compare": {"op": ">", "left": {"var": "McpSpeed"}, "right": {"literal": 1.0}}}},
        {"variable": "McpDelta", "value": {"param": "DeltaTime"}},
    ]
    u = must(set_update(spec, compile=True), "set_update_function")
    ap = u["applied"]
    check(ap.get("created_graph") and not ap.get("unchanged") and ap["assignment_count"] == 4, f"함수 그래프 생성 · 대입 4 · 노드 {ap['node_count']}")
    check(u["compile"]["num_errors"] == 0 and u["compile"]["num_warnings"] == 0, f"컴파일 0 에러 · 0 경고(스레드 안전) ({u['compile']['num_errors']}/{u['compile']['num_warnings']})")
    for m in u["compile"].get("messages", []):
        if m["level"] != "info":
            print(f"   compile[{m['level']}] {m['text'][:200]}")
    uf = u["update_function"]
    check(uf and uf["generated"] and not uf["modified"] and len(uf["assignments"]) == 4 and uf["assignments"][3]["value"] == {"param": "DeltaTime"} and uf["function"] == "BlueprintThreadSafeUpdateAnimation", f"update_function 조회: {json.dumps(uf, ensure_ascii=False)[:300]}")
    g = structure(graph=uf["graph_guid"])
    classes = sorted({n["class"] for n in g["nodes"]})
    check("K2Node_FunctionEntry" in classes and "K2Node_VariableSet" in classes and "K2Node_PropertyAccess" in classes and "K2Node_CallFunction" in classes, f"함수 그래프 노드 클래스 {classes}")
    sets = [n for n in g["nodes"] if n["class"] == "K2Node_VariableSet"]
    check(len(sets) == 4, f"VariableSet 4개")
    u2 = must(set_update(spec), "re-apply")
    check(u2["applied"].get("unchanged") is True, "같은 스펙 재적용 → unchanged")
    u3 = must(set_update(spec[:2]), "shrink")
    check(not u3["applied"].get("unchanged") and u3["applied"]["assignment_count"] == 2 and u3["update_function"]["node_count"] < uf["node_count"] and u3["compile"]["num_errors"] == 0, f"스펙 변경 → 재생성 (노드 {uf['node_count']} → {u3['update_function']['node_count']})")
    u4 = must(set_update(spec), "restore 4")
    check(u4["applied"]["assignment_count"] == 4 and u4["compile"]["num_errors"] == 0, "4개로 복원")
    r = set_update([{"variable": "Speed", "value": {"literal": 1.0}}]); check(code(r) == "BAD_REQUEST" and reason(r) == "READ_ONLY", f"BlueprintReadOnly 대입 → READ_ONLY ({reason(r)})")
    r = set_update([{"variable": "McpSpeed", "value": {"literal": 1.0}}, {"variable": "McpSpeed", "value": {"literal": 2.0}}]); check(code(r) == "BAD_REQUEST" and reason(r) == "DUPLICATE_VARIABLE", f"중복 대입 → DUPLICATE_VARIABLE ({reason(r)})")
    r = set_update([{"variable": "bMcpFalling", "value": {"access": vector_path}}]); check(code(r) == "BAD_REQUEST" and reason(r) == "TYPE_INCOMPATIBLE", f"bool ← vector → TYPE_INCOMPATIBLE ({reason(r)})")
    r = set_update([{"variable": "McpSpeed", "value": {"param": "Nope"}}]); check(code(r) == "BAD_REQUEST" and "param 'Nope'" in msg(r), f"없는 param → BAD_REQUEST ({msg(r)})")
    r = set_update([{"variable": "McpNope", "value": {"literal": 1.0}}]); check(code(r) == "BAD_REQUEST" and "McpNope" in msg(r), f"없는 변수 → BAD_REQUEST ({msg(r)})")
    r = set_update([{"variable": "McpVelocity", "value": {"literal": 1.0}}]); check(code(r) == "BAD_REQUEST" and "literal" in msg(r), f"vector ← literal → BAD_REQUEST ({msg(r)})")
    r = set_update(); r = bridge.call("set_update_function", {"asset_path": ABP}); check(code(r) == "BAD_REQUEST" and reason(r) == "NO_ASSIGNMENTS", f"assignments 누락 → NO_ASSIGNMENTS ({reason(r)})")
    u5 = must(set_update(spec), "verify unchanged after rejects")
    check(u5["applied"].get("unchanged") is True and not u5["update_function"]["modified"], "거부 뒤 함수 그래프 무변경")

    print("\n=== E. 변수 삭제 ===")
    r = remove_var("McpDelta"); check(code(r) == "BAD_REQUEST" and reason(r) == "VARIABLE_IN_USE", f"사용 중 삭제 → VARIABLE_IN_USE ({reason(r)})")
    d = must(remove_var("McpDelta", force=True), "force remove")
    check(d.get("removed") == "McpDelta" and d.get("was_used") is True and var_of(d, "McpDelta") is None, "force 삭제 → removed · was_used · 변수 사라짐")
    check(d["update_function"]["modified"] is True, "생성 함수가 modified=true (노드 제거됨)")
    u6 = must(set_update(spec[:3]), "re-apply without McpDelta")
    check(not u6["applied"].get("unchanged") and u6["compile"]["num_errors"] == 0 and not u6["update_function"]["modified"], "나머지 3개로 재생성 → 컴파일 0 에러 · modified=false")
    d2 = must(remove_var("McpTarget"), "remove unused")
    check(d2.get("was_used") is False and var_of(d2, "McpTarget") is None, "미사용 변수 삭제")

    print("\n=== F. 저장 ===")
    c = compile_(save=True)
    check(c["num_errors"] == 0, "컴파일 0 에러 + 저장")
    i = info()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"revision": i["revision"], "variables": sorted(v["name"] for v in i["variables"] if v["source"] == "blueprint"),
                   "update_source": i["update_function"]["source"], "vector_path": vector_path}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    i = info()
    check(sorted(v["name"] for v in i["variables"] if v["source"] == "blueprint") == saved["variables"], f"BP 변수 유지 {saved['variables']}")
    check(i["revision"] == saved["revision"], "revision 동일")
    uf = i["update_function"]
    check(uf and uf["generated"] and not uf["modified"] and uf["source"] == saved["update_source"], "update_function source 동일 · modified=false")
    c = compile_()
    check(c["num_errors"] == 0 and c["num_warnings"] == 0, f"컴파일 0 에러 · 0 경고 ({c['num_errors']}/{c['num_warnings']})")
    u = must(set_update([{"variable": a["variable"], "value": a["value"]} for a in uf["assignments"]]), "re-apply same")
    check(u["applied"].get("unchanged") is True, "재시작 뒤 같은 스펙 → unchanged")


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
