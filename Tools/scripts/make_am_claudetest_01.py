import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import ab_montage

spec = {
    "source": "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Jump",
    "dst_dir": "/Game/AstralBreak/_ScriptTest",
    "name": "AM_ClaudeTest_01",
    "notifies": [
        {
            "type": "GameplayEventWindow",
            "track": "Combat",
            "start": 0.4,
            "duration": 0.2,
            "begin_event_tag": "GameplayEvent.WeaponTrace.Begin",
            "end_event_tag": "GameplayEvent.WeaponTrace.End",
        }
    ],
}

result = ab_montage.build_from_spec(spec)
print(result)
