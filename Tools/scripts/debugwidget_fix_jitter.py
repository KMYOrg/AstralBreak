# 디버그 위젯 흔들림 수정 — ScaleBox 고정 배율(UserSpecified) + DebugText 좌측 정렬 (멱등)
import unreal

WBP        = "/Game/UI/BP_DebugWidget"
TEXT_NAME  = "DebugText"
SCALE_NAME = "DebugScaleBox"
USER_SCALE = 0.75

EAL = unreal.EditorAssetLibrary
log = unreal.log

bp = unreal.load_asset(WBP)
tree = unreal.find_object(bp, "WidgetTree")
widgets = {w.get_name(): w for w in unreal.ObjectIterator(unreal.Widget) if w.get_outer() == tree}

scale = widgets.get(SCALE_NAME)
text = widgets.get(TEXT_NAME)
if not scale or not text:
    raise RuntimeError(f"WBP_FAIL: 위젯 없음 scale={scale is not None} text={text is not None}")

# 1) 고정 배율 — 매 프레임 desired size 재계산이 사라져 크기가 흔들리지 않는다
scale.set_stretch(unreal.Stretch.USER_SPECIFIED)
scale.set_user_specified_scale(USER_SCALE)

# 2) 좌측 정렬 — 최장 줄 폭이 바뀌어도 나머지 줄이 옆으로 밀리지 않는다
text.set_editor_property("justification", unreal.TextJustify.LEFT)

unreal.BlueprintEditorLibrary.compile_blueprint(bp)
saved = EAL.save_asset(WBP, only_if_is_dirty=False)
log(f"WBP_SAVED: {saved}")

log(f"WBP_VERIFY: stretch={scale.get_editor_property('stretch')} scale={scale.get_editor_property('user_specified_scale')} justification={text.get_editor_property('justification')}")
log("WBP_FIX_DONE")
