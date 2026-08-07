"""빌드 전 안전 점검 — 저장 안 된 맵/애셋이 있는지 확인만 한다 (읽기 전용)."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

dirty_maps = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
dirty_content = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()

unreal.log(f"현재 레벨: {les.get_current_level().get_outer().get_name()}")
unreal.log(f"저장 안 된 맵: {len(dirty_maps)}개")
for p in dirty_maps:
    unreal.log(f"  [MAP-DIRTY] {p.get_name()}")

unreal.log(f"저장 안 된 컨텐츠 애셋: {len(dirty_content)}개")
for p in dirty_content[:20]:
    unreal.log(f"  [ASSET-DIRTY] {p.get_name()}")
if len(dirty_content) > 20:
    unreal.log(f"  ... 외 {len(dirty_content) - 20}개")
