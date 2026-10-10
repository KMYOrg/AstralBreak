"""에디터 원격 실행 연결 프로브 — 에디터가 떴는지, 어떤 빌드인지, 7단계 클래스가 로드되는지 출력.
    python Tools/ue_exec.py Tools/scripts/probe_editor.py
"""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

print("PROJECT", unreal.Paths.get_project_file_path())
print("ENGINE", unreal.SystemLibrary.get_engine_version())
print("BUILD_CONFIG", str(unreal.SystemLibrary.get_build_configuration()))
for cls_path in ("/Script/AstralBreak.AstralAnimNotifyState_InputFacing",
                 "/Script/AstralBreak.AstralRootMotionModifier_InputFacing"):
    print("CLASS", cls_path, "OK" if unreal.load_class(None, cls_path) else "MISSING")
print("PROBE_DONE")
