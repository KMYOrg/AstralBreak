# 디버그 위젯 BP의 위젯 트리 덤프 — 루트 · 자식 · 캔버스 슬롯 · 폰트
# WidgetTree.RootWidget / Widget.Slot 은 Edit·Blueprint 플래그가 없어 파이썬에 노출되지 않는다 →
# ObjectIterator로 WidgetTree 소속 위젯을 모으고, 슬롯은 WidgetLayoutLibrary.slot_as_canvas_slot 로 얻는다
import unreal

WBP = "/Game/UI/BP_DebugWidget"
log = unreal.log

bp = unreal.load_asset(WBP)
tree = unreal.find_object(bp, "WidgetTree")
log(f"WBP_TREE: {tree.get_path_name() if tree else None}")

widgets = [w for w in unreal.ObjectIterator(unreal.Widget) if w.get_outer() == tree]
log(f"WBP_WIDGET_COUNT: {len(widgets)}")

roots = [w for w in widgets if w.get_parent() is None]
log(f"WBP_ROOTS: {[f'{w.get_name()}({w.get_class().get_name()})' for w in roots]}")


def describe(widget, depth=0):
    pad = "  " * depth
    desc = f"{pad}{widget.get_name()} ({widget.get_class().get_name()})"
    cslot = unreal.WidgetLayoutLibrary.slot_as_canvas_slot(widget)
    if cslot:
        a = cslot.get_anchors()
        o = cslot.get_offsets()
        al = cslot.get_alignment()
        desc += (f" canvas: anchors=({a.minimum.x:.2f},{a.minimum.y:.2f})-({a.maximum.x:.2f},{a.maximum.y:.2f})"
                 f" offsets=({o.left:.0f},{o.top:.0f},{o.right:.0f},{o.bottom:.0f}) autosize={cslot.get_auto_size()} align=({al.x:.1f},{al.y:.1f})")
    if isinstance(widget, unreal.TextBlock):
        font = widget.get_editor_property("font")
        desc += f" font_size={font.get_editor_property('size')}"
        try:
            desc += f" is_variable={widget.get_editor_property('is_variable')}"
        except Exception:
            pass
    log(f"WBP_NODE: {desc}")
    if isinstance(widget, unreal.PanelWidget):
        for child in widget.get_all_children():
            describe(child, depth + 1)


for r in roots:
    describe(r)
log("WBP_PROBE_DONE")
