"""조작 화면의 상태 검사 — 바탕 위 표시(끄기) · 긴 글자 (설계 §11 'Phase 3 설계' ②, Phase 3-3). 진단(gen/diagnose)이 부른다.

표시(E8 mark_*) — 표시를 끈 엔진 렌더 ↔ 표시 없는 합성(mark_state) · 끈 자리에 흔적도 구멍도 없는가: 시안의 띠를 획 자리만 둘레에서 메운 그림과 같은가(검정 · 회색 바탕,
  mark_trace — 획 밖은 시안 그대로여야 하므로 네모 구멍이 여기서 걸린다) · 켠 것과 뚜렷이 다른가(mark_same) · 표시 밖이 안 바뀌는가(mark_outside).
긴 글자(E8 long_*) — 긴 값을 넣은 엔진 렌더에서 바뀐 픽셀이 글자 칸(위젯 상자 + 외곽선) 밖으로 안 나가고(long_outside) · 이웃 글자에 안 닿고(long_touch) ·
  칸을 채울 만큼 길다(long_short — 짧으면 아무것도 확인한 것이 아니다). 엔진 렌더가 없으면(오프라인) 글자는 못 본다.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from gen import backdrop
from gen import diagnose as dg

MARK_RING = 4             # 흔적 판정 — 획 마스크를 이만큼 넓힌 자리까지
LONG_PAD = 2              # 글자 칸 밖 허용 — 안티앨리어싱(외곽선 · 빛 몫은 따로 더한다)
LONG_FILL = 0.8           # 긴 값은 칸 폭의 이만큼까지는 닿아야 한다
LONG_NAME = "state_long"
CHANGED = 8.0             # 바뀐 픽셀 — 채널 최대 차


def load_extra(run_dir) -> dict:
    """run 폴더 → {marks: [layer.json marks + 마스크], long: {위젯: 긴 값}}."""
    rd = pathlib.Path(run_dir)
    out: dict = {"marks": [], "long": {}}
    p = rd / "brief.json"
    if p.is_file():
        brief = json.loads(p.read_text(encoding="utf-8"))
        out["long"] = {d["widget"]: str(d["long_sample"]) for d in brief.get("dynamic_data", []) if d.get("long_sample")}
    p = rd / "layer.json"
    if p.is_file():
        for m in json.loads(p.read_text(encoding="utf-8")).get("marks") or []:
            f = rd / str(m.get("mask") or "")
            if f.is_file():
                out["marks"].append({**m, "mask_px": dg._load_l(f) > 0.5})
    return out


def mark_name(wid: str) -> str:
    return f"state_{wid}_off"


def requests(extra: dict | None, ov_state: dict) -> dict[str, dict]:
    """상태 렌더 목록(state_requests 에 더한다) — 표시마다 끈 상태 하나, 긴 글자는 모두 함께 한 장."""
    if not extra:
        return {}
    out = {mark_name(m["widget"]): {**ov_state, m["widget"]: {**ov_state.get(m["widget"], {}), "visible": False}} for m in extra["marks"]}
    if extra["long"]:
        out[LONG_NAME] = {**ov_state, **{w: {**ov_state.get(w, {}), "text": t} for w, t in extra["long"].items()}}
    return out


def _finding(check: str, wid: str, box, area, cause: str, renderer: str, max_de=None, mean_de=None) -> dict:
    return {"stage": "state", "code": "E8", "check": check, "box": [int(v) for v in box], "area": int(area), "max_de": max_de, "mean_de": mean_de, "widgets": [wid],
            "renderer": renderer, "fixable": False, "cause": cause}


def mark_states(marks: list[dict], spec_state: dict, boxes: list[dict], textures: dict, canvas, rc, ra, s: dict, base, render_state=None) -> dict:
    """base = 컨셉 상태 렌더(표시를 켠 것), rc · ra = 정답 아트(곧은 색 · 알파), render_state(이름) → 엔진 렌더(못 그리면 예외). → {marks, findings, images, renderer}."""
    from gen import overlay_mark, state_check
    W, H = int(canvas[0]), int(canvas[1])
    T, trace = float(s["local_de"]), float(s["text_trace_de"])
    out: dict = {"marks": [], "findings": [], "images": {}, "renderer": "composite" if render_state is None else "engine"}
    geo = {b["id"]: b for b in boxes}
    textz = np.zeros((H, W), bool)
    for w in spec_state.get("widgets", []):
        g = geo.get(w["id"])
        if w.get("type") in backdrop.TEXT_TYPES and g and g.get("visible", True) and g["w"] > 0:
            textz |= dg._box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], dg.HIDDEN_PAD)
    for m in marks:
        wid, box = m["widget"], m["box"]
        rec: dict = {"widget": wid, "over": m.get("over"), "box": box}
        out["marks"].append(rec)
        if not any(w["id"] == wid for w in spec_state["widgets"]):
            out["findings"].append(_finding("mark_state", wid, box, 1, "mark - the widget is gone from the spec", out["renderer"]))
            continue
        off_spec = dg._without(spec_state, {wid})
        comp = {k: backdrop.compose(off_spec, boxes, textures, canvas, bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY))}
        off = comp["black"]
        if render_state is not None:
            try:
                off = render_state(mark_name(wid))
                if off is None:
                    raise ValueError("no picture")
            except Exception as exc:  # noqa: BLE001 — 끈 상태를 못 그렸다 = 오류(합성으로 물러나지 않는다)
                out["findings"].append(_finding("mark_render", wid, box, 1, f"mark - the off state could not be rendered ({type(exc).__name__}: {str(exc)[:120]})", "engine"))
                continue
        out["images"][wid] = {"on": np.asarray(base, float), "off": np.asarray(off, float), "off_gray": comp["gray"]}
        px = m["mask_px"]
        pad = [box[0] - overlay_mark.PAD, box[1] - overlay_mark.PAD, box[2] + 2 * overlay_mark.PAD, box[3] + 2 * overlay_mark.PAD]
        zone = dg._box_mask((H, W), pad) & ~textz

        def find(check, a, b, where, limit, cause):
            de = dg.delta_e(a, b, where=where)
            loc = state_check.masked_local(de, where, state_check.BUTTON_COVER)
            fl = (loc > limit) & where
            rec.setdefault("checks", {})[check] = round(float(loc[where].max()), 2) if where.any() else 0.0
            for bl in state_check._blobs(fl, loc, 12):
                out["findings"].append(_finding(check.split(":")[0], wid, bl["box"], bl["area"], cause, out["renderer"], bl["max_de"], bl["mean_de"]))
        find("mark_state", off, comp["black"], zone, T, "mark - the off state is not what the textures give (it did not hide, or something else moved)")
        # 정답: 획 자리만 둘레에서 메운 시안 — 획 밖은 시안 그대로
        hole = dg._dilate(px, MARK_RING)
        bc, ba = overlay_mark.fill(rc, ra, hole, overlay_mark.window(box, (H, W)))
        wx0, wy0, wx1, wy1 = overlay_mark.window(box, (H, W))
        want_c, want_a = rc.copy(), ra.copy()
        want_c[wy0:wy1, wx0:wx1], want_a[wy0:wy1, wx0:wx1] = bc, ba
        for k, bg in (("black", (0.0, 0.0, 0.0)), ("gray", tuple(float(v) for v in backdrop.GRAY))):
            want = want_c * want_a[..., None] + np.asarray(bg)[None, None] * (1 - want_a[..., None])
            find(f"mark_trace:{k}", off if k == "black" else comp["gray"], want, zone, trace, f"mark - with the mark off its place is not the plain background (trace or hole, {k})")
        # 켬 ↔ 끔의 구별은 획 속에서 — 마스크는 옅은 가장자리까지라 중앙값이 흐려진다 [실측 R20261125_210931 7.8]
        true = dg.delta_e(rc * ra[..., None], want_c * want_a[..., None], where=px)
        core = px & (true >= np.percentile(true[px], 70))
        med = float(np.median(dg.delta_e(np.asarray(base, float), off, where=core)[core]))
        rec["contrast"] = round(med, 1)
        if med < T:
            out["findings"].append(_finding("mark_same", wid, box, int(core.sum()), f"mark - on and off look the same (median difference {med:.1f})", out["renderer"], round(med, 1)))
        outside = ~dg._dilate(px, 2)
        find("mark_outside", off, np.asarray(base, float), outside, T, "mark - hiding it changes something else")
    return out


def long_texts(longs: dict[str, str], spec_state: dict, boxes: list[dict], canvas, s: dict, base, render_state=None, notext=None) -> dict:
    """긴 글자 — base = 컨셉 상태 엔진 렌더, notext = 글자를 모두 비운 엔진 렌더(칸을 채웠는가 · 이웃 글자 자리). → {texts, findings, image}."""
    W, H = int(canvas[0]), int(canvas[1])
    out: dict = {"texts": [], "findings": [], "image": None, "renderer": "composite" if render_state is None else "engine"}
    if not longs or render_state is None:
        return out
    geo = {b["id"]: b for b in boxes}
    index = {w["id"]: w for w in spec_state["widgets"]}
    try:
        img = render_state(LONG_NAME)
        if img is None:
            raise ValueError("no picture")
    except Exception as exc:  # noqa: BLE001
        for wid in longs:
            out["findings"].append(_finding("long_render", wid, [0, 0, W, H], 1, f"long text - the state could not be rendered ({type(exc).__name__}: {str(exc)[:120]})", "engine"))
        return out
    out["image"] = img
    base = np.asarray(base, float)
    changed = dg.maxabs(img, base) > CHANGED
    zones = {}
    allowed = np.zeros((H, W), bool)
    for wid in longs:
        g, w = geo.get(wid), index.get(wid)
        if not g or not w or g["w"] <= 0:
            out["findings"].append(_finding("long_render", wid, [0, 0, W, H], 1, "long text - the text widget is not drawn", "engine"))
            continue
        pad = LONG_PAD + float(((w.get("font") or {}).get("outline") or {}).get("size") or 0) + float(((w.get("font") or {}).get("glow") or {}).get("size") or 0)
        zones[wid] = dg._box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], pad)
        allowed |= zones[wid]
    import cv2
    stray = changed & ~allowed
    n, lab, st, _ = cv2.connectedComponentsWithStats(stray.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 6:
            x, y, bw, bh = (int(v) for v in st[i, :4])
            own = min(zones, key=lambda k: abs(geo[k]["y"] + geo[k]["h"] / 2 - (y + bh / 2)) + abs(geo[k]["x"] + geo[k]["w"] / 2 - (x + bw / 2)) * 0.1)
            out["findings"].append(_finding("long_outside", own, [x, y, bw, bh], int(st[i, cv2.CC_STAT_AREA]), "long text - the text leaves its box", "engine"))
    for wid, z in zones.items():
        g = geo[wid]
        rec = {"widget": wid, "box": [round(float(g[k]), 1) for k in ("x", "y", "w", "h")], "long": longs[wid]}
        ink = (dg.maxabs(img, notext) > dg.INK_FLOOR) & z if notext is not None else changed & z
        xs = np.nonzero(ink.any(axis=0))[0]
        reach = float(xs.max() - xs.min() + 1) / float(g["w"]) if len(xs) else 0.0
        rec["fill"] = round(reach, 3)
        if reach < LONG_FILL:
            out["findings"].append(_finding("long_short", wid, [g["x"], g["y"], g["w"], g["h"]], int(ink.sum()),
                                            f"long text - it fills only {reach:.0%} of its box, so nothing was checked (longer sample, or the text was not applied)", "engine"))
        for w in spec_state["widgets"]:                           # 이웃 글자 칸으로 들어가는가(글자 칸끼리 겹치면 긴 값이 이웃 위에 그려진다)
            o = geo.get(w["id"])
            if w["id"] == wid or w.get("type") not in backdrop.TEXT_TYPES or not o or not o.get("visible", True) or o["w"] <= 0:
                continue
            hit = ink & dg._box_mask((H, W), [o["x"], o["y"], o["w"], o["h"]])
            if int(hit.sum()) >= 6:
                out["findings"].append(_finding("long_touch", wid, dg._bbox(hit), int(hit.sum()), f"long text - it runs into '{w['id']}'", "engine"))
                rec.setdefault("touches", []).append(w["id"])
        out["texts"].append(rec)
    return out
