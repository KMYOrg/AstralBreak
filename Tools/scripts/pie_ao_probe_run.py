"""AimOffset 단독 PIE 프로브 — 액터를 돌리지 않고 조준 방향만 바꿔 두 손 거리·AimYaw 를 기록한다 (제자리 회전과 분리).

    python Tools/scripts/pie_ao_probe_run.py

begin → arm → record → aim(yaw +80) → aim(−80) → aim(0, pitch −60) → aim(0, pitch +60) → aim(0,0) → dump → end. 각 자세 0.8초.
정상 두 손 거리 ≈ 23cm(Rifle_Idle 26 · AO 샘플 19~33). 어떤 방향에서 5cm 로 무너지면 AO 샘플/기준 포즈 문제.
"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

SRC = (ROOT / "scripts" / "pie_aim_probe.py").read_text(encoding="utf-8")


def step(name: str, yaw: float = 0.0, pitch: float = 0.0) -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r"^AIM_YAW_OFF = .*$", f"AIM_YAW_OFF = {yaw}", src, count=1, flags=re.M)
    src = re.sub(r"^AIM_PITCH = .*$", f"AIM_PITCH = {pitch}", src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def main() -> int:
    step("begin")
    time.sleep(10.0)
    step("arm")
    step("record")
    for yaw, pitch in ((80, 0), (-80, 0), (0, -60), (0, 60), (0, 0)):
        step("fire")
        step("aim", yaw, pitch)
        time.sleep(0.8)
    step("dump")
    step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
