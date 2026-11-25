"""공용 테마(config/theme_<id>.yaml) — 버튼 상태 그림 = 기본 그림의 함수 (설계 §11 'Phase 3 설계' ② · 작은 시험 (다)).

상태 일곱 중 기본(normal_base)은 사람이 승인한 그림 그대로이고, 나머지 여섯은 여기 식으로 만든다(codex 0). 알파는 비활성만 곱한다 — 다시 그린 상태 그림은
윤곽이 2.6 ~ 3.9 px 흔들렸고(codex 편집 · 상태 시트) 식은 0 이다 [실측 11-25]. 식이 정답이라 엔진 렌더를 픽셀로 견줄 수 있다(gen/state_check button_states).
선택은 어느 상태 위에나 얹는 덮개라, 그 상태의 색을 강조색 쪽으로 같은 비율만큼 섞는다(알파 그대로).
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np

from core import button, config

LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)


class ThemeError(ValueError):
    pass


def path_of(theme_id: str) -> pathlib.Path:
    return config.CONFIG_DIR / f"theme_{theme_id}.yaml"


def load(theme_id: str, path=None) -> dict:
    """테마 + sha256(내용의 정규 JSON — 줄바꿈 · 주석과 무관). 빠진 값은 오류(기본값으로 메우지 않는다)."""
    p = pathlib.Path(path) if path else path_of(theme_id)
    try:
        t = config.load_yaml(p)
    except config.ConfigError as exc:
        raise ThemeError(str(exc)) from exc
    need = {"text": ("color", "outline", "pressed_offset"), "button": ("accent", "line", "hovered", "pressed", "disabled", "selected")}
    for sec, keys in need.items():
        if not isinstance(t.get(sec), dict) or any(k not in t[sec] for k in keys):
            raise ThemeError(f"{p.name}: '{sec}' needs {list(keys)}")
    for sec, keys in (("line", ("lo", "span")), ("hovered", ("warm", "lift", "lift_left", "lift_reach", "line_floor", "line_full")),
                      ("pressed", ("plate", "line", "line_tint")), ("disabled", ("line", "alpha")), ("selected", ("fill", "reach"))):
        v = t["button"][sec]
        if not isinstance(v, dict) or any(k not in v for k in keys):
            raise ThemeError(f"{p.name}: button.{sec} needs {list(keys)}")
    if t.get("id") != theme_id:
        raise ThemeError(f"{p.name}: id '{t.get('id')}' != '{theme_id}'")
    t["sha256"] = hashlib.sha256(json.dumps({k: v for k, v in t.items() if k != "sha256"}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return t


def _rgb(hex_color: str) -> np.ndarray:
    h = str(hex_color).lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def smooth(t) -> np.ndarray:
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _parts(c: np.ndarray, t: dict):
    rgb, a = c[..., :3].astype(np.float32), c[..., 3:4].astype(np.float32)
    lum = (rgb @ LUM)[..., None] / 255.0
    line = smooth((lum - float(t["line"]["lo"])) / max(1e-6, float(t["line"]["span"])))      # 선 · 칼날 정도
    x = np.linspace(0, 1, c.shape[1], dtype=np.float32)[None, :, None]
    return rgb, a, lum, line, x


def _hovered(c, t):
    rgb, _, lum, line, x = _parts(c, t)
    h = t["hovered"]
    lift = float(h["lift"]) + float(h["lift_left"]) * smooth(1 - x / max(1e-6, float(h["lift_reach"])))
    plate = rgb + (_rgb(h["warm"]) - rgb) * lift
    edge = _rgb(t["accent"]) * (float(h["line_floor"]) + (1 - float(h["line_floor"])) * smooth(lum / max(1e-6, float(h["line_full"]))))
    return plate * (1 - line) + edge * line


def _pressed(c, t):
    rgb, _, lum, line, _ = _parts(c, t)
    p = t["pressed"]
    return rgb * float(p["plate"]) * (1 - line) + (lum * float(p["line"])) * _rgb(p["line_tint"]) * line


def _disabled(c, t):
    _, _, lum, line, _ = _parts(c, t)
    return np.repeat(lum * 255 * (1 - (1 - float(t["disabled"]["line"])) * line), 3, -1)


def _selected(rgb, c, t):
    _, _, _, line, x = _parts(c, t)
    s = t["selected"]
    m = np.maximum(float(s["fill"]) * smooth(1 - x / max(1e-6, float(s["reach"]))), line)
    return rgb * (1 - m) + _rgb(t["accent"]) * m


def state(rgba, brush: str, theme: dict) -> np.ndarray:
    """기본 그림(곧은 RGBA — HxWx4, 0 ~ 255) → 그 상태의 RGBA(uint8)."""
    c = np.asarray(rgba, np.float32)
    t = theme["button"]
    if brush == button.BASE:
        rgb, a = c[..., :3], c[..., 3:4]
    elif brush == "disabled":
        rgb, a = _disabled(c, t), c[..., 3:4] * float(t["disabled"]["alpha"])
    elif brush in button.DERIVED:
        kind, _, part = brush.partition("_")
        rgb = {"base": c[..., :3], "hovered": _hovered(c, t), "pressed": _pressed(c, t)}[part]
        rgb = _selected(rgb, c, t) if kind == "selected" else rgb
        a = c[..., 3:4]
    else:
        raise ThemeError(f"'{brush}' is not a button state ({', '.join(button.BRUSHES)})")
    return np.clip(np.round(np.concatenate([rgb, a], -1)), 0, 255).astype(np.uint8)


def derive(src: pathlib.Path, dst: pathlib.Path, brush: str, theme: dict) -> tuple[list[int], bool]:
    """PNG 한 장 → 상태 그림 PNG. → ([w, h], 알파가 있나)."""
    from PIL import Image
    with Image.open(src) as im:
        out = state(np.asarray(im.convert("RGBA")), brush, theme)
    dst = pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(dst, format="PNG")
    return [int(out.shape[1]), int(out.shape[0])], bool((out[..., 3] < 255).any())
