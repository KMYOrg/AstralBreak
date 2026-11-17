"""게이지 채움을 컨셉에서 결정적으로 따오기 (1b 후속 F — codex · LLM 없음).

B 의 `gradient_bar` 는 채운 부분에서 줄마다 색만 뽑아 사각형을 만든다 — 컨셉 채움의 모양(왼쪽 '<' 끝 · 몸통 둘레 밝은 테두리)과
몸통 ↔ 프레임 선 사이 트랙 띠의 빛(빈 트랙보다 밝다)이 빠지고, 막대 상자가 띠를 빼서 위아래 어두운 트랙이 보였다(사용자 사람 눈 11-15).

측정(`measure`, 따온 프레임이 아래 깔린 가로 게이지만):
  1. 채움 몸통 — 밝기 L(0.299 R + 0.587 G + 0.114 B)이 문턱 T = (몸통 L + 빈 트랙 L) / 2 보다 밝은 픽셀을 3×3 열기(가는 프레임 선과 이어진
     다리를 끊음) → 씨앗(LLM 막대의 채운 부분 가운데)에서 4-연결 → 원래 마스크 안에서 2 px 되살림.
  2. 트랙 상자 — 오른쪽은 몸통 가운데 줄을 따라 빈 트랙 끝 프레임 선(L > T)까지, 위 · 아래는 빈 쪽 열에서 가운데 줄부터 프레임 선까지
     (채운 쪽 띠 안의 경사면 밝은 줄에 걸리지 않게 — 빈 쪽이 짧으면 몸통 열에서), 왼쪽은 몸통 왼쪽 끝 − 띠 폭(띠도 '<' 를 따른다).
  3. 진행 끝(end = scale) — 몸통 오른쪽 끝의 세로 테두리(end_in px)와 빈 트랙으로 번진 빛(spill — 빈 트랙보다 L 4 이상 밝은 열, 최대 24 px).
텍스처(`render`, 같은 값 → 같은 바이트): 트랙 상자 1:1.
  - 왼쪽 끝(lead px): 컨셉 픽셀 그대로, 알파 = 몸통 ∪ (몸통에서 띠 폭 안 · 어두운 쪽 · 몸통과 4-연결) — 그 밖(프레임 선 · 장식)은 투명.
  - 가운데: 줄마다 대표색(컨셉 몸통 구간의 중앙값, 띠 포함 — 가로로는 같은 색) — 왼쪽 끝과 8 px 섞음.
  - end = scale: 오른쪽 끝(end_in + spill + 1 px)에 컨셉의 진행 끝 테두리 + 번짐(번짐은 빈 트랙 색 E 위에 그 줄의 테두리 색 G 를 얹는
    알파 a = (C − E)·(G − E) / |G − E|²). ProgressBar `bar_fill_style: scale` + 채움 brush box(margin = 왼쪽 끝 · 오른쪽 끝)로 그리면
    양끝은 고정, 가운데만 진행률만큼 늘어난다([소스] SProgressBar.cpp:141-157 클립 · Scale 이면 칠할 폭 = W·p, ElementBatcher.cpp:857-867 box 여백 고정).
    end = mask(Slate 기본): 진행률 자리에서 딱 자르므로 오른쪽 끝 구간 없음.
  - right_to_left 는 프레임 상자 안에서 좌우를 뒤집어 같은 계산을 한 뒤 되뒤집는다.
"""
from __future__ import annotations

import numpy as np

MIN_CONTRAST = 40.0      # 몸통 L − 빈 트랙 L 이 이보다 작으면 채움을 못 가른다
MAX_BAND = 12            # 몸통 ↔ 프레임 선 띠 최대 폭(px)
LEAD_EXTENT = 0.85       # 몸통 세로 폭이 안정 구간의 이 비율에 닿는 열 = 왼쪽 끝 모양이 끝나는 곳
LEAD_PAD = 8
BLEND = 8                # 왼쪽 끝 컨셉 픽셀 ↔ 줄 대표색 섞는 폭
END_IN = 5               # 진행 끝 세로 테두리 폭(몸통 안쪽)
SPILL_MIN_L = 4.0        # 번짐 = 빈 트랙보다 이만큼 밝은 열
SPILL_MAX = 24
END_BLEND = 6
TRACK_SAMPLE = 60        # 1b 후속 G2 — 게이지 프레임 옮겨 심기: 빈 트랙 맨 오른쪽 이 폭에서 줄 색을 뽑는다


class ConceptFillError(ValueError):
    pass


def luminance(rgb) -> np.ndarray:
    return np.asarray(rgb, float)[..., :3] @ np.array([0.299, 0.587, 0.114])


def _body_mask(L: np.ndarray, T: float, seed_xy) -> np.ndarray | None:
    import cv2
    bright = (L > T).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(bright, cv2.MORPH_OPEN, k, iterations=1)
    _, lab = cv2.connectedComponents(opened, connectivity=4)
    sx, sy = int(seed_xy[0]), int(seed_xy[1])
    if not (0 <= sy < L.shape[0] and 0 <= sx < L.shape[1]) or lab[sy, sx] == 0:
        return None
    body = lab == lab[sy, sx]
    for _ in range(2):
        body = cv2.dilate(body.astype(np.uint8), k).astype(bool) & bright.astype(bool)
    return body


def _crop(ref, frame_box, flip: bool) -> np.ndarray:
    ox, oy, ow, oh = (int(v) for v in frame_box)
    c = np.asarray(ref, float)[oy:oy + oh, ox:ox + ow, :3]
    if c.shape[0] != oh or c.shape[1] != ow:
        raise ConceptFillError(f"frame box {list(frame_box)} is outside the reference")
    return c[:, ::-1] if flip else c


def measure(ref, frame_box, bar_box, percent: float, fill_type: str = "left_to_right", end: str = "scale") -> dict:
    """→ {"params": {...}, "widget_box": [x, y, w, h], "margin": [l, 0, r, 0] | None, "record": {...}}. 못 재면 ConceptFillError(이유)."""
    if fill_type not in ("left_to_right", "right_to_left"):
        raise ConceptFillError(f"bar_fill_type {fill_type} — only horizontal fills")
    p = float(percent)
    if not 0.15 <= p <= 0.9:
        raise ConceptFillError(f"sample percent {p:g} — needs both a filled and an empty part to measure (0.15 ~ 0.9)")
    flip = fill_type == "right_to_left"
    ox, oy, ow, oh = (int(round(v)) for v in frame_box)
    crop = _crop(ref, [ox, oy, ow, oh], flip)
    L = luminance(crop)
    bx, by, bw, bh = (float(v) for v in bar_box)
    # 프레임 상자 기준 좌표로 — 뒤집으면 막대의 오른쪽 끝이 왼쪽 끝이 된다
    bx = (ox + ow) - (bx + bw) if flip else bx - ox
    by -= oy
    r0, r1 = int(round(by + 0.25 * bh)), max(int(round(by + 0.75 * bh)), int(round(by + 0.25 * bh)) + 1)
    if r0 < 0 or r1 > oh:
        raise ConceptFillError("bar box rows are outside the frame box")
    body_L = float(np.median(L[r0:r1, int(bx + 0.15 * p * bw):max(int(bx + 0.85 * p * bw), int(bx + 0.15 * p * bw) + 1)]))
    e0 = int(bx + max(p + 0.08, 0.85) * bw)
    e1 = max(int(bx + 0.97 * bw), e0 + 1)
    empty_L = float(np.median(L[r0:r1, e0:min(e1, ow)])) if e0 < ow else float("nan")
    if not np.isfinite(empty_L) or body_L - empty_L < MIN_CONTRAST:
        raise ConceptFillError(f"filled part L {body_L:.0f} vs empty track L {empty_L:.0f} — contrast below {MIN_CONTRAST:g}")
    T = round((body_L + empty_L) / 2.0, 1)
    seed = [int(round(bx + 0.5 * p * bw)), int(round(by + 0.5 * bh))]
    body = _body_mask(L, T, seed)
    if body is None:
        raise ConceptFillError("the seed in the middle of the filled part is not bright")
    ys, xs = np.where(body)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    if x0 <= 2 or x1 >= ow - 3 or y0 <= 1 or y1 >= oh - 2:
        raise ConceptFillError(f"the bright fill region touches the frame box edge (x {x0}-{x1}, y {y0}-{y1}) — it leaked into the frame lines")
    if x1 - x0 < 0.4 * p * bw or y1 - y0 + 1 < 0.4 * bh:
        raise ConceptFillError(f"the bright fill region is too small ({x1 - x0 + 1}×{y1 - y0 + 1} px)")
    # 몸통 위 · 아래 끝: 몸통 가운데 열 9 개의 중앙값(한 열의 잡티 · 경사면 밝은 줄에 흔들리지 않게)
    cols = np.linspace(x0 + 0.3 * (x1 - x0), x0 + 0.7 * (x1 - x0), 9).round().astype(int)
    spans = [(int(r.min()), int(r.max())) for r in (np.where(body[:, c])[0] for c in cols) if len(r)]
    if not spans:
        raise ConceptFillError("no body columns to measure the track from")
    body_top, body_bot = int(np.median([s[0] for s in spans])), int(np.median([s[1] for s in spans]))
    ym = (body_top + body_bot) // 2
    mid = slice(max(0, ym - 2), ym + 3)
    line = np.median(L[mid], axis=0)
    right = None
    for x in range(x1 + 20, ow):
        if line[x] > T:
            right = x - 1
            break
    if right is None:
        raise ConceptFillError("no frame line at the right end of the empty track")

    def walk(c):
        t = ym
        while t > 0 and L[t - 1, c] <= T:
            t -= 1
        b = ym
        while b < oh - 1 and L[b + 1, c] <= T:
            b += 1
        return t, b

    # 트랙 위 · 아래 = 빈 쪽 열에서 가운데 줄부터 프레임 선(L > T)까지 — 빈 쪽엔 프레임 선만 밝다
    # [실측 F — C1 컨셉] 채운 쪽 띠 안에는 빛 받은 경사면 밝은 줄(L 100 ~ 200)이 있어 몸통 열로 재면 선보다 앞에서 멈춘다
    e_lo, e_hi = x1 + 30, right - 8
    if e_hi - e_lo >= 8:
        tb = [walk(c) for c in np.linspace(e_lo, e_hi, 9).round().astype(int)]
        track_from = "empty columns"
    else:
        tb = []
        for c in cols:
            r = np.where(body[:, c])[0]
            if len(r):
                t, b = int(r.min()), int(r.max())
                while t > 0 and L[t - 1, c] <= T:
                    t -= 1
                while b < oh - 1 and L[b + 1, c] <= T:
                    b += 1
                tb.append((t, b))
        track_from = "body columns (empty part too short)"
    top, bot = int(np.median([v[0] for v in tb])), int(np.median([v[1] for v in tb]))
    band_top, band_bot = body_top - top, bot - body_bot
    if top <= 0 or bot >= oh - 1 or max(band_top, band_bot) > MAX_BAND or min(band_top, band_bot) < 0:
        raise ConceptFillError(f"track rows {top}-{bot} around the body {body_top}-{body_bot} do not look like a framed track")
    band = int(round((band_top + band_bot) / 2.0))
    left = max(0, x0 - band - 1)
    ext = body[top:bot + 1, left:right + 1].sum(axis=0)
    stable = float(np.median(ext[(x0 - left) + (x1 - x0) // 4:(x0 - left) + (x1 - x0) // 2]))
    hit = np.where(ext >= LEAD_EXTENT * stable)[0]
    lead = int(hit[0]) + LEAD_PAD if len(hit) else -1
    if lead <= 0 or lead > 0.5 * (x1 - left):
        raise ConceptFillError(f"the left end shape does not settle (lead {lead})")
    prof = [lead + 6, (x1 - left) - END_IN - 8]
    if prof[1] - prof[0] < 20:
        raise ConceptFillError(f"too few body columns for the row colors ({prof})")
    spill = 0
    if end == "scale":
        e_lo, e_hi = x1 + 30, right - 8
        if e_hi - e_lo >= 8:
            empty_rows = np.median(L[top:bot + 1, e_lo:e_hi], axis=1)
            for x in range(x1 + 1, min(x1 + 1 + SPILL_MAX, right)):
                if float(np.mean(L[top:bot + 1, x] - empty_rows)) < SPILL_MIN_L:
                    break
                spill += 1
    params = {"frame_box": [ox, oy, ow, oh], "flip": flip, "threshold": T, "seed": seed, "track": [left, top, right, bot],
              "body_end": x1, "lead": lead, "band_radius": max(band_top, band_bot) + 1, "profile": prof, "end": end,
              "end_in": END_IN if end == "scale" else 0, "spill": spill}
    tw = right - left + 1 + (spill if end == "scale" else 0)
    th = bot - top + 1
    wx = ox + (ow - left - tw) if flip else ox + left
    margin = None
    if end == "scale":
        ml, mr = round(lead / tw, 4), round((END_IN + spill + 1) / tw, 4)
        margin = [mr, 0.0, ml, 0.0] if flip else [ml, 0.0, mr, 0.0]
    track_w = right - left + 1
    rec = {"threshold": T, "body_L": round(body_L, 1), "empty_L": round(empty_L, 1), "band": [band_top, band_bot], "track_from": track_from,
           "lead": lead, "spill": spill, "body_box": [x0, y0, x1 - x0 + 1, y1 - y0 + 1], "concept_percent": round((x1 - left + 1) / track_w, 3)}
    return {"params": params, "widget_box": [int(wx), oy + top, int(tw), int(th)], "margin": margin, "record": rec}


def unfilled_track(ref, params: dict) -> tuple[np.ndarray, np.ndarray]:
    """게이지 프레임 옮겨 심기용(1b 후속 G2) — 컨셉에서 채움이 구워진 트랙 자리를 같은 줄 빈 트랙 색으로 메운다.
    자리 = 트랙 전체(줄 top ~ bot × 열 left ~ right)에서 그 구역 밖까지 이어진 밝은 덩어리(프레임 선 · 양 끝 캡)를 뺀 전부 — 몸통 · 밝은 테두리 ·
    몸통 쪽 띠 · 번짐 · 몸통과 끊긴 채움 빛 조각 · 채움 끝 뒤로 옅어지는 빛까지. 색 = 그 줄 빈 트랙 맨 오른쪽(right − 4 앞 TRACK_SAMPLE px, 빛이 가장
    덜 닿은 곳)의 중앙값 — 트랙이 줄마다 고른 한 색이 된다(진행률이 바뀌어도 컨셉 채움 끝 자리에 빛이 남지 않게, 메운 자리와 경계 없이).
    [실측 G2 전투 HUD run] 채움 끝 + 번짐까지만 메우자 그 뒤 옅은 빛과 단이 졌다(렌더 x 1171 세로 경계).
    → (자리 마스크, 메운 프레임 조각) — 둘 다 frame_box 좌표 · 컨셉 방향(뒤집기 전). 못 하면 ConceptFillError.
    [실측 G 후속] 게이지 프레임은 옮겨 심기를 건너뛰어 테두리 · 끝 캡이 run 마다 codex 판 그대로였다(사용자 눈 — G 끝 run 4 가 나음)."""
    flip = bool(params.get("flip"))
    crop = _crop(ref, params["frame_box"], flip)
    L = luminance(crop)
    left, top, right, bot = (int(v) for v in params["track"])
    x1, spill, T = int(params["body_end"]), int(params.get("spill", 0)), float(params["threshold"])
    body = _body_mask(L, T, params["seed"])
    if body is None:
        raise ConceptFillError("the seed in the middle of the filled part is not bright")
    import cv2
    e_hi = right - 4
    e_lo = max(x1 + spill + 6, e_hi - TRACK_SAMPLE)
    if e_hi - e_lo < 4:
        raise ConceptFillError(f"the empty part of the track is too short to sample ({e_lo}-{e_hi})")
    rows = np.median(crop[top:bot + 1, e_lo:e_hi], axis=1)
    region = np.zeros(L.shape, bool)
    region[top:bot + 1, max(0, left):min(L.shape[1], right + 1)] = True
    # 밝은 덩어리(몸통 제외) 중 구역 밖까지 이어진 것 = 프레임 선 · 캡 장식 — 그대로. 구역 안에 갇힌 것은 몸통과 끊긴 채움 빛 조각 — 메운다
    # [실측 G2 — G 크기 끝 run 2 컨셉] 트랙 아래 줄에 채움 빛 조각이 점점이 남았다
    n, lab = cv2.connectedComponents(((L > T) & ~body).astype(np.uint8), connectivity=8)
    outside = np.unique(lab[~region & (lab > 0)])
    hole = region & ~np.isin(lab, outside[outside > 0])
    out = crop.copy()
    rr, cc = np.where(hole)
    out[rr, cc] = rows[rr - top]
    if flip:
        out, hole = out[:, ::-1], hole[:, ::-1]
    return hole, out


def render(ref, params: dict) -> np.ndarray:
    """→ (h, w, 4) float RGBA(0 ~ 255, 직선 알파). measure 가 준 값으로 언제나 같은 그림."""
    import cv2
    flip = bool(params.get("flip"))
    crop = _crop(ref, params["frame_box"], flip)
    L = luminance(crop)
    T = float(params["threshold"])
    body = _body_mask(L, T, params["seed"])
    if body is None:
        raise ConceptFillError("the seed is no longer bright — the reference changed")
    left, top, right, bot = (int(v) for v in params["track"])
    x1, lead, rad = int(params["body_end"]), int(params["lead"]), int(params["band_radius"])
    end, end_in, spill = params.get("end", "mask"), int(params.get("end_in", 0)), int(params.get("spill", 0))
    th, track_w = bot - top + 1, right - left + 1
    tw = track_w + (spill if end == "scale" else 0)
    c = crop[top:bot + 1, left:right + 1]
    Lc = L[top:bot + 1, left:right + 1]
    bc = body[top:bot + 1, left:right + 1]
    a0, a1 = (int(v) for v in params["profile"])
    profile = np.median(c[:, a0:a1], axis=1)                                   # (th, 3)
    dil = cv2.dilate(bc.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rad + 1, 2 * rad + 1))).astype(bool)
    cand = (bc | (dil & (Lc <= T))).astype(np.uint8)
    _, lab = cv2.connectedComponents(cand, connectivity=4)
    seed_r = int(np.argmax(bc[:, min(lead + 2, track_w - 1)])) if bc[:, min(lead + 2, track_w - 1)].any() else th // 2
    keep = lab == lab[seed_r, min(lead + 2, track_w - 1)]
    # 구멍 메우기 — 띠 안 경사면 밝은 줄(L > T 이지만 몸통과 안 이어짐)이 투명 줄로 남지 않게: 왼쪽 가장자리(= '<' 바깥)에 닿지 않는 빈 곳은 채움
    _, lab_o = cv2.connectedComponents((~keep).astype(np.uint8), connectivity=4)
    outside = set(np.unique(lab_o[:, 0]).tolist()) - {0}
    keep |= (~keep) & ~np.isin(lab_o, list(outside))
    alpha = cv2.blur(keep.astype(np.float32), (3, 3))
    alpha = np.maximum(alpha, bc.astype(np.float32))
    out = np.zeros((th, tw, 4), float)
    w = np.clip((np.arange(track_w) - (lead - BLEND)) / BLEND, 0.0, 1.0)      # 0 = 컨셉 픽셀, 1 = 줄 대표색
    out[:, :track_w, :3] = c * (1 - w[None, :, None]) + profile[:, None, :] * w[None, :, None]
    out[:, :track_w, 3] = np.maximum(alpha, w[None, :]) * 255.0
    if end == "scale":
        out[:, track_w:, :3] = profile[:, None, :]
        out[:, track_w:, 3] = 255.0
        src0 = x1 - left - end_in                                             # 컨셉 열(트랙 기준): 진행 끝 테두리 시작
        seg = end_in + spill + 1
        full = crop[top:bot + 1, left + src0:left + src0 + seg]
        e_lo, e_hi = x1 + 30, right - 8
        E = np.median(crop[top:bot + 1, e_lo:e_hi], axis=1) if e_hi - e_lo >= 8 else crop[top:bot + 1, right - 4]
        G = profile                                                            # 번짐 색 = 그 줄의 채움색(테두리 흰빛이 아니라 — 실측 F: 희뿌옇게 나옴)
        seg_rgba = np.zeros((th, seg, 4), float)
        seg_rgba[:, :end_in + 1, :3] = full[:, :end_in + 1]
        seg_rgba[:, :end_in + 1, 3] = 255.0
        if spill:
            C = full[:, end_in + 1:]
            d = (G - E)[:, None, :]
            a = np.clip(np.sum((C - E[:, None, :]) * d, axis=2) / np.maximum(np.sum(d * d, axis=2), 1.0), 0.0, 1.0)
            a *= 1.0 - np.arange(1, spill + 1) / (spill + 1)                  # 끝에서 0 — 번짐 길이 상한에서 딱 끊기지 않게
            seg_rgba[:, end_in + 1:, :3] = np.broadcast_to(G[:, None, :], C.shape)
            seg_rgba[:, end_in + 1:, 3] = a * 255.0
        start = tw - seg
        out[:, start:, :] = seg_rgba
        k = np.clip((np.arange(END_BLEND) + 1) / (END_BLEND + 1), 0, 1)       # 가운데 줄 대표색 → 진행 끝 테두리 쪽으로 섞음
        b0 = max(0, start - END_BLEND)
        out[:, b0:start, :3] = profile[:, None, :] * (1 - k[None, -(start - b0):, None]) + full[:, :1, :3] * k[None, -(start - b0):, None]
    out = np.clip(out, 0.0, 255.0)
    # 완전 투명 픽셀도 RGB 를 이웃 색으로(쌍선형 필터의 어두운 테두리 방지 — procedural 규칙과 같게)
    clear = out[:, :, 3] < 1.0
    if clear.any():
        out[clear, :3] = np.broadcast_to(profile[:, None, :], out.shape[:2] + (3,))[clear]
    return out[:, ::-1] if flip else out


def render_bytes(reference_path, params: dict) -> tuple[int, int, bytes]:
    from PIL import Image
    with Image.open(reference_path) as im:
        ref = np.asarray(im.convert("RGB"))
    arr = np.round(render(ref, params)).astype(np.uint8)
    return int(arr.shape[1]), int(arr.shape[0]), arr.tobytes()
