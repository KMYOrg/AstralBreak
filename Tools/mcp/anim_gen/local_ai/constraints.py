"""request.generation.constraints[] → Kimodo 제약 (Phase 5). 형식 검사는 request.py, 파일 · 루트 검사는 local_ai Provider 가 한다.

종류
- root_path{points[{t, forward_cm, left_cm, yaw_deg?}]} → Kimodo 'root2d'. 좌표는 캐릭터 기준 — 생성 첫 프레임의 정면(+Z, Kimodo)이
  forward, 왼쪽(+X)이 left, yaw 는 왼쪽으로 도는 쪽이 + (Kimodo heading θ 와 같은 방향). 대상 스켈레톤 축과 상관없이 같은 뜻이다
  (blender 변환이 대상 정면으로 돌린다). yaw 가 있는 점과 없는 점은 root2d 두 개로 나눈다(같은 집합 안에서 프레임이 같아야 한다).
- keep_pose{npz, times[], part} → 이전 Kimodo 결과(NPZ)의 그 시각 포즈를 고정하고 나머지만 다시 만든다(레퍼런스 기반 반복 다듬기).
  part = full(fullbody) · left_hand · right_hand · left_foot · right_foot (Kimodo end-effector). 실행 스크립트가 NPZ 에서 꺼낸다.
- kimodo_raw{path} → Kimodo constraints.json(웹 데모 · --save_example_dir 형식)을 그대로.

시각 → 프레임 = round(t × fps). 생성 길이(frames) 밖이면 거부한다.
"""
from __future__ import annotations

import math

KINDS = ("root_path", "keep_pose", "kimodo_raw")
PARTS = {"full": "fullbody", "left_hand": "left-hand", "right_hand": "right-hand", "left_foot": "left-foot", "right_foot": "right-foot"}
RAW_TYPES = {"root2d", "fullbody", "end-effector", "left-hand", "right-hand", "left-foot", "right-foot"}


class ConstraintError(Exception):
    def __init__(self, reason: str, message: str, **details):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details


def frame_of(t: float, fps: float, frames: int, where: str) -> int:
    f = int(round(t * fps))
    if not 0 <= f < frames:
        raise ConstraintError("CONSTRAINT_OUT_OF_RANGE", f"{where}: t={t:g}s is frame {f}, outside the {frames} generated frames "
                              f"(0 ~ {(frames - 1) / fps:.3f}s)", frame=f, frames=frames)
    return f


def root_path_items(points: list[dict], fps: float, frames: int, where: str) -> list[dict]:
    """→ Kimodo root2d dict 1~2 개 (smooth_root_2d 는 미터, (x, z) = (left, forward))."""
    groups: dict[bool, list[tuple[int, dict]]] = {True: [], False: []}
    seen: set[int] = set()
    for k, p in enumerate(points):
        f = frame_of(p["t"], fps, frames, f"{where}.points[{k}]")
        if f in seen:
            raise ConstraintError("DUPLICATE_FRAME", f"{where}.points[{k}]: frame {f} appears twice", frame=f)
        seen.add(f)
        groups[p.get("yaw_deg") is not None].append((f, p))
    items = []
    for with_yaw in (False, True):
        group = sorted(groups[with_yaw], key=lambda fp: fp[0])
        if not group:
            continue
        item = {"type": "root2d", "frame_indices": [f for f, _ in group],
                "smooth_root_2d": [[p["left_cm"] / 100.0, p["forward_cm"] / 100.0] for _, p in group]}
        if with_yaw:
            item["global_root_heading"] = [[math.cos(math.radians(p["yaw_deg"])), math.sin(math.radians(p["yaw_deg"]))] for _, p in group]
        items.append(item)
    return items


def check_raw(items, frames: int, where: str) -> None:
    """Kimodo constraints.json 모양만 본다(타입 · 프레임 범위) — 값은 Kimodo 로더가 읽는다."""
    if not isinstance(items, list) or not items:
        raise ConstraintError("BAD_RAW_CONSTRAINTS", f"{where}: must be a non-empty JSON list of Kimodo constraints")
    for k, item in enumerate(items):
        if not isinstance(item, dict) or item.get("type") not in RAW_TYPES:
            raise ConstraintError("BAD_RAW_CONSTRAINTS", f"{where}[{k}]: type must be one of {sorted(RAW_TYPES)}", got=(item or {}).get("type"))
        idx = item.get("frame_indices")
        if not isinstance(idx, list) or not idx or not all(isinstance(i, int) and not isinstance(i, bool) for i in idx):
            raise ConstraintError("BAD_RAW_CONSTRAINTS", f"{where}[{k}].frame_indices must be a non-empty list of integers")
        bad = [i for i in idx if not 0 <= i < frames]
        if bad:
            raise ConstraintError("CONSTRAINT_OUT_OF_RANGE", f"{where}[{k}]: frame(s) {bad[:5]} outside the {frames} generated frames", frames=frames)


def convert(constraints: list[dict], fps: float, frames: int) -> list[dict]:
    """→ 실행 스크립트용 명세. root_path 는 Kimodo dict 로 끝내고, 파일 종류(keep_pose · kimodo_raw)는 경로 · 프레임만 넘긴다."""
    out = []
    for k, c in enumerate(constraints):
        where = f"generation.constraints[{k}]"
        if c["type"] == "root_path":
            out.append({"kind": "kimodo", "source": where, "items": root_path_items(c["points"], fps, frames, where)})
        elif c["type"] == "keep_pose":
            idx = sorted({frame_of(t, fps, frames, f"{where}.times") for t in c["times"]})
            out.append({"kind": "keep_pose", "source": where, "npz": c["npz"], "type": PARTS[c.get("part", "full")], "frame_indices": idx})
        else:
            out.append({"kind": "raw", "source": where, "path": c["path"]})
    return out
