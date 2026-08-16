# 더티 패키지 전체 저장 후 에디터 종료 (리플렉션 변경 빌드를 위해)
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
print("SAVED_ALL")
unreal.SystemLibrary.quit_editor()
