"""PNG 읽기 · 쓰기 — 표준 라이브러리만(zlib). 8비트 RGBA · RGB · 회색(+알파), 인터레이스 없음.

procedural 에셋 쓰기 · refine 검사 · 렌더 결과 읽기에 쓴다. Pillow 없이 돌게 하는 것이 목적이라 범위를 좁게 둔다.
"""
from __future__ import annotations

import pathlib
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}   # 색 형식 → 채널 수 (3 = 팔레트는 받지 않는다)


class PngError(ValueError):
    pass


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode_rgba(width: int, height: int, rgba: bytes | bytearray) -> bytes:
    if len(rgba) != width * height * 4:
        raise PngError(f"expected {width * height * 4} bytes, got {len(rgba)}")
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)   # 필터 없음 — 결정적 출력(같은 픽셀 → 같은 바이트 · 같은 sha256)
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b"")


def write_rgba(path: str | pathlib.Path, width: int, height: int, rgba: bytes | bytearray) -> pathlib.Path:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_rgba(width, height, rgba))
    return path


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(data: bytes) -> tuple[int, int, bytes]:
    """→ (width, height, RGBA 바이트)."""
    if not data.startswith(SIGNATURE):
        raise PngError("not a PNG")
    pos, width, height, ctype, idat = 8, 0, 0, None, bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in _CHANNELS or interlace:
                raise PngError(f"unsupported PNG (depth {depth}, color type {ctype}, interlace {interlace})")
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if ctype is None:
        raise PngError("no IHDR")
    ch = _CHANNELS[ctype]
    stride = width * ch
    raw = zlib.decompress(bytes(idat))
    out = bytearray(height * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        ftype = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ftype == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 0xFF
        elif ftype == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif ftype == 3:
            for x in range(stride):
                left = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif ftype == 4:
            for x in range(stride):
                left = line[x - ch] if x >= ch else 0
                upleft = prev[x - ch] if x >= ch else 0
                line[x] = (line[x] + _paeth(left, prev[x], upleft)) & 0xFF
        elif ftype != 0:
            raise PngError(f"bad filter {ftype} on row {y}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    if ch == 4:
        return width, height, bytes(out)
    rgba = bytearray(width * height * 4)
    for i in range(width * height):
        px = out[i * ch:(i + 1) * ch]
        if ch == 3:
            rgba[i * 4:i * 4 + 4] = bytes((px[0], px[1], px[2], 255))
        elif ch == 2:
            rgba[i * 4:i * 4 + 4] = bytes((px[0], px[0], px[0], px[1]))
        else:
            rgba[i * 4:i * 4 + 4] = bytes((px[0], px[0], px[0], 255))
    return width, height, bytes(rgba)


def read_rgba(path: str | pathlib.Path) -> tuple[int, int, bytes]:
    return decode(pathlib.Path(path).read_bytes())
