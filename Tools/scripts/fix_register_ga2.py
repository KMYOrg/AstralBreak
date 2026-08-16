# DA_AbilitySet_Vesper 등록 — struct import_text(직렬화 경로)로 편집 제한 우회
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary
GA_CLS_PATH = "/Game/AbilitySystem/Abilities/GA_Hero_UltGainOnDamaged.GA_Hero_UltGainOnDamaged_C"

ds = EAL.load_asset("/Game/AbilitySystem/AbilitySets/Hero/DA_AbilitySet_Vesper")
arr = list(ds.get_editor_property("granted_gameplay_abilities"))

# 기존 엔트리 포맷 확인 (참고 출력)
if arr:
    print("[Info] 기존 엔트리 export_text:", arr[0].export_text())

already = any(e.get_editor_property("ability") and "UltGainOnDamaged" in e.get_editor_property("ability").get_name() for e in arr)
if already:
    print("[OK] 이미 등록 — 스킵")
else:
    entry = unreal.AstralAbilitySet_GameplayAbility()
    entry.import_text(f'(Ability="/Script/Engine.BlueprintGeneratedClass\'{GA_CLS_PATH}\'",AbilityLevel=1)')
    ab = entry.get_editor_property("ability")
    if not ab:
        raise RuntimeError("import_text 후 ability 가 비어 있음 — 포맷 확인 필요")
    arr.append(entry)
    ds.set_editor_property("granted_gameplay_abilities", arr)
    EAL.save_loaded_asset(ds)
    print(f"[OK] 등록 완료: {[e.get_editor_property('ability').get_name() if e.get_editor_property('ability') else 'None' for e in ds.get_editor_property('granted_gameplay_abilities')]}")
print("FIX2_DONE")
