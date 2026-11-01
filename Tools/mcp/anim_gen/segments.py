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
"""
from __future__ import annotations

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
