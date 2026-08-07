import unreal

log = unreal.log
abl = unreal.AnimationLibrary

# 1) 기존 태그의 export_text 형식 확인
ar = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(
    class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimMontage")],
    package_paths=["/Game"], recursive_paths=True,
)
sample = None
for a in ar.get_assets(f):
    mon = unreal.load_asset(str(a.package_name))
    if not mon:
        continue
    for ev in abl.get_animation_notify_events(mon):
        n = ev.get_editor_property("notify_state_class") or ev.get_editor_property("notify")
        if not n or "Astral" not in n.get_class().get_name():
            continue
        for prop in ("event_tag", "begin_event_tag", "end_event_tag"):
            try:
                t = n.get_editor_property(prop)
                nm = str(t.get_editor_property("tag_name"))
                if nm and nm != "None":
                    log(f"=== 실제 태그 샘플 ===")
                    log(f"  tag_name    : {nm}")
                    log(f"  export_text : {t.export_text()}")
                    log(f"  is_valid    : {unreal.GameplayTagLibrary.is_gameplay_tag_valid(t)}")
                    sample = nm
                    break
            except Exception as e:
                pass
        if sample: break
    if sample: break

if not sample:
    log("!! 태그가 채워진 Notify를 못 찾음")
    raise SystemExit

# 2) import_text 포맷 시도
log("=== import_text 시도 ===")
for fmt in (sample, f'(TagName="{sample}")', f'"{sample}"'):
    t = unreal.GameplayTag()
    try:
        t.import_text(fmt)
        nm = str(t.get_editor_property("tag_name"))
        ok = unreal.GameplayTagLibrary.is_gameplay_tag_valid(t)
        log(f"  [{'OK ' if nm == sample else 'NG '}] {fmt!r} -> tag_name={nm}, valid={ok}")
    except Exception as e:
        log(f"  [ERR] {fmt!r} -> {type(e).__name__}: {e}")

# 3) 미등록 태그가 걸러지는지
log("=== 미등록 태그 검증 ===")
t = unreal.GameplayTag()
try:
    t.import_text("Bogus.Tag.XYZ")
    log(f"  tag_name={t.get_editor_property('tag_name')}, "
        f"valid={unreal.GameplayTagLibrary.is_gameplay_tag_valid(t)}")
except Exception as e:
    log(f"  예외: {type(e).__name__}: {e}")