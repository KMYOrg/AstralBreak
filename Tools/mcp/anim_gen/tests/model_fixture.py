"""Phase 8-4a — C++ body_clearance model{} 모양의 작은 합성 모델(test_body_model · FakeEditor 가 같이 쓴다).

골격: root → pelvis(0, 0, 95) → spine_01(0, 0, 120) → spine_05(0, 0, 145) → upperarm_l(+18, 0, 140) → lowerarm_l(+18, 0, 114) → hand_l(+18, 0, 88),
upperarm_r 쪽은 X 를 뒤집은 짝(Vesper 처럼 몸 왼쪽 = +X). 기준 포즈의 로컬 회전은 모두 항등이라 점의 영향 로컬 위치 = 점 − 본 기준 위치.
프레임 k 에서 왼 위팔이 앞 축(+Y) 둘레로 angles[k]° 돈다(20° 면 손이 몸통 축 0.2 cm 앞까지). 몸통 지도 = 몸통 축(엉덩 중점 (0,0,95) → 척추 끝
(0,0,145)) 둘레 반경 10 cm 원통(구멍 한 칸), 머리 · 목 지도 = (0,0,150) → (0,0,175) 반경 9, 넓적다리 지도는 축 없음(length 0).
"""
from __future__ import annotations

import base64
import math
import struct

BONES = ["root", "pelvis", "spine_01", "spine_05", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r"]
PARENTS = [-1, 0, 1, 2, 3, 4, 5, 3, 7, 8]
REST = [(0, 0, 0), (0, 0, 95), (0, 0, 25), (0, 0, 25), (18, 0, -5), (0, 0, -26), (0, 0, -26), (-18, 0, -5), (0, 0, -26), (0, 0, -26)]
HOLE = (10, 5)   # 몸통 지도 빈 칸(t 칸, 각도 칸)


def f32(values) -> str:
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode()


def i16(values, unit: float = 0.01) -> str:
    return base64.b64encode(struct.pack(f"<{len(values)}h", *[(-32768 if v < 0 else min(32767, int(round(v / unit)))) for v in values])).decode()


def _qy(deg: float):
    h = math.radians(deg) / 2.0
    return (0.0, math.sin(h), 0.0, math.cos(h))


def _rot(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def _mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def pose(angle_l: float) -> list:
    """컴포넌트 공간 (q, t) — 왼 위팔 로컬만 angle_l° (앞 축 둘레)."""
    out = []
    for b, (p, t) in enumerate(zip(PARENTS, REST)):
        lq = _qy(angle_l) if BONES[b] == "upperarm_l" else (0.0, 0.0, 0.0, 1.0)
        if p < 0:
            out.append((lq, t))
            continue
        pq, pt = out[p]
        out.append((_mul(pq, lq), tuple(a + c for a, c in zip(_rot(pq, t), pt))))
    return out


def rest_position(bone: str):
    return pose(0.0)[BONES.index(bone)][1]


def _point(side: str, part: str, bone: str, offset):
    b = BONES.index(bone)
    ref = tuple(a + c for a, c in zip(rest_position(bone), offset))
    return {"side": side, "part": part, "dominant": b, "ref_cm": list(ref), "influences": [[b, 1.0, *offset]]}


def _map(part: str, a, length: float, t_min: float, t_max: float, t_bins: int, radius: float, frames: int, hole=None, labels=None) -> dict:
    axis = []
    for _ in range(frames):
        axis += [*a, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, length]
    cells = [radius] * (t_bins * 36)
    if hole:
        cells[hole[0] * 36 + hole[1]] = -1.0
    out = {"part": part, "t_min": t_min, "t_max": t_max, "t_bins": t_bins, "angle_bins": 36, "axis_b64": f32(axis), "radius_unit_cm": 0.01,
           "radius_b64": i16(cells * frames)}
    if labels:
        out["part_of_t_bin"] = labels
    return out


def make_model(angles=(0.0, 20.0, 40.0)) -> dict:
    frames = len(angles)
    poses = []
    for a in angles:
        for q, t in pose(a):
            poses += [*q, *t, 1.0, 1.0, 1.0]
    points = [_point("l", "hand", "hand_l", (0.0, 0.0, 0.0)), _point("l", "forearm", "lowerarm_l", (0.0, 0.0, -10.0)),
              _point("l", "upper_arm", "upperarm_l", (0.0, 0.0, -18.0)), _point("r", "hand", "hand_r", (0.0, 0.0, 0.0))]
    labels = []
    for t in range(40):
        c = -0.25 + (t + 0.5) / 40 * 1.3
        labels.append("pelvis" if c < 0.2 else "belly" if c < 0.5 else "chest")
    maps = [_map("torso", (0.0, 0.0, 95.0), 50.0, -0.25, 1.05, 40, 10.0, frames, HOLE, labels),
            _map("thigh_l", (0.0, 0.0, 0.0), 0.0, -0.15, 1.0, 30, -1.0, frames), _map("thigh_r", (0.0, 0.0, 0.0), 0.0, -0.15, 1.0, 30, -1.0, frames),
            _map("head_neck", (0.0, 0.0, 150.0), 25.0, -0.1, 1.05, 24, 9.0, frames)]
    return {"version": 1, "mesh": "/Game/Test/SK_Synthetic", "scale": 0.95, "contact_cm": 0.95, "penetration_cm": 1.9, "fps": 30.0,
            "frames_total": frames, "frames": list(range(frames)), "times": [i / 30.0 for i in range(frames)],
            "bones": {"names": BONES, "parents": PARENTS},
            "roles": {"arms": [{"side": "l", "clavicle": None, "upper": "upperarm_l", "elbow": "lowerarm_l", "wrist": "hand_l", "twist": []},
                               {"side": "r", "clavicle": None, "upper": "upperarm_r", "elbow": "lowerarm_r", "wrist": "hand_r", "twist": []}],
                      "pelvis": "pelvis", "spine_top": "spine_05", "spine": ["spine_01", "spine_05"], "neck_root": None, "head": None},
            "poses": {"layout": "f32 [frame][bone] qx qy qz qw tx ty tz sx sy sz", "b64": f32(poses)},
            "influence_layout": "[bone, weight, local_x, local_y, local_z]", "points": points, "torso_t_bounds": {"belly": 0.2, "chest": 0.5},
            "leg_thigh_t_min": 0.2, "maps": maps, "b64_bytes": 0, "seconds": 0.0}


def per_frame_from(model: dict, series: dict) -> dict:
    """body_model.series 결과 → C++ per_frame{} 모양(전 프레임 = 모델 프레임)."""
    return {"frames": len(model["frames"]), "times": model["times"],
            "series": [{"side": s, "arm_part": p, "body_part": b, "depth": [None if d is None else round(d, 3) for d in v]} for (s, p, b), v in series.items()]}
