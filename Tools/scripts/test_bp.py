import unreal

log, err = unreal.log, unreal.log_error
eal = unreal.EditorAssetLibrary
bel = unreal.BlueprintEditorLibrary

DST = "/Game/AstralBreak/_ScriptTest/BP_ScriptTest"

def step(label, fn):
    try:
        r = fn()
        log(f"[OK]   {label}" + (f" -> {r}" if r is not None else ""))
        return r
    except Exception as e:
        err(f"[FAIL] {label}: {type(e).__name__}: {e}")
        return None

if eal.does_asset_exist(DST):
    eal.delete_asset(DST)

# 1) 생성
bp = step("BP 생성", lambda: bel.create_blueprint_asset_with_parent(
    asset_path=DST, parent_class=unreal.Actor))
if not bp:
    raise SystemExit

# 2) SubobjectDataSubsystem 표면 확인
sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
log("=== SubobjectDataSubsystem 함수 ===")
for m in sorted(m for m in dir(sub) if not m.startswith("_") and m not in
                ("cast", "get_class", "get_default_object", "get_editor_property",
                 "get_fname", "get_full_name", "get_name", "get_outer", "get_outermost",
                 "get_package", "get_path_name", "get_typed_outer", "get_world",
                 "set_editor_properties", "set_editor_property", "static_class",
                 "call_method", "modify", "rename", "is_package_external",
                 "is_editor_property_overridden", "reset_editor_property")):
    log(f"  {m}")

# 3) 컴포넌트 추가
handles = step("subobject 조회",
               lambda: sub.k2_gather_subobject_data_for_blueprint(bp))
if handles:
    log(f"       루트 핸들 {len(handles)}개")
    params = unreal.AddNewSubobjectParams(
        parent_handle=handles[0],
        new_class=unreal.StaticMeshComponent,
        blueprint_context=bp,
    )
    res = step("컴포넌트 추가", lambda: sub.add_new_subobject(params))
    if res:
        log(f"       반환: {res} ({type(res).__name__})")
        h = res[1] if isinstance(res, (tuple, list)) and len(res) > 1 else res
        step("이름 변경", lambda: sub.rename_subobject(h, "TestMesh"))

# 4) CDO 디폴트값
cdo = step("CDO 획득", lambda: unreal.get_default_object(bp.generated_class()))
if cdo:
    step("bReplicates", lambda: cdo.set_editor_property("replicates", True))
    step("Tags", lambda: cdo.set_editor_property("tags", [unreal.Name("ScriptGenerated")]))

# 5) 컴파일 + 저장
step("컴파일", lambda: bel.compile_blueprint(bp))
step("저장", lambda: eal.save_loaded_asset(bp))