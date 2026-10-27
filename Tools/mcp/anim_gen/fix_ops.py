"""blender 보정 op 사전 — 이름 · 기본값 · 인자 검사 · 실행 순서의 한 곳 (Phase 8-3, 지침서 §9 `fix.ops` · §14 Phase 8 '8-3').

providers/blender.py(계획 검사 — FIX_OPS)와 blender/fix_legs.py(Blender 안 실행)가 같이 쓴다. 모두 리타깃 **전** 소스 골격(변환된 BVH 아마추어)에서 돈다.
- smooth       — 로컬 회전(쿼터니언 부호 연속) · 루트 위치의 시간 가우시안(local_ai.refine — 8-1 수정안 A 와 같은 함수). 휘두름 정점을 깎으므로 기본으로 켜지 않는다.
- stance_width — 두 발을 디딘 프레임의 발 좌우 비(발목 간격의 엉덩 축 성분 / 엉덩 관절 폭 — motion_metrics.stance 정의)를 max_ratio 아래로(대상 메시 기준 —
                 계획이 다리 치수로 소스 간격에 사상한다). 오프셋은 그 발의 접지 구간마다 상수(디딘 발이 미끄러지지 않게), 공중 구간은 부드럽게 잇는다.
                 keep_knee_bend(기본 참 — 8-3 후속 2026-10-27): 골반 높이 그대로 발을 모으면 무릎이 더 굽는다(시험 대상 p50 37 ~ 42° → 48 ~ 60°) —
                 좁힌 만큼 골반을 올려 엉덩 → 발목 거리를 원래대로(foot_fix.pelvis_raise).
- foot_lock    — 접지 구간마다 발목을 한 점에 고정(수평 = 가장 느린 프레임 · 높이 = 중앙값), 경계 blend_frames 프레임 블렌드. lock_rotation 이면 발 전역 회전도
                 그 프레임 값으로(기본은 원래 회전 — 뒤꿈치 · 발끝 구름을 지킨다).
stance_width 와 foot_lock 은 같은 다리 풀이 한 번(foot_fix.solve → 2본 IK)으로 — 차례로 고치면 서로 깬다(8-1 E1: 위팔만 돌린 보정이 양손을 벌렸다).
순서는 고정: smooth → 다리 풀이. 기준값(E0 2026-10-27): 운영 Vesper 낫 공격의 타격 중 발 좌우 비 p50 4.1 ~ 5.0 · 끝 자세 2.1 · 대기 1.9, 8-1 시험 대상은
처음부터 끝까지 3.7 ~ 5.1 을 유지 → 상한 3.0(사용자 결정 — 어깨 폭 1.5 배 남짓의 전투 자세).
"""
from __future__ import annotations

import copy

from . import motion_metrics

ORDER = ("smooth", "stance_width", "foot_lock")
LEG_OPS = frozenset({"stance_width", "foot_lock"})
SIDES = ("left", "right")
OPS = {
    "smooth": {"sigma_frames": 1.0, "bones": "all", "root": True, "from_s": None, "to_s": None},
    "stance_width": {"max_ratio": 3.0, "min_ratio": 1.2, "max_shift_cm": 25.0, "blend_s": 0.2, "keep_knee_bend": True},
    "foot_lock": {"feet": ["left", "right"], "contacts": "auto", "height_ratio": motion_metrics.CONTACT_HEIGHT_RATIO,
                  "speed_ratio": motion_metrics.CONTACT_SPEED_RATIO, "min_frames": motion_metrics.CONTACT_MIN_FRAMES, "blend_frames": 3,
                  "lock_rotation": False},
}


class FixOpError(ValueError):
    """(필드, 이유) — Provider 가 BAD_REQUEST 로 바꾼다."""


def _num(op: dict, key: str, lo: float, hi: float, field: str, integer: bool = False) -> None:
    v = op[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi or (integer and int(v) != v):
        raise FixOpError(f"{field}.{key}", f"must be {'an integer' if integer else 'a number'} in [{lo:g}, {hi:g}] (got {v!r})")
    op[key] = int(v) if integer else float(v)


def normalize_op(raw: dict, index: int = 0) -> dict:
    """op 하나 → 기본값을 채운 op. 모르는 키 · 범위 밖이면 FixOpError. 이름은 OPS 안이어야 한다(밖이면 Provider 가 UNSUPPORTED_FIX_OP)."""
    name = raw["op"]
    field = f"fix.ops[{index}]"
    extra = sorted(set(raw) - set(OPS[name]) - {"op"})
    if extra:
        raise FixOpError(f"{field}.{extra[0]}", f"unknown key for {name} — allowed {sorted(OPS[name])}")
    op = {"op": name, **copy.deepcopy(OPS[name]), **{k: copy.deepcopy(v) for k, v in raw.items() if k != "op"}}
    if name == "smooth":
        _num(op, "sigma_frames", 0.5, 3.0, field)
        if op["bones"] != "all" and not (isinstance(op["bones"], list) and op["bones"] and all(isinstance(b, str) and b for b in op["bones"])):
            raise FixOpError(f"{field}.bones", "must be \"all\" or a non-empty list of bone names")
        if not isinstance(op["root"], bool):
            raise FixOpError(f"{field}.root", "must be a boolean")
        for key in ("from_s", "to_s"):
            if op[key] is not None:
                _num(op, key, 0.0, 600.0, field)
        if op["from_s"] is not None and op["to_s"] is not None and op["from_s"] > op["to_s"]:
            raise FixOpError(f"{field}.from_s", "must be ≤ to_s")
    elif name == "stance_width":
        _num(op, "max_ratio", 1.0, 10.0, field)
        _num(op, "min_ratio", 0.0, op["max_ratio"], field)
        _num(op, "max_shift_cm", 1.0, 100.0, field)
        _num(op, "blend_s", 0.0, 2.0, field)
        if not isinstance(op["keep_knee_bend"], bool):
            raise FixOpError(f"{field}.keep_knee_bend", "must be a boolean")
    elif name == "foot_lock":
        feet = op["feet"]
        if not isinstance(feet, list) or not feet or any(f not in SIDES for f in feet) or len(set(feet)) != len(feet):
            raise FixOpError(f"{field}.feet", "must be a non-empty subset of [\"left\", \"right\"]")
        if op["contacts"] != "auto":
            raise FixOpError(f"{field}.contacts", "must be \"auto\" (contacts are detected from the ankle track)")
        _num(op, "height_ratio", 0.005, 0.2, field)
        _num(op, "speed_ratio", 0.02, 2.0, field)
        _num(op, "min_frames", 2, 60, field, integer=True)
        _num(op, "blend_frames", 0, 30, field, integer=True)
        if not isinstance(op["lock_rotation"], bool):
            raise FixOpError(f"{field}.lock_rotation", "must be a boolean")
    return op


def ordered(ops: list[dict]) -> tuple[list[dict], bool]:
    """정해진 순서(smooth → 다리 풀이)로 — (정렬한 ops, 순서가 바뀌었나). 같은 op 두 번이면 FixOpError."""
    names = [o["op"] for o in ops]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise FixOpError("fix.ops", f"{dup} given more than once — one of each (stance_width and foot_lock are solved together)")
    out = sorted(ops, key=lambda o: ORDER.index(o["op"]) if o["op"] in ORDER else len(ORDER))
    return out, [o["op"] for o in out] != names


def legs_from(joints: list[dict], chains: list[dict] | None, feet: list[str] | None) -> dict:
    """소스 골격 다리 본 — retarget 단계의 LeftLeg/RightLeg 체인 시작(엉덩 관절) · source_feet(발목, 없으면 체인 끝의 부모) · 발목의 부모(무릎).
    엉덩 → 무릎 → 발목이 부모 사슬이 아니면 FixOpError(2본 IK 를 풀 수 없다). joints = [{name, parent}](bvh.summary)."""
    parent = {j["name"]: j["parent"] for j in joints}
    by = {c["name"]: c for c in chains or []}
    out = {}
    for i, side in enumerate(SIDES):
        chain = by.get(f"{side.title()}Leg")
        if not chain:
            raise FixOpError("legs", f"no {side.title()}Leg chain — give retarget.source_chains (the leg ops need the source hip · knee · ankle)")
        hip = chain["start"]
        ankle = (feet or [None, None])[i] or parent.get(chain["end"])
        knee = parent.get(ankle)
        if ankle not in parent or not knee or parent.get(knee) != hip:
            raise FixOpError("legs", f"{side} leg {hip} → ? → {ankle} is not a two-bone hip → knee → ankle chain in the source skeleton")
        out[side] = {"hip": hip, "knee": knee, "ankle": ankle}
    return out


def contact_params(ops: list[dict]) -> dict:
    """다리 풀이의 접지 판정 — foot_lock 이 있으면 그 값, 없으면 기본(stance_width 의 '접지 구간마다 상수' 도 같은 접지를 쓴다)."""
    lock = next((o for o in ops if o["op"] == "foot_lock"), None) or OPS["foot_lock"]
    return {k: lock[k] for k in ("height_ratio", "speed_ratio", "min_frames")}
