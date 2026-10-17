"""Phase 6-3 BlendSpace 생성 — create_blendspace · list_animation_assets(details).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase6_3_test.py [--recheck]

새 Tool 은 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출(bridge)로 검증한다.
대상(생성·덮어쓰기): /Game/Animation/Test/BS_McpTest (1D) · BS_McpTest2D (2D) · ABP_McpBsTest (BlendSpacePlayer 로 사용).
원본 BS_Hero_Locomotion1D 와 운영 애셋은 읽기만.
검사 항목:
  A. list details — 원본 BS_Hero_Locomotion1D 의 축·샘플 요약
  B. 1D 생성 — 원본과 같은 스켈레톤·축·샘플 → class BlendSpace1D · 축/샘플/grid 수 동일 · 저장
  C. 사용 — 새 ABP 에 BlendSpacePlayer(set_asset BS_McpTest) + Speed→X → 컴파일 0 에러 → 저장
  D. 2D 생성 — 축 2 · 샘플 3 → class BlendSpace · grid_sample_count=(gx+1)(gy+1)
  E. 거부 — dimensions 3 · 축 수 불일치 · min≥max · grid 0 · 범위 밖 샘플 · 중복 위치 · 없는 애니 · 몽타주를 샘플로 · 스켈레톤 불일치(있으면) · ASSET_EXISTS · 보호 애셋 overwrite · 실패 시 애셋 미생성
  R. --recheck — BS_McpTest/2D 요약 동일 · ABP_McpBsTest revision 동일 · 컴파일 0 에러
"""
from __future__ import annotations

import json
import os
import sys

from anim_graph_mcp import bridge

SRC_BS = "/Game/Animation/Hero/Anims/Locomotions/BS_Hero_Locomotion1D"
BS1 = "/Game/Animation/Test/BS_McpTest"
BS2 = "/Game/Animation/Test/BS_McpTest2D"
ABP = "/Game/Animation/Test/ABP_McpBsTest"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
PROD_ABP = "/Game/Animation/Hero/ABP_Hero_Base"
DEMO_ABP = "/Game/Assets/IdaFaber/Blueprints/ABP_UE5_Demo_F"
MONTAGE = "/Game/Animation/Hero/Montages/AM_Hero_Attack1"
STATE_FILE = "Tools/mcp/phase6_3_state.json"
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
    return env.get("error", {}).get("details", {}).get("reason", "")


def describe(path: str) -> dict | None:
    folder = path.rsplit("/", 1)[0]
    r = must(bridge.call("list_animation_assets", {"class": "BlendSpace", "path_prefix": folder, "details": True, "limit": 50}, timeout=bridge.COMPILE_TIMEOUT), f"list {folder}")
    for a in r["assets"]:
        if a["asset_path"].startswith(path + "."):
            return a.get("blendspace")
    return None


def shape(d: dict) -> dict:
    """비교용 — 축(name/min/max/grid/snap/wrap) · 샘플(animation, value) · 수"""
    return {
        "class": d["class"], "dimensions": d["dimensions"], "skeleton": d["skeleton"],
        "axes": [(a["name"], a["min"], a["max"], a["grid"], a["snap"], a["wrap"]) for a in d["axes"]],
        "samples": sorted((s["animation"], tuple(round(v, 4) for v in s["value"])) for s in d["samples"]),
        "sample_count": d["sample_count"], "grid_sample_count": d["grid_sample_count"],
        "segment_count": d["segment_count"], "triangle_count": d["triangle_count"],
    }


def create(**kw) -> dict:
    return bridge.call("create_blendspace", kw, timeout=bridge.COMPILE_TIMEOUT)


def exists_bs(path: str) -> bool:
    return describe(path) is not None


def main_sections() -> None:
    print("=== A. 원본 요약 ===")
    st = must(bridge.call("get_editor_status"), "status")
    check("create_blendspace" in {t["name"] for t in st["tools"]}, f"create_blendspace 등록 (총 {len(st['tools'])})")
    src = describe(SRC_BS)
    check(src is not None and src["dimensions"] == 1 and len(src["axes"]) == 1 and src["sample_count"] >= 2, f"원본 요약: {json.dumps(src, ensure_ascii=False)[:300]}")
    src_axis = src["axes"][0]
    src_samples = [{"animation": s["animation"], "value": s["value"]} for s in src["samples"]]
    axes1 = [{"name": src_axis["name"], "min": src_axis["min"], "max": src_axis["max"], "grid": src_axis["grid"], "snap": src_axis["snap"], "wrap": src_axis["wrap"]}]
    print(f"   axis {axes1[0]} · samples {len(src_samples)}")

    print("\n=== B. 1D 생성 ===")
    r = create(asset_path=BS1, skeleton=src["skeleton"], dimensions=1, axes=axes1, samples=src_samples, overwrite=True, save=True)
    b = must(r, "create 1D")
    check(b.get("created") and b.get("saved") and b["class"] == "BlendSpace1D", "created · saved · BlendSpace1D")
    check(shape(b) == shape(src), "축·샘플·grid·선분 수가 원본과 동일")
    check(b["segment_count"] == len(src_samples) - 1, f"1D 선분 수 = 샘플-1 ({b['segment_count']})")
    check(all(s.get("valid", True) for s in b["samples"]), "모든 샘플 valid")
    check(abs(b["anim_length"] - src["anim_length"]) < 1e-3, f"anim_length 동일 ({b['anim_length']:.3f})")
    again = describe(BS1)
    check(again is not None and shape(again) == shape(b), "list details 재조회 동일")
    check(os.path.exists("Content/Animation/Test/BS_McpTest.uasset"), "디스크 파일 존재")

    print("\n=== C. ABP 에서 사용 ===")
    abp = must(bridge.call("create_animation_blueprint", {"asset_path": ABP, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": True}), "create abp")
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "structure")
    root = next(n for n in s["nodes"] if n["class"] == "AnimGraphNode_Root")
    ap = bridge.call("apply_graph_operations", {"asset_path": ABP, "expected_revision": s["revision"], "compile": True, "save": True, "operations": [
        {"op": "add_node", "ref": "speed", "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-800, 100]},
        {"op": "add_node", "ref": "bs", "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 0], "asset": BS1},
        {"op": "connect", "from": {"ref": "speed", "pin": "Speed"}, "to": {"ref": "bs", "pin": "X"}},
        {"op": "connect", "from": {"ref": "bs", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]}, timeout=bridge.COMPILE_TIMEOUT)
    a = must(ap, "apply")
    check(a["compile"].get("num_errors") == 0 and a.get("saved"), f"BlendSpacePlayer(BS_McpTest)+Speed→X 컴파일 0 에러 (warnings={a['compile'].get('num_warnings')}) · 저장")
    s2 = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "structure 2")
    bs_node = next(n for n in s2["nodes"] if n["class"] == "AnimGraphNode_BlendSpacePlayer")
    check((bs_node.get("asset") or "").startswith(BS1), f"노드 asset = {bs_node.get('asset')}")
    abp_rev = s2["revision"]

    print("\n=== D. 2D 생성 ===")
    anims = [s["animation"] for s in src_samples]
    axes2 = [{"name": "Speed", "min": 0, "max": 600, "grid": 3}, {"name": "Direction", "min": -180, "max": 180, "grid": 4, "wrap": True}]
    samples2 = [{"animation": anims[0], "value": [0, 0]}, {"animation": anims[1 % len(anims)], "value": [300, -90]}, {"animation": anims[-1], "value": [600, 180]}]
    r = create(asset_path=BS2, skeleton=SKELETON, dimensions=2, axes=axes2, samples=samples2, overwrite=True, save=True)
    d2 = must(r, "create 2D")
    check(d2["class"] == "BlendSpace" and d2["dimensions"] == 2 and d2["sample_count"] == 3, "BlendSpace · 2D · 샘플 3")
    check([a["name"] for a in d2["axes"]] == ["Speed", "Direction"] and d2["axes"][1]["wrap"] is True and d2["axes"][1]["min"] == -180, "축 2 · wrap · 범위")
    # 2D 기본(bInterpolateUsingGrid=false)은 삼각분할 — 샘플 3 → 삼각형 1, 그리드 0 (BlendSpace.cpp:2784-2804)
    check(d2["triangle_count"] == 1 and d2["grid_sample_count"] == 0 and d2["interpolate_using_grid"] is False, f"삼각형 1 · 그리드 0 ({d2['triangle_count']}/{d2['grid_sample_count']})")
    check(all(s.get("valid", True) for s in d2["samples"]), "2D 샘플 전부 valid")

    print("\n=== E. 거부 ===")
    probe = "/Game/Animation/Test/BS_McpProbe"
    base = dict(skeleton=SKELETON, dimensions=1, axes=axes1, samples=src_samples)
    r = create(asset_path=probe, **{**base, "dimensions": 3}); check(code(r) == "BAD_REQUEST", f"dimensions 3 → BAD_REQUEST ({code(r)})")
    r = create(asset_path=probe, **{**base, "dimensions": 2}); check(code(r) == "BAD_REQUEST", f"축 수 불일치 → BAD_REQUEST ({code(r)})")
    r = create(asset_path=probe, **{**base, "axes": [{"name": "X", "min": 10, "max": 10}]}); check(code(r) == "BAD_REQUEST", f"min≥max → BAD_REQUEST ({code(r)})")
    r = create(asset_path=probe, **{**base, "axes": [{"name": "X", "min": 0, "max": 1, "grid": 0}]}); check(code(r) == "BAD_REQUEST", f"grid 0 → BAD_REQUEST ({code(r)})")
    r = create(asset_path=probe, **{**base, "samples": [{"animation": anims[0], "value": [src_axis["max"] + 100]}]})
    check(code(r) == "BAD_REQUEST" and reason(r) == "OUT_OF_RANGE", f"범위 밖 샘플 → OUT_OF_RANGE ({code(r)}/{reason(r)})")
    r = create(asset_path=probe, **{**base, "samples": [{"animation": anims[0], "value": [src_axis["min"]]}, {"animation": anims[-1], "value": [src_axis["min"]]}]})
    check(code(r) == "BAD_REQUEST" and reason(r) == "DUPLICATE_POSITION", f"중복 위치 → DUPLICATE_POSITION ({code(r)}/{reason(r)})")
    r = create(asset_path=probe, **{**base, "samples": [{"animation": "/Game/Animation/Nope/AS_Nope", "value": [0]}]}); check(code(r) == "ASSET_NOT_FOUND", f"없는 애니 → ASSET_NOT_FOUND ({code(r)})")
    r = create(asset_path=probe, **{**base, "samples": [{"animation": MONTAGE, "value": [0]}]}); check(code(r) == "BAD_REQUEST", f"몽타주를 샘플로 → BAD_REQUEST ({code(r)})")
    # 스켈레톤 불일치 — 다른 스켈레톤의 AnimSequence 가 있으면
    other = None
    lst = must(bridge.call("list_animation_assets", {"class": "AnimSequence", "path_prefix": "/Game", "limit": 5000}), "list seq")
    for a in lst["assets"]:
        if a.get("skeleton") and not a["skeleton"].startswith(SKELETON):
            other = a["asset_path"]
            break
    if other:
        r = create(asset_path=probe, **{**base, "samples": [{"animation": other, "value": [src_axis["min"]]}]})
        check(code(r) == "BAD_REQUEST" and reason(r) == "SKELETON_MISMATCH", f"스켈레톤 불일치({other}) → SKELETON_MISMATCH ({code(r)}/{reason(r)})")
    else:
        print("   (다른 스켈레톤의 AnimSequence 가 없어 스켈레톤 불일치 검사 생략)")
    check(not exists_bs(probe) and not os.path.exists("Content/Animation/Test/BS_McpProbe.uasset"), "거부된 생성은 애셋을 남기지 않음")
    r = create(asset_path=BS1, **base); check(code(r) == "ASSET_EXISTS", f"overwrite 없이 재생성 → ASSET_EXISTS ({code(r)})")
    r = create(asset_path=DEMO_ABP, overwrite=True, **base); check(code(r) == "ASSET_PROTECTED", f"보호 경로 애셋 overwrite → ASSET_PROTECTED ({code(r)})")
    r = create(asset_path=PROD_ABP, overwrite=True, **base); check(code(r) == "ASSET_PROTECTED", f"운영 ABP 경로 overwrite → ASSET_PROTECTED ({code(r)})")
    check(shape(describe(BS1)) == shape(src), "거부들 뒤 BS_McpTest 그대로")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"bs1": shape(describe(BS1)), "bs2": shape(describe(BS2)), "abp_revision": abp_rev}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)

    def norm(d: dict) -> dict:
        d = dict(d)
        d["axes"] = [tuple(a) for a in d["axes"]]
        d["samples"] = [(s[0], tuple(s[1])) for s in d["samples"]]
        return d
    check(shape(describe(BS1)) == norm(saved["bs1"]), "BS_McpTest 요약 동일")
    check(shape(describe(BS2)) == norm(saved["bs2"]), "BS_McpTest2D 요약 동일")
    s = must(bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": 0}), "structure")
    check(s["revision"] == saved["abp_revision"], f"ABP_McpBsTest revision 동일 ({s['revision']})")
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
