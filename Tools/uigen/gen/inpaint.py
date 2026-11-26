"""외부 인페인팅 — LaMa ONNX (1b 후속 L 다음 G2 (가)).

모델 = Hugging Face `Carve/LaMa-ONNX` 의 `lama_fp32.onnx`(big-lama 를 옮긴 것, Apache-2.0, 입력 512 × 512 고정 · opset 17) — 경로는
`pipeline.yaml extract.lama_model`(Tools/uigen 기준, 기본 work/_models/ — git 무시). 실행 중 내려받지 않는다: 파일이 없거나 추론이 실패하면 None(부르는 쪽이
글자 없는 판으로 물러나 기록). 추론 = 이미 깔린 onnxruntime CPU 실행기(같은 입력 → 같은 출력) — 창 · 마스크 해시로 캐시(work/_lama_cache/, git 무시).

  patch(full_rgb, x0, y0, mask_win) → mask_win(창 좌표 — full 의 (x0, y0) 부터) 자리의 인페인팅 색(창 크기 HxWx3 float) 또는 None
"""
from __future__ import annotations

import hashlib
import pathlib

import numpy as np

SIZE = 512
UIGEN = pathlib.Path(__file__).resolve().parent.parent
CACHE = UIGEN / "work" / "_lama_cache"
_STATE: dict = {"path": None, "session": None, "error": None, "io": None}
CACHE_VERSION = b"lama-v3-mirrored-mask"     # 입력 · 전처리를 바꾸면 올린다(옛 캐시를 안 쓰게) — v3: 거울 채움에 마스크도 거울(글자 사본 안 비침)


def configure(path) -> None:
    """모델 경로(절대 또는 Tools/uigen 기준) — 바뀌면 세션을 다시 연다."""
    p = pathlib.Path(path) if path else None
    if p is not None and not p.is_absolute():
        p = UIGEN / p
    if p != _STATE["path"]:
        _STATE.update(path=p, session=None, error=None, io=None)


def _session():
    if _STATE["session"] is not None:
        return _STATE["session"]
    p = _STATE["path"]
    if p is None or not p.is_file():
        _STATE["error"] = f"model file missing: {p}"
        return None
    try:
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.log_severity_level = 3
        sess = ort.InferenceSession(str(p), sess_options=so, providers=["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001 — 기록하고 None
        _STATE["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return None
    ins = sess.get_inputs()
    img = next((i.name for i in ins if "image" in i.name.lower()), ins[0].name)
    msk = next((i.name for i in ins if "mask" in i.name.lower()), ins[1].name if len(ins) > 1 else None)
    _STATE.update(session=sess, io={"image": img, "mask": msk, "output": sess.get_outputs()[0].name})
    return sess


def status() -> dict:
    return {"path": str(_STATE["path"]) if _STATE["path"] else None, "loaded": _STATE["session"] is not None, "error": _STATE["error"], "io": _STATE["io"]}


def run512(rgb, mask) -> np.ndarray | None:
    """512 × 512 RGB(0 ~ 255) · 마스크(True = 메울 자리) → 인페인팅 RGB(0 ~ 255 float) 또는 None. 마스크 밖은 입력 그대로 돌려준다."""
    sess = _session()
    if sess is None:
        return None
    rgb = np.ascontiguousarray(np.clip(np.asarray(rgb, np.float32), 0, 255))
    m = np.asarray(mask, bool)
    key = hashlib.sha1(CACHE_VERSION + rgb.round().astype(np.uint8).tobytes() + np.packbits(m).tobytes()
                       + str(_STATE["path"].stat().st_size).encode()).hexdigest()
    cp = CACHE / f"{key}.npy"
    if cp.is_file():
        try:
            return np.load(cp)
        except (OSError, ValueError):
            pass
    io = _STATE["io"]
    # 메울 자리는 입력에서 지운다(원본 LaMa 의 image × (1 − mask)) — 안 지우면 이 ONNX 판은 마스크 안 글자를 다시 그렸다 [실측 R20261119_144231 체인 패널]
    x = ((rgb / 255.0) * (~m)[..., None]).transpose(2, 0, 1)[None].astype(np.float32)
    feeds = {io["image"]: x}
    if io["mask"]:
        feeds[io["mask"]] = m[None, None].astype(np.float32)
    out = np.asarray(sess.run([io["output"]], feeds)[0], np.float32)[0]
    if out.shape[0] == 3:
        out = out.transpose(1, 2, 0)
    if float(out.max()) <= 1.5:
        out = out * 255.0
    out = np.clip(out, 0, 255)
    out = np.where(m[..., None], out, rgb)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(cp, out.astype(np.float32))
    except OSError:
        pass
    return out


def patch(full_rgb, x0: int, y0: int, mask_win) -> np.ndarray | None:
    """full_rgb(텍스처 전체 HxWx3) 위 창(x0, y0 부터 mask_win 크기)의 마스크 자리 인페인팅 → 창 크기 RGB 또는 None.
    512 × 512 창 = 마스크 상자 가운데(텍스처 안으로 밀어 넣음 · 텍스처가 작으면 가장자리 거울 채움). 마스크 상자가 512 를 넘으면 None."""
    full = np.asarray(full_rgb, np.float32)
    H, W = full.shape[:2]
    mw = np.asarray(mask_win, bool)
    if not mw.any():
        return None
    h, w = mw.shape
    ys, xs = np.nonzero(mw)
    gy0, gy1, gx0, gx1 = y0 + int(ys.min()), y0 + int(ys.max()) + 1, x0 + int(xs.min()), x0 + int(xs.max()) + 1
    if gy1 - gy0 > SIZE or gx1 - gx0 > SIZE:
        _STATE["error"] = f"mask box {gx1 - gx0}×{gy1 - gy0} exceeds {SIZE}"
        return None
    pad_y, pad_x = max(0, SIZE - H), max(0, SIZE - W)
    # 1b 후속 L 다음 — 글자 지우기 마감: 거울 채움 전에 마스크를 텍스처 전체 좌표로 놓고 마스크도 같이 거울 — 마스크 안 지운 그림만 거울에 비치게.
    # 그림만 거울로 늘리면 거울에 비친 글자 사본(마스크 밖)을 LaMa 가 그대로 베껴 지운 자리에 글자를 다시 그렸다 [실측 오프라인 R20261119_190059 배너(높이 124) — '3' 이
    # 흰 글자로 다시 그려짐 · S4 76.6]
    mfull = np.zeros((H, W), bool)
    fy0, fx0 = max(0, y0), max(0, x0)
    fy1, fx1 = min(H, y0 + h), min(W, x0 + w)
    if fy1 > fy0 and fx1 > fx0:
        mfull[fy0:fy1, fx0:fx1] = mw[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    pads = ((pad_y // 2, pad_y - pad_y // 2), (pad_x // 2, pad_x - pad_x // 2))
    if pad_y or pad_x:
        big = np.pad(full * (~mfull)[..., None], pads + ((0, 0),), mode="reflect")
        bigm = np.pad(mfull, pads, mode="reflect")
    else:
        big, bigm = full, mfull
    oy, ox = pad_y // 2, pad_x // 2
    BH, BW = big.shape[:2]
    cy, cx = (gy0 + gy1) // 2 + oy, (gx0 + gx1) // 2 + ox
    wy0 = int(min(max(0, cy - SIZE // 2), BH - SIZE))
    wx0 = int(min(max(0, cx - SIZE // 2), BW - SIZE))
    m512 = bigm[wy0:wy0 + SIZE, wx0:wx0 + SIZE].copy()
    ty0, tx0 = y0 + oy - wy0, x0 + ox - wx0
    sy0, sx0 = max(0, -ty0), max(0, -tx0)
    sy1, sx1 = min(h, SIZE - ty0), min(w, SIZE - tx0)
    res = run512(big[wy0:wy0 + SIZE, wx0:wx0 + SIZE], m512)
    if res is None:
        return None
    out = np.zeros((h, w, 3), np.float32)
    out[sy0:sy1, sx0:sx1] = res[ty0 + sy0:ty0 + sy1, tx0 + sx0:tx0 + sx1]
    return out
