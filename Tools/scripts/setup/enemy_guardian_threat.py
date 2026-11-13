"""M3 뒤 다듬기 T3 · T4 — 수호병의 타깃 추첨 값 (설계 Docs/Design/m3-enemy-ai.md §13) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것: C++ 빌드(UAstralThreatComponent 의 bDrawWithoutDamage · DistanceWeight · SpreadWeight),
/Game/AI/Enemy/BP_EnemyController_Guardian (enemy_guardian_c2_assets.py)

이 스크립트가 하는 것 (다시 돌려도 같다):
    BP_EnemyController_Guardian   ThreatComponent 의 세 값만 쓴다. 단위 B 의 값(피해 가중 · 창 · 유지 · 재추첨 간격 · 제외)은 건드리지 않는다
    BP_EnemyController_Melee      읽기만 한다 — 세 값이 기본(끔 · 0 · 0)으로 남아 있는지 결과에 적는다(마네킹 불변)

값은 전부 잠정이다. 결과는 Tools/mcp/results/enemy_guardian_threat.json 에 쓴다(Saved 는 읽을 수 없다).
"""
import json
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B

importlib.reload(B)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_guardian_threat.json"
GUARDIAN_CONTROLLER_PATH = "/Game/AI/Enemy/BP_EnemyController_Guardian"
MELEE_CONTROLLER_PATH = "/Game/AI/Enemy/BP_EnemyController_Melee"

# ─── 잠정값 ───
THREAT_VALUES = {
    "draw_without_damage": True,   # 아무도 안 때렸어도 추첨한다 (끄면 가장 가까운 사람)
    "distance_weight": 2.0,        # 가장 가까운 후보 3배, 두 배 먼 후보 2배
    "spread_weight": 1.0,          # 다른 수호병 한 마리가 이미 노리는 후보는 절반
}
ALL_PROPS = ("damage_weight", "damage_window", "hold_time", "retarget_cooldown", "exclude_time", *THREAT_VALUES)

result = {"ok": False, "steps": {}, "errors": []}


def threat_of(path):
    bp = unreal.load_asset(path)
    if not bp:
        raise RuntimeError(f"BP 없음: {path}")
    return bp, unreal.get_default_object(bp.generated_class()).get_editor_property("threat_component")


def read(threat):
    values = {}
    for name in ALL_PROPS:
        value = threat.get_editor_property(name)
        values[name] = bool(value) if isinstance(value, bool) else round(float(value), 3)
    return values


def step_guardian_threat():
    bp, threat = threat_of(GUARDIAN_CONTROLLER_PATH)
    info = {"path": GUARDIAN_CONTROLLER_PATH, "before": read(threat)}
    for name, value in THREAT_VALUES.items():
        threat.set_editor_property(name, value)
    info["saved"] = B.compile_and_save(bp)

    _, saved = threat_of(GUARDIAN_CONTROLLER_PATH)
    info["after"] = read(saved)
    for name, value in THREAT_VALUES.items():
        if info["after"][name] != value:
            raise RuntimeError(f"threat_component.{name} 가 저장되지 않았다: {info['after'][name]}")
    return info


def step_melee_unchanged():
    _, threat = threat_of(MELEE_CONTROLLER_PATH)
    info = {"path": MELEE_CONTROLLER_PATH, "values": read(threat)}
    if info["values"]["draw_without_damage"] or info["values"]["distance_weight"] or info["values"]["spread_weight"]:
        raise RuntimeError("마네킹 컨트롤러의 추첨 값이 기본이 아니다")
    return info


def main():
    for name, fn in (("guardian_threat", step_guardian_threat), ("melee_unchanged", step_melee_unchanged)):
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"ENEMY_GUARDIAN_THREAT {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
