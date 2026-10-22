import sys
# 히어로 제자리 회전 클립 4개 — Content 루트(/Game/MF_Rifle_Turn*) → /Game/Animation/Hero/Anims/TurnInPlace/ 로 이동 (멱등).
# 스켈레톤 재할당은 MCP Tool reassign_skeleton 이 먼저(또는 뒤에) 한다. 실행은 ue_exec 브릿지 경유 (주석에 확장자 금지 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary
log = unreal.log

NAMES = ["MF_Rifle_TurnLeft_90", "MF_Rifle_TurnLeft_180", "MF_Rifle_TurnRight_90", "MF_Rifle_TurnRight_180"]
DST_DIR = "/Game/Animation/Hero/Anims/TurnInPlace"

for name in NAMES:
    src = f"/Game/{name}"
    dst = f"{DST_DIR}/{name}"
    if EAL.does_asset_exist(dst):
        log(f"MOVE_EXISTS: {dst}")
    elif EAL.does_asset_exist(src):
        if not EAL.rename_asset(src, dst):
            raise RuntimeError(f"MOVE_FAIL: {src} -> {dst}")
        log(f"MOVE_OK: {src} -> {dst}")
    else:
        raise RuntimeError(f"MOVE_FAIL: source missing {src}")
    # rename 이 남긴 리다이렉터는 참조자가 없으니 바로 지운다 (Content 루트를 비워 둔다)
    if EAL.does_asset_exist(src):
        data = EAL.find_asset_data(src)
        if data.asset_class_path.asset_name == "ObjectRedirector":
            EAL.delete_asset(src)
            log(f"MOVE_REDIRECTOR_DELETED: {src}")

# 턴 클립이 Lyra 규약 커브(TurnYawWeight · RemainingTurnYaw)를 갖는지 — UAstralAnimInstance 가 GetCurveValue 로 읽는다. 없으면 제자리 회전이 돌지 않는다
for name in NAMES:
    seq = unreal.load_asset(f"{DST_DIR}/{name}")
    curves = [str(c) for c in unreal.AnimationLibrary.get_animation_curve_names(seq, unreal.RawCurveTrackTypes.RCT_FLOAT)]
    skel = seq.get_editor_property("skeleton").get_path_name()
    lowered = {c.lower() for c in curves}   # 실측: 클립의 커브 이름이 소문자(turnyawweight) — FName 비교는 대소문자 무시라 GetCurveValue 는 그대로 읽는다
    ok = {"turnyawweight", "remainingturnyaw"} <= lowered
    log(f"MOVE_CURVES{'_OK' if ok else '_MISSING'}: {name} len={seq.get_play_length():.3f} skeleton={skel} curves={curves}")

log("MOVE_DONE")
