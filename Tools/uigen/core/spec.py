"""spec 의미 검사 · 정규화 · 왕복 비교 (설계 §4-3 · §8-1 '왕복').

구조 · 형식은 schemas/spec.schema.json 이 보고, 여기서는 스키마로 못 보는 것(부모-슬롯 짝 · 타입별 style 키 · 트리 · 참조)을 본다.

정규화 규칙 — 왕복 판정은 roundtrip_view(normalize(입력)) == roundtrip_view(normalize(역추출)):
  - 위젯 순서 = 트리 순서(루트부터 깊이 우선, 형제는 목록 순서). 형제 순서가 곧 슬롯 순서다.
  - 생략한 스칼라(슬롯 · 글꼴 · 정렬 · 보이기 · ProgressBar 값 등)는 아래 기본값 표로 채운다. 표는 5.7.4 UMG 생성자 기본값을 따른다
    [소스] BorderSlot.cpp:18 padding (4,2) · OverlaySlot.cpp:15 Left/Top · VerticalBoxSlot.cpp:17-19 Fill/Fill/Automatic ·
    ButtonSlot.cpp:17-20 (4,2) Center · UniformGridSlot.cpp:16 Left/Top · TextBlock.cpp:35 Roboto 24 Bold · ProgressBar.cpp:30-34 ·
    Spacer.cpp:17 (1,1) · SlateBrush.cpp:11-17 (흰색 · Image · 32×32 · Margin 0) · 패널류 SelfHitTestInvisible(CanvasPanel.cpp:18 등).
    파이프라인은 정규화한(전부 명시한) spec 을 브리지에 보내므로, 표와 엔진 기본값이 어긋나도 파이프라인 왕복은 깨지지 않는다.
  - 생략한 브러시 = 엔진 기본 스타일(CDO). 채우지 않는다 — 역추출도 CDO 와 같은 브러시는 내지 않는다.
    브러시를 적으면 브러시 안의 생략값(draw_as · color · margin · image_size · 둥근 모서리)은 채운다. image_size 기본 = 그 에셋 크기(없으면 32×32).
  - 색은 '#RRGGBBAA' 대문자, 수는 소수 셋째 자리 반올림(정수 값은 정수).
"""
from __future__ import annotations

import copy
import json

WIDGET_TYPES = ("CanvasPanel", "Overlay", "VerticalBox", "HorizontalBox", "UniformGridPanel", "SizeBox",
                "Border", "Image", "TextBlock", "ProgressBar", "Button", "Spacer")

# 부모 타입 → 자식 슬롯 kind
CHILD_SLOT_KIND = {"CanvasPanel": "canvas", "Overlay": "overlay", "VerticalBox": "vertical_box", "HorizontalBox": "horizontal_box",
                   "UniformGridPanel": "uniform_grid", "Border": "border", "SizeBox": "size_box", "Button": "button"}
SINGLE_CHILD = frozenset({"Border", "SizeBox", "Button"})
LEAF = frozenset({"Image", "TextBlock", "ProgressBar", "Spacer"})

STYLE_KEYS = {
    "Border": {"brush"},
    "Image": {"brush"},
    "ProgressBar": {"background", "fill", "fill_color", "percent", "bar_fill_type"},
    "SizeBox": {"width_override", "height_override"},
    "Spacer": {"size"},
    "UniformGridPanel": {"slot_padding", "min_slot_width", "min_slot_height"},
    "Button": {"normal", "hovered", "pressed"},
}
BRUSH_KEYS = frozenset({"brush", "background", "fill", "normal", "hovered", "pressed"})

# 바인딩 kind → 받을 수 있는 위젯 타입 (None = 아무 위젯 — flag 는 보이기만 바꾼다)
BINDING_WIDGET_TYPES = {"progress": {"ProgressBar"}, "text": {"TextBlock"}, "number": {"TextBlock"}, "image": {"Image"}, "flag": None}

SLOT_DEFAULTS = {
    "canvas": {"anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [0, 0], "size": [100, 30], "z": 0, "auto_size": False},
    "overlay": {"padding": [0, 0, 0, 0], "h_align": "left", "v_align": "top"},
    "vertical_box": {"padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill", "size_rule": "auto", "fill": 1},
    "horizontal_box": {"padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill", "size_rule": "auto", "fill": 1},
    "uniform_grid": {"row": 0, "column": 0, "h_align": "left", "v_align": "top"},
    "border": {"padding": [4, 2, 4, 2], "h_align": "fill", "v_align": "fill"},
    "size_box": {"padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill"},
    "button": {"padding": [4, 2, 4, 2], "h_align": "center", "v_align": "center"},
}
PANEL_TYPES = frozenset({"CanvasPanel", "Overlay", "VerticalBox", "HorizontalBox", "UniformGridPanel", "SizeBox", "Spacer"})
FONT_DEFAULT = {"size": 24, "weight": "bold", "color": "#FFFFFFFF", "family": None}
STYLE_SCALAR_DEFAULTS = {
    "ProgressBar": {"fill_color": "#FFFFFFFF", "percent": 0, "bar_fill_type": "left_to_right"},
    "Spacer": {"size": [1, 1]},
    "UniformGridPanel": {"slot_padding": [0, 0, 0, 0], "min_slot_width": 0, "min_slot_height": 0},
}
BRUSH_DEFAULT_IMAGE_SIZE = [32, 32]

# WBP 가 담지 않는 위젯 필드 — 왕복 비교에서 뺀다 (바인딩은 부모 클래스의 BindWidget 이 담는다)
NON_WBP_WIDGET_FIELDS = ("bbox_intent", "binding", "note")


class SpecError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} spec error(s): " + "; ".join(errors[:5]))


# ---------------------------------------------------------------------------------------------------------------------
# 값 정규화

def canon_number(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return v
    r = round(float(v), 3)
    if r == 0:
        return 0  # -0.0 도 0
    return int(r) if r == int(r) else r


def canon_color(s: str) -> str:
    s = s.strip().upper()
    if len(s) == 7:
        s += "FF"
    return s


def parse_color(s: str) -> tuple[int, int, int, int]:
    s = canon_color(s)
    return int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16), int(s[7:9], 16)


def _canon(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _canon(v, k) for k, v in value.items() if v is not None or k == "family"}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, str) and key and key.endswith("color"):
        return canon_color(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return canon_number(value)
    return value


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------------------------------------------------
# 트리

def widget_index(spec: dict) -> dict[str, dict]:
    return {w["id"]: w for w in spec.get("widgets", [])}


def children_map(spec: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {w["id"]: [] for w in spec.get("widgets", [])}
    for w in spec.get("widgets", []):
        p = w.get("parent")
        if p is not None and p in out:
            out[p].append(w["id"])
    return out


def tree_order(spec: dict) -> list[str]:
    """루트부터 깊이 우선. 도달 못 하는 위젯은 빠진다(validate_semantics 가 따로 잡는다)."""
    kids = children_map(spec)
    root = spec.get("root")
    out, seen = [], set()
    stack = [root] if root in kids else []
    while stack:
        wid = stack.pop()
        if wid in seen:
            continue
        seen.add(wid)
        out.append(wid)
        stack.extend(reversed(kids.get(wid, [])))
    return out


def descendants(spec: dict, wid: str) -> list[str]:
    kids = children_map(spec)
    out, stack = [], list(kids.get(wid, []))
    while stack:
        c = stack.pop()
        out.append(c)
        stack.extend(kids.get(c, []))
    return out


def bound_widgets(spec: dict) -> dict[str, dict]:
    """바인딩 있는 위젯 id → binding."""
    return {w["id"]: w["binding"] for w in spec.get("widgets", []) if w.get("binding")}


# ---------------------------------------------------------------------------------------------------------------------
# 의미 검사

def validate_semantics(spec: dict) -> list[str]:
    errs: list[str] = []
    widgets = spec.get("widgets", [])
    ids = [w.get("id") for w in widgets]
    seen: set[str] = set()
    for wid in ids:
        if wid in seen:
            errs.append(f"DUPLICATE_ID: '{wid}'")
        seen.add(wid)
    index = widget_index(spec)
    root = spec.get("root")
    if root not in index:
        return errs + [f"NO_ROOT: root '{root}' is not in widgets[]"]
    root_w = index[root]
    if root_w.get("parent") is not None:
        errs.append(f"ROOT_HAS_PARENT: '{root}'")
    if root_w.get("slot") is not None:
        errs.append(f"ROOT_HAS_SLOT: '{root}' (the root has no parent slot)")
    if root_w.get("type") not in CHILD_SLOT_KIND:
        errs.append(f"ROOT_NOT_PANEL: root '{root}' is a {root_w.get('type')}")

    kids = children_map(spec)
    for w in widgets:
        wid, wtype, parent = w.get("id"), w.get("type"), w.get("parent")
        if wid == root:
            pass
        elif parent is None:
            errs.append(f"NO_PARENT: '{wid}'")
        elif parent not in index:
            errs.append(f"PARENT_NOT_FOUND: '{wid}' → '{parent}'")
        else:
            ptype = index[parent].get("type")
            if ptype in LEAF:
                errs.append(f"PARENT_IS_LEAF: '{wid}' under {ptype} '{parent}'")
            expected = CHILD_SLOT_KIND.get(ptype)
            slot = w.get("slot")
            if slot is not None and expected and slot.get("kind") != expected:
                errs.append(f"SLOT_KIND: '{wid}' slot.kind '{slot.get('kind')}' but parent '{parent}' is a {ptype} (needs '{expected}')")
        if wtype in SINGLE_CHILD and len(kids.get(wid, [])) > 1:
            errs.append(f"TOO_MANY_CHILDREN: {wtype} '{wid}' holds one child, has {len(kids[wid])}")
        allowed_style = STYLE_KEYS.get(wtype, set())
        for key in (w.get("style") or {}):
            if key not in allowed_style:
                errs.append(f"STYLE_KEY: '{wid}' ({wtype}) has no style '{key}'")
        if wtype != "TextBlock":
            for key in ("text", "font", "justification"):
                if key in w:
                    errs.append(f"TEXT_FIELD: '{wid}' ({wtype}) cannot have '{key}'")
        binding = w.get("binding")
        if binding:
            okay = BINDING_WIDGET_TYPES.get(binding.get("kind"))
            if okay is not None and wtype not in okay:
                errs.append(f"BINDING_TYPE: '{wid}' ({wtype}) cannot take a '{binding.get('kind')}' binding")
            if binding.get("format") and binding.get("kind") != "number":
                errs.append(f"BINDING_FORMAT: '{wid}' format is only for number bindings")
        text = w.get("text") or {}
        if text.get("source", "static") == "static" and ("data" in text or "sample" in text):
            errs.append(f"TEXT_STATIC: '{wid}' static text has data/sample (use source: dynamic)")
        if text.get("source") == "dynamic" and "value" in text:
            errs.append(f"TEXT_DYNAMIC: '{wid}' dynamic text has value (use sample)")
        if text.get("source") == "dynamic" and (not binding or binding.get("data") != text.get("data")):
            errs.append(f"TEXT_DATA: '{wid}' dynamic text data '{text.get('data')}' must match its binding data")

    reachable = set(tree_order(spec))
    for wid in ids:
        if wid not in reachable:
            errs.append(f"UNREACHABLE: '{wid}' is not under root '{root}' (cycle or broken parent chain)")

    data_seen: dict[str, str] = {}
    for wid, b in bound_widgets(spec).items():
        if b["data"] in data_seen:
            errs.append(f"DUPLICATE_BINDING_DATA: '{b['data']}' on '{data_seen[b['data']]}' and '{wid}'")
        data_seen[b["data"]] = wid

    assets = spec.get("assets", [])
    asset_ids = [a.get("asset_id") for a in assets]
    if len(set(asset_ids)) != len(asset_ids):
        errs.append("DUPLICATE_ASSET_ID")
    for a in assets:
        if a.get("nine_slice") is False and a.get("margin"):
            errs.append(f"ASSET_MARGIN: '{a['asset_id']}' has margin but nine_slice is false")
    for w in widgets:
        for key, brush in (w.get("style") or {}).items():
            if key in BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset") and brush["asset"] not in asset_ids:
                errs.append(f"ASSET_NOT_FOUND: '{w.get('id')}'.style.{key} → '{brush['asset']}'")
            if key in BRUSH_KEYS and isinstance(brush, dict) and brush.get("draw_as") == "rounded_box" and brush.get("margin"):
                errs.append(f"BRUSH_MARGIN: '{w.get('id')}'.style.{key} rounded_box has no 9-slice margin")
    for pair in spec.get("allow_overlap", []):
        for wid in pair:
            if wid not in index:
                errs.append(f"ALLOW_OVERLAP_NOT_FOUND: '{wid}'")
    for wid in spec.get("locked", []):
        if wid not in index:
            errs.append(f"LOCKED_NOT_FOUND: '{wid}'")
    return errs


def require_valid(spec: dict) -> None:
    errs = validate_semantics(spec)
    if errs:
        raise SpecError(errs)


# ---------------------------------------------------------------------------------------------------------------------
# 정규화

def _asset_sizes(spec: dict) -> dict[str, list]:
    return {a["asset_id"]: list(a["size"]) for a in spec.get("assets", []) if "asset_id" in a and "size" in a}


def normalize_brush(brush: dict, asset_sizes: dict[str, list]) -> dict:
    b = _canon(brush)
    draw_as = b.setdefault("draw_as", "image")
    b.setdefault("color", "#FFFFFFFF")
    if draw_as in ("box", "border"):
        b.setdefault("margin", [0, 0, 0, 0])
    if draw_as == "rounded_box":
        b.setdefault("radius", 0)
        b.setdefault("outline_color", "#00000000")
        b.setdefault("outline_width", 0)
    if draw_as != "none":
        b.setdefault("image_size", list(asset_sizes.get(b.get("asset"), BRUSH_DEFAULT_IMAGE_SIZE)))
    return _canon(b)


def normalize_widget(w: dict, parent_type: str | None, asset_sizes: dict[str, list]) -> dict:
    out = _canon(copy.deepcopy(w))
    wtype = out["type"]
    if parent_type is not None:
        kind = CHILD_SLOT_KIND.get(parent_type)
        slot = dict(out.get("slot") or {})
        if kind:
            slot.setdefault("kind", kind)
            for k, v in SLOT_DEFAULTS.get(slot["kind"], {}).items():
                slot.setdefault(k, copy.deepcopy(v))
        out["slot"] = _canon(slot)
    out.setdefault("visibility", "self_hit_test_invisible" if wtype in PANEL_TYPES else "visible")
    style = dict(out.get("style") or {})
    for k, v in STYLE_SCALAR_DEFAULTS.get(wtype, {}).items():
        style.setdefault(k, copy.deepcopy(v))
    for key in list(style):
        if key in BRUSH_KEYS and isinstance(style[key], dict):
            style[key] = normalize_brush(style[key], asset_sizes)
    if style:
        out["style"] = _canon(style)
    else:
        out.pop("style", None)
    if wtype == "TextBlock":
        text = dict(out.get("text") or {})
        text.setdefault("source", "static")
        if text["source"] == "static":
            text.setdefault("value", "")
        else:
            text.setdefault("sample", "")
        out["text"] = text
        font = dict(FONT_DEFAULT)
        font.update(out.get("font") or {})
        out["font"] = _canon(font)
        out.setdefault("justification", "left")
    if out.get("binding"):
        b = out["binding"]
        b.setdefault("optional", False)
    return out


def normalize(spec: dict, asset_sizes: dict[str, list] | None = None) -> dict:
    """정규화한 새 spec. 의미 검사를 통과한 spec 을 준다(트리 밖 위젯은 빠진다)."""
    sizes = _asset_sizes(spec) if asset_sizes is None else asset_sizes
    index = widget_index(spec)
    widgets = []
    for wid in tree_order(spec):
        w = index[wid]
        parent_type = index[w["parent"]]["type"] if w.get("parent") in index else None
        widgets.append(normalize_widget(w, parent_type, sizes))
    out = {k: _canon(copy.deepcopy(v)) for k, v in spec.items() if k != "widgets"}
    out["widgets"] = widgets
    out.setdefault("assets", [])
    out.setdefault("allow_overlap", [])
    out.setdefault("locked", [])
    out["allow_overlap"] = sorted(sorted(p) for p in out["allow_overlap"])
    out["locked"] = sorted(out["locked"])
    out.pop("note", None)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 왕복

def roundtrip_view(spec: dict, ue_path_to_asset: dict[str, str] | None = None, asset_sizes: dict[str, list] | None = None) -> dict:
    """WBP 가 담는 것만 남긴 정규화 투영.

    ue_path_to_asset — 역추출 spec 의 브러시 asset 은 UE 경로(/Game/_AutoGen/<run>/T_x)다. manifest 의 ue_path → asset_id 로 바꿔 비교한다.
    asset_sizes — 역추출 spec 에는 assets[] 가 없으므로 입력 spec 의 에셋 크기를 준다(image_size 기본값).
    """
    src = copy.deepcopy(spec)
    if ue_path_to_asset:
        for w in src.get("widgets", []):
            for key, brush in (w.get("style") or {}).items():
                if key in BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset"):
                    asset = brush["asset"]
                    bare = asset.split(".", 1)[0]
                    brush["asset"] = ue_path_to_asset.get(asset) or ue_path_to_asset.get(bare) or asset
    norm = normalize(src, asset_sizes)
    widgets = []
    for w in norm["widgets"]:
        v = {k: val for k, val in w.items() if k not in NON_WBP_WIDGET_FIELDS}
        if "text" in v:
            t = v["text"]
            v["text"] = {"value": t.get("value", t.get("sample", ""))}
        widgets.append(v)
    return {"root": norm["root"], "widgets": widgets}


def diff(a, b, path: str = "", limit: int = 50) -> list[str]:
    """첫 limit 개 차이를 'path: a != b' 로."""
    out: list[str] = []

    def walk(x, y, p):
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x:
                    out.append(f"{p}.{k}: <missing> != {canonical_json(y[k])}")
                elif k not in y:
                    out.append(f"{p}.{k}: {canonical_json(x[k])} != <missing>")
                else:
                    walk(x[k], y[k], f"{p}.{k}")
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (xi, yi) in enumerate(zip(x, y)):
                key = xi.get("id") if isinstance(xi, dict) and isinstance(yi, dict) and xi.get("id") == yi.get("id") and "id" in xi else i
                walk(xi, yi, f"{p}[{key}]")
        elif x != y:
            out.append(f"{p}: {canonical_json(x)} != {canonical_json(y)}")

    walk(a, b, path or "$")
    return out


def roundtrip_equal(spec: dict, exported: dict, ue_path_to_asset: dict[str, str] | None = None) -> tuple[bool, list[str]]:
    sizes = _asset_sizes(spec)
    left = roundtrip_view(spec, asset_sizes=sizes)
    right = roundtrip_view(exported, ue_path_to_asset, asset_sizes=sizes)
    d = diff(left, right)
    return not d, d
