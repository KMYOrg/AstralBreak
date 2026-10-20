import sys
# 진단 — PIE 에서 히어로를 찾아 조준 상태 파이프라인(태그 → AnimInstance bIsAiming → 회전 모드 → 레이어 링크)을 읽는다.
# 모드는 소스 첫 줄 뒤 STEP 상수로 고른다: begin(PIE 시작) · arm(라이플 스타일 태그 + AimHold GE 30초 적용) · sample(값 읽기) · end(PIE 종료)
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

STEP = "sample"

log = unreal.log
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
RIFLE_LAYERS = "/Game/Animation/Hero/ABP_HeroLayers_Rifle"
PROPS = ("bIsAiming", "AimYaw", "AimPitch", "Speed", "MovementDirection", "bHasMovementInput")


SWITCH_GA = "/Game/AbilitySystem/Abilities/GA_Hero_SwitchCombatStyle.GA_Hero_SwitchCombatStyle_C"
FIRE_GA = "/Game/AbilitySystem/Abilities/GA_Hero_BasicAttack_Projectile.GA_Hero_BasicAttack_Projectile_C"


def owned_tags(asc):
    # Python 에선 FGameplayTag 를 이름으로 만들 수 없다(TagName 읽기 전용) — ASC(IGameplayTagAssetInterface) 의 보유 태그를 문자열로 읽는다
    return unreal.GameplayTagLibrary.get_debug_string_from_gameplay_tag_container(unreal.GameplayTagLibrary.get_owned_gameplay_tags(asc))


def heroes():
    world = UES.get_game_world()
    if not world:
        raise RuntimeError("PIE_NO_WORLD")
    return world, unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralCharacter_Hero)


def dump_anim(label, anim):
    if not anim:
        log(f"PIE_{label}: None")
        return
    vals = {p: anim.get_editor_property(p) for p in PROPS}
    log(f"PIE_{label}: {anim.get_class().get_name()} {vals}")


if STEP == "begin":
    LES.editor_request_begin_play()
    log("PIE_BEGIN_REQUESTED")

elif STEP == "end":
    LES.editor_request_end_play()
    log("PIE_END_REQUESTED")

else:
    world, actors = heroes()
    log(f"PIE_HEROES: {len(actors)}")
    for a in actors:
        asc = a.get_astral_ability_system_component()   # AbilitySystemBlueprintLibrary 는 Python 에 노출되지 않는다
        mesh = a.get_editor_property("mesh")
        cmc = a.get_editor_property("character_movement")
        if STEP == "arm":
            # 실제 경로 그대로 — 전환 GA(근접 → 원거리) 와 원거리 기본 공격 GA 를 클래스로 활성화 (입력 없이). 공격 GA 가 서버에서 AimHold GE 를 적용해야 한다
            switch_cls = unreal.load_class(None, SWITCH_GA)
            fire_cls = unreal.load_class(None, FIRE_GA)
            sw = asc.try_activate_ability_by_class(switch_cls, True)
            log(f"PIE_ARM_SWITCH: {sw} tags={owned_tags(asc)}")
            fi = asc.try_activate_ability_by_class(fire_cls, True)
            log(f"PIE_ARM_FIRE: {fi} tags={owned_tags(asc)}")
        log(f"PIE_ACTOR: {a.get_name()} role={a.get_local_role()} asc={asc is not None}")
        if asc:
            log(f"PIE_TAGS: {owned_tags(asc)} active_ge={len(asc.get_active_effects(unreal.GameplayEffectQuery()))}")
        log(f"PIE_ROT: orient={cmc.get_editor_property('orient_rotation_to_movement')} ctrl_yaw={a.get_editor_property('use_controller_rotation_yaw')}")
        main_anim = mesh.get_anim_instance()
        dump_anim("MAIN", main_anim)
        rifle_cls = unreal.load_asset(RIFLE_LAYERS).generated_class()
        linked = mesh.get_linked_anim_layer_instance_by_class(rifle_cls)
        dump_anim("LINKED_RIFLE", linked)
        if main_anim:
            try:
                log(f"PIE_STATE: Locomotions={main_anim.get_current_state_name(0)}")
            except Exception as e:  # noqa: BLE001
                log(f"PIE_STATE: n/a ({e})")
    log("PIE_PROBE_DONE")
