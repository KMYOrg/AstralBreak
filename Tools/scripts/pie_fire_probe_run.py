"""비조준 등진 사격 PIE 프로브 드라이버 — 에디터 밖(일반 python)에서 pie_aim_probe 의 단계를 차례로 보낸다.

    python Tools/scripts/pie_fire_probe_run.py [face_yaw=175] [record_seconds=1.5]

begin(PIE) → arm(라이플 전환 + 사격 = 조준 2초) → 조준 만료 대기 → record → face_away(카메라 Yaw = 몸 + face_yaw, 몸은 그대로) → fire → 대기 → dump → end.
기대(2026-10-20 수정 뒤): PIE_SHOT 의 body_gap ≤ 10(몸이 돈 뒤 발사) · mesh_gap ≈ body_gap(조준 진입 피벗 — 오프셋 0) · 발사 시각이 face_away 뒤 ~0.17초(조준 회전 1080°/s).
수정 전에는 face_away 직후 같은 틱에 투사체가 나오고 body_gap ≈ face_yaw.
"""
import sys
import time

from pie_turn_probe_run import step


def main() -> int:
    face_yaw = float(sys.argv[1]) if len(sys.argv) > 1 else 175.0
    record_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
    step("begin", face_yaw)
    time.sleep(10.0)
    step("arm", face_yaw)
    time.sleep(3.0)   # AimHold 2초 만료 — 비조준(이동 방향 추종) 상태에서 시작
    step("sample", face_yaw)
    step("record", face_yaw)
    step("face_away", face_yaw)
    step("fire", face_yaw)
    time.sleep(record_seconds)
    step("dump", face_yaw)
    step("end", face_yaw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
