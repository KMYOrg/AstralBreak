"""버튼 칸 — spec 최상위 `button` 이 말하는 것의 단일 원천 (설계 §11 'Phase 3 설계' ②, Phase 3-2).

버튼 칸 WBP 의 그림은 위젯이 아니라 **클래스 기본값의 스타일**(UCommonButtonStyle 파생 애셋 — 상태 그림 일곱)이 그린다. 파이프라인의 앞 단계(오리기 · 합성 · 진단)는
위젯마다 그림을 보므로, spec 에는 그 그림이 Image 위젯 하나(`button.art` — 칸 전체 크기, 기본 상태)로 있고 에디터로 보내는 트리에서만 뺀다:
  spec.widgets  … art 위젯 포함(오프라인 단계가 그대로 쓴다)
  에디터 목표   … art 를 뺀 트리 + defaults.Style(editor_target)
  역추출        … 트리에는 art 가 없고 button_style 의 브러시 일곱이 돌아온다(style_diff 가 견준다)
  geometry      … art 자리 = 안쪽 버튼(INNER_ID)이 실제로 그려진 상자(geometry_rows)
"""
from __future__ import annotations

from core import spec as spec_mod

BASE = "normal_base"
BRUSHES = (BASE, "normal_hovered", "normal_pressed", "selected_base", "selected_hovered", "selected_pressed", "disabled")
DERIVED = BRUSHES[1:]
# 상태 → render_widget 덮어쓰기(버튼 자신 = ".", 화면에 놓인 칸이면 그 이름)
OVERRIDES = {BASE: {}, "normal_hovered": {"button": "hovered"}, "normal_pressed": {"button": "pressed"}, "selected_base": {"button": "selected"},
             "selected_hovered": {"button": "selected_hovered"}, "selected_pressed": {"button": "selected_pressed"}, "disabled": {"enabled": False}}
SELF_KEY = "."
INNER_ID = "InternalRootButtonBase"       # UCommonButtonBase::ConstructInternalButton 이 만드는 루트(렌더 geometry 에만 있다 — 역추출에는 없다)


def of(spec: dict) -> dict | None:
    b = spec.get("button")
    return b if isinstance(b, dict) else None


def art_id(spec: dict) -> str | None:
    b = of(spec)
    return b["art"] if b else None


def derived_asset_id(base: str, brush: str) -> str:
    return f"{base}_{brush}"


def brush_assets(spec: dict) -> dict[str, str]:
    """상태 → 에셋 id. 버튼 칸이 아니면 빈 것."""
    b = of(spec)
    if not b:
        return {}
    art = spec_mod.widget_index(spec)[b["art"]]
    return {BASE: art["style"]["brush"]["asset"], **b["states"]}


def brushes(spec: dict) -> dict[str, dict]:
    """상태 → 스타일 애셋의 브러시(정규형 — 역추출과 같은 모양)."""
    sizes = {a["asset_id"]: list(a["size"]) for a in spec.get("assets", [])}
    w, h = (int(v) for v in spec["canvas"])
    return {k: spec_mod.normalize_brush({"draw_as": "image", "asset": aid, "image_size": [w, h]}, sizes) for k, aid in brush_assets(spec).items()}


def min_size(spec: dict) -> list[int]:
    return [int(v) for v in spec["canvas"]]


def style_props(spec: dict) -> dict:
    """스타일 애셋의 그림 아닌 값(부모 클래스가 더한 속성) — 테마가 정한 것."""
    b = of(spec) or {}
    return {"PressedTextOffset": list(b["pressed_offset"])} if b.get("pressed_offset") is not None else {}


def style_name(screen_id: str) -> str:
    return f"BS_{screen_id}"


def tree_widgets(spec: dict) -> list[dict]:
    """에디터 트리에 있는 위젯 — art 를 뺀 것."""
    art = art_id(spec)
    return [w for w in spec["widgets"] if w["id"] != art]


def editor_target(spec: dict, style_path: str | None = None) -> dict:
    """apply_widget_spec 의 spec — 정규화한 트리 + locked(+ 버튼 칸이면 defaults.Style)."""
    norm = spec_mod.normalize(spec)
    out = {"root": norm["root"], "widgets": tree_widgets(norm), "locked": norm["locked"]}
    if of(spec):
        if not style_path:
            raise spec_mod.SpecError(["BUTTON_STYLE: a button cell needs its style asset before the widget tree is applied"])
        out["defaults"] = {"Style": style_path}
    return out


def style_diff(spec: dict, export: dict, ue_to_asset: dict[str, str] | None = None, style_path: str | None = None) -> list[str]:
    """버튼 칸의 스타일 ↔ 역추출(export_widget_spec) — 다른 것 목록. 버튼 칸이 아니면 스타일이 없어야 한다."""
    got = export.get("button_style")
    have = ((export.get("spec") or {}).get("defaults") or {}).get("Style")
    if not of(spec):
        return [f"button_style: the spec is not a button cell but the blueprint has style '{have}'"] if have else []
    if not have or not isinstance(got, dict):
        return ["button_style: <missing> — the blueprint's class defaults have no style"]
    out = []
    if style_path and have != style_path:
        out.append(f"button_style.class: {have} != {style_path}")
    b = {k: dict(v) for k, v in (got.get("brushes") or {}).items()}
    for v in b.values():
        asset = v.get("asset")
        if asset and ue_to_asset:
            v["asset"] = ue_to_asset.get(asset) or ue_to_asset.get(asset.split(".", 1)[0]) or asset
    sizes = {a["asset_id"]: list(a["size"]) for a in spec.get("assets", [])}
    out += spec_mod.diff(brushes(spec), {k: spec_mod.normalize_brush(v, sizes) for k, v in b.items()}, "button_style.brushes")
    out += spec_mod.diff(min_size(spec), got.get("min_size"), "button_style.min_size")
    out += spec_mod.diff(style_props(spec), got.get("props") or {}, "button_style.props")
    return out


def geometry_rows(spec: dict, geometry: list[dict]) -> list[dict]:
    """렌더 geometry — 안쪽 버튼의 상자를 art 위젯의 줄로 바꾼다(루트 아래 · Image). 버튼 칸이 아니면 그대로."""
    art = art_id(spec)
    if not art:
        return geometry
    out = []
    for g in geometry:
        if g["id"] == INNER_ID:
            out.append({**g, "id": art, "type": "Image", "parent": spec["root"]})
        elif g["id"] == spec["root"]:
            out.append({**g, "parent": ""})
        else:
            out.append(g)
    return out


def errors(spec: dict) -> list[str]:
    """최상위 button 의 의미 검사(core/spec.validate_semantics 가 부른다)."""
    b = of(spec)
    if not b:
        return [f"DERIVED: '{a['asset_id']}' is a derived asset but the spec has no button" for a in spec.get("assets", []) if a.get("provenance") == "derived"]
    errs = []
    index, root = spec_mod.widget_index(spec), spec.get("root")
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    art = index.get(b["art"])
    brush = ((art or {}).get("style") or {}).get("brush") or {}
    if not art or art.get("type") != "Image" or art.get("parent") != root or brush.get("draw_as", "image") != "image" or not brush.get("asset"):
        errs.append(f"BUTTON_ART: button.art '{b['art']}' must be an Image directly under the root, drawn as image with an asset")
        return errs
    canvas = [float(v) for v in spec["canvas"]]
    bb = art.get("bbox_intent")
    if bb is not None and [float(v) for v in bb] != [0.0, 0.0, *canvas]:
        errs.append(f"BUTTON_ART: '{b['art']}' bbox_intent {bb} must be the whole cell [0, 0, {canvas[0]:g}, {canvas[1]:g}]")
    if any(w.get("parent") == b["art"] for w in spec["widgets"]):
        errs.append(f"BUTTON_ART: '{b['art']}' cannot hold children — the art is the button style, not a widget")
    if art.get("binding"):
        errs.append(f"BUTTON_ART: '{b['art']}' cannot be bound")
    if set(b["states"]) != set(DERIVED):
        errs.append(f"BUTTON_STATES: states {sorted(b['states'])} != {sorted(DERIVED)}")
    for k, aid in b["states"].items():
        a = assets.get(aid)
        if not a or a.get("provenance") != "derived" or (a.get("derived") or {}) != {"from": brush["asset"], "brush": k}:
            errs.append(f"BUTTON_STATES: '{aid}' must be a derived asset {{from: {brush['asset']}, brush: {k}}}")
        elif list(a["size"]) != list((assets.get(brush["asset"]) or {}).get("size") or []):
            errs.append(f"BUTTON_STATES: '{aid}' size {a['size']} differs from its base '{brush['asset']}'")
    for a in spec.get("assets", []):
        if a.get("provenance") == "derived" and a["asset_id"] not in b["states"].values():
            errs.append(f"DERIVED: '{a['asset_id']}' is not one of the button states")
    return errs
