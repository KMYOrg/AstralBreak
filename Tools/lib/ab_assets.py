"""레벨 배치용 애셋 조회. Claude Code가 실제 존재하는 애셋만 쓰도록 한다."""
import unreal

_ar = unreal.AssetRegistryHelpers.get_asset_registry()

# 카탈로그에서 제외할 경로 (샘플/데모 에셋)
EXCLUDE = ("/Game/Assets/IdaFaber", "/Game/Characters/UEFN_Mannequin")


def list_meshes(package_path: str = "/Game", name_filter: str = "",
                exclude=EXCLUDE, limit: int = 300) -> list:
    f = unreal.ARFilter(
        class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")],
        package_paths=[package_path], recursive_paths=True,
    )
    out = []
    for a in _ar.get_assets(f):
        p = str(a.package_name)
        if any(p.startswith(x) for x in exclude):
            continue
        if name_filter and name_filter.lower() not in p.lower():
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return sorted(out)


def mesh_bounds(path: str) -> dict:
    """메시 실측 크기. 배치 스케일 계산에 쓴다."""
    m = unreal.load_asset(path)
    if not m:
        return {"path": path, "error": "load failed"}
    b = m.get_bounds()
    e = b.box_extent
    return {
        "path": path,
        "size": [round(e.x * 2, 1), round(e.y * 2, 1), round(e.z * 2, 1)],
    }


def catalog(package_path: str = "/Game", limit: int = 300) -> list:
    return [mesh_bounds(p) for p in list_meshes(package_path, limit=limit)]


def scale_for(mesh_path: str, target_size) -> list:
    """목표 크기(cm)에 맞는 스케일 값 계산. target_size 중 None은 1.0 유지."""
    info = mesh_bounds(mesh_path)
    if "size" not in info:
        raise RuntimeError(f"bounds 조회 실패: {mesh_path}")
    out = []
    for src, tgt in zip(info["size"], target_size):
        out.append(1.0 if tgt is None or src == 0 else round(tgt / src, 4))
    return out