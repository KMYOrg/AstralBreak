import unreal

mon = unreal.load_asset("/Game/AstralBreak/_ScriptTest/AM_ScriptTest_01")
log = unreal.log

log("=== AlphaBlend 구조체 ===")
try:
    ab = unreal.AlphaBlend()
    log(f"  생성 OK: {ab}")
    for f in ("blend_time", "blend_option", "custom_curve"):
        try:
            log(f"  [있음] {f} = {ab.get_editor_property(f)}")
        except Exception:
            log(f"  [없음] {f}")
except Exception as e:
    log(f"  AlphaBlend 생성 실패: {e}")

log("=== AnimMontage 노출 프로퍼티 ===")
seen = set()
for name in ("blend_in", "blend_out", "blend_mode_in", "blend_mode_out",
             "slot_anim_tracks", "composite_sections", "notifies",
             "enable_root_motion_translation", "enable_root_motion_rotation",
             "blend_out_trigger_time", "sync_group", "sync_slot_index",
             "branching_points", "b_enable_auto_blend_out"):
    try:
        v = mon.get_editor_property(name)
        log(f"  [있음] {name} = {type(v).__name__}")
        seen.add(name)
    except Exception:
        log(f"  [없음] {name}")

log("=== 슬롯/섹션 조회 함수 ===")
for m in sorted(m for m in dir(mon) if not m.startswith("_")
                and any(k in m for k in ("slot", "section", "get_"))):
    log(f"  {m}")