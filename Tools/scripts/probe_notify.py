import unreal

log = unreal.log

for path in ("/Script/AstralBreak.AstralAnimNotify_GameplayEvent",
             "/Script/AstralBreak.AstralAnimNotifyState_GameplayEventWindow"):
    cls = unreal.load_class(None, path)
    log(f"=== {path} ===")
    if not cls:
        log("  [FAIL] 클래스 로드 실패 - 모듈명/클래스명 확인")
        continue
    cdo = unreal.get_default_object(cls)
    for p in ("EventTag", "BeginEventTag", "EndEventTag", "EventData",
              "event_tag", "begin_event_tag", "end_event_tag", "event_data"):
        try:
            v = cdo.get_editor_property(p)
            log(f"  [있음] {p} = {v}")
        except Exception:
            pass

log("=== FGameplayEventData 필드 ===")
d = unreal.GameplayEventData()
for f in ("event_tag", "instigator", "target", "optional_object", "optional_object2",
          "context_handle", "instigator_tags", "target_tags",
          "event_magnitude", "target_data"):
    try:
        d.get_editor_property(f)
        log(f"  [있음] {f}")
    except Exception:
        log(f"  [없음] {f}")