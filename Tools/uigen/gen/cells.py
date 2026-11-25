"""놓인 칸(UserWidget) — 진단은 칸을 '그 칸의 spec + 텍스처로 합성한 그림 한 장'으로 본다 (설계 §11 'Phase 3 설계' ②).

칸은 자기 run 에서 만들어 승격한 WBP 다. 승격 기록(promoted/<ScreenId>/promotion.json)의 wbp 경로로 원천 묶음을 찾아, 그 칸의 spec · geometry · 텍스처를
투명 위에 쌓는다(글자는 엔진 글꼴이라 빠진다 — 글자 상자를 따로 준다). 버튼 칸이면 상태마다 한 장(core/button 의 상태 일곱).
"""
from __future__ import annotations

import functools
import json
import pathlib

import numpy as np

from core import button, config
from core import spec as spec_mod

ROOT = config.UIGEN_DIR / "promoted"
PREFIX = "cell:"              # textures 사전의 열쇠 — 에셋 id 와 섞이지 않게


def key(class_path: str, brush: str = button.BASE) -> str:
    return f"{PREFIX}{class_path.split('.', 1)[0]}" + ("" if brush == button.BASE else f"#{brush}")


def index(root: pathlib.Path | None = None) -> dict[str, dict]:
    """승격된 화면 — WBP 패키지 경로 → {screen_id, source}."""
    out = {}
    for p in sorted(pathlib.Path(root or ROOT).glob("*/promotion.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[rec["wbp"].split(".", 1)[0]] = {"screen_id": rec["screen_id"], "source": p.parent / "source"}
    return out


def placed(spec: dict) -> list[dict]:
    return [w for w in spec.get("widgets", []) if w.get("type") == spec_mod.CELL_TYPE]


@functools.lru_cache(maxsize=16)
def _picture(source: str, stamp: float) -> dict:
    """칸 하나 — {size, states: {상태: 곧은 RGBA float}, texts: [상자], button}. 묶음이 바뀌면(stamp) 다시."""
    from gen import backdrop
    sd = pathlib.Path(source)
    spec = json.loads((sd / "spec.json").read_text(encoding="utf-8"))
    geo = json.loads((sd / "geometry.json").read_text(encoding="utf-8"))
    manifest = json.loads((sd / "manifest.json").read_text(encoding="utf-8"))
    canvas = [int(v) for v in spec["canvas"]]
    boxes = geo["geometry"].get(f"{canvas[0]}x{canvas[1]}") or next(iter(geo["geometry"].values()))
    textures = {a["asset_id"]: backdrop._load(sd / a["file"]) for a in manifest["assets"]}
    used = button.brush_assets(spec)
    states = {}
    for brush in used or {button.BASE: None}:
        sp = with_state(spec, brush) if used else spec
        rgb, cov, _ = backdrop.compose(sp, boxes, textures, canvas, (0, 0, 0))
        col = np.where(cov[..., None] > 1e-4, rgb / np.maximum(cov, 1e-4)[..., None], 0.0)
        states[brush] = np.concatenate([np.clip(col, 0, 255), cov[..., None] * 255], axis=2)
    types = {w["id"]: w.get("type") for w in spec["widgets"]}
    texts = [[float(b[k]) for k in ("x", "y", "w", "h")] for b in boxes if types.get(b["id"]) in backdrop.TEXT_TYPES and b.get("visible", True)]
    return {"size": canvas, "states": states, "texts": texts, "button": bool(used)}


def with_state(spec: dict, brush: str) -> dict:
    """버튼 칸 spec 의 기본 그림을 그 상태의 에셋으로 바꾼 사본(합성용)."""
    aid = button.brush_assets(spec)[brush]
    art = button.art_id(spec)
    return {**spec, "widgets": [{**w, "style": {**w["style"], "brush": {**w["style"]["brush"], "asset": aid}}} if w["id"] == art else w for w in spec["widgets"]]}


def picture(class_path: str, root: pathlib.Path | None = None) -> dict | None:
    rec = index(root).get(class_path.split(".", 1)[0])
    if rec is None or not (rec["source"] / "geometry.json").is_file():
        return None
    return _picture(rec["source"].as_posix(), (rec["source"] / "spec.json").stat().st_mtime)


def attach(spec: dict, textures: dict, root: pathlib.Path | None = None) -> dict:
    """놓인 칸마다 합성 그림을 textures 에 더한다(backdrop.compose 가 쓴다) — 못 찾은 칸은 빠지고 합성이 missing 으로 적는다. textures 를 돌려준다."""
    for w in placed(spec):
        p = picture(str(w.get("class") or ""), root)
        if p is not None:
            for brush, img in p["states"].items():
                textures[key(w["class"], brush)] = img
    return textures


def text_boxes(spec: dict, boxes: list[dict], root: pathlib.Path | None = None) -> list[tuple[str, list[float]]]:
    """놓인 칸 안 글자 상자(화면 좌표) — [(칸 id, [x, y, w, h])]. 화면 spec 에는 그 글자가 없다. 렌더 geometry 의 '칸/글자' 줄(실제로 그려진 자리 — 글자는 놓은
    화면이 정해 칸 혼자의 보기 글자와 길이가 다르다), 없으면(옛 geometry) 칸 혼자 그린 자리."""
    geo = {b["id"]: b for b in boxes}
    out = []
    for w in placed(spec):
        p, g = picture(str(w.get("class") or ""), root), geo.get(w["id"])
        if p is None or not g or not g.get("visible", True) or g["w"] <= 0 or g["h"] <= 0:
            continue
        rows = [b for b in boxes if b["id"].startswith(w["id"] + "/")]
        if rows:
            out += [(w["id"], [float(b[k]) for k in ("x", "y", "w", "h")]) for b in rows if b.get("visible", True) and b["w"] > 0 and b["h"] > 0]
            continue
        kx, ky = float(g["w"]) / p["size"][0], float(g["h"]) / p["size"][1]
        out += [(w["id"], [g["x"] + t[0] * kx, g["y"] + t[1] * ky, t[2] * kx, t[3] * ky]) for t in p["texts"]]
    return out
