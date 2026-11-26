"""게이지 채움을 컨셉에서 결정적으로 따오기 (1b 후속 F — codex · LLM 없음).

B 의 `gradient_bar` 는 채운 부분에서 줄마다 색만 뽑아 사각형을 만든다 — 컨셉 채움의 모양(왼쪽 '<' 끝 · 몸통 둘레 밝은 테두리)과
몸통 ↔ 프레임 선 사이 트랙 띠의 빛(빈 트랙보다 밝다)이 빠지고, 막대 상자가 띠를 빼서 위아래 어두운 트랙이 보였다(사용자 사람 눈 11-15).

측정(`measure`, 따온 프레임이 아래 깔린 가로 게이지만):
  1. 채움 몸통 — 밝기 L(0.299 R + 0.587 G + 0.114 B)이 문턱 T = (몸통 L + 빈 트랙 L) / 2 보다 밝은 픽셀을 3×3 열기(가는 프레임 선과 이어진
     다리를 끊음) → 씨앗(LLM 막대의 채운 부분 가운데)에서 4-연결 → 원래 마스크 안에서 2 px 되살림.
  2. 트랙 상자 — 오른쪽은 몸통 가운데 줄을 따라 빈 트랙 끝 프레임 선(L > T)까지, 위 · 아래는 빈 쪽 열에서 가운데 줄부터 프레임 선까지
     (채운 쪽 띠 안의 경사면 밝은 줄에 걸리지 않게 — 빈 쪽이 짧으면 몸통 열에서), 왼쪽은 몸통 왼쪽 끝 − 띠 폭(띠도 '<' 를 따른다).
  3. 진행 끝(end = scale) — 몸통 오른쪽 끝의 세로 테두리(end_in px)와 빈 트랙으로 번진 빛(spill — 빈 트랙보다 L 4 이상 밝은 열, 최대 24 px).
     1b 후속 L 다음 F2 — 컨셉 채움 텍스처(texture concept)는 번짐을 빼고(spill 0) 잰 값은 spill_measured 로만 — 번짐 열이 100 % 에서 트랙 밖 끝 장식을 덮었다.
텍스처(`render`, 같은 값 → 같은 바이트): 트랙 상자 1:1.
  - 왼쪽 끝(lead px): 컨셉 픽셀 그대로, 알파 = 몸통 ∪ (몸통에서 띠 폭 안 · 어두운 쪽 · 몸통과 4-연결) — 그 밖(프레임 선 · 장식)은 투명.
  - 가운데: 줄마다 대표색(컨셉 몸통 구간의 중앙값, 띠 포함 — 가로로는 같은 색) — 왼쪽 끝과 8 px 섞음.
  - end = scale: 오른쪽 끝(end_in + spill + 1 px)에 컨셉의 진행 끝 테두리 + 번짐(번짐은 빈 트랙 색 E 위에 그 줄의 테두리 색 G 를 얹는
    알파 a = (C − E)·(G − E) / |G − E|²). ProgressBar `bar_fill_style: scale` + 채움 brush box(margin = 왼쪽 끝 · 오른쪽 끝)로 그리면
    양끝은 고정, 가운데만 진행률만큼 늘어난다([소스] SProgressBar.cpp:141-157 클립 · Scale 이면 칠할 폭 = W·p, ElementBatcher.cpp:857-867 box 여백 고정).
    end = mask(Slate 기본): 진행률 자리에서 딱 자르므로 오른쪽 끝 구간 없음.
  - right_to_left 는 프레임 상자 안에서 좌우를 뒤집어 같은 계산을 한 뒤 되뒤집는다.
  - 1b 후속 L 다음 G3 — 끝 모양(end_shape): 오른쪽 고정 여백(컨셉 70 % 의 곧은 진행 끝)은 100 % 에서 트랙 끝 장식 안쪽 호를 덮었다 [실측 R20261119_144231
    사용자 눈]. 컨셉 빈 트랙 오른쪽 끝(track_hole 윤곽 — 끝 장식 안쪽 호까지)을 줄마다 재(offsets = right − 그 줄 hole 끝) 여백 = END_IN + 1 + 호 깊이로
    넓히고, 여백 알파 = 100 % 자리의 hole · 진행 끝 테두리는 그 줄 hole 끝을 따라 그린다 — 100 % 에서 왼쪽 '<' 처럼 호에 맞게 들어간다. 대신 중간 진행률의
    끝은 곧은 선이 아니라 호 모양(컨셉 70 % 와 다름 → 진단 근사 gauge_end_shape, state_check.end_shape_zones). 호 깊이 0(곧은 끝)이면 예전 그대로.
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
END_SHAPE_MAX = 24       # 1b 후속 L 다음 G3 — 빈 트랙 끝 호 깊이를 찾는 폭(px) — 넘으면 끝 모양 없이(예전 곧은 끝)


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


def _lead(body: np.ndarray, top: int, bot: int, left: int, right: int, x0: int, x1: int) -> int:
    """왼쪽 끝 모양이 끝나는 열(트랙 기준) — 몸통 세로 폭이 안정 구간의 LEAD_EXTENT 에 닿는 첫 열 + LEAD_PAD. 못 재면 -1."""
    ext = body[top:bot + 1, left:right + 1].sum(axis=0)
    stable = float(np.median(ext[(x0 - left) + (x1 - x0) // 4:(x0 - left) + (x1 - x0) // 2]))
    hit = np.where(ext >= LEAD_EXTENT * stable)[0]
    return int(hit[0]) + LEAD_PAD if len(hit) else -1


def _measure_full(ref, frame_box, bar_box, flip: bool, end: str) -> dict:
    """1b 후속 J — 가득 찬 게이지(컨셉 진행률 ≥ FULL_MIN): 빈 부분이 없어 빈 트랙 밝기 대신 막대 둘레 어두운 띠(막대 줄 ± 반 높이의 아래 20 %)로
    문턱을 잡고, 몸통 · 띠 · 양끝 모양(왼쪽 · 오른쪽 lead)을 잰다. 텍스처 = 트랙 전체 컨셉 조각(1:1), 진행률이 줄면 양끝은 고정 · 몸통만 준다.
    [실측 J R20261117_192631 파티 HUD] HP 1.0 이 'sample percent 1' 로 빠져 사각 gradient_bar — 화살 끝 '<' '>' 빠짐 · 막대 위 6 px 구멍(국소 ΔE00 29)."""
    ox, oy, ow, oh = (int(round(v)) for v in frame_box)
    # 프레임 상자를 FULL_PAD 넓혀 잰다 — analyze 프레임 상자가 막대 둘레 선을 자르면 띠 끝(선)을 못 찾는다
    # [실측 J R20261117_192631 — HpFrame 상자 위 끝 = 막대 위 5 px, 선은 그 밖]
    H_, W_ = np.asarray(ref).shape[:2]
    nx, ny = max(0, ox - FULL_PAD), max(0, oy - FULL_PAD)
    ox, oy, ow, oh = nx, ny, min(W_, ox + ow + FULL_PAD) - nx, min(H_, oy + oh + FULL_PAD) - ny
    crop = _crop(ref, [ox, oy, ow, oh], flip)
    L = luminance(crop)
    bx, by, bw, bh = (float(v) for v in bar_box)
    bx = (ox + ow) - (bx + bw) if flip else bx - ox
    by -= oy
    r0, r1 = int(round(by + 0.25 * bh)), max(int(round(by + 0.75 * bh)), int(round(by + 0.25 * bh)) + 1)
    if r0 < 0 or r1 > oh:
        raise ConceptFillError("bar box rows are outside the frame box")
    c0, c1 = int(bx + 0.15 * bw), max(int(bx + 0.85 * bw), int(bx + 0.15 * bw) + 1)
    if c0 < 0 or c1 > ow:
        raise ConceptFillError(f"bar box {list(bar_box)} is outside the frame box {list(frame_box)}")
    body_L = float(np.median(L[r0:r1, c0:c1]))
    q0, q1 = max(0, int(round(by - 0.5 * bh))), min(oh, int(round(by + 1.5 * bh)))
    if q1 <= q0:
        raise ConceptFillError("no rows around the full bar to measure the dark band")
    dark_L = float(np.percentile(L[q0:q1, c0:c1], 20))
    if body_L - dark_L < MIN_CONTRAST:
        raise ConceptFillError(f"full bar L {body_L:.0f} vs the dark band around it L {dark_L:.0f} — contrast below {MIN_CONTRAST:g}")
    T = round((body_L + dark_L) / 2.0, 1)
    seed = [int(round(bx + 0.5 * bw)), int(round(by + 0.5 * bh))]
    body = _body_mask(L, T, seed)
    if body is None:
        raise ConceptFillError("the seed in the middle of the full bar is not bright")
    ys, xs = np.where(body)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    if x0 <= 2 or x1 >= ow - 3 or y0 <= 1 or y1 >= oh - 2:
        raise ConceptFillError(f"the bright bar touches the frame box edge (x {x0}-{x1}, y {y0}-{y1}) — it leaked into the frame lines")
    if x1 - x0 < 0.6 * bw or y1 - y0 + 1 < 0.4 * bh:
        raise ConceptFillError(f"the bright bar is too small ({x1 - x0 + 1}×{y1 - y0 + 1} px against the bar box {bw:.0f}×{bh:.0f})")
    cols = np.linspace(x0 + 0.3 * (x1 - x0), x0 + 0.7 * (x1 - x0), 9).round().astype(int)
    spans = [(int(r.min()), int(r.max())) for r in (np.where(body[:, c])[0] for c in cols) if len(r)]
    body_top, body_bot = int(np.median([s[0] for s in spans])), int(np.median([s[1] for s in spans]))
    tb = []
    for c in cols:
        t, b = body_top, body_bot
        while t > 0 and L[t - 1, c] <= T:
            t -= 1
        while b < oh - 1 and L[b + 1, c] <= T:
            b += 1
        tb.append((t, b))
    top, bot = int(np.median([v[0] for v in tb])), int(np.median([v[1] for v in tb]))
    band_top, band_bot = body_top - top, bot - body_bot
    track_from = "body columns (full bar)"
    if top <= 0 or bot >= oh - 1 or max(band_top, band_bot) > MAX_BAND or min(band_top, band_bot) < 0:
        # 막대 둘레에 문턱보다 밝은 선이 없다 — 막대 자체(밝은 테두리 포함)가 트랙 [실측 J 파티 HUD — 위 · 아래 L 48 ~ 92 청록 띠 뒤 바로 어둠]
        top, bot, band_top, band_bot = body_top, body_bot, 0, 0
        track_from = "body rows (no frame line beside the full bar)"
    band = int(round((band_top + band_bot) / 2.0))
    left, right = max(0, x0 - band - 1), min(ow - 1, x1 + band + 1)
    lead = _lead(body, top, bot, left, right, x0, x1)
    rb = body[:, ::-1]
    rlead = _lead(rb, top, bot, ow - 1 - right, ow - 1 - left, ow - 1 - x1, ow - 1 - x0)
    seg = right - left + 1
    if lead <= 0 or rlead <= 0 or lead + rlead > 0.6 * seg:
        raise ConceptFillError(f"the end shapes of the full bar do not settle (lead {lead}, right lead {rlead})")
    th = bot - top + 1
    params = {"frame_box": [ox, oy, ow, oh], "flip": flip, "threshold": T, "seed": seed, "track": [left, top, right, bot],
              "body_end": x1, "lead": lead, "rlead": rlead, "band_radius": max(band_top, band_bot) + 1, "end": "scale", "end_in": 0, "spill": 0,
              "full": True, "texture": "concept"}
    wx = ox + (ow - left - seg) if flip else ox + left
    ml, mr = round(lead / seg, 4), round(rlead / seg, 4)
    rec = {"full": True, "threshold": T, "body_L": round(body_L, 1), "dark_L": round(dark_L, 1), "band": [band_top, band_bot],
           "track_from": track_from, "lead": lead, "rlead": rlead, "body_box": [x0, y0, x1 - x0 + 1, y1 - y0 + 1], "concept_percent": 1.0}
    return {"params": params, "widget_box": [int(wx), oy + top, int(seg), int(th)], "margin": [mr, 0.0, ml, 0.0] if flip else [ml, 0.0, mr, 0.0],
            "record": rec, "texture_size": [int(seg), int(th)], "percent": 1.0}


FULL_MIN = 0.97          # 1b 후속 J — 컨셉 진행률이 이 이상이면 가득 찬 게이지로 잰다(_measure_full)
FULL_PAD = 16            # 가득 찬 게이지는 프레임 상자를 이만큼 넓혀 잰다(띠 끝 선이 상자 밖일 수 있음)


def measure(ref, frame_box, bar_box, percent: float, fill_type: str = "left_to_right", end: str = "scale") -> dict:
    """→ {"params": {...}, "widget_box": [x, y, w, h], "margin": [l, 0, r, 0] | None, "record": {...}}. 못 재면 ConceptFillError(이유)."""
    if fill_type not in ("left_to_right", "right_to_left"):
        raise ConceptFillError(f"bar_fill_type {fill_type} — only horizontal fills")
    p = float(percent)
    if p >= FULL_MIN and end == "scale":
        return _measure_full(ref, frame_box, bar_box, fill_type == "right_to_left", end)
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
    # 1b 후속 L 다음 F2 — 컨셉 채움 텍스처(texture concept)에서 번짐을 뺀다(spill 0 — 잰 값은 spill_measured 로 기록만). scale + box 여백 고정이라 번짐 열은
    # 오른쪽 여백에 들어 100 % 에서 트랙 끝을 넘어 끝 장식을 덮었다(번짐 열 = 빈 트랙 색 · 알파 1 → 어두운 사각형) [실측 R20261119_091634 사용자 인게임].
    # 번짐 알파를 '빈 트랙보다 밝은 만큼'(render 의 절차 길 식)으로만 줘도 진행 끝 바로 뒤 빛(알파 0.75)이 100 % 끝 장식에 남아 상태 검사 S2 를 못 넘었다
    # [실측 같은 run 오프라인 — 트랙 밖 국소 ΔE00 최대 15.9 · 27 px > 10] → 번짐 0. 컨셉 진행률의 끝 빛은 진단이 근사 gauge_end_glow 로 기록(state_check.end_glow_zones)
    spill_measured, spill = (spill, 0) if end == "scale" else (0, spill)
    params = {"frame_box": [ox, oy, ow, oh], "flip": flip, "threshold": T, "seed": seed, "track": [left, top, right, bot],
              "body_end": x1, "lead": lead, "band_radius": max(band_top, band_bot) + 1, "profile": prof, "end": end,
              "end_in": END_IN if end == "scale" else 0, "spill": spill}
    if spill_measured:
        params["spill_measured"] = spill_measured
    tw = right - left + 1 + (spill if end == "scale" else 0)
    th = bot - top + 1
    wx = ox + (ow - left - tw) if flip else ox + left
    margin, tex_size, percent = None, [int(tw), int(th)], None
    if end == "scale":
        # 1b 후속 J — 채움 텍스처 = 컨셉의 채워진 구간 그대로(왼쪽 끝 · 몸통 · 진행 끝 · 번짐 — render_concept_segment). scale 로 그리면 칠할 폭 = 막대 폭 ×
        # 진행률이라 미리보기 진행률 = 구간 폭 ÷ 막대 폭이면 컨셉과 1:1, 다른 진행률에선 양끝(margin) 고정 · 몸통만 늘어난다.
        # [실측 J-b 기준선 R20261117_134535] 줄마다 대표색 한 줄 몸통은 컨셉의 밝은 결을 지워 국소 ΔE00 10 ~ 22, 진행률 0.7(입력 sample)로 그려
        # 채움 끝이 컨셉보다 약 25 px 짧았다(최대 80) · 왼쪽 끝 알파 밖 어두운 초승달
        seg = x1 - left + 1 + spill
        params["texture"] = "concept"
        right_m = END_IN + spill + 1
        end_cap = None
        if not spill:
            # 1b 후속 L 다음 — 글자 지우기 마감 H4 (나)(사용자 결정 11-19): 채움 오른쪽 끝은 곧게(컨셉 70 % 진행 끝 그대로 — 중간 진행률에 호 · '>' 가 안 나옴),
            # 가득 차면 끝 장식 호에 맞게 = 따로 '끝 덮개' 이미지(end_cap — analyze 가 채움 위에 위젯 하나)가 덮는다. G3(채움 여백을 호 모양으로)는 중간 진행률 끝이
            # 뾰족 · 계단이었다 [사용자 눈 R20261119_190059]
            es = end_shape(ref, params)
            if es is not None and es["margin"] + lead < seg:
                end_cap = es
        ml, mr = round(lead / seg, 4), round(right_m / seg, 4)
        margin = [mr, 0.0, ml, 0.0] if flip else [ml, 0.0, mr, 0.0]
        tex_size = [int(seg), int(th)]
        percent = round(seg / tw, 4)
    track_w = right - left + 1
    rec = {"threshold": T, "body_L": round(body_L, 1), "empty_L": round(empty_L, 1), "band": [band_top, band_bot], "track_from": track_from,
           "lead": lead, "spill": spill, "body_box": [x0, y0, x1 - x0 + 1, y1 - y0 + 1], "concept_percent": round((x1 - left + 1) / track_w, 3)}
    if spill_measured:
        rec["spill_measured"] = spill_measured
    if params.get("end_shape"):
        rec["end_shape"] = {"depth": params["end_shape"]["depth"], "margin": params["end_shape"]["margin"]}
    out = {"params": params, "widget_box": [int(wx), oy + top, int(tw), int(th)], "margin": margin, "record": rec, "texture_size": tex_size,
           "percent": percent}
    if end == "scale" and end_cap is not None:
        out["end_cap"] = end_cap
        rec["end_cap"] = {"depth": end_cap["depth"]}
    return out


def end_shape(ref, params: dict) -> dict | None:
    """G3 — 컨셉 빈 트랙 오른쪽 끝 모양(측정 방향): 줄(top ~ bot)마다 offsets = right − 그 줄 hole 이 끝 END_SHAPE_MAX px 구간 시작부터 처음 끊기는 열
    (구간 시작이 hole 이 아니면 None). 마지막 hole 열로 재면 끝 장식 안쪽 선 너머 hole 까지 닿아, 중간 진행률에서 그 선 자리가 가는 틈으로 비쳤다
    [실측 오프라인 R20261119_144231 — 50 % 끝에 ')' 모양 빈 트랙 선]. 호 깊이 = offsets 최대, 여백 = END_IN + 1 + 깊이. 곧은 끝(깊이 0) · 못 재면 None."""
    try:
        hole, _ = track_hole(ref, params)
    except ConceptFillError:
        return None
    left, top, right, bot = (int(v) for v in params["track"])
    lo = max(int(params["body_end"]) + 1, right - END_SHAPE_MAX)
    offs: list[int | None] = []
    for r in range(top, bot + 1):
        run = hole[r, lo:right + 1]
        if not run[0]:
            offs.append(None)
            continue
        gap = np.nonzero(~run)[0]
        last = int(gap[0]) - 1 if len(gap) else len(run) - 1
        offs.append(int(right - (lo + last)))
    valid = [o for o in offs if o is not None]
    if not valid or max(valid) <= 0:
        return None
    depth = int(max(valid))
    return {"offsets": offs, "depth": depth, "margin": END_IN + 1 + depth}


def _apply_end_shape(c, a, crop, params: dict, hole, seg: int) -> None:
    """G3 — 채움 텍스처(c · a — 측정 방향, 트랙 줄 × seg 열)의 오른쪽 여백을 빈 트랙 끝 모양으로(제자리). 여백 열 j 는 100 % 에서 트랙 열 right − (seg − 1 − j):
    알파 = 줄의 끝(offsets)까지 1 · 그 너머 0(끝 장식 · 프레임은 투명), 색 = 마지막 가운데 열 색, 줄 끝에서 END_IN + 1 열 = 컨셉 진행 끝 테두리(그 줄)."""
    es = params["end_shape"]
    left, top, right, bot = (int(v) for v in params["track"])
    x1 = int(params["body_end"])
    mR = int(es["margin"])
    m0 = seg - mR
    if m0 < 1:
        return
    bcol = c[:, m0 - 1].copy()
    for i, o in enumerate(es["offsets"]):
        c[i, m0:] = bcol[i]
        if o is None:
            a[i, m0:] = 0.0
            continue
        e = seg - 1 - int(o)
        a[i, m0:] = (np.arange(m0, seg) <= e).astype(np.float32) * (a[i, m0 - 1] > 0)
        bs = e - END_IN
        k0 = max(bs, m0)
        if e >= k0:
            c[i, k0:e + 1] = crop[top + i, x1 - END_IN + (k0 - bs):x1 + 1]


END_CAP_PAD = 3          # 1b 후속 L 다음 H4 — 끝 덮개 열 = 트랙 끝에서 호 깊이 + 이만큼(px — 호 안쪽 안티앨리어싱)
END_CAP_SOFT = 2         # 호 안쪽 가장자리 부드럽게 — 덮개 불투명 픽셀 왼쪽 이만큼(px)은 컨셉 밝기를 호 색 ↔ 빈 트랙 색으로 풀어 분수 알파(계단 없음)
END_CAP_MIN_DL = 10.0    # 그때 호 ↔ 빈 트랙 밝기 차가 이보다 작으면 풀지 않음(알파 0)


def end_cap_cols(params: dict, es: dict) -> tuple[int, int]:
    """끝 덮개 열(측정 방향 — 트랙 끝 right 까지)."""
    left, top, right, bot = (int(v) for v in params["track"])
    return max(int(params["body_end"]) + 1, right - int(es["depth"]) - END_CAP_PAD), right


def end_cap_box(params: dict, es: dict) -> list[int]:
    """끝 덮개 캔버스 상자 [x, y, w, h](뒤집기 반영)."""
    ox, oy, ow, oh = (int(v) for v in params["frame_box"])
    left, top, right, bot = (int(v) for v in params["track"])
    c0, c1 = end_cap_cols(params, es)
    x = ox + (ow - 1 - c1) if params.get("flip") else ox + c0
    return [int(x), oy + top, c1 - c0 + 1, bot - top + 1]


def render_end_cap(ref, params: dict) -> np.ndarray:
    """1b 후속 L 다음 H4 (나) — 끝 덮개(procedural concept_end_cap): 트랙 끝 열(end_cap_cols)에서 끝 장식 안쪽 호부터 바깥(줄마다 hole 이 처음 끊기는 열 — end_shape
    offsets · 트랙 구역 밖까지 이어진 밝은 구조물)은 판이 그리는 그림 그대로(빈 트랙 덧칠 unfilled_track — 판과 같은 픽셀이라 중간 진행률엔 안 보임) 알파 1,
    그 왼쪽 END_CAP_SOFT px 는 컨셉 밝기를 호 ↔ 빈 트랙 색으로 풀어 분수 알파 + 호 색(가장자리 부드럽게 — 줄 끝 0/1 계단 없음), 나머지 투명.
    가득 찬 채움(곧은 끝 — 트랙 끝까지)이 호를 넘는 부분을 덮는다. → (h, w, 4) float RGBA(0 ~ 255, 직선 알파, 캔버스 방향)."""
    import cv2
    es = params["end_cap"]
    hole, crop = track_hole(ref, params)
    _, filled = unfilled_track(ref, {k: v for k, v in params.items() if k not in ("end_cap", "shape")})
    if params.get("flip"):
        filled = filled[:, ::-1]
    left, top, right, bot = (int(v) for v in params["track"])
    c0, c1 = end_cap_cols(params, es)
    L = luminance(crop)
    h, w = bot - top + 1, c1 - c0 + 1
    col = np.asarray(filled, float)[top:bot + 1, c0:c1 + 1].copy()
    a = np.zeros((h, w), np.float32)
    offs = es.get("offsets") or []
    track_L = np.zeros(h)
    for i in range(h):
        r = top + i
        o = offs[i] if i < len(offs) else None
        b = c0 if o is None else right - int(o) + 1
        a[i, max(0, b - c0):] = 1.0
        a[i] = np.maximum(a[i], (~hole[r, c0:c1 + 1]).astype(np.float32))       # 구역 밖까지 이어진 밝은 구조물(프레임 선 · 호)
        hv = hole[r, c0:c1 + 1] & (a[i] < 1)
        track_L[i] = float(np.median(luminance(col[i][hv][None])[0])) if hv.any() else float(np.median(L[r, c0:c1 + 1]))
    for i in range(h):
        r = top + i
        for j in range(1, w):
            if a[i, j] < 1 or a[i, j - 1] >= 1:
                continue
            La = float(L[r, c0 + j])
            if La - track_L[i] < END_CAP_MIN_DL:
                continue
            for k in range(1, END_CAP_SOFT + 1):
                jj = j - k
                if jj < 0 or a[i, jj] > 0:
                    break
                t = float(np.clip((L[r, c0 + jj] - track_L[i]) / (La - track_L[i]), 0.0, 1.0))
                if t <= 0.02:
                    break
                a[i, jj] = t
                col[i, jj] = crop[r, c0 + j]
    out = np.dstack([col, a * 255.0])
    clear = out[..., 3] < 1.0
    if clear.any() and (~clear).any():
        _, lab = cv2.distanceTransformWithLabels(clear.astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        src = np.argwhere(~clear)
        idx = lab[clear] - 1
        out[clear, :3] = out[src[idx, 0], src[idx, 1], :3]
    out = np.clip(out, 0.0, 255.0)
    return out[:, ::-1] if params.get("flip") else out


def render_end_cap_bytes(reference_path, params: dict) -> tuple[int, int, bytes]:
    from PIL import Image
    with Image.open(reference_path) as im:
        ref = np.asarray(im.convert("RGB"))
    arr = np.round(render_end_cap(ref, params)).astype(np.uint8)
    return int(arr.shape[1]), int(arr.shape[0]), arr.tobytes()


def unfilled_track(ref, params: dict) -> tuple[np.ndarray, np.ndarray]:
    """게이지 프레임 옮겨 심기용(1b 후속 G2) — 컨셉에서 채움이 구워진 트랙 자리를 같은 줄 빈 트랙 색으로 메운다.
    자리 = 트랙 전체(줄 top ~ bot × 열 left ~ right)에서 그 구역 밖까지 이어진 밝은 덩어리(프레임 선 · 양 끝 캡)를 뺀 전부 — 몸통 · 밝은 테두리 ·
    몸통 쪽 띠 · 번짐 · 몸통과 끊긴 채움 빛 조각 · 채움 끝 뒤로 옅어지는 빛까지. 색 = 그 줄 빈 트랙 맨 오른쪽(right − 4 앞 TRACK_SAMPLE px, 빛이 가장
    덜 닿은 곳)의 중앙값 — 트랙이 줄마다 고른 한 색이 된다(진행률이 바뀌어도 컨셉 채움 끝 자리에 빛이 남지 않게, 메운 자리와 경계 없이).
    [실측 G2 전투 HUD run] 채움 끝 + 번짐까지만 메우자 그 뒤 옅은 빛과 단이 졌다(렌더 x 1171 세로 경계).
    → (자리 마스크, 메운 프레임 조각) — 둘 다 frame_box 좌표 · 컨셉 방향(뒤집기 전). 못 하면 ConceptFillError.
    [실측 G 후속] 게이지 프레임은 옮겨 심기를 건너뛰어 테두리 · 끝 캡이 run 마다 codex 판 그대로였다(사용자 눈 — G 끝 run 4 가 나음)."""
    flip = bool(params.get("flip"))
    hole, crop = track_hole(ref, params)
    left, top, right, bot = (int(v) for v in params["track"])
    # 1b 후속 L 다음 F2 — 번짐을 뺀 채움(spill 0)도 빈 트랙 색 표본 자리는 잰 번짐 뒤(spill_measured) — 판 트랙 색이 예전과 같은 바이트
    x1, spill = int(params["body_end"]), int(params.get("spill_measured", params.get("spill", 0)))
    if params.get("full"):
        raise ConceptFillError("a full gauge has no empty part in the concept to take the track colour from")
    e_hi = right - 4
    e_lo = max(x1 + spill + 6, e_hi - TRACK_SAMPLE)
    if e_hi - e_lo < 4:
        raise ConceptFillError(f"the empty part of the track is too short to sample ({e_lo}-{e_hi})")
    rows = np.median(crop[top:bot + 1, e_lo:e_hi], axis=1)
    out = crop.copy()
    rr, cc = np.where(hole)
    out[rr, cc] = rows[rr - top]
    if flip:
        out, hole = out[:, ::-1], hole[:, ::-1]
    return hole, out


def track_hole(ref, params: dict) -> tuple[np.ndarray, np.ndarray]:
    """채움이 덮는 트랙 자리(측정 방향 — flip 이면 뒤집힌 좌표) = 트랙 구역에서 구역 밖까지 이어진 밝은 덩어리(프레임 선 · 끝 캡)를 뺀 전부 → (자리, 측정 방향 crop)."""
    import cv2
    flip = bool(params.get("flip"))
    crop = _crop(ref, params["frame_box"], flip)
    L = luminance(crop)
    left, top, right, bot = (int(v) for v in params["track"])
    T = float(params["threshold"])
    body = _body_mask(L, T, params["seed"])
    if body is None:
        raise ConceptFillError("the seed in the middle of the filled part is not bright")
    region = np.zeros(L.shape, bool)
    region[top:bot + 1, max(0, left):min(L.shape[1], right + 1)] = True
    # 밝은 덩어리(몸통 제외) 중 구역 밖까지 이어진 것 = 프레임 선 · 캡 장식 — 그대로. 구역 안에 갇힌 것은 몸통과 끊긴 채움 빛 조각 — 메운다
    # [실측 G2 — G 크기 끝 run 2 컨셉] 트랙 아래 줄에 채움 빛 조각이 점점이 남았다
    if params.get("full"):
        # 가득 찬 게이지 = 막대 실루엣(몸통 + 띠 반지름) — 트랙 사각형 전체면 화살 끝 바깥 어두운 모서리까지 채움이 불투명하게 칠했다
        # [실측 J R20261117_205334 — HP 오른쪽 끝 모서리 '이중' 국소 ΔE00 36]
        r = int(params.get("band_radius", 1))
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        return region & cv2.dilate(body.astype(np.uint8), k).astype(bool), crop
    n, lab = cv2.connectedComponents(((L > T) & ~body).astype(np.uint8), connectivity=8)
    outside = np.unique(lab[~region & (lab > 0)])
    return region & ~np.isin(lab, outside[outside > 0]), crop


def render_concept_segment(ref, params: dict) -> np.ndarray:
    """1b 후속 J — 채움 텍스처 = 컨셉의 채워진 구간(트랙 왼쪽 끝 ~ 몸통 끝 + 번짐) 픽셀 그대로, 알파 = unfilled_track 이 빈 트랙으로 메우는 자리
    (프레임 선 · 끝 캡처럼 구역 밖까지 이어진 밝은 덩어리는 투명 — 아래 판이 그린다). → (h, seg, 4) float RGBA."""
    import cv2
    flip = bool(params.get("flip"))
    hole, crop = track_hole(ref, params)
    left, top, right, bot = (int(v) for v in params["track"])
    # 가득 찬 게이지(full)는 트랙 전체(양끝 띠 포함), 아니면 왼쪽 끝 ~ 몸통 끝 + 번짐
    seg = right - left + 1 if params.get("full") else int(params["body_end"]) - left + 1 + int(params.get("spill", 0))
    c = crop[top:bot + 1, left:left + seg]
    a = hole[top:bot + 1, left:left + seg].astype(np.float32)
    if c.shape[1] != seg:
        raise ConceptFillError(f"the filled segment ({seg} px) runs past the frame box")
    a = np.maximum(a, cv2.blur(a, (3, 3)) * (a > 0))            # 가장자리 그대로(안 넓힘)
    if params.get("end_shape") and not params.get("full"):
        c = c.copy()
        _apply_end_shape(c, a, crop, params, hole, seg)          # G3 — 오른쪽 여백 = 빈 트랙 끝 호 모양
    out = np.dstack([c, a * 255.0])
    clear = out[..., 3] < 1.0
    if clear.any() and (~clear).any():
        # 완전 투명 픽셀 RGB = 가장 가까운 보이는 픽셀 색(이중선형 필터의 어두운 테두리 방지)
        _, lab = cv2.distanceTransformWithLabels(clear.astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        src = np.argwhere(~clear)
        idx = lab[clear] - 1
        out[clear, :3] = out[src[idx, 0], src[idx, 1], :3]
    out = np.clip(out, 0.0, 255.0)
    return out[:, ::-1] if flip else out


def render(ref, params: dict) -> np.ndarray:
    """→ (h, w, 4) float RGBA(0 ~ 255, 직선 알파). measure 가 준 값으로 언제나 같은 그림."""
    import cv2
    if params.get("end") == "scale" and params.get("texture") == "concept":
        return render_concept_segment(ref, params)
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
