from __future__ import annotations

import hashlib
import struct
import zlib

import pytest
from conftest import fixture_spec

from core import png
from gen import procedural
from gen.router import RouteError, choose_backend

ROUTING = {"kinds": {"icon": {"primary": "codex", "fallback": []}, "panel_bg": {"primary": "procedural", "fallback": ["codex"]},
                     "frame": {"primary": "codex", "fallback": ["procedural"]}}}


def px(w, data, x, y):
    i = (y * w + x) * 4
    return tuple(data[i:i + 4])


def _encode_with_filters(w, h, rgba):
    """행마다 필터 0~4 를 돌려 가며 쓴 PNG — 디코더의 필터 복원 시험용."""
    stride, raw, prev = w * 4, bytearray(), bytearray(w * 4)
    for y in range(h):
        line = rgba[y * stride:(y + 1) * stride]
        f = y % 5
        enc = bytearray(stride)
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            pred = [0, a, b, (a + b) >> 1, png._paeth(a, b, c)][f]
            enc[x] = (line[x] - pred) & 0xFF
        raw += bytes([f]) + enc
        prev = bytearray(line)

    def chunk(k, body):
        return struct.pack(">I", len(body)) + k + body + struct.pack(">I", zlib.crc32(k + body) & 0xFFFFFFFF)
    return png.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def test_png_roundtrip_and_filters(tmp_path):
    w, h = 7, 11
    data = bytes((i * 37 + 11) % 256 for i in range(w * h * 4))
    p = png.write_rgba(tmp_path / "a.png", w, h, data)
    assert png.read_rgba(p) == (w, h, data)
    assert png.decode(_encode_with_filters(w, h, data)) == (w, h, data)


def test_png_rejects_garbage():
    with pytest.raises(png.PngError):
        png.decode(b"not a png")


def _asset(aid):
    return next(a for a in fixture_spec()["assets"] if a["asset_id"] == aid)


def test_rounded_frame_shape():
    a = _asset("ult_frame")
    w, h, data = procedural.render(a)
    assert (w, h) == (200, 50) and len(data) == w * h * 4
    assert px(w, data, 0, 0)[3] == 0                       # 둥근 모서리 밖 = 투명
    assert px(w, data, 0, 0)[:3] == (0xE8, 0xB5, 0x4A)      # 투명 픽셀도 테두리 색(어두운 테두리 방지)
    assert px(w, data, 100, 1)[:3] == (0xE8, 0xB5, 0x4A) and px(w, data, 100, 1)[3] == 255   # 위 테두리
    assert px(w, data, 100, 40) == (0x1A, 0x14, 0x0C, 0xD9)  # 아래쪽 안 = 채움(하이라이트는 위쪽만)


def test_gradient_panel_shape():
    a = _asset("chain_panel_bg")
    w, h, data = procedural.render(a)
    top, bottom = px(w, data, 160, 10), px(w, data, 160, 150)
    assert top[0] > bottom[0] and top[2] > bottom[2]       # 위가 밝은 쪽(2A2233 → 140F1A)
    assert px(w, data, 0, 0)[3] == 0 and px(w, data, 319, 159)[3] == 0


def test_soft_glow_shape():
    a = _asset("ult_glow")
    w, h, data = procedural.render(a)
    assert px(w, data, 128, 16)[3] == 255                  # 가운데 = 빛 색 그대로
    assert px(w, data, 0, 0)[3] == 0                       # 모서리 = 투명
    assert px(w, data, 0, 0)[:3] == (0xFF, 0xD2, 0x7A)


def test_render_is_deterministic():
    a = _asset("ult_frame")
    assert hashlib.sha256(procedural.render(a)[2]).digest() == hashlib.sha256(procedural.render(a)[2]).digest()


def test_nine_slice_margin_matches_fixture():
    for aid in ("ult_frame", "chain_panel_bg"):
        a = _asset(aid)
        assert procedural.nine_slice_margin(a) == a["margin"], aid
    assert procedural.nine_slice_margin(_asset("ult_glow")) is None


def test_unknown_shape():
    with pytest.raises(procedural.ProceduralError):
        procedural.render({"asset_id": "x", "size": [8, 8], "procedural": {"shape": "star"}})


def test_router():
    allowed = ["procedural"]
    assert choose_backend({"asset_id": "a", "kind": "frame", "provenance": "procedural"}, ROUTING, allowed) == "procedural"
    with pytest.raises(RouteError) as e:
        choose_backend({"asset_id": "a", "kind": "frame", "provenance": "codex"}, ROUTING, allowed)
    assert e.value.code == "BACKEND_NOT_ALLOWED"
    assert choose_backend({"asset_id": "a", "kind": "panel_bg"}, ROUTING, allowed) == "procedural"
    assert choose_backend({"asset_id": "a", "kind": "frame"}, ROUTING, allowed) == "procedural"   # primary codex 허용 밖 → fallback
    with pytest.raises(RouteError) as e:
        choose_backend({"asset_id": "a", "kind": "icon"}, ROUTING, allowed)
    assert e.value.code == "NO_ALLOWED_BACKEND"
