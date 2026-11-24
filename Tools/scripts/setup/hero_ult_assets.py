"""M4 단위 A 오의 애셋 + 단위 D 전용 몽타주 (설계 Docs/Design/m4-ult-chain.md §6 단위 A · 단위 D) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것: UAstralGA_Hero_Ult · InputTag.Ult 가 들어간 C++ 빌드.

이 스크립트가 하는 것 (없으면 만들고, 있으면 값만 다시 쓴다 — 여러 번 돌려도 같다):
    /Game/Input/Actions/IA_Ult                  IA_Jump 를 복제한 bool 액션
    /Game/Input/Mappings/IMC_Default            IA_Ult 에 키 하나씩 — 아래 후보 가운데 아직 안 쓰는 첫 키(키보드 · 게임패드)
    /Game/Input/DA_Input_Hero_Default           AbilityInputActions 에 (IA_Ult, InputTag.Ult)
    AM_Vesper_Sickle_Ult1 (ULT_MONTAGE)          노티파이 — 타격 이벤트 · 락온 방향 워프 · 폰 충돌 · 타격 이펙트. 이 스크립트의 트랙만 비우고 다시 단다
    /Game/AbilitySystem/Abilities/GA_Hero_Ult   UAstralGA_Hero_Ult 의 BP 자식 — 전용 몽타주 · 타격 이벤트 GameplayEvent.Ult.Hit · 쓰는 동안의 스타일(근접)
    /Game/AbilitySystem/AbilitySets/Hero/DA_AbilitySet_Vesper   (GA_Hero_Ult, InputTag.Ult) 항목을 덧붙인다 — 기존 항목은 그대로

시퀀스 · 몽타주 자체는 애니 생성 파이프라인(단위 D)이 만들어 승격한 것이다 — 여기서 만들지 않는다.
결과는 Tools/mcp/results/hero_ult_assets.json 에 쓴다(Saved 는 읽을 수 없다).
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

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/hero_ult_assets.json"

IA_SRC = "/Game/Input/Actions/IA_Jump"
IA_DST = "/Game/Input/Actions/IA_Ult"
IMC = "/Game/Input/Mappings/IMC_Default"
CFG = "/Game/Input/DA_Input_Hero_Default"
INPUT_TAG = "InputTag.Ult"

ABILITY_DIR = "/Game/AbilitySystem/Abilities"
GA_NAME = "GA_Hero_Ult"
GA_PARENT = "/Script/AstralBreak.AstralGA_Hero_Ult"
MARK_FINISHER_CLASS = f"{ABILITY_DIR}/GA_Hero_MarkFinisher.GA_Hero_MarkFinisher_C"
SET_PATH = "/Game/AbilitySystem/AbilitySets/Hero/DA_AbilitySet_Vesper"  # 영웅의 세트 — 오의는 무기가 아니라 영웅의 것이다(강화 공격은 무기 세트가 준다)

# ─── 잠정값 ───
ULT_MONTAGE = "/Game/Animation/Hero/Vesper/Sickle/Actions/AM_Vesper_Sickle_Ult1"  # 단위 D 전용 몽타주 (None = 강화 공격의 몽타주를 빌린다 — 단위 A 의 임시)
HIT_EVENT_TAG = "GameplayEvent.Ult.Hit"
ULT_COMBAT_STYLE = "State.CombatStyle.Melee"       # 쓰는 동안 드는 무기(낫) — 원거리에서 써도 낫으로 바꿔 들고 끝나면 되돌린다
# 몽타주 노티파이(초) — 날 끝이 땅에 닿는 시각 1.27, 앞으로 나가는 루트 모션은 0.25 ~ 1.5
HIT_TIME = 1.27
FACING_WARP = ("Ult.Facing", 0.0, 0.4)             # 이름(GA 의 FacingWarpTargetName) · 시작 · 길이 — 달려 나가기 전에 돈다
PAWN_COLLISION = (0.0, 1.7)                        # 적에게 닿으면 멈춘다
HIT_FX = "/Game/Assets/SciFi_VFX/Niagara/Explosion/NS_Explosion_EMP"   # 잠정 — 타격 순간 땅에 하나
HIT_FX_OFFSET = (0.0, 240.0, 5.0)                  # 메시 컴포넌트 공간(앞 = +Y) — 날이 찍히는 자리
HIT_FX_SCALE = 1.0
BASE_DAMAGE = 200.0
TRACE_START_OFFSET = 50.0
TRACE_DISTANCE = 400.0
TRACE_RADIUS = 150.0
KEYBOARD_CANDIDATES = ["R", "G", "T", "V", "X", "Z"]
GAMEPAD_CANDIDATES = ["Gamepad_LeftThumbstick", "Gamepad_DPad_Up", "Gamepad_DPad_Down"]

eal = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
result = {"ok": False, "steps": {}, "errors": []}


def export(value):
    try:
        return value.export_text()
    except Exception:
        return str(value)


def key_name(mapping):
    return str(mapping.get_editor_property("key").get_editor_property("key_name"))


def make_key(name):
    try:
        return unreal.Key(key_name=name)
    except Exception:
        key = unreal.Key()
        key.set_editor_property("key_name", name)
        return key


def step_input_action():
    M.tag(INPUT_TAG)  # 미등록이면 여기서 멈춘다 — C++ 미빌드 / 옛 바이너리
    created = not eal.does_asset_exist(IA_DST)
    action = eal.duplicate_asset(IA_SRC, IA_DST) if created else unreal.load_asset(IA_DST)
    if not action:
        raise RuntimeError(f"IA 복제 실패: {IA_SRC} -> {IA_DST}")
    action.set_editor_property("value_type", unreal.InputActionValueType.BOOLEAN)
    action.set_editor_property("triggers", [])
    action.set_editor_property("modifiers", [])
    return {"path": IA_DST, "created": created, "saved": eal.save_loaded_asset(action, False)}


def step_mapping():
    action = unreal.load_asset(IA_DST)
    context = unreal.load_asset(IMC)
    if not context:
        raise RuntimeError(f"IMC 로드 실패: {IMC}")

    # 5.7: 매핑은 DefaultKeyMappings.Mappings 에 산다 (lockon_input 과 같은 방법)
    mappings = list(context.get_editor_property("default_key_mappings").get_editor_property("mappings"))
    used = {key_name(m) for m in mappings}
    mine = [key_name(m) for m in mappings if m.get_editor_property("action") == action]
    info = {"before": {key_name(m): str(m.get_editor_property("action").get_name()) for m in mappings if m.get_editor_property("action")}, "already": mine, "mapped": []}

    for candidates in (KEYBOARD_CANDIDATES, GAMEPAD_CANDIDATES):
        if any(name in mine for name in candidates):
            continue  # 이 종류의 키는 이미 달려 있다
        free = [name for name in candidates if name not in used]
        if not free:
            info.setdefault("no_free_key", []).append(candidates)
            continue
        context.map_key(action, make_key(free[0]))
        info["mapped"].append(free[0])

    # MapKey 는 패키지를 더티로 표시하지 않는다 — 강제 저장
    info["saved"] = eal.save_asset(IMC, only_if_is_dirty=False)
    after = unreal.load_asset(IMC).get_editor_property("default_key_mappings").get_editor_property("mappings")
    info["keys"] = [key_name(m) for m in after if m.get_editor_property("action") == action]
    if not info["keys"]:
        raise RuntimeError("IA_Ult 에 달린 키가 없다")
    return info


def step_input_config():
    action = unreal.load_asset(IA_DST)
    config = unreal.load_asset(CFG)
    if not config:
        raise RuntimeError(f"InputConfig 로드 실패: {CFG}")
    entries = list(config.get_editor_property("ability_input_actions"))
    info = {"before": [export(e) for e in entries]}
    if any(e.get_editor_property("input_action") == action for e in entries):
        info["added"] = False
    else:
        # 구조체의 프로퍼티가 EditDefaultsOnly 라 import_text 로 채운다
        entry = unreal.AstralInputAction()
        entry.import_text(f'(InputAction="{action.get_path_name()}",InputTag=(TagName="{INPUT_TAG}"))')
        entries.append(entry)
        config.set_editor_property("ability_input_actions", entries)
        info["added"] = True
    info["saved"] = eal.save_loaded_asset(config, False)
    info["after"] = [export(e) for e in unreal.load_asset(CFG).get_editor_property("ability_input_actions")]
    return info


def step_montage():
    """전용 몽타주의 노티파이 — 이 스크립트가 소유한 트랙 넷만 비우고 다시 단다."""
    if not ULT_MONTAGE:
        return {"skipped": "전용 몽타주 없음"}
    montage = unreal.load_asset(ULT_MONTAGE)
    if not montage:
        raise RuntimeError(f"오의 몽타주 없음: {ULT_MONTAGE}")
    length = montage.get_play_length()
    info = {"path": montage.get_path_name(), "length": round(length, 4), "cleared": {t: M.clear_track(montage, t) for t in ("Combat", "Facing", "PawnCollision", "FX")}}

    sequence = unreal.load_asset(ULT_MONTAGE.replace("/AM_", "/AS_"))
    info["root_motion"] = {"before": bool(sequence.get_editor_property("enable_root_motion"))}
    if not info["root_motion"]["before"]:
        sequence.set_editor_property("enable_root_motion", True)
        info["root_motion"]["saved"] = eal.save_loaded_asset(sequence, False)
    info["root_motion"]["after"] = bool(sequence.get_editor_property("enable_root_motion"))

    M.add_notify(montage, "Combat", HIT_TIME, M.NOTIFY_CLASSES["GameplayEvent"], event_tag=M.tag(HIT_EVENT_TAG))
    name, start, duration = FACING_WARP
    M.add_motion_warping_window(montage, "Facing", start, duration, name)
    M.add_pawn_collision_window(montage, "PawnCollision", PAWN_COLLISION[0], PAWN_COLLISION[1], "StopOnHit")
    if HIT_FX:
        system = unreal.load_asset(HIT_FX)
        if not system:
            raise RuntimeError(f"이펙트 없음: {HIT_FX}")
        M.add_notify(montage, "FX", HIT_TIME, "/Script/NiagaraAnimNotifies.AnimNotify_PlayNiagaraEffect", template=system, attached=False,
                     location_offset=unreal.Vector(*HIT_FX_OFFSET), scale=unreal.Vector(HIT_FX_SCALE, HIT_FX_SCALE, HIT_FX_SCALE))
    info["saved"] = M.save(montage)
    info["notifies"] = M.describe_notifies(montage)
    info["describe"] = M.describe(montage)
    for key in ("blend_in", "blend_out"):
        info[key] = round(float(montage.get_editor_property(key).get_editor_property("blend_time")), 3)
    return info


def step_ability():
    if ULT_MONTAGE:
        montage = unreal.load_asset(ULT_MONTAGE)
        source = ULT_MONTAGE
    else:
        finisher = unreal.load_class(None, MARK_FINISHER_CLASS)
        if not finisher:
            raise RuntimeError(f"강화 공격 클래스 없음: {MARK_FINISHER_CLASS}")
        montage = unreal.get_default_object(finisher).get_editor_property("attack_montage")
        source = "GA_Hero_MarkFinisher.attack_montage"
    if not montage:
        raise RuntimeError(f"오의 몽타주 없음 ({source})")

    path = f"{ABILITY_DIR}/{GA_NAME}"
    created = not eal.does_asset_exist(path)
    if created:
        parent = unreal.load_class(None, GA_PARENT)
        if not parent:
            raise RuntimeError(f"부모 클래스 없음: {GA_PARENT} — 빌드 확인")
        bp = None
        factory_class = getattr(unreal, "GameplayAbilitiesBlueprintFactory", None)
        if factory_class:
            # 에디터의 '게임플레이 어빌리티 블루프린트' 와 같은 종류로 만든다 (enemy_guardian_c2_assets 와 같은 방법)
            factory = factory_class()
            factory.set_editor_property("parent_class", parent)
            bp = asset_tools.create_asset(GA_NAME, ABILITY_DIR, getattr(unreal, "GameplayAbilityBlueprint", None), factory)
        if not bp:
            bp = B.create_bp(path, parent)
    else:
        bp = unreal.load_asset(path)

    values = {
        "ult_montage": montage,
        "hit_event_tag": M.tag(HIT_EVENT_TAG),
        "base_damage": BASE_DAMAGE,
        "trace_start_offset": TRACE_START_OFFSET,
        "trace_distance": TRACE_DISTANCE,
        "trace_radius": TRACE_RADIUS,
        "ult_combat_style": M.tag(ULT_COMBAT_STYLE),
        "facing_warp_target_name": FACING_WARP[0],
    }
    info = {"path": path, "created": created, "montage_source": source, "montage": montage.get_path_name(),
            "defaults_failed": B.set_defaults(bp, values), "saved": B.compile_and_save(bp)}
    cdo = unreal.get_default_object(bp.generated_class())
    info["class"] = bp.generated_class().get_path_name()
    info["readback"] = {name: export(cdo.get_editor_property(name)) for name in values}
    for name in ("cost_gameplay_effect_class", "ability_tags", "activation_owned_tags", "activation_blocked_tags", "cancel_abilities_with_tag", "block_abilities_with_tag"):
        try:
            info["readback"][name] = export(cdo.get_editor_property(name))
        except Exception as error:  # noqa: BLE001
            info["readback"][name] = f"(읽지 못함: {error})"
    info["montage_notifies"] = M.describe_notifies(montage)
    info["montage_length"] = round(montage.get_play_length(), 3)
    return info


def step_ability_set():
    ability_class = f"{ABILITY_DIR}/{GA_NAME}.{GA_NAME}_C"
    if not unreal.load_class(None, ability_class):
        raise RuntimeError(f"어빌리티 클래스 없음: {ability_class}")

    asset = unreal.load_asset(SET_PATH)
    if not asset:
        raise RuntimeError(f"어빌리티 세트 없음: {SET_PATH}")
    entries = list(asset.get_editor_property("granted_gameplay_abilities"))
    info = {"path": SET_PATH, "before": [export(e) for e in entries]}
    # 클래스 경로 전체로 본다 — 이름만 보면 GA_Hero_UltGainOnDamaged 가 걸린다
    if any(ability_class in text for text in info["before"]):
        info["added"] = False
    else:
        entry = unreal.AstralAbilitySet_GameplayAbility()
        entry.import_text("(Ability=\"/Script/Engine.BlueprintGeneratedClass'%s'\",AbilityLevel=1,InputTag=(TagName=\"%s\"))" % (ability_class, INPUT_TAG))
        entries.append(entry)
        asset.set_editor_property("granted_gameplay_abilities", entries)
        info["added"] = True
    info["saved"] = eal.save_loaded_asset(asset, False)
    info["after"] = [export(e) for e in unreal.load_asset(SET_PATH).get_editor_property("granted_gameplay_abilities")]
    return info


def step_probe_other_abilities():
    """읽기만 — 오의의 Cancel / Block 이 찾는 asset tag 가 다른 히어로 어빌리티 BP 에 실제로 달려 있는지 본다."""
    info = {}
    for name in ("GA_Hero_Dodge", "GA_Hero_Defend", "GA_Hero_BasicAttack_Melee", "GA_Hero_MarkFinisher", "GA_Hero_SwitchCombatStyle"):
        cls = unreal.load_class(None, f"{ABILITY_DIR}/{name}.{name}_C")
        if not cls:
            info[name] = "(없음)"
            continue
        try:
            info[name] = export(unreal.get_default_object(cls).get_editor_property("ability_tags"))
        except Exception as error:  # noqa: BLE001
            info[name] = f"(읽지 못함: {error})"
    return info


def main():
    steps = (("input_action", step_input_action), ("mapping", step_mapping), ("input_config", step_input_config), ("montage", step_montage),
             ("ability", step_ability), ("ability_set", step_ability_set), ("other_abilities", step_probe_other_abilities))
    # 인자로 단계 이름을 주면 그것만 — -ExecutePythonScript="<이 파일> montage ability"
    wanted = [arg for arg in sys.argv[1:] if arg in dict(steps)]
    for name, fn in steps:
        if wanted and name not in wanted:
            continue
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
            break
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"HERO_ULT_ASSETS {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
