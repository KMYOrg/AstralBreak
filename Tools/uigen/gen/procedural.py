"""procedural 제공자 — 코드로 그리는 UI 텍스처 (설계 §7 'procedural', 1a 의 유일한 백엔드).

모양 3종(spec 에셋의 procedural.shape):
  rounded_frame   둥근 사각 테두리 + 안쪽 채움(+ 위쪽 안쪽 하이라이트) — 9-slice 프레임
  gradient_panel  위 → 아래 그라데이션 + 둥근 모서리 + 테두리 — 패널 배경
  soft_glow       타원 가장자리로 갈수록 투명해지는 빛 — 강조 효과

색은 sRGB hex, 출력은 직선 알파(미리 곱하지 않음) RGBA8. 완전 투명 픽셀도 RGB 를 테두리 · 빛 색으로 채워 쌍선형 필터의 어두운 테두리를 막는다.
같은 입력 → 같은 바이트(결정적). 안티앨리어싱은 둥근 사각 거리장(픽셀 중심 기준 0.5 px 폭).
"""
from __future__ import annotations

import math

from core.spec import parse_color


class ProceduralError(ValueError):
    pass


def _rgba(hex_color: str | None, default: str = "#00000000") -> tuple[float, float, float, float]:
    r, g, b, a = parse_color(hex_color or default)
    return float(r), float(g), float(b), a / 255.0


def _sd_round_rect(px: float, py: float, cx: float, cy: float, hx: float, hy: float, r: float) -> float:
    """둥근 사각 경계까지의 부호 거리(안 = 음수)."""
    qx = abs(px - cx) - (hx - r)
    qy = abs(py - cy) - (hy - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _smoothstep(e0: float, e1: float, x: float) -> float:
    t = _clamp01((x - e0) / (e1 - e0)) if e1 != e0 else (1.0 if x >= e1 else 0.0)
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _store(buf: bytearray, i: int, r: float, g: float, b: float, a: float) -> None:
    buf[i] = int(round(_clamp01(r / 255.0) * 255))
    buf[i + 1] = int(round(_clamp01(g / 255.0) * 255))
    buf[i + 2] = int(round(_clamp01(b / 255.0) * 255))
    buf[i + 3] = int(round(_clamp01(a) * 255))


def _framed(w: int, h: int, p: dict, fill_at) -> bytearray:
    """둥근 사각 + 테두리 — fill_at(y) 가 그 줄의 안쪽 채움색을 준다."""
    radius = float(p.get("radius", 0))
    border = float(p.get("border_px", 0))
    bc = _rgba(p.get("border_color"), "#FFFFFFFF")
    hl = _rgba(p.get("highlight_color")) if p.get("highlight_color") else None
    cx, cy, hx, hy = w / 2.0, h / 2.0, w / 2.0, h / 2.0
    r = min(radius, hx, hy)
    buf = bytearray(w * h * 4)
    for y in range(h):
        py = y + 0.5
        fc = fill_at(py / h)
        top = _clamp01(1.0 - py / (h / 2.0))
        for x in range(w):
            px = x + 0.5
            d = _sd_round_rect(px, py, cx, cy, hx, hy, r)
            outer = _clamp01(0.5 - d)
            inner_d = d + border
            inner = _clamp01(0.5 - inner_d) if border > 0 else 1.0
            cr, cg, cb = _lerp(bc[0], fc[0], inner), _lerp(bc[1], fc[1], inner), _lerp(bc[2], fc[2], inner)
            ca = _lerp(bc[3], fc[3], inner) * outer
            if hl and -2.0 <= inner_d <= 0.0 and top > 0.0:
                k = hl[3] * top * _clamp01(1.0 + inner_d / 2.0)
                cr, cg, cb = _lerp(cr, hl[0], k), _lerp(cg, hl[1], k), _lerp(cb, hl[2], k)
            if ca <= 0.0:
                cr, cg, cb = bc[0], bc[1], bc[2]
            _store(buf, (y * w + x) * 4, cr, cg, cb, ca)
    return buf


def _rounded_frame(w: int, h: int, p: dict) -> bytearray:
    fc = _rgba(p.get("fill_color"))
    return _framed(w, h, p, lambda _t: fc)


def _gradient_panel(w: int, h: int, p: dict) -> bytearray:
    top, bottom = _rgba(p.get("top_color"), "#202020FF"), _rgba(p.get("bottom_color"), "#101010FF")
    return _framed(w, h, p, lambda t: tuple(_lerp(a, b, t) for a, b in zip(top, bottom)))


def _soft_glow(w: int, h: int, p: dict) -> bytearray:
    c = _rgba(p.get("color"), "#FFFFFFFF")
    falloff = float(p.get("falloff", 0.5))
    cx, cy = w / 2.0, h / 2.0
    buf = bytearray(w * h * 4)
    for y in range(h):
        ny = (y + 0.5 - cy) / cy
        for x in range(w):
            nx = (x + 0.5 - cx) / cx
            dist = math.hypot(nx, ny)
            a = c[3] * (1.0 - _smoothstep(falloff, 1.0, dist))
            _store(buf, (y * w + x) * 4, c[0], c[1], c[2], a)
    return buf


SHAPES = {"rounded_frame": _rounded_frame, "gradient_panel": _gradient_panel, "soft_glow": _soft_glow}


def render(asset: dict) -> tuple[int, int, bytes]:
    """spec 에셋 → (w, h, RGBA 바이트)."""
    p = asset.get("procedural") or {}
    shape = p.get("shape")
    if shape not in SHAPES:
        raise ProceduralError(f"asset '{asset.get('asset_id')}': unknown procedural shape '{shape}' (known: {sorted(SHAPES)})")
    w, h = (int(v) for v in asset["size"])
    return w, h, bytes(SHAPES[shape](w, h, p))


def nine_slice_margin(asset: dict) -> list[float] | None:
    """모서리 영역(radius + 테두리 + 1 px)을 비율로 — 테두리가 있는 모양만."""
    p = asset.get("procedural") or {}
    if p.get("shape") not in ("rounded_frame", "gradient_panel"):
        return None
    w, h = (int(v) for v in asset["size"])
    corner = float(p.get("radius", 0)) + float(p.get("border_px", 0)) + 1.0
    mx, my = round(min(corner / w, 0.49), 3), round(min(corner / h, 0.49), 3)
    return [mx, my, mx, my]
