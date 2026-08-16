# AttachOffset 개명 승계 검증 — 기존 MeshOffset 값이 유지되는지
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary
AR = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/AstralBreak", "AstralWeaponDefinition"), unreal.TopLevelAssetPath("/Script/AstralBreak", "AstralRangedWeaponDefinition")], recursive_paths=True, package_paths=["/Game"], recursive_classes=True)
for a in AR.get_assets(f):
    p = str(a.package_name)
    ds = EAL.load_asset(p)
    if not ds:
        continue
    mi = ds.get_editor_property("mesh_info")
    ao = mi.get_editor_property("attach_offset")
    ov = mi.get_editor_property("override_holster_offset")
    print(f"{p}: AttachOffset.T={ao.translation} R={ao.rotation.rotator()} OverrideHolster={ov}")
print("VERIFY_DONE")
