"""상태 검사 (1b 후속 L 다음 — 상태 렌더 검증, 11-19) — 컨셉 한 장이 그린 상태 밖의 상태를 그려 둘레 · 컨셉 상태와 맞댄다.

매핑(layer · refine 판 · concept_fill 채움)은 컨셉 한 장(한 상태)만 보고 픽셀 주인과 다른 상태를 추측하고, 진단은 그 상태 하나를 검정 바탕에서만 봐서
그 추측을 성공으로 판정했다 [실측 R20261119_091634 사용자 인게임 — ① 시작 때 숨는 '오의 불가' 자리 판에 회색 둥근 상자 · 어두운 덩어리(검정 위에선 안
보이고, 진단은 글자를 컨셉 상태로 켠 렌더만 봐 글자가 덮음) ② 게이지 100 % 에서 채움 번짐 24 px 가 트랙 끝을 넘어 끝 장식을 어두운 사각형으로 덮음
(70 % 미리보기는 빈 트랙 위라 컨셉과 같음)].

S1 숨김 흔적(hidden_trace) — 시작 때 숨는 위젯(diagnose._hidden_roots — 그 아래 전부)을 모두 끈 게임 기본 상태를 검정 엔진 렌더(없으면 검정 합성) ·
   회색 · 흰 바탕 텍스처 합성(gen/backdrop)으로 그리고, 컨셉이 그 위젯을 그린 것(hidden_state_split 의 drawn_in_concept)마다 그 자리(글자 = 상자 + 빛 +
   4 px, 그 밖 = 상자 + 4 px — 다른 보이는 글자 · 런타임 그림 자리는 뺌)에서 둘레로 설명되지 않는 덩어리를 찾는다. 설명 =
   (가) 둘레 가까이: 둘레 고리(RING px)의 가우스 가중 평균(σ NEAR_SIGMAS — 받침이 있는 자리만)
   (나) 띠: 같은 줄(열)의 양끝 둘레 대표색이 BAND_DE 안으로 같으면 그 사이 선형 보간(자리를 가로지르는 구조선 · 빛 띠 — 게이지 테두리 윗선)
   (다) 둘레 대표색(고리 중앙값 — 자리 안은 둘레처럼 비어야 한다)
   (라) 컨셉 그대로: 컨셉이 그린 글자 · 빛 자리(컨셉 글자 획 + 빛 + FOOT_PAD, 글자 아닌 위젯은 상자) 밖에서 컨셉 픽셀과 같음(그 자리의 구조물 — 테두리 가운데 장식)
   픽셀 차 = 그중 가장 작은 ΔE00 → 자리 안만의 7 × 7 창 평균 > local_de 인 자리 덩어리(넓이 ≥ min_area) — 바탕 셋 중 하나라도.
S2 게이지 끝(gauge_states) — 가로 게이지마다 진행률 0 · 0.05 · 1.0 렌더(엔진 — 없으면 합성): 트랙 상자 밖(막대 상자 + GAUGE_PAD 안 — 프레임 · 끝 장식)
   이 컨셉 상태 렌더와 국소 차 > local_de(트랙 밖만의 창 평균 — 트랙 안 채움 차가 번져 들지 않게) · 1.0 에서 트랙 끝 구간이 0 과 같음(채움이 안 닿음 —
   END_SAME_FRAC 넘게 ΔE00 < END_SAME_DE) · 0 에서 트랙 안(보이는 글자 자리 뺌)이 채움 없는 합성과 국소 차 > local_de(채움이 남음).
S3 — S1 의 회색 · 흰 바탕 합성 지표는 시작 때 숨는 글자 상자를 빼지 않는다(backdrop.text_mask · 진단 글자 구역 제외를 안 쓴다 — 그 자리가 검사 대상).
S4 글자 밑 흔적(text_trace — 1b 후속 L 다음 L-1 글자 완전 지우기) — 모든 글자를 빈 값으로 그린 상태(엔진 overrides text "" · 텍스처 합성 = 글자 없음)에서
   보이는 글자(시작 때 숨는 글자는 S1 몫)마다 자리 = 컨셉 글자 획(후보 · 핵심) + 빛 꼬리(glow_measure, ≤ TEXT_TAIL_MAX) + TEXT_ZONE_PAD ∩ 상자 + 빛 + 4 px.
   설명 = S1 (가) · (나) · (다) + (마) 글자 없는 판 ±2 px 이동 최소(판이 그린 띠 · 테두리) + (라) 컨셉 그대로 — 단 (라)는 컨셉이 글자 · 빛을 그린 자리
   (핵심 획 + TEXT_CORE_PAD ∪ 빛 꼬리 안 '컨셉이 판(±2 px 이동 최대)보다 L* TEXT_GLOW_DL 넘게 밝은' 픽셀) 밖에서만 — 빈 값에선 컨셉 글자 · 빛이 정답이
   아니다. 자리가 겹친 글자는 한 덩어리로(둘레 고리 공유). 판정 = 자리 안만의 3 × 3 창 평균 > text_trace_de · 덩어리 ≥ text_trace_min_area —
   S1 의 7 × 7 · 10 은 얇은 빛 윤곽을 못 본다 [실측 R20261119_144231 체인 패널 '4.2' 빛 윤곽 — 3 × 3 최대 7.1 · 7 × 7 최대 5.8, 깨끗한 L-2 010312 ·
   보호 run(판 설명 넣은 뒤) 3 × 3 최대 ≤ 4.8]. 값이 바뀌는 글자(바인딩 number · text)는 같은 형식 다른 값(_other_value)으로도 그려(엔진만) 새 글자 +
   빛 자리를 뺀 옛 자리에서 같은 판정(text_value_trace).
S4 보강(1b 후속 L 다음 — 글자 지우기 마감, 11-19):
   숨는 묶음 — 시작 때 숨는 위젯 중 자기 · 자손이 텍스처를 그리는 것(texture_groups — 배너)은 그 위젯만 켠 글자 없는 상태(합성 · 엔진 visible + text "")로
     그 아래 글자 자리를 같은 판정(결함 · 기록에 state). 글자만 숨는 것('오의 불가')은 S1 · F1 그대로.
   가는 선(text_contour) — 자리 안 픽셀 차 > text_contour_de 가 8-연결로 골격 길이 ≥ text_contour_len · 두께 ≤ CONTOUR_THICK(곧은 가로 · 세로 선은 구조선 —
     line_like 기록만). 3 × 3 평균은 1 px 윤곽(국소 3.1)을 못 봤다 [실측 R20261119_190059 '4' 안쪽 윤곽].
   (마) 글자 없는 판은 이 자리 둘레 고리에 색조 맞춘 사본(_tone_matched) — 판 그대로면 둘레와 색조가 다른 판 조각을 글자 자리에 붙인 얼룩까지 '판과 같음'.
   밝힌 검정(lift — 검정 합성 × text_trace_lift)은 기록만(local_max.lift) — refine 글자 지우기 고르기가 쓴다(어두운 판의 낮은 대비 흔적).
S2 보강(gauge_end_cover · gauge_end_gap) — concept_fill 게이지는 1.0 에서 트랙 끝 구간(끝에서 max(END_COLS, END_SHAPE_FRAC × 트랙 폭)) 안의 컨셉 트랙
   hole(concept_fill.track_hole — 끝 장식 안쪽 호까지) 밖 프레임 구조물이 0 렌더와 국소 차 > local_de(채움이 끝 장식 호를 덮음 — S2 는 트랙 상자 밖만 봐 못 봤다
   [실측 R20261119_144231 사용자 눈 — 100 % 오른쪽 끝 곧은 테두리]) · 그 구간 hole 이 0 렌더와 END_SAME_FRAC 넘게 같음(호 안 빈 트랙을 못 채움).
S4 보강(1b 후속 L 다음 — 글자 지우기 다음, 11-20):
   V2 구조선 규칙 좁힘 — 선 모양 덩어리(짧은 변 ≤ TEXT_LINE_MAX · 곧은 가는 선)는 글자 없는 판(색조 맞춘 판 ±2 px)에도 있는 선일 때만 구조선(기록만, plate_line).
     판에 없는 선은 appearance.text_line_plate: error 면 결함(line_not_in_plate) — 막대 윗선 위에 남은 글자 빛 자국이 '구조선'으로 빠졌다.
   V3 밝힌 검정 — 둘레 고리 검정 합성 L*(ring_l) · 밝힘 국소 > LIFT_RECORD_DE 덩어리(lift_like) 기록. appearance.text_lift_mode: error 면 어두운 판 자리
     (ring_l < LIFT_DARK_L)의 밝힘 국소 > text_lift_de 덩어리를 결함(check text_lift).
S1 보강 hidden_halo(L-2 기본 전환 ④, 11-23) — 접히는 루트 직계 영역(시작 때 숨음 · flag 바인딩 — 컨셉이 그린 것)을 하나씩 끈 상태에서, 그 영역 몫
   (gen/territory.claim — 컨셉에서 보이는 픽셀 중 가장 가까운 영역이 이 위젯 · 96 px 안 — 과 자기 상자 안)에 **정적 판이 그린 픽셀**이 바탕(검정 · 회색 · 흰)과
   3 × 3 국소 ΔE00 > halo_de 로 다른 덩어리(≥ min_area) = 위젯이 접혀도 남는 빛 · 넘침. S1 은 위젯 상자 밖 4 px 고리를 기록만 했다(overhang_px) — 실제로는 상자 밖
   수십 px 까지 남았다 [실측 L-2 R20261120_140653 — 배너 23,021 px · 체인 패널 19,583 px(flag — 시작 때는 보여 S1 대상도 아니었다)]. 엔진 렌더(접히는 영역을 모두
   끈 state_toggles_off)가 있으면 검정은 그것으로도 본다.
버튼 상태(button_states — Phase 3-2): 버튼마다(버튼 칸 자신 · 화면에 놓인 버튼 칸) 상태 일곱(core/button)의 엔진 렌더를 '그 상태의 그림을 얹은 텍스처 합성'과 견준다
   — 정답이 식(gen/theme)이라 픽셀로 견줄 수 있다. button_state(안쪽 — 글자 획 둘레 뺀 7 × 7 국소 > button_de) · button_outside(버튼 밖이 컨셉 상태와 다름) ·
   button_same(두 상태가 구별되지 않음) · button_text(글자가 안 읽힘) · button_text_moved(글자가 테마의 거리와 다르게 움직임) · button_render(그 상태를 못 그림 — 덮어쓰기가
   안 먹으면 render_widget 이 오류를 낸다. 합성으로 물러나지 않는다: 물러나면 정답을 정답과 견주게 된다).
결과 = 결함 dict(stage state · code E8 · check) — diagnose 가 appearance.state_checks 에 따라 기록만(record) 또는 오류로(error) — appearance.state_record_only
   에 든 check 는 오류 모드에서도 기록만(새 검사를 묶음 거짓 양성 0 확인 전까지).
"""
from __future__ import annotations

import copy

import numpy as np

from core import button
from gen import backdrop, cells
from gen import diagnose as dg
from gen import territory

WHITE = (255, 255, 255)
RING = 6                    # 둘레 고리 폭(px)
NEAR_SIGMAS = (2.0, 4.0)    # (가) 둘레 가까이 — 이 크기의 가우스 가중 평균만(멀리는 띠 · 대표색 · 컨셉으로만 설명)
NEAR_SUPPORT = 0.05
BAND_DE = 10.0              # (나) 같은 줄(열) 양끝 둘레 대표색 ΔE00 이 이보다 작으면 띠
BAND_MIN_PX = 2             # 양끝 둘레 각각 이만큼 이상 픽셀이 있어야 띠
FOOT_PAD = 3                # (라) 컨셉 글자 · 빛 자리 = 컨셉 글자 획 + 빛 + 이만큼
GAUGE_PAD = 8               # S2 트랙 밖 = 막대 상자 + 이만큼(px) 안
GAUGE_STATES = (0.0, 0.05, 1.0)
BAR_STATES = (0.0, 0.05, 0.15, 0.4, 0.65, 0.9, 1.0)     # 모양 막대(gen/silhouette — 메인 HUD 11-24) — 중간 넷은 자르는 자리 · 방향
BAR_EDGE_PX = 2             # 자르는 자리에서 이만큼(px) 안은 판정에서 뺀다(화면 픽셀 반올림)
BAR_ZONE_ALPHA = 0.1        # 막대 자리 = 텍스처 알파가 이보다 큰 픽셀
END_COLS = 8                # S2 1.0 트랙 끝 구간 = 끝에서 max(이만큼, 트랙 폭 × END_FRAC) px(맨 끝 2 px 뺌) × 트랙 가운데 절반 줄
END_FRAC = 0.03
END_SAME_DE = 5.0           # 그 구간이 0 렌더와 ΔE00 이만큼 안이면 '안 바뀜'(채움이 안 닿음)
END_SAME_FRAC = 0.3
END_SHAPE_FRAC = 0.08       # S2 보강 — 끝 장식 호를 보는 트랙 끝 구간(트랙 폭 비)
TEXT_TAIL_MAX = 24          # S4 — 글자 빛 꼬리 상한(px — glow_measure max_d)
TEXT_ZONE_PAD = 3           # S4 자리 = 컨셉 글자 획 + 빛 꼬리 + 이만큼
TEXT_CORE_PAD = 2           # S4 (라) 금지 자리 = 핵심 획 + 이만큼 ∪ 빛 픽셀
TEXT_GLOW_DL = 3.0          # S4 빛 픽셀 = 컨셉 L* − 판 ±2 px 이동 최대 L* > 이것(판에도 있는 구조물은 빛 아님)
TEXT_LOCAL = 3              # S4 국소 창(px)
TEXT_LINE_MAX = 2           # S4 덩어리 상자의 짧은 변이 이 이하면 선 모양(구조선) — 기록(line_like)만
# 1b 후속 L 다음 — 글자 지우기 마감: S4 가는 선(text_contour). 3 × 3 창 평균(text_trace)은 1 px 윤곽(국소 3.1)을 못 봤다 [실측 R20261119_190059 체인 패널 '4' —
# 판 구조물 지킴이 남긴 컨셉 빛 테두리 선 385 px · 섞임 띠의 판 색 고리]. 자리 안 픽셀 차(설명 최소 ΔE00) > CONTOUR_DE 가 8-연결로 이어진 덩어리의 골격 길이 ≥ CONTOUR_LEN
# 이고 두께(넓이 ÷ 골격 길이) ≤ CONTOUR_THICK(두꺼운 덩어리는 text_trace 몫). 값은 appearance.text_contour_de · text_contour_len 으로 덮음
CONTOUR_DE = 2.5
CONTOUR_LEN = 40
CONTOUR_THICK = 3.0
CONTOUR_LINK = 1            # 가는 선 — 이만큼(px) 틈은 잇고 잼(text_contour_link 로 덮음)
CONTOUR_LINK_DENSITY = 0.3  # 이은 덩어리에서 원래 픽셀 비율 하한(흩어진 잡티 빼기)
CONTOUR_LINE_SHORT = 5      # 가는 선 덩어리 상자 짧은 변 ≤ 이것 · 긴 변 ≥ 짧은 변 × CONTOUR_LINE_RATIO 면 곧은 구조선(기록만)
CONTOUR_LINE_RATIO = 4.0
# 1b 후속 L 다음 — 글자 지우기 다음 V2: 선 모양 덩어리(짧은 변 ≤ TEXT_LINE_MAX · 곧은 가는 선)를 구조선(기록만)으로 보는 것은 **그 선이 글자 없는 판에도 있을 때만**
# — 선 픽셀의 LINE_PLATE_FRAC 이상이 색조 맞춘 판 ±2 px 이동 최소 차(d_s)가 판 바탕(둘레 고리 판 중앙값)과의 차(d_b)보다 LINE_PLATE_MARGIN 넘게 작고(판의 선이
# 바탕보다 그 선을 잘 설명) 판의 그 자리(±2 px 최대)가 판 바탕과 text_trace_de 넘게 다를 때(판에 실제로 선이 있음). 아니면 판에 없는 선 = 글자 흔적
# [실측 R20261120_005215 파티 HP 숫자 — 막대 윗선 약 5 px 위의 녹색 빛 반원 띠 22 × 2 · 7.1 이 '구조선'으로 빠졌다(사용자 눈)]
LINE_PLATE_FRAC = 0.6
LINE_PLATE_MARGIN = 2.0
# 1b 후속 L 다음 — 글자 지우기 다음 V3: 밝힌 검정(lift)은 어두운 판 자리(둘레 고리 검정 합성 L* < LIFT_DARK_L)에서만 판정 후보 — 밝은 자리는 × 3 이 255 로
# 잘려 뜻이 없다. 기록 덩어리 = 밝힘 3 × 3 국소 > LIFT_RECORD_DE(보정용 낮은 문턱)
LIFT_DARK_L = 20.0
LIFT_RECORD_DE = 3.0


def _glow(w: dict) -> float:
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    return float((f.get("glow") or {}).get("size") or 0)


def _gbox(g: dict) -> list[float]:
    return [g["x"], g["y"], g["w"], g["h"]]


def masked_local(de, m, cover_min: float):
    """자리 m 안 픽셀만의 7 × 7 창 평균(자리 밖 값이 번져 들지 않게) — 창 안 자리 비율 < cover_min 이면 0."""
    import cv2
    mf = np.asarray(m, np.float32)
    c = cv2.blur(mf, (dg.WIN, dg.WIN))
    v = cv2.blur((np.asarray(de, np.float32) * mf), (dg.WIN, dg.WIN)) / np.maximum(c, 1e-6)
    return np.where(c >= cover_min, v, 0.0)


def _blobs(flag, loc, min_area: int) -> list[dict]:
    import cv2
    out = []
    n, lab, _, _ = cv2.connectedComponentsWithStats(cv2.dilate(flag.astype(np.uint8), np.ones((3, 3), np.uint8)), connectivity=8)
    for i in range(1, n):
        blob = (lab == i) & flag
        area = int(blob.sum())
        if area < min_area:
            continue
        out.append({"mask": blob, "box": dg._bbox(blob), "area": area, "max_de": round(float(loc[blob].max()), 1), "mean_de": round(float(loc[blob].mean()), 1)})
    return out


def _near_estimate(img, ring):
    """(가) 둘레 고리 픽셀의 가우스 가중 평균 — σ 작은 것부터, 받침(가중치 합) ≥ NEAR_SUPPORT 인 자리만. → (추정 HxWx3, 받침 있음 HxW)."""
    import cv2
    w = ring.astype(np.float32)
    est = np.zeros(img.shape, np.float32)
    done = np.zeros(ring.shape, bool)
    for s in NEAR_SIGMAS:
        den = cv2.GaussianBlur(w, (0, 0), s)
        ok = (den > NEAR_SUPPORT) & ~done
        if ok.any():
            num = np.dstack([cv2.GaussianBlur((img[..., i] * w).astype(np.float32), (0, 0), s) for i in range(3)])
            est[ok] = num[ok] / den[ok][:, None]
            done |= ok
    return est, done


def _band_estimate(img, zone, ring, axis: int):
    """(나) 띠 — 줄(axis 0) · 열(axis 1)마다 자리 양끝 바로 밖 둘레(RING px)의 중앙값 둘이 BAND_DE 안으로 같으면 그 사이 선형 보간. → (추정, 있음)."""
    from core import color
    if axis == 1:
        e, v = _band_estimate(np.transpose(img, (1, 0, 2)), zone.T, ring.T, 0)
        return np.transpose(e, (1, 0, 2)), v.T
    H, W = zone.shape
    est = np.zeros(img.shape, np.float32)
    valid = np.zeros((H, W), bool)
    rows = np.nonzero(zone.any(axis=1))[0]
    ends = []
    for y in rows:
        xs = np.nonzero(zone[y])[0]
        x0, x1 = int(xs.min()), int(xs.max())
        lm = ring[y, max(0, x0 - RING):x0]
        rm = ring[y, x1 + 1:x1 + 1 + RING]
        if int(lm.sum()) < BAND_MIN_PX or int(rm.sum()) < BAND_MIN_PX:
            continue
        L = np.median(img[y, max(0, x0 - RING):x0][lm], axis=0)
        R = np.median(img[y, x1 + 1:x1 + 1 + RING][rm], axis=0)
        ends.append((y, x0, x1, L, R))
    if not ends:
        return est, valid
    Ls = np.array([e[3] for e in ends], float)
    Rs = np.array([e[4] for e in ends], float)
    de = color.delta_e00(color.srgb_to_lab(Ls.reshape(-1, 1, 3)), color.srgb_to_lab(Rs.reshape(-1, 1, 3))).reshape(-1)
    for (y, x0, x1, L, R), d in zip(ends, de):
        if d >= BAND_DE:
            continue
        t = (np.arange(x0, x1 + 1) - (x0 - 1)) / float(x1 + 1 - (x0 - 1))
        est[y, x0:x1 + 1] = L[None, :] * (1 - t[:, None]) + R[None, :] * t[:, None]
        valid[y, x0:x1 + 1] = True
    return est, valid


def explain_diff(img, concept, zone, ring, foot, extra=None) -> np.ndarray:
    """자리 안 픽셀마다 '둘레 · 컨셉으로 설명되는 가장 가까운 값'과의 ΔE00(가 · 나 · 다 · 라 중 최소). 자리 밖은 0.
    extra = 더 넣을 설명 ΔE00 지도들(S4 (마) 글자 없는 판 ±2 px 이동 최소)."""
    from core import color
    img = np.asarray(img, np.float32)
    lab = color.srgb_to_lab(img[zone])          # 자리 안 픽셀만 잰다(끝에 자리 밖은 0)

    def de_to(est):
        out = np.zeros(zone.shape, np.float32)
        out[zone] = color.delta_e00(lab, color.srgb_to_lab(np.asarray(est, np.float32)[zone]))
        return out
    big = np.float32(1e9)
    d = np.full(zone.shape, big, np.float32)
    est, ok = _near_estimate(img, ring)
    if ok.any():
        d = np.where(ok, np.minimum(d, de_to(est)), d)
    for ax in (0, 1):
        est, ok = _band_estimate(img, zone, ring, ax)
        if ok.any():
            d = np.where(ok, np.minimum(d, de_to(est)), d)
    if ring.any():
        med = np.median(img[ring], axis=0)
        d = np.minimum(d, de_to(np.broadcast_to(med, img.shape)))
    if concept is not None:
        d = np.where(~foot, np.minimum(d, de_to(concept)), d)
    for e in extra or []:
        d = np.minimum(d, np.asarray(e, np.float32))
    return np.where(zone, d, 0.0).astype(np.float32)


def _crop_box(m, pad: int, shape):
    bb = dg._bbox(m)
    H, W = shape
    x0, y0 = max(0, bb[0] - pad), max(0, bb[1] - pad)
    return x0, y0, min(W, bb[0] + bb[2] + pad), min(H, bb[1] + bb[3] + pad)


def hidden_trace(spec: dict, boxes: list[dict], textures: dict, canvas, concept_rgb, concept_a, states: list[dict], glyphs: dict, s: dict,
                 render_off=None) -> dict:
    """S1 — → {"roots": [자리마다 기록], "findings": [결함], "images": {"black", "gray", "white"}(게임 기본 상태 — compare.png 띠), "renderer"}."""
    W, H = int(canvas[0]), int(canvas[1])
    geo = {b["id"]: b for b in boxes}
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    roots = dg._hidden_roots(spec)
    off_ids: set[str] = set()
    for r in roots:
        off_ids |= dg._subtree(spec, r)
    spec_off = dg._without(spec, off_ids)
    gray, gcov, ginfo = backdrop.compose(spec_off, boxes, textures, canvas, backdrop.GRAY, owners=True)
    white = backdrop.compose(spec_off, boxes, textures, canvas, WHITE)[0]
    renderer = "engine" if render_off is not None else "composite"
    black = render_off if render_off is not None else backdrop.compose(spec_off, boxes, textures, canvas, (0, 0, 0))[0]
    imgs = {"black": black, "gray": gray, "white": white}
    out = {"renderer": renderer, "roots": [], "findings": [], "images": imgs}
    if not roots:
        return out
    owner, owner_ids = ginfo.get("owner"), ginfo.get("owner_ids", [])
    excl = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        g = geo.get(w["id"])
        if not g or not g.get("visible", True) or w["id"] in off_ids or g["w"] <= 0 or g["h"] <= 0:
            continue
        if w.get("type") in backdrop.TEXT_TYPES:
            excl |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + _glow(w))      # 보이는 엔진 글자 — 합성엔 없다
        elif w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image":
            excl |= dg._box_mask((H, W), _gbox(g), 2)                              # 런타임 그림(정답 없음)
    ca = np.asarray(concept_a, np.float32)[..., None]
    concepts = {k: np.asarray(concept_rgb, np.float32) * ca + np.asarray(bg, np.float32) * (1 - ca)
                for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", WHITE))}
    drawn = {h["widget"]: h for h in states}
    T, cover, min_area = float(s["local_de"]), float(s["bg_cover"]), int(s["min_area"])
    for r in roots:
        h = drawn.get(r)
        if h is None or not h.get("drawn_in_concept"):
            out["roots"].append({"widget": r, "skipped": "the concept does not draw it — the game-start state is the concept state (main diagnosis)"})
            continue
        zone = np.zeros((H, W), bool)
        foot = np.zeros((H, W), bool)
        for i in sorted(dg._subtree(spec, r)):
            g = geo.get(i)
            if not g or g["w"] <= 0 or g["h"] <= 0:
                continue
            w = widgets[i]
            if w.get("type") in backdrop.TEXT_TYPES:
                gl = _glow(w)
                zone |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + gl)
                gm = glyphs.get(i)
                foot |= dg._dilate(gm, int(np.ceil(gl)) + FOOT_PAD) if gm is not None and gm.any() else dg._box_mask((H, W), _gbox(g), gl)
            else:
                zone |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD)
                foot |= dg._box_mask((H, W), _gbox(g))
        zone &= ~excl
        rec = {"widget": r, "zone_px": int(zone.sum())}
        # 기록만 — 숨는 글자 아닌 위젯 상자 바로 밖(+ HIDDEN_PAD)에 정적 판이 그리는 픽셀(넘침 장식 조각이 판에 남아 위젯이 숨어도 보임). 컨셉과 같은 픽셀이라
        # (라)가 설명해 결함으로는 안 센다 — 판 소유는 layer 몫 [실측 R20261119_091634 — 배너 양끝 · 아래 문장 판1 · 2 · 3]
        ring_out = np.zeros((H, W), bool)
        for i in dg._subtree(spec, r):
            g = geo.get(i)
            if g and g["w"] > 0 and g["h"] > 0 and widgets[i].get("type") not in backdrop.TEXT_TYPES:
                ring_out |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD) & ~dg._box_mask((H, W), _gbox(g))
        if ring_out.any() and owner is not None:
            plate_ids = [k for k, oid in enumerate(owner_ids) if str(oid).startswith("StaticPlate")]
            ov = ring_out & (gcov > 0.1) & np.isin(owner, plate_ids)
            if ov.any():
                rec["overhang_px"] = int(ov.sum())
                rec["overhang_owners"] = sorted({owner_ids[k] for k in np.unique(owner[ov])})
        if rec["zone_px"] < min_area:
            out["roots"].append({**rec, "skipped": "no spot left after the visible texts"})
            continue
        x0, y0, x1, y1 = _crop_box(zone, RING + dg.WIN, (H, W))
        z = zone[y0:y1, x0:x1]
        ring = dg._dilate(z, RING) & ~z & ~excl[y0:y1, x0:x1]
        rec["ring_px"] = int(ring.sum())
        if rec["ring_px"] < 20:
            out["roots"].append({**rec, "skipped": "no ring around the spot"})
            continue
        f = foot[y0:y1, x0:x1]
        flag = np.zeros(z.shape, bool)
        best = np.zeros(z.shape, np.float32)
        which: dict[str, np.ndarray] = {}
        rec["local_max"] = {}
        for k, img in imgs.items():
            d = explain_diff(img[y0:y1, x0:x1], concepts[k][y0:y1, x0:x1], z, ring, f)
            loc = masked_local(d, z, cover)
            fl = (loc > T) & z
            rec["local_max"][k] = round(float(loc[z].max()), 2)
            which[k] = fl
            flag |= fl
            best = np.maximum(best, np.where(z, loc, 0.0))
        bl = _blobs(flag, best, min_area)
        rec["blobs"] = len(bl)
        out["roots"].append(rec)
        for b in bl:
            bgs = [k for k, fl in which.items() if (fl & b["mask"]).any()]
            m = b["mask"]
            top = []
            if owner is not None:
                own = owner[y0:y1, x0:x1][m]
                ids, cnt = np.unique(own[own >= 0], return_counts=True)
                top = [owner_ids[k] for k in ids[np.argsort(-cnt)][:2]]
            bx = b["box"]
            out["findings"].append({"stage": "state", "code": "E8", "check": "hidden_trace", "box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "area": b["area"],
                                    "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": [r] + [t for t in top if t != r], "backgrounds": bgs,
                                    "renderer": renderer, "fixable": False,
                                    "cause": f"hidden trace — with '{r}' hidden (game start) its spot shows a blob the surroundings do not explain "
                                             f"({', '.join(bgs)} backdrop)"})
    return out


def hidden_halo(spec: dict, boxes: list[dict], textures: dict, canvas, concept_a, states: list[dict], s: dict, render_off=None) -> dict:
    """S1 보강 — 접히는 영역을 껐을 때 정적 판에 남은 그 영역의 빛 · 넘침. → {"roots": [기록], "findings": [결함], "images": {"black", "gray", "white"}(접히는
    영역을 모두 끈 상태 — compare.png 띠), "toggles": [끈 영역 id], "renderer"}."""
    import cv2
    W, H = int(canvas[0]), int(canvas[1])
    geo = {b["id"]: b for b in boxes}
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    tex_ids = {w["id"] for w in spec.get("widgets", []) if w.get("type") not in backdrop.TEXT_TYPES
               and any(isinstance(b, dict) and b.get("asset") in textures and b.get("draw_as", "image") != "none"
                       for k, b in (w.get("style") or {}).items() if k in dg.spec_brush_keys())}
    ca = np.asarray(concept_a, np.float32)
    T, min_area = float(s.get("halo_de", HALO_DE)), int(s["min_area"])
    drawn = {h["widget"]: h for h in states}
    out: dict = {"renderer": "engine" if render_off is not None else "composite", "roots": [], "findings": [], "images": {}, "toggles": []}
    omap = territory.owner_map(spec, (H, W), boxes)
    off_all: set[str] = set()
    targets = []
    for reg in territory.toggle_regions(spec):
        sub = dg._subtree(spec, reg["id"])
        off_all |= sub
        out["toggles"].append(reg["id"])
        tex = sorted(i for i in sub if i in tex_ids and geo.get(i, {}).get("w", 0) > 0)
        if not tex:
            continue                                        # 글자만 접히는 영역 — S1 · refine 글자 길 몫
        if reg.get("visibility") in ("collapsed", "hidden") and not (drawn.get(reg["id"]) or {}).get("drawn_in_concept"):
            out["roots"].append({"widget": reg["id"], "skipped": "the concept does not draw it"})
            continue
        targets.append((reg, sub, tex))
    sp_off = dg._without(spec, off_all)
    out["images"] = {k: backdrop.compose(sp_off, boxes, textures, canvas, bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", WHITE))}
    if render_off is not None:
        out["images"]["black"] = render_off
    texts = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        g = geo.get(w["id"])
        if w.get("type") in backdrop.TEXT_TYPES and w["id"] not in off_all and g and g["w"] > 0 and g["h"] > 0:
            texts |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + _glow(w))
    for reg, sub, tex in targets:
        box_m = np.zeros((H, W), bool)
        for i in tex:
            box_m |= dg._box_mask((H, W), _gbox(geo[i]))
        zone = (territory.claim(spec, ca, reg["id"], boxes, omap=omap) | box_m) & (ca > territory.VISIBLE)
        # 정적 판이 그린 것 = 판을 뺀 합성과의 차(옅은 빛까지 — 맨 위 위젯 지도는 알파 0.1 아래를 못 본다)
        sp = dg._without(spec, sub)
        sp_np = dg._without(sp, {w["id"] for w in sp["widgets"] if w["id"].startswith(territory.PLATE_PREFIX)})
        rec = {"widget": reg["id"], "why": territory.collapsible(reg), "zone_px": int(zone.sum()), "plate_px": 0, "local_max": {}}
        worst = np.zeros((H, W), np.float32)
        m = zone.astype(np.float32)
        cnt = np.maximum(cv2.blur(m, (3, 3)), 1e-6)
        any_d = np.zeros((H, W), bool)
        for nm, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", WHITE)):
            img = backdrop.compose(sp, boxes, textures, canvas, bg)[0]
            base = backdrop.compose(sp_np, boxes, textures, canvas, bg)[0]
            plate = np.abs(img - base).max(axis=2) > 0.5
            if nm == "black" and render_off is not None:     # 엔진(접히는 영역 모두 끔) — 판이 그린 자리만, 보이는 엔진 글자 자리는 합성 그대로
                img = np.where((plate & ~texts)[..., None], np.asarray(render_off, float), img)
            de = dg.delta_e(img, base, where=plate & zone)
            any_d |= plate & zone
            loc = np.where(zone, cv2.blur(de * m, (3, 3)) / cnt, 0.0)
            rec["local_max"][nm] = round(float(loc.max()), 2)
            worst = np.maximum(worst, loc)
        rec["plate_px"] = int(any_d.sum())
        if not any_d.any():
            out["roots"].append(rec)
            continue
        flag = worst > T
        rec["over_px"] = int(flag.sum())
        bl = _blobs(flag, worst, min_area)
        rec["blobs"] = len(bl)
        out["roots"].append(rec)
        for b in bl:
            out["findings"].append({"stage": "state", "code": "E8", "check": "hidden_halo", "box": b["box"], "area": b["area"], "max_de": b["max_de"],
                                    "mean_de": b["mean_de"], "widgets": [reg["id"]], "renderer": out["renderer"], "fixable": False,
                                    "cause": f"hidden halo — with '{reg['id']}' collapsed ({rec['why']}) its glow / overhang stays in the static plate"})
    return out


HALO_DE = 2.0              # 접힌 위젯 둘레에 남은 빛 — 3 × 3 국소 ΔE00(검정 · 회색 · 흰 중 최대)


def _other_digit(ch: str) -> str:
    return str((int(ch) + 5) % 10) if ch.isdigit() else ch


def value_overrides(spec: dict) -> dict:
    """S4 — 값이 바뀌는 글자(text.source dynamic + sample)의 같은 형식 다른 값(숫자마다 + 5 mod 10 — '4.2' → '9.7' · '2/4' → '7/9' · '3' → '8', 숫자 밖 글자는
    그대로). 시작 때 숨는 글자는 뺀다(S1 몫). → {위젯: {"text": 값}}."""
    hidden: set[str] = set()
    for r in dg._hidden_roots(spec):
        hidden |= dg._subtree(spec, r)
    out = {}
    for w in spec.get("widgets", []):
        t = w.get("text") if isinstance(w.get("text"), dict) else {}
        if w.get("type") in backdrop.TEXT_TYPES and t.get("source") == "dynamic" and t.get("sample") not in (None, "") and w["id"] not in hidden:
            v = "".join(_other_digit(c) for c in str(t["sample"]))
            if v != str(t["sample"]):
                out[w["id"]] = {"text": v}
    return out


def thin(m) -> np.ndarray:
    """Zhang-Suen 골격(8-연결 한 줄) — 가는 선 길이 재기(S4 text_contour). OpenCV ximgproc · scikit-image 가 없어 numpy 로."""
    img = np.pad(np.asarray(m, bool).astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9, c = img[1:-1, :-2], img[:-2, :-2], img[1:-1, 1:-1]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            A = sum(((nb[i] == 0) & (nb[i + 1] == 1)).astype(np.uint8) for i in range(8))
            m1, m2 = (p2 * p4 * p6, p4 * p6 * p8) if step == 0 else (p2 * p4 * p8, p2 * p6 * p8)
            rem = (c == 1) & (B >= 2) & (B <= 6) & (A == 1) & (m1 == 0) & (m2 == 0)
            if rem.any():
                img[1:-1, 1:-1][rem] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def contour_blobs(flag, de, min_len: int, max_thick: float, link: int = 0) -> list[dict]:
    """S4 가는 선 — flag(설명 안 되는 픽셀) 8-연결 덩어리 중 골격 길이 ≥ min_len · 두께(넓이 ÷ 길이) ≤ max_thick → [{mask, box, area, length, thick, max_de}].
    link > 0 이면 link px 틈은 잇고 잰다(덩어리 = 넓힌 것의 8-연결, 길이 = 넓힌 덩어리 골격, 두께 = 원래 픽셀 ÷ 길이, 원래 픽셀이 넓힌 덩어리의
    CONTOUR_LINK_DENSITY 아래면 흩어진 잡티라 뺌) — 1 px 끊긴 윤곽 조각이 따로 재져 골격 24 px 로 문턱 아래였다 [실측 R20261119_190059 '4']."""
    import cv2
    out = []
    f8 = np.asarray(flag, np.uint8)
    grown = cv2.dilate(f8, np.ones((2 * link + 1, 2 * link + 1), np.uint8)) if link > 0 else f8
    n, lab, st, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    for i in range(1, n):
        x, y, w, h, area_g = (int(v) for v in st[i])
        if max(w, h) < min_len // 2:
            continue
        sub_g = lab[y:y + h, x:x + w] == i
        sub = sub_g & (f8[y:y + h, x:x + w] > 0)
        area = int(sub.sum())
        if area < min_len // 2:
            continue
        if link > 0 and area < CONTOUR_LINK_DENSITY * area_g:
            continue
        L = int(thin(sub_g).sum()) if link > 0 else int(thin(sub).sum())
        if L < min_len or area / max(1, L) > max_thick:
            continue
        m = np.zeros(flag.shape, bool)
        m[y:y + h, x:x + w] = sub
        out.append({"mask": m, "box": [x, y, w, h], "area": area, "length": L, "thick": round(area / max(1, L), 2),
                    "max_de": round(float(np.asarray(de)[m].max()), 1), "mean_de": round(float(np.asarray(de)[m].mean()), 1)})
    return out


def texture_groups(spec: dict, textures: dict) -> list[dict]:
    """S4 숨는 묶음(1b 후속 L 다음 — 글자 지우기 마감) — 시작 때 숨는 위젯 중 자기 · 자손이 텍스처를 그리는(브러시 에셋 — draw_as none 아님 · 텍스처 있음)
    것은 글자와 그 밑 텍스처가 같이 숨는다(배너 BurstBanner — S1 은 숨은 상태만 보고 F1 은 '글자만 숨는' 경우라 아무도 배너가 뜬 상태의 글자 밑을 안 봤다).
    → [{"root", "texts": 그 아래 글자 id 집합}] — 글자만 숨는 것('오의 불가')은 빠짐(S1 · F1 그대로)."""
    out = []
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    for r in dg._hidden_roots(spec):
        sub = dg._subtree(spec, r)
        texts = {i for i in sub if widgets.get(i, {}).get("type") in backdrop.TEXT_TYPES}
        draws = False
        for i in sub:
            for k, b in ((widgets.get(i) or {}).get("style") or {}).items():
                if isinstance(b, dict) and b.get("asset") and b.get("draw_as", "image") != "none" and b["asset"] in textures:
                    draws = True
        if texts and draws:
            out.append({"root": r, "texts": texts})
    return out


TONE_MAX = 40.0             # S4 (마) 판 색조 맞춤 채널당 상한(refine.PLATE_TONE_MAX 와 같음)


def _tone_matched(plate, img, ring, box) -> np.ndarray:
    """S4 (마) — 글자 없는 판을 이 자리 둘레 고리(ring — 상자 box 좌표)에서 그림(img)에 색조 맞춘 사본(전체 크기, 상자 안만 바꿈 — 채널마다 평면 a + bx + cy,
    ± TONE_MAX). 판 그대로를 설명으로 쓰면 텍스처가 둘레와 색조가 다른 판 픽셀을 글자 자리에 붙인 얼룩(글자 모양 어두운 자국)까지 '판과 같다'로 설명했다
    [실측 R20261119_190059 배너 '체인 버스트' · '3' — 사용자 눈, 판 그대로 설명이면 3 × 3 최대 1.79]. 띠 · 테두리 위 글자(판이 그 구조를 그림 — (마)의 이유)는
    둘레도 판과 같은 색조라 맞춤이 거의 0."""
    x0, y0, x1, y1 = box
    P = np.asarray(plate, np.float32)
    sub_p, sub_i = P[y0:y1, x0:x1], np.asarray(img, np.float32)[y0:y1, x0:x1]
    if int(ring.sum()) < 20:
        return P
    yy, xx = np.nonzero(ring)
    h, w = ring.shape
    A = np.stack([np.ones(len(xx)), xx / max(1.0, w), yy / max(1.0, h)], axis=1)
    coef, *_ = np.linalg.lstsq(A, (sub_i - sub_p)[ring], rcond=None)
    gy, gx = np.mgrid[0:h, 0:w]
    corr = np.clip(coef[0][None, None] + coef[1][None, None] * (gx / max(1.0, w))[..., None] + coef[2][None, None] * (gy / max(1.0, h))[..., None],
                   -TONE_MAX, TONE_MAX)
    out = P.copy()
    out[y0:y1, x0:x1] = np.clip(sub_p + corr, 0, 255)
    return out


def plate_line(m, img, plate_tm, ring, box, ds, T: float) -> dict:
    """V2 — 선 모양 덩어리 m(상자 box 좌표)이 글자 없는 판에도 있는 선인가. img · plate_tm = 같은 바탕의 그림 · 색조 맞춘 판(전체 크기), ring = 둘레 고리(상자 좌표),
    ds = 그림 ↔ 색조 맞춘 판 ±2 px 이동 최소 ΔE00(상자 좌표 — (마) 설명). → {"in_plate", "closer", "plate_contrast"}."""
    import cv2
    from core import color
    x0, y0, x1, y1 = box
    m = np.asarray(m, bool)
    if not m.any() or plate_tm is None or int(ring.sum()) < 10:
        return {"in_plate": None}
    P = np.asarray(plate_tm, np.float32)[y0:y1, x0:x1]
    I = np.asarray(img, np.float32)[y0:y1, x0:x1]
    bgP = np.median(P[ring], axis=0)
    lab_bg = color.srgb_to_lab(np.broadcast_to(bgP, I.shape).astype(np.float32))
    d_b = color.delta_e00(color.srgb_to_lab(I), lab_bg)
    closer = float(np.mean(np.asarray(ds)[m] < d_b[m] - LINE_PLATE_MARGIN))
    dP = color.delta_e00(color.srgb_to_lab(P), lab_bg).astype(np.float32)
    dP = cv2.dilate(dP, np.ones((2 * dg.SHIFT_TOL + 1, 2 * dg.SHIFT_TOL + 1), np.uint8))      # ±2 px 이동 중 가장 뚜렷한 판 픽셀
    pc = float(np.median(dP[m]))
    return {"in_plate": bool(closer >= LINE_PLATE_FRAC and pc > T), "closer": round(closer, 2), "plate_contrast": round(pc, 1)}


def _shift_max_l(img, box, r: int = 2) -> np.ndarray:
    """상자 안 픽셀마다 ±r px 옮긴 img 의 L* 최대(판에도 있는 구조물 — 다시 그린 판의 몇 px 어긋남을 덮음)."""
    from core import color
    x0, y0, x1, y1 = box
    H, W = np.shape(img)[:2]
    L = color.srgb_to_lab(np.asarray(img, np.float32)[max(0, y0 - r):min(H, y1 + r), max(0, x0 - r):min(W, x1 + r)])[..., 0]
    ox, oy = x0 - max(0, x0 - r), y0 - max(0, y0 - r)
    Lp = np.pad(L, ((r, r), (r, r)), mode="edge")
    best = np.full((y1 - y0, x1 - x0), -1e9, np.float32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            best = np.maximum(best, Lp[r + oy + dy:r + oy + dy + (y1 - y0), r + ox + dx:r + ox + dx + (x1 - x0)])
    return best


def text_trace(spec: dict, boxes: list[dict], canvas, concept_rgb, concept_a, plate, gm: dict, s: dict, images: dict, renderer: str = "composite",
               render_values=None, render_notext=None, groups: list | None = None) -> dict:
    """S4 — images = 글자 없는 상태 그림 {"black", "gray", "white"}(게임 시작 상태 — 엔진이면 black 은 엔진 글자 빈 값 렌더), plate = 글자 없는 판 (곧은 색, 알파)
    또는 None, gm = diagnose.text_glyph_masks(컨셉 글자 획). render_values(엔진 — 값 글자를 _other_value 로) · render_notext 가 둘 다 있으면 값 바뀜 검사도.
    groups = S4 숨는 묶음(texture_groups — 텍스처째 숨는 위젯) [{"root", "texts", "images": 그 위젯만 켠 글자 없는 상태 {black, gray, white}, "render": 엔진 또는 None}]
    — 그 글자들은 그 상태 그림에서 같은 판정(결함 · 기록에 "state": root).
    판정 둘: text_trace(3 × 3 창 평균 > text_trace_de · 덩어리 ≥ text_trace_min_area) · text_contour(가는 선 — 픽셀 차 > text_contour_de 가 골격 길이 ≥
    text_contour_len 으로 이어짐, 두께 ≤ CONTOUR_THICK).
    → {"texts": [글자마다 기록], "findings": [결함], "renderer"}."""
    import cv2
    from core import color
    W, H = int(canvas[0]), int(canvas[1])
    geo = {b["id"]: b for b in boxes}
    widgets = {w["id"]: w for w in spec.get("widgets", [])}
    hidden: set[str] = set()
    for r in dg._hidden_roots(spec):
        hidden |= dg._subtree(spec, r)
    group_of = {t: g["root"] for g in groups or [] for t in g["texts"]}
    T, min_area = float(s.get("text_trace_de", 5.0)), int(s.get("text_trace_min_area", 24))
    cde, clen = float(s.get("text_contour_de", CONTOUR_DE)), int(s.get("text_contour_len", CONTOUR_LEN))
    clink = int(s.get("text_contour_link", CONTOUR_LINK))
    out = {"renderer": renderer, "texts": [], "findings": []}
    ca = np.asarray(concept_a, np.float32)[..., None]
    cblack = np.asarray(concept_rgb, np.float32) * ca
    pblack = None
    if plate is not None:
        pc, pa = np.asarray(plate[0], np.float32), np.asarray(plate[1], np.float32)[..., None]
        pblack = pc * pa
    bgs = {"black": (0, 0, 0), "gray": backdrop.GRAY, "white": WHITE}
    excl = np.zeros((H, W), bool)
    for w in spec.get("widgets", []):
        g = geo.get(w["id"])
        if g and g["w"] > 0 and g.get("visible", True) and w.get("type") == "Image" and (w.get("binding") or {}).get("kind") == "image":
            excl |= dg._box_mask((H, W), _gbox(g), 2)                              # 런타임 그림(정답 없음)
    zones, cores, glows = {}, {}, {}
    U = np.zeros((H, W), bool)
    F = np.zeros((H, W), bool)
    for wid, v in gm.items():
        w, g = widgets.get(wid), geo.get(wid)
        if w is None or g is None or (wid in hidden and wid not in group_of) or g["w"] <= 0 or g["h"] <= 0:
            continue
        core, strokes = v["concept"], v["concept"] | v["concept_cand"]
        st_ = {"state": group_of[wid]} if wid in group_of else {}
        if not strokes.any():
            out["texts"].append({"widget": wid, "skipped": "no concept glyph strokes", **st_})
            continue
        gmz = dg.glow_measure(cblack, pblack, core, max_d=TEXT_TAIL_MAX) if core.any() else None
        tail = int(gmz["size"]) if gmz and gmz.get("size") else 0
        gl = _glow(w)
        zone = dg._dilate(strokes, tail + TEXT_ZONE_PAD) & dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + max(gl, float(tail))) & ~excl
        foot = dg._dilate(strokes, TEXT_CORE_PAD)
        if tail and pblack is not None:
            reach = dg._dilate(core, tail + TEXT_ZONE_PAD)
            bb = dg._bbox(reach)
            if bb:
                x0, y0, x1, y1 = bb[0], bb[1], bb[0] + bb[2], bb[1] + bb[3]
                lc = color.srgb_to_lab(cblack[y0:y1, x0:x1])[..., 0]
                glow_px = np.zeros((H, W), bool)
                glow_px[y0:y1, x0:x1] = (lc - _shift_max_l(pblack, (x0, y0, x1, y1))) > TEXT_GLOW_DL
                foot |= reach & glow_px
        elif tail:
            foot |= dg._dilate(core, tail + TEXT_ZONE_PAD)
        zones[wid], cores[wid], glows[wid] = zone, strokes, max(gl, float(tail))
        U |= zone
        F |= foot & zone
        out["texts"].append({"widget": wid, "zone_px": int(zone.sum()), "glow_tail": tail, **st_})
    if not U.any():
        return out
    concepts = {k: cblack + np.asarray(bg, np.float32) * (1 - ca) for k, bg in bgs.items()}
    plates = {k: pblack + np.asarray(bg, np.float32) * (1 - pa) for k, bg in bgs.items()} if pblack is not None else None
    lift = float(s.get("text_trace_lift") or 0)
    if lift > 1:
        # 밝힌 검정(lift) — 어두운 판(L* ≈ 9)의 흔적은 ΔE00 이 작게 재진다(SL 가중 — 어두운 쪽 둔감). 사람은 텍스처를 밝혀 · 확대해 본다
        concepts["lift"] = np.clip(concepts["black"] * lift, 0, 255)
        if plates is not None:
            plates["lift"] = np.clip(plates["black"] * lift, 0, 255)
    rec_of = {r["widget"]: r for r in out["texts"]}

    def judge(imgs: dict, region, check: str, rend: str, state: str | None = None, ring_excl=None):
        n, lab = cv2.connectedComponents(region.astype(np.uint8), connectivity=8)
        for ci in range(1, n):
            comp = lab == ci
            if int(comp.sum()) < min_area:
                continue
            x0, y0, x1, y1 = _crop_box(comp, RING + 3, (H, W))
            z = comp[y0:y1, x0:x1]
            ring = dg._dilate(z, RING) & ~U[y0:y1, x0:x1] & ~excl[y0:y1, x0:x1]
            if ring_excl is not None:
                # 값 바뀜 검사 — 새로 그린 글자 · 빛(다른 값) 자리는 둘레 고리에서 뺀다: 둘레 설명 · 판 색조 맞춤이 그 밝은 글자 쪽으로 끌려 어두운 패널 바탕을 '설명 안 됨'으로
                # 봤다 [실측 R20261120_001224 L-2 — 텍스처는 원본 아트 그대로인데 '9.7' 옆 ChainTimerText 값 흔적 12.9]
                ring &= ~ring_excl[y0:y1, x0:x1]
            if int(ring.sum()) < 20:
                continue
            f = F[y0:y1, x0:x1]
            flag = np.zeros(z.shape, bool)
            best = np.zeros(z.shape, np.float32)
            cflag = np.zeros(z.shape, bool)
            cbest = np.zeros(z.shape, np.float32)
            which, cwhich = {}, {}
            tms, dss = {}, {}                     # V2 — 바탕마다 색조 맞춘 판 · (마) 설명 지도(선 모양 덩어리가 판에도 있는 선인지)
            loc_lift = None
            for k, img in imgs.items():
                ex = None
                if plates is not None:
                    tms[k] = _tone_matched(plates[k], img, ring, (x0, y0, x1, y1))
                    dss[k] = dg._shift_min_de(img, tms[k], (x0, y0, x1, y1), where=z)      # 설명 · 선 판정 모두 자리 z 안만 본다
                    ex = [dss[k]]
                d = explain_diff(img[y0:y1, x0:x1], concepts[k][y0:y1, x0:x1], z, ring, f, extra=ex)
                c = cv2.blur(z.astype(np.float32), (TEXT_LOCAL, TEXT_LOCAL))
                loc = np.where(c >= 0.3, cv2.blur(d * z, (TEXT_LOCAL, TEXT_LOCAL)) / np.maximum(c, 1e-6), 0.0) * z
                if k == "lift":
                    loc_lift = loc
                if k != "lift":
                    # 밝힌 검정(lift)은 기록만(local_max.lift — refine 글자 지우기 고르기가 씀) — 게이트로 쓰면 보호 run 조작 안내도 5 ~ 9 로 부풀었다
                    # [실측 11-19 보정 — 배너 '체인 버스트' 4.5 · 깨끗한 L-2 0.5 · controls_alpha 5 ~ 9]
                    fl = (loc > T) & z
                    which[k] = fl
                    flag |= fl
                    best = np.maximum(best, loc)
                    cf = (d > cde) & z
                    cwhich[k] = cf
                    cflag |= cf
                    cbest = np.maximum(cbest, np.where(z, d, 0.0))
                for wid, zm in zones.items():
                    zz = zm[y0:y1, x0:x1] & z
                    if zz.any():
                        key = "local_max" if check == "text_trace" else "value_local_max"
                        rec_of[wid].setdefault(key, {})[k] = round(max(float(loc[zz].max()), rec_of[wid].get(key, {}).get(k, 0.0)), 2)
            def in_plate(m, ks):
                """V2 — 선 모양 덩어리가 판에도 있는 선인가(플래그된 바탕 중 하나라도 판이 설명하면 판에 있음)."""
                best_r: dict = {"in_plate": None}
                for k in ks:
                    if k == "lift" or k not in tms:
                        continue
                    r_ = plate_line(m, imgs[k], tms[k], ring, (x0, y0, x1, y1), dss[k], T)
                    if r_.get("in_plate") or best_r.get("in_plate") is None:
                        best_r = {**r_, "backdrop": k}
                    if r_.get("in_plate"):
                        break
                return best_r
            line_err = str(s.get("text_line_plate") or "record") == "error"
            # 가는 선(text_contour) — 골격 길이 기록은 짧은 것까지(보정용), 결함은 clen 이상만
            ckey = "contour_len" if check == "text_trace" else "value_contour_len"
            for b in contour_blobs(cflag, cbest, max(12, clen // 3), CONTOUR_THICK, link=clink):
                m = b["mask"]
                ov = sorted(((int((zm[y0:y1, x0:x1] & m).sum()), wid) for wid, zm in zones.items()), reverse=True)
                ws = [wid for c_, wid in ov if c_ > 0]
                for wid in ws[:1]:
                    rec_of[wid][ckey] = max(int(rec_of[wid].get(ckey, 0)), b["length"])
                if b["length"] < clen:
                    continue
                bx = b["box"]
                bgs_ = [k for k, fl in cwhich.items() if (fl & m).any()]
                if min(bx[2], bx[3]) <= CONTOUR_LINE_SHORT and max(bx[2], bx[3]) >= CONTOUR_LINE_RATIO * max(1, min(bx[2], bx[3])):
                    # 곧은 가로 · 세로 선(막대 윗선 — 다시 그린 판과 1 px 어긋남)은 글자 윤곽이 아니라 구조선 — 기록만(text_trace 의 line_like 와 같은 뜻)
                    # [실측 11-19 보정 — 파티 003127 HP 숫자 아래 40 × 2 · 45 × 5]. V2 — 그 선이 판에도 있을 때만(text_line_plate: error 면 판에 없는 선은 결함)
                    ip = in_plate(m, bgs_)
                    out.setdefault("line_like", []).append({"check": "text_contour", "box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "max_de": b["max_de"],
                                                            "length": b["length"], "widgets": ws[:1], **ip, **({"state": state} if state else {})})
                    if not (line_err and ip.get("in_plate") is False):
                        continue
                cname = "text_contour" if check == "text_trace" else "text_value_contour"
                out["findings"].append({"stage": "state", "code": "E8", "check": cname, "box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "area": b["area"],
                                        "length": b["length"], "thick": b["thick"], "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": ws,
                                        "backgrounds": bgs_, "renderer": rend, "fixable": False, **({"state": state} if state else {}),
                                        "cause": f"text contour — a thin line ({b['length']} px long) under '{ws[0] if ws else '?'}' the surroundings do not "
                                                 f"explain ({', '.join(bgs_)} backdrop{', ' + state + ' shown' if state else ''})"})
            for b in _blobs(flag, best, min_area):
                m = b["mask"]
                ov = sorted(((int((zm[y0:y1, x0:x1] & m).sum()), wid) for wid, zm in zones.items()), reverse=True)
                ws = [wid for c_, wid in ov if c_ > 0]
                bx = b["box"]
                bgs_ = [k for k, fl in which.items() if (fl & m).any()]
                if min(b["box"][2], b["box"][3]) <= TEXT_LINE_MAX:
                    # 짧은 변 ≤ TEXT_LINE_MAX px 인 선 모양은 글자 흔적이 아니라 구조선(막대 윗선 — 다시 그린 판과 1 px 어긋남) [실측 R20261119_003127 파티 HP 숫자 아래 23 × 2].
                    # V2 — 그 선이 판에도 있을 때만 구조선(text_line_plate: error 면 판에 없는 선은 결함 — 위 23 × 2 는 사용자 눈으로 막대 윗선 위 빛 자국이었다)
                    ip = in_plate(m, bgs_)
                    out.setdefault("line_like", []).append({"check": check, "box": [b["box"][0] + x0, b["box"][1] + y0, b["box"][2], b["box"][3]], "max_de": b["max_de"],
                                                            "widgets": ws[:1], **ip, **({"state": state} if state else {})})
                    if not (line_err and ip.get("in_plate") is False):
                        continue
                for wid in ws[:1]:
                    rec_of[wid]["blobs"] = rec_of[wid].get("blobs", 0) + 1
                what = "with every text empty" if check == "text_trace" else "with the value texts at another value"
                if state:
                    what += f" and '{state}' shown"
                line_ = min(b["box"][2], b["box"][3]) <= TEXT_LINE_MAX
                out["findings"].append({"stage": "state", "code": "E8", "check": check, "box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "area": b["area"],
                                        "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": ws, "backgrounds": bgs_, "renderer": rend, "fixable": False,
                                        **({"state": state} if state else {}), **({"line_not_in_plate": True} if line_ else {}),
                                        "cause": f"text trace — {what}, the textures under '{ws[0] if ws else '?'}' still show the concept glyph / glow "
                                                 f"({', '.join(bgs_)} backdrop{'; a line the text-free plate does not have' if line_ else ''})"})
            # V3 — 밝힌 검정(lift): 둘레 고리 검정 합성 L*(어두운 판 자리만 판정 후보) · 밝힘 국소 > LIFT_RECORD_DE 덩어리 기록(보정). text_lift_mode: error 면
            # 어두운 자리(ring_l < LIFT_DARK_L)의 밝힘 국소 > text_lift_de 덩어리를 결함(check text_lift)
            if loc_lift is not None and check == "text_trace" and imgs.get("black") is not None:
                lab_r = color.srgb_to_lab(np.asarray(imgs["black"], np.float32)[y0:y1, x0:x1][ring])
                ring_l = float(np.median(lab_r[:, 0])) if len(lab_r) else 100.0
                for wid, zm in zones.items():
                    if (zm[y0:y1, x0:x1] & z).any():
                        rec_of[wid]["ring_l"] = round(min(ring_l, float(rec_of[wid].get("ring_l", 1e9))), 1)
                lift_err = str(s.get("text_lift_mode") or "record") == "error"
                lde = float(s.get("text_lift_de") or 1e9)
                for b in _blobs((loc_lift > min(LIFT_RECORD_DE, lde)) & z, loc_lift, min_area):
                    m = b["mask"]
                    ov = sorted(((int((zm[y0:y1, x0:x1] & m).sum()), wid) for wid, zm in zones.items()), reverse=True)
                    ws = [wid for c_, wid in ov if c_ > 0]
                    bx = b["box"]
                    out.setdefault("lift_like", []).append({"box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "area": b["area"], "max_de": b["max_de"],
                                                            "mean_de": b["mean_de"], "ring_l": round(ring_l, 1), "widgets": ws[:1],
                                                            **({"state": state} if state else {})})
                    if lift_err and ring_l < LIFT_DARK_L and b["max_de"] > lde:
                        mm = m & (loc_lift > lde)
                        if int(mm.sum()) >= min_area:
                            bb2 = dg._bbox(mm)
                            out["findings"].append({"stage": "state", "code": "E8", "check": "text_lift", "box": [bb2[0] + x0, bb2[1] + y0, bb2[2], bb2[3]],
                                                    "area": int(mm.sum()), "max_de": b["max_de"], "mean_de": round(float(loc_lift[mm].mean()), 1), "widgets": ws,
                                                    "backgrounds": ["lift"], "renderer": rend, "fixable": False, "ring_l": round(ring_l, 1),
                                                    **({"state": state} if state else {}),
                                                    "cause": f"text trace (lifted) — on a dark plate (ring L* {ring_l:.0f}) the texture under "
                                                             f"'{ws[0] if ws else '?'}' still shows a low-contrast glyph trace when brightened × {lift:g}"})
    imgs = dict(images)
    if render_notext is not None:
        imgs["black"] = render_notext

    def lifted(d_: dict) -> dict:
        return {**d_, "lift": np.clip(np.asarray(d_["black"], np.float32) * lift, 0, 255)} if lift > 1 and d_.get("black") is not None else d_
    imgs = lifted(imgs)
    main = np.zeros((H, W), bool)
    for wid, zm in zones.items():
        if wid not in group_of:
            main |= zm
    if main.any():
        judge(imgs, main, "text_trace", renderer)
    # S4 숨는 묶음 — 그 위젯만 켠 글자 없는 상태(엔진이면 black 은 엔진)에서 그 아래 글자 자리
    for g in groups or []:
        reg = np.zeros((H, W), bool)
        for wid in g["texts"]:
            if wid in zones:
                reg |= zones[wid]
        if not reg.any():
            continue
        gi = dict(g["images"])
        if g.get("render") is not None:
            gi["black"] = g["render"]
        gi = lifted(gi)
        judge(gi, reg, "text_trace", "engine" if g.get("render") is not None else "composite", state=g["root"])
        out.setdefault("groups", []).append({"root": g["root"], "texts": sorted(g["texts"]), "renderer": "engine" if g.get("render") is not None else "composite"})
    if render_values is not None and render_notext is not None:
        vals = value_overrides(spec)
        new = dg._dilate(dg.maxabs(render_values, render_notext) > dg.INK_FLOOR, 1)
        newz = np.zeros((H, W), bool)
        for wid in vals:
            g = geo.get(wid)
            if g and wid in zones:
                newz |= dg._dilate(new & dg._box_mask((H, W), _gbox(g), glows[wid] + 4), int(np.ceil(glows[wid])) + 2)
        region = np.zeros((H, W), bool)
        for wid in vals:
            if wid in zones:
                region |= zones[wid]
        region &= ~newz
        if region.any():
            judge({"black": render_values}, region, "text_value_trace", "engine", ring_excl=newz | dg._dilate(new, 2))   # 값 렌더의 모든 글자(고정 글자 포함)
        out["values"] = {k: v["text"] for k, v in vals.items()}
    return out


def _track_hole_canvas(ref_png, proc: dict, shape) -> np.ndarray | None:
    """concept_fill 트랙 hole(끝 장식 안쪽 호까지 — 프레임 선 · 끝 캡 뺌)을 캔버스 마스크로."""
    from gen import concept_fill
    try:
        hole, _ = concept_fill.track_hole(ref_png, proc)
    except (concept_fill.ConceptFillError, KeyError, ValueError):
        return None
    if proc.get("flip"):
        hole = hole[:, ::-1]
    fx, fy, fw, fh = (int(v) for v in proc["frame_box"])
    m = np.zeros(shape, bool)
    H, W = shape
    sx1, sy1 = min(W, fx + fw), min(H, fy + fh)
    m[fy:sy1, fx:sx1] = hole[:sy1 - fy, :sx1 - fx]
    return m


def track_box(spec: dict, w: dict, g: dict) -> tuple[list[float], str]:
    """게이지 트랙 상자(캔버스) — 채움이 concept_fill 이면 잰 트랙(frame_box + track, 뒤집기 반영), 아니면 막대 상자."""
    st = w.get("style") or {}
    fill = st.get("fill") if isinstance(st.get("fill"), dict) else {}
    proc = next((a.get("procedural") or {} for a in spec.get("assets", []) if a.get("asset_id") == fill.get("asset")), {})
    if proc.get("shape") == "concept_fill" and proc.get("frame_box") and proc.get("track"):
        fx, fy, fw, _ = (float(v) for v in proc["frame_box"])
        l_, t_, r_, b_ = (int(v) for v in proc["track"])
        x0 = fx + (fw - 1 - r_) if proc.get("flip") else fx + l_
        return [x0, fy + t_, float(r_ - l_ + 1), float(b_ - t_ + 1)], "concept_fill track"
    return _gbox(g), "gauge box"


def _with_percent(spec: dict, wid: str, p: float | None, no_fill: bool = False) -> dict:
    s2 = copy.deepcopy(spec)
    for w in s2.get("widgets", []):
        if w["id"] == wid:
            st = w.setdefault("style", {})
            if p is not None:
                st["percent"] = float(p)
            if no_fill:
                st["fill"] = {"draw_as": "none"}
    return s2


RADIAL_STATES = (0.0, 0.15, 0.4, 0.65, 0.9, 1.0)   # 원형 진행(고리) — 0 · 중간 넷(닦는 끝이 네 사분면의 빗각 306 · 216 · 126 · 36°) · 가득. 25 · 50 · 75 % 는
# 끝이 90° 배수에 놓여 중심이 8 px 어긋나도 안 보였다(시험)
RADIAL_EDGE_PX = 2.5                            # 닦는 끝에서 이만큼(호 길이 px) 안은 안티앨리어싱 — arc 판정에서 뺀다
RADIAL_ZONE_ALPHA = 0.1                         # 고리 자리 = 텍스처 알파가 이보다 큰 픽셀


def radial_targets(spec_state: dict, boxes: list[dict]) -> list[tuple[dict, dict, dict, dict]]:
    """원형 진행(고리) 대상 — 보이는 Image + brush.wipe → [(위젯, geometry, style, brush)]."""
    geo = {b["id"]: b for b in boxes}
    out = []
    for w in spec_state.get("widgets", []):
        st, g = w.get("style") or {}, geo.get(w["id"])
        brush = st.get("brush") if isinstance(st.get("brush"), dict) else {}
        if w.get("type") == "Image" and brush.get("wipe") and g and g.get("visible", True) and g["w"] > 0 and g["h"] > 0:
            out.append((w, g, st, brush))
    return out


def gauge_targets(spec_state: dict, boxes: list[dict]) -> list[tuple[dict, dict, dict, dict, str, tuple]]:
    """S2 대상 — 보이는 ProgressBar(채움 있음) → [(위젯, geometry, style, 채움 브러시, 채움 방향, 그려 볼 비율 — 가로가 아니면 빔)]."""
    from gen import silhouette
    geo = {b["id"]: b for b in boxes}
    shaped = silhouette.bars(spec_state)
    out = []
    for w in spec_state.get("widgets", []):
        if w.get("type") != "ProgressBar":
            continue
        g, st = geo.get(w["id"]), w.get("style") or {}
        fill = st.get("fill") if isinstance(st.get("fill"), dict) else None
        if not g or not g.get("visible", True) or g["w"] <= 0 or g["h"] <= 0 or not fill or fill.get("draw_as", "image") == "none":
            continue
        kind = st.get("bar_fill_type", "left_to_right")
        percents = (BAR_STATES if w["id"] in shaped else GAUGE_STATES) if kind in ("left_to_right", "right_to_left") else ()
        out.append((w, g, st, fill, kind, percents))
    return out


def percent_name(wid: str, p: float) -> str:
    """비율 하나의 상태 렌더 이름(= 출력 폴더)."""
    return f"state_{wid}_{int(round(float(p) * 100)):03d}"


def state_requests(spec: dict, spec_state: dict, states: list[dict], boxes: list[dict], textures: dict, checks: bool = True, extra: dict | None = None) -> dict[str, dict]:
    """진단이 쓸 상태 렌더 전부 — {이름: overrides}. 진단은 이 목록만 보고 렌더를 쓰고(단일 원천), verify 는 이 목록을 한 묶음으로 미리 그린다(Phase 2 — 호출마다
    글꼴 준비 2 초를 기다리던 것을 한 번으로). 상태 하나의 렌더는 다른 렌더 결과에 기대지 않는다. checks False = 컨셉 상태만(state_checks off)."""
    ov_state = {h["widget"]: {"visible": bool(h["drawn_in_concept"])} for h in states}
    out: dict[str, dict] = {"state": ov_state}                                     # 컨셉 상태(숨은 위젯을 컨셉처럼 켜고 끔)
    if not checks:
        return out
    roots = dg._hidden_roots(spec)
    ov0 = {r: {"visible": False} for r in roots}
    if roots:
        out["state_off"] = ov0                                                      # S1 — 게임 기본 상태
    toggles = [r["id"] for r in territory.toggle_regions(spec)]
    if toggles:
        out["state_toggles_off"] = {r: {"visible": False} for r in sorted(set(roots) | set(toggles))}   # S1 보강 — 접히는 영역 모두 끔
    pct = [(w["id"], p) for w, _g, _st, _fill, _kind, percents in gauge_targets(spec_state, boxes) for p in percents]          # S2
    pct += [(w["id"], p) for w, _g, _st, brush in radial_targets(spec_state, boxes) if brush.get("asset") in textures for p in RADIAL_STATES]
    for wid, p in pct:
        out[percent_name(wid, p)] = {**ov_state, wid: {**ov_state.get(wid, {}), "percent": float(p)}}
    for t in button_targets(spec_state, boxes, textures):                          # 버튼 상태(Phase 3-2) — 기본은 컨셉 상태 렌더("state")와 같다
        for b in button.DERIVED:
            out[button_name(t["id"], b)] = {**ov_state, t["key"]: {**ov_state.get(t["key"], {}), **button.OVERRIDES[b]}}
    if extra:                                                                       # 바탕 위 표시 · 긴 글자(Phase 3-3)
        from gen import screen_check
        out.update(screen_check.requests(extra, ov_state))
    off_ids: set[str] = set()
    for r in roots:
        off_ids |= dg._subtree(spec, r)
    texts = [w["id"] for w in spec.get("widgets", []) if w.get("type") in backdrop.TEXT_TYPES]
    out["state_notext"] = {**ov0, **{t: {"text": ""} for t in texts if t not in off_ids}}                                       # S4 — 모든 글자 빈 값
    vals = value_overrides(spec)
    if vals:
        out["state_values"] = {**ov0, **vals}                                       # S4 — 값 글자를 다른 값으로
    for g in texture_groups(spec, textures):                                        # S4 숨는 묶음 — 그 위젯만 켠 글자 없는 상태
        off_g: set[str] = set()
        for r in roots:
            if r != g["root"]:
                off_g |= dg._subtree(spec, r)
        out[f"state_notext_{g['root']}"] = {**{r: {"visible": False} for r in roots if r != g["root"]}, g["root"]: {"visible": True},
                                            **{t: {"text": ""} for t in texts if t not in off_g}}
    return out


BUTTON_GLYPH_PAD = 3        # 글자 획 둘레 — 이만큼(px)은 안쪽 판정에서 뺀다(안티앨리어싱 · 외곽선 · 눌린 글자 이동)
BUTTON_TEXT_SHIFT = 4       # 글자가 움직인 거리를 찾는 범위(px)
BUTTON_COVER = 0.2          # 7 × 7 창 안 판정 픽셀 비율 하한


def button_name(wid: str, brush: str) -> str:
    """버튼 상태 하나의 렌더 이름(= 출력 폴더)."""
    return f"state_{wid}_{brush}"


def button_targets(spec_state: dict, boxes: list[dict], textures: dict) -> list[dict]:
    """버튼 상태 대상 — 버튼 칸 자신(덮어쓰기 열쇠 '.')과 화면에 놓인 버튼 칸. [{id, key, box, swap(상태 → 합성용 spec · textures), texts}]."""
    geo = {b["id"]: b for b in boxes}
    out = []
    art = button.art_id(spec_state)
    used = button.brush_assets(spec_state) if art else {}
    g = geo.get(art) if art else None
    if g and g.get("visible", True) and g["w"] > 0 and all(a in textures for a in used.values()):
        texts = [_gbox(geo[w["id"]]) for w in spec_state["widgets"] if w.get("type") in backdrop.TEXT_TYPES and geo.get(w["id"], {}).get("visible", True) and w["id"] in geo]
        out.append({"id": art, "key": button.SELF_KEY, "box": _gbox(g), "texts": texts, "offset": (button.of(spec_state) or {}).get("pressed_offset") or [0, 0],
                    "state": lambda b: (cells.with_state(spec_state, b), textures)})
    for w in cells.placed(spec_state):
        g, p = geo.get(w["id"]), cells.picture(str(w.get("class") or ""))
        if p is None or not p["button"] or not g or not g.get("visible", True) or g["w"] <= 0:
            continue
        cls = w["class"]
        out.append({"id": w["id"], "key": w["id"], "box": _gbox(g), "texts": [t for i, t in cells.text_boxes(spec_state, boxes) if i == w["id"]], "offset": None,
                    "state": lambda b, cls=cls: (spec_state, {**textures, cells.key(cls): textures[cells.key(cls, b)]})})
    return out


def _text_shift(a, b, r: int = BUTTON_TEXT_SHIFT) -> tuple[list[int], float]:
    """글자 마스크 a 를 어디로 옮기면 b 와 가장 겹치나 — ([dx, dy], IoU)."""
    best = ([0, 0], -1.0)
    n = int(a.sum()) + int(b.sum())
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            inter = int((np.roll(a, (dy, dx), (0, 1)) & b).sum())
            iou = inter / max(1, n - inter)
            if iou > best[1] + 1e-9 or (abs(iou - best[1]) <= 1e-9 and abs(dx) + abs(dy) < abs(best[0][0]) + abs(best[0][1])):
                best = ([dx, dy], iou)
    return best


def button_states(spec_state: dict, boxes: list[dict], textures: dict, canvas, s: dict, base, render_state=None) -> dict:
    """버튼 상태 검사 — base = 컨셉 상태 렌더(엔진이면 엔진, 아니면 합성), render_state(이름) → 그 상태의 엔진 렌더(못 그리면 예외). 없으면(오프라인) 합성끼리라
    안쪽 판정은 뜻이 없고 '상태끼리 구별'만 본다. → {"buttons", "findings", "images": {버튼: {상태: 그림}}, "gray", "renderer"}."""
    W, H = int(canvas[0]), int(canvas[1])
    T, distinct, readable = float(s["button_de"]), float(s["button_distinct_de"]), float(s["button_text_de"])
    out: dict = {"buttons": [], "findings": [], "images": {}, "gray": {}, "renderer": "composite" if render_state is None else "engine"}
    for t in button_targets(spec_state, boxes, textures):
        rec: dict = {"widget": t["id"], "states": {}}
        box = dg._box_mask((H, W), t["box"])

        def add(check, brush, mask_box, area, cause, max_de=None, mean_de=None):
            out["findings"].append({"stage": "state", "code": "E8", "check": check, "brush": brush, "box": mask_box, "area": int(area), "max_de": max_de, "mean_de": mean_de,
                                    "widgets": [t["id"]], "renderer": out["renderer"], "fixable": False, "cause": cause})
        ibox = [int(round(v)) for v in t["box"]]
        want, imgs = {}, {}
        for b in button.BRUSHES:
            sp, tex = t["state"](b)
            want[b] = backdrop.compose(sp, boxes, tex, canvas, (0, 0, 0))[0]
            if b == button.BASE:
                imgs[b] = np.asarray(base, float)
            elif render_state is None:
                imgs[b] = want[b]
            else:
                try:
                    imgs[b] = render_state(button_name(t["id"], b))
                    if imgs[b] is None:
                        raise ValueError("no picture")
                except Exception as exc:  # noqa: BLE001 — 그 상태를 못 그렸다 = 오류(합성으로 물러나지 않는다)
                    imgs.pop(b, None)
                    rec["states"][b] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
                    add("button_render", b, ibox, box.sum(), f"button - the state '{b}' could not be rendered ({type(exc).__name__}: {str(exc)[:120]})")
        out["images"][t["id"]] = imgs
        out["gray"][t["id"]] = {b: backdrop.compose(*_gray_args(t, b, boxes), canvas, backdrop.GRAY)[0] for b in button.BRUSHES}
        cov = backdrop.compose(*_gray_args(t, button.BASE, boxes), canvas, (0, 0, 0))[1]
        # 글자 획 — 상태마다 '글자 없는 합성과 다른 픽셀'(글자 상자 안). 안쪽 판정은 그 둘레를 빼고, 글자 자체는 읽히는가 · 움직인 거리로 본다
        textz = np.zeros((H, W), bool)
        for tb in t["texts"]:
            textz |= dg._box_mask((H, W), tb, dg.HIDDEN_PAD + BUTTON_TEXT_SHIFT)
        glyph = {b: (dg.maxabs(im, want[b]) > dg.INK_FLOOR) & textz for b, im in imgs.items()} if render_state is not None else {}
        base_g = glyph.get(button.BASE)
        strokes = dg._dilate(base_g, BUTTON_GLYPH_PAD + BUTTON_TEXT_SHIFT) if base_g is not None and base_g.any() else np.zeros((H, W), bool)
        # 획의 속(가장 또렷한 픽셀) — 읽히는가를 재는 자리
        core = (dg.maxabs(imgs[button.BASE], want[button.BASE]) > dg.INK_MIN * 2) & textz if base_g is not None else np.zeros((H, W), bool)
        inside = box & ~(strokes & textz)
        for b, im in imgs.items():
            r = rec["states"].setdefault(b, {})
            de = dg.delta_e(im, want[b], where=inside)
            loc = masked_local(de, inside, BUTTON_COVER)
            fl = (loc > T) & inside
            r.update(inside_max=round(float(loc[inside].max()), 2) if inside.any() else 0.0, inside_px=int(fl.sum()))
            for bl in _blobs(fl, loc, min(int(s["min_area"]), 12)):
                add("button_state", b, bl["box"], bl["area"], f"button - '{b}' does not look like its own picture (wrong brush, shifted or not applied)", bl["max_de"], bl["mean_de"])
            if b != button.BASE:
                loc_o, (ox, oy) = _diff_local(im, imgs[button.BASE], ~dg._dilate(box, 1), 0.0)
                r["outside_max"] = round(float(loc_o.max()), 2)
                fo = loc_o > T
                for bl in _blobs(fo, loc_o, min(int(s["min_area"]), 12)) if fo.any() else ():
                    add("button_outside", b, [bl["box"][0] + ox, bl["box"][1] + oy, bl["box"][2], bl["box"][3]], bl["area"],
                        f"button - '{b}' changes something outside the button", bl["max_de"], bl["mean_de"])
            if core.any():
                sh, iou = _text_shift(core, dg.maxabs(im, want[b]) > dg.INK_FLOOR) if b != "disabled" else ([0, 0], None)
                moved = np.roll(core, (sh[1], sh[0]), (0, 1))
                tde = float(np.median(dg.delta_e(im, want[b], where=moved)[moved]))
                r.update(text_de=round(tde, 1), text_shift=sh, text_iou=None if iou is None else round(iou, 3))
                if tde < readable:
                    add("button_text", b, dg._bbox(moved), moved.sum(), f"button - the label is not readable in '{b}' (ΔE00 {tde:.1f} < {readable:g})")
                expect = [int(round(v)) for v in t["offset"]] if t["offset"] is not None and b.endswith("pressed") else [0, 0]
                if t["offset"] is not None and b != "disabled" and sh != expect:
                    add("button_text_moved", b, dg._bbox(moved), moved.sum(), f"button - the label moved {sh} px in '{b}', the theme says {expect}")
        # 상태끼리 구별 — 버튼 안(글자 둘레 뺌 · 알파 > 0.5)의 평균 차. 두 그림이 같으면 사람은 상태를 못 가른다. 검정 바탕(렌더)과 회색 바탕(합성) 중 큰 쪽 —
        # 검정 위에서는 투명도 차이가 숨는다 [실측 Phase 3-2 — 누름 ↔ 비활성(알파 × 0.5)이 검정 0.98 · 회색 18.55]. 렌더가 그 상태의 그림이 맞는지는 button_state 몫
        solid = inside & (cov > 0.5)
        names = [b for b in button.BRUSHES if b in imgs]
        gray = out["gray"][t["id"]]
        rec["distinct"], rec["distinct_black"] = {}, {}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                mb, mg = (float(dg.delta_e(x[a], x[b], where=solid)[solid].mean()) if solid.any() else 0.0 for x in (imgs, gray))
                m = max(mb, mg)
                rec["distinct"][f"{a} / {b}"] = round(m, 2)
                rec["distinct_black"][f"{a} / {b}"] = round(mb, 2)
                if m < distinct:
                    add("button_same", b, ibox, solid.sum(), f"button - '{a}' and '{b}' look the same (mean ΔE00 {m:.2f} < {distinct:g})")
        out["buttons"].append(rec)
    return out


def _gray_args(t: dict, brush: str, boxes: list[dict]) -> tuple:
    sp, tex = t["state"](brush)
    return sp, boxes, tex


def radial_states(spec_state: dict, boxes: list[dict], textures: dict, canvas, s: dict, base, render_pct=None) -> dict:
    """원형 진행(고리 — Image + brush.wipe, 전투 HUD 동작 11-23) — 비율 RADIAL_STATES 의 엔진 렌더(render_pct — 없으면 합성)를 본다:
      radial_full     100 % 가 컨셉 상태(base)와 같다 — 고리 자리
      radial_zero     0 % 가 '고리를 흔적 값으로만 그린' 텍스처 합성과 같다 — 고리 자리
      radial_arc      중간 비율에서 남아야 할 쪽 = 100 % 렌더, 닦여야 할 쪽 = 0 % 렌더(끝 ± RADIAL_EDGE_PX 뺌) — 각도 · 방향 · 중심 · 흔적
      radial_outside  어느 비율에서도 고리 자리 밖(고리 안 띠 · 글자 · 나머지 화면)이 100 % 렌더 그대로다 — 닦이며 다른 그림을 자르지 않는다
    → gauge_states 와 같은 모양 {"gauges", "findings", "images", "renderer"}."""
    from gen import radial
    W, H = int(canvas[0]), int(canvas[1])
    geo = {b["id"]: b for b in boxes}
    T, min_area = float(s["local_de"]), min(int(s["min_area"]), 12)
    textz = np.zeros((H, W), bool)
    for w in spec_state.get("widgets", []):
        g = geo.get(w["id"])
        if w.get("type") in backdrop.TEXT_TYPES and g and g.get("visible", True) and g["w"] > 0:
            textz |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + _glow(w))
    out = {"gauges": [], "findings": [], "images": {}, "renderer": "composite" if render_pct is None else "engine"}
    for w, g, st, brush in radial_targets(spec_state, boxes):
        wipe = brush["wipe"]
        tex = textures.get(brush.get("asset"))
        rec = {"widget": w["id"], "percent": st.get("percent", 1.0), "fill_type": f"radial {wipe.get('mode', 'clockwise')}", "track_alpha": wipe.get("track_alpha", 0)}
        if tex is None:
            out["gauges"].append({**rec, "skipped": f"texture {brush.get('asset')} is missing"})
            continue
        x, y, bw, bh = (int(round(float(g[k]))) for k in ("x", "y", "w", "h"))
        lay = backdrop._resize(tex, bw, bh)
        zone = np.zeros((H, W), bool)
        cx0, cy0, cx1, cy1 = max(0, x), max(0, y), min(W, x + bw), min(H, y + bh)
        zone[cy0:cy1, cx0:cx1] = (lay[..., 3] > 255 * RADIAL_ZONE_ALPHA)[cy0 - y:cy1 - y, cx0 - x:cx1 - x]
        soft = np.zeros((H, W), bool)                       # 고리 텍스처가 조금이라도 그리는 자리(+ 1 px) — 밖 판정에서 뺀다
        soft[cy0:cy1, cx0:cx1] = (lay[..., 3] > 0)[cy0 - y:cy1 - y, cx0 - x:cx1 - x]
        soft = dg._dilate(soft, 1)
        zone &= ~textz
        imgs, used = {}, {}
        for p in RADIAL_STATES:
            img = None
            if render_pct is not None:
                try:
                    img = render_pct(w["id"], p)
                except Exception as exc:  # noqa: BLE001 — 엔진 렌더 실패는 기록하고 합성으로
                    rec.setdefault("render_errors", []).append(f"{p:g}: {type(exc).__name__}: {exc}"[:160])
            used[p] = "engine" if img is not None else "composite"
            if img is None:
                img = backdrop.compose(_with_percent(spec_state, w["id"], p), boxes, textures, canvas, (0, 0, 0))[0]
            imgs[p] = img
        out["images"][w["id"]] = imgs
        rec["renderer"] = used
        rec["zone_px"] = int(zone.sum())
        isz = brush.get("image_size") or [tex.shape[1], tex.shape[0]]
        c = wipe.get("center") or [isz[0] / 2, isz[1] / 2]
        ctr = [x + float(c[0]) * bw / float(isz[0]), y + float(c[1]) * bh / float(isz[1])]
        mode = wipe.get("mode", "clockwise")

        def find(check, p, m, a, b, cause):
            loc = masked_local(dg.delta_e(a, b, where=m), m, 0.0)
            fl = (loc > T) & m
            rec.setdefault("checks", {})[f"{check}_{p:g}"] = {"max": round(float(loc[m].max()), 2) if m.any() else 0.0, "px": int(fl.sum())}
            for bl in _blobs(fl, loc, min_area):
                out["findings"].append({"stage": "state", "code": "E8", "check": check, "percent": p, "box": bl["box"], "area": bl["area"], "max_de": bl["max_de"],
                                        "mean_de": bl["mean_de"], "widgets": [w["id"]], "renderer": used.get(p, "composite"), "fixable": False, "cause": cause})
        if not zone.any():
            out["findings"].append({"stage": "state", "code": "E8", "check": "radial_full", "percent": 1.0, "box": [x, y, bw, bh], "area": 0, "max_de": None,
                                    "mean_de": None, "widgets": [w["id"]], "renderer": used[1.0], "fixable": False, "cause": "ring - the ring texture is empty"})
            out["gauges"].append(rec)
            continue
        find("radial_full", 1.0, zone, imgs[1.0], base, "ring - at 100% the ring does not match the concept state")
        zero = backdrop.compose(_with_percent(spec_state, w["id"], 0.0), boxes, textures, canvas, (0, 0, 0))[0]
        find("radial_zero", 0.0, zone, imgs[0.0], zero, "ring - at 0% something other than the faint track stays where the ring was")
        for p in RADIAL_STATES[1:-1]:
            keep = radial.kept_side((H, W), ctr, p, mode)
            want = np.where(keep[..., None], imgs[1.0], imgs[0.0])
            m = zone & ~radial.edge_band((H, W), ctr, p, mode, RADIAL_EDGE_PX)
            find("radial_arc", p, m, imgs[p], want, f"ring - at {p:.0%} the kept / emptied parts are not where the angle says (center, direction or track)")
        for p in RADIAL_STATES[:-1]:
            find("radial_outside", p, ~soft, imgs[p], imgs[1.0], f"ring - at {p:.0%} something outside the ring pixels changed (the wipe cuts another drawing)")
        out["gauges"].append(rec)
    return out


def gauge_states(spec_state: dict, boxes: list[dict], textures: dict, canvas, s: dict, base, render_pct=None, ref_png=None) -> dict:
    """S2 — spec_state(컨셉 상태 spec — 컨셉이 안 그린 숨은 위젯 뺌) · base(그 상태 렌더 — 엔진이면 엔진, 아니면 검정 합성).
    render_pct(widget, percent) → 엔진 렌더 HxWx3 또는 None(합성으로 물러남). ref_png(reference.png RGB — concept_fill 이 잰 그림)가 있으면 S2 보강(끝 모양).
    → {"gauges", "findings", "images": {위젯: {진행률: 그림}}, "renderer"}."""
    W, H = int(canvas[0]), int(canvas[1])
    geo = {b["id"]: b for b in boxes}
    T, cover, min_area = float(s["local_de"]), float(s["bg_cover"]), int(s["min_area"])
    textz = np.zeros((H, W), bool)
    for w in spec_state.get("widgets", []):
        g = geo.get(w["id"])
        if w.get("type") in backdrop.TEXT_TYPES and g and g.get("visible", True) and g["w"] > 0:
            textz |= dg._box_mask((H, W), _gbox(g), dg.HIDDEN_PAD + _glow(w))
    out = {"gauges": [], "findings": [], "images": {}, "renderer": "composite" if render_pct is None else "engine"}
    from gen import silhouette
    shaped = silhouette.bars(spec_state)
    for w, g, st, fill, kind, percents in gauge_targets(spec_state, boxes):
        rec = {"widget": w["id"], "percent": st.get("percent"), "fill_type": kind}
        if not percents:
            out["gauges"].append({**rec, "skipped": "only horizontal fills"})
            continue
        tb, src = track_box(spec_state, w, g)
        rec.update(track=[round(v, 1) for v in tb], track_from=src)
        imgs, used = {}, {}
        for p in percents:
            img = None
            if render_pct is not None:
                try:
                    img = render_pct(w["id"], p)
                except Exception as exc:  # noqa: BLE001 — 엔진 렌더 실패는 기록하고 합성으로
                    rec.setdefault("render_errors", []).append(f"{p:g}: {type(exc).__name__}: {exc}"[:160])
            used[p] = "engine" if img is not None else "composite"
            if img is None:
                img = backdrop.compose(_with_percent(spec_state, w["id"], p), boxes, textures, canvas, (0, 0, 0))[0]
            imgs[p] = img
        out["images"][w["id"]] = imgs
        rec["renderer"] = used
        region = dg._box_mask((H, W), _gbox(g), GAUGE_PAD) & ~dg._box_mask((H, W), tb)
        barz = None
        if w["id"] in shaped:
            barz = _bar_zone(textures.get(shaped[w["id"]]), g, (H, W))
            if barz is None:
                out["gauges"].append({**rec, "skipped": f"texture {shaped[w['id']]} is missing"})
                continue
            out["findings"] += _bar_findings(w["id"], g, barz, imgs, used, base, textz, T, min(min_area, 12), rec)
        rec["states"] = {}
        for p, img in imgs.items():
            if barz is not None:                         # 모양 막대 — 다른 곳이 없으면(보통) 전 화면을 안 잰다, 있으면 아래 그대로
                loc_, _ = _diff_local(img, base, region, cover)
                if loc_.max() <= T:
                    rec["states"][f"{p:g}"] = {"outside_max": round(float(loc_.max()), 2), "outside_px": 0}
                    continue
            loc = masked_local(dg.delta_e(img, base, where=region), region, cover)
            fl = (loc > T) & region
            rec["states"][f"{p:g}"] = {"outside_max": round(float(loc[region].max()), 2) if region.any() else 0.0, "outside_px": int(fl.sum())}
            for b in _blobs(fl, loc, min_area):
                out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_outside", "percent": p, "box": b["box"], "area": b["area"],
                                        "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": [w["id"]], "renderer": used[p], "fixable": False,
                                        "cause": f"gauge end — at {p:.0%} the fill paints outside the track (frame · end cap differ from the concept state)"})
        if barz is not None:                        # 모양 막대 — 끝(칼끝 · 어두운 테두리)은 bar_full · bar_cut 이 봤다. 0 % 에 남은 채움만(막대 상자 둘레 — 아래와 같은 검사)
            bx = dg._bbox(dg._box_mask((H, W), _gbox(g), GAUGE_PAD))
            bs = (slice(bx[1], bx[1] + bx[3]), slice(bx[0], bx[0] + bx[2]))
            tz = dg._box_mask((H, W), tb) & ~textz
            if used[0.0] == "engine" and tz.any():
                nofill = backdrop.compose(_with_percent(spec_state, w["id"], 0.0, no_fill=True), boxes, textures, canvas, (0, 0, 0))[0]
                loc = masked_local(dg.delta_e(imgs[0.0][bs], nofill[bs]), tz[bs], cover)
                fl = (loc > T) & tz[bs]
                rec["zero_max"] = round(float(loc[tz[bs]].max()), 2)
                for b in _blobs(fl, loc, min_area) if fl.any() else ():
                    out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_zero_fill", "percent": 0.0, "box": [b["box"][0] + bx[0], b["box"][1] + bx[1], b["box"][2], b["box"][3]],
                                            "area": b["area"], "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": [w["id"]], "renderer": "engine", "fixable": False,
                                            "cause": "gauge end — at 0% fill pixels stay inside the track"})
            out["gauges"].append(rec)
            # 그림은 compare.png 상태 띠용 — 막대 여덟 × 비율 일곱이라 8 비트로(전 화면 실수 그림 56 장 = 2.8 GB)
            out["images"][w["id"]] = {p: np.clip(np.round(im), 0, 255).astype(np.uint8) for p, im in imgs.items()}
            continue
        # 1.0 — 트랙 끝 구간이 0 과 같으면 채움이 끝까지 안 닿음
        x, y, tw, th = tb
        k = max(END_COLS, int(round(END_FRAC * tw)))
        endb = [x + tw - k - 2, y + 0.25 * th, k, 0.5 * th] if kind == "left_to_right" else [x + 2, y + 0.25 * th, k, 0.5 * th]
        em = dg._box_mask((H, W), endb) & ~textz
        if em.any():
            same = float((dg.delta_e(imgs[1.0], imgs[0.0], where=em)[em] < END_SAME_DE).mean())
            rec["end_unchanged_frac"] = round(same, 3)
            if same > END_SAME_FRAC:
                out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_end_short", "percent": 1.0, "box": dg._bbox(em), "area": int(em.sum()),
                                        "max_de": None, "mean_de": None, "widgets": [w["id"]], "renderer": used[1.0], "fixable": False,
                                        "cause": f"gauge end — at 100% the end of the track still looks empty ({same:.0%} unchanged from 0%)"})
        # S2 보강(1b 후속 L 다음 L-1 글자 완전 지우기 · 게이지 끝 모양) — concept_fill 트랙 끝 구간: hole 밖(끝 장식 호 · 프레임 선)이 1.0 에서 덮이면 cover,
        # hole 이 0 과 같으면 gap. 트랙 상자 안이라 위 트랙 밖 검사가 못 봤다
        fill_asset = next((a for a in spec_state.get("assets", []) if a.get("asset_id") == fill.get("asset")), {})
        proc = fill_asset.get("procedural") or {}
        if ref_png is not None and proc.get("shape") == "concept_fill" and src == "concept_fill track":
            hole = _track_hole_canvas(ref_png, proc, (H, W))
            if hole is not None:
                ke = max(END_COLS, int(round(END_SHAPE_FRAC * tw)))
                ez = dg._box_mask((H, W), [x + tw - ke, y, ke, th] if kind == "left_to_right" else [x, y, ke, th]) & ~textz
                frame = ez & ~hole
                d10 = dg.delta_e(imgs[1.0], imgs[0.0], where=ez)
                rec["end_shape"] = {"cols": ke, "frame_px": int(frame.sum()), "hole_px": int((ez & hole).sum())}
                if frame.any():
                    loc = masked_local(d10, frame, 0.0)
                    fl = (loc > T) & frame
                    rec["end_shape"]["cover_max"] = round(float(loc[frame].max()), 2)
                    for b in _blobs(fl, loc, min(min_area, 12)):
                        out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_end_cover", "percent": 1.0, "box": b["box"], "area": b["area"],
                                                "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": [w["id"]], "renderer": used[1.0], "fixable": False,
                                                "cause": "gauge end — at 100% the fill covers the end cap arc / frame inside the track end (the concept's empty-track "
                                                         "end shape is not followed)"})
                hz = ez & hole
                if hz.any():
                    same_h = float((d10[hz] < END_SAME_DE).mean())
                    rec["end_shape"]["hole_unchanged_frac"] = round(same_h, 3)
                    if same_h > END_SAME_FRAC:
                        out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_end_gap", "percent": 1.0, "box": dg._bbox(hz), "area": int(hz.sum()),
                                                "max_de": None, "mean_de": None, "widgets": [w["id"]], "renderer": used[1.0], "fixable": False,
                                                "cause": f"gauge end — at 100% the empty track inside the end cap stays unfilled ({same_h:.0%} unchanged from 0%)"})
        # 0 — 트랙 안이 채움 없는 합성과 다르면 채움이 남음(엔진만 — 합성은 0 이면 채움을 안 그린다)
        tz = dg._box_mask((H, W), tb) & ~textz
        if used[0.0] == "engine" and tz.any():
            nofill = backdrop.compose(_with_percent(spec_state, w["id"], 0.0, no_fill=True), boxes, textures, canvas, (0, 0, 0))[0]
            loc = masked_local(dg.delta_e(imgs[0.0], nofill, where=tz), tz, cover)
            fl = (loc > T) & tz
            rec["zero_max"] = round(float(loc[tz].max()), 2)
            for b in _blobs(fl, loc, min_area):
                out["findings"].append({"stage": "state", "code": "E8", "check": "gauge_zero_fill", "percent": 0.0, "box": b["box"], "area": b["area"],
                                        "max_de": b["max_de"], "mean_de": b["mean_de"], "widgets": [w["id"]], "renderer": "engine", "fixable": False,
                                        "cause": "gauge end — at 0% fill pixels stay inside the track"})
        out["gauges"].append(rec)
    return out


def _diff_local(a, b, m, cover: float):
    """masked_local(ΔE00(a, b), m, cover) 를 두 그림이 실제로 다른(채널 차 > 0) 자리 둘레 창에서만 — 다른 픽셀이 없는 곳의 값은 0 이라 전 화면으로 잰 것과 같다.
    → (잘라 낸 국소 지도, 왼쪽 위 (x, y)). 다른 곳이 없으면 1 × 1 의 0."""
    d = (np.asarray(a) != np.asarray(b)).any(axis=2) & m
    if not d.any():
        return np.zeros((1, 1)), (0, 0)
    H, W = m.shape
    ys, xs = np.nonzero(d)
    P = 2 * dg.WIN
    x0, y0, x1, y1 = max(0, int(xs.min()) - P), max(0, int(ys.min()) - P), min(W, int(xs.max()) + 1 + P), min(H, int(ys.max()) + 1 + P)
    s = (slice(y0, y1), slice(x0, x1))
    return masked_local(dg.delta_e(np.asarray(a)[s], np.asarray(b)[s]), m[s], cover), (x0, y0)


def _bar_zone(tex, g: dict, shape):
    """모양 막대 텍스처 → (막대 자리 = 알파 > BAR_ZONE_ALPHA, 조금이라도 그리는 자리 + 1 px) 캔버스 bool, 텍스처가 없으면 None."""
    if tex is None:
        return None
    H, W = shape
    x, y, bw, bh = (int(round(float(g[k]))) for k in ("x", "y", "w", "h"))
    lay = backdrop._resize(tex, bw, bh)
    cx0, cy0, cx1, cy1 = max(0, x), max(0, y), min(W, x + bw), min(H, y + bh)
    zone, soft = np.zeros((H, W), bool), np.zeros((H, W), bool)
    zone[cy0:cy1, cx0:cx1] = (lay[..., 3] > 255 * BAR_ZONE_ALPHA)[cy0 - y:cy1 - y, cx0 - x:cx1 - x]
    soft[cy0:cy1, cx0:cx1] = (lay[..., 3] > 0)[cy0 - y:cy1 - y, cx0 - x:cx1 - x]
    return zone, dg._dilate(soft, 1)


def _bar_findings(wid: str, g: dict, barz, imgs: dict, used: dict, base, textz, T: float, min_area: int, rec: dict) -> list[dict]:
    """모양 막대 — bar_full(100 % = 컨셉 상태) · bar_track(0 % 가 빈 자리 색으로 보인다 — 100 % 와 뚜렷이 다르고 아무것도 없는 것과도 다르다) · bar_cut(중간
    비율에서 남아야 할 쪽 = 100 % 렌더, 빈 쪽 = 0 % 렌더) · bar_outside(어느 비율에서도 막대 밖이 100 % 렌더 그대로 — 이웃 막대 · 글자)."""
    zone, soft = barz[0] & ~textz, barz[1]
    H, W = zone.shape
    found: list[dict] = []

    def find(check, p, m, a, b, cause):
        loc, (x0, y0) = _diff_local(a, b, m, 0.0)
        sub_m = m[y0:y0 + loc.shape[0], x0:x0 + loc.shape[1]]
        fl = (loc > T) & sub_m
        rec.setdefault("checks", {})[f"{check}_{p:g}"] = {"max": round(float(loc[sub_m].max()), 2) if sub_m.any() else 0.0, "px": int(fl.sum())}
        for bl in _blobs(fl, loc, min_area) if fl.any() else ():
            bx = bl["box"]
            found.append({"stage": "state", "code": "E8", "check": check, "percent": p, "box": [bx[0] + x0, bx[1] + y0, bx[2], bx[3]], "area": bl["area"], "max_de": bl["max_de"],
                          "mean_de": bl["mean_de"], "widgets": [wid], "renderer": used.get(p, "composite"), "fixable": False, "cause": cause})
    if not zone.any():
        return [{"stage": "state", "code": "E8", "check": "bar_full", "percent": 1.0, "box": [int(g["x"]), int(g["y"]), int(g["w"]), int(g["h"])], "area": 0,
                 "max_de": None, "mean_de": None, "widgets": [wid], "renderer": used.get(1.0, "composite"), "fixable": False, "cause": "bar - the bar texture is empty"}]
    find("bar_full", 1.0, zone, imgs[1.0], base, "bar - at 100% the bar does not match the concept state")
    body = zone & ~dg._dilate(~barz[0], 2)                           # 막대 속(가장자리 2 px 뺌) — 어두운 테두리는 빈 자리와 비슷해도 된다
    body = body if body.any() else zone
    bx = dg._bbox(body)
    bs = (slice(bx[1], bx[1] + bx[3]), slice(bx[0], bx[0] + bx[2]))
    med = float(np.median(dg.delta_e(imgs[1.0][bs], imgs[0.0][bs])[body[bs]]))
    rec["track_contrast"] = round(med, 1)
    if med < T:
        found.append({"stage": "state", "code": "E8", "check": "bar_track", "percent": 0.0, "box": dg._bbox(body), "area": int(body.sum()), "max_de": round(med, 1),
                      "mean_de": round(med, 1), "widgets": [wid], "renderer": used.get(0.0, "composite"), "fixable": False,
                      "cause": f"bar - the empty bar looks like the full bar (median difference {med:.1f}) - the empty part is not tinted"})
    xx = np.arange(W)[None, :] + 0.5
    for p in BAR_STATES[1:-1]:
        cut = float(g["x"]) + p * float(g["w"])
        want = np.where((xx < cut)[..., None], imgs[1.0], imgs[0.0])
        m = zone & (np.abs(xx - cut) > BAR_EDGE_PX)
        find("bar_cut", p, m, imgs[p], want, f"bar - at {p:.0%} the filled / empty parts are not where the percent says (direction, width or tint)")
    for p in BAR_STATES[:-1]:
        find("bar_outside", p, ~soft, imgs[p], imgs[1.0], f"bar - at {p:.0%} something outside the bar pixels changed (the bar cuts another drawing)")
    return found


def end_glow_zones(spec: dict, shape) -> list[dict]:
    """F2 — 번짐을 뺀 concept_fill 채움(spill 0 · spill_measured > 0)의 컨셉 상태 진행 끝 빛 자리(캔버스): 트랙 줄 × 몸통 끝 − 3 ~ + spill_measured + 8.
    그 자리의 국소 차는 근사(gauge_end_glow) — 한 brush 로는 70 % 의 끝 빛과 100 % 의 트랙 끝 맞춤을 같이 못 한다(S2 가 100 % 를 지킨다)."""
    out = []
    for a in spec.get("assets", []):
        p = a.get("procedural") or {}
        if p.get("shape") != "concept_fill" or p.get("full") or int(p.get("spill", 0)) or int(p.get("spill_measured", 0)) <= 0:
            continue
        fx, fy, fw, _ = (float(v) for v in p["frame_box"])
        _, t_, _, b_ = (int(v) for v in p["track"])
        x1 = int(p["body_end"])
        c0, c1 = x1 - 3, x1 + int(p["spill_measured"]) + 8
        if p.get("flip"):
            c0, c1 = int(fw) - 1 - c1, int(fw) - 1 - c0
        m = dg._box_mask(shape, [fx + c0, fy + t_, c1 - c0 + 1, b_ - t_ + 1])
        users = [w["id"] for w in spec.get("widgets", []) if ((w.get("style") or {}).get("fill") or {}).get("asset") == a["asset_id"]]
        out.append({"asset": a["asset_id"], "widgets": users, "mask": m, "box": dg._bbox(m), "spill_measured": int(p["spill_measured"])})
    return out


def end_shape_zones(spec: dict, shape) -> list[dict]:
    """G3(1b 후속 L 다음) — 끝 모양(end_shape)을 넣은 concept_fill 채움의 컨셉 상태 진행 끝 자리(캔버스): 트랙 줄 × 몸통 끝 − 여백 − 1 ~ + 2.
    그 자리 국소 차는 근사(gauge_end_shape) — 100 % 에서 끝 장식 호에 맞게 들어가는 대신 중간 진행률의 끝이 곧은 선이 아니라 호 모양(S2 보강이 100 % 를 지킨다)."""
    out = []
    for a in spec.get("assets", []):
        p = a.get("procedural") or {}
        es = p.get("end_shape")
        if p.get("shape") != "concept_fill" or p.get("full") or not es:
            continue
        fx, fy, fw, _ = (float(v) for v in p["frame_box"])
        _, t_, _, b_ = (int(v) for v in p["track"])
        x1 = int(p["body_end"])
        c0, c1 = x1 - int(es["margin"]) - 1, x1 + 2
        if p.get("flip"):
            c0, c1 = int(fw) - 1 - c1, int(fw) - 1 - c0
        m = dg._box_mask(shape, [fx + c0, fy + t_, c1 - c0 + 1, b_ - t_ + 1])
        users = [w["id"] for w in spec.get("widgets", []) if ((w.get("style") or {}).get("fill") or {}).get("asset") == a["asset_id"]]
        out.append({"asset": a["asset_id"], "widgets": users, "mask": m, "box": dg._bbox(m), "depth": int(es.get("depth", 0)), "kind": "gauge_end_shape"})
    return out
