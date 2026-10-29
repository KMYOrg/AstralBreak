"""Phase 8-4b — 대상(리타깃이 끝난 Vesper) 애니 위의 한 풀이: 몸 전체 관통 · 양손 파지 keep · 발 pin · 지시 목표 (순수 Python — numpy 없음).

원천은 C++ 몸 모델 하나(validate_animation body_clearance{parts all, hands, model} — body_model.py 가 읽는다). 이 모듈은 그 모델의 포즈를
관절 회전 델타(부모 공간 회전 벡터 — apply_animation_edits bone_deltas 와 같은 뜻)로 바꿔 가며 같은 반경 지도에 다시 묻는다:

  자유도   — 팔마다 쇄골 swing 2 · 위팔 swing 2(뼈 축에 수직 — 비틀림 0) · 팔꿈치 경첩 1(굽힘 평면 법선, 굽힘 2 ~ 155°) · 두 손목 3(파지 프레임만 —
             파지 방향을 맞출 때만, 그 밖은 손목 로컬 원래대로). 지시 목표 구간만: 척추 마디 · 목/머리 3씩(합 상한) · 골반 회전 3 + 이동 3(→ 다리 닫힌 식
             IK 로 원래 발목 · 발 전역 회전).
  잔차     — 층 가중(같은 GN 안 — TIER): 하드 목표 > 관통(손 · 아래팔 점 ↔ 몸통 칸 · 넓적다리 · 머리목 · 반대 팔 손 · 아래팔, 손끼리는 맞닿음까지
             허용) · 다리 늘어남 > 파지 keep(보조 손바닥 점 · 회전의 주 손목 기준 상대 변환) · 위팔 점 '원래보다 안 깊어짐'(TIER upper — 재검사 대상
             아님) > 소프트 목표 > 소프트(주 손 · 손목 위치 — 어깨 바탕 본 기준). 관절 변화 충실도(FID_CM) · 시간 연속(앞 프레임 보정 쪽 — TEMPORAL)은 rad 단위 행. 관통 = max(0, 깊이 +
             margin), 바깥 방향 = 지도 축에서 점 쪽(칸 반경을 고정한 선형화 — C++ Resolve 의 ω × r 와 같다), LBS 점의 야코비안 = 조상 관절마다
             ω × (가중 점 − 관절). 몸통 · 넓적다리 지도는 clearance.allow_contact(기본)면 맞닿음(깊이 ≤ contact_cm)까지 정상(손끼리와 같은
             규칙 — 관통 = max(0, 깊이 − contact), CONTACT_MAPS), 머리목 · allow_contact 끔은 margin 만큼 떼어 둔다(max(0, 깊이 + margin)).
  지도     —지도마다 기준 본(몸통 = t 칸별 펠비스 · 척추 마디, 넓적다리 = 넓적다리, 머리 = 목 뿌리 · 머리, 손 = 손목, 아래팔 = 팔꿈치)에 붙어 강체로
             따라간다: 풀이 포즈의 점을 T원래(기준 본) · T풀이(기준 본)⁻¹ 로 되돌려 원래 지도에 묻는다. 기준 본이 안 움직이면 C++ 규칙 그대로.
  한 프레임 — 감쇠 GN(LM, μ 0.1 시작) ≤ 12 회 · 한 걸음 ≤ 8°(상한을 넘는 관절은 그 걸음만 상한까지), 후보 점 = 깊이 > −(margin + 3 cm).
             목표가 있는 프레임은 두 번 푼다: x_T(목표 · keep · 충실도) → x(전부).
  시간     — 관통 몫 Δ = x − x_T 만 가중 매끈화 스플라인(spline — 하드 잔차로 푼 프레임 가중 SPLINE_ACTIVE_WEIGHT · 그 밖 SPLINE_QUIET_WEIGHT,
             2차 차분 벌점, 보정 구간 ± 2·폭 밖 0) → x_T + S(Δ). 원본이 루프(validate numeric.loop — C++ bLoop)면 순환(끝 프레임 = 첫 프레임 —
             스플라인 · 재검사 받침이 감아 돌고 첫 · 끝 델타가 같다). 목표 몫은 완급(목표 자체를 smoothstep 으로 0 → 1)이라 매끈화하지 않는다(목표 구간 밖 변화 0), 목표 구간 안은
             그 프레임 Δ 를 그대로 섞는다(목표가 관통에 막힌 되돌림이 이웃으로 번지지 않게).
  재검사   — 하드 잔차가 남은 프레임만 그 값에서 다시(두 팔 함께) → 증분(± 1 프레임 받침)을 같은 스플라인(바깥 가중만
             SPLINE_RECHECK_QUIET_WEIGHT)으로 더한다(passes + EXTRA_PASSES).
             위반 프레임만 매끈화 없이 고치는 처음 판(보조 팔 따라가기 · 마무리)은 이웃과 끊겨 떨림을 만들었다(띠 정정 zigzag 1.05 → 4.7) — 남는 작은
             위반(keep ≈ 1 ~ 2 cm · 고립 관통 프레임)은 한계로 보고한다.
결과 = 본별 프레임 델타(bone_deltas) · 모델 예측(쌍별 깊이 — C++ 실측과 대조) · keep 오차 · 목표 달성 · 남은 관통.
"""
from __future__ import annotations

import copy
import math
import re
import time

from . import body_model as bm
from . import motion_metrics as mm
from . import timing
from .local_ai import refine

VERSION = 1
DEFAULTS = {
    "mode": "auto",
    "clearance": {"margin_cm": 0.5, "allow_contact": True, "hands": True, "upper_arm": "no_worse", "secondary": "record", "legs": False},
    "grip": {"mode": "auto", "lead_hand": "right", "window": None, "spacing_cm": None, "tolerance_cm": None},
    "joints": {"clavicle_deg": 10.0, "upper_arm_deg": 45.0, "elbow_deg": 60.0, "wrist_deg": 30.0, "spine_deg": 0.0, "spine_deg_for_targets": 20.0,
               "neck_deg_for_targets": 20.0, "pelvis_cm": 15.0, "pelvis_deg": 10.0},
    "targets": [],
    "weights": {"clearance": 10.0, "grip": 10.0, "pins": 10.0, "targets": 5.0, "lead_hand": 3.0, "fidelity": 1.0},
    "smooth_s": 0.13,
    "passes": 3,
}
TARGET_KEYS = {"id", "note", "effector", "at", "hold_s", "position", "rotation", "ease_s", "weight", "priority"}
TARGET_DEFAULTS = {"note": None, "hold_s": 0.0, "position": None, "rotation": None, "ease_s": 0.15, "weight": 1.0, "priority": "soft"}
EFFECTORS = ("hand_l", "hand_r", "foot_l", "foot_r", "head", "pelvis")
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# 층 배율 — weights 값에 곱한다(잔차 가중 = (값 × 층)²). 하드 목표 > 관통 · 늘어남 > keep > 소프트 목표 > 소프트(주 손 · 손목 위치) — 기본 weights 로
# 위 층이 아래 층보다 √가중 3 배 이상(하드 목표 5 × 1000 : 관통 10 × 30 : keep 10 × 10 : 소프트 목표 5 × 10 : 소프트 ≤ 3). 관절 변화 충실도는 cm 가 아니라
# rad 단위 행(FID_CM)이라 따로 — 관통 1 cm ≈ 관절 3 rad, 소프트 목표 1 cm ≈ 0.5 rad 와 같은 값
# 위팔 '안 깊어짐'(upper)은 keep 과 같은 층(관통의 1/3)이고 재검사 대상이 아니다 — 관통과 같은 하드 층(30)이던 처음 판은 사이 프레임의 작은 위팔
# 깊어짐(운영 걷기 위반 65 프레임 — 손 44 보다 많다)까지 다시 풀며 팔을 벌려, 원본이 넓적다리에서 3.7 ~ 5.8 cm 떨어진 f30 ~ 33 에서 위팔 보정 17.6° ·
# 손목 바깥 13.6 cm(주기마다 10 / 13.6 / 13.4 / 7 cm — 사용자 Persona '중간에 팔이 더 멀어졌다 돌아옴'). upper 10 이면 주기마다 3.9 ~ 5.7 cm 로 고르고
# 손목 p95 14.9 → 6.6 cm, 위팔 → 가슴은 46 · 76% → 17 · 16%(오프라인 — 원래보다 나빠지지 않음). 허용 폭만 넓히기(+0.5 · +1 cm)로는 안 고쳐졌다
TIER = {"hard_target": 1000.0, "clearance": 30.0, "grip": 10.0, "upper": 10.0, "target": 10.0, "soft": 1.0}
ROT_CM = 11.5            # 회전 잔차 cm/rad — 1 cm ↔ 5°(기준 2 의 위치 · 방향 허용과 같은 비)
FID_CM = 100.0           # 관절 변화 충실도 cm/rad — 처음 판 10 은 관통 항에 비해 너무 약해(1 rad ≈ 관통 0.03 cm) 풀이가 아무 해나 잡고 경로가 크게 돌았다
                         # (운영 걷기 f22: 손 → 넓적다리 6.5 cm 에 팔꿈치 30° · 위팔 16°). 100 이면 최소 변화 해, 남는 관통 ≈ 0.02 cm
TEMPORAL = 2.0           # 시간 연속 — 앞 프레임 보정 쪽 √가중(충실도 대비). 낫 정정 선택 1.7 ~ 1.9초: 이 항 없이는 프레임마다 손을 머리 위 · 아래로
                         # 번갈아 빼는 다른 해로 뛰어(위팔 보정 40.7 → 27 → 12.6 → 45°) keep 이 24 cm 깨졌다
JOINT_COST = {"clavicle": 4.0, "upper": 1.0, "elbow": 1.0, "wrist": 3.0, "spine": 2.0, "neck": 2.0, "pelvis": 2.0}
MAX_ITER = 12
LM_RETRIES = 8
EXTRA_PASSES = 3         # 요청 passes 위에 더 도는 재검사(스플라인 증분) — 보간이 새로 만든 작은 위반(낫 정정 선택 f64)까지 잡는다
STEP_RAD = math.radians(8.0)
STEP_CM = 3.0
CANDIDATE_CM = 3.0       # 이보다 얕게 떨어진 점만 풀이 후보(끝에 전체 재검사)
TOL_CM = 0.05            # 관통 잔차 허용(C++ ResolveToleranceCm 와 같다)
KEEP_TOL_CM, KEEP_TOL_DEG = 0.3, 1.5   # 재검사 대상이 되는 keep 오차(× scale · °) — 기준 2(1 cm · 5°)의 절반. 0.2 · 1° 는 보간 프레임의
                                       # 작은 어긋남마다 그 프레임만 다시 풀어 떨림을 만들었다(띠 정정 1.05 → 7.0)
BEND_MIN, BEND_MAX = math.radians(2.0), math.radians(155.0)
STRAIGHT_RAD = math.radians(10.0)      # 이보다 펴진 프레임의 경첩 축은 굽힌 프레임 평균(위팔 로컬)
REACH = 0.995            # 엉덩 → 발목 ≤ 다리 길이 × 이 비(늘어남 금지)
GRIP_BLEND_S = 0.1       # 파지 프레임 경계 블렌드(keep 가중 smoothstep)
GRIP_MIN_FRAMES = 3
GRIP_GAP_FRAMES = 2      # 띠 밖으로 잠깐(≤ 이 프레임) 나간 것은 파지로 이어 본다
HAND_MAPS = ("hand_l", "hand_r", "forearm_l", "forearm_r")
# clearance.allow_contact 가 맞닿음(≤ contact_cm)을 허용하는 몸 지도 — 머리목은 하드 기준(관통 0)이라 margin 을 둔다: 맞닿음(1.05)과 관통 판정(2.1)
# 사이 여유가 1 cm 뿐이라 매끈화로 묽어진 프레임이 넘는다(오프라인 검 선택 손 → 머리 2.5% · 8.26 cm, 머리목 margin 이면 0.8% · 2.19). 넓적다리만은
# 안 된다 — 걷기 손은 골반 쪽 몸통에도 스친다(손목 이동 p50 13.7 cm 그대로)
CONTACT_MAPS = ("torso", "thigh_l", "thigh_r")
UP = (0.0, 0.0, 1.0)

_sub, _add, _scale, _dot, _cross, _norm = bm._sub, bm._add, bm._scale, bm._dot, bm._cross, bm._norm


class BodyFitError(ValueError):
    """요청 fix.body 오류 — (필드, 메시지[, reason])."""

    def __init__(self, field: str, message: str, reason: str = "BAD_FIELD"):
        super().__init__(field, message)
        self.field, self.message, self.reason = field, message, reason


# ---- 요청 ----
def _num(value, lo: float, hi: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and lo <= value <= hi


def _vec(value, n: int = 3) -> bool:
    return isinstance(value, list) and len(value) == n and all(_num(v, -1e4, 1e4) for v in value)


def _merge(out: dict, raw, field: str) -> None:
    if not isinstance(raw, dict):
        raise BodyFitError(field, "must be an object")
    for key, value in raw.items():
        if key not in out:
            raise BodyFitError(f"{field}.{key}", f"unknown key — allowed {sorted(out)}", "UNKNOWN_FIELD")
        out[key] = value


def normalize(raw) -> dict | None:
    """요청 fix.body — true · {} · 부분 객체 → 기본값을 채운 객체, mode off · false · None → None. 잘못이면 BodyFitError(필드, 이유)."""
    if raw is None or raw is False:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raise BodyFitError("fix.body", "must be true or an object")
    out = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key not in out:
            raise BodyFitError(f"fix.body.{key}", f"unknown key — allowed {sorted(out)}", "UNKNOWN_FIELD")
        if isinstance(out[key], dict):
            _merge(out[key], value, f"fix.body.{key}")
        else:
            out[key] = value
    if out["mode"] not in ("auto", "measure", "off"):
        raise BodyFitError("fix.body.mode", "must be auto | measure | off")
    if out["mode"] == "off":
        return None
    c, g, j, w = out["clearance"], out["grip"], out["joints"], out["weights"]
    if not _num(c["margin_cm"], 0.0, 5.0):
        raise BodyFitError("fix.body.clearance.margin_cm", "must be a number in [0, 5] (cm × scale)")
    for key in ("allow_contact", "hands", "legs"):
        if not isinstance(c[key], bool):
            raise BodyFitError(f"fix.body.clearance.{key}", "must be a boolean")
    if c["upper_arm"] not in ("no_worse", "off"):
        raise BodyFitError("fix.body.clearance.upper_arm", "must be no_worse | off (upper-arm pairs are kept no deeper than before, not targeted)")
    if c["secondary"] not in ("record", "off"):
        raise BodyFitError("fix.body.clearance.secondary", "must be record | off (secondary branches — coat flaps — are measured, never constrained)")
    if g["mode"] not in ("auto", "keep", "off"):
        raise BodyFitError("fix.body.grip.mode", "must be auto | keep | off (weapon grip is Phase 8-4c)")
    if g["lead_hand"] not in ("left", "right"):
        raise BodyFitError("fix.body.grip.lead_hand", "must be left | right")
    if g["window"] is not None and not (isinstance(g["window"], list) and len(g["window"]) == 2 and all(_num(v, 0.0, 600.0) for v in g["window"])
                                        and g["window"][0] < g["window"][1]):
        raise BodyFitError("fix.body.grip.window", "must be null or [from_s, to_s] with from < to")
    for key, hi in (("spacing_cm", 200.0), ("tolerance_cm", 100.0)):
        if g[key] is not None and not (_num(g[key], 0.0, hi) and g[key] > 0):
            raise BodyFitError(f"fix.body.grip.{key}", f"must be null or a number in (0, {hi:g}] cm")
    for key, hi in (("clavicle_deg", 30.0), ("upper_arm_deg", 90.0), ("elbow_deg", 120.0), ("wrist_deg", 60.0), ("spine_deg", 30.0),
                    ("spine_deg_for_targets", 45.0), ("neck_deg_for_targets", 45.0), ("pelvis_cm", 40.0), ("pelvis_deg", 30.0)):
        if not _num(j[key], 0.0, hi):
            raise BodyFitError(f"fix.body.joints.{key}", f"must be a number in [0, {hi:g}]")
        j[key] = float(j[key])
    if j["spine_deg"] > 0:
        raise BodyFitError("fix.body.joints.spine_deg", "spine freedom outside target windows is off in 8-4b (decision D) — use spine_deg_for_targets",
                           "NOT_SUPPORTED")
    for key, value in w.items():
        if not _num(value, 0.0, 100.0):
            raise BodyFitError(f"fix.body.weights.{key}", "must be a number in [0, 100]")
        w[key] = float(value)
    if not _num(out["smooth_s"], 0.0, 1.0):
        raise BodyFitError("fix.body.smooth_s", "must be a number in [0, 1] (seconds)")
    if not (isinstance(out["passes"], int) and not isinstance(out["passes"], bool) and 1 <= out["passes"] <= 5):
        raise BodyFitError("fix.body.passes", "must be an integer in [1, 5]")
    if not isinstance(out["targets"], list):
        raise BodyFitError("fix.body.targets", "must be a list")
    out["targets"] = [_target(i, t) for i, t in enumerate(out["targets"])]
    ids = [t["id"] for t in out["targets"]]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        raise BodyFitError("fix.body.targets", f"duplicate id(s) {dup}", "DUPLICATE_ID")
    return out


def _target(i: int, raw) -> dict:
    where = f"fix.body.targets[{i}]"
    if not isinstance(raw, dict):
        raise BodyFitError(where, "must be an object")
    extra = sorted(set(raw) - TARGET_KEYS)
    if extra:
        raise BodyFitError(f"{where}.{extra[0]}", f"unknown key — allowed {sorted(TARGET_KEYS)}", "UNKNOWN_FIELD")
    t = {**copy.deepcopy(TARGET_DEFAULTS), **copy.deepcopy(raw)}
    if not isinstance(t.get("id"), str) or not _ID.match(t["id"]):
        raise BodyFitError(f"{where}.id", "must be a short id (letters, digits, _ -)")
    if not isinstance(t.get("effector"), str) or not t["effector"]:
        raise BodyFitError(f"{where}.effector", f"must be one of {list(EFFECTORS)} or a bone name")
    if t["note"] is not None and not isinstance(t["note"], str):
        raise BodyFitError(f"{where}.note", "must be a string (the user's words — recorded only)")
    at = t.get("at")
    if not isinstance(at, dict) or len({"event", "time", "window"} & set(at)) != 1:
        raise BodyFitError(f"{where}.at", "must be {event, offset_s?, index?} | {time} | {window: [a, b]}")
    extra = sorted(set(at) - {"event", "offset_s", "index", "time", "window"})
    if extra:
        raise BodyFitError(f"{where}.at.{extra[0]}", "unknown key", "UNKNOWN_FIELD")
    if "event" in at:
        if at["event"] not in timing.POINT_EVENTS + timing.WINDOW_EVENTS:
            raise BodyFitError(f"{where}.at.event", f"must be one of {list(timing.POINT_EVENTS + timing.WINDOW_EVENTS)}")
        if not _num(at.get("offset_s", 0.0), -60.0, 60.0):
            raise BodyFitError(f"{where}.at.offset_s", "must be a number (seconds)")
        if not (isinstance(at.get("index", 0), int) and not isinstance(at.get("index", 0), bool) and at.get("index", 0) >= 0):
            raise BodyFitError(f"{where}.at.index", "must be an integer ≥ 0 (n-th window of a window event)")
    elif "time" in at:
        if not _num(at["time"], 0.0, 600.0):
            raise BodyFitError(f"{where}.at.time", "must be a time in seconds ≥ 0")
    elif not (isinstance(at["window"], list) and len(at["window"]) == 2 and all(_num(v, 0.0, 600.0) for v in at["window"]) and at["window"][0] <= at["window"][1]):
        raise BodyFitError(f"{where}.at.window", "must be [from_s, to_s] with from ≤ to")
    for key, lo, hi in (("hold_s", 0.0, 10.0), ("ease_s", 0.0, 2.0), ("weight", 0.0, 10.0)):
        if not _num(t[key], lo, hi):
            raise BodyFitError(f"{where}.{key}", f"must be a number in [{lo:g}, {hi:g}]")
    if t["priority"] not in ("soft", "hard"):
        raise BodyFitError(f"{where}.priority", "must be soft | hard")
    pos, rot = t["position"], t["rotation"]
    if pos is None and rot is None:
        raise BodyFitError(where, "needs position and/or rotation", "MISSING_FIELD")
    if pos is not None:
        if not isinstance(pos, dict):
            raise BodyFitError(f"{where}.position", "must be an object")
        if "away_from" in pos:
            if set(pos) - {"away_from", "min_cm"} or not isinstance(pos["away_from"], str) or not _num(pos.get("min_cm"), 0.0, 200.0):
                raise BodyFitError(f"{where}.position", "away_from form is {away_from: part | bone, min_cm}")
        else:
            key = "offset_cm" if "offset_cm" in pos else "absolute_cm" if "absolute_cm" in pos else None
            if key is None or set(pos) - {key, "space"} or not _vec(pos[key]):
                raise BodyFitError(f"{where}.position", "must be {offset_cm | absolute_cm: [3], space} or {away_from, min_cm}")
            pos.setdefault("space", "body")
            if pos["space"] not in ("body", "component"):
                raise BodyFitError(f"{where}.position.space", "must be body (forward · left · up) | component")
    if rot is not None:
        if not isinstance(rot, dict) or set(rot) - {"offset_deg", "space"} or not _vec(rot.get("offset_deg")):
            raise BodyFitError(f"{where}.rotation", "must be {offset_deg: [pitch, yaw, roll], space}")
        rot.setdefault("space", "body")
        if rot["space"] not in ("body", "local"):
            raise BodyFitError(f"{where}.rotation.space", "must be body | local")
        if t["effector"] in ("foot_l", "foot_r"):
            raise BodyFitError(f"{where}.rotation", "foot rotation targets are Phase 8-4d (legs) — give a position", "NOT_SUPPORTED")
    return t


# ---- 쿼터니언 (라디안 회전 벡터) ----
def qexp(v) -> tuple:
    a = _norm(v)
    if a < 1e-12:
        return bm.qnormalize((0.5 * v[0], 0.5 * v[1], 0.5 * v[2], 1.0))
    s = math.sin(a / 2.0) / a
    return (v[0] * s, v[1] * s, v[2] * s, math.cos(a / 2.0))


def qlog(q) -> tuple:
    return tuple(math.radians(c) for c in bm.to_rotvec_deg(q))


def _unit(v, fallback=(1.0, 0.0, 0.0)):
    n = _norm(v)
    return _scale(v, 1.0 / n) if n > 1e-9 else fallback


def _perp(u):
    """u 에 수직인 단위 벡터 두 개."""
    a = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _unit(_cross(u, a))
    return e1, _cross(u, e1)


def _wxyz(q):
    return [q[3], q[0], q[1], q[2]]


def _xyzw(q):
    return bm.qnormalize((q[1], q[2], q[3], q[0]))


def _smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def _slerp(a, b, s: float):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0.0:
        b, d = tuple(-x for x in b), -d
    if d > 0.9995:
        return bm.qnormalize(tuple(x + s * (y - x) for x, y in zip(a, b)))
    th = math.acos(min(1.0, d))
    sa, sb = math.sin((1 - s) * th) / math.sin(th), math.sin(s * th) / math.sin(th)
    return bm.qnormalize(tuple(sa * x + sb * y for x, y in zip(a, b)))


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float] | None:
    """가우스 소거(부분 피벗) — 특이면 None."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-14:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            k = m[r][c] / m[c][c]
            if k:
                for cc in range(c, n + 1):
                    m[r][cc] -= k * m[c][cc]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][cc] * x[cc] for cc in range(r + 1, n))) / m[r][r]
    return x


def _rel_point(orig, new, p):
    """T원래 · T새⁻¹ — 기준 본이 움직인 만큼 점을 원래 자리로(지도 조회용)."""
    q, t, _ = new
    local = bm.qrot(bm.qconj(q), _sub(p, t))
    return _add(bm.qrot(orig[0], local), orig[1])


# ---- 시간 매끈화 ----
SPLINE_WIDTH = 1.5             # 매끈화 폭 = 이 배 × smooth_s 프레임(λ = 폭⁴, 꼬리 포락선 폭 ~ 2·폭)
SPLINE_ACTIVE_WEIGHT = 30.0   # 보정 프레임(하드 잔차로 푼 프레임)의 자료 가중
SPLINE_QUIET_WEIGHT = 10.0    # 보정이 필요 없는 프레임(증분 0)의 자료 가중(첫 풀이) — 처음 판 1 은 λ 에 비해 약해 보정 프레임이 고르게 흩어진
                              # 동작(걷기 — 손이 반 주기마다 넓적다리를 스친다)에서 사이 프레임까지 팔을 벌린 채 이었다(운영 걷기 손목 이동 p50
                              # 13.9 cm · 121 프레임 전부 > 3 cm, 관통 없던 f0 도 19 cm). 10 이면 사이 프레임이 원래 쪽으로 돌아오고(맞닿음
                              # 허용과 함께 p50 ≈ 7 cm), 띠 정정 keep 최대 1.37 → 0.46 cm(오프라인 — 8-4a 모델 사본)
SPLINE_RECHECK_QUIET_WEIGHT = 1.0   # 재검사 증분을 이을 때의 같은 가중 — 재검사는 남은 1 ~ 3 프레임 위반의 작은 증분이라 10 이면 절반쯤 묽어져 패스가
                                    # 끝나도 못 풀었다(오프라인 걷기 손 → 넓적다리 1.7% · 4.44 cm · 달리기 1.3% · 2.47 cm → 1 이면 0, 손목 p50 +0.9 cm)
SPLINE_LOOP_PAD = 8.0         # 루프 순환 — 앞뒤로 감아 붙이는 길이(폭의 배). 꼬리 감쇠 e^(−8/√2) ≈ 0.4% 라 감아 붙인 끝의 영향이 남지 않는다


def spline(series: list, active: list[bool], radius: int, loop: bool = False, quiet: float | None = None) -> list:
    """3-벡터 열의 가중 매끈화 스플라인 — Σ w_f |x_f − y_f|² + λ Σ |x_{f+1} − 2x_f + x_{f−1}|² 최소(성분별, 5대각 직접 풀이), w = 보정 프레임
    SPLINE_ACTIVE_WEIGHT · 그 밖 quiet(기본 SPLINE_QUIET_WEIGHT), λ = 폭⁴(폭 = SPLINE_WIDTH × radius 프레임). 보정 프레임 둘레를 가속 연속으로 잇고, 스플라인
    꼬리는 길게 남으므로 가장 가까운 보정 프레임에서 폭까지 1 → 2·폭에서 0 인 smoothstep 포락선을 곱한다(보정 구간 ± 2·폭 밖 변화 0).
    가중 30 · 폭 1.5 는 실측 절충 — 1e4(보정 프레임을 그대로 지남)는 프레임 풀이의 잡음까지 살려 떨림이 늘었고(검 선택 zigzag 0.33 → 1.8), 더 넓히면
    (폭 2) 고립 정점이 묽어져 관통 · keep 이 남았다. 처음 판(관절마다 크기 기준 팽창 + 가우시안 — C++ SmoothRotationVectors)은 빠른 휘두름에서
    ±radius 떨어진 프레임의 관절 해를 그대로 옮겨 와 두 팔 짝(keep)과 관통 해소를 깼다(낫 정정 선택 keep 8 ~ 19 cm).
    loop — 끝 프레임은 첫 프레임과 같은 시점(루프 애셋 관례 — C++ loop_boundary 도 첫 · 끝을 비교한다): 둘을 한 점으로 합쳐(보정한 쪽 값, 둘 다면
    평균) 끝을 뺀 열을 앞뒤로 SPLINE_LOOP_PAD × 폭만큼 감아 붙여 풀고 가운데를 쓴다(포락선 거리도 감아 돈다) → 결과 끝 = 첫(이음매 0)."""
    n = len(series)
    if radius <= 0 or n < 3:
        return [tuple(v) for v in series]
    if loop and n > 3:
        m = n - 1
        first, act0 = tuple(series[0]), bool(active[0])
        if active[-1] and not active[0]:
            first, act0 = tuple(series[-1]), True
        elif active[-1] == active[0]:
            first = tuple((a + b) * 0.5 for a, b in zip(series[0], series[-1]))
        core, core_act = [first] + [tuple(v) for v in series[1:m]], [act0] + list(active[1:m])
        pad = int(math.ceil(SPLINE_LOOP_PAD * SPLINE_WIDTH * radius))
        idx = [(k - pad) % m for k in range(m + 2 * pad)]
        out = _spline_line([core[i] for i in idx], [core_act[i] for i in idx], radius, quiet)[pad:pad + m]
        return out + [out[0]]
    return _spline_line(series, active, radius, quiet)


def _spline_line(series: list, active: list[bool], radius: int, quiet: float | None) -> list:
    """spline 의 열린 열 풀이(포락선 포함)."""
    n = len(series)
    quiet = SPLINE_QUIET_WEIGHT if quiet is None else quiet
    near = [None] * n
    last = None
    for i in range(n):
        last = i if active[i] else last
        near[i] = None if last is None else i - last
    last = None
    for i in range(n - 1, -1, -1):
        last = i if active[i] else last
        if last is not None and (near[i] is None or last - i < near[i]):
            near[i] = last - i
    width = SPLINE_WIDTH * radius
    env = [0.0 if d is None else 1.0 if d <= width else _smoothstep(1.0 - (d - width) / width) for d in near]
    lam = float(width) ** 4
    weight = [SPLINE_ACTIVE_WEIGHT if a else quiet for a in active]
    base = [[0.0] * 5 for _ in range(n)]   # base[i][k] = A(i, i + k − 2)
    for i in range(n):
        base[i][2] = weight[i]
    for r in range(n - 2):
        c = (1.0, -2.0, 1.0)
        for a in range(3):
            for b in range(3):
                base[r + a][b - a + 2] += lam * c[a] * c[b]
    out = [[0.0, 0.0, 0.0] for _ in range(n)]
    for comp in range(3):
        m = [row[:] for row in base]
        rhs = [series[i][comp] * weight[i] for i in range(n)]
        for k in range(n):
            piv = m[k][2]
            for i in range(k + 1, min(n, k + 3)):
                fac = m[i][k - i + 2] / piv
                if fac:
                    for j in range(k, min(n, k + 3)):
                        m[i][j - i + 2] -= fac * m[k][j - k + 2]
                    rhs[i] -= fac * rhs[k]
        for k in range(n - 1, -1, -1):
            acc = rhs[k]
            for j in range(k + 1, min(n, k + 3)):
                acc -= m[k][j - k + 2] * out[j][comp]
            out[k][comp] = acc / m[k][2]
    return [(v[0] * e, v[1] * e, v[2] * e) for v, e in zip(out, env)]


# ---- 리그 ----
class Rig:
    """몸 모델 위의 관절 · 역할 · 프레임별 로컬 포즈 · FK(델타) · 지도 기준 본."""

    def __init__(self, model: bm.BodyModel):
        self.model = model
        self.n = len(model.bones)
        self.frames = len(model.frames)
        self.parents = model.parents
        self.anc = []
        for b in range(self.n):
            chain, x = [], b
            while x >= 0:
                chain.append(x)
                x = self.parents[x]
            self.anc.append(chain)
        self.anc_set = [set(c) for c in self.anc]
        self.local = [model.local_pose(f) for f in range(self.frames)]
        idx = model.index.get
        roles = model.roles or {}
        self.arms, self.legs = {}, {}
        for a in roles.get("arms") or []:
            arm = {"clavicle": idx(a.get("clavicle") or ""), "upper": idx(a.get("upper") or ""), "elbow": idx(a.get("elbow") or ""),
                   "wrist": idx(a.get("wrist") or "")}
            if None in (arm["upper"], arm["elbow"], arm["wrist"]):
                raise BodyFitError("model", f"arm role {a} has bones outside the model")
            self.arms[a["side"]] = arm
        for leg in roles.get("legs") or []:
            item = {k: idx(leg.get(k) or "") for k in ("thigh", "knee", "foot")}
            if None not in item.values():
                self.legs[leg["side"]] = item
        if set(self.arms) != {"l", "r"}:
            raise BodyFitError("model", "the body model needs both arms (roles.arms l · r)")
        self.pelvis = idx(roles.get("pelvis") or "")
        self.spine = [b for b in (idx(s) for s in roles.get("spine") or []) if b is not None]
        self.spine_top = idx(roles.get("spine_top") or "")
        self.neck_root, self.head = idx(roles.get("neck_root") or ""), idx(roles.get("head") or "")
        self.neck = []
        if self.head is not None and self.neck_root is not None and self.neck_root in self.anc_set[self.head]:
            self.neck = list(reversed(self.anc[self.head][:self.anc[self.head].index(self.neck_root) + 1]))
        self.leg_len = {s: _norm(_sub(model.poses[0][g["thigh"]][1], model.poses[0][g["knee"]][1]))
                        + _norm(_sub(model.poses[0][g["knee"]][1], model.poses[0][g["foot"]][1])) for s, g in self.legs.items()}
        self.hinge = {s: self._hinge_axes(s) for s in self.arms}
        self.bend0 = {s: [self._bend(f, s, model.poses[f]) for f in range(self.frames)] for s in self.arms}

    def side_of(self, side: str) -> str:
        return "r" if side == "l" else "l"

    def _bend(self, f: int, side: str, pose) -> float:
        a = self.arms[side]
        u = _sub(pose[a["elbow"]][1], pose[a["upper"]][1])
        v = _sub(pose[a["wrist"]][1], pose[a["elbow"]][1])
        c = _dot(_unit(u), _unit(v))
        return math.acos(min(1.0, max(-1.0, c)))

    def _hinge_axes(self, side: str) -> list:
        """프레임별 팔꿈치 경첩 축(위팔 로컬 = 팔꿈치의 부모 공간) — +θ 가 굽힘을 늘린다. 거의 펴진 프레임은 굽힌 프레임 평균."""
        a = self.arms[side]
        parent = self.parents[a["elbow"]]
        out, good = [], []
        for f in range(self.frames):
            pose = self.model.poses[f]
            u = _sub(pose[a["elbow"]][1], pose[a["upper"]][1])
            v = _sub(pose[a["wrist"]][1], pose[a["elbow"]][1])
            c = _cross(u, v)
            if _norm(c) > math.sin(STRAIGHT_RAD) * _norm(u) * _norm(v):
                local = bm.qrot(bm.qconj(pose[parent][0]), _unit(c))
                out.append(local)
                good.append(local)
            else:
                out.append(None)
        if good:
            mean = _unit((sum(g[0] for g in good), sum(g[1] for g in good), sum(g[2] for g in good)))
        else:
            d = bm.qrot(bm.qconj(self.model.poses[0][parent][0]), _sub(self.model.poses[0][a["wrist"]][1], self.model.poses[0][a["elbow"]][1]))
            mean = _perp(_unit(d))[0]
        return [x or mean for x in out]

    def fk(self, f: int, rot: dict, trans: dict | None = None, override: dict | None = None) -> list:
        """프레임 f 원래 포즈에 델타 — rot{본: 부모 공간 회전 벡터(rad)} · trans{본: 부모 공간 이동(cm)} · override{본: 컴포넌트 회전(쿼터니언)}.
        안 움직인 본은 원래 튜플 그대로(is 로 '안 움직임'을 안다)."""
        comp0, local = self.model.poses[f], self.local[f]
        out = list(comp0)
        moved = [False] * self.n
        trans = trans or {}
        override = override or {}
        for b in range(self.n):
            p = self.parents[b]
            own = b in rot or b in trans or b in override
            if not own and not (p >= 0 and moved[p]):
                continue
            q, t, s = local[b]
            if b in override:
                q = bm.qnormalize(bm.qmul(bm.qconj(out[p][0]), override[b])) if p >= 0 else override[b]
            elif b in rot:
                q = bm.qnormalize(bm.qmul(qexp(rot[b]), q))
            if b in trans:
                t = _add(t, trans[b])
            out[b] = (q, t, s) if p < 0 else bm.compose((q, t, s), out[p])
            moved[b] = True
        return out

    def leg_overrides(self, f: int, pose, ankles: dict) -> tuple[dict, dict]:
        """골반이 움직인 포즈(다리는 강체로 따라감) → 다리마다 넓적다리 · 무릎 컴포넌트 회전(foot_fix.swing_two_bone — 굽힘 평면 최소 회전)과
        발 = 원래 컴포넌트 회전. ankles{side: 발목 목표}. → (override, {side: {clamped, error_cm, reach_cm}})."""
        over, info = {}, {}
        fwd = self.body_frame(f)[1][0]
        for side, target in ankles.items():
            leg = self.legs.get(side)
            if leg is None:
                continue
            hip, knee, ankle = (pose[leg[k]][1] for k in ("thigh", "knee", "foot"))
            r_th = refine.matrix_from_quat(_wxyz(pose[leg["thigh"]][0]))
            r_sh = refine.matrix_from_quat(_wxyz(pose[leg["knee"]][0]))
            res = _leg_ik(hip, knee, ankle, r_th, r_sh, target, fwd)
            over[leg["thigh"]] = _xyzw(refine.quat_from_matrix(res["r_thigh"]))
            over[leg["knee"]] = _xyzw(refine.quat_from_matrix(res["r_shin"]))
            over[leg["foot"]] = self.model.poses[f][leg["foot"]][0]
            info[side] = {"clamped": res["clamped"], "error_cm": res["error"], "reach_cm": _norm(_sub(target, hip))}
        return over, info

    def body_frame(self, f: int) -> tuple:
        """몸 기준틀(원래 포즈) — 원점 = 두 엉덩 관절 중점, 왼 = (엉덩L − 엉덩R) 수평, 위 = +Z, 앞 = 위 × 왼. 다리가 없으면 위팔로."""
        pose = self.model.poses[f]
        if {"l", "r"} <= set(self.legs):
            a, b = pose[self.legs["l"]["thigh"]][1], pose[self.legs["r"]["thigh"]][1]
        else:
            a, b = pose[self.arms["l"]["upper"]][1], pose[self.arms["r"]["upper"]][1]
        origin = _scale(_add(a, b), 0.5)
        left = _unit((a[0] - b[0], a[1] - b[1], 0.0))
        return origin, (_cross(UP, left), left, UP)


def _leg_ik(hip, knee, ankle, r_thigh, r_shin, target, fwd) -> dict:
    """다리 2본 IK — foot_fix.swing_two_bone 과 같은 순서(다리 전체를 엉덩 둘레로 '엉덩 → 발목'이 목표 쪽이 되게 최소 회전 → 길이만 맞춤 —
    굽힘 평면 유지)에 곧은 다리(굽힘 평면 없음)는 몸 앞(fwd)으로 굽힌다. r_* = 컴포넌트 회전 행렬. → {r_thigh, r_shin, clamped, error}."""
    q0 = refine.rotation_between(_sub(ankle, hip), _sub(target, hip))
    knee1 = _add(hip, tuple(refine._mv(q0, _sub(knee, hip))))
    ankle1 = _add(hip, tuple(refine._mv(q0, _sub(ankle, hip))))
    r_th1, r_sh1 = refine._mm(q0, r_thigh), refine._mm(q0, r_shin)
    l1, l2 = _norm(_sub(knee1, hip)), _norm(_sub(ankle1, knee1))
    v = _sub(target, hip)
    d = _norm(v)
    u = _unit(v, _unit(_sub(ankle1, hip)))
    lo, hi = abs(l1 - l2) + 1e-6 * (l1 + l2), (l1 + l2) * (1.0 - 1e-6)
    dc = min(max(d, lo), hi)
    e = _sub(knee1, hip)
    perp = _sub(e, _scale(u, _dot(e, u)))
    if _norm(perp) > 1e-3 * l1:
        pole = _unit(perp)
    else:
        pole = _unit(_sub(fwd, _scale(u, _dot(fwd, u))), _perp(u)[0])
    cos_a = max(-1.0, min(1.0, (l1 * l1 + dc * dc - l2 * l2) / (2.0 * l1 * dc)))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    new_knee = _add(hip, _scale(_add(_scale(u, cos_a), _scale(pole, sin_a)), l1))
    reached = _add(hip, _scale(u, dc))
    q1 = refine.rotation_between(e, _sub(new_knee, hip))
    q2 = refine.rotation_between(tuple(refine._mv(q1, _sub(ankle1, knee1))), _sub(reached, new_knee))
    return {"r_thigh": refine._mm(q1, r_th1), "r_shin": refine._mm(refine._mm(q2, q1), r_sh1), "clamped": abs(dc - d) > 1e-6 * (l1 + l2),
            "error": _norm(_sub(reached, target))}


def _body_vec(frame: tuple, v) -> tuple:
    fwd, left, up = frame[1]
    return _add(_add(_scale(fwd, v[0]), _scale(left, v[1])), _scale(up, v[2]))


def _body_rot(frame: tuple, deg) -> tuple:
    """몸 축 둘레 yaw(위) · pitch(왼) · roll(앞) — Rz · Ry · Rx 순(컴포넌트 공간 쿼터니언)."""
    fwd, left, up = frame[1]
    p, y, r = (math.radians(v) for v in deg)
    return bm.qmul(bm.qmul(qexp(_scale(up, y)), qexp(_scale(left, p))), qexp(_scale(fwd, r)))


# ---- 파지 ----
def grip_weights(rig: Rig, cfg: dict, scale: float) -> dict:
    """keep 가중(프레임별 0 ~ 1) — 손목 간격이 띠(motion_metrics.grip_band) 안인 구간(짧은 빈틈은 이어 보고 GRIP_MIN_FRAMES 이상) + 경계 smoothstep.
    window(초)가 있으면 그 안만. mode off → 전부 0."""
    model = rig.model
    n = rig.frames
    lead = "r" if cfg["lead_hand"] == "right" else "l"
    out = {"mode": cfg["mode"], "lead": lead, "off": rig.side_of(lead), "weights": [0.0] * n, "frames": [], "runs_s": [], "band_cm": None}
    if cfg["mode"] == "off":
        return out
    spacing, tol = cfg.get("spacing_cm"), cfg.get("tolerance_cm")
    lo, hi = mm.grip_band(scale, spacing, tol if tol is not None else mm.GRIP_TOL_CM)
    out["band_cm"] = [round(lo, 2), round(hi, 2)]
    wl, wr = rig.arms["l"]["wrist"], rig.arms["r"]["wrist"]
    fps = model.fps
    flags = []
    for f in range(n):
        gap = _norm(_sub(model.poses[f][wl][1], model.poses[f][wr][1]))
        t = model.times[f]
        inside = cfg["window"] is None or cfg["window"][0] - 1e-6 <= t <= cfg["window"][1] + 1e-6
        flags.append(inside and lo <= gap <= hi)
    # 짧은 빈틈 잇기
    for f in range(n):
        if not flags[f]:
            a = f
            while a < n and not flags[a]:
                a += 1
            if 0 < f and a < n and a - f <= GRIP_GAP_FRAMES:
                for k in range(f, a):
                    flags[k] = True
    runs = mm.runs(flags, GRIP_MIN_FRAMES)
    blend = max(1, int(round(GRIP_BLEND_S * fps)))
    w = out["weights"]
    for a, b in runs:
        for f in range(a, b + 1):
            w[f] = 1.0
        for k in range(1, blend + 1):
            s = _smoothstep(1.0 - k / (blend + 1))
            if a - k >= 0:
                w[a - k] = max(w[a - k], s)
            if b + k < n:
                w[b + k] = max(w[b + k], s)
    out["frames"] = [f for f in range(n) if w[f] >= 1.0]
    out["runs_s"] = [[round(model.times[a], 4), round(model.times[b], 4)] for a, b in runs]
    return out


# ---- 지시 목표 ----
def resolve_targets(rig: Rig, targets: list[dict], events: dict | None, joints: dict) -> list[dict]:
    """targets[] → 프레임 구간 · 완급 · 본 · 자유도 · 프레임별 목표(위치 · 회전). 사건을 못 찾거나 클립 밖이면 skipped{reason}."""
    model = rig.model
    fps, n = model.fps, rig.frames
    out = []
    for t in targets:
        item = {"id": t["id"], "note": t.get("note"), "effector": t["effector"], "priority": t["priority"], "weight": t["weight"], "spec": t,
                "skipped": None}
        try:
            a, b = _window_s(t, events)
        except BodyFitError as err:
            item["skipped"] = {"reason": err.reason, "message": err.message}
            out.append(item)
            continue
        length = (n - 1) / fps
        if b < -1e-6 or a > length + 1e-6:
            item["skipped"] = {"reason": "TARGET_OUT_OF_RANGE", "message": f"window [{a:.3f}, {b:.3f}] s is outside the clip [0, {length:.3f}]"}
            out.append(item)
            continue
        fa, fb = max(0, int(round(a * fps))), min(n - 1, int(round(b * fps)))
        ease = int(round(t["ease_s"] * fps))
        ramp = [0.0] * n
        for f in range(max(0, fa - ease), min(n, fb + ease + 1)):
            if fa <= f <= fb:
                ramp[f] = 1.0
            elif f < fa:
                ramp[f] = _smoothstep((f - (fa - ease - 1)) / (ease + 1))
            else:
                ramp[f] = _smoothstep(((fb + ease + 1) - f) / (ease + 1))
        kind, side, bone, dof = _effector(rig, t)
        item.update(window_s=[round(a, 4), round(b, 4)], frames=[fa, fb], ease_frames=ease, ramp=ramp, kind=kind, side=side, bone=bone,
                    bone_name=model.bones[bone], dof=dof)
        pos, rot = t["position"], t["rotation"]
        item["pos"], item["rot"], item["away"] = {}, {}, None
        if pos and "away_from" in pos:
            center = _away_bone(rig, pos["away_from"])
            item["away"] = {"bone": center, "min_cm": float(pos["min_cm"])}
        for f in range(n):
            s = ramp[f]
            if s <= 0.0:
                continue
            frame = rig.body_frame(f)
            p0, q0 = model.poses[f][bone][1], model.poses[f][bone][0]
            if pos and "offset_cm" in pos:
                off = _body_vec(frame, pos["offset_cm"]) if pos["space"] == "body" else tuple(pos["offset_cm"])
                item["pos"][f] = _add(p0, _scale(off, s))
            elif pos and "absolute_cm" in pos:
                full = _add(frame[0], _body_vec(frame, pos["absolute_cm"])) if pos["space"] == "body" else tuple(pos["absolute_cm"])
                item["pos"][f] = _add(p0, _scale(_sub(full, p0), s))
            if rot:
                if rot["space"] == "body":
                    full = bm.qnormalize(bm.qmul(_body_rot(frame, rot["offset_deg"]), q0))
                else:
                    full = bm.qnormalize(bm.qmul(q0, qexp(tuple(math.radians(v) for v in rot["offset_deg"]))))
                item["rot"][f] = _slerp(q0, full, s)
        out.append(item)
    return out


def _window_s(t: dict, events: dict | None) -> tuple[float, float]:
    at, hold = t["at"], float(t["hold_s"])
    if "time" in at:
        return float(at["time"]), float(at["time"]) + hold
    if "window" in at:
        return float(at["window"][0]), float(at["window"][1])
    name, off = at["event"], float(at.get("offset_s", 0.0))
    ev = (events or {}).get(name)
    if name in timing.WINDOW_EVENTS:
        if name == "both_planted":
            items = ev or []
            k = int(at.get("index", 0))
            ev = items[k] if k < len(items) else None
        if not ev:
            raise BodyFitError("at.event", f"event {name}[{at.get('index', 0)}] not found", "EVENT_NOT_FOUND")
        return float(ev[0]) + off, float(ev[1]) + off
    if ev is None:
        raise BodyFitError("at.event", f"event {name} not found ({(events or {}).get('reason') or 'no swing'})", "EVENT_NOT_FOUND")
    return float(ev) + off, float(ev) + off + hold


def _effector(rig: Rig, t: dict) -> tuple[str, str | None, int, list]:
    """→ (종류, 쪽, 본, 자유도 [(관절, 종류)]). 종류 arm · spine · neck · pelvis · foot."""
    model, name = rig.model, t["effector"]
    rot = t["rotation"] is not None
    if name in ("hand_l", "hand_r"):
        side = name[-1]
        dof = [(rig.arms[side]["wrist"], "wrist")] if rot else []
        return "arm", side, rig.arms[side]["wrist"], dof
    if name in ("foot_l", "foot_r"):
        side = name[-1]
        if side not in rig.legs:
            raise BodyFitError(f"targets.{t['id']}.effector", f"{name}: the body model has no {side} leg", "UNKNOWN_EFFECTOR")
        return "foot", side, rig.legs[side]["foot"], []
    if name == "pelvis":
        if rig.pelvis is None or set(rig.legs) != {"l", "r"}:
            raise BodyFitError(f"targets.{t['id']}.effector", "pelvis targets need the pelvis and both legs in the body model", "UNKNOWN_EFFECTOR")
        return "pelvis", None, rig.pelvis, [(rig.pelvis, "pelvis")]
    if name == "head":
        if not rig.neck:
            raise BodyFitError(f"targets.{t['id']}.effector", "the body model has no neck/head chain", "UNKNOWN_EFFECTOR")
        return "neck", None, rig.head, [(b, "neck") for b in rig.neck]
    bone = model.index.get(name)
    if bone is None:
        raise BodyFitError(f"targets.{t['id']}.effector", f"{name} is not a body-model bone or one of {list(EFFECTORS)}", "UNKNOWN_EFFECTOR")
    if bone in rig.spine:
        chain = rig.spine[:rig.spine.index(bone) + 1]
        return "spine", None, bone, [(b, "spine") for b in chain]
    if bone in rig.neck:
        return "neck", None, bone, [(b, "neck") for b in rig.neck[:rig.neck.index(bone) + 1]]
    for side, arm in rig.arms.items():
        root = arm["clavicle"] if arm["clavicle"] is not None else arm["upper"]
        if root in rig.anc_set[bone]:
            dof = [(arm["wrist"], "wrist")] if rot and arm["wrist"] in rig.anc_set[bone] else []
            return "arm", side, bone, dof
    raise BodyFitError(f"targets.{t['id']}.effector", f"{name} is not on an arm, the spine or the neck (legs: give foot_l / foot_r)", "UNKNOWN_EFFECTOR")


def _away_bone(rig: Rig, name: str) -> int:
    alias = {"head": rig.head, "pelvis": rig.pelvis, "hand_l": rig.arms["l"]["wrist"], "hand_r": rig.arms["r"]["wrist"]}
    bone = alias.get(name) if name in alias else rig.model.index.get(name)
    if bone is None:
        raise BodyFitError("position.away_from", f"{name} is not a body-model bone or part", "UNKNOWN_EFFECTOR")
    return bone


# ---- 풀이 ----
class Solver:
    """한 풀이 — 프레임별 감쇠 GN · 관통 몫 매끈화 · 재검사 · 보조 팔 다듬기."""

    def __init__(self, model: bm.BodyModel, cfg: dict, *, grip: dict | None = None, targets: list[dict] | None = None, loop: bool = False):
        self.model = model
        self.rig = Rig(model)
        self.cfg = cfg
        self.scale = model.scale
        self.loop = bool(loop) and self.rig.frames > 3   # 원본 루프(validate numeric.loop) — 시간 처리를 순환으로(끝 프레임 = 첫 프레임)
        self.margin = cfg["clearance"]["margin_cm"] * model.scale
        # 몸 지도(몸통 · 넓적다리 · 머리목)에서 허용하는 깊이 — allow_contact(기본)면 맞닿음(≤ contact_cm)까지 정상(손끼리와 같은 규칙, 관통 판정
        # penetration_cm 은 그대로). 처음 판(margin 만큼 떼기)은 엄지 끝 하나가 넓적다리를 스치는 걷기에서도 팔 전체를 바깥으로 밀었다
        contact = cfg["clearance"]["allow_contact"]
        self.body_allow = {name: model.contact_cm if contact and name in CONTACT_MAPS else -self.margin for name in model.maps}
        self.hand_contact = model.contact_cm
        self.w = cfg["weights"]
        j = cfg["joints"]
        self.caps = {"clavicle": math.radians(j["clavicle_deg"]), "upper": math.radians(j["upper_arm_deg"]), "elbow": math.radians(j["elbow_deg"]),
                     "wrist": math.radians(j["wrist_deg"]), "pelvis_cm": j["pelvis_cm"], "pelvis": math.radians(j["pelvis_deg"])}
        rig = self.rig
        self.grip = grip or {"weights": [0.0] * rig.frames, "lead": "r", "off": "l", "frames": []}
        self.targets = [t for t in (targets or []) if not t.get("skipped")]
        self.hands = bool(cfg["clearance"]["hands"]) and all(m in model.maps for m in HAND_MAPS)
        self.upper_mode = cfg["clearance"]["upper_arm"]
        # 관절 종류 · 상한 — 목표 사슬은 상한을 마디 수로 나눈다(합 ≤ 상한)
        self.kind = {}
        for side, arm in rig.arms.items():
            if arm["clavicle"] is not None:
                self.kind[arm["clavicle"]] = "clavicle"
            self.kind[arm["upper"]] = "upper"
            self.kind[arm["elbow"]] = "elbow"
            self.kind[arm["wrist"]] = "wrist"
        self.cap_of = {b: self.caps[k] for b, k in self.kind.items()}
        for t in self.targets:
            for b, k in t["dof"]:
                self.kind.setdefault(b, k)
                if k == "spine":
                    self.cap_of[b] = math.radians(j["spine_deg_for_targets"]) / max(1, len([x for x in t["dof"] if x[1] == "spine"]))
                elif k == "neck":
                    self.cap_of[b] = math.radians(j["neck_deg_for_targets"]) / max(1, len([x for x in t["dof"] if x[1] == "neck"]))
                elif k == "pelvis":
                    self.cap_of[b] = self.caps["pelvis"]
        # 점 · 지도 · 기준 본
        self.points = model.points
        self.arm_points = [i for i, p in enumerate(self.points) if p["part"] in bm.ARM_PARTS]
        self.maps = model.maps
        self.anchors = {}
        legs = {s: g for s, g in rig.legs.items()}
        for name in model.maps:
            if name.startswith("thigh_") and name[-1] in legs:
                self.anchors[name] = [legs[name[-1]]["thigh"]]
            elif name.startswith("calf_") and name[-1] in legs:
                self.anchors[name] = [legs[name[-1]]["knee"]]
            elif name.startswith("hand_"):
                self.anchors[name] = [rig.arms[name[-1]]["wrist"]]
            elif name.startswith("forearm_"):
                self.anchors[name] = [rig.arms[name[-1]]["elbow"]]
            elif name == "head_neck" and rig.neck:
                self.anchors[name] = list(rig.neck)
            elif name == "torso" and rig.pelvis is not None:
                self.anchors[name] = [rig.pelvis] + [b for b in rig.spine if b != rig.pelvis]
        # 파지 — 보조 손바닥 점(손목 로컬, 0 번 프레임 손 점 중심) · 프레임별 원래 상대 변환
        self.arm_base = {s: rig.parents[a["clavicle"] if a["clavicle"] is not None else a["upper"]] for s, a in rig.arms.items()}
        g = self.grip
        self.lead, self.off = g["lead"], g["off"]
        self.palm_local = self._palm_local(self.off)
        self.keep_rel = {}
        for f in range(rig.frames):
            if g["weights"][f] > 0.0:
                pose = model.poses[f]
                lw, ow = pose[rig.arms[self.lead]["wrist"]], pose[rig.arms[self.off]["wrist"]]
                palm = bm.transform_point(ow, self.palm_local)
                self.keep_rel[f] = (bm.qrot(bm.qconj(lw[0]), _sub(palm, lw[1])), bm.qnormalize(bm.qmul(bm.qconj(lw[0]), ow[0])))
        self.orig_upper_depth: dict = {}
        self.stats = {"frame_solves": 0, "evaluations": 0, "clamped": {}}

    def _palm_local(self, side: str):
        rig, model = self.rig, self.model
        wrist = rig.arms[side]["wrist"]
        pts = [p for p in self.points if p["side"] == side and p["part"] == "hand"]
        if not pts:
            return (0.0, 0.0, 0.0)
        pose = model.poses[0]
        acc = (0.0, 0.0, 0.0)
        for p in pts:
            acc = _add(acc, model.skin(pose, p))
        c = _scale(acc, 1.0 / len(pts))
        q, t, _ = pose[wrist]
        return bm.qrot(bm.qconj(q), _sub(c, t))

    # ---- 프레임별 자유도 ----
    def _joints(self, f: int, only: set | None = None) -> list:
        rig = self.rig
        out = []
        for side in ("l", "r"):
            arm = rig.arms[side]
            for k in ("clavicle", "upper", "elbow"):
                if arm[k] is not None:
                    out.append(arm[k])
        if self.grip["weights"][f] > 0.0:
            # 파지 방향을 맞출 때만 손목을 연다(그 밖은 손목 로컬 원래대로) — 주 손목도 열어야 팔을 옮겨도 주 손 방향(주 손 충실도)이 남고 보조 손목이
            # 혼자 주 손 회전 변화를 다 떠안지 않는다(낫 정정 선택 — 보조 손목만이면 상대 방향 23°)
            out += [rig.arms[self.off]["wrist"], rig.arms[self.lead]["wrist"]]
        for t in self.targets:
            if t["ramp"][f] > 0.0:
                for b, _ in t["dof"]:
                    if b not in out:
                        out.append(b)
        if only is not None:
            out = [b for b in out if b in only]
        return out

    def _dofs(self, f: int, joints: list, state: dict, pose) -> list:
        """[(관절, 'r' | 't', 부모 공간 축, 컴포넌트 축)] — swing 축은 지금 뼈 방향에 수직, 경첩 = 위팔 로컬 축."""
        rig, local = self.rig, self.rig.local[f]
        out = []
        for b in joints:
            kind = self.kind[b]
            p = rig.parents[b]
            pq = pose[p][0] if p >= 0 else (0.0, 0.0, 0.0, 1.0)
            if kind in ("clavicle", "upper"):
                side = next(s for s, a in rig.arms.items() if a[kind] == b)
                child = rig.arms[side]["upper" if kind == "clavicle" else "elbow"]
                q_now = bm.qmul(qexp(state["rot"].get(b, (0.0, 0.0, 0.0))), local[b][0])
                d = _unit(bm.qrot(q_now, local[child][1]))
                axes = _perp(d)
            elif kind == "elbow":
                side = next(s for s, a in rig.arms.items() if a["elbow"] == b)
                axes = (rig.hinge[side][f],)
            else:
                axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            for a in axes:
                out.append((b, "r", a, bm.qrot(pq, a)))
            if kind == "pelvis":
                for a in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
                    out.append((b, "t", a, bm.qrot(pq, a)))
        return out

    # ---- 지도 조회 ----
    def _anchor(self, name: str, f: int, p, pose):
        chain = self.anchors.get(name)
        if not chain:
            return None
        if len(chain) == 1:
            return chain[0]
        ax = self.maps[name].axes[f]
        if ax["length"] <= 0.0:
            return chain[0]
        q = _rel_point(self.model.poses[f][chain[0]], pose[chain[0]], p) if pose[chain[0]] is not self.model.poses[f][chain[0]] else p
        t = _dot(_sub(q, ax["a"]), ax["dir"]) / ax["length"]
        best = chain[0]
        for b in chain[1:]:
            tb = _dot(_sub(self.model.poses[f][b][1], ax["a"]), ax["dir"]) / ax["length"]
            if tb <= t:
                best = b
        return best

    def probe(self, name: str, f: int, p, pose, min_t: float | None = None):
        """→ (깊이 cm, 바깥 방향(풀이 공간), 기준 본, t 칸) | None — 기준 본이 움직였으면 점을 원래 자리로 되돌려 묻는다."""
        mp = self.maps[name]
        anchor = self._anchor(name, f, p, pose)
        q, back = p, None
        if anchor is not None and pose[anchor] is not self.model.poses[f][anchor]:
            orig = self.model.poses[f][anchor]
            q = _rel_point(orig, pose[anchor], p)
            back = bm.qmul(pose[anchor][0], bm.qconj(orig[0]))
        hit = mp.depth(f, q, min_t)
        if hit is None:
            return None
        ax = mp.axes[f]
        rel = _sub(q, ax["a"])
        radial = _sub(rel, _scale(ax["dir"], _dot(rel, ax["dir"])))
        n = _unit(radial, ax["x"])
        if back is not None:
            n = bm.qrot(back, n)
        return hit[0], n, anchor, hit[1]

    def _maps_for(self, side: str) -> list:
        """팔 점이 묻는 지도 — 몸통 · 넓적다리 · 머리목 · (hands 면) 반대 팔 손 · 아래팔."""
        names = [m for m in ("torso", "thigh_l", "thigh_r", "head_neck") if m in self.maps]
        if self.hands:
            o = self.rig.side_of(side)
            names += [f"hand_{o}", f"forearm_{o}"]
        return names

    def body_part(self, name: str, t_bin: int) -> str:
        return self.model.torso_part(t_bin) if name == "torso" else name

    # ---- 평가 ----
    def _jac_point(self, contribs, dofs, pose) -> list:
        """LBS 점(또는 강체 점)의 자유도별 미분 — contribs[(본, 가중, 위치)]."""
        rig = self.rig
        out = []
        for b, kind, _, w in dofs:
            c = pose[b][1]
            acc = (0.0, 0.0, 0.0)
            for bone, wt, pb in contribs:
                if b in rig.anc_set[bone]:
                    acc = _add(acc, _scale(_cross(w, _sub(pb, c)) if kind == "r" else w, wt))
            out.append(acc)
        return out

    def _jac_rigid(self, bone: int, p, dofs, pose) -> list:
        return self._jac_point([(bone, 1.0, p)], dofs, pose)

    def _jac_rot(self, bone: int, dofs) -> list:
        return [w if (kind == "r" and b in self.rig.anc_set[bone]) else (0.0, 0.0, 0.0) for b, kind, _, w in dofs]

    def evaluate(self, f: int, state: dict, anchor: dict, families: set, points: list, joints: list, jac: bool = True) -> dict:
        """cost · 정규 방정식(H, g) · 진단. families ⊂ {clear, upper, keep, lead, wrist, fid, targets, reach}."""
        rig, model = self.rig, self.model
        pose, leg_info = self.pose(f, state)
        dofs = self._dofs(f, joints, state, pose) if jac else []
        n = len(dofs)
        H = [[0.0] * n for _ in range(n)] if jac else None
        g = [0.0] * n
        cost = 0.0
        info = {"clear": [], "keep": None, "targets": {}, "reach": leg_info}

        def row(r: float, grad, w2: float):
            nonlocal cost
            cost += w2 * r * r
            if jac:
                for i in range(n):
                    gi = grad[i]
                    if gi:
                        g[i] += w2 * r * gi
                        Hi = H[i]
                        for k in range(i, n):
                            if grad[k]:
                                Hi[k] += w2 * gi * grad[k]

        def rows3(vec, jvec, w2):
            for c in range(3):
                row(vec[c], [jv[c] for jv in jvec] if jac else None, w2)

        # 관통 — 손 · 아래팔(허용 깊이 body_allow 너머) · 위팔(원래보다 안 깊어짐 — TIER upper)
        if "clear" in families or "upper" in families:
            wc = (self.w["clearance"] * TIER["clearance"]) ** 2
            wu = (self.w["clearance"] * TIER["upper"]) ** 2
            for i in points:
                pt = self.points[i]
                upper = pt["part"] == "upper_arm"
                if upper and (self.upper_mode == "off" or "upper" not in families):
                    continue
                if not upper and "clear" not in families:
                    continue
                contribs = [(b, wt, bm.transform_point(pose[b], lp)) for b, wt, lp in pt["influences"]]
                p = (sum(c[2][0] * c[1] for c in contribs), sum(c[2][1] * c[1] for c in contribs), sum(c[2][2] * c[1] for c in contribs))
                jp = None
                for name in self._maps_for(pt["side"]):
                    hit = self.probe(name, f, p, pose)
                    if hit is None:
                        continue
                    d, nrm, anc, t_bin = hit
                    if upper:
                        r = d - max(self.orig_upper_depth.get((f, i, name), self.body_allow[name]), self.body_allow[name])
                    elif name in HAND_MAPS:
                        r = d - self.hand_contact   # 손끼리는 맞닿음(≤ contact_cm)까지 정상 — 파지한 두 손을 떼지 않는다
                    else:
                        r = d - self.body_allow[name]
                    if r <= 0.0:
                        continue
                    info["clear"].append((i, name, d, t_bin, r))
                    if jac:
                        if jp is None:
                            jp = self._jac_point(contribs, dofs, pose)
                        ja = self._jac_rigid(anc, p, dofs, pose) if anc is not None else None
                        grad = [-_dot(nrm, _sub(jp[k], ja[k]) if ja else jp[k]) for k in range(n)]
                    else:
                        grad = None
                    row(r, grad, wu if upper else wc)
        # 파지 keep — 보조 손바닥 점 · 회전의 주 손목 기준 상대 변환
        wk = self.grip["weights"][f]
        if "keep" in families and wk > 0.0 and f in self.keep_rel:
            lw_b, ow_b = rig.arms[self.lead]["wrist"], rig.arms[self.off]["wrist"]
            rel_p, rel_q = self.keep_rel[f]
            lw, ow = pose[lw_b], pose[ow_b]
            palm = bm.transform_point(ow, self.palm_local)
            tgt = _add(bm.qrot(lw[0], rel_p), lw[1])
            e_rot = _scale(qlog(bm.qmul(ow[0], bm.qconj(bm.qmul(lw[0], rel_q)))), ROT_CM)
            w2 = (self.w["grip"] * TIER["grip"] * wk) ** 2
            info["keep"] = {"pos_cm": _norm(_sub(palm, tgt)), "deg": math.degrees(_norm(e_rot) / ROT_CM)}
            if jac:
                ja, jb = self._jac_rigid(ow_b, palm, dofs, pose), self._jac_rigid(lw_b, tgt, dofs, pose)
                ra, rb = self._jac_rot(ow_b, dofs), self._jac_rot(lw_b, dofs)
                rows3(_sub(palm, tgt), [_sub(x, y) for x, y in zip(ja, jb)], w2)
                rows3(e_rot, [_scale(_sub(x, y), ROT_CM) for x, y in zip(ra, rb)], w2)
            else:
                rows3(_sub(palm, tgt), None, w2)
                rows3(e_rot, None, w2)
        # 주 손 충실도(파지 프레임) · 손목 위치 충실도(모든 프레임) — 어깨 바탕 본(쇄골의 부모 — 척추 끝) 기준 상대 변환이라 골반 · 척추 목표가
        # 몸을 옮기면 손은 따라간다(팔 모양 충실도)
        apose = anchor.get("pose") if ("lead" in families or "wrist" in families) else None
        for side in ("l", "r") if apose is not None else ():
            wb, base = rig.arms[side]["wrist"], self.arm_base[side]
            pw, aw, pb, ab = pose[wb], apose[wb], pose[base], apose[base]
            tgt = _add(bm.qrot(pb[0], bm.qrot(bm.qconj(ab[0]), _sub(aw[1], ab[1]))), pb[1])
            jpos = [_sub(x, y) for x, y in zip(self._jac_rigid(wb, pw[1], dofs, pose), self._jac_rigid(base, tgt, dofs, pose))] if jac else None
            if "lead" in families and side == self.lead and wk > 0.0:
                w2 = (self.w["lead_hand"] * TIER["soft"] * wk) ** 2
                q_tgt = bm.qmul(pb[0], bm.qmul(bm.qconj(ab[0]), aw[0]))
                e_rot = _scale(qlog(bm.qmul(pw[0], bm.qconj(q_tgt))), ROT_CM)
                rows3(_sub(pw[1], tgt), jpos, w2)
                rows3(e_rot, [_scale(_sub(x, y), ROT_CM) for x, y in zip(self._jac_rot(wb, dofs), self._jac_rot(base, dofs))] if jac else None, w2)
            if "wrist" in families:
                rows3(_sub(pw[1], tgt), jpos, (self.w["fidelity"] * TIER["soft"]) ** 2)
        # 지시 목표 — 완급(목표 자체를 0 → 1) · 위치 · 회전 · 떨어뜨리기
        if "targets" in families:
            for t in self.targets:
                s = t["ramp"][f]
                if s <= 0.0 or t["kind"] == "foot":
                    continue
                w2 = (self.w["targets"] * t["weight"] * (TIER["hard_target"] if t["priority"] == "hard" else TIER["target"])) ** 2
                b = t["bone"]
                pb = pose[b]
                err = {}
                if f in t["pos"]:
                    e = _sub(pb[1], t["pos"][f])
                    err["pos_cm"] = _norm(e)
                    rows3(e, self._jac_rigid(b, pb[1], dofs, pose) if jac else None, w2)
                if f in t["rot"]:
                    e = _scale(qlog(bm.qmul(pb[0], bm.qconj(t["rot"][f]))), ROT_CM)
                    err["deg"] = math.degrees(_norm(e) / ROT_CM)
                    rows3(e, [_scale(x, ROT_CM) for x in self._jac_rot(b, dofs)] if jac else None, w2)
                if t["away"]:
                    c = pose[t["away"]["bone"]][1]
                    d0 = _norm(_sub(model.poses[f][b][1], model.poses[f][t["away"]["bone"]][1]))
                    want = d0 + s * max(0.0, t["away"]["min_cm"] - d0)
                    v = _sub(pb[1], c)
                    dist = _norm(v)
                    err["away_cm"] = max(0.0, want - dist)
                    if want - dist > 0.0:
                        u = _unit(v)
                        if jac:
                            ja, jb = self._jac_rigid(b, pb[1], dofs, pose), self._jac_rigid(t["away"]["bone"], c, dofs, pose)
                            row(want - dist, [-_dot(u, _sub(x, y)) for x, y in zip(ja, jb)], w2)
                        else:
                            row(want - dist, None, w2)
                info["targets"][t["id"]] = err
        # 다리 늘어남(골반이 움직인 프레임)
        if "reach" in families and leg_info:
            w2 = (self.w["pins"] * TIER["clearance"]) ** 2
            for side, li in leg_info.items():
                over = li["reach_cm"] - REACH * rig.leg_len[side]
                if over > 0.0:
                    hb = rig.legs[side]["thigh"]
                    hip = pose[hb][1]
                    u = _unit(_sub(hip, self.ankle_target(f, side)))
                    row(over, [_dot(u, x) for x in self._jac_rigid(rig.parents[hb], hip, dofs, pose)] if jac else None, w2)
        # 관절 변화 충실도(기준 = anchor 상태) · 시간 연속(앞 프레임 보정 쪽 — 프레임마다 다른 해로 뛰지 않게)
        if "fid" in families and jac:
            wf = (self.w["fidelity"] * TIER["soft"]) ** 2
            prev = anchor.get("prev")
            for k, (b, kind, a, _) in enumerate(dofs):
                cost_j = JOINT_COST.get(self.kind.get(b, "upper"), 1.0)
                bucket = "rot" if kind == "r" else "trans"
                scale_k = (FID_CM if kind == "r" else 1.0) * cost_j
                for ref, w2 in ((anchor, wf), (prev, wf * TEMPORAL ** 2)):
                    if ref is None:
                        continue
                    v = _sub(state[bucket].get(b, (0.0, 0.0, 0.0)), ref[bucket].get(b, (0.0, 0.0, 0.0)))
                    r = scale_k * _dot(a, v)
                    cost += w2 * r * r
                    g[k] += w2 * r * scale_k
                    H[k][k] += w2 * scale_k * scale_k
        if jac:
            for i in range(n):
                for k in range(i):
                    H[i][k] = H[k][i]
        self.stats["evaluations"] += 1
        return {"cost": cost, "H": H, "g": g, "dofs": dofs, "pose": pose, "info": info}

    # ---- 포즈 ----
    def ankle_target(self, f: int, side: str):
        base = self.model.poses[f][self.rig.legs[side]["foot"]][1]
        for t in self.targets:
            if t["kind"] == "foot" and t["side"] == side and f in t["pos"]:
                return t["pos"][f]
        return base

    def legs_active(self, f: int, state: dict) -> dict:
        """다리 IK 가 필요한 프레임 — 골반이 움직였거나 발 목표가 있다 → {side: 발목 목표}."""
        moved = self.rig.pelvis is not None and (self.rig.pelvis in state["rot"] or self.rig.pelvis in state["trans"])
        out = {}
        for side in self.rig.legs:
            foot_target = any(t["kind"] == "foot" and t["side"] == side and f in t["pos"] for t in self.targets)
            if moved or foot_target:
                out[side] = self.ankle_target(f, side)
        return out

    def pose(self, f: int, state: dict) -> tuple[list, dict]:
        rig = self.rig
        pose = rig.fk(f, state["rot"], state["trans"])
        ankles = self.legs_active(f, state)
        if not ankles:
            return pose, {}
        over, info = rig.leg_overrides(f, pose, ankles)
        return rig.fk(f, state["rot"], state["trans"], over), info

    # ---- 한 프레임 ----
    def _clamp(self, f: int, state: dict) -> None:
        for b, v in list(state["rot"].items()):
            kind = self.kind.get(b)
            if kind == "elbow":
                side = next(s for s, a in self.rig.arms.items() if a["elbow"] == b)
                axis = self.rig.hinge[side][f]
                h = _dot(v, axis)
                off = _sub(v, _scale(axis, h))
                # 원래 굽힘이 한계 밖이어도 0(원래 그대로)은 늘 허용
                lo = max(-self.cap_of[b], min(0.0, BEND_MIN - self.rig.bend0[side][f]))
                hi = min(self.cap_of[b], max(0.0, BEND_MAX - self.rig.bend0[side][f]))
                hc = min(max(h, lo), hi)
                if abs(hc - h) > 1e-4:
                    self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1
                state["rot"][b] = _add(off, _scale(axis, hc))
                continue
            cap = self.cap_of.get(b)
            if cap is not None and _norm(v) > cap:
                state["rot"][b] = _scale(v, cap / _norm(v))
                if _norm(v) > cap + 1e-4:
                    self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1
        for b, v in list(state["trans"].items()):
            cap = self.caps["pelvis_cm"]
            if _norm(v) > cap:
                state["trans"][b] = _scale(v, cap / _norm(v))
                self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1

    def _at_limit(self, f: int, b: int, state: dict) -> bool:
        """관절이 상한(또는 팔꿈치 굽힘 범위 끝 — 다 편 팔은 더 못 뻗는다)에 닿았는가."""
        v = state["rot"].get(b, (0.0, 0.0, 0.0))
        if self.kind.get(b) == "elbow":
            side = next(s for s, a in self.rig.arms.items() if a["elbow"] == b)
            h = _dot(v, self.rig.hinge[side][f])
            bend = self.rig.bend0[side][f] + h
            return bend <= BEND_MIN + 1e-3 or bend >= BEND_MAX - 1e-3 or abs(h) >= self.cap_of[b] - 1e-3
        cap = self.cap_of.get(b)
        return cap is not None and _norm(v) >= cap - 1e-4

    def _toward_cap(self, f: int, b: int, kind: str, v, step):
        """v + step — 넘으면 그 관절 걸음만 상한 위까지 줄인다(나머지 관절 걸음은 그대로 — 뒤 클램프가 GN 방향을 비틀지 않게)."""
        new = _add(v, step)
        if kind == "t":
            cap = self.caps["pelvis_cm"]
        elif self.kind.get(b) == "elbow":
            return new   # 경첩 한계는 _clamp(굽힘 범위)
        else:
            cap = self.cap_of.get(b)
        if cap is None or _norm(new) <= cap:
            return new
        # |v + α·step| = cap 인 α ∈ [0, 1]
        a2, b2, c2 = _dot(step, step), 2.0 * _dot(v, step), _dot(v, v) - cap * cap
        disc = b2 * b2 - 4.0 * a2 * c2
        if a2 <= 1e-18 or disc < 0.0:
            return v
        alpha = min(1.0, max(0.0, (-b2 + math.sqrt(disc)) / (2.0 * a2)))
        return _add(v, _scale(step, alpha))

    @staticmethod
    def _copy(state: dict) -> dict:
        return {"rot": dict(state["rot"]), "trans": dict(state["trans"])}

    def solve_frame(self, f: int, start: dict, anchor: dict, families: set, points: list, only: set | None = None) -> tuple[dict, dict]:
        """감쇠 GN(LM) — start 에서, 충실도 기준 anchor(상태 + 그 포즈). → (상태, 마지막 평가)."""
        joints = self._joints(f, only)
        state = self._copy(start)
        ev = self.evaluate(f, state, anchor, families, points, joints)
        self.stats["frame_solves"] += 1
        mu = 0.1   # 마쿼트 감쇠 — A = H + μ·diag(H)
        for _ in range(MAX_ITER):
            n = len(ev["dofs"])
            if n == 0 or ev["cost"] < 1e-12:
                break
            H, g = ev["H"], ev["g"]
            accepted = False
            for _ in range(LM_RETRIES):
                A = [[H[i][k] + ((mu * H[i][i] + 1e-9) if i == k else 0.0) for k in range(n)] for i in range(n)]
                step = _solve_linear(A, [-x for x in g])
                if step is None:
                    mu *= 10.0
                    continue
                trial = self._copy(state)
                per_joint: dict = {}
                for (b, kind, a, _), s in zip(ev["dofs"], step):
                    key = (b, kind)
                    per_joint[key] = _add(per_joint.get(key, (0.0, 0.0, 0.0)), _scale(a, s))
                shrink = 1.0
                for (b, kind), v in per_joint.items():
                    lim = STEP_RAD if kind == "r" else STEP_CM
                    if _norm(v) > lim:
                        shrink = min(shrink, lim / _norm(v))
                for (b, kind), v in per_joint.items():
                    bucket = trial["rot"] if kind == "r" else trial["trans"]
                    bucket[b] = self._toward_cap(f, b, kind, bucket.get(b, (0.0, 0.0, 0.0)), _scale(v, shrink))
                self._clamp(f, trial)
                ev2 = self.evaluate(f, trial, anchor, families, points, joints)
                if ev2["cost"] < ev["cost"]:
                    gain = ev["cost"] - ev2["cost"]
                    state, ev = trial, ev2
                    mu = max(mu / 3.0, 1e-12)
                    accepted = True
                    if gain < 1e-7 * max(1.0, ev2["cost"]):
                        return state, ev
                    break
                mu *= 4.0
            if not accepted:
                break
        return state, ev

    # ---- 전체 ----
    def _anchor_of(self, f: int, state: dict) -> dict:
        pose, _ = self.pose(f, state)
        return {"rot": dict(state["rot"]), "trans": dict(state["trans"]), "pose": pose}

    def _candidates(self, f: int, pose) -> list:
        """깊이 > −(margin + CANDIDATE_CM) 인 팔 점 — 위팔은 원래 깊이를 기억(안 깊어짐 기준). 문턱은 허용 깊이(allow_contact)와 무관하다 —
        허용 깊이 − 3 cm 로 좁히면 목표가 손을 옮기는 동안 다가오는 넓적다리 점이 후보에서 빠져, 손이 넓적다리 축 위(바깥 방향이 정해지지 않는
        자리)까지 들어가 갇혔다(합성 몸 쪽 목표 4.7 cm)."""
        out = []
        lim = -(self.margin + CANDIDATE_CM * self.scale)
        orig = pose is self.model.poses[f] or all(pose[b] is self.model.poses[f][b] for b in range(len(pose)))
        for i in self.arm_points:
            pt = self.points[i]
            p = self.model.skin(pose, pt)
            hit_any = False
            for name in self._maps_for(pt["side"]):
                hit = self.probe(name, f, p, pose)
                if hit is None:
                    continue
                if pt["part"] == "upper_arm" and orig:
                    self.orig_upper_depth[(f, i, name)] = hit[0]
                if hit[0] > lim:
                    hit_any = True
            if hit_any:
                out.append(i)
        return out

    def _violations(self, f: int, state: dict, points: list) -> dict:
        """다시 풀 위반 — 손 · 아래팔 관통 · keep. 위팔 '안 깊어짐'은 풀 때만 함께 맞추고 위반으로 세지 않는다(TIER upper 주석)."""
        ev = self.evaluate(f, state, {"rot": {}, "trans": {}}, {"clear", "keep"}, points, self._joints(f), jac=False)
        clear = [c for c in ev["info"]["clear"] if c[4] > TOL_CM]
        keep = ev["info"]["keep"]
        bad_keep = bool(keep and (keep["pos_cm"] > KEEP_TOL_CM * self.scale or keep["deg"] > KEEP_TOL_DEG))
        return {"clear": clear, "keep": bad_keep, "keep_err": keep}

    def run(self, log=None) -> dict:
        t0 = time.time()
        rig, n = self.rig, self.rig.frames
        zero = {"rot": {}, "trans": {}}
        radius = int(round(self.cfg["smooth_s"] * self.model.fps))
        cand = [self._candidates(f, self.model.poses[f]) for f in range(n)]
        base_anchor = [self._anchor_of(f, zero) for f in range(n)]
        targeted = [any(t["ramp"][f] > 0.0 for t in self.targets) for f in range(n)]
        # ---- 1 회: x_T(목표 · keep · 충실도) → x(전부) ----
        x_t, x_full, active = [], [], []
        prev_t = prev_full = None
        for f in range(n):
            if targeted[f]:
                st, ev = self.solve_frame(f, prev_t or zero, {**base_anchor[f], "prev": prev_t}, {"keep", "lead", "wrist", "fid", "targets", "reach"}, cand[f])
                prev_t = st
            else:
                st, prev_t = zero, None
            x_t.append(st)
            if targeted[f]:
                # 목표가 손을 옮긴 곳의 점도 후보로(원래 포즈에서는 멀었던 점)
                cand[f] = sorted(set(cand[f]) | set(self._candidates(f, self.pose(f, st)[0])))
            need = self._violations(f, st, cand[f])
            if need["clear"] or need["keep"]:
                start = prev_full if prev_full is not None else st
                sf, _ = self.solve_frame(f, start, {**base_anchor[f], "prev": prev_full}, {"clear", "upper", "keep", "lead", "wrist", "fid", "targets", "reach"},
                                         cand[f])
                prev_full = sf
            else:
                sf, prev_full = st, None
            x_full.append(sf)
            active.append(sf is not st)
        rho = [max((t["ramp"][f] for t in self.targets), default=0.0) for f in range(n)]
        state = self._combine(x_t, [self._diff(a, b) for a, b in zip(x_full, x_t)], radius, rho, active, SPLINE_QUIET_WEIGHT)
        passes = 1
        # ---- 재검사: 남은 하드 잔차가 있는 프레임만 그 값에서 다시(두 팔 함께 — 짝이 맞는다) → 증분도 스플라인으로 이어 붙인다 ----
        # (처음 판의 '보조 팔 따라가기' · '매끈화 없는 마무리'는 위반 프레임만 골라 다시 풀어 이웃과 끊겼다 — 띠 정정 떨림 1.05 → 4.7)
        for _ in range(self.cfg["passes"] - 1 + EXTRA_PASSES):
            cand = [sorted(set(c) | set(self._candidates(f, self.pose(f, state[f])[0]))) for f, c in enumerate(cand)]
            incs, again = [], []
            for f in range(n):
                v = self._violations(f, state[f], cand[f])
                again.append(bool(v["clear"] or v["keep"]))
                if again[-1]:
                    prev = state[f - 1] if f else (state[n - 2] if self.loop else None)
                    sf, _ = self.solve_frame(f, state[f], {**self._anchor_of(f, state[f]), "prev": prev},
                                             {"clear", "upper", "keep", "lead", "wrist", "fid", "targets", "reach"}, cand[f])
                    incs.append(self._diff(sf, state[f]))
                else:
                    incs.append({"rot": {}, "trans": {}})
            if not any(again):
                break
            passes += 1
            # 고립된 위반 프레임의 증분은 넓은 매끈화에 묽어진다 → 바로 이웃(±1 — 자세가 거의 같다, 루프면 감아 돈다)에도 같은 증분을 줘 3 프레임 받침으로
            active = list(again)
            for f in [f for f in range(n) if again[f]]:
                for g in self._neighbors(f, n):
                    if not again[g] and self._size(incs[f]) > self._size(incs[g]):
                        incs[g] = incs[f]
                        active[g] = True
            state = self._combine(state, incs, radius, rho, active, SPLINE_RECHECK_QUIET_WEIGHT)
        if log:
            log(f"body_fit: {n} frames · passes {passes} · {self.stats['frame_solves']} frame solves · {round(time.time() - t0, 1)} s")
        return self._result(state, passes, time.time() - t0)

    def _neighbors(self, f: int, n: int) -> list:
        """±1 프레임 — 루프면 감아 돈다(끝 프레임 = 첫 프레임: 0 · n−1 의 이웃 = n−2 · 1)."""
        if not self.loop:
            return [g for g in (f - 1, f + 1) if 0 <= g < n]
        m = n - 1
        out = []
        for g in ((f % m - 1) % m, (f % m + 1) % m):
            out += [0, m] if g == 0 else [g]
        return out

    @staticmethod
    def _size(d: dict) -> float:
        return math.sqrt(sum(_dot(v, v) for v in d["rot"].values()) + sum(_dot(v, v) for v in d["trans"].values()) * 1e-4)

    @staticmethod
    def _diff(a: dict, b: dict) -> dict:
        out = {"rot": {}, "trans": {}}
        for key in ("rot", "trans"):
            for j in set(a[key]) | set(b[key]):
                d = _sub(a[key].get(j, (0.0, 0.0, 0.0)), b[key].get(j, (0.0, 0.0, 0.0)))
                if _norm(d) > 1e-12:
                    out[key][j] = d
        return out

    def _combine(self, base: list, incs: list, radius: int, rho: list, active: list[bool], quiet: float) -> list:
        """base + 증분 — 목표 구간 밖은 매끈화 S((1 − ρ)·증분), 안(완급 ρ)은 그 프레임 증분 그대로: (1 − ρ)·S + ρ·증분(목표가 관통에 막힌 구간의
        되돌림(T4)이 이웃으로 번지지 않는다). S = 관절 · 성분별 가중 매끈화 스플라인(spline — active = 하드 잔차로 푼 프레임). 끝에 상한.
        루프면 스플라인이 순환이고 끝 프레임 = 첫 프레임 상태(같은 시점 — 목표가 끝 프레임에만 걸려도 첫 프레임 쪽 해를 쓴다)."""
        n = len(base)
        out = [self._copy(s) for s in base]
        joints = {(key, j) for d in incs for key in ("rot", "trans") for j in d[key]}
        for key, j in joints:
            raw = [d[key].get(j, (0.0, 0.0, 0.0)) for d in incs]
            sm = spline([_scale(v, 1.0 - rho[f]) for f, v in enumerate(raw)], active, radius, self.loop, quiet)
            for f in range(n):
                v = _add(_scale(sm[f], 1.0 - rho[f]), _scale(raw[f], rho[f]))
                if _norm(v) > 1e-12:
                    out[f][key][j] = _add(out[f][key].get(j, (0.0, 0.0, 0.0)), v)
        for f in range(n):
            self._clamp(f, out[f])
        if self.loop:
            out[-1] = self._copy(out[0])
        return out

    # ---- 결과 ----
    def _result(self, state: list, passes: int, seconds: float) -> dict:
        rig, model, n = self.rig, self.model, self.rig.frames
        poses, legs = [], []
        for f in range(n):
            p, li = self.pose(f, state[f])
            poses.append(p)
            legs.append(li)
        # 본별 부모 공간 델타 — 회전 = 새 로컬 ⊗ 원래 로컬⁻¹(다리 IK 포함), 이동 = 새 로컬 − 원래 로컬
        rot_out, trans_out = {}, {}
        for f in range(n):
            local0 = rig.local[f]
            for b in range(rig.n):
                if poses[f][b] is model.poses[f][b]:
                    continue
                p = rig.parents[b]
                new_local = poses[f][b] if p < 0 else bm.relative(poses[f][b], poses[f][p])
                dq = bm.qnormalize(bm.qmul(new_local[0], bm.qconj(local0[b][0])))
                dv = bm.to_rotvec_deg(dq)
                dt = _sub(new_local[1], local0[b][1])
                if _norm(dv) > 1e-4:
                    rot_out.setdefault(b, {})[f] = dv
                if _norm(dt) > 1e-4:
                    trans_out.setdefault(b, {})[f] = dt
        deltas = {"bones": []}
        degs = []
        for b in sorted(set(rot_out) | set(trans_out)):
            entry = {"bone": model.bones[b], "rotation_deg": None, "translation_cm": None}
            if b in rot_out:
                entry["rotation_deg"] = [[round(c, 5) for c in rot_out[b].get(f, (0.0, 0.0, 0.0))] for f in range(n)]
                degs += [_norm(v) for v in rot_out[b].values()]
            if b in trans_out:
                entry["translation_cm"] = [[round(c, 5) for c in trans_out[b].get(f, (0.0, 0.0, 0.0))] for f in range(n)]
            deltas["bones"].append(entry)
        changed = sorted({f for d in rot_out.values() for f in d} | {f for d in trans_out.values() for f in d})
        # 루프 이음매 — 첫 · 끝 프레임 델타 차(본별 최대 °, 다리 IK 포함). 루프면 0(순환)
        seam = 0.0
        for d in rot_out.values():
            a, b = bm.from_rotvec_deg(d.get(0, (0.0, 0.0, 0.0))), bm.from_rotvec_deg(d.get(n - 1, (0.0, 0.0, 0.0)))
            seam = max(seam, _norm(bm.to_rotvec_deg(bm.qmul(a, bm.qconj(b)))))
        deltas.update(frames_changed=len(changed), deg_p95=round(bm.percentile(degs, 95.0), 3) if degs else 0.0, deg_max=round(max(degs), 3) if degs else 0.0,
                      clamped={model.bones[b]: c for b, c in self.stats["clamped"].items()})
        # 관절 이동(모델 본 전부 — 보정 구간 밖 0 확인용)
        moved = [max((_norm(_sub(poses[f][b][1], model.poses[f][b][1])) for b in range(rig.n)), default=0.0) for f in range(n)]
        # keep · 목표 달성
        keep = self.keep_report(poses)
        targets = self.target_report(poses, state)
        predicted = measure(model, poses, self)
        return {"version": VERSION, "frames": n, "poses": poses, "state": state, "deltas": deltas, "moved_cm": moved, "changed_frames": changed,
                "keep": keep, "targets": targets, "predicted": predicted, "legs": legs, "passes": passes,
                "loop": {"on": self.loop, "seam_deg": round(seam, 3)},
                "seconds": round(seconds, 2), "stats": {k: v for k, v in self.stats.items() if k != "clamped"}}

    def keep_report(self, poses: list) -> dict:
        rig = self.rig
        pos, deg = [], []
        for f, (rel_p, rel_q) in self.keep_rel.items():
            if self.grip["weights"][f] < 1.0:
                continue
            lw, ow = poses[f][rig.arms[self.lead]["wrist"]], poses[f][rig.arms[self.off]["wrist"]]
            palm = bm.transform_point(ow, self.palm_local)
            pos.append(_norm(_sub(palm, _add(bm.qrot(lw[0], rel_p), lw[1]))))
            deg.append(math.degrees(_norm(qlog(bm.qmul(ow[0], bm.qconj(bm.qmul(lw[0], rel_q)))))))
        return {"frames": len(pos), "pos_cm_p95": round(bm.percentile(pos, 95.0), 3) if pos else None, "pos_cm_max": round(max(pos), 3) if pos else None,
                "deg_p95": round(bm.percentile(deg, 95.0), 3) if deg else None, "deg_max": round(max(deg), 3) if deg else None}

    def target_report(self, poses: list, state: list) -> list:
        """목표마다 구간(완급 1) 오차 — 못 닿으면 blocked_by(그 프레임의 하드 잔차 · 상한)."""
        out = []
        tol_cm, tol_deg = 1.0 * self.scale, 3.0
        for t in self.targets:
            fa, fb = t["frames"]
            pos_err, rot_err, away_err, bad = [], [], [], []
            for f in range(fa, fb + 1):
                pb = poses[f][t["bone"]]
                e = {}
                if f in t["pos"]:
                    e["pos"] = _norm(_sub(pb[1], t["pos"][f]))
                    pos_err.append(e["pos"])
                if f in t["rot"]:
                    e["deg"] = math.degrees(_norm(qlog(bm.qmul(pb[0], bm.qconj(t["rot"][f])))))
                    rot_err.append(e["deg"])
                if t["away"]:
                    c = poses[f][t["away"]["bone"]][1]
                    e["away"] = max(0.0, t["away"]["min_cm"] - _norm(_sub(pb[1], c)))
                    away_err.append(e["away"])
                if e.get("pos", 0.0) > tol_cm or e.get("deg", 0.0) > tol_deg or e.get("away", 0.0) > tol_cm:
                    bad.append(f)
            blocked = set()
            for f in bad:
                v = self._violations(f, state[f], self.arm_points)
                near = self.evaluate(f, state[f], self._anchor_of(f, state[f]), {"clear"}, self.arm_points, self._joints(f), jac=False)["info"]["clear"]
                if near or v["clear"]:
                    blocked.add("clearance")
                if self.grip["weights"][f] > 0.0 and t["kind"] == "arm":
                    blocked.add("grip")
                chain = [b for b, _ in t["dof"]]
                if t["kind"] == "arm":
                    chain += [self.rig.arms[t["side"]][k] for k in ("clavicle", "upper", "elbow") if self.rig.arms[t["side"]][k] is not None]
                if any(self._at_limit(f, b, state[f]) for b in chain):
                    blocked.add("joint_limit")
                if t["kind"] == "pelvis":
                    li = self.pose(f, state[f])[1]
                    if any(x["reach_cm"] > REACH * self.rig.leg_len[s] - 1e-3 for s, x in li.items()):
                        blocked.add("pins")
            pct = lambda xs: round(bm.percentile(xs, 95.0), 3) if xs else None  # noqa: E731
            out.append({"id": t["id"], "note": t["note"], "effector": t["effector"], "bone": t["bone_name"], "priority": t["priority"],
                        "window_s": t["window_s"], "frames": t["frames"], "ease_frames": t["ease_frames"],
                        "requested": {k: t["spec"][k] for k in ("position", "rotation") if t["spec"].get(k)},
                        "achieved": {"error_cm_p95": pct(pos_err or away_err), "error_cm_max": round(max(pos_err or away_err), 3) if (pos_err or away_err) else None,
                                     "error_deg_p95": pct(rot_err), "error_deg_max": round(max(rot_err), 3) if rot_err else None},
                        "reached": not bad, "blocked_by": sorted(blocked) if bad else []})
        return out


# ---- 예측 측정 (C++ parts · hands 쌍과 같은 키 · 통계) ----
def measure(model: bm.BodyModel, poses: list | None = None, solver: Solver | None = None) -> dict:
    """프레임별 포즈(없으면 원래)로 쌍별 깊이 → {series{key: [깊이 | None]}, pairs{"s|part|body": stats}}. 지도는 기준 본을 따라간다(solver 규칙)."""
    solver = solver or Solver(model, normalize(True))
    frames = []
    for f in range(len(model.frames)):
        pose = poses[f] if poses else model.poses[f]
        best: dict = {}
        for i in solver.arm_points:
            pt = solver.points[i]
            p = model.skin(pose, pt)
            for name in solver._maps_for(pt["side"]):
                hit = solver.probe(name, f, p, pose)
                if hit is None:
                    continue
                key = (pt["side"], pt["part"], solver.body_part(name, hit[3]))
                if key not in best or hit[0] > best[key]:
                    best[key] = hit[0]
        frames.append(best)
    keys = sorted({k for best in frames for k in best})
    series = {k: [best.get(k) for best in frames] for k in keys}
    pairs = {"|".join(k): bm.pair_stats(v, model.contact_cm, model.penetration_cm) for k, v in sorted(series.items())}
    return {"series": series, "pairs": pairs}


def solve(model: bm.BodyModel, cfg: dict, *, grip: dict | None = None, targets: list[dict] | None = None, loop: bool = False, log=None) -> dict:
    """한 풀이 — 모델 · 정규화한 fix.body · 파지(grip_weights) · 풀린 목표(resolve_targets) · 원본 루프 여부 → Solver.run 결과."""
    return Solver(model, cfg, grip=grip, targets=targets, loop=loop).run(log=log)


def bone_deltas_op(result: dict) -> dict | None:
    """풀이 결과 → apply_animation_edits op(bone_deltas · space parent). 바꿀 것이 없으면 None."""
    bones = [b for b in result["deltas"]["bones"] if b["rotation_deg"] or b["translation_cm"]]
    return {"op": "bone_deltas", "space": "parent", "bones": bones} if bones else None
