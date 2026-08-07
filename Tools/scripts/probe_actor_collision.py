"""배치된 엄폐 기둥 액터의 콜리전 프로파일 확인 — 읽기 전용."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

for a in eas.get_all_level_actors():
    if not a or not a.get_actor_label().startswith("SM_Cover_Pillar_00"):
        continue
    comp = a.get_component_by_class(unreal.StaticMeshComponent)
    if not comp:
        continue
    unreal.log(f"=== {a.get_actor_label()} ===")
    unreal.log(f"  collision_enabled = {comp.get_collision_enabled()}")
    unreal.log(f"  profile           = {comp.get_collision_profile_name()}")
    unreal.log(f"  object_type       = {comp.get_collision_object_type()}")
    unreal.log(f"  → Visibility  응답 = {comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)}")
    unreal.log(f"  → WorldStatic 응답 = {comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_WORLD_STATIC)}")
    unreal.log(f"  → Pawn        응답 = {comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)}")
    break
