"""총구 축 PIE 프로브 — 조준 중 총열(총구 소켓 +X)과 실제 발사 방향(총구 → 카메라 조준점, ResolveShot 과 같은 계산) 사이 각을 상황별로 잰다.

    python Tools/scripts/pie_muzzle_probe_run.py [sections=static,pitch,offset,turn,spin,strafe] [grip=current|socket_only|bone]

begin → arm → record(0.8초마다 사격해 조준 유지, 타임라인 끔) → 구간마다 (자세 · mark · 대기) → dump → end.
구간: static(정지 조준) · pitch(카메라 Pitch ±40 · ±60 · −80) · offset(제자리 회전 오프셋 ±45 × Pitch 0 · ±40 — AO Yaw ±45)
      · turn(점진 90° 회전 — 턴 클립 Rotation/Recovery, Pitch 0 · −40) · spin(빠른 360° — 오프셋이 AO 범위 ±90 을 넘는다) · strafe(조준 이동 앞 · 오른쪽 · 뒤 · 왼쪽).
출력: PIE_MUZZLE_ALL(전체) · PIE_MUZZLE_BUCKET(turn_rot · ao_sat · moving · static) · PIE_MUZZLE_SEG(구간; 이름이 * 면 과도 구간 전체) ·
      PIE_MUZZLE_WORST · PIE_MUZZLE_SHOTS(발사 틱 총열 ↔ 실제 투사체 속도 — 지표 검증).
오차 부호: yawErr/pitchErr = 총열 − 발사 방향 (pitchErr < 0 = 총구가 조준점보다 아래).
"""
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

SRC = (ROOT / "scripts" / "pie_aim_probe.py").read_text(encoding="utf-8")
TIMELINE_SEGMENTS = ""   # 셋째 인자 — PIE_MUZZLE_TL 로 타임라인을 낼 구간 이름(쉼표)


def step(name: str, yaw: float = 0.0, pitch: float = 0.0, turn: float = 0.0, mark: str = "", spin_step: float = 2.0,
         move: tuple[float, float, float] = (0.0, 0.0, 0.0), grip: str = "current") -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r'^GRIP = ".*?"', f'GRIP = "{grip}"', src, count=1, flags=re.M)
    src = re.sub(r"^AUTO_FIRE = .*$", "AUTO_FIRE = 0.8", src, count=1, flags=re.M)
    src = re.sub(r"^TIMELINE = .*$", "TIMELINE = False", src, count=1, flags=re.M)
    src = re.sub(r"^AIM_YAW_OFF = .*$", f"AIM_YAW_OFF = {yaw}", src, count=1, flags=re.M)
    src = re.sub(r"^AIM_PITCH = .*$", f"AIM_PITCH = {pitch}", src, count=1, flags=re.M)
    src = re.sub(r"^TURN_YAW = .*$", f"TURN_YAW = {turn}", src, count=1, flags=re.M)
    src = re.sub(r"^SPIN_STEP = .*$", f"SPIN_STEP = {spin_step}", src, count=1, flags=re.M)
    src = re.sub(r'^MARK = ".*"', f'MARK = "{mark}"', src, count=1, flags=re.M)
    src = re.sub(r"^MOVE = .*$", f"MOVE = {tuple(float(x) for x in move)}", src, count=1, flags=re.M)
    src = re.sub(r'^SEG_TIMELINE = ".*?"', f'SEG_TIMELINE = "{TIMELINE_SEGMENTS}"', src, count=1, flags=re.M)
    src = re.sub(r'^CONSOLE_CMD = ".*?"', lambda _: f'CONSOLE_CMD = {os.environ.get("PROBE_CONSOLE", "")!r}', src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def hold(label: str, pitch: float, seconds: float = 1.2) -> None:
    # 표식 먼저 — aim 이 카메라를 한 틱에 꺾는 과도 구간이 이 구간 앞쪽(SEG_SKIP 로 건너뜀)에 들어가게
    step("mark", mark=label)
    step("aim", 0.0, pitch)
    time.sleep(seconds)


def main() -> int:
    sections = (sys.argv[1] if len(sys.argv) > 1 else "static,pitch,offset,turn,spin,strafe").split(",")
    grip = sys.argv[2] if len(sys.argv) > 2 else "current"   # 진단 전용 무기 배치(pie_aim_probe GRIP) — 애셋은 바꾸지 않는다
    global TIMELINE_SEGMENTS
    TIMELINE_SEGMENTS = sys.argv[3] if len(sys.argv) > 3 else ""
    step("begin")
    time.sleep(10.0)
    step("arm")
    time.sleep(1.0)    # 전환 GA 가 라이플을 손 소켓에 붙인 뒤(재부착 때 ApplyMeshInfo 가 메시 배치를 되돌린다)
    step("grip", grip=grip)
    if os.environ.get("PROBE_CONSOLE"):
        step("console")   # 진단 전용 튜닝 변형 — PIE 인스턴스에만 (예: set ABP_Hero_Combat_C TurnInPlaceSettings (...))
    step("record")
    time.sleep(0.5)
    try:
        if "static" in sections:
            hold("static", 0.0, 1.5)
        if "pitch" in sections:
            for p in (-40.0, 40.0, -60.0, 60.0, -80.0):
                hold(f"p{int(p)}", p)
        if "offset" in sections:
            # 오른쪽으로 45 → RootYawOffset ≈ −45 (턴 임계 50 아래) → AimYaw +45
            step("aim", 0.0, 0.0)
            step("spin", turn=45.0)
            time.sleep(0.6)
            for p, tag in ((0.0, "p0"), (-40.0, "pD"), (40.0, "pU")):
                hold(f"oR45_{tag}", p)
            # 왼쪽으로 90 → +45 → AimYaw −45
            step("aim", 0.0, 0.0)
            step("spin", turn=-90.0)
            time.sleep(0.8)
            for p, tag in ((0.0, "p0"), (-40.0, "pD"), (40.0, "pU")):
                hold(f"oL45_{tag}", p)
        if "turn" in sections:
            # 점진 90° — 오프셋이 임계를 넘어 턴 클립(Rotation → Recovery)이 돈다
            for p, tag in ((0.0, "p0"), (-40.0, "pD")):
                step("aim", 0.0, p)
                time.sleep(1.0)
                step("mark", mark=f"turn90_{tag}*")
                step("spin", turn=90.0)
                time.sleep(2.0)
        if "spin" in sections:
            # 빠른 360°(틱당 6°) — 오프셋 클램프 150 > AO 90 이라 상체가 따라가지 못하는 구간
            step("aim", 0.0, 0.0)
            time.sleep(1.0)
            step("mark", mark="spin360*")
            step("spin", turn=360.0, spin_step=6.0)
            time.sleep(2.5)
        if "strafe" in sections:
            step("aim", 0.0, 0.0)
            time.sleep(0.8)
            for tag, mv in (("f", (1.0, 0.0)), ("r", (0.0, 1.0)), ("b", (-1.0, 0.0)), ("l", (0.0, -1.0))):
                step("mark", mark=f"strafe_{tag}*")
                step("move", move=(mv[0], mv[1], 1.5))
                time.sleep(1.8)
            step("aim", 0.0, -40.0)
            step("mark", mark="strafe_f_pD*")
            step("move", move=(1.0, 0.0, 1.5))
            time.sleep(1.8)
        step("mark", mark="end")
        time.sleep(0.3)
        step("dump")
    finally:
        step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
