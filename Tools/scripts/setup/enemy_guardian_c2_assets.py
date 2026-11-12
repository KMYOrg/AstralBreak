"""M3 단위 C2 수호병 애셋 (설계 Docs/Design/m3-enemy-ai.md §10 C2) — 에디터 안에서 돈다. enemy_guardian_assets.py(C1) 뒤에 돌린다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것 (MCP 로 만든다 — 호출 기록은 설계 문서 §10 'C2 구현 결과'):
    /Game/Characters/Enemy/Guardian/AM_Guardian_Combo · AM_Guardian_Heavy            anim-graph-mcp create_anim_montage (Attack5 · Attack6)
    /Game/Characters/Enemy/Guardian/AM_Guardian_HitF · HitB · HitL · HitR · AM_Guardian_Stagger   같은 도구 (GetHitF/B/L/R · Rage)
    /Game/AI/Enemy/ST_Enemy_Guardian                                                 state-tree-mcp

이 스크립트가 하는 것 (GA · GE · 컨트롤러 BP 는 없으면 만들고, 값은 돌릴 때마다 다시 쓴다 — 아래 잠정값을 고쳐 다시 돌리면 된다. 팩 · 마네킹 애셋은 읽기만 한다):
    공격 몽타주 2개에 노티파이 — 트랙 'Combat' 을 비우고 다시 단다: 타격(GameplayEvent.Enemy.AttackHit) + 휘두름 시작(GameplayEvent.Enemy.AttackSwing)
    GA_Guardian_Combo · GA_Guardian_Heavy   UAstralGA_Enemy_MeleeAttack 의 BP 자식 — asset tag · 공격 중 태그 · 피해 태그 · 준비 재생 속도
    GA_Guardian_HitReact · GA_Guardian_Stagger · GE_Enemy_Exposed
    DA_AbilitySet_Enemy_Guardian            GA_Death + 위 GA 4개로 바꾼다 (GA_Guardian_Attack 은 뺀다 — 애셋은 남는다)
    /Game/AI/Enemy/BP_EnemyController_Guardian   AAstralEnemyController 자식, 트리 = ST_Enemy_Guardian, 위협 값은 BP_EnemyController_Melee 와 같게
    BP_Enemy_Guardian                       AIControllerClass 만 위 컨트롤러로

준비는 느리게 · 휘두름은 원래 속도로: 몽타주의 애니 세그먼트는 파이썬에 나오지 않아(SlotAnimTracks) 나눌 수 없다. 대신 휘두름 시작 노티파이를 달고
공격 GA 가 그 앞은 MontagePlayRate(느림), 뒤는 SwingPlayRate 로 튼다. 준비 재생 속도는 '예고 길이' 에서 아래 prepare_rate() 가 계산한다.

값은 전부 잠정이다(§0-4). 결과는 Tools/mcp/results/enemy_guardian_c2_assets.json 에 쓴다(Saved 는 읽을 수 없다).
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

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_guardian_c2_assets.json"

GUARDIAN_DIR = "/Game/Characters/Enemy/Guardian"
AI_DIR = "/Game/AI/Enemy"
SET_PATH = f"{GUARDIAN_DIR}/DA_AbilitySet_Enemy_Guardian"
ENEMY_PATH = "/Game/Characters/Enemy/BP_Enemy_Guardian"
TREE_PATH = f"{AI_DIR}/ST_Enemy_Guardian"
CONTROLLER_PATH = f"{AI_DIR}/BP_EnemyController_Guardian"
MELEE_CONTROLLER_CLASS = f"{AI_DIR}/BP_EnemyController_Melee.BP_EnemyController_Melee_C"  # 위협 값의 기준(읽기만)
GA_DEATH_CLASS = "/Game/AbilitySystem/Abilities/GA_Death.GA_Death_C"

HIT_EVENT_TAG = "GameplayEvent.Enemy.AttackHit"
SWING_EVENT_TAG = "GameplayEvent.Enemy.AttackSwing"
NOTIFY_TRACK = "Combat"

# ─── 잠정값 ───
# 공격 2종. hit_times · swing_start 는 몽타주 안의 시각(초, 재생 속도 1 기준 — 근거는 설계 문서 'C1 구현 결과 — 잰 값' 과 'C2 구현 결과').
# telegraph = 발동부터 첫 타격까지(초). 준비 구간(0 ~ swing_start)만 느리게 틀어 이 길이를 맞춘다
ATTACKS = {
    "Combo": {
        "montage": "AM_Guardian_Combo",
        "ga": "GA_Guardian_Combo",
        "ability_tag": "Ability.Enemy.Attack.Combo",
        "hit_times": [0.43, 0.95, 1.30],
        "swing_start": 0.27,        # 오른손을 뒤로 다 뺀 시각(전방 −105 cm · 속도 최소 274 cm/s — 0.267초)
        "telegraph": 1.0,
        "facing_track": 0.7,        # 예고 앞부분 타깃 추적 — 나머지 0.3초는 방향 고정
        "damage": 8.0,              # 타당
        "damage_tags": [],
    },
    "Heavy": {
        "montage": "AM_Guardian_Heavy",
        "ga": "GA_Guardian_Heavy",
        "ability_tag": "Ability.Enemy.Attack.Heavy",
        "hit_times": [0.35],
        "swing_start": 0.20,        # 손을 머리 위로 든 시각
        "telegraph": 1.2,
        "facing_track": 0.9,
        "damage": 30.0,
        "damage_tags": ["Damage.Type.Unguardable"],  # 가드 불가 · 패링 가능
    },
}
SWING_PLAY_RATE = 1.0        # 휘두름 구간 — 원래 속도
STAGGER_RECOVERY = 0.0       # 경직은 GA_Guardian_Stagger 가 맡는다
TRACE_START_OFFSET = 45.0    # 캡슐 표면에서 시작
TRACE_DISTANCE = 100.0       # 45 + 100 + 65 = 앞 210 cm — 선 거리(ST_Enemy_Guardian 의 AcceptableRadius 75 → 중심 간 약 125 cm)에서 닿는다
TRACE_RADIUS = 65.0
DRAW_TELEGRAPH_DEBUG = True  # 준비 동작과 판정 범위가 맞는지 눈으로 본 뒤 끈다
ATTACK_COMMON_TAGS = ["Ability.Attack"]              # 사망 · 경직의 취소가 찾는 부모 태그
ATTACKING_STATE_TAGS = ["State.Enemy.Attacking"]     # 공격 중 — 피격 반응이 버틴다

HIT_REACT = {
    "ga": "GA_Guardian_HitReact",
    "montages": {"front_montage": "AM_Guardian_HitF", "back_montage": "AM_Guardian_HitB", "left_montage": "AM_Guardian_HitL", "right_montage": "AM_Guardian_HitR"},
    "min_interval": 2.5,
}
STAGGER = {
    "ga": "GA_Guardian_Stagger",
    "montage": "AM_Guardian_Stagger",
    "duration": 2.0,
}
EXPOSED_GE = "GE_Enemy_Exposed"
EXPOSED_MULTIPLIER = 1.5     # 경직 동안 받는 피해 배율 (IncomingDamageMultiplier × 이 값)
THREAT_PROPS = ("damage_weight", "damage_window", "hold_time", "retarget_cooldown", "exclude_time")

eal = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "steps": {}, "errors": []}


def export(value):
    try:
        return value.export_text()
    except Exception:
        return str(value)


def tag_container(names):
    """이름 목록 → FGameplayTagContainer. 등록되지 않은 태그면 예외(M.tag 가 검사한다)."""
    for name in names:
        M.tag(name)
    container = unreal.GameplayTagContainer()
    container.import_text("(GameplayTags=(%s))" % ",".join('(TagName="%s")' % name for name in names))
    return container


def prepare_rate(spec):
    """준비 구간의 재생 속도 — swing_start / (예고 − 휘두름 구간에서 첫 타격까지 걸리는 시간)."""
    swing_to_hit = (min(spec["hit_times"]) - spec["swing_start"]) / SWING_PLAY_RATE
    prepare_seconds = spec["telegraph"] - swing_to_hit
    if spec["swing_start"] <= 0.0 or swing_to_hit < 0.0 or prepare_seconds <= 0.0:
        raise RuntimeError(f"{spec['ga']}: swing_start {spec['swing_start']} · 첫 타격 {min(spec['hit_times'])} · 예고 {spec['telegraph']} 로는 준비 속도를 낼 수 없다")
    return spec["swing_start"] / prepare_seconds


def ensure_bp(name, directory, parent_path, ability=False):
    """없으면 만든다. (bp, 만들었는가)"""
    path = f"{directory}/{name}"
    if eal.does_asset_exist(path):
        return unreal.load_asset(path), False
    parent = unreal.load_class(None, parent_path)
    if not parent:
        raise RuntimeError(f"부모 클래스 없음: {parent_path} — 빌드 확인")
    bp = None
    factory_class = getattr(unreal, "GameplayAbilitiesBlueprintFactory", None) if ability else None
    if factory_class:
        # 에디터의 '게임플레이 어빌리티 블루프린트' 와 같은 종류로 만든다 — enemy_guardian_assets.py 와 같은 방법
        factory = factory_class()
        factory.set_editor_property("parent_class", parent)
        bp = asset_tools.create_asset(name, directory, getattr(unreal, "GameplayAbilityBlueprint", None), factory)
    if not bp:
        bp = B.create_bp(path, parent)
    return bp, True


def write_defaults(bp, values, readback_extra=()):
    info = {"defaults_failed": B.set_defaults(bp, values), "saved": B.compile_and_save(bp)}
    cdo = unreal.get_default_object(bp.generated_class())
    info["class"] = bp.generated_class().get_path_name()
    info["readback"] = {name: export(cdo.get_editor_property(name)) for name in list(values) + list(readback_extra)}
    return info


def load_montage(name):
    montage = unreal.load_asset(f"{GUARDIAN_DIR}/{name}")
    if not montage:
        raise RuntimeError(f"몽타주 없음: {GUARDIAN_DIR}/{name} — anim-graph-mcp create_anim_montage 로 먼저 만든다")
    return montage


def step_montage_notifies():
    info = {}
    for key, spec in ATTACKS.items():
        montage = load_montage(spec["montage"])
        length = montage.get_play_length()
        entry = {"removed": M.clear_track(montage, NOTIFY_TRACK)}
        for time in [spec["swing_start"]] + spec["hit_times"]:
            if not 0.0 < time < length:
                raise RuntimeError(f"{spec['montage']}: 노티파이 시각 {time} 이 몽타주 길이 {length:.3f} 밖이거나 0 이다(0초 노티파이는 첫 틱에 빠진다)")
        M.add_notify(montage, NOTIFY_TRACK, spec["swing_start"], M.NOTIFY_CLASSES["GameplayEvent"], event_tag=M.tag(SWING_EVENT_TAG))
        for time in spec["hit_times"]:
            M.add_notify(montage, NOTIFY_TRACK, time, M.NOTIFY_CLASSES["GameplayEvent"], event_tag=M.tag(HIT_EVENT_TAG))
        entry["saved"] = M.save(montage)
        entry["describe"] = M.describe(montage)
        entry["notifies"] = M.describe_notifies(montage)
        info[key] = entry
    return info


def step_attack_abilities():
    info = {}
    for key, spec in ATTACKS.items():
        bp, created = ensure_bp(spec["ga"], GUARDIAN_DIR, "/Script/AstralBreak.AstralGA_Enemy_MeleeAttack", ability=True)
        rate = prepare_rate(spec)
        values = {
            "attack_montage": load_montage(spec["montage"]),
            "montage_play_rate": rate,
            "swing_play_rate": SWING_PLAY_RATE,
            "facing_track_duration": spec["facing_track"],
            "base_damage": spec["damage"],
            "stagger_recovery": STAGGER_RECOVERY,
            "trace_start_offset": TRACE_START_OFFSET,
            "trace_distance": TRACE_DISTANCE,
            "trace_radius": TRACE_RADIUS,
            "draw_telegraph_debug": DRAW_TELEGRAPH_DEBUG,
            "damage_tags": tag_container(spec["damage_tags"]),
            # asset tag — 트리의 ActivateAbility Task 가 스펙을 찾는 키. 부모의 Ability.Enemy.Attack.Melee 를 이 공격의 태그로 바꾼다
            "ability_tags": tag_container(ATTACK_COMMON_TAGS + [spec["ability_tag"]]),
            "activation_owned_tags": tag_container(ATTACKING_STATE_TAGS),
        }
        entry = write_defaults(bp, values, ("hit_event_tag", "telegraph_duration"))
        entry["created"] = created
        entry["prepare_rate"] = round(rate, 4)
        entry["prepare_seconds"] = round(spec["swing_start"] / rate, 3)
        info[key] = entry
    return info


def step_hit_react():
    bp, created = ensure_bp(HIT_REACT["ga"], GUARDIAN_DIR, "/Script/AstralBreak.AstralGA_Enemy_HitReact", ability=True)
    values = {prop: load_montage(name) for prop, name in HIT_REACT["montages"].items()}
    values["min_interval"] = HIT_REACT["min_interval"]
    info = write_defaults(bp, values, ("ability_tags", "activation_owned_tags", "activation_blocked_tags"))
    info["created"] = created
    return info


def step_exposed_effect():
    bp, created = ensure_bp(EXPOSED_GE, GUARDIAN_DIR, "/Script/GameplayAbilities.GameplayEffect")
    modifier = unreal.GameplayModifierInfo()
    # EditDefaultsOnly 구조체는 소유 애셋 없이 set_editor_property 가 막힌다 — import_text 로 채운다(AbilitySet 항목과 같은 방법)
    modifier.import_text(
        '(Attribute=(AttributeName="IncomingDamageMultiplier",Attribute=/Script/AstralBreak.AstralHealthSet:IncomingDamageMultiplier,'
        'AttributeOwner="/Script/CoreUObject.Class\'/Script/AstralBreak.AstralHealthSet\'"),'
        'ModifierOp=MultiplyAdditive,ModifierMagnitude=(MagnitudeCalculationType=ScalableFloat,ScalableFloatMagnitude=(Value=%f)))' % EXPOSED_MULTIPLIER)
    info = write_defaults(bp, {
        "duration_policy": unreal.GameplayEffectDurationType.INFINITE,  # 경직 GA 가 걸고 뗀다
        "modifiers": [modifier],
    })
    info["created"] = created
    return info


def step_stagger():
    exposed = unreal.load_class(None, f"{GUARDIAN_DIR}/{EXPOSED_GE}.{EXPOSED_GE}_C")
    if not exposed:
        raise RuntimeError("GE_Enemy_Exposed 클래스 없음")
    bp, created = ensure_bp(STAGGER["ga"], GUARDIAN_DIR, "/Script/AstralBreak.AstralGA_Enemy_Stagger", ability=True)
    info = write_defaults(bp, {
        "stagger_montage": load_montage(STAGGER["montage"]),
        "stagger_duration": STAGGER["duration"],
        "exposed_effect_class": exposed,
    }, ("ability_tags", "activation_owned_tags", "activation_blocked_tags"))
    info["created"] = created
    return info


def step_ability_set():
    asset = unreal.load_asset(SET_PATH)
    if not asset:
        raise RuntimeError(f"AbilitySet 없음: {SET_PATH} — enemy_guardian_assets.py 를 먼저 돌린다")
    info = {"path": SET_PATH, "before": [export(e) for e in asset.get_editor_property("granted_gameplay_abilities")]}

    names = [spec["ga"] for spec in ATTACKS.values()] + [HIT_REACT["ga"], STAGGER["ga"]]
    entries = []
    for ability_class in [GA_DEATH_CLASS] + [f"{GUARDIAN_DIR}/{name}.{name}_C" for name in names]:
        if not unreal.load_class(None, ability_class):
            raise RuntimeError(f"어빌리티 클래스 없음: {ability_class}")
        entry = unreal.AstralAbilitySet_GameplayAbility()
        entry.import_text("(Ability=\"/Script/Engine.BlueprintGeneratedClass'%s'\",AbilityLevel=1)" % ability_class)
        entries.append(entry)
    asset.set_editor_property("granted_gameplay_abilities", entries)

    info["saved"] = eal.save_loaded_asset(asset, False)
    info["abilities"] = [export(e) for e in asset.get_editor_property("granted_gameplay_abilities")]
    return info


def step_controller():
    tree = unreal.load_asset(TREE_PATH)
    if not tree:
        raise RuntimeError(f"트리 없음: {TREE_PATH} — state-tree-mcp 로 먼저 저작")
    melee_class = unreal.load_class(None, MELEE_CONTROLLER_CLASS)
    if not melee_class:
        raise RuntimeError("BP_EnemyController_Melee 없음")

    bp, created = ensure_bp("BP_EnemyController_Guardian", AI_DIR, "/Script/AstralBreak.AstralEnemyController")
    info = {"path": CONTROLLER_PATH, "created": created}
    cdo = unreal.get_default_object(bp.generated_class())

    # 트리 참조 — enemy_melee_assets.py 와 같은 방법
    component = cdo.get_editor_property("state_tree_component")
    reference = component.get_editor_property("state_tree_ref")
    try:
        reference.set_editor_property("state_tree", tree)
        info["ref_method"] = "set_editor_property"
    except Exception as error:  # noqa: BLE001
        reference.import_text("(StateTree=\"/Script/StateTreeModule.StateTree'%s.%s'\")" % (TREE_PATH, TREE_PATH.rsplit("/", 1)[1]))
        info["ref_method"] = f"import_text ({error})"
    component.set_editor_property("state_tree_ref", reference)

    # 위협 값 — 마네킹 컨트롤러 BP 의 값을 읽어 그대로 넣는다(읽기만)
    melee_threat = unreal.get_default_object(melee_class).get_editor_property("threat_component")
    threat = cdo.get_editor_property("threat_component")
    failed = []
    for name in THREAT_PROPS:
        try:
            threat.set_editor_property(name, melee_threat.get_editor_property(name))
        except Exception as error:  # noqa: BLE001
            failed.append(f"threat_component.{name}: {error}")
    info["defaults_failed"] = failed

    info["saved"] = B.compile_and_save(bp)
    saved_cdo = unreal.get_default_object(bp.generated_class())
    saved_threat = saved_cdo.get_editor_property("threat_component")
    info["state_tree_ref"] = export(saved_cdo.get_editor_property("state_tree_component").get_editor_property("state_tree_ref"))
    info["threat"] = {name: saved_threat.get_editor_property(name) for name in THREAT_PROPS}
    info["melee_threat"] = {name: melee_threat.get_editor_property(name) for name in THREAT_PROPS}
    return info


def step_enemy():
    bp = unreal.load_asset(ENEMY_PATH)
    controller_bp = unreal.load_asset(CONTROLLER_PATH)
    if not bp or not controller_bp:
        raise RuntimeError("BP_Enemy_Guardian 또는 BP_EnemyController_Guardian 없음")
    info = {"path": ENEMY_PATH, "before": str(unreal.get_default_object(bp.generated_class()).get_editor_property("ai_controller_class"))}
    info["defaults_failed"] = B.set_defaults(bp, {"ai_controller_class": controller_bp.generated_class()})
    info["saved"] = B.compile_and_save(bp)
    saved_cdo = unreal.get_default_object(bp.generated_class())
    info["ai_controller_class"] = str(saved_cdo.get_editor_property("ai_controller_class"))
    info["ability_sets"] = [str(a.get_path_name()) for a in saved_cdo.get_editor_property("ability_sets")]
    return info


def main():
    steps = (("montage_notifies", step_montage_notifies), ("attack_abilities", step_attack_abilities), ("hit_react", step_hit_react),
             ("exposed_effect", step_exposed_effect), ("stagger", step_stagger), ("ability_set", step_ability_set),
             ("controller", step_controller), ("enemy", step_enemy))
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
    unreal.log(f"ENEMY_GUARDIAN_C2_ASSETS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
