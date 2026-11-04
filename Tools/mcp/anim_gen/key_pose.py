"""Phase 9-3 (U3) — 키 포즈 제약: 대상(Vesper) 애셋의 자세 → Kimodo(SOMA77) 제약. 순수 Python — 서버 · Kimodo 러너가 함께 쓴다.

경로(지침서 §14 '9-3'): 대상 애셋 → 역리타기터(Vesper → SOMA, 생성 Job 과 같은 리그 규칙) → SOMA 시퀀스 → validate_animation profile
(컴포넌트 회전 · 위치, 프레임 0 은 내지 않아 hold_pose 로 한 프레임 민다) → 여기서 Kimodo 로컬 회전(axis-angle) · 엉덩 위치(m).

좌표(E0 2026-11-01 실측 — 기준 포즈 오프셋 77 관절 ≤ 0.001 cm):
- UE SOMA 스켈레톤 기준 포즈 = Kimodo 표준 T 포즈(전역 회전 0)를 BVH (x, y, z) → UE (x, z, y) 로 옮긴 것(Blender bvh_to_fbx — bvh.to_ue).
- 그래서 Kimodo 전역 회전 G = S·(Q_t · Q_ref⁻¹)·S (S = y ↔ z 바꿈, 반사) — 쿼터니언으로 (x, y, z, w) → (−x, −z, −y, w).
- 위치는 UE 컴포넌트 공간(cm) = Kimodo 세계(m)를 같은 S 로 — 루트 트랙 · 바닥 맞춤은 애니의 세계 위치를 바꾸지 않는다.
- 방향(heading) = Kimodo compute_heading_angle 과 같은 식: d = RightLeg − LeftLeg, atan2(d_z, −d_x) — 0 = +Z 정면, R_y(φ) 만큼 돌리면 +φ.

배치(placement): Kimodo 제약은 그 프레임의 바닥 루트 · 방향까지 묶는다 → 항목마다 한 번의 강체(수평 이동 + yaw)로 첫 키(생성 프레임이 가장
이른 키)를 목표에 둔다 — origin(원점 · 정면 +Z — 생성 첫 프레임의 정규 원점) 또는 pass1(같은 seed 를 키 없이 만든 1차의 그 프레임 엉덩 xz ·
방향). 키 사이 상대 궤적은 원천 그대로.
"""
from __future__ import annotations

import ast
import math
import pathlib
import re

from .body_model import qconj, qmul, qnormalize

KIND = "key_pose"
PLACEMENTS = ("auto", "origin", "pass1")
ROOT_WRAPPER = "Root"          # Kimodo BVH 의 Root 래퍼 — SOMA77 관절이 아니다
HIPS = "Hips"
LEFT_HIP, RIGHT_HIP = "LeftLeg", "RightLeg"   # SOMA 의 LeftLeg = 넓적다리(엉덩 관절) — Kimodo hip_joint_idx
PROFILE_MAX_SAMPLES = 240      # validate_animation profile 표본 상한(AnimMcpAnimValidator ProfileJson) — 넘으면 몇 프레임씩 묶는다
# Kimodo 가 위치로 조건을 거는 SOMA30 관절 중 몸 — 추종 · 왕복 표의 관절(손 · 발 끝 · 눈 · 턱은 손가락 · 매핑 밖이라 뺀다)
BODY_JOINTS = ["Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head", "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
               "RightShoulder", "RightArm", "RightForeArm", "RightHand", "LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase",
               "RightLeg", "RightShin", "RightFoot", "RightToeBase"]
# 요청 part → Kimodo 제약(종류, end-effector 관절). 손 · 발은 일반 end-effector(joint_names) — 클래스 이름(left-hand …)으로 주면 Kimodo 후처리가
# 그 프레임을 고정해 앞뒤가 튄다(8-1 실측 — 감사 §18), 일반 EE 면 확산 조건만
KIMODO_PART = {"full": ("fullbody", None), "left_hand": ("end-effector", ["LeftHand"]), "right_hand": ("end-effector", ["RightHand"]),
               "left_foot": ("end-effector", ["LeftFoot"]), "right_foot": ("end-effector", ["RightFoot"])}
# part → 추종을 재는 관절(위치) · 회전도 재는 관절(손 · 발 end-effector)
PART_JOINTS = {"full": BODY_JOINTS, "left_hand": ["LeftHand"], "right_hand": ["RightHand"], "left_foot": ["LeftFoot", "LeftToeBase"],
               "right_foot": ["RightFoot", "RightToeBase"]}
PART_ROTATIONS = {"left_hand": ["LeftHand"], "right_hand": ["RightHand"], "left_foot": ["LeftFoot"], "right_foot": ["RightFoot"]}
TPOSE_FILE = ("assets", "skeletons", "somaskel77", "somaskel77_standard_tpose.bvh")
JITTER_HALF_FRAMES = 10        # 키 둘레 떨림 창(± 프레임)


class KeyPoseError(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


# ---- Kimodo 설치본의 표준 T 포즈 BVH (SOMA 스켈레톤을 Job 마다 Work 에 — 사용자 결정 ①) ----
def kimodo_package_dir(python: pathlib.Path | None) -> pathlib.Path | None:
    """Kimodo venv 의 kimodo 패키지 폴더 — 일반 설치(site-packages/kimodo) 또는 편집 설치(__editable___kimodo_*_finder.py 의 MAPPING)."""
    if not python:
        return None
    site = pathlib.Path(python).parents[1] / "Lib" / "site-packages"
    if (site / "kimodo" / "__init__.py").is_file():
        return site / "kimodo"
    for finder in sorted(site.glob("__editable___kimodo_*_finder.py")):
        match = re.search(r"^MAPPING[^=]*=\s*(\{.*?\})\s*$", finder.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
        if match:
            try:
                path = ast.literal_eval(match.group(1)).get("kimodo")
            except (ValueError, SyntaxError):
                continue
            if path and (pathlib.Path(path) / "__init__.py").is_file():
                return pathlib.Path(path)
    return None


def tpose_path(python: pathlib.Path | None) -> pathlib.Path | None:
    pkg = kimodo_package_dir(python)
    path = pkg.joinpath(*TPOSE_FILE) if pkg else None
    return path if path and path.is_file() else None


def two_frame_bvh(text: str) -> str:
    """한 프레임 BVH → 같은 줄 두 번(Blender 변환 · 기준 포즈 FBX 2프레임 — 동작 FBX 를 임포트하지 않으므로 둘 다 기준 포즈)."""
    lines = text.splitlines()
    try:
        m = next(i for i, ln in enumerate(lines) if ln.strip().upper() == "MOTION")
    except StopIteration:
        raise KeyPoseError("BAD_TPOSE", "the T-pose BVH has no MOTION section") from None
    rows = [ln for ln in lines[m + 3:] if ln.strip()]
    if not lines[m + 1].strip().lower().startswith("frames") or not rows:
        raise KeyPoseError("BAD_TPOSE", "the T-pose BVH has no frame rows")
    return "\n".join(lines[:m + 1] + ["Frames: 2", lines[m + 2], rows[0], rows[0]]) + "\n"


# ---- UE (cm · z-up · 왼손계) → Kimodo (m · y-up) ----
def ue_to_kimodo_quat(q) -> tuple:
    """회전 R_UE → S·R·S (S = y ↔ z 반사) — 축은 유사 벡터라 −S(축)."""
    return (-q[0], -q[2], -q[1], q[3])


def ue_to_kimodo_point(p) -> tuple:
    return (p[0] / 100.0, p[2] / 100.0, p[1] / 100.0)


def rotvec(q) -> list[float]:
    """쿼터니언 → 회전 벡터(라디안, |각| ≤ π) — Kimodo local_joints_rot(axis-angle)."""
    x, y, z, w = qnormalize(q)
    if w < 0.0:
        x, y, z, w = -x, -y, -z, -w
    s = math.sqrt(max(0.0, 1.0 - w * w))
    if s < 1e-12:
        return [0.0, 0.0, 0.0]
    angle = 2.0 * math.atan2(s, w)
    return [x / s * angle, y / s * angle, z / s * angle]


def from_rotvec(v) -> tuple:
    angle = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if angle < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    s = math.sin(angle / 2.0) / angle
    return (v[0] * s, v[1] * s, v[2] * s, math.cos(angle / 2.0))


def ry(angle: float) -> tuple:
    """Kimodo +Y 축 회전(오른손계 — x' = x cos + z sin, z' = −x sin + z cos)."""
    return (0.0, math.sin(angle / 2.0), 0.0, math.cos(angle / 2.0))


def rotate_y(p, angle: float) -> tuple:
    c, s = math.cos(angle), math.sin(angle)
    return (p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c)


def heading(left_hip, right_hip) -> float:
    """Kimodo compute_heading_angle — d = 오른 엉덩 − 왼 엉덩, atan2(d_z, −d_x) (0 = +Z 정면)."""
    d = (right_hip[0] - left_hip[0], right_hip[1] - left_hip[1], right_hip[2] - left_hip[2])
    return math.atan2(d[2], -d[0])


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def convert(rot: dict, pos: dict, ref: dict, parents: dict) -> dict:
    """한 프레임 SOMA(UE) 컴포넌트 회전 {본: (x, y, z, w)} · 위치 {본: cm} · 기준 포즈 컴포넌트 회전 · 부모 → Kimodo
    {rotvec{관절: [rad]}, hips_m, heading_rad}. Root 래퍼는 빼고, 부모가 래퍼(Hips)면 로컬 = 전역(Kimodo 루트 관절)."""
    glob = {}
    for bone, q in rot.items():
        if bone == ROOT_WRAPPER or bone not in ref:
            continue
        glob[bone] = qnormalize(ue_to_kimodo_quat(qnormalize(qmul(q, qconj(ref[bone])))))
    out = {}
    for bone, g in glob.items():
        parent = parents.get(bone)
        local = g if parent in (None, ROOT_WRAPPER) or parent not in glob else qmul(qconj(glob[parent]), g)
        out[bone] = [round(x, 7) for x in rotvec(local)]
    missing = [b for b in (HIPS, LEFT_HIP, RIGHT_HIP) if b not in pos or b not in out]
    if missing:
        raise KeyPoseError("KEY_POSE_JOINTS_MISSING", f"the SOMA profile has no {missing}")
    hips = ue_to_kimodo_point(pos[HIPS])
    return {"rotvec": out, "hips_m": [round(x, 7) for x in hips],
            "heading_rad": round(heading(ue_to_kimodo_point(pos[LEFT_HIP]), ue_to_kimodo_point(pos[RIGHT_HIP])), 7)}


# ---- 편집 op (profile 이 프레임 0 을 내지 않는다 — hold_pose 로 한 프레임 밀어 표본 i = 원천 프레임 first + i) ----
def edit_ops(source_frames: list[int], fps: float, total_frames: int) -> tuple[list[dict], int]:
    """→ (apply_animation_edits ops, 표본 0 의 원천 프레임). 길면(표본 상한 240 을 넘으면) 키 구간만 남긴 뒤 민다."""
    lo, hi = min(source_frames), max(source_frames)
    hold = {"op": "hold_pose", "at": 0.0, "duration": round(1.0 / fps, 6)}
    if total_frames <= PROFILE_MAX_SAMPLES:
        return [hold], 0
    if hi - lo + 1 > PROFILE_MAX_SAMPLES:
        raise KeyPoseError("KEY_POSE_SPAN_TOO_LONG", f"key frames {lo} ~ {hi} span more than {PROFILE_MAX_SAMPLES} source frames — split the item",
                           first=lo, last=hi)
    return [{"op": "trim", "start": round(lo / fps, 6), "end": round(hi / fps, 6)}, hold], lo


# ---- 배치 · Kimodo 제약 ----
def place(keys: list[dict], target: dict | None) -> tuple[list[dict], dict]:
    """키(생성 프레임 순) → 첫 키를 target{xz: [x, z], heading_rad}(None = 원점 · 정면 +Z)에 두는 강체 하나. 엉덩 관절 회전에만 yaw 를 곱한다
    (나머지는 부모 상대라 그대로). 키에 바닥 루트(smooth_xz — Kimodo 의 매끈한 엉덩 경로)가 있으면 그 점을 기준점으로 옮기고 함께 돌린다(Kimodo
    정규화 = 바닥 루트가 원점, 없으면 엉덩 xz). → (배치한 키 [{frame, rotvec, hips_m, smooth_xz?}], 배치 기록 {yaw_deg, anchor_frame, shift_m, anchor})."""
    keys = sorted(keys, key=lambda k: k["frame"])
    anchor = keys[0]
    want_h = (target or {}).get("heading_rad", 0.0)
    want_xz = (target or {}).get("xz", [0.0, 0.0])
    yaw = wrap(want_h - anchor["heading_rad"])
    smooth = all(k.get("smooth_xz") for k in keys)
    a = anchor["smooth_xz"] if smooth else [anchor["hips_m"][0], anchor["hips_m"][2]]
    q_yaw = ry(yaw)

    def move(x, z):
        rel = rotate_y((x - a[0], 0.0, z - a[1]), yaw)
        return [rel[0] + want_xz[0], rel[2] + want_xz[1]]
    out = []
    for k in keys:
        hx, hz = move(k["hips_m"][0], k["hips_m"][2])
        rv = dict(k["rotvec"])
        rv[HIPS] = [round(x, 7) for x in rotvec(qmul(q_yaw, from_rotvec(k["rotvec"][HIPS])))]
        row = {"frame": k["frame"], "rotvec": rv, "hips_m": [round(hx, 7), k["hips_m"][1], round(hz, 7)]}
        if smooth:
            row["smooth_xz"] = [round(x, 7) for x in move(*k["smooth_xz"])]
        out.append(row)
    return out, {"yaw_deg": round(math.degrees(yaw), 3), "anchor_frame": anchor["frame"], "anchor": "smooth_root" if smooth else "hips",
                 "shift_m": [round(want_xz[0] - a[0], 4), round(want_xz[1] - a[1], 4)]}


def constraint(part: str, placed: list[dict], joints: list[str]) -> dict:
    """→ Kimodo constraints.json 항목(fullbody · end-effector{joint_names} — local_joints_rot [T, J, 3] = joints 순서, 원천에 없는 관절은 0).
    바닥 루트가 있으면 smooth_root_2d(없으면 Kimodo 가 엉덩 xz 로 채운다 — 그 프레임만 바닥 루트 = 엉덩이라 경로가 꺾인다)."""
    kind, names = KIMODO_PART[part]
    out = {"type": kind, "frame_indices": [k["frame"] for k in placed],
           "local_joints_rot": [[k["rotvec"].get(j, [0.0, 0.0, 0.0]) for j in joints] for k in placed],
           "root_positions": [k["hips_m"] for k in placed]}
    if all(k.get("smooth_xz") for k in placed):
        out["smooth_root_2d"] = [k["smooth_xz"] for k in placed]
    if names:
        out["joint_names"] = list(names)
    return out


# ---- 추종 · 떨림 (Kimodo 러너 · 통합 테스트) ----
def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def spread(values: list[float], digits: int = 2) -> dict | None:
    if not values:
        return None
    return {"p50": round(_pct(values, 0.5), digits), "p95": round(_pct(values, 0.95), digits), "max": round(max(values), digits)}


def zigzag_values(track: list, lo: int, hi: int) -> list[float]:
    """프레임 지그재그(motion_metrics.zigzag 와 같은 정의 — 가속도가 앞 프레임과 반대면 min(|a_f|, |a_f−1|)) 를 [lo, hi] 프레임 안에서."""
    n = len(track)
    acc = {}
    for f in range(max(1, lo - 1), min(n - 1, hi + 1)):
        acc[f] = [track[f + 1][i] - 2.0 * track[f][i] + track[f - 1][i] for i in range(3)]
    out = []
    for f in range(max(2, lo), min(n - 1, hi + 1)):
        a, b = acc.get(f), acc.get(f - 1)
        if a is None or b is None:
            continue
        dot = sum(a[i] * b[i] for i in range(3))
        out.append(min(math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))) if dot < 0 else 0.0)
    return out


def key_jitter(tracks: list[list], frames: list[int], half: int = JITTER_HALF_FRAMES) -> float | None:
    """키 둘레 ± half 프레임의 관절 지그재그 p95(cm/프레임²) — 8-1 수정안 A 의 교훈(성긴 키가 키 사이를 진동시켰다)을 키 포즈에서 본다."""
    values = []
    for track in tracks:
        for f in frames:
            values += zigzag_values(track, f - half, f + half)
    p = _pct(values, 0.95)
    return None if p is None else round(p, 3)
