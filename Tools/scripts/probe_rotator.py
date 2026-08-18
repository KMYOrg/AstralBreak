"""unreal.Rotator 생성자 인자 순서 확인 — 읽기 전용."""
import unreal

r = unreal.Rotator(11.0, 22.0, 33.0)
unreal.log(f"unreal.Rotator(11, 22, 33) -> roll={r.roll}  pitch={r.pitch}  yaw={r.yaw}")

if r.roll == 11.0:
    unreal.log(">>> 생성자 순서 = (roll, pitch, yaw)")
elif r.pitch == 11.0:
    unreal.log(">>> 생성자 순서 = (pitch, yaw, roll)")
else:
    unreal.log(">>> 예상 밖 순서")

# ab_level._rot 이 (0, 90, 0) 을 넘겼을 때 실제로 무엇이 세팅되는가
r2 = unreal.Rotator(0.0, 90.0, 0.0)
unreal.log(f"Rotator(0, 90, 0) -> roll={r2.roll}  pitch={r2.pitch}  yaw={r2.yaw}")
