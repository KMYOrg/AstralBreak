"""회색 · 다른 바탕 위 확인 (1b 후속 H3 — 기록만).

render_widget 은 검정 바탕에 구운 불투명 PNG 만 낸다. 검정 위에선 '어둡고 불투명한 칠'과 '투명'이 같은 픽셀이라, H2 끝 run 의 결함
(엠블럼 뒤 문양이 불투명 남색 얼룩 · 띠 끝이 들쭉날쭉 잘림)을 렌더 · 지표가 못 잡고 사람이 WBP 디자이너 회색 바탕에서 찾았다
[실측 R20261116_212649]. 그래서 최종 텍스처를 위젯 상자(geometry.json — 실제 렌더의 상자) · 그리는 순서(캔버스 z · 자식 순서)대로
아무 바탕 위에 다시 쌓는다(C++ 변경 없음 — 사용자 결정 11-17). 글자(TextBlock)는 엔진 글꼴이라 빠진다 — 지표는 글자 상자를 뺀다.

  compose(...)      → 바탕 위에 쌓은 RGB · 덮임(알파) · 기록(그린 위젯 · 못 그린 것)
  check(run_dir)    → 합성기 검산(검정 위 합성 ↔ render.png) · 회색 위 합성 ↔ 컨셉(곧은 색 · 알파를 회색 위에) ΔE00 ·
                      '어둡고 불투명' 비율 · 알파 절벽(합성엔 있고 컨셉엔 없는 급경사) + 그림(assets/compare/backdrop_*.png)
컨셉 쪽 정답은 ⓐ transparent 일 때만 진짜다(ⓑ 는 flat_unmix 추정 — truth 'unmix_estimate' 로 표시, ⓒ 는 비교 없음).
Slate 는 곧은 색을 sRGB 값 그대로 섞는다(검산으로 고름 — 기록 compositor.space). 값은 잠정이다.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

GRAY = (128, 128, 128)
DARK_MAX = 90              # '어두운' 픽셀 = 곧은 색 채널 최대가 이보다 작음
OPAQUE = 0.95              # 그중 알파가 이보다 크면 '어둡고 불투명'
VISIBLE = 0.02
CLIFF = 0.5                # 이웃 픽셀 알파 차가 이보다 크면 절벽
CLIFF_REF = 0.2            # 컨셉 알파 차가 이보다 작은 자리의 절벽 = 컨셉에 없는 절벽(잘림)
TEXT_PAD = 6               # 글자 상자 제외 여유(빛 · 안티앨리어싱)
TEXT_TYPES = ("TextBlock", "RichTextBlock")


def _rgba(color: str | None, default=(255, 255, 255, 255)) -> np.ndarray:
    if not color:
        return np.asarray(default, float)
    h = color.lstrip("#")
    v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
    return np.asarray(v + [255] * (4 - len(v)), float)


def paint_order(spec: dict) -> list[dict]:
    """그리는 순서 — 깊이 우선, 캔버스 자식은 slot.z 오름차순(같으면 spec 순서 — Slate SConstraintCanvas 와 같음), 그 밖은 spec 순서."""
    kids: dict[str, list[dict]] = {}
    by_id = {}
    for w in spec.get("widgets", []):
        by_id[w["id"]] = w
        if w.get("parent"):
            kids.setdefault(w["parent"], []).append(w)
    out: list[dict] = []

    def walk(w):
        out.append(w)
        ch = kids.get(w["id"], [])
        if w.get("type") == "CanvasPanel":
            ch = sorted(ch, key=lambda c: (c.get("slot") or {}).get("z", 0))     # sorted 는 안정 정렬
        for c in ch:
            walk(c)
    root = by_id.get(spec.get("root") or "Root")
    if root:
        walk(root)
    return out


def _load(path: pathlib.Path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"), float)


def _resize(tex: np.ndarray, w: int, h: int) -> np.ndarray:
    """곧은 RGBA 를 미리 곱한 채로 늘려 가장자리 색이 검게 번지지 않게."""
    import cv2
    if tex.shape[1] == w and tex.shape[0] == h:
        return tex
    a = tex[..., 3:4] / 255.0
    pm = np.concatenate([tex[..., :3] * a, a], axis=2).astype(np.float32)
    interp = cv2.INTER_AREA if (w < tex.shape[1] and h < tex.shape[0]) else cv2.INTER_LINEAR
    r = cv2.resize(pm, (max(1, w), max(1, h)), interpolation=interp).astype(float)
    ra = np.clip(r[..., 3:4], 0, 1)
    col = np.where(ra > 1e-4, r[..., :3] / np.maximum(ra, 1e-4), 0)
    return np.concatenate([np.clip(col, 0, 255), ra * 255], axis=2)


def _nine_slice(tex: np.ndarray, w: int, h: int, margin, image_size) -> np.ndarray:
    """box · border — 모서리 = 텍스처(또는 image_size) 픽셀 × margin 크기 그대로, 변 · 가운데는 늘림(border 는 가운데 비움)."""
    th, tw = tex.shape[:2]
    isz = image_size or [tw, th]
    l, t, r, b = (float(m) for m in margin)
    dl, dr = int(round(l * isz[0])), int(round(r * isz[0]))
    dt, db = int(round(t * isz[1])), int(round(b * isz[1]))
    sl, sr, st, sb = int(round(l * tw)), int(round(r * tw)), int(round(t * th)), int(round(b * th))
    dl, dr = min(dl, w // 2), min(dr, w - w // 2)
    dt, db = min(dt, h // 2), min(db, h - h // 2)
    out = np.zeros((h, w, 4), float)
    xs = [(0, sl, 0, dl), (sl, tw - sr, dl, w - dr), (tw - sr, tw, w - dr, w)]
    ys = [(0, st, 0, dt), (st, th - sb, dt, h - db), (th - sb, th, h - db, h)]
    for (sy0, sy1, dy0, dy1) in ys:
        for (sx0, sx1, dx0, dx1) in xs:
            if sy1 > sy0 and sx1 > sx0 and dy1 > dy0 and dx1 > dx0:
                out[dy0:dy1, dx0:dx1] = _resize(tex[sy0:sy1, sx0:sx1], dx1 - dx0, dy1 - dy0)
    return out


def _rounded(w: int, h: int, brush: dict) -> np.ndarray:
    c = _rgba(brush.get("color"))
    rad = float(brush.get("radius") or 0)
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    dx = np.maximum(np.maximum(rad - xx, xx - (w - rad)), 0)
    dy = np.maximum(np.maximum(rad - yy, yy - (h - rad)), 0)
    inside = np.clip(rad - np.hypot(dx, dy) + 0.5, 0, 1) if rad > 0 else np.ones((h, w))
    out = np.zeros((h, w, 4), float)
    out[..., :3] = c[:3]
    out[..., 3] = inside * c[3]
    ow = float(brush.get("outline_width") or 0)
    if ow > 0 and brush.get("outline_color"):
        oc = _rgba(brush["outline_color"])
        edge = np.minimum(np.minimum(xx, w - xx), np.minimum(yy, h - yy))
        ring = (edge < ow) & (inside > 0)
        out[ring, :3] = oc[:3]
        out[ring, 3] = oc[3] * inside[ring]
    return out


def _brush_layer(brush: dict | None, w: int, h: int, textures: dict, missing: list, wid: str) -> np.ndarray | None:
    if not brush or brush.get("draw_as", "image") == "none" or w <= 0 or h <= 0:
        return None
    da = brush.get("draw_as", "image")
    if da == "rounded_box" or not brush.get("asset"):
        if da == "rounded_box":
            return _rounded(w, h, brush)
        c = _rgba(brush.get("color"))
        out = np.zeros((h, w, 4), float)
        out[..., :3], out[..., 3] = c[:3], c[3]
        return out
    tex = textures.get(brush["asset"])
    if tex is None:
        missing.append({"widget": wid, "asset": brush["asset"]})
        return None
    if da in ("box", "border") and brush.get("margin"):
        lay = _nine_slice(tex, w, h, brush["margin"], brush.get("image_size"))
        if da == "border":
            m = brush["margin"]
            th, tw = tex.shape[:2]
            isz = brush.get("image_size") or [tw, th]
            x0, x1 = int(round(m[0] * isz[0])), w - int(round(m[2] * isz[0]))
            y0, y1 = int(round(m[1] * isz[1])), h - int(round(m[3] * isz[1]))
            if x1 > x0 and y1 > y0:
                lay[y0:y1, x0:x1] = 0
    else:
        lay = _resize(tex, w, h).copy()
    tint = _rgba(brush.get("color"))
    lay[..., :3] *= tint[:3] / 255.0
    lay[..., 3] *= tint[3] / 255.0
    return lay


def _apply_wipe(lay: np.ndarray, brush: dict, wipe: dict, percent, textures: dict) -> None:
    """원형 닦기(전투 HUD 동작, 11-23) — 레이어 알파를 제자리에서 닦는다(gen/radial.wipe_factor — 엔진 M_RadialWipe 와 같은 식). 중심은 image_size 픽셀 기준."""
    from gen import radial
    h, w = lay.shape[:2]
    tex = textures.get(brush.get("asset"))
    isz = brush.get("image_size") or ([tex.shape[1], tex.shape[0]] if tex is not None else [w, h])
    c = wipe.get("center") or [isz[0] / 2, isz[1] / 2]
    lay[..., 3] *= radial.wipe_factor((h, w), [float(c[0]) * w / float(isz[0]), float(c[1]) * h / float(isz[1])], float(percent),
                                      wipe.get("mode", "clockwise"), float(wipe.get("track_alpha", 0)))


def _progress_layers(st: dict, w: int, h: int, textures, missing, wid) -> list[tuple[np.ndarray, tuple]]:
    out = []
    bg = _brush_layer(st.get("background"), w, h, textures, missing, wid)
    if bg is not None:
        out.append((bg, (0, 0)))
    pct = float(st.get("percent", 0.0))
    fill_brush = dict(st.get("fill") or {})
    if st.get("fill_color") and not fill_brush.get("color"):
        fill_brush["color"] = st["fill_color"]
    if not fill_brush or pct <= 0:
        return out
    kind = st.get("bar_fill_type", "left_to_right")
    horiz = kind in ("left_to_right", "right_to_left", "fill_from_center")
    full = w if horiz else h
    n = int(round(full * min(pct, 1.0)))
    if n <= 0:
        return out
    if st.get("bar_fill_style") == "scale":
        lay = _brush_layer(fill_brush, n if horiz else w, h if horiz else n, textures, missing, wid)
    else:
        lay = _brush_layer(fill_brush, w, h, textures, missing, wid)
    if lay is None:
        return out
    if st.get("bar_fill_style") != "scale":
        if kind == "left_to_right":
            lay, off = lay[:, :n], (0, 0)
        elif kind == "right_to_left":
            lay, off = lay[:, w - n:], (w - n, 0)
        elif kind == "fill_from_center":
            a = (w - n) // 2
            lay, off = lay[:, a:a + n], (a, 0)
        elif kind == "top_to_bottom":
            lay, off = lay[:n], (0, 0)
        else:
            lay, off = lay[h - n:], (0, h - n)
    else:
        off = {"right_to_left": (w - n, 0), "fill_from_center": ((w - n) // 2, 0), "bottom_to_top": (0, h - n)}.get(kind, (0, 0))
    out.append((lay, off))
    return out


OWNER_ALPHA = 0.1          # owners=True — 픽셀마다 이보다 불투명하게 마지막으로 그린 위젯(맨 위)


def compose(spec: dict, boxes: list[dict], textures: dict, canvas, background=GRAY, owners: bool = False) -> tuple[np.ndarray, np.ndarray, dict]:
    """spec 그리는 순서 · boxes(geometry 한 해상도 — 실제 렌더 상자) · textures {asset_id: 곧은 RGBA float} → (RGB float, 덮임 0 ~ 1, 기록).
    섞기는 곧은 색 sRGB 값 그대로(src·a + dst·(1 − a)). 보이지 않는(visible false) 위젯과 그 아래는 그리지 않는다.
    owners 면 기록에 'owner'(픽셀마다 맨 위 위젯 번호 — 없으면 -1) · 'owner_ids'(번호 → 위젯 id)를 더한다(1b 후속 J 진단)."""
    W, H = int(canvas[0]), int(canvas[1])
    acc = np.ones((H, W, 3), float) * np.asarray(background, float)[None, None]
    cov = np.zeros((H, W), float)
    owner = np.full((H, W), -1, np.int32) if owners else None
    owner_ids: list[str] = []
    geo = {b["id"]: b for b in boxes}
    drawn, missing, skipped_text, hidden = [], [], [], set()
    for w in paint_order(spec):
        g = geo.get(w["id"])
        # 시작 때 숨은 위젯도 그린다(render.png 의 force_visible 과 같은 상태) — 컨셉은 경고 글자 · 빛처럼 기본으로 숨은 위젯이 보이는 상태를 그리기도 해
        # 숨김을 빼면 오히려 컨셉과 멀어졌다 [실측 H3 — 단색 전투 HUD 회색 ΔE00 6.8 → 11.0]. 렌더 상자에서 안 보이는(visible false) 위젯만 뺀다
        if w.get("parent") in hidden or g is None or not g.get("visible", True):
            hidden.add(w["id"])
            continue
        x, y, bw, bh = (int(round(float(g[k]))) for k in ("x", "y", "w", "h"))
        st = w.get("style") or {}
        t = w.get("type")
        if t in TEXT_TYPES:
            skipped_text.append(w["id"])
            continue
        if t in ("Image", "Border"):
            lays = [(lay, (0, 0))] if (lay := _brush_layer(st.get("brush"), bw, bh, textures, missing, w["id"])) is not None else []
            wipe = (st.get("brush") or {}).get("wipe")
            if wipe and lays:
                _apply_wipe(lays[0][0], st["brush"], wipe, st.get("percent", 1.0), textures)
        elif t == "ProgressBar":
            lays = _progress_layers(st, bw, bh, textures, missing, w["id"])
        elif t == "Button":
            lays = [(lay, (0, 0))] if (lay := _brush_layer(st.get("normal"), bw, bh, textures, missing, w["id"])) is not None else []
        elif t == "UserWidget":                        # Phase 3-2 — 놓인 칸: 그 칸을 합성한 그림 한 장(gen/cells.attach 가 textures 에 넣는다)
            from gen import cells
            cell = textures.get(cells.instance_key(w["id"]))          # 그 칸 하나만 바꾼 그림(상태 합성)이 먼저
            if cell is None:
                cell = textures.get(cells.key(str(w.get("class") or "")))
            if cell is None:
                missing.append({"widget": w["id"], "asset": w.get("class")})
            lays = [(_resize(cell, bw, bh), (0, 0))] if cell is not None and bw > 0 and bh > 0 else []
        else:
            lays = []
        for lay, (ox, oy) in lays:
            lh, lw = lay.shape[:2]
            x0, y0 = x + ox, y + oy
            cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x0 + lw), min(H, y0 + lh)
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            sub = lay[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
            a = np.clip(sub[..., 3] / 255.0, 0, 1)
            acc[cy0:cy1, cx0:cx1] = sub[..., :3] * a[..., None] + acc[cy0:cy1, cx0:cx1] * (1 - a[..., None])
            cov[cy0:cy1, cx0:cx1] = a + cov[cy0:cy1, cx0:cx1] * (1 - a)
            if owner is not None:
                if not owner_ids or owner_ids[-1] != w["id"]:
                    owner_ids.append(w["id"])
                sel = a > OWNER_ALPHA
                o = owner[cy0:cy1, cx0:cx1]
                o[sel] = len(owner_ids) - 1
            drawn.append(w["id"])
    info = {"drawn": sorted(set(drawn)), "missing": missing, "text_skipped": skipped_text}
    if owner is not None:
        info.update(owner=owner, owner_ids=owner_ids)
    return np.clip(acc, 0, 255), cov, info


def text_mask(spec: dict, boxes: list[dict], canvas, pad: int = TEXT_PAD) -> np.ndarray:
    W, H = int(canvas[0]), int(canvas[1])
    m = np.zeros((H, W), bool)
    types = {w["id"]: w.get("type") for w in spec.get("widgets", [])}
    for b in boxes:
        if types.get(b["id"]) in TEXT_TYPES and b.get("visible", True):
            x0, y0 = max(0, int(b["x"]) - pad), max(0, int(b["y"]) - pad)
            m[y0:int(b["y"] + b["h"]) + pad, x0:int(b["x"] + b["w"]) + pad] = True
    return m


def _cliffs(a: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(a, bool)
    gx[:, 1:] = np.abs(np.diff(a, axis=1)) > CLIFF
    gy = np.zeros_like(a, bool)
    gy[1:] = np.abs(np.diff(a, axis=0)) > CLIFF
    return gx | gy


def _ref_grad(a: np.ndarray) -> np.ndarray:
    g = np.zeros_like(a)
    g[:, 1:] = np.abs(np.diff(a, axis=1))
    g[1:] = np.maximum(g[1:], np.abs(np.diff(a, axis=0)))
    import cv2
    return cv2.dilate(g.astype(np.float32), np.ones((3, 3), np.uint8))     # ±1 px 어긋남은 같은 절벽


def dark_opaque(rgb: np.ndarray, a: np.ndarray, where=None) -> dict:
    """곧은 색이 어두운(채널 최대 < DARK_MAX) 보이는 픽셀 중 알파 > OPAQUE 비율 — 검정 배경 컨셉을 불투명으로 읽은 흔적."""
    dark = (rgb[..., :3].max(axis=2) < DARK_MAX) & (a > VISIBLE)
    if where is not None:
        dark &= where
    n = int(dark.sum())
    return {"dark_px": n, "opaque_ratio": round(float((a[dark] > OPAQUE).mean()), 4) if n else None}


def check(run_dir, background=GRAY, out_dir=None) -> dict:
    """run 폴더 → 기록(report.recorded.backdrop). 그림: <out_dir 또는 assets/compare>/backdrop_gray.png(합성 — 글자 없음) ·
    backdrop_concept_gray.png(컨셉을 같은 바탕 위에 — ⓐ ⓑ) · backdrop.png(위 둘을 나란히 · 절반 크기)."""
    from PIL import Image

    from core import color
    rd = pathlib.Path(run_dir)
    spec = json.loads((rd / "spec.json").read_text(encoding="utf-8"))
    geo = json.loads((rd / "geometry.json").read_text(encoding="utf-8"))
    canvas = geo.get("canvas") or spec.get("canvas")
    boxes = geo["geometry"].get(f"{canvas[0]}x{canvas[1]}") or next(iter(geo["geometry"].values()))
    manifest = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    from gen import cells
    textures = cells.attach(spec, {a["asset_id"]: _load(rd / a["file"]) for a in manifest.get("assets", []) if a.get("file") and (rd / a["file"]).is_file()})
    norm = json.loads((rd / "normalize.json").read_text(encoding="utf-8")) if (rd / "normalize.json").is_file() else {}
    bg_kind = ((norm.get("fit") or norm).get("background") or {}).get("kind") if isinstance(norm, dict) else None
    tmask = text_mask(spec, boxes, canvas)
    rec: dict = {"background": "#%02X%02X%02X" % tuple(background), "concept_kind": bg_kind, "text_excluded_px": int(tmask.sum())}

    # 합성기 검산 — 검정 위 합성 ↔ 실제 렌더(글자 상자 밖, 둘 중 하나라도 보이는 자리)
    black, cov_b, info = compose(spec, boxes, textures, canvas, (0, 0, 0))
    rec["compose"] = info
    if (rd / "render.png").is_file():
        ren = _load(rd / "render.png")[..., :3]
        if ren.shape[:2] == black.shape[:2]:
            m = ~tmask & ((cov_b > VISIBLE) | (ren.max(axis=2) > 8))
            d = np.abs(black - ren).max(axis=2)[m]
            rec["compositor"] = {"space": "srgb", "px": int(m.sum()), "mean_abs": round(float(d.mean()), 2) if d.size else None,
                                 "p95_abs": round(float(np.percentile(d, 95)), 2) if d.size else None}
    gray, cov, _ = compose(spec, boxes, textures, canvas, background)
    out = pathlib.Path(out_dir) if out_dir else rd / "assets" / "compare"
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray.round().astype(np.uint8)).save(out / "backdrop_gray.png")
    # 텍스처마다 '어둡고 불투명'
    per = {aid: dark_opaque(t[..., :3], t[..., 3] / 255.0) for aid, t in textures.items()}
    rec["dark_opaque_textures"] = {k: v for k, v in per.items() if v["dark_px"]}
    # 컨셉 쪽(ⓐ = 정답 · ⓑ = 추정)
    rcol, ralpha = rd / "reference_color.png", rd / "reference_alpha.png"
    if rcol.is_file() and ralpha.is_file():
        rc = _load(rcol)[..., :3]
        with Image.open(ralpha) as im:
            ra = np.asarray(im.convert("L"), float) / 255.0
        rec["truth"] = "concept_alpha" if bg_kind == "transparent" else "unmix_estimate"
        cg = rc * ra[..., None] + np.asarray(background, float)[None, None] * (1 - ra[..., None])
        Image.fromarray(np.clip(cg, 0, 255).round().astype(np.uint8)).save(out / "backdrop_concept_gray.png")
        m = ~tmask & ((cov > VISIBLE) | (ra > VISIBLE))
        if m.any():
            de = color.delta_e00(color.srgb_to_lab(gray[m]), color.srgb_to_lab(cg[m]))
            rec["gray_de00"] = {"px": int(m.sum()), "mean": round(float(de.mean()), 2), "p95": round(float(np.percentile(de, 95)), 2),
                                "over10": round(float((de > 10).mean()), 4)}
            rec["alpha_mae"] = round(float(np.abs(cov[m] - ra[m]).mean()), 4)
        cl = _cliffs(cov) & (_ref_grad(ra) < CLIFF_REF) & ~tmask
        rec["alpha_cliffs"] = {"compose_only": int(cl.sum()), "concept": int((_cliffs(ra) & ~tmask).sum())}
        # 합성 쪽 '어둡고 불투명'(보이는 위젯 자리) ↔ 컨셉
        comp_rgb = np.where(cov[..., None] > 1e-3, (gray - np.asarray(background, float) * (1 - cov[..., None])) / np.maximum(cov, 1e-3)[..., None], 0)
        rec["dark_opaque"] = {"compose": dark_opaque(np.clip(comp_rgb, 0, 255), cov, ~tmask), "concept": dark_opaque(rc, ra, ~tmask)}
        h, w = gray.shape[:2]
        side = np.concatenate([np.clip(cg, 0, 255), np.full((h, 8, 3), 255.0), gray], axis=1).round().astype(np.uint8)
        Image.fromarray(side).resize((side.shape[1] // 2, h // 2), Image.Resampling.LANCZOS).save(out / "backdrop.png")
    rec["images"] = sorted(p.name for p in out.glob("backdrop*.png"))
    return rec
