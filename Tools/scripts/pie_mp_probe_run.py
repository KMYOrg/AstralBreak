"""멀티플레이 애니 레이어 PIE 프로브 드라이버 — 에디터 밖(일반 python)에서 pie_mp_probe 의 단계를 차례로 보낸다.

    python Tools/scripts/pie_mp_probe_run.py [players=3] [client_fire | client_fire_snap | pose [grip=current|socket_only|bone] | client_pose]

client_fire 모드는 run_client_fire 참조(클라 월드 입력 주입으로 등진 사격), pose 모드는 run_pose 참조(조준 회전 자세를 월드별로). 기본 모드:

begin(리슨 서버 + 클라, 한 프로세스) → sample(시작) → switch(호스트 근접→원거리) → sample → fire(호스트) → sample(조준 중) → switch(원거리→근접) → sample → end.
전환·사격은 호스트 폰만 한다(클라 월드 직접 발동은 크래시 — pie_mp_probe 주석). 클라 화면의 호스트 폰(시뮬 프록시)으로 클라 측 경로를 본다.
기대(2026-10-20 수정 뒤): 같은 폰은 모든 월드(SERVER·CLIENT)에서 같은 값 —
  시작 = Melee·rifle_layer '-' / 전환 뒤 호스트 폰 = Ranged·'Y' / 사격 뒤 = main_aim 1·layer_aim 1 / 재전환 뒤 = Melee·'-'.
수정 전 클라: 시작부터 모든 폰 rifle_layer 'Y', layer_aim 0 고정(main_aim 1 이어도), 재전환해도 'Y' 유지.
"""
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ue_exec  # noqa: E402

PROBE = ROOT / "scripts" / "pie_mp_probe.py"
SRC = PROBE.read_text(encoding="utf-8")


def step(name: str, label: str = "", players: int = 3, yaw: float = 0.0, pitch: float = 0.0, grip: str = "current") -> None:
    src = re.sub(r'^STEP = ".*"$', f'STEP = "{name}"', SRC, count=1, flags=re.M)
    src = re.sub(r'^GRIP = ".*?"', f'GRIP = "{grip}"', src, count=1, flags=re.M)
    src = re.sub(r'^LABEL = ".*"$', f'LABEL = "{label}"', src, count=1, flags=re.M)
    src = re.sub(r"^NUM_PLAYERS = \d+", f"NUM_PLAYERS = {players}", src, count=1, flags=re.M)
    src = re.sub(r"^POSE_YAW = .*$", f"POSE_YAW = {yaw}", src, count=1, flags=re.M)
    src = re.sub(r"^POSE_PITCH = .*$", f"POSE_PITCH = {pitch}", src, count=1, flags=re.M)
    res = ue_exec.run(src, discover_timeout=20)
    for line in res.get("output", []):
        if line["type"] != "Info" or line["output"].startswith("PIE_"):
            print(f"[{name}] {line['output']}")
    if not res.get("success"):
        raise SystemExit(f"[FAIL] step {name}")


def run_client_fire(players: int, snap: bool) -> None:
    """클라 등진 사격 — 클라 월드에 입력 주입(전환 → 등지기 → 사격). 기대(2026-10-21 수정 뒤): 클릭 1회에 클라당 투사체 1발,
    proj_yaw ≈ 그 클라의 control_yaw. snap=True 는 클라 쪽 몸만 미리 정렬해 "클라가 먼저 정렬" 경합을 결정적으로 만든다 —
    수정 전 로직이면 클라의 EndAbility 가 대기 중인 서버 인스턴스를 끝내 투사체 0."""
    step("begin", players=players)
    time.sleep(20.0)
    try:
        step("client_switch")          # 낫 → 총
        time.sleep(1.5)
        step("sample", "client_ranged")
        step("client_face_away")
        time.sleep(1.0)                # 컨트롤 회전이 이동 패킷으로 서버에 간다
        if snap:
            step("client_snap_body")
        step("shots_before")
        step("client_fire")
        time.sleep(1.0)
        step("shots_after")
    finally:
        step("end")


def run_pose(players: int, grip: str = "current") -> None:
    """조준 자세 — 호스트 폰을 조준 중 돌려(제자리 회전 오프셋) Pitch 를 주고, 모든 월드에서 그 폰의 손 거리·총 Pitch·총구 축(PIE_MP_MUZZLE)을 읽는다.
    클라 월드의 호스트 폰은 시뮬 프록시(AimPitch = RemoteViewPitch, 오프셋은 복제된 액터 Yaw 로 각자 계산). 기대(2026-10-21 AO→RotateRootBone 순서 뒤):
    같은 조건이면 서버·클라가 같은 자세이고, 단일 PIE 프로브(pie_pose_probe_run)의 같은 구간 값과 같다. grip = 진단 전용 무기 배치(grip_all)."""
    step("begin", players=players)
    time.sleep(20.0)
    try:
        step("switch")
        time.sleep(1.5)
        if grip != "current":
            step("grip_all", grip=grip)
        # 단계 하나가 ~0.7초 — 사격(조준 유지)은 회전 단계 안에서도 한다. 회전은 앞 사격 뒤 조준 진입 피벗(0.3초)이 지난 다음이어야 오프셋이 쌓인다
        step("fire")
        for label, yaw, pitch in (("o0_p0", 0.0, 0.0), ("o0_pD", 0.0, -40.0), ("oR45_pU", 45.0, 40.0), ("oL45_pD", -90.0, -40.0)):
            step("pose_turn", yaw=yaw, pitch=pitch)
            step("pose_sample", label)
    finally:
        step("end")


def run_client_pose(players: int) -> None:
    """클라가 조준한 폰 — 각 클라의 로컬 폰에 Pitch 를 주고 사격 입력을 주입해 조준을 유지한 채, 모든 월드에서 총구 축(PIE_MP_MUZZLE)을 읽는다.
    다른 클라의 화면 = 시뮬 프록시(서버가 복제한 조준점 ObservedAimTarget), 서버 = 원격 플레이어(ServerUpdateCamera 카메라로 직접 계산).
    기준은 서버가 그 폰의 발사에 쓰는 조준점. 바닥(pD)이 가까운 표적 — 복제 전엔 시뮬 프록시가 먼 점을 겨눠 10° 대로 어긋났다"""
    step("begin", players=players)
    time.sleep(20.0)
    try:
        step("client_switch")          # 낫 → 총
        time.sleep(1.5)
        for label, pitch in (("c_p0", 0.0), ("c_pD", -40.0), ("c_pU", 40.0)):
            step("client_pose_turn", pitch=pitch)
            time.sleep(0.8)            # 카메라가 이동 패킷에 실려 서버로 · 조준 태그·조준점이 관찰자에게
            step("pose_sample", label)
    finally:
        step("end")


def main() -> int:
    players = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if len(sys.argv) > 2 and sys.argv[2] == "client_pose":
        run_client_pose(players)
        return 0
    if len(sys.argv) > 2 and sys.argv[2] in ("client_fire", "client_fire_snap"):
        run_client_fire(players, snap=sys.argv[2] == "client_fire_snap")
        return 0
    if len(sys.argv) > 2 and sys.argv[2] == "pose":
        run_pose(players, sys.argv[3] if len(sys.argv) > 3 else "current")
        return 0
    step("begin", players=players)
    time.sleep(20.0)   # 창 N 개 · 접속 · InitState 체인 · 로드아웃 복원
    try:
        step("sample", "start")
        step("switch")
        time.sleep(1.5)
        step("sample", "after_switch")
        step("fire")
        time.sleep(0.5)
        step("sample", "aiming")
        time.sleep(2.5)   # AimHold 2초 만료
        step("switch")
        time.sleep(1.5)
        step("sample", "after_switch_back")
    finally:
        step("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
