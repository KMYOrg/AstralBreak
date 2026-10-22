"""조준 자세 PIE 프로브 — 제자리 회전 오프셋(RootYawOffset) × AimOffset Pitch 조합에서 두 손 거리·가슴·목 기울기를 구간별로 잰다.

    python Tools/scripts/pie_pose_probe_run.py [pitch=40] [offset=45] [spin_pitch=-40]

begin → arm → record(기록 콜백이 0.8초마다 사격해 조준 유지) → 구간마다 (자세 · mark · 대기) → 끝에 점진 연속 회전(spin_pitch 로 내려다본 채 360°) → dump → end.
구간: 오프셋 0 / −offset(오른쪽으로 offset 만큼 돈 뒤) / +offset 각각에서 Pitch 0 · −pitch · +pitch.
오프셋은 턴 임계(50) 아래라 턴 클립 없이 유지된다 — AimYaw = −오프셋으로 상체가 되돌아 조준하는 상태.
출력 PIE_POSE(구간 평균) · PIE_WORST(조준 중 최악) · PIE_S(타임라인). 같은 Pitch 에서 오프셋 0 구간과 비교해
옆 기울기·총 Pitch 가 오프셋·Pitch 둘 다 0 이 아닐 때만 틀어지면 AO 가산의 축이 루트 회전으로 틀어진 것.
"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

SRC = (ROOT / "scripts" / "pie_aim_probe.py").read_text(encoding="utf-8")


def step(name: str, yaw: float = 0.0, pitch: float = 0.0, turn: float = 0.0, mark: str = "", spin_step: float = 2.0) -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    # 조준 유지는 기록 콜백이 0.8초마다 사격 — 단계(원격 실행) 지연이 쌓여도 AimHold 2초가 끊기지 않는다
    src = re.sub(r"^AUTO_FIRE = .*$", "AUTO_FIRE = 0.8", src, count=1, flags=re.M)
    src = re.sub(r"^AIM_YAW_OFF = .*$", f"AIM_YAW_OFF = {yaw}", src, count=1, flags=re.M)
    src = re.sub(r"^AIM_PITCH = .*$", f"AIM_PITCH = {pitch}", src, count=1, flags=re.M)
    src = re.sub(r"^TURN_YAW = .*$", f"TURN_YAW = {turn}", src, count=1, flags=re.M)
    src = re.sub(r"^SPIN_STEP = .*$", f"SPIN_STEP = {spin_step}", src, count=1, flags=re.M)
    src = re.sub(r'^MARK = ".*"', f'MARK = "{mark}"', src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def hold(label: str, pitch: float, seconds: float = 1.2) -> None:
    step("aim", 0.0, pitch)
    step("mark", mark=label)
    time.sleep(seconds)


def grid(prefix: str, pitch: float) -> None:
    for p, tag in ((0.0, "p0"), (-pitch, "pD"), (pitch, "pU"), (-1.5 * pitch, "pDD")):
        hold(f"{prefix}_{tag}", p)


def main() -> int:
    pitch = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
    offset = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
    spin_pitch = float(sys.argv[3]) if len(sys.argv) > 3 else -40.0
    step("begin")
    time.sleep(10.0)
    step("arm")
    step("record")
    time.sleep(0.5)
    grid("o0", pitch)
    # 오른쪽으로 offset 만큼 → RootYawOffset ≈ −offset (턴 임계 아래)
    step("aim", 0.0, 0.0)
    step("spin", turn=offset)
    time.sleep(0.6)
    grid(f"oR{int(offset)}", pitch)
    # 왼쪽으로 2×offset → RootYawOffset ≈ +offset
    step("aim", 0.0, 0.0)
    step("spin", turn=-2.0 * offset)
    time.sleep(0.8)
    grid(f"oL{int(offset)}", pitch)
    # 실전 재현 — 내려다본 채 점진 연속 회전(턴 클립 · 재진입 포함)
    step("aim", 0.0, spin_pitch)
    step("mark", mark="spin_start")
    step("spin", turn=360.0, spin_step=3.0)
    time.sleep(3.0)
    step("mark", mark="spin_end")
    time.sleep(0.5)
    step("dump")
    step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
