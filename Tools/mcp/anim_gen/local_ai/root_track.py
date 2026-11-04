"""Kimodo BVH 의 루트 트랙 (Phase 5 — 스파이크 정정 2).

Kimodo 의 BVH 내보내기(kimodo/exports/bvh.py)는 원점에 고정된 래퍼 'Root'(채널 전부 0) 아래 'Hips' 에 전역 위치 · 회전을 쓴다.
그대로 리타깃하면 리타기터 Root Motion op 가 소스 루트(정지)를 복사해 대상 루트는 원점에 남고 골반만 걸어 나간다(스파이크
root_travel_cm 0). 리타기터 op 설정을 바꾸면 Phase 1~4 의 모든 경로가 달라지므로, Kimodo 출력 안에서 고친다:

  Root = 모델 출력의 바닥 궤적 smooth_root_pos (x, z) · 방향 global_root_heading (cos θ, sin θ)
  Hips = Root 기준 상대값  p' = R_y(θ)ᵀ (p − r),  R' = R_y(θ)ᵀ R

θ 는 정면(+Z)에서 왼쪽(+X)으로 잰 Y 축 회전(kimodo motion_rep.feature_utils.compute_heading_angle — 오른쪽 엉덩이 − 왼쪽 엉덩이의
atan2(dz, −dx)). BVH 회전 채널 'Zrotation Yrotation Xrotation' 은 R = Rz · Ry · Rx 이고, 위치 채널은 부모 공간의 절대 위치다
(Blender BVH 임포터가 기준 머리를 빼서 포즈 이동으로 쓴다).
"""
from __future__ import annotations

import math

ROOT_CHANNELS = ["Xposition", "Yposition", "Zposition", "Zrotation", "Yrotation", "Xrotation"]


class RootTrackError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---- 3×3 행렬 (리스트) ----
def _rx(deg: float) -> list[list[float]]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def rot_y(deg: float) -> list[list[float]]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _rz(deg: float) -> list[list[float]]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def matmul(a, b) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def transpose(a) -> list[list[float]]:
    return [[a[j][i] for j in range(3)] for i in range(3)]


def apply(m, v) -> list[float]:
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def euler_zyx_to_matrix(z: float, y: float, x: float) -> list[list[float]]:
    """BVH 'Zrotation Yrotation Xrotation' (도) → R = Rz · Ry · Rx."""
    return matmul(matmul(_rz(z), rot_y(y)), _rx(x))


def matrix_to_euler_zyx(m) -> tuple[float, float, float]:
    """R = Rz(a) · Ry(b) · Rx(c) → (a, b, c) 도. b = ±90° 근처(짐벌)는 c = 0 으로 둔다."""
    sb = max(-1.0, min(1.0, -m[2][0]))
    b = math.asin(sb)
    if abs(sb) < 1.0 - 1e-9:
        a = math.atan2(m[1][0], m[0][0])
        c = math.atan2(m[2][1], m[2][2])
    else:
        a = math.atan2(-m[0][1], m[1][1])
        c = 0.0
    return math.degrees(a), math.degrees(b), math.degrees(c)


def heading_deg(cos_sin: list[list[float]]) -> list[float]:
    """global_root_heading (cos θ, sin θ) → θ (도), 이어지게 펼친다(±180° 넘어가며 튀지 않게)."""
    out: list[float] = []
    for c, s in cos_sin:
        a = math.degrees(math.atan2(s, c))
        if out:
            while a - out[-1] > 180.0:
                a -= 360.0
            while a - out[-1] < -180.0:
                a += 360.0
        out.append(a)
    return out


# ---- BVH 텍스트 ----
def _structure(lines: list[str]) -> tuple[int, int]:
    """'ROOT Root' 바로 아래 첫 관절이 'Hips' 이고 둘 다 위치 3 + 회전 ZYX 3 채널인지 본다 → (MOTION 줄 번호, 첫 데이터 줄 번호)."""
    names, channels = [], []
    motion = None
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith(("ROOT", "JOINT")):
            names.append(line.split(None, 1)[1].strip() if len(line.split()) > 1 else "")
        elif line.startswith("CHANNELS") and len(channels) < 2:
            channels.append(line.split()[2:])
        elif line == "MOTION":
            motion = i
            break
    if motion is None:
        raise RootTrackError("BAD_BVH", "no MOTION section")
    if names[:2] != ["Root", "Hips"] or channels[:2] != [ROOT_CHANNELS, ROOT_CHANNELS]:
        raise RootTrackError("UNEXPECTED_HIERARCHY", f"expected ROOT Root → JOINT Hips with {' '.join(ROOT_CHANNELS)} channels, got "
                             f"{names[:2]} {channels[:2]} — the Kimodo BVH layout changed")
    first = motion + 3  # MOTION · Frames: · Frame Time:
    if first > len(lines) or not lines[motion + 1].strip().startswith("Frames:"):
        raise RootTrackError("BAD_BVH", "MOTION needs 'Frames:' and 'Frame Time:' lines")
    return motion, first


def apply_root_track(text: str, root_xz_cm: list[tuple[float, float]], heading: list[float], precision: int = 6) -> tuple[str, dict]:
    """Root 에 (x, 0, z) · Y 회전 θ 를 넣고 Hips 를 Root 기준으로 바꾼 BVH 텍스트와 통계 {frames, root_travel_cm, heading_delta_deg}."""
    lines = text.splitlines()
    _, first = _structure(lines)
    rows = [ln for ln in lines[first:] if ln.strip()]
    if len(rows) != len(root_xz_cm) or len(rows) != len(heading):
        raise RootTrackError("FRAME_COUNT_MISMATCH", f"{len(rows)} BVH frames, {len(root_xz_cm)} root positions, {len(heading)} headings")
    out_rows, travel, prev = [], 0.0, None
    for row, (x, z), theta in zip(rows, root_xz_cm, heading):
        values = row.split()
        if len(values) < 12:
            raise RootTrackError("BAD_BVH", f"a frame has {len(values)} values (< 12)")
        r0, h0 = [float(v) for v in values[0:6]], [float(v) for v in values[6:12]]
        # 지금 Hips 의 전역(부모 = Root 의 현재 채널) — Kimodo 는 Root 를 0 으로 쓰지만 일반식으로 합친다
        root_rot = euler_zyx_to_matrix(r0[3], r0[4], r0[5])
        hips_pos = [r0[k] + v for k, v in enumerate(apply(root_rot, h0[0:3]))]
        hips_rot = matmul(root_rot, euler_zyx_to_matrix(h0[3], h0[4], h0[5]))
        inv = transpose(rot_y(theta))
        local_pos = apply(inv, [hips_pos[0] - x, hips_pos[1], hips_pos[2] - z])
        lz, ly, lx = matrix_to_euler_zyx(matmul(inv, hips_rot))
        new = [x, 0.0, z, 0.0, theta, 0.0, *local_pos, lz, ly, lx]
        out_rows.append(" ".join(f"{v:.{precision}f}" for v in new) + (" " + " ".join(values[12:]) if len(values) > 12 else ""))
        if prev is not None:
            travel += math.hypot(x - prev[0], z - prev[1])
        prev = (x, z)
    stats = {"frames": len(rows), "root_travel_cm": round(travel, 2),
             "root_displacement_cm": round(math.hypot(root_xz_cm[-1][0] - root_xz_cm[0][0], root_xz_cm[-1][1] - root_xz_cm[0][1]), 2),
             "heading_delta_deg": round(heading[-1] - heading[0], 2)}
    return "\n".join(lines[:first] + out_rows) + "\n", stats
