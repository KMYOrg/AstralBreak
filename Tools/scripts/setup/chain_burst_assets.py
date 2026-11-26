"""M4 단위 B 체인 버스트 애셋 (설계 Docs/Design/m4-ult-chain.md §3 · §6 단위 B) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것: AAstralRaidGameState · UAstralChainBurstComponent 가 들어간 C++ 빌드.

이 스크립트가 하는 것 (여러 번 돌려도 같다):
    /Game/GameModes/BP_AstralGameState_Raid   부모를 AAstralGameState -> AAstralRaidGameState 로 바꾼다. 이미 그 자식이면 건드리지 않는다
읽기만 하는 것:
    /Game/GameModes/BP_AstralGameMode_Raid    GameStateClass 가 위 BP 인지 (이미 그렇다 — 바꾸지 않는다)
    체인 컴포넌트의 잠정값 (BP 의 CDO 에서)

값(윈도우 · 유예 · 피해 · 반경)은 스크립트가 쓰지 않는다 — C++ 기본값이 잠정값이고, 고칠 때는 BP_AstralGameState_Raid 의 ChainBurstComponent 디테일에서 고친다.
결과는 Tools/mcp/results/chain_burst_assets.json 에 쓴다(Saved 는 읽을 수 없다).
"""
import json
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B

importlib.reload(B)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/chain_burst_assets.json"

GAME_STATE_BP = "/Game/GameModes/BP_AstralGameState_Raid"
GAME_MODE_BP = "/Game/GameModes/BP_AstralGameMode_Raid"
NEW_PARENT = "/Script/AstralBreak.AstralRaidGameState"
COMPONENT_PROPERTY = "chain_burst_component"
COMPONENT_VALUES = ("window_seconds", "grace_seconds", "max_participants", "team_ult_gain",
                    "ult_block_effect_class", "cast_timeout",
                    "burst_base_damage", "burst_damage_multipliers", "burst_radius")

eal = unreal.EditorAssetLibrary
result = {"ok": False, "steps": {}, "errors": []}


def export(value):
    try:
        return value.export_text()
    except Exception:
        return str(value)


def parent_chain(cls):
    """생성 클래스에서 위로 — 이름 목록 (읽기 확인용)."""
    names = []
    try:
        for base in type(unreal.get_default_object(cls)).__mro__:
            names.append(base.__name__)
            if base.__name__ in ("GameStateBase", "GameModeBase", "Actor"):
                break
    except Exception as error:  # noqa: BLE001
        names.append(f"(읽지 못함: {error})")
    return names


def step_reparent():
    parent = unreal.load_class(None, NEW_PARENT)
    if not parent:
        raise RuntimeError(f"부모 클래스 없음: {NEW_PARENT} — 빌드 확인")
    bp = unreal.load_asset(GAME_STATE_BP)
    if not bp:
        raise RuntimeError(f"BP 로드 실패: {GAME_STATE_BP}")

    info = {"path": GAME_STATE_BP, "before": parent_chain(bp.generated_class())}
    already = unreal.MathLibrary.class_is_child_of(bp.generated_class(), parent)
    info["reparented"] = not already
    if not already:
        unreal.BlueprintEditorLibrary.reparent_blueprint(bp, parent)
        info["saved"] = B.compile_and_save(bp)
        bp = unreal.load_asset(GAME_STATE_BP)

    generated = bp.generated_class()
    info["after"] = parent_chain(generated)
    if not unreal.MathLibrary.class_is_child_of(generated, parent):
        raise RuntimeError(f"부모 교체가 반영되지 않았다: {info['after']}")

    component = unreal.get_default_object(generated).get_editor_property(COMPONENT_PROPERTY)
    if not component:
        raise RuntimeError("BP 의 CDO 에 체인 컴포넌트가 없다")
    info["component"] = component.get_class().get_name()
    info["values"] = {}
    for name in COMPONENT_VALUES:
        try:
            info["values"][name] = export(component.get_editor_property(name))
        except Exception as error:  # noqa: BLE001
            info["values"][name] = f"(읽지 못함: {error})"
    return info


def step_probe_game_mode():
    """읽기만 — 레이드 GameMode BP 가 이 GameState BP 를 지정하는지."""
    cls = unreal.load_class(None, f"{GAME_MODE_BP}.{GAME_MODE_BP.rsplit('/', 1)[1]}_C")
    if not cls:
        raise RuntimeError(f"GameMode BP 클래스 없음: {GAME_MODE_BP}")
    game_state_class = unreal.get_default_object(cls).get_editor_property("game_state_class")
    info = {"path": GAME_MODE_BP, "game_state_class": game_state_class.get_path_name() if game_state_class else None}
    expected = f"{GAME_STATE_BP}.{GAME_STATE_BP.rsplit('/', 1)[1]}_C"
    info["points_at_raid_game_state"] = info["game_state_class"] == expected
    if not info["points_at_raid_game_state"]:
        raise RuntimeError(f"GameMode 의 GameStateClass 가 {expected} 가 아니다: {info['game_state_class']}")
    return info


def main():
    steps = (("reparent", step_reparent), ("game_mode", step_probe_game_mode))
    for name, fn in steps:
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
            break
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"CHAIN_BURST_ASSETS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
