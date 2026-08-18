import unreal

# ─────────── 설정 ───────────
SRC_ANIM = "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Jump"
DST_DIR  = "/Game/AstralBreak/_ScriptTest"
MON_NAME = "AM_ScriptTest_01"
# ────────────────────────────

log = unreal.log
err = unreal.log_error
at  = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
abl = unreal.AnimationLibrary


def step(label, fn):
    try:
        r = fn()
        log(f"[OK]   {label}" + (f" -> {r}" if r is not None else ""))
        return r
    except Exception as e:
        err(f"[FAIL] {label}: {type(e).__name__}: {e}")
        return None


# 1) 소스 로드
seq = unreal.load_asset(SRC_ANIM)
if not seq:
    err(f"소스 애니메이션 없음: {SRC_ANIM}")
    raise SystemExit
skeleton = seq.get_editor_property("skeleton")
log(f"[OK]   소스 로드: {seq.get_name()} ({seq.get_play_length():.3f}s)")
log(f"       skeleton = {skeleton.get_name() if skeleton else 'None'}")

# 2) 기존 테스트 애셋 정리
dst = f"{DST_DIR}/{MON_NAME}"
if eal.does_asset_exist(dst):
    eal.delete_asset(dst)
    log(f"[OK]   기존 애셋 삭제")

# 3) 팩토리 (확정 시그니처)
fac = unreal.AnimMontageFactory()
step("target_skeleton",  lambda: fac.set_editor_property("target_skeleton", skeleton))
step("source_animation", lambda: fac.set_editor_property("source_animation", seq))

# 4) 생성
mon = step("몽타주 생성",
           lambda: at.create_asset(MON_NAME, DST_DIR, unreal.AnimMontage, fac))
if not mon:
    raise SystemExit

# 5) 블렌드 - AlphaBlend 사용
def set_blend(prop, t):
    ab = unreal.AlphaBlend()
    ab.set_editor_property("blend_time", t)
    mon.set_editor_property(prop, ab)

step("blend_in",  lambda: set_blend("blend_in",  0.08))
step("blend_out", lambda: set_blend("blend_out", 0.20))

# 6) Notify 트랙
step("notify 트랙", lambda: abl.add_animation_notify_track(mon, "Combat", unreal.LinearColor(1.0, 0.2, 0.2, 1.0)))

# 7) Notify
cn = unreal.load_class(None, "/Script/Engine.AnimNotify_PlaySound")
step("notify 추가", lambda: abl.add_animation_notify_event(mon, "Combat", 0.15, cn))

# 8) NotifyState
cs = unreal.load_class(None, "/Script/Engine.AnimNotifyState_DisableRootMotion")
if cs:
    step("notify state 추가", lambda: abl.add_animation_notify_state_event(mon, "Combat", 0.30, 0.20, cs))
else:
    log("       AnimNotifyState_DisableRootMotion 없음 - 건너뜀")

# 9) 저장
step("저장", lambda: eal.save_loaded_asset(mon))

# 10) 검증 - slot_anim_tracks 제거
log("=== 결과 ===")
log(f"       길이   : {mon.get_play_length():.3f}s")
try:
    secs = mon.get_editor_property("composite_sections")
    log(f"       섹션   : {[str(s.get_editor_property('section_name')) for s in secs]}")
except Exception as e:
    log(f"       섹션   : 조회 불가 ({e})")
log(f"       트랙   : {[str(n) for n in abl.get_animation_notify_track_names(mon)]}")
log(f"       notify : {len(abl.get_animation_notify_events(mon))}개")