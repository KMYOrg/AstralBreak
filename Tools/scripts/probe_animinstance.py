import unreal

log = unreal.log

# 1) 프로젝트 AnimInstance 계층
log("=== AstralBreak AnimInstance 클래스 ===")
for name in dir(unreal):
    if "AnimInstance" not in name or not name.startswith("Astral"):
        continue
    cls = getattr(unreal, name)
    log(f"  {name}")

# 2) 애셋 참조로 쓸 만한 UPROPERTY 스캔
TARGET = "/Script/AstralBreak.AstralAnimInstance"   # 실제 클래스명으로 수정
cls = unreal.load_class(None, TARGET)
if not cls:
    log(f"!! 클래스 로드 실패: {TARGET}")
else:
    cdo = unreal.get_default_object(cls)
    log(f"=== {TARGET} 노출 프로퍼티 ===")
    for m in sorted(m for m in dir(cdo) if not m.startswith("_")):
        try:
            v = cdo.get_editor_property(m)
        except Exception:
            continue
        t = type(v).__name__
        if t in ("BlendSpace", "AnimSequence", "AnimMontage", "PoseSearchDatabase",
                 "Object", "NoneType") or "DataAsset" in t or "Set" in t:
            log(f"  {m:40} : {t} = {v}")

# 3) 프로젝트 ABP 목록
ar = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(
    class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimBlueprint")],
    package_paths=["/Game"], recursive_paths=True,
)
assets = ar.get_assets(f)
log(f"=== AnimBlueprint {len(assets)}개 ===")
for a in assets:
    log(f"  {a.package_name}")