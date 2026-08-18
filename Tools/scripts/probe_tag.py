import unreal

log = unreal.log
abl = unreal.AnimationLibrary

log("=== GameplayTag 노출 표면 ===")
log(f"  doc: {unreal.GameplayTag.__doc__}")
log(f"  dir: {[m for m in dir(unreal.GameplayTag) if not m.startswith('_')]}")

# 기존 몽타주에서 실제 태그 객체 확보
ar = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(
    class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimMontage")],
    package_paths=["/Game"],
    recursive_paths=True,
)
assets = ar.get_assets(f)
log(f"=== AnimMontage {len(assets)}개 ===")

hit = 0
for a in assets:
    if hit >= 5:
        break
    mon = unreal.load_asset(str(a.package_name))
    if not mon:
        continue
    for ev in abl.get_animation_notify_events(mon):
        n = None
        for field in ("notify", "notify_state_class"):
            try:
                n = ev.get_editor_property(field)
                if n:
                    break
            except Exception:
                pass
        if not n or "Astral" not in n.get_class().get_name():
            continue
        for prop in ("event_tag", "begin_event_tag", "end_event_tag"):
            try:
                t = n.get_editor_property(prop)
                s = str(t)
                if s and s not in ("None", "{}"):
                    log(f"  {a.asset_name} / {n.get_class().get_name()}.{prop}")
                    log(f"      value = {s}   type = {type(t).__name__}")
                    hit += 1
            except Exception:
                pass