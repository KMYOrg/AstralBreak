"""생성 이미지 후처리 (설계 §7 refine) — 배경 제거 · 여백 자르기 · 크기 맞춤 · 9-slice margin 추정 · codex 참조 자르기
· (1b 후속 A) 컨셉에서 따오기의 입력 조각 · 되자르기 · 안쪽 알파.

Pillow · numpy · OpenCV(headless)는 rapidocr 와 함께 설치됐다(1b-3 사용자 승인). procedural 에셋은 이 모듈을 거치지 않는다(이미 정확한 크기 · 투명).
값은 잠정이다.
"""
from __future__ import annotations

import math
import pathlib

ALPHA_PRESENT_RATIO = 0.02   # 완전 투명 픽셀이 이만큼 있으면 이미 배경이 빠진 것으로 본다
BG_TOLERANCE = 22            # 배경 flood fill 의 채널별 허용 차이(0~255)
TRIM_ALPHA = 8               # 이보다 불투명한 픽셀이 내용
TRIM_PAD = 2
# 9-slice margin 추정 (1b 후속 A 실측 — 끝 run 3장 · 따오기 2장): 옛 방식(열 · 행 평균을 가운데 열 · 행과 비교, ±6)은 5장 중 4장 실패였다.
# 원인 두 가지: ① 가운데 열 · 행이 장식(변 가운데 표식 · 왕관)이라 기준이 틀어짐(가운데 열 ↔ 3 px 옆 차이 2.8 ~ 9.2)
# ② 평균이 위아래 일부에만 있는 모서리 장식을 묻음(체인 패널 모서리 0.13 · 0.21 을 0.018 로 넓힘).
# → 기준 = 가운데 20 % 열(행)의 픽셀별 중앙값, 거리 = 열(행)을 픽셀 단위로 비교한 차이의 p99, 가운데에서 바깥으로 넓히며 짧은 끊김(GAP)은 건너뜀,
#   축마다 따로(실패한 축만 spec 값). p99 에서 체인 패널 margin 이 허용 6 ~ 24 사이에서 거의 같다(0.12 ~ 0.13 · 0.19 ~ 0.22) → 10.
BAND_MIN = 0.2               # 9-slice 늘림 띠가 이 비율보다 짧으면 그 축은 추정 실패(spec margin 을 쓴다)
BAND_TOL = 10.0              # 미리 곱한 RGBA 채널 평균 차이의 p99 허용(0~255)
BAND_PCT = 99                # 열(행) 안 픽셀 차이의 백분위
BAND_REF_FRAC = 0.2          # 기준 = 가운데 이만큼의 열(행) 픽셀별 중앙값
BAND_GAP_FRAC = 0.02         # 이보다 짧은 끊김은 건너뛴다(최소 2 px)
BAND_CENTER_GAP_FRAC = 0.04  # 가운데 ±BAND_CENTER_ZONE 안에서 시작하는 끊김(변 가운데 표식)은 이만큼까지 — [실측 A run] 체인 패널 표식 2.9 · 3.3 %
BAND_CENTER_ZONE = 0.05
MARGIN_CLAMP = (0.01, 0.45)
# 컨셉에서 따오기 (1b 후속 A) — [실측 A-1] built-in image_gen 편집은 출력 캔버스 비율을 입력 비율에 맞춘다(1.624 → 1598×984, 2.993 → 2170×725).
# 지금까지 본 가장 긴 출력 비율이 3:1(2172×724) — 그보다 긴 요소는 실제 장면으로 짧은 변을 넓혀 3:1 안에 넣는다.
EXTRACT_MAX_ASPECT = 3.0
EXTRACT_PAD = 8
CROP_BACK_PAD = 2            # 되자를 때 요소 상자 바깥으로 더 둘 px(입력 조각 기준)
INTERIOR_ALPHA = 0.9
INTERIOR_MAX_L = 35.0        # 안쪽으로 볼 어두운 픽셀(L*)
INTERIOR_EDGE_FRAC = 0.04    # 모양 가장자리에서 이만큼(짧은 변 비율) 안쪽부터


def load_rgba(path: str | pathlib.Path):
    from PIL import Image
    with Image.open(path) as im:
        return im.convert("RGBA")


def alpha_stats(im) -> dict:
    import numpy as np
    a = np.asarray(im)[:, :, 3]
    return {"transparent_ratio": round(float((a == 0).mean()), 4), "has_alpha": bool((a < 255).any())}


def remove_background(im) -> tuple:
    """이미 투명이면 그대로. 아니면 테두리 색을 배경으로 보고 테두리에서 이어진 비슷한 색을 투명으로(가장자리 1 px 부드럽게)."""
    import cv2
    import numpy as np
    from PIL import Image
    st = alpha_stats(im)
    if st["transparent_ratio"] >= ALPHA_PRESENT_RATIO:
        return im, {"method": "kept_alpha", **st}
    rgb = np.asarray(im.convert("RGB")).copy()
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0).astype(int)
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
    tol = (BG_TOLERANCE,) * 3
    seeds = [(x, 0) for x in range(0, w, max(1, w // 64))] + [(x, h - 1) for x in range(0, w, max(1, w // 64))] + \
            [(0, y) for y in range(0, h, max(1, h // 64))] + [(w - 1, y) for y in range(0, h, max(1, h // 64))]
    for x, y in seeds:
        if mask[y + 1, x + 1] == 0 and np.abs(rgb[y, x].astype(int) - bg).max() <= BG_TOLERANCE:
            cv2.floodFill(rgb, mask, (x, y), (0, 0, 0), tol, tol, flags)
    bgmask = mask[1:-1, 1:-1] > 0
    alpha = np.where(bgmask, 0, 255).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    alpha[bgmask & (alpha < 255)] = 0
    out = np.dstack([np.asarray(im.convert("RGB")), alpha])
    res = Image.fromarray(out, "RGBA")
    return res, {"method": "border_flood_fill", "bg_color": "#%02X%02X%02X" % tuple(int(v) for v in bg), "tolerance": BG_TOLERANCE,
                 "removed_ratio": round(float(bgmask.mean()), 4)}


def trim(im) -> tuple:
    """알파 > TRIM_ALPHA 인 내용의 상자로 자른다(+ TRIM_PAD). 내용이 없으면 그대로."""
    import numpy as np
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.where(a > TRIM_ALPHA)
    if len(xs) == 0:
        return im, None
    x0, y0 = max(0, int(xs.min()) - TRIM_PAD), max(0, int(ys.min()) - TRIM_PAD)
    x1, y1 = min(im.width, int(xs.max()) + 1 + TRIM_PAD), min(im.height, int(ys.max()) + 1 + TRIM_PAD)
    return im.crop((x0, y0, x1, y1)), [x0, y0, x1 - x0, y1 - y0]


def fit(im, size, stretch: bool) -> tuple:
    """spec 크기로. 9-slice(늘어나는 틀)는 그대로 늘리고, 나머지는 비율을 지켜 가운데에(투명 여백)."""
    from PIL import Image
    tw, th = int(size[0]), int(size[1])
    if stretch:
        return im.resize((tw, th), Image.Resampling.LANCZOS), "stretch"
    s = min(tw / im.width, th / im.height)
    nw, nh = max(1, round(im.width * s)), max(1, round(im.height * s))
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    out.alpha_composite(im.resize((nw, nh), Image.Resampling.LANCZOS), ((tw - nw) // 2, (th - nh) // 2))
    return out, "contain"


def _line_distance(lines):
    """lines: (n, m, 4) — n 개의 열(또는 행). 기준(가운데 BAND_REF_FRAC 의 픽셀별 중앙값)과의 픽셀 차이 p{BAND_PCT}."""
    import numpy as np
    n = lines.shape[0]
    half = max(1, int(round(n * BAND_REF_FRAC / 2)))
    ref = np.median(lines[max(0, n // 2 - half):n // 2 + half + 1], axis=0)
    return np.percentile(np.abs(lines - ref[None]).mean(axis=2), BAND_PCT, axis=1)


def _band(d) -> tuple[int, int] | None:
    """가운데에서 양쪽으로 d < BAND_TOL 인 동안 넓힌다 — 끊김은 BAND_GAP_FRAC 까지, 가운데 ±BAND_CENTER_ZONE 안에서 시작한 끊김(변 가운데
    표식)은 BAND_CENTER_GAP_FRAC 까지 건너뛴다. 한쪽이라도 좋은 칸이 없으면 None."""
    n = len(d)
    c = n // 2
    gap = max(2, int(round(BAND_GAP_FRAC * n)))
    center_gap = max(gap, int(round(BAND_CENTER_GAP_FRAC * n)))
    zone = BAND_CENTER_ZONE * n
    ends = []
    for step in (-1, 1):
        i, last_good, bad, start = c, None, 0, None
        while 0 <= i < n:
            if d[i] < BAND_TOL:
                last_good, bad, start = i, 0, None
            else:
                if bad == 0:
                    start = i
                bad += 1
                if bad > (center_gap if abs(start - c) <= zone else gap):
                    break
            i += step
        if last_good is None:
            return None
        ends.append(last_good)
    return ends[0], ends[1]


def estimate_nine_slice(im) -> list[float | None] | None:
    """늘려도 되는 띠(가운데 열 · 행들과 픽셀 단위로 거의 같은 연속 구간)를 축마다 찾아 margin [l, t, r, b].
    실패한 축은 None 자리(그 축만 spec 값을 쓴다), 두 축 다 실패하면 None."""
    import numpy as np
    arr = np.asarray(im).astype(float)
    a = arr[:, :, 3:4] / 255.0
    pre = np.concatenate([arr[:, :, :3] * a, arr[:, :, 3:4]], axis=2)
    h, w = pre.shape[:2]
    lo, hi = MARGIN_CLAMP
    clamp = lambda v: round(min(hi, max(lo, v)), 3)   # noqa: E731
    out: list[float | None] = [None, None, None, None]
    bx = _band(_line_distance(np.transpose(pre, (1, 0, 2))))
    if bx and (bx[1] - bx[0] + 1) / w >= BAND_MIN:
        out[0], out[2] = clamp(bx[0] / w), clamp((w - 1 - bx[1]) / w)
    by = _band(_line_distance(pre))
    if by and (by[1] - by[0] + 1) / h >= BAND_MIN:
        out[1], out[3] = clamp(by[0] / h), clamp((h - 1 - by[1]) / h)
    return None if all(v is None for v in out) else out


def merge_margin(estimated: list | None, spec: list | None) -> tuple[list | None, str]:
    """축별 추정값 + spec 값 → (쓸 margin, 출처 estimated | mixed | spec). 둘 다 없는 자리가 있으면 (None, …)."""
    if estimated is None:
        return (list(spec) if spec else None), "spec"
    if all(v is not None for v in estimated):
        return list(estimated), "estimated"
    if not spec:
        return None, "mixed"
    return [e if e is not None else s for e, s in zip(estimated, spec)], "mixed"


# ---------------------------------------------------------------------------------------------------------------------
# 컨셉에서 따오기 (source_mode: extract)

def extract_region(bbox, canvas, pad: int = EXTRACT_PAD, max_aspect: float = EXTRACT_MAX_ASPECT) -> tuple[list[int], list[int], bool]:
    """요소 상자(bbox + pad)를 담는 입력 영역 — 비율이 max_aspect 보다 길면 짧은 변을 실제 화면으로 넓힌다(캔버스 안, 가장자리면 밀어 넣음).
    → (영역 [x, y, w, h], 영역 안 요소 상자 [x, y, w, h], 비율을 맞췄나)."""
    W, H = int(canvas[0]), int(canvas[1])
    x, y, w, h = (float(v) for v in bbox)
    ex0, ey0 = max(0, int(math.floor(x)) - pad), max(0, int(math.floor(y)) - pad)
    ex1, ey1 = min(W, int(math.ceil(x + w)) + pad), min(H, int(math.ceil(y + h)) + pad)
    rx0, ry0, rx1, ry1 = ex0, ey0, ex1, ey1

    def grow(a0, a1, need, limit):
        extra = need - (a1 - a0)
        if extra <= 0:
            return a0, a1
        a0 -= extra // 2
        a1 += extra - extra // 2
        if a0 < 0:
            a1, a0 = min(limit, a1 - a0), 0
        if a1 > limit:
            a0, a1 = max(0, a0 - (a1 - limit)), limit
        return a0, a1

    rw, rh = rx1 - rx0, ry1 - ry0
    if rw / rh > max_aspect:
        ry0, ry1 = grow(ry0, ry1, int(math.ceil(rw / max_aspect)), H)
    elif rh / rw > max_aspect:
        rx0, rx1 = grow(rx0, rx1, int(math.ceil(rh / max_aspect)), W)
    region = [rx0, ry0, rx1 - rx0, ry1 - ry0]
    element = [ex0 - rx0, ey0 - ry0, ex1 - ex0, ey1 - ey0]
    ok = max(region[2] / region[3], region[3] / region[2]) <= max_aspect + 1e-6
    return region, element, ok


def extract_input(reference, bbox, text_boxes, dest, pad: int = EXTRACT_PAD, max_aspect: float = EXTRACT_MAX_ASPECT) -> dict:
    """codex 편집 입력 — reference 에서 extract_region 을 잘라 그 안의 글자 위젯 자리를 inpaint 로 지운다(reference_crop 과 같은 지우기)."""
    from PIL import Image
    with Image.open(reference) as im:
        size = im.size
    region, element, ok = extract_region(bbox, size, pad, max_aspect)
    info = reference_crop(reference, region, text_boxes, dest, pad=0)
    info.update(element=element, aspect=round(region[2] / region[3], 3), aspect_within_limit=ok, max_aspect=max_aspect)
    return info


def crop_back(im, region, element, pad: int = CROP_BACK_PAD) -> tuple:
    """편집 결과(캔버스 = 입력 영역을 늘린 것)에서 요소 상자만 되자른다. 캔버스 비율이 입력과 다르면 축마다 따로 늘려 맞춘다(기록)."""
    sx, sy = im.width / float(region[2]), im.height / float(region[3])
    x0, y0 = max(0, (element[0] - pad) * sx), max(0, (element[1] - pad) * sy)
    x1, y1 = min(im.width, (element[0] + element[2] + pad) * sx), min(im.height, (element[1] + element[3] + pad) * sy)
    box = [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]
    return im.crop(tuple(box)), {"scale": [round(sx, 4), round(sy, 4)], "canvas_aspect_change_pct": round((sx / sy - 1) * 100, 2),
                                 "box": [box[0], box[1], box[2] - box[0], box[3] - box[1]]}


def interior_fill(im, alpha: float = INTERIOR_ALPHA, max_lightness: float = INTERIOR_MAX_L, edge_frac: float = INTERIOR_EDGE_FRAC,
                  flatten: bool = True) -> tuple:
    """속이 비치는 안쪽을 결정적으로 — 안쪽 = 모양(알파 > 128 의 바깥 윤곽을 채움) 가장자리에서 짧은 변 edge_frac 이상 떨어지고 장식선
    (L* ≥ 45 · C* ≥ 20, 2 px 넓힘)이 아닌 자리. flatten 이면 그 자리를 대표색(안쪽의 불투명 · 어두운 픽셀 L* < max_lightness 의 중앙값) 한 색 ·
    알파 alpha 로 칠하고(1.5 px 부드럽게), 아니면 어두운 불투명 픽셀의 알파에만 alpha 를 곱한다.
    [실측 A-1] built-in image_gen 은 '알파 약 90 %'를 요청해도 안쪽을 거의 불투명(250 ~ 254)으로 낸다.
    [실측 A 실제 run] 같은 요청에 글자를 지운 자리를 메우지 않고 비워 둔 판도 나온다(체인 패널 안쪽 35.6 % 가 알파 < 128) — 그래서 평탄화가 기본."""
    import cv2
    import numpy as np
    from PIL import Image
    from core import color
    arr = np.asarray(im.convert("RGBA")).copy()
    a = arr[:, :, 3].astype(np.float32)
    P = 8   # 0 테두리 덧대기 — 모양이 그림 가장자리에 닿아도(따온 텍스처는 위젯 상자로 바짝 자른다) close · 거리 변환이 가장자리를 바깥으로 본다
    m = cv2.copyMakeBorder(((a > 128).astype(np.uint8)) * 255, P, P, P, P, cv2.BORDER_CONSTANT, value=0)
    cnts, _ = cv2.findContours(cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    shape_p = np.zeros_like(m)
    if cnts:
        cv2.drawContours(shape_p, [max(cnts, key=cv2.contourArea)], -1, 255, thickness=-1)
    shape = shape_p[P:-P, P:-P]
    ys, xs = np.where(shape > 0)
    if len(xs) == 0:
        return im, {"alpha": alpha, "changed_ratio": 0.0, "note": "no shape"}
    edge = max(2.0, edge_frac * min(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1))
    dist = cv2.distanceTransform((shape_p > 0).astype(np.uint8), cv2.DIST_L2, 3)[P:-P, P:-P]
    lab = color.srgb_to_lab(arr[:, :, :3])
    lines = (lab[..., 0] >= 45.0) & (np.hypot(lab[..., 1], lab[..., 2]) >= 20.0) & (a > 128)
    lines = cv2.dilate(lines.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    inside = (dist > edge) & ~lines
    dark_opaque = inside & (lab[..., 0] < max_lightness) & (a > 200)
    info = {"alpha": alpha, "flatten": flatten, "max_lightness": max_lightness, "edge_px": round(float(edge), 1),
            "inside_ratio": round(float(inside.mean()), 4), "holes_before": round(float((inside & (a < 128)).sum() / max(1, inside.sum())), 4)}
    if flatten and dark_opaque.sum() >= 16:
        fill = np.median(arr[:, :, :3][dark_opaque], axis=0)
        soft = cv2.GaussianBlur(inside.astype(np.float32), (0, 0), 1.5)[..., None]
        arr[:, :, :3] = np.clip(arr[:, :, :3] * (1 - soft) + fill[None, None, :] * soft, 0, 255).astype(np.uint8)
        arr[:, :, 3] = np.clip(a * (1 - soft[..., 0]) + alpha * 255.0 * soft[..., 0], 0, 255).astype(np.uint8)
        info.update(flattened=True, fill_color="#%02X%02X%02X" % tuple(int(v) for v in fill), changed_ratio=round(float(inside.mean()), 4))
    else:
        soft = cv2.GaussianBlur(dark_opaque.astype(np.float32), (0, 0), 1.5)
        arr[:, :, 3] = np.clip(a * (1 - (1 - alpha) * soft), 0, 255).astype(np.uint8)
        info.update(flattened=False, changed_ratio=round(float(dark_opaque.mean()), 4))
        if flatten:
            info["note"] = "too few dark opaque interior pixels — alpha only"
    return Image.fromarray(arr, "RGBA"), info


def reference_crop(reference: str | pathlib.Path, bbox, text_boxes, dest: str | pathlib.Path, pad: int = 8) -> dict:
    """reference 에서 bbox(+pad)를 잘라 codex 참조(-i)로. 그 안의 글자 위젯 자리(text_boxes — reference 좌표)는 지운다(inpaint)
    — 참조 그림의 글자를 생성기가 베끼지 않게."""
    import cv2
    import numpy as np
    from PIL import Image
    with Image.open(reference) as im:
        rgb = np.asarray(im.convert("RGB")).copy()
    H, W = rgb.shape[:2]
    x, y, w, h = (float(v) for v in bbox)
    x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
    x1, y1 = min(W, int(x + w) + pad), min(H, int(y + h) + pad)
    crop = rgb[y0:y1, x0:x1].copy()
    mask = np.zeros(crop.shape[:2], np.uint8)
    erased = 0
    for tb in text_boxes:
        tx, ty, tw, th = (float(v) for v in tb)
        ax0, ay0 = max(x0, int(tx) - 2), max(y0, int(ty) - 2)
        ax1, ay1 = min(x1, int(tx + tw) + 2), min(y1, int(ty + th) + 2)
        if ax1 > ax0 and ay1 > ay0:
            mask[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] = 255
            erased += 1
    if erased:
        bgr = cv2.inpaint(crop[:, :, ::-1].copy(), mask, 7, cv2.INPAINT_TELEA)
        crop = bgr[:, :, ::-1]
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(dest, format="PNG")
    return {"file": dest.name, "region": [x0, y0, x1 - x0, y1 - y0], "text_boxes_erased": erased}
