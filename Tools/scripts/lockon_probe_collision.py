"""락온 LOS 채널 도입 전 점검 — 히어로/더미 BP의 캡슐·메시 콜리전 프리셋 확인 (읽기 전용).

Custom 프리셋 컴포넌트는 새 채널(AstralTargetLOS)에 채널 기본값(Block)을 받는다.
Pawn/CharacterMesh 프리셋이면 DefaultEngine.ini의 EditProfiles(Ignore)가 적용된다.
"""
import unreal

BP_PATHS = [
    "/Game/Characters/Hero/BP_Hero_Vesper",
    "/Game/Characters/Enemy/BP_TargetDummy",
]

VIS = unreal.CollisionChannel.ECC_VISIBILITY


def dump_component(label, comp):
    if not comp:
        unreal.log(f"  {label}: (없음)")
        return
    unreal.log(f"  {label}: profile={comp.get_collision_profile_name()} "
               f"enabled={comp.get_collision_enabled()} "
               f"objType={comp.get_collision_object_type()} "
               f"Visibility={comp.get_collision_response_to_channel(VIS)}")


for path in BP_PATHS:
    bp = unreal.load_asset(path)
    if not bp:
        unreal.log_error(f"로드 실패: {path}")
        continue
    gen_class = bp.generated_class()
    cdo = unreal.get_default_object(gen_class)
    unreal.log(f"=== {path.split('/')[-1]} ({gen_class.get_name()}) ===")
    dump_component("Capsule", cdo.get_component_by_class(unreal.CapsuleComponent))
    dump_component("Mesh   ", cdo.get_component_by_class(unreal.SkeletalMeshComponent))

# 레벨의 Custom 프리셋 스태틱 메시 — 새 채널에 기본 Block을 받는다 (지형이면 의도대로, 장식/볼륨이면 확인 필요)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
custom = []
for a in eas.get_all_level_actors():
    if not a:
        continue
    for comp in a.get_components_by_class(unreal.PrimitiveComponent):
        if comp.get_collision_profile_name() == "Custom" and comp.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION:
            custom.append(f"{a.get_actor_label()}/{comp.get_name()} Visibility={comp.get_collision_response_to_channel(VIS)}")
unreal.log(f"=== 레벨 Custom 프리셋 컴포넌트 {len(custom)}개 ===")
for line in custom[:40]:
    unreal.log(f"  {line}")
