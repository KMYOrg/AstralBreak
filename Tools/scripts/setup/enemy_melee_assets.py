"""M3 단위 A 적 애셋 생성 (설계 Docs/Design/m3-enemy-ai.md §8 ⑦) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

만드는 것 (전부 새 애셋 — 이미 있으면 건너뛰고 덮어쓰지 않는다):
    /Game/AbilitySystem/Abilities/Enemy/GA_Enemy_MeleeAttack        UAstralGA_Enemy_MeleeAttack 의 BP 자식 (값은 C++ 기본값 그대로)
    /Game/AbilitySystem/AbilitySets/Enemy/DA_AbilitySet_Enemy_Melee GA_Death + GA_Enemy_MeleeAttack (루프 GA 는 넣지 않는다)
    /Game/AI/Enemy/BP_EnemyController_Melee                         AAstralEnemyController 자식, 트리 = ST_Enemy_Melee
    /Game/Characters/Enemy/BP_Enemy_Melee                           AAstralCombatCharacter 자식, 메시는 BP_TargetDummy 와 같은 것(임시)

먼저 있어야 하는 것: /Game/AI/Enemy/ST_Enemy_Melee (state-tree-mcp 로 저작).
결과는 Tools/mcp/results/enemy_melee_assets.json 에 쓴다(Saved 는 읽을 수 없다). 값은 CDO 에 쓴 뒤 컴파일한다.
"""
import json
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B

importlib.reload(B)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_melee_assets.json"

GA_DIR = "/Game/AbilitySystem/Abilities/Enemy"
GA_NAME = "GA_Enemy_MeleeAttack"
GA_DEATH_CLASS = "/Game/AbilitySystem/Abilities/GA_Death.GA_Death_C"
SET_DIR = "/Game/AbilitySystem/AbilitySets/Enemy"
SET_NAME = "DA_AbilitySet_Enemy_Melee"
EXISTING_SET = "/Game/AbilitySystem/AbilitySets/Enemy/DA_AbilitySet_Enemy"
TREE_PATH = "/Game/AI/Enemy/ST_Enemy_Melee"
CONTROLLER_PATH = "/Game/AI/Enemy/BP_EnemyController_Melee"
ENEMY_PATH = "/Game/Characters/Enemy/BP_Enemy_Melee"
DUMMY_CLASS = "/Game/Characters/Enemy/BP_TargetDummy.BP_TargetDummy_C"

YAW_RATE = 360.0

eal = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "steps": {}, "errors": []}


def export(value):
    try:
        return value.export_text()
    except Exception:
        return str(value)


def step_ga():
    path = f"{GA_DIR}/{GA_NAME}"
    info = {"path": path}
    if eal.does_asset_exist(path):
        info["skipped"] = "exists"
        return info

    parent = unreal.load_class(None, "/Script/AstralBreak.AstralGA_Enemy_MeleeAttack")
    if not parent:
        raise RuntimeError("AstralGA_Enemy_MeleeAttack 클래스 없음 — 빌드 확인")

    # 에디터의 '게임플레이 어빌리티 블루프린트' 와 같은 종류로 만든다 (팩토리가 없으면 일반 BP)
    factory_class = getattr(unreal, "GameplayAbilitiesBlueprintFactory", None)
    bp = None
    if factory_class:
        factory = factory_class()
        factory.set_editor_property("parent_class", parent)
        bp = asset_tools.create_asset(GA_NAME, GA_DIR, getattr(unreal, "GameplayAbilityBlueprint", None), factory)
        info["factory"] = "GameplayAbilitiesBlueprintFactory"
    if not bp:
        bp = B.create_bp(path, parent)
        info["factory"] = "plain blueprint"

    info["saved"] = B.compile_and_save(bp)
    info["class"] = bp.generated_class().get_path_name()
    info["asset_class"] = bp.get_class().get_name()
    return info


def step_ability_set():
    path = f"{SET_DIR}/{SET_NAME}"
    info = {"path": path}

    # 참고 — 더미용 세트의 모양
    existing = unreal.load_asset(EXISTING_SET)
    if existing:
        info["reference_set"] = {
            "abilities": [export(e) for e in existing.get_editor_property("granted_gameplay_abilities")],
            "effects": [export(e) for e in existing.get_editor_property("granted_gameplay_effects")],
            "attributes": [export(e) for e in existing.get_editor_property("granted_attributes")],
        }

    if eal.does_asset_exist(path):
        info["skipped"] = "exists"
        return info

    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.AstralAbilitySet)
    asset = asset_tools.create_asset(SET_NAME, SET_DIR, unreal.AstralAbilitySet, factory)
    if not asset:
        raise RuntimeError("AbilitySet 생성 실패")

    entries = []
    for ability_class in (GA_DEATH_CLASS, f"{GA_DIR}/{GA_NAME}.{GA_NAME}_C"):
        if not unreal.load_class(None, ability_class):
            raise RuntimeError(f"어빌리티 클래스 없음: {ability_class}")
        entry = unreal.AstralAbilitySet_GameplayAbility()
        # EditDefaultsOnly 구조체는 소유 애셋 없이 set_editor_property 가 막힌다 — import_text 로 채운다
        entry.import_text("(Ability=\"/Script/Engine.BlueprintGeneratedClass'%s'\",AbilityLevel=1)" % ability_class)
        entries.append(entry)
    asset.set_editor_property("granted_gameplay_abilities", entries)

    info["saved"] = eal.save_loaded_asset(asset, False)
    info["abilities"] = [export(e) for e in asset.get_editor_property("granted_gameplay_abilities")]
    return info


def step_controller():
    info = {"path": CONTROLLER_PATH}
    if eal.does_asset_exist(CONTROLLER_PATH):
        info["skipped"] = "exists"
        return info

    tree = unreal.load_asset(TREE_PATH)
    if not tree:
        raise RuntimeError(f"트리 없음: {TREE_PATH} — state-tree-mcp 로 먼저 저작")

    bp = B.create_bp(CONTROLLER_PATH, "/Script/AstralBreak.AstralEnemyController")
    cdo = unreal.get_default_object(bp.generated_class())
    component = cdo.get_editor_property("state_tree_component")
    reference = component.get_editor_property("state_tree_ref")
    try:
        reference.set_editor_property("state_tree", tree)
        info["ref_method"] = "set_editor_property"
    except Exception as error:  # noqa: BLE001
        reference.import_text("(StateTree=\"/Script/StateTreeModule.StateTree'%s.%s'\")" % (TREE_PATH, TREE_PATH.rsplit("/", 1)[1]))
        info["ref_method"] = f"import_text ({error})"
    component.set_editor_property("state_tree_ref", reference)

    info["saved"] = B.compile_and_save(bp)
    saved_cdo = unreal.get_default_object(bp.generated_class())
    info["state_tree_ref"] = export(saved_cdo.get_editor_property("state_tree_component").get_editor_property("state_tree_ref"))
    return info


def step_enemy():
    info = {"path": ENEMY_PATH}
    if eal.does_asset_exist(ENEMY_PATH):
        info["skipped"] = "exists"
        return info

    controller_bp = unreal.load_asset(CONTROLLER_PATH)
    ability_set = unreal.load_asset(f"{SET_DIR}/{SET_NAME}")
    dummy_class = unreal.load_class(None, DUMMY_CLASS)
    if not controller_bp or not ability_set or not dummy_class:
        raise RuntimeError("컨트롤러 BP · AbilitySet · BP_TargetDummy 중 없는 것이 있다")

    bp = B.create_bp(ENEMY_PATH, "/Script/AstralBreak.AstralCombatCharacter")
    cdo = unreal.get_default_object(bp.generated_class())
    dummy = unreal.get_default_object(dummy_class)

    # 메시 — 더미와 같은 것(임시). 적 메시 · 애니는 단위 D
    source_mesh = dummy.get_editor_property("mesh")
    target_mesh = cdo.get_editor_property("mesh")
    copied, failed = {}, []
    for name in ("skeletal_mesh_asset", "animation_mode", "anim_class", "override_materials", "relative_location", "relative_rotation", "relative_scale3d"):
        try:
            value = source_mesh.get_editor_property(name)
            target_mesh.set_editor_property(name, value)
            copied[name] = str(value)
        except Exception as error:  # noqa: BLE001
            failed.append(f"mesh.{name}: {error}")
    info["mesh_copied"] = copied

    failed += B.set_defaults(bp, {
        "auto_possess_ai": unreal.AutoPossessAI.PLACED_IN_WORLD_OR_SPAWNED,
        "ai_controller_class": controller_bp.generated_class(),
        "ability_sets": [ability_set],
    })

    # 회전 — 이동 방향이 아니라 컨트롤러 회전을 따른다(추격 = 경로 방향, 예고 = 타깃 포커스). 베이스 기본값은 바꾸지 않는다
    movement = cdo.get_editor_property("character_movement")
    for name, value in (("orient_rotation_to_movement", False), ("use_controller_desired_rotation", True),
                        ("rotation_rate", unreal.Rotator(pitch=0.0, yaw=YAW_RATE, roll=0.0))):
        try:
            movement.set_editor_property(name, value)
        except Exception as error:  # noqa: BLE001
            failed.append(f"character_movement.{name}: {error}")

    info["defaults_failed"] = failed
    info["saved"] = B.compile_and_save(bp)

    saved_cdo = unreal.get_default_object(bp.generated_class())
    saved_movement = saved_cdo.get_editor_property("character_movement")
    saved_mesh = saved_cdo.get_editor_property("mesh")
    info["readback"] = {
        "auto_possess_ai": str(saved_cdo.get_editor_property("auto_possess_ai")),
        "ai_controller_class": str(saved_cdo.get_editor_property("ai_controller_class")),
        "ability_sets": [str(a.get_path_name()) for a in saved_cdo.get_editor_property("ability_sets")],
        "orient_rotation_to_movement": saved_movement.get_editor_property("orient_rotation_to_movement"),
        "use_controller_desired_rotation": saved_movement.get_editor_property("use_controller_desired_rotation"),
        "rotation_rate": str(saved_movement.get_editor_property("rotation_rate")),
        "skeletal_mesh_asset": str(saved_mesh.get_editor_property("skeletal_mesh_asset")),
        "anim_class": str(saved_mesh.get_editor_property("anim_class")),
    }
    info["dummy_reference"] = {
        "ability_sets": [str(a.get_path_name()) for a in dummy.get_editor_property("ability_sets")],
        "auto_possess_ai": str(dummy.get_editor_property("auto_possess_ai")),
        "ai_controller_class": str(dummy.get_editor_property("ai_controller_class")),
    }
    return info


def main():
    for name, fn in (("ga", step_ga), ("ability_set", step_ability_set), ("controller", step_controller), ("enemy", step_enemy)):
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
            break
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"ENEMY_MELEE_ASSETS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
