import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_montage as m

mon = m.create_montage(
    src_anim_path="/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Jump",
    dst_dir="/Game/AstralBreak/_ScriptTest",
    montage_name="AM_ScriptTest_02",
    blend_in=0.08,
    blend_out=0.20,
    overwrite=True,
)

m.clear_track(mon, "Combat")
m.add_notify(mon, "Combat", 0.15, "/Script/Engine.AnimNotify_PlaySound")
m.add_notify_state(mon, "Combat", 0.30, 0.20,
                   "/Script/Engine.AnimNotifyState_DisableRootMotion")
m.save(mon)

for k, v in m.describe(mon).items():
    unreal.log(f"  {k:12} : {v}")