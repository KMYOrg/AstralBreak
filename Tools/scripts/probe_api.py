import unreal

log = unreal.log

def dump(label, obj, keys=()):
    log(f"=== {label} ===")
    names = [m for m in dir(obj) if not m.startswith("_")]
    if keys:
        names = [m for m in names if any(k in m for k in keys)]
    for m in sorted(names):
        log(f"  {m}")

# 1) 몽타주 팩토리: 소스 애니메이션 프로퍼티 이름 찾기
fac = unreal.AnimMontageFactory()
log("=== AnimMontageFactory 프로퍼티 ===")
for name in ("source_animation", "target_anim_sequence", "preview_anim_sequence",
             "target_skeleton", "asset_class"):
    try:
        v = fac.get_editor_property(name)
        log(f"  [있음] {name} = {v}")
    except Exception as e:
        log(f"  [없음] {name}")

# 2) Notify 계열 시그니처
log("=== AnimationLibrary notify ===")
for m in sorted(m for m in dir(unreal.AnimationLibrary) if "notify" in m or "sync" in m):
    doc = (getattr(unreal.AnimationLibrary, m).__doc__ or "").split("\n")[0].strip()
    log(f"  {m}")
    if doc:
        log(f"      {doc[:160]}")

# 3) 레벨 API
dump("LevelEditorSubsystem", unreal.LevelEditorSubsystem, ("level",))
dump("EditorActorSubsystem", unreal.EditorActorSubsystem, ("spawn", "destroy", "get_all"))

# 4) AnimBlueprintFactory
log("=== AnimBlueprintFactory 프로퍼티 ===")
af = unreal.AnimBlueprintFactory()
for name in ("target_skeleton", "parent_class", "preview_skeletal_mesh",
             "template", "blueprint_type"):
    try:
        af.get_editor_property(name)
        log(f"  [있음] {name}")
    except Exception:
        log(f"  [없음] {name}")