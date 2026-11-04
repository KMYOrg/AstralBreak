"""APNG — 같은 크기 PNG 프레임들을 다시 압축하지 않고 움직이는 PNG 한 장으로 잇는다 (지침서 §14 Phase 8 '8-2'). 표준 라이브러리만.

capture_animation(C++)이 쓴 연속 프레임(뷰를 나란히 한 장씩)을 받는다. 각 프레임 PNG 의 IDAT(필터 바이트를 품은 zlib 스트림)는 그대로
APNG 프레임 데이터가 될 수 있다 — 첫 프레임은 IDAT, 나머지는 fdAT(순번 + 같은 데이터). 그래서 픽셀을 풀지 않는다(numpy · Pillow ·
ffmpeg 설치 없음). 모든 프레임의 IHDR(크기 · 비트 깊이 · 색 형식 · 인터레이스)이 같아야 한다. 브라우저(Chromium · Firefox · Safari)는
APNG 를 움직이는 그림으로, 나머지 뷰어는 첫 프레임 정지 그림으로 보여 준다.
"""
from __future__ import annotations

import pathlib
import struct
import zlib
from fractions import Fraction

SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 첫 프레임에서 옮기는 보조 청크(색 공간 · 해상도) — 그 밖(tEXt · tIME …)은 버린다
_KEEP_BEFORE_IDAT = {b"sRGB", b"gAMA", b"cHRM", b"iCCP", b"pHYs", b"sBIT"}


class ApngError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """PNG 바이트 → [(형식, 본문)] — 서명 · CRC 를 검사하고 IEND 에서 멈춘다."""
    if not data.startswith(SIGNATURE):
        raise ApngError("NOT_PNG", "missing PNG signature")
    chunks = []
    pos = len(SIGNATURE)
    while pos + 12 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if len(body) != length or zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ApngError("BAD_CHUNK", f"chunk {kind!r} at {pos} is truncated or fails its CRC")
        chunks.append((kind, body))
        pos += 12 + length
        if kind == b"IEND":
            return chunks
    raise ApngError("NO_IEND", "PNG ends without IEND")


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def delay(fps: float) -> tuple[int, int]:
    """프레임 시간 = num / den 초 (fcTL 은 16비트) — 15 fps → (1, 15)."""
    frac = Fraction(1.0 / fps).limit_denominator(1000)
    return frac.numerator, frac.denominator


def assemble(frames: list[str | pathlib.Path], out: str | pathlib.Path, fps: float, plays: int = 0) -> dict:
    """frames(같은 IHDR 의 PNG 들, 시간 순) → out(APNG). plays 0 = 무한 반복. → {path, frames, fps, delay, size, bytes}."""
    if not frames:
        raise ApngError("NO_FRAMES", "no frames to assemble")
    if not 0 < fps <= 120:
        raise ApngError("BAD_FPS", f"fps {fps} out of (0, 120]")
    parsed = []
    for path in frames:
        chunks = read_chunks(pathlib.Path(path).read_bytes())
        if chunks[0][0] != b"IHDR":
            raise ApngError("NO_IHDR", f"{path}: first chunk is not IHDR")
        if any(kind in (b"acTL", b"fcTL", b"fdAT") for kind, _ in chunks):
            raise ApngError("ALREADY_ANIMATED", f"{path} is already an APNG")
        parsed.append(chunks)
    ihdr = parsed[0][0][1]
    for path, chunks in zip(frames, parsed):
        if chunks[0][1] != ihdr:
            raise ApngError("FRAME_MISMATCH", f"{path}: IHDR differs from the first frame (size / depth / colour type must match)")
    width, height = struct.unpack(">II", ihdr[:8])
    num, den = delay(fps)
    body = bytearray(SIGNATURE)
    body += chunk(b"IHDR", ihdr)
    body += chunk(b"acTL", struct.pack(">II", len(parsed), plays))
    for kind, data in parsed[0]:
        if kind == b"IDAT":
            break
        if kind in _KEEP_BEFORE_IDAT:
            body += chunk(kind, data)
    seq = 0
    for index, chunks in enumerate(parsed):
        # dispose NONE · blend SOURCE — 프레임마다 전체를 덮는다
        body += chunk(b"fcTL", struct.pack(">IIIIIHHBB", seq, width, height, 0, 0, num, den, 0, 0))
        seq += 1
        for kind, data in chunks:
            if kind != b"IDAT":
                continue
            if index == 0:
                body += chunk(b"IDAT", data)
            else:
                body += chunk(b"fdAT", struct.pack(">I", seq) + data)
                seq += 1
    body += chunk(b"IEND", b"")
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(body))
    return {"path": out.as_posix(), "frames": len(parsed), "fps": fps, "delay": [num, den], "size": [width, height], "bytes": len(body)}


def inspect(path: str | pathlib.Path) -> dict:
    """APNG 구조 요약 — {frames, plays, size, sequence_ok, idat, fdat} (검사 · 테스트용)."""
    chunks = read_chunks(pathlib.Path(path).read_bytes())
    actl = next((d for k, d in chunks if k == b"acTL"), None)
    seqs = [struct.unpack(">I", d[:4])[0] for k, d in chunks if k in (b"fcTL", b"fdAT")]
    width, height = struct.unpack(">II", chunks[0][1][:8])
    return {"frames": struct.unpack(">I", actl[:4])[0] if actl else 1, "plays": struct.unpack(">I", actl[4:8])[0] if actl else None,
            "size": [width, height], "sequence_ok": seqs == list(range(len(seqs))),
            "fctl": sum(1 for k, _ in chunks if k == b"fcTL"), "idat": sum(1 for k, _ in chunks if k == b"IDAT"),
            "fdat": sum(1 for k, _ in chunks if k == b"fdAT")}
