"""M3 뒤 다듬기 T1 · T2 — 수호병 회피(RVO) 값 (설계 Docs/Design/m3-enemy-ai.md §13) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

공격 자리 나눔(ST_Enemy_Guardian 의 Approach 상태 — state-tree-mcp 로 저작)을 넣은 뒤에는 자리가 적끼리의 간격을 정한다.
RVO 를 켠 채로는 서 있는 두 마리 사이의 자리에 들어가지 못한다(회피 반경이 캡슐의 1.5배 — §13 실측). 그래서 끈다.

이 스크립트가 하는 것 (다시 돌려도 같다):
    BP_Enemy_Guardian      CharacterMovement 의 bUseRVOAvoidance 만 USE_RVO_AVOIDANCE 값으로. 다른 값은 건드리지 않는다

결과는 Tools/mcp/results/enemy_guardian_engage_slots.json 에 쓴다(Saved 는 읽을 수 없다).
"""
import json
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B

importlib.reload(B)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_guardian_engage_slots.json"
ENEMY_PATH = "/Game/Characters/Enemy/BP_Enemy_Guardian"

# ─── 잠정값 ───
USE_RVO_AVOIDANCE = False

result = {"ok": False, "steps": {}, "errors": []}


def step_guardian_rvo():
    bp = unreal.load_asset(ENEMY_PATH)
    if not bp:
        raise RuntimeError(f"BP 없음: {ENEMY_PATH}")
    movement = unreal.get_default_object(bp.generated_class()).get_editor_property("character_movement")
    info = {"path": ENEMY_PATH, "before": bool(movement.get_editor_property("use_rvo_avoidance"))}
    movement.set_editor_property("use_rvo_avoidance", USE_RVO_AVOIDANCE)
    info["saved"] = B.compile_and_save(bp)

    saved = unreal.get_default_object(bp.generated_class()).get_editor_property("character_movement")
    info["use_rvo_avoidance"] = bool(saved.get_editor_property("use_rvo_avoidance"))
    info["max_walk_speed"] = saved.get_editor_property("max_walk_speed")
    if info["use_rvo_avoidance"] != USE_RVO_AVOIDANCE:
        raise RuntimeError("bUseRVOAvoidance 가 저장되지 않았다")
    return info


def main():
    try:
        result["steps"]["guardian_rvo"] = step_guardian_rvo()
    except Exception as error:  # noqa: BLE001
        result["errors"].append(f"guardian_rvo: {error}")
        result["steps"]["guardian_rvo"] = {"error": str(error), "trace": traceback.format_exc()}
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"ENEMY_GUARDIAN_ENGAGE_SLOTS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
