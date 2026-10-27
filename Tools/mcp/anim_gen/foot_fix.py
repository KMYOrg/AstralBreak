"""다리 보정 — 발 간격 좁히기(stance_width) · 발 고정(foot_lock)의 발목 목표 (Phase 8-3, fix_ops 의 다리 풀이).

순수 Python(pytest 대상). Blender 스크립트(blender/fix_legs.py)가 프레임별 엉덩 관절 · 발목 위치와 접지(motion_metrics.detect_contacts)를 넘기고, 여기서 받은
발목 목표로 2본 IK(local_ai.refine.two_bone — 팔 파지와 같은 함수, 원래 무릎 굽힘 평면 유지)를 푼다. 좌표는 cm, up = 위 축 번호.

- 간격: 프레임마다 두 발의 엉덩 축 성분 |d| 가 상한을 넘는 만큼 두 발을 반씩 안쪽으로(엉덩 축 방향). 그 오프셋을 **발마다 접지 구간 평균으로 상수**로
  만들고(디딘 발이 미끄러지지 않게) 공중 구간은 smoothstep 으로 앞뒤 접지의 오프셋을 잇는다 → 상수로 만들면서 모자라는 만큼을 전역 배율(이분 탐색)로
  채워 두 발을 디딘 프레임의 최대 간격이 상한 + 0.5 cm 안에 들게 한다. 오프셋 크기는 max_shift_cm 로 자른다.
- 고정: 접지 구간마다 발목을 한 점(수평 = 구간에서 가장 느린 프레임의 위치 + 오프셋, 높이 = 구간 중앙값)에, 구간 앞뒤 blend_frames 는 smoothstep 블렌드.
- 무릎 굽힘 유지(stance_width keep_knee_bend — 8-3 후속): 골반 높이 그대로 발을 모으면 엉덩 → 발목 거리가 줄어 무릎이 더 굽는다 → 그 거리를 원래대로
  돌리는 만큼 골반(엉덩 관절)을 올린다(pelvis_raise). 발목 목표는 그대로라 디딘 발은 고정된 채다.
"""
from __future__ import annotations

import math

from . import motion_metrics as mm

TOL_CM = 0.5          # 간격 상한 여유
MAX_MULTIPLIER = 4.0  # 접지 평균으로 깎인 만큼 채우는 배율의 상한
EPS_CM = 1e-3         # 이보다 작게 움직인 목표는 '안 바뀜'(그 프레임은 IK 를 풀지 않는다 — 원래 키 그대로)
RAISE_SIGMA_FRAMES = 2.0   # 골반 상승 스무딩 — 상체 전체가 따라 움직이므로 프레임 사이 들썩임이 없게


def smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def _hunit(a, b, up: int) -> list[float]:
    """a − b 의 수평 단위 벡터(3 성분, 위 성분 0)."""
    v = [a[i] - b[i] if i != up else 0.0 for i in range(3)]
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-9 else [0.0, 0.0, 0.0]


def _lateral(fl, fr, u) -> float:
    return sum((fl[i] - fr[i]) * u[i] for i in range(3))


def base_offsets(ankle: dict, hip: dict, up: int, cap_cm: float) -> dict:
    """프레임별 '상한까지 줄이는' 오프셋 {left, right}(수평 벡터) — 넘친 만큼의 반씩 두 발을 안쪽으로."""
    out = {"left": [], "right": []}
    for fl, fr, hl, hr in zip(ankle["left"], ankle["right"], hip["left"], hip["right"]):
        u = _hunit(hl, hr, up)
        d = _lateral(fl, fr, u)
        excess = max(0.0, abs(d) - cap_cm)
        s = (1.0 if d >= 0 else -1.0) * excess / 2.0
        out["left"].append([-s * c for c in u])
        out["right"].append([s * c for c in u])
    return out


def piecewise(per_frame: list[list[float]], contact_runs: list[tuple[int, int]], blend_frames: int) -> list[list[float]]:
    """접지 구간마다 평균(상수), 구간 사이는 smoothstep 으로 잇고, 처음 · 끝 앞뒤는 가까운 구간 값. 접지가 없으면 프레임별 값을 blend_frames 가우시안으로."""
    n = len(per_frame)
    if not contact_runs:
        from .local_ai import refine
        return [list(v) for v in refine.smooth_series(per_frame, max(1.0, blend_frames / 2.0))] if n else []
    means = [[sum(per_frame[f][i] for f in range(a, b + 1)) / (b - a + 1) for i in range(3)] for a, b in contact_runs]
    out: list = [None] * n
    for (a, b), m in zip(contact_runs, means):
        for f in range(a, b + 1):
            out[f] = list(m)
    first, last = contact_runs[0], contact_runs[-1]
    for f in range(0, first[0]):
        out[f] = list(means[0])
    for f in range(last[1] + 1, n):
        out[f] = list(means[-1])
    for k in range(len(contact_runs) - 1):
        a = contact_runs[k][1]
        b = contact_runs[k + 1][0]
        for f in range(a + 1, b):
            w = smoothstep((f - a) / (b - a))
            out[f] = [means[k][i] + (means[k + 1][i] - means[k][i]) * w for i in range(3)]
    return out


def _clamp(v: list[float], limit: float) -> list[float]:
    n = math.sqrt(sum(c * c for c in v))
    return [c * limit / n for c in v] if n > limit else v


def _planted_max(ankle: dict, hip: dict, off: dict, up: int, frames: list[int]) -> tuple[float, float]:
    vals = []
    for f in frames:
        u = _hunit(hip["left"][f], hip["right"][f], up)
        fl = [ankle["left"][f][i] + off["left"][f][i] for i in range(3)]
        fr = [ankle["right"][f][i] + off["right"][f][i] for i in range(3)]
        vals.append(abs(_lateral(fl, fr, u)))
    return (max(vals), min(vals)) if vals else (0.0, 0.0)


def stance(ankle: dict, hip: dict, contacts: dict, up: int, cap_cm: float, min_cm: float, max_shift_cm: float, blend_frames: int) -> dict:
    """간격 오프셋 {left, right}[F] + 배율 · 두 발 디딘 프레임의 최대 · 최소 간격(전 → 후)."""
    n = len(ankle["left"])
    runs = {s: mm.runs(contacts[s]) for s in ("left", "right")}
    planted = [f for f in range(n) if contacts["left"][f] and contacts["right"][f]] or list(range(n))
    base = base_offsets(ankle, hip, up, cap_cm)
    zero = {s: [[0.0, 0.0, 0.0]] * n for s in ("left", "right")}
    before_max, before_min = _planted_max(ankle, hip, zero, up, planted)

    def build(m: float) -> dict:
        return {s: [_clamp(v, max_shift_cm) for v in piecewise([[c * m for c in v] for v in base[s]], runs[s], blend_frames)] for s in ("left", "right")}

    def ok(off: dict) -> bool:
        return _planted_max(ankle, hip, off, up, planted)[0] <= cap_cm + TOL_CM

    m, off = 1.0, build(1.0)
    if before_max > cap_cm + TOL_CM and not ok(off):
        lo, hi = 1.0, MAX_MULTIPLIER
        best = build(hi)
        if ok(best):
            for _ in range(16):
                mid = (lo + hi) / 2.0
                cand = build(mid)
                if ok(cand):
                    hi, best = mid, cand
                else:
                    lo = mid
            m, off = hi, best
        else:
            m, off = hi, best
    after_max, after_min = _planted_max(ankle, hip, off, up, planted)
    if after_min < min_cm - TOL_CM:
        # 너무 좁혔다(무릎이 부딪힌다) — 최소 간격을 지키는 데까지 배율을 내린다
        lo, hi = 0.0, m
        for _ in range(16):
            mid = (lo + hi) / 2.0
            cand = build(mid)
            if _planted_max(ankle, hip, cand, up, planted)[1] >= min_cm - TOL_CM:
                lo, off = mid, cand
            else:
                hi = mid
        m = lo
        after_max, after_min = _planted_max(ankle, hip, off, up, planted)
    shift = max(math.sqrt(sum(c * c for c in v)) for s in ("left", "right") for v in off[s]) if n else 0.0
    return {"offsets": off, "multiplier": round(m, 4), "planted_frames": len(planted), "cap_cm": round(cap_cm, 2), "min_cm": round(min_cm, 2),
            "planted_max_cm": {"before": round(before_max, 2), "after": round(after_max, 2)},
            "planted_min_cm": {"before": round(before_min, 2), "after": round(after_min, 2)}, "max_shift_cm": round(shift, 2),
            "reached": after_max <= cap_cm + TOL_CM}


def lock(ankle: list, free: list, contact_runs: list[tuple[int, int]], up: int, blend_frames: int) -> tuple[list, list[dict]]:
    """접지 구간마다 한 점 고정(+ 앞뒤 블렌드) — (목표[F], 고정 기록[{run, frame, at}])."""
    n = len(ankle)
    weight = [0.0] * n
    pin_at: list = [None] * n
    pins = []
    for a, b in contact_runs:
        def hspeed(f):
            g = f + 1 if f + 1 <= b else f - 1
            if g < a or g == f:
                return 0.0
            return math.sqrt(sum((ankle[g][i] - ankle[f][i]) ** 2 for i in range(3) if i != up))
        k = min(range(a, b + 1), key=hspeed)
        zs = sorted(ankle[f][up] for f in range(a, b + 1))
        at = list(free[k])
        at[up] = zs[len(zs) // 2] + (free[k][up] - ankle[k][up])
        pins.append({"run": [a, b], "frame": k, "at": [round(c, 3) for c in at]})
        for f in range(max(0, a - blend_frames), min(n, b + blend_frames + 1)):
            if a <= f <= b:
                w = 1.0
            elif f < a:
                w = smoothstep((f - (a - blend_frames - 1)) / (blend_frames + 1))
            else:
                w = smoothstep(((b + blend_frames + 1) - f) / (blend_frames + 1))
            if w > weight[f]:
                weight[f], pin_at[f] = w, at
    targets = [[free[f][i] + (pin_at[f][i] - free[f][i]) * weight[f] for i in range(3)] if pin_at[f] else list(free[f]) for f in range(n)]
    return targets, pins


def target_model(source_pelvis_rest: list[float], up: int, target: dict | None, axes=(1.0, 1.0, 1.0)) -> dict | None:
    """대상 모델 — 리타기터가 하는 일을 소스 공간에서 다시 계산한다(PelvisMotionOp.cpp DecodePose · FKChainsOp — per_bone 정렬):
    대상 골반 위치 = s · 소스 골반 위치(s = 대상 / 소스 골반 초기 높이), 회전 = 소스 골반 회전 변화 · 대상 초기 회전 → 대상 엉덩 관절 = s · P_s(f) +
    Δ(f) · (대상 엉덩 관절 − 대상 골반)(초기 포즈), 다리 뼈는 소스 방향 그대로 대상 길이(8-1 손목 간격 실측 — 프레임별 0.2 cm).
    target = 대상 leg_dims + rest{pelvis, hip_l, hip_r}(UE 기준 포즈 cm), axes = UE → 이 공간 축 부호(Blender = (1, −1, 1)). 없으면 None(소스 공간)."""
    rest = (target or {}).get("rest") or {}
    if not (target and target.get("thigh_cm") and target.get("shin_cm") and rest.get("pelvis") and rest.get("hip_l") and rest.get("hip_r")):
        return None
    if source_pelvis_rest[up] <= 1.0:
        return None
    conv = lambda p: [p[i] * axes[i] for i in range(3)]  # noqa: E731
    pelvis = conv(rest["pelvis"])
    s = pelvis[up] / source_pelvis_rest[up]
    return {"space": "target_model", "scale": round(s, 5), "thigh_cm": target["thigh_cm"], "shin_cm": target["shin_cm"],
            "hip_width_cm": target["hip_width_cm"], "hip_offset": {"left": [a - b for a, b in zip(conv(rest["hip_l"]), pelvis)],
                                                                   "right": [a - b for a, b in zip(conv(rest["hip_r"]), pelvis)]}}


def predict_hip(model: dict, side: str, pelvis_pos: list[float], delta) -> list[float]:
    """대상 엉덩 관절 = s · 소스 골반 위치 + Δ · 대상 엉덩 오프셋(Δ = 소스 골반 회전 변화 3×3)."""
    from .local_ai import refine as kr
    off = kr._mv(delta, model["hip_offset"][side])
    return [model["scale"] * pelvis_pos[i] + off[i] for i in range(3)]


def target_leg(hip_t, hip, knee, ankle, model: dict) -> tuple[list[float], list[float]]:
    """대상 무릎 · 발목 — 대상 엉덩 관절에서 소스 뼈 방향 · 대상 길이."""
    d1 = [knee[i] - hip[i] for i in range(3)]
    d2 = [ankle[i] - knee[i] for i in range(3)]
    n1, n2 = math.sqrt(sum(c * c for c in d1)) or 1.0, math.sqrt(sum(c * c for c in d2)) or 1.0
    k = [hip_t[i] + d1[i] * model["thigh_cm"] / n1 for i in range(3)]
    return k, [k[i] + d2[i] * model["shin_cm"] / n2 for i in range(3)]


def swing_two_bone(hip, knee, ankle, r_thigh, r_shin, target) -> dict:
    """다리 2본 IK — 먼저 다리 전체를 엉덩 관절 둘레로 '엉덩 → 발목' 방향이 목표 방향이 되게 최소 회전(무릎 굽힘 평면도 같이 돈다), 그다음 길이만
    맞춘다(refine.two_bone). 원래 굽힘 평면을 그대로 두면 발을 안으로 모을 때 무릎이 밖으로 빠진다(Blender 스파이크 — 무릎 간격 57.7 → 60.0 cm 로
    벌어짐). 결과 모양은 refine.two_bone 과 같다(r_arm = 넓적다리, r_fore = 정강이 전역 회전)."""
    from .local_ai import refine as kr
    q = kr.rotation_between([ankle[i] - hip[i] for i in range(3)], [target[i] - hip[i] for i in range(3)])
    knee2 = [hip[i] + kr._mv(q, [knee[k] - hip[k] for k in range(3)])[i] for i in range(3)]
    ankle2 = [hip[i] + kr._mv(q, [ankle[k] - hip[k] for k in range(3)])[i] for i in range(3)]
    return kr.two_bone(hip, knee2, ankle2, kr._mm(q, r_thigh), kr._mm(q, r_shin), target)


def pelvis_raise(hip: dict, ankle_before: dict, ankle_after: dict, up: int, sigma_frames: float = RAISE_SIGMA_FRAMES) -> dict:
    """keep_knee_bend — 프레임별 골반 상승(위 축, 풀이 공간 cm). 다리마다 엉덩 → 발목 거리를 보정 전과 같게 하는 상승 = √(max(D0² − H'², 0)) − V'
    (D0 = 보정 전 거리, H' · V' = 보정 뒤 발목 목표까지 수평 · 수직 거리) — 2본 IK 의 무릎 굽힘은 이 거리로만 정해진다. 두 다리 중 작은 쪽(어느 다리도
    원래보다 펴지지 않는다 — IK 늘어남 0 유지 · 사용자 결정 2026-10-27), 0 미만은 0 → σ 프레임 가우시안 → 다시 프레임별 상한으로.
    → {dz[F], p50, max, frames(> 0.05 cm)}.
    한계(8-3 후속 실측): 원래 굽힘을 되돌리면 원본이 거의 펴던 자리(검 선택 0.5초 — 11°)에서 다리가 다시 펴지고, 그 자세의 무릎은 간격 · 고정
    블렌드가 공중 발 경로에 만드는 엉덩 → 발목 거리 꺾임에 민감해 무릎 떨림이 커진다(1.32 → 1.89). 블렌드 길이 · 공중 보정량 스무딩 · C2 블렌드 ·
    최소 굽힘 상한은 줄이지 못했다 — 공중 발 경로를 디딤 사이에서 다시 짜는 것은 8-4(대상 쪽 풀이 — 지침서 §14 8-4 ③)."""
    from .local_ai import refine
    n = len(hip["left"])
    need = {}
    for side in ("left", "right"):
        vals = []
        for f in range(n):
            h, a0, a1 = hip[side][f], ankle_before[side][f], ankle_after[side][f]
            d0 = math.sqrt(sum((h[i] - a0[i]) ** 2 for i in range(3)))
            dh = math.sqrt(sum((h[i] - a1[i]) ** 2 for i in range(3) if i != up))
            vals.append(math.sqrt(max(d0 * d0 - dh * dh, 0.0)) - (h[up] - a1[up]))
        need[side] = vals
    cap = [max(0.0, min(need["left"][f], need["right"][f])) for f in range(n)]
    smooth = [v[0] for v in refine.smooth_series([[c] for c in cap], sigma_frames)] if n and sigma_frames > 0 else list(cap)
    dz = [max(0.0, min(s, c)) for s, c in zip(smooth, cap)]
    return {"dz": dz, "p50": round(mm.percentile(dz, 0.5), 2) if dz else 0.0, "max": round(max(dz), 2) if dz else 0.0,
            "frames": sum(d > 0.05 for d in dz)}


def raised(hip: dict, dz: list[float], up: int) -> dict:
    """엉덩 관절 트랙을 프레임별 dz 만큼 위로(골반 상승을 따라 — 상체 · 엉덩 관절이 같이 오른다)."""
    return {side: [[p[i] + (dz[f] if i == up else 0.0) for i in range(3)] for f, p in enumerate(track)] for side, track in hip.items()}


def solve(ankle: dict, hip: dict, contacts: dict, *, up: int, stance_cfg: dict | None = None, lock_cfg: dict | None = None) -> dict:
    """다리 풀이 한 번 — 발목 목표 {left, right}[F] · 바뀐 프레임 · 간격 · 고정 기록 · 골반 상승(keep_knee_bend).
    stance_cfg = {cap_cm, min_cm, max_shift_cm, blend_frames, keep_knee_bend?}(풀이 공간 cm), lock_cfg = {feet, blend_frames}.
    골반을 올리면 그 프레임은 발목 목표가 그대로여도 IK 를 다시 푼다(changed) — 엉덩이 올라간 만큼 다리를 펴야 발이 바닥에 남는다."""
    n = len(ankle["left"])
    out = {"stance": None, "pins": {}, "targets": {}, "changed": {}, "pelvis_raise": None}
    off = {s: [[0.0, 0.0, 0.0]] * n for s in ("left", "right")}
    if stance_cfg:
        st = stance(ankle, hip, contacts, up, stance_cfg["cap_cm"], stance_cfg["min_cm"], stance_cfg["max_shift_cm"], stance_cfg["blend_frames"])
        off = st.pop("offsets")
        out["stance"] = st
    for side in ("left", "right"):
        free = [[ankle[side][f][i] + off[side][f][i] for i in range(3)] for f in range(n)]
        if lock_cfg and side in lock_cfg["feet"]:
            free, out["pins"][side] = lock(ankle[side], free, mm.runs(contacts[side]), up, lock_cfg["blend_frames"])
        out["targets"][side] = free
        out["changed"][side] = [math.sqrt(sum((free[f][i] - ankle[side][f][i]) ** 2 for i in range(3))) > EPS_CM for f in range(n)]
    if stance_cfg and stance_cfg.get("keep_knee_bend"):
        out["pelvis_raise"] = pelvis_raise(hip, ankle, out["targets"], up)
        dz = out["pelvis_raise"]["dz"]
        for side in ("left", "right"):
            out["changed"][side] = [c or dz[f] > EPS_CM for f, c in enumerate(out["changed"][side])]
    return out
