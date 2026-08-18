import unreal

ar = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(
    class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimSequence")],
    package_paths=["/Game"],
    recursive_paths=True,
)
assets = ar.get_assets(f)

unreal.log(f"=== AnimSequence: {len(assets)}개 ===")
for a in assets[:40]:
    unreal.log(f"  {a.package_name}")
if len(assets) > 40:
    unreal.log(f"  ... 외 {len(assets) - 40}개")