"""M3 단위 C1 수호병 애셋 생성 (설계 Docs/Design/m3-enemy-ai.md §10 C1) — 에디터 안에서 돈다.

    떠 있는 에디터:  python Tools/ue_exec.py Tools/scripts/setup/enemy_guardian_assets.py
    또는:            UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것 (anim-graph-mcp 로 만든다 — 호출 기록은 설계 문서 §10 'C1 구현 결과'):
    /Game/Characters/Enemy/Guardian/BS_Guardian_Locomotion   create_blendspace (Idle1 — WalkF — Run, 축 Speed)
    /Game/Characters/Enemy/Guardian/ABP_Enemy_Guardian        create_animation_blueprint + apply_graph_operations
    /Game/Characters/Enemy/Guardian/AM_Guardian_Attack        create_anim_montage (공격 시퀀스 1개)

이 스크립트가 하는 것 (이미 있으면 건너뛴다 — 값만 다시 쓰려면 애셋을 지우고 돌린다. 팩 애셋 · 마네킹 애셋은 읽기만 한다):
    AM_Guardian_Attack 에 타격 노티파이(GameplayEvent.Enemy.AttackHit) — 트랙 'Combat' 을 비우고 다시 단다(멱등)
    /Game/Characters/Enemy/Guardian/GA_Guardian_Attack           UAstralGA_Enemy_MeleeAttack 의 BP 자식 — 몽타주 · 재생 속도 · 스윕 값
    /Game/Characters/Enemy/Guardian/DA_AbilitySet_Enemy_Guardian GA_Death + GA_Guardian_Attack
    /Game/Characters/Enemy/BP_Enemy_Guardian                     AAstralCombatCharacter 자식 — 메시 · ABP · 캡슐, 컨트롤러 · 이동 값은 BP_Enemy_Melee 와 같게

값은 전부 잠정이다(§0-4). 근거(잰 값)는 설계 문서의 'C1 구현 결과 — 잰 값' 표.
결과는 Tools/mcp/results/enemy_guardian_assets.json 에 쓴다(Saved 는 읽을 수 없다).
"""
import json
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B
import ab_montage as M

importlib.reload(B)
importlib.reload(M)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_guardian_assets.json"

GUARDIAN_DIR = "/Game/Characters/Enemy/Guardian"
MONTAGE_PATH = f"{GUARDIAN_DIR}/AM_Guardian_Attack"
ABP_PATH = f"{GUARDIAN_DIR}/ABP_Enemy_Guardian"
GA_NAME = "GA_Guardian_Attack"
SET_NAME = "DA_AbilitySet_Enemy_Guardian"
ENEMY_PATH = "/Game/Characters/Enemy/BP_Enemy_Guardian"  # SpawnEnemy 는 /Game/Characters/Enemy/ 바로 아래만 로드한다

MESH_PATH = "/Game/Assets/SciFi_Beast06/Mesh/SK_SciFi_Beast06_Skin1"
GA_DEATH_CLASS = "/Game/AbilitySystem/Abilities/GA_Death.GA_Death_C"
MELEE_ENEMY_CLASS = "/Game/Characters/Enemy/BP_Enemy_Melee.BP_Enemy_Melee_C"  # 이동 값 · 컨트롤러의 기준(읽기만)

HIT_EVENT_TAG = "GameplayEvent.Enemy.AttackHit"
HIT_NOTIFY_TRACK = "Combat"

# ─── 잠정값 — 잰 값에서 정했다(설계 문서 'C1 구현 결과') ───
HIT_TIMES = [0.45]           # 몽타주 안의 타격 시각(초, 재생 속도 1 기준). 여러 개면 연타. Attack1: 오른손 속도 최대 0.433 · 전방 최대 도달 0.467
MONTAGE_PLAY_RATE = 0.45     # 준비 동작 길이(= 예고) 맞춤 — 0.45 / 0.45 = 1.00초(단위 A 에서 확인한 예고 길이)
FACING_TRACK_DURATION = 0.7  # 예고 앞부분 타깃 추적(초) — 마네킹과 같은 값. 나머지 0.3초는 방향 고정
BASE_DAMAGE = 15.0           # 마네킹과 같은 값
TRACE_START_OFFSET = 45.0    # 캡슐 표면에서 시작
TRACE_DISTANCE = 165.0       # 45 + 165 + 75 = 앞 285 cm — 멈추는 거리(도달 판정 150 + 45 + 히어로 캡슐)에서 닿는다
TRACE_RADIUS = 75.0
DRAW_TELEGRAPH_DEBUG = True  # 준비 동작과 판정 범위가 맞는지 눈으로 본 뒤 끈다

CAPSULE_RADIUS = 45.0        # 메시 경계: 몸통 ±30 · 다리 ±52 (팔을 편 기준 자세의 폭 232 는 쓰지 않는다)
CAPSULE_HALF_HEIGHT = 100.0  # 메시 높이 208 (머리 181 · 등 208)
MESH_RELATIVE_Z = -100.0     # 메시 원점(발, z -0.3)을 캡슐 바닥으로
MESH_RELATIVE_YAW = -90.0    # 메시 전방(+Y) → 캡슐 +X
MAX_WALK_SPEED = 300.0       # Run 애니의 이동 속도(디딤 구간 발 속도). None = BP_Enemy_Melee 와 같은 값

PACK_ANIM_DIR = "/Game/Assets/SciFi_Beast06/Animations"
PACK_ANIMS = ["Idle1", "WalkF", "Run", "Death1", "Attack1", "Attack2", "Attack3", "Attack4", "Attack5", "Attack6"]

eal = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "steps": {}, "errors": []}


def export(value):
    try:
        return value.export_text()
    except Exception:
        return str(value)


def step_pack_facts():
    """팩 시퀀스에서 읽기만 한다 — 루트 모션 플래그(설계 문서의 '잰 값' 표에 쓴다)."""
    info = {}
    for name in PACK_ANIMS:
        sequence = unreal.load_asset(f"{PACK_ANIM_DIR}/Anim_SciFi_Beast06_{name}")
        if not sequence:
            info[name] = "missing"
            continue
        facts = {"length": round(sequence.get_play_length(), 4)}
        for prop in ("enable_root_motion", "force_root_lock", "root_motion_root_lock"):
            try:
                facts[prop] = str(sequence.get_editor_property(prop))
            except Exception as error:  # noqa: BLE001
                facts[prop] = f"unreadable ({error})"
        info[name] = facts
    return info


def step_montage_notify():
    info = {"path": MONTAGE_PATH}
    montage = unreal.load_asset(MONTAGE_PATH)
    if not montage:
        raise RuntimeError(f"몽타주 없음: {MONTAGE_PATH} — anim-graph-mcp create_anim_montage 로 먼저 만든다")

    info["removed"] = M.clear_track(montage, HIT_NOTIFY_TRACK)
    length = montage.get_play_length()
    for time in HIT_TIMES:
        if not 0.0 < time < length:
            raise RuntimeError(f"타격 시각 {time} 이 몽타주 길이 {length:.3f} 밖이거나 0 이다(0초 노티파이는 첫 틱에 빠진다)")
        M.add_notify(montage, HIT_NOTIFY_TRACK, time, M.NOTIFY_CLASSES["GameplayEvent"], event_tag=M.tag(HIT_EVENT_TAG))

    info["saved"] = M.save(montage)
    info["describe"] = M.describe(montage)
    info["notifies"] = M.describe_notifies(montage)
    return info


def step_ga():
    path = f"{GUARDIAN_DIR}/{GA_NAME}"
    info = {"path": path}
    if eal.does_asset_exist(path):
        info["skipped"] = "exists"
        return info

    parent = unreal.load_class(None, "/Script/AstralBreak.AstralGA_Enemy_MeleeAttack")
    montage = unreal.load_asset(MONTAGE_PATH)
    if not parent or not montage:
        raise RuntimeError("AstralGA_Enemy_MeleeAttack 클래스 또는 몽타주 없음")

    # 에디터의 '게임플레이 어빌리티 블루프린트' 와 같은 종류로 만든다 (팩토리가 없으면 일반 BP) — enemy_melee_assets.py 와 같은 방법
    factory_class = getattr(unreal, "GameplayAbilitiesBlueprintFactory", None)
    bp = None
    if factory_class:
        factory = factory_class()
        factory.set_editor_property("parent_class", parent)
        bp = asset_tools.create_asset(GA_NAME, GUARDIAN_DIR, getattr(unreal, "GameplayAbilityBlueprint", None), factory)
        info["factory"] = "GameplayAbilitiesBlueprintFactory"
    if not bp:
        bp = B.create_bp(path, parent)
        info["factory"] = "plain blueprint"

    values = {
        "attack_montage": montage,
        "montage_play_rate": MONTAGE_PLAY_RATE,
        "facing_track_duration": FACING_TRACK_DURATION,
        "base_damage": BASE_DAMAGE,
        "trace_start_offset": TRACE_START_OFFSET,
        "trace_distance": TRACE_DISTANCE,
        "trace_radius": TRACE_RADIUS,
        "draw_telegraph_debug": DRAW_TELEGRAPH_DEBUG,
    }
    info["defaults_failed"] = B.set_defaults(bp, values)
    info["saved"] = B.compile_and_save(bp)

    cdo = unreal.get_default_object(bp.generated_class())
    info["class"] = bp.generated_class().get_path_name()
    info["readback"] = {name: str(cdo.get_editor_property(name)) for name in list(values) + ["hit_event_tag", "telegraph_duration", "stagger_recovery"]}
    return info


def step_ability_set():
    path = f"{GUARDIAN_DIR}/{SET_NAME}"
    info = {"path": path}
    if eal.does_asset_exist(path):
        info["skipped"] = "exists"
        return info

    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.AstralAbilitySet)
    asset = asset_tools.create_asset(SET_NAME, GUARDIAN_DIR, unreal.AstralAbilitySet, factory)
    if not asset:
        raise RuntimeError("AbilitySet 생성 실패")

    entries = []
    for ability_class in (GA_DEATH_CLASS, f"{GUARDIAN_DIR}/{GA_NAME}.{GA_NAME}_C"):
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


def step_enemy():
    info = {"path": ENEMY_PATH}
    if eal.does_asset_exist(ENEMY_PATH):
        info["skipped"] = "exists"
        return info

    mesh_asset = unreal.load_asset(MESH_PATH)
    abp = unreal.load_asset(ABP_PATH)
    ability_set = unreal.load_asset(f"{GUARDIAN_DIR}/{SET_NAME}")
    melee_class = unreal.load_class(None, MELEE_ENEMY_CLASS)
    if not mesh_asset or not abp or not ability_set or not melee_class:
        raise RuntimeError("메시 · ABP · AbilitySet · BP_Enemy_Melee 중 없는 것이 있다")
    melee = unreal.get_default_object(melee_class)
    melee_movement = melee.get_editor_property("character_movement")

    bp = B.create_bp(ENEMY_PATH, "/Script/AstralBreak.AstralCombatCharacter")
    cdo = unreal.get_default_object(bp.generated_class())
    failed = []

    def put(target, label, name, value):
        try:
            target.set_editor_property(name, value)
        except Exception as error:  # noqa: BLE001
            failed.append(f"{label}.{name}: {error}")

    # 메시 · ABP
    mesh = cdo.get_editor_property("mesh")
    put(mesh, "mesh", "skeletal_mesh_asset", mesh_asset)
    put(mesh, "mesh", "animation_mode", unreal.AnimationMode.ANIMATION_BLUEPRINT)
    put(mesh, "mesh", "anim_class", abp.generated_class())
    put(mesh, "mesh", "relative_location", unreal.Vector(0.0, 0.0, MESH_RELATIVE_Z))
    put(mesh, "mesh", "relative_rotation", unreal.Rotator(pitch=0.0, yaw=MESH_RELATIVE_YAW, roll=0.0))

    # 캡슐 — 메시 경계에서 정한 값
    capsule = cdo.get_editor_property("capsule_component")
    put(capsule, "capsule", "capsule_half_height", CAPSULE_HALF_HEIGHT)
    put(capsule, "capsule", "capsule_radius", CAPSULE_RADIUS)

    # 컨트롤러 · AbilitySet — 컨트롤러(= 트리 · 어그로)는 마네킹과 같은 것을 그대로 쓴다
    failed += B.set_defaults(bp, {
        "auto_possess_ai": melee.get_editor_property("auto_possess_ai"),
        "ai_controller_class": melee.get_editor_property("ai_controller_class"),
        "ability_sets": [ability_set],
    })

    # 이동 — BP_Enemy_Melee 와 같은 값(§8 ⑤: 컨트롤러 회전을 따른다). 베이스 기본값은 바꾸지 않는다
    movement = cdo.get_editor_property("character_movement")
    for name in ("orient_rotation_to_movement", "use_controller_desired_rotation", "rotation_rate", "max_walk_speed"):
        value = melee_movement.get_editor_property(name)
        if name == "max_walk_speed" and MAX_WALK_SPEED is not None:
            value = MAX_WALK_SPEED
        put(movement, "character_movement", name, value)

    info["defaults_failed"] = failed
    info["saved"] = B.compile_and_save(bp)

    saved_cdo = unreal.get_default_object(bp.generated_class())
    saved_movement = saved_cdo.get_editor_property("character_movement")
    saved_mesh = saved_cdo.get_editor_property("mesh")
    saved_capsule = saved_cdo.get_editor_property("capsule_component")
    info["readback"] = {
        "auto_possess_ai": str(saved_cdo.get_editor_property("auto_possess_ai")),
        "ai_controller_class": str(saved_cdo.get_editor_property("ai_controller_class")),
        "ability_sets": [str(a.get_path_name()) for a in saved_cdo.get_editor_property("ability_sets")],
        "orient_rotation_to_movement": saved_movement.get_editor_property("orient_rotation_to_movement"),
        "use_controller_desired_rotation": saved_movement.get_editor_property("use_controller_desired_rotation"),
        "rotation_rate": str(saved_movement.get_editor_property("rotation_rate")),
        "max_walk_speed": saved_movement.get_editor_property("max_walk_speed"),
        "skeletal_mesh_asset": str(saved_mesh.get_editor_property("skeletal_mesh_asset")),
        "anim_class": str(saved_mesh.get_editor_property("anim_class")),
        "mesh_relative_location": str(saved_mesh.get_editor_property("relative_location")),
        "mesh_relative_rotation": str(saved_mesh.get_editor_property("relative_rotation")),
        "capsule_radius": saved_capsule.get_editor_property("capsule_radius"),
        "capsule_half_height": saved_capsule.get_editor_property("capsule_half_height"),
    }
    info["melee_reference"] = {
        "max_walk_speed": melee_movement.get_editor_property("max_walk_speed"),
        "rotation_rate": str(melee_movement.get_editor_property("rotation_rate")),
        "capsule_radius": melee.get_editor_property("capsule_component").get_editor_property("capsule_radius"),
    }
    return info


def main():
    for name, fn in (("pack_facts", step_pack_facts), ("montage_notify", step_montage_notify), ("ga", step_ga), ("ability_set", step_ability_set), ("enemy", step_enemy)):
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
            break
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"ENEMY_GUARDIAN_ASSETS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
