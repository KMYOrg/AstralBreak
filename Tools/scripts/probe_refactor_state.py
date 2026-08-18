# 리팩터링(정책/문맥 분리) 에디터 작업 전 현황 프로브 — 읽기 전용
import sys, importlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()

def list_by_class(cls_name):
    f = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/AstralBreak", cls_name)], recursive_paths=True, package_paths=["/Game"])
    return AR.get_assets(f)

def obj(path):
    return unreal.EditorAssetLibrary.load_asset(path)

print("=== AbilitySets ===")
for a in list_by_class("AstralAbilitySet"):
    p = str(a.package_name)
    ds = obj(p)
    if not ds:
        continue
    abilities = ds.get_editor_property("granted_gameplay_abilities")
    names = []
    for e in abilities:
        ab = e.get_editor_property("ability")
        tag = e.get_editor_property("input_tag")
        names.append(f"{ab.get_name() if ab else 'None'}(tag={tag})")
    print(f"{p}: [{', '.join(names)}]")

print("=== PawnData (Hero) ===")
for a in list_by_class("AstralPawnData_Hero"):
    p = str(a.package_name)
    ds = obj(p)
    if not ds:
        continue
    sets = [s.get_name() if s else "None" for s in ds.get_editor_property("ability_sets")]
    equip = [str(e) for e in ds.get_editor_property("default_equipment")]
    style = ds.get_editor_property("initial_combat_style")
    pawn_cls = ds.get_editor_property("pawn_class")
    print(f"{p}: sets={sets} equip={equip} style={style} pawn={pawn_cls.get_name() if pawn_cls else 'None'}")

print("=== EquipmentFamilies (HolsterSocket 승계 확인) ===")
for a in list_by_class("AstralEquipmentFamily"):
    p = str(a.package_name)
    ds = obj(p)
    if not ds:
        continue
    rows = []
    for s in ds.get_editor_property("actors_to_spawn"):
        rows.append(f"attach={s.get_editor_property('attach_socket')} holster={s.get_editor_property('holster_socket')}")
    style = ds.get_editor_property("combat_style")
    print(f"{p}: style={style} {rows}")

print("=== GameMode/GameState BPs ===")
bp_filter = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")], recursive_paths=True, package_paths=["/Game"])
for a in AR.get_assets(bp_filter):
    p = str(a.package_name)
    bp = obj(p)
    if not bp:
        continue
    gc = bp.generated_class()
    if not gc:
        continue
    cdo = unreal.get_default_object(gc)
    if isinstance(cdo, unreal.GameModeBase):
        pd = cdo.get_editor_property("default_pawn_data") if hasattr(cdo, "get_editor_property") else None
        try:
            pd = cdo.get_editor_property("default_pawn_data")
        except Exception:
            pd = "<n/a>"
        gs = cdo.get_editor_property("game_state_class")
        print(f"[GameMode] {p}: PawnData={pd.get_name() if isinstance(pd, unreal.Object) else pd} GameStateClass={gs.get_name() if gs else 'None'}")
    elif isinstance(cdo, unreal.GameStateBase):
        print(f"[GameState] {p}")

print("=== GA BP 폴더 힌트 ===")
ga_filter = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")], recursive_paths=True, package_paths=["/Game/AbilitySystem"])
for a in AR.get_assets(ga_filter):
    print(str(a.package_name))

print("PROBE_DONE")
