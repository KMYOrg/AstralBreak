"""에디터 안에서 Automation 테스트 실행 — 결과는 read_automation_results.py로 읽는다.
    python Tools/ue_exec.py Tools/scripts/run_automation_tests.py
필터는 아래 TEST_FILTER. 비동기 실행이라 큐잉만 하고 반환한다. 명령 수신 여부는 로그의 LogAutomationCommandLine 줄로 확인.
"""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

TEST_FILTER = "AstralBreak.InputFacing"

world = None
try:
    world = unreal.EditorLevelLibrary.get_editor_world()
except Exception as ex:
    print("NO_EDITOR_WORLD", ex)

unreal.SystemLibrary.execute_console_command(world, f"Automation RunTests {TEST_FILTER}")
print(f"QUEUED Automation RunTests {TEST_FILTER} world={world}")
