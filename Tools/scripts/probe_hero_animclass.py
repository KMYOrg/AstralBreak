import sys
# 진단(읽기만) — BP_Hero_Vesper 메시 컴포넌트의 기본 AnimClass·메시와 DA_CD_Vesper 의 Mesh·AnimInstanceClass 를 비교한다.
# RefreshAppearance 는 "메시가 다를 때만" AnimInstanceClass 를 적용하므로, BP 메시가 이미 같은 메시면 CD 의 ABP 가 적용되지 않는다는 가설 확인용
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

log = unreal.log
bp = unreal.load_asset("/Game/Characters/Hero/BP_Hero_Vesper")
cd = unreal.load_asset("/Game/Characters/Hero/Data/DA_CD_Vesper")
cls = bp.generated_class()
cdo = unreal.get_default_object(cls)
mesh = cdo.get_editor_property("mesh")
log(f"PROBE_BP_MESH: {mesh.get_editor_property('skeletal_mesh_asset')}")
log(f"PROBE_BP_ANIMCLASS: {mesh.get_editor_property('anim_class')}")
log(f"PROBE_BP_ANIMMODE: {mesh.get_editor_property('animation_mode')}")
log(f"PROBE_CD_MESH: {cd.get_editor_property('mesh')}")
log(f"PROBE_CD_ANIMCLASS: {cd.get_editor_property('anim_instance_class')}")
log("PROBE_DONE")
