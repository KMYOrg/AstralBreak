"""실행 중인 에디터를 저장 없이 종료 — 자동화 세션에서 내가 띄운 에디터를 내릴 때.
    python Tools/ue_exec.py Tools/scripts/quit_editor.py
"""
import unreal

print("QUIT_REQUESTED")
unreal.SystemLibrary.quit_editor()
