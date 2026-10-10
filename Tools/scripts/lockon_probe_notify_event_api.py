"""probe — FAnimNotifyEvent의 Python 노출 프로퍼티/함수 확인 (시간·트랙·태그 접근 경로). 애셋 무변경."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

abl = unreal.AnimationLibrary
mon = unreal.load_asset("/Game/Animation/Hero/Montages/AM_Hero_Attack1")
events = abl.get_animation_notify_events(mon)
ev = events[0]
print("dir(ev):", [p for p in dir(ev) if not p.startswith("_")])
for name in ("track_index", "trigger_time_offset", "duration", "link_value", "link_method", "segment_begin_time", "segment_length", "notify_state_class", "notify_name"):
    try:
        print(f"  {name} = {ev.get_editor_property(name)}")
    except Exception as ex:
        print(f"  {name} -> ERROR {ex}")
for fn in ("get_anim_notify_event_trigger_time", "get_anim_notify_event_duration"):
    f = getattr(abl, fn, None)
    print(f"  abl.{fn}: {f(ev) if f else 'MISSING'}")
print("abl notify fns:", [p for p in dir(abl) if "notify" in p.lower()])
ns = ev.get_editor_property("notify_state_class")
tag = ns.get_editor_property("begin_event_tag")
print("tag dir:", [p for p in dir(tag) if not p.startswith("_")])
print("tag_name:", tag.get_editor_property("tag_name"))
