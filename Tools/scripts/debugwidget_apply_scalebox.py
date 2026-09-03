# 디버그 위젯 BP — DebugText를 ScaleBox(ScaleToFit, DownOnly)로 감싸 세로 넘침 시 자동 축소
# 변경 전 /Game/UI/BP_DebugWidget_Backup 으로 복제 (멱등 — 이미 감싸져 있으면 스킵)
# WidgetTree.RootWidget / Widget.Slot 은 파이썬 미노출 → ObjectIterator + WidgetLayoutLibrary 경유
import unreal

WBP    = "/Game/UI/BP_DebugWidget"
BACKUP = "/Game/UI/BP_DebugWidget_Backup"
TEXT_NAME  = "DebugText"
SCALE_NAME = "DebugScaleBox"
SLOT_WIDTH = 640.0      # 텍스트 최대 폭 — 넘치면 가로 기준으로도 축소
PAD_BOTTOM = 10.0       # 화면 아래 여백 (Top은 기존 값 유지)

EAL = unreal.EditorAssetLibrary
log = unreal.log

# 0) 백업
if not EAL.does_asset_exist(BACKUP):
    if not EAL.duplicate_asset(WBP, BACKUP):
        raise RuntimeError("WBP_FAIL: 백업 복제 실패")
    log(f"WBP_BACKUP: {BACKUP}")
else:
    log(f"WBP_BACKUP_EXISTS: {BACKUP}")

bp = unreal.load_asset(WBP)
tree = unreal.find_object(bp, "WidgetTree")
if not tree:
    raise RuntimeError("WBP_FAIL: WidgetTree 없음")


def tree_widgets():
    return [w for w in unreal.ObjectIterator(unreal.Widget) if w.get_outer() == tree]


def find_widget(name):
    for w in tree_widgets():
        if w.get_name() == name:
            return w
    return None


roots = [w for w in tree_widgets() if w.get_parent() is None]
if len(roots) != 1 or not isinstance(roots[0], unreal.CanvasPanel):
    raise RuntimeError(f"WBP_FAIL: 루트 CanvasPanel 식별 실패 {[r.get_name() for r in roots]}")
canvas = roots[0]

text = find_widget(TEXT_NAME)
if not text:
    raise RuntimeError(f"WBP_FAIL: {TEXT_NAME} 없음")

if find_widget(SCALE_NAME):
    log("WBP_ALREADY_WRAPPED")
    raise SystemExit

# 1) 기존 캔버스 슬롯 값 보존
old_slot = unreal.WidgetLayoutLibrary.slot_as_canvas_slot(text)
if not old_slot:
    raise RuntimeError("WBP_FAIL: DebugText가 캔버스 슬롯이 아님")
o = old_slot.get_offsets()
left, top = o.left, o.top
log(f"WBP_OLD_SLOT: offsets=({o.left:.0f},{o.top:.0f},{o.right:.0f},{o.bottom:.0f})")

# 2) 텍스트를 캔버스에서 떼고 ScaleBox를 캔버스에 추가
if not canvas.remove_child(text):
    raise RuntimeError("WBP_FAIL: remove_child 실패")

scale = unreal.new_object(unreal.ScaleBox, outer=tree, name=SCALE_NAME)
scale.set_editor_property("stretch", unreal.Stretch.SCALE_TO_FIT)
scale.set_editor_property("stretch_direction", unreal.StretchDirection.DOWN_ONLY)

slot = canvas.add_child_to_canvas(scale)
slot.set_auto_size(False)
slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0.0, 0.0), maximum=unreal.Vector2D(0.0, 1.0)))
# 세로 스트레치 앵커: Left=X, Top=위 여백, Right=폭, Bottom=아래 여백
slot.set_offsets(unreal.Margin(left=left, top=top, right=SLOT_WIDTH, bottom=PAD_BOTTOM))
slot.set_alignment(unreal.Vector2D(0.0, 0.0))

# 3) 텍스트를 ScaleBox 안으로 (좌상단 정렬)
scale_slot = scale.add_child(text)
if scale_slot:
    try:
        scale_slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_LEFT)
        scale_slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_TOP)
    except Exception as e:
        log(f"WBP_SLOT_ALIGN_SKIP: {e}")

# 4) 컴파일 · 저장
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
saved = EAL.save_asset(WBP, only_if_is_dirty=False)
log(f"WBP_SAVED: {saved}")

# 5) 재검증
scale2 = find_widget(SCALE_NAME)
text2 = find_widget(TEXT_NAME)
parent_ok = text2 is not None and scale2 is not None and text2.get_parent() == scale2
scale_parent_ok = scale2 is not None and scale2.get_parent() == canvas
log(f"WBP_VERIFY: text_in_scalebox={parent_ok} scalebox_in_canvas={scale_parent_ok}")
log("WBP_APPLY_DONE")
