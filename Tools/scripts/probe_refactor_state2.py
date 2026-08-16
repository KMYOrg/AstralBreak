# 통합 전 2차 프로브 — InputConfig/InitialCombatStyle/GA BP 경로
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary

for p in ["/Game/Characters/Hero/Data/DA_Hero_Raid_Vesper", "/Game/Characters/Hero/Data/DA_Hero_Hub_Vesper"]:
    ds = EAL.load_asset(p)
    ic = ds.get_editor_property("input_config")
    style = ds.get_editor_property("initial_combat_style")
    hero = ds.get_editor_property("hero_tag")
    print(f"{p}: InputConfig={ic.get_path_name() if ic else 'None'} InitialStyle={style.to_string() if hasattr(style,'to_string') else style} HeroTag={hero.to_string() if hasattr(hero,'to_string') else hero}")

AR = unreal.AssetRegistryHelpers.get_asset_registry()
print("=== GA/Hero BP 경로 ===")
f = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")], recursive_paths=True, package_paths=["/Game/AbilitySystem"])
for a in AR.get_assets(f):
    print(str(a.package_name))

print("=== Characters BP ===")
f2 = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")], recursive_paths=True, package_paths=["/Game/Characters"])
for a in AR.get_assets(f2):
    print(str(a.package_name))
print("PROBE2_DONE")
