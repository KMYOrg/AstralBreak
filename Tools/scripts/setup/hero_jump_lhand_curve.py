import sys
# 점프 3클립에 왼손 IK 끄기 커브 (멱등) — DisableLHandIK = 1: 이 클립의 왼손은 총을 쥐지 않는다 (2026-10-22, 라이플 점프 왼손 IK)
#   UAstralAnimInstance::LeftHandIKAlpha = 파지점 × (1 − 커브 × (1 − AimPoseAlpha)) — 비조준 공중에선 왼손을 놓아 점프 클립의 팔 그대로,
#   조준 중엔 무기 포즈 오버레이가 상체를 두 손 조준 자세로 덮으니 다시 잡는다. 착지 뒤 Idle/Move 로의 크로스페이드(0.2초)가 커브를 0 으로 내린다.
#   클립은 무기 무관(낫·맨손도 쓴다) — 커브를 읽는 쪽은 파지점이 있을 때(양손 총)뿐이라 무해. 운영 ABP_Hero_Base 는 읽지 않는다.
#   나중에 무기 전용 두 손 점프 클립이 생기면 그 클립엔 커브를 넣지 않으면 된다(왼손을 계속 잡는다) — 판단은 콘텐츠가 한다
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

REVERT = False   # True — 커브를 지운다

CURVE = "DisableLHandIK"   # = UAstralAnimInstance::LeftHandIKDisableCurve
LOCO = "/Game/Animation/Hero/Anims/Locomotions"
CLIPS = [f"{LOCO}/AS_Hero_Jump", f"{LOCO}/AS_Hero_FallLoop", f"{LOCO}/AS_Hero_Land"]   # 베이스 Locomotions 의 JumpStart · FallLoop · FallLand

AL = unreal.AnimationLibrary
EAL = unreal.EditorAssetLibrary
log = unreal.log
FLOAT = unreal.RawCurveTrackTypes.RCT_FLOAT

for path in CLIPS:
    seq = unreal.load_asset(path)
    if seq is None:
        raise RuntimeError(f"JUMP_CURVE_FAIL: {path} 없음")
    length = seq.get_play_length()
    has = AL.does_curve_exist(seq, CURVE, FLOAT)
    if REVERT:
        if has:
            AL.remove_curve(seq, CURVE, False)
            EAL.save_loaded_asset(seq, False)
        log(f"JUMP_CURVE {path.split('/')[-1]} removed={has}")
        continue
    keys = AL.get_float_keys(seq, CURVE) if has else ([], [])
    want = ([0.0, length], [1.0, 1.0])
    same = has and len(keys[0]) == 2 and all(abs(a - b) < 1e-4 for a, b in zip(keys[0], want[0])) and all(abs(a - b) < 1e-4 for a, b in zip(keys[1], want[1]))
    if not same:
        if has:
            AL.remove_curve(seq, CURVE, False)
        AL.add_curve(seq, CURVE, FLOAT, False)
        AL.add_float_curve_keys(seq, CURVE, want[0], want[1])
        # 커브 추가는 패키지를 더티로 표시하지 않을 수 있다 — 강제 저장 (몽타주 노티파이와 같은 함정)
        EAL.save_loaded_asset(seq, False)
    keys = AL.get_float_keys(seq, CURVE)
    log(f"JUMP_CURVE {path.split('/')[-1]} length={length:.3f} changed={not same} keys={[round(t, 3) for t in keys[0]]}={[round(v, 3) for v in keys[1]]}")
log("JUMP_CURVE_DONE")
