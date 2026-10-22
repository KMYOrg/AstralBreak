"""라이플 점프 자세 PIE 프로브 드라이버 (2026-10-22) — 조준 점프의 상체 · 비조준 점프의 왼손 IK.

    python Tools/scripts/pie_jump_probe_run.py [move=0]

begin → arm(낫 → 총) → record(자동 사격 0.8초 — 조준 유지) → ground_aim → jump_aim → (사격 멈추고 AimHold 만료) → ground_noaim → jump_noaim → dump → end.
move > 0 이면 각 점프 직전부터 전진 입력(달리기 점프). 출력:
  PIE_REF      지상 기준 자세(조준·비조준) — 손 거리 · 왼손↔파지 소켓 · 총열↔카메라 · 총 Pitch · 왼손 IK 알파 · 조준 오버레이 가중치
  PIE_JUMPSEG  공중 구간 요약 — 상체 편차(가슴 공간 두 손 위치의 지상 기준과의 거리 합, cm) · 총열↔카메라 · 왼손 IK 알파 범위 ·
               놓는 시점(이륙 뒤 알파 < 0.5) · 다시 잡는 시점(착지 뒤 ≥ 0.5) · 가슴 공간 왼손 최대 속도
  PIE_JUMPHANDS 공중 오른손의 지상 기준과의 거리(가슴 공간) · 손 뗌 가중치 · 이륙/착지 구간 오른손·왼손 최대 속도
  PIE_JTL      이륙 0.2초 전 ~ 착지 0.8초 뒤 타임라인(0.05초)
기대(무기 포즈 오버레이 · LeftHandIKAlpha 뒤): 조준 점프 = 상체 편차 작음 · 총열↔카메라 ≈ 지상 · 알파 1 유지 /
비조준 점프 = 공중에서 알파 0(왼손이 점프 클립 그대로) · 착지 크로스페이드 동안 다시 1.
수정 전(2026-10-22): 조준 상체 편차 평균 83cm · 총열↔카메라 하강 중 45° / 비조준 왼손↔소켓 0(공중 내내 IK).
"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

SRC = (ROOT / "scripts" / "pie_jump_probe.py").read_text(encoding="utf-8")


def step(name: str, mark: str = "", auto_fire: float | None = None, move: float | None = None) -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r'^MARK = ".*"$', f'MARK = "{mark}"', src, count=1, flags=re.M)
    if auto_fire is not None:
        src = re.sub(r"^AUTO_FIRE = .*$", f"AUTO_FIRE = {auto_fire}", src, count=1, flags=re.M)
    if move is not None:
        src = re.sub(r"^MOVE_FWD = .*$", f"MOVE_FWD = {move}", src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def jump(label: str, auto_fire: float, move: float) -> None:
    if move:
        step("input", auto_fire=auto_fire, move=move)
        time.sleep(0.6)   # 달리기 상태로
    step("jump", label)
    time.sleep(2.2)
    step("input", auto_fire=auto_fire, move=0.0)


def main() -> int:
    move = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    step("begin")
    time.sleep(12.0)
    try:
        step("arm")
        time.sleep(1.5)
        step("record", auto_fire=0.8)
        time.sleep(0.3)
        step("mark", "ground_aim")
        time.sleep(1.5)
        jump("jump_aim", 0.8, move)
        step("input", auto_fire=0.0, move=0.0)
        time.sleep(2.8)   # AimHold 2초 만료
        step("mark", "ground_noaim")
        time.sleep(1.5)
        jump("jump_noaim", 0.0, move)
        step("mark", "end")
        time.sleep(0.2)
        step("dump")
    finally:
        step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
