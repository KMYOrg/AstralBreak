"""색 차이 — sRGB → CIELAB(D65) · CIEDE2000 · 영역 통계 (설계 §8-2 '영역 대표색 ΔE00', 1b 후속 A · C 공용).

A(컨셉에서 따오기)는 '컨셉 자른 것 ↔ 최종 텍스처'에, C(외형 검토 라운드)는 '컨셉 영역 ↔ 렌더 영역'에 같은 함수를 쓴다.
값은 기록만 한다(결정 6 — 게이트로 올리는 것은 Phase 2 보정 뒤).

- `delta_e00` 은 Sharma · Wu · Dalal(2005) 시험 쌍 34개 중 11개로 확인한다(tests/test_color.py — 소수 넷째 자리).
- 얇은 선(금테 1 ~ 3 px)에서 픽셀별 ΔE 는 1 px 어긋남에 크게 흔들린다 [실측 1b 후속 A 채록 — 금선 픽셀별 평균 12 ~ 27].
  그래서 영역 비교의 기본은 **대표색**(영역 안 Lab 중앙값끼리의 ΔE00)이고, 픽셀별 평균 · p95 는 보조 기록이다.
"""
from __future__ import annotations

import numpy as np

_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(rgb) -> np.ndarray:
    """sRGB(0 ~ 255, 마지막 축 3) → Lab. 알파는 받지 않는다(합성은 부르는 쪽이)."""
    c = np.asarray(rgb, dtype=np.float64)[..., :3] / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = (lin @ _M.T) / _WHITE_D65
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e00(lab1, lab2) -> np.ndarray:
    """CIEDE2000 (kL = kC = kH = 1). 브로드캐스트된다."""
    lab1, lab2 = np.asarray(lab1, dtype=np.float64), np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c7 = ((np.hypot(a1, b1) + np.hypot(a2, b2)) / 2) ** 7
    g = 0.5 * (1 - np.sqrt(c7 / (c7 + 25.0 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    prod = c1p * c2p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(prod == 0, 0.0, dh)
    d_l, d_c = L2 - L1, c2p - c1p
    d_h = 2 * np.sqrt(prod) * np.sin(np.radians(dh) / 2)
    l_bar, c_bar = (L1 + L2) / 2, (c1p + c2p) / 2
    hsum, habs = h1p + h2p, np.abs(h1p - h2p)
    h_bar = np.where(habs <= 180, hsum / 2, np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2))
    h_bar = np.where(prod == 0, hsum, h_bar)
    r = np.radians
    t = 1 - 0.17 * np.cos(r(h_bar - 30)) + 0.24 * np.cos(r(2 * h_bar)) + 0.32 * np.cos(r(3 * h_bar + 6)) - 0.20 * np.cos(r(4 * h_bar - 63))
    d_theta = 30 * np.exp(-(((h_bar - 275) / 25) ** 2))
    cb7 = c_bar ** 7
    r_c = 2 * np.sqrt(cb7 / (cb7 + 25.0 ** 7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / np.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar
    s_h = 1 + 0.015 * c_bar * t
    r_t = -np.sin(r(2 * d_theta)) * r_c
    return np.sqrt((d_l / s_l) ** 2 + (d_c / s_c) ** 2 + (d_h / s_h) ** 2 + r_t * (d_c / s_c) * (d_h / s_h))


def representative(rgb, mask) -> list[float] | None:
    """영역 대표색 = 마스크 안 Lab 의 채널별 중앙값. 빈 마스크면 None."""
    mask = np.asarray(mask, bool)
    if not mask.any():
        return None
    return [round(float(v), 3) for v in np.median(srgb_to_lab(np.asarray(rgb)[mask]), axis=0)]


def region_delta_e(rgb_a, rgb_b, mask_a, mask_b=None) -> dict:
    """두 그림의 영역 비교 → {representative, pixel{mean, p95}, n_a, n_b}.

    representative = 대표색(Lab 중앙값)끼리의 ΔE00 — mask_b 가 없으면 같은 마스크.
    pixel = 같은 자리 픽셀끼리의 ΔE00(두 그림이 같은 격자일 때만 — mask_a 자리에서) 평균 · p95.
    """
    mask_a = np.asarray(mask_a, bool)
    mask_b = mask_a if mask_b is None else np.asarray(mask_b, bool)
    out: dict = {"n_a": int(mask_a.sum()), "n_b": int(mask_b.sum()), "representative": None, "pixel": None}
    ra, rb = representative(rgb_a, mask_a), representative(rgb_b, mask_b)
    if ra is not None and rb is not None:
        out["representative"] = round(float(delta_e00(np.array(ra), np.array(rb))), 2)
    a, b = np.asarray(rgb_a), np.asarray(rgb_b)
    if a.shape[:2] == b.shape[:2] and mask_a.any():
        de = delta_e00(srgb_to_lab(a[mask_a]), srgb_to_lab(b[mask_a]))
        out["pixel"] = {"mean": round(float(de.mean()), 2), "p95": round(float(np.percentile(de, 95)), 2)}
    return out
