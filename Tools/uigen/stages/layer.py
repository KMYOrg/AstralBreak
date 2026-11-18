"""layer — 기능 단위로 쪼개기 (1b 후속 J-a — analyze 뒤 결정적 단계, LLM 없음).

1b 후속 A ~ I 는 런타임에 안 바뀌는 장식까지 보이는 요소마다 텍스처로 쪼갰고, 한 장으로 칠한 그림을 겹치게 나누는 자리마다 '이 픽셀은 누구 것'에
정답이 없어 소유 규칙을 덧댔다(이중 · 'T' 가림 · ㄴ자 구멍 · 계단 · 절취선 · 직선 잘림 · 배지 양옆 선 — 설계 §11 'J 설계'). 원칙: 텍스처를 나누는
기준 = 런타임 기능.

  기능 요소(따로 그린다) = 바인딩(글자 · 숫자 · 게이지 · 런타임 이미지 · flag) · 시작 때 숨은 위젯 · 그 아래 전부(같이 접힌다) · 버튼 ·
    크기가 변하는 9-slice(box · border 브러시 + 크기 고정 아님) · 크기 고정이 아닌 영역 안 · inputs `separate`(사람이 따로 두고 싶은 요소 id).
    고정 글자는 지금처럼 엔진 TextBlock(현지화).
  정적 장식(그 밖의 '컨셉에서 오리는' 이미지 브러시) → 브러시는 그리지 않음(draw_as none, 위젯은 자리 · 필수 요소로 남음) · 에셋은 spec 에서 뺌.
  정적 판 = 컨셉에서 보이는 픽셀(알파 > 0.02) 중 기능 요소 자리(오리는 기능 요소 상자 · 런타임 이미지 상자)를 뺀
    전부를, 그 픽셀이 속한 영역(루트 직계 — 상자 안, 아니면 가장 가까운 상자)의 앵커 묶음마다 2 px 넓혀 이은 덩어리로 나눠 덩어리마다 텍스처
    하나(투명한 틈에서만 나뉘므로 공유 픽셀 · 경계 없음). 크기 상한 layers.plate_max(2048 — 넘으면 가장 투명한 열 · 줄에서 둘로). 판 위젯 =
    캔버스 직속 Image `StaticPlate<n>`(그 영역과 같은 앵커 · 정렬 — 해상도가 바뀌어도 같이 움직인다), 그리는 순서는 맨 아래(가장 작은 z · 루트 자식 맨 앞).
  글자 자리 · 게이지 트랙 메우기는 refine 의 판 텍스처 단계(_plate_entry)가 한다(글자 없는 판 · 줄 보간 · unfilled_track).
기록: layer.json · 판 마스크 layer/plate_<n>.png. ⓐ ⓑ(알파를 아는 컨셉)만 — ⓒ 는 예전처럼 요소마다 오린다(건너뜀 + 이유).
"""
from __future__ import annotations

import numpy as np

from core import schema
from core import spec as spec_mod
from stages import StageError

PLATE_PREFIX = "StaticPlate"
PLATE_ASSET = "static_plate"
VISIBLE = 0.02
JOIN_PX = 2
MIN_PLATE_PX = 24            # 이보다 작은 떨어진 덩어리(알파 잡티)는 판으로 만들지 않는다


def settings(cfg: dict) -> dict:
    c = dict((cfg or {}).get("layers") or {})
    c.setdefault("enabled", True)
    c.setdefault("plate_max", 2048)
    return c


def _index(spec: dict) -> dict:
    return spec_mod.widget_index(spec)


def _region(spec: dict, wid: str) -> dict | None:
    index = _index(spec)
    root = spec.get("root") or "Root"
    w = index.get(wid)
    while w is not None and w.get("parent") and w["parent"] != root:
        w = index.get(w["parent"])
    return w if w is not None and w.get("parent") == root else None


def _extract_ids(spec: dict) -> set[str]:
    return {a["asset_id"] for a in spec.get("assets", []) if a.get("source_mode") == "extract"}


def _brush_assets(w: dict) -> list[tuple[str, dict]]:
    return [(k, b) for k, b in (w.get("style") or {}).items() if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset")]


def classify(spec: dict, inputs: dict | None = None) -> dict[str, str]:
    """위젯 id → 기능 요소 이유(정적 장식 · 무관 위젯은 빠짐). 정적 장식 판단은 static_widgets."""
    from stages import refine
    index = _index(spec)
    separate = set((inputs or {}).get("separate") or [])
    out: dict[str, str] = {}

    def own_reason(w: dict) -> str | None:
        b = (w.get("binding") or {}).get("kind")
        if b:
            return f"binding {b}"
        if w.get("visibility") in ("collapsed", "hidden"):
            return f"starts {w['visibility']}"
        if w.get("type") == "Button":
            return "button"
        if w["id"] in separate:
            return "inputs separate"
        if any(b.get("draw_as") in ("box", "border") for _, b in _brush_assets(w)) and not refine.fixed_size(spec, w["id"]):
            return "9-slice that changes size"
        return None
    for w in spec.get("widgets", []):
        r = own_reason(w)
        if r:
            out[w["id"]] = r
    # 기능 요소(flag · 숨김 · 버튼 · separate) 아래는 같이 접히고 같이 움직인다 — 그 레이어
    for w in spec.get("widgets", []):
        if w["id"] in out:
            continue
        p = w.get("parent")
        while p and p in index:
            if p in out and out[p].split(" ")[0] in ("binding", "starts", "button", "inputs") and not out[p].startswith(("binding text", "binding number",
                                                                                                                          "binding progress", "binding image")):
                out[w["id"]] = f"inside {p} ({out[p]})"
                break
            p = index[p].get("parent")
    for w in spec.get("widgets", []):
        if w["id"] not in out and _brush_assets(w) and not refine.fixed_size(spec, w["id"]):
            out[w["id"]] = "region changes size with the screen"
    return out


def static_widgets(spec: dict, functional: dict[str, str]) -> list[str]:
    """정적 장식 = 기능 요소가 아니고 브러시가 전부 '컨셉에서 오리는'(extract) 에셋인 위젯 — 판으로 굽는다."""
    ext = _extract_ids(spec)
    out = []
    for w in spec.get("widgets", []):
        if w["id"] in functional or w.get("type") in ("TextBlock", "RichTextBlock", "ProgressBar"):
            continue
        br = _brush_assets(w)
        if br and all(b["asset"] in ext and b.get("draw_as", "image") != "none" for _, b in br):
            out.append(w["id"])
    return out


def _int_box(bb, W: int, H: int):
    x0, y0 = int(np.floor(float(bb[0]))), int(np.floor(float(bb[1])))
    x1, y1 = int(np.ceil(float(bb[0]) + float(bb[2]))), int(np.ceil(float(bb[1]) + float(bb[3])))
    return max(0, x0), max(0, y0), min(W, x1), min(H, y1)


def _split(mask, box, limit: int) -> list[list[int]]:
    """덩어리 상자가 limit 을 넘으면 가장 투명한(마스크 픽셀이 가장 적은) 가운데 쪽 열 · 줄에서 둘로 — 상자 목록 [x0, y0, x1, y1]."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= limit and h <= limit:
        return [box]
    sub = mask[y0:y1, x0:x1]
    if w >= h:
        prof = sub.sum(axis=0).astype(float)
        lo, hi = int(0.25 * w), max(int(0.75 * w), int(0.25 * w) + 1)
        c = x0 + lo + int(np.argmin(prof[lo:hi]))
        return _split(mask, [x0, y0, c, y1], limit) + _split(mask, [c, y0, x1, y1], limit)
    prof = sub.sum(axis=1).astype(float)
    lo, hi = int(0.25 * h), max(int(0.75 * h), int(0.25 * h) + 1)
    c = y0 + lo + int(np.argmin(prof[lo:hi]))
    return _split(mask, [x0, y0, x1, c], limit) + _split(mask, [x0, c, x1, y1], limit)


def plan(spec: dict, alpha, functional: dict[str, str], static: list[str], plate_max: int = 2048) -> dict:
    """정적 판 계획 → {"plates": [{"n", "box", "region", "mask"(캔버스 bool)}], "func_zone", "excluded_px", …}."""
    import cv2
    H, W = alpha.shape
    root = spec.get("root") or "Root"
    index = _index(spec)
    ext = _extract_ids(spec)
    vis = alpha > VISIBLE
    func_zone = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        bb = w.get("bbox_intent")
        if not bb:
            continue
        cut_fn = w["id"] in functional and any(b["asset"] in ext and b.get("draw_as") != "none" for _, b in _brush_assets(w))
        runtime = w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image"
        if cut_fn or runtime:
            x0, y0, x1, y1 = _int_box(bb, W, H)
            func_zone[y0:y1, x0:x1] = True
    # 기능 요소 상자 안은 판에 넣지 않는다 — 상자 안쪽 불투명 2 px 를 판도 같이 그리면(확대 절취선 메움) flag 패널이 숨어도 테두리가 판에 남았다(J-a 시험)
    static_px = vis & ~func_zone
    # 영역(루트 직계) — 상자 안이면 그 영역, 아니면 가장 가까운 상자. 크기 고정이 아닌 영역 몫은 판에 넣지 않는다(그 영역 장식은 기능 요소 길)
    from stages import refine
    regions = [w for w in spec.get("widgets", []) if w.get("parent") == root and w.get("bbox_intent") and not w["id"].startswith(PLATE_PREFIX)]
    if not regions:
        return {"plates": [], "func_zone_px": int(func_zone.sum()), "reason": "no canvas regions"}
    big = np.full((H, W), np.inf, np.float32)
    owner = np.full((H, W), -1, np.int32)
    for k, r in enumerate(regions):
        x0, y0, x1, y1 = _int_box(r["bbox_intent"], W, H)
        m = np.ones((H, W), np.uint8)
        m[y0:y1, x0:x1] = 0
        d = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        sel = d < big
        owner[sel] = k
        big[sel] = d[sel]
    fixed = [refine.fixed_size(spec, r["id"]) for r in regions]
    groups: dict[tuple, list[int]] = {}
    for k, r in enumerate(regions):
        if not fixed[k]:
            continue
        slot = r.get("slot") or {}
        key = (tuple(float(v) for v in (slot.get("anchors") or [0, 0, 0, 0])), tuple(float(v) for v in (slot.get("alignment") or [0, 0])))
        groups.setdefault(key, []).append(k)
    # 글자 자리(상자 + 빛 + 4 px) — 그 안에만 있는 덩어리는 글자뿐이라 판으로 만들지 않는다(엔진 글자가 그린다)
    text_zone = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        if w.get("type") in ("TextBlock", "RichTextBlock") and w.get("bbox_intent"):
            g = float(((w.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(w.get("font"), dict) else 0.0
            bb = w["bbox_intent"]
            x0, y0, x1, y1 = _int_box([bb[0] - g - 4, bb[1] - g - 4, bb[2] + 2 * g + 8, bb[3] + 2 * g + 8], W, H)
            text_zone[y0:y1, x0:x1] = True
    plates, n, text_only, specks = [], 0, 0, 0
    dropped = int((static_px & ~np.isin(owner, [k for k in range(len(regions)) if fixed[k]])).sum())
    for key, ks in groups.items():
        gm = static_px & np.isin(owner, ks)
        if not gm.any():
            continue
        cnt, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(gm.astype(np.uint8), np.ones((2 * JOIN_PX + 1,) * 2, np.uint8)), connectivity=8)
        for i in range(1, cnt):
            comp = gm & (lab == i)
            if not comp.any():
                continue
            if float(text_zone[comp].mean()) >= 0.9:
                text_only += int(comp.sum())
                continue
            if int(comp.sum()) < MIN_PLATE_PX:               # 떨어진 잡티(알파 몇 픽셀) — 진단 최소 넓이보다 작다
                specks += int(comp.sum())
                continue
            ys, xs = np.nonzero(comp)
            box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            # 영역 = 이 덩어리에서 픽셀이 가장 많은 영역(앵커는 묶음이 같다)
            rk = int(np.bincount(owner[comp][owner[comp] >= 0], minlength=len(regions)).argmax())
            for b in _split(comp, box, int(plate_max)):
                sub = np.zeros((H, W), bool)
                sub[b[1]:b[3], b[0]:b[2]] = comp[b[1]:b[3], b[0]:b[2]]
                if not sub.any():
                    continue
                ys2, xs2 = np.nonzero(sub)
                bb = [int(xs2.min()), int(ys2.min()), int(xs2.max()) + 1, int(ys2.max()) + 1]
                for lo, hi, lim in ((0, 2, W), (1, 3, H)):         # 텍스처 최소 4 px(스키마) — 가는 덩어리는 상자만 넓힘(마스크 그대로)
                    if bb[hi] - bb[lo] < 4:
                        c = (bb[lo] + bb[hi]) // 2
                        bb[lo] = max(0, min(c - 2, lim - 4))
                        bb[hi] = bb[lo] + 4
                n += 1
                plates.append({"n": n, "box": [bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1]], "region": regions[rk]["id"], "mask": sub,
                               "px": int(sub.sum())})
    return {"plates": plates, "func_zone_px": int(func_zone.sum()), "unassigned_px": dropped,
            "text_only_px": text_only, "specks_px": specks, "regions": [r["id"] for r in regions]}


def apply(spec: dict, functional: dict[str, str], static: list[str], plates: list[dict]) -> dict:
    """spec 을 바꾼다 — 정적 장식 브러시 → none, 안 쓰이는 extract 에셋 빼기, 판 에셋 · 판 위젯(루트 자식 맨 앞 · 가장 작은 z) · 겹침 허용 쌍. → 기록."""
    root = spec.get("root") or "Root"
    index = _index(spec)
    cw, ch = (float(v) for v in spec.get("canvas", [1920, 1080]))
    changed = []
    for wid in static:
        w = index[wid]
        for k, b in _brush_assets(w):
            changed.append({"widget": wid, "key": k, "old": dict(b)})
            w["style"][k] = {"draw_as": "none"}
    # 판 위 게이지의 텍스처 없는 배경(엔진 둥근 상자 · 색 칠)은 그리지 않는다 — 판이 컨셉의 빈 트랙을 그린다(채움만 게이지가 그림)
    # [실측 J R20261117_191858 파티 HUD — analyze 가 0 % 게이지 배경을 둥근 상자로 칠해 판의 트랙을 덮어 국소 ΔE00 최대 79]
    gauge_bg = []
    for w in spec.get("widgets", []):
        bb, st = w.get("bbox_intent"), w.get("style") or {}
        bgb = st.get("background")
        if w.get("type") != "ProgressBar" or not bb or not isinstance(bgb, dict) or bgb.get("asset") or bgb.get("draw_as", "image") == "none":
            continue
        x0, y0 = int(bb[0]), int(bb[1])
        x1, y1 = int(np.ceil(bb[0] + bb[2])), int(np.ceil(bb[1] + bb[3]))
        on_plate = any(p["mask"][max(0, y0):y1, max(0, x0):x1].mean() > 0.5 for p in plates if p.get("mask") is not None and y1 > y0 and x1 > x0)
        if on_plate:
            gauge_bg.append({"widget": w["id"], "old": dict(bgb)})
            st["background"] = {"draw_as": "none"}
    used = {b["asset"] for w in spec.get("widgets", []) for _, b in _brush_assets(w)}
    removed = [a["asset_id"] for a in spec.get("assets", []) if a.get("source_mode") == "extract" and a["asset_id"] not in used]
    spec["assets"] = [a for a in spec.get("assets", []) if a["asset_id"] not in removed]
    zs = [float((w.get("slot") or {}).get("z", 0)) for w in spec.get("widgets", []) if w.get("parent") == root]
    zmin = min(zs) if zs else 0
    zmin = int(zmin) if float(zmin).is_integer() else zmin
    first = next((i for i, w in enumerate(spec["widgets"]) if w.get("parent") == root), len(spec["widgets"]))
    added = []
    for p in plates:
        reg = index[p["region"]]
        slot = reg.get("slot") or {}
        an, al = list(slot.get("anchors") or [0, 0, 0, 0]), list(slot.get("alignment") or [0, 0])
        x, y, w, h = (float(v) for v in p["box"])
        pos = [round(x + al[0] * w - an[0] * cw, 2), round(y + al[1] * h - an[1] * ch, 2)]
        aid, wid = f"{PLATE_ASSET}{p['n']}", f"{PLATE_PREFIX}{p['n']}"
        spec["assets"].append({"asset_id": aid, "kind": "ornament", "provenance": "provided", "source_mode": "plate", "size": [int(w), int(h)],
                               "source": f"static plate {p['n']} — concept pixels of the non-functional decorations (region {p['region']})"})
        deco = {"id": wid, "type": "Image", "parent": root, "bbox_intent": [x, y, w, h],
                "slot": {"kind": "canvas", "anchors": an, "alignment": al, "position": pos, "size": [w, h], "z": zmin},
                "style": {"brush": {"draw_as": "image", "asset": aid}}}
        spec["widgets"].insert(first, deco)
        first += 1
        pairs = []
        for o in spec["widgets"]:
            ob = o.get("bbox_intent")
            if o.get("parent") == root and o["id"] != wid and ob and \
                    min(x + w, ob[0] + ob[2]) > max(x, ob[0]) and min(y + h, ob[1] + ob[3]) > max(y, ob[1]):
                pair = sorted([wid, o["id"]])
                if pair not in spec.setdefault("allow_overlap", []):
                    spec["allow_overlap"].append(pair)
                pairs.append(o["id"])
        added.append({"widget": wid, "asset": aid, "box": p["box"], "region": p["region"], "px": p["px"], "allow_overlap_with": pairs})
    return {"static_brushes": changed, "removed_assets": removed, "plates": added, "gauge_backgrounds": gauge_bg}


def run(run, opts) -> str:
    from PIL import Image
    from stages import generate
    cfg = settings(run.cfg)
    if not cfg["enabled"]:
        run.write_json("layer.json", {"applied": False, "reason": "layers.enabled is off"})
        return "skipped — layers.enabled is off"
    bg = generate.background_kind(run)
    if bg not in ("transparent", "flat") or not run.path("reference_alpha.png").is_file():
        run.write_json("layer.json", {"applied": False, "reason": f"background {bg} — the concept alpha is unknown, elements are cut one by one as before"})
        return f"skipped — background {bg} (no concept alpha)"
    spec = run.read_json("spec.json")
    inputs = run.read_json("inputs.json") if run.path("inputs.json").is_file() else {}
    functional = classify(spec, inputs)
    static = static_widgets(spec, functional)
    if not static:
        run.write_json("layer.json", {"applied": False, "reason": "no static decoration to bake", "functional": functional})
        return "no static decoration — every drawn element is functional"
    from stages.refine import _reference_layers, art_files
    if art_files(run):              # 1b 후속 K-a — 우리가 만든 컨셉은 글자 없는 아트(투명 위 글자 잔상 지움)의 보이는 픽셀로 판을 나눈다
        alpha = _reference_layers(run, bg)[1]
    else:
        with Image.open(run.path("reference_alpha.png")) as im:
            alpha = np.asarray(im.convert("L"), float) / 255.0
    pl = plan(spec, alpha, functional, static, int(cfg["plate_max"]))
    if not pl["plates"]:
        run.write_json("layer.json", {"applied": False, "reason": "no visible static pixels", "functional": functional, "static": static})
        return "no visible static pixels"
    rec = apply(spec, functional, static, pl["plates"])
    errs = spec_mod.validate_semantics(spec)
    if errs:
        raise StageError("SPEC_INVALID", "layer left an invalid spec: " + "; ".join(errs[:6]), errors=errs)
    schema.require("spec", spec)
    run.path("layer").mkdir(parents=True, exist_ok=True)
    for p in pl["plates"]:
        Image.fromarray((p["mask"] * 255).astype(np.uint8), "L").save(run.path("layer", f"plate_{p['n']}.png"))
    run.write_json("spec.json", spec)
    run.write_json("layer.json", {"applied": True, "functional": functional, "static": static, "plates": rec["plates"],
                                  "removed_assets": rec["removed_assets"], "static_brushes": rec["static_brushes"], "gauge_backgrounds": rec["gauge_backgrounds"],
                                  "func_zone_px": pl["func_zone_px"], "unassigned_px": pl.get("unassigned_px"),
                                  "text_only_px": pl.get("text_only_px"), "specks_px": pl.get("specks_px"),
                                  "masks": [f"layer/plate_{p['n']}.png" for p in pl["plates"]]})
    return (f"{len(static)} static decoration(s) → {len(rec['plates'])} plate(s) {[p['box'] for p in rec['plates']]}, functional {len(functional)}, "
            f"removed assets {rec['removed_assets']}")
