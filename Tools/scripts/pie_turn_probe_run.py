"""제자리 회전 PIE 프로브 드라이버 — 에디터 밖(일반 python)에서 pie_aim_probe 의 단계를 차례로 보낸다.

    python Tools/scripts/pie_turn_probe_run.py [turn_yaw=90] [record_seconds=3.5] [extra_turns=0] [turn_interval=0.6] [spin]

begin(PIE) → arm(라이플 전환 + AimHold 30초) → record(틱마다 RootYawOffset 등 수집) → turn(컨트롤러 Yaw +turn_yaw) → record_seconds 대기 → dump → end.
기대: turn 직후 off ≈ −turn_yaw · kind=Right90(양수 회전) → wants=True → idleturn=TurnInPlaceRotation → off 가 0 으로 수렴하며 fin=True →
TurnInPlaceRecovery → Idle. off 가 반대로 커지면(−180 쪽) FAstralTurnInPlaceState::SelectKind 부호를 뒤집어야 한다.
"""
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

PROBE = ROOT / "scripts" / "pie_aim_probe.py"
SRC = PROBE.read_text(encoding="utf-8")


def step(name: str, turn_yaw: float) -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r"^TURN_YAW = .*$", f"TURN_YAW = {turn_yaw}", src, count=1, flags=re.M)
    src = re.sub(r'^CONSOLE_CMD = ".*?"', lambda _: f'CONSOLE_CMD = {os.environ.get("PROBE_CONSOLE", "")!r}', src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def main() -> int:
    turn_yaw = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    record_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.5
    extra_turns = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    turn_interval = float(sys.argv[4]) if len(sys.argv) > 4 else 0.6   # 회전 구간(~0.56초) 안에 다시 돌리려면 0.3 이하
    spin = len(sys.argv) > 5 and sys.argv[5] == "spin"   # 점프 대신 틱마다 2도씩 점진 회전(마우스 흉내)
    step("begin", turn_yaw)
    time.sleep(10.0)
    step("arm", turn_yaw)
    if os.environ.get("PROBE_CONSOLE"):
        step("console", turn_yaw)   # 진단 전용 튜닝 변형 — PIE 인스턴스에만
    step("record", turn_yaw)
    # AimHold 는 2초 — 사격 직후 바로 돌려야 회전이 조준 중(누적 모드)에 들어간다 (실측: arm→sample→turn 순서는 2초를 넘겨 aim=False 상태에서 돌았다)
    step("fire", turn_yaw)
    step("spin" if spin else "turn", turn_yaw)
    # 기록 중 조준 유지 — AimHold 2초보다 짧은 간격으로 사격 GA 재활성화. extra_turns 만큼 0.7초 간격으로 같은 방향으로 더 돈다(연속 회전 재진입 검사)
    t_end = time.time() + record_seconds
    turns_left = extra_turns
    while time.time() < t_end:
        time.sleep(turn_interval if turns_left > 0 else 0.6)
        step("fire", turn_yaw)
        if turns_left > 0:
            turns_left -= 1
            step("spin" if spin else "turn", turn_yaw)
    step("dump", turn_yaw)
    step("sample", turn_yaw)
    step("end", turn_yaw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
