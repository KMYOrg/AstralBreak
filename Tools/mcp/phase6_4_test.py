"""Phase 6-4a Property Binding — bind_pin · unbind_pin op · optional_pins[].binding 조회 · revision 반영 · 롤백.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_4_test.py [--recheck]

op 추가라 Tool 은 그대로(12/13개) — 세션 재시작 없이 MCP 에서도 바로 쓸 수 있다. 테스트는 HTTP 직접 호출.
대상: /Game/Animation/Test/ABP_McpBindTest (덮어쓰기) — BlendSpacePlayer(BS_McpTest, phase6-3 산출물) 의 X 핀을 Speed 에 묶는다.
검사 항목:
  A. bind — X ← ["Speed"] (VariableGet 없이) → 컴파일 0 에러 · optional_pins[X].bound=true · binding.path/type=Property · 핀 노출됨 · revision 변경
  B. 재바인딩 — 점 경로 "GroundDistance" 로 교체(replaced) · 함수 경로 ["GetDeltaSeconds"] → type=Function
  C. unbind — bound=false · revision 이 A 이전과 같음(핀 노출은 유지되므로 '노출 전' 과는 다름 → expose 상태 기준 비교)
  D. 롤백 — bind + 실패 op → rollback_verified · bound=false · revision 복원 / unbind + 실패 op → 바인딩 복원
  E. 거부 — 없는 핀 프로퍼티 · 해석 안 되는 경로 · 타입 비호환 · 핀 링크 중 · AnimGraph 노드 아님(VariableGet) · unbind 미바인딩 · path 누락
  F. 저장 → --recheck: 재시작 뒤 bound·path·revision 동일 · 컴파일 0 에러
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

ABP = "/Game/Animation/Test/ABP_McpBindTest"
BS = "/Game/Animation/Test/BS_McpTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = "Tools/mcp/phase6_4_state.json"
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
    """오류 details.reason — 사전 검증 실패는 details.planned[i].error.details.reason 에 중첩된다"""
    d = env.get("error", {}).get("details", {}) or {}
    if d.get("reason"):
        return d["reason"]
    for p in d.get("planned", []) or []:
        r = (p.get("error") or {}).get("details", {}) or {}
        if r.get("reason"):
            return r["reason"]
    return ""


def structure() -> dict:
    return must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}, timeout=bridge.COMPILE_TIMEOUT), "structure")


def apply(ops: list, expected: str | None = None, **kw) -> dict:
    params = {"asset_path": ABP, "operations": ops, **kw}
    if expected:
        params["expected_revision"] = expected
    return bridge.call("apply_graph_operations", params, timeout=bridge.COMPILE_TIMEOUT)


def preview(ops: list) -> dict:
    return bridge.call("preview_graph_operations", {"asset_path": ABP, "operations": ops})


def node_of(s: dict, cls: str) -> dict:
    return next(n for n in s["nodes"] if n["class"] == cls)


def pin_x(s: dict) -> dict:
    return next(p for p in node_of(s, "AnimGraphNode_BlendSpacePlayer")["optional_pins"] if p["property"] == "X")


def main_sections() -> None:
    print("=== 준비: ABP + BlendSpacePlayer ===")
    must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create")
    s0 = structure()
    root = node_of(s0, "AnimGraphNode_Root")
    r = must(apply([
        {"op": "add_node", "ref": "bs", "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 0], "asset": BS},
        {"op": "connect", "from": {"ref": "bs", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ], expected=s0["revision"], compile=True), "setup")
    bs = r["refs"]["bs"]
    s1 = structure()
    px = pin_x(s1)
    print(f"   X pin before: shown={px['shown']} bound={px['bound']}")
    rev_setup = s1["revision"]

    print("\n=== A. bind X ← Speed ===")
    pv = preview([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}])
    check(pv.get("ok") and pv["result"]["valid"], "preview valid")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}], expected=rev_setup, compile=True)
    a = must(r, "bind")
    op0 = a["operations"][0]
    check(a["compile"].get("num_errors") == 0, f"컴파일 0 에러 (warnings={a['compile'].get('num_warnings')})")
    check(op0.get("type") == "Property" and op0.get("replaced") is False and op0.get("pin_exposed") is (not px["shown"]), f"op 결과 type/replaced/pin_exposed: {op0}")
    s2 = structure()
    px2 = pin_x(s2)
    check(px2["bound"] and px2["shown"] and px2.get("binding", {}).get("path") == ["Speed"] and px2["binding"]["type"] == "Property", f"optional_pins[X] bound · path Speed: {px2.get('binding')}")
    check(node_of(s2, "AnimGraphNode_BlendSpacePlayer")["has_binding"] is True, "has_binding")
    check(s2["revision"] != rev_setup, "revision 변경 (바인딩이 해시에 포함)")
    check(not any(n["class"] == "K2Node_VariableGet" for n in s2["nodes"]), "VariableGet 노드 없음")
    rev_bound = s2["revision"]
    # 노출만 한 상태의 revision (C 절 비교용) — 바인딩 전에 핀만 노출하면 어떤 값인지는 unbind 뒤 측정

    print("\n=== B. 재바인딩 · 함수 경로 ===")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": "GroundDistance"}], expected=rev_bound, compile=True)
    b = must(r, "rebind dotted")
    check(b["operations"][0].get("replaced") is True and b["compile"].get("num_errors") == 0, "점 경로 재바인딩 → replaced · 컴파일 0 에러")
    s3 = structure()
    check(pin_x(s3)["binding"]["path"] == ["GroundDistance"] and s3["revision"] != rev_bound, "path GroundDistance · revision 변경")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["GetDeltaSeconds"]}], expected=s3["revision"], compile=True)
    if r.get("ok"):
        s4 = structure()
        check(r["result"]["operations"][0].get("type") == "Function" and pin_x(s4)["binding"]["type"] == "Function" and r["result"]["compile"].get("num_errors") == 0, "함수 경로 GetDeltaSeconds → type Function · 컴파일 0 에러")
    else:
        check(False, f"함수 경로 바인딩: {json.dumps(r.get('error'), ensure_ascii=False)[:300]}")
        s4 = structure()
    # 다시 Speed 로
    must(apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}], expected=s4["revision"]), "back to Speed")
    s5 = structure()
    check(s5["revision"] == rev_bound, "Speed 로 되돌리면 revision 이 A 와 같음 (결정적)")

    print("\n=== C. unbind ===")
    r = apply([{"op": "unbind_pin", "node": bs, "property": "X"}], expected=rev_bound, compile=True)
    c = must(r, "unbind")
    s6 = structure()
    px6 = pin_x(s6)
    check(not px6["bound"] and "binding" not in px6 and px6["shown"], "bound=false · binding 없음 · 핀은 노출 유지")
    check(c["compile"].get("num_errors") == 0, "unbind 뒤 컴파일 0 에러")
    rev_exposed = s6["revision"]
    check(rev_exposed != rev_bound, "revision 변경")
    r = apply([{"op": "unbind_pin", "node": bs, "property": "X"}])
    check(code(r) == "BAD_REQUEST", f"미바인딩 unbind → BAD_REQUEST ({code(r)})")

    print("\n=== D. 롤백 ===")
    # 기존 노드의 없는 핀은 사전 검증에서 걸려 아무것도 적용되지 않는다 — 롤백 경로는 같은 배치의 ref 노드로 만든다 (6-1 함정)
    def failing_tail() -> list[dict]:
        return [
            {"op": "add_node", "ref": "tmp", "class": "AnimGraphNode_SequencePlayer", "pos": [-900, 600]},
            {"op": "connect", "from": {"ref": "tmp", "pin": "NoSuchPin"}, "to": {"node": root["node_guid"], "pin": "Result"}},
        ]
    bad = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}] + failing_tail(), expected=rev_exposed)
    det = bad.get("error", {}).get("details", {})
    check(not bad.get("ok") and det.get("failed_index") == 2 and det.get("rollback_verified") is True, f"bind + 실패 op → rollback_verified ({det.get('rollback_verified')})")
    s7 = structure()
    check(not pin_x(s7)["bound"] and s7["revision"] == rev_exposed, "롤백 뒤 bound=false · revision 복원")
    must(apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}], expected=rev_exposed), "bind again")
    bad = apply([{"op": "unbind_pin", "node": bs, "property": "X"}] + failing_tail(), expected=rev_bound)
    det = bad.get("error", {}).get("details", {})
    check(not bad.get("ok") and det.get("failed_index") == 2 and det.get("rollback_verified") is True, "unbind + 실패 op → rollback_verified")
    s8 = structure()
    check(pin_x(s8)["bound"] and pin_x(s8)["binding"]["path"] == ["Speed"] and s8["revision"] == rev_bound, "롤백 뒤 바인딩 복원 · revision == A")

    print("\n=== E. 거부 ===")
    r = apply([{"op": "bind_pin", "node": bs, "property": "NoSuchProp", "path": ["Speed"]}]); check(code(r) == "BAD_REQUEST", f"없는 핀 프로퍼티 → BAD_REQUEST ({code(r)})")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["NoSuchVar"]}]); check(code(r) == "BAD_REQUEST" and reason(r) == "PATH_UNRESOLVED", f"해석 안 되는 경로 → PATH_UNRESOLVED ({code(r)}/{reason(r)})")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["GameplayTagPropertyMap"]}]); check(code(r) == "BAD_REQUEST" and reason(r) == "TYPE_INCOMPATIBLE", f"구조체 → float 비호환 → TYPE_INCOMPATIBLE ({code(r)}/{reason(r)})")
    r = apply([{"op": "bind_pin", "node": bs, "property": "X"}]); check(code(r) == "BAD_REQUEST", f"path 누락 → BAD_REQUEST ({code(r)})")
    r = apply([{"op": "bind_pin", "node": root["node_guid"], "property": "Result", "path": ["Speed"]}]); check(code(r) == "BAD_REQUEST", f"Root 노드 Result → BAD_REQUEST ({code(r)})")
    check(pin_x(structure())["bound"], "거부들 뒤 바인딩 유지")
    # 핀 링크 중 — 바인딩 해제 뒤 VariableGet 연결 → bind 거부
    s9 = structure()
    r = must(apply([
        {"op": "unbind_pin", "node": bs, "property": "X"},
        {"op": "add_node", "ref": "speed", "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-800, 100]},
        {"op": "connect", "from": {"ref": "speed", "pin": "Speed"}, "to": {"node": bs, "pin": "X"}},
    ], expected=s9["revision"]), "unbind + link")
    vg = r["refs"]["speed"]
    r = apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}]); check(code(r) == "BAD_REQUEST" and reason(r) == "PIN_LINKED", f"핀 링크 중 → PIN_LINKED ({code(r)}/{reason(r)})")
    r = apply([{"op": "bind_pin", "node": vg, "property": "Speed", "path": ["Speed"]}]); check(code(r) == "BAD_REQUEST", f"VariableGet 에 bind → BAD_REQUEST ({code(r)})")
    r = apply([{"op": "bind_pin", "ref": "nope", "property": "X", "path": ["Speed"]}]); check(code(r) in ("BAD_REQUEST", "NODE_NOT_FOUND"), f"없는 ref → 거부 ({code(r)})")
    # 같은 배치 ref 에 bind (pending 경로) — 새 BlendSpacePlayer 를 만들고 그 X 를 묶는다
    s10 = structure()
    r = apply([
        {"op": "add_node", "ref": "bs2", "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 300], "asset": BS},
        {"op": "bind_pin", "ref": "bs2", "property": "X", "path": ["Speed"]},
    ], expected=s10["revision"], compile=True)
    rr = must(r, "pending ref bind")
    check(rr["compile"].get("num_errors") == 0 and rr["operations"][1].get("type") == "Property", "같은 배치 ref 노드에 bind → 컴파일 0 에러")
    bs2 = rr["refs"]["bs2"]
    # 정리: 링크 제거(노드 삭제) → 별도 배치로 bs 를 다시 Speed 에 묶는다 (bind 의 사전 검증은 같은 배치의 앞선 링크 해제를 모른다)
    s11 = structure()
    must(apply([{"op": "remove_node", "node": vg}, {"op": "remove_node", "node": bs2}], expected=s11["revision"]), "cleanup remove")
    s12 = structure()
    must(apply([{"op": "bind_pin", "node": bs, "property": "X", "path": ["Speed"]}], expected=s12["revision"], compile=True), "cleanup bind")

    print("\n=== F. 저장 ===")
    fin = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP, "save_on_success": True}, timeout=bridge.COMPILE_TIMEOUT), "compile+save")
    check(fin.get("num_errors") == 0 and fin.get("saved"), "최종 컴파일 0 에러 · 저장")
    sF = structure()
    pxF = pin_x(sF)
    check(pxF["bound"] and pxF["binding"]["path"] == ["Speed"], "최종 상태: X ← Speed")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"revision": sF["revision"], "bs": bs, "binding": pxF["binding"]}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE} (revision {sF['revision']})")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = structure()
    px = pin_x(s)
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(px["bound"] and px["binding"] == saved["binding"], f"바인딩 동일 {px.get('binding')}")
    c = must(bridge.call("compile_animation_blueprint", {"asset_path": ABP}, timeout=bridge.COMPILE_TIMEOUT), "compile")
    check(c.get("num_errors") == 0, "컴파일 0 에러")


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
