"""히어로 애니 애셋 스켈레톤 통합 — /Game/Animation/Hero 아래 B 스켈레톤 애셋을 A 로 (1회성 콘텐츠 작업, 2026-10-19 사용자 확정).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/reassign_hero_skeleton.py [--apply]

  A = /Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F  (히어로 메시 · ABP_Hero_Base · BS_Vesper_Locomotion1D)
  B = /Game/IdaFaber/Meshes/Girl/SKEL_UE5_F         (같은 메시를 두 번 임포트해 생긴 두 번째 스켈레톤 — AO_Rifle*·Rifle_Jog*·M_Neutral_*·Jump_*·Attack1~3·몽타주)
--apply 없이는 dry_run 계획만 출력한다. 적용 뒤 레지스트리로 B 애셋이 0 인지 확인하고, ABP_Hero_Base 가 그대로 컴파일되는지 본다.
"""
from __future__ import annotations

import json
import sys

from anim_graph_mcp import bridge

SKEL_A = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
SKEL_B = "/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PREFIX = "/Game/Animation/Hero"
PROD_ABP = "/Game/Animation/Hero/ABP_Hero_Base"


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def main() -> int:
    must(bridge.call("get_editor_status"), "status")
    plan = must(bridge.call("reassign_skeleton", {"skeleton": SKEL_A, "from_skeleton": SKEL_B, "path_prefix": PREFIX, "dry_run": True}, timeout=bridge.COMPILE_TIMEOUT), "dry_run")
    print(f"B 애셋 {plan['total']}개 → A (참조로 딸려가는 것 {len(plan['referred'])}개, 건너뜀 {len(plan['skipped'])}개)")
    for p in plan["planned"]:
        print(f"   {p['class']:<14} {p['asset'].split('.')[0]}" + (f"  missing={p['missing_bones']}" if p.get("missing_bones") else ""))
    for r in plan["referred"]:
        print(f"   (referred) {r['class']:<14} {r['asset'].split('.')[0]}")
    if "--apply" not in sys.argv:
        print("\n계획만 출력했다. 적용하려면 --apply")
        return 0

    res = must(bridge.call("reassign_skeleton", {"skeleton": SKEL_A, "from_skeleton": SKEL_B, "path_prefix": PREFIX, "confirm": True}, timeout=600.0), "apply")
    print(f"\nchanged {len(res['changed_assets'])} · referred_changed {len(res['referred_changed'])} · failed {len(res['failed'])} · saved={res['saved']} · skeleton_saved={res['skeleton_saved']}")
    for f in res["failed"]:
        print(f"   [FAIL] {f}")

    left = must(bridge.call("reassign_skeleton", {"skeleton": SKEL_A, "from_skeleton": SKEL_B, "path_prefix": PREFIX, "dry_run": True}, timeout=bridge.COMPILE_TIMEOUT), "leftover")
    print(f"남은 B 애셋: {left['total']}")
    comp = must(bridge.call("compile_animation_blueprint", {"asset_path": PROD_ABP}, timeout=bridge.COMPILE_TIMEOUT), "compile prod")
    print(f"ABP_Hero_Base 컴파일: errors={comp['num_errors']} warnings={comp['num_warnings']}")
    return 0 if (not res["failed"] and left["total"] == 0 and comp["num_errors"] == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
