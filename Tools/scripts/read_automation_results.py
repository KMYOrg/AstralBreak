"""에디터 안에서 자기 로그를 읽어 Automation 결과 줄만 출력 — run_automation_tests.py 뒤에 폴링용.
    python Tools/ue_exec.py Tools/scripts/read_automation_results.py
가장 최근에 갱신된 Saved/Logs/AstralBreak*.log(동시 실행 인스턴스는 _2 등 접미사)를 고른다.
"""
import sys, glob, os, re
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

TEST_FILTER = "AstralBreak.InputFacing"
log_dir = unreal.Paths.project_log_dir()
candidates = glob.glob(os.path.join(log_dir, "AstralBreak*.log"))
if not candidates:
    print("NO_LOG")
    raise SystemExit

latest = max(candidates, key=os.path.getmtime)
print("LOG", latest)

pattern = re.compile(r"Test Completed\. Result=\{(\w+)\} Name=\{([^}]*)\} Path=\{(" + re.escape(TEST_FILTER) + r"[^}]*)\}")
errors = []
results = []
automation_lines = []
with open(latest, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        m = pattern.search(line)
        if m:
            results.append((m.group(3), m.group(1)))
        elif "LogAutomationController: Error" in line or "Automation Test Failed" in line:
            errors.append(line.rstrip())
        if ("LogAutomationCommandLine" in line or "LogAutomationController" in line) and "LogPython" not in line:
            automation_lines.append(line.rstrip()[:200])

for path, result in results:
    print("RESULT", result, path)
for e in errors[-20:]:
    print("ERRLINE", e)
# 진단 — 명령이 수신됐는지, 어디까지 진행됐는지
for a in automation_lines[-12:]:
    print("AUTO", a)
print("COUNT", len(results))
