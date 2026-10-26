"""Kimodo 2차 생성(refine)의 자동 제약 — 1차 결과 → 양손 파지 · 발 접지 · 루트 (Phase 8-1, 지침서 §14 Phase 8).

요청 플래그(constraints.two_hand_weapon_grip · foot_contact)를 Kimodo 제약으로 바꾼다: 같은 seed 로 1차 생성 → 이 모듈이 1차 결과로 목표를 계산 →
같은 seed 로 2차 생성(요청 제약 + 자동 제약). kimodo_run.py(Kimodo venv)가 부르고, 계획 단계(plan)는 local_ai Provider 가 부른다(모델을 띄우지
않는다). 순수 Python(리스트 수학 — MCP venv 에 numpy 가 없다), pytest 대상. 위치 단위는 입력 그대로(Kimodo m) — cm 값은 unit_cm 으로 바꾼다.

Kimodo 사실(소스 확인 · 스파이크, 2026-10-26 — D:/AnimGenModels/Kimodo/src/kimodo/kimodo/):
- EndEffectorConstraintSet(constraints.py:328-) 은 전역 위치 · 회전을 받는다. 확산 조건 = 손 관절 위치(SOMA30 {Side}Hand · {Side}HandMiddleEnd) +
  손 회전 + 같은 프레임의 루트 2D · 높이 · 정면(엉덩 관절 두 점 — 상체 비틀기는 자유).
- 후처리(post_processing)는 마스크를 클래스 이름(fullbody · left-hand · right-hand · left-foot · right-foot · root2d)으로만 만들고, 고정 목표는
  제약의 '전역 회전'을 FK 로 다시 푼 포즈(루트 xz = 매끈한 루트)에서 얻는다(postprocess.py extract_input_motion_from_constraints). 스파이크:
  손을 left-hand · right-hand 로 고정하면 처음 · 끝 12프레임이 1차 손 간격으로 되돌아가고, 발을 고정하면 목표가 매끈한 루트만큼 어긋나 미끄러진다
  → 손 · 발은 일반 end-effector(joint_names)로 넣어 확산 조건만 건다(후처리는 표준 접지 정리만). 그래도 제약 포즈는 팔 2본 IK(two_bone)로 FK 와
  맞춘다(손 회전 · 손 끝 위치가 팔과 어긋나지 않는 실제 골격 포즈 — Kimodo 자체 구간 전이 제약과 같은 형식).

파지 목표 규칙: 손잡이 축 a = 1차 '주 손목(grip.lead_hand) → 보조 손목' 단위 벡터(프레임별 — 보조 손이 이미 있는 쪽, 두 손목이 AXIS_MIN_CM
안이면 주 손 너클 Index2 → Pinky2), 간격 s = 주 손 너클 폭 + 1 cm(검 손잡이 — 요청 간격이 있으면 계획이 정한 생성 골격 간격: 자루 무기는 축을
따라 수십 cm, Vesper 낫 운영 애니 양손 구간 50 ~ 78 cm. 대상 기준 grip.target_spacing_cm 은 local_ai 계획이 간격 사상(motion_metrics.gap_map)으로
생성 간격으로 바꿔 넘긴다 — 이 모듈은 생성 골격 cm 만 본다).
보조 손목 후보 = 주 손목 + a·s. meet = 두 손목을 함께 평행 이동해(최소) 보조 손목이 보조 어깨에서 팔 길이 × 0.92, 주 손목이 주 어깨에서 × 0.98 안에
들게(방향: 보조 어깨 쪽 → 안 되면 어깨 중점 쪽). lead = 주 손 궤적 그대로(도달은 모델에 맡김 — 비교용). 손 회전 = 새 아래팔 회전 × 1차 손목
로컬 회전(keep — 주 · 보조 모두, 1차 손목 굽힘 유지). 처음 규칙(보조 손 '손목 → MiddleEnd' 를 주 손에 맞추는 최소 회전 · 주 손은 전역 회전
고정)은 IK 목표에서 이미 손목을 96 ~ 99° 꺾고 2차가 116° 까지 따랐다(스파이크 2026-10-26, seed 20261025 — keep 은 최대 50°, 파지 100%).
대가 = 양손 방향 정렬 7 → 35°(1차 수준) — 손잡이를 나란히 쥐는 손 방향 · 손가락 · 무기 소켓은 8-4.
축 정정(2026-10-26 밤 — 낫 Persona '팔 꼬임 · 머리 · 배 관통'): 처음 축 = 주 손 너클 Index2 → Pinky2(새끼 쪽 = 폼멜 쪽)는 무기 없이 만든 1차의
펼친 손에서 실제 두 손목 방향과 84 ~ 128° 어긋났다. 간격 7 cm(검)에서는 목표가 조금 비켜날 뿐이지만 60 cm(낫)에서는 보조 손 목표가 몸 반대편에
찍혀 손 좌우 뒤바뀜 1차 0 ~ 5% → 목표 85 ~ 93% → 2차 46 ~ 93%, 목표 이동 p50 34 ~ 59 cm(팔 길이 1.5 ~ 2배), 손이 머리 15 cm 안 48 ~ 88% 였다
(검 실행도 목표 24 ~ 32% 뒤바뀜). 1차 두 손목 방향이면 뒤바뀜 0 ~ 5%(1차 수준) · 이동 p50 0 ~ 20 cm.

2차 출력 스무딩(smooth_sigma_frames): 손 · 발 end-effector 를 키 프레임마다 조건으로 주면 separated CFG 의 제약 항이 키 프레임 사이를 진동하며
메워 2차 결과에 프레임 진동(지그재그 p95 0.6 ~ 0.9 cm/frame², 1차 ≤ 0.08)이 생긴다. 2차 출력의 로컬 회전(쿼터니언 — 부호 연속) · 루트 위치에
가우시안 σ 1프레임 → FK(kimodo_run). 스파이크: 네 seed 모두 ≤ 0.08 · 파지 100% · 휘두름 정점 −4%(σ 2 는 −13% · 발 미끄러짐 7.9 cm/s — 과함).
"""
from __future__ import annotations

import math

FLAGS = ("two_hand_weapon_grip", "foot_contact")
SIDES = {"left": "Left", "right": "Right"}
DEFAULTS = {"mode": "auto", "grip": {"lead_hand": "right", "target": "meet", "spacing_cm": None, "target_spacing_cm": None, "from_s": None, "to_s": None},
            "keyframe_step": 3}
TARGETS = ("meet", "lead")
REACH = {"support": 0.92, "lead": 0.98}   # 팔 길이(어깨 → 팔꿈치 + 팔꿈치 → 손목) 대비 — 다 펴지 않게
SPACING_PAD_CM = 1.0                      # 너클 폭 + 1 cm = 두 손목 간격 (SOMA 6.0 → 7.0 cm)
AXIS_MIN_CM = 2.0                         # 1차 두 손목이 이보다 가까우면 방향이 잡음이라 손잡이 축 = 주 손 너클(Index2 → Pinky2)
MIN_CONTACT_FRAMES = 4                    # 이보다 짧은 접지는 건너뛴다(스치기)
SMOOTH_SIGMA_FRAMES = 1.0                 # 2차 출력 시간 스무딩(가우시안 σ, 프레임) — 1차는 건드리지 않는다
SMOOTH_TRUNCATE = 4.0                     # 커널 반경 = round(σ × 4) (scipy gaussian_filter1d 와 같은 기본)
_EPS = 1e-9


class RefineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---- 벡터 · 행렬 (리스트) ----
def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _mul(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a, fallback=None):
    n = norm(a)
    return _mul(a, 1.0 / n) if n > _EPS else (fallback or [0.0, 0.0, 0.0])


def _mv(m, v):
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)]


def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _t(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def _perpendicular(u):
    """u 에 수직인 단위 벡터 하나(가장 덜 평행한 축과의 외적)."""
    axis = min(range(3), key=lambda i: abs(u[i]))
    e = [0.0, 0.0, 0.0]
    e[axis] = 1.0
    return _unit(_cross(u, e))


def rotation_between(a, b):
    """단위 벡터 a 를 b 로 보내는 최소 회전(Rodrigues). 반대 방향이면 수직 축 둘레 180°."""
    a, b = _unit(a), _unit(b)
    c = max(-1.0, min(1.0, _dot(a, b)))
    axis = _cross(a, b)
    s = norm(axis)
    if s < 1e-12:
        if c > 0:
            return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        axis, s, c = _perpendicular(a), 1.0, -1.0
        k = axis
        angle = math.pi
    else:
        k = _mul(axis, 1.0 / s)
        angle = math.atan2(s, c)
    x, y, z = k
    cs, sn, vc = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return [[cs + x * x * vc, x * y * vc - z * sn, x * z * vc + y * sn],
            [y * x * vc + z * sn, cs + y * y * vc, y * z * vc - x * sn],
            [z * x * vc - y * sn, z * y * vc + x * sn, cs + z * z * vc]]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ---- 프레임 ----
def keyframes(first: int, last: int, step: int) -> list[int]:
    """first, first+step, … 와 끝 프레임."""
    if last < first:
        return []
    out = list(range(first, last + 1, step))
    if out[-1] != last:
        out.append(last)
    return out


def window(frames: int, fps: float, from_s: float | None, to_s: float | None) -> tuple[int, int]:
    """grip.from_s ~ to_s(초, 없으면 처음 · 끝) → 프레임 [first, last]."""
    first = 0 if from_s is None else int(round(from_s * fps))
    last = frames - 1 if to_s is None else int(round(to_s * fps))
    if not 0 <= first <= last < frames:
        raise RefineError("CONSTRAINT_OUT_OF_RANGE", f"grip window {from_s}s ~ {to_s}s is frames {first} ~ {last}, outside the {frames} generated "
                          f"frames (0 ~ {(frames - 1) / fps:.3f}s) or reversed")
    return first, last


def contact_runs(flags: list[bool], min_len: int = MIN_CONTACT_FRAMES) -> list[tuple[int, int]]:
    """연속 참 구간 [시작, 끝] 중 min_len 프레임 이상."""
    runs, start = [], None
    for i, on in enumerate(list(flags) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_len:
                runs.append((start, i - 1))
            start = None
    return runs


def foot_frames(flags: list[bool], step: int, skip=frozenset(), min_len: int = MIN_CONTACT_FRAMES) -> list[int]:
    """1차 접지 구간(≥ min_len) 안의 키 프레임 — 요청 제약이 이미 고정한 프레임(skip)은 뺀다."""
    out = []
    for a, b in contact_runs(flags, min_len):
        out += [f for f in keyframes(a, b, step) if f not in skip]
    return out


_PARTS = {"left-hand": ("left_hand",), "right-hand": ("right_hand",), "left-foot": ("left_foot",), "right-foot": ("right_foot",),
          "fullbody": ("left_hand", "right_hand", "left_foot", "right_foot", "root"), "root2d": ("root",)}
_EE_PARTS = {"LeftHand": "left_hand", "RightHand": "right_hand", "LeftFoot": "left_foot", "RightFoot": "right_foot", "Hips": "root"}


def pinned(items: list[dict]) -> dict[str, set[int]]:
    """요청 제약(Kimodo dict: type · frame_indices · joint_names?)이 이미 고정한 부위별 프레임 — 자동 제약은 그 프레임을 건너뛴다."""
    out: dict[str, set[int]] = {p: set() for p in ("left_hand", "right_hand", "left_foot", "right_foot", "root")}
    for item in items:
        parts = _PARTS.get(item.get("type"))
        if item.get("type") == "end-effector":
            parts = tuple(_EE_PARTS[j] for j in item.get("joint_names") or [] if j in _EE_PARTS)
        for part in parts or ():
            out[part] |= {int(f) for f in item.get("frame_indices") or []}
    return out


# ---- 2차 출력 스무딩 (kimodo_run 이 계획의 smooth_sigma_frames 로 부른다) ----
def gaussian_kernel(sigma: float | None, truncate: float = SMOOTH_TRUNCATE) -> list[float]:
    """정규화한 가우시안 가중치(길이 2r + 1, r = int(truncate·σ + 0.5)). σ 가 없거나 0 이하면 [1.0](스무딩 없음)."""
    if not sigma or sigma <= 0:
        return [1.0]
    r = int(truncate * sigma + 0.5)
    w = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-r, r + 1)]
    total = sum(w)
    return [x / total for x in w]


def smooth_series(values: list, sigma: float | None) -> list[list[float]]:
    """시간 축(첫 차원) 가우시안 — 값은 프레임마다 같은 길이의 수 목록. 양 끝은 대칭으로 접는다(d c b a | a b c d — scipy 'reflect')."""
    w = gaussian_kernel(sigma)
    r, n = len(w) // 2, len(values)
    if r == 0 or n == 0:
        return [list(v) for v in values]

    def at(i: int):
        while i < 0 or i >= n:
            i = -i - 1 if i < 0 else 2 * n - i - 1
        return values[i]
    dim = len(values[0])
    out = []
    for t in range(n):
        acc = [0.0] * dim
        for k, wk in enumerate(w):
            v = at(t + k - r)
            for c in range(dim):
                acc[c] += wk * v[c]
        out.append(acc)
    return out


def quat_from_matrix(m) -> list[float]:
    """회전 행렬(m·v) → 단위 쿼터니언 [w, x, y, z] (Shepperd — 가장 큰 성분 기준)."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = [0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s]
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        q = [(m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s]
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        q = [(m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s]
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        q = [(m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s]
    n = math.sqrt(sum(c * c for c in q))
    return [c / n for c in q]


def matrix_from_quat(q) -> list[list[float]]:
    """쿼터니언 [w, x, y, z](정규화한다) → 회전 행렬."""
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    w, x, y, z = (c / n for c in q)
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def smooth_rotations(mats: list, sigma: float | None) -> list:
    """프레임 × 관절 회전 행렬 [T][J][3][3] → 같은 모양. 관절마다 쿼터니언 부호를 시간 축으로 잇고(q·q_prev < 0 이면 뒤집기 — q 와 −q 는 같은
    회전이라 잇지 않으면 평균이 0 쪽으로 무너진다) 성분별 가우시안 → 정규화 → 행렬."""
    if not mats:
        return []
    joints = len(mats[0])
    out = [[None] * joints for _ in mats]
    for j in range(joints):
        qs: list[list[float]] = []
        for t in range(len(mats)):
            q = quat_from_matrix(mats[t][j])
            if qs and sum(a * b for a, b in zip(q, qs[-1])) < 0:
                q = [-c for c in q]
            qs.append(q)
        for t, q in enumerate(smooth_series(qs, sigma)):
            out[t][j] = matrix_from_quat(q)
    return out


# ---- 계획 (보이는 것 = 실행 인자) ----
def plan(flags: dict, refine: dict, *, frames: int, fps: float, requested_root: bool, spacing: dict | None = None) -> dict:
    """요청 플래그 · generation.refine → {mode, passes, rules[], keyframe_step, smooth_sigma_frames}. 변환할 플래그가 없거나 mode off 면 1차만
    (스무딩 None). 스무딩 σ 는 여기서만 정한다 — 러너(kimodo_run)는 받은 값을 쓰기만 한다. spacing = 계획이 푼 자루 무기 간격
    (motion_metrics.grip_spacing — 생성 · 대상 간격 · 띠 · 사상): 규칙 spacing_cm 은 생성 골격 간격(러너가 목표 · 소스 띠에 쓴다)."""
    step = refine["keyframe_step"]
    on = [f for f in FLAGS if (flags or {}).get(f)]
    if refine["mode"] == "off" or not on:
        return {"mode": refine["mode"], "passes": 1, "rules": [], "keyframe_step": step, "flags": on, "smooth_sigma_frames": None}
    rules = []
    if "two_hand_weapon_grip" in on:
        g = refine["grip"]
        first, last = window(frames, fps, g["from_s"], g["to_s"])
        rule = {"flag": "two_hand_weapon_grip", "kimodo": ["end-effector[LeftHand, RightHand]"],
                "frames": {"from": first, "to": last, "step": step, "count": len(keyframes(first, last, step))},
                "target": g["target"], "lead_hand": g["lead_hand"], "spacing_cm": g["spacing_cm"],
                "spacing_from": "request" if g["spacing_cm"] else f"lead knuckle width (Index2 → Pinky2, pass 1) + {SPACING_PAD_CM:g} cm",
                "axis": f"pass-1 lead wrist → support wrist, per frame (lead knuckle Index2 → Pinky2 when the wrists are < {AXIS_MIN_CM:g} cm apart)",
                "reach": dict(REACH), "pose": "two-bone IK of both arms — an FK-consistent pose; diffusion condition only (no post-process pin)"}
        if spacing:
            m = spacing["map"]
            rule.update(spacing_cm=spacing["source_cm"], target_spacing_cm=spacing["target_cm"], band_cm=spacing["source_band_cm"],
                        target_band_cm=spacing["target_band_cm"], spacing_map=m,
                        spacing_from=("request (generation skeleton)" if spacing["from"] == "source" else
                                      f"request target_spacing_cm {spacing['target_cm']:g} cm → generation {spacing['source_cm']:g} cm") +
                        f" — gap map: target = {m['target_shoulder_cm']:g} + {m['arm_ratio']:g} × (generation − {m['source_shoulder_cm']:g}) "
                        "(shoulder joints at their own width, the arm part × the arm-length ratio; grip line along the shoulder line)")
        rules.append(rule)
    if "foot_contact" in on:
        rules.append({"flag": "foot_contact", "kimodo": ["end-effector[LeftFoot]", "end-effector[RightFoot]"],
                      "frames": {"from": f"pass-1 foot_contacts runs ≥ {MIN_CONTACT_FRAMES} frames", "step": step},
                      "target": "pass-1 foot pose (post-processing keeps its own contact cleanup — forced on)"})
    if not requested_root:
        rules.append({"flag": None, "kimodo": ["root2d"], "frames": {"from": 0, "to": frames - 1, "step": step,
                                                                      "count": len(keyframes(0, frames - 1, step))},
                      "target": "pass-1 smooth root (x, z) + heading — keeps the pass-1 path and facing"})
    return {"mode": refine["mode"], "passes": 2, "rules": rules, "keyframe_step": step, "flags": on, "smooth_sigma_frames": SMOOTH_SIGMA_FRAMES,
            "smooth_target": "pass-2 output — local rotations (quaternion, sign-continuous) + root position, Gaussian in time → FK of the 77 joints "
                             "(damps the frame zigzag sparse end-effector keyframes leave; pass 1 untouched)"}


# ---- 팔 2본 IK ----
def two_bone(shoulder, elbow, wrist, r_arm, r_fore, target) -> dict:
    """어깨 고정 · 1차 팔꿈치 굽힘 평면 유지 → 손목이 target 에 닿는 팔 전역 회전. 못 닿으면 그 방향으로 다 편 곳(clamped).
    r_arm · r_fore = 위팔(어깨 관절) · 아래팔(팔꿈치 관절) 전역 회전 — FK: elbow = shoulder + r_arm·off, wrist = elbow + r_fore·off."""
    l1, l2 = norm(_sub(elbow, shoulder)), norm(_sub(wrist, elbow))
    v = _sub(target, shoulder)
    d = norm(v)
    u = _unit(v, _unit(_sub(wrist, shoulder)))
    lo, hi = abs(l1 - l2) + 1e-6 * (l1 + l2), (l1 + l2) * (1.0 - 1e-6)
    dc = min(max(d, lo), hi)
    reached = _add(shoulder, _mul(u, dc))
    e = _sub(elbow, shoulder)
    perp = _sub(e, _mul(u, _dot(e, u)))
    pole = _unit(perp) if norm(perp) > 1e-6 * l1 else _perpendicular(u)
    cos_a = max(-1.0, min(1.0, (l1 * l1 + dc * dc - l2 * l2) / (2.0 * l1 * dc)))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    new_elbow = _add(shoulder, _mul(_add(_mul(u, cos_a), _mul(pole, sin_a)), l1))
    q1 = rotation_between(_sub(elbow, shoulder), _sub(new_elbow, shoulder))
    q2 = rotation_between(_mv(q1, _sub(wrist, elbow)), _sub(reached, new_elbow))
    return {"elbow": new_elbow, "wrist": reached, "r_arm": _mm(q1, r_arm), "r_fore": _mm(_mm(q2, q1), r_fore),
            "clamped": abs(dc - d) > 1e-6 * (l1 + l2), "error": norm(_sub(reached, target))}


def _interval(p, c, r, u):
    """|p + k·u − c| ≤ r 인 k 구간 — 없으면 None."""
    w = _sub(p, c)
    b = _dot(u, w)
    disc = b * b - (_dot(w, w) - r * r)
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    return -b - sq, -b + sq


def meet_offset(lead_w, sup_w, lead_sh, sup_sh, r_lead, r_sup) -> tuple[list[float], str]:
    """두 손목을 함께 옮길 최소 평행 이동 — 이미 닿으면 0. 방향: 보조 어깨 쪽 → 어깨 중점 쪽 → (둘 다 안 되면) 중점 쪽에서 초과가 가장 작은 곳."""
    if norm(_sub(sup_w, sup_sh)) <= r_sup and norm(_sub(lead_w, lead_sh)) <= r_lead:
        return [0.0, 0.0, 0.0], "inside"
    mid = _mul(_add(lead_sh, sup_sh), 0.5)
    center = _mul(_add(lead_w, sup_w), 0.5)
    directions = (("support_shoulder", _unit(_sub(sup_sh, sup_w))), ("shoulder_mid", _unit(_sub(mid, center))))
    for kind, u in directions:
        a, b = _interval(sup_w, sup_sh, r_sup, u), _interval(lead_w, lead_sh, r_lead, u)
        if a and b:
            lo, hi = max(a[0], b[0], 0.0), min(a[1], b[1])
            if lo <= hi:
                return _mul(u, lo), kind
    u = directions[1][1]
    span = norm(_sub(mid, center))
    best = min((max(norm(_sub(_add(sup_w, _mul(u, k)), sup_sh)) - r_sup, norm(_sub(_add(lead_w, _mul(u, k)), lead_sh)) - r_lead), k)
               for k in (span * i / 50.0 for i in range(51)))
    return _mul(u, best[1]), "closest"


def _lengths(pos: dict, side: str) -> float:
    s, e, w = pos[f"{side}Arm"], pos[f"{side}ForeArm"], pos[f"{side}Hand"]
    return (sum(norm(_sub(e[f], s[f])) for f in range(len(s))) + sum(norm(_sub(w[f], e[f])) for f in range(len(s)))) / len(s)


def _angle_deg(a, b) -> float:
    na, nb = norm(a), norm(b)
    if na < _EPS or nb < _EPS:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(a, b) / (na * nb)))))


def _move_arm(pos: dict, rot: dict, side: str, f: int, target) -> tuple[dict, dict]:
    """한 팔을 IK 로 옮긴다 — 손 전역 회전 = 새 아래팔 회전 × 1차 손목 로컬 회전(keep: 손목 굽힘은 1차 그대로), 손 끝 관절(MiddleEnd ·
    ThumbEnd)은 손과 함께 강체로 → 바꾼 관절 {이름: {pos, rot}} · IK 결과. 두 팔이 같은 규칙이다."""
    shoulder, elbow, wrist = pos[f"{side}Arm"][f], pos[f"{side}ForeArm"][f], pos[f"{side}Hand"][f]
    ik = two_bone(shoulder, elbow, wrist, rot[f"{side}Arm"][f], rot[f"{side}ForeArm"][f], target)
    hand_rot = _mm(ik["r_fore"], _mm(_t(rot[f"{side}ForeArm"][f]), rot[f"{side}Hand"][f]))
    rigid = _mm(hand_rot, _t(rot[f"{side}Hand"][f]))
    changes = {f"{side}Arm": {"pos": list(shoulder), "rot": ik["r_arm"]}, f"{side}ForeArm": {"pos": ik["elbow"], "rot": ik["r_fore"]},
               f"{side}Hand": {"pos": ik["wrist"], "rot": hand_rot}}
    for child in (f"{side}HandMiddleEnd", f"{side}HandThumbEnd"):
        if child in pos:
            changes[child] = {"pos": _add(ik["wrist"], _mv(rigid, _sub(pos[child][f], wrist))), "rot": _mm(rigid, rot[child][f])}
    return changes, ik


def solve_grip(pose: dict, knuckles: dict, frames: list[int], *, lead: str = "right", target: str = "meet", spacing_cm: float | None = None,
               unit_cm: float = 100.0) -> dict:
    """1차 포즈(SOMA30 전역 위치 · 회전 — 양 팔 {Side}Arm · ForeArm · Hand · HandMiddleEnd · HandThumbEnd) · 주 손 너클(77 관절
    {Side}HandIndex2 · {Side}HandPinky2 — 기본 간격 · 손목이 겹칠 때의 축) → 프레임마다 바꿀 관절 {f: {이름: {pos, rot}}} · 목표 · 통계(cm).
    손잡이 축 = 1차 주 손목 → 보조 손목(AXIS_MIN_CM 안이면 너클 축). 통계의 뒤바뀜 % 는 어깨 축 기준(보조 손목이 주 어깨 쪽으로 넘어간 프레임)."""
    if target not in TARGETS:
        raise RefineError("BAD_TARGET", f"grip target must be one of {TARGETS}")
    lead_s, sup_s = SIDES[lead], SIDES["left" if lead == "right" else "right"]
    pos, rot = pose["pos"], pose["rot"]
    index, pinky = knuckles[f"{lead_s}HandIndex2"], knuckles[f"{lead_s}HandPinky2"]
    knuckle = sum(norm(_sub(pinky[f], index[f])) for f in range(len(index))) / len(index)
    spacing = spacing_cm / unit_cm if spacing_cm else knuckle + SPACING_PAD_CM / unit_cm
    reach_lead, reach_sup = REACH["lead"] * _lengths(pos, lead_s), REACH["support"] * _lengths(pos, sup_s)
    changes, targets = {}, {}
    moved, before, after, errors, kinds, align, bend, off = [], [], [], [], {}, [], [], []
    axis_from = {"wrist_line": 0, "knuckle": 0}
    clamped = crossed_before = crossed_after = 0
    for f in frames:
        g0 = pos[f"{lead_s}Hand"][f]
        line = _sub(pos[f"{sup_s}Hand"][f], g0)
        knuckle_axis = _unit(_sub(pinky[f], index[f]))
        if norm(line) * unit_cm >= AXIS_MIN_CM:
            axis = _unit(line)
            axis_from["wrist_line"] += 1
            off.append(_angle_deg(knuckle_axis, line))   # 처음 규칙(너클 축)이었다면 어긋났을 각 — 기록만
        else:
            axis = knuckle_axis
            axis_from["knuckle"] += 1
        sup0 = _add(g0, _mul(axis, spacing))
        sup_sh, lead_sh = pos[f"{sup_s}Arm"][f], pos[f"{lead_s}Arm"][f]
        shoulders = _sub(sup_sh, lead_sh)
        crossed_before += _dot(line, shoulders) < 0
        before.append(norm(_sub(sup0, sup_sh)) / (reach_sup / REACH["support"]))
        if target == "meet":
            d, kind = meet_offset(g0, sup0, lead_sh, sup_sh, reach_lead, reach_sup)
        else:
            d, kind = [0.0, 0.0, 0.0], "lead_fixed"
        kinds[kind] = kinds.get(kind, 0) + 1
        lead_t, sup_t = _add(g0, d), _add(sup0, d)
        frame_changes, ik = _move_arm(pos, rot, sup_s, f, sup_t)
        clamped += ik["clamped"]
        errors.append(ik["error"] * unit_cm)
        after.append(norm(_sub(ik["wrist"], sup_sh)) / (reach_sup / REACH["support"]))
        if norm(d) > _EPS:
            lead_changes, lik = _move_arm(pos, rot, lead_s, f, lead_t)
            frame_changes.update(lead_changes)
            clamped += lik["clamped"]
            errors.append(lik["error"] * unit_cm)
        changes[f] = frame_changes
        targets[f] = {"lead": frame_changes.get(f"{lead_s}Hand", {"pos": g0})["pos"], "support": ik["wrist"]}
        crossed_after += _dot(_sub(targets[f]["support"], targets[f]["lead"]), shoulders) < 0
        moved.append(norm(d) * unit_cm)
        # 목표 포즈의 손 — 양손 '손목 → MiddleEnd' 방향 차(나란히 쥐는가) · 보조 손목 굽힘(아래팔 → 손 vs 손 → MiddleEnd), 기록만
        tip = {s: frame_changes.get(f"{s}HandMiddleEnd", {"pos": pos[f"{s}HandMiddleEnd"][f]})["pos"] for s in (lead_s, sup_s)}
        lead_w = targets[f]["lead"]
        align.append(_angle_deg(_sub(tip[lead_s], lead_w), _sub(tip[sup_s], ik["wrist"])))
        bend.append(_angle_deg(_sub(ik["wrist"], ik["elbow"]), _sub(tip[sup_s], ik["wrist"])))

    def spread(v):
        return {"p50": None if not v else round(_pct(v, 0.5), 2), "max": None if not v else round(max(v), 2)}

    def share(n):
        return round(100.0 * n / len(frames), 1) if frames else None

    return {"frames": changes, "targets": targets, "lead": lead_s, "support": sup_s, "target": target, "hand_rule": "keep",
            "spacing_cm": round(spacing * unit_cm, 2), "knuckle_cm": round(knuckle * unit_cm, 2),
            "stats": {"keyframes": len(frames), "moved_cm": spread(moved), "reach_ratio_before": spread(before), "reach_ratio_after": spread(after),
                      "ik_error_cm": spread(errors), "clamped": clamped, "directions": kinds,
                      "hand_align_deg": spread(align), "support_wrist_bend_deg": spread(bend),
                      "axis_from": axis_from, "knuckle_vs_wrist_line_deg": spread(off),
                      "crossed_pct": {"pass1": share(crossed_before), "targets": share(crossed_after)}}}
