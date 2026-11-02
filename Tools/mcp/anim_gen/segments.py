"""세그먼트 생성 (Phase 9-2 — 후속 로드맵 U2-a, 지침서 §11 · §14 Phase 9 '9-2') — 프레임 · 경계 · 시각 사상 · 이음매 수치 · 몽타주 섹션.

요청 segments[{prompt, duration_seconds, name?, swing?}](2 ~ 6개, prompt 대신) → local_ai 한 Kimodo 실행에 프롬프트 · 프레임 목록 ·
num_transition_frames(generation.transition_frames). Kimodo _multiprompt: 둘째 세그먼트부터 길이 N + T 로 만들고 처음 T 프레임에 앞 세그먼트
끝 T 프레임의 전신 + 손발 자세 제약을 걸어 그 T 프레임을 대신한다 — 이은 총 프레임 = 세그먼트 프레임 합, 전역 제약(root_path · keep_pose ·
2차 파지 · 발 · root2d)은 crop_move 로 이은 타임라인 프레임 번호 그대로.

이음매 수치 — 경계 시각마다(C++ validate_animation seams 의 SeamStepRatio 와 같은 꼴: 이음매 = 들어가는 · 나오는 단계 중 큰 값, 분모 = 앞 4 ·
뒤 4 단계 중앙값 중 큰 값, 바닥 = 클립 중앙값 × 0.25):
- 회전 단계 비(rotation_step_ratio) — Kimodo 쪽(관절 로컬 회전 평균 변화)은 여기서, Vesper 쪽은 C++ SEAM_JUMP(같은 식)
- 손 · 발 · 골반 · 루트 속도: 앞뒤 비(speed_ratio — 이음매 앞 3 · 뒤 3 표본 속도 중앙값의 큰 쪽 ÷ 작은 쪽, 기록) · 속도 변화 비
  (speed_step_ratio — |Δv| 에 같은 꼴, 판정 ≤ SEAM_RATIO_MAX)
순수 Python(pytest 대상) — kimodo_run(Kimodo venv) · 이음매 단계 · 통합 테스트가 같은 정의를 쓴다.

Phase 9-3c (U2-b — Provider 를 섞은 세그먼트): segments[] 에 기존 애셋 구간({source: existing, asset, start?, end?})을 섞는다. 생성 세그먼트(붙어 있는
덩어리 하나)는 한 Kimodo 실행 — 기존 이웃이 있는 쪽은 겹칠 K = 전이 − 1 프레임만큼 생성을 늘리고, 그 T(= K + 1) 프레임에 이웃 끝(앞) · 첫(뒤) T
프레임 자세를 자동 전신 키로 준다(Kimodo _multiprompt 전이와 같은 규칙 — 자세와 속도가 함께 이어진다). join 단계가 그 겹친 구간을 크로스페이드로 잇는다.
"""
from __future__ import annotations

import math

from . import timing

MIN_SEGMENTS, MAX_SEGMENTS = 2, 6
MIN_SEGMENT_S = 0.5            # 15 프레임 @ 30 fps — 전이(≤ 10)보다 길게
MAX_TOTAL_S = 10.0             # Kimodo 모델 카드 300 프레임(local_ai MAX_FRAMES) — 합계도 같은 상한
TRANSITION_DEFAULT = 5         # Kimodo 기본(0.17초 @ 30 fps)
TRANSITION_RANGE = (1, 10)     # Kimodo 데모 UI 슬라이더 범위
SEAM_RATIO_MAX = 3.0           # C++ FThresholds::SeamRatioMax 와 같은 값(SEAM_JUMP)
STEP_WINDOW = 4                # C++ SeamStepRatio Window
SPEED_SIDE = 3                 # 앞뒤 비 — 이음매 앞 · 뒤 표본 수
SPEED_FLOOR_CM_S = 5.0         # 속도 변화 비의 분모 바닥(cm/s × scale) — 멈춘 발 · 골반에서 비가 터지지 않게
ROLES = ("hand_l", "hand_r", "foot_l", "foot_r", "pelvis", "root")
ROUND = 4
# Phase 9-3c — 섞은 세그먼트
SOURCES = ("generate", "existing")
MIXED_TRANSITION_MIN = 2       # 겹침 K = 전이 − 1 ≥ 1 프레임(크로스페이드 · 골반 맞춤 표본이 있어야 한다)
GAP_ROLES = ("hand_l", "hand_r", "foot_l", "foot_r", "pelvis", "head")   # 겹친 구간 자세 차를 재는 역할(이음매 측정 본)


def default_name(index: int) -> str:
    return f"Seg{index + 1}"


def plan_frames(durations: list[float], fps: float) -> dict:
    """세그먼트 길이(초) → {frames[], start_frame[], total_frames, boundaries_s[], starts_s[], ends_s[], length_s}. 세그먼트 i = round(길이 × fps),
    마지막만 + 1(local_ai 의 '길이 = (프레임 − 1) / fps' 규칙 — 한 프롬프트와 같은 총 길이). 경계 = 둘째 세그먼트부터의 시작 프레임 / fps."""
    frames = [max(1, int(round(d * fps))) for d in durations]
    frames[-1] += 1
    starts, acc = [], 0
    for n in frames:
        starts.append(acc)
        acc += n
    total = acc
    ends = [s + n for s, n in zip(starts, frames)]
    ends[-1] = total - 1
    return {"frames": frames, "start_frame": starts, "total_frames": total,
            "starts_s": [round(s / fps, ROUND) for s in starts], "ends_s": [round(e / fps, ROUND) for e in ends],
            "boundaries_s": [round(s / fps, ROUND) for s in starts[1:]], "length_s": round((total - 1) / fps, ROUND)}


def swing_window(segments: list[dict], starts_s: list[float], ends_s: list[float], transition_frames: int, fps: float) -> list[float] | None:
    """swing 표시 세그먼트 → fix.timing 정점 탐색 창(초) = 그 세그먼트 ± 전이(앞 끝 자세를 잇는 T 프레임 — 휘두름이 경계에 걸칠 수 있다)."""
    k = next((i for i, s in enumerate(segments) if s.get("swing")), None)
    if k is None:
        return None
    pad = transition_frames / fps
    return [round(max(0.0, starts_s[k] - pad), ROUND), round(ends_s[k] + pad, ROUND)]


def map_times(times: list[float], warp: list[list[float]] | None) -> list[float]:
    """생성 타임라인 시각 → 최종 타임라인(시간 보정 warp — timing.plan 의 [[원, 새, 배율]…]). warp 가 없으면 그대로. 자른 머리 · 꼬리 안은 처음 · 끝."""
    if not warp:
        return [round(t, ROUND) for t in times]
    return [round(timing.warp_time(warp, t), ROUND) for t in times]


def sections(names: list[str], starts_s: list[float], length_s: float, fps: float) -> tuple[list[dict], list[dict]]:
    """세그먼트 이름 · 최종 시작 시각 → 몽타주 섹션[{name, start, next}](next = 다음 섹션 — 끝까지 이어 재생, 마지막 null) · 건너뛴 것.
    첫 섹션은 0. 시간 보정 트림이 세그먼트를 지워 시작이 앞 섹션 + 1 프레임 안이거나 끝을 넘으면 그 섹션을 건너뛴다."""
    out, skipped = [], []
    for i, (name, start) in enumerate(zip(names, starts_s)):
        start = 0.0 if i == 0 else round(start, ROUND)
        if out and (start <= out[-1]["start"] + 1.0 / fps - 1e-6 or start >= length_s - 1e-6):
            skipped.append({"name": name, "start": start, "reason": "COLLAPSED_BY_TIMING"})
            continue
        out.append({"name": name, "start": start, "next": None})
    for a, b in zip(out, out[1:]):
        a["next"] = b["name"]
    return out, skipped


def _median(values: list[float]) -> float | None:
    v = sorted(values)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else 0.5 * (v[m - 1] + v[m])


def step_ratio(steps: list[float], k: int, floor_abs: float = 1e-3) -> float | None:
    """C++ SeamStepRatio 와 같은 식 — steps[i] = i → i+1 단계 크기, k = 이음매 프레임: 이음매 = max(steps[k−1], steps[k]), 분모 = 앞 4 · 뒤 4
    중앙값 중 큰 값(바닥 = 전체 중앙값 × 0.25 · floor_abs)."""
    if not steps:
        return None
    first, last = min(max(k - 1, 0), len(steps) - 1), min(max(k, 0), len(steps) - 1)
    seam = max(steps[first:last + 1])
    before = steps[max(0, first - STEP_WINDOW):first]
    after = steps[last + 1:last + 1 + STEP_WINDOW]
    floor = max((_median(steps) or 0.0) * 0.25, floor_abs)
    den = max(_median(before) or 0.0, _median(after) or 0.0, floor)
    return round(seam / den, 2)


def _sample_index(times: list[float], t: float) -> int | None:
    """표본 시각(구간 끝 — validate_animation profile 규약) 중 이음매 시각 이후 첫 표본 = 이음매로 들어가는 단계."""
    for k, x in enumerate(times):
        if x >= t - 1e-6:
            return k
    return None


def speed_seams(times: list[float], speeds: dict[str, list[float]], seam_times: list[float], scale: float = 1.0) -> list[dict]:
    """역할별 속도 열(cm/s — times[k] = 단계 k 의 끝 시각, validate_animation profile 규약) → 이음매마다 {time, roles{역할: {before, after,
    speed_ratio, speed_step_ratio}}, speed_step_ratio_max}. scale = pelvis 높이 / 100(바닥 크기)."""
    out = []
    for t in seam_times:
        k = _sample_index(times, t)
        row = {"time": round(t, ROUND), "roles": {}}
        if k is None or k == 0:
            row["reason"] = "OUT_OF_RANGE"
            out.append(row)
            continue
        for role, v in speeds.items():
            if not v:
                continue
            before = v[max(0, k - SPEED_SIDE):k]
            after = v[k + 1:k + 1 + SPEED_SIDE]
            vb, va = _median(before), _median(after)
            ratio = None
            if vb is not None and va is not None:
                lo = max(min(vb, va), SPEED_FLOOR_CM_S * scale)
                ratio = round(max(vb, va) / lo, 2)
            dv = [abs(v[i] - v[i - 1]) for i in range(1, len(v))]   # dv[i − 1] = 단계 i − 1 → i 의 속도 변화
            # 이음매로 들어가는 단계 k 의 속도가 튀면 dv[k − 1](k − 1 → k) · dv[k](k → k + 1) 둘 다 커진다 — step_ratio 의 k 자리 = k
            ssr = step_ratio(dv, k, SPEED_FLOOR_CM_S * scale) if dv else None
            row["roles"][role] = {"before_cm_s": round(vb / scale, 1) if vb is not None else None,
                                  "after_cm_s": round(va / scale, 1) if va is not None else None, "speed_ratio": ratio, "speed_step_ratio": ssr}
        vals = [r["speed_step_ratio"] for r in row["roles"].values() if r["speed_step_ratio"] is not None]
        row["speed_step_ratio_max"] = max(vals) if vals else None
        out.append(row)
    return out


def worst(rows: list[dict], key: str) -> float | None:
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


# ---- Phase 9-3c — 섞은 세그먼트 ----
def is_mixed(segs: list[dict] | None) -> bool:
    return any(s.get("source") == "existing" for s in segs or [])


def layout(segs: list[dict]) -> dict:
    """세그먼트 순서 → {generated[인덱스], lead(생성 덩어리 바로 앞 기존 인덱스 | None), trail(바로 뒤 | None)} — 요청 검사가 덩어리 하나를 보장한다."""
    gen = [i for i, s in enumerate(segs) if s.get("source", "generate") == "generate"]
    lead = gen[0] - 1 if gen and gen[0] > 0 else None
    trail = gen[-1] + 1 if gen and gen[-1] + 1 < len(segs) else None
    return {"generated": gen, "lead": lead, "trail": trail}


def overlap_frames(transition_frames: int) -> int:
    """기존 ↔ 생성 이음매의 겹침 K(생성 fps 프레임) — 전이 T 프레임을 겹쳐 키로 묶으면 그 사이 간격이 T − 1(Kimodo 전이와 같은 수)."""
    return max(1, int(transition_frames) - 1)


def mixed_frames(durations: list[float], lead: bool, trail: bool, overlap: int, fps: float) -> dict:
    """생성 세그먼트 길이 → plan_frames, 기존 이웃이 있는 쪽 세그먼트를 겹침 K 프레임만큼 늘린다(요청 길이 = 새 동작 — 겹친 키 프레임은 이웃 자세)."""
    d = list(durations)
    if lead:
        d[0] += overlap / fps
    if trail:
        d[-1] += overlap / fps
    return plan_frames(d, fps)


def seam_key_constraints(lead: dict | None, trail: dict | None, total_frames: int, overlap: int, fps: float) -> list[dict]:
    """이음매 자동 키(요청 key_pose 꼴 + source 이름) — 앞 이웃 끝 K + 1 프레임 → 생성 프레임 0 ~ K(origin), 뒤 이웃 첫 K + 1 프레임 → 생성 끝 K + 1 프레임
    (pass1). 이웃 = {index, asset, start, end}(초 — end 는 계획이 잰 값). 원천 시각 간격 = 생성 프레임 간격(1/fps)."""
    out = []
    if lead is not None:
        out.append({"type": "key_pose", "source": f"segments[{lead['index']}].seam", "asset": lead["asset"], "part": "full", "placement": "origin",
                    "times": [round(lead["end"] - (overlap - i) / fps, 6) for i in range(overlap + 1)],
                    "at": [round(i / fps, 6) for i in range(overlap + 1)]})
    if trail is not None:
        first = total_frames - 1 - overlap
        out.append({"type": "key_pose", "source": f"segments[{trail['index']}].seam", "asset": trail["asset"], "part": "full", "placement": "pass1",
                    "times": [round(trail["start"] + i / fps, 6) for i in range(overlap + 1)],
                    "at": [round((first + i) / fps, 6) for i in range(overlap + 1)]})
    return out


def heading_deg(hip_l: list[float], hip_r: list[float]) -> float:
    """몸 방향(UE 컴포넌트 xy) — 왼 → 오른 엉덩 관절 벡터의 각(°). 두 자세의 차만 쓴다(rotate_root yaw 와 같은 부호 — x → y 가 +)."""
    return math.degrees(math.atan2(hip_r[1] - hip_l[1], hip_r[0] - hip_l[0]))


def wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def sample_index(times: list[float], t: float) -> int:
    """profile 표본(시각 = 구간 끝, 프레임 1 부터) 중 t 에 가장 가까운 것 — 프레임 0 은 표본이 없어 첫 표본."""
    return min(range(len(times)), key=lambda i: abs(times[i] - t))


def overlap_pairs(prev: dict, nxt: dict, prev_end: float, nxt_start: float, blend: float, steps: int) -> list[tuple[int, int]]:
    """겹친 구간의 같은 비율 시각 표본 짝(앞 [끝 − blend, 끝] ↔ 뒤 [시작, 시작 + blend]). profile 은 프레임 0 표본이 없다 — 반 표본 간격 밖이면
    (그 시각 표본 없음) 그 단계는 뺀다."""
    def near(times: list[float], t: float) -> int | None:
        k = sample_index(times, t)
        half = 0.5 * ((times[1] - times[0]) if len(times) > 1 else 1.0 / 30.0) + 1e-6
        return k if abs(times[k] - t) <= half else None
    out = []
    for i in range(steps + 1):
        a = near(prev["times"], prev_end - blend + blend * i / steps)
        b = near(nxt["times"], nxt_start + blend * i / steps)
        if a is not None and b is not None:
            out.append((a, b))
    return out


def overlap_fit(prev: dict, nxt: dict, pairs: list[tuple[int, int]]) -> dict | None:
    """겹친 구간 전체로 맞춤 — 몸 방향 차(앞 − 뒤, 엉덩 관절 선)의 원형 평균(°) · 골반 수평 차(앞 + shift − 뒤)의 평균(cm). 한 순간이 아니라 구간 평균이라
    크로스페이드 동안 두 궤적이 가장 덜 어긋난다(M1 실측: 겹침 끝 한 순간 맞춤은 뒤 이음매 자세 차 p50 1.6 cm 에 골반 궤적 차가 더해져 3.5 cm)."""
    if not pairs:
        return None
    s = c = 0.0
    dx = dy = 0.0
    for a, b in pairs:
        pa, pb = prev["pos"], nxt["pos"]
        d = math.radians(heading_deg(pa["hip_l"][a], pa["hip_r"][a]) - heading_deg(pb["hip_l"][b], pb["hip_r"][b]))
        s, c = s + math.sin(d), c + math.cos(d)
        dx += pa["pelvis"][a][0] + prev["shift"][0] - pb["pelvis"][b][0] - nxt["shift"][0]
        dy += pa["pelvis"][a][1] + prev["shift"][1] - pb["pelvis"][b][1] - nxt["shift"][1]
    n = len(pairs)
    return {"yaw_deg": math.degrees(math.atan2(s, c)), "shift": [dx / n, dy / n], "samples": n}


def overlap_gap(prev: dict, nxt: dict, prev_end: float, nxt_start: float, blend: float, steps: int, roles=GAP_ROLES) -> dict | None:
    """겹친 구간 자세 차(cm) — 앞 조각 [끝 − blend, 끝] ↔ 뒤 조각 [시작, 시작 + blend] 의 같은 비율 시각, 역할 관절 위치(이은 좌표 — 조각마다 shift 를 더한다).
    prev · nxt = {times, pos{역할: [[x, y, z]…]}, shift[x, y]}. 키를 준 이음매는 거의 0(같은 자세), 대조(키 없음)는 두 동작의 차."""
    values = []
    for a, b in overlap_pairs(prev, nxt, prev_end, nxt_start, blend, steps):
        for role in roles:
            pa, pb = (prev["pos"].get(role) or [None] * (a + 1))[a], (nxt["pos"].get(role) or [None] * (b + 1))[b]
            if pa is None or pb is None:
                continue
            pa = [pa[0] + prev["shift"][0], pa[1] + prev["shift"][1], pa[2]]
            pb = [pb[0] + nxt["shift"][0], pb[1] + nxt["shift"][1], pb[2]]
            values.append(math.dist(pa, pb))
    if not values:
        return None
    s = sorted(values)
    return {"p50": round(_median(s), 2), "max": round(s[-1], 2), "samples": len(values)}
