"""자동 차이 진단 (1b 후속 J-b) — verify 의 appearance 게이트 · report.recorded.diagnosis.

1b 후속 A ~ I 는 게이트(상자) · 1:1 합성 평균 지표만 보고 '통과'를 말했고, 사람이 매번 새 결함을 찾았다. 평균은 국소 결함을 묻는다
[실측 R20261117_154442 — 렌더 ↔ 컨셉 평균 ΔE00 0.54 인데 7 × 7 창 국소 지도의 위 자리는 사용자가 찾은 결함 그대로: E · T 배지 양옆 선 ·
'돌진 공격' 10.5 px 어긋남]. 그래서 자리마다 · 여러 배율에서 레퍼런스와 맞대고, 결함마다 차이가 처음 생긴 단계를 짚는다.

비교 셋(레퍼런스 = 변환 · 정규화된 컨셉 — ⓐ ⓑ 는 곧은 색 × 알파):
  ① 검정 위: 렌더(force_visible 1:1) ↔ 레퍼런스 — 배치 · 엔진 · 글자까지 보인다.
  ② 회색 위: 최종 텍스처 합성(gen/backdrop — 렌더 상자 · 그리는 순서) ↔ 레퍼런스 — 검정이 숨기는 알파 결함(이중 · 구멍)이 보인다.
  ③ 3 배: 텍스처를 Slate 처럼 따로 늘린 합성 ↔ 레퍼런스 한 장 늘림 — 텍스처 경계 절취선(zoom_seams).
  ④ 글자: 렌더 글자 획 ↔ 컨셉 글자 획을 그림끼리(측정값이 아니라 마스크끼리) — 컨셉 획 = 글자 없는 판과 다른 픽셀 중 글자색 쪽 핵심 획(빛 번짐 제외),
     렌더 획 = 렌더와 글자 없는 합성이 다른 픽셀 중 같은 쪽. 크기 · 위치 · 굵기 · 색 · 외곽선(빛).
국소 결함 = 7 × 7 창 평균 ΔE00 > local_de 인 자리 덩어리(넓이 ≥ min_area) — 글자 자리 · 레퍼런스에 안 그려진 상태(시작 때 숨은 위젯 중 컨셉에 없는 것 —
그 자리는 그 위젯을 뺀 합성으로 비교)는 뺀다.
원인 단계: 1:1 텍스처 합성에도 있으면 '텍스처'(그 자리 위젯 · 알파 이중 · 구멍 · 글자 구멍 메우기), 합성엔 없고 렌더에만 있으면 '배치'(위상 상관 이동) 또는
'엔진'(그리기 · 압축), 3 배에서만이면 '경계', 글자 상자면 '글자'(무엇이 다른지). 변환 컨셉 ↔ 원본 이동은 기록만.
고칠 수 있는 것: 글자 크기 · 위치 · 굵기(글자 맞춤 — 결정적) — 나머지는 리포트로 실패. 값은 잠정(J-b 보정 — 설계 §11 'J').
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from core import color
from gen import backdrop

WIN = 7
DEFAULTS = {
    "local_de": 10.0,        # 7 × 7 창 평균 ΔE00 문턱
    "min_area": 24,          # 결함 덩어리 최소 넓이(px)
    "text_h_tol": 0.08,      # 글자 획 높이 비 |1 − 비| 허용
    "text_pos_px": 3.0,      # 글자 중심 차 허용(px) — 글자 높이 × text_pos_k 와 큰 쪽
    "text_pos_k": 0.1,
    "text_weight": 1.3,      # 획 밀도 비(렌더 ÷ 컨셉) 허용 — 굵기가 둘(Regular · Bold, 밀도 비 약 1.52)뿐이라 반 단계(1.233) + 잡음 0.05(로그) — 그 사이 굵기 컨셉은 어느 쪽도 1.22 안에 못 든다[실측 J R20261117_173214 어빌리티 1.245]
    "text_color_de": 12.0,   # 핵심 획 대표색 ΔE00 허용
    "text_dark_frac": 0.2,   # 획 안 '바탕보다 어두운' 픽셀 비율(외곽선 · 그림자)의 컨셉 ↔ 렌더 차 허용
    "text_halo_frac": 0.2,   # 획 후보 중 핵심 밖 '바탕보다 밝은' 픽셀 비율(빛 번짐)의 차 허용
    "seam_dark_px": 90,      # 3 배 절취선 — 한 자리에서 컨셉 한 장 확대보다 20 넘게 어두운 확대 픽셀이 이만큼 이상이면 결함
    # 1b 후속 K — 오류(E) · 근사(A)
    "weight_margin": 0.06,   # E9 굵기 — 가진 굵기 중 더 가까운 것(로그 거리)이 지금보다 이만큼 넘게 가까우면 "가장 가까운 선택 아님" — PIL 표와 엔진 렌더 굵기 간격 차(약 5 %)를 덮는다 [실측 K R20261118_011648 "돌진 공격" Regular 0.895 ↔ Medium 1.105 진동]
    "bg_cover": 0.3,         # E1 글자 구역 바탕 — 7 × 7 창 안 바탕 픽셀(획 + 2 px 밖) 비율이 이 이상인 자리만 잰다
    "blur_ratio": 0.8,       # E2 뭉개짐 — 위젯 자리 선명도(기울기 에너지) 렌더 ÷ 컨셉이 이 미만이면 오류
    "glow_min": 8.0,         # E7 빛 유무 — 획 2 ~ 6 px 띠가 글자 없는 바탕보다 L 이만큼 밝으면 빛(analyze text_glow.min_excess 와 같은 값)
    # 1b 후속 L 다음 — E1 획에 붙은 잔상(glyph_residue): 렌더 글자가 안 덮은 컨셉 획 자리의 텍스처 · 렌더가 글자 없는 바탕 두 추정과 ΔE00 이만큼 넘게 다른 픽셀 덩어리
    "residue_de": 20.0,      # [실측 R20261118_120715 단색 '4' 밑 잔상 11 px · 평균 31.3 · 최대 45.7 — 보호 run 다섯(L-1 · L-2 · controls 셋)은 20 넘는 픽셀 0]
    "residue_min_px": 6,     # 덩어리 최소 픽셀(같은 자리 124503 은 1 px 둘 — 안 셈)
    # 1b 후속 L 다음 — 상태 검사(gen/state_check — S1 숨김 흔적 · S2 게이지 끝): record = 기록만(rec state_checks) · error = 오류(E8 상태) · off.
    # 묶음(정답 · 회귀) 26 run 기록만 재진단 거짓 양성 0 뒤 error [실측 11-19 — 발견은 모두 같은 종류 실제 결함]
    "state_checks": "error",
    # 1b 후속 L 다음 L-1 글자 완전 지우기 — S4 글자 밑 흔적(state_check.text_trace): 자리 안만의 3 × 3 창 평균 문턱 · 덩어리 최소 넓이
    "text_trace_de": 5.0,
    "text_trace_min_area": 24,
    # 1b 후속 L 다음 — 글자 지우기 마감: S4 가는 선(state_check text_contour) — 자리 안 픽셀 차 문턱 · 골격 길이 문턱
    "text_contour_de": 2.5,
    "text_contour_len": 40,
    "text_contour_link": 1,   # 가는 선 — 이만큼(px) 틈은 잇고 잼
    # S4 '밝힌 검정'(검정 합성 × 이 값) — 기록만(local_max.lift · refine 글자 지우기 고르기). 어두운 판의 낮은 대비 흔적은 ΔE00 이 작게 재진다
    # [실측 R20261119_190059 배너 '체인 버스트' 검정 1.47 · 밝힘 4.54, 깨끗한 L-2 0.5]. 0 이면 안 잼
    "text_trace_lift": 3.0,
    # 1b 후속 L 다음 — 글자 지우기 다음 V2: 선 모양 덩어리(짧은 변 ≤ 2 px · 곧은 가는 선)는 글자 없는 판에도 있는 선일 때만 구조선(기록만) — record = 판에 없는 선도
    # 기록만(line_like 의 in_plate False), error = 판에 없는 선은 결함. [실측 11-20 묶음 32 run 기록만 재진단 — 선 모양 발견 = 파티 run 셋의 같은 HP 숫자 막대
    # 윗선 위 빛 반원 자국 23 × 2(판에 없음 · closer 0.51 · 판 대비 4.1 — 사용자 눈 실제 흔적)뿐, 판에 있는 선 0 → 거짓 양성 0] → error
    "text_line_plate": "error",
    # V3: 밝힌 검정 — record = 기록만(lift_like), error = 어두운 판 자리(둘레 L* < state_check.LIFT_DARK_L)에서 밝힘 국소 > text_lift_de 덩어리를 결함(check text_lift).
    # [실측 11-20 묶음 32 run — 어두운 자리 밝힘 덩어리(국소 > 3.0, ≥ 24 px) 63 개(18 run)를 그림으로 분류: 모두 실제 흔적(최저 3.7 = 190059 '4' 가는 윤곽, 4.1 · 5.2 = 파티
    # 빛 줄기), 깨끗한 판(L-2 셋 · 새 L-1 235452)은 덩어리 0(국소 최대 3.6) → 거짓 양성 0 문턱 4.0] → error
    "text_lift_mode": "error",
    "text_lift_de": 4.0,
    # L-2 기본 전환 ④ — 접히는 위젯(시작 때 숨음 · flag)을 껐을 때 정적 판에 남은 빛(state_check.hidden_halo): 3 × 3 국소 ΔE00(검정 · 회색 · 흰 중 최대) 문턱
    "halo_de": 2.0,
    # 오류 모드에서도 기록만 둘 check(새 검사 — 묶음 거짓 양성 0 확인 전까지)
    "state_record_only": [],
}
# 결함 → 오류 번호(설계 §11 K): E1 얼룩 · 잔상 · E2 뭉개짐 · E3 잘림 · 빠짐 · E4 구멍 · 이중 · E5 절취선 · E6 위치 · E7 효과 유무 · E8 상태 · E9 가장 가까운 선택 아님
TEXT_CODES = {"size": "E9", "weight": "E9", "color": "E9", "position": "E6", "unmeasured": "E6", "outline": "E7", "glow": "E7", "shadow": "E7", "missing": "E3",
              "glow_strength": "E9", "baked": "E1"}
BAKED_KEEP = 0.6                    # 1b 후속 L 다음 — 글자 없는 판과 다른 컨셉 글자 픽셀의 이만큼 이상을 텍스처 합성이 그대로(INK_FLOOR 안) 가지면 '텍스처에 글자가 남음'
GLOW_PEAK_TOL = 1.25               # 1b 후속 L-2 사람 눈 — 둘 다 빛날 때 띠 밝기(glow_measure peak) 비가 이보다 크면 빛 세기 다름(그리고 차 ≥ 문턱/2)
GLOW_ALPHA_RANGE = (0.15, 1.0)     # 빛 세기 어휘 = font.glow.color 알파(analyze derive_text_glow · style._add_glow 와 같은 범위)
INK_MIN, INK_FLOOR = 48.0, 24.0     # 글자 차이 마스크 — 오츠 문턱 하한 · 후보 하한(style._diff_text_mask 와 같은 값)
CORE_SPREAD = 15.0                  # 획 후보 L* 폭(p90 − p10)이 이보다 넓으면 오츠로 갈라 글자색 쪽만(빛 번짐 · 안티앨리어싱 빼기)
TEXT_MIN_CORE = 20                  # 핵심 획이 이보다 적으면 글자 없음
HIDDEN_PAD = 4
END_GLOW_FRAC = 0.6                 # F2 — 국소 결함 상자의 이만큼 이상이 번짐 뺀 채움의 진행 끝 빛 자리(state_check.end_glow_zones)면 근사 gauge_end_glow
TEXT_ZONE_PAD = 4
ZOOM = 3
ZOOM_BG = 40.0
ZOOM_DARK = 20.0
STAGE_COLORS = {"texture": (255, 64, 64), "placement": (255, 200, 0), "engine": (255, 128, 0), "seam": (64, 160, 255), "text": (64, 255, 128)}


def settings(cfg: dict | None) -> dict:
    s = dict(DEFAULTS)
    s.update({k: v for k, v in ((cfg or {}).get("appearance") or {}).items() if k in DEFAULTS})
    return s


def enabled(cfg: dict | None) -> bool:
    return bool(((cfg or {}).get("appearance") or {}).get("enabled", True))


# ---------------------------------------------------------------------------------------------------------------------
# 기본 도구

def _load_rgb(path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), float)


def _load_l(path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), float) / 255.0


def delta_e(a, b) -> np.ndarray:
    return color.delta_e00(color.srgb_to_lab(a), color.srgb_to_lab(b)).astype(np.float32)


def local_mean(de) -> np.ndarray:
    import cv2
    return cv2.blur(np.asarray(de, np.float32), (WIN, WIN))


def _dilate(m, r: int):
    import cv2
    if r <= 0:
        return np.asarray(m, bool)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(np.asarray(m, np.uint8), k) > 0


def _box_mask(shape, box, pad: float = 0) -> np.ndarray:
    H, W = shape
    m = np.zeros((H, W), bool)
    x, y, w, h = (float(v) for v in box)
    x0, y0 = max(0, int(np.floor(x - pad))), max(0, int(np.floor(y - pad)))
    x1, y1 = min(W, int(np.ceil(x + w + pad))), min(H, int(np.ceil(y + h + pad)))
    if x1 > x0 and y1 > y0:
        m[y0:y1, x0:x1] = True
    return m


def _bbox(m) -> list[int] | None:
    ys, xs = np.nonzero(m)
    if not len(ys):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def _otsu(v) -> float:
    import cv2
    v = np.clip(np.asarray(v, float), 0, 255).astype(np.uint8).reshape(-1, 1)
    t, _ = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(t)


def _drop_small(m, n: int = 6):
    import cv2
    k, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    small = [i for i in range(1, k) if st[i, cv2.CC_STAT_AREA] < n]
    return m & ~np.isin(lab, small) if small else m


def _subtree(spec: dict, wid: str) -> set[str]:
    kids: dict[str, list[str]] = {}
    for w in spec.get("widgets", []):
        if w.get("parent"):
            kids.setdefault(w["parent"], []).append(w["id"])
    out, stack = set(), [wid]
    while stack:
        cur = stack.pop()
        out.add(cur)
        stack.extend(kids.get(cur, []))
    return out


def _without(spec: dict, ids: set[str]) -> dict:
    return {**spec, "widgets": [w for w in spec.get("widgets", []) if w["id"] not in ids]}


def _font_l(w: dict) -> float | None:
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    g = f.get("gradient") if isinstance(f.get("gradient"), dict) else None
    hexes = [g.get("top_color"), g.get("bottom_color")] if g else [f.get("color") or "#FFFFFFFF"]
    rgbs = []
    for h in hexes:
        h = str(h or "").lstrip("#")
        if len(h) >= 6:
            rgbs.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    if not rgbs:
        return None
    return float(color.srgb_to_lab(np.asarray(rgbs, float).mean(axis=0).reshape(1, 3))[0, 0])


# ---------------------------------------------------------------------------------------------------------------------
# 3 배 절취선 (1b 후속 I 후속 replay_refine.zoom_seams 를 옮김 — 타일만 계산)

def zoom_seams(spec: dict, boxes: list[dict], textures: dict, rc, ra, bbox, tmask, scale: int = ZOOM, picture=None) -> dict:
    """나눈 텍스처를 각각 scale 배 늘려 겹친 그림 ↔ 컨셉 한 장을 늘린 그림 — 텍스처 경계의 절취선(덮임 모자람 · 투명 픽셀 색 섞임)을 잰다.
    image 브러시만(텍스처가 상자보다 크면 늘려 그림) — 9-slice · 글자는 뺀다. 세는 자리 = 두 텍스처 이상의 보이는 픽셀이 2 px 안에 맞닿는 경계
    (글자 상자 + 6 px 밖 · 컨셉 알파 > 0.05). bbox = 캔버스 [x0, y0, x1, y1] — 그 안에서 경계 자리 둘레 타일만 계산한다.
    → {zone_px, dark_px, dark_mean, worst, spots[{box, dark_px}] …} (dark_px = 확대 픽셀 수)."""
    import cv2
    geo = {b["id"]: b for b in boxes}
    lays = []
    H0, W0 = ra.shape
    other = np.zeros((H0, W0), bool)      # 이미지 브러시가 아닌 그리기(게이지 · 9-slice · 둥근 상자)가 덮는 자리 — 확대 모사에 없으니 비교에서 뺀다
    for w in backdrop.paint_order(spec):
        st = w.get("style") or {}
        br = st.get("brush") or st.get("normal") or {}
        g = geo.get(w["id"])
        if not g or not g.get("visible", True) or g["w"] <= 0 or g["h"] <= 0:
            continue
        drawn_other = w.get("type") == "ProgressBar" or any(isinstance(b, dict) and b.get("draw_as", "image") not in ("image", "none")
                                                            for k, b in st.items() if k in ("brush", "normal", "background", "fill"))
        if drawn_other and w.get("type") not in backdrop.TEXT_TYPES:
            other |= _box_mask((H0, W0), [g["x"], g["y"], g["w"], g["h"]], 2)
        if not isinstance(br, dict) or br.get("draw_as") != "image" or br.get("asset") not in textures:
            continue
        lays.append((textures[br["asset"]].astype(np.float32), float(g["x"]), float(g["y"]), float(g["w"]), float(g["h"])))
    ref = np.dstack([rc, ra * 255.0]).astype(np.float32)
    x0, y0, x1, y1 = (int(v) for v in bbox)
    H, W = ra.shape
    count = np.zeros((H, W), np.int16)
    k5 = np.ones((5, 5), np.uint8)
    for t, ox, oy, bw, bh in lays:
        sup = np.zeros((H, W), np.uint8)
        ix, iy, iw, ih = int(round(ox)), int(round(oy)), int(round(bw)), int(round(bh))
        ta = cv2.resize(t[..., 3], (iw, ih), interpolation=cv2.INTER_AREA) if (t.shape[1], t.shape[0]) != (iw, ih) else t[..., 3]
        cx0, cy0, cx1, cy1 = max(0, ix), max(0, iy), min(W, ix + iw), min(H, iy + ih)
        if cx1 > cx0 and cy1 > cy0:
            sup[cy0:cy1, cx0:cx1] = ta[cy0 - iy:cy1 - iy, cx0 - ix:cx1 - ix] > 0
        count += cv2.dilate(sup, k5).astype(np.int16)
    seam = (count >= 2) & ~tmask & (ra > 0.05) & ~other
    seam[:y0] = False
    seam[y1:] = False
    seam[:, :x0] = False
    seam[:, x1:] = False
    rec = {"scale": scale, "bbox": [x0, y0, x1, y1], "zone_px": int(seam.sum()), "dark_px": 0, "dark_mean": 0.0, "worst": 0.0, "spots": [],
           "layers": len(lays)}
    if not seam.any():
        return rec
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(seam.astype(np.uint8), np.ones((17, 17), np.uint8)), connectivity=8)
    dark_all = np.zeros((H, W), np.int32)
    total, worst, dark = 0.0, 0.0, 0

    def comp(layers, gx, gy):
        acc = np.full(gx.shape + (3,), ZOOM_BG, np.float32)
        for t, ox, oy, bw, bh in layers:
            # Slate: 상자(쿼드) 밖은 그리지 않고, 상자 안 가장자리는 텍셀을 고정(clamp) 샘플링 — 텍스처 바깥을 투명으로 섞지 않는다
            u, v = gx - ox, gy - oy
            if not ((u >= 0) & (v >= 0) & (u < bw) & (v < bh)).any():
                continue
            sx, sy = t.shape[1] / bw, t.shape[0] / bh
            s = cv2.remap(t, (u * sx - 0.5).astype(np.float32), (v * sy - 0.5).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            inside = (u >= 0) & (v >= 0) & (u < bw) & (v < bh)
            s[~inside] = 0
            al = s[..., 3:] / 255.0
            acc = s[..., :3] * al + acc * (1 - al)
        return acc
    rows = []
    for i in range(1, n):
        tx, ty, tw, th = (int(st[i, k]) for k in range(4))
        tx0, ty0, tx1, ty1 = max(0, tx), max(0, ty), min(W, tx + tw), min(H, ty + th)
        zone_c = seam[ty0:ty1, tx0:tx1] & (lab[ty0:ty1, tx0:tx1] == i)
        if not zone_c.any():
            continue
        gx, gy = np.meshgrid((np.arange((tx1 - tx0) * scale) + 0.5) / scale + tx0, (np.arange((ty1 - ty0) * scale) + 0.5) / scale + ty0)
        split, single = comp(lays, gx, gy), comp([(ref, 0.0, 0.0, float(W), float(H))], gx, gy)
        d = (single - split).mean(axis=2)
        zone = np.repeat(np.repeat(zone_c, scale, axis=0), scale, axis=1)
        m = (d > ZOOM_DARK) & zone
        c = int(m.sum())
        if c:
            iy, ix = np.nonzero(m)
            np.add.at(dark_all, ((iy // scale) + ty0, (ix // scale) + tx0), 1)
            total += float(d[m].sum())
        dark += c
        worst = max(worst, float(d[zone].max()) if zone.any() else 0.0)
        if picture is not None and c:
            rows.append(np.concatenate([single, np.full((single.shape[0], 6, 3), 255, np.float32), split], axis=1))
    if picture is not None and rows:
        from PIL import Image
        wmax = max(r.shape[1] for r in rows)
        rows = [np.pad(r, ((0, 6), (0, wmax - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
        Image.fromarray(np.clip(np.concatenate(rows, axis=0), 0, 255).astype(np.uint8)).save(picture)
    spots = []
    if dark:
        mk = (dark_all > 0).astype(np.uint8)
        k, slab, sst, _ = cv2.connectedComponentsWithStats(cv2.dilate(mk, k5), connectivity=8)
        for j in range(1, k):
            sel = slab == j
            spots.append({"box": [int(sst[j, 0]), int(sst[j, 1]), int(sst[j, 2]), int(sst[j, 3])], "dark_px": int(dark_all[sel].sum())})
        spots.sort(key=lambda s: -s["dark_px"])
    alpha_hist = np.histogram(ra[dark_all > 0], bins=[0, 0.3, 0.6, 0.9, 0.97, 1.01])[0].tolist() if dark else []
    rec.update(dark_px=dark, dark_mean=round(total / max(1, dark), 1), worst=round(worst, 1), spots=spots[:40], alpha_hist=alpha_hist)
    return rec


# ---------------------------------------------------------------------------------------------------------------------
# 글자 — 그림끼리

CORE_FRAC = 0.5            # 핵심 획 = 후보 중 바탕과의 차가 후보 p90 의 이만큼 이상 — 빛 번짐 · 그림자 · 안티앨리어싱은 반투명이라 차가 작다
                           # (밝기 반 가르기는 그라데이션 금색 글자의 아래 반을 지웠다 [실측 J-b 기준선 R20261117_094643 '체인 버스트' 높이 비 0.53])


def maxabs(a, b) -> np.ndarray:
    return np.abs(np.asarray(a, float) - np.asarray(b, float)).max(axis=2).astype(np.float32)


CORE_WIN = 9               # 핵심 획 국소 기준 창(px)


CORE_DEPTH = 2.0           # 획 속 = 후보 가장자리에서 이만큼(px) 안쪽 — 그 대표색(위 · 아래 반)이 글자색
CORE_COLOR_DE = 25.0       # 핵심 획 = 획 속 대표색에 ΔE00 이만큼 안으로 가까운 픽셀(외곽선 · 그림자 빼기)


def _font_refs(w: dict) -> list | None:
    """렌더 글자의 알려진 글자색(그라데이션이면 위 · 아래) — 외곽선 · 빛 글자의 렌더 핵심 획을 고를 때만(core_of refs).
    (1b 후속 L-2) 빛 글자도: 짙은 빛(알파 0.96 빨강)은 글자와 한 덩어리 후보가 되고 획 속 대표색이 빛 색이 돼 핵심 획 = 빛으로 잡혔다
    [실측 R20261118_141410 '오의 불가' — 렌더 핵심 획 L* 14 · 색 ΔE00 75 · 상자 83 × 50 → 글자 맞춤이 크기 32 → 22 · 빛 8 → 18 로 돌았음]."""
    f = w.get("font") if isinstance(w.get("font"), dict) else None
    if not f or not ((f.get("outline") or {}).get("size") or (f.get("glow") or {}).get("size")):
        return None
    def rgb(h):
        h = str(h or "").lstrip("#")
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) if len(h) >= 6 else None
    g = f.get("gradient") or {}
    refs = [c for c in (rgb(g.get("top_color")), rgb(g.get("bottom_color"))) if c is not None] if g else []
    if not refs and rgb(f.get("color")) is not None:
        refs = [rgb(f.get("color"))]
    return refs or None


def core_of(d, cand, img=None, refs_hint: list | None = None) -> np.ndarray:
    """글자 후보 중 핵심 획 — 주변 CORE_WIN 창 안 후보의 최대 차의 CORE_FRAC 이상(빛 번짐 · 안티앨리어싱은 바로 옆 획보다 차가 작다, J-c).
    전체 p90 기준은 바탕이 고르지 않으면(빛 위에 걸친 '오의 불가' 아래 반) 획을 지웠다 [실측 J-b 094643].
    img 를 주면 '글자색 쪽'만 — 획 속(가장자리에서 CORE_DEPTH 안쪽)의 위 · 아래 반 대표색에 가까운 픽셀만 남겨 바탕과 차가 큰 검은 외곽선을 뺀다
    [실측 J R20261117_184207 단색 '오의 불가' — 외곽선이 핵심 획에 섞여 글자색 위쪽이 #2C0403 · 밀도 비 0.57]."""
    import cv2
    if not cand.any():
        return cand
    dm = cv2.dilate(np.where(cand, d, 0).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CORE_WIN, CORE_WIN)))
    core = cand & (d >= CORE_FRAC * dm)
    if img is None or not core.any():
        return core
    if refs_hint:
        # 렌더 외곽선 글자 — 글자색을 안다(획 속 대표색은 굵은 외곽선이면 외곽선이 된다 [실측 J R20261117_210351 방패 '10' 핵심 획 = 검은 외곽선, 색 ΔE00 88])
        refs = refs_hint
        cand_core = cand & (d > INK_MIN)
        lab = color.srgb_to_lab(np.asarray(img, float)[cand_core])
        near = np.min([color.delta_e00(lab, color.srgb_to_lab(np.asarray(r, float).reshape(1, 3))) for r in refs], axis=0) < CORE_COLOR_DE
        out = np.zeros_like(core)
        out[cand_core] = near
        if int(out.sum()) >= TEXT_MIN_CORE:
            return out
    dt = cv2.distanceTransform(cand.astype(np.uint8), cv2.DIST_L2, 3)
    inner = core & (dt >= CORE_DEPTH)
    if int(inner.sum()) < TEXT_MIN_CORE:
        return core
    ys = np.nonzero(inner)[0]
    mid = float(np.median(ys))
    rows = np.arange(inner.shape[0])[:, None]
    refs = [np.median(np.asarray(img, float)[inner & sel], axis=0) for sel in (rows <= mid, rows > mid) if (inner & sel).any()]
    lab = color.srgb_to_lab(np.asarray(img, float)[core])
    near = np.min([color.delta_e00(lab, color.srgb_to_lab(r.reshape(1, 3))) for r in refs], axis=0) < CORE_COLOR_DE
    out = np.zeros_like(core)
    out[core] = near
    return out if int(out.sum()) >= TEXT_MIN_CORE else core


def _main_cluster(m, h: float) -> np.ndarray:
    """한 줄 글자의 덩어리 묶음 — 가로 틈이 글자 높이(h)보다 큰 곳에서 묶음을 나눠 넓이가 가장 큰 묶음만(멀리 떨어진 장식 끝 · 잡티 빼기)
    [실측 J-b 094643 '2/4' — 패널 폭 상자 안 오른쪽 끝 장식 조각으로 폭 비 0.29]."""
    import cv2
    k, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if k <= 2:
        return m
    comps = sorted(range(1, k), key=lambda i: st[i, cv2.CC_STAT_LEFT])
    groups, cur, right = [], [comps[0]], st[comps[0], 0] + st[comps[0], 2]
    for i in comps[1:]:
        if st[i, 0] - right > h:
            groups.append(cur)
            cur = []
        cur.append(i)
        right = max(right, st[i, 0] + st[i, 2])
    groups.append(cur)
    if len(groups) == 1:
        return m
    best = max(groups, key=lambda g: sum(int(st[i, cv2.CC_STAT_AREA]) for i in g))
    return m & np.isin(lab, best)


SPLIT_SHARE = 0.05         # 한 덩어리의 이만큼(그리고 SPLIT_MIN_PX) 이상이 둘 넘는 글자 상자(빛 여백 뺀 상자)에 들면 픽셀 단위로 나눈다
SPLIT_MIN_PX = 40          # [실측 J R20261117_204115 — 작은 'Lv' 는 이름과 이어진 덩어리의 20 % 미만이라 0.2 로는 안 나뉨]
SPLIT_STRONG = 0.55        # 나눌 때 '센 획' = 덩어리 차 p95 의 이만큼 이상(빛 번짐 · 다리는 그보다 약하다 — core_of 의 CORE_FRAC 과 같은 생각)
SPLIT_EXCL_PX, SPLIT_EXCL_SHARE = 15, 0.1   # 센 획이 한 글자의 '자기 구역'(다른 후보 core 와 안 겹친 core)에 이만큼(px · 획 비) 걸치면 그 글자의 증거
BODY_NEAR = 6              # 겹친 core 안에만 있는 센 획 → 이어진 본체(증거로 정한 그 글자의 다른 센 획)까지 ≤ max(이것, BODY_NEAR_FRAC × 그 글자 core 높이)이고
BODY_NEAR_FRAC = 0.3       # 다른 후보 본체보다 BODY_CLEAR 배 이상 가까우면 그 글자 몫
BODY_CLEAR = 2.0           # [실측 R20261118_175104 '인' ㄴ 받침 — '체인' 본체 4 ~ 5 px · '4.2' 본체 18 ~ 23 px]


PRIOR_GROW = 3             # 렌더 획 주인을 정할 때 컨셉 획(넓힘)과 겹치는지 보는 반경(px)


def _prior_owner(prior: dict | None, ys, xs, keys) -> str | None:
    """컨셉에서 이미 정한 글자 획(prior — 넓힌 마스크)과 겹치는 픽셀이 가장 많은 글자(60 % 이상일 때만)."""
    if not prior:
        return None
    hits = {k: int(prior[k][ys, xs].sum()) for k in keys if k in prior}
    tot = sum(hits.values())
    if tot <= 0:
        return None
    k = max(hits, key=hits.get)
    return k if hits[k] >= 0.6 * tot else None


def assign_glyphs(d, zones: dict, owns: dict, cores: dict | None = None, prior: dict | None = None) -> dict:
    """차이 지도(채널 최대) → 글자 위젯마다 후보 획: 차 > INK_MIN 인 덩어리를 그 무게중심이 든 탐색 구역의 글자 중 자기 상자에 가장 가까운 것
    (상자 안이면 상자 중심과의 거리를 상자 크기로 나눈 값)에 준다 — 겹친 글자 상자('4.2' 아래 '2/4')에서 이웃 획이 끼지 않게.
    cores(빛 여백을 뺀 글자 상자 — 1b 후속 J)를 주면 상자 거리는 그것으로 재고, 한 덩어리가 둘 넘는 core 상자에 SPLIT_SHARE 이상씩 걸치면
    픽셀마다 가장 가까운 core 상자로 나눈다 — 빛 번짐이 이웃 글자를 한 덩어리로 이었다
    [실측 J R20261117_201408 파티 HUD — 본문 SDF 빛을 단 'Lv' · '100' · 이름이 한 덩어리 → 'Lv' 누락 · 이름 높이 비 1.89].
    센 획 하나의 주인(진단 거짓 양성 E1 고침, 11-18): 두 글자 이상의 '자기 구역'(다른 후보 core 와 안 겹친 core)에 SPLIT_EXCL 이상씩 걸치면 픽셀로 나누고
    (붙은 '3/'), 아니면 통째로 — 컨셉 획(prior, 렌더만) → 한 글자의 자기 구역에만 걸치면 그 글자(다수 쪽) → 겹친 core 안에만 있으면 이어진 본체(증거로 정한 다른 센 획 중 가장 가까운 글자 — BODY_NEAR 안 · 다른 후보보다 BODY_CLEAR 배 가까울 때, 모든 후보에 본체가 있을 때만) →
    무게중심 상자 거리. 무게중심이 core 둘 이상에 든 작은 덩어리도 증거가 없으면 같은 본체 판정(아니면 예전 상자 거리).
    [실측 R20261118_175104 원래 전투 HUD — 빛 여백으로 넓은 '4.2' core 가 '체인' 아래 15 px 와 겹쳐 '인' ㄴ 받침(두 core 안에만 있는 한 센 획)이
    픽셀마다 상자 거리로 갈려 오른쪽 반이 '4.2' 몫 → 본체와 떨어진 조각이라 '4.2' 거르기(_filter_glyph_parts)에서 빠져 어느 글자 획도 아닌 바탕 E1 27]"""
    import cv2
    H, W = d.shape
    allz = np.zeros((H, W), bool)
    for z in zones.values():
        allz |= z
    m = (d > INK_MIN) & allz
    out = {k: np.zeros((H, W), bool) for k in zones}
    body = {k: np.zeros((H, W), bool) for k in zones}   # 증거로 정한 센 획 — 겹친 core 안에만 있는 획의 주인을 가릴 '이어진 본체'
    n, lab, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    boxes = {k: _bbox(v) for k, v in (cores or owns).items()}
    later = []      # 본체를 다 모은 뒤 정할 덩어리(겹친 core 안에만 있는 센 획이 든 것)

    def norm_d(k, xs, ys):
        x, y, w, h = boxes[k]
        ddx = np.maximum(0, np.maximum(x - xs, xs - (x + w - 1))) / max(1.0, w)
        ddy = np.maximum(0, np.maximum(y - ys, ys - (y + h - 1))) / max(1.0, h)
        cdx = np.abs(xs - (x + w / 2.0)) / max(1.0, w) + np.abs(ys - (y + h / 2.0)) / max(1.0, h)
        return (ddx + ddy) * 10.0 + cdx * 0.01

    def excl_of(cands, bx, by, bw, bh):
        ex = {}
        for k in cands:
            others = np.zeros((bh, bw), bool)
            for k2 in cands:
                if k2 != k:
                    others |= cores[k2][by:by + bh, bx:bx + bw]
            ex[k] = cores[k][by:by + bh, bx:bx + bw] & ~others
        return ex

    def evidence(ex, cands, mj) -> list:
        sz = int(mj.sum())
        return [k for k in cands if int((ex[k] & mj).sum()) >= max(SPLIT_EXCL_PX, int(SPLIT_EXCL_SHARE * sz))]

    dts: dict = {}

    def by_body(cands, yy, xx, fb: int) -> int:
        """겹친 core 안에만 있는 센 획(전역 좌표 yy, xx) — 이어진 본체가 뚜렷이 가까운 후보, 아니면 fb."""
        if not len(yy) or any(not body[k].any() for k in cands):
            return fb
        dist = []
        for k in cands:
            if k not in dts:
                dts[k] = cv2.distanceTransform((~body[k]).astype(np.uint8), cv2.DIST_L2, 5)
            dist.append(float(dts[k][yy, xx].min()))
        o = int(np.argmin(dist))
        if dist[o] <= max(float(BODY_NEAR), BODY_NEAR_FRAC * float(boxes[cands[o]][3])) and all(
                dd >= BODY_CLEAR * max(1.0, dist[o]) for t, dd in enumerate(dist) if t != o):
            return o
        return fb

    def paint_multi(multi, bx, by, sel, strong, lab2, owner):
        _, near = cv2.distanceTransformWithLabels((~strong).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(sel)
        src = np.argwhere(strong)
        idx = near[ys, xs] - 1
        pick = np.array([owner.get(int(v), 0) for v in lab2[src[idx, 0], src[idx, 1]]], int)
        for j, k in enumerate(multi):
            o = pick == j
            yy, xx = ys[o] + by, xs[o] + bx
            keep = zones[k][yy, xx]
            out[k][yy[keep], xx[keep]] = True

    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 6:
            continue
        bx, by, bw, bh = (int(v) for v in st[i, :4])
        sel = lab[by:by + bh, bx:bx + bw] == i
        # 센 획 픽셀로 센다 — 큰 덩어리('44993' + 붙은 '/')에서 이웃 글자 몫이 덩어리 넓이 비로는 작다
        sd = d[by:by + bh, bx:bx + bw]
        strong = sel & (sd >= SPLIT_STRONG * float(np.percentile(sd[sel], 95)))
        multi = []
        if cores:
            area = float(strong.sum())
            multi = [k for k in zones if boxes.get(k) is not None
                     and float((cores[k][by:by + bh, bx:bx + bw] & strong).sum()) >= max(float(SPLIT_MIN_PX), SPLIT_SHARE * area)]
        if prior and len(multi) < 2:
            # 렌더 — 한 글자 상자 안 덩어리는 컨셉 획과 겹치면 그 주인(인접한 두 글자 사이 획이 컨셉 · 렌더에서 다른 글자 몫이 되지 않게)
            ys0, xs0 = np.nonzero(sel)
            st0 = strong[ys0, xs0]
            ys0, xs0 = ys0 + by, xs0 + bx
            pk = _prior_owner(prior, ys0[st0], xs0[st0], list(zones))
            if pk is not None:
                keep = zones[pk][ys0, xs0]
                out[pk][ys0[keep], xs0[keep]] = True
                body[pk][ys0[keep & st0], xs0[keep & st0]] = True
                continue
        if cores and len(multi) >= 2:
            # 센 획(덩어리 차 p95 의 SPLIT_STRONG 이상)끼리 먼저 주인을 정하고, 빛 다리 · 번짐 픽셀은 가장 가까운 센 획의 주인을 따른다
            # — 픽셀마다 상자 거리로 가르면 겹친 줄 상자 가운데에서 다리가 반씩 갈려 높이가 부풀었다
            n2, lab2, _, cen2 = cv2.connectedComponentsWithStats(strong.astype(np.uint8), connectivity=8)
            ex = excl_of(multi, bx, by, bw, bh)
            if n2 <= 2 and len(evidence(ex, multi, strong)) >= 2:
                # 센 획도 한 덩어리이고 두 글자의 자기 구역에 걸침 — 픽셀마다 가장 가까운 core 상자로
                ys, xs = np.nonzero(sel)
                pick = np.stack([norm_d(k, xs + bx, ys + by) for k in multi]).argmin(axis=0)
                for j, k in enumerate(multi):
                    o = pick == j
                    yy, xx = ys[o] + by, xs[o] + bx
                    keep = zones[k][yy, xx]
                    out[k][yy[keep], xx[keep]] = True
                    so = keep & strong[ys[o], xs[o]]
                    body[k][yy[so], xx[so]] = True
                continue
            lab2 = lab2.astype(np.int64)
            owner: dict = {}
            pend = []
            nid = n2
            for j2 in range(1, n2):
                mj = lab2 == j2
                yy2, xx2 = np.nonzero(mj)
                big = evidence(ex, multi, mj)
                if len(big) >= 2:
                    # 한 센 획이 두 글자의 자기 구역에 걸침(붙은 '3/') — 그 획은 픽셀마다 나눈다
                    # [실측 J R20261117_211123 파티 HUD — 넓은 렌더 숫자 '3' 에 '/' 가 붙어 통째로 현재치 몫]
                    pk_ = np.stack([norm_d(k, xx2 + bx, yy2 + by) for k in big]).argmin(axis=0)
                    for t, k in enumerate(big):
                        sel_t = pk_ == t
                        lab2[yy2[sel_t], xx2[sel_t]] = nid
                        owner[nid] = multi.index(k)
                        body[k][yy2[sel_t] + by, xx2[sel_t] + bx] = True
                        nid += 1
                    continue
                # 렌더는 컨셉에서 정한 획(같은 글자)이 먼저, 그다음 자기 구역 증거가 하나인 글자(다수 쪽)
                pk2 = _prior_owner(prior, yy2 + by, xx2 + bx, multi) if prior else None
                if pk2 is None and big:
                    pk2 = big[0]
                if pk2 in multi:
                    owner[j2] = multi.index(pk2)
                    body[pk2][yy2 + by, xx2 + bx] = True
                    continue
                cx2, cy2 = np.array([float(cen2[j2][0]) + bx]), np.array([float(cen2[j2][1]) + by])
                pend.append((j2, yy2 + by, xx2 + bx, int(np.argmin([norm_d(k, cx2, cy2)[0] for k in multi]))))
            if pend:
                later.append(("multi", multi, bx, by, sel, strong, lab2, owner, pend))
            else:
                paint_multi(multi, bx, by, sel, strong, lab2, owner)
            continue
        cx, cy = float(cen[i][0]), float(cen[i][1])
        ix, iy = min(W - 1, max(0, int(round(cx)))), min(H - 1, max(0, int(round(cy))))
        best, bd, inside_k = None, None, []
        for k, z in zones.items():
            if not z[iy, ix] or boxes.get(k) is None:
                continue
            x, y, w, h = boxes[k]
            inside = x <= cx < x + w and y <= cy < y + h
            if inside:
                inside_k.append(k)
            dist = abs(cx - (x + w / 2.0)) / max(1.0, w) + abs(cy - (y + h / 2.0)) / max(1.0, h)
            key = (0 if inside else 1, dist)
            if bd is None or key < bd:
                best, bd = k, key
        if best is None:
            continue
        ys1, xs1 = np.nonzero(strong)
        if cores and len(inside_k) >= 2 and strong.any() and not evidence(excl_of(inside_k, bx, by, bw, bh), inside_k, strong):
            later.append(("one", i, inside_k, ys1 + by, xs1 + bx, inside_k.index(best)))
            continue
        out[best] |= lab == i
        body[best][ys1 + by, xs1 + bx] = True
    # 겹친 core 안에만 있는 센 획 — 증거로 정한 본체를 다 모은 뒤(본체끼리 잇달아 번지지 않게 한 번만)
    for item in later:
        if item[0] == "multi":
            _, multi, bx, by, sel, strong, lab2, owner, pend = item
            for j2, yy, xx, fb in pend:
                owner[j2] = by_body(multi, yy, xx, fb)
            paint_multi(multi, bx, by, sel, strong, lab2, owner)
        else:
            _, i, cands, yy, xx, fb = item
            out[cands[by_body(cands, yy, xx, fb)]] |= lab == i
    return out


LINE_THIN = 3              # 글자 후보에서 뺄 가는 선 — 두께 ≤ 이것이고 글자 하나보다 긴 것(가로 > 상자 높이 × 1.5 · 세로 > 상자 높이)
OWN_SHARE = 0.5            # 덩어리 픽셀의 이만큼 이상이 자기 글자 상자(넓힘) 안이어야 글자 획
STROKE_SHARE = 0.45        # 기준 획 두께(덩어리 거리 변환 최대의 넓이 가중 중앙값)의 이만큼도 안 되는 가는 덩어리는 글자 획이 아니다(판이 다시 그린 배지 테두리 호)


SPACING_EM = 1.34          # 자간 1/1000 em × 글자 크기 → px(Slate 글자 크기 pt → px)


def spacing_gap(w: dict) -> float:
    """넓은 자간 글자의 낱말 틈에 더해 줄 px(자간 둘 — 빈칸 글자 양옆). 자간이 없으면 0 — 예전 판정 그대로.
    [실측 combat_hud_blade R20261123_155229 '체인 버스트' 자간 240 — 낱말 틈 35 px > 0.6 × 상자 높이 31 px 라 '체인' 이 획 묶음에서 빠짐]"""
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    return 2.0 * max(0.0, float(f.get("letter_spacing") or 0)) / 1000.0 * float(f.get("size") or 0) * SPACING_EM


def _filter_glyph_parts(m, own, gap_extra: float = 0.0) -> np.ndarray:
    """후보 덩어리 중 글자 획만 — 글자 하나보다 긴 가는 가로 · 세로 선(판 어긋남 · 띠 가장자리), 자기 글자 상자 밖이 대부분인 덩어리(이웃 장식),
    가장 큰 덩어리보다 훨씬 가는 덩어리(배지 테두리 호)는 뺀다.
    [실측 J-b 기준선 R20261117_154442] 컨셉 획 마스크에 띠 위아래 가장자리 1 ~ 3 px 선 · 'R' 옆 날개 조각 · E · T 배지 테두리 호가 끼어 높이 비 0.5 ·
    밀도 비 3.4 로 오판. 두께만 보는 선 규칙은 작은 렌더 '회피' 의 2 px 세로획(ㅣ)까지 지웠다 — 길이를 글자 상자에 견준다."""
    import cv2
    bb = _bbox(own)
    h = bb[3] if bb else 20
    # 글자 하나보다 긴 선(패널 테두리 · 띠 가장자리)은 획과 붙어 한 덩어리가 되기도 한다 — 열림 연산으로 그 선 픽셀만 먼저 뺀다
    # [실측 J-b 기준선 R20261117_094643 '2/4' — 패널 아래 테두리선이 숫자 밑동에 붙어 폭 비 0.18]
    m8 = m.astype(np.uint8)
    lh = cv2.morphologyEx(m8, cv2.MORPH_OPEN, np.ones((1, max(3, int(1.5 * h))), np.uint8))
    lv = cv2.morphologyEx(m8, cv2.MORPH_OPEN, np.ones((max(3, int(1.05 * h)), 1), np.uint8))
    if lh.any() or lv.any():
        m = m & ~((lh | lv) > 0)
    k, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if k <= 1:
        return m
    keep_zone = _dilate(own, int(round(max(4.0, 0.25 * h))))
    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 3)
    drop, comps = [], []
    for i in range(1, k):
        w_, h_, a_ = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT], st[i, cv2.CC_STAT_AREA]
        if (h_ <= LINE_THIN and w_ > 1.5 * h) or (w_ <= LINE_THIN and h_ > h):
            drop.append(i)
            continue
        sel = lab == i
        if float(keep_zone[sel].mean()) < OWN_SHARE:
            drop.append(i)
            continue
        comps.append((i, int(a_), float(dt[sel].max())))
    if comps:
        # 기준 두께 = 덩어리 획 두께의 넓이 가중 중앙값 — 가장 큰 덩어리 하나를 기준으로 하면 획이 이어져 두꺼워진 덩어리('공격' 윗부분 dt 5)가
        # 나머지 글자를 다 지웠다 [실측 J-b 095249 '돌진 공격']
        big = max(c[1] for c in comps)
        order = sorted(comps, key=lambda c: c[2])
        tot, acc, ref = sum(c[1] for c in comps), 0, order[-1][2]
        for c in order:
            acc += c[1]
            if acc >= tot / 2.0:
                ref = c[2]
                break
        drop += [i for i, a_, d in comps if d < STROKE_SHARE * ref and a_ < 0.5 * big]
    m = m & ~np.isin(lab, drop) if drop else m
    return _main_cluster(m, 0.6 * h + gap_extra) if m.any() else m


def notext_unused(rd: pathlib.Path) -> set[str]:
    """정적 판 글자 메우기(refine._plate_item_fill)가 글자 없는 판 픽셀을 안 쓴 글자(정합 실패 · 투명 위 글자 — 둘레 컨셉으로 메움) — 그 자리의 판은
    글자 잔상이 남았을 수 있어 컨셉 획을 판 차로 재면 획이 지워진다 [실측 J R20261117_205334 파티 HUD 이름 — 컨셉 획 아래 반 빠짐 → 높이 비 1.6]."""
    try:
        logs = json.loads((rd / "refine.json").read_text(encoding="utf-8"))["passes"][-1]["assets"]
    except (OSError, ValueError, KeyError, IndexError):
        return set()
    out = set()
    for lg in logs:
        if lg.get("source_mode") != "plate":
            continue
        for wn in lg.get("windows") or []:
            # '둘레 컨셉'으로 메운 글자(투명 위 · 상자 안 · L-3b 획 둘레 좁은 메움). 판 색에 알파만 둘레인 '… (text-free concept alpha disagrees)' 는 판을 쓴 것.
            # 1b 후속 L 다음 — 판 중앙값 메움('text-free concept median')도 판 픽셀 그대로가 아니다(판의 글자 자국을 뭉갬) — 컨셉 획은 텍스처 합성과의 차로
            if wn.get("item") and (not wn.get("used") or str(wn.get("alpha_from") or "").startswith(
                    ("concept neighbourhood —", "concept neighbourhood inside", "concept neighbourhood around", "text-free concept median"))):
                out.add(wn["item"])
    return out


GLYPH_COLOR_DE = 30.0      # 아트 모드 글자 후보 = 사양 글자색(위 · 아래)에 ΔE00 이만큼 안


def _font_colors(w: dict) -> list:
    """사양 글자색(그라데이션이면 위 · 아래) — RGB 목록."""
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    g = f.get("gradient") if isinstance(f.get("gradient"), dict) else None
    out = []
    for h in ([g.get("top_color"), g.get("bottom_color")] if g else [f.get("color")]):
        h = str(h or "").lstrip("#")
        if len(h) >= 6:
            out.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    return out


SHIFT_TOL = 2              # 아트 모드 차이 — 다시 그린 장식 어긋남을 덮는 이동 범위(px)


def _shift_min_diff(a, b, zones: dict) -> np.ndarray:
    """채널 최대 차 — b 를 ±SHIFT_TOL px 옮긴 것 중 가장 작은 차(글자 구역들을 품는 상자 안만, 밖은 그냥 차)."""
    d = maxabs(a, b)
    allz = np.zeros(d.shape, bool)
    for z in zones.values():
        allz |= z
    bb = _bbox(allz)
    if bb is None:
        return d
    H, W = d.shape
    x0, y0 = max(0, bb[0] - SHIFT_TOL), max(0, bb[1] - SHIFT_TOL)
    x1, y1 = min(W, bb[0] + bb[2] + SHIFT_TOL), min(H, bb[1] + bb[3] + SHIFT_TOL)
    A = np.asarray(a, float)[y0:y1, x0:x1]
    best = d[y0:y1, x0:x1].copy()
    for dy in range(-SHIFT_TOL, SHIFT_TOL + 1):
        for dx in range(-SHIFT_TOL, SHIFT_TOL + 1):
            if not dx and not dy:
                continue
            ys = np.clip(np.arange(y0, y1) + dy, 0, H - 1)
            xs = np.clip(np.arange(x0, x1) + dx, 0, W - 1)
            Bs = np.asarray(b, float)[np.ix_(ys, xs)]
            best = np.minimum(best, np.abs(A - Bs).max(axis=2))
    out = d.copy()
    out[y0:y1, x0:x1] = best
    return out.astype(np.float32)


def text_glyph_masks(ref_black, render, compose_black, texts: list[dict], geo: dict, notext_black=None, render_bg=None,
                     notext_skip: set | None = None, color_gate: bool = False) -> dict:
    """글자 위젯마다 컨셉 · 렌더 획(후보 · 핵심). 렌더 획 = 렌더 ↔ 글자 없는 텍스처 합성(compose_black) 차.
    컨셉 획 = 컨셉 ↔ 텍스처 합성 차와 컨셉 ↔ 글자 없는 판(notext_black — 있으면) 차 중 작은 것: 글자 획은 두 바탕 모두와 다르고, 텍스처의 글자 구멍
    메움이 컨셉 바탕과 다른 자리(줄 보간 — [실측 J-b 095249 '돌진 공격' 띠])는 판과 같으며, codex 판이 배지 테두리 · 띠 가장자리를 몇 px 다르게 다시
    그린 자리([실측 J-b 154442 E · T 배지 호])는 합성과 같다. 판이 없으면(ⓑ) 합성만. render_bg = 렌더와 같은 상태(force_visible)의 합성 —
    컨셉에 없는 숨은 빛이 글자 밑에 깔려도 렌더 글자만 떼어 낸다(없으면 compose_black).
    → {wid: {"own", "zone", "concept_cand", "concept", "render_cand", "render"}}"""
    H, W = ref_black.shape[:2]
    owns, zones, cores = {}, {}, {}
    for w in texts:
        g = geo[w["id"]]
        bb = w.get("bbox_intent") or [g["x"], g["y"], g["w"], g["h"]]
        owns[w["id"]] = _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]]) | _box_mask((H, W), bb)
        zones[w["id"]] = _dilate(owns[w["id"]], int(round(max(6.0, 0.5 * float(bb[3])))))
        # 빛 여백을 뺀 글자 상자(analyze 가 빛 크기만큼 사방 넓힘 — 이웃 글자 상자와 겹친다)
        s = float(((w.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(w.get("font"), dict) else 0.0
        cores[w["id"]] = _box_mask((H, W), [bb[0] + s, bb[1] + s, max(1.0, bb[2] - 2 * s), max(1.0, bb[3] - 2 * s)])
    d_c, d_r = maxabs(ref_black, compose_black), maxabs(render, compose_black if render_bg is None else render_bg)
    if color_gate:
        # 1b 후속 K-a 아트 모드 — 바탕(텍스처 · 판)이 컨셉을 다시 그린 아트라 장식이 몇 px 어긋난 채로 차이에 남는다: ±2 px 이동 중 가장 작은 차로 잰다
        # (글자는 아트 어디에도 없어 그대로 남는다) [실측 K R20261118_010950 단색 '2/4' — 아래 테두리 가운데 장식이 획 후보에 섞여 폭 135 px]
        d_c = _shift_min_diff(ref_black, compose_black, zones)
        if notext_black is not None:
            d_c = np.minimum(d_c, _shift_min_diff(ref_black, notext_black, zones))
    if notext_black is not None and not color_gate:
        d_n = np.minimum(d_c, maxabs(ref_black, notext_black))
        if notext_skip:
            skip = np.zeros((H, W), bool)
            for k in notext_skip:
                if k in zones:
                    skip |= zones[k]
            d_c = np.where(skip, d_c, d_n)
        else:
            d_c = d_n
    cc = assign_glyphs(d_c, zones, owns, cores)
    if color_gate:
        # 1b 후속 K-a 아트 모드 — 바탕(아트)이 컨셉을 다시 그린 그림이라 '컨셉과 다른 픽셀'에 다시 그린 장식(패널 모서리)도 낀다: 사양 글자색 근처만 획 후보
        # [실측 K R20261117_234013 '2/4' — 모서리 장식이 획으로 잡혀 크기 · 위치 오류]
        lab_all = None
        for w in texts:
            cols = _font_colors(w)
            if not cols or not cc[w["id"]].any():
                continue
            if lab_all is None:
                lab_all = color.srgb_to_lab(np.asarray(ref_black, float))
            m = cc[w["id"]]
            near = np.min([color.delta_e00(lab_all[m], color.srgb_to_lab(np.asarray(c_, float).reshape(1, 3))) for c_ in cols], axis=0) < GLYPH_COLOR_DE
            keep = np.zeros_like(m)
            keep[m] = near
            cc[w["id"]] = keep
    fc = {w["id"]: _filter_glyph_parts(cc[w["id"]], owns[w["id"]], spacing_gap(w)) for w in texts}
    # 렌더 획 주인은 컨셉에서 정한 획을 따른다(겹치면) — 컨셉 · 렌더가 같은 획을 같은 글자 몫으로
    prior = {k: _dilate(core_of(d_c, v, ref_black), PRIOR_GROW) for k, v in fc.items() if v.any()}
    cr = assign_glyphs(d_r, zones, owns, cores, prior=prior)
    out = {}
    for w in texts:
        k = w["id"]
        a, b = fc[k], _filter_glyph_parts(cr[k], owns[k], spacing_gap(w))
        out[k] = {"own": owns[k], "zone": zones[k], "concept_cand": a, "render_cand": b, "concept": core_of(d_c, a, ref_black),
                  "render": core_of(d_r, b, render, _font_refs(w))}
    return out


TRIM = 1.0                 # 획 상자 = 픽셀 좌표의 TRIM ~ 100 − TRIM 백분위 — 장식 끝 조각 · 잡티 몇 픽셀이 상자를 키우지 않게


def _stats(core, img) -> dict | None:
    if int(core.sum()) < TEXT_MIN_CORE:
        return None
    ys, xs = np.nonzero(core)
    x0, x1 = int(np.floor(np.percentile(xs, TRIM))), int(np.ceil(np.percentile(xs, 100 - TRIM)))
    y0, y1 = int(np.floor(np.percentile(ys, TRIM))), int(np.ceil(np.percentile(ys, 100 - TRIM)))
    # 1b 후속 K — 가는 꼬리(위아래 줄 중 잉크가 몸통 줄의 1/4 도 안 되는 줄 — 긴 사선 '/' 등)가 상자 높이의 15 % 넘게 차지하면서 잉크는 10 % 미만이면
    # 높이는 몸통 줄로 잰다 — 글꼴마다 사선 길이가 달라 '2/4' 크기가 1.69 배로 재져 크기 · 위치를 못 믿었다 [실측 K R20261118_000325]
    rows = np.asarray(core, bool).sum(axis=1)
    nz = rows[rows > 0]
    body = np.nonzero(rows >= 0.25 * float(np.percentile(nz, 75)))[0] if len(nz) else np.array([], int)
    tail = False
    if len(body):
        # 늘 몸통 줄로(컨셉 · 렌더 같은 규칙) — '꼬리가 높이의 15 % 넘을 때만'으로 하자 크기마다 켜졌다 꺼져 '2/4' 맞춤이 30 → 22 → 26 으로 진동했다
        # [실측 K R20261118_002153]
        by0, by1 = int(body.min()), int(body.max())
        if by0 > y0 or by1 < y1:
            y0, y1, tail = max(y0, by0), min(y1, by1), True
    bb = [x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1)]
    x, y, w, h = bb
    sub = core[y:y + h, x:x + w]
    lab = np.median(color.srgb_to_lab(np.asarray(img, float)[core]), axis=0)
    # 밀도 = 잉크 있는 열만(빈 열 — 낱말 · 글자 사이 틈 — 뺌): 상자 전체로 재면 자간이 굵기 판정을 바꿨다 [실측 L-2 R20261118_171644 '체인 버스트' —
    # 위치 판 자간 +2 px 에 밀도 비 0.936 → 0.898 로 굵기 E9 가 새로 생겨 판이 버려짐]. 굵기 표(pipeline.yaml fonts.weight_density)도 같은 정의로 잼
    cols = sub.any(axis=0)
    dens = float(sub[:, cols].mean()) if cols.any() else 0.0
    return {"box": bb, "center": [x + w / 2.0, y + h / 2.0], "px": int(core.sum()), "density": round(dens, 4),
            "gap_cols": int((~cols).sum()), "lab": [round(float(v), 2) for v in lab], **({"thin_tail_cut": True} if tail else {})}


def _edge_fracs(cand, core, img, bg) -> tuple[float, float] | None:
    """글자 후보 중 (바탕보다 어두운 픽셀 비율 — 외곽선 · 그림자, 핵심 획 밖이면서 바탕보다 밝은 픽셀 비율 — 빛 번짐 · 안티앨리어싱).
    렌더 획 마스크는 엔진 외곽선까지 품어 둘레 띠로는 외곽선이 안 보인다 — 획 안에서 센다."""
    if int(cand.sum()) < TEXT_MIN_CORE:
        return None
    dl = color.srgb_to_lab(np.asarray(img, float)[cand])[..., 0] - color.srgb_to_lab(np.asarray(bg, float)[cand])[..., 0]
    # 빛 = 핵심 획에서 1 px 넘게 떨어진 밝은 픽셀 — 바로 옆 1 px 은 안티앨리어싱 · 흐림(생성 컨셉의 작은 글자는 렌더보다 흐리다 —
    # [실측 J R20261117_185327 '체인' 22 크기: 1 px 고리까지 세면 0.34 ↔ 0.13 으로 '빛' 오판])
    halo = (~_dilate(core, 1)[cand]) & (dl > 8)
    return float((dl < -8).mean()), float(halo.mean())


def fonts_without_sdf(cfg: dict | None) -> set[str] | None:
    """SDF(거리장) 사본이 없는 글꼴 family — 엔진이 글자 빛(font.glow)을 못 그린다(pipeline.yaml fonts — 기본 family = body)."""
    if not cfg or not cfg.get("fonts"):
        return None
    from core import config
    try:
        roles = config.font_roles(cfg)
    except Exception:  # noqa: BLE001
        return None
    return {v["family"] for v in roles.values() if not v.get("sdf_family")}


MEASURE_TRUST_H = (0.7, 1.4)   # 글자 획 상자 높이 비 신뢰 범위(style.TEXT_FIT_TRUST_H 와 같음)
MEASURE_TRUST_WH = 0.3         # 폭 비 ÷ 높이 비가 1 에서 이만큼 넘게 벗어나면 측정을 못 믿음(style.TEXT_FIT_TRUST_WH 와 같음)
MEASURE_TRUST_H_WIDE = 1.6     # 폭 비 ÷ 높이 비가 1 ± 0.2 안이면(크기만 다른 같은 모양) 높이 비 상한을 여기까지 — [실측 K R20261118_000325 '2/4' 1.42 · 폭 1.20]


def measure_trusted(hr: float, wr: float) -> bool:
    """글자 획 상자 비교를 믿나 — 진단 · 글자 맞춤(style.text_fit 크기 판) 공용. 하한 0.7 은 그대로('T' 0.632 → 40 → 63 오판, H2)."""
    wh = abs(wr / max(1e-6, hr) - 1.0)
    if wh > MEASURE_TRUST_WH or hr < MEASURE_TRUST_H[0]:
        return False
    return hr <= MEASURE_TRUST_H[1] or (hr <= MEASURE_TRUST_H_WIDE and wh <= 0.2)


GLOW_PEAK_D = (2, 6)       # 빛 판정 띠(획에서 px)
GLOW_RING_D = (2.0, 10.0)  # 빛 비율 고리
GLOW_FAR_D = (12.0, 16.0)  # 바탕 색조 차(판 ↔ 컨셉) 기준 고리 — 그만큼 빼고 잰다
GLOW_TAIL = 3.0            # 빛 끝 = 바탕보다 이만큼 밝은 마지막 거리
GLOW_MAXD = 16


def glow_measure(img, bg, strokes, min_excess: float = DEFAULTS["glow_min"], max_d: int = GLOW_MAXD) -> dict | None:
    """1b 후속 K E7 — 글자 빛 단일 측정: analyze derive_text_glow · 글자 맞춤(style._fit_glow) · 진단이 이 함수 하나를 쓴다.
    획(strokes) 둘레 거리 d 띠마다 (L(img) − L(bg)) 중앙값 — bg = 같은 자리의 글자 없는 바탕(렌더면 텍스처 합성, 컨셉이면 글자 없는 판).
    판 ↔ 컨셉 색조 차는 12 ~ 16 px 고리의 중앙값만큼 빼고 잰다. bg 가 None 이면 10 ~ 14 px 띠 밝기 중앙값을 바탕으로(예전 analyze — 판이 없을 때).
    [실측 J 남은 일 사람 눈] analyze 만 바탕을 '획 10 ~ 14 px 밖 띠'로 재 두 톤 띠 밝기를 빛으로 봤고('돌진 공격' · '공격' 청록 빛), 진단은 후보 마스크 안만
    세 그 빛을 못 봤다. → {present, peak, size, frac(2 ~ 10 px 고리 중 8 넘게 밝은 비율), excess{d: L}} · 획이 없으면 None."""
    import cv2
    bb = _bbox(strokes)
    if bb is None:
        return None
    H, W = strokes.shape
    p = max_d + 2
    x0, y0, x1, y1 = max(0, bb[0] - p), max(0, bb[1] - p), min(W, bb[0] + bb[2] + p), min(H, bb[1] + bb[3] + p)
    st = np.asarray(strokes, bool)[y0:y1, x0:x1]
    dist = cv2.distanceTransform((~st).astype(np.uint8), cv2.DIST_L2, 5)
    L = color.srgb_to_lab(np.asarray(img, float)[y0:y1, x0:x1])[..., 0]
    if bg is None:
        ring = (dist > 10) & (dist <= 14)
        if not ring.any():
            return None
        dL = L - float(np.median(L[ring]))
    else:
        dL = L - color.srgb_to_lab(np.asarray(bg, float)[y0:y1, x0:x1])[..., 0]
        far = (dist > GLOW_FAR_D[0]) & (dist <= GLOW_FAR_D[1])
        if far.any():
            dL = dL - float(np.median(dL[far]))
    exc = {}
    for d in range(1, max_d + 1):
        m = (dist > d - 1) & (dist <= d)
        exc[d] = float(np.median(dL[m])) if m.any() else 0.0
    peak = max(exc[d] for d in range(GLOW_PEAK_D[0], GLOW_PEAK_D[1] + 1))
    ring = (dist > GLOW_RING_D[0]) & (dist <= GLOW_RING_D[1])
    frac = float((dL[ring] > 8).mean()) if ring.any() else 0.0
    present = peak >= float(min_excess)
    size = 0
    if peak >= float(min_excess) / 2:      # 크기는 '빛 있음'(glow_on — 문턱의 절반)부터 잰다
        size = 2
        while size + 1 <= max_d and exc[size + 1] >= GLOW_TAIL:
            size += 1
        size = max(3, size + 1)
    band = (dist > GLOW_PEAK_D[0] - 1) & (dist <= GLOW_PEAK_D[1])
    if bg is None:
        bgl = float(np.median(L[(dist > 10) & (dist <= 14)])) if ((dist > 10) & (dist <= 14)).any() else 0.0
    else:
        bgl = float(np.median(color.srgb_to_lab(np.asarray(bg, float)[y0:y1, x0:x1])[..., 0][band])) if band.any() else 0.0
    return {"present": bool(present), "peak": round(peak, 1), "size": int(size), "frac": round(frac, 3), "bg_l": round(bgl, 1),
            "excess": {d: round(v, 1) for d, v in exc.items() if d <= 12}}


SHADOW_MAXD = 3            # 1b 후속 L-3c — 그림자 오프셋 탐색 범위(px)
SHADOW_MIN = 16.0          # 그림자 있음 = 옮긴 획 자리가 글자 없는 바탕보다 L* 이만큼 어둡고 그만큼 반대쪽보다도 더 어두움(외곽선 · 고른 테는 사방이 같아 빠짐)
                           # [실측 L — 조작 안내 띠 위 글자는 띠 경계 탓에 9.6 ~ 11.3(그림자 아님), 키 배지 글자 그림자 20.3, 원래 전투 HUD 글자 ≤ 3]


def shadow_measure(img, bg, strokes, min_dark: float = SHADOW_MIN, max_d: int = SHADOW_MAXD) -> dict | None:
    """1b 후속 L-3c — 글자 그림자 단일 측정(진단 E7 · 글자 맞춤 style._fit_shadow 공용, glow_measure 와 같은 생각): 핵심 획을 (dx, dy) 옮긴 자리(획 밖)에서
    L(바탕) − L(img) 중앙값이 반대쪽 (−dx, −dy) 보다 얼마나 더 어두운가. bg = 같은 자리의 글자 없는 바탕(렌더면 텍스처 합성, 컨셉이면 글자 없는 판),
    None 이면 획 10 ~ 14 px 밖 고리 중앙값. [사람 눈 L — 원래 전투 HUD '체인 버스트' · '체인' · '2/4' 오른쪽 아래 얇은 그림자, 진단 어두운 비율 차 0.065 ~ 0.117
    로 외곽선 기준(0.2) 밖이라 오류도 근사도 아니었다]. → {present, offset, dark, color} · 획이 없으면 None."""
    import cv2
    bb = _bbox(strokes)
    if bb is None:
        return None
    H, W = strokes.shape
    p = max(max_d, 14) + 2
    x0, y0, x1, y1 = max(0, bb[0] - p), max(0, bb[1] - p), min(W, bb[0] + bb[2] + p), min(H, bb[1] + bb[3] + p)
    st = np.asarray(strokes, bool)[y0:y1, x0:x1]
    L = color.srgb_to_lab(np.asarray(img, float)[y0:y1, x0:x1])[..., 0]
    if bg is None:
        dist = cv2.distanceTransform((~st).astype(np.uint8), cv2.DIST_L2, 5)
        ring = (dist > 10) & (dist <= 14)
        if not ring.any():
            return None
        dark = float(np.median(L[ring])) - L
    else:
        dark = color.srgb_to_lab(np.asarray(bg, float)[y0:y1, x0:x1])[..., 0] - L
    h, w = st.shape
    aa = _dilate(st, 1)          # 획 바로 옆 1 px 은 안티앨리어싱(글자색 섞임 — 밝음)이라 뺀다

    def moved(dx, dy):
        out = np.zeros_like(st)
        ys0, ys1 = max(0, dy), min(h, h + dy)
        xs0, xs1 = max(0, dx), min(w, w + dx)
        out[ys0:ys1, xs0:xs1] = st[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
        return out & ~aa
    best = None
    for dy in range(-max_d, max_d + 1):
        for dx in range(-max_d, max_d + 1):
            if not dx and not dy:
                continue
            m, o = moved(dx, dy), moved(-dx, -dy)
            if int(m.sum()) < 10 or int(o.sum()) < 10:
                continue
            # 옮긴 자리 평균 — 중앙값이면 (2, 2) 그림자에서 (2, 0) 도 같은 점수라 오프셋이 갈리지 않았다
            d_m, d_o = float(np.mean(dark[m])), float(np.median(dark[o]))
            score = d_m - max(0.0, d_o)
            if best is None or score > best[0] + 0.5 or (abs(score - best[0]) <= 0.5 and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2])):
                best = (score, dx, dy, d_m, m)
    if best is None:
        return None
    score, dx, dy, d_m, m = best
    present = score >= min_dark and d_m >= min_dark
    sel = m & (dark >= min_dark)
    c = np.median(np.asarray(img, float)[y0:y1, x0:x1][sel], axis=0) if sel.any() else np.zeros(3)
    return {"present": bool(present), "offset": [int(dx), int(dy)], "dark": round(score, 1),
            "color": "#%02X%02X%02XFF" % tuple(int(round(min(255.0, max(0.0, float(v))))) for v in c)}


CLEAR_RING = 6             # 투명 위 글자 판정 둘레 고리(px)
CLEAR_ALPHA = 0.35         # 그 고리 컨셉 알파 중앙값이 이 미만이면 '투명 위 글자'(refine.PLATE_CLEAR_ALPHA 와 같은 값)


def clear_text_residue(col, alpha, cc, ca, spec: dict) -> tuple:
    """1b 후속 K — 글자 없는 판(곧은 색 col · 알파)에서 '투명 위 글자' 자리의 잔상을 지운다: 글자 상자(+ 빛 + 2 px) 안을 컨셉(cc · ca)으로 바꾸고 컨셉 글자 획
    (컨셉 ↔ 판이 다른 픽셀 + 3 px + 빛)만 둘레 컨셉으로 메운다. 상자 둘레 컨셉이 불투명(띠 · 패널 위 글자)이면 판 그대로. refine 아트 · analyze 빛 바탕 ·
    진단 빛 바탕이 같이 쓴다 [실측 K R20261117_233356 — codex 요소 없는 판이 투명 위 붉은 '오의 불가' 를 붉은 얼룩으로 남겨 렌더 얼룩 · 숨은 상태 오판 ·
    빛 측정 실패]. → (색, 알파, 기록)."""
    H, W = ca.shape
    col, alpha = np.array(col, float, copy=True), np.array(alpha, float, copy=True)
    recs = []
    for t in spec.get("widgets", []):
        bb = t.get("bbox_intent")
        if t.get("type") not in backdrop.TEXT_TYPES or not bb:
            continue
        glow = float(((t.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(t.get("font"), dict) else 0.0
        import cv2
        reg = _box_mask((H, W), bb, glow + 2)
        inside = _box_mask((H, W), bb)
        ring = _dilate(reg, CLEAR_RING) & ~reg
        if not ring.any() or float(np.median(ca[ring])) >= CLEAR_ALPHA:
            continue
        ys, xs = np.nonzero(_dilate(reg, CLEAR_RING + 2))
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        r = reg[y0:y1, x0:x1]
        csub, asub = cc[y0:y1, x0:x1], ca[y0:y1, x0:x1]
        # 상자 밖으로 이어진 불투명 구조물(프레임 선 · 패널)은 컨셉 그대로 지킨다(+ 2 px). 그 구조물이 상자 절반 이상이면 투명 위 글자가 아니다(패널 위 글자) —
        # 둘레 고리만 보면 패널 폭으로 넓힌 상자('2/4')가 패널 밖 투명에 걸쳐, 상자 안 알파만 보면 글자에 딱 맞는 상자('오의 불가' — 빛 · 획이 절반)가 오판했다
        # [실측 K R20261117_234013 · 235644]
        n_o, lab_o = cv2.connectedComponents((asub > 0.5).astype(np.uint8), connectivity=8)
        cross = np.unique(lab_o[(lab_o > 0) & ~r])
        protect = _dilate(np.isin(lab_o, cross[cross > 0]), 2) if len(cross) else np.zeros_like(r)
        if float(protect[r].mean()) >= 0.5:
            continue
        # 상자 안은 투명으로 — 글자 · 빛은 엔진이 그린다(획 구멍을 둘레로 메우면 컨셉 빛 번짐이 텍스처에 구워졌다 [실측 K R20261117_234013 '오의 불가' ㅇ 속])
        hole = r & ~protect
        fc, fa = csub, np.where(hole, 0.0, asub)
        col[y0:y1, x0:x1] = np.where(r[..., None], fc, col[y0:y1, x0:x1])
        alpha[y0:y1, x0:x1] = np.where(r, fa, alpha[y0:y1, x0:x1])
        recs.append({"text": t["id"], "box_alpha": round(float(np.median(ca[inside])), 3), "ring_alpha": round(float(np.median(ca[ring])), 3) if ring.any() else None,
                     "hole_px": int(hole.sum()), "box_px": int(r.sum())})
    return col, alpha, recs


def _fill_track(rd: pathlib.Path, spec: dict, w: dict, shape) -> np.ndarray | None:
    """게이지(ProgressBar) 채움이 concept_fill 이면 그 트랙 안쪽 마스크(캔버스 좌표 — gen/concept_fill.unfilled_track 과 같은 그림 reference.png), 아니면 None."""
    fill = (w.get("style") or {}).get("fill")
    if not isinstance(fill, dict):
        return None
    proc = next(((a.get("procedural") or {}) for a in spec.get("assets", []) if a.get("asset_id") == fill.get("asset")), {})
    if proc.get("shape") != "concept_fill" or not proc.get("frame_box") or not (rd / "reference.png").is_file():
        return None
    try:
        from gen import concept_fill
        hole, _ = concept_fill.unfilled_track(_load_rgb(rd / "reference.png"), proc)
    except Exception:  # noqa: BLE001 — 못 재면 상자
        return None
    out = np.zeros(shape, bool)
    fx, fy, fw, fh = (int(v) for v in proc["frame_box"])
    H, W = shape
    sx0, sy0, sx1, sy1 = max(0, fx), max(0, fy), min(W, fx + fw), min(H, fy + fh)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0:sy1, sx0:sx1] = np.asarray(hole, bool)[sy0 - fy:sy1 - fy, sx0 - fx:sx1 - fx]
    return out if out.any() else None


def art_mode(bgrec: dict | None) -> bool:
    """1b 후속 L-1 — '글자 없는 아트가 아트의 정답'인가. 원본 생성 아트(L-2 — normalize background.art role original)일 때만 참.
    글자 든 컨셉이 사람이 승인한 그림이면 codex 가 다시 그린 글자 없는 판은 정답이 아니다 — 컨셉 픽셀 + 글자 자리만 판(외부 컨셉 길과 하나로), 진단도 컨셉과
    [실측 K R20261118_003804 — 판을 정답으로 삼자 배너 렌더 ↔ 컨셉 국소 상위 5 % 10.9(J 컨셉 픽셀 0.5), 진단은 판과 비교해 못 봄]. refine.art_files 와 같은 조건."""
    art = (bgrec or {}).get("art") or {}
    return bool(art.get("used")) and art.get("role") == "original"


def residue_free(rec: dict | None) -> bool:
    """1b 후속 L-2 — 아트 · 글자 없는 판 기록(normalize background.art · notext)이 '글자를 그린 적 없는 원본 아트'(text_residue False)인가.
    그러면 투명 위 글자 잔상 지우기(clear_text_residue — K 의 codex 판 잔상용)를 건너뛴다: 지울 잔상이 없고, 글자 상자 안의 아트 장식까지 비울 수 있다."""
    return (rec or {}).get("text_residue") is False


def art_element_free(bgrec: dict | None) -> bool:
    """아트가 K 의 '요소 없는 판'(게이지 채움 · 런타임 그림을 비운 판)인가 — L-2 원본 아트는 게이지 채움까지 그린 그림이라 False(element_free)."""
    return ((bgrec or {}).get("art") or {}).get("element_free", True) is not False


def _refine_spec(rd: pathlib.Path, spec: dict) -> dict:
    """refine 때 spec(specs/000.json) — 잔상 지우기를 refine 과 같은 글자 상자로(글자 맞춤이 상자를 바꿔도). 없으면 지금 spec."""
    try:
        return json.loads((rd / "specs" / "000.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return spec


def notext_layers(rd: pathlib.Path, nt: dict, spec: dict) -> tuple:
    """글자 없는 판 (곧은 색, 알파) — 투명 위 글자 자리 잔상은 지운 것(clear_text_residue — refine 아트 · analyze 와 같음)."""
    spec = _refine_spec(rd, spec)
    col, alpha = _load_rgb(rd / nt["color"]), _load_l(rd / nt["alpha"])
    if not residue_free(nt) and (rd / "reference_color.png").is_file() and (rd / "reference_alpha.png").is_file():
        col, alpha, _ = clear_text_residue(col, alpha, _load_rgb(rd / "reference_color.png"), _load_l(rd / "reference_alpha.png"), spec)
    return col, alpha


def _notext_cleared(rd: pathlib.Path, nt: dict, spec: dict):
    """글자 없는 판(검정 위 미리 곱한 색) — 투명 위 글자 자리 잔상은 지운 것(clear_text_residue — refine 아트 · analyze 와 같음)."""
    col, alpha = notext_layers(rd, nt, spec)
    return col * alpha[..., None]


MANUAL_CHECKS = ("text_trace", "text_contour", "text_lift", "text_value_trace", "text_value_contour")
MANUAL_OVERLAP = 0.6                # 결함 상자의 이만큼 이상이 '정답 없음' 자리(+ 빛 + 4 px) 안이어야 수동 확인으로 돌림


def manual_checks(rd: pathlib.Path) -> list[dict]:
    """1b 후속 L 다음 — 글자 지우기 다음(사용자 결정 ③ · V8): refine 마지막 고르기(refine.json passes[].erase_gate[].manual_check)의 수동 확인 표시 —
    reason no_truth(글자 밑 정답 없는 자리 — 근거 · 자리 상자) · complex_background(복잡 배경 — 기록만)."""
    try:
        doc = json.loads((pathlib.Path(rd) / "refine.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for p in doc.get("passes") or []:
        eg = p.get("erase_gate")
        if eg:
            out = [{**m, "asset": aid} for aid, r in eg.items() for m in (r.get("manual_check") or [])]
    return out


def manual_match(f: dict, checks: list[dict], spec: dict) -> dict | None:
    """S4 결함 f 가 '정답 없음' 표시(같은 글자 · 자리 상자 + 빛 + 4 px 안에 결함 상자의 MANUAL_OVERLAP 이상)에 드는가 → 그 표시 또는 None. 다른 결함은 그대로 오류."""
    if f.get("check") not in MANUAL_CHECKS or not f.get("widgets") or not f.get("box"):
        return None
    index = {w["id"]: w for w in spec.get("widgets", [])}
    x, y, w, h = (float(v) for v in f["box"])
    for m in checks:
        if m.get("reason") != "no_truth" or m.get("widget") != f["widgets"][0] or not m.get("box"):
            continue
        fw = index.get(m["widget"]) or {}
        gl = float(((fw.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(fw.get("font"), dict) else 0.0
        bx, by, bw, bh = (float(v) for v in m["box"])
        p = gl + 4.0
        ix = max(0.0, min(x + w, bx + bw + p) - max(x, bx - p))
        iy = max(0.0, min(y + h, by + bh + p) - max(y, by - p))
        if ix * iy >= MANUAL_OVERLAP * max(1.0, w * h):
            return {"reason": "no_truth", "box": m["box"], "evidence": m.get("evidence")}
    return None


def composite_text_trace(rd: pathlib.Path, spec: dict, boxes: list[dict], textures: dict, s: dict, gm: dict | None = None,
                         cache: dict | None = None) -> tuple[dict, dict]:
    """1b 후속 L 다음 — 글자 지우기 마감: 게이트와 같은 함수(text_glyph_masks + state_check.text_trace — 가는 선 · 숨는 묶음 포함)로 S4 를 텍스처 합성만으로
    (엔진 없음). refine 의 글자 지우기 고르기(텍스처 후보마다 캔버스 합성)와 회귀 묶음 replay 가 같이 쓴다 — 텍스처 단독 점수는 캔버스 합성 · 다른 텍스처
    겹침 · 바탕 셋이 달라 조작 안내 악화를 못 가렸다 [실측 회귀 k_final_1119]. gm 을 주면 그 글자 획(후보끼리 같은 자리로 견주게).
    cache = 같은 run 의 컨셉 · 판 읽기를 다시 안 하게(부르는 쪽 dict). → (tt, {gm, comp, not_drawn, texts})."""
    from gen import state_check
    c = cache if cache is not None else {}
    canvas = [int(v) for v in (spec.get("canvas") or [1920, 1080])]
    if "ref_text" not in c:
        norm = json.loads((rd / "normalize.json").read_text(encoding="utf-8"))
        bgrec = norm.get("background") or {}
        nt = bgrec.get("notext") or {}
        rc, ra = _load_rgb(rd / "reference_color.png"), _load_l(rd / "reference_alpha.png")
        ref_text = rc * ra[..., None]
        notext = _notext_cleared(rd, nt, spec) if nt.get("used") and (rd / str(nt.get("color"))).is_file() else None
        plate = notext_layers(rd, nt, spec) if nt.get("used") and (rd / str(nt.get("color"))).is_file() and (rd / str(nt.get("alpha"))).is_file() else None
        truth = ref_text
        art = bgrec.get("art") or {}
        if art_mode(bgrec) and (rd / str(art.get("color"))).is_file():
            truth = _load_rgb(rd / art["color"]) * _load_l(rd / art["alpha"])[..., None]
        c.update(ref_text=ref_text, rc=rc, ra=ra, notext=notext, plate=plate, truth=truth, bgrec=bgrec, skip=notext_unused(rd))
    geo = {b["id"]: b for b in boxes}
    comp, cov, _ = backdrop.compose(spec, boxes, textures, canvas, (0, 0, 0))
    not_drawn, states = hidden_state_split(spec, boxes, textures, canvas, c["truth"], comp, comp, cov, ref_text=c["ref_text"], notext_black=c["notext"])
    sp = _without(spec, not_drawn) if not_drawn else spec
    comp_s = backdrop.compose(sp, boxes, textures, canvas, (0, 0, 0))[0] if not_drawn else comp
    texts = [w for w in spec.get("widgets", []) if w.get("type") in backdrop.TEXT_TYPES and w["id"] not in not_drawn and w.get("bbox_intent")]
    if gm is None:
        gm = text_glyph_masks(c["ref_text"], comp_s, comp_s, texts, geo, c["notext"], render_bg=comp_s, notext_skip=c["skip"], color_gate=art_mode(c["bgrec"]))
    roots = _hidden_roots(spec)
    off_ids: set[str] = set()
    for r_ in roots:
        off_ids |= _subtree(spec, r_)
    sp_off = _without(spec, off_ids)
    bgs = (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))
    imgs = {k: backdrop.compose(sp_off, boxes, textures, canvas, bg)[0] for k, bg in bgs}
    groups = state_check.texture_groups(spec, textures)
    for g_ in groups:
        off_g: set[str] = set()
        for r_ in roots:
            if r_ != g_["root"]:
                off_g |= _subtree(spec, r_)
        sp_g = _without(spec, off_g)
        g_["images"] = {k: backdrop.compose(sp_g, boxes, textures, canvas, bg)[0] for k, bg in bgs}
        g_["render"] = None
    tt = state_check.text_trace(spec, boxes, canvas, c["rc"], c["ra"], c["plate"], gm, s, imgs, groups=groups)
    bg = text_zone_bg(c["ref_text"], c["truth"], comp_s, gm, texts, c["notext"], s)
    return tt, {"gm": gm, "comp": comp_s, "not_drawn": not_drawn, "texts": texts, "states": states, "bg": bg}


def text_zone_bg(ref_text, truth, comp, gm: dict, texts: list[dict], notext, s: dict) -> dict:
    """1b 후속 L 다음 — 글자 지우기 다음: 컨셉 상태 글자 구역 바탕(렌더 없이 텍스처 합성만 — 진단 E1 글자 구역 바탕 · regress_set 텍스처 지표와 같은 정의): 글자 상자
    + TEXT_ZONE_PAD + 빛에서 컨셉 글자 획(후보 · 핵심 + 4 px 붙은 차 · 빛 반경 · 밝은 빛) + 2 px 를 뺀 자리의 합성 ↔ 정답 7 × 7 국소 ΔE00. 엔진이 그 위에 글자 · 빛만
    그리므로 이 자리의 합성 차는 컨셉 상태에서 그대로 보인다 — 지운 판 고르기가 빈 값 S4 만 보고 고른 판이 컨셉 상태 E1 을 만들었다 [실측 R20261122_135359 파티 방패
    lama — E1 75, R20261120_142400 Lv clear_alpha — E1 9]. → {글자: {"bg_max", "bg_px": 국소 > local_de 픽셀}}."""
    import cv2
    H, W = comp.shape[:2]
    eff_bg = notext if notext is not None else comp
    brighter = (color.srgb_to_lab(ref_text)[..., 0] - color.srgb_to_lab(eff_bg)[..., 0]) > 4.0
    attached = maxabs(ref_text, eff_bg) > INK_FLOOR
    strokes = np.zeros((H, W), bool)
    for w in texts:
        v = gm.get(w["id"])
        if v is None:
            continue
        gl = float(((w.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(w.get("font"), dict) else 0.0
        strokes |= v["concept_cand"] | v["concept"] | (_dilate(v["concept"], 4) & attached)
        if gl:
            strokes |= _dilate(v["concept"], int(round(gl))) | (_dilate(v["concept"], GLOW_MAXD) & brighter)
    strokes = _dilate(strokes, 2)
    de = delta_e(comp, truth)
    T, cov = float(s["local_de"]), float(s["bg_cover"])
    out = {}
    for w in texts:
        f = w.get("font") if isinstance(w.get("font"), dict) else {}
        gl = float((f.get("glow") or {}).get("size") or 0)
        zone = _box_mask((H, W), w["bbox_intent"], TEXT_ZONE_PAD + gl) & ~strokes
        if not zone.any():
            continue
        c_ = cv2.blur(zone.astype(np.float32), (WIN, WIN))
        loc = np.where(c_ >= cov, cv2.blur((de * zone).astype(np.float32), (WIN, WIN)) / np.maximum(c_, 1e-6), 0.0)
        z = zone & (c_ >= cov)
        if z.any():
            out[w["id"]] = {"bg_max": round(float(loc[z].max()), 2), "bg_px": int((loc[z] > T).sum())}
    return out


def trace_scores(tt: dict) -> dict:
    """composite_text_trace 결과 → 글자마다 {"local": 바탕 셋 최대 3 × 3 국소, "lift": 밝힌 검정(기록), "contour": 가는 선 골격 길이 최대,
    "findings": 결함 수(text_trace · text_contour)}."""
    out = {}
    for t in tt.get("texts") or []:
        if t.get("skipped"):
            continue
        lm = t.get("local_max") or {}
        out[t["widget"]] = {"local": round(max([v for k, v in lm.items() if k != "lift"] or [0.0]), 2), "lift": round(float(lm.get("lift") or 0.0), 2),
                            "contour": int(t.get("contour_len") or 0), "findings": 0}
    for f in tt.get("findings") or []:
        if f.get("check") in ("text_trace", "text_contour", "text_lift") and f.get("widgets"):
            w0 = f["widgets"][0]
            if w0 in out:
                out[w0]["findings"] += 1
    return out


def glow_alpha(f: dict | None) -> float | None:
    """사양 빛 색(font.glow.color '#RRGGBBAA')의 알파 0 ~ 1 — 빛 세기 어휘. 빛이 없거나 알파가 없으면(#RRGGBB) None · 1.0."""
    g = (f or {}).get("glow") if isinstance(f, dict) else None
    if not isinstance(g, dict) or not g.get("size"):
        return None
    h = str(g.get("color") or "").lstrip("#")
    return int(h[6:8], 16) / 255.0 if len(h) >= 8 else 1.0


def glow_on(g: dict | None, gmin: float = DEFAULTS["glow_min"]) -> bool:
    """빛 있음(진단 E7 · 글자 맞춤 넣기 · 떼기 공용) = 띠 밝기 ≥ 문턱의 절반. analyze 는 더 보수적으로 문턱(present)일 때만 붙이고, 그 사이는 맞춤이 넣는다
    — 넣기 · 떼기 문턱이 다르면 진동했다 [실측 K R20261118_004754 '4.2' 컨셉 6.1 — 넣고(3) 다음 판에 뗌]."""
    return bool(g) and float(g.get("peak") or 0) >= gmin / 2


def weight_table(cfg: dict | None, family: str | None) -> dict[str, float] | None:
    """1b 후속 K — 그 글꼴 family(에셋 경로)가 가진 굵기 → 획 밀도(Regular = 1, pipeline.yaml fonts.weight_density [실측 PIL]). 없으면 None."""
    if not cfg or not family:
        return None
    t = ((cfg.get("fonts") or {}).get("weight_density") or {}).get(family)
    return {str(k): float(v) for k, v in t.items()} if isinstance(t, dict) and t else None


def nearest_weight(dens: float, cur: str, table: dict[str, float]) -> tuple[str, float]:
    """밀도 비(렌더 ÷ 컨셉) dens 인 지금 굵기 cur 에서, 가진 굵기 중 컨셉에 가장 가까운 것(로그 거리) → (굵기, 그 굵기로 바꾼 뒤 예상 밀도 비)."""
    base = table.get(cur)
    if not base or dens <= 0:
        return cur, dens
    best = min(table, key=lambda k: abs(np.log(dens * table[k] / base)))
    return best, dens * table[best] / base


CONCEPT_CONTRAST_MIN = 10.0   # 1b 후속 L 다음 — 컨셉 핵심 획 ↔ 둘레 바탕(획 밖 1 ~ 4 px · 후보 밖) 대표색 ΔE00 이 이 미만이면 컨셉 획을 못 찾은 것(바탕을 획으로 잼)
CONTRAST_RING = (1, 4)        # [실측 R20261118_130201 파티 '100' 0.5 · 이름 2.2 ↔ 정상 글자(보호 run 다섯 · 단색 · 정답 묶음 run) 39.5 이상]


def concept_contrast(core, cand, img) -> float | None:
    """컨셉 핵심 획 대표색(중앙값 Lab) ↔ 둘레 바탕 대표색 ΔE00 — 글자는 바탕과 구별돼야 읽힌다. 둘레 = 핵심 획 밖 1 ~ 4 px 중 획 후보 밖(없으면 후보 밖 고리)."""
    if int(np.asarray(core).sum()) < TEXT_MIN_CORE:
        return None
    ring = _dilate(core, CONTRAST_RING[1]) & ~_dilate(core, CONTRAST_RING[0]) & ~np.asarray(cand, bool)
    if int(ring.sum()) < 10:
        ring = _dilate(cand, CONTRAST_RING[1]) & ~_dilate(cand, CONTRAST_RING[0])
        if int(ring.sum()) < 10:
            return None
    img = np.asarray(img, float)
    a = np.median(color.srgb_to_lab(img[np.asarray(core, bool)]), axis=0)
    b = np.median(color.srgb_to_lab(img[ring]), axis=0)
    return float(color.delta_e00(a, b))


def baked_glyphs(masks: dict, ref_black, compose_black, concept_bg) -> dict | None:
    """1b 후속 L 다음 — 텍스처에 컨셉 글자가 남았나: 글자 상자 안 컨셉 ↔ 글자 없는 판 차 > INK_MIN 인 픽셀(작은 잡티 빼고 ≥ 3 × TEXT_MIN_CORE) 중
    텍스처 합성이 컨셉과 INK_FLOOR 안으로 같은 몫 ≥ BAKED_KEEP. 판이 없으면(판을 안 쓴 글자) None."""
    if concept_bg is None:
        return None
    own = np.asarray(masks.get("own"), bool)
    g = _drop_small(own & (maxabs(ref_black, concept_bg) > INK_MIN))
    n = int(g.sum())
    if n < 3 * TEXT_MIN_CORE:
        return None
    kept = g & (maxabs(compose_black, ref_black) <= INK_FLOOR)
    frac = float(kept.sum()) / n
    return {"glyph_px": n, "kept_frac": round(frac, 3), "box": _bbox(kept)} if frac >= BAKED_KEEP else None


def _declared_fonts(rd: pathlib.Path) -> dict[str, dict]:
    """run 의 brief 가 가진 '글꼴로 그린 참고판의 글꼴 값'(위젯 id → {size, weight, color}) — 없으면 {}."""
    p = pathlib.Path(rd) / "brief.json"
    if not p.is_file():
        return {}
    from stages import analyze
    return analyze.declared_fonts(json.loads(p.read_text(encoding="utf-8")))


def compare_text(w: dict, masks: dict, ref_black, render, compose_black, s: dict, render_bg=None, no_sdf: set | None = None,
                 concept_bg=None, weights: dict | None = None, declared: dict | None = None) -> dict:
    """글자 하나 — 오류(causes → 번호 TEXT_CODES)와 근사(approx: 가장 가까운 선택을 골랐는데 남은 차 — 표현 한계).
    declared = 글꼴로 그린 참고판이 정한 글꼴 값(brief font — 메인 HUD 11-24): 굵기는 그림을 재지 않고 '그 값과 같은가'로 본다(작은 글자의 획 밀도는 같은 글꼴에서도
    ± 15 % 흔들린다). 크기(높이 비) · 색 차는 그대로 재서 실제로 다르면 오류 — 글자 맞춤이 고칠 수 없으므로 fixable 아님."""
    c, r = _stats(masks["concept"], ref_black), _stats(masks["render"], render)
    rec: dict = {"widget": w["id"], "concept": c, "render": r, "approx": []}
    causes = []
    if c is None:
        # 1b 후속 L 다음 — 컨셉 획 = 컨셉 ↔ 텍스처 합성 차라, 텍스처가 컨셉 글자를 그대로 남기면 획이 비어 아무 말 없이 건너뛰었다(렌더 = 남은 글자 + 엔진 글자
        # 이중) [사람 눈 아님 — 이 세션 compare.png 확인, controls_alpha R20261119_004119 '돌진 공격' 진단 오류 0]. 글자 없는 판과 다른 컨셉 글자 픽셀을 텍스처가
        # 그대로 가지면 E1 baked
        bk = baked_glyphs(masks, ref_black, compose_black, concept_bg)
        if bk:
            rec["baked"] = bk
            rec.update(causes=["baked"], codes=[TEXT_CODES["baked"]], fixable=False)
            return rec
        rec["record_only"] = "no concept glyph found (hidden state or not drawn) — not compared"
        return rec
    # 1b 후속 L 다음 — 컨셉 '획'이 둘레 바탕과 구별되지 않으면 글자가 아니라 바탕(번진 텍스처 상자와 다른 투명 틈)을 잰 것: 크기 · 위치 · 색 · 효과 전부 못 믿는다
    # [사용자 눈 R20261118_130201 파티 'Lv 100' — 컨셉 '100' 핵심 획 L* 0.5(실제 글자는 흰 빛 글자) · 대비 0.5, 렌더도 글자 맞춤이 그 측정대로 검정 · 52 로
    # 바꿔 색 차 0.37 · 높이 비 0.96 '같음' — 실제 렌더는 검정 · 약 1.5 배]
    cct = concept_contrast(masks["concept"], masks["concept_cand"], ref_black)
    if cct is not None:
        rec["concept_contrast"] = round(cct, 1)
        if cct < CONCEPT_CONTRAST_MIN:
            rec["unmeasured"] = {"concept_contrast": round(cct, 1),
                                 "note": "the concept 'glyph' matches its surroundings — the concept glyph was not found (background measured as glyph), nothing compared"}
            rec.update(causes=["unmeasured"], codes=[TEXT_CODES["unmeasured"]], fixable=False)
            return rec
    if r is None:
        causes.append("missing")
        rec["causes"] = causes
        return rec
    hr, wr = r["box"][3] / c["box"][3], r["box"][2] / c["box"][2]
    dx, dy = c["center"][0] - r["center"][0], c["center"][1] - r["center"][1]
    dens = r["density"] / max(1e-6, c["density"])
    cde = float(color.delta_e00(np.asarray(c["lab"]), np.asarray(r["lab"])))
    rec.update(h_ratio=round(hr, 3), w_ratio=round(wr, 3), center_d=[round(dx, 1), round(dy, 1)], density_ratio=round(dens, 3), color_de=round(cde, 2))
    lim = max(float(s["text_pos_px"]), float(s["text_pos_k"]) * c["box"][3])
    rec["pos_limit"] = round(lim, 1)
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    if not measure_trusted(hr, wr):
        # 획 상자 높이 · 폭이 서로 안 맞는다 = 글꼴 모양이 다르다(렌더 사선 '/' 가 숫자 아래로 길게 — 상자 높이 1.69 배, 숫자 크기는 비슷 [실측 K R20261118_000325 '2/4']).
        # 글자 맞춤과 같은 신뢰 규칙 — 크기 · 위치 · 굵기는 이 측정으로 판정하지 않고 근사(글꼴 모양)로 남긴다. 색 · 효과 유무는 그대로 본다
        # 근사가 아니라 오류 — '가장 가까운 선택'을 확인 못 했다. 획이 테두리선과 겹쳐 잘리면 이렇게 재진다(그 자체가 위치 결함)
        # [실측 K R20261118_010950 단색 '2/4' — 렌더가 패널 아래 금선과 겹쳐 폭 비 0.39 · 높이 비 0.78, '모양 근사'로 넘겨 사람 눈에만 보였다]
        causes.append("unmeasured")
        rec["unmeasured"] = {"h_ratio": round(hr, 3), "w_ratio": round(wr, 3),
                             "note": "glyph boxes disagree (clipped, merged with a line, or a different shape) — size / position / weight could not be confirmed"}
        hr_ok = False
    else:
        hr_ok = True
    if hr_ok and abs(1.0 - hr) > float(s["text_h_tol"]):
        causes.append("size")
    # 위치(E6) — 글자 모양 폭이 달라(폭 비 ÷ 높이 비가 8 % 넘게 다름 — 글꼴 결, 근사) 가운데가 어긋나면 정렬 끝(왼 · 오른쪽)이 맞는지로 본다
    # [실측 J 남은 일 R20261117_215853 파티 HUD HP 현재치 — 컨셉 숫자가 좁은 글꼴, 오른쪽 정렬, 가운데 7.5 px]
    if hr_ok and max(abs(dx), abs(dy)) > lim:
        just = w.get("justification") or "left"
        edge = None
        if abs(wr / max(1e-6, hr) - 1.0) > 0.08 and just in ("left", "right") and abs(dy) <= lim:
            cx0, rx0 = c["box"][0], r["box"][0]
            edge = (cx0 - rx0) if just == "left" else ((cx0 + c["box"][2]) - (rx0 + r["box"][2]))
            rec["edge_d"] = round(float(edge), 1)
        if edge is not None and abs(edge) <= lim:
            rec["approx"].append({"kind": "width", "w_over_h": round(wr / max(1e-6, hr), 3), "anchor": just,
                                  "note": "glyph widths differ (font shape) — the justified edge matches, the centre cannot"})
        else:
            causes.append("position")
    # 굵기(E9 · A) — 가진 굵기 중 컨셉 밀도에 가장 가까운 것을 골랐나(로그 거리). 표가 없으면 예전 허용(text_weight 배)
    table = weights or None
    cur = str(f.get("weight") or "bold")
    if declared:
        rec["declared_font"] = dict(declared)
        for k, cause in (("size", "size"), ("weight", "weight"), ("color", "color")):
            have = f.get(k) if k != "weight" else cur
            if str(have).upper() != str(declared[k]).upper() and cause not in causes:
                causes.append(cause)
        if hr_ok and abs(np.log(dens)) > 0.05:
            rec["approx"].append({"kind": "weight", "weight": cur, "density_ratio": round(dens, 3), "declared": True,
                                  "note": "the font is the one the text reference was drawn with — the rest is the measurement of small strokes"})
    elif not hr_ok:
        pass
    elif table and cur in table:
        best, after = nearest_weight(dens, cur, table)
        rec["weight_nearest"] = best
        if best != cur and abs(np.log(after)) + float(s["weight_margin"]) < abs(np.log(dens)):
            causes.append("weight")
        elif abs(np.log(dens)) > 0.05:
            rec["approx"].append({"kind": "weight", "weight": cur, "density_ratio": round(dens, 3), "available": sorted(table, key=table.get),
                                  "note": "nearest available weight — the rest is the font's own stroke"})
    elif not (1.0 / float(s["text_weight"]) <= dens <= float(s["text_weight"])):
        causes.append("weight")
    if cde > float(s["text_color_de"]) and "color" not in causes:
        causes.append("color")
    # 외곽선(E7 유무) — 획 안 어두운 픽셀 비율 / 빛(E7 유무 · 근사 세기) — 단일 측정 glow_measure(획 둘레 고리 ↔ 글자 없는 바탕)
    rbg = compose_black if render_bg is None else render_bg
    fc = _edge_fracs(masks["concept_cand"], masks["concept"], ref_black, compose_black)
    fr = _edge_fracs(masks["render_cand"], masks["render"], render, rbg)
    if fc and fr:
        rec["dark_frac"] = [round(fc[0], 3), round(fr[0], 3)]
        rec["halo_frac"] = [round(fc[1], 3), round(fr[1], 3)]
        if abs(fr[0] - fc[0]) > float(s["text_dark_frac"]):
            causes.append("outline")
    gc = glow_measure(ref_black, concept_bg, masks["concept"], float(s["glow_min"]))     # 판이 없으면 고리 밝기 바탕(예전 analyze 와 같음)
    gr = glow_measure(render, rbg, masks["render"], float(s["glow_min"]))
    if gc and gr:
        rec["glow"] = {"concept": {k: gc[k] for k in ("present", "peak", "size", "frac")}, "render": {k: gr[k] for k in ("present", "peak", "size", "frac")}}
        # 유무 차 = 둘 다 빛은 아니고 띠 밝기 차가 문턱의 절반 이상 — 문턱 하나로 가르면 7.8 ↔ 8 같은 경계에서 갈린다
        # [실측 K 기준선 R20261117_214030 '공격' — 렌더 7.8 · 컨셉 2.2, 사람 눈에 청록 빛]
        gmin = float(s["glow_min"])
        c_on, r_on = glow_on(gc, gmin), glow_on(gr, gmin)
        if c_on != r_on and abs(gr["peak"] - gc["peak"]) >= gmin / 2:
            gr_more = gr["peak"] > gc["peak"]
            fam = f.get("family")
            if not gr_more and no_sdf is not None and fam in no_sdf:
                # 컨셉은 빛나는데 이 글꼴엔 SDF(거리장) 사본이 없어 엔진이 빛을 못 그린다 — 고칠 길이 에셋뿐이라 기록만(보고)
                rec["limits"] = [{"cause": "glow", "reason": "the concept glows but this font has no distance-field (SDF) copy — "
                                                             "add fonts.roles.<role>.sdf_family to draw text glow"}]
            else:
                causes.append("glow")
                rec["glow_note"] = "the render glows but the concept does not" if gr_more else "the concept glows but the render does not"
        elif c_on and r_on:
            # 1b 후속 L-2 사람 눈 — 빛 세기(띠 밝기)도 '가장 가까운 선택'으로: 빛 색 알파를 더 낮추거나 높일 수 있는데 세기가 25 % 넘게 다르면 E9,
            # 알파가 끝(0.15 · 1.0)이라 더 못 가면 근사 [사용자 눈 R20261118_142524 '오의 불가' — 렌더 빛이 더 세고 붉음, 띠 밝기 30.7 ↔ 42.7 · 알파 0.96]
            ratio = max(gr["peak"], 1e-3) / max(gc["peak"], 1e-3)
            if abs(gr["peak"] - gc["peak"]) >= gmin / 2 and max(ratio, 1.0 / ratio) > GLOW_PEAK_TOL:
                a = glow_alpha(f)
                can = a is not None and ((ratio > 1 and a > GLOW_ALPHA_RANGE[0] + 0.01) or (ratio < 1 and a < GLOW_ALPHA_RANGE[1] - 0.01))
                if can:
                    causes.append("glow_strength")
                    rec["glow_note"] = f"glow strength {gr['peak']} vs the concept {gc['peak']} (glow colour alpha {a:.2f} can go {'down' if ratio > 1 else 'up'})"
                else:
                    rec["approx"].append({"kind": "glow_strength", "peak": [gc["peak"], gr["peak"]], "alpha": a,
                                          "note": "glow colour alpha is at its limit — the rest is the engine glow curve"})
            if abs(gc["size"] - gr["size"]) > 1:
                rec["approx"].append({"kind": "glow", "size": [gc["size"], gr["size"]], "peak": [gc["peak"], gr["peak"]],
                                      "note": "both glow — strength / falloff differs (engine glow is one material curve)"})
    # 그림자(E7 유무, 1b 후속 L-3c) — 단일 측정 shadow_measure(옮긴 획 자리 ↔ 글자 없는 바탕, 반대쪽 빼기)
    sc = shadow_measure(ref_black, concept_bg, masks["concept"])
    sr = shadow_measure(render, rbg, masks["render"])
    if sc and sr:
        rec["shadow"] = {"concept": sc, "render": sr}
        if sc["present"] != sr["present"] and abs(sc["dark"] - sr["dark"]) >= SHADOW_MIN / 2:
            causes.append("shadow")
            rec["shadow_note"] = "the concept has a drop shadow but the render does not" if sc["present"] else "the render has a drop shadow but the concept does not"
    rec["causes"] = causes
    rec["codes"] = sorted({TEXT_CODES.get(k, "E9") for k in causes})
    has_glow = bool((f.get("glow") or {}).get("size"))
    rec["fixable"] = bool(causes) and all(k in ("size", "position", "weight", "color", "outline", "shadow", "glow_strength")
                                          or (k == "glow" and (has_glow or glow_on(gc, float(s["glow_min"]))))
                                          for k in causes)   # 글자 맞춤(크기 판 — 색 · 외곽선 J-c · 빛 J · K)
    if declared and set(causes) & {"size", "weight", "color", "outline", "shadow", "glow", "glow_strength"}:
        rec["fixable"] = False                                # 글꼴 값은 참고판 배치 파일이 정한다 — 맞춤 판이 안 건드린다
    return rec


RESIDUE_SIGMAS = (2.0, 4.0, 8.0, 16.0)   # 매끈한 글자 없는 바탕 — 원천 가우스 가중 평균, 받침이 모자란 픽셀만 다음 반경(refine._smooth_fill 과 같은 생각)
RESIDUE_SUPPORT = 0.05
RESIDUE_SRC_GAP = 3                      # 바탕 원천 = 컨셉 글자 획(후보 · 핵심) · 빛 반경에서 이만큼(px) 밖


def _smooth_bg(img, src) -> tuple[np.ndarray, np.ndarray]:
    """원천(src) 픽셀의 정규화 가우스 평균 → (바탕 HxWx3, 받침 있음 HxW)."""
    import cv2
    w = np.asarray(src, np.float32)
    img = np.asarray(img, np.float32)
    out = np.zeros(img.shape, np.float32)
    done = np.zeros(w.shape, bool)
    if not w.any():
        return out, done
    for s in RESIDUE_SIGMAS:
        den = cv2.GaussianBlur(w, (0, 0), s)
        ok = (den > RESIDUE_SUPPORT) & ~done
        if ok.any():
            num = np.dstack([cv2.GaussianBlur(img[..., i] * w, (0, 0), s) for i in range(3)])
            out[ok] = num[ok] / den[ok][:, None]
            done |= ok
        if done.all():
            break
    return out, done


def _shift_min_de(a, b, box, r: int = SHIFT_TOL) -> np.ndarray:
    """ΔE00(a, b 를 ±r px 옮긴 것)의 최소 — 상자 [x0, y0, x1, y1) 안만(판이 구조선을 1 ~ 2 px 어긋나게 다시 그림)."""
    x0, y0, x1, y1 = box
    H, W = np.shape(a)[:2]
    la = color.srgb_to_lab(np.asarray(a, float)[y0:y1, x0:x1])
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys = np.clip(np.arange(y0, y1) + dy, 0, H - 1)
            xs = np.clip(np.arange(x0, x1) + dx, 0, W - 1)
            d = color.delta_e00(la, color.srgb_to_lab(np.asarray(b, float)[np.ix_(ys, xs)]))
            best = d if best is None else np.minimum(best, d)
    return np.asarray(best, np.float32)


def glyph_residue(ref_text, comp, gm: dict, texts: list[dict], notext_black=None, render=None, de_min: float = DEFAULTS["residue_de"],
                  min_px: int = DEFAULTS["residue_min_px"]) -> dict:
    """E1 획에 붙은 잔상(1b 후속 L 다음 — 외부 · 단색 입력 검증 틀).
    글자 구역 바탕 E1 은 모든 글자 획(컨셉 · 렌더 후보) + 2 px 와 컨셉 획 4 px 안 효과를 빼고 재서, 컨셉 획 자리에 텍스처가 남긴 글자 조각(메움이 획 끝을
    덜 덮음)이 렌더 글자 바로 옆에 보여도 못 봤다 [사용자 눈 R20261118_120715 단색 '2/4' — '4' 밑 잔상, 글자 구역 바탕 국소 최대 9.78 < 10]. 그 자리는
    컨셉이 글자라 '컨셉과 같나'로는 판정이 안 된다 — 글자 없는 바탕 추정과 견준다.
    자리 = 컨셉 글자 획(후보 · 핵심 + 1 px) 중 렌더 글자(모든 글자의 렌더 후보 · 렌더 핵심 + 1 px)가 안 덮은 픽셀 — 렌더가 텍스처를 그대로 보여 주는 곳.
    잔상 = 텍스처 합성과 렌더가 **둘 다** 글자 없는 바탕 두 추정 **모두**와 ΔE00 de_min 넘게 다른 픽셀: ① 컨셉 글자 바깥(모든 글자 획 · 빛 반경 + 3 px 밖)의
    가우스 가중 평균 ② 글자 없는 판 ±2 px 이동 최소(판이 지킨 구조선 · 판으로 메운 자리). 엔진 글자 차이(빛 · 그림자 · 외곽선 · 글꼴 모양)는 렌더에만 있어
    텍스처 합성이 바탕과 같다 → min 으로 빠진다(텍스처 합성 ↔ 컨셉 · 렌더 ↔ 컨셉 min 과 같은 원리). render 가 None 이면 텍스처 합성만(오프라인 replay —
    보이는지는 모름, 자리는 컨셉 획 전체).
    → {wid: {"zone_px", "px"(de_min 넘는 픽셀), "max_de", "blobs": [{box, area, mean_de, max_de}](넓이 ≥ min_px, 큰 순)}}"""
    import cv2
    H, W = np.shape(ref_text)[:2]
    if not gm:
        return {}
    concept_all = np.zeros((H, W), bool)
    render_all = np.zeros((H, W), bool)
    glowz = np.zeros((H, W), bool)
    for w in texts:
        v = gm.get(w["id"])
        if not v:
            continue
        concept_all |= v["concept_cand"] | v["concept"]
        render_all |= v["render_cand"] | _dilate(v["render"], 1)
        f = w.get("font") if isinstance(w.get("font"), dict) else {}
        gl = float((f.get("glow") or {}).get("size") or 0)
        if gl > 0:
            glowz |= _dilate(v["concept"], int(round(gl)))
    bg_s, ok_s = _smooth_bg(ref_text, ~_dilate(concept_all | glowz, RESIDUE_SRC_GAP))
    out = {}
    for w in texts:
        k = w["id"]
        v = gm.get(k)
        if not v:
            continue
        zone = _dilate(v["concept"] | v["concept_cand"], 1) & ok_s
        if render is not None:
            zone &= ~render_all
        zp = int(zone.sum())
        if not zp:
            out[k] = {"zone_px": 0, "px": 0, "max_de": 0.0, "blobs": []}
            continue
        bb = _bbox(_dilate(zone, 1))
        x0, y0, x1, y1 = bb[0], bb[1], bb[0] + bb[2], bb[1] + bb[3]
        z = zone[y0:y1, x0:x1]
        sides = [comp] + ([render] if render is not None else [])
        d = None
        for img in sides:
            de = delta_e(np.asarray(img, float)[y0:y1, x0:x1], bg_s[y0:y1, x0:x1])
            if notext_black is not None:
                de = np.minimum(de, _shift_min_de(img, notext_black, (x0, y0, x1, y1)))
            d = de if d is None else np.minimum(d, de)
        d = np.where(z, d, 0.0).astype(np.float32)
        m = d > float(de_min)
        blobs = []
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] < int(min_px):
                continue
            sel = lab == i
            blobs.append({"box": [int(st[i, 0] + x0), int(st[i, 1] + y0), int(st[i, 2]), int(st[i, 3])], "area": int(st[i, cv2.CC_STAT_AREA]),
                          "mean_de": round(float(d[sel].mean()), 1), "max_de": round(float(d[sel].max()), 1)})
        blobs.sort(key=lambda b_: -b_["area"] * b_["mean_de"])
        out[k] = {"zone_px": zp, "px": int(m.sum()), "max_de": round(float(d.max()), 1), "blobs": blobs}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 본체

def _inputs(rd: pathlib.Path, spec: dict | None = None) -> dict:
    spec = spec or json.loads((rd / "spec.json").read_text(encoding="utf-8"))
    geo = json.loads((rd / "geometry.json").read_text(encoding="utf-8"))
    canvas = [int(v) for v in (geo.get("canvas") or spec.get("canvas"))]
    boxes = geo["geometry"].get(f"{canvas[0]}x{canvas[1]}") or next(iter(geo["geometry"].values()))
    manifest = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    textures = {a["asset_id"]: backdrop._load(rd / a["file"]) for a in manifest.get("assets", []) if a.get("file") and (rd / a["file"]).is_file()}
    norm = json.loads((rd / "normalize.json").read_text(encoding="utf-8")) if (rd / "normalize.json").is_file() else {}
    bg = (norm.get("background") or {})
    return {"spec": spec, "canvas": canvas, "boxes": boxes, "textures": textures, "norm": norm, "bg": bg}


def spec_brush_keys():
    from core import spec as spec_mod
    return spec_mod.BRUSH_KEYS


def _hidden_roots(spec: dict) -> list[str]:
    index = {w["id"]: w for w in spec.get("widgets", [])}

    def hidden(w):
        return w.get("visibility") in ("collapsed", "hidden")
    out = []
    for w in spec.get("widgets", []):
        if not hidden(w):
            continue
        p, up = w.get("parent"), False
        while p and p in index:
            if hidden(index[p]):
                up = True
                break
            p = index[p].get("parent")
        if not up:
            out.append(w["id"])
    return out


GLYPH_EVIDENCE = 0.05      # 숨은 글자 위젯 상자 중 컨셉이 글자 없는 판과 크게(INK_MIN) 다른 픽셀 비율이 이 이상이면 '컨셉이 그 글자를 그렸다'


def hidden_state_split(spec: dict, boxes: list[dict], textures: dict, canvas, ref_black, render, comp_black, cov_black,
                       ref_text=None, notext_black=None) -> tuple[set[str], list[dict]]:
    """레퍼런스에 안 그려진 상태 — 시작 때 숨은 위젯(subtree)마다 그 위젯을 넣은 쪽 · 뺀 쪽 중 레퍼런스에 가까운 쪽으로 '컨셉이 그 상태를 그렸나'를 정한다
    (텍스처는 합성 ↔ 그 위젯 뺀 합성, 글자는 렌더 ↔ 글자 없는 합성 — 글자 든 컨셉 ref_text 와, 1b 후속 K-a 아트 모드면 아트엔 글자가 없다). → (안 그려진 위젯 id, 기록)."""
    W, H = int(canvas[0]), int(canvas[1])
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    geo = {b["id"]: b for b in boxes}
    not_drawn: set[str] = set()
    states = []
    de_comp_all = None
    ref_text = ref_black if ref_text is None else ref_text
    de_ren_all = delta_e(render, ref_text)
    for hid in _hidden_roots(spec):
        sub = _subtree(spec, hid)
        tex_ids = [i for i in sub if widgets[i].get("type") not in backdrop.TEXT_TYPES and geo.get(i, {}).get("visible", True) and geo.get(i)]
        txt_ids = [i for i in sub if widgets[i].get("type") in backdrop.TEXT_TYPES and geo.get(i, {}).get("visible", True) and geo.get(i)]
        z_tex = np.zeros((H, W), bool)
        for i in tex_ids:
            g = geo[i]
            if g["w"] > 0 and g["h"] > 0:
                z_tex |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD)
        z_txt = np.zeros((H, W), bool)
        for i in txt_ids:
            g = geo[i]
            z_txt |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD)
        if not (z_tex.any() or z_txt.any()):
            continue
        wo, _, _ = backdrop.compose(_without(spec, sub), boxes, textures, canvas, (0, 0, 0))
        if de_comp_all is None:
            de_comp_all = delta_e(comp_black, ref_black)
        d_with = d_wo = 0.0
        n = 0
        if z_tex.any():
            m = z_tex & (cov_black > 0.02)
            if m.any():
                d_with += float(de_comp_all[m].sum())
                d_wo += float(delta_e(wo[m], ref_black[m]).sum())
                n += int(m.sum())
        if z_txt.any():
            d_with += float(de_ren_all[z_txt].sum())
            d_wo += float(delta_e(comp_black[z_txt], ref_text[z_txt]).sum())
            n += int(z_txt.sum())
        shown = n > 0 and d_with < d_wo
        extra = {}
        if notext_black is not None and txt_ids and not z_tex.any():
            # 글자만 있는 숨은 위젯 — 컨셉의 그 상자에 글자 획(글자 없는 판과 다른 픽셀)이 있나로 정한다. 렌더 글자가 아직 효과(빛 · 외곽선)를 못 맞췄으면 '넣은 쪽 ↔
            # 뺀 쪽' 차가 거의 같아(16.15 ↔ 16.03) 안 그린 것으로 보고 글자 맞춤에서도 빠졌다 [실측 K R20261118_010321 단색 '오의 불가']
            dtx = maxabs(ref_text, notext_black) > INK_MIN
            frac = float(dtx[z_txt].mean()) if z_txt.any() else 0.0
            shown = frac >= GLYPH_EVIDENCE
            extra = {"glyph_frac": round(frac, 3), "decided_by": "glyph evidence in the concept (text-free concept difference)"}
        states.append({"widget": hid, "subtree": sorted(sub), "drawn_in_concept": bool(shown),
                       "de_with": round(d_with / max(1, n), 2), "de_without": round(d_wo / max(1, n), 2), **extra})
        if not shown:
            not_drawn |= sub
    return not_drawn, states


def run_text_masks(run_dir, spec: dict, render_path=None) -> dict | None:
    """1b 후속 J-c — 글자 맞춤(stages/style.text_fit)이 진단과 같은 획(핵심 획 · 빛 제외)으로 재도록, run 폴더의 렌더(마지막 통과) · 텍스처 ·
    레퍼런스에서 글자 위젯마다 {"concept", "render", …} 마스크. ⓐ ⓑ 가 아니거나 재료가 없으면 None(예전 밝기 측정)."""
    rd = pathlib.Path(run_dir)
    try:
        inp = _inputs(rd, spec)
    except (OSError, ValueError, KeyError, StopIteration):
        return None
    spec, canvas, boxes, textures, bgrec = inp["spec"], inp["canvas"], inp["boxes"], inp["textures"], inp["bg"]
    W, H = canvas
    rp = pathlib.Path(render_path) if render_path else rd / "render.png"
    if bgrec.get("kind") not in ("transparent", "flat") or not (rd / "reference_alpha.png").is_file() or not rp.is_file():
        return None
    render = _load_rgb(rp)
    if render.shape[:2] != (H, W):
        return None
    ref_black = _load_rgb(rd / "reference_color.png") * _load_l(rd / "reference_alpha.png")[..., None]
    nt = bgrec.get("notext") or {}
    notext_black = None
    if nt.get("used") and (rd / str(nt.get("color"))).is_file() and (rd / str(nt.get("alpha"))).is_file():
        notext_black = _notext_cleared(rd, nt, spec)
    comp_black, cov_black, _ = backdrop.compose(spec, boxes, textures, canvas, (0, 0, 0))
    not_drawn, _ = hidden_state_split(spec, boxes, textures, canvas, ref_black, render, comp_black, cov_black, notext_black=notext_black)
    comp_state = backdrop.compose(_without(spec, not_drawn), boxes, textures, canvas, (0, 0, 0))[0] if not_drawn else comp_black
    geo = {b["id"]: b for b in boxes}
    texts = [w for w in spec.get("widgets", []) if w.get("type") in backdrop.TEXT_TYPES and w["id"] not in not_drawn
             and geo.get(w["id"], {}).get("visible", True) and geo.get(w["id"])]
    skip = notext_unused(rd)
    gm = text_glyph_masks(ref_black, render, comp_state, texts, geo, notext_black, render_bg=comp_black, notext_skip=skip, color_gate=art_mode(bgrec))
    for k, v in gm.items():                  # 외곽선 · 빛 맞춤(style._fit_outline · _fit_glow)이 진단과 같은 바탕으로 재게
        v["concept_bg"], v["render_bg"] = comp_state, comp_black
        v["concept_glow_bg"] = notext_black if notext_black is not None and k not in skip else None
        # 1b 후속 L 다음 — 글자 맞춤도 진단과 같은 측정 실패 안전망(컨셉 대비 < CONCEPT_CONTRAST_MIN 이면 그 글자 안 건드림)
        v["concept_contrast"] = concept_contrast(v["concept"], v["concept_cand"], ref_black) if v.get("concept_cand") is not None else None
    return gm


def _state_render(render_state, overrides: dict, name: str, shape):
    """1b 후속 L 다음 — verify render_state(overrides, name) 로 다른 상태 엔진 렌더(출력 폴더 = 이름마다 — 같은 폴더면 OUTPUT_DIR_NOT_EMPTY) → HxWx3 또는 None."""
    p = render_state(overrides, name)
    img = _load_rgb(p) if p else None
    return img if img is not None and img.shape[:2] == tuple(shape) else None


def diagnose(run_dir, out_dir=None, cfg: dict | None = None, spec: dict | None = None, pictures: bool = True, render_state=None) -> dict:
    """run 폴더(spec · geometry · manifest · render.png · reference*) → 진단 기록(defects · summary · badness …) + 그림(out_dir).
    render_state(overrides) → PNG 경로: 숨은 위젯을 컨셉 상태로 켜고 끈 엔진 렌더(verify — 사람 눈 그림 compare.png 가운데 · E8). 없으면 base.
    비교할 수 없으면 {"skipped": 이유}."""
    import cv2
    rd = pathlib.Path(run_dir)
    s = settings(cfg)
    if not (rd / "reference.png").is_file():
        return {"skipped": "no reference (hand spec) — nothing to compare"}
    if not (rd / "render.png").is_file() or not (rd / "geometry.json").is_file():
        return {"skipped": "no render (verify did not render)"}
    inp = _inputs(rd, spec)
    spec, canvas, boxes, textures, bgrec = inp["spec"], inp["canvas"], inp["boxes"], inp["textures"], inp["bg"]
    W, H = canvas
    render = _load_rgb(rd / "render.png")
    if render.shape[:2] != (H, W):
        return {"skipped": f"render {list(render.shape[:2][::-1])} is not the canvas {canvas} — cannot compare"}
    kind = bgrec.get("kind")
    if kind in ("transparent", "flat") and (rd / "reference_color.png").is_file() and (rd / "reference_alpha.png").is_file():
        rc, ra = _load_rgb(rd / "reference_color.png"), _load_l(rd / "reference_alpha.png")
        truth = "concept_alpha" if kind == "transparent" else "unmix_estimate"
    else:
        return {"skipped": f"background {kind} — the concept has no alpha (scene composite), the render cannot be compared pixel by pixel"}
    ref_text = rc * ra[..., None]            # 글자 든 컨셉 — 글자 획 · 글자 스타일 비교(사양을 잰 그림)
    rc0, ra0 = rc, ra                        # 상태 검사 S1 (라) '컨셉 그대로' — 글자 든 컨셉(아트 모드 바꿈 전)
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    geo = {b["id"]: b for b in boxes}
    art = bgrec.get("art") or {}
    if art_mode(bgrec) and (rd / str(art.get("color"))).is_file() and (rd / str(art.get("alpha"))).is_file():
        # 1b 후속 K-a → L-2 — 원본 생성 아트(글자 없이 그린 그림이 사람이 승인한 정답): 아트의 정답 = 그 아트(전 화면 — 글자 구역 포함). 아트가 비운 게이지 막대 ·
        # 런타임 그림 자리만 컨셉(글자 참고판)으로. 글자 든 컨셉이 정답인 run(L-1)은 이 분기를 타지 않는다 — 늘 컨셉과 비교
        ac, aa = _load_rgb(rd / art["color"]), _load_l(rd / art["alpha"])
        if not residue_free(art):
            ac, aa, _ = clear_text_residue(ac, aa, rc, ra, _refine_spec(rd, spec))     # refine 아트와 같게(투명 위 글자 잔상 지움 — refine 때 글자 상자)
        keep = np.zeros((H, W), bool)
        for w in spec.get("widgets", []):
            bb = w.get("bbox_intent")
            if bb and w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image":
                keep |= _box_mask((H, W), bb, 2)
            elif bb and w.get("type") == "ProgressBar" and art_element_free(bgrec):
                # (L-2 원본 아트는 채움까지 그린 그림이라 막대도 아트가 정답 — 이 분기는 K 의 요소 없는 판만)
                # 채워진 구간만(아트는 채움을 비웠다) — 막대 끝 장식 · 빈 트랙은 아트 그대로 [실측 K R20261117_233356 — 막대 상자 전체를 컨셉으로 두자 오른쪽 끝 캡 이중 E4]
                st_ = w.get("style") or {}
                pct = st_.get("percent")
                x_, y_, bw_, bh_ = (float(v) for v in bb)
                if isinstance(pct, (int, float)) and st_.get("bar_fill_type", "left_to_right") in ("left_to_right", "right_to_left"):
                    fw_ = bw_ * max(0.0, min(1.0, float(pct)))
                    x_ = x_ if st_.get("bar_fill_type", "left_to_right") == "left_to_right" else x_ + bw_ - fw_
                    bw_ = fw_
                if bw_ > 0:
                    part = _box_mask((H, W), [x_, y_, bw_, bh_], 1)
                    # 채움이 컨셉 모양(concept_fill)이면 그 트랙 안쪽만 — 막대 끝 장식(프레임)은 아트 몫 [실측 K R20261118_005625 단색 — 왼쪽 끝 장식 2 ~ 3 px 어긋남 E1 16]
                    hole = _fill_track(rd, spec, w, (H, W))
                    keep |= (part & hole) if hole is not None else part
        rc, ra = np.where(keep[..., None], rc, ac), np.where(keep, ra, aa)
        truth = "text_free_art"
    ref_black = rc * ra[..., None]
    gray = np.asarray(backdrop.GRAY, float)
    ref_gray = rc * ra[..., None] + gray[None, None] * (1 - ra[..., None])
    nt = bgrec.get("notext") or {}
    notext_black = None
    if nt.get("used") and (rd / str(nt.get("color"))).is_file() and (rd / str(nt.get("alpha"))).is_file():
        notext_black = _notext_cleared(rd, nt, spec)
    rec: dict = {"truth": truth, "settings": s, "canvas": canvas}
    if art_mode(bgrec) and (bgrec.get("text_ref") or {}).get("used"):
        rec["truth_text"] = "text_reference_glyphs"     # L-2 — 글자 비교 · compare.png 왼쪽 = 원본 아트 + 참고판 글자 획(normalize 가 합친 reference)
    elif art_mode(bgrec):
        rec["truth_text"] = "spec_only"                 # L-2 참고판 없음 — 컨셉 글자 획이 없어 글자는 기록만(record_only)

    # 레퍼런스에 안 그려진 상태 — 시작 때 숨은 위젯(subtree) 중 컨셉이 그 상태를 그리지 않은 것은 빼고 비교(그 자리 = 그 위젯을 뺀 합성)
    comp_black, cov_black, _ = backdrop.compose(spec, boxes, textures, canvas, (0, 0, 0))
    not_drawn, states = hidden_state_split(spec, boxes, textures, canvas, ref_black, render, comp_black, cov_black, ref_text=ref_text, notext_black=notext_black)
    rec["hidden_states"] = states
    # E8 안전망 — '컨셉이 안 그림'으로 판정한 숨은 글자인데 컨셉의 그 상자에 글자 획(글자 없는 판과 다른 픽셀)이 뚜렷하면 판정이 틀린 것(그 자리는 비교에서
    # 빠지므로 다른 검사로는 안 보인다) [실측 K R20261117_235644 — 판 잔상 탓에 '오의 불가' 를 안 그린 것으로 봐 렌더에서 빠짐, 사람 눈에만 보임]
    state_suspects = []
    if notext_black is not None:
        dtx = None
        for h in states:
            if h["drawn_in_concept"]:
                continue
            for i in h["subtree"]:
                g = geo.get(i)
                if widgets[i].get("type") not in backdrop.TEXT_TYPES or not g or g.get("w", 0) <= 0:
                    continue
                if dtx is None:
                    dtx = maxabs(ref_text, notext_black) > INK_MIN
                m = _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]])
                frac = float(dtx[m].mean()) if m.any() else 0.0
                if frac >= 0.05:
                    state_suspects.append({"stage": "state", "code": "E8", "box": [int(g["x"]), int(g["y"]), int(g["w"]), int(g["h"])], "area": int(m.sum()),
                                           "widgets": [i], "fixable": False, "max_de": None, "mean_de": None,
                                           "cause": f"state — judged hidden in the concept, but {frac:.0%} of its box differs from the text-free concept (glyphs?)"})
    spec_state = _without(spec, not_drawn) if not_drawn else spec
    if not_drawn:
        comp_state, cov_state, cinfo = backdrop.compose(spec_state, boxes, textures, canvas, (0, 0, 0), owners=True)
    else:
        comp_state, cov_state, cinfo = backdrop.compose(spec, boxes, textures, canvas, (0, 0, 0), owners=True)
    gray_state, _, _ = backdrop.compose(spec_state, boxes, textures, canvas, gray)
    base = render.copy()
    nd_zone = np.zeros((H, W), bool)
    for i in not_drawn:
        g = geo.get(i)
        if g and g.get("visible", True) and g["w"] > 0 and g["h"] > 0:
            nd_zone |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD)
            gl = float(((widgets[i].get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(widgets[i].get("font"), dict) else 0.0
            if gl:
                nd_zone |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD + gl)
    # 그 자리의 다른(그려진) 글자 픽셀은 렌더 그대로 — [실측 J-b 094643] 숨은 '가득 빛' 자리를 통째로 바꾸자 그 위 '오의 불가' 아래 반이 지워졌다
    txt_px = maxabs(render, comp_black) > INK_FLOOR
    nd_text = np.zeros((H, W), bool)
    for i in not_drawn:
        if widgets[i].get("type") in backdrop.TEXT_TYPES and geo.get(i):
            g = geo[i]
            nd_text |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD)
    swap = nd_zone & (~txt_px | nd_text)
    base[swap] = comp_state[swap]

    # 글자 — 보이는(컨셉에 그려진) TextBlock 마다 그림끼리
    texts = [w for w in spec.get("widgets", []) if w.get("type") in backdrop.TEXT_TYPES and w["id"] not in not_drawn
             and geo.get(w["id"], {}).get("visible", True) and geo.get(w["id"])]
    text_zone = np.zeros((H, W), bool)
    skip_nt = notext_unused(rd)
    gm = text_glyph_masks(ref_text, render, comp_state, texts, geo, notext_black, render_bg=comp_black, notext_skip=skip_nt, color_gate=(truth == "text_free_art"))
    no_sdf = fonts_without_sdf(cfg)
    declared = _declared_fonts(rd)
    own_boxes = {k: v["own"] for k, v in gm.items()}
    trecs = []
    for w in texts:
        f = w.get("font") if isinstance(w.get("font"), dict) else {}
        glow = float((f.get("glow") or {}).get("size") or 0)
        masks = gm[w["id"]]
        cbg = notext_black if notext_black is not None and w["id"] not in skip_nt else None
        tr = compare_text(w, masks, ref_text, render, comp_state, s, render_bg=comp_black, no_sdf=no_sdf, concept_bg=cbg,
                          weights=weight_table(cfg, f.get("family")), declared=declared.get(w["id"]))
        trecs.append(tr)
        tz = masks["own"] | masks["concept_cand"] | masks["render_cand"]
        text_zone |= _dilate(tz, int(round(TEXT_ZONE_PAD + glow + max(0.0, float((f.get("outline") or {}).get("size") or 0)))))
    # 텍스처의 글자 구멍 메움 자리는 refine 때 글자 상자(specs/000.json)에 고정 — 글자 맞춤이 글자를 옮겨도 그 자리는 같은 기준으로 뺀다
    # [실측 J R20261117_190852 — '4.2' 를 5 px 올리자 그 아래 메움 자리가 드러나 위치 판이 버려졌다]
    s0 = rd / "specs" / "000.json"
    if s0.is_file():
        try:
            for w0 in json.loads(s0.read_text(encoding="utf-8")).get("widgets", []):
                if w0.get("type") in backdrop.TEXT_TYPES and w0.get("bbox_intent") and w0["id"] not in not_drawn:
                    g0 = float(((w0.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(w0.get("font"), dict) else 0.0
                    text_zone |= _box_mask((H, W), w0["bbox_intent"], TEXT_ZONE_PAD + g0)
        except (OSError, ValueError):
            pass
    rec["texts"] = trecs
    # 런타임 이미지(binding image — 초상화 등) 자리는 게임이 넣는 그림이라 비교 정답이 없다 — 빼고 기록
    # [실측 J R20261117_191858 파티 HUD — 컨셉 캐릭터 그림 ↔ 둥근 상자 자리표시]
    runtime_zone = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        g = geo.get(w["id"])
        if w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image" and g and g.get("visible", True):
            runtime_zone |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], 2)
    text_zone |= runtime_zone

    # 국소 지도 — ① 검정 위 렌더(상태 맞춤) ↔ 레퍼런스 ② 회색 위 텍스처 합성 ↔ 레퍼런스
    de_b = delta_e(base, ref_black)
    de_g = delta_e(gray_state, ref_gray)
    loc_b, loc_g = local_mean(de_b), local_mean(de_g)
    de_c = delta_e(comp_state, ref_black)
    loc_c = local_mean(de_c)
    T = float(s["local_de"])
    defect = ((loc_b > T) | (loc_g > T)) & ~text_zone
    rec["maps"] = {"black_mean": round(float(de_b[~text_zone].mean()), 3), "gray_mean": round(float(de_g[~text_zone].mean()), 3),
                   "black_local_max": round(float(loc_b[~text_zone].max()), 2), "gray_local_max": round(float(loc_g[~text_zone].max()), 2),
                   "text_zone_px": int(text_zone.sum()), "not_drawn_px": int(nd_zone.sum()), "runtime_image_px": int(runtime_zone.sum())}
    owner, owner_ids = cinfo.get("owner"), cinfo.get("owner_ids", [])
    defects = []
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(defect.astype(np.uint8), np.ones((3, 3), np.uint8)), connectivity=8)
    for i in range(1, n):
        blob = (lab == i) & defect
        area = int(blob.sum())
        if area < int(s["min_area"]):
            continue
        bb = _bbox(blob)
        from_gray = bool((loc_g[blob] > T).mean() >= 0.5) and not bool((loc_b[blob] > T).mean() >= 0.5)
        tex = bool((loc_c[blob] > 0.7 * T).mean() >= 0.5) or from_gray
        d = (cov_state - ra)[blob]
        own = owner[blob] if owner is not None else np.array([-1])
        ids, cnt = np.unique(own[own >= 0], return_counts=True)
        top = [owner_ids[k] for k in ids[np.argsort(-cnt)][:3]] if len(ids) else []
        item = {"box": bb, "area": area, "max_de": round(float(max(loc_b[blob].max(), loc_g[blob].max())), 1),
                "mean_de": round(float(np.maximum(loc_b, loc_g)[blob].mean()), 1), "widgets": top, "alpha_d": round(float(d.mean()), 3)}
        if tex:
            item["stage"] = "texture"
            if not top and float(ra[blob].mean()) > 0.1:
                item["cause"] = "missing — no texture draws these concept pixels"
            elif d.mean() > 0.15:
                item["cause"] = "double — the textures are more opaque than the concept here"
            elif d.mean() < -0.15:
                item["cause"] = "hole — the textures cover less than the concept here"
            else:
                near_text = any(_dilate(m, int(round(max(4.0, 0.5 * float((widgets[k].get("bbox_intent") or [0, 0, 0, 20])[3]))))) [blob].any()
                                for k, m in own_boxes.items())
                item["cause"] = "colour — near a text hole fill (text-free concept / interpolation)" if near_text else "colour — texture pixels differ"
        else:
            x, y, bw, bh = bb
            p = 24
            X0, Y0, X1, Y1 = max(0, x - p), max(0, y - p), min(W, x + bw + p), min(H, y + bh + p)
            a = cv2.cvtColor(np.clip(base[Y0:Y1, X0:X1], 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
            b = cv2.cvtColor(np.clip(ref_black[Y0:Y1, X0:X1], 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
            (sx, sy), resp = cv2.phaseCorrelate(b, a)
            if max(abs(sx), abs(sy)) >= 1.0 and resp > 0.1:
                item["stage"] = "placement"
                item["cause"] = f"shifted by ({round(float(sx), 1)}, {round(float(sy), 1)}) px against the concept"
            else:
                item["stage"] = "engine"
                item["cause"] = "the engine draws differently from the 1:1 texture composite (draw mode · scale · compression)"
        item["fixable"] = False
        defects.append(item)
    defects.sort(key=lambda r: -r["area"] * r["mean_de"])
    # F2(1b 후속 L 다음) — 번짐을 뺀 concept_fill 채움(spill 0 · spill_measured > 0)의 컨셉 상태 진행 끝 빛 자리는 근사: 한 brush(scale + box 여백 고정)로는
    # 컨셉 진행률의 끝 빛과 100 % 의 트랙 끝 맞춤을 같이 못 한다(번짐을 남기면 100 % 에서 트랙 밖 끝 장식을 덮음 — 상태 검사 S2 가 지킨다).
    # 그 자리 안이 상자 넓이 END_GLOW_FRAC 이상인 국소 결함은 오류에서 빼 근사 gauge_end_glow 로 [실측 R20261119_091634 — 100 % 끝 어두운 사각형]
    gauge_approx = []
    from gen import state_check
    # G3(1b 후속 L 다음) — 끝 모양(end_shape) 채움의 컨셉 상태 진행 끝 자리도 근사 gauge_end_shape(중간 진행률의 끝이 호 모양 — 100 % 는 S2 보강이 지킨다)
    glow_zones = state_check.end_glow_zones(spec, (H, W)) + state_check.end_shape_zones(spec, (H, W))
    if glow_zones:
        kept = []
        for d in defects:
            x, y, bw, bh = d["box"]
            # 같은 채움의 끝 빛 · 끝 모양 자리는 이어져 있다 — 그 합에서 넓이 비를 보고 더 많이 겹친 쪽 종류로
            z = None
            for asset in {z_["asset"] for z_ in glow_zones}:
                zs = [z_ for z_ in glow_zones if z_["asset"] == asset]
                um = np.zeros_like(zs[0]["mask"])
                for z_ in zs:
                    um |= z_["mask"]
                if float(um[y:y + bh, x:x + bw].mean()) >= END_GLOW_FRAC:
                    z = max(zs, key=lambda z_: float(z_["mask"][y:y + bh, x:x + bw].mean()))
                    break
            if z is None:
                kept.append(d)
                continue
            if z.get("kind") == "gauge_end_shape":
                gauge_approx.append({"widget": (z["widgets"] or [z["asset"]])[0], "kind": "gauge_end_shape", "box": d["box"], "area": d["area"],
                                     "max_de": d.get("max_de"), "note": f"concept-state progress end follows the empty-track end arc ({z['depth']} px deep) "
                                                                        "so 100% fits the end cap — the concept draws a straight end here"})
                continue
            gauge_approx.append({"widget": (z["widgets"] or [z["asset"]])[0], "kind": "gauge_end_glow", "box": d["box"], "area": d["area"], "max_de": d.get("max_de"),
                                 "note": f"concept-state end glow left out — the fill has no spill ({z['spill_measured']} px measured) so 100% stays inside the track"})
        defects = kept

    # E1 글자 구역 바탕(1b 후속 K) — 국소 지도가 빼던 글자 구역도, 모든 글자 획(컨셉 · 렌더 후보 + 2 px)을 뺀 바탕 픽셀에서 잰다.
    # 차 = min(렌더 ↔ 컨셉, 텍스처 합성 ↔ 컨셉): 텍스처 메움의 색조 · 모양 차(얼룩 · 잔상)는 둘 다 다르고, 엔진 글자 효과(빛)만 다르면 렌더만 다르다(E7 몫),
    # 컨셉에 있던 빛을 텍스처가 지우고 엔진이 다시 그리면 합성만 다르다(정상). [실측 J 남은 일 사람 눈 — '공격' 둘레 얼룩, 국소 ΔE00 13 ~ 22]
    strokes = np.zeros((H, W), bool)
    near_glyph = np.zeros((H, W), bool)
    glow_of = {t["widget"]: ((t.get("glow") or {}).get("concept") or {}) for t in trecs}
    brighter = None
    # 획에 붙은 글자 효과(그림자 · 외곽선 · 획 끝 결 — 핵심 획 4 px 안에서 컨셉이 글자 없는 바탕과 뚜렷이 다른 픽셀)는 효과(E7) · 근사 몫 — 바탕 얼룩으로 세지 않는다
    # [실측 K R20261118_003123 '체인' — 컨셉 그림자 · ㄴ 끝이 아트 모드 글자색 거르기에서 획 밖으로 빠져 E1 25.7]
    eff_bg = notext_black if notext_black is not None else comp_state
    attached = maxabs(ref_text, eff_bg) > INK_FLOOR
    for k, v in gm.items():
        strokes |= v["concept_cand"] | v["render_cand"] | v["concept"] | v["render"]
        strokes |= _dilate(v["concept"], 4) & attached
        gc_ = glow_of.get(k) or {}
        if gc_.get("present") or float(gc_.get("peak") or 0) >= DEFAULTS["glow_min"] / 2:
            # 컨셉 빛 번짐 자리는 글자 효과(E7 유무 · 근사 세기) 몫 — 바탕 얼룩으로 두 번 세지 않는다. 자리 = 획 16 px 안에서 컨셉이 글자 없는 판보다 실제로
            # 밝은 픽셀(측정 크기만 빼면 넓게 번진 빛 끝이 얼룩으로 남았다 [실측 K R20261117_234013 '오의 불가' — 빛 없는 렌더, E1 max 34])
            if brighter is None:
                bgl = notext_black if notext_black is not None else comp_state
                brighter = (color.srgb_to_lab(ref_text)[..., 0] - color.srgb_to_lab(bgl)[..., 0]) > 4.0
            strokes |= _dilate(v["concept"], int(gc_.get("size") or 0)) | (_dilate(v["concept"], GLOW_MAXD) & brighter)
        f_ = (widgets.get(k) or {}).get("font") or {}
        # 핵심 획(글자색)만 — 후보에는 아트가 다시 그린 장식(패널 모서리)이 '컨셉과 다른 픽셀'로 끼었다 [실측 K R20261117_234013 '2/4' 상자 안 모서리 ΔE 40]
        near_glyph |= _dilate(v["concept"], 6 + int(float((f_.get("glow") or {}).get("size") or 0)))
    strokes = _dilate(strokes, 2)
    bgz = text_zone & ~runtime_zone & ~strokes & ~nd_zone
    rec["text_background"] = {"zone_px": int(bgz.sum())}
    loc_t = np.zeros((H, W), np.float32)
    if bgz.any():
        import cv2 as _cv
        if truth == "text_free_art":
            # 아트 모드 — 글자 획 둘레(지운 글자 자리)는 글자 든 컨셉과(아트가 잔상을 남기면 아트 비교로는 안 보인다 [실측 K R20261117_233356 — 투명 위
            # '오의 불가' 자리 붉은 얼룩]), 획에서 먼 글자 상자 안(패널 테두리선 등)은 아트와(아트가 정답 — 다시 그린 선 위치는 아트 몫)
            d_txt = np.minimum(delta_e(base, ref_text), delta_e(comp_state, ref_text))
            dmin = np.where(near_glyph, d_txt, np.minimum(de_b, de_c)) * bgz
        else:
            dmin = np.minimum(de_b, de_c) * bgz
        cover = _cv.blur(bgz.astype(np.float32), (WIN, WIN))
        loc_t = np.where(cover >= float(s["bg_cover"]), _cv.blur(dmin.astype(np.float32), (WIN, WIN)) / np.maximum(cover, 1e-6), 0.0)
        e1 = (loc_t > T) & bgz
        rec["text_background"].update(local_max=round(float(loc_t[bgz].max()), 2), mean=round(float(dmin[bgz].sum() / max(1, bgz.sum())), 2))
        k1, lab1, _, _ = cv2.connectedComponentsWithStats(cv2.dilate(e1.astype(np.uint8), np.ones((3, 3), np.uint8)), connectivity=8)
        for i in range(1, k1):
            blob = (lab1 == i) & e1
            area = int(blob.sum())
            if area < int(s["min_area"]):
                continue
            near = [k for k, v in gm.items() if _dilate(v["own"], 8)[blob].any()]
            defects.append({"stage": "texture", "code": "E1", "box": _bbox(blob), "area": area, "max_de": round(float(loc_t[blob].max()), 1),
                            "mean_de": round(float(loc_t[blob].mean()), 1), "widgets": near[:3], "fixable": False,
                            "cause": "smear — the background around the text differs from the concept (text fill tone / shape)"})
    # E1 획에 붙은 잔상(1b 후속 L 다음) — 위 바탕 검사가 빼는 컨셉 획 자리 중 렌더 글자가 안 덮은 곳에서 텍스처 · 렌더가 글자 없는 바탕과 다름
    residue = glyph_residue(ref_text, comp_state, gm, texts, notext_black, render=base, de_min=float(s["residue_de"]), min_px=int(s["residue_min_px"]))
    rec["text_residue"] = {k: {"zone_px": v["zone_px"], "px": v["px"], "max_de": v["max_de"], "blobs": v["blobs"][:3]} for k, v in residue.items()}
    for k, v in residue.items():
        for b in v["blobs"]:
            defects.append({"stage": "texture", "code": "E1", "box": b["box"], "area": b["area"], "max_de": b["max_de"], "mean_de": b["mean_de"],
                            "widgets": [k], "fixable": False,
                            "cause": "residue — the texture keeps part of the concept glyph where the render glyph does not cover it (text fill missed the stroke)"})

    # E2 뭉개짐(1b 후속 K) — 텍스처가 그리는 자리마다 선명도(밝기 기울기 에너지) 렌더 ÷ 컨셉 · 텍셀 밀도(텍스처 px ÷ 화면 px — < 1 은 늘려 그림)
    blur_rows = []
    if owner is not None:
        gray_r = cv2.cvtColor(np.clip(base, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray_c = cv2.cvtColor(np.clip(ref_black, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)

        def energy(g):
            return np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
        er, ec = energy(gray_r), energy(gray_c)
        free = (ra > 0.05) & ~text_zone & ~nd_zone & ~_dilate(runtime_zone, 2)
        for j, wid in enumerate(owner_ids):
            region = (owner == j) & free
            n_px = int(region.sum())
            if n_px < 400:
                continue
            w = widgets.get(wid) or {}
            stl = w.get("style") or {}
            br = next((b for k_, b in stl.items() if k_ in ("brush", "normal", "fill") and isinstance(b, dict) and b.get("asset") in textures), None)
            g = geo.get(wid) or {}
            dens = round(textures[br["asset"]].shape[1] / max(1.0, float(g.get("w") or 1)), 3) if br and g.get("w") else None
            ce = float(ec[region].mean())
            if ce < 2.0:                    # 평평한 자리(기울기 없음) — 비교 뜻 없음
                continue
            ratio = float(er[region].mean()) / ce
            blur_rows.append({"widget": wid, "ratio": round(ratio, 3), "texel_density": dens, "px": n_px})
            if ratio < float(s["blur_ratio"]):
                defects.append({"stage": "texture", "code": "E2", "box": _bbox(region), "area": n_px, "widgets": [wid], "fixable": False,
                                "max_de": None, "mean_de": None, "cause": f"blurred — the render is {ratio:.2f} as sharp as the concept here (texel density {dens})"})
    rec["sharpness"] = blur_rows

    # ③ 3 배 절취선
    tmask = backdrop.text_mask(spec_state, boxes, canvas)
    vis = cov_state > 0.02
    seams = None
    if vis.any():
        bbv = _bbox(vis)
        seams = zoom_seams(spec_state, boxes, textures, rc, ra, [max(0, bbv[0] - 8), max(0, bbv[1] - 8), min(W, bbv[0] + bbv[2] + 8), min(H, bbv[1] + bbv[3] + 8)],
                           tmask)
        for sp in seams.get("spots", []):
            if sp["dark_px"] >= int(s["seam_dark_px"]):
                x, y, bw, bh = sp["box"]
                own = owner[y:y + bh, x:x + bw] if owner is not None else np.array([-1])
                ids = np.unique(own[own >= 0])
                defects.append({"stage": "seam", "box": sp["box"], "area": sp["dark_px"], "cause": "texture boundary darkens when the engine magnifies the split textures",
                                "widgets": [owner_ids[k] for k in ids][:4], "fixable": False})
    rec["seams"] = seams

    for t in trecs:
        if t.get("causes"):
            bx = (t.get("render") or t.get("concept") or t.get("baked") or {}).get("box") or (widgets[t["widget"]].get("bbox_intent") or [0, 0, 0, 0])
            defects.append({"stage": "text", "box": [int(v) for v in bx], "widgets": [t["widget"]], "causes": t["causes"], "fixable": bool(t.get("fixable")),
                            "cause": ", ".join(t["causes"]) + (f" ({t['glow_note']})" if t.get("glow_note") else ""), "code": (t.get("codes") or ["E9"])[0],
                            "codes": t.get("codes"),
                            "measured": {k: t.get(k) for k in ("h_ratio", "center_d", "density_ratio", "color_de", "dark_frac", "halo_frac", "weight_nearest", "glow")}})
    defects.extend(state_suspects)
    for d in defects:
        if "code" not in d:
            cz = str(d.get("cause") or "")
            d["code"] = {"placement": "E6", "seam": "E5", "engine": "E1"}.get(d["stage"]) or (
                "E3" if cz.startswith("missing") else "E4" if cz.startswith(("double", "hole")) else "E1")
    for k, d in enumerate(defects, 1):
        d["n"] = k
    rec["defects"] = defects
    by_stage: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for d in defects:
        by_stage[d["stage"]] = by_stage.get(d["stage"], 0) + 1
        by_code[d["code"]] = by_code.get(d["code"], 0) + 1
    # 상태(E8 기록) — 기계용 render.png(force_visible)는 컨셉이 안 그린 숨은 위젯까지 켠다(사람 눈에 보이면 안 되는 상태) · 시작 때 숨었는데
    # 컨셉이 그린 위젯(미리보기 · 샘플과 다른 상태). 사람 눈 그림 compare.png 는 컨셉 상태로 그린다(verify 가 그 상태로 렌더 — 못 맞추면 E8 오류)
    rec["state"] = {"force_visible_extra": sorted(h["widget"] for h in states if not h["drawn_in_concept"]),
                    "drawn_hidden_at_start": sorted(h["widget"] for h in states if h["drawn_in_concept"])}
    approx = [{"widget": t["widget"], **a} for t in trecs for a in t.get("approx") or []] + gauge_approx
    rec["approx"] = approx
    badness = 0.0
    for d in defects:
        if d.get("code") == "E2":
            badness += d["area"] / 100.0
        elif d["stage"] in ("texture", "placement", "engine"):
            badness += d["area"] * max(0.0, d["mean_de"] - T) / 100.0
        elif d["stage"] == "seam":
            badness += d["area"] / 100.0
        else:
            m = d.get("measured") or {}
            gl_ = m.get("glow") or {}
            gpk = [float((gl_.get(k) or {}).get("peak") or 0) for k in ("concept", "render")]
            badness += abs(1 - float(m.get("h_ratio") or 1)) * 50 + max(abs(v) for v in (m.get("center_d") or [0, 0])) \
                + abs(np.log(max(1e-3, float(m.get("density_ratio") or 1)))) * 20 + 10 * ("missing" in d.get("causes", [])) \
                + (abs(np.log(max(1e-3, gpk[1]) / max(1e-3, gpk[0]))) * 20 if "glow_strength" in d.get("causes", []) else 0.0)
    limits = [{"widget": t["widget"], **x} for t in trecs for x in t.get("limits") or []]
    rec["summary"] = {"defects": len(defects), "errors": len(defects), "approx": len(approx), "by_code": by_code, "by_stage": by_stage,
                      "fixable": sum(1 for d in defects if d.get("fixable")), "limits": limits,
                      "texts_compared": sum(1 for t in trecs if t.get("render") and t.get("concept")), "hidden_not_drawn": sorted(not_drawn)}
    rec["badness"] = round(badness, 3)
    # 변환 흔들림(기록만) — 원본 ↔ 변환 컨셉 이동
    cv = bgrec.get("convert") or {}
    if cv.get("used"):
        rec["conversion"] = {"cached": bool((cv.get("concept") or {}).get("cached")), "codex_calls": cv.get("codex_calls")}
        orig = inp["norm"].get("original_concept")
        if orig and pathlib.Path(orig).is_file():
            try:
                from PIL import Image
                with Image.open(orig) as im:
                    o = np.asarray(im.convert("L").resize((W, H), Image.Resampling.BILINEAR), np.float32)
                r8 = cv2.cvtColor(np.clip(ref_black, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
                (sx, sy), resp = cv2.phaseCorrelate(o, r8, cv2.createHanningWindow((W, H), cv2.CV_32F))
                rec["conversion"].update(shift_px=[round(float(sx), 1), round(float(sy), 1)], response=round(float(resp), 3))
            except Exception as exc:  # noqa: BLE001 — 기록만
                rec["conversion"]["error"] = str(exc)[:200]
    heat = np.maximum(np.where(text_zone, 0.0, np.maximum(loc_b, loc_g)), loc_t)
    # 사람 눈 그림의 가운데 = 컨셉 상태 렌더(verify 가 hidden_state_split 으로 숨은 위젯을 컨셉처럼 켜고 끈 실제 엔진 렌더) — 없으면 기계 상태 맞춤(base)
    shown = base
    if render_state is not None:
        ov = {h["widget"]: {"visible": bool(h["drawn_in_concept"])} for h in states}
        try:
            sp = render_state(ov)
            sr = _load_rgb(sp) if sp else None
            if sr is not None and sr.shape[:2] == (H, W):
                shown = sr
                rec["state"]["render"] = str(sp)
                # E8 — 컨셉 상태로 그린 렌더가 숨은 위젯 자리에서 기계 비교(base)보다 컨셉과 다르면(상태를 못 맞춤)
                hz = np.zeros((H, W), bool)
                for h in states:
                    for i in h["subtree"]:
                        g = geo.get(i)
                        if g and g.get("w", 0) > 0 and g.get("h", 0) > 0:
                            hz |= _box_mask((H, W), [g["x"], g["y"], g["w"], g["h"]], HIDDEN_PAD)
                loc_s = local_mean(delta_e(sr, ref_black))
                bad = hz & (loc_s > T) & ~(np.maximum(loc_b, loc_g) > T) & ~text_zone
                k8, lab8, st8, _ = cv2.connectedComponentsWithStats(bad.astype(np.uint8), connectivity=8)
                for i in range(1, k8):
                    if st8[i, cv2.CC_STAT_AREA] >= int(s["min_area"]):
                        blob = lab8 == i
                        defects.append({"stage": "state", "code": "E8", "box": _bbox(blob), "area": int(blob.sum()), "widgets": rec["state"]["force_visible_extra"][:3]
                                        + rec["state"]["drawn_hidden_at_start"][:3], "fixable": False, "max_de": round(float(loc_s[blob].max()), 1),
                                        "cause": "state — the concept-state render does not match the concept here (hidden widget state)"})
                        defects[-1]["n"] = len(defects)
                        rec["summary"]["defects"] = rec["summary"]["errors"] = len(defects)
                        rec["summary"]["by_code"]["E8"] = rec["summary"]["by_code"].get("E8", 0) + 1
        except Exception as exc:  # noqa: BLE001 — 상태 렌더 실패는 기록(그림은 base 로)
            rec["state"]["render_error"] = f"{type(exc).__name__}: {exc}"[:300]
    # 상태 검사(1b 후속 L 다음 — gen/state_check): S1 숨김 흔적(시작 때 숨는 위젯을 끈 게임 기본 상태 — 검정 엔진 렌더 · 회색 · 흰 바탕 합성, 숨는 글자 상자도
    # 빼지 않음 = S3) · S2 게이지 끝(진행률 0 · 0.05 · 1.0). 엔진 렌더(verify render_state)가 없으면 합성(정답 묶음 · 회귀 묶음 오프라인) — 기록만(record) · 오류(error, E8)
    band = None
    sc_mode = str(s.get("state_checks") or "record")
    if sc_mode != "off":
        sc: dict = {"mode": sc_mode}
        try:
            engine = render_state is not None and bool(rec["state"].get("render"))
            roots = _hidden_roots(spec)
            rend_off = None
            if engine and roots:
                try:
                    rend_off = _state_render(render_state, {r: {"visible": False} for r in roots}, "state_off", (H, W))
                except Exception as exc:  # noqa: BLE001 — 기록하고 합성으로
                    sc["render_off_error"] = f"{type(exc).__name__}: {exc}"[:200]
            glyphs = {k: (v["concept"] | v["concept_cand"]) for k, v in gm.items()}
            ht = state_check.hidden_trace(spec, boxes, textures, canvas, rc0, ra0, states, glyphs, s, render_off=rend_off)
            # S1 보강 — 접히는 영역(시작 때 숨음 · flag)을 모두 끈 상태의 남은 빛
            rend_tog = None
            from gen import territory
            togs = [r_["id"] for r_ in territory.toggle_regions(spec)]
            if engine and togs:
                try:
                    rend_tog = _state_render(render_state, {r: {"visible": False} for r in sorted(set(roots) | set(togs))}, "state_toggles_off", (H, W))
                except Exception as exc:  # noqa: BLE001 — 기록하고 합성으로
                    sc["render_toggles_error"] = f"{type(exc).__name__}: {exc}"[:200]
            hh = state_check.hidden_halo(spec, boxes, textures, canvas, ra0, states, s, render_off=rend_tog)
            ov_state = {h["widget"]: {"visible": bool(h["drawn_in_concept"])} for h in states}
            rp = None
            if engine:
                def rp(wid, p):
                    ov = {**ov_state, wid: {**ov_state.get(wid, {}), "percent": float(p)}}
                    return _state_render(render_state, ov, f"state_{wid}_{int(round(float(p) * 100)):03d}", (H, W))
            base_g = shown if engine else comp_state
            ref_png = _load_rgb(rd / "reference.png")
            gs = state_check.gauge_states(spec_state, boxes, textures, canvas, s, base_g, render_pct=rp, ref_png=ref_png)
            # 원형 진행(고리 — 전투 HUD 동작 11-23): 0 · 중간 넷 · 100 % — 게이지와 같은 모양이라 그림 · 기록을 같이 싣는다
            rs = state_check.radial_states(spec_state, boxes, textures, canvas, s, base_g, render_pct=rp)
            gs = {**gs, "gauges": gs["gauges"] + rs["gauges"], "findings": gs["findings"] + rs["findings"], "images": {**gs["images"], **rs["images"]}}
            # S4 글자 밑 흔적(1b 후속 L 다음 L-1 글자 완전 지우기) — 모든 글자 빈 값 상태(텍스처 합성 · 엔진 text "")와 값 글자를 다른 값으로 그린 엔진 렌더
            tt, notext_imgs, values_img, group_imgs = None, None, None, {}
            try:
                off_ids: set[str] = set()
                for r_ in roots:
                    off_ids |= _subtree(spec, r_)
                notext_imgs = {"black": backdrop.compose(_without(spec, off_ids), boxes, textures, canvas, (0, 0, 0))[0],
                               "gray": ht["images"]["gray"], "white": ht["images"]["white"]}
                plate = notext_layers(rd, nt, spec) if nt.get("used") and (rd / str(nt.get("color"))).is_file() and (rd / str(nt.get("alpha"))).is_file() else None
                r_nt = r_val = None
                if engine:
                    ov0 = {r_: {"visible": False} for r_ in roots}
                    ov_nt = {**ov0, **{w_["id"]: {"text": ""} for w_ in spec.get("widgets", []) if w_.get("type") in backdrop.TEXT_TYPES and w_["id"] not in off_ids}}
                    try:
                        r_nt = _state_render(render_state, ov_nt, "state_notext", (H, W))
                        vals = state_check.value_overrides(spec)
                        if vals and r_nt is not None:
                            r_val = _state_render(render_state, {**ov0, **vals}, "state_values", (H, W))
                    except Exception as exc:  # noqa: BLE001 — 기록하고 합성으로
                        sc["render_text_error"] = f"{type(exc).__name__}: {exc}"[:200]
                # S4 숨는 묶음(글자 지우기 마감) — 텍스처째 숨는 위젯(배너)은 그것만 켠 글자 없는 상태로(합성 · 엔진 visible + text "")
                groups = state_check.texture_groups(spec, textures)
                for g_ in groups:
                    off_g: set[str] = set()
                    for r_ in roots:
                        if r_ != g_["root"]:
                            off_g |= _subtree(spec, r_)
                    sp_g = _without(spec, off_g)
                    g_["images"] = {k_: backdrop.compose(sp_g, boxes, textures, canvas, bg_)[0]
                                    for k_, bg_ in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
                    g_["render"] = None
                    if engine:
                        ov_g = {**{r_: {"visible": False} for r_ in roots if r_ != g_["root"]}, g_["root"]: {"visible": True},
                                **{w_["id"]: {"text": ""} for w_ in spec.get("widgets", []) if w_.get("type") in backdrop.TEXT_TYPES and w_["id"] not in off_g}}
                        try:
                            g_["render"] = _state_render(render_state, ov_g, f"state_notext_{g_['root']}", (H, W))
                        except Exception as exc:  # noqa: BLE001 — 기록하고 합성으로
                            sc.setdefault("render_group_errors", []).append(f"{g_['root']}: {type(exc).__name__}: {exc}"[:200])
                tt = state_check.text_trace(spec, boxes, canvas, rc0, ra0, plate, gm, s, notext_imgs, renderer="engine" if r_nt is not None else "composite",
                                            render_values=r_val, render_notext=r_nt, groups=groups)
                if r_nt is not None:
                    notext_imgs["black"] = r_nt
                values_img = r_val
                group_imgs = {g_["root"]: {"images": {**g_["images"], **({"black": g_["render"]} if g_["render"] is not None else {})},
                                           "renderer": "engine" if g_["render"] is not None else "composite",
                                           "box": [geo[g_["root"]][k_] for k_ in ("x", "y", "w", "h")] if g_["root"] in geo else None} for g_ in groups}
            except Exception as exc:  # noqa: BLE001 — 검사가 깨지면 기록
                sc["text_trace_error"] = f"{type(exc).__name__}: {exc}"[:300]
            findings = [{k: v for k, v in f.items() if k != "mask"} for f in ht["findings"] + hh["findings"] + gs["findings"] + (tt["findings"] if tt else [])]
            rec_only = set(s.get("state_record_only") or [])
            # 사용자 결정 ③(11-20) — refine 이 '정답 없음'(근거 기록)으로 표시한 글자 자리 안의 S4 결함은 오류 대신 '정답 없음 — 수동 확인 필요'(다른 결함은 그대로 오류)
            mchecks = manual_checks(rd)
            for f in findings:
                if f.get("check") in rec_only:
                    f["record_only"] = True
                mm = manual_match(f, mchecks, spec)
                if mm:
                    f["manual_check"] = mm
            if mchecks:
                rec["manual_check"] = [{**m, "findings": [{k: f.get(k) for k in ("check", "box", "max_de", "area")} for f in findings
                                                          if (f.get("manual_check") or {}).get("box") == m.get("box") and f.get("widgets", [None])[0] == m.get("widget")]}
                                       for m in mchecks]
                rec["summary"]["manual_check"] = sum(1 for f in findings if f.get("manual_check"))
            sc.update(hidden_trace={"renderer": ht["renderer"], "roots": ht["roots"]},
                      hidden_halo={"renderer": hh["renderer"], "roots": hh["roots"], "toggles": hh["toggles"]}, gauge_states={"renderer": gs["renderer"], "gauges": gs["gauges"]},
                      findings=findings)
            if tt is not None:
                sc["text_trace"] = {"renderer": tt["renderer"], "texts": tt["texts"], **({"values": tt["values"]} if tt.get("values") else {}),
                                    **({"line_like": tt["line_like"]} if tt.get("line_like") else {}), **({"groups": tt["groups"]} if tt.get("groups") else {}),
                                    **({"lift_like": tt["lift_like"]} if tt.get("lift_like") else {})}
            band = {"off": ht["images"], "off_renderer": ht["renderer"], "toggles_off": hh["images"] if hh["toggles"] else {}, "toggles_renderer": hh["renderer"],
                    "gauges": gs["images"], "gauge_base": base_g,
                    "gauge_boxes": {k: [geo[k]["x"], geo[k]["y"], geo[k]["w"], geo[k]["h"]] for k in gs["images"] if k in geo},
                    "gauge_renderer": {g_["widget"]: g_.get("renderer") for g_ in gs["gauges"]},
                    "notext": notext_imgs, "notext_renderer": tt["renderer"] if tt else None, "values": values_img, "notext_groups": group_imgs}
            if sc_mode == "error" and findings:
                for f in [f_ for f_ in findings if not f_.get("record_only") and not f_.get("manual_check")]:
                    defects.append(dict(f))
                    defects[-1]["n"] = len(defects)
                    rec["summary"]["by_code"]["E8"] = rec["summary"]["by_code"].get("E8", 0) + 1
                    rec["summary"]["by_stage"]["state"] = rec["summary"]["by_stage"].get("state", 0) + 1
                    rec["badness"] = round(rec["badness"] + f["area"] / 100.0, 3)
                rec["summary"]["defects"] = rec["summary"]["errors"] = len(defects)
        except Exception as exc:  # noqa: BLE001 — 검사가 깨지면 기록(오류 모드면 아래 게이트가 못 넘게 표시)
            sc["error"] = f"{type(exc).__name__}: {exc}"[:300]
        rec["state_checks"] = sc
    if pictures and out_dir is not None:
        try:
            rec["pictures"] = _pictures(pathlib.Path(out_dir), ref_black, base, comp_state, heat, defects)
            man = [f for f in (rec.get("state_checks") or {}).get("findings") or [] if f.get("manual_check")]
            cx = [m for m in rec.get("manual_check") or [] if m.get("reason") == "complex_background"]
            rec["pictures"].append(compare_picture(pathlib.Path(out_dir) / "compare.png", ref_text, shown, heat, defects, trecs, gm, band=band,
                                                   manual=man, complex_bg=cx))
        except Exception as exc:  # noqa: BLE001 — 그림 실패는 기록만
            rec["pictures_error"] = f"{type(exc).__name__}: {exc}"[:300]
    if out_dir is not None:
        od = pathlib.Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        (od / "diagnosis.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return rec


def _pictures(out: pathlib.Path, ref, ren, comp, loc, defects) -> list[str]:
    """번호 붙인 결함 그림 — defects.png(레퍼런스 | 렌더 | 국소 지도, 절반 크기) · defects_sheet.png(결함마다 레퍼런스 | 렌더 | 합성 확대)."""
    import cv2
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    H, W = loc.shape
    heat = np.ascontiguousarray(cv2.applyColorMap(np.clip(loc * 8, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1])
    panels = [np.ascontiguousarray(np.clip(ref, 0, 255).astype(np.uint8)), np.ascontiguousarray(np.clip(ren, 0, 255).astype(np.uint8)), heat]
    for d in defects:
        x, y, w, h = d["box"]
        c = STAGE_COLORS.get(d["stage"], (255, 255, 255))
        for p in panels:
            cv2.rectangle(p, (x - 3, y - 3), (x + w + 3, y + h + 3), c, 2)
            cv2.putText(p, str(d["n"]), (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, c, 2, cv2.LINE_AA)
    sep = np.full((H, 8, 3), 255, np.uint8)
    side = np.concatenate([panels[0], sep, panels[1], sep, panels[2]], axis=1)
    Image.fromarray(side).resize((side.shape[1] // 2, H // 2), Image.Resampling.LANCZOS).save(out / "defects.png")
    names = ["defects.png"]
    rows = []
    for d in defects[:24]:
        x, y, w, h = d["box"]
        p = 16
        X0, Y0, X1, Y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
        tiles = [np.clip(a[Y0:Y1, X0:X1], 0, 255) for a in (ref, ren, comp)]
        k = 140.0 / max(1, Y1 - Y0)
        k = min(k, 900.0 / max(1, 3 * (X1 - X0)))
        tw, th = max(1, int((X1 - X0) * k)), max(1, int((Y1 - Y0) * k))
        tiles = [cv2.resize(t.astype(np.uint8), (tw, th), interpolation=cv2.INTER_NEAREST if k >= 1 else cv2.INTER_AREA) for t in tiles]
        lab = np.full((th, 44, 3), 30, np.uint8)
        cv2.putText(lab, str(d["n"]), (4, min(th - 4, 28)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, STAGE_COLORS.get(d["stage"], (255, 255, 255)), 2, cv2.LINE_AA)
        sp = np.full((th, 4, 3), 255, np.uint8)
        rows.append(np.concatenate([lab, tiles[0], sp, tiles[1], sp, tiles[2]], axis=1))
    if rows:
        wmax = max(r.shape[1] for r in rows)
        rows = [np.pad(r, ((0, 4), (0, wmax - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
        Image.fromarray(np.concatenate(rows, axis=0)).save(out / "defects_sheet.png")
        names.append("defects_sheet.png")
    return names


BAND_LABEL_H = 22
BAND_PAD = 24          # 상태 띠의 게이지 조각 = 막대 상자 + 이만큼(px — 프레임 끝 장식까지)


def _band_rows(band: dict, top_w: int) -> list:
    """1b 후속 L 다음 — compare.png 상태 띠: ① 게임 기본 상태(시작 때 숨는 위젯 끔) — 엔진(또는 합성) 검정 | 회색 바탕 합성 | 흰 바탕 합성(절반 크기)
    ② 게이지마다 컨셉 상태 | 0 % | 5 % | 100 % 조각(1:1, 두 장씩). 글자는 cv2 기본 글꼴이라 영문."""
    import cv2
    sep = 4

    def tile(img, label, scale):
        a = np.clip(img, 0, 255).astype(np.uint8)
        if scale != 1:
            a = cv2.resize(a, (max(1, int(a.shape[1] * scale)), max(1, int(a.shape[0] * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST)
        lab = np.full((BAND_LABEL_H, a.shape[1], 3), 30, np.uint8)
        cv2.putText(lab, label[:90], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
        return np.concatenate([lab, a], axis=0)

    def hcat(ts):
        h = max(t.shape[0] for t in ts)
        ts = [np.pad(t, ((0, h - t.shape[0]), (0, 0), (0, 0)), constant_values=255) for t in ts]
        out = [ts[0]]
        for t in ts[1:]:
            out += [np.full((h, sep, 3), 255, np.uint8), t]
        return np.concatenate(out, axis=1)
    rows = []
    off = band.get("off") or {}
    names = (("black", f"game start (start-hidden widgets off) - {band.get('off_renderer', 'composite')} on black"),
             ("gray", "game start - texture composite on gray"), ("white", "game start - texture composite on white"))
    ts = [tile(off[k], lbl, 0.5) for k, lbl in names if off.get(k) is not None]
    if ts:
        rows.append(hcat(ts))
    # 1b 후속 L 다음 L-1 글자 완전 지우기 — S4: 모든 글자 빈 값(엔진 또는 합성 검정 | 회색 | 흰 바탕 합성) · 값 글자를 다른 값으로(엔진)
    tg = band.get("toggles_off") or {}
    ts = [tile(tg[k], lbl, 0.5) for k, lbl in (("black", f"every collapsible widget off - {band.get('toggles_renderer', 'composite')} on black"),
                                               ("gray", "every collapsible widget off - texture composite on gray"),
                                               ("white", "every collapsible widget off - texture composite on white")) if tg.get(k) is not None]
    if ts:
        rows.append(hcat(ts))
    nt_ = band.get("notext") or {}
    ts = [tile(nt_[k], lbl, 0.5) for k, lbl in (("black", f"every text empty - {band.get('notext_renderer') or 'composite'} on black"),
                                                 ("gray", "every text empty - texture composite on gray"),
                                                 ("white", "every text empty - texture composite on white")) if nt_.get(k) is not None]
    if band.get("values") is not None:
        ts.append(tile(band["values"], "value texts at another value - engine", 0.5))
    for k in range(0, len(ts), 3):
        rows.append(hcat(ts[k:k + 3]))
    # 글자 지우기 마감 — S4 숨는 묶음: 텍스처째 숨는 위젯(배너)만 켜고 글자 빈 값(엔진 또는 합성 검정 | 회색 | 흰 바탕 합성), 그 위젯 상자 + BAND_PAD 1:1
    for root, gr in (band.get("notext_groups") or {}).items():
        bb, imgs = gr.get("box"), gr.get("images") or {}
        if not bb or not imgs:
            continue
        H, W = next(iter(imgs.values())).shape[:2]
        x0, y0 = max(0, int(bb[0]) - BAND_PAD), max(0, int(bb[1]) - BAND_PAD)
        x1, y1 = min(W, int(np.ceil(bb[0] + bb[2])) + BAND_PAD), min(H, int(np.ceil(bb[1] + bb[3])) + BAND_PAD)
        per = max(1, min(3, (top_w + sep) // max(1, (x1 - x0) + sep)))
        scale = 1.0 if per >= 2 else max(0.25, top_w / float(x1 - x0))
        ts = [tile(imgs[k][y0:y1, x0:x1], f"{root} shown, texts empty - {gr.get('renderer') if k == 'black' else 'composite'} on {k}", min(1.0, scale))
              for k in ("black", "gray", "white") if imgs.get(k) is not None]
        for k in range(0, len(ts), per):
            rows.append(hcat(ts[k:k + per]))
    for wid, imgs in (band.get("gauges") or {}).items():
        bb = (band.get("gauge_boxes") or {}).get(wid)
        if not bb:
            continue
        H, W = next(iter(imgs.values())).shape[:2]
        x0, y0 = max(0, int(bb[0]) - BAND_PAD), max(0, int(bb[1]) - BAND_PAD)
        x1, y1 = min(W, int(np.ceil(bb[0] + bb[2])) + BAND_PAD), min(H, int(np.ceil(bb[1] + bb[3])) + BAND_PAD)
        rend = (band.get("gauge_renderer") or {}).get(wid) or {}
        items = [("concept state", band.get("gauge_base"))] + [(f"{p:.0%} - {rend.get(p, 'composite')}", im) for p, im in sorted(imgs.items())]
        scale = 1.0 if 2 * (x1 - x0) + sep <= top_w else max(0.25, (top_w - sep) / (2.0 * (x1 - x0)))
        ts = [tile(im[y0:y1, x0:x1], f"{wid} {lbl}", scale) for lbl, im in items if im is not None]
        for k in range(0, len(ts), 2):
            rows.append(hcat(ts[k:k + 2]))
    return rows


MANUAL_COLOR = (255, 64, 255)      # 수동 확인(정답 없음) 표시 색 — 오류 단계 색과 겹치지 않게


def compare_picture(path: pathlib.Path, ref, shown, heat, defects, trecs, gm, band: dict | None = None, manual: list | None = None,
                    complex_bg: list | None = None) -> str:
    """1b 후속 K — 사람 눈 비교 그림: 위 = 컨셉 | 컨셉 상태 렌더 | 국소 차이(글자 구역 바탕 포함, 결함 번호 · 오류 번호) — 절반 크기,
    아래 = 글자마다 3 배 확대 타일(컨셉 | 렌더 + 오류 · 근사 표시). 보고 전에 이 그림을 본다(force_visible render.png 는 기계용).
    1b 후속 L 다음 — band(상태 검사 그림)가 있으면 맨 아래 상태 띠(_band_rows — 게임 기본 상태 · 게이지 0 / 5 / 100 % · 밝은 바탕).
    글자 지우기 다음(사용자 결정 ③) — manual(오류 대신 '정답 없음 — 수동 확인 필요'로 돌린 S4 결함)은 국소 차이 판에 자홍 상자 'M' · 위 판 바로 밑 줄로 눈에 띄게,
    complex_bg(V8 복잡 배경 글자 — 기록)도 그 줄에."""
    import cv2
    from PIL import Image
    H, W = heat.shape
    hm = np.ascontiguousarray(cv2.applyColorMap(np.clip(heat * 8, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1])
    panels = [np.ascontiguousarray(np.clip(a, 0, 255).astype(np.uint8)) for a in (ref, shown)] + [hm]
    for d in defects:
        x, y, w, h = d["box"]
        c = STAGE_COLORS.get(d["stage"], (255, 255, 255))
        cv2.rectangle(panels[2], (x - 3, y - 3), (x + w + 3, y + h + 3), c, 2)
        cv2.putText(panels[2], f"{d['n']}:{d.get('code', '')}", (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, c, 2, cv2.LINE_AA)
    for f in manual or []:
        x, y, w, h = (int(v) for v in f["box"])
        for p in (panels[1], panels[2]):
            cv2.rectangle(p, (x - 4, y - 4), (x + w + 4, y + h + 4), MANUAL_COLOR, 3)
            cv2.putText(p, "M:no truth", (x, max(14, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, MANUAL_COLOR, 2, cv2.LINE_AA)
    sep = np.full((H, 8, 3), 255, np.uint8)
    top = np.concatenate([panels[0], sep, panels[1], sep, panels[2]], axis=1)
    top = np.asarray(Image.fromarray(top).resize((top.shape[1] // 2, H // 2), Image.Resampling.LANCZOS))
    rows = []
    notes = []
    for f in manual or []:
        ev = (f.get("manual_check") or {}).get("evidence") or {}
        notes.append((f"MANUAL CHECK - no ground truth under '{(f.get('widgets') or ['?'])[0]}' ({f.get('check')} max {f.get('max_de')}): "
                      f"concept alpha {ev.get('concept_alpha')} vs text-free plate {ev.get('plate_alpha')}, {ev.get('px')} px - not counted as an error",
                      MANUAL_COLOR))
    for m in complex_bg or []:
        bg = m.get("background") or {}
        notes.append((f"MANUAL CHECK - complex background under '{m.get('widget')}' (edge {bg.get('edge_frac')} / L* std {bg.get('l_std')}, "
                      f"generative fill backend: {m.get('backend', 'none')}) - recorded only", (255, 180, 64)))
    if notes:
        bar = np.full((26 * len(notes) + 6, top.shape[1], 3), 30, np.uint8)
        for k, (txt, c) in enumerate(notes):
            cv2.putText(bar, txt[:150], (8, 20 + 26 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 1, cv2.LINE_AA)
        rows.append(bar)
    for t in trecs:
        c, r = t.get("concept"), t.get("render")
        boxes = [b["box"] for b in (c, r) if b]
        if not boxes:
            continue
        x0 = max(0, min(b[0] for b in boxes) - 8)
        y0 = max(0, min(b[1] for b in boxes) - 8)
        x1 = min(W, max(b[0] + b[2] for b in boxes) + 8)
        y1 = min(H, max(b[1] + b[3] for b in boxes) + 8)
        k = 3 if (x1 - x0) * 3 * 2 <= top.shape[1] - 260 else max(1, (top.shape[1] - 260) // (2 * max(1, x1 - x0)))
        tiles = [cv2.resize(np.clip(a[y0:y1, x0:x1], 0, 255).astype(np.uint8), ((x1 - x0) * k, (y1 - y0) * k), interpolation=cv2.INTER_NEAREST)
                 for a in (ref, shown)]
        th = tiles[0].shape[0]
        lab = np.full((max(th, 48), 250, 3), 30, np.uint8)
        codes = ",".join(t.get("codes") or []) or "ok"
        ap = ",".join(sorted({a["kind"] for a in t.get("approx") or []}))
        colr = (255, 90, 90) if t.get("causes") else (120, 230, 140)
        cv2.putText(lab, str(t["widget"])[:22], (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(lab, codes + (f"  A:{ap}" if ap else ""), (4, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colr, 1, cv2.LINE_AA)
        tiles = [np.pad(tl, ((0, lab.shape[0] - th), (0, 0), (0, 0)), constant_values=255) for tl in tiles]
        sp = np.full((lab.shape[0], 6, 3), 255, np.uint8)
        rows.append(np.concatenate([lab, tiles[0], sp, tiles[1]], axis=1))
    if band:
        rows += _band_rows(band, top.shape[1])
    out = [top]
    if rows:
        wmax = max([top.shape[1]] + [r_.shape[1] for r_ in rows])
        out = [np.pad(a, ((0, 6), (0, wmax - a.shape[1]), (0, 0)), constant_values=255) for a in [top] + rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.concatenate(out, axis=0)).save(path)
    return path.name


def gate(rec: dict) -> dict:
    """진단 기록 → verify 게이트 dict(appearance). 통과 = 오류(E) 0 — 근사(A)는 표로만(1b 후속 K)."""
    if rec.get("skipped"):
        return {"name": "appearance", "pass": True, "skipped": rec["skipped"]}
    if rec.get("error"):
        return {"name": "appearance", "pass": False, "details": {"error": rec["error"]}}
    sc = rec.get("state_checks") or {}
    if sc.get("mode") == "error" and sc.get("error"):
        return {"name": "appearance", "pass": False, "details": {"error": f"state checks failed: {sc['error']}"}}
    sm = rec.get("summary") or {}
    top = [{k: d.get(k) for k in ("n", "code", "stage", "cause", "box", "area", "widgets", "fixable", "max_de")} for d in (rec.get("defects") or [])[:20]]
    return {"name": "appearance", "pass": sm.get("defects", 0) == 0, "value": sm.get("defects", 0), "threshold": 0,
            "details": {"errors": sm.get("errors", sm.get("defects", 0)), "approx": sm.get("approx", 0), "by_code": sm.get("by_code"),
                        "by_stage": sm.get("by_stage"), "fixable": sm.get("fixable"), "limits": sm.get("limits"), "badness": rec.get("badness"), "defects": top,
                        "maps": rec.get("maps"), "hidden_not_drawn": sm.get("hidden_not_drawn"), "truth": rec.get("truth")}}
