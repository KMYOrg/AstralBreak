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
  접히는 위젯의 빛 · 넘침(L-2 기본 전환 ④, 11-23) — 런타임에 접히는 루트 직계 영역(flag 바인딩 · 시작 때 숨음)의 상자 밖 빛은 늘 보이는 판에 남아, 위젯이
    접혀도 빛 테두리가 보였다 [실측 L-2 R20261120_140653 — 배너 23,021 px · 체인 패널 19,583 px, 국소 ΔE00 최대 23]. 그래서 판을 나누기 전에 그 영역 몫
    (gen/territory.claim — 가장 가까운 영역 · 96 px 안)을 **자기 마스크**로 잡고 위젯 상자를 그 범위까지 넓힌다(grow_toggles): canvas 슬롯 자리 · 크기 ·
    bbox_intent · 에셋 크기 · margin 을 같이 바꾸고 자식은 슬롯 여백을 같은 만큼 늘려 화면 자리를 그대로 둔다. 판은 상자 대신 자기 마스크를 빼고, 오리기는 자기 마스크
    밖을 투명으로(refine._cut_entry) — 이웃 픽셀을 안 가져간다. 넓힐 수 없는 구조면 이유를 기록하고(그 빛은 판에 남는다) 상태 검사 hidden_halo 가 잡는다.
기록: layer.json · 판 마스크 layer/plate_<n>.png. ⓐ ⓑ(알파를 아는 컨셉)만 — ⓒ 는 예전처럼 요소마다 오린다(건너뜀 + 이유).
"""
from __future__ import annotations

import numpy as np

from core import schema
from core import spec as spec_mod
from gen import territory
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


FILL_TOL = 2.0               # 자식이 부모를 꽉 채운다고 볼 상자 차(px)
GROW_KINDS = ("overlay", "border", "size_box", "button")     # 자식 여백을 늘려 화면 자리를 지킬 수 있는 슬롯


def _fills(child: dict, parent: dict) -> bool:
    """child 가 parent 를 여백 없이 꽉 채우나(상자가 같고 fill · 여백 0)."""
    slot = child.get("slot") or {}
    cb, pb = child.get("bbox_intent"), parent.get("bbox_intent")
    if not cb or not pb or slot.get("kind") not in GROW_KINDS:
        return False
    d = spec_mod.SLOT_DEFAULTS[slot["kind"]]
    pad = slot.get("padding", d["padding"])
    return (max(abs(a - b) for a, b in zip([cb[0], cb[1], cb[0] + cb[2], cb[1] + cb[3]], [pb[0], pb[1], pb[0] + pb[2], pb[1] + pb[3]])) <= FILL_TOL
            and slot.get("h_align", d["h_align"]) == "fill" and slot.get("v_align", d["v_align"]) == "fill" and all(abs(float(v)) < 1e-6 for v in pad))


def _carrier(spec: dict, region: dict) -> tuple[list[dict], str | None]:
    """접히는 영역의 그림을 그리는 위젯까지의 길 [영역, …, 그리는 위젯] — 컨셉에서 오리는 브러시를 가진, 영역을 꽉 채우는 위젯. → (길, 안 되는 이유)."""
    index = _index(spec)
    ext = _extract_ids(spec)
    kids = spec_mod.children_map(spec)

    def draws(w):
        return [b["asset"] for _, b in _brush_assets(w) if b["asset"] in ext and b.get("draw_as", "image") != "none"]
    path = [region]
    while True:
        w = path[-1]
        if draws(w):
            return path, None
        cand = [index[c] for c in kids.get(w["id"], []) if _fills(index[c], w)]
        nxt = next((c for c in cand if draws(c)), None) or (cand[0] if len(cand) == 1 else None)
        if nxt is None:
            return path, "no brush cut from the concept fills this region"
        path.append(nxt)


def _stay(child: dict, parent_old, parent_new) -> str | None:
    """부모 상자가 넓어져도 자식의 화면 자리를 그대로 — 슬롯 여백(canvas 는 position)을 고친다. → 못 하는 이유."""
    slot = child.setdefault("slot", {})
    kind = slot.get("kind")
    l, t = parent_old[0] - parent_new[0], parent_old[1] - parent_new[1]
    r, b = (parent_new[0] + parent_new[2]) - (parent_old[0] + parent_old[2]), (parent_new[1] + parent_new[3]) - (parent_old[1] + parent_old[3])
    if kind in GROW_KINDS:
        pad = list(slot.get("padding", spec_mod.SLOT_DEFAULTS[kind]["padding"]))
        slot["padding"] = [round(float(v) + g, 2) for v, g in zip(pad, (l, t, r, b))]
        return None
    if kind == "canvas":
        an = slot.get("anchors") or [0, 0, 0, 0]
        if an[0] != an[2] or an[1] != an[3]:
            return f"{child['id']} stretches with the region"
        pos = slot.get("position") or [0, 0]
        slot["position"] = [round(float(pos[0]) + l + an[0] * (parent_old[2] - parent_new[2]), 2),
                            round(float(pos[1]) + t + an[1] * (parent_old[3] - parent_new[3]), 2)]
        return None
    return f"{child['id']} sits in a {kind} slot"


def fill_toggles(spec: dict) -> list[dict]:
    """전투 HUD 동작(11-23) — 접히는 영역이 상자(Overlay)이고 그 안의 컨셉에서 오리는 그림이 하나뿐인데 영역을 꽉 채우지 않으면(옆에 글자가 있는 '표시' —
    오의 가능 표시 = 낫날 그림 + 키 글자) 그림 상자를 영역까지 넓힌다: 넓힌 자리는 컨셉의 투명한 픽셀이라 그림은 그대로이고, 그래야 이 영역의 빛 · 넘침을 그 그림이
    가질 수 있다(_carrier). 크기를 늘려 그리는 그림(9-slice) · 여럿이 쓰는 에셋은 안 바꾼다. → 기록."""
    from stages import refine
    index = _index(spec)
    kids = spec_mod.children_map(spec)
    ext = _extract_ids(spec)
    out = []
    for reg in territory.toggle_regions(spec):
        if not reg.get("bbox_intent"):
            continue
        path, why = _carrier(spec, reg)
        if not why or path[-1].get("type") != "Overlay":
            continue
        host = path[-1]
        inside = [index[i] for i in _descendants(kids, host["id"]) if any(b["asset"] in ext and b.get("draw_as", "image") != "none" for _, b in _brush_assets(index[i]))]
        if len(inside) != 1 or inside[0].get("parent") != host["id"] or not inside[0].get("bbox_intent") or inside[0].get("type") != "Image":
            continue
        w = inside[0]
        key, b = next((k, x) for k, x in _brush_assets(w) if x["asset"] in ext)
        a = next(x for x in spec["assets"] if x["asset_id"] == b["asset"])
        if b.get("draw_as", "image") != "image" or a.get("nine_slice") or b.get("wipe") or len(refine.asset_users(spec, a["asset_id"])) != 1 \
                or not refine.fixed_size(spec, reg["id"]):
            continue
        ob, nb = [float(v) for v in w["bbox_intent"]], [float(v) for v in host["bbox_intent"]]
        if ob[0] < nb[0] - FILL_TOL or ob[1] < nb[1] - FILL_TOL or ob[0] + ob[2] > nb[0] + nb[2] + FILL_TOL or ob[1] + ob[3] > nb[1] + nb[3] + FILL_TOL:
            continue                                       # 영역 밖으로 나간 그림 — 줄이는 것은 이 단계가 할 일이 아니다
        size_old = list(a["size"])
        k = min(1.0, 1024.0 / max(size_old[0] * nb[2] / ob[2], size_old[1] * nb[3] / ob[3]))
        a["size"] = [max(4, int(round(size_old[0] * nb[2] / ob[2] * k))), max(4, int(round(size_old[1] * nb[3] / ob[3] * k)))]
        if a.get("ref_bbox"):
            rb = [float(v) for v in a["ref_bbox"]]
            rx0, ry0 = min(rb[0], nb[0]), min(rb[1], nb[1])
            a["ref_bbox"] = [int(rx0), int(ry0), int(np.ceil(max(rb[0] + rb[2], nb[0] + nb[2]) - rx0)), int(np.ceil(max(rb[1] + rb[3], nb[1] + nb[3]) - ry0))]
        b.pop("image_size", None)
        w["bbox_intent"] = [round(v, 2) for v in nb]
        w["slot"] = {"kind": "overlay", "padding": [0, 0, 0, 0], "h_align": "fill", "v_align": "fill"}
        out.append({"region": reg["id"], "widget": w["id"], "asset": a["asset_id"], "old_box": ob, "box": nb, "size_old": size_old, "size_new": list(a["size"])})
    return out


def split_radials(spec: dict, alpha) -> list[dict]:
    """전투 HUD 동작(11-23) — 원형 진행(고리) 위젯마다 자기 픽셀 마스크(gen/radial — analyze 가 잰 것과 같은 함수). → [{widget, asset, box, mask, …기록}]."""
    from gen import radial
    out = []
    for w in spec.get("widgets", []):
        b = (w.get("style") or {}).get("brush") or {}
        if w.get("type") != "Image" or not b.get("wipe") or not w.get("bbox_intent"):
            continue
        try:
            m = radial.measure(alpha, w["bbox_intent"])
        except radial.RadialError as exc:
            raise StageError("RADIAL_MEASURE", f"'{w['id']}': {exc}", widget=w["id"], box=w["bbox_intent"]) from exc
        x0, y0, x1, y1 = _int_box(w["bbox_intent"], alpha.shape[1], alpha.shape[0])
        inbox = np.zeros(alpha.shape, bool)
        inbox[y0:y1, x0:x1] = True
        out.append({"widget": w["id"], "asset": b.get("asset"), "box": [x0, y0, x1 - x0, y1 - y0], **m["record"], "mask": m["mask"] & inbox})
    return out


def radial_masks(run) -> dict[str, np.ndarray]:
    """layer.json radials — 고리 위젯 id → 자기 픽셀(캔버스 bool). run 마다 한 번 읽는다(refine 이 씀)."""
    cache = getattr(run, "radial_ring_masks", None)
    if cache is not None:
        return cache
    from PIL import Image
    out: dict[str, np.ndarray] = {}
    if run.path("layer.json").is_file():
        for r in run.read_json("layer.json").get("radials") or []:
            f = run.path(str(r.get("mask") or ""))
            if r.get("widget") and r.get("mask") and f.is_file():
                with Image.open(f) as im:
                    out[r["widget"]] = np.asarray(im.convert("L")) > 127
    try:
        run.radial_ring_masks = out
    except AttributeError:
        pass
    return out


def grow_toggles(spec: dict, alpha) -> list[dict]:
    """접히는 영역의 상자를 자기 몫(빛 · 넘침)까지 넓힌다(spec 을 바꿈). → 기록 [{widget, carrier, old_box, box, grow, px, mask} | {widget, skipped}]."""
    from stages import refine
    H, W = alpha.shape
    cw, ch = (float(v) for v in spec.get("canvas", [1920, 1080]))
    index = _index(spec)
    root = spec.get("root") or "Root"
    kids = spec_mod.children_map(spec)
    regs, owner, dist = territory.owner_map(spec, alpha.shape)
    out: list[dict] = []
    import cv2
    for reg in territory.toggle_regions(spec):
        if not reg.get("bbox_intent"):
            continue
        rec: dict = {"widget": reg["id"], "why": territory.collapsible(reg)}
        path, why = _carrier(spec, reg)
        if why:
            if any(_brush_assets(index[i]) for i in [reg["id"], *_descendants(kids, reg["id"])]):
                out.append({**rec, "skipped": why})          # 글자만 접히는 위젯은 옮길 빛이 없다(refine 의 글자 길 몫)
            continue
        carrier = path[-1]
        aid = next(b["asset"] for _, b in _brush_assets(carrier) if b["asset"] in _extract_ids(spec))
        if not refine.fixed_size(spec, reg["id"]):
            out.append({**rec, "skipped": "the region changes size with the screen"})
            continue
        if len(refine.asset_users(spec, aid)) != 1:
            out.append({**rec, "skipped": f"asset {aid} is shared by several widgets"})
            continue
        old = [float(v) for v in reg["bbox_intent"]]
        x0, y0, x1, y1 = territory.int_box(old, W, H)
        own = territory.claim(spec, alpha, reg["id"], omap=(regs, owner, dist))
        box_m = np.zeros((H, W), bool)
        box_m[y0:y1, x0:x1] = True
        outside = own & ~box_m
        # 상자와 안 이어진 잡티(MIN_PLATE_PX 미만)는 판도 만들지 않으므로 여기서도 버린다(상자만 공연히 커진다)
        n, lab, _, _ = cv2.connectedComponentsWithStats(cv2.dilate((own | box_m).astype(np.uint8), np.ones((2 * JOIN_PX + 1,) * 2, np.uint8)), connectivity=8)
        touch = set(np.unique(lab[box_m]).tolist())
        for i in range(1, n):
            comp = outside & (lab == i)
            if i not in touch and 0 < int(comp.sum()) < MIN_PLATE_PX:
                outside &= ~comp
        if not outside.any():
            continue
        ys, xs = np.nonzero(outside | box_m)
        nb = [float(min(xs.min(), old[0])), float(min(ys.min(), old[1])), 0.0, 0.0]
        nb[2], nb[3] = max(float(xs.max() + 1), old[0] + old[2]) - nb[0], max(float(ys.max() + 1), old[1] + old[3]) - nb[1]
        # 먼저 자식들이 제자리를 지킬 수 있는지 본다(사본) — 하나라도 안 되면 이 영역은 안 바꾼다
        stay = []
        for k, p in enumerate(path):
            nxt = path[k + 1]["id"] if k + 1 < len(path) else None
            stay += [index[c] for c in kids.get(p["id"], []) if c != nxt]
        saved = [dict(c.get("slot") or {}) for c in stay]
        bad = next((r for r in (_stay(c, old, nb) for c in stay) if r), None)
        if bad:
            for c, s in zip(stay, saved):
                c["slot"] = s
            out.append({**rec, "skipped": f"children cannot keep their place ({bad})"})
            continue
        for p in path:
            p["bbox_intent"] = [round(v, 2) for v in nb]
        slot = reg["slot"]
        an, al = list(slot.get("anchors") or [0, 0, 0, 0]), list(slot.get("alignment") or [0, 0])
        slot["position"] = [round(nb[0] + al[0] * nb[2] - an[0] * cw, 2), round(nb[1] + al[1] * nb[3] - an[1] * ch, 2)]
        slot["size"] = [round(nb[2], 2), round(nb[3], 2)]
        asset = next(a for a in spec["assets"] if a["asset_id"] == aid)
        size_old = list(asset["size"])
        k = min(1.0, 1024.0 / max(size_old[0] * nb[2] / old[2], size_old[1] * nb[3] / old[3]))
        asset["size"] = [max(4, int(round(size_old[0] * nb[2] / old[2] * k))), max(4, int(round(size_old[1] * nb[3] / old[3] * k)))]
        g = [old[0] - nb[0], old[1] - nb[1], nb[0] + nb[2] - old[0] - old[2], nb[1] + nb[3] - old[1] - old[3]]
        holders = [asset] + [b for _, b in _brush_assets(carrier) if b["asset"] == aid]
        for h in holders:
            if h.get("margin"):
                m = [float(v) for v in h["margin"]]
                h["margin"] = [round((m[0] * old[2] + g[0]) / nb[2], 4), round((m[1] * old[3] + g[1]) / nb[3], 4),
                               round((m[2] * old[2] + g[2]) / nb[2], 4), round((m[3] * old[3] + g[3]) / nb[3], 4)]
        if asset.get("ref_bbox"):
            rb = [float(v) for v in asset["ref_bbox"]]
            rx0, ry0 = min(rb[0], nb[0]), min(rb[1], nb[1])
            asset["ref_bbox"] = [int(rx0), int(ry0), int(np.ceil(max(rb[0] + rb[2], nb[0] + nb[2]) - rx0)), int(np.ceil(max(rb[1] + rb[3], nb[1] + nb[3]) - ry0))]
        pairs = []
        for o in spec["widgets"]:
            ob = o.get("bbox_intent")
            if o.get("parent") == root and o["id"] != reg["id"] and ob and min(nb[0] + nb[2], ob[0] + ob[2]) > max(nb[0], ob[0]) \
                    and min(nb[1] + nb[3], ob[1] + ob[3]) > max(nb[1], ob[1]):
                pair = sorted([reg["id"], o["id"]])
                if pair not in spec.setdefault("allow_overlap", []):
                    spec["allow_overlap"].append(pair)
                    pairs.append(o["id"])
        out.append({**rec, "carrier": carrier["id"], "asset": aid, "old_box": old, "box": [round(v, 2) for v in nb], "grow": [round(v, 2) for v in g],
                    "px": int(outside.sum()), "size_old": size_old, "size_new": list(asset["size"]), "children_kept": [c["id"] for c in stay],
                    "allow_overlap_with": pairs, "mask": outside | box_m})
    return out


def _descendants(kids: dict, wid: str) -> list[str]:
    out, stack = [], list(kids.get(wid, []))
    while stack:
        i = stack.pop()
        out.append(i)
        stack += kids.get(i, [])
    return out


def own_masks(run) -> dict[str, np.ndarray]:
    """layer.json toggles — 그리는 위젯 id → 자기 마스크(캔버스 bool). run 마다 한 번 읽는다(refine 이 씀)."""
    cache = getattr(run, "toggle_own_masks", None)
    if cache is not None:
        return cache
    from PIL import Image
    out: dict[str, np.ndarray] = {}
    if run.path("layer.json").is_file():
        for t in run.read_json("layer.json").get("toggles") or []:
            f = run.path(str(t.get("mask") or ""))
            if t.get("carrier") and t.get("mask") and f.is_file():
                with Image.open(f) as im:
                    out[t["carrier"]] = np.asarray(im.convert("L")) > 127
    try:
        run.toggle_own_masks = out
    except AttributeError:
        pass
    return out


def plan(spec: dict, alpha, functional: dict[str, str], static: list[str], plate_max: int = 2048, own: dict | None = None, omap=None) -> dict:
    """정적 판 계획 → {"plates": [{"n", "box", "region", "mask"(캔버스 bool)}], "func_zone", "excluded_px", …}.
    own = 상자를 넓힌 접히는 위젯의 자기 마스크(그리는 위젯 id → 캔버스 bool — 상자 대신 그 자리만 판에서 뺀다), omap = 넓히기 전 상자로 잰 영역 주인."""
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
        if cut_fn and own and w["id"] in own:
            func_zone |= own[w["id"]]
        elif cut_fn or runtime:
            x0, y0, x1, y1 = _int_box(bb, W, H)
            func_zone[y0:y1, x0:x1] = True
    # 기능 요소 상자 안은 판에 넣지 않는다 — 상자 안쪽 불투명 2 px 를 판도 같이 그리면(확대 절취선 메움) flag 패널이 숨어도 테두리가 판에 남았다(J-a 시험)
    static_px = vis & ~func_zone
    # 영역(루트 직계) — 상자 안이면 그 영역, 아니면 가장 가까운 상자. 크기 고정이 아닌 영역 몫은 판에 넣지 않는다(그 영역 장식은 기능 요소 길)
    from stages import refine
    regions, owner, _ = omap if omap is not None else territory.owner_map(spec, (H, W))
    if not regions:
        return {"plates": [], "func_zone_px": int(func_zone.sum()), "reason": "no canvas regions"}
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
    from stages.refine import _reference_layers, art_files
    if art_files(run):              # 1b 후속 K-a — 우리가 만든 컨셉은 글자 없는 아트(투명 위 글자 잔상 지움)의 보이는 픽셀로 판을 나눈다
        alpha = _reference_layers(run, bg)[1]
    else:
        with Image.open(run.path("reference_alpha.png")) as im:
            alpha = np.asarray(im.convert("L"), float) / 255.0
    # L-2 기본 전환 ④ — 접히는 위젯의 빛 · 넘침을 먼저 그 위젯으로(상자 넓힘). 판 조각의 영역 주인은 넓히기 전 상자로 잰다(넓힌 네모가 이웃 픽셀을 자기 것으로 안 세게)
    filled = fill_toggles(spec)
    omap = territory.owner_map(spec, alpha.shape)
    grown = grow_toggles(spec, alpha)
    run.path("layer").mkdir(parents=True, exist_ok=True)
    rings = split_radials(spec, alpha)
    for r in rings:
        m = r.pop("mask")
        r["mask"] = f"layer/ring_{r['widget']}.png"
        Image.fromarray((m * 255).astype(np.uint8), "L").save(run.path(r["mask"]))
    run.radial_ring_masks = None
    own: dict[str, np.ndarray] = {}
    for t in grown:
        m = t.pop("mask", None)
        if m is not None:
            t["mask"] = f"layer/own_{t['carrier']}.png"
            own[t["carrier"]] = m
            Image.fromarray((m * 255).astype(np.uint8), "L").save(run.path(t["mask"]))
    run.toggle_own_masks = None
    tog = {**({"toggles": grown} if grown else {}), **({"radials": rings} if rings else {}), **({"filled": filled} if filled else {})}
    if not static and not own:
        if filled:                      # 그림 상자를 넓힌 spec — 굽을 판이 없어도 남긴다
            schema.require("spec", spec)
            run.write_json("spec.json", spec)
        run.write_json("layer.json", {"applied": False, "reason": "no static decoration to bake", "functional": functional, **tog})
        return "no static decoration — every drawn element is functional"
    pl = plan(spec, alpha, functional, static, int(cfg["plate_max"]), own=own, omap=omap) if static else {"plates": [], "func_zone_px": 0}
    if not pl["plates"] and not own:
        if filled:
            schema.require("spec", spec)
            run.write_json("spec.json", spec)
        run.write_json("layer.json", {"applied": False, "reason": "no visible static pixels", "functional": functional, "static": static, **tog})
        return "no visible static pixels"
    rec = apply(spec, functional, static if pl["plates"] else [], pl["plates"])
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
                                  "masks": [f"layer/plate_{p['n']}.png" for p in pl["plates"]], **tog})
    moved = "; ".join(f"{t['widget']} box grew {t['grow']} ({t['px']} px of its own glow)" if t.get("mask") else f"{t['widget']} kept ({t['skipped']})" for t in grown)
    return (f"{len(static)} static decoration(s) → {len(rec['plates'])} plate(s) {[p['box'] for p in rec['plates']]}, functional {len(functional)}, "
            f"removed assets {rec['removed_assets']}" + (f" — collapsible: {moved}" if moved else ""))
