"""가리는 위젯 없음 — 버튼 위에 놓인 장식이 클릭을 먹는가 (설계 §11 'Phase 3 설계' ②, Phase 3-3).

UMG 의 Image · TextBlock 은 기본 보이기가 visible 이라 아무것도 안 해도 클릭을 먹는다. 파이프라인은 클릭을 받는 화면 종류에서 기본값을 바꾸고(core/spec.default_visibility),
여기서는 **에디터에 실제로 있는 트리(역추출)** 로 다시 본다 — 누가 visible 을 적었거나 조정기가 값을 못 옮겼으면 여기서 걸린다.
Slate 히트 테스트: 나중에 그려진 것이 먼저 받는다. visible 만 자기가 받고, self_hit_test_invisible 은 자식만, hit_test_invisible 은 자식까지 못 받는다.
"""
from __future__ import annotations

from core import cellref
from core import spec as spec_mod

MIN_PX = 1.0              # 이보다 작은 겹침(px²)은 반올림


def _box(g: dict | None):
    return None if not g or float(g.get("w", 0)) <= 0 or float(g.get("h", 0)) <= 0 else [float(g[k]) for k in ("x", "y", "w", "h")]


def _cut(a, b) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def paint_order(spec: dict) -> list[dict]:
    from gen import backdrop
    return backdrop.paint_order(spec)


def _cell_spec(class_path: str, root=None) -> dict | None:
    rec = cellref.index(root).get(cellref.package_of(class_path))
    return cellref._source_spec(rec) if rec else None             # noqa: SLF001


def _eats(spec: dict) -> list[dict]:
    """칸 속에서 클릭을 먹는 위젯 — 정규형에서 visible 이고 조상이 hit_test_invisible 이 아닌 것."""
    norm = spec_mod.normalize(spec)
    index = spec_mod.widget_index(norm)
    out = []
    for w in norm["widgets"]:
        if w["visibility"] != "visible":
            continue
        p, ok = w.get("parent"), True
        while p in index:
            if index[p]["visibility"] in ("hit_test_invisible", "collapsed", "hidden"):
                ok = False
                break
            p = index[p].get("parent")
        if ok:
            out.append(w)
    return out


def check(spec: dict, exported: dict, geometry: list[dict], promoted_root=None) -> dict:
    """→ {buttons, blocked: [{button, by, why, area}], dead: [{button, why}]}."""
    geo = {g["id"]: g for g in geometry}
    tree = {**exported, "root": exported.get("root") or spec.get("root")}
    index = spec_mod.widget_index(tree)
    order = paint_order(tree)
    pos = {w["id"]: i for i, w in enumerate(order)}

    def vis(w: dict) -> str:
        return w.get("visibility") or spec_mod.default_visibility(w)          # 역추출은 늘 적는다 — 없으면 엔진 기본

    def reachable(w: dict) -> str | None:
        """클릭이 닿지 않는 이유(조상) 또는 None."""
        p = w.get("parent")
        while p in index:
            v = vis(index[p])
            if v in ("hit_test_invisible", "collapsed", "hidden"):
                return f"ancestor '{p}' is {v}"
            p = index[p].get("parent")
        return None

    def ancestors(wid: str) -> set[str]:
        out, p = set(), (index.get(wid) or {}).get("parent")
        while p in index:
            out.add(p)
            p = index[p].get("parent")
        return out

    buttons = [w for w in order if w.get("type") == "Button" or (w.get("type") == spec_mod.CELL_TYPE and cellref.is_button(w.get("class"), promoted_root))]
    ids = {b["id"] for b in buttons}
    blocked, dead = [], []
    for b in buttons:
        why = reachable(b)
        if why is None and vis(b) not in (("visible",) if b.get("type") == "Button" else ("visible", "self_hit_test_invisible")):
            why = f"it is {vis(b)}"
        if why:
            dead.append({"button": b["id"], "why": why})
        bb = _box(geo.get(b["id"]))
        if bb is None:
            dead.append({"button": b["id"], "why": "not drawn"})
            continue
        up = ancestors(b["id"])
        for w in order[pos[b["id"]] + 1:]:
            if w["id"] in up or b["id"] in ancestors(w["id"]):
                continue
            wb = _box(geo.get(w["id"]))
            if wb is None or reachable(w) is not None:
                continue
            v = vis(w)
            if w["id"] in ids:
                area = _cut(bb, wb) if v in ("visible", "self_hit_test_invisible") else 0.0
                reason = "another button"
            elif v == "visible":
                area, reason = _cut(bb, wb), "visible"
            elif w.get("type") == spec_mod.CELL_TYPE and v == "self_hit_test_invisible":
                inner = _cell_spec(w.get("class"), promoted_root)
                eats = _eats(inner) if inner else [{"id": "?"}]
                area = 0.0
                reason = "cell with visible parts"
                if eats:
                    kx = wb[2] / float(inner["canvas"][0]) if inner else 1.0
                    ky = wb[3] / float(inner["canvas"][1]) if inner else 1.0
                    for e in eats:
                        eb = e.get("bbox_intent")
                        part = [wb[0] + eb[0] * kx, wb[1] + eb[1] * ky, eb[2] * kx, eb[3] * ky] if eb else wb
                        area = max(area, _cut(bb, part))
            else:
                continue
            if area > MIN_PX:
                blocked.append({"button": b["id"], "by": w["id"], "why": reason, "area": round(area, 1)})
    return {"buttons": sorted(ids), "blocked": blocked, "dead": dead}
