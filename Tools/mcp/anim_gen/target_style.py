"""대상별 기준값 (Phase 9-5a · U8-b — 지침서 §14 '9-5a'). 순수 Python — 라우터(한계) · direct_key(시간 보정) · blender(다리 op) · body_fit 이 같이 쓴다.

시간 보정 · 다리 보정 · 선별의 기준값은 운영 Vesper 애니에서 정했다. 치수 차이는 대부분 이미 정규화돼 있다(거리 × scale = 골반 높이 / 100 · 발 좌우 비 =
엉덩 폭 배수 · 파지 허용 = 팔 길이 비). 남는 것 둘:

- 손 속도 기준 — 시간 보정 정점 목표(target_peak_cm_s) · 빠른 구간 매끈화 기준(body_fit.SPEED_REF_CM)은 손목 속도 / scale 인데, FK 리타깃은 회전을 복사하므로
  (E0 2026-11-03: 세 대상의 손 · 아래팔 각속도가 같다) 같은 동작의 이 값은 팔 길이 / scale 에 비례한다. 팔이 상대적으로 긴 몸(Vesper 0.453 · IdaFaber 남성
  0.547 · UE5 Manny 0.574)은 같은 동작이 더 빠르게 잡혀 시간 보정 배율이 달라지고(낫 ×2.0 · ×1.91 · ×1.77) 매끈화 프레임이 는다 → 기준에 몸 비율
  ratio = (팔 / scale)_대상 ÷ (팔 / scale)_기준 몸 을 곱한다. 시험: 낫 배율 ×2.0 · 시간 보정 떨림 8.6 · 9.5 → 3.4 · 2.5(Vesper 3.45), IdaFaber 남성 검 떨림 6.2 → 1.6.
- 스타일 — 얼마나 빠르게 · 넓게 서는지는 치수가 아니라 캐릭터의 값이다. 운영 애니가 없는 대상은 Vesper 값을 몸 비율만 옮겨 쓰고 한계로 알린다.
  운영 애니를 재서 값을 정했으면 정책 style.profiles 에 둔다(환산 대신 그 값).

대상 = 기준 몸(정책 style.reference_skeleton)이면 아무것도 바꾸지 않는다 — 계획 · Job 이 비트 같다.
"""
from __future__ import annotations

from .editor import package_path

STANCE_OP = "stance_width"


def reference(policy: dict | None) -> str | None:
    return package_path(((policy or {}).get("style") or {}).get("reference_skeleton"))


def is_reference(policy: dict | None, skeleton: str) -> bool:
    """대상이 기준 몸인가. 정책에 기준 몸이 없으면(시험 · 옛 정책 파일) 참 — 옮길 기준이 없다."""
    ref = reference(policy)
    return not ref or package_path(skeleton) == ref


def profile(policy: dict | None, skeleton: str) -> dict:
    """대상의 정책 프로필 — 없으면 {}. 기준 몸은 프로필을 읽지 않는다(기준값 그 자체)."""
    if is_reference(policy, skeleton):
        return {}
    profiles = ((policy or {}).get("style") or {}).get("profiles") or {}
    return next((v for k, v in profiles.items() if package_path(k) == package_path(skeleton)), {})


def proportion(bones: dict) -> float | None:
    """팔 길이 / scale — selection_bones 의 arm_dims · leg_dims(둘 다 대상 메시 기준 포즈)."""
    arm = (bones.get("arm_dims") or {}).get("arm_cm")
    pelvis = (bones.get("leg_dims") or {}).get("pelvis_height_cm")
    return arm / (pelvis / 100.0) if arm and pelvis else None


def ratio(bones: dict, reference_bones: dict) -> float | None:
    """(팔 / scale)_대상 ÷ (팔 / scale)_기준 몸 — 못 재면 None(환산하지 않는다)."""
    target, ref = proportion(bones), proportion(reference_bones)
    return target / ref if target and ref else None


def peak(cfg: dict, prof: dict, body_ratio: float | None) -> dict:
    """시간 보정 정점 목표 → {value, from, factor}. from = request(요청 값) · profile(정책) · body_ratio(기준값 × 몸 비율) · default(비율을 못 잼 — 기준값 그대로)."""
    base = cfg["target_peak_cm_s"]
    if cfg.get("target_peak_given"):
        return {"value": base, "from": "request", "factor": None}
    if "timing_target_peak_cm_s" in prof:
        return {"value": float(prof["timing_target_peak_cm_s"]), "from": "profile", "factor": None}
    if body_ratio is None:
        return {"value": base, "from": "default", "factor": None}
    return {"value": round(base * body_ratio, 1), "from": "body_ratio", "factor": round(body_ratio, 4)}


def apply_stance(ops: list[dict], raw_ops: list[dict], prof: dict) -> None:
    """정책 프로필의 발 좌우 비 상한 — 요청이 max_ratio 를 주지 않은 stance_width op 에만. ops = 기본값을 채운 op · raw_ops = 요청 그대로(같은 op 이름으로 맞춘다)."""
    if "stance_max_ratio" not in prof or any(o["op"] == STANCE_OP and "max_ratio" in o for o in raw_ops):
        return
    for op in ops:
        if op["op"] == STANCE_OP:
            op["max_ratio"] = max(float(prof["stance_max_ratio"]), op["min_ratio"])   # fix_ops — min_ratio ≤ max_ratio


def reference_values(request: dict, steps: list[dict], prof: dict) -> list[str]:
    """이 계획이 기준 몸의 스타일 값을 쓰는 자리(요청 · 프로필이 정하지 않은 것) — 한계 TARGET_STYLE_FROM_REFERENCE 의 내용."""
    out = []
    timing = (request.get("fix") or {}).get("timing")
    if timing and not timing.get("target_peak_given") and "timing_target_peak_cm_s" not in prof:
        out.append("fix.timing target_peak_cm_s")
    raw_ops = (request.get("fix") or {}).get("ops") or []
    if any(o["op"] == STANCE_OP and "max_ratio" not in o for o in raw_ops) and "stance_max_ratio" not in prof:
        out.append("stance_width max_ratio")
    if any(s["step"] == "select" for s in steps):
        out.append("select thresholds")
    return out
