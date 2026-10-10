"""락온 4단계 probe — 공격 몽타주의 노티파이 타임라인 덤프 + MotionWarping 모디파이어의 Python 프로퍼티명 확인.

애셋을 바꾸지 않는다. 워프 밴드 배치 전 WeaponTrace 시작 시각을 알기 위해 먼저 돌린다.
    python Tools/ue_exec.py Tools/scripts/lockon_probe_montage_notifies.py
"""
import sys, importlib, json
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as m; importlib.reload(m)

MONTAGES = [
    "/Game/Animation/Hero/Montages/AM_Hero_Attack1",
    "/Game/Animation/Hero/Montages/AM_Hero_Attack2",
    "/Game/Animation/Hero/Montages/AM_Hero_Attack3",
    "/Game/Animation/Hero/Montages/AM_Hero_Finisher1",
]

for path in MONTAGES:
    mon = unreal.load_asset(path)
    if not mon:
        print(f"[MISSING] {path}")
        continue
    print(f"== {path}  length={round(mon.get_play_length(), 4)}")
    for e in m.describe_notifies(mon):
        print("   ", json.dumps(e, ensure_ascii=False))

# MotionWarping 모디파이어 프로퍼티명 introspection — 임시 객체, 애셋 무관
cls = unreal.load_class(None, m.MOTION_WARPING_CLASS)
print(f"== MotionWarping notify class: {cls}")
if cls:
    ns = unreal.new_object(cls)
    mod = ns.get_editor_property("root_motion_modifier")
    print("   modifier:", mod.get_class().get_name() if mod else None)
    if mod:
        names = [p for p in dir(mod) if not p.startswith("_") and "warp" in p.lower() or p in ("rotation_type", "rotation_method")]
        print("   props:", names)
        for key in ("warp_target_name", "warp_rotation", "warp_translation", "rotation_type", "rotation_method"):
            try:
                print(f"   {key} = {mod.get_editor_property(key)}")
            except Exception as ex:
                print(f"   {key} -> ERROR {ex}")
