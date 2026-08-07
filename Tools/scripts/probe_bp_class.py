"""BP 액터 클래스 로드 경로 검증 — spawn_class의 _CLASSES 폴백이 BP에 통하는가. 읽기 전용."""
import unreal

CANDIDATES = [
    "/Game/Characters/Enemy/BP_TargetDummy.BP_TargetDummy_C",
    "/Game/Characters/Enemy/BP_TargetDummy",
]

for path in CANDIDATES:
    try:
        cls = unreal.load_class(None, path)
    except Exception as e:
        cls = None
        unreal.log(f"load_class 예외: {path} -> {type(e).__name__}: {e}")
    unreal.log(f"load_class({path!r}) -> {cls}")

# EditorAssetLibrary 경로도 확인
try:
    bp = unreal.EditorAssetLibrary.load_asset("/Game/Characters/Enemy/BP_TargetDummy")
    unreal.log(f"load_asset -> {bp}")
    if bp:
        gc = bp.get_editor_property("generated_class")
        unreal.log(f"  generated_class -> {gc}")
except Exception as e:
    unreal.log_error(f"load_asset 실패: {type(e).__name__}: {e}")
