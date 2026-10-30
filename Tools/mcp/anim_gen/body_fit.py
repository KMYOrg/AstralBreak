"""Phase 8-4b · 8-4c — 대상(리타깃이 끝난 Vesper) 애니 위의 한 풀이: 몸 전체 관통 · 양손 파지(keep · 무기 weapon) · 발 pin · 지시 목표
(순수 Python — numpy 없음).

  무기(8-4c) — 요청 weapon(weapon.py 가 메시 사실로 푼 값 → WeaponRig): 무기 = 주 손(부착 본)의 강체. weapon 모드는 keep 대신 보조 손바닥 점 →
             목표 점(원래 손바닥 → 손잡이 선분 위 가장 가까운 점 — 미끄러짐, smootherstep(무기 파지 가중) 보간 · 잔차는 가득 가중 — 8-4c 후속) · 보조 손
             회전(무기 공간 ± 허용각, 없으면 원래 상대 회전) · 보조 손목 굽힘 ≤ max(원래 최대, wrist_bend_max_deg)(관통 층) — keep 과 같은 층, 주 손 방향
             충실도는 keep 층(무기 방향). 손끼리 관통은 하드 그대로(보조 손이 미끄러져 피한다). 매끈화 · 재검사 뒤 파지 구간 전체를 보조 팔만으로
             마무리(_snap_weapon — 스플라인이 묽힌 손잡이 거리를 되돌린다).
  손목 굽힘 — 파지 프레임(손목을 여는 프레임) 보조 손목 굽힘 ≤ 원래 + BEND_KEEP_TOL_DEG(관통 층 hinge — 8-4c 후속, keep 이 팔 보정을 손목에 떠넘겨 원본보다
             꺾이지 않게). 본 풀이에는 두지 않고 본 풀이 뒤 보조 손목만 다듬는다(_finish_wrist — 2차: 본 풀이에 걸면 팔 보정 경로가 바뀌어 매끈화 뒤
             재검사가 못 따라갔다). 손가락 뿌리 = 대상 메시 손가락 체인 제안 {Side}Middle 시작(fingers), 없으면 끈다.
             weapon_tip 목표 = 부착 본의 강체 점. 무기-몸 관통은 기록만(weapon_body — 무기 기록 점 ↔ 같은 몸 지도). 무기가 없으면 이 경로는 쉰다.
             무기 파지는 원래 보조 손이 손잡이 근처(WEAPON_NEAR_CM × scale)인 구간만 — 먼 띠 프레임은 keep(사용자 결정 '가' — grip_weights).
  샘플 전이(8-4c c2) — pose_from[]: 같은 스켈레톤 애니(샘플)의 로컬 회전을 본 묶음(bundle_bones — 템플릿 체인 · 손 트리, 이름 추측 없음)으로 가져온다.
             지시 목표와 같은 (가) 블록: 목표 없는 해(base) 위에서 완급 > 0 블록만 '덮은 자세'(_overlay — 묶음 본 로컬 = slerp(base 로컬, 샘플 로컬,
             weight × 완급), pose = 샘플 한 시각 · motion = 구간 단조 시각 사상, 사건은 샘플 · 대상 각자 timing.events)를 출발점 · 충실도 기준으로
             다시 푼다. 손가락 · 트위스트 등 자유도가 아닌 본은 덮은 값 그대로, 척추 · 목머리는 그 구간만 3축 자유도, 팔은 기존 자유도(관절 상한은 덮은
             자세에서 잰다 — ref_rot). 하드(관통 바닥 = base 깊이 · keep = base 관계 · 발)가 이기고, 묶음 본 충실도는 × weights.pose_from. 덮은 자세에서
             벗어난 본은 pose_from_report 가 막은 것과 함께 보고한다(POSE_FROM_PARTIAL).

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
  시간     — 관통 몫 Δ 만 가중 매끈화 스플라인(spline — 하드 잔차로 푼 프레임 가중 SPLINE_ACTIVE_WEIGHT · 그 밖 SPLINE_QUIET_WEIGHT,
             2차 차분 벌점, 보정 구간 ± 2·폭 밖 0) → S(Δ). 원본이 루프(validate numeric.loop — C++ bLoop)면 순환(끝 프레임 = 첫 프레임 —
             스플라인 · 재검사 받침이 감아 돌고 첫 · 끝 델타가 같다).
  지시 목표 — (가) 목표 없는 풀이(base — 목표 없는 Job 과 같은 코드 · 입력)를 먼저 끝내고, 완급 > 0 블록(구간 ± ease)만 base 를 출발점 · 기준으로
             다시 푼다: 블록 밖 = base 그대로(구간 ± ease 밖 변화 0). 블록 안은 두 번 — x_T(목표 · keep · 충실도) → x(전부), 관통 몫 Δ = x − x_T 는
             완급 ρ 만큼 그 프레임 값 · 나머지는 블록 안 스플라인(spline_block — 앞뒤 0 고정). 목표는 완급(목표 자체를
             smootherstep 으로 0 → 1)이라 매끈화하지 않는다.
  재검사   — 하드 잔차가 남은 프레임만 그 값에서 다시(두 팔 함께) → 증분(± 1 프레임 받침)을 같은 스플라인(바깥 가중만
             SPLINE_RECHECK_QUIET_WEIGHT)으로 더한다(passes + EXTRA_PASSES).
             위반 프레임만 매끈화 없이 고치는 처음 판(보조 팔 따라가기 · 마무리)은 이웃과 끊겨 떨림을 만들었다(띠 정정 zigzag 1.05 → 4.7) — 남는 작은
             위반(keep ≈ 1 ~ 2 cm · 고립 관통 프레임)은 한계로 보고한다.
결과 = 본별 프레임 델타(bone_deltas) · 모델 예측(쌍별 깊이 — C++ 실측과 대조) · keep 오차 · 목표 달성 · 남은 관통.
"""
from __future__ import annotations

import bisect
import copy
import math
import re
import time

from . import body_model as bm
from . import motion_metrics as mm
from . import timing
from .local_ai import refine
from .weapon import hand_tree

VERSION = 1
DEFAULTS = {
    "mode": "auto",
    "clearance": {"margin_cm": 0.5, "allow_contact": True, "hands": True, "upper_arm": "no_worse", "secondary": "record", "legs": False},
    "grip": {"mode": "auto", "lead_hand": "right", "window": None, "spacing_cm": None, "tolerance_cm": None, "blend_s": None, "wrist_bend_max_deg": None},
    "joints": {"clavicle_deg": 10.0, "upper_arm_deg": 45.0, "elbow_deg": 60.0, "wrist_deg": 30.0, "spine_deg": 0.0, "spine_deg_for_targets": 20.0,
               "neck_deg_for_targets": 20.0, "pelvis_cm": 15.0, "pelvis_deg": 10.0},
    "targets": [],
    "pose_from": [],
    "weights": {"clearance": 10.0, "grip": 10.0, "pins": 10.0, "targets": 5.0, "pose_from": 3.0, "lead_hand": 3.0, "fidelity": 1.0},
    "smooth_s": 0.13,
    "passes": 3,
}
TARGET_KEYS = {"id", "note", "effector", "at", "hold_s", "position", "rotation", "ease_s", "weight", "priority"}
TARGET_DEFAULTS = {"note": None, "hold_s": 0.0, "position": None, "rotation": None, "ease_s": 0.15, "weight": 1.0, "priority": "soft"}
EFFECTORS = ("hand_l", "hand_r", "foot_l", "foot_r", "head", "pelvis", "weapon_tip")
POSE_FROM_KEYS = {"id", "note", "asset", "bones", "mode", "source", "target", "hold_s", "ease_s", "weight", "space"}
POSE_FROM_DEFAULTS = {"note": None, "hold_s": 0.0, "ease_s": 0.15, "weight": 1.0, "space": "local"}
# 샘플 전이 묶음 프리셋(8-4c c2) — 대상 메시 템플릿 체인 이름 · 손 쪽(bundle_bones). legs 는 발 pin 과 함께 다리 IK 가 필요해 8-4d(다리 블록)까지 막는다
BUNDLE_PRESETS = ("spine", "neck_head", "arm_l", "arm_r", "upper_body", "fingers_l", "fingers_r")
POSE_FROM_TOL_DEG = 0.5  # 기준 7 — 막히지 않은 묶음 본의 로컬 회전 = 덮은 자세(블렌드) 허용
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
# weapon 모드(8-4c)의 경계 블렌드 — 보조 손을 원래 자리에서 손잡이로 옮기므로(keep 은 원래 관계라 옮김이 작다) 이음매가 튀지 않게 keep 의 두 배
GRIP_BLEND_WEAPON_S = 0.2
# weapon 파지를 거는 거리(원래 보조 손바닥 점 ↔ 손잡이, × scale) — 사용자 결정 '가'(2026-10-29): 무기를 오른손 소켓 · 운영 offset 으로 붙이면 생성 낫
# 애니의 왼손은 자루에서 p50 30 ~ 43 cm(두 손 선 ∠ 자루 ≈ 60° — 오른손 방향이 운영과 다르다)라 붙이는 것은 보정이 아니라 재배치 → 이미 가까운
# 프레임만 붙이고 먼 프레임은 keep + 한계 GRIP_NOT_APPLICABLE(원인은 생성 쪽 후속). 운영 낫 Attack2 는 E0 선분에서 p50 11.7 · p5 2.7 cm
WEAPON_NEAR_CM = 15.0
# 손잡이에서 주 손 자리를 뺀 폭(± 이 값 × scale, 선분 위) — 결정 ③(손끼리 하드 · 보조 손이 미끄러져 피한다): E0 선분이 주 손 자리(선분 위 ≈ 14 cm)를
# 지나가 보조 손을 투영점으로 끌면 손끼리 관통에 막혀 7 cm 가 남고 떨렸다(운영 Attack2 오프라인 — zigzag 8.2 → 23). 자리를 빼면 가까운 조각 끝으로 간다
WEAPON_LEAD_CLEAR_CM = 7.0
WEAPON_TOL_CM = 0.5      # 재검사 대상이 되는 무기 파지 오차(손바닥 점 ↔ 손잡이 × 가중 — cm × scale) · 회전 · 손목 굽힘 초과(°) — 기준 1(p95 1 cm) 의 절반
WEAPON_TOL_DEG, BEND_TOL_DEG = 2.0, 1.0
# keep 파지 프레임 보조 손목 굽힘 허용(원래 굽힘 위 °) — 원래보다 더 굽히지 않는다(8-4c 후속, 사용자 Persona 2026-10-29): 손목을 여는 파지 프레임에서
# keep(주 손 기준 상대 회전)이 팔을 옮긴 만큼을 보조 손목이 떠안아 원본보다 더 꺾였다(낫 정정 8-4b 실측 원본 91.1 → 102.1°, 띠 정정 f72 +1 ~ +3°)
BEND_KEEP_TOL_DEG = 2.0
# 본 풀이 잔차 묶음 — 관통 · 위팔 · keep · 무기 파지 · 주 손 · 손목 위치 · 관절 충실도 · 지시 목표 · 다리 늘어남. 손목 굽힘 상한(bend)은 본 풀이 뒤
# 다듬기(_snap_weapon · _finish_wrist)에만 둔다(8-4c 후속 2차 — _finish_wrist 주석)
FAMILIES = frozenset({"clear", "upper", "keep", "weapon", "lead", "wrist", "fid", "targets", "reach"})
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
    if g["mode"] not in ("auto", "weapon", "keep", "off"):
        raise BodyFitError("fix.body.grip.mode", "must be auto | weapon | keep | off (auto = keep inside the grip band — the weapon grip is opt-in: "
                           "weapon, with the request weapon's grip for the other hand)")
    if g["lead_hand"] not in ("left", "right"):
        raise BodyFitError("fix.body.grip.lead_hand", "must be left | right")
    if g["window"] is not None and not (isinstance(g["window"], list) and len(g["window"]) == 2 and all(_num(v, 0.0, 600.0) for v in g["window"])
                                        and g["window"][0] < g["window"][1]):
        raise BodyFitError("fix.body.grip.window", "must be null or [from_s, to_s] with from < to")
    for key, hi in (("spacing_cm", 200.0), ("tolerance_cm", 100.0)):
        if g[key] is not None and not (_num(g[key], 0.0, hi) and g[key] > 0):
            raise BodyFitError(f"fix.body.grip.{key}", f"must be null or a number in (0, {hi:g}] cm")
    if g["blend_s"] is not None and not _num(g["blend_s"], 0.0, 1.0):
        raise BodyFitError("fix.body.grip.blend_s", "must be null (keep 0.1 · weapon 0.2 s) or a number in [0, 1] seconds")
    if g["wrist_bend_max_deg"] is not None and not _num(g["wrist_bend_max_deg"], 0.0, 180.0):
        raise BodyFitError("fix.body.grip.wrist_bend_max_deg", "must be null or a number in [0, 180] — the off-hand wrist bend cap is max(this, the clip's own max)")
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
    if not isinstance(out["pose_from"], list):
        raise BodyFitError("fix.body.pose_from", "must be a list")
    out["pose_from"] = [_pose_from(i, p) for i, p in enumerate(out["pose_from"])]
    ids += [p["id"] for p in out["pose_from"]]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        raise BodyFitError("fix.body.pose_from", f"duplicate id(s) {dup} (targets and pose_from share one id space)", "DUPLICATE_ID")
    return out


def _pose_from(i: int, raw) -> dict:
    """pose_from[i] — 샘플 전이 한 항목(8-4c c2). bones = 프리셋(BUNDLE_PRESETS) · 본 이름 하나 또는 목록(실행 · 계획이 bundle_bones 로 푼다)."""
    where = f"fix.body.pose_from[{i}]"
    if not isinstance(raw, dict):
        raise BodyFitError(where, "must be an object")
    extra = sorted(set(raw) - POSE_FROM_KEYS)
    if extra:
        raise BodyFitError(f"{where}.{extra[0]}", f"unknown key — allowed {sorted(POSE_FROM_KEYS)}", "UNKNOWN_FIELD")
    p = {**copy.deepcopy(POSE_FROM_DEFAULTS), **copy.deepcopy(raw)}
    if not isinstance(p.get("id"), str) or not _ID.match(p["id"]):
        raise BodyFitError(f"{where}.id", "must be a short id (letters, digits, _ -)")
    if p["note"] is not None and not isinstance(p["note"], str):
        raise BodyFitError(f"{where}.note", "must be a string (the user's words — recorded only)")
    if not isinstance(p.get("asset"), str) or not p["asset"].startswith("/"):
        raise BodyFitError(f"{where}.asset", "must be the sample AnimSequence path (same skeleton as the target)", "MISSING_FIELD")
    names = [p.get("bones")] if isinstance(p.get("bones"), str) else p.get("bones")
    if not (isinstance(names, list) and names and all(isinstance(x, str) and x.strip() for x in names)):
        raise BodyFitError(f"{where}.bones", f"must be a preset {list(BUNDLE_PRESETS)}, a bone name or a list of them")
    if "legs" in names:
        raise BodyFitError(f"{where}.bones", "legs need the foot pins and a leg IK — Phase 8-4d (legs block)", "NOT_SUPPORTED")
    p["bones"] = list(dict.fromkeys(names))
    if p.get("mode") not in ("pose", "motion"):
        raise BodyFitError(f"{where}.mode", "must be pose (one sample instant onto the target window) | motion (sample window onto the target window)")
    for key in ("source", "target"):
        p[key] = _span_spec(f"{where}.{key}", p.get(key))
    if p["mode"] == "pose" and not _is_point(p["source"]):
        raise BodyFitError(f"{where}.source", "pose takes one sample instant — {event: point event, offset_s?} | {time}")
    if p["mode"] == "motion" and (_is_point(p["source"]) or _is_point(p["target"])):
        raise BodyFitError(f"{where}.{'source' if _is_point(p['source']) else 'target'}",
                           "motion maps a sample window onto a target window — {window: [a, b]} | {event: swing | both_planted}")
    for key, lo, hi in (("hold_s", 0.0, 10.0), ("ease_s", 0.0, 2.0), ("weight", 0.0, 1.0)):
        if not _num(p[key], lo, hi):
            raise BodyFitError(f"{where}.{key}", f"must be a number in [{lo:g}, {hi:g}]")
        p[key] = float(p[key])
    if p["space"] != "local":
        raise BodyFitError(f"{where}.space", "only local (parent-space rotations) is supported", "NOT_SUPPORTED")
    return p


def _span_spec(where: str, raw) -> dict:
    """pose_from source · target — {event, offset_s?, index?} | {time} | {window: [a, b]}(끝 = 초 · 점 사건 이름 · start · end)."""
    if not isinstance(raw, dict) or len({"event", "time", "window"} & set(raw)) != 1:
        raise BodyFitError(where, "must be {event, offset_s?, index?} | {time} | {window: [a, b]}", "MISSING_FIELD" if raw is None else "BAD_FIELD")
    extra = sorted(set(raw) - {"event", "offset_s", "index", "time", "window"})
    if extra:
        raise BodyFitError(f"{where}.{extra[0]}", "unknown key", "UNKNOWN_FIELD")
    if "event" in raw:
        if raw["event"] not in timing.POINT_EVENTS + timing.WINDOW_EVENTS:
            raise BodyFitError(f"{where}.event", f"must be one of {list(timing.POINT_EVENTS + timing.WINDOW_EVENTS)}")
        if not _num(raw.get("offset_s", 0.0), -60.0, 60.0):
            raise BodyFitError(f"{where}.offset_s", "must be a number (seconds)")
        if not (isinstance(raw.get("index", 0), int) and not isinstance(raw.get("index", 0), bool) and raw.get("index", 0) >= 0):
            raise BodyFitError(f"{where}.index", "must be an integer ≥ 0 (n-th window of a window event)")
    elif "time" in raw:
        if not _num(raw["time"], 0.0, 600.0):
            raise BodyFitError(f"{where}.time", "must be a time in seconds ≥ 0")
    else:
        w = raw["window"]
        ok = isinstance(w, list) and len(w) == 2 and all(_num(v, 0.0, 600.0) or v in timing.POINT_EVENTS + ("start", "end") for v in w)
        if not ok or (all(_num(v, 0.0, 600.0) for v in w) and w[0] > w[1]):
            raise BodyFitError(f"{where}.window", "must be [from, to] — seconds, point event names or start | end (from ≤ to)")
    return copy.deepcopy(raw)


def _is_point(spec: dict) -> bool:
    return "time" in spec or ("event" in spec and spec["event"] in timing.POINT_EVENTS)


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


def _smootherstep(x: float) -> float:
    """지시 목표 완급 — 양끝 가속도 0(C2): smoothstep 은 완급 끝에서 가속이 갑자기 0 이 되어 블록 끝 변화가 컸다(오프라인 T1 2.82 → 1.57 cm ·
    T2 0.85 → 0.47, T1 목표 오차 p95 1.05 → 0.90 cm)."""
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


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
SPLINE_PIN_FRAMES = 2         # 지시 목표 블록 앞뒤에 붙이는 0 고정 프레임 — 2차 차분 벌점이 세 프레임을 묶으므로 둘이면 블록 밖(증분 0)과 위치 · 기울기가 이어진다
SPLINE_PIN_WEIGHT = 1e6       # 그 고정 프레임의 자료 가중 — λ(폭 6 → 1296)보다 충분히 커 사실상 0 에 묶는다


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


def spline_block(series: list, active: list[bool], radius: int, pin_before: bool, pin_after: bool, quiet: float | None = None,
                 whole_loop: bool = False) -> list:
    """지시 목표 블록 안의 매끈화 — 블록 앞(pin_before) · 뒤(pin_after)에 SPLINE_PIN_FRAMES 프레임의 0 을 고정 가중으로 붙여 풀고 블록만 쓴다 →
    블록 밖(목표 없는 해 — 증분 0)과 위치 · 기울기가 이어지고 꼬리가 블록 밖으로 새지 않는다(구간 ± ease 밖 변화 0). 블록이 루프 원 전체면
    (whole_loop — 붙일 블록 밖이 없다) 순환 spline."""
    n = len(series)
    if radius <= 0 or n == 0:
        return [tuple(v) for v in series]
    if whole_loop:
        return spline(list(series) + [series[0]], list(active) + [active[0]], radius, True, quiet)[:n]
    a, b = (SPLINE_PIN_FRAMES if pin_before else 0), (SPLINE_PIN_FRAMES if pin_after else 0)
    if n + a + b < 3:
        return [tuple(v) for v in series]
    zero = (0.0, 0.0, 0.0)
    padded = [zero] * a + [tuple(v) for v in series] + [zero] * b
    return _spline_line(padded, [False] * a + list(active) + [False] * b, radius, quiet, [True] * a + [False] * n + [True] * b)[a:a + n]


def _spline_line(series: list, active: list[bool], radius: int, quiet: float | None, fixed: list[bool] | None = None) -> list:
    """spline 의 열린 열 풀이(포락선 포함). fixed — 그 프레임 자료 가중을 SPLINE_PIN_WEIGHT 로(spline_block 의 0 고정)."""
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
    if fixed is not None:
        weight = [SPLINE_PIN_WEIGHT if x else w for w, x in zip(weight, fixed)]
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
def _flag_weights(flags: list[bool], fps: float, blend_s: float) -> tuple[list[float], list]:
    """프레임 깃발 → 가중(0 ~ 1) · 구간 — 짧은 빈틈(≤ GRIP_GAP_FRAMES) 잇기 · GRIP_MIN_FRAMES 이상 · 경계 smoothstep 블렌드."""
    n = len(flags)
    flags = list(flags)
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
    blend = max(1, int(round(blend_s * fps)))
    w = [0.0] * n
    for a, b in runs:
        for f in range(a, b + 1):
            w[f] = 1.0
        for k in range(1, blend + 1):
            s = _smoothstep(1.0 - k / (blend + 1))
            if a - k >= 0:
                w[a - k] = max(w[a - k], s)
            if b + k < n:
                w[b + k] = max(w[b + k], s)
    return w, runs


def grip_weights(rig: Rig, cfg: dict, scale: float, weapon: WeaponRig | None = None) -> dict:
    """keep 가중(프레임별 0 ~ 1) — 손목 간격이 띠(motion_metrics.grip_band) 안인 구간(짧은 빈틈은 이어 보고 GRIP_MIN_FRAMES 이상) + 경계 smoothstep.
    window(초)가 있으면 그 안만. mode off → 전부 0.
    weapon 모드(8-4c — weapon 에 보조 손 grip): 무기 파지 구간 = 원래 보조 손바닥 점이 손잡이에서 WEAPON_NEAR_CM × scale 안인 프레임(window 안 — 양손
    간격 띠는 보지 않는다: 띠는 무기 기하가 없을 때 '같은 무기를 쥠'의 대리이고, 운영 낫처럼 손이 가까운 파지는 띠 밖이다) → weapon_weights(블렌드
    0.2초), keep_weights = 띠 가중 − 무기 가중(손이 먼 띠 프레임은 keep 그대로), weights = 둘의 큰 쪽(자유도 · 주 손 충실도)."""
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
    flags, inside = [], []
    for f in range(n):
        gap = _norm(_sub(model.poses[f][wl][1], model.poses[f][wr][1]))
        t = model.times[f]
        inside.append(cfg["window"] is None or cfg["window"][0] - 1e-6 <= t <= cfg["window"][1] + 1e-6)
        flags.append(inside[f] and lo <= gap <= hi)
    blend_s = cfg.get("blend_s")
    w, runs = _flag_weights(flags, fps, GRIP_BLEND_S if blend_s is None else blend_s)
    out["weights"] = w
    out["frames"] = [f for f in range(n) if w[f] >= 1.0]
    out["runs_s"] = [[round(model.times[a], 4), round(model.times[b], 4)] for a, b in runs]
    if cfg["mode"] == "weapon" and weapon is not None and weapon.active:
        near_cm = WEAPON_NEAR_CM * scale
        dist = [weapon.grip_state(f, model.poses[f])["dist"] for f in range(n)]
        ww, wruns = _flag_weights([inside[f] and dist[f] <= near_cm for f in range(n)], fps, GRIP_BLEND_WEAPON_S if blend_s is None else blend_s)
        out.update(keep_weights=[max(0.0, a - b) for a, b in zip(w, ww)], weapon_weights=ww, weights=[max(a, b) for a, b in zip(w, ww)],
                   weapon_frames=[f for f in range(n) if ww[f] >= 1.0], weapon_runs_s=[[round(model.times[a], 4), round(model.times[b], 4)] for a, b in wruns],
                   near_cm=round(near_cm, 2), band_far_frames=sum(1 for f in range(n) if w[f] >= 1.0 and ww[f] <= 0.0),
                   dist_cm={"p50": round(bm.percentile(dist, 50.0), 2), "p5": round(bm.percentile(dist, 5.0), 2)})
    return out


def grip_mode(cfg: dict, weapon: dict | None) -> str:
    """요청 fix.body.grip.mode + 요청 weapon(weapon.normalize) → 풀이가 쓰는 모드. **무기 파지는 옵트인**(사용자 결정 2026-10-29): auto 는 무기가
    있어도 keep(보조 손 grip 이 있으면 손잡이 거리 · 두 손 선 각도만 기록 — 한계 GRIP_NOT_APPLICABLE), 무기가 없으면 auto(지금처럼 띠 안 keep).
    근거: 낫을 운영 부착(오른손 소켓 · offset)으로 붙이면 생성 낫 애니의 왼손은 자루에서 p50 30 ~ 43 cm(두 손 선 ∠ 자루 ≈ 60°), 운영 낫 왼손은 자루를
    쥐지 않고 빠르게 지나가 붙이면 동작이 망가졌다(Attack2 오프라인 거리 p95 13.8 → 7.0 cm · zigzag 8.2 → 19). weapon 은 요청이 줄 때만 —
    보조 손 grip 이 없거나 런타임 IK 면 BodyFitError(WEAPON_GRIP_UNKNOWN)."""
    mode = cfg["mode"]
    g = next((x for x in (weapon or {}).get("grips") or [] if x["hand"] != (weapon or {}).get("lead_hand")), None)
    if mode == "weapon" and (g is None or g["runtime_ik"]):
        raise BodyFitError("fix.body.grip.mode", "weapon needs request weapon.grips with the other hand's segment | socket | sockets (not runtime_ik)",
                           "WEAPON_GRIP_UNKNOWN")
    if mode == "auto" and g is not None:
        return "keep"
    return mode


# ---- 무기 (8-4c) ----
class WeaponRig:
    """요청 weapon 을 풀어 둔 값(weapon.resolve) → 몸 모델 위의 강체 무기: 부착 본(주 손목 또는 그 자손)에 붙은 무기 메시 공간 → 본 공간 변환 ·
    손잡이 선분 · 보조 손 회전 목표(본 공간 — 요청 회전이 없으면 프레임마다 원래 상대 회전) · 손바닥 점(보조 손목 로컬, 프레임별 — 손가락 로컬은
    풀이가 바꾸지 않는다) · 쥠 축(기록) · 손목 굽힘 상한 · 무기 끝 · 기록 점. grip 은 보조 손 grip 이 있으면(런타임 IK 아님) 늘 풀어 두고, 제약은
    weapon 모드(active)일 때만 — 그 밖은 손잡이 거리 · 두 손 선 기록 · 무기 끝 · 무기-몸 기록만."""

    def __init__(self, rig: Rig, resolved: dict, *, mode: str, wrist_bend_max_deg: float | None = None):
        model = rig.model
        self.resolved = resolved
        self.bone = model.index.get(resolved["bone"])
        if self.bone is None:
            raise BodyFitError("weapon.attach", f"the attach bone {resolved['bone']} is not in the body model", "WEAPON_ATTACH_UNKNOWN")
        lead = resolved["lead"]
        if rig.arms[lead]["wrist"] not in rig.anc_set[self.bone]:
            raise BodyFitError("weapon.attach", f"the attach bone {resolved['bone']} is not the {lead} wrist or below it", "WEAPON_ATTACH_UNKNOWN")
        self.lead = lead
        q, t, s = resolved["local"]
        self.local = (tuple(q), tuple(t), tuple(s))
        self.tip_local = bm.transform_point(self.local, resolved["tip"]) if resolved.get("tip") else None
        self.points = [(bm.transform_point(self.local, p["p"]), float(p["r"]), p["part"]) for p in resolved.get("points") or []]
        self.grip = None
        g = resolved.get("grip")
        if g is not None and not g["runtime_ik"] and resolved.get("hand"):
            self.grip = self._grip(rig, g, resolved.get("hand") or {}, wrist_bend_max_deg)
        # 파지 제약은 weapon 모드만(옵트인) — 그 밖은 손잡이 거리 · 두 손 선을 기록만
        self.active = mode == "weapon" and self.grip is not None

    def _grip(self, rig: Rig, g: dict, hand: dict, bend_max: float | None) -> dict:
        model = rig.model
        side = g["hand"]
        arm = rig.arms[side]
        wrist, elbow = arm["wrist"], arm["elbow"]
        middle = model.index.get(hand.get("middle") or "")
        if middle is None or wrist not in rig.anc_set[middle]:
            raise BodyFitError(f"weapon.grips.{side}", f"the middle finger root {hand.get('middle')} is not below the {side} wrist in the body model",
                               "WEAPON_GRIP_UNKNOWN")
        a, b = tuple(g["from"]), tuple(g["to"])
        d = _sub(b, a)
        dir_w = _scale(d, 1.0 / _norm(d)) if _norm(d) > 1e-6 else None
        rot_w = tuple(g["rotation"]) if g.get("rotation") else None
        # 손바닥 점(손목 로컬) — 프레임별 손목 · 가운데 손가락 뿌리 중점. 회전 목표 — 요청 회전이 없으면 프레임마다 원래 상대 회전(부착 본 기준 —
        # 사용자 결정 '가': 운영 낫 왼손은 자루를 감아 쥐지 않아(쥠 축 ∠ 자루 p50 52° · 무기 공간 회전 퍼짐 p50 51°) 한 회전으로 맞출 근거가 없다)
        # 원래 손바닥 점(부착 본 공간, 프레임별) — 블렌드 프레임 목표의 출발점(무기 강체로 따라간다 — grip_state)
        palm, rot_f, palm_bone = [], [], []
        for f in range(rig.frames):
            pose = model.poses[f]
            mid = _scale(_add(pose[wrist][1], pose[middle][1]), 0.5)
            palm.append(bm.qrot(bm.qconj(pose[wrist][0]), _sub(mid, pose[wrist][1])))
            rot_f.append(bm.qnormalize(bm.qmul(bm.qconj(pose[self.bone][0]), pose[wrist][0])))
            palm_bone.append(bm.qrot(bm.qconj(pose[self.bone][0]), _sub(mid, pose[self.bone][1])))
        # 쥠 축(보조 손 로컬 — 기록만) — 검지 → 새끼 뿌리(0 번 프레임, 앞 방향에 직교), 손가락 체인이 없으면 요청 회전에서 손잡이가 놓이는 손 로컬 방향
        axis = None
        idx_b, pin_b = model.index.get(hand.get("index") or ""), model.index.get(hand.get("pinky") or "")
        if dir_w is not None and idx_b is not None and pin_b is not None:
            pose = model.poses[0]
            fwd = _unit(_sub(pose[middle][1], pose[wrist][1]))
            lat = _sub(pose[idx_b][1], pose[pin_b][1])
            lat = _unit(_sub(lat, _scale(fwd, _dot(lat, fwd))))
            axis = bm.qrot(bm.qconj(pose[wrist][0]), lat)
        elif dir_w is not None and rot_w is not None:
            axis = bm.qrot(bm.qconj(rot_w), dir_w)
        bend0 = [self.bend(model.poses[f], elbow, wrist, middle) for f in range(rig.frames)]
        cap = max(max(bend0), math.radians(bend_max) if bend_max is not None else 0.0)
        # 손잡이 조각 — 선분에서 주 손 자리(주 손목의 선분 위 투영 ± WEAPON_LEAD_CLEAR_CM × scale, 0 번 프레임 — 무기는 주 손의 강체라 거의 일정)를 뺀다
        sa, sb = bm.transform_point(self.local, a), bm.transform_point(self.local, b)
        pieces = [(0.0, 1.0)]
        zone = None
        length = _norm(_sub(sb, sa))
        if length > 1e-6:
            lead_local = bm.qrot(bm.qconj(model.poses[0][self.bone][0]), _sub(model.poses[0][rig.arms[self.lead]["wrist"]][1], model.poses[0][self.bone][1]))
            u = _dot(_sub(lead_local, sa), _sub(sb, sa)) / (length * length)
            hw = WEAPON_LEAD_CLEAR_CM * model.scale / length
            cut = [(lo, hi) for lo, hi in ((0.0, min(1.0, u - hw)), (max(0.0, u + hw), 1.0)) if hi - lo > 1e-6]
            if cut and hw > 0.0 and cut != [(0.0, 1.0)]:
                pieces, zone = cut, (u - hw, u + hw, hw)
        # 프레임별 조각 · 주 손 자리 통과 비(8-4c 후속) — 원래 손바닥의 선분 위 투영으로 고른다. 원래 손이 주 손 자리를 건너가는 동안(운영 Attack2 f59 ~ f61
        # — 투영 11.5 → 19.1 cm, 자리 8.4 ~ 23.1) 가장 가까운 조각 끝은 한 프레임에 자리 폭(14.7 cm)을 건너뛰어 손이 반대 손을 꿰뚫거나 순간 이동했다
        # (오프라인 떨림 8.2 → 21.8) → 그 건너는 구간(자리 안 연속 프레임 중 조각이 바뀌는 것)만 통과 비 = smootherstep(1 − 자리 끝에서 든 깊이 / 반폭),
        # 목표 보간이 이 비만큼 원래 손바닥 쪽으로(grip_state). 한쪽에 머무는 자리 안 프레임(두 손이 가까운 파지)은 그대로 조각 끝으로 끈다
        l2 = length * length
        s0 = [_dot(_sub(palm_bone[f], sa), _sub(sb, sa)) / l2 if l2 > 1e-12 else 0.0 for f in range(rig.frames)]
        piece_f = [min(range(len(pieces)), key=lambda k: max(pieces[k][0] - x, 0.0, x - pieces[k][1])) for x in s0]
        pass_f = [1.0] * rig.frames
        inside = [zone is not None and zone[0] < x < zone[1] for x in s0]
        f = 0
        while f < rig.frames:
            if not inside[f]:
                f += 1
                continue
            a0 = f
            while f < rig.frames and inside[f]:
                f += 1
            if len({piece_f[k] for k in range(a0, f)}) > 1:
                for k in range(a0, f):
                    pass_f[k] = _smootherstep(1.0 - min(s0[k] - zone[0], zone[1] - s0[k]) / zone[2])
        # 통과 비를 시간으로 넓힌다(± GRIP_BLEND_WEAPON_S — 떨어진 만큼 smootherstep 으로 묽힌 최솟값, 8-4c 후속 2차): 위치만 본 비는 원래 손이 자리를
        # 2 ~ 3 프레임에 건너는 동안 목표를 손잡이 → 원래 손 → 손잡이로 바꿔 팔이 튀었다(운영 Attack2 옵트인 f58 ~ f64 — 손목 걸음 f63 6.5 · 팔꿈치 7.1 cm,
        # 원본 0.5 · 1.2). 넓히면 블렌드와 같은 폭으로 드나든다(오프라인 — 구간 파지 p95 1.28 → 0.88 · 최대 7.8 → 1.08 cm, 떨림 = 원본)
        b = max(1, int(round(GRIP_BLEND_WEAPON_S * model.fps)))
        dip = [1.0 - x for x in pass_f]
        pass_f = [1.0 - max([dip[k] * _smootherstep(1.0 - abs(f - k) / (b + 1)) for k in range(max(0, f - b), min(rig.frames, f + b + 1)) if dip[k] > 0.0] or [0.0])
                  for f in range(rig.frames)]
        return {"side": side, "wrist": wrist, "elbow": elbow, "middle": middle, "seg": (sa, sb), "pieces": pieces, "zone": zone, "piece_f": piece_f, "pass_f": pass_f,
                "seg_w": (a, b), "dir": bm.qrot(self.local[0], dir_w) if dir_w is not None else None,
                "rot": bm.qnormalize(bm.qmul(self.local[0], rot_w)) if rot_w is not None else None, "rot_f": rot_f, "axis": axis,
                "tol": math.radians(g["tol_deg"]), "palm": palm, "palm_bone": palm_bone, "bend0": bend0, "cap": cap, "form": g.get("form")}

    @staticmethod
    def bend(pose, elbow: int, wrist: int, middle: int) -> float:
        """손목 굽힘(rad) — 아래팔(팔꿈치 → 손목) vs 손(손목 → 가운데 손가락 뿌리), motion_metrics.wrist_bend 와 같은 정의."""
        u = _unit(_sub(pose[wrist][1], pose[elbow][1]))
        h = _unit(_sub(pose[middle][1], pose[wrist][1]))
        return math.atan2(_norm(_cross(h, u)), _dot(u, h))

    def frame(self, pose) -> tuple:
        """그 포즈의 무기 메시 변환(컴포넌트)."""
        return bm.compose(self.local, pose[self.bone])

    def grip_state(self, f: int, pose, blend: float = 1.0) -> dict:
        """그 포즈의 파지 상태 — 손바닥 점 · 손잡이 위 가장 가까운 점(미끄러짐 s 0 ~ 1) · 거리 · 목표 점 · 목표 오차 · 회전 오차(rad, 허용각 전 — 요청
        회전 또는 원래 상대 회전) · 쥠 축 각(기록) · 손목 굽힘 · 두 손 선(보조 손바닥 점 − 주 손목) ∠ 손잡이.
        blend(0 ~ 1 — 풀이는 smootherstep(무기 파지 가중)) × 주 손 자리 통과 비(pass_f) — 목표 점 = 원래 손바닥 점(부착 본 공간 — 무기 강체로 따라간다)
        → 손잡이 위 가장 가까운 점 보간, 요청 회전도 원래 상대 회전 → 요청 회전 slerp(8-4b 지시 목표 완급과 같은 방식). 1 이면 목표 = 가장 가까운 점.
        조각은 원래 손바닥 투영이 고른 것(piece_f) 안에서만 미끄러진다 — 주 손 자리를 건너뛰지 않는다."""
        g = self.grip
        W, O = pose[self.bone], pose[g["wrist"]]
        palm = bm.transform_point(O, g["palm"][f])
        a, b = bm.transform_point(W, g["seg"][0]), bm.transform_point(W, g["seg"][1])
        ab = _sub(b, a)
        l2 = _dot(ab, ab)
        s0 = _dot(_sub(palm, a), ab) / l2 if l2 > 1e-12 else 0.0
        lo, hi = g["pieces"][g["piece_f"][f]]
        s = min(hi, max(lo, s0))
        c = _add(a, _scale(ab, s))
        k = blend * g["pass_f"][f]
        target = c if k >= 1.0 else _add(_scale(bm.transform_point(W, g["palm_bone"][f]), 1.0 - k), _scale(c, k))
        out = {"palm": palm, "closest": c, "s": s, "along_cm": s * math.sqrt(l2), "dist": _norm(_sub(palm, c)), "target": target,
               "err": _norm(_sub(palm, target)), "blend": k, "axis": None, "hands_line": None, "bend": self.bend(pose, g["elbow"], g["wrist"], g["middle"]),
               "rel": self.target_rel(f, k)}
        out["rot"] = _norm(qlog(bm.qmul(O[0], bm.qconj(bm.qmul(W[0], out["rel"])))))
        if g["dir"] is not None:
            t_w = bm.qrot(W[0], g["dir"])
            if g["axis"] is not None:
                a_w = bm.qrot(O[0], g["axis"])
                out["axis"] = math.atan2(_norm(_cross(a_w, t_w)), abs(_dot(a_w, t_w)))
            v = _sub(palm, pose[self.bone][1])
            if _norm(v) > 1e-6:
                out["hands_line"] = math.atan2(_norm(_cross(v, t_w)), abs(_dot(v, t_w)))
        return out

    def target_rel(self, f: int, blend: float = 1.0):
        """보조 손 회전 목표(부착 본 기준) — 요청 회전(블렌드 프레임은 원래 상대 회전에서 slerp), 없으면 그 프레임의 원래 상대 회전."""
        g = self.grip
        if g["rot"] is None:
            return g["rot_f"][f]
        return g["rot"] if blend >= 1.0 else _slerp(g["rot_f"][f], g["rot"], blend)


# ---- 지시 목표 ----
def resolve_targets(rig: Rig, targets: list[dict], events: dict | None, joints: dict, weapon: WeaponRig | None = None) -> list[dict]:
    """targets[] → 프레임 구간 · 완급 · 본 · 자유도 · 프레임별 목표(위치 · 회전). 사건을 못 찾거나 클립 밖이면 skipped{reason}.
    weapon_tip(8-4c) = 무기 끝 점(요청 weapon.tip — 부착 본의 강체 점 point_local)."""
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
        ramp = _ease_ramp(n, fa, fb, ease)
        kind, side, bone, dof = _effector(rig, t, weapon)
        item.update(window_s=[round(a, 4), round(b, 4)], frames=[fa, fb], ease_frames=ease, ramp=ramp, kind=kind, side=side, bone=bone,
                    bone_name=model.bones[bone], dof=dof)
        if t["effector"] == "weapon_tip":
            item["point_local"] = weapon.tip_local
        pos = t["position"]
        item["away"] = None
        if pos and "away_from" in pos:
            center = _away_bone(rig, pos["away_from"])
            item["away"] = {"bone": center, "min_cm": float(pos["min_cm"])}
        _target_poses(rig, item, model.poses)
        out.append(item)
    return out


def _ease_ramp(n: int, fa: int, fb: int, ease: int) -> list:
    """구간 [fa, fb] = 1, 앞뒤 ease 프레임 smootherstep, 그 밖 0 — 지시 목표 · 샘플 전이 완급."""
    ramp = [0.0] * n
    for f in range(max(0, fa - ease), min(n, fb + ease + 1)):
        if fa <= f <= fb:
            ramp[f] = 1.0
        elif f < fa:
            ramp[f] = _smootherstep((f - (fa - ease - 1)) / (ease + 1))
        else:
            ramp[f] = _smootherstep(((fb + ease + 1) - f) / (ease + 1))
    return ramp


def _target_poses(rig: Rig, item: dict, poses: list) -> None:
    """완급 > 0 프레임마다 목표 위치 · 회전 — 오프셋 기준 = poses 의 본(resolve_targets = 원본, 풀이 = 목표 없는 해 — Solver._solve_targets).
    item["pos"] · item["rot"] 을 새 사전으로 바꾼다(호출 쪽 사전을 건드리지 않는다)."""
    t, bone, ramp = item["spec"], item["bone"], item["ramp"]
    pos, rot = t["position"], t["rotation"]
    out_pos, out_rot = {}, {}
    for f in range(len(ramp)):
        s = ramp[f]
        if s <= 0.0:
            continue
        frame = rig.body_frame(f)
        p0, q0 = _target_point(item, poses[f]), poses[f][bone][0]
        if pos and "offset_cm" in pos:
            off = _body_vec(frame, pos["offset_cm"]) if pos["space"] == "body" else tuple(pos["offset_cm"])
            out_pos[f] = _add(p0, _scale(off, s))
        elif pos and "absolute_cm" in pos:
            full = _add(frame[0], _body_vec(frame, pos["absolute_cm"])) if pos["space"] == "body" else tuple(pos["absolute_cm"])
            out_pos[f] = _add(p0, _scale(_sub(full, p0), s))
        if rot:
            if rot["space"] == "body":
                full = bm.qnormalize(bm.qmul(_body_rot(frame, rot["offset_deg"]), q0))
            else:
                full = bm.qnormalize(bm.qmul(q0, qexp(tuple(math.radians(v) for v in rot["offset_deg"]))))
            out_rot[f] = _slerp(q0, full, s)
    item["pos"], item["rot"] = out_pos, out_rot


def _target_point(t: dict, pose):
    """목표의 위치 점 — 본 원점, weapon_tip 이면 부착 본의 강체 점(무기 끝)."""
    local = t.get("point_local")
    return bm.transform_point(pose[t["bone"]], local) if local is not None else pose[t["bone"]][1]


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


def _effector(rig: Rig, t: dict, weapon: WeaponRig | None = None) -> tuple[str, str | None, int, list]:
    """→ (종류, 쪽, 본, 자유도 [(관절, 종류)]). 종류 arm · spine · neck · pelvis · foot. weapon_tip = 주 손 팔(무기는 주 손의 강체)."""
    model, name = rig.model, t["effector"]
    rot = t["rotation"] is not None
    if name == "weapon_tip":
        if weapon is None or weapon.tip_local is None:
            raise BodyFitError(f"targets.{t['id']}.effector", "weapon_tip needs the request weapon with tip {socket} | {point_cm}", "WEAPON_TIP_UNKNOWN")
        wrist = rig.arms[weapon.lead]["wrist"]
        return "arm", weapon.lead, weapon.bone, [(wrist, "wrist")] if rot else []
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


# ---- 샘플 전이 (8-4c c2) ----
def bundle_bones(names: list[str], info: dict) -> dict:
    """pose_from bones(프리셋 · 본 이름) → 본 이름 — 대상 메시 inspect_skeleton(details · template_match · suggest_finger_chains) 하나에서(이름 추측 없음):
    spine = 템플릿 Spine 체인 경로 · neck_head = Neck + Head · arm_l/r = {Side}Clavicle + {Side}Arm + 위팔 · 아래팔의 체인 밖 잎 자식(트위스트 — 자식이
    있는 가지는 옷 자락이라 뺀다: Vesper 위팔 아래 재킷 자락 2마디는 C++ 몸 모델 twist 규칙엔 들고 끝 마디는 모델 밖이다) · fingers_l/r = 손가락 체인
    제안 다섯 시작과 자손(메타카팔은 빼고 — 손바닥 점 · 손목 굽힘이 쓰는 가운데 손가락 뿌리 위치가 그대로) · upper_body = 앞 넷. 골반 · 그 조상 · 다리 체인 가지는 NOT_SUPPORTED(8-4d), 체인이 없으면 POSE_FROM_PRESET_UNKNOWN, 모르는 본은 UNKNOWN_BONE.
    → {bones[], presets{프리셋: [본]}}."""
    parents = {b.get("name"): b.get("parent") for b in info.get("bones") or []}
    children: dict = {}
    for b, p in parents.items():
        children.setdefault(p, []).append(b)
    tm = info.get("template_match") or {}
    chains = {c.get("name"): c for c in tm.get("chains") or []}

    def subtree(root):
        out, stack = [], [root]
        while stack:
            x = stack.pop()
            out.append(x)
            stack += sorted(children.get(x) or [], reverse=True)
        return out

    def path(name):
        c = chains.get(name) or {}
        out, x = [], c.get("end")
        while x is not None:
            out.append(x)
            if x == c.get("start"):
                return out[::-1]
            x = parents.get(x)
        raise BodyFitError("bones", f"the target mesh has no template chain {name} (inspect_skeleton template_match) — the preset cannot be resolved",
                           "POSE_FROM_PRESET_UNKNOWN")

    forbidden = set()
    for leg in ("LeftLeg", "RightLeg"):
        if (chains.get(leg) or {}).get("start") in parents:
            forbidden |= set(subtree(chains[leg]["start"]))
    x = tm.get("pelvis")
    while x is not None:
        forbidden.add(x)
        x = parents.get(x)

    def preset(name):
        if name == "spine":
            return path("Spine")
        if name == "neck_head":
            return path("Neck") + path("Head")
        if name in ("arm_l", "arm_r"):
            side = "Left" if name == "arm_l" else "Right"
            arm = path(f"{side}Arm")
            out = path(f"{side}Clavicle") + arm
            for b in arm[:-1]:
                out += [c for c in sorted(children.get(b) or []) if c not in arm and not children.get(c)]
            return out
        if name == "upper_body":
            return [b for part in ("spine", "neck_head", "arm_l", "arm_r") for b in preset(part)]
        roots = [r for r in hand_tree(info, name[-1]).values() if r and r in parents]
        if not roots:
            raise BodyFitError("bones", f"the target mesh has no {'Left' if name[-1] == 'l' else 'Right'} finger chains (inspect_skeleton suggest_finger_chains)",
                               "POSE_FROM_PRESET_UNKNOWN")
        return [b for r in roots for b in subtree(r)]

    out, presets = [], {}
    for name in names:
        if name in BUNDLE_PRESETS:
            bones = [b for b in preset(name) if b not in forbidden]
            presets[name] = bones
        elif name in parents:
            if name in forbidden:
                raise BodyFitError("bones", f"{name} is the pelvis, above it or on a leg — legs need the foot pins and a leg IK (Phase 8-4d)", "NOT_SUPPORTED")
            bones = [name]
        else:
            raise BodyFitError("bones", f"{name} is neither a preset {list(BUNDLE_PRESETS)} nor a bone of the target mesh", "UNKNOWN_BONE")
        out += [b for b in bones if b not in out]
    return {"bones": out, "presets": presets}


def _span_s(spec: dict, events: dict | None, length: float, hold: float = 0.0) -> tuple[float, float]:
    """source · target 시각(초) — 점(사건 · time, + hold) · 구간 사건 · window(끝 = 초 · 점 사건 · start · end). 사건 없음 → EVENT_NOT_FOUND."""
    if "window" not in spec:
        return _window_s({"at": spec, "hold_s": hold}, events)
    ends = []
    for v in spec["window"]:
        if isinstance(v, str):
            ev = 0.0 if v == "start" else length if v == "end" else (events or {}).get(v)
            if ev is None:
                raise BodyFitError("window", f"event {v} not found ({(events or {}).get('reason') or 'no swing'})", "EVENT_NOT_FOUND")
            ends.append(float(ev))
        else:
            ends.append(float(v))
    if ends[0] > ends[1]:
        raise BodyFitError("window", f"window [{ends[0]:.3f}, {ends[1]:.3f}] s runs backwards", "TARGET_OUT_OF_RANGE")
    return ends[0], ends[1]


def _map_time(anchors: list, t: float) -> float:
    """대상 초 → 샘플 초 — 앵커(대상 s, 샘플 s, 이름)를 잇는 구간별 선형(앞뒤는 끝 값 — ease 프레임은 구간 끝 자세)."""
    if t <= anchors[0][0] or len(anchors) == 1:
        return anchors[0][1]
    for (t0, s0, _), (t1, s1, _) in zip(anchors, anchors[1:]):
        if t <= t1:
            return s0 if t1 - t0 <= 1e-9 else s0 + (s1 - s0) * (t - t0) / (t1 - t0)
    return anchors[-1][1]


def pose_from_spans(p: dict, events: dict | None, length: float, fps: float, s_events: dict | None, s_length: float, s_fps: float) -> dict:
    """pose_from 한 항목의 시각 — target(대상 사건 · 초, 점이면 + hold_s) · source(샘플 사건 · 초) → {window_s, source_s, frames, ease_frames, anchors,
    alignment}. 사상 앵커 = 구간 시작(pose 는 이것 하나 — 샘플 한 시각) · motion 은 두 구간 안에 같이 든 점 사건(시간 순 단조인 것) · 구간 끝.
    정렬 차(프레임) = 앵커마다 max(대상 프레임 반올림, 그 프레임의 사상 시각 − 샘플 사건 시각 × 샘플 fps). 사건 없음 EVENT_NOT_FOUND · 클립 밖
    TARGET_OUT_OF_RANGE(target 은 클립과 겹치면 자르고, source 는 샘플 클립 안이어야 한다)."""
    ta, tb = _span_s(p["target"], events, length, p["hold_s"] if _is_point(p["target"]) else 0.0)
    sa, sb = _span_s(p["source"], s_events, s_length)
    if tb < -1e-6 or ta > length + 1e-6:
        raise BodyFitError("target", f"target window [{ta:.3f}, {tb:.3f}] s is outside the clip [0, {length:.3f}]", "TARGET_OUT_OF_RANGE")
    if sa < -1e-6 or sb > s_length + 1e-6:
        raise BodyFitError("source", f"source [{sa:.3f}, {sb:.3f}] s is outside the sample clip [0, {s_length:.3f}]", "TARGET_OUT_OF_RANGE")
    n = int(round(length * fps)) + 1
    label = lambda spec, k: spec.get("event") if "event" in spec else ("time" if "time" in spec else (spec["window"][k] if isinstance(spec["window"][k], str) else "window"))  # noqa: E731
    anchors = [(ta, sa, label(p["target"], 0))]
    if p["mode"] == "motion":
        inner = sorted((float(events[e]), float(s_events[e]), e) for e in timing.POINT_EVENTS
                       if (events or {}).get(e) is not None and (s_events or {}).get(e) is not None
                       and ta + 1e-6 < events[e] < tb - 1e-6 and sa + 1e-6 < s_events[e] < sb - 1e-6)
        for te, se, e in inner:
            if se > anchors[-1][1] + 1e-6:
                anchors.append((te, se, e))
        anchors.append((tb, sb, label(p["target"], 1)))
    fa, fb = max(0, int(round(ta * fps))), min(n - 1, int(round(tb * fps)))
    align = []
    for te, se, name in anchors:
        f = min(n - 1, max(0, int(round(te * fps))))
        err = max(abs(f - te * fps), abs(_map_time(anchors, f / fps) - se) * s_fps)
        align.append({"anchor": name, "target_s": round(te, 4), "source_s": round(se, 4), "target_frame": f, "error_frames": round(err, 3)})
    return {"window_s": [round(ta, 4), round(tb, 4)], "source_s": [round(sa, 4), round(sb, 4)], "frames": [fa, fb], "ease_frames": int(round(p["ease_s"] * fps)),
            "anchors": anchors, "alignment": align}


def _sample_local(sm: bm.BodyModel, t: float, pairs: list, cache: dict) -> dict:
    """샘플 모델의 시각 t 로컬 회전 — 이웃 두 모델 프레임 slerp. pairs = [(대상 본, 샘플 본)] → {대상 본: 쿼터니언}."""
    times = sm.times
    i = max(0, min(len(times) - 2, bisect.bisect_right(times, t) - 1)) if len(times) > 1 else 0
    u = 0.0 if len(times) < 2 or times[i + 1] - times[i] <= 1e-12 else min(1.0, max(0.0, (t - times[i]) / (times[i + 1] - times[i])))
    for k in (i, min(i + 1, len(times) - 1)):
        if k not in cache:
            cache[k] = sm.local_pose(k)
    a, b = cache[i], cache[min(i + 1, len(times) - 1)]
    return {tb: _slerp(a[sb][0], b[sb][0], u) for tb, sb in pairs}


def resolve_pose_from(rig: Rig, items: list[dict], events: dict | None, samples: dict) -> list[dict]:
    """pose_from[](항목마다 resolved_bones · resolved_presets = bundle_bones) + samples{asset: {model: BodyModel, events}} → 블록 풀이가 쓰는 값:
    구간 · 완급 · 본(대상 모델 번호) · 펼친 프레임 k(구간 ± ease, 루프면 클립 밖 번호도)마다 샘플 로컬 회전(시간 slerp — pose 는 한 시각, motion 은
    구간별 선형 사상, ease 프레임은 구간 끝 자세). 사건 없음 · 클립 밖이면 skipped{reason}, 모델에 없는 본은 missing(보고). 샘플 모델의 본 부모가
    대상과 다르면 BodyFitError(SAMPLE_SKELETON_MISMATCH)."""
    model = rig.model
    fps, n = model.fps, rig.frames
    out = []
    for p in items:
        item = {"id": p["id"], "note": p.get("note"), "asset": p["asset"], "mode": p["mode"], "weight": float(p["weight"]), "spec": p, "skipped": None,
                "bone_names": list(p.get("resolved_bones") or []), "presets": dict(p.get("resolved_presets") or {})}
        sample = samples.get(p["asset"])
        if sample is None:
            raise BodyFitError(f"pose_from.{p['id']}.asset", f"no sample model for {p['asset']}", "SAMPLE_NOT_FOUND")
        sm = sample["model"]
        s_len = (int(sm.raw.get("frames_total") or len(sm.frames)) - 1) / sm.fps
        try:
            spans = pose_from_spans(p, events, (n - 1) / fps, fps, sample.get("events"), s_len, sm.fps)
        except BodyFitError as err:
            item["skipped"] = {"reason": err.reason, "message": err.message}
            out.append(item)
            continue
        pairs, missing = [], []
        for name in item["bone_names"]:
            b, sb = model.index.get(name), sm.index.get(name)
            if b is None or sb is None:
                missing.append(name)
                continue
            pa = model.bones[model.parents[b]] if model.parents[b] >= 0 else None
            ps = sm.bones[sm.parents[sb]] if sm.parents[sb] >= 0 else None
            if pa != ps:
                raise BodyFitError(f"pose_from.{p['id']}.asset", f"bone {name}: parent {ps} in the sample vs {pa} in the target — not the same skeleton",
                                   "SAMPLE_SKELETON_MISMATCH")
            pairs.append((b, sb))
        fa, fb = spans["frames"]
        ease = spans["ease_frames"]
        cache: dict = {}
        local_k = {k: _sample_local(sm, _map_time(spans["anchors"], k / fps), pairs, cache) for k in range(fa - ease, fb + ease + 1)}
        fingers = {model.index[b] for pr, bs in item["presets"].items() if pr.startswith("fingers_") for b in bs if b in model.index}
        item.update(spans, bones=[b for b, _ in pairs], missing=missing, ramp=_ease_ramp(n, fa, fb, ease), local_k=local_k, finger_bones=fingers,
                    sample_fps=sm.fps, sample_length_s=round(s_len, 4))
        out.append(item)
    return out


# ---- 풀이 ----
class Solver:
    """한 풀이 — 프레임별 감쇠 GN · 관통 몫 매끈화 · 재검사 · 보조 팔 다듬기."""

    def __init__(self, model: bm.BodyModel, cfg: dict, *, grip: dict | None = None, targets: list[dict] | None = None, loop: bool = False,
                 weapon: WeaponRig | None = None, fingers: dict | None = None, pose_from: list[dict] | None = None):
        self.model = model
        self.fingers = fingers
        self.rig = Rig(model)
        # 무기(8-4c) — weapon 모드면 파지 = 손잡이 선분 · 무기 공간 회전(keep 대신), 아니면 무기 끝 목표 · 기록만
        self.weapon = weapon
        self.wgrip = weapon.grip if weapon is not None and weapon.active else None
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
        # 얕은 사본 — 풀이가 목표의 완급(루프 감아 돎) · 목표 자세(목표 없는 해 기준)를 새 값으로 바꾼다(호출 쪽 목록은 그대로)
        self.targets = [dict(t) for t in (targets or []) if not t.get("skipped")]
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
        # 샘플 전이(8-4c c2) — 묶음의 척추 · 목머리 본은 그 구간만 3축 자유도(상한 = 덮은 자세에서 ± 목표용 상한 / 마디 수), 팔은 이미 자유도, 손가락 ·
        # 트위스트 등은 자유도가 아니다(덮은 값 그대로). 얕은 사본 — 루프면 풀이가 완급 · 프레임별 샘플 로컬을 감아 돈 값으로 바꾼다
        self.pose_from = [dict(p) for p in (pose_from or []) if not p.get("skipped")]
        for p in self.pose_from:
            p["dof"] = [(b, "spine") for b in p["bones"] if b in rig.spine] + [(b, "neck") for b in p["bones"] if b in rig.neck]
            for kind in ("spine", "neck"):
                chain = [b for b, k in p["dof"] if k == kind]
                for b in chain:
                    self.kind.setdefault(b, kind)
                    self.cap_of.setdefault(b, math.radians(j[f"{kind}_deg_for_targets"]) / len(chain))
            p["local"] = {f: p["local_k"][f] for f in range(rig.frames) if f in p["local_k"]}
        self.ref_rot: dict = {}    # {프레임: {본: 덮은 자세의 델타}} — 관절 상한을 여기서 잰다(블록 풀이 동안만, 없으면 원래 규칙)
        self.ref_bend: dict = {}   # {프레임: {쪽: 덮은 자세의 팔꿈치 굽힘}}
        self.pf_req: dict = {}     # {프레임: {본: 덮은 자세의 로컬 회전}} — pose_from_report 기준
        self.pf_at: dict = {}      # {프레임: 완급 > 0 인 묶음 본} — 관절 충실도 × weights.pose_from
        self.pf_state: dict = {}   # {프레임: 덮은 자세 상태} — 막은 것 판정(덮은 자세가 이미 관통이면 clearance)
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
        # keep · 무기 파지 가중 — weapon 모드면 grip_weights 가 나눠 준다(keep = 띠 − 무기 파지), 아니면 keep = 파지 가중 그대로 · 무기 0
        self.keep_w = g.get("keep_weights") or g["weights"]
        self.weapon_w = g.get("weapon_weights") if self.wgrip is not None and g.get("weapon_weights") else [0.0] * rig.frames
        self.weapon_s = [_smootherstep(w) for w in self.weapon_w]   # 무기 파지 목표 보간(grip_state blend)
        self.bend_rig, self.bend_cap = self._bend_caps()
        self.keep_rel = {}
        for f in range(rig.frames):
            if self.keep_w[f] > 0.0:
                self.keep_rel[f] = self._keep_of(model.poses[f])
        self.keep_orig = self.keep_rel   # keep_report 는 늘 원본 관계로 잰다(목표 블록은 keep_rel 을 목표 없는 해의 관계로 바꾼다)
        # 목표 블록의 기준(_solve_targets) — 관통 바닥{(f, 점, 지도): 목표 없는 해의 깊이} · away 거리의 기준 자세. 목표 없는 풀이는 비어 있음 · 원본
        self.floor: dict = {}
        self.live_lateral = False   # probe 의 각도 0 방향을 그 자세의 어깨로(C++ 와 같은 칸 나눔 — _finish_wrist 동안만)
        self.ref_poses = model.poses
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

    def _bend_rig(self, side: str, weapon: bool) -> dict | None:
        """그 손의 손목 굽힘 상한(프레임별 rad | None — 파지 가중 > 0 프레임(손목을 여는 프레임 — _joints)만). 손가락 뿌리 = 대상 메시 손가락 체인 제안
        {Side}Middle 시작(fingers — 이름 추측 없음, 보조 손은 없으면 무기 grip 의 것, 없으면 None — 끈다). keep = 프레임별 원래 굽힘 + BEND_KEEP_TOL_DEG,
        weapon(보조 손 · 무기 파지 프레임) = WeaponRig cap(max(원래 최대, wrist_bend_max_deg)) — 블렌드 프레임은 smootherstep(무기 가중)으로 잇는다."""
        rig, model = self.rig, self.model
        n = rig.frames
        arm = rig.arms[side]
        name = (self.fingers or {}).get(side)
        if not name and weapon:
            name = model.bones[self.wgrip["middle"]]
        middle = model.index.get(name or "")
        if middle is None or middle == arm["wrist"] or arm["wrist"] not in rig.anc_set[middle]:
            return None
        br = {"side": side, "wrist": arm["wrist"], "elbow": arm["elbow"], "middle": middle, "middle_name": model.bones[middle],
              "bend0": [WeaponRig.bend(model.poses[f], arm["elbow"], arm["wrist"], middle) for f in range(n)]}
        tol = math.radians(BEND_KEEP_TOL_DEG)
        caps = []
        for f in range(n):
            if self.grip["weights"][f] <= 0.0:
                caps.append(None)
                continue
            cap = br["bend0"][f] + tol
            if weapon and self.weapon_w[f] > 0.0:
                cap = (1.0 - self.weapon_s[f]) * cap + self.weapon_s[f] * self.wgrip["cap"]
            caps.append(cap)
        br["caps"] = caps
        return br

    def _bend_caps(self) -> tuple[dict | None, list]:
        """보조 손목 굽힘 상한 — self.bends(경첩을 거는 손 리그 목록), 반환 = (보조 손 리그 | None, 프레임별 상한). 주 손목은 기록만(bend_report) —
        두 손목에 걸어 보니(오프라인 낫 s27) keep 이 9.1 → 20.7 cm 로 풀리고 머리 관통이 늘었다."""
        off = self.wgrip["side"] if self.wgrip is not None else self.off
        br = self._bend_rig(off, self.wgrip is not None)
        self.bends = [br] if br is not None else []
        return br, (br["caps"] if br else [None] * self.rig.frames)

    def _keep_of(self, pose) -> tuple:
        """보조 손바닥 점 · 회전의 주 손목 기준 상대 변환(keep 기준)."""
        lw, ow = pose[self.rig.arms[self.lead]["wrist"]], pose[self.rig.arms[self.off]["wrist"]]
        palm = bm.transform_point(ow, self.palm_local)
        return bm.qrot(bm.qconj(lw[0]), _sub(palm, lw[1])), bm.qnormalize(bm.qmul(bm.qconj(lw[0]), ow[0]))

    def _limit(self, f: int, i: int, name: str, upper: bool) -> float:
        """팔 점 i 가 지도 name 에서 허용되는 깊이 — 위팔 = 원래 깊이(안 깊어짐) · 손끼리 = 맞닿음 · 몸 = body_allow, 목표 블록이면 목표 없는 해의
        깊이(floor)보다 얕게 요구하지 않는다(목표는 관통을 base 보다 깊게 만들지 못하고, base 에 남은 한계는 다시 풀지 않는다)."""
        if upper:
            lim = max(self.orig_upper_depth.get((f, i, name), self.body_allow[name]), self.body_allow[name])
        elif name in HAND_MAPS:
            lim = self.hand_contact   # 손끼리는 맞닿음(≤ contact_cm)까지 정상 — 파지한 두 손을 떼지 않는다
        else:
            lim = self.body_allow[name]
        if self.floor:
            lim = max(lim, self.floor.get((f, i, name), lim))
        return lim

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
        for t in self.targets + self.pose_from:
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
        hit = mp.depth(f, q, min_t, self._lateral_x(mp, f, pose, back) if self.live_lateral else None)
        if hit is None:
            return None
        ax = mp.axes[f]
        rel = _sub(q, ax["a"])
        radial = _sub(rel, _scale(ax["dir"], _dot(rel, ax["dir"])))
        n = _unit(radial, ax["x"])
        if back is not None:
            n = bm.qrot(back, n)
        return hit[0], n, anchor, hit[1]

    def _lateral_x(self, mp, f: int, pose, back):
        """C++ 와 같은 지도 각도 0 방향 — 그 자세의 어깨(upperarm_l − upperarm_r, 기준 본이 움직였으면 원래 자리로 되돌린 방향)를 축에 수직으로. 원래
        자세면 저장된 축 x 와 같다(실제 모델 8 지도 차 ≤ 1e-6). 모델 지도는 원래 축을 기준 본 강체로 따라가므로 쇄골을 옮긴 프레임은 C++ 칸 나눔과
        1 ~ 2° 어긋난다 — 칸 경계 점은 반경이 크게 다른 칸에 든다(s25 f55 검지 — 모델 −2.13 · C++ +2.81 cm). 반경은 모델 지도의 같은 번호 칸."""
        lat = _sub(pose[self.rig.arms["l"]["upper"]][1], pose[self.rig.arms["r"]["upper"]][1])
        if back is not None:
            lat = bm.qrot(bm.qconj(back), lat)
        d = mp.axes[f]["dir"]
        lat = _sub(lat, _scale(d, _dot(lat, d)))
        return _unit(lat) if _norm(lat) > 1e-9 else None

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
        """cost · 정규 방정식(H, g) · 진단. families ⊂ FAMILIES ∪ {bend}."""
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
                    r = d - self._limit(f, i, name, upper)
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
        wkk, ww = self.keep_w[f], self.weapon_w[f]   # weapon 모드면 keep = 띠 − 무기 파지(손이 먼 띠 프레임), 아니면 wkk == wk
        if "keep" in families and wkk > 0.0 and f in self.keep_rel:
            lw_b, ow_b = rig.arms[self.lead]["wrist"], rig.arms[self.off]["wrist"]
            rel_p, rel_q = self.keep_rel[f]
            lw, ow = pose[lw_b], pose[ow_b]
            palm = bm.transform_point(ow, self.palm_local)
            tgt = _add(bm.qrot(lw[0], rel_p), lw[1])
            e_rot = _scale(qlog(bm.qmul(ow[0], bm.qconj(bm.qmul(lw[0], rel_q)))), ROT_CM)
            w2 = (self.w["grip"] * TIER["grip"] * wkk) ** 2
            info["keep"] = {"pos_cm": _norm(_sub(palm, tgt)), "deg": math.degrees(_norm(e_rot) / ROT_CM)}
            if jac:
                ja, jb = self._jac_rigid(ow_b, palm, dofs, pose), self._jac_rigid(lw_b, tgt, dofs, pose)
                ra, rb = self._jac_rot(ow_b, dofs), self._jac_rot(lw_b, dofs)
                rows3(_sub(palm, tgt), [_sub(x, y) for x, y in zip(ja, jb)], w2)
                rows3(e_rot, [_scale(_sub(x, y), ROT_CM) for x, y in zip(ra, rb)], w2)
            else:
                rows3(_sub(palm, tgt), None, w2)
                rows3(e_rot, None, w2)
        # 무기 파지(weapon 모드 — 8-4c, 무기 파지 가중 > 0 — 원래 손이 손잡이 근처인 구간) — 보조 손바닥 점 → 목표 점(원래 손바닥 → 손잡이 선분 위 가장
        # 가까운 점을 smootherstep(가중) 보간 — 미끄러짐, 그 점의 움직임은 무기 강체로) · 보조 손 회전(요청 회전 또는 원래 상대 회전 — 허용각 밖만).
        # 잔차는 가득 가중 — 가중만 줄이던 처음 판은 블렌드 끝(가중 0.05)에도 손잡이 잔차가 충실도를 이겨 원래 손이 떠난 뒤까지 손을 손잡이에 붙였다
        # (운영 Attack2 옵트인 f68 — 원래 손바닥 ↔ 자루 18.7 cm 에 결과 5.9, 손목 간격 35.9 → 5.4, 손끼리 −27 → +5.8 cm — 사용자 Persona '손 겹침')
        wg = self.wgrip
        if "weapon" in families and wg is not None and ww > 0.0:
            wb, ob = self.weapon.bone, wg["wrist"]
            st = self.weapon.grip_state(f, pose, self.weapon_s[f])
            w2 = (self.w["grip"] * TIER["grip"]) ** 2
            info["weapon"] = {"pos_cm": st["err"], "rot_deg": 0.0, "bend_deg": 0.0}
            e = _sub(st["palm"], st["target"])
            rows3(e, [_sub(x, y) for x, y in zip(self._jac_rigid(ob, st["palm"], dofs, pose), self._jac_rigid(wb, st["target"], dofs, pose))] if jac else None, w2)
            jr = [_sub(x, y) for x, y in zip(self._jac_rot(ob, dofs), self._jac_rot(wb, dofs))] if jac else None
            if st["rot"] > wg["tol"]:
                ev = qlog(bm.qmul(pose[ob][0], bm.qconj(bm.qmul(pose[wb][0], st["rel"]))))
                u = _scale(ev, 1.0 / st["rot"])
                info["weapon"]["rot_deg"] = math.degrees(st["rot"] - wg["tol"])
                row((st["rot"] - wg["tol"]) * ROT_CM, [ROT_CM * _dot(u, x) for x in jr] if jac else None, w2)
            # 보조 손목 굽힘 ≤ 무기 상한 max(원래 최대, wrist_bend_max_deg)(관통과 같은 층 — c1, 본 풀이에도 둔다): 요청 회전을 손목이 다 떠안으면
            # 마무리(_snap_weapon) 한 번으로는 팔로 못 옮긴다(합성 상한 0° — 손목 1.9°, 쥠 축 p95 16.2°). 원래 + 2° 상한(bend)은 다듬기에만
            if st["bend"] > wg["cap"]:
                u = _unit(_sub(pose[ob][1], pose[wg["elbow"]][1]))
                h = _unit(_sub(pose[wg["middle"]][1], pose[ob][1]))
                m = _unit(_cross(h, u))
                info["weapon"]["bend_deg"] = math.degrees(st["bend"] - wg["cap"])
                jb = [_sub(x, y) for x, y in zip(self._jac_rot(ob, dofs), self._jac_rot(wg["elbow"], dofs))] if jac else None
                row((st["bend"] - wg["cap"]) * ROT_CM, [-ROT_CM * _dot(m, x) for x in jb] if jac else None, (self.w["clearance"] * TIER["clearance"]) ** 2)
        # 보조 손목 굽힘 상한(파지 프레임 — 손목을 여는 프레임, 관통과 같은 층 hinge — 꺾임을 만들지 않는다, 다듬기 단계만): keep = 프레임별 원래 굽힘 +
        # BEND_KEEP_TOL_DEG(원래보다 더 굽히지 않음), 무기 파지 = max(원래 최대, wrist_bend_max_deg) — 블렌드 프레임은 둘을 smootherstep(가중)으로 잇는다(bend_caps)
        for br in self.bends if "bend" in families else ():
            cap = br["caps"][f]
            if cap is None:
                continue
            ob, eb, mb = br["wrist"], br["elbow"], br["middle"]
            bend = WeaponRig.bend(pose, eb, ob, mb)
            info["bend_deg"] = max(info.get("bend_deg", 0.0), math.degrees(bend - cap))
            if bend > cap:
                u = _unit(_sub(pose[ob][1], pose[eb][1]))
                h = _unit(_sub(pose[mb][1], pose[ob][1]))
                m = _unit(_cross(h, u))
                jb = [_sub(x, y) for x, y in zip(self._jac_rot(ob, dofs), self._jac_rot(eb, dofs))] if jac else None
                row((bend - cap) * ROT_CM, [-ROT_CM * _dot(m, x) for x in jb] if jac else None, (self.w["clearance"] * TIER["clearance"]) ** 2)
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
                # weapon 모드면 주 손 방향 = 무기 방향(무기는 주 손의 강체 — 돌면 휘두름 궤적이 바뀐다) → 파지와 같은 층 · 같은 가중(grip). lead_hand 가중
                # 으로 층만 올리면(√30) 보조 손 회전 잔차(√100)를 무기가 반쯤 떠안아 합성에서 무기가 5.2° 돌았다
                w2r = max(w2, (self.w["grip"] * TIER["grip"] * ww) ** 2) if self.wgrip is not None else w2
                rows3(e_rot, [_scale(_sub(x, y), ROT_CM) for x, y in zip(self._jac_rot(wb, dofs), self._jac_rot(base, dofs))] if jac else None, w2r)
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
                pt = _target_point(t, pose)
                err = {}
                if f in t["pos"]:
                    e = _sub(pt, t["pos"][f])
                    err["pos_cm"] = _norm(e)
                    rows3(e, self._jac_rigid(b, pt, dofs, pose) if jac else None, w2)
                if f in t["rot"]:
                    e = _scale(qlog(bm.qmul(pb[0], bm.qconj(t["rot"][f]))), ROT_CM)
                    err["deg"] = math.degrees(_norm(e) / ROT_CM)
                    rows3(e, [_scale(x, ROT_CM) for x in self._jac_rot(b, dofs)] if jac else None, w2)
                if t["away"]:
                    c = pose[t["away"]["bone"]][1]
                    d0 = _norm(_sub(_target_point(t, self.ref_poses[f]), self.ref_poses[f][t["away"]["bone"]][1]))
                    want = d0 + s * max(0.0, t["away"]["min_cm"] - d0)
                    v = _sub(pt, c)
                    dist = _norm(v)
                    err["away_cm"] = max(0.0, want - dist)
                    if want - dist > 0.0:
                        u = _unit(v)
                        if jac:
                            ja, jb = self._jac_rigid(b, pt, dofs, pose), self._jac_rigid(t["away"]["bone"], c, dofs, pose)
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
            # 샘플 전이 묶음 본은 기준(덮은 자세) 쪽 충실도를 weights.pose_from 으로 — 하드가 몸을 옮겨야 하면 묶음 밖 관절을 먼저 쓴다
            pf = self.pf_at.get(f, ())
            wp = (self.w.get("pose_from", 3.0) * TIER["soft"]) ** 2
            for k, (b, kind, a, _) in enumerate(dofs):
                cost_j = JOINT_COST.get(self.kind.get(b, "upper"), 1.0)
                bucket = "rot" if kind == "r" else "trans"
                scale_k = (FID_CM if kind == "r" else 1.0) * cost_j
                for ref, w2 in ((anchor, wp if b in pf else wf), (prev, wf * TEMPORAL ** 2)):
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
    def _clamp(self, f: int, state: dict, count: bool = True) -> None:
        """관절 상한 · 팔꿈치 굽힘 범위로 자른다 — count 면 잘린 관절을 stats.clamped 에 센다(JOINT_LIMIT 판정)."""
        if not count:
            saved = self.stats["clamped"]
            self.stats["clamped"] = {}
            self._clamp(f, state)
            self.stats["clamped"] = saved
            return
        ref = self.ref_rot.get(f) or {}
        for b, v in list(state["rot"].items()):
            kind = self.kind.get(b)
            r = ref.get(b)
            if kind == "elbow":
                side = next(s for s, a in self.rig.arms.items() if a["elbow"] == b)
                axis = self.rig.hinge[side][f]
                h = _dot(v, axis)
                off = _sub(v, _scale(axis, h))
                if r is not None:
                    # 샘플 전이 — 상한 · 굽힘 범위를 덮은 자세(그 굽힘 · 경첩 성분)에서 잰다
                    h0 = _dot(r, axis)
                    bend = self.ref_bend[f][side]
                    lo = max(-self.cap_of[b], min(0.0, BEND_MIN - bend))
                    hi = min(self.cap_of[b], max(0.0, BEND_MAX - bend))
                    dc = min(max(h - h0, lo), hi)
                    if abs(dc - (h - h0)) > 1e-4:
                        self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1
                    state["rot"][b] = _add(off, _scale(axis, h0 + dc))
                    continue
                # 원래 굽힘이 한계 밖이어도 0(원래 그대로)은 늘 허용
                lo = max(-self.cap_of[b], min(0.0, BEND_MIN - self.rig.bend0[side][f]))
                hi = min(self.cap_of[b], max(0.0, BEND_MAX - self.rig.bend0[side][f]))
                hc = min(max(h, lo), hi)
                if abs(hc - h) > 1e-4:
                    self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1
                state["rot"][b] = _add(off, _scale(axis, hc))
                continue
            cap = self.cap_of.get(b)
            if r is not None and cap is not None:
                d = _sub(v, r)
                if _norm(d) > cap:
                    state["rot"][b] = _add(r, _scale(d, cap / _norm(d)))
                    if _norm(d) > cap + 1e-4:
                        self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + 1
                continue
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
        r = (self.ref_rot.get(f) or {}).get(b)
        if self.kind.get(b) == "elbow":
            side = next(s for s, a in self.rig.arms.items() if a["elbow"] == b)
            h = _dot(v, self.rig.hinge[side][f])
            if r is not None:
                h -= _dot(r, self.rig.hinge[side][f])
                bend = self.ref_bend[f][side] + h
            else:
                bend = self.rig.bend0[side][f] + h
            return bend <= BEND_MIN + 1e-3 or bend >= BEND_MAX - 1e-3 or abs(h) >= self.cap_of[b] - 1e-3
        cap = self.cap_of.get(b)
        return cap is not None and _norm(v if r is None else _sub(v, r)) >= cap - 1e-4

    def _toward_cap(self, f: int, b: int, kind: str, v, step):
        """v + step — 넘으면 그 관절 걸음만 상한 위까지 줄인다(나머지 관절 걸음은 그대로 — 뒤 클램프가 GN 방향을 비틀지 않게)."""
        if kind == "t":
            cap = self.caps["pelvis_cm"]
        elif self.kind.get(b) == "elbow":
            return _add(v, step)   # 경첩 한계는 _clamp(굽힘 범위)
        else:
            cap = self.cap_of.get(b)
            r = (self.ref_rot.get(f) or {}).get(b)
            if r is not None and cap is not None:
                # 샘플 전이 — 상한은 덮은 자세에서
                return _add(r, self._toward_cap_rel(_sub(v, r), step, cap))
        return self._toward_cap_rel(v, step, cap)

    @staticmethod
    def _toward_cap_rel(v, step, cap):
        """|v + α·step| ≤ cap 인 가장 큰 α ∈ [0, 1] 만큼(cap 이 없으면 다)."""
        new = _add(v, step)
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
        """다시 풀 위반 — 손 · 아래팔 관통 · keep · 무기 파지(weapon 모드 — 손잡이 거리 × 가중 · 회전 초과 · 무기 상한 넘은 손목 굽힘). 위팔 '안 깊어짐'은
        풀 때만 함께 맞추고 위반으로 세지 않는다(TIER upper 주석). 원래 + 2° 손목 상한은 본 풀이 뒤 다듬기라 여기 없다(_finish_wrist)."""
        ev = self.evaluate(f, state, {"rot": {}, "trans": {}}, {"clear", "keep", "weapon"}, points, self._joints(f), jac=False)
        clear = [c for c in ev["info"]["clear"] if c[4] > TOL_CM]
        keep = ev["info"]["keep"]
        bad_keep = bool(keep and (keep["pos_cm"] > KEEP_TOL_CM * self.scale or keep["deg"] > KEEP_TOL_DEG))
        wi = ev["info"].get("weapon")
        bad_weapon = bool(wi and (wi["pos_cm"] > WEAPON_TOL_CM * self.scale or wi["rot_deg"] > WEAPON_TOL_DEG or wi["bend_deg"] > BEND_TOL_DEG))
        return {"clear": clear, "keep": bad_keep, "keep_err": keep, "weapon": bad_weapon, "any": bool(clear or bad_keep or bad_weapon)}

    def run(self, log=None) -> dict:
        t0 = time.time()
        if not self.targets and not self.pose_from:
            state, passes = self._solve_states()
            region = None
        else:
            # (가) 목표 없는 풀이(목표 없는 Job 과 같은 코드 · 입력 — cfg 는 targets · pose_from 키만 다르고 풀이는 그 키를 읽지 않는다) → 완급 > 0
            # 블록만 다시(지시 목표 · 샘플 전이 함께)
            base_solver = Solver(self.model, self.cfg, grip=self.grip, loop=self.loop, weapon=self.weapon, fingers=self.fingers)
            base, passes = base_solver._solve_states()
            state, region = self._solve_targets(base, [base_solver.pose(f, s)[0] for f, s in enumerate(base)])
            for key in ("frame_solves", "evaluations"):
                self.stats[key] += base_solver.stats[key]
            for b, c in base_solver.stats["clamped"].items():
                self.stats["clamped"][b] = self.stats["clamped"].get(b, 0) + c
        if log:
            log(f"body_fit: {self.rig.frames} frames · passes {passes} · {self.stats['frame_solves']} frame solves · {round(time.time() - t0, 1)} s"
                + (f" · target blocks {region['blocks']} (passes {region['passes']})" if region else ""))
        out = self._result(state, passes, time.time() - t0)
        if region:
            out["region"] = region
        return out

    def _solve_states(self) -> tuple[list, int]:
        """목표 없는 풀이 — 프레임별 상태 · 패스 수."""
        n = self.rig.frames
        zero = {"rot": {}, "trans": {}}
        radius = int(round(self.cfg["smooth_s"] * self.model.fps))
        cand = [self._candidates(f, self.model.poses[f]) for f in range(n)]
        base_anchor = [self._anchor_of(f, zero) for f in range(n)]
        # ---- 1 회: 위반 프레임만 풀이(앞 프레임 해에서 시작 — 이어진 위반 구간이 한 해를 따라간다) ----
        x_full, active = [], []
        prev_full = None
        for f in range(n):
            need = self._violations(f, zero, cand[f])
            if need["any"]:
                start = prev_full if prev_full is not None else zero
                sf, _ = self.solve_frame(f, start, {**base_anchor[f], "prev": prev_full}, FAMILIES, cand[f])
                prev_full = sf
            else:
                sf, prev_full = zero, None
            x_full.append(sf)
            active.append(sf is not zero)
        state = self._combine([zero] * n, [self._diff(a, zero) for a in x_full], radius, active, SPLINE_QUIET_WEIGHT)
        passes = 1
        # ---- 재검사: 남은 하드 잔차가 있는 프레임만 그 값에서 다시(두 팔 함께 — 짝이 맞는다) → 증분도 스플라인으로 이어 붙인다 ----
        # (처음 판의 '보조 팔 따라가기' · '매끈화 없는 마무리'는 위반 프레임만 골라 다시 풀어 이웃과 끊겼다 — 띠 정정 떨림 1.05 → 4.7)
        for _ in range(self.cfg["passes"] - 1 + EXTRA_PASSES):
            cand = [sorted(set(c) | set(self._candidates(f, self.pose(f, state[f])[0]))) for f, c in enumerate(cand)]
            incs, again = [], []
            for f in range(n):
                v = self._violations(f, state[f], cand[f])
                again.append(v["any"])
                if again[-1]:
                    prev = state[f - 1] if f else (state[n - 2] if self.loop else None)
                    sf, _ = self.solve_frame(f, state[f], {**self._anchor_of(f, state[f]), "prev": prev}, FAMILIES, cand[f])
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
            state = self._combine(state, incs, radius, active, SPLINE_RECHECK_QUIET_WEIGHT)
        return self._finish_wrist(self._snap_weapon(state)), passes

    def _snap_weapon(self, state: list, blocks: list | None = None) -> list:
        """weapon 모드 마무리(8-4c) — 매끈화 · 재검사 뒤 파지 프레임(가중 > 0) 전부를 보조 팔(쇄골 · 위팔 · 팔꿈치 · 손목)만으로 다시 푼다(관통 · 위팔 ·
        무기 파지 · 손목 위치 · 관절 충실도 — 기준 = 매끈화한 상태, 시간 연속 = 앞 프레임 마무리). 관절 델타 스플라인은 비선형 파지(손바닥 ↔ 손잡이)를
        묽혀 0.4 ~ 1.2 cm 를 남겼다(합성 — 프레임 풀이는 0.02) — 위반 프레임만이 아니라 구간 전체를 같은 규칙으로 이어 고치므로 8-4b 의 '위반 프레임만
        마무리'(띠 정정 zigzag 1.05 → 4.7)처럼 끊기지 않는다(합성 최대 1.15 → 0.011 cm · zigzag 0.44 → 0.03). 무기 · 주 손은 그대로. blocks = 목표 블록
        프레임 목록들(그 프레임만 — 밖은 목표 없는 해 그대로), 없으면 전체."""
        wg = self.wgrip
        if wg is None:
            return state
        arm = self.rig.arms[wg["side"]]
        only = {arm[k] for k in ("clavicle", "upper", "elbow", "wrist") if arm[k] is not None}
        fam = {"clear", "upper", "weapon", "keep", "bend", "wrist", "fid"}   # keep = 블렌드 프레임의 keep 몫(무기 파지 가중과 나눠 가진다)
        out = list(state)
        for run in (blocks if blocks is not None else [range(self.rig.frames - 1 if self.loop else self.rig.frames)]):
            prev = carried = None
            for f in run:
                if self.weapon_w[f] <= 0.0:
                    prev = carried = None
                    continue
                cand = sorted(set(self._candidates(f, self.model.poses[f])) | set(self._candidates(f, self.pose(f, state[f])[0])))
                anchor = {**self._anchor_of(f, state[f]), "prev": prev}
                out[f], ev = self.solve_frame(f, state[f], anchor, fam, cand, only=only)
                # 둘째 출발점 = 앞 프레임 마무리 증분을 이어 받은 상태(비용이 낮은 쪽) — 매끈화가 빠른 블렌드 아웃(원래 손이 0.2 초에 7 → 43 cm 떠남)과
                # 주 손 자리 통과를 이웃과 섞어 손이 반대 손을 꿰뚫은 채 들어오면 그 자리에서 시작한 풀이는 양쪽 바깥 방향이 엇갈려 갇혔다(운영 Attack2
                # 옵트인 오프라인 — f61 · f62 손끼리 4.75 · 5.38 → 4.31 · 1.78 cm, 구간 파지 p95 3.36 → 1.28 cm, 떨림 8.16 → 8.88(원래 8.16))
                if carried is not None:
                    start = self._plus(state[f], carried)
                    self._clamp(f, start, count=False)
                    alt, ev2 = self.solve_frame(f, start, anchor, fam, cand, only=only)
                    if ev2["cost"] < ev["cost"]:
                        out[f] = alt
                carried = self._diff(out[f], state[f])
                prev = out[f]
        if self.loop:
            out[-1] = self._copy(out[0])
        return out

    def _finish_wrist(self, state: list, blocks: list | None = None) -> list:
        """보조 손목 다듬기(8-4c 후속 2차) — 본 풀이(매끈화 · 재검사 · 무기 마무리) 뒤 손목 굽힘 상한이 있는 파지 프레임 전부를 보조 손목만으로 다시
        푼다(관통 · 손목 굽힘 상한 · 관절 충실도 — 기준 = 그 상태, 시간 연속 = 앞 프레임 다듬기 증분 — 위반 프레임만이 아니라 구간 전체라 끊기지 않는다.
        _snap_weapon 처럼 앞 프레임 상태 자체를 기준으로 하면 keep 이 없는 다듬기는 손목 회전을 앞 프레임 쪽으로 늦춰, 상한이 안 걸린 s27 에서도 keep
        회전이 12.2 → 21.2° 로 풀렸다). 상한을 본 풀이 잔차에 걸던 1차 판은 팔 보정 경로를 바꿔 매끈화 뒤 재검사가 못 따라갔다(통합 — 낫 정정 머리목
        0 → 1.7% · 2.88 cm, s27 주 손목 59.8 → 66.6°, 운영 Attack2 꼬임 7.4 → 13.7%, T5 무기 끝 p95 2.04 → 2.45 cm) — 손목만 돌리면 팔 · 주 손은 본 풀이
        해 그대로다(오프라인 실제 모델 — 다듬기 전 = 8-4b 값, 주 손 · 보조 팔꿈치 이동 0).
        - 관통은 그 상태보다 깊어지지 않게만(쌍 단위 바닥 _floor_at(pair) — 손목만 돌린 손이 몸 · 머리로 다시 들지 않게, 남은 얕은 관통을 손목 하나로
          그 프레임만 풀지 않게). 바닥이 없으면 s25 f55 머리 1.76 cm 를 손목을 14° 펴서 빼 떨림 2.17 → 6.06, 점마다 바닥이면 낫 정정 f48 · f51 이 갇히거나
          (굽힘 +6.1°) 머리 근처에서 상한보다 4° 더 펴 떨림 1.99 → 2.75. 관통을 빼면 s25 머리 1.76 → 2.71 cm 로 새로 든다.
        - 다듬기 동안 지도 각도 칸은 C++ 처럼 그 자세의 어깨로 나눈다(live_lateral — _lateral_x). 본 풀이가 쇄골을 옮긴 프레임은 원래 축과 1 ~ 2° 어긋나,
          원래 축으로 다듬으면 칸 경계의 손가락 점을 모델은 얕다(−2.13) · C++ 는 깊다(+2.81 cm)고 봤다(s25 f55 — 통합 0.8% · 2.81, 이 규칙이면 0% · 1.50).
          본 풀이는 원래 축 그대로(8-4b 해).
        - keep 은 두지 않는다 — 같은 손목을 상한과 반대로 당겨 상한이 안 맞았다(keep 을 두면 낫 정정 +3.6° · 최대 94.6(원본 91.1), s25 +3.3°). 빼면
          +2.1 · +2.1° 이고 대가는 keep 회전(낫 정정 최대 2.6 → 10.9° · s25 2.7 → 7.2° — c2_keep 은 8-4b 부터 알려진 미달)이다.
        무기 파지 프레임(가중 > 0)은 _snap_weapon 이 보조 팔 전체로 이미 상한까지 풀었다 — 건너뛰고 시간 연속만 잇는다. blocks = 목표 블록 프레임
        목록들(_snap_weapon 과 같다)."""
        br = self.bend_rig
        if br is None:
            return state
        only = {br["wrist"]}
        fam = {"clear", "bend", "fid"}
        n = self.rig.frames
        out = list(state)
        floor0, self.floor = self.floor, dict(self.floor)
        self.live_lateral = True
        for run in (blocks if blocks is not None else [range(n - 1 if self.loop else n)]):
            carried = None
            for f in run:
                if self.bend_cap[f] is None:
                    carried = None
                    continue
                if self.weapon_w[f] > 0.0:
                    carried = self._diff(out[f], state[f])
                    continue
                pose = self.pose(f, state[f])[0]
                cand = sorted(set(self._candidates(f, self.model.poses[f])) | set(self._candidates(f, pose)))
                self._floor_at(f, pose, pair=True)
                prev = self._plus(state[f], carried) if carried is not None else None
                out[f], _ = self.solve_frame(f, state[f], {**self._anchor_of(f, state[f]), "prev": prev}, fam, cand, only=only)
                carried = self._diff(out[f], state[f])
        self.floor, self.live_lateral = floor0, False
        if self.loop:
            out[-1] = self._copy(out[0])
        return out

    # ---- (가) 지시 목표 블록 ----
    def _solve_targets(self, base: list, base_poses: list) -> tuple[list, dict]:
        """목표 없는 해 base 를 그대로 두고 완급 > 0 블록만 다시 푼다 — 블록 밖 = base 복사(본 델타가 목표 없는 Job 과 같다 → 구간 ± ease 밖 변화 0).
        블록 안의 기준 = base: 목표 오프셋(_target_poses) · 충실도(관절 · 손목 · 주 손 — anchor = base 상태 · 자세) · keep 상대 변환 · 관통 바닥
        (_limit — max(허용, base 깊이)) · away 거리. 완급이 0 으로 갈수록 해가 base 로 수렴해 이음매가 이어진다(블록 앞뒤는 spline_block 의 0 고정).
        x_T 는 base + 앞 프레임 목표 증분 × 완급 비에서, 관통 몫 x 는 앞 프레임의 관통 증분을 x_T 위에 이어 시작한다(블록 첫 프레임은 둘 다 base) — 지난 판은 앞 프레임
        해로 시작하는 한 줄 사슬이 구간 끝의 다른 상태에서 출발해 구간 뒤 전체가 다른 국소 해로 갔다(T3 f47 23 cm · T4 머리 관통 10.6 cm). 관통 몫
        Δ = x − x_T 는 _combine_block(ρ 섞기 · 블록 안 스플라인). 재검사도 블록 프레임만. → (상태, region 요약)."""
        n = self.rig.frames
        radius = int(round(self.cfg["smooth_s"] * self.model.fps))
        if self.loop:
            for t in self.targets:
                t["ramp"] = self._wrap_ramp(t)
            for p in self.pose_from:
                self._wrap_pose_from(p)
        for t in self.targets:
            _target_poses(self.rig, t, base_poses)
        self.ref_poses = base_poses
        blocks = self._blocks()
        frames = [f for blk, _, _ in blocks for f in blk]
        # 샘플 전이 — 덮은 자세(묶음 본 로컬 = slerp(base, 샘플, weight × 완급))가 출발점 · 충실도 기준. 샘플 전이가 없는 프레임은 base 그대로(같은 객체)
        ov = {f: self._overlay(f, base[f]) for f in frames}
        ov_poses = {f: base_poses[f] if ov[f] is base[f] else self.pose(f, ov[f])[0] for f in frames}
        anchor = {f: {"rot": dict(ov[f]["rot"]), "trans": dict(ov[f]["trans"]), "pose": ov_poses[f]} for f in frames}
        # 기준 바꾸기 — keep 상대 변환 · 관통 바닥(원래 위팔 깊이를 먼저 채운다)
        self.keep_rel = dict(self.keep_orig)
        if any(ov[f] is not base[f] for f in frames):
            self._fill_grip_gaps([f for f in frames if ov[f] is not base[f]])
        cand = {}
        for f in frames:
            if f in self.keep_orig or self.keep_w[f] > 0.0:
                self.keep_rel[f] = self._keep_of(base_poses[f])
            cand[f] = sorted(set(self._candidates(f, self.model.poses[f])) | set(self._candidates(f, base_poses[f])))
            if ov[f] is not base[f]:
                cand[f] = sorted(set(cand[f]) | set(self._candidates(f, ov_poses[f])))
        self.floor = {}
        for f in frames:
            self._floor_at(f, base_poses[f])
            if ov[f] is not base[f]:
                # 위팔 '안 깊어짐' 기준은 덮은 자세(샘플이 원래 그 깊이) — 손 · 아래팔은 base 바닥 그대로(덮기가 관통을 base 보다 깊게 못 만든다)
                self._floor_at(f, ov_poses[f], parts=("upper_arm",))
                br = self.bend_rig
                if br is not None and self.bend_cap[f] is not None and br["wrist"] in self.pf_req[f]:
                    # 보조 손목을 덮은 프레임만 — 굽힘 상한 기준 = max(원래, 덮은 자세) + 허용(샘플 손목을 다듬기가 되돌리지 않게). 손목을 안 덮으면 원래 + 허용
                    # 그대로(덮은 자세 = base 라 그 굽힘에 허용을 또 얹으면 base 의 허용 위에 쌓였다 — S2 보조 손목 증가 4.05°)
                    bend = WeaponRig.bend(ov_poses[f], br["elbow"], br["wrist"], br["middle"])
                    self.bend_cap[f] = max(self.bend_cap[f], bend + math.radians(BEND_KEEP_TOL_DEG))
        state = [self._copy(s) for s in base]
        fam_t = FAMILIES - {"clear", "upper"}
        fam = FAMILIES
        solves0 = self.stats["frame_solves"]
        # ---- 1 회: 블록마다 x_T(목표 · keep · 충실도) → 위반이면 x(전부) — 관통 몫 사슬 = 앞 프레임 증분을 x_T 위에 ----
        # x_T 는 base + 앞 프레임 목표 증분 × 완급 비(ρ_f / ρ_f−1)에서 시작하고 시간 연속 항을 두지 않는다 — 관통 활성 집합이 없어 프레임마다 다른 해로
        # 뛰지 않는다. 앞 프레임 증분 그대로 시작하면 LM(≤ 12 회)이 base 쪽으로 다 돌아오지 못하고, 시간 연속 항은 앞 프레임 증분 쪽으로 당겨, 완급이
        # 줄어도 증분이 남았다(T4 f13 완급 0.10 에 4.98 cm · 비용 2270 — base 시작이면 1.39 cm · 102, 합성 블록 끝 2.79 → 1.22 cm). base 에서만 시작하면
        # 유지 구간의 목표가 관절 상한에 걸린 다른 국소 해로 갔다(합성 목표 오차 0.34 → 1.38 cm). 시간 연속은 관통 몫(x)에만
        rho = [max((t["ramp"][f] for t in self.targets + self.pose_from), default=0.0) for f in range(n)]
        for blk, pin_a, pin_b in blocks:
            x_t, incs, active = [], [], []
            d_t = d_full = None
            for k, f in enumerate(blk):
                start = ov[f]
                if d_t is not None:
                    start = self._plus(ov[f], self._scaled(d_t, rho[f] / rho[blk[k - 1]]))
                    self._clamp(f, start, count=False)
                st, _ = self.solve_frame(f, start, {**anchor[f], "prev": None}, fam_t, cand[f])
                d_t = self._diff(st, ov[f])
                # 목표가 손을 옮긴 곳의 점도 후보로(원래 · base 자세에서는 멀었던 점)
                cand[f] = sorted(set(cand[f]) | set(self._candidates(f, self.pose(f, st)[0])))
                need = self._violations(f, st, cand[f])
                if need["any"]:
                    carried = None
                    if d_full is not None:
                        carried = self._plus(st, d_full)
                        self._clamp(f, carried, count=False)
                    sf, _ = self.solve_frame(f, carried or st, {**anchor[f], "prev": carried}, fam, cand[f])
                    d_full = self._diff(sf, st)
                else:
                    sf, d_full = st, None
                x_t.append(st)
                incs.append(self._diff(sf, st))
                active.append(sf is not st)
            for f, s in zip(blk, self._combine_block(blk, x_t, incs, radius, active, SPLINE_QUIET_WEIGHT, pin_a, pin_b)):
                state[f] = s
        if self.loop:
            state[-1] = self._copy(state[0])
        # ---- 재검사: 블록 프레임만(증분도 블록 안 스플라인 · ±1 받침도 블록 안) ----
        pen, contact = self.model.penetration_cm, self.model.contact_cm
        base_pairs = {f: self._pair_depths(f, base_poses[f]) for f in frames if ov[f] is not base[f]}
        passes = 1
        total = self.cfg["passes"] - 1 + EXTRA_PASSES
        for it in range(total):
            any_again = False
            for blk, pin_a, pin_b in blocks:
                incs, again, deep = [], [], []
                for f in blk:
                    cand[f] = sorted(set(cand[f]) | set(self._candidates(f, self.pose(f, state[f])[0])))
                    v = self._violations(f, state[f], cand[f])
                    again.append(v["any"])
                    # 마지막 재검사에서만 — 스플라인 패스들이 못 푼, 덮기가 새로 만든 관통(깊이 > 관통 판정이고 그 쌍(쪽 · 부위 · 지도)의 base 최대 깊이 + 관통
                    # 여유보다 깊다). 첫 재검사부터 걸면 스플라인이 몇 패스에 매끈하게 풀 손-머리 관통을 그 프레임 값으로 한 번에 고쳐 튀었다(S2 f62 · f63 —
                    # 떨림 4.36, 스플라인만이면 1.29), 점 단위 바닥으로 재면 몸통이 손에 대해 돈 프레임까지 든다
                    bp = base_pairs.get(f) or {}
                    deep.append(it == total - 1 and any(c[2] > pen and c[2] > bp.get((self.points[c[0]]["side"], self.points[c[0]]["part"], c[1]), -math.inf)
                                                        + pen - contact for c in v["clear"]))
                    if again[-1]:
                        sf, _ = self.solve_frame(f, state[f], {**self._anchor_of(f, state[f]), "prev": self._prev_state(state, f)}, fam, cand[f])
                        incs.append(self._diff(sf, state[f]))
                    else:
                        incs.append({"rot": {}, "trans": {}})
                if not any(again):
                    continue
                any_again = True
                active = list(again)
                for k in [k for k in range(len(blk)) if again[k]]:
                    for g in (k - 1, k + 1):
                        if 0 <= g < len(blk) and not again[g] and self._size(incs[k]) > self._size(incs[g]):
                            incs[g] = incs[k]
                            active[g] = True
                combined = self._combine_block(blk, [state[f] for f in blk], incs, radius, active, SPLINE_RECHECK_QUIET_WEIGHT, pin_a, pin_b, deep)
                for f, s in zip(blk, combined):
                    state[f] = s
            if not any_again:
                break
            passes += 1
            if self.loop:
                state[-1] = self._copy(state[0])
        frames_of = [blk for blk, _, _ in blocks]
        state = self._finish_wrist(self._snap_weapon(state, frames_of), frames_of)
        return state, {"blocks": [[blk[0], blk[-1]] for blk, _, _ in blocks], "passes": passes, "frame_solves": self.stats["frame_solves"] - solves0}

    def _floor_at(self, f: int, pose, pair: bool = False, parts: tuple | None = None) -> None:
        """관통 바닥 — 그 자세에서 허용(_limit)보다 깊은 (f, 팔 점, 지도)의 깊이를 floor 에 둔다(그보다 얕게 요구하지 않는다 — 그 자세에 남은 한계는
        다시 풀지 않는다). pair = 점마다 대신 쌍(쪽 · 부위 · 지도 — 보고 쌍과 같은 묶음)의 최대 깊이를 그 쌍의 모든 점에: 쌍별 깊이가 그 자세보다
        깊어지지 않는다는 같은 보장이지만 점 하나가 제 깊이에 걸려 손 전체를 더 돌리지 않는다(_finish_wrist). parts = 그 팔 부위 점만(샘플 전이의
        위팔 — 덮은 자세 기준)."""
        deep = {}
        for i in self.arm_points:
            pt = self.points[i]
            if parts is not None and pt["part"] not in parts:
                continue
            p = self.model.skin(pose, pt)
            for name in self._maps_for(pt["side"]):
                hit = self.probe(name, f, p, pose)
                if hit is not None and hit[0] > self._limit(f, i, name, pt["part"] == "upper_arm"):
                    if pair:
                        key = (pt["side"], pt["part"], name)
                        deep[key] = max(deep.get(key, hit[0]), hit[0])
                    else:
                        self.floor[(f, i, name)] = hit[0]
        for i in self.arm_points if deep else ():
            pt = self.points[i]
            for name in self._maps_for(pt["side"]):
                d = deep.get((pt["side"], pt["part"], name))
                if d is not None and d > self.floor.get((f, i, name), -math.inf):
                    self.floor[(f, i, name)] = d

    def _overlay(self, f: int, s: dict) -> dict:
        """샘플 전이 덮은 자세 — 상태 s(목표 없는 해)에서 완급 > 0 인 pose_from 마다(요청 순서로 겹쳐) 묶음 본 로컬 = slerp(지금 로컬, 샘플 로컬,
        weight × 완급). 그 프레임의 관절 상한 기준(ref_rot · ref_bend) · 보고 기준(pf_req) · 충실도 배율 본(pf_at)을 둔다. 덮을 것이 없으면 s 그대로."""
        items = [p for p in self.pose_from if p["ramp"][f] > 0.0 and f in p["local"]]
        if not items:
            return s
        out = self._copy(s)
        local0 = self.rig.local[f]
        req = {}
        for p in items:
            k = p["weight"] * p["ramp"][f]
            for b in p["bones"]:
                q0 = local0[b][0]
                new = _slerp(bm.qnormalize(bm.qmul(qexp(out["rot"].get(b, (0.0, 0.0, 0.0))), q0)), p["local"][f][b], k)
                v = qlog(bm.qmul(new, bm.qconj(q0)))
                if _norm(v) > 1e-12:
                    out["rot"][b] = v
                else:
                    out["rot"].pop(b, None)
                req[b] = new
        self.pf_req[f] = req
        self.pf_at[f] = set(req)
        self.pf_state[f] = out
        self.ref_rot[f] = {b: out["rot"].get(b, (0.0, 0.0, 0.0)) for b in req}
        pose = self.pose(f, out)[0]
        self.ref_bend[f] = {side: self.rig._bend(f, side, pose) for side, arm in self.rig.arms.items() if arm["elbow"] in req}
        return out

    def _fill_grip_gaps(self, frames: list) -> None:
        """샘플 전이로 두 손 관계가 바뀌는 프레임 — 파지 띠의 짧은 빈틈(앞뒤 GRIP_BLEND_WEAPON_S 안에 가득 파지)을 메운다: 가중 = max(그 값,
        min(앞쪽 최대, 뒤쪽 최대)). 띠는 '같은 무기를 쥠'의 대리라 생성 손 간격이 띠 끝을 넘나들면 깜빡이는데, 덮기 전에는 원래 관계라 무해했지만 덮은
        두 손 관계가 keep 과 다르면 keep 이 약해지는 몇 프레임만 팔이 샘플 쪽으로 튀었다(낫 정정 S3 오프라인 — f110 ~ 114 가중 0.84 · 0.5 · 0.16, 떨림
        1.28 → 3.81 · 관통 몫을 스플라인으로 이으면 6.37). keep · 파지 가중(손목 자유도 · 주 손 충실도)을 같이 메우고 grip 사전은 사본(호출 쪽 기록은 그대로)."""
        w = max(1, int(round(GRIP_BLEND_WEAPON_S * self.model.fps)))
        kw, gw = list(self.keep_w), list(self.grip["weights"])
        for f in frames:
            if kw[f] >= 1.0:
                continue
            fill = min(max(self.keep_w[max(0, f - w):f + 1]), max(self.keep_w[f:f + w + 1]))
            if fill > kw[f]:
                kw[f] = fill
                gw[f] = max(gw[f], fill)
        self.keep_w = kw
        self.grip = {**self.grip, "weights": gw}

    def _wrap_pose_from(self, p: dict) -> None:
        """루프 원본 — 샘플 전이 완급 · 프레임별 샘플 로컬을 감아 돈다(_wrap_ramp 와 같은 규칙 — 겹치면 완급이 큰 쪽의 샘플 로컬)."""
        n = self.rig.frames
        m = n - 1
        fa, fb = p["frames"]
        ease = p["ease_frames"]
        p["ramp"] = self._wrap_ramp(p)
        best: dict = {}
        for k in range(fa - ease, fb + ease + 1):
            v = 1.0 if fa <= k <= fb else _smootherstep((k - (fa - ease - 1)) / (ease + 1)) if k < fa else _smootherstep(((fb + ease + 1) - k) / (ease + 1))
            if k in p["local_k"] and v > best.get(k % m, (-1.0, None))[0]:
                best[k % m] = (v, p["local_k"][k])
        p["local"] = {f: x[1] for f, x in best.items()}
        if 0 in p["local"]:
            p["local"][n - 1] = p["local"][0]

    def _pair_depths(self, f: int, pose) -> dict:
        """그 자세의 쌍(쪽 · 팔 부위 · 지도 — _floor_at(pair) 와 같은 묶음)별 최대 깊이."""
        out: dict = {}
        for i in self.arm_points:
            pt = self.points[i]
            p = self.model.skin(pose, pt)
            for name in self._maps_for(pt["side"]):
                hit = self.probe(name, f, p, pose)
                if hit is not None:
                    key = (pt["side"], pt["part"], name)
                    out[key] = max(out.get(key, hit[0]), hit[0])
        return out

    def _wrap_ramp(self, t: dict) -> list:
        """루프 원본 — 완급을 감아 돈다(첫 프레임 근처 목표의 ease 가 끝 프레임 쪽으로, 끝 프레임 = 첫 프레임). resolve_targets 의 같은 smootherstep."""
        n = self.rig.frames
        m = n - 1
        fa, fb = t["frames"]
        ease = t["ease_frames"]
        ramp = [0.0] * n
        for k in range(fa - ease, fb + ease + 1):
            if fa <= k <= fb:
                v = 1.0
            elif k < fa:
                v = _smootherstep((k - (fa - ease - 1)) / (ease + 1))
            else:
                v = _smootherstep(((fb + ease + 1) - k) / (ease + 1))
            ramp[k % m] = max(ramp[k % m], v)
        ramp[n - 1] = ramp[0]
        return ramp

    def _blocks(self) -> list:
        """완급 > 0 인 이어진 프레임 묶음 → [(프레임(시간 순), 앞에 블록 밖 프레임이 있나, 뒤에 있나)]. 루프면 끝 프레임(= 첫)을 빼고 감아 돈다."""
        n = self.rig.frames
        m = n - 1 if self.loop else n
        on = [any(t["ramp"][f] > 0.0 for t in self.targets + self.pose_from) for f in range(m)]
        if not any(on):
            return []
        if all(on):
            return [(list(range(m)), False, False)]
        runs, f = [], 0
        while f < m:
            if on[f]:
                a = f
                while f < m and on[f]:
                    f += 1
                runs.append(list(range(a, f)))
            else:
                f += 1
        if self.loop and len(runs) > 1 and on[0] and on[m - 1]:
            runs[0] = runs.pop() + runs[0]
        return [(r, True, True) if self.loop else (r, r[0] > 0, r[-1] < n - 1) for r in runs]

    def _prev_state(self, state: list, f: int):
        """앞 프레임 상태(시간 연속 기준) — 루프면 0 의 앞 = n−2."""
        if f:
            return state[f - 1]
        return state[self.rig.frames - 2] if self.loop else None

    @staticmethod
    def _scaled(d: dict, k: float) -> dict:
        return {key: {j: _scale(v, k) for j, v in d[key].items()} for key in ("rot", "trans")}

    @staticmethod
    def _plus(a: dict, d: dict | None) -> dict:
        out = Solver._copy(a)
        for key in ("rot", "trans"):
            for j, v in (d or {}).get(key, {}).items():
                out[key][j] = _add(out[key].get(j, (0.0, 0.0, 0.0)), v)
        return out

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

    def _combine(self, base: list, incs: list, radius: int, active: list[bool], quiet: float) -> list:
        """base + S(증분) — S = 관절 · 성분별 가중 매끈화 스플라인(spline — active = 하드 잔차로 푼 프레임). 끝에 상한.
        루프면 스플라인이 순환이고 끝 프레임 = 첫 프레임 상태(같은 시점)."""
        n = len(base)
        out = [self._copy(s) for s in base]
        joints = {(key, j) for d in incs for key in ("rot", "trans") for j in d[key]}
        for key, j in joints:
            sm = spline([d[key].get(j, (0.0, 0.0, 0.0)) for d in incs], active, radius, self.loop, quiet)
            for f in range(n):
                v = sm[f]
                if _norm(v) > 1e-12:
                    out[f][key][j] = _add(out[f][key].get(j, (0.0, 0.0, 0.0)), v)
        for f in range(n):
            self._clamp(f, out[f])
        if self.loop:
            out[-1] = self._copy(out[0])
        return out

    def _combine_block(self, frames: list, base: list, incs: list, radius: int, active: list[bool], quiet: float, pin_a: bool, pin_b: bool,
                       deep: list[bool] | None = None) -> list:
        """목표 블록의 base + 증분 — 완급 ρ 만큼 그 프레임 증분, 나머지는 블록 안 매끈화: (1 − ρ)·S_E((1 − ρ)·증분) + ρ·증분. S_E = spline_block
        (블록 앞뒤 0 고정 — 블록 밖으로 새지 않는다). 전부 S_E 로 이으면 짧은 블록 가장자리(완급 0.5 근처)의 재검사 증분이 0 고정에 눌려 관통이 남았다
        (합성 몸 쪽 목표 2.0 cm > 맞닿음 0.95 — ρ 섞기는 1.03). 그 프레임 몫도 반경 2 로 약하게 이으면 오프라인 T4 떨림은 1.82 → 1.21 이었지만 짧은
        블록에서 막힌 목표의 되돌림이 번져 완급 프레임 관통 0.6 cm 가 남아(합성) 쓰지 않는다. 끝에 상한. → 블록 프레임 상태 목록."""
        # 샘플 전이 — 관통 몫의 ρ = 지시 목표 완급만(샘플 전이만 있는 프레임은 블록 안 스플라인 — 목표 없는 풀이와 같은 규칙): 그 프레임 값으로 두면
        # 덮기가 만든 고립 관통 보정이 그대로 남아 튀었다(낫 정정 S2 오프라인 — 목을 덮어 손-머리가 f62 · f63 에만 닿아 두 팔 12° → 떨림 1.28 → 6.87,
        # 스플라인이면 1.30). 재검사에서 덮기가 새로 만든 관통(쌍 깊이 > 관통 판정 · base 쌍 + 관통 여유 — _solve_targets)이 남은 프레임(deep)만 샘플 전이
        # 완급만큼 그 프레임 값 — 스플라인만이면 덮기가 몸 안 깊이 민 팔을 0 고정 블록 가장자리(완급 0.5)에서 못 따라갔다(합성 3.0 cm), 재검사 전부를 그
        # 프레임 값으로 두면 맞닿음 근처 작은 증분이 다시 튀었다(S2 · S3 떨림 3.44 · 5.75). keep · 충실도 몫(x_T)은 늘 프레임마다 그대로 — 그것까지 이으면 덮기가 두 손 관계를 0.13 초에 바꾸는 블록 시작에서
        # keep 이 묽어졌다(S3 f78 10.6 cm)
        rho = [max([t["ramp"][f] for t in self.targets] + ([p["ramp"][f] for p in self.pose_from] if deep and deep[k] else []), default=0.0)
               for k, f in enumerate(frames)]
        out = [self._copy(s) for s in base]
        whole = self.loop and len(frames) == self.rig.frames - 1
        joints = {(key, j) for d in incs for key in ("rot", "trans") for j in d[key]}
        for key, j in joints:
            raw = [d[key].get(j, (0.0, 0.0, 0.0)) for d in incs]
            sm = spline_block([_scale(v, 1.0 - rho[k]) for k, v in enumerate(raw)], active, radius, pin_a, pin_b, quiet, whole)
            for k in range(len(frames)):
                v = _add(_scale(sm[k], 1.0 - rho[k]), _scale(raw[k], rho[k]))
                if _norm(v) > 1e-12:
                    out[k][key][j] = _add(out[k][key].get(j, (0.0, 0.0, 0.0)), v)
        for k, f in enumerate(frames):
            self._clamp(f, out[k])
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
        out = {"version": VERSION, "frames": n, "poses": poses, "state": state, "deltas": deltas, "moved_cm": moved, "changed_frames": changed,
               "keep": keep, "wrist_bend": self.bend_report(poses), "targets": targets, "predicted": predicted, "legs": legs, "passes": passes,
               "loop": {"on": self.loop, "seam_deg": round(seam, 3)},
               "seconds": round(seconds, 2), "stats": {k: v for k, v in self.stats.items() if k != "clamped"}}
        if self.pose_from:
            out["pose_from"] = self.pose_from_report(poses, state)
        if self.weapon is not None:
            # 무기(8-4c) — 파지 오차(전 = 원본 포즈 · 후) · 무기-몸 관통 기록(모델 지도 — 제약 아님)
            out["weapon"] = {"grip": {"before": self.weapon_report(model.poses), "after": self.weapon_report(poses)} if self.weapon.grip else None,
                             "body": {"before": weapon_body(self, model.poses), "after": weapon_body(self, poses)}}
        return out

    def weapon_report(self, poses: list) -> dict:
        """weapon 모드 파지 오차 — 무기 파지 프레임(가중 1 · 주 손 자리 밖) 손바닥 점 ↔ 손잡이 선분 거리 · 미끄러짐 위치(선분 시작에서 cm) · 회전 오차
        (요청 회전 또는 원래 상대 회전) · 쥠 축 ↔ 손잡이 각(부호 무관 — 기록) · 보조 손목 굽힘(°, 상한과 함께) · 블렌드 프레임(0 < 가중 < 1)과 주 손 자리
        통과 프레임(가중 1 · 원래 손바닥 투영이 주 손 자리 안)의 목표 점(원래 손바닥 → 손잡이 보간 — 풀이와 같은 목표) 오차 · 모든 프레임의 손잡이
        거리 · 두 손 선 ∠ 손잡이(기록)."""
        wg = self.weapon.grip
        dist, along, rot, axis, bend, dist_all, hands, blend, passing = [], [], [], [], [], [], [], [], []
        for f in range(self.rig.frames):
            st = self.weapon.grip_state(f, poses[f])
            bend.append(math.degrees(st["bend"]))
            dist_all.append(st["dist"])
            if st["hands_line"] is not None:
                hands.append(math.degrees(st["hands_line"]))
            if 0.0 < self.weapon_w[f] < 1.0:
                blend.append(self.weapon.grip_state(f, poses[f], self.weapon_s[f])["err"])
            elif self.weapon_w[f] >= 1.0 and wg["pass_f"][f] < 1.0:
                passing.append(st["err"])
                continue
            if self.weapon_w[f] < 1.0:
                continue
            dist.append(st["dist"])
            along.append(st["along_cm"])
            rot.append(math.degrees(st["rot"]))
            if st["axis"] is not None:
                axis.append(math.degrees(st["axis"]))
        p95 = lambda xs: round(bm.percentile(xs, 95.0), 3) if xs else None  # noqa: E731
        mx = lambda xs: round(max(xs), 3) if xs else None  # noqa: E731
        return {"frames": len(dist), "dist_cm_p95": p95(dist), "dist_cm_max": mx(dist), "along_cm": [round(min(along), 2), round(max(along), 2)] if along else None,
                "rot_deg_p95": p95(rot), "rot_deg_max": mx(rot), "axis_deg_p95": p95(axis), "axis_deg_max": mx(axis),
                "wrist_bend_deg_max": mx(bend), "wrist_bend_cap_deg": round(math.degrees(wg["cap"]), 3), "rotation_tol_deg": round(math.degrees(wg["tol"]), 3),
                "rotation_target": "request" if wg["rot"] is not None else "original_relative", "active": self.wgrip is not None,
                "blend": {"frames": len(blend), "target_err_cm_p95": p95(blend), "target_err_cm_max": mx(blend)},
                "lead_pass": {"frames": len(passing), "target_err_cm_max": mx(passing),
                              "zone_cm": [round(x * _norm(_sub(*wg["seg"])), 2) for x in wg["zone"][:2]] if wg["zone"] else None},
                "all_frames": {"dist_cm_p50": round(bm.percentile(dist_all, 50.0), 2), "dist_cm_p5": round(bm.percentile(dist_all, 5.0), 2),
                               "hands_line_deg_p50": round(bm.percentile(hands, 50.0), 2) if hands else None}}

    def bend_report(self, poses: list) -> dict:
        """보조 손목 굽힘 상한 기록 — 상한이 있는 프레임(파지 — 손목을 연다)의 원래 대비 굽힘 증가(°) · 상한 넘은 프레임(> BEND_TOL_DEG) · 모든 프레임의
        원래 대비 증가 최대(매끈화 꼬리 포함) · 굽힘 최대(전 · 후). 주 손은 손가락 뿌리가 있으면 기록만. 손가락 뿌리가 없으면 {on: False}."""
        br = self.bend_rig
        if br is None:
            return {"on": False, "reason": "no {Side}Middle finger chain on the target mesh (or the weapon grip) — the off-hand wrist bend cap is off"}
        n = self.rig.frames
        r3 = lambda x: round(x, 3) if x is not None else None  # noqa: E731
        inc, inc_all, after, over = [], [], [], 0
        for f in range(n):
            b = WeaponRig.bend(poses[f], br["elbow"], br["wrist"], br["middle"])
            after.append(b)
            inc_all.append(math.degrees(b - br["bend0"][f]))
            if self.bend_cap[f] is not None:
                inc.append(inc_all[-1])
                over += math.degrees(b - self.bend_cap[f]) > BEND_TOL_DEG
        out = {"on": True, "side": br["side"], "middle": br["middle_name"], "tol_deg": BEND_KEEP_TOL_DEG, "frames": len(inc),
               "increase_deg_max": r3(max(inc)) if inc else None, "increase_deg_p95": r3(bm.percentile(inc, 95.0)) if inc else None, "over_cap_frames": over,
               "all_frames_increase_deg_max": r3(max(inc_all)), "bend_deg_max": [r3(math.degrees(max(br["bend0"]))), r3(math.degrees(max(after)))]}
        lead = self.rig.side_of(br["side"])
        arm = self.rig.arms[lead]
        mid = self.model.index.get((self.fingers or {}).get(lead) or "")
        if mid is not None and arm["wrist"] in self.rig.anc_set[mid] and mid != arm["wrist"]:
            d = [math.degrees(WeaponRig.bend(poses[f], arm["elbow"], arm["wrist"], mid) - WeaponRig.bend(self.model.poses[f], arm["elbow"], arm["wrist"], mid))
                 for f in range(n) if self.bend_cap[f] is not None]
            out["lead"] = {"side": lead, "increase_deg_max": r3(max(d)) if d else None}
        return out

    def pose_from_report(self, poses: list, state: list) -> list:
        """샘플 전이마다 — 구간(완급 1) 프레임 묶음 본의 결과 로컬 ↔ 덮은 자세(pf_req — slerp(base, 샘플, weight)) 각(°, p95 · 최대), 완급 프레임 최대(기록),
        POSE_FROM_TOL_DEG 를 넘은 본(partial — 그 프레임의 관통(결과 또는 덮은 자세가 base 바닥 너머) · 파지 · 관절 상한, 아무것도 아니면 smoothing(이웃
        프레임 보정이 블록 스플라인으로 번진 몫)), 손가락 묶음 본
        최대, 모델에 없는 본(missing). 같은 본을 여러 항목이 덮으면 기준은 마지막 덮은 값."""
        rig = self.rig
        out = []
        for p in self.pose_from:
            window, ease_deg, per_bone = [], [], {}
            fingers = []
            for f in range(rig.frames - 1 if self.loop else rig.frames):
                s = p["ramp"][f]
                req = self.pf_req.get(f) or {}
                if s <= 0.0:
                    continue
                for b in p["bones"]:
                    if b not in req:
                        continue
                    pb = rig.parents[b]
                    loc = poses[f][b][0] if pb < 0 else bm.relative(poses[f][b], poses[f][pb])[0]
                    d = math.degrees(_norm(qlog(bm.qmul(loc, bm.qconj(req[b])))))
                    if s < 1.0:
                        ease_deg.append(d)
                        continue
                    window.append(d)
                    if b in p["finger_bones"]:
                        fingers.append(d)
                    if d > POSE_FROM_TOL_DEG:
                        per_bone.setdefault(b, []).append((f, d))
            partial = []
            for b, rows in sorted(per_bone.items()):
                blocked = set()
                for f, _ in rows:
                    near = self.evaluate(f, state[f], self._anchor_of(f, state[f]), {"clear"}, self.arm_points, self._joints(f), jac=False)["info"]["clear"]
                    if near or (f in self.pf_state and self._violations(f, self.pf_state[f], self.arm_points)["clear"]):
                        blocked.add("clearance")
                    if self.grip["weights"][f] > 0.0 and any((a["clavicle"] if a["clavicle"] is not None else a["upper"]) in rig.anc_set[b]
                                                             for a in rig.arms.values()):
                        blocked.add("grip")
                    if self._at_limit(f, b, state[f]):
                        blocked.add("joint_limit")
                partial.append({"bone": rig.model.bones[b], "frames": [rows[0][0], rows[-1][0]], "count": len(rows), "deg_max": round(max(d for _, d in rows), 3),
                                "blocked_by": sorted(blocked) or ["smoothing"]})
            r3 = lambda xs: round(max(xs), 3) if xs else None  # noqa: E731
            out.append({"id": p["id"], "note": p["note"], "asset": p["asset"], "mode": p["mode"], "weight": p["weight"],
                        "bones": [rig.model.bones[b] for b in p["bones"]], "missing": p.get("missing") or [], "presets": sorted(p.get("presets") or {}),
                        "window_s": p["window_s"], "source_s": p["source_s"], "frames": p["frames"], "ease_frames": p["ease_frames"],
                        "alignment": p["alignment"], "sample_fps": p.get("sample_fps"),
                        "achieved": {"deg_p95": round(bm.percentile(window, 95.0), 3) if window else None, "deg_max": r3(window), "ease_deg_max": r3(ease_deg)},
                        "fingers": {"bones": len(p["finger_bones"]), "deg_max": r3(fingers)} if p["finger_bones"] else None,
                        "partial": partial, "blocked_by": sorted({x for row in partial for x in row["blocked_by"]})})
        return out

    def keep_report(self, poses: list) -> dict:
        rig = self.rig
        pos, deg = [], []
        for f, (rel_p, rel_q) in self.keep_orig.items():
            if self.keep_w[f] < 1.0:
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
                pt = _target_point(t, poses[f])
                e = {}
                if f in t["pos"]:
                    e["pos"] = _norm(_sub(pt, t["pos"][f]))
                    pos_err.append(e["pos"])
                if f in t["rot"]:
                    e["deg"] = math.degrees(_norm(qlog(bm.qmul(pb[0], bm.qconj(t["rot"][f])))))
                    rot_err.append(e["deg"])
                if t["away"]:
                    c = poses[f][t["away"]["bone"]][1]
                    e["away"] = max(0.0, t["away"]["min_cm"] - _norm(_sub(pt, c)))
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


WEAPON_BODY_MAPS = ("torso", "thigh_l", "thigh_r", "head_neck")


def weapon_body(solver: Solver, poses: list) -> dict | None:
    """무기-몸 관통 기록(8-4c — 제약 아님): 무기 기록 점(weapon.record_points — 자루 선 + 반경 · 날 단면 격자)을 프레임마다 무기 강체로 옮겨 몸 지도
    (몸통 칸 · 넓적다리 · 머리목 — 풀이와 같은 probe)에 묻는다. 깊이 = 지도 깊이 + 점 반경. → {pairs{"부위|몸 부위": stats}, worst{…}, points, approx} | None."""
    wp = solver.weapon
    if wp is None or not wp.points:
        return None
    model = solver.model
    names = [m for m in WEAPON_BODY_MAPS if m in solver.maps]
    series: dict = {}
    worst = None
    n = len(model.frames)
    for f in range(n):
        W = poses[f][wp.bone]
        best: dict = {}
        for p_local, r, part in wp.points:
            p = bm.transform_point(W, p_local)
            for name in names:
                hit = solver.probe(name, f, p, poses[f])
                if hit is None:
                    continue
                key = (part, solver.body_part(name, hit[3]))
                d = hit[0] + r
                if key not in best or d > best[key]:
                    best[key] = d
                if worst is None or d > worst["depth_cm"]:
                    worst = {"depth_cm": round(d, 2), "frame": f, "time": round(model.times[f], 4), "part": part, "body": key[1]}
        for key in set(series) | set(best):
            series.setdefault(key, [None] * f).append(best.get(key))
    pairs = {"|".join(k): bm.pair_stats(v, model.contact_cm, model.penetration_cm) for k, v in sorted(series.items())}
    return {"pairs": pairs, "worst": worst, "points": len(wp.points), "approx": "geometry slices (handle line + radius, head slices as filled boxes)"}


def solve(model: bm.BodyModel, cfg: dict, *, grip: dict | None = None, targets: list[dict] | None = None, loop: bool = False, weapon: WeaponRig | None = None,
          fingers: dict | None = None, pose_from: list[dict] | None = None, log=None) -> dict:
    """한 풀이 — 모델 · 정규화한 fix.body · 파지(grip_weights) · 풀린 목표(resolve_targets) · 원본 루프 여부 · 무기(WeaponRig, 8-4c) · 손가락 뿌리
    (fingers{side: 대상 메시 손가락 체인 제안 {Side}Middle 시작 — 보조 손목 굽힘 상한, 없으면 그 제약을 끈다) · 풀린 샘플 전이(resolve_pose_from,
    8-4c c2) → Solver.run 결과."""
    return Solver(model, cfg, grip=grip, targets=targets, loop=loop, weapon=weapon, fingers=fingers, pose_from=pose_from).run(log=log)


def bone_deltas_op(result: dict) -> dict | None:
    """풀이 결과 → apply_animation_edits op(bone_deltas · space parent). 바꿀 것이 없으면 None."""
    bones = [b for b in result["deltas"]["bones"] if b["rotation_deg"] or b["translation_cm"]]
    return {"op": "bone_deltas", "space": "parent", "bones": bones} if bones else None
