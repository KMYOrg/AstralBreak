# 디버그 위젯 BP 재컴파일 + 강제 저장 — 로드 시 컴파일러가 정리한 변수 GUID 맵(고아 DebugScaleBox 항목 제거)을 디스크에 반영
import unreal

WBP = "/Game/UI/BP_DebugWidget"
EAL = unreal.EditorAssetLibrary
log = unreal.log

bp = unreal.load_asset(WBP)
if not bp:
    raise RuntimeError("WBP_FAIL: 로드 실패")

unreal.BlueprintEditorLibrary.compile_blueprint(bp)
saved = EAL.save_asset(WBP, only_if_is_dirty=False)
log(f"WBP_RESAVED: {saved}")

tree = unreal.find_object(bp, "WidgetTree")
names = sorted(w.get_name() for w in unreal.ObjectIterator(unreal.Widget) if w.get_outer() == tree)
log(f"WBP_WIDGETS_NOW: {names}")
log("WBP_RESAVE_DONE")
