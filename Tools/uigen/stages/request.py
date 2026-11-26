"""요청이 정하는 자리 — 놓인 칸 · 영역 앵커 · 글자 칸 · 바탕 위 표시 (설계 §11 'Phase 3 설계' ②, Phase 3-3). analyze 가 부른다.

LLM 에게 맡기지 않는 것들이다: 칸의 크기(= 칸 캔버스)와 자리(요청 at — normalize 가 시안과 견줌), 해상도가 바뀔 때 같이 움직여야 하는 묶음의 앵커,
긴 글자가 넘지 말아야 할 칸, 표시 획의 상자. LLM 이 내는 spec 에는 이 어휘가 없다(analyze.output_schema).
"""
from __future__ import annotations

import copy

from core import spec as spec_mod
from stages import StageError

CELL_Z = 10               # 놓인 칸은 같은 루트의 그림 · 글자보다 뒤에 그린다(클릭을 받는 것이 맨 위)
COVER_MAX = 0.04          # 칸 상자에 이보다 걸치는 다른 위젯은 칸 자리를 다시 그린 것(overlap 게이트와 같은 비율)


def cells(brief: dict) -> list[dict]:
    return list(brief.get("cells") or [])


def cell_lines(brief: dict) -> list[str]:
    """프롬프트 줄 — 칸 자리는 파이프라인이 채운다."""
    return [f"- {c['widget']}: {c['cell']} at [{c['at'][0]}, {c['at'][1]}, {c['size'][0]}, {c['size'][1]}]" for c in cells(brief)]


def place_cells(spec: dict, brief: dict) -> dict:
    """놓인 칸을 spec 에 넣은 사본 — 루트 직계, 크기 = 칸 캔버스, 자리 = 요청."""
    out = copy.deepcopy(spec)
    root = out.get("root")
    mine = {c["widget"] for c in cells(brief)}
    out["widgets"] = [w for w in out.get("widgets", []) if not (w["id"] in mine and w.get("type") == spec_mod.CELL_TYPE)]
    data = {d["widget"]: d for d in brief.get("dynamic_data", [])}
    for c in cells(brief):
        x, y, w, h = float(c["at"][0]), float(c["at"][1]), float(c["size"][0]), float(c["size"][1])
        d = data[c["widget"]]
        b = {"data": d["id"], "kind": d["type"]}
        if d["type"] == "action" and d.get("selectable"):
            b["selectable"] = True
        out["widgets"].append({"id": c["widget"], "type": spec_mod.CELL_TYPE, "class": c["class"], "parent": root, "bbox_intent": [x, y, w, h],
                               **({"props": dict(c["props"])} if c.get("props") else {}),
                               "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": [w, h], "z": CELL_Z}, "binding": b})
    return out


def cell_errors(spec: dict, brief: dict) -> list[str]:
    """칸 자리를 다른 위젯이 쓰면 안 된다 — 칸의 그림은 칸이 그린다."""
    errs = []
    want = {c["widget"] for c in cells(brief)}
    for w in spec.get("widgets", []):
        if w.get("type") == spec_mod.CELL_TYPE and w["id"] not in want:
            errs.append(f"CELL: '{w['id']}' — placed cells come from the request, not from the analysis")
    for c in cells(brief):
        bx = [float(c["at"][0]), float(c["at"][1]), float(c["size"][0]), float(c["size"][1])]
        for w in spec.get("widgets", []):
            bb = w.get("bbox_intent")
            if w["id"] in want or not bb or w["id"] == spec.get("root"):
                continue
            ix = max(0.0, min(bx[0] + bx[2], float(bb[0]) + float(bb[2])) - max(bx[0], float(bb[0])))
            iy = max(0.0, min(bx[1] + bx[3], float(bb[1]) + float(bb[3])) - max(bx[1], float(bb[1])))
            small = min(bx[2] * bx[3], float(bb[2]) * float(bb[3]))
            if small > 0 and ix * iy / small > COVER_MAX:
                errs.append(f"CELL_COVER: '{w['id']}' covers the place of the cell '{c['widget']}' {[int(v) for v in bx]} — the pipeline puts the cell there; make no widget, "
                            f"region or asset for it (split a region that spans it)")
    return errs


def apply_anchor_regions(spec: dict, brief: dict) -> list[dict]:
    """루트 직계(점 앵커)의 앵커를 요청한 묶음 것으로 — 캔버스 크기에서 자리는 그대로이고, 해상도가 바뀌면 묶음이 같이 움직인다. → 기록."""
    regions = brief.get("anchor_regions") or []
    if not regions:
        return []
    W, H = (float(v) for v in spec["canvas"])
    out = []
    for w in spec["widgets"]:
        s, bb = w.get("slot") or {}, w.get("bbox_intent")
        if w.get("parent") != spec.get("root") or s.get("kind") != "canvas" or not bb:
            continue
        cx, cy = float(bb[0]) + float(bb[2]) / 2, float(bb[1]) + float(bb[3]) / 2
        reg = next((r for r in regions if r["box"][0] <= cx <= r["box"][0] + r["box"][2] and r["box"][1] <= cy <= r["box"][1] + r["box"][3]), None)
        if reg is None:
            continue
        ax, ay = (float(v) for v in reg["anchor"])
        x, y, bw, bh = (float(v) for v in bb)
        new = {**s, "anchors": [ax, ay, ax, ay], "alignment": [ax, ay], "position": [round(x + ax * bw - ax * W, 2), round(y + ay * bh - ay * H, 2)], "size": [bw, bh]}
        new.pop("auto_size", None)
        if spec_mod._canon(new) != spec_mod._canon(s):          # noqa: SLF001
            out.append({"widget": w["id"], "anchor": [ax, ay], "old": {k: s.get(k) for k in ("anchors", "alignment", "position")}})
        w["slot"] = new
    return out


def text_boxes(brief: dict) -> dict[str, list[float]]:
    return {d["widget"]: [float(v) for v in d["text_box"]] for d in brief.get("dynamic_data", []) if d.get("text_box")}


def text_box_errors(spec: dict, brief: dict) -> list[str]:
    index = spec_mod.widget_index(spec)
    errs = []
    for wid in text_boxes(brief):
        w = index.get(wid)
        p = index.get((w or {}).get("parent")) or {}
        if w and p.get("type") not in ("Overlay", "CanvasPanel"):
            errs.append(f"TEXT_BOX_PARENT: '{wid}' needs a fixed text box — put it directly in an Overlay or a CanvasPanel, its parent is a {p.get('type')}")
        elif w and p.get("id") != spec.get("root") and not p.get("bbox_intent"):
            errs.append(f"TEXT_BOX_PARENT: '{wid}' parent '{p.get('id')}' has no bbox_intent")
        if w and w.get("justification") == "center":            # 엔진은 가운데 정렬 글자를 줄이지 않는다(양 끝이 잘린다)
            errs.append(f"TEXT_BOX_JUSTIFY: '{wid}' is shortened with an ellipsis when it is too long — the engine does that only for left or right justification")
    return errs


def apply_text_boxes(spec: dict, brief: dict, cfg: dict) -> list[dict]:
    """넘치면 줄이는 글자(overflow)의 칸 — 폭은 요청한 상자, 높이는 줄 높이(+ 외곽선), 세로는 상자 가운데. → 기록."""
    from stages import style
    boxes = text_boxes(brief)
    if not boxes:
        return []
    index = spec_mod.widget_index(spec)
    W, H = (float(v) for v in spec["canvas"])
    over = {d["widget"]: d.get("overflow") for d in brief.get("dynamic_data", [])}
    out = []
    for wid, (x, y, bw, bh) in boxes.items():
        w = index[wid]
        font = w.get("font") or {}
        lh = style._line_height(cfg, font.get("family"), float(font.get("size") or 24)) or bh            # noqa: SLF001
        lh = round(lh + 2.0 * float((font.get("outline") or {}).get("size") or 0), 1)
        cy = y + bh / 2
        bb = [x, round(cy - lh / 2, 2), bw, lh]
        old = {"bbox": w.get("bbox_intent"), "slot": copy.deepcopy(w.get("slot"))}
        p = index[w["parent"]]
        if p["type"] == "Overlay":
            px, py, pw, ph = (float(v) for v in p["bbox_intent"])
            # 세로는 상자 가운데 정렬 — 위 · 아래 여백 차의 절반이 이동이다
            dy = cy - (py + ph / 2)
            w["slot"] = {"kind": "overlay", "padding": [round(x - px, 2), round(max(0.0, 2 * dy), 2), round(px + pw - x - bw, 2), round(max(0.0, -2 * dy), 2)],
                         "h_align": "fill", "v_align": "center"}
        else:
            ox, oy = (0.0, 0.0) if p["id"] == spec.get("root") else (float(p["bbox_intent"][0]), float(p["bbox_intent"][1]))
            cw, ch = (W, H) if p["id"] == spec.get("root") else (float(p["bbox_intent"][2]), float(p["bbox_intent"][3]))
            s = w.get("slot") or {}
            an, al = (s.get("anchors") or [0, 0, 0, 0]), (s.get("alignment") or [0, 0])
            w["slot"] = {"kind": "canvas", "anchors": [an[0], an[1], an[0], an[1]], "alignment": list(al), **({"z": s["z"]} if "z" in s else {}),
                         "position": [round(bb[0] - ox + al[0] * bw - an[0] * cw, 2), round(bb[1] - oy + al[1] * lh - an[1] * ch, 2)], "size": [bw, lh]}
        w["bbox_intent"] = bb
        if over.get(wid):
            w["overflow"] = over[wid]
        out.append({"widget": wid, "box": bb, "overflow": over.get(wid), "old": old})
    return out


def marks(brief: dict) -> dict[str, str]:
    """바탕 위 표시 — 위젯 id → 바탕 위젯 id(요청 data[].over)."""
    return {d["widget"]: d["over"] for d in brief.get("dynamic_data", []) if d.get("over")}


def mark_errors(spec: dict, brief: dict) -> list[str]:
    index = spec_mod.widget_index(spec)
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    users: dict[str, list[str]] = {}
    for w in spec.get("widgets", []):
        for k, b in (w.get("style") or {}).items():
            if k in spec_mod.BRUSH_KEYS and isinstance(b, dict) and b.get("asset"):
                users.setdefault(b["asset"], []).append(w["id"])
    errs = []
    for wid in marks(brief):
        w = index.get(wid)
        if not w:
            continue
        brush = (w.get("style") or {}).get("brush") or {}
        a = assets.get(brush.get("asset"))
        if not a or a.get("source_mode") != "extract" or brush.get("draw_as", "image") != "image" or a.get("nine_slice"):
            errs.append(f"MARK_ASSET: '{wid}' needs its own source_mode extract asset drawn as image (no nine_slice) — the mark is split from the drawing under it")
        elif users.get(brush["asset"]) != [wid]:
            errs.append(f"MARK_ASSET: asset '{brush['asset']}' is shared by {users.get(brush['asset'])} — the mark '{wid}' needs its own asset")
        p = index.get(w.get("parent")) or {}
        if p.get("type") != "Overlay" or not p.get("bbox_intent"):
            errs.append(f"MARK_PARENT: '{wid}' must sit in an Overlay with a bbox_intent (layers on top of each other), its parent is {w.get('parent')!r}")
    return errs


def derive_marks(spec: dict, brief: dict, color, alpha) -> list[dict]:
    """표시 획을 아트에서 재(gen/overlay_mark) 위젯 상자 · 여백 · 에셋 크기를 획 상자로. 못 재면 StageError MARK_MEASURE. → 기록."""
    from gen import overlay_mark
    want = marks(brief)
    if not want:
        return []
    if alpha is None:
        raise StageError("MARK_MEASURE", "the concept alpha is unknown (a scene composite) — a mark cannot be split from the drawing under it")
    index = spec_mod.widget_index(spec)
    out = []
    for wid, base in want.items():
        w = index[wid]
        try:
            m = overlay_mark.measure(color, alpha, overlay_mark.fit_box(color, alpha, w["bbox_intent"]))
        except overlay_mark.MarkError as exc:
            raise StageError("MARK_MEASURE", f"'{wid}': {exc}", widget=wid, box=w.get("bbox_intent")) from exc
        x, y, bw, bh = m["box"]
        px, py, pw, ph = (float(v) for v in index[w["parent"]]["bbox_intent"])
        pad = [round(v, 2) for v in (x - px, y - py, px + pw - x - bw, py + ph - y - bh)]
        rec = {"widget": wid, "over": base, "old_bbox": list(w["bbox_intent"]), "old_slot": copy.deepcopy(w.get("slot")), **m["record"]}
        w["bbox_intent"] = [x, y, bw, bh]
        w["slot"] = {"kind": "overlay", "padding": pad, "h_align": "fill", "v_align": "fill"}
        aid = w["style"]["brush"]["asset"]
        w["style"]["brush"] = {"draw_as": "image", "asset": aid}
        a = next(x_ for x_ in spec["assets"] if x_["asset_id"] == aid)
        a.update(size=[max(4, bw), max(4, bh)], ref_bbox=[x, y, bw, bh])
        rec["asset"] = aid
        out.append(rec)
    return out
