import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_blueprint as B
importlib.reload(B) 

spec = {
    "path": "/Game/AstralBreak/_ScriptTest/BP_SpecTest",
    "parent": "/Script/Engine.Character",
    "components": [
        {"class": "/Script/Engine.SpringArmComponent", "name": "CameraBoom"},
        {"class": "/Script/Engine.CameraComponent", "name": "FollowCamera",
         "parent": "CameraBoom"},
    ],
    "defaults": {"replicates": True},
    "overwrite": True,
}

r = B.build_from_spec(spec)
for k, v in r.items():
    unreal.log(f"  {k:12} : {v}")

unreal.log("=== 감사 함수 ===")
unreal.log(f"  list_bps  : {B.list_bps('/Game/AstralBreak/_ScriptTest')}")
unreal.log(f"  describe  : {B.describe_bp(spec['path'])}")