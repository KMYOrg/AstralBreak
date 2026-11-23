"""원형 진행(고리) — 컨셉 알파에서 고리 원 · 안쪽 모서리를 재고 픽셀을 나누고, 각도로 닦는 식을 정한다 (전투 HUD 동작, 11-23 — 설계 §11 '전투 HUD 동작 설계').

progress 바인딩인 Image(고리)는 자기 텍스처를 각도로 닦아 남은 비율을 보인다(엔진 = WidgetMcp M_RadialWipe, 오프라인 합성 = 여기 wipe_factor — 같은 식).
고리와 같은 자리에 다른 그림(고리 안 띠)이 붙어 있어도 픽셀마다 주인이 하나다(ring_mask 안 = 고리 텍스처, 밖 = 다른 텍스처) — 1:1 로 그리므로 가득 찬
상태의 합성은 나누기 전과 같은 그림이다.

  재는 법 — 바깥 윤곽(상자 줄 · 열마다 알파 > 0.5 의 바깥 끝)에 최소제곱 원, 1° 마다 바깥에서 안으로 처음 끊기는 반지름 = 안쪽 모서리.
  다른 그림이 닿은 각도는 끊기지 않고 안쪽으로 번진다(언제나 더 작은 쪽으로만 틀린다) → 거울 자리 넷(θ · −θ · 180° ± θ)의 두 번째로 큰 값.
  못 재면 RadialError — 조용히 물러나지 않는다.

각도는 12시 = 0, 시계 방향 +. 남은 비율 p 의 닦기: clockwise = 12시에서 시계 방향으로 (1 − p) 바퀴를 지움, mirror = 12시에서 좌우로 같이 (1 − p) 반 바퀴씩 지움.
"""
from __future__ import annotations

import numpy as np

MODES = ("clockwise", "mirror")
EDGE_ALPHA = 0.5             # 바깥 윤곽 점 — 알파가 이보다 큰 바깥 끝
IN_ALPHA = 0.08              # 안쪽 모서리 — 바깥에서 안으로 알파가 처음 이 아래로 떨어지는 곳 [실측 — 고리 안 빈 자리의 잔 알파 ≤ 0.04]
RESID_P95 = 2.0              # 원 잔차 p95 상한(px) [실측 승격본 1.14]
MIN_FOUND = 0.8              # 안쪽 모서리를 거울 자리 없이 찾은 각도 비율 하한은 아니고, 고친 뒤 고리 두께가 말이 되는 각도 비율
MAX_THICK = 0.25             # 두께 ≤ 바깥 반지름 × 이것 — 넘으면 그 각도는 번진 것
MARGIN_IN = 2.0              # 마스크는 안쪽 모서리에서 이만큼(px) 더 안으로(옅은 가장자리까지 고리 몫)
MARGIN_IN_TOUCHED = 0.5      # 다른 그림(띠)이 닿은 각도는 이만큼만 — 그 그림 조각을 고리가 가져가지 않게
MARGIN_OUT = 3.0             # 바깥 반지름에서 이만큼(px) 밖까지 고리 몫(어두운 테 · 안티앨리어싱)
BOX_PAD = 0                  # 고리 위젯 상자 = 바깥 반지름 + MARGIN_OUT 을 품는 정수 상자(+ 이만큼)
SEARCH_PAD = 12              # analyze 가 준 상자를 이만큼 넓혀 윤곽을 찾는다
GHOST_ALPHA = 0.15           # 깨끗한 각도에서 마스크 바로 안(4 px)에 남은 알파 상한 — 넘으면 안쪽 모서리를 잘못 잰 것(닦인 자리에 잔상)
GHOST_PX = 4


class RadialError(ValueError):
    pass


def angles(shape, center) -> tuple[np.ndarray, np.ndarray]:
    """→ (픽셀 중심까지 반지름 px, 12시 = 0 · 시계 방향 각도 rad [−π, π])."""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]] + 0.5
    dx, dy = xx - float(center[0]), yy - float(center[1])
    return np.hypot(dx, dy), np.arctan2(dx, -dy)


def wipe_factor(shape, center, percent: float, mode: str = "clockwise", track_alpha: float = 0.0) -> np.ndarray:
    """남은 비율 → 불투명도 배수(0 ~ 1). 끝은 부호 거리(px) ± 0.5 로 부드럽게 — M_RadialWipe 의 식과 같다."""
    if mode not in MODES:
        raise RadialError(f"mode {mode!r} — one of {MODES}")
    p = float(np.clip(percent, 0.0, 1.0))
    if p >= 1.0:
        return np.ones(shape, float)
    if p <= 0.0:
        return np.full(shape, float(track_alpha))
    rr, a = angles(shape, center)
    if mode == "clockwise":
        turn = 2.0 * np.pi
        t = np.mod(a, turn)                       # 12시에서 시계 방향 [0, 2π)
        gone = (1.0 - p) * turn
        # 남은 호 = [gone, 2π) — 움직이는 끝(gone)과 12시(2π) 양쪽 끝에서의 부호 거리
        d = np.minimum(t - gone, turn - t)
        d = np.where(t < gone, np.maximum(t - gone, -t), d)
    else:
        t = np.abs(a)                             # 12시에서 좌우로 [0, π]
        d = t - (1.0 - p) * np.pi
    k = np.clip(d * rr + 0.5, 0.0, 1.0)
    return float(track_alpha) + (1.0 - float(track_alpha)) * k


def edge_band(shape, center, percent: float, mode: str, px: float) -> np.ndarray:
    """닦는 끝에서 px 안(호 길이) — 진단이 안티앨리어싱 자리를 뺀다."""
    rr, a = angles(shape, center)
    p = float(np.clip(percent, 0.0, 1.0))
    if mode == "clockwise":
        turn = 2.0 * np.pi
        t = np.mod(a, turn)
        d = np.minimum(np.abs(t - (1.0 - p) * turn), np.minimum(t, turn - t))
    else:
        d = np.abs(np.abs(a) - (1.0 - p) * np.pi)
    return d * rr <= px


def kept_side(shape, center, percent: float, mode: str) -> np.ndarray:
    """남아야 할 쪽(안티앨리어싱 없이)."""
    rr, a = angles(shape, center)
    p = float(np.clip(percent, 0.0, 1.0))
    if mode == "clockwise":
        return np.mod(a, 2.0 * np.pi) >= (1.0 - p) * 2.0 * np.pi
    return np.abs(a) >= (1.0 - p) * np.pi


def _fit_circle(pts: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    P = np.asarray(pts, float)
    cx = cy = r = 0.0
    for _ in range(8):
        M = np.c_[2 * P, np.ones(len(P))]
        sol = np.linalg.lstsq(M, (P ** 2).sum(1), rcond=None)[0]
        cx, cy = float(sol[0]), float(sol[1])
        r = float(np.sqrt(max(1e-6, sol[2] + cx * cx + cy * cy)))
        d = np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r)
        keep = d < max(3.0, 2.5 * float(np.median(d)))
        if keep.all():
            break
        P = P[keep]
        if len(P) < 24:
            break
    return cx, cy, r, P


def measure(alpha: np.ndarray, box) -> dict:
    """alpha(캔버스 0 ~ 1) · box(analyze 가 준 고리 상자 [x, y, w, h]) → {"center"(캔버스 px), "radius", "r_in"(360 개), "box"(정수 [x, y, w, h]),
    "mask"(캔버스 bool), "record"}. 못 재면 RadialError."""
    H, W = alpha.shape
    x, y, bw, bh = (float(v) for v in box)
    x0, y0 = max(0, int(np.floor(x)) - SEARCH_PAD), max(0, int(np.floor(y)) - SEARCH_PAD)
    x1, y1 = min(W, int(np.ceil(x + bw)) + SEARCH_PAD), min(H, int(np.ceil(y + bh)) + SEARCH_PAD)
    a = alpha[y0:y1, x0:x1]
    if min(a.shape) < 32:
        raise RadialError(f"box {list(box)} is too small for a ring")
    on = a > EDGE_ALPHA
    pts = []
    for yy in range(a.shape[0]):
        s = np.nonzero(on[yy])[0]
        if len(s):
            pts += [(s[0], yy + 0.5), (s[-1] + 1, yy + 0.5)]
    for xx in range(a.shape[1]):
        s = np.nonzero(on[:, xx])[0]
        if len(s):
            pts += [(xx + 0.5, s[0]), (xx + 0.5, s[-1] + 1)]
    if len(pts) < 200:
        raise RadialError(f"only {len(pts)} outline points inside {list(box)}")
    cx, cy, r, used = _fit_circle(np.array(pts))
    resid = np.abs(np.hypot(used[:, 0] - cx, used[:, 1] - cy) - r)
    p95 = float(np.percentile(resid, 95))
    cover = len(used) / len(pts)
    if p95 > RESID_P95 or cover < 0.7:
        raise RadialError(f"the outline is not a circle (residual p95 {p95:.2f} px, {cover:.0%} of the outline on the circle)")
    if not (0.35 * max(bw, bh) <= r <= 0.75 * max(bw, bh)):
        raise RadialError(f"circle radius {r:.1f} does not match the box {list(box)}")
    # 각도마다 안쪽 모서리 — 0.5 px 걸음 이중선형
    import cv2
    th = np.radians(np.arange(360))
    rs = np.arange(r - 1.0, r * (1.0 - MAX_THICK) - 1.0, -0.5)
    mx = (cx + np.sin(th)[:, None] * rs[None] - 0.5).astype(np.float32)
    my = (cy - np.cos(th)[:, None] * rs[None] - 0.5).astype(np.float32)
    prof = cv2.remap(a.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    raw = np.empty(360)
    for d in range(360):
        low = np.nonzero(prof[d] < IN_ALPHA)[0]
        raw[d] = rs[low[0]] if len(low) else rs[-1]
    raw = np.where(prof[:, 0] < IN_ALPHA, r, raw)          # 칼날 끝이 만나는 틈 — 두께 0
    idx = np.arange(360)
    mir = np.stack([raw[idx], raw[(-idx) % 360], raw[(180 - idx) % 360], raw[(180 + idx) % 360]])
    fixed = np.sort(mir, axis=0)[-2]
    dirty = raw < fixed - 2.0                              # 거울 자리보다 안쪽 — 다른 그림이 닿은 각도
    ok = float((fixed > r * (1.0 - MAX_THICK) + 1.0).mean())
    if ok < MIN_FOUND:
        raise RadialError(f"the inner edge is not found at {1 - ok:.0%} of the angles (another drawing touches the ring all around?)")
    rr, ang = angles(a.shape, (cx, cy))
    deg = np.mod(np.degrees(ang), 360.0)
    d0 = np.floor(deg).astype(int) % 360
    f = deg - np.floor(deg)
    rin = fixed[d0] * (1 - f) + fixed[(d0 + 1) % 360] * f
    mg = np.where(dirty, MARGIN_IN_TOUCHED, MARGIN_IN)
    margin = np.minimum(mg[d0], mg[(d0 + 1) % 360])
    m = (rr >= rin - margin) & (rr <= r + MARGIN_OUT)
    ghost = (~m) & (rr >= rin - MARGIN_IN - GHOST_PX) & (rr < rin) & ~(dirty[d0] | dirty[(d0 + 1) % 360])
    for k in range(1, 4):                                  # 닿은 각도 둘레 3° 는 깨끗하다고 안 본다
        ghost &= ~(dirty[(d0 + k) % 360] | dirty[(d0 - k) % 360])
    gmax = float(a[ghost].max()) if ghost.any() else 0.0
    if gmax > GHOST_ALPHA:
        raise RadialError(f"alpha {gmax:.2f} stays just inside the ring at clean angles — the inner edge is wrong (a wiped ring would leave a ghost)")
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = m
    ccx, ccy = cx + x0, cy + y0
    ring = r + MARGIN_OUT + BOX_PAD
    bx0, by0 = max(0, int(np.floor(ccx - ring))), max(0, int(np.floor(ccy - ring)))
    bx1, by1 = min(W, int(np.ceil(ccx + ring))), min(H, int(np.ceil(ccy + ring)))
    rec = {"center": [round(ccx, 2), round(ccy, 2)], "radius": round(r, 2), "outline_points": len(pts), "on_circle": round(cover, 3),
           "residual_px": {"p50": round(float(np.median(resid)), 2), "p95": round(p95, 2), "max": round(float(resid.max()), 2)},
           "thickness_px": {"min": round(float((r - fixed).min()), 1), "max": round(float((r - fixed).max()), 1)},
           "touched_deg": int(dirty.sum()), "ghost_alpha_max": round(gmax, 3), "mask_px": int(mask.sum()),
           "visible_px": int((mask & (alpha > 0.02)).sum())}
    return {"center": (ccx, ccy), "radius": r, "r_in": fixed, "box": [bx0, by0, bx1 - bx0, by1 - by0], "mask": mask, "record": rec}
