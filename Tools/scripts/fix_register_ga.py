# DA_AbilitySet_Vesper 에 GA_Hero_UltGainOnDamaged 등록 (생성자 kwargs 우회) + Hub PawnData 삭제 재시도
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary

ga_cls = EAL.load_asset("/Game/AbilitySystem/Abilities/GA_Hero_UltGainOnDamaged").generated_class()
ds = EAL.load_asset("/Game/AbilitySystem/AbilitySets/Hero/DA_AbilitySet_Vesper")
arr = list(ds.get_editor_property("granted_gameplay_abilities"))
already = any(e.get_editor_property("ability") and e.get_editor_property("ability").get_name() == ga_cls.get_name() for e in arr)
if already:
    print("[OK] 이미 등록 — 스킵")
else:
    entry = unreal.AstralAbilitySet_GameplayAbility(ability=ga_cls, ability_level=1)
    arr.append(entry)
    ds.set_editor_property("granted_gameplay_abilities", arr)
    EAL.save_loaded_asset(ds)
    print(f"[OK] 등록 완료 — 세트 내용: {[e.get_editor_property('ability').get_name() if e.get_editor_property('ability') else 'None' for e in arr]}")

p = "/Game/Characters/Hero/Data/DA_Hero_Hub_Vesper"
if EAL.does_asset_exist(p):
    refs = unreal.AssetRegistryHelpers.get_asset_registry().get_referencers(unreal.Name("/Game/Characters/Hero/Data/DA_Hero_Hub_Vesper"), unreal.AssetRegistryDependencyOptions())
    print(f"[Info] DA_Hero_Hub_Vesper 참조자: {[str(r) for r in refs] if refs else '없음'}")
    if not refs:
        ok = EAL.delete_asset(p)
        print(f"[{'OK' if ok else 'FAIL'}] DA_Hero_Hub_Vesper 삭제")
else:
    print("[OK] DA_Hero_Hub_Vesper 이미 없음")
print("FIX_DONE")
