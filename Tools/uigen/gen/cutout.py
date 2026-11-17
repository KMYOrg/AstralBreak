"""컨셉 픽셀 직접 오리기 (1b 후속 H — 설계 §11 'H 설계'. 창작은 codex, 매핑은 결정적).

G2 사람 눈(11-16): 상용 게임 화면 두 장은 배치 · 크기 · 글자는 맞았지만 선이 끊기고 테두리가 흐리고 장식이 잘리고 띠 무늬가 단색 상자가 됐다.
원인은 에셋 확보였다 — codex 가 요소를 다시 그리고(얇은 선 · 빛 가장자리가 흐려지거나 끊김), 안쪽을 한 색으로 칠하고(옮겨 심기는 실루엣
IoU 0.55 ~ 0.70 < 0.85 로 물러남), 텍스처를 위젯 상자로 되잘랐다(상자 밖 장식이 잘림). 그래서 컨셉에 보이는 요소는 컨셉 픽셀을 오려 쓴다:

  입력 종류(normalize 가 판정 — classify): ⓐ transparent — 알파 그대로 · ⓑ flat — 테두리 띠가 한 색(배경 키): 단단한 실루엣(키와 크게 다른
    픽셀 덩어리의 윤곽을 채운 것) 안은 불투명, 밖의 번짐 · 반투명은 배경색 언믹싱(α = 채널마다 키에서 끝값까지의 비 중 최대, 색 = K + (P − K) / α)
    · ⓒ scene — 합성 스크린샷: 실루엣은 GrabCut(위젯 상자 + codex 실루엣 '아마 전경' · 장식선 '확실한 전경' 시드) + 가이드 필터 가장자리,
    색은 컨셉 픽셀 그대로(장면이 섞인 채 굽는다 — 사용자 결정 11-16: 반투명 언믹싱 실험은 넣지 않음, 기록만).
  넘침(overhang): 알파 덩어리가 위젯 상자 밖으로 이어지고 그 자리가 다른 '그리는' 위젯 상자가 아니면 텍스처 상자를 넓힌다
    (그리는 법은 refine 의 장식 Image — 사용자 결정 (가')).
  가려진 자리(글자 · 자식 이미지 · 런타임 이미지): concept_pixels 의 글자 구멍 + 줄 보간(알파 채널도 같이 보간). 글자 없는 판(inputs
    concept_notext — make_concept --text-free)이 있으면 글자 구멍만 그 판 픽셀로(요소마다 ±3 px 재정합 · 어긋나면 줄 보간으로 물러남).
같은 입력 → 같은 바이트(GrabCut 의 k-means 는 OpenCV RNG 씨앗을 고정한다). 값은 잠정이다.
"""
from __future__ import annotations

import numpy as np

from core import color as color_mod

BACKGROUNDS = ("transparent", "flat", "scene")
RING_FRAC = 0.02            # 배경 판정 — 그림 테두리 띠 = 짧은 변의 2 %(최소 RING_MIN px)
RING_MIN = 4
FLAT_TOL = 12               # 테두리 띠 픽셀이 키(중앙값)와 채널 최대 차 ≤ 이것이면 같은 색
FLAT_RATIO = 0.97           # 그 비율 이상이면 단색 배경(ⓑ)
ALPHA_PRESENT = 0.01        # 알파 < 250 픽셀이 이만큼 이상이면 투명 PNG(ⓐ)
LOW_DIFF = 10               # ⓑ — 키와 채널 최대 차가 이 이하면 배경(압축 · 생성 잡음)
SOLID_DIFF = 64             # ⓑ — 이 이상 다른 픽셀 덩어리의 윤곽 안 = 단단한 실루엣(불투명) — 어두운 패널 안쪽도 테두리 윤곽 안이라 불투명
SMALL_PX = 64               # 짧은 변이 이보다 작은 요소는 codex 를 거치지 않는다(설계 H 5 — G2 방패 배지 54 px 는 17 배로 키워 흐림)
GC_ITERS = 5
GC_RING = 2                 # ⓒ — 검색 상자 바깥 띠(위젯 상자 밖에 여유가 있는 변만) = 확실한 배경
GC_MIN_IN = 0.15            # ⓒ — (codex 시드 없을 때) 위젯 상자 안 전경이 이보다 적으면 실패
GC_MIN_SEED_KEPT = 0.4      # ⓒ — (codex 시드 있을 때) 시드 안 전경이 이보다 적으면 실패
GC_MAX_LEAK = 2.0           # ⓒ — 상자 밖(가리지 않은 자리) 전경 / 상자 안 전경이 이보다 크면 실패(장면으로 샘)
GC_SEED_MIN = 0.05          # codex 실루엣이 위젯 상자의 이만큼도 안 덮으면 시드로 안 씀
SEED_ERODE = 3              # GrabCut 결과에 더하는 codex 실루엣 속 = 실루엣을 이만큼 깎은 것(위젯 상자 안만)
GC_SEED_LOW = 0.3           # codex 실루엣이 위젯 상자의 이보다 적게 덮으면 상자 전체를 '아마 전경'으로(요소 일부만 그린 codex)
GC_BOX_SEED_MAX = 128       # 단 짧은 변이 이보다 작은 요소만 — [실측 H run — 조작 안내 엠블럼 650 × 513, 시드 0.11] 상자 전체가 전경이 돼 둘레 연기를
                            # 끌어오고 이웃 상자 모양으로 네모나게 잘렸다(큰 장식은 codex 가 가는 선만 그려도 시드 안만 아마 전경)
RECT_MIN_PX = 100           # 사각 패널 규칙(실루엣 = 상자)은 짧은 변이 이 이상일 때만 — [실측 H run] 96 px R 키 배지가 둘레 빛 선으로 상자를 '꽉 채워' 상자째 쓰였다
BLOCK_PAD = 4               # 다른 그리는 위젯 자리를 이만큼 넓혀 막는다(안티앨리어싱 · 테두리선이 bbox 밖으로 1 ~ 3 px)
SEED_BOUND = 3              # 작은 정사각형 요소의 GrabCut 전경을 묶는 codex 실루엣 넓힘(px)
GF_R = 2                    # 가이드 필터 반경 · eps(회색조 0 ~ 1)
GF_EPS = 1e-3
RECT_FILL = 0.97            # ⓒ — 컨셉 장식선 채운 모양이 위젯 상자의 이만큼 이상 = 사각 패널(실루엣 = 상자, concept_pixels 와 같은 규칙)
OVERHANG_FRAC = 0.3         # 넘침 검색 여유 = 위젯 짧은 변 × 이것(OVERHANG_MIN ~ OVERHANG_MAX px)
OVERHANG_MIN = 16
OVERHANG_MAX = 128
OVERHANG_ALPHA = 0.04       # 이보다 불투명한 픽셀이 넘침 덩어리
OVERHANG_MIN_PX = 40        # 넘침 픽셀이 이보다 적으면 넘침 없음(가장자리 잡음)
OVERHANG_MIN_EXTENT = 4     # 위젯 상자 밖으로 이만큼(px) 안 나가면 넘침 없음
SEARCH_PAD = 8              # 넘침을 안 볼 때도 GrabCut 이 상자 둘레 장면을 배경으로 배우게 두는 여유
EDGE_FRAC = 0.04            # concept_pixels.EDGE_FRAC 과 같은 '안쪽' 정의
LINE_NEAR = 3


class CutoutError(ValueError):
    pass


def _dilate(mask, r: int):
    import cv2
    if r <= 0:
        return np.asarray(mask, bool)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(np.asarray(mask, np.uint8), k) > 0


def _erode(mask, r: int):
    return ~_dilate(~np.asarray(mask, bool), r)


def _hex(c) -> str:
    return "#%02X%02X%02X" % tuple(int(round(float(v))) for v in c[:3])


# ---------------------------------------------------------------------------------------------------------------------
# 입력 종류

def classify(arr, override: str | None = "auto") -> dict:
    """컨셉(numpy RGB · RGBA uint8, 원본 해상도) → {kind, auto, source, alpha_ratio, ring_px, ring_uniform, key_color}.
    ⓐ 알파 < 250 픽셀이 ALPHA_PRESENT 이상 → transparent · ⓑ 테두리 띠의 FLAT_RATIO 이상이 키 ± FLAT_TOL → flat · 아니면 scene.
    override(inputs concept_background)가 auto 가 아니면 그것을 쓴다 — 알파가 없는데 transparent 면 CutoutError."""
    a = np.asarray(arr)
    H, W = a.shape[:2]
    rgb = a[..., :3].astype(np.int16)
    alpha = a[..., 3] if a.ndim == 3 and a.shape[2] == 4 else None
    r = max(RING_MIN, int(round(RING_FRAC * min(H, W))))
    ring = np.zeros((H, W), bool)
    ring[:r], ring[-r:], ring[:, :r], ring[:, -r:] = True, True, True, True
    alpha_ratio = float((alpha < 250).mean()) if alpha is not None else 0.0
    if alpha is not None and alpha_ratio >= ALPHA_PRESENT:
        vis = ring & (alpha >= 250)
        key = np.median(rgb[vis], axis=0) if vis.any() else np.zeros(3)
        uniform = 0.0
        auto = "transparent"
    else:
        key = np.median(rgb[ring], axis=0)
        uniform = float((np.abs(rgb[ring] - key[None]).max(axis=1) <= FLAT_TOL).mean())
        auto = "flat" if uniform >= FLAT_RATIO else "scene"
    kind = auto if override in (None, "auto") else override
    if kind not in BACKGROUNDS:
        raise CutoutError(f"concept_background '{override}' is not auto|{'|'.join(BACKGROUNDS)}")
    if kind == "transparent" and alpha is None:
        raise CutoutError("concept_background transparent but the concept has no alpha channel")
    return {"kind": kind, "auto": auto, "source": "auto" if override in (None, "auto") else "inputs", "alpha_ratio": round(alpha_ratio, 4),
            "ring_px": r, "ring_uniform": round(uniform, 4), "key_color": _hex(key), "key": [int(round(float(v))) for v in key]}


def flat_unmix(rgb, key) -> tuple[np.ndarray, np.ndarray, dict]:
    """ⓑ 단색 배경 → (곧은 색 float HxWx3, 알파 0 ~ 1, 기록). 단단한 실루엣 = 키와 SOLID_DIFF 이상 다른 픽셀(5×5 닫기)의 바깥 윤곽을 채운 것
    중 키와 LOW_DIFF 넘게 다른 픽셀(윤곽 안이라도 키 그대로인 구멍은 배경이 비치는 자리) → 알파 1. 그 밖은 색→알파(GIMP 'color to alpha'):
    채널마다 P > K 면 (P − K) / (255 − K), 아니면 (K − P) / K 의 최대 — 키와 LOW_DIFF 이하면 0. 색 = K + (P − K) / α."""
    import cv2
    P = np.asarray(rgb, float)[..., :3]
    K = np.asarray(key, float).reshape(1, 1, 3)
    diff = np.abs(P - K).max(axis=2)
    up = np.where(P > K, (P - K) / np.maximum(255.0 - K, 1.0), (K - P) / np.maximum(K, 1.0))
    ac = np.clip(up.max(axis=2), 0.0, 1.0)
    ac[diff <= LOW_DIFF] = 0.0
    hard = cv2.morphologyEx((diff >= SOLID_DIFF).astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    pad = 2
    hp = cv2.copyMakeBorder(hard, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    cnts, _ = cv2.findContours(hp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(hp)
    if cnts:
        cv2.drawContours(filled, cnts, -1, 255, thickness=-1)
    solid = (filled[pad:-pad, pad:-pad] > 0) & (diff > LOW_DIFF)
    alpha = np.where(solid, 1.0, ac)
    safe = np.maximum(alpha, 1e-3)[..., None]
    col = np.where(alpha[..., None] > 1e-3, K + (P - K) / safe, K)
    col = np.clip(col, 0.0, 255.0)
    rec = {"solid_ratio": round(float(solid.mean()), 4), "translucent_ratio": round(float(((alpha > 0) & (alpha < 1)).mean()), 4),
           "background_ratio": round(float((alpha == 0).mean()), 4), "low_diff": LOW_DIFF, "solid_diff": SOLID_DIFF}
    return col, alpha, rec


# ---------------------------------------------------------------------------------------------------------------------
# ⓒ 실루엣 — GrabCut + 가이드 필터

def guided_filter(I, p, r: int = GF_R, eps: float = GF_EPS) -> np.ndarray:
    """회색조 안내 I(0 ~ 1) · 입력 p → 가장자리를 I 에 맞춘 p (He et al. 가이드 필터 — 상자 평균은 cv2.boxFilter, ximgproc 없음)."""
    import cv2
    I = np.asarray(I, np.float64)
    p = np.asarray(p, np.float64)
    k = (2 * r + 1, 2 * r + 1)

    def mean(x):
        return cv2.boxFilter(x, cv2.CV_64F, k, borderType=cv2.BORDER_REFLECT)
    mI, mp = mean(I), mean(p)
    a = (mean(I * p) - mI * mp) / (mean(I * I) - mI * mI + eps)
    b = mp - a * mI
    return mean(a) * I + mean(b)


def rect_panel(rgb_box) -> tuple[bool, float]:
    """위젯 상자 컨셉 조각의 장식선 채운 모양이 상자의 RECT_FILL 이상인가(사각 패널) — concept_pixels.transplant 와 같은 규칙."""
    from gen import fidelity
    shape, _ = fidelity.fill_shape(fidelity.line_mask(np.asarray(rgb_box)[..., :3]))
    fill = round(float(shape.mean()), 4)
    return fill >= RECT_FILL, fill


def grabcut_alpha(rgb, box, seed=None, blocked=None) -> tuple[np.ndarray, dict]:
    """ⓒ — 검색 조각 rgb(uint8 HxWx3) · 위젯 상자 box(조각 좌표 [x0, y0, x1, y1]) · seed(codex 알파 0 ~ 1, 조각 크기 · 없으면 None) ·
    blocked(다른 그리는 위젯 자리 — 둘레 장면 중앙값으로 칠해 확실한 배경으로, 이웃 UI 색을 배경 모형이 배우지 않게) → (알파 0 ~ 1, 기록).
    시드: 상자 안 = 아마 전경(codex 실루엣이 있으면 그 안만, 밖은 아마 배경) · 상자 안 장식선(codex 가 있으면 그 둘레만) = 확실한 전경 ·
    상자 밖 = 아마 배경 · 검색 조각 바깥 띠(여유 있는 변) = 확실한 배경. 실패(상자 안 전경 < GC_MIN_IN · 장면으로 샘 > GC_MAX_LEAK)는 CutoutError."""
    import cv2
    from gen import fidelity
    img = np.ascontiguousarray(np.asarray(rgb, np.uint8)[..., :3]).copy()
    H, W = img.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in box)
    inbox = np.zeros((H, W), bool)
    inbox[y0:y1, x0:x1] = True
    init = np.full((H, W), cv2.GC_PR_BGD, np.uint8)
    rec: dict = {}
    seed_m = None
    if seed is not None:
        seed_m = np.asarray(seed, float) > 0.5
        cover = float((seed_m & inbox).sum() / max(1, inbox.sum()))
        rec["seed_cover"] = round(cover, 4)
        if cover < GC_SEED_MIN:
            seed_m = None
    init[inbox] = cv2.GC_PR_FGD
    thin = seed_m is not None and int((_erode(seed_m, SEED_ERODE) & inbox).sum()) < 0.2 * max(1, int((seed_m & inbox).sum()))
    if thin:
        rec["seed_thin"] = True       # 가는 고리(안쪽을 지운 테두리)는 침식하면 사라진다 — 상자 전체 시드로 [실측 H 오프라인 — 파티 HUD HP 프레임]
    low = seed_m is not None and rec["seed_cover"] < GC_SEED_LOW and min(x1 - x0, y1 - y0) < GC_BOX_SEED_MAX
    if seed_m is not None and (low or thin):
        # codex 실루엣이 상자를 조금만 덮으면(요소 일부만 그림) 상자 안 전체 = 아마 전경, 실루엣 속(침식) = 확실한 전경 — codex 가 빠뜨린 부분을 색 모형이
        # 되찾게 [실측 H 오프라인 — G2 파티 HUD 검 아이콘: 시드 0.138, 시드 밖을 '아마 배경'으로 두자 둘레 청록 마름모가 통째로 빠졌다]
        init[inbox & _erode(seed_m, SEED_ERODE)] = cv2.GC_FGD
        rec["seed"] = "widget box (probable foreground) + eroded codex silhouette (sure foreground) — the silhouette covers little of the box or is thin"
        rec["box_seeded"] = True
    elif seed_m is not None:
        # 그 밖에는 실루엣 안 = 아마 전경, 상자 안 나머지 = 아마 배경 — 상자 전체를 전경으로 두면 둘레 장면(엠블럼 뒤 연기 · 이웃 띠 조각)까지 끌려왔다
        init[inbox & ~seed_m] = cv2.GC_PR_BGD
        init[inbox & _erode(seed_m, SEED_ERODE)] = cv2.GC_FGD
        rec["seed"] = "codex silhouette (probable foreground, eroded core sure) inside the widget box"
    else:
        rec["seed"] = "widget box (probable foreground)"
    lines = fidelity.line_mask(img) & inbox
    if seed_m is not None:
        lines &= _dilate(seed_m, 3)
    init[lines] = cv2.GC_FGD
    b = GC_RING
    sides = {"top": y0 > b, "bottom": H - y1 > b, "left": x0 > b, "right": W - x1 > b}
    if sides["top"]:
        init[:b, :] = cv2.GC_BGD
    if sides["bottom"]:
        init[-b:, :] = cv2.GC_BGD
    if sides["left"]:
        init[:, :b] = cv2.GC_BGD
    if sides["right"]:
        init[:, -b:] = cv2.GC_BGD
    if blocked is not None:
        bl = np.asarray(blocked, bool) & ~inbox
        if bl.any():
            free = ~inbox & ~bl
            fill = np.median(img[free], axis=0) if free.any() else np.median(img.reshape(-1, 3), axis=0)
            img[bl] = fill.astype(np.uint8)
            init[bl] = cv2.GC_BGD
            rec["blocked_px"] = int(bl.sum())
    if not ((init == cv2.GC_BGD) | (init == cv2.GC_PR_BGD)).any():
        raise CutoutError("GrabCut has no background sample around the widget box")
    rec.update(lines_px=int(lines.sum()), bgd_ring=[k for k, v in sides.items() if v])
    cv2.setRNGSeed(0)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img[..., ::-1].copy(), init, None, bgd, fgd, GC_ITERS, cv2.GC_INIT_WITH_MASK)
    fg = (init == cv2.GC_FGD) | (init == cv2.GC_PR_FGD)
    bw, bh = x1 - x0, y1 - y0
    if seed_m is not None and not rec.get("box_seeded") and min(bw, bh) < GC_BOX_SEED_MAX and max(bw, bh) < COMPACT_ASPECT * min(bw, bh):
        # 작은 정사각형 요소(키 배지 · 아이콘)는 상자 안 전경을 codex 실루엣(+SEED_BOUND) 안으로 — 둘레 색이 아이콘 테두리와 비슷해 상자 모서리까지
        # 전경이 돼 네모 조각으로 보였다 [실측 H 끝 run 2차 — 조작 안내 마우스 · 스페이스 키 아이콘 상자 안 전경 0.98]
        fg = (fg & ~inbox) | (fg & inbox & _dilate(seed_m, SEED_BOUND))
        rec["bounded_by_seed"] = True
    fin = int((fg & inbox).sum())
    in_ratio = fin / max(1, int(inbox.sum()))
    leak = float((fg & ~inbox).sum() / max(1, fin))
    rec.update(in_box_ratio=round(in_ratio, 4), leak_ratio=round(leak, 4))
    if seed_m is not None and not rec.get("box_seeded"):
        # codex 실루엣이 테두리 고리면(안쪽을 지우라는 따오기) 상자 안 전경이 원래 적다 — 실패는 '시드의 대부분을 버림'으로 본다
        # [실측 H 오프라인 — G2 파티 HP 프레임: 상자 안 0.114 를 실패로 봤다]
        kept = float((fg & seed_m & inbox).sum() / max(1, int((seed_m & inbox).sum())))
        rec["seed_kept"] = round(kept, 4)
        if kept < GC_MIN_SEED_KEPT:
            raise CutoutError(f"GrabCut kept only {kept:.3f} of the codex silhouette (< {GC_MIN_SEED_KEPT})")
    elif in_ratio < GC_MIN_IN:
        raise CutoutError(f"GrabCut kept only {in_ratio:.3f} of the widget box (< {GC_MIN_IN})")
    if leak > GC_MAX_LEAK:
        raise CutoutError(f"GrabCut leaked into the scene ({leak:.2f} × the in-box foreground outside the box)")
    gray = color_mod.srgb_to_lab(np.asarray(rgb, float)[..., :3])[..., 0] / 100.0
    soft = np.clip(guided_filter(gray, fg.astype(float)), 0.0, 1.0)
    soft[_erode(fg, GF_R + 1)] = 1.0
    soft[~_dilate(fg, GF_R + 1)] = 0.0
    return soft, rec


# ---------------------------------------------------------------------------------------------------------------------
# 넘침 · 합치기

def search_box(box, canvas, overhang: bool) -> list[int]:
    """위젯 상자(reference [x, y, w, h]) → 알파 · 넘침을 볼 상자 [x0, y0, x1, y1](캔버스 안)."""
    x, y, w, h = (float(v) for v in box)
    m = int(round(min(OVERHANG_MAX, max(OVERHANG_MIN, OVERHANG_FRAC * min(w, h))))) if overhang else SEARCH_PAD
    W, H = int(canvas[0]), int(canvas[1])
    return [max(0, int(np.floor(x)) - m), max(0, int(np.floor(y)) - m), min(W, int(np.ceil(x + w)) + m), min(H, int(np.ceil(y + h)) + m)]


def overhang(alpha, box, blocked) -> tuple[np.ndarray, dict]:
    """alpha(검색 조각) · box(조각 좌표 [x0, y0, x1, y1]) · blocked(다른 그리는 위젯 자리) → (상자 밖에 남길 마스크, 기록).
    상자 안에 닿는 알파 덩어리(> OVERHANG_ALPHA, 8-연결 — 상자 안 ∪ 가리지 않은 바깥에서 셈) 중 상자 밖 · 가리지 않은 부분."""
    import cv2
    a = np.asarray(alpha, float)
    H, W = a.shape
    x0, y0, x1, y1 = (int(v) for v in box)
    inbox = np.zeros((H, W), bool)
    inbox[y0:y1, x0:x1] = True
    free = ~inbox & ~np.asarray(blocked, bool)
    cand = (a > OVERHANG_ALPHA) & (inbox | free)
    _, lab = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    ids = np.unique(lab[inbox & cand])
    keep = np.isin(lab, ids[ids > 0]) & free
    px = int(keep.sum())
    if px < OVERHANG_MIN_PX:
        return np.zeros((H, W), bool), {"px": px, "used": False}
    ys, xs = np.where(keep | inbox)
    bb = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    extent = max(x0 - bb[0], y0 - bb[1], bb[2] - x1, bb[3] - y1)
    if extent < OVERHANG_MIN_EXTENT:   # 가장자리 빛 1 ~ 3 px 는 장식 Image 를 따로 둘 만큼이 아니다([실측 H 오프라인] 전투 HUD 게이지 프레임 1 px)
        return np.zeros((H, W), bool), {"px": px, "used": False, "extent_px": extent}
    return keep, {"px": px, "used": True, "box": bb, "extent_px": extent}


FILL_LIKE_FRAC = 0.15       # 테두리에 이어진 '장식선' 덩어리가 실루엣 넓이의 이만큼을 넘으면 선이 아니라 밝은 채움(파란 띠 등) — 테두리 띠만 장식선으로


KEEP_DEPTH_FRAC = 0.25      # 지키는 테두리 장식선 = 보이는 윤곽에서 짧은 변 × 이것 안(모서리 장식은 안, 띠 가운데 경계선 · 글자는 밖)


def frame_keep_near_edge(keep, vis) -> np.ndarray:
    """frame_keep 을 보이는 윤곽(vis — 알파 > SOURCE_ALPHA 모양) 가장자리에서 KEEP_DEPTH_FRAC 안으로 — [실측 H — UI 만 컨셉 두 톤 띠] 띠 가운데
    밝은 경계선이 띠 끝 테두리 띠에 닿아 '장식선'으로 지켜지고, 거기 붙은 첫 글자 획('돌' · '공' · '점' · '택')까지 구멍에서 빠져 줄무늬가 번졌다."""
    import cv2
    from gen import fidelity
    bb = fidelity.bbox_of(vis)
    if not bb:
        return keep
    P = 8
    dist = cv2.distanceTransform(cv2.copyMakeBorder(np.asarray(vis, np.uint8), P, P, P, P, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[P:-P, P:-P]
    return np.asarray(keep, bool) & (dist <= KEEP_DEPTH_FRAC * min(bb[2], bb[3]))


def frame_keep(rgb, shape, edge_px: float) -> np.ndarray:
    """글자 구멍 · 줄 보간이 지키는 테두리 장식선 — concept_pixels.frame_lines(테두리 띠에 닿는 장식선 덩어리)와 같되, 덩어리가 실루엣의
    FILL_LIKE_FRAC 를 넘으면 그 덩어리는 테두리 띠(edge_px + 2) 안만. [실측 H 오프라인 — G2 조작 안내] 밝은 청록 띠 전체가 장식선 판정(L* ≥ 45 ·
    C* ≥ 20)이라 띠 위 흰 글자('어빌리티' · '링크 어택')가 덩어리에 묻혀 구멍이 안 뚫렸고, 줄 보간이 띠 전체를 피해 먼 픽셀로 흰 줄을 칠했다."""
    import cv2
    from gen import concept_pixels as cp
    from gen import fidelity
    shape = np.asarray(shape, bool)
    lm = cv2.dilate(fidelity.line_mask(rgb).astype(np.uint8), np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(lm, connectivity=8)
    ring = cp.edge_ring(shape, edge_px)
    ids = np.unique(lab[ring & (lm > 0)])
    ids = ids[ids > 0]
    big = [i for i in ids if stats[i, cv2.CC_STAT_AREA] > FILL_LIKE_FRAC * max(1, int(shape.sum()))]
    keep = np.isin(lab, [i for i in ids if i not in big])
    if big:
        keep |= np.isin(lab, big) & ring
    return keep


TOPHAT_MIN = 14.0           # 글자 상자 안 가는 획 = 밝기(L*)의 흰 · 검은 탑햇이 이보다 큰 픽셀
TOPHAT_K = 0.3              # 탑햇 커널 = 글자 상자 높이 × 이것(획 폭보다 크게, 최소 7 px)
TOPHAT_GROW = 3


def glyph_holes(rgb, texts, keep, ink_recs=()) -> tuple[np.ndarray, list[dict]]:
    """글자 상자 안의 가는 획(밝은 획 + 어두운 외곽선) — L* 의 흰 탑햇 · 검은 탑햇 > TOPHAT_MIN 을 TOPHAT_GROW 넓힌 것(keep 은 뺌).
    text_ink 는 상자 안 밝기를 둘로 갈라 글자 쪽을 고르는데, 두 톤 띠(위 밝은 청록 · 아래 짙은 파랑) 위 흰 글자는 위쪽 띠까지 같은 쪽이 돼 획의
    절반만 잡았다 [실측 H 오프라인 — G2 조작 안내 '돌진 공격' 위 절반 · '링크 어택' 흐린 자국]. 탑햇은 배경 톤과 무관하게 획 폭보다 가는 것만 본다.
    빛 글자는 analyze 가 상자를 사방 빛 크기만큼 넓혔으므로(fidelity.region_report 와 같게) 원래 줄 상자(t['glow_box'] — 빛만큼 줄인 것)에서 본다."""
    import cv2
    from gen import concept_pixels as cp
    col = np.asarray(rgb, float)[..., :3]
    H, W = col.shape[:2]
    L = color_mod.srgb_to_lab(col)[..., 0].astype(np.float32)
    out = np.zeros((H, W), bool)
    recs = []
    for t in texts:
        x, y, w, h = (float(v) for v in t["box"])
        g = min(float(t.get("glow_orig") or 0), 0.25 * min(w, h))
        x, y, w, h = x + g, y + g, w - 2 * g, h - 2 * g
        p = cp.HOLE_PAD
        x0, y0, x1, y1 = max(0, int(x) - p), max(0, int(y) - p), min(W, int(np.ceil(x + w)) + p), min(H, int(np.ceil(y + h)) + p)
        if x1 - x0 < 6 or y1 - y0 < 6:
            continue
        ks = max(7, int(round(TOPHAT_K * h)) | 1)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks))
        sub = L[y0:y1, x0:x1]
        m = (cv2.morphologyEx(sub, cv2.MORPH_TOPHAT, k) > TOPHAT_MIN) | (cv2.morphologyEx(sub, cv2.MORPH_BLACKHAT, k) > TOPHAT_MIN)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        small = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] < 6]
        if small:
            m &= ~np.isin(lab, small)
        m = _dilate(m, TOPHAT_GROW) & ~_dilate(np.asarray(keep, bool)[y0:y1, x0:x1], 2)
        out[y0:y1, x0:x1] |= m
        recs.append({"widget": t.get("id"), "kernel_px": ks, "tophat_px": int(m.sum())})
    return out, recs


GLOW_GROW_FRAC = 0.2        # 글자 구멍의 빛 넓힘 상한 = 요소 짧은 변 × 이것
HOLE_MAX_FRAC = 0.8         # 탑햇 · 상자 전체 구멍이 요소 모양의 이만큼을 넘으면 쓰지 않는다(메울 원천이 없음)
COMPACT_ASPECT = 1.5        # 긴 변 < 짧은 변 × 이것이면 정사각에 가까운 요소 — 구멍을 inpaint 로
TEXT_RECT_PAD = 2           # 글자 획 사각형 구멍의 여유(px)
TEXT_RECT_SIDE_K = 0.5      # 글자 사각형 구멍의 가로 여유 = 획 높이 × 이것
SOURCE_ALPHA = 0.05         # 구멍 메우기 원천 = 이보다 불투명한 픽셀
FILL_SEARCH = 12            # concept_pixels.FILL_SEARCH 와 같다 — 줄 보간이 구멍 끝에서 원천을 찾는 거리


def fill_holes(rgb, alpha, hole, valid, inpaint_only: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """구멍(hole)을 줄마다 좌우 가장 가까운 원천(valid · FILL_SEARCH px 안) 3 개 중앙값 사이 직선 보간 — 색 · 알파 같이(concept_pixels.row_fill 과 같은 생각,
    안쪽 빛은 세로 단면이라 줄 밝기가 남는다). 양쪽 다 원천이 없는 줄 조각은 inpaint(Telea — 원천만 쓰게 원천 밖도 가림)로.
    inpaint_only(작은 요소)면 전부 inpaint — [실측 H 오프라인 — 54 px 방패 배지] 줄 보간이 밝은 베벨 · 어두운 외곽선 사이를 이어 가로 줄무늬가 됐다."""
    import cv2
    col = np.asarray(rgb, float)
    a = np.asarray(alpha, float)
    H, W = a.shape
    valid = np.asarray(valid, bool) & ~np.asarray(hole, bool)
    rgba = np.dstack([col, a * 255.0])
    out = rgba.copy()
    if not hole.any():
        return out[..., :3], np.clip(out[..., 3] / 255.0, 0.0, 1.0)
    fb = None

    def fallback():
        nonlocal fb
        if fb is None:
            m = (~valid).astype(np.uint8) * 255
            c8 = np.clip(np.round(col), 0, 255).astype(np.uint8)
            a8 = np.clip(np.round(a * 255.0), 0, 255).astype(np.uint8)
            if valid.any():
                fc = cv2.inpaint(c8[..., ::-1].copy(), m, 5, cv2.INPAINT_TELEA)[..., ::-1]
                fa = cv2.inpaint(a8, m, 5, cv2.INPAINT_TELEA)
            else:
                fc, fa = c8, a8
            fb = np.dstack([fc.astype(float), fa.astype(float)])
        return fb

    def side(y, start, step):
        got, x = [], start
        while 0 <= x < W and abs(x - start) <= FILL_SEARCH and len(got) < 3:
            if valid[y, x]:
                got.append(rgba[y, x])
            x += step
        return np.median(got, axis=0) if got else None
    if inpaint_only:
        out[hole] = fallback()[hole]
        return out[..., :3], np.clip(out[..., 3] / 255.0, 0.0, 1.0)
    for y in range(H):
        xs = np.where(hole[y])[0]
        if len(xs) == 0:
            continue
        for run in np.split(xs, np.where(np.diff(xs) > 1)[0] + 1):
            lft, rgt = side(y, int(run[0]) - 1, -1), side(y, int(run[-1]) + 1, 1)
            if lft is None and rgt is None:
                out[y, run] = fallback()[y, run]
                continue
            lft = rgt if lft is None else lft
            rgt = lft if rgt is None else rgt
            t = (np.arange(len(run)) + 1) / (len(run) + 1)
            out[y, run] = lft[None] * (1 - t[:, None]) + rgt[None] * t[:, None]
    return out[..., :3], np.clip(out[..., 3] / 255.0, 0.0, 1.0)


NOTEXT_SHIFT = 6            # 글자 없는 판 — 요소마다 이 범위(px) 이동을 탐색해 구멍 둘레가 가장 잘 맞는 자리를 쓴다(fill_from 은 사방 이만큼 큰 조각).
                            # [실측 H2 오프라인 — 조작 안내] 전역 정합 뒤에도 왼쪽 띠 −1 ~ −3 · 오른쪽 띠 +3 ~ +4(codex 가 그림을 가로로 살짝 늘림) → ±3 은 끝에 걸렸다
NOTEXT_RING = 6             # 맞춤을 재는 구멍 둘레 띠(구멍 밖 px, 보이는 픽셀만)
NOTEXT_TIE = 0.5            # 가장 작은 차와 이만큼(또는 NOTEXT_TIE_REL 비) 안의 이동은 같다고 보고 가장 작은 이동을 고른다
NOTEXT_TIE_REL = 0.05
NOTEXT_MAX_DIFF = 24.0      # 둘레 띠 평균 차(미리 곱한 색 0 ~ 255, 채널 평균)가 이보다 크면 같은 그림으로 안 보고 예전 메우기로 물러남 —
                            # [실측 H2 — 조작 안내] 띠 2.4 ~ 14.3 · 엠블럼 7 ~ 8 · 키 배지 15.5 ~ 18.6(테두리가 날카로워 1 px 차가 크다 — 18 이면 E 배지가
                            # 오갔다), 다른 그림(잡음)은 수십
NOTEXT_MIN_RING = 20        # 둘레 띠가 이보다 작으면 맞춤을 잴 수 없다 — 물러남
NOTEXT_GROW = 2             # 섞는 마스크 = 글자 구멍을 이만큼 넓혀
NOTEXT_BLUR = 1.2           # 이 시그마로 흐린 것(구멍 안은 1)
NOTEXT_STROKE_GAP = 2       # 획 둘레로 잴 때 획에서 이만큼 떨어진 곳부터(안티앨리어싱 · 가는 빛)
GAIN_MIN, GAIN_MAX = 0.25, 4.0   # 판 알파 맞춤 비(컨셉 ÷ 판)의 범위
GAIN_SCALE = 60.0           # fill_holes(0 ~ 255 색 통로)로 비를 보간할 때 곱하는 수 — GAIN_MAX × 이것 ≤ 255
GAIN_SMOOTH = 4.0           # 이은 비를 펴는 가우시안 시그마(px)
GAIN_SKIP = 0.02            # 둘레 비가 전부 1 ± 이것 안이면 맞추지 않는다(판과 컨셉의 알파가 같다 — ⓑ 언믹싱판 등)


def _notext_shift(col, a, glyph, hole, nt_col, nt_a, strokes=None) -> dict:
    """글자 없는 판 조각(사방 NOTEXT_SHIFT 큰 것)을 ±NOTEXT_SHIFT 옮겨 가며 구멍 둘레 띠(구멍 밖 NOTEXT_RING px · 컨셉에서 보이는 픽셀 · 다른 구멍 아님)의
    미리 곱한 색 평균 차가 가장 작은 이동을 찾는다 → {shift, diff, ring_px, best_diff, ring_from}. 가장 작은 차와 NOTEXT_TIE 안이면 더 작은 이동(결정적).
    구멍 둘레가 NOTEXT_MIN_RING 보다 작으면 획(strokes) 둘레로 잰다 — [실측 H3 R20261117_090812 — 투명 컨셉 E 키 배지] analyze 글자 상자가 배지보다 커
    글자 사각형 구멍이 배지 전체라 둘레가 0 px → 판을 못 쓰고 inpaint 방사 무늬가 남았다. 사각형 안이라도 획 밖은 컨셉 픽셀(배지 원판)이다."""
    H, W = a.shape
    P = NOTEXT_SHIFT
    ring = _dilate(glyph, NOTEXT_RING) & ~hole & (a > SOURCE_ALPHA)
    n = int(ring.sum())
    ring_from = "hole"
    if n < NOTEXT_MIN_RING and strokes is not None and (strokes & glyph).any():
        s = strokes & glyph
        ring = _dilate(s, NOTEXT_RING + NOTEXT_STROKE_GAP) & ~_dilate(s, NOTEXT_STROKE_GAP) & ~(hole & ~glyph) & (a > SOURCE_ALPHA)
        n, ring_from = int(ring.sum()), "strokes"
    if n < NOTEXT_MIN_RING:
        return {"ring_px": n, "diff": None, "shift": [0, 0], "ring_from": ring_from}
    ref = (col * a[..., None])[ring]
    # 판 알파 수준을 둘레의 컨셉 수준으로 먼저 맞춘 뒤 비교 — 알파 수준 차(뒤에서 _notext_alpha_gain 이 맞춘다)가 '다른 그림' 차로 섞이지 않게
    # [실측 H3 R20261117_095249] 판이 반투명 띠를 더 불투명하게 그려 공격 띠 둘레 차가 20.9(물러남 기준 24 근처)
    na0 = nt_a[P:P + H, P:P + W]
    both = ring & (na0 > SOURCE_ALPHA)
    level = float(np.clip(np.median(a[both] / np.maximum(na0[both], 1e-3)), GAIN_MIN, GAIN_MAX)) if both.sum() >= NOTEXT_MIN_RING else 1.0
    cand = []
    for dy in range(-P, P + 1):
        for dx in range(-P, P + 1):
            c = nt_col[P + dy:P + dy + H, P + dx:P + dx + W]
            al = np.clip(nt_a[P + dy:P + dy + H, P + dx:P + dx + W] * level, 0.0, 1.0)
            cand.append((float(np.abs((c * al[..., None])[ring] - ref).mean()), dx, dy))
    # 가장 작은 차에서 NOTEXT_TIE 안이면 더 작은 이동 — [실측 H2 오프라인 — '점프' 띠] 가로로 완만한 무늬라 −3 (4.20) · −6 (3.97) 처럼 차가 거의 같은
    # 채 범위 끝으로 끌려갔다(잘 안 정해지는 이동은 작게)
    lo = min(d for d, _, _ in cand)
    d, dx, dy = min((c for c in cand if c[0] <= lo + max(NOTEXT_TIE, NOTEXT_TIE_REL * lo)), key=lambda c: (abs(c[1]) + abs(c[2]), c[0], c[1], c[2]))
    return {"ring_px": n, "diff": round(d, 2), "shift": [dx, dy], "best_diff": round(lo, 2), "ring_from": ring_from, "alpha_level": round(level, 3)}


def _notext_alpha_gain(a, n_a, glyph, hole, zone) -> tuple[np.ndarray | None, dict]:
    """판 알파를 컨셉 알파 수준에 맞추는 곱(zone 안) → (비 HxW 또는 None, 기록). 글자 구멍 둘레(구멍 밖 NOTEXT_RING px · 둘 다 보이는 픽셀)의
    컨셉 ÷ 판 알파 비를 줄 보간(fill_holes)으로 구멍 안까지 이어 판 알파에 곱한다 — 판의 무늬 · 경사는 그대로, 수준만 컨셉에.
    [실측 H3 R20261117_090812 — 투명 컨셉] codex 가 글자 없는 판을 그리며 반투명 띠를 더 불투명하게 그렸다(글자 둘레 알파 컨셉 0.85 ~ 0.94 ↔ 판
    0.98 ~ 0.99) → 판으로 메운 글자 자리만 진한 사각 패치로 보였다(회색 바탕). 검정 위에선 거의 안 보인다."""
    ring = _dilate(glyph, NOTEXT_RING) & ~hole & (a > SOURCE_ALPHA) & (n_a > SOURCE_ALPHA)
    n = int(ring.sum())
    if n < NOTEXT_MIN_RING:
        return None, {"alpha_gain": None, "gain_ring_px": n}
    r = np.clip(a / np.maximum(n_a, 1e-3), GAIN_MIN, GAIN_MAX)
    med = float(np.median(r[ring]))
    rec = {"alpha_gain": round(med, 3), "gain_ring_px": n}
    if float(np.percentile(np.abs(r[ring] - 1.0), 90)) < GAIN_SKIP:
        rec["alpha_gain_applied"] = False
        return None, rec
    import cv2
    from gen import fidelity
    holes = zone & ~ring
    # 가로로 긴 구멍(띠 위 글자)은 세로로(위 · 아래 둘레 사이) 잇는다 — 띠는 가로로 옅어져 비도 가로로 변하는데, 줄(가로) 보간은 넓은 글자 사각형의
    # 양끝 비만 직선으로 이어 가운데가 어긋났다 [실측 H3 오프라인 — '돌진 공격' 띠 왼쪽 옅어지는 쪽이 회색으로 · 아래 짙은 반이 진하게]
    hb = fidelity.bbox_of(holes)
    tall = hb is not None and hb[3] > hb[2]
    src = np.dstack([r * GAIN_SCALE] * 3)
    if tall:
        g, _ = fill_holes(src, np.ones_like(a), holes, ring)
    else:
        g, _ = fill_holes(src.transpose(1, 0, 2), np.ones_like(a).T, holes.T, ring.T)
        g = g.transpose(1, 0, 2)
    g = g[..., 0] / GAIN_SCALE
    # 줄마다 따로 이은 비는 줄 사이가 들쭉날쭉해 옅어지는 띠 끝에 가로 줄무늬가 남았다 [실측 H3 오프라인 — '돌진 공격' 띠 왼쪽] → 구멍 · 둘레 안에서
    # 정규화 가우시안으로 2차원으로 편다(밖 값이 섞이지 않게)
    w = (holes | ring).astype(np.float32)
    num = cv2.GaussianBlur((g * w).astype(np.float32), (0, 0), GAIN_SMOOTH)
    den = cv2.GaussianBlur(w, (0, 0), GAIN_SMOOTH)
    g = np.where(holes, num / np.maximum(den, 1e-6), g)
    gain = np.where(zone, np.clip(g, GAIN_MIN, GAIN_MAX), 1.0)
    rec["alpha_gain_applied"] = True
    return gain, rec


def _bridged(base, hole):
    """구멍 픽셀 중 같은 줄의 구멍 구간 양 끝 바로 바깥(또는 같은 열의 위 · 아래)이 둘 다 요소 픽셀(base)인 것 — 요소를 가로지른 구멍(요소 안)."""
    H, W = hole.shape
    out = np.zeros((H, W), bool)
    for m, b in ((hole, base), (hole.T, base.T)):
        h, w = m.shape
        idx = np.broadcast_to(np.arange(w), (h, w))
        left = np.maximum.accumulate(np.where(~m, idx, -1), axis=1)                       # 왼쪽(자기 포함) 가장 가까운 구멍 아닌 픽셀
        right = (w - 1) - np.maximum.accumulate(np.where(~m[:, ::-1], idx, -1), axis=1)[:, ::-1]
        right = np.where(right > w - 1, -1, right)
        rows = np.broadcast_to(np.arange(h)[:, None], (h, w))
        lb = (left >= 0) & b[rows, np.clip(left, 0, w - 1)]
        rb = (right >= 0) & (right <= w - 1) & b[rows, np.clip(right, 0, w - 1)]
        r = m & lb & rb
        out |= r if m is hole else r.T
    return out


def compose(rgb, alpha, texts=(), excludes=(), interior_alpha: float | None = None, lock_lines: bool = False,
            whole_text_boxes: bool = False, clear_boxes=None, hole_alpha: str = "shape", fill_from=None,
            fill_skip=()) -> tuple[np.ndarray, np.ndarray, dict]:
    """텍스처 상자 조각(곧은 색 float HxWx3 · 알파 0 ~ 1) → (색, 알파, 기록) — 가려진 자리 메우기 · 안쪽 알파.
    texts: [{"id", "box" (조각 좌표), "glow"}] · excludes: [[x, y, w, h]] (concept_pixels.text_holes 와 같은 꼴).
    구멍(글자 획 · 자식 이미지)은 줄마다 좌우 성한 픽셀 사이 보간 — 알파도 같이(ⓑ 의 글자 획은 불투명 전경이라 알파도 메워야 한다).
    interior_alpha 가 있으면 실루엣 안쪽(가장자리에서 짧은 변 4 % 안 · 장식선 아님)을 그 알파로(frame · panel_bg — G 와 같은 정의, ⓐ 는 None).
    lock_lines(ⓒ)면 실루엣 둘레 LINE_NEAR px 안 컨셉 장식선을 알파 1 로(가이드 필터가 얇은 선을 깎지 않게).
    whole_text_boxes 면 글자 위젯 상자(+여유) 전체를 구멍으로(OCR 이 구운 글자 자국을 잡았을 때 한 번 더).
    clear_boxes(조각 좌표)는 투명하게 비운다 — 이 요소 속의 런타임 이미지(초상화) 자리, 테두리 장식선은 남김.
    fill_from = (색, 알파 또는 None) — 글자 없는 판(make_concept --text-free)의 같은 조각을 사방 NOTEXT_SHIFT px 크게. 있으면 글자 구멍(획 ∪ 탑햇 ∪
    글자 사각형 — 자식 이미지 · 게이지 구멍(excludes)과 fill_skip 상자는 빼고)만 그 픽셀로: ±NOTEXT_SHIFT 이동 중 구멍 둘레가 가장 맞는 자리,
    경계는 NOTEXT_GROW 넓혀 NOTEXT_BLUR 흐린 마스크로 섞음, 구멍이 요소 대부분이라도 쓴다(too_big 규칙 끔 — 원천이 판). 둘레 차가 NOTEXT_MAX_DIFF
    를 넘으면 판 없이 예전 길(줄 보간 · inpaint)로 다시 하고 기록. 알파가 None(ⓒ)이면 색만 쓴다(알파는 GrabCut 실루엣 그대로)."""
    import cv2
    from gen import concept_pixels as cp
    from gen import fidelity
    col = np.asarray(rgb, float)[..., :3]
    a = np.asarray(alpha, float)
    H, W = a.shape
    sil = a > 0.5
    rec: dict = {}
    if not sil.any():
        raise CutoutError("no opaque silhouette in the texture box")
    use_nt = fill_from is not None
    shape, how = fidelity.fill_shape(sil)
    bb = fidelity.bbox_of(shape) or fidelity.bbox_of(sil)
    edge_px = max(2.0, EDGE_FRAC * min(bb[2], bb[3]))
    vis = fidelity.fill_shape(a > SOURCE_ALPHA)[0] | shape
    fl = frame_keep_near_edge(frame_keep(col, shape, edge_px), vis)
    # 글자 빛 넓힘은 요소 짧은 변의 GLOW_GROW_FRAC 까지 — [실측 H 오프라인 — 파티 HUD 54 px 방패 배지] 빛 13 px 글자 '10' 의 구멍(6 + 1.5 × 13 px)이
    # 배지 전체를 덮어 회색 사각형이 됐다
    cap = max(0.0, (GLOW_GROW_FRAC * min(bb[2], bb[3]) - cp.HOLE_GROW) / cp.HOLE_GLOW_K)
    texts = [{**t, "glow": min(float(t.get("glow") or 0), cap), "glow_orig": float(t.get("glow") or 0)} for t in texts]
    ink_hole, hole_recs = cp.text_holes(col, texts, fl, [], ring=cp.edge_ring(shape, edge_px), drop_frame_touch=True)
    excl_hole, _ = cp.text_holes(col, [], fl, list(excludes))
    hole = excl_hole | ink_hole
    th, th_recs = glyph_holes(col, texts, fl)
    if ink_hole.any():
        # 탑햇 획은 text_ink 구멍에 닿는 덩어리만 — 글자 상자가 요소 폭 전체면 배지 테두리 · 패널 모서리 장식까지 가는 획으로 잡혔다
        # [실측 H run — 조작 안내 R 키 배지 테두리가 지워지고 줄무늬 · 단색 컨셉 체인 패널 아래 모서리 장식이 가로로 번짐]
        n, lab = cv2.connectedComponents(th.astype(np.uint8), connectivity=8)
        ids = np.unique(lab[th & _dilate(ink_hole, 2)])
        th = np.isin(lab, ids[ids > 0])
    strokes = ink_hole | th            # 사각형을 더하기 전 획 — 판 정합을 획 둘레로 잴 때(글자 사각형이 요소 전체인 키 배지)
    # 글자마다 (획 구멍 ∪ 탑햇 획)을 감싸는 사각형을 통째로 구멍으로 — 획 모양 구멍은 조각나 줄 보간이 조각 사이의 글자색 · 이웃 배지 테두리를
    # 원천으로 써 글자 속 가로 줄무늬 · 흐린 회색 네모가 됐다 [실측 H — UI 만 컨셉 run '공격' · '회피']. 사각형 밖 원천은 띠 · 패널 색이라 가로 띠는
    # 줄 보간이 띠의 세로 단면을 그대로 잇는다(글자 위젯이 위를 덮는다). 테두리 장식선은 지킨다.
    rect = np.zeros((H, W), bool)
    widened = {r.get("widget"): r.get("box") for r in hole_recs if r.get("widget") and r.get("box")}
    for t in texts:
        x, y, w, h = (float(v) for v in (widened.get(t.get("id")) or t["box"]))
        p = cp.HOLE_PAD
        x0, y0, x1, y1 = max(0, int(x) - p), max(0, int(y) - p), min(W, int(np.ceil(x + w)) + p), min(H, int(np.ceil(y + h)) + p)
        if x1 <= x0 or y1 <= y0:
            continue
        m = (ink_hole | th)[y0:y1, x0:x1]
        bbm = fidelity.bbox_of(m)
        if bbm:
            # 찾은 획 ∪ 글자 위젯 줄 상자(빛 여백 뺀 것) — text_ink 가 첫 · 끝 글자나 두 톤 띠 경계 줄의 획을 놓치면 그 조각에서 줄 보간 줄무늬가 번졌다
            tx, ty, tw, th_ = (float(v) for v in t["box"])
            gl = min(float(t.get("glow_orig") or 0), 0.25 * min(tw, th_))
            g = TEXT_RECT_PAD
            # 가로는 획 높이의 절반만큼 더 — analyze 글자 상자가 실제 첫 · 끝 글자보다 안쪽에서 시작 · 끝나 그 바깥 조각이 남았다
            # [실측 H — UI 만 컨셉 '돌진 공격' 상자 오차 약 12 px · '링크 어택' 끝 글자]
            gx = max(g, int(round(TEXT_RECT_SIDE_K * bbm[3])))
            rx0 = min(x0 + bbm[0], int(tx + gl)) - gx
            rx1 = max(x0 + bbm[0] + bbm[2], int(np.ceil(tx + tw - gl))) + gx
            ry0 = min(y0 + bbm[1], int(ty + gl)) - g
            ry1 = max(y0 + bbm[1] + bbm[3], int(np.ceil(ty + th_ - gl))) + g
            rect[max(0, ry0):min(H, ry1), max(0, rx0):min(W, rx1)] = True
    th = (th | rect) & ~_dilate(fl, 2)
    # 넓이 기준 = 보이는 픽셀(알파 > SOURCE_ALPHA)의 모양 vis — ⓑ 반투명 띠는 알파 0.5 넘는 부분이 작아 사각형 구멍이 '요소의 80 % 초과'로 오판돼 버려졌다
    area = max(1, int(vis.sum()))

    def too_big(m) -> bool:
        # 구멍이 요소를 거의 다 덮으면 메울 원천이 없다 — [실측 H 오프라인 — 54 px 방패 배지 위 글자 '10'] 탑햇 · 상자 전체 구멍이 배지 전부라 원래 숫자가 남았다
        return int((m & vis).sum()) > HOLE_MAX_FRAC * area
    # 글자 없는 판이 있으면 too_big 규칙은 끈다 — 원천이 판이라 구멍이 요소 대부분이어도 메울 수 있다(판이 물러나면 아래에서 예전 길로 다시)
    if not use_nt and too_big(hole | th):
        rec["tophat_dropped"] = "tophat strokes would cover most of the element — only the text_ink holes"
    else:
        hole |= th
    rec["tophat"] = th_recs
    if whole_text_boxes:
        wide = hole.copy()
        for t in texts:
            x, y, w, h = (float(v) for v in t["box"])
            p = cp.HOLE_PAD
            wide[max(0, int(y) - p):min(H, int(np.ceil(y + h)) + p), max(0, int(x) - p):min(W, int(np.ceil(x + w)) + p)] = True
        wide &= ~_dilate(fl, 2)
        if not use_nt and too_big(wide):
            rec["whole_text_boxes_skipped"] = "the text boxes cover most of the element"
        else:
            hole = wide
    clear = np.zeros((H, W), bool)
    for x, y, w, h in (clear_boxes or []):
        clear[max(0, int(y)):min(H, int(np.ceil(y + h))), max(0, int(x)):min(W, int(np.ceil(x + w)))] = True
    clear &= ~_dilate(fl, 1)
    nt = None
    if use_nt:
        # 글자 구멍 = 구멍 중 자식 이미지 · 게이지 구멍(excludes)과 fill_skip(게이지 막대 — 판에도 채움이 구워져 있다) 밖. 비울 자리도 뺀다
        glyph = hole & ~excl_hole & ~clear
        for x, y, w, h in fill_skip:
            glyph[max(0, int(y)):min(H, int(np.ceil(y + h))), max(0, int(x)):min(W, int(np.ceil(x + w)))] = False
        nt_col = np.asarray(fill_from[0], float)[..., :3]
        nt_a = np.asarray(fill_from[1], float) if fill_from[1] is not None else np.ones(nt_col.shape[:2])
        P = NOTEXT_SHIFT
        if nt_col.shape[:2] != (H + 2 * P, W + 2 * P) or nt_a.shape != (H + 2 * P, W + 2 * P):
            raise CutoutError(f"fill_from must be the texture box grown by {P} px on every side ({nt_col.shape[:2]} for {H}x{W})")
        nrec = {"glyph_px": int(glyph.sum())}
        if glyph.any():
            nrec.update(_notext_shift(col, a, glyph, hole, nt_col, nt_a, strokes=strokes))
        why = None
        if not glyph.any():
            why = "no text hole outside the child image · gauge holes"
        elif nrec["diff"] is None:
            why = f"ring around the text holes is too small to align ({nrec['ring_px']} px < {NOTEXT_MIN_RING})"
        elif nrec["diff"] > NOTEXT_MAX_DIFF:
            why = f"ring difference {nrec['diff']} > {NOTEXT_MAX_DIFF} after the best shift {nrec['shift']} — not the same picture here"
        if why:
            # 판 없이 예전 길로 다시(too_big 규칙도 되살아남) — 판이 어긋난 자리를 그 픽셀로 칠하지 않는다
            o_rgb, o_a, r = compose(rgb, alpha, texts, excludes, interior_alpha=interior_alpha, lock_lines=lock_lines, whole_text_boxes=whole_text_boxes,
                                    clear_boxes=clear_boxes, hole_alpha=hole_alpha)
            r["notext"] = {**nrec, "used": False, "reason": why}
            return o_rgb, o_a, r
        dx, dy = nrec["shift"]
        nt = (nt_col[P + dy:P + dy + H, P + dx:P + dx + W], nt_a[P + dy:P + dy + H, P + dx:P + dx + W], glyph, nrec,
              fill_from[1] is not None)
    # 메우기는 요소 안에서만 — 원천 = 구멍 · 테두리선 둘레 · 비울 자리가 아닌 실루엣 픽셀. 요소 밖 구멍 자리는 알파 0:
    # ⓐ ⓑ(hole_alpha 'shape') 는 글자 획도 불투명 전경이라 '구멍 뺀 실루엣'의 윤곽 밖 = 요소 밖(패널 밖으로 나온 글자),
    # ⓒ('alpha') 는 원래 알파 < 0.5 인 구멍 자리 = 요소 밖 — 윤곽 규칙이면 패널 폭 글자 구멍이 사각 패널 옆 테두리까지 닿아 테두리에 구멍이 났다
    # [실측 H 오프라인 — 전투 HUD 체인 패널 · 파티 HUD 방패 배지]
    # 원천 = 보이는 픽셀(알파 > SOURCE_ALPHA) — ⓑ 의 어두운 반투명 띠는 알파 0.5 미만이라 실루엣 기준이면 원천에서 빠져 먼 밝은 픽셀(배지 테두리)로
    # 칠한 회색 네모가 됐다 [실측 H — UI 만 컨셉 '회피' 띠]
    base = (a > SOURCE_ALPHA) & ~hole & ~clear
    # 작거나 정사각에 가까운 요소(배지 · 아이콘 · 엠블럼)는 inpaint — 줄 보간은 가로로 긴 띠 · 패널(안쪽 빛이 세로 단면)용
    compact = min(bb[2], bb[3]) < SMALL_PX or max(bb[2], bb[3]) < COMPACT_ASPECT * min(bb[2], bb[3])
    out_rgb, out_a = fill_holes(col, a, hole, base & ~_dilate(fl, 1), inpaint_only=compact)
    rec["fill"] = "inpaint (small or compact element)" if compact else "rows (inpaint where no source within reach)"
    if nt is not None:
        # 글자 구멍은 글자 없는 판 픽셀로 — 줄 보간은 띠의 사선 무늬 · 배지 베벨 · 광택 · 날개 장식을 되살리지 못한다 [실측 H — UI 만 컨셉 run
        # 'R173820': 글자 자리 평평한 패치 · R 배지 뭉개짐 · R 옆 흰 얼룩]. 경계는 넓혀 흐린 마스크로 섞어 이음매를 숨긴다(미리 곱한 색으로)
        n_col, n_a, glyph, nrec, with_alpha = nt
        m = cv2.GaussianBlur(_dilate(glyph, NOTEXT_GROW).astype(np.float32), (0, 0), NOTEXT_BLUR).astype(float)
        m = np.clip(np.where(glyph, 1.0, m), 0.0, 1.0)
        m[clear] = 0.0
        # 경계 띠는 이 요소에 보이는 픽셀이 있던 자리에서만 — 빈 자리(이웃 몫으로 뺀 픽셀 · 요소 밖)에 판의 알파를 새로 넣으면 가는 줄이 생긴다
        # [실측 H2 오프라인 — 조작 안내 엠블럼: E 글자 구멍 좌우 가장자리에 회피 띠 알파 0.1 ~ 0.14 세로줄]
        m[~glyph & ~(a > SOURCE_ALPHA)] = 0.0
        if with_alpha:
            gain, grec = _notext_alpha_gain(a, n_a, glyph, hole, m > 0)
            nrec.update(grec)
            if gain is not None:
                n_a = np.clip(n_a * gain, 0.0, 1.0)
            na = m * n_a + (1 - m) * out_a
            pm = m[..., None] * n_col * n_a[..., None] + (1 - m)[..., None] * out_rgb * out_a[..., None]
            out_rgb = np.where(na[..., None] > 1e-4, pm / np.maximum(na, 1e-4)[..., None], out_rgb)
            out_a = na
        else:
            out_rgb = m[..., None] * n_col + (1 - m)[..., None] * out_rgb
        rec["notext"] = {**nrec, "used": True, "blend_px": int((m > 0).sum())}
        rec["fill"] += " · text holes from the text-free concept"
    if hole_alpha == "alpha":
        out_a[hole & (a < 0.5)] = 0.0
    else:
        elem = fidelity.fill_shape(base)[0] if base.any() else shape
        outside = hole & ~_dilate(elem, 1)
        if nt is not None and nt[4]:
            # 글자 없는 판의 알파가 글자 뒤의 정답 — 판으로 메운 글자 구멍은 윤곽 규칙으로 비우지 않는다(판이 투명한 자리는 이미 투명)
            outside &= ~nt[2]
        # 같은 줄(또는 열)에서 구멍 양쪽 바로 옆이 요소 픽셀인 구멍은 요소 안 — [실측 I 오프라인 — 조작 안내 회피 띠] 글자 사각형(E · '회피')이 띠를 위아래로
        # 끝까지 가르자 '구멍 뺀 실루엣'이 두 조각이 돼 그 사이 270 px 가 윤곽 밖으로 비워졌다
        bridged = _bridged(base, hole)
        if (outside & bridged).any():
            rec["hole_bridged_px"] = int((outside & bridged).sum())
        out_a[outside & ~bridged] = 0.0
    out_a[clear] = 0.0
    if clear.any():
        rec["cleared_px"] = int(clear.sum())
    # 장식선 판정은 메운 뒤 색으로 — 메우기 전 색이면 글자 획(장식선 아님)과 밝은 띠(장식선)가 갈려 안쪽 알파가 글자 모양으로 0.9 / 1 이 됐다
    # [실측 H 오프라인 — 조작 안내 '어빌리티' 유령 글자]
    cl = fidelity.line_mask(out_rgb)
    if interior_alpha is not None:
        P = 8
        dist_in = cv2.distanceTransform(cv2.copyMakeBorder(shape.astype(np.uint8), P, P, P, P, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[P:-P, P:-P]
        interior = (dist_in > edge_px) & ~_dilate(cl & shape, 1)
        out_a[interior] = float(interior_alpha)
        rec["interior_ratio"] = round(float(interior.mean()), 4)
        rec["interior_alpha"] = float(interior_alpha)
    if lock_lines:
        locked = cl & _dilate(sil, LINE_NEAR) & ~hole
        out_a[locked] = 1.0
        rec["lines_locked_px"] = int(locked.sum())
    rec.update(shape_from=how, edge_px=round(edge_px, 1), texts=hole_recs, hole_ratio=round(float(hole.mean()), 4),
               whole_text_boxes=bool(whole_text_boxes))
    return out_rgb, out_a, rec


def to_image(rgb, alpha, size):
    """곧은 색 · 알파 → PIL RGBA(size) — 미리 곱한 색과 알파를 따로 늘리고(LANCZOS) 나눈다(투명 자리 색이 가장자리로 번지지 않게)."""
    from PIL import Image
    col = np.asarray(rgb, float)[..., :3]
    a = np.clip(np.asarray(alpha, float), 0.0, 1.0)
    H, W = a.shape
    tw, th = int(size[0]), int(size[1])
    if (tw, th) == (W, H):
        pm, aa = col * a[..., None], a
    else:
        def rs(ch):
            return np.asarray(Image.fromarray(ch.astype(np.float32), "F").resize((tw, th), Image.Resampling.LANCZOS), float)
        pm = np.dstack([rs(col[..., i] * a) for i in range(3)])
        aa = np.clip(rs(a), 0.0, 1.0)
    out = np.where(aa[..., None] > 1e-4, pm / np.maximum(aa, 1e-4)[..., None], 0.0)
    rgba = np.dstack([np.clip(out, 0, 255), aa * 255.0]).round().astype(np.uint8)
    return Image.fromarray(bleed_transparent_rgb(rgba), "RGBA")


def bleed_transparent_rgb(rgba):
    """완전 투명(알파 0) 픽셀의 색을 가장 가까운 보이는 픽셀 색으로 — 알파는 그대로라 1:1 그림은 같고, 엔진이 텍스처를 늘릴 때(곧은 알파 이중선형)
    가장자리에 검정이 섞이지 않는다. [실측 I — 조작 안내 R20261117_135820 디자이너 확대] 투명 픽셀 색이 (0, 0, 0)이라 텍스처 경계마다 검은 절취선."""
    import cv2
    a = rgba[..., 3]
    empty = a == 0
    if not empty.any() or empty.all():
        return rgba
    _, lab = cv2.distanceTransformWithLabels(empty.astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    src = np.argwhere(~empty)                        # 라벨 = 보이는 픽셀의 행 우선 순서(1 부터)
    idx = lab[empty] - 1
    out = rgba.copy()
    out[empty, :3] = rgba[src[idx, 0], src[idx, 1], :3]
    return out
