"""AstralBreak Blueprint 자동화 헬퍼. UE 5.7 실측 검증 완료.

확인된 제약:
  - EventGraph 노드 생성 불가. 로직은 C++ 부모 클래스에 둔다.
  - SubobjectDataSubsystem 은 EngineSubsystem 이다 (EditorSubsystem 아님)
"""
import unreal

_eal = unreal.EditorAssetLibrary
_bel = unreal.BlueprintEditorLibrary
_sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)


# ─────────────────────── 생성 ───────────────────────

def create_bp(asset_path: str, parent_class, overwrite: bool = False):
    """부모 클래스를 지정해 Blueprint 를 만든다.

    parent_class 는 unreal.Actor 같은 클래스 객체이거나
    '/Script/AstralBreak.AstralCharacterPlayer' 같은 경로 문자열.
    """
    if isinstance(parent_class, str):
        cls = unreal.load_class(None, parent_class)
        if not cls:
            raise RuntimeError(f"부모 클래스 로드 실패: {parent_class}")
    else:
        cls = parent_class

    if _eal.does_asset_exist(asset_path):
        if not overwrite:
            raise RuntimeError(f"이미 존재 (overwrite=True 필요): {asset_path}")
        _eal.delete_asset(asset_path)

    bp = _bel.create_blueprint_asset_with_parent(
        asset_path=asset_path, parent_class=cls)
    if not bp:
        raise RuntimeError(f"BP 생성 실패: {asset_path}")
    return bp


def duplicate_bp(src_path: str, dst_path: str, overwrite: bool = False):
    """기존 BP 를 복제한다. 템플릿 기반 생성용."""
    if _eal.does_asset_exist(dst_path):
        if not overwrite:
            raise RuntimeError(f"이미 존재: {dst_path}")
        _eal.delete_asset(dst_path)
    bp = _eal.duplicate_asset(src_path, dst_path)
    if not bp:
        raise RuntimeError(f"복제 실패: {src_path} -> {dst_path}")
    return bp


# ─────────────────────── 컴포넌트 ───────────────────────

def _root_handle(bp):
    handles = _sub.k2_gather_subobject_data_for_blueprint(bp)
    if not handles:
        raise RuntimeError("subobject 핸들 없음")
    return handles[0]


def add_component(bp, component_class, name: str = None, parent_handle=None):
    """컴포넌트를 추가하고 핸들을 반환한다.

    parent_handle 을 주면 그 아래에 붙는다 (계층 구성).
    """
    if isinstance(component_class, str):
        component_class = unreal.load_class(None, component_class)
    if not component_class:
        raise RuntimeError("컴포넌트 클래스 로드 실패")

    params = unreal.AddNewSubobjectParams(
        parent_handle=parent_handle or _root_handle(bp),
        new_class=component_class,
        blueprint_context=bp,
    )
    handle, fail = _sub.add_new_subobject(params)
    if str(fail):
        raise RuntimeError(f"컴포넌트 추가 실패: {fail}")
    if name:
        _sub.rename_subobject(handle, name)
    return handle


def component_handles(bp) -> dict:
    """{이름: 핸들} 사전. 미완성 - k2_find_subobject_data_from_handle 에서
    오브젝트를 꺼내는 경로 미확인. 조회용이며 생성 경로와 무관하다."""
    out = {}
    for h in _sub.k2_gather_subobject_data_for_blueprint(bp):
        try:
            data = _sub.k2_find_subobject_data_from_handle(h)
            obj = data.get_object() if hasattr(data, "get_object") else None
            if obj:
                out[obj.get_name()] = h
        except Exception:
            pass
    return out


# ─────────────────────── 디폴트값 ───────────────────────

def set_defaults(bp, props: dict):
    """CDO 프로퍼티를 설정한다. 실패한 키를 리스트로 반환."""
    cdo = unreal.get_default_object(bp.generated_class())
    failed = []
    for k, v in props.items():
        try:
            cdo.set_editor_property(k, v)
        except Exception as e:
            failed.append(f"{k}: {e}")
    return failed


def compile_and_save(bp) -> bool:
    _bel.compile_blueprint(bp)
    return _eal.save_loaded_asset(bp)


# ─────────────────────── 조회 / 감사 ───────────────────────

_ar = unreal.AssetRegistryHelpers.get_asset_registry()


def list_bps(package_path: str = "/Game/AstralBreak", parent_filter: str = "") -> list:
    f = unreal.ARFilter(
        class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")],
        package_paths=[package_path], recursive_paths=True,
    )
    out = []
    for a in _ar.get_assets(f):
        p = str(a.package_name)
        if parent_filter:
            parent = _parent_from_tag(p)
            if not parent:
                bp = unreal.load_asset(p)
                parent = _parent_from_mro(bp) if bp else None
            if not parent or parent_filter.lower() not in parent.lower():
                continue
        out.append(p)
    return sorted(out)


def _parent_from_tag(asset_path: str):
    """AssetRegistry 태그에서 부모 클래스. 로드 없이 조회 가능."""
    try:
        f = unreal.ARFilter(package_names=[asset_path])
        hits = _ar.get_assets(f)
        if not hits:
            return None
        for key in ("ParentClass", "NativeParentClass"):
            v = hits[0].get_tag_value(key)
            if v:
                return str(v)
    except Exception:
        pass
    return None


def _parent_from_mro(bp):
    """generated_class 의 MRO 에서 부모 이름."""
    try:
        gen = bp.generated_class()
        if not gen:
            return None
        mro = gen.__mro__
        return mro[1].__name__ if len(mro) > 1 else None
    except Exception:
        return None


def describe_bp(asset_path: str) -> dict:
    bp = unreal.load_asset(asset_path)
    if not bp:
        return {"path": asset_path, "error": "load failed"}
    return {
        "path": asset_path,
        "parent": _parent_from_tag(asset_path) or _parent_from_mro(bp),
    }


def batch_set_defaults(asset_paths: list, props: dict, dry_run: bool = True) -> list:
    """여러 BP 의 CDO 값을 일괄 수정한다. 기본은 dry_run."""
    results = []
    for p in asset_paths:
        bp = unreal.load_asset(p)
        if not bp:
            results.append({"path": p, "error": "load failed"})
            continue
        if dry_run:
            results.append({"path": p, "would_set": list(props.keys())})
            continue
        failed = set_defaults(bp, props)
        compile_and_save(bp)
        results.append({"path": p, "failed": failed})
    return results


# ─────────────────────── 스펙 빌드 ───────────────────────

def build_from_spec(spec: dict) -> dict:
    """JSON 스펙 하나로 BP 를 생성한다.

    {
      "path": "/Game/AstralBreak/Characters/BP_Astral_Warrior",
      "parent": "/Script/AstralBreak.AstralCharacterPlayer",
      "template": null,                     // 있으면 복제, 없으면 신규
      "components": [
        {"class": "/Script/Engine.SpringArmComponent", "name": "CameraBoom"},
        {"class": "/Script/Engine.CameraComponent", "name": "FollowCamera",
         "parent": "CameraBoom"}
      ],
      "defaults": {"MaxCombo": 4},
      "overwrite": true
    }
    """
    path = spec["path"]
    ow = spec.get("overwrite", False)

    if spec.get("template"):
        bp = duplicate_bp(spec["template"], path, overwrite=ow)
    else:
        bp = create_bp(path, spec["parent"], overwrite=ow)

    named = {}
    for c in spec.get("components", []):
        parent_h = named.get(c["parent"]) if c.get("parent") else None
        h = add_component(bp, c["class"], c.get("name"), parent_h)
        if c.get("name"):
            named[c["name"]] = h

    failed = set_defaults(bp, spec.get("defaults", {})) if spec.get("defaults") else []
    compile_and_save(bp)

    r = describe_bp(path)
    if failed:
        r["defaults_failed"] = failed
    return r

def safe_delete_directory(path: str) -> bool:
    """열린 에디터 탭을 모두 닫고 디렉터리를 삭제한다.
    레벨이 포함된 경우 삭제 대상 맵이 현재 열려 있으면 안 된다."""
    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_asset_editors()
    return _eal.delete_directory(path)