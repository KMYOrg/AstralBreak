import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_montage as m

NSTATE = "/Script/AstralBreak.AstralAnimNotifyState_GameplayEventWindow"

mon = m.create_montage(
    src_anim_path="/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Jump",
    dst_dir="/Game/AstralBreak/_ScriptTest",
    montage_name="AM_ScriptTest_03",
    blend_in=0.08,
    blend_out=0.20,
    overwrite=True,
)

m.clear_track(mon, "Combat")

ns = m.add_notify_state(
    mon, "Combat", 0.30, 0.25, NSTATE,
    begin_event_tag=m.tag("GameplayEvent.WeaponTrace.Begin"),
    end_event_tag=m.tag("GameplayEvent.WeaponTrace.End"),
    event_data=m.make_event_data(magnitude=1.0),
)

m.save(mon)

unreal.log(f"  begin : {ns.get_editor_property('begin_event_tag').get_editor_property('tag_name')}")
unreal.log(f"  end   : {ns.get_editor_property('end_event_tag').get_editor_property('tag_name')}")
for k, v in m.describe(mon).items():
    unreal.log(f"  {k:12} : {v}")

# 미등록 태그가 실제로 막히는지
try:
    m.tag("Bogus.Tag.XYZ")
    unreal.log_error("  !! 미등록 태그가 통과됨 - 검증 실패")
except RuntimeError as e:
    unreal.log(f"  [OK] 미등록 태그 차단: {e}")