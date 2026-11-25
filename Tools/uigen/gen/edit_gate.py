"""수정 회귀 게이트의 순수 계산 (Phase 4 — 설계 §11 'Phase 4 설계' ④). 에디터 없이 합성 입력으로 시험한다.

이어서 고치기의 정답은 컨셉이 아니라 **같은 에디터에서 막 지은 base**(고치기 전)다. 바꾸겠다고 적은 자리 밖은 하나도 안 바뀌어야 한다:
  spec     엔진 역추출 base ↔ 새 것 — 대상 밖 위젯 · 공통 텍스처 설정 · 형제 순서가 같음, 조정기가 바꾼 위젯 ⊆ 대상
  geometry 세 해상도 — 대상 밖 위젯 상자 차 ≤ GEO_EPS
  픽셀      세 해상도 + 진단이 쓰는 모든 상태 + sample — 대상 자리 밖 다른 픽셀 0(문턱 없음).
           자리 = 대상 상자(앞 ∪ 뒤) + 글자 효과(외곽선 · 그림자 · 빛) + PAD px. 밖에 남으면 '대상이 실제로 그린 픽셀'(대상을 끈 렌더와의 차)로 다시 잰다
  효과     어느 그림에서도 픽셀 · geometry 가 안 변하면 실패(NO_EFFECT)
바꾼 자리 안의 모양은 판정하지 않는다(정답이 없다) — edit.png 를 사람이 본다.

외형 진단(gen/diagnose)은 고치지 않고 결과만 나눈다: base 에도 있던 결함 = 이어받음 · 새 결함이 자리 안 = 의도한 변경 · 자리 밖 = 오류.
엔진 그림끼리 견주는 상태 검사(막대 · 고리 · 게이지)는 자리 안이어도 새로 생기면 오류(컨셉과 상관없이 동작이 깨진 것).
"""
from __future__ import annotations

import hashlib
import math
import pathlib

import numpy as np

from core import spec as spec_mod
from gen import diagnose as dg

GATE = "edit_regression"
PAD = 2                         # 대상 상자 밖 여유(px) — 안티앨리어싱 · 반올림
GEO_EPS = 0.01                  # geometry 차 허용(px) — 같은 에디터 세션이라 실측 0
DEFECT_PAD = dg.WIN // 2        # 진단은 7 × 7 창 평균이라 자리 밖 이만큼까지는 자리 안 픽셀이 번진 값이다
ENGINE_CHECKS = ("bar_", "radial_", "gauge_")      # 엔진 렌더끼리 견주는 상태 검사(gen/state_check)


# ---------------------------------------------------------------------------------------------------------------------
# 자리

def scope(before: dict, after: dict, roots) -> set[str]:
    """대상 + 자손 — 앞 · 뒤 spec 어느 쪽에든 있는 것(더하거나 뺀 위젯 포함)."""
    out = set()
    for r in roots:
        out.add(r)
        for sp in (before, after):
            if r in spec_mod.widget_index(sp):
                out.update(spec_mod.descendants(sp, r))
    return out


def effect_pad(*widgets) -> float:
    """글자 외곽선 · 그림자 · 빛이 상자 밖으로 나가는 폭(px) — 앞 · 뒤 중 큰 쪽."""
    pad = 0.0
    for w in widgets:
        f = (w or {}).get("font")
        if not isinstance(f, dict):
            continue
        pad = max(pad, float((f.get("outline") or {}).get("size") or 0), float((f.get("glow") or {}).get("size") or 0),
                  *(abs(float(v)) for v in (f.get("shadow") or {}).get("offset") or [0]))
    return pad


def pads(before: dict, after: dict, ids) -> dict[str, float]:
    b, a = spec_mod.widget_index(before), spec_mod.widget_index(after)
    return {i: effect_pad(b.get(i), a.get(i)) + PAD for i in ids}


def zone_mask(shape, geometries, ids, pad: dict[str, float]) -> np.ndarray:
    """대상 상자(앞 ∪ 뒤)를 그 위젯의 여유만큼 넓힌 자리. geometries = {id: {x, y, w, h}} 여럿."""
    z = np.zeros(shape[:2], bool)
    for geo in geometries:
        for i in ids:
            g = geo.get(i)
            if not g or float(g["w"]) <= 0 or float(g["h"]) <= 0:
                continue
            p = pad.get(i, PAD)
            x0, y0 = math.floor(float(g["x"]) - p), math.floor(float(g["y"]) - p)
            x1, y1 = math.ceil(float(g["x"]) + float(g["w"]) + p), math.ceil(float(g["y"]) + float(g["h"]) + p)
            z[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    return z


def by_resolution(geometry_doc: dict) -> dict[str, dict[str, dict]]:
    """geometry.json 의 geometry → {"1920x1080": {id: 줄}}."""
    return {res: {g["id"]: g for g in rows} for res, rows in geometry_doc.items()}


# ---------------------------------------------------------------------------------------------------------------------
# 그림

def load(path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), np.uint8)


def same_file(a, b) -> bool:
    a, b = pathlib.Path(a), pathlib.Path(b)
    return a.stat().st_size == b.stat().st_size and hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


def diff_mask(a, b) -> np.ndarray:
    """다른 픽셀(채널 하나라도 다름). 크기가 다르면 전부 다름."""
    if a.shape != b.shape:
        return np.ones(a.shape[:2], bool)
    return (a != b).any(axis=2)


def bbox(m) -> list[int] | None:
    ys, xs = np.nonzero(m)
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)] if len(xs) else None


def image_row(before, after, zone, footprint=None) -> dict:
    """그림 하나 — {px, outside, box, outside_box}. zone 의 크기가 그림과 다르면(가짜 렌더 등) 전부 밖으로 센다."""
    d = diff_mask(before, after)
    ok = zone if zone is not None and zone.shape == d.shape else np.zeros(d.shape, bool)
    if footprint is not None and footprint.shape == d.shape:
        ok = ok | footprint
    out = d & ~ok
    row = {"px": int(d.sum()), "outside": int(out.sum())}
    if row["px"]:
        row["box"] = bbox(d)
    if row["outside"]:
        row["outside_box"] = bbox(out)
    return row


def compare_sets(before: dict, after: dict) -> dict:
    """그림 묶음 둘({이름: 경로})이 같은가 — 문턱 없이. {n, same_bytes, same_pixels, different: {이름: {px, box} | "missing"}}."""
    out: dict = {"n": len(before), "same_bytes": 0, "same_pixels": 0, "different": {}}
    for name, p in before.items():
        q = after.get(name)
        if q is None or not pathlib.Path(p).is_file() or not pathlib.Path(q).is_file():
            out["different"][name] = "missing"
            continue
        if same_file(p, q):
            out["same_bytes"] += 1
            out["same_pixels"] += 1
            continue
        d = diff_mask(load(p), load(q))
        if d.any():
            out["different"][name] = {"px": int(d.sum()), "box": bbox(d)}
        else:
            out["same_pixels"] += 1
    for name in after:
        if name not in before:
            out["different"][name] = "extra"
    return out


# ---------------------------------------------------------------------------------------------------------------------
# spec · geometry

def _texture_settings(rows) -> dict[str, dict]:
    return {t.get("asset_path", "").split(".", 1)[0]: {k: t.get(k) for k in ("compression", "lod_group", "mip_gen", "never_stream", "srgb", "size")}
            for t in rows or []}


def spec_changes(before: dict, after: dict, allowed: set, ue_to_asset: dict | None = None, sizes: dict | None = None, touched=()) -> dict:
    """엔진 역추출 앞 · 뒤(export_widget_spec 결과 — {"spec", "textures"})의 대상 밖 차이. touched = 조정기가 바꾼 위젯."""
    va = spec_mod.roundtrip_view(before.get("spec") or {}, ue_to_asset, sizes or {})
    vb = spec_mod.roundtrip_view(after.get("spec") or {}, ue_to_asset, sizes or {})
    wa, wb = {w["id"]: w for w in va["widgets"]}, {w["id"]: w for w in vb["widgets"]}
    diffs: list[str] = []
    if va["root"] != vb["root"]:
        diffs.append(f"root: {va['root']} != {vb['root']}")
    for wid in sorted((set(wa) | set(wb)) - allowed):
        if wid not in wb:
            diffs.append(f"{wid}: removed")
        elif wid not in wa:
            diffs.append(f"{wid}: added")
        else:
            diffs.extend(spec_mod.diff(wa[wid], wb[wid], wid, limit=10))
    order_a = [w["id"] for w in va["widgets"] if w["id"] not in allowed]
    order_b = [w["id"] for w in vb["widgets"] if w["id"] not in allowed]
    if set(order_a) == set(order_b) and order_a != order_b:
        diffs.append(f"order: {[a for a, b in zip(order_a, order_b) if a != b][:5]} …")
    ta, tb = _texture_settings(before.get("textures")), _texture_settings(after.get("textures"))
    for pkg in sorted(set(ta) & set(tb)):
        if ta[pkg] != tb[pkg]:
            diffs.append(f"texture {pkg}: {ta[pkg]} != {tb[pkg]}")
    beyond = sorted(set(touched) - allowed)
    return {"diffs": diffs, "touched_beyond": beyond, "textures_added": sorted(set(tb) - set(ta)), "textures_removed": sorted(set(ta) - set(tb))}


def geometry_changes(before: dict, after: dict, allowed: set, eps: float = GEO_EPS) -> dict:
    """{"outside": {id: {해상도: 차}}, "inside": {…}} — before · after = {해상도: {id: 줄}}. 있다가 없거나 없다가 생기면 차 None."""
    out: dict = {"outside": {}, "inside": {}}
    for res in sorted(set(before) | set(after)):
        a, b = before.get(res, {}), after.get(res, {})
        for wid in sorted(set(a) | set(b)):
            g, h = a.get(wid), b.get(wid)
            if g is None or h is None:
                d = None
            else:
                d = max(abs(float(g[k]) - float(h[k])) for k in ("x", "y", "w", "h"))
                if d <= eps:
                    continue
                d = round(d, 3)
            out["inside" if wid in allowed else "outside"].setdefault(wid, {})[res] = d
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 외형 결과 나누기

def _key(d: dict) -> tuple:
    return d.get("code"), d.get("stage"), d.get("check"), tuple(sorted(d.get("widgets") or []))


def _touch(a, b) -> bool:
    if not a or not b:
        return True
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def inside(box, zone) -> bool:
    """결함 상자가 통째로 (DEFECT_PAD 만큼 넓힌) 자리 안인가."""
    if not box or zone is None or not zone.any():
        return False
    z = dg._dilate(zone, DEFECT_PAD)
    x, y, w, h = (int(math.floor(box[0])), int(math.floor(box[1])), int(math.ceil(box[2])), int(math.ceil(box[3])))
    H, W = z.shape
    sub = z[max(0, y):max(0, y + max(1, h)), max(0, x):max(0, x + max(1, w))]
    return x >= 0 and y >= 0 and x + w <= W and y + h <= H and sub.size > 0 and bool(sub.all())


def engine_check(d: dict) -> bool:
    return str(d.get("check") or "").startswith(ENGINE_CHECKS)


def split_defects(base: list[dict], new: list[dict], zone, allowed: set) -> dict:
    """진단 결함 나누기 — {"inherited", "intended", "errors"}(각 {n, code, stage, check, widgets, box, cause, why})."""
    left = list(base)
    out: dict = {"inherited": [], "intended": [], "errors": []}

    def row(d, why):
        return {**{k: d.get(k) for k in ("n", "code", "stage", "check", "widgets", "box", "area", "max_de", "cause") if d.get(k) is not None}, "why": why}

    for d in new:
        hit = next((i for i, b in enumerate(left) if _key(b) == _key(d) and _touch(b.get("box"), d.get("box"))), None)
        if hit is not None:
            left.pop(hit)
            out["inherited"].append(row(d, "the base has it too"))
        elif engine_check(d):
            out["errors"].append(row(d, "engine-against-engine state check (bar / ring / gauge) — wrong at any design"))
        elif d.get("stage") == "text" and d.get("widgets") and set(d["widgets"]) <= allowed:
            out["intended"].append(row(d, "measures only the edited text itself"))     # 글자 결함은 그 글자 획만 잰다(상자는 컨셉 획 자리일 수 있다)
        elif inside(d.get("box"), zone):
            out["intended"].append(row(d, "inside the edited spot"))
        else:
            out["errors"].append(row(d, "outside the edited spot"))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 게이트

def appearance(gate: dict, split: dict) -> dict:
    """외형 게이트 — 오류(자리 밖 · 엔진 검사)만 센다. 원래 진단 요약은 details.diagnosis 에 남긴다."""
    errs = split["errors"]
    return {"name": gate["name"], "pass": not errs, "value": len(errs), "threshold": 0,
            "details": {"mode": "edit", "errors": errs[:20], "inherited": split["inherited"][:20], "intended": split["intended"][:20],
                        "counts": {k: len(v) for k, v in split.items()}, "diagnosis": gate.get("details")}}


def regression_gate(spec: dict, geometry: dict, images: dict, scope_ids: set, notes: dict | None = None) -> dict:
    """12번째 게이트 — spec = spec_changes, geometry = geometry_changes, images = {이름: image_row}."""
    out_px = {n: r for n, r in images.items() if r.get("outside")}
    changed = {n: r["px"] for n, r in images.items() if r.get("px")}
    effect = bool(changed) or bool(geometry["inside"]) or bool(geometry["outside"])
    problems = []
    if spec["diffs"]:
        problems.append(f"spec: {len(spec['diffs'])} difference(s) outside the targets")
    if spec["touched_beyond"]:
        problems.append(f"spec: the reconciler touched {spec['touched_beyond']}")
    if geometry["outside"]:
        problems.append(f"geometry: {sorted(geometry['outside'])[:6]} moved")
    if out_px:
        problems.append(f"pixels: {len(out_px)} of {len(images)} picture(s) differ outside the edited spot (worst {max(r['outside'] for r in out_px.values())} px)")
    if not effect:
        problems.append("NO_EFFECT: no picture and no geometry changed — wrong widget or fully covered")
    return {"name": GATE, "pass": not problems, "value": len(problems), "threshold": 0,
            "details": {"problems": problems, "scope": sorted(scope_ids), "spec": spec,
                        "geometry": {"outside": geometry["outside"], "moved_targets": geometry["inside"]},
                        "pixels": {"pictures": len(images), "changed": len(changed), "outside": out_px,
                                   "footprint": sorted(n for n, r in images.items() if r.get("footprint")), "largest_change": max(changed.values(), default=0)},
                        "effect": effect, **(notes or {})}}


# ---------------------------------------------------------------------------------------------------------------------
# 사람 눈 그림

def clusters(zone, limit: int = 4, gap: int = 24) -> list[list[int]]:
    """자리를 가까운 것끼리 묶은 상자 — 멀리 떨어진 대상을 한 장에 넣어 작아지지 않게."""
    import cv2
    if zone is None or not zone.any():
        return []
    n, lab, st, _ = cv2.connectedComponentsWithStats(dg._dilate(zone, gap).astype(np.uint8), connectivity=8)
    rows = sorted(((int(st[i, cv2.CC_STAT_AREA]), bbox(zone & (lab == i))) for i in range(1, n)), key=lambda r: -r[0])
    return [b for _, b in rows if b][:limit]


def picture(path, views: list[dict], zone, margin: int = 20, max_w: int = 620, scale_max: float = 4.0) -> dict | None:
    """edit.png — 자리 묶음마다 · 그림마다 '고치기 전 | 고친 뒤 | 달라진 픽셀'(빨강 = 자리 안, 자홍 = 자리 밖, 노란 선 = 자리). views = [{"name", "before", "after"}]."""
    import cv2
    from PIL import Image, ImageDraw
    boxes = clusters(zone)
    if not boxes or not views:
        return None
    H, W = zone.shape
    edge = zone & ~cv2.erode(zone.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    rows = []
    for k, (x, y, w, h) in enumerate(boxes, 1):
        x0, y0, x1, y1 = max(0, x - margin), max(0, y - margin), min(W, x + w + margin), min(H, y + h + margin)
        s = max(1.0, min(scale_max, max_w / float(x1 - x0)))
        seen = set()
        for v in views:
            a, b = v["before"], v["after"]
            if a.shape[:2] != (H, W) or b.shape[:2] != (H, W):
                continue
            key = (a[y0:y1, x0:x1].tobytes(), b[y0:y1, x0:x1].tobytes())
            if key in seen:                       # 이 자리에서 앞의 그림과 똑같다 — 한 번만 보여 준다
                continue
            seen.add(key)
            d = diff_mask(a, b)
            third = (b.astype(np.float32) * 0.35).astype(np.uint8)
            third[edge] = (90, 80, 0)
            third[d & zone] = (255, 60, 60)
            third[d & ~zone] = (255, 0, 255)
            sub = d[y0:y1, x0:x1]
            size = (int(round((x1 - x0) * s)), int(round((y1 - y0) * s)))
            tiles = [Image.fromarray(im[y0:y1, x0:x1]).resize(size, Image.Resampling.NEAREST if i == 2 else Image.Resampling.LANCZOS)
                     for i, im in enumerate((a, b, third))]
            row = Image.new("RGB", (size[0] * 3 + 28, size[1] + 26), (38, 40, 46))
            ImageDraw.Draw(row).text((8, 6), f"spot {k} [{x},{y} {w}x{h}] - {v['name']}: before | after | changed ({int(sub.sum())} px here, "
                                             f"{int((sub & ~zone[y0:y1, x0:x1]).sum())} outside the boxes)", fill=(235, 230, 215))
            for i, t in enumerate(tiles):
                row.paste(t, (8 + i * (size[0] + 6), 22))
            rows.append(row)
    if not rows:
        return None
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 6 for r in rows)), (20, 20, 22))
    top = 0
    for r in rows:
        sheet.paste(r, (0, top))
        top += r.height + 6
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return {"spots": boxes, "views": [v["name"] for v in views], "size": list(sheet.size)}
