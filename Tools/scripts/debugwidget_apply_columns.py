# 디버그 위젯 3열 재배치 — 좌상단 DebugText(상태) · 우상단 LockOnText(락온·조준) · 우하단 PartyText(로비)
# ScaleBox 해체, TextBlock 2개 추가, 폰트 고정, 전부 auto size라 각 열은 텍스트 폭만 차지한다 (멱등)
# WidgetTree.RootWidget / Widget.Slot 은 파이썬 미노출 → ObjectIterator + WidgetLayoutLibrary 경유
import unreal

WBP        = "/Game/UI/BP_DebugWidget"
SCALE_NAME = "DebugScaleBox"
FONT_SIZE  = 16
MARGIN     = 20.0

# 이름 → (앵커 min, 앵커 max, 정렬, 오프셋 left/top)  — auto size라 Left/Top은 앵커 기준 위치
LAYOUT = {
    "DebugText":  ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0), ( MARGIN,  MARGIN)),   # 좌상단
    "LockOnText": ((1.0, 0.0), (1.0, 0.0), (1.0, 0.0), (-MARGIN,  MARGIN)),   # 우상단 (오른쪽 끝에서 안쪽으로)
    "PartyText":  ((1.0, 1.0), (1.0, 1.0), (1.0, 1.0), (-MARGIN, -MARGIN)),   # 우하단
}

EAL = unreal.EditorAssetLibrary
log = unreal.log

bp = unreal.load_asset(WBP)
tree = unreal.find_object(bp, "WidgetTree")
if not tree:
    raise RuntimeError("WBP_FAIL: WidgetTree 없음")


def tree_widgets():
    return {w.get_name(): w for w in unreal.ObjectIterator(unreal.Widget) if w.get_outer() == tree}


widgets = tree_widgets()
roots = [w for w in widgets.values() if w.get_parent() is None]
canvases = [w for w in roots if isinstance(w, unreal.CanvasPanel)]
if len(canvases) != 1:
    raise RuntimeError(f"WBP_FAIL: 루트 CanvasPanel 식별 실패 {[r.get_name() for r in roots]}")
canvas = canvases[0]

text = widgets.get("DebugText")
if not text:
    raise RuntimeError("WBP_FAIL: DebugText 없음")

# 1) ScaleBox 해체 — 텍스트를 캔버스로 되돌리고 ScaleBox는 트랜지언트 패키지로 보내 애셋에서 제거
scale = widgets.get(SCALE_NAME)
if scale:
    scale.remove_child(text)
    canvas.remove_child(scale)
    # 트랜지언트 패키지로 이동 — 안 되면 고아 객체로 남지만 계층에는 없어 무해
    try:
        transient = unreal.find_object(None, "/Engine/Transient")
        scale.rename(name=None, new_outer=transient)
        log("WBP_SCALEBOX_REMOVED")
    except Exception as e:
        log(f"WBP_SCALEBOX_ORPHANED: {e}")
if text.get_parent() != canvas:
    canvas.add_child_to_canvas(text)

# 2) 폰트 — DebugText의 FSlateFontInfo를 복사해 크기만 고정
font = text.get_editor_property("font")
font.set_editor_property("size", FONT_SIZE)

# 3) 신규 TextBlock (없을 때만)
for name in ("LockOnText", "PartyText"):
    if name in widgets:
        log(f"WBP_TEXT_EXISTS: {name}")
        continue
    tb = unreal.new_object(unreal.TextBlock, outer=tree, name=name)
    canvas.add_child_to_canvas(tb)
    log(f"WBP_TEXT_CREATED: {name}")

widgets = tree_widgets()

# 4) 슬롯·폰트·정렬 일괄 적용
for name, (amin, amax, align, (left, top)) in LAYOUT.items():
    w = widgets[name]
    w.set_font(font)
    w.set_editor_property("justification", unreal.TextJustify.LEFT)
    try:
        w.set_editor_property("is_variable", True)   # BindWidgetOptional 이름 바인딩 대상
    except Exception as e:
        log(f"WBP_ISVAR_SKIP: {name} {e}")

    slot = unreal.WidgetLayoutLibrary.slot_as_canvas_slot(w)
    if not slot:
        raise RuntimeError(f"WBP_FAIL: {name} 캔버스 슬롯 없음")
    slot.set_auto_size(True)
    slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(*amin), maximum=unreal.Vector2D(*amax)))
    slot.set_alignment(unreal.Vector2D(*align))
    slot.set_offsets(unreal.Margin(left=left, top=top, right=0.0, bottom=0.0))

# 5) 컴파일 · 저장
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
saved = EAL.save_asset(WBP, only_if_is_dirty=False)
log(f"WBP_SAVED: {saved}")

# 6) 재검증
widgets = tree_widgets()
for name in LAYOUT:
    w = widgets.get(name)
    s = unreal.WidgetLayoutLibrary.slot_as_canvas_slot(w) if w else None
    if not w or not s:
        log(f"VERIFY_FAIL: {name}")
        continue
    a = s.get_anchors()
    o = s.get_offsets()
    log(f"VERIFY_{name}: parent={w.get_parent().get_name()} anchors=({a.minimum.x:.0f},{a.minimum.y:.0f})-({a.maximum.x:.0f},{a.maximum.y:.0f}) offsets=({o.left:.0f},{o.top:.0f}) autosize={s.get_auto_size()} font={w.get_editor_property('font').get_editor_property('size')}")
log(f"VERIFY_SCALEBOX_GONE: {SCALE_NAME not in widgets}")
log("WBP_COLUMNS_DONE")
