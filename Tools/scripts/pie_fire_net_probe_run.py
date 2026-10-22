"""원거리 사격 네트워크 타이밍 프로브 드라이버 — 에디터 밖(일반 python)에서 pie_fire_net_probe 의 단계를 차례로 보낸다.

    python Tools/scripts/pie_fire_net_probe_run.py [mode=timing] [lag_ms=100] [players=3] [repeats=3] [client_loss_pct=0] [camera_drop_pct=0]

리슨 서버 + 클라(players-1), 모든 월드 송신 지연 lag_ms(왕복 ≈ 2×lag), 클라 송신 손실 client_loss_pct,
클라 ServerUpdateCamera 만 camera_drop_pct 버림(서버 카메라 캐시 고장 주입). 클라 입력은 Enhanced Input 주입(실제 입력 경로).
timing — ① 비조준·등진(175°) 첫 발 × repeats: 클라 활성화 → 조준 태그 → 몸 정렬 → 발사(어빌리티 종료) / 서버 활성화 · 조준 태그 · 투사체 시각
         ② 연사 0/0.5/1.0/1.5초: 조준 태그가 끊기지 않는지, 마지막 발 + 2초 창에서 서버·클라가 함께 꺼지는지
         ③ 서버 거부(AbilitySystem.DenyClientActivations 1): 클라가 예측한 조준 태그가 롤백되는지(서버는 켜지지 않음)
host   — ① 과 같은 첫 발을 호스트·클라가 동시에 × repeats. 호스트(로컬 권위) 시각표와 각 클라 화면의 시뮬 프록시(clientN-sim) 조준 태그 도착
flick  — 조준 중(정렬) 카메라를 꺾은 같은 틱에 사격(FLICKS 6종) × repeats: 클라가 발사 순간 본 조준점 ↔ 서버 투사체 방향 오차(dir_err),
         클라 카메라 ↔ 그 순간 서버가 아는 카메라(cam_div — 검증 허용각 근거)
읽는 법: PIE_FN_EV 는 상태가 바뀐 프레임만(t 는 기록 시작 기준 초), PIE_FN_SHOT 은 서버 투사체, PIE_FN_FIRE 는 클라 발사 ↔ 투사체 짝.
"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

PROBE = ROOT / "scripts" / "pie_fire_net_probe.py"
SRC = PROBE.read_text(encoding="utf-8")


def step(name: str, label: str = "", players: int = 3, lag: int = 0, loss: int = 0, drop_camera: int = 0, deny: int = 0, presses=(0.0,), flick: float = 0.0, flick_pitch: float = 0.0, face: float = 175.0, host: bool = False) -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r'^LABEL = ".*"$', f'LABEL = "{label}"', src, count=1, flags=re.M)
    src = re.sub(r"^NUM_PLAYERS = \d+", f"NUM_PLAYERS = {players}", src, count=1, flags=re.M)
    src = re.sub(r"^LAG_MS = \d+", f"LAG_MS = {lag}", src, count=1, flags=re.M)
    src = re.sub(r"^LOSS = \d+", f"LOSS = {loss}", src, count=1, flags=re.M)
    src = re.sub(r"^DROP_CAMERA = \d+", f"DROP_CAMERA = {drop_camera}", src, count=1, flags=re.M)
    src = re.sub(r"^DENY = \d+", f"DENY = {deny}", src, count=1, flags=re.M)
    src = re.sub(r"^FACE_YAW = .*?(?=\s+#)", f"FACE_YAW = {face}", src, count=1, flags=re.M)
    src = re.sub(r"^PRESS_TIMES = \[.*?\]", f"PRESS_TIMES = {list(presses)}", src, count=1, flags=re.M)
    src = re.sub(r"^FLICK_YAW = .*?(?=\s+#)", f"FLICK_YAW = {flick}", src, count=1, flags=re.M)
    src = re.sub(r"^FLICK_PITCH = .*?(?=\s+#)", f"FLICK_PITCH = {flick_pitch}", src, count=1, flags=re.M)
    src = re.sub(r"^HOST = (True|False)", f"HOST = {host}", src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        print(f"[{name}] {line['output']}", flush=True)
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def run_timing(players: int, lag: int, repeats: int) -> None:
    for i in range(repeats):
        step("face_away")
        time.sleep(1.0)                 # 컨트롤 회전이 이동 패킷으로 서버에 간다
        step("record", f"first{i}")
        time.sleep(1.5)
        step("dump")
        time.sleep(2.5)                 # AimHold 2초 만료 → 다음 회차도 비조준에서 시작
    step("record", "rapid", presses=(0.0, 0.5, 1.0, 1.5))
    time.sleep(4.8)
    step("dump")
    time.sleep(1.0)
    step("face_away")
    step("deny", deny=players - 1)       # 클라마다 1회
    time.sleep(1.0)
    step("record", "deny")
    time.sleep(1.5)
    step("dump")


FLICKS = (          # (이름, Yaw, Pitch) — 플릭 다음 프레임에 사격. 허용각 안 Yaw·Pitch 는 그 프레임에 바로 발사(카메라 갱신과 한 프레임 차), 큰 Yaw 는 몸 정렬(~1080°/s) 뒤 발사
    ("yaw8", 8.0, 0.0), ("pitch15", 0.0, 15.0), ("yaw60", 60.0, 0.0),
    ("yaw-8", -8.0, 0.0), ("pitch-15", 0.0, -15.0), ("yaw-60", -60.0, 0.0),
)


def run_host(repeats: int) -> None:
    for i in range(repeats):
        step("face_away", host=True)
        time.sleep(1.0)
        step("record", f"host{i}", host=True)
        time.sleep(1.5)
        step("dump")
        time.sleep(2.5)


def run_flick(players: int, lag: int, repeats: int) -> None:
    step("record", "arm")                # 조준 진입 + 정렬
    time.sleep(1.0)
    step("dump")
    for i in range(repeats):
        for name, yaw, pitch in FLICKS:
            # 0초 = 조준 유지(정렬 상태, 플릭 없음), 0.6초 = 플릭과 같은 틱에 사격
            step("record", f"{name}#{i}", presses=(0.0, 0.6), flick=yaw, flick_pitch=pitch)
            time.sleep(1.2)
            step("dump")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "timing"
    lag = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    players = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    repeats = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    loss = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    drop_camera = int(sys.argv[6]) if len(sys.argv) > 6 else 0
    step("begin", players=players)
    time.sleep(20.0)                    # 창 N 개 · 접속 · InitState 체인 · 로드아웃 복원
    try:
        step("lag", lag=lag, loss=loss, drop_camera=drop_camera)
        step("client_switch", host=(mode == "host"))   # 낫 → 총
        time.sleep(2.0)
        if mode == "flick":
            run_flick(players, lag, repeats)
        elif mode == "host":
            run_host(repeats)
        else:
            run_timing(players, lag, repeats)
    finally:
        step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
