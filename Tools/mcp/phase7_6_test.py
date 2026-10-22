"""Phase 7-6 — 스켈레톤 재할당 (reassign_skeleton).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_6_test.py [--recheck]

새 Tool 은 세션 재시작 전 MCP 에 보이지 않으므로 HTTP 직접 호출로 검증한다.
테스트 몽타주 /Game/Animation/Test/AM_McpSkelTest(스켈레톤 A 시퀀스 AS_Idle 로 생성)를 B 로 보냈다가 A 로 되돌린다.
⚠️ 엔진의 ReplaceSkeleton 은 참조 애셋(세그먼트 AS_Idle)을 **항상** 같이 옮긴다(AnimationAsset.cpp:468-474, 7-6 실측) — 그래서 이 테스트는
운영 시퀀스 AS_Idle 을 A→B→A 왕복시킨다(내용 불변, 두 번 재저장). 중간에 끊기면 `reassign_skeleton {skeleton: A, assets: [AS_Idle]}` 로 복구.
  A = /Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F (히어로 메시·ABP_Hero_Base)
  B = /Game/IdaFaber/Meshes/Girl/SKEL_UE5_F        (같은 본 이름, 다른 애셋 — 7-3 실측. 7-6 에서 히어로 애셋 40개를 A 로 통합한 뒤 빈 스켈레톤)
검사 항목:
  A. 준비 — Tool 등록 · 테스트 몽타주 생성(A)
  B. 거부 — skeleton 누락 · 없는 skeleton · assets/from_skeleton 둘 다 없음 · from==target · confirm 없음 · assets 타입 오류 · 애셋 불변
  C. dry_run — planned 1 · referred 에 세그먼트 AS_Idle · 애셋 불변
  D. 양성 — A→B (changed 1 · referred_changed 1 · 저장) · 레지스트리가 몽타주·AS_Idle 모두 B 로 보고 · 재호출은 skipped(already_on_target)
  E. 복귀 — from_skeleton 수집(B, /Game/Animation/Test)으로 B→A · 몽타주·AS_Idle 모두 A · 남은 B 애셋 0
  F. 본 검증 — UEFN 마네킹 스켈레톤(본 이름 다름)으로 시퀀스 재할당 → BONES_MISSING 거부(애셋 불변), dry_run 도 같은 거부
  G. set_sequence_additive — AS_Vesper_Rifle_AO_CD 로 같은 값 → unchanged · ref_frame_index 0→1→0 왕복(저장) · 거부(잘못된 enum ·
     다른 스켈레톤 기준 포즈 → SKELETON_MISMATCH · 몽타주 → BAD_REQUEST · 음수 인덱스) · additive_valid 유지
  R. --recheck — 에디터 재시작 뒤 테스트 몽타주·AS_Idle 이 A, 몽타주 슬롯이 스켈레톤에 등록됨, AO_RifleCD 기준 포즈 그대로
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

SKEL_A = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
SKEL_B = "/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F"
SKEL_OTHER = "/Game/Characters/UEFN_Mannequin/Meshes/SK_UEFN_Mannequin"
SEQ_A = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
MONTAGE = "/Game/Animation/Test/AM_McpSkelTest"
TEST_DIR = "/Game/Animation/Test"
AO_CD = "/Game/Animation/Hero/Vesper/Rifle/Aim/AS_Vesper_Rifle_AO_CD"
AO_BASE = "/Game/Animation/Hero/Vesper/Rifle/Locomotion/AS_Vesper_Rifle_Idle"
OTHER_SEQ = "/Game/Characters/UEFN_Mannequin/Animations/Walk/M_Neutral_Walk_Loop_F"
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
    return (env.get("error") or {}).get("code", "") if not env.get("ok") else "OK"


def reason(env: dict) -> str:
    return ((env.get("error") or {}).get("details") or {}).get("reason", "")


def call(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def skeleton_of(path: str) -> str:
    r = must(call("list_animation_assets", path_prefix=path.rsplit("/", 1)[0], details=False), f"list {path}")
    for a in r["assets"]:
        if a["asset_path"].startswith(path + "."):
            return (a["skeleton"] or "").split(".")[0]
    return ""


def restore_idle() -> None:
    """실패 경로 안전망 — AS_Idle 이 B 에 남지 않게."""
    if skeleton_of(SEQ_A) != SKEL_A:
        call("reassign_skeleton", skeleton=SKEL_A, assets=[SEQ_A], confirm=True)


def main_sections() -> None:
    print("=== A. 준비 ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check("reassign_skeleton" in names, f"Tool reassign_skeleton 등록 (총 {len(names)})")
    check(skeleton_of(SEQ_A) == SKEL_A, "시작 상태: AS_Idle 은 A")
    m = must(call("create_anim_montage", asset_path=MONTAGE, animation=SEQ_A, slot="DefaultSlot", overwrite=True, save=True), "create montage")
    check(m["skeleton"].startswith(SKEL_A) and m["saved"], f"테스트 몽타주 생성 (skeleton {m['skeleton']})")

    print("\n=== B. 거부 ===")
    r = call("reassign_skeleton"); check(code(r) == "BAD_REQUEST", f"skeleton 누락 → {code(r)}")
    r = call("reassign_skeleton", skeleton="/Game/Nope/SKEL_X", assets=[MONTAGE], confirm=True); check(code(r) == "ASSET_NOT_FOUND", f"없는 skeleton → {code(r)}")
    r = call("reassign_skeleton", skeleton=SKEL_B, confirm=True); check(code(r) == "BAD_REQUEST" and "assets" in r["error"]["message"], f"assets/from_skeleton 없음 → {code(r)}")
    r = call("reassign_skeleton", skeleton=SKEL_B, from_skeleton=SKEL_B, confirm=True); check(code(r) == "BAD_REQUEST" and "same" in r["error"]["message"], f"from == target → {code(r)}")
    r = call("reassign_skeleton", skeleton=SKEL_B, assets=[MONTAGE]); check(code(r) == "BAD_REQUEST" and "confirm" in r["error"]["message"], f"confirm 없음 → {code(r)}")
    r = call("reassign_skeleton", skeleton=SKEL_B, assets=[1], confirm=True); check(code(r) == "BAD_REQUEST" and ((r.get("error") or {}).get("details") or {}).get("field") == "assets", f"assets 타입 오류 → {code(r)}")
    check(skeleton_of(MONTAGE) == SKEL_A and skeleton_of(SEQ_A) == SKEL_A, "거부 뒤 몽타주·AS_Idle 불변 (A)")

    print("\n=== C. dry_run ===")
    d = must(call("reassign_skeleton", skeleton=SKEL_B, assets=[MONTAGE], dry_run=True), "dry_run")
    check(d["dry_run"] and len(d["planned"]) == 1 and d["planned"][0]["asset"].startswith(MONTAGE) and d["planned"][0]["from"].startswith(SKEL_A), f"planned 1: {d['planned'][0]['asset']} from {d['planned'][0]['from']}")
    check(len(d["referred"]) == 1 and d["referred"][0]["asset"].startswith(SEQ_A) and d["skipped"] == [] and not d["changed"], f"referred = 세그먼트 AS_Idle (엔진이 같이 옮긴다) · skipped 없음 · changed=false")
    check(skeleton_of(MONTAGE) == SKEL_A and skeleton_of(SEQ_A) == SKEL_A, "dry_run 은 애셋을 바꾸지 않는다")

    print("\n=== D. 양성 A→B (세그먼트 동반) ===")
    p = must(call("reassign_skeleton", skeleton=SKEL_B, assets=[MONTAGE], confirm=True), "A→B")
    check(p["changed"] and len(p["changed_assets"]) == 1 and p["saved"] and p["failed"] == [], f"changed 1 · saved (skeleton_saved={p['skeleton_saved']})")
    check(len(p["referred_changed"]) == 1 and p["referred_changed"][0].startswith(SEQ_A), f"referred_changed = AS_Idle: {p['referred_changed']}")
    check(skeleton_of(MONTAGE) == SKEL_B, "레지스트리: 몽타주 스켈레톤 B")
    check(skeleton_of(SEQ_A) == SKEL_B, "레지스트리: 세그먼트 AS_Idle 도 B (ReplaceSkeleton 의 참조 전파)")
    again = must(call("reassign_skeleton", skeleton=SKEL_B, assets=[MONTAGE], confirm=True), "A→B again")
    check(not again["changed"] and again["skipped"] and again["skipped"][0]["reason"] == "already_on_target", "같은 대상 재호출 → skipped already_on_target")

    print("\n=== E. 복귀 B→A ===")
    back = must(call("reassign_skeleton", skeleton=SKEL_A, from_skeleton=SKEL_B, path_prefix=TEST_DIR, confirm=True), "B→A (from_skeleton 수집)")
    check(back["changed"] and any(x["asset"].startswith(MONTAGE) for x in back["changed_assets"]), f"from_skeleton 수집으로 되돌림: {[x['asset'] for x in back['changed_assets']]}")
    check(skeleton_of(MONTAGE) == SKEL_A and skeleton_of(SEQ_A) == SKEL_A, "레지스트리: 몽타주·AS_Idle 모두 A")
    left = must(call("reassign_skeleton", skeleton=SKEL_A, from_skeleton=SKEL_B, path_prefix="/Game", dry_run=True), "leftover")
    check(left["total"] == 0 and left["planned"] == [], f"/Game 전체에 B 애셋 0 (히어로 애셋 통합 뒤 B 는 빈 스켈레톤)")

    print("\n=== F. 본 검증 ===")
    r = call("reassign_skeleton", skeleton=SKEL_OTHER, assets=[SEQ_A], confirm=True)
    check(code(r) == "BAD_REQUEST" and reason(r) == "BONES_MISSING" and r["error"]["details"]["assets"][0]["missing_bones"], f"본 이름이 다른 스켈레톤 → {code(r)}/{reason(r)} (missing {len(r['error']['details']['assets'][0]['missing_bones'])})")
    check(skeleton_of(SEQ_A) == SKEL_A, "거부 뒤 AS_Idle 불변")
    r = call("reassign_skeleton", skeleton=SKEL_OTHER, assets=[SEQ_A], dry_run=True)
    check(code(r) == "BAD_REQUEST" and reason(r) == "BONES_MISSING", "dry_run 도 BONES_MISSING 을 먼저 알린다")

    print("\n=== G. set_sequence_additive ===")
    check("set_sequence_additive" in names, "Tool set_sequence_additive 등록")
    same = must(call("set_sequence_additive", asset_path=AO_CD, additive_type="RotationOffsetMeshSpace", ref_pose_type="AnimFrame", ref_pose_sequence=AO_BASE, ref_frame_index=0), "same values")
    check(same["unchanged"] and same["additive_valid"] and same["ref_pose_sequence"].startswith(AO_BASE), f"같은 값 → unchanged · additive_valid ({same['additive_type']}/{same['ref_pose_type']})")
    up = must(call("set_sequence_additive", asset_path=AO_CD, ref_frame_index=1, save=True), "frame 1")
    check(up["changed"] == ["RefFrameIndex"] and up["ref_frame_index"] == 1 and up["saved"] and up["additive_valid"], "ref_frame_index 0→1 · 저장 · additive_valid")
    down = must(call("set_sequence_additive", asset_path=AO_CD, ref_frame_index=0, save=True), "frame 0")
    check(down["ref_frame_index"] == 0 and down["saved"], "ref_frame_index 1→0 복귀 · 저장")
    r = call("set_sequence_additive", asset_path=AO_CD, additive_type="Nope"); check(reason(r) == "BAD_ENUM", f"잘못된 enum → {code(r)}/{reason(r)}")
    r = call("set_sequence_additive", asset_path=AO_CD, ref_pose_sequence=OTHER_SEQ); check(reason(r) == "SKELETON_MISMATCH", f"다른 스켈레톤 기준 포즈 → {code(r)}/{reason(r)}")
    r = call("set_sequence_additive", asset_path=MONTAGE, additive_type="None"); check(code(r) == "BAD_REQUEST", f"몽타주 → {code(r)}")
    r = call("set_sequence_additive", asset_path=AO_CD, ref_frame_index=-1); check(reason(r) == "OUT_OF_RANGE", f"음수 인덱스 → {reason(r)}")
    final = must(call("set_sequence_additive", asset_path=AO_CD), "describe")
    check(final["unchanged"] and final["ref_frame_index"] == 0 and final["additive_valid"], "거부들 뒤 설정 불변")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 ===")
    check(skeleton_of(MONTAGE) == SKEL_A, "테스트 몽타주 스켈레톤 A (저장 반영)")
    check(skeleton_of(SEQ_A) == SKEL_A, "AS_Idle 스켈레톤 A")
    cd = must(call("set_sequence_additive", asset_path=AO_CD), "describe AO_CD")
    check(cd["unchanged"] and cd["ref_frame_index"] == 0 and cd["additive_valid"] and cd["ref_pose_sequence"].startswith(AO_BASE), "AO_RifleCD 기준 포즈 그대로 (저장 반영)")
    info = must(call("list_animation_assets", path_prefix=TEST_DIR, asset_class="AnimMontage", details=True), "montage details")
    mine = [a for a in info["assets"] if a["asset_path"].startswith(MONTAGE + ".")]
    check(len(mine) == 1 and mine[0]["montage"]["slots"][0]["in_skeleton"], "몽타주 슬롯이 스켈레톤 A 에 등록된 상태")


def main() -> int:
    st = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(st['tools'])}")
    try:
        if "--recheck" in sys.argv:
            recheck()
        else:
            main_sections()
    finally:
        restore_idle()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
