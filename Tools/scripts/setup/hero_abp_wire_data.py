import sys
# 히어로 ABP 전환 배선 — DA_EF_Rifle.AnimLayerClass = ABP_HeroLayers_Rifle_C · DA_CD_Vesper.AnimInstanceClass = ABP_Hero_Combat_C (멱등)
# REVERT = True 로 바꿔 실행하면 원래대로(AnimLayerClass 비움 · ABP_Hero_Base_C). 실행은 ue_exec 브릿지 경유 (주의: UE ExecuteFile 모드가
# 소스 앞부분의 ".p"+"y" 문자열을 파일 경로로 오인하므로 주석에 확장자를 쓰지 말 것)
# 선행: 2026-10-19 C++ 빌드(UAstralEquipmentFamily.AnimLayerClass) 로 뜬 에디터 · ABP_Hero_Combat / ABP_HeroLayers_Rifle 이 build_hero_combat 으로 생성·저장돼 있어야 한다
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

REVERT = False

EAL = unreal.EditorAssetLibrary
log = unreal.log

FAMILY_RIFLE = "/Game/Equipment/Weapon/DA_EF_Rifle"
CHAR_DEF = "/Game/Characters/Hero/Data/DA_CD_Vesper"
HERO_BP = "/Game/Characters/Hero/BP_Hero_Vesper"   # 메시 컴포넌트 기본 AnimClass — 로비 없는 테스트 맵(CharacterId 없음)에선 CD 가 아니라 이 값이 쓰인다
LAYERS_RIFLE = "/Game/Animation/Hero/ABP_HeroLayers_Rifle"
ABP_COMBAT = "/Game/Animation/Hero/ABP_Hero_Combat"
ABP_BASE = "/Game/Animation/Hero/ABP_Hero_Base"


def generated_class(path):
    bp = unreal.load_asset(path)
    if not bp:
        raise RuntimeError(f"WIRE_FAIL: load {path}")
    cls = bp.generated_class()
    if not cls:
        raise RuntimeError(f"WIRE_FAIL: {path} has no generated class (컴파일 필요)")
    return cls


family = unreal.load_asset(FAMILY_RIFLE)
cd = unreal.load_asset(CHAR_DEF)
if not family or not cd:
    raise RuntimeError(f"WIRE_FAIL: load {FAMILY_RIFLE} / {CHAR_DEF}")

layer_cls = None if REVERT else generated_class(LAYERS_RIFLE)
abp_cls = generated_class(ABP_BASE if REVERT else ABP_COMBAT)

if family.get_editor_property("anim_layer_class") != layer_cls:
    family.set_editor_property("anim_layer_class", layer_cls)
    if not EAL.save_loaded_asset(family, False):
        raise RuntimeError(f"WIRE_FAIL: save {FAMILY_RIFLE}")
    log(f"WIRE_SET: {FAMILY_RIFLE}.AnimLayerClass = {layer_cls}")
else:
    log(f"WIRE_EXISTS: {FAMILY_RIFLE}.AnimLayerClass")

if cd.get_editor_property("anim_instance_class") != abp_cls:
    cd.set_editor_property("anim_instance_class", abp_cls)
    if not EAL.save_loaded_asset(cd, False):
        raise RuntimeError(f"WIRE_FAIL: save {CHAR_DEF}")
    log(f"WIRE_SET: {CHAR_DEF}.AnimInstanceClass = {abp_cls}")
else:
    log(f"WIRE_EXISTS: {CHAR_DEF}.AnimInstanceClass")

# 히어로 BP 메시 컴포넌트의 기본 AnimClass — RefreshAppearanceFromLoadout 은 CharacterId 가 있을 때만 CD 를 적용하므로(로비 경유),
# 단독 테스트 맵에서는 이 기본값이 실제로 쓰인다 (2026-10-19 PIE 실측: 이것이 ABP_Hero_Base 라 레이어 링크가 무효였다)
hero_bp = unreal.load_asset(HERO_BP)
if not hero_bp:
    raise RuntimeError(f"WIRE_FAIL: load {HERO_BP}")
hero_cdo = unreal.get_default_object(hero_bp.generated_class())
hero_mesh = hero_cdo.get_editor_property("mesh")
if hero_mesh.get_editor_property("anim_class") != abp_cls:
    hero_mesh.set_editor_property("anim_class", abp_cls)
    hero_mesh.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_BLUEPRINT)
    if not EAL.save_loaded_asset(hero_bp, False):
        raise RuntimeError(f"WIRE_FAIL: save {HERO_BP}")
    log(f"WIRE_SET: {HERO_BP} Mesh.AnimClass = {abp_cls}")
else:
    log(f"WIRE_EXISTS: {HERO_BP} Mesh.AnimClass")

log("WIRE_DONE")
