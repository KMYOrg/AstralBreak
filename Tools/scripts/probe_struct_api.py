# AstralAbilitySet_GameplayAbility 구조체의 쓰기 우회 API 프로브 + 실제 시도
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

e = unreal.AstralAbilitySet_GameplayAbility()
print("methods:", [m for m in dir(e) if not m.startswith("_")])

EAL = unreal.EditorAssetLibrary
ga_cls = EAL.load_asset("/Game/AbilitySystem/Abilities/GA_Hero_UltGainOnDamaged").generated_class()

# 시도 1: set_editor_properties (일괄)
try:
    e.set_editor_properties({"ability": ga_cls, "ability_level": 1})
    print("TRY1 set_editor_properties: OK ->", e.get_editor_property("ability"))
except Exception as ex:
    print("TRY1 FAIL:", ex)

# 시도 2: copy 후 to_tuple 확인
try:
    src = e.copy()
    print("TRY2 copy ok:", src)
except Exception as ex:
    print("TRY2 FAIL:", ex)
print("PROBE_STRUCT_DONE")
