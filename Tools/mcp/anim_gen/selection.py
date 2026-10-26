"""후보 선별 점수 (Phase 8-1, 지침서 §14 Phase 8 · §16-9).

retarget 파이프의 select 단계가 후보(seed 별 Kimodo 결과)를 모두 Vesper 로 리타깃하고 validate_animation(profile_positions · body_clearance)로 잰
수치(motion_metrics)를 받아, 지표마다 벌점 pᵢ(0 = 좋음 ~ 1)을 매기고 score = Σ wᵢ·pᵢ / Σ wᵢ 가 가장 낮은 후보를 고른다(동률은 낮은 번호 = seed 순).
순수 Python — 같은 기록(metrics · weights)으로 다시 계산하면 같은 선택이다(Job selection 에 남긴 값으로 재현). 수치 선별은 시각 판정이 아니다
(한계 SELECTED_BY_NUMBERS — 최종 판정은 사람이 Persona 에서).

벌점(E2 · 사용자 판정으로 고친다, 결과 표에 원 수치를 모두 남긴다):
- grip      1 − grip_pct/100 (two_hand_weapon_grip 일 때만)
- stance    clamp((발 좌우 비 p90 − 2.5) / 5.0, 0, 1) — Vesper 엉덩 관절 폭 ≈ 18 cm 라 2.5배 ≈ 45 cm. 기준 시험 Vesper 5.55 → 0.61
            (설계의 폭 2.5 는 E1 실측 Vesper 비 5.55 에서 1.0 으로 포화해 넓은 후보끼리 구별이 안 돼 5.0 으로 정정)
- swing     1 − 정점 / 후보 중 최고 정점(상대 — 절대 임계값을 쓰지 않는 §13 원칙, weapon_action 일 때만)
- attack    max(1 − 궤적 폭 / 후보 중 최고, clamp((1.0 − 궤적 폭) / 1.0)) — 궤적 폭 = 손별 손목 궤적 상자 대각선 / 팔 길이 중 큰 쪽(motion_metrics.attack
            버전 3 — 한손 공격도 무기 손으로 잰다).
            후보끼리의 상대 + 절대 하한(팔 길이 1.0 — 운영 공격 최저 1.46, 기록 Job 의 '서 있기' 0.38) — weapon_action 일 때만
- clearance 보정 전 관통 %/100 (팔 중 큰 쪽). 검 손잡이 파지(요청 간격 없음)면 비파지 프레임 관통 상한(non_grip) — 양손을 가슴 앞에 모으면 아래팔이
            가슴에 닿는 게 정상이라 파지 프레임 관통을 세면 움직임이 작은 후보가 유리해진다(파지 프레임 관통은 8-4 C안 몫). 자루 무기(요청 간격 —
            metrics.grip.spacing_cm)면 전체 관통(all_polearm): 손이 수십 cm 벌어져 있어 모은 손 가정이 없고, 낫 후보의 몸 관통 71 ~ 79 % 를 이 규칙이
            0 으로 뺐다(운영 낫 애니 0 ~ 34 %)
- breakage  검증 FAILED = 후보 제외, NEEDS_REVIEW = 0.5, PASSED_WITH_WARNINGS = 0.5 — 단 경고가 관통 검사(body_clearance)에서만 왔으면 0
            (관통은 clearance 가 센다 — 이중 계산 제거). 근거 = metrics.breakage.scored_warnings(관통 검사 밖 경고). 기록에 없으면 상태대로
- cross     clamp((팔 꼬임 % − 20) / 50) (two_hand_weapon_grip 일 때만 — 한손 공격 · 팔짱은 원래 교차한다) — motion_metrics.arm_cross crossed_pct
            (손목이 손 폭 10 cm × scale 넘게 엇갈린 프레임). 운영 낫 애니 0 ~ 16.3 % → 0, 망가진 낫 후보 12.5 ~ 91.7 %
- head      clamp((손-머리 근접 % − 5) / 25) (모든 동작) — motion_metrics.head_near near_pct(손 점이 머리 본 10 cm × scale 안). 운영 낫 0 % → 0,
            망가진 낫 후보 41.7 ~ 90 % → 1

개정 이력: 2026-10-26 Persona 소견 ② '공격 자세가 맞나' — 기록 Job c49a83 이 '양손 모아 서 있기'(seed 26, 궤적 폭 0.38)를 골랐다. 원인 = 관통
이중 계산 · 파지 프레임 관통 벌점 · 공격다움 지표 없음 → attack 추가 · 파지면 비파지 관통 · 깨짐에서 관통 경고 제외(같은 수치로 seed 25).
2026-10-26 밤 낫 Persona '팔 꼬임 · 머리 관통 · 배 관통' — 기록 Job ad275a 가 손이 뒤바뀌고(85 ~ 93 %) 머리에 박힌(42 ~ 90 %) 후보를 PASS 로 골랐다.
원인 = 파지 목표 축(refine) · 자루 무기에도 비파지 관통만 셈 · 꼬임 · 머리 지표 없음 → 자루 무기는 전체 관통 · cross · head 추가.
"""
from __future__ import annotations

from . import motion_metrics as mm

METRIC_VERSION = mm.VERSION
WEIGHTS = {"grip": 3.0, "stance": 2.0, "swing": 2.0, "attack": 2.0, "clearance": 1.0, "breakage": 1.0, "cross": 2.0, "head": 2.0}
THRESHOLDS = {"grip_cm": mm.GRIP_CM, "grip_tolerance_cm": mm.GRIP_TOL_CM, "stance_ratio_base": 2.5, "stance_ratio_span": 5.0, "attack_width_floor": 1.0, "warnings_penalty": 0.5,
              "grip_reached_pct": 80.0, "cross_cm": mm.CROSS_CM, "cross_pct_base": 20.0, "cross_pct_span": 50.0,
              "head_near_cm": mm.HEAD_NEAR_CM, "head_pct_base": 5.0, "head_pct_span": 25.0}
_STATUS = {"PASSED": 0.0, "PASSED_WITH_WARNINGS": THRESHOLDS["warnings_penalty"], "NEEDS_REVIEW": THRESHOLDS["warnings_penalty"]}


class WeightError(ValueError):
    pass


def check_weights(raw) -> dict:
    """generation.select.weights — 키는 WEIGHTS 의 8개만, 값은 0 이상의 수. 빠진 키는 기본값."""
    if raw is None:
        return dict(WEIGHTS)
    if not isinstance(raw, dict):
        raise WeightError("must be an object {" + ", ".join(WEIGHTS) + "}")
    extra = sorted(set(raw) - set(WEIGHTS))
    if extra:
        raise WeightError(f"unknown key(s) {extra} — allowed {sorted(WEIGHTS)}")
    for k, v in raw.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise WeightError(f"{k} must be a number ≥ 0")
    return {**WEIGHTS, **{k: float(v) for k, v in raw.items()}}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def clearance_pct(metrics: dict, grip_on: bool) -> tuple[float | None, str | None]:
    """관통 벌점에 쓰는 % 와 근거 — 검 손잡이 파지(요청 간격 없음)면 비파지 프레임 관통 상한(손목 트랙이 없어 못 재면 전체), 자루 무기(측정이 쓴 요청
    간격 metrics.grip.spacing_cm — 같은 기록으로 다시 계산해도 같다)면 전체(all_polearm), 파지 플래그가 없으면 전체(보정 전) 관통."""
    pen = (metrics.get("clearance") or {}).get("penetration_pct")
    if grip_on:
        if (metrics.get("grip") or {}).get("spacing_cm"):
            return pen, None if pen is None else "all_polearm"
        upper = (metrics.get("non_grip") or {}).get("non_grip_penetration_pct_max")
        if upper is not None:
            return upper, "non_grip"
    return pen, None if pen is None else "all"


def breakage(metrics: dict, status: str) -> float | None:
    """깨짐 벌점 — 관통 검사(body_clearance)에서만 온 경고는 세지 않는다(clearance 가 센다). scored_warnings 가 기록에 없으면 상태대로."""
    base = _STATUS.get(status)
    scored = (metrics.get("breakage") or {}).get("scored_warnings")
    if status == "PASSED_WITH_WARNINGS" and scored is not None and not scored:
        return 0.0
    return base


def penalties(metrics: dict, status: str, *, best_swing: float | None, grip_on: bool, swing_on: bool, best_width: float | None = None) -> dict:
    """한 후보의 벌점 — 켜지지 않은 지표 · 값이 없는 지표(기록에 없는 옛 버전 포함)는 None(점수에서 빠진다)."""
    out = {"grip": None, "stance": None, "swing": None, "attack": None, "clearance": None, "breakage": breakage(metrics, status), "cross": None, "head": None}
    grip = metrics.get("grip") or {}
    if grip_on and grip.get("grip_pct") is not None:
        out["grip"] = round(1.0 - grip["grip_pct"] / 100.0, 4)
    p90 = ((metrics.get("stance") or {}).get("lateral_ratio") or {}).get("p90")
    if p90 is not None:
        out["stance"] = round(_clamp((p90 - THRESHOLDS["stance_ratio_base"]) / THRESHOLDS["stance_ratio_span"]), 4)
    peak = (metrics.get("swing") or {}).get("peak_cm_s")
    if swing_on and peak is not None and best_swing:
        out["swing"] = round(_clamp(1.0 - peak / best_swing), 4)
    width = (metrics.get("attack") or {}).get("width_arm_ratio")
    if swing_on and width is not None:
        floor = THRESHOLDS["attack_width_floor"]
        relative = _clamp(1.0 - width / best_width) if best_width else 0.0
        out["attack"] = round(max(relative, _clamp((floor - width) / floor)), 4)
    pen, _ = clearance_pct(metrics, grip_on)
    if pen is not None:
        out["clearance"] = round(_clamp(pen / 100.0), 4)
    crossed = (metrics.get("cross") or {}).get("crossed_pct")
    if grip_on and crossed is not None:
        out["cross"] = round(_clamp((crossed - THRESHOLDS["cross_pct_base"]) / THRESHOLDS["cross_pct_span"]), 4)
    near = (metrics.get("head") or {}).get("near_pct")
    if near is not None:
        out["head"] = round(_clamp((near - THRESHOLDS["head_pct_base"]) / THRESHOLDS["head_pct_span"]), 4)
    return out


def score(pen: dict, weights: dict) -> float:
    used = [(weights[k], v) for k, v in pen.items() if v is not None and weights.get(k, 0) > 0]
    total = sum(w for w, _ in used)
    return round(sum(w * v for w, v in used) / total, 4) if total else 0.0


def rank(candidates: list[dict], weights: dict | None = None, *, grip_on: bool, swing_on: bool) -> dict:
    """candidates[{index, seed, status, metrics{grip, stance, swing, clearance}, …}] → 각 후보에 penalties · score · rank(1 = 고름) · excluded,
    picked{index, seed, score, reason}. FAILED 는 제외, 전부 FAILED 면 picked None."""
    weights = check_weights(weights)
    usable = [c for c in candidates if c.get("status") != "FAILED"]
    peaks = [(c["metrics"].get("swing") or {}).get("peak_cm_s") for c in usable]
    best_swing = max((p for p in peaks if p is not None), default=None)
    widths = [(c["metrics"].get("attack") or {}).get("width_arm_ratio") for c in usable]
    best_width = max((w for w in widths if w is not None), default=None)
    out = []
    for c in candidates:
        entry = dict(c)
        if c.get("status") == "FAILED":
            entry.update(penalties=None, score=None, rank=None, excluded={"reason": "VALIDATION_FAILED"})
        else:
            pen = penalties(c["metrics"], c.get("status", "PASSED"), best_swing=best_swing, grip_on=grip_on, swing_on=swing_on, best_width=best_width)
            entry.update(penalties=pen, score=score(pen, weights), excluded=None, clearance_basis=clearance_pct(c["metrics"], grip_on)[1])
        out.append(entry)
    order = sorted((e for e in out if e["score"] is not None), key=lambda e: (e["score"], e["index"]))
    for r, e in enumerate(order, 1):
        e["rank"] = r
    picked = None
    if order:
        top = order[0]
        picked = {"index": top["index"], "seed": top.get("seed"), "score": top["score"], "reason": _reason(top, order[1] if len(order) > 1 else None, weights)}
    return {"metric_version": METRIC_VERSION, "weights": weights, "thresholds": dict(THRESHOLDS), "grip_on": grip_on, "swing_on": swing_on,
            "best_swing_cm_s": best_swing, "best_width_arm_ratio": best_width, "candidates": out, "picked": picked}


def _reason(top: dict, second: dict | None, weights: dict) -> str:
    """한 줄 — 고른 후보의 지표별 기여(w·p)와, 2위가 있으면 가장 크게 앞선 지표."""
    contrib = sorted(((k, weights[k] * v) for k, v in top["penalties"].items() if v is not None and weights.get(k, 0) > 0), key=lambda kv: -kv[1])
    parts = " · ".join(f"{k} {v:.2f}" for k, v in contrib) or "no active metric"
    if second is None:
        return f"only candidate — score {top['score']:.3f} ({parts})"
    gains = sorted(((k, weights[k] * ((second["penalties"].get(k) or 0) - (v or 0))) for k, v in top["penalties"].items()
                    if weights.get(k, 0) > 0 and (v is not None or second["penalties"].get(k) is not None)), key=lambda kv: -kv[1])
    lead = ", ".join(f"{k} {g:+.2f}" for k, g in gains[:2] if g > 0) or "tie broken by index"
    return f"score {top['score']:.3f} vs #{second['index']} {second['score']:.3f} — ahead on {lead} (weighted: {parts})"
