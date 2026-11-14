"""verify 게이트의 수치 계산 — 렌더 geometry(render_widget) · spec · 프로필로 (설계 §8-1). 에디터 없이 합성 geometry 로 시험한다.

geometry 한 줄 = render_widget 의 {id, type, parent, x, y, w, h, visible} — 페인트 공간(= 픽셀, Scale 1) 좌표.
bbox · bbox_intent = [x, y, w, h].

[실측 1a-4] Slate 는 그리기(클립) 영역 밖으로 완전히 나간 위젯을 그리지 않는다(패널의 자식 컬링). 그런 위젯과 그 자식은 페인트 공간
geometry 가 기본값 (0, 0, 0, 0) 으로 남는다 — painted() 가 이것을 가른다. 부분적으로 걸친 위젯은 그려지고 실제 좌표가 나온다.

규칙(잠정 — 값은 profiles/<screen_type>.yaml gates):
  화면 밖   — 보이는(visible) 위젯 중 크기가 있는 것이 [0, W] × [0, H] 밖으로 EPS 넘게 나가면 하나. 그려지지 않은(컬링) 보이는 위젯도 하나.
  겹침      — 같은 부모의 형제 쌍에서 교차 면적 / 작은 쪽 면적 > overlap_max_ratio. 부모 타입이 stacking_parents(Overlay)면
              그 자식끼리는 보지 않고, spec.allow_overlap 쌍도 뺀다. 크기 0 은 뺀다.
  배치(IoU) — bbox_intent 가 있는 위젯만. 루트 Canvas 의 직계 = 영역(region), 자식이 없는 위젯 = 말단(leaf), 둘 다면 영역(더 엄격),
              그 사이(박스 등)는 기록만(inner). min(intent w, h) < small_px 면 IoU 대신 중심점 거리 ≤ small_center_max_px.
"""
from __future__ import annotations

import math

from core import spec as spec_mod

EPS = 0.5   # px — 페인트 공간 좌표의 부동소수 오차


def box(g: dict) -> tuple[float, float, float, float]:
    return float(g["x"]), float(g["y"]), float(g["w"]), float(g["h"])


def area(b) -> float:
    return max(0.0, b[2]) * max(0.0, b[3])


def intersection(a, b) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def iou(a, b) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def center_distance(a, b) -> float:
    return math.hypot((a[0] + a[2] / 2) - (b[0] + b[2] / 2), (a[1] + a[3] / 2) - (b[1] + b[3] / 2))


def r3(v: float) -> float:
    return round(float(v), 3)


def by_id(geometry: list[dict]) -> dict[str, dict]:
    return {g["id"]: g for g in geometry}


def painted(g: dict | None) -> bool:
    """그려진 geometry 인가 — 컬링된 위젯은 (0, 0, 0, 0) 그대로다(위 [실측])."""
    return g is not None and not (float(g["x"]) == 0 and float(g["y"]) == 0 and float(g["w"]) == 0 and float(g["h"]) == 0)


# ---------------------------------------------------------------------------------------------------------------------

def offscreen(geometry: list[dict], resolution, eps: float = EPS) -> list[dict]:
    """보이는 위젯 중 화면 밖으로 나간 것 — [{id, bbox, out: {left, top, right, bottom}}] (밖으로 나간 px),
    그려지지 않은 것은 {id, bbox: None, not_painted: True}."""
    W, H = float(resolution[0]), float(resolution[1])
    out = []
    for g in geometry:
        if not g.get("visible", True):
            continue
        if not painted(g):
            out.append({"id": g["id"], "bbox": None, "not_painted": True,
                        "out": "not painted — culled outside the draw area (Slate skips children wholly outside the clip rect)"})
            continue
        b = box(g)
        if b[2] <= 0 or b[3] <= 0:
            continue
        over = {"left": -b[0], "top": -b[1], "right": b[0] + b[2] - W, "bottom": b[1] + b[3] - H}
        over = {k: r3(v) for k, v in over.items() if v > eps}
        if over:
            out.append({"id": g["id"], "bbox": [r3(v) for v in b], "out": over})
    return out


def _allowed_pairs(spec: dict) -> set[frozenset]:
    return {frozenset(p) for p in spec.get("allow_overlap", [])}


def overlaps(geometry: list[dict], spec: dict, max_ratio: float, stacking_parents) -> dict:
    """형제 bbox 교차 — {checked, skipped_stacking, allowed, violations[{a, b, parent, ratio, intersection}]}."""
    gi = by_id(geometry)
    stacking = set(stacking_parents or [])
    allowed = _allowed_pairs(spec)
    siblings: dict[str, list[dict]] = {}
    for g in geometry:
        if g.get("parent"):
            siblings.setdefault(g["parent"], []).append(g)
    checked, skipped, allowed_n, violations = 0, 0, 0, []
    for parent, kids in siblings.items():
        ptype = (gi.get(parent) or {}).get("type")
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                a, b = kids[i], kids[j]
                if ptype in stacking:
                    skipped += 1
                    continue
                if frozenset((a["id"], b["id"])) in allowed:
                    allowed_n += 1
                    continue
                ba, bb = box(a), box(b)
                small = min(area(ba), area(bb))
                if small <= 0:
                    continue
                checked += 1
                inter = intersection(ba, bb)
                ratio = inter / small
                if ratio > max_ratio:
                    violations.append({"a": a["id"], "b": b["id"], "parent": parent, "ratio": r3(ratio), "intersection": r3(inter)})
    return {"checked": checked, "skipped_stacking": skipped, "allowed": allowed_n, "violations": violations}


def placement(spec: dict, geometry: list[dict], gates: dict) -> dict[str, list[dict]]:
    """bbox_intent 대비 배치 — {region: [...], leaf: [...], inner: [...]}. 줄마다 {id, rule (iou|center), value, threshold, pass, intent, bbox}."""
    gi = by_id(geometry)
    kids = spec_mod.children_map(spec)
    root = spec["root"]
    small_px = float(gates["small_px"])
    out: dict[str, list[dict]] = {"region": [], "leaf": [], "inner": []}
    for w in spec["widgets"]:
        intent = w.get("bbox_intent")
        if not intent or w["id"] == root:
            continue
        category = "region" if w.get("parent") == root else ("leaf" if not kids.get(w["id"]) else "inner")
        row: dict = {"id": w["id"], "intent": [r3(v) for v in intent]}
        g = gi.get(w["id"])
        small = min(float(intent[2]), float(intent[3])) < small_px
        if small:
            row.update(rule="center", threshold=float(gates["small_center_max_px"]))
        else:
            row.update(rule="iou", threshold=float(gates["iou_region_min" if category == "region" else "iou_leaf_min"]))
        if g is None:
            row.update(value=None, bbox=None, ok=False, missing=True)
        else:
            if not painted(g):
                row["not_painted"] = True   # 값은 (0, 0, 0, 0) 그대로 계산된다 — IoU 0 · 중심 거리 큼 → 실패
            b = box(g)
            row["bbox"] = [r3(v) for v in b]
            if small:
                d = center_distance(b, intent)
                row.update(value=r3(d), ok=d <= row["threshold"])
            else:
                v = iou(b, intent)
                row.update(value=r3(v), ok=v >= row["threshold"])
        row["pass"] = row.pop("ok")
        out[category].append(row)
    return out


def placement_gate_value(rows: list[dict]) -> dict:
    ious = [r["value"] for r in rows if r["rule"] == "iou" and r["value"] is not None]
    centers = [r["value"] for r in rows if r["rule"] == "center" and r["value"] is not None]
    return {"iou_min": min(ious) if ious else None, "center_max_px": max(centers) if centers else None, "widgets": len(rows)}
