"""동작 수치 — 양손 간격(파지) · 발 좌우 간격 · 휘두름 정점 · 궤적 폭 · 비파지 관통 상한 · 떨림 · 손목 굽힘 · 팔 꼬임 · 손-머리 근접
(Phase 8-1, 지침서 §13 '제약' 행).

같은 정의를 두 곳이 쓴다: local_ai/kimodo_run.py(Kimodo venv — 1 · 2차 생성의 관절 위치, m · y-up → cm)와 retarget 파이프의 select 단계
(validate_animation profile_positions — Vesper 컴포넌트 공간 cm · z-up). 순수 Python(리스트 — MCP venv 에 numpy 가 없다), pytest 대상.

역할 이름: hand_l · hand_r(손목) · hip_l · hip_r(엉덩 관절) · foot_l · foot_r(발목) · shoulder_l · shoulder_r(어깨 관절 = 위팔 시작) ·
elbow_l · elbow_r(팔꿈치 = 아래팔 시작). 선택 역할 finger_l · finger_r(중지 첫 마디 — 손목 굽힘, Kimodo 쪽만) · head(머리 본 = 두개 바닥 —
손-머리 근접, 지터 · 다른 지표에는 안 쓴다). 손 점(hand_points) = 손목 아래 손가락 · 손바닥 관절 트랙(Kimodo SOMA 손 관절 · Vesper 손 본 자손). 위치 단위는 cm.
scale = 펠비스 높이 / 100 — 플러그인 관통 · 파지 거리 기준과 같은 배율(Core/AnimMcpBodyClearance 의 GripCm 20 cm × scale). Kimodo 쪽은 1.

버전 2 (2026-10-26 Persona 소견 후): 궤적 폭 · 손 들기(attack — 공격다움, '양손 모아 서 있기' 후보를 거른다), 떨림(jitter — 프레임 지그재그),
손목 굽힘(wrist_bend), 접지 발 미끄러짐(contact_slide — Kimodo 접지 라벨이 있을 때만).
버전 3 (같은 날 — 낫 기준 보정): 궤적 폭 · 손 들기를 손별로 재 큰 쪽(한손 공격에서 빈 손이 가만있으면 두 손 중점은 절반쯤으로 작아진다 — 중점 값은
기록), 양손 겹침(hand_contact — 손 본 아래 손가락 · 손바닥 뼈 선분 사이 거리, 기록만).
버전 4 (같은 날 밤 — 낫 Persona '팔 꼬임 · 머리 관통 · 배 관통'): 팔 꼬임(arm_cross — 엉덩 축 위 두 손목 좌우 뒤바뀜) · 손-머리 근접(head_near).
기준은 운영 낫 애니 4개(AS_Vesper_Sickle_Attack1 ~ 3 · Finisher1, Vesper 측정)에서 정했다 — 손이 10 cm 넘게 엇갈린 프레임 0 ~ 16.3 %(margin 0 이면
4 ~ 42 % — 낫 베기는 원래 팔이 교차한다), 손 점-머리 본 최소 11.0 cm(10 cm 안 0 %). 망가진 낫 후보(Job ad275a): 엇갈림 12.5 ~ 91.7 % · 머리 10 cm 안
41.7 ~ 90 %. 검 손잡이(손목 5 ~ 7 cm)는 margin 0 이면 88 ~ 100 % 가 '뒤바뀜'(손목을 포갠다) — 그래서 margin 을 둔다.
버전 5 (같은 밤 — 자루 무기 파지 띠 정정): 띠 = (요청 간격 ± 13) × pelvis scale 이었는데 FK 리타깃은 관절 회전을 복사해 손 간격이 어깨 폭 · 팔 길이를
따른다(기록 Job f991aa Vesper = 소스 × 0.79, 띠는 × 1.052 — 요청 > 52 cm 면 늘 띠 밖). 간격 사상(gap_map — 두 골격 기준 포즈의 어깨 관절 폭 ·
팔 길이)으로 생성 골격 간격 ↔ 대상 간격을 바꾸고(grip_spacing), 띠는 각 골격 간격 ± 허용(생성 13 cm · 대상 13 × 팔 길이 비)으로 그 골격 cm 에서
잰다. 검 손잡이(간격 없음)는 그대로 ≤ 20 cm × scale.
"""
from __future__ import annotations

import math

VERSION = 5
GRIP_TOL_CM = 13.0      # 요청 간격(자루 무기)이 있을 때 파지로 보는 ± 폭(생성 골격 cm — 대상은 × 팔 길이 비) — grip_band · grip_spacing
HAND_CONTACT_CM = 2.5   # 두 손의 손가락 · 손바닥 뼈 선분이 이보다 가까우면 살이 겹친다(손가락 굵기 ≈ 2 cm, 손바닥 두께 ≈ 3 cm) — × scale
CROSS_CM = 10.0         # 팔 꼬임 = 왼 손목이 오른 손목보다 엉덩 축 위에서 이만큼 넘게 오른쪽(손 폭 ≈ 8 ~ 10 cm 넘게 넘어감) — × scale
HEAD_NEAR_CM = 10.0     # 손-머리 근접 = 손목 · 손 점이 머리 본(두개 바닥)에서 이보다 가깝다(머리 반지름 ≈ 9 ~ 10 cm — 운영 낫 최소 11.0) — × scale
GRIP_CM = 20.0
ROLES = ("hand_l", "hand_r", "hip_l", "hip_r", "foot_l", "foot_r", "shoulder_l", "shoulder_r", "elbow_l", "elbow_r")
OPTIONAL_ROLES = ("finger_l", "finger_r")
HEAD_ROLE = "head"
EDGE_S = 0.67   # 떨림을 처음 · 중간 · 끝으로 나누는 길이(초) — 정지한 처음 · 끝에서 눈에 띈다(사용자 소견 ①)


def percentile(values: list[float], q: float) -> float | None:
    """선형 보간 백분위(q 0 ~ 1). 빈 목록은 None."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _r(x: float | None, digits: int = 2) -> float | None:
    return None if x is None else round(x, digits)


def _dist(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _horizontal(v, up: int) -> tuple[float, float]:
    axes = [i for i in range(3) if i != up]
    return v[axes[0]], v[axes[1]]


def _spread(values: list[float]) -> dict:
    return {"min": _r(min(values) if values else None), "p10": _r(percentile(values, 0.1)), "p50": _r(percentile(values, 0.5)),
            "p90": _r(percentile(values, 0.9)), "max": _r(max(values) if values else None)}


def in_window(times: list[float], window: tuple[float | None, float | None] | None) -> list[int]:
    """시각 구간 [from, to](초, None = 끝까지) 안의 표본 번호."""
    lo, hi = (window or (None, None))
    return [i for i, t in enumerate(times) if (lo is None or t >= lo - 1e-6) and (hi is None or t <= hi + 1e-6)]


def gaps(hand_l: list, hand_r: list) -> list[float]:
    return [_dist(a, b) for a, b in zip(hand_l, hand_r)]


class GripSpacingError(ValueError):
    pass


def arm_dims(positions: dict, bones: dict) -> dict | None:
    """기준 포즈 위치 {본: [x, y, z]}(cm) · 역할 본(shoulder_l · elbow_l · hand_l …) → 어깨 관절 폭(shoulder_l ↔ shoulder_r) · 팔 길이(어깨 → 팔꿈치
    → 손목, 양팔 평균) — 손목 간격 사상(gap_map)의 치수. 본 위치가 하나라도 없으면 None."""
    roles = ("shoulder_l", "shoulder_r", "elbow_l", "elbow_r", "hand_l", "hand_r")
    if not all(bones.get(r) and positions.get(bones[r]) for r in roles):
        return None
    p = {r: positions[bones[r]] for r in roles}
    arms = [_dist(p[f"shoulder_{s}"], p[f"elbow_{s}"]) + _dist(p[f"elbow_{s}"], p[f"hand_{s}"]) for s in ("l", "r")]
    return {"shoulder_width_cm": _r(_dist(p["shoulder_l"], p["shoulder_r"])), "arm_cm": _r(sum(arms) / 2.0)}


def gap_map(source: dict, target: dict) -> dict:
    """두 골격 치수(arm_dims) → 손목 간격 사상 {source_shoulder_cm, target_shoulder_cm, arm_ratio}: 대상 간격 = W_t + k·(생성 간격 − W_s),
    k = 팔_t / 팔_s. FK 리타깃(본 대 본 정렬)은 본 방향을 복사해 대상 본 벡터 = 소스 본 벡터 × 길이 비 — 손목 차 = 어깨 차 × W_t/W_s + 팔 차 × k
    (기록 Job f991aa 프레임별 |오차| p50 0.2 cm). 파지선이 어깨선과 나란하면(자루를 몸 앞에 가로로 쥔다) 이 닫힌 식이 된다 — 그 기록(cos 0.79 ~ 0.97)
    에서 p50 오차 −1.0 ~ +0.1 cm(pelvis scale × 는 +15 ~ +17, 팔 길이 비 × 는 +3 ~ +4). 파지선이 세로에 가까울수록 대상 간격을 낮게 본다
    (Vesper 생성 간격 75 에서 −4 cm, 어깨가 넓은 대상일수록 크다) — 결과는 select 가 대상에서 직접 잰다."""
    return {"source_shoulder_cm": source["shoulder_width_cm"], "target_shoulder_cm": target["shoulder_width_cm"],
            "arm_ratio": round(target["arm_cm"] / source["arm_cm"], 4)}


def map_gap(m: dict, gap_cm: float, to: str = "target") -> float:
    """간격 사상(gap_map) — 대상으로: W_t + k·(g − W_s), 생성 골격으로: W_s + (g − W_t) / k."""
    if to == "target":
        return m["target_shoulder_cm"] + m["arm_ratio"] * (gap_cm - m["source_shoulder_cm"])
    return m["source_shoulder_cm"] + (gap_cm - m["target_shoulder_cm"]) / m["arm_ratio"]


def grip_spacing(m: dict, *, source_cm: float | None = None, target_cm: float | None = None, tolerance_cm: float = GRIP_TOL_CM) -> dict:
    """자루 무기 요청 간격 하나(생성 골격 source_cm 또는 대상 target_cm) → 두 골격의 간격 · 허용 · 띠. 생성 쪽(refine 목표 · Kimodo 소스 수치)과
    대상 쪽(select)이 이 한 결과를 쓴다. 허용: 생성 tolerance_cm, 대상 tolerance_cm × k(사상의 기울기 — 대상 띠 = 생성 띠의 상)."""
    if (source_cm is None) == (target_cm is None):
        raise GripSpacingError("give exactly one of source_cm · target_cm")
    src = source_cm if source_cm is not None else map_gap(m, target_cm, "source")
    tgt = target_cm if target_cm is not None else map_gap(m, source_cm, "target")
    if src <= 0 or tgt <= 0:
        raise GripSpacingError(f"{source_cm if source_cm is not None else target_cm} cm maps to {tgt if source_cm is not None else src:.2f} cm on the "
                               f"{'target' if source_cm is not None else 'generation'} skeleton (shoulder joints {m['source_shoulder_cm']} → "
                               f"{m['target_shoulder_cm']} cm, arm ratio {m['arm_ratio']}) — not a two-handed gap")
    src, tgt = round(src, 2), round(tgt, 2)
    tol = {"source": tolerance_cm, "target": round(tolerance_cm * m["arm_ratio"], 2)}
    return {"from": "target" if target_cm is not None else "source", "source_cm": src, "target_cm": tgt, "tolerance_cm": tol,
            "source_band_cm": [_r(x) for x in grip_band(1.0, src, tol["source"])], "target_band_cm": [_r(x) for x in grip_band(1.0, tgt, tol["target"])],
            "map": dict(m)}


def grip_band(scale: float = 1.0, spacing_cm: float | None = None, tolerance_cm: float = GRIP_TOL_CM) -> tuple[float, float]:
    """파지로 보는 손목 간격 [lo, hi](잰 골격의 cm). 요청 간격이 없으면(검 손잡이) [0, 20 × scale] — 플러그인 GripCm 과 같다. 간격 s 가 있으면(자루
    무기) [s − 허용, s + 허용] — s · 허용은 이미 그 골격 cm 다(grip_spacing: 생성 골격 13 cm, 대상 13 × 팔 길이 비). 13 cm = 검 손잡이 기본 간격
    ≈ 7 cm 에 20 cm 기준이 준 여유."""
    if not spacing_cm:
        return 0.0, GRIP_CM * scale
    return max(0.0, spacing_cm - tolerance_cm), spacing_cm + tolerance_cm


def grip(hand_l: list, hand_r: list, times: list[float], scale: float = 1.0, window=None, spacing_cm: float | None = None,
         tolerance_cm: float = GRIP_TOL_CM) -> dict:
    """손목 간격(프레임별) — 파지 = 간격이 grip_band 안(검: ≤ 20 cm × scale). grip_pct 는 파지 구간(window) 안 표본 비율."""
    gap = gaps(hand_l, hand_r)
    idx = in_window(times, window)
    sel = [gap[i] for i in idx]
    lo, hi = grip_band(scale, spacing_cm, tolerance_cm)
    return {"threshold_cm": _r(hi), "band_cm": [_r(lo), _r(hi)], "spacing_cm": spacing_cm, "tolerance_cm": tolerance_cm if spacing_cm else None,
            "samples": len(sel), "gap_cm": _spread(sel), "grip_pct": _r(100.0 * sum(lo <= g <= hi for g in sel) / len(sel), 1) if sel else None}


def stance(foot_l: list, foot_r: list, hip_l: list, hip_r: list, up: int) -> dict:
    """발 좌우 간격 비 = |(발L − 발R)수평 · 엉덩 축 방향수평| / |엉덩L − 엉덩R|수평 (프레임별 — 몸이 돌아도 좌우만 잰다).
    앞뒤 보폭 = 엉덩 축에 수직인 수평 성분 / 다리 길이(엉덩 → 발목 거리의 최대 — 다리를 편 프레임) — 기록만."""
    lateral, forward, widths, legs = [], [], [], []
    for fl, fr, hl, hr in zip(foot_l, foot_r, hip_l, hip_r):
        ax, ay = _horizontal([hl[i] - hr[i] for i in range(3)], up)
        width = math.hypot(ax, ay)
        legs += [_dist(hl, fl), _dist(hr, fr)]
        if width < 1e-6:
            continue
        ux, uy = ax / width, ay / width
        dx, dy = _horizontal([fl[i] - fr[i] for i in range(3)], up)
        widths.append(width)
        lateral.append(abs(dx * ux + dy * uy) / width)
        forward.append(abs(-dx * uy + dy * ux))
    leg = max(legs) if legs else None
    return {"lateral_ratio": _spread(lateral), "hip_width_cm": _r(percentile(widths, 0.5)),
            "lateral_cm": _spread([r * w for r, w in zip(lateral, widths)]), "leg_cm": _r(leg),
            "stride_leg_ratio": {"p50": _r(percentile([f / leg for f in forward], 0.5), 3) if leg else None,
                                 "p90": _r(percentile([f / leg for f in forward], 0.9), 3) if leg else None}}


def speeds(track: list, times: list[float]) -> list[float]:
    """표본 사이 선속도(cm/s) — 첫 표본은 0(앞 표본이 없다)."""
    out = [0.0]
    for i in range(1, len(track)):
        dt = times[i] - times[i - 1]
        out.append(_dist(track[i], track[i - 1]) / dt if dt > 1e-9 else 0.0)
    return out[:len(track)] if track else []


def swing(hand_l: list, hand_r: list, times: list[float], scale: float = 1.0) -> dict:
    """휘두름 정점 = 두 손목 중 빠른 쪽의 최대 속도 / scale(cm/s) · 정점 시각 · 동작 구간 비율(정점 50% 이상 표본 %, 기록만)."""
    best = None
    for side, track in (("hand_l", hand_l), ("hand_r", hand_r)):
        v = speeds(track, times)
        if not v:
            continue
        i = max(range(len(v)), key=v.__getitem__)
        if best is None or v[i] > best[1][best[2]]:
            best = (side, v, i)
    if best is None:
        return {"peak_cm_s": None, "hand": None, "peak_time": None, "active_pct": None}
    side, v, i = best
    peak = v[i]
    return {"peak_cm_s": _r(peak / scale, 1), "hand": side, "peak_time": _r(times[i], 4),
            "active_pct": _r(100.0 * sum(x >= 0.5 * peak for x in v) / len(v), 1) if peak > 0 else 0.0}


def _mid(a, b):
    return [(a[i] + b[i]) * 0.5 for i in range(3)]


def arm_length(shoulder: list, elbow: list, hand: list) -> float | None:
    """위팔 + 아래팔 길이(프레임 평균, cm) — 본 길이라 굽힌 자세에서도 같다."""
    n = min(len(shoulder), len(elbow), len(hand))
    if not n:
        return None
    return sum(_dist(shoulder[i], elbow[i]) + _dist(elbow[i], hand[i]) for i in range(n)) / n


def _box(track: list, origin: list) -> list[float]:
    """origin(프레임별) 기준 궤적의 축별 범위(cm)."""
    rel = [[p[i] - o[i] for i in range(3)] for p, o in zip(track, origin)]
    return [max(v[i] for v in rel) - min(v[i] for v in rel) for i in range(3)] if rel else [0.0, 0.0, 0.0]


def attack(tracks: dict, times: list[float], up: int) -> dict:
    """공격다움 — 팔 길이(양팔 평균) 대비 비율이라 scale 이 필요 없다. 손별로 재 큰 쪽을 쓴다(양손 파지면 두 손이 거의 같고, 한손 공격이면 무기
    손이 잡힌다 — 버전 2 의 두 손 중점은 빈 손이 가만있으면 절반쯤으로 작아졌다, 중점 값은 width_mid_arm_ratio 로 기록).
    궤적 폭 = 엉덩 관절 중점(≈ 펠비스) 기준 손목 궤적의 상자 대각선 / 팔 길이 — 휘두르면 크고 '양손 모아 서 있기' 는 작다(기록 Job
             c49a83 Vesper 중점: seed 25 1.65 · seed 26 0.38, 운영 공격 1.46 ~ 4.40). 점수에 쓴다(selection attack).
    손 들기 = max(손목 높이 − 어깨 중점 높이) / 팔 길이 — 들어 올리는 베기만 크다(수평 베기는 작다) → 기록만."""
    arm = [arm_length(tracks[f"shoulder_{s}"], tracks[f"elbow_{s}"], tracks[f"hand_{s}"]) for s in ("l", "r")]
    arm = [a for a in arm if a]
    if not arm:
        return {"arm_cm": None, "box_cm": None, "width_arm_ratio": None, "width_by_hand": None, "width_mid_arm_ratio": None, "hand": None,
                "raise_arm_ratio": None, "raise_time": None}
    arm_cm = sum(arm) / len(arm)
    hips = list(map(_mid, tracks["hip_l"], tracks["hip_r"]))
    shoulders = list(map(_mid, tracks["shoulder_l"], tracks["shoulder_r"]))
    boxes = {s: _box(tracks[f"hand_{s}"], hips) for s in ("l", "r")}
    widths = {s: math.sqrt(sum(b * b for b in boxes[s])) / arm_cm for s in boxes}
    hand = max(widths, key=widths.get)
    mid = _box(list(map(_mid, tracks["hand_l"], tracks["hand_r"])), hips)
    lift = [(tracks[f"hand_{s}"][f][up] - shoulders[f][up], f) for s in ("l", "r") for f in range(min(len(shoulders), len(tracks[f"hand_{s}"])))]
    top = max(lift) if lift else None
    return {"arm_cm": _r(arm_cm), "box_cm": [_r(b) for b in boxes[hand]], "width_arm_ratio": _r(widths[hand], 3),
            "width_by_hand": {s: _r(w, 3) for s, w in widths.items()}, "width_mid_arm_ratio": _r(math.sqrt(sum(b * b for b in mid)) / arm_cm, 3),
            "hand": f"hand_{hand}", "raise_arm_ratio": None if top is None else _r(top[0] / arm_cm, 3),
            "raise_time": None if top is None else _r(times[top[1]], 4)}


def _seg_dist(p1, q1, p2, q2) -> float:
    """두 선분 사이 최단 거리(닫힌 선분 — Ericson, Real-Time Collision Detection 5.1.9)."""
    d1, d2, r = [q1[i] - p1[i] for i in range(3)], [q2[i] - p2[i] for i in range(3)], [p1[i] - p2[i] for i in range(3)]
    a, e, f = sum(x * x for x in d1), sum(x * x for x in d2), sum(d2[i] * r[i] for i in range(3))
    if a < 1e-12 and e < 1e-12:
        return math.sqrt(sum(x * x for x in r))
    if a < 1e-12:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = sum(d1[i] * r[i] for i in range(3))
        if e < 1e-12:
            s, t = max(0.0, min(1.0, -c / a)), 0.0
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            den = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / den)) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = max(0.0, min(1.0, -c / a)), 0.0
            elif t > 1.0:
                s, t = max(0.0, min(1.0, (b - c) / a)), 1.0
    return math.sqrt(sum((p1[i] + d1[i] * s - p2[i] - d2[i] * t) ** 2 for i in range(3)))


def hand_contact(segs_l: list, segs_r: list, times: list[float], scale: float = 1.0, contact_cm: float = HAND_CONTACT_CM) -> dict:
    """양손 겹침 — 왼손 · 오른손 뼈 선분(손 본 → 손가락 · 손바닥 본, (부모 트랙, 자식 트랙) 쌍)의 프레임별 최단 거리. contact_cm × scale 보다
    가까운 프레임 % · 처음 시각 · 최소 · p50. 메시가 아니라 뼈라 근사다(기록만 — 2026-10-26 Persona 소견 '손끼리 겹친다')."""
    if not segs_l or not segs_r or not times:
        return {"contact_pct": None, "first_time": None, "min_cm": None, "p50_cm": None, "threshold_cm": None}
    n = min(len(times), *(len(a) for a, _ in segs_l + segs_r))
    dists = [min(_seg_dist(a[f], b[f], c[f], d[f]) for a, b in segs_l for c, d in segs_r) for f in range(n)]
    threshold = contact_cm * scale
    first = next((times[f] for f in range(n) if dists[f] < threshold), None)
    return {"contact_pct": _r(100.0 * sum(d < threshold for d in dists) / n, 1), "first_time": _r(first, 4), "min_cm": _r(min(dists)),
            "p50_cm": _r(percentile(dists, 0.5)), "threshold_cm": _r(threshold)}


def arm_cross(hand_l: list, hand_r: list, hip_l: list, hip_r: list, times: list[float], up: int, scale: float = 1.0,
              cross_cm: float = CROSS_CM) -> dict:
    """팔 꼬임 — 프레임마다 엉덩 관절 축(왼 − 오른, 수평) 위 두 손목의 좌우 차 = (왼 손목 − 오른 손목) · 축(cm, 양수 = 제자리). 왼 손목이 오른 손목보다
    cross_cm × scale 넘게 오른쪽인 프레임 %(crossed_pct — 점수), 조금이라도 넘어간 프레임 %(swapped_pct — 기록), 넘어간 깊이(cm) p50 · 최대 · 처음 시각.
    몸이 돌아도 몸 기준 좌우만 잰다(stance 와 같은 축)."""
    lateral, kept = [], []
    for f, (wl, wr, hl, hr) in enumerate(zip(hand_l, hand_r, hip_l, hip_r)):
        ax, ay = _horizontal([hl[i] - hr[i] for i in range(3)], up)
        width = math.hypot(ax, ay)
        if width < 1e-6:
            continue
        dx, dy = _horizontal([wl[i] - wr[i] for i in range(3)], up)
        lateral.append((dx * ax + dy * ay) / width)
        kept.append(f)
    if not lateral:
        return {"crossed_pct": None, "swapped_pct": None, "depth_cm": None, "first_time": None, "threshold_cm": None}
    threshold = cross_cm * scale
    depth = [-x for x in lateral if x < 0]
    first = next((times[f] for f, x in zip(kept, lateral) if x < -threshold and f < len(times)), None)
    return {"crossed_pct": _r(100.0 * sum(x < -threshold for x in lateral) / len(lateral), 1),
            "swapped_pct": _r(100.0 * len(depth) / len(lateral), 1),
            "depth_cm": {"p50": _r(percentile(depth, 0.5)), "max": _r(max(depth) if depth else None)},
            "first_time": _r(first, 4), "threshold_cm": _r(threshold)}


def head_near(points: list[list], head: list, times: list[float], scale: float = 1.0, near_cm: float = HEAD_NEAR_CM) -> dict:
    """손-머리 근접 — 프레임마다 손 점(양 손목 + 손가락 · 손바닥 관절 트랙)과 머리 본 사이 최소 거리. near_cm × scale 보다 가까운 프레임 % · 처음
    시각 · 최소 · p10 · p50. 머리 본은 두개 바닥(목 위) 점이라 메시 접촉이 아니라 근사다 — 머리 반지름 안이면 손이 머리 · 턱에 박힌다."""
    if not points or not head or not times:
        return {"near_pct": None, "first_time": None, "min_cm": None, "p10_cm": None, "p50_cm": None, "threshold_cm": None, "points": len(points or [])}
    n = min(len(times), len(head), *(len(p) for p in points))
    dists = [min(_dist(p[f], head[f]) for p in points) for f in range(n)]
    threshold = near_cm * scale
    first = next((times[f] for f in range(n) if dists[f] < threshold), None)
    return {"near_pct": _r(100.0 * sum(d < threshold for d in dists) / n, 1), "first_time": _r(first, 4), "min_cm": _r(min(dists)),
            "p10_cm": _r(percentile(dists, 0.1)), "p50_cm": _r(percentile(dists, 0.5)), "threshold_cm": _r(threshold), "points": len(points)}


def zigzag(tracks: list[list], times: list[float], scale: float = 1.0, edge_s: float = EDGE_S) -> dict:
    """떨림 = 프레임 지그재그: 가속도 a_f = p[f+1] − 2p[f] + p[f−1](cm/프레임²)가 앞 프레임과 반대 방향(a_f · a_f−1 < 0)이면 min(|a_f|, |a_f−1|),
    아니면 0 — 관절마다 재서 처음 edge_s 초 · 중간 · 끝 edge_s 초의 p95(/ scale). 표본은 프레임마다(Kimodo 출력 · profile 1 표본/프레임)여야
    한다. 2차 생성 진동 0.6 ~ 0.9 vs 1차 ≤ 0.08(스파이크). 빠른 휘두름의 타격 순간도 크게 잡으므로(운영 공격 0.6 ~ 5.6) 기록만."""
    if len(times) < 4:
        return {"start": None, "middle": None, "end": None, "max": None, "joints": len(tracks)}
    t0, t1 = times[0], times[-1]
    parts: dict[str, list[float]] = {"start": [], "middle": [], "end": []}
    for track in tracks:
        acc = [[track[f + 1][i] - 2.0 * track[f][i] + track[f - 1][i] for i in range(3)] for f in range(1, len(track) - 1)]
        for k in range(1, len(acc)):
            a, b = acc[k], acc[k - 1]
            z = min(math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))) if sum(a[i] * b[i] for i in range(3)) < 0 else 0.0
            t = times[k + 1]
            part = "start" if t <= t0 + edge_s + 1e-6 else "end" if t >= t1 - edge_s - 1e-6 else "middle"
            parts[part].append(z / scale)
    every = parts["start"] + parts["middle"] + parts["end"]
    return {**{k: _r(percentile(v, 0.95), 3) for k, v in parts.items()}, "max": _r(max(every) if every else None, 3), "joints": len(tracks)}


def wrist_bend(elbow: list, hand: list, finger: list) -> dict:
    """손목 굽힘(°) = 아래팔(팔꿈치 → 손목)과 손(손목 → 중지 첫 마디) 방향의 각 — 2차 보조 손 116° 꺾임(소견 ③)을 잰 정의."""
    out = []
    for e, h, f in zip(elbow, hand, finger):
        a, b = [h[i] - e[i] for i in range(3)], [f[i] - h[i] for i in range(3)]
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        if na > 1e-9 and nb > 1e-9:
            out.append(math.degrees(math.acos(max(-1.0, min(1.0, sum(a[i] * b[i] for i in range(3)) / (na * nb))))))
    return {"p50": _r(percentile(out, 0.5), 1), "p95": _r(percentile(out, 0.95), 1), "max": _r(max(out) if out else None, 1)}


def contact_slide(track: list, contacts: list[bool], times: list[float], up: int, scale: float = 1.0) -> dict:
    """접지 발 미끄러짐 = 앞 · 뒤 표본이 모두 접지인 구간의 발목 수평 속도(cm/s, / scale) p95 · 최대 — 접지 라벨이 있는 쪽(Kimodo)만."""
    v = []
    for i in range(1, min(len(track), len(contacts), len(times))):
        dt = times[i] - times[i - 1]
        if contacts[i] and contacts[i - 1] and dt > 1e-9:
            dx, dy = _horizontal([track[i][k] - track[i - 1][k] for k in range(3)], up)
            v.append(math.hypot(dx, dy) / dt / scale)
    return {"frames": len(v), "p95": _r(percentile(v, 0.95)), "max": _r(max(v) if v else None)}


def measure(tracks: dict, times: list[float], *, up: int, scale: float = 1.0, window=None, spacing_cm: float | None = None,
            tolerance_cm: float = GRIP_TOL_CM, hand_points: list[list] | None = None) -> dict:
    """역할별 위치(cm) → {grip, stance, swing, attack, jitter, wrist_bend, cross, head}. 빠진 역할의 지표는 None. spacing_cm · tolerance_cm = 이
    골격 cm 의 파지 간격 · 허용(grip_spacing — 생성 골격 또는 대상, grip_band). hand_points = 손-머리 근접에 손목과 함께 쓰는 손 점 트랙(없으면
    finger_l · finger_r 역할) — Kimodo · Vesper 가 같은 정의로 잰다."""
    have = {r for r in ROLES + OPTIONAL_ROLES if tracks.get(r)}
    out = {"version": VERSION, "scale": _r(scale, 4), "samples": len(times), "grip": None, "stance": None, "swing": None, "attack": None,
           "jitter": None, "wrist_bend": None, "cross": None, "head": None}
    if {"hand_l", "hand_r"} <= have:
        out["grip"] = grip(tracks["hand_l"], tracks["hand_r"], times, scale, window, spacing_cm, tolerance_cm)
        out["swing"] = swing(tracks["hand_l"], tracks["hand_r"], times, scale)
        if tracks.get(HEAD_ROLE):
            extra = hand_points if hand_points is not None else [tracks[r] for r in OPTIONAL_ROLES if r in have]
            out["head"] = head_near([tracks["hand_l"], tracks["hand_r"]] + [p for p in extra if p], tracks[HEAD_ROLE], times, scale)
    if {"hand_l", "hand_r", "hip_l", "hip_r"} <= have:
        out["cross"] = arm_cross(tracks["hand_l"], tracks["hand_r"], tracks["hip_l"], tracks["hip_r"], times, up, scale)
    if {"foot_l", "foot_r", "hip_l", "hip_r"} <= have:
        out["stance"] = stance(tracks["foot_l"], tracks["foot_r"], tracks["hip_l"], tracks["hip_r"], up)
    if {"hand_l", "hand_r", "hip_l", "hip_r", "shoulder_l", "shoulder_r", "elbow_l", "elbow_r"} <= have:
        out["attack"] = attack(tracks, times, up)
    if have:
        out["jitter"] = zigzag([tracks[r] for r in ROLES + OPTIONAL_ROLES if r in have], times, scale)
    bend = {s: wrist_bend(tracks[f"elbow_{s}"], tracks[f"hand_{s}"], tracks[f"finger_{s}"]) for s in ("l", "r")
            if {f"elbow_{s}", f"hand_{s}", f"finger_{s}"} <= have}
    out["wrist_bend"] = bend or None
    return out


def non_grip(hand_l: list, hand_r: list, times: list[float], scale: float, penetration_pct: float | None, worst_time: float | None,
             window=None, spacing_cm: float | None = None, tolerance_cm: float = GRIP_TOL_CM) -> dict:
    """비파지 프레임 관통의 상한(사용자 결정 2 — 기록만, 점수 밖). 검증기는 프레임별 관통을 내지 않으므로(% · 깊이 분포 · 최악 프레임뿐)
    상한 = min(비파지 프레임 %, 관통 %). 최악 프레임이 파지 프레임인지도 적는다(가장 가까운 표본으로)."""
    g = grip(hand_l, hand_r, times, scale, window, spacing_cm, tolerance_cm)
    pct = g["grip_pct"]
    non = None if pct is None else _r(100.0 - pct, 1)
    upper = None if non is None or penetration_pct is None else _r(min(non, penetration_pct), 1)
    worst_in = None
    if worst_time is not None and times and penetration_pct:
        i = min(range(len(times)), key=lambda k: abs(times[k] - worst_time))
        lo, hi = grip_band(scale, spacing_cm, tolerance_cm)
        worst_in = lo <= _dist(hand_l[i], hand_r[i]) <= hi
    return {"grip_pct": pct, "non_grip_frames_pct": non, "penetration_pct": penetration_pct, "non_grip_penetration_pct_max": upper,
            "worst_in_grip": worst_in}
