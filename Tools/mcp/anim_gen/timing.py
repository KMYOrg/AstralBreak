"""흐느적 보정 — 휘두름 구간 탐지 · 가속(time_warp) · 정지 머리 / 꼬리 트림(trim) op 만들기 (Phase 8-3, 지침서 §14 Phase 8 '8-3').

신호는 대상 시퀀스의 validate_animation profile 이다 — speed_cm_s[본][k] = 프레임 F−1 → F 구간의 선속도(cm/s), times[k] = 구간 끝 시각
(AnimMcpAnimValidator.cpp ProfileJson — 241 프레임 넘으면 여러 프레임을 묶은 최대값). 계산은 정수 프레임으로 하고, op 는 C++ 편집 op
(apply_animation_edits trim · time_warp — AnimMcpAnimEditOps.cpp)만 쓴다. 순수 Python(pytest 대상) — 계획(기존 애셋 미리보기)과 실행이 같이 쓴다.

규칙 (E0 — 2026-10-27, 운영 Vesper 낫 공격 5개 · 8-1 시험 대상 4개 실측):
- 휘두름 신호 s = 두 손목 속도 중 큰 쪽 / pelvis scale, σ 1 표본 가우시안(local_ai.refine.gaussian_kernel — 탐지에만). 정점 P = max s.
  시험 대상 정점 312 ~ 615 cm/s, 운영 낫 공격 1,098 ~ 1,821.
- 핵심 C = s ≥ core_ratio·P 인 첫 표본 ~ 마지막 표본(여러 번 베기도 하나로 — 그 사이도 공격이다).
- 휘두름 W = C 를 s ≥ edge_ratio·P 동안 넓힌 뒤 s 가 계속 줄어드는 쪽으로 국소 최소까지 — 경계는 손이 가장 느린 프레임(속도 단차 = 이음매가 작다).
- 정지 = 전신 속도(측정 역할 본 전부의 최대 / scale) < still.speed_cm_s(30 — 검 시험 대상은 1.6 ~ 2.0 초 뒤 내내 < 30, 운영 공격은 정지 꼬리 0).
  처음부터 이어지는 정지(머리 — 낫 시험 대상 0 ~ 0.9 초 < 10 cm/s)와 끝까지 이어지는 정지(꼬리 — 검 2.0 ~ 2.3 초)가 min_s 이상이면 keep 만 남긴다
  (사용자 결정 2026-10-27: 머리도 기본으로 자른다 — 0.2 초 남김). 휘두름 시작 · 끝을 넘어 자르지 않는다.
- 복귀 R = [W 끝, 꼬리 시작](꼬리가 없으면 클립 끝까지 — 낫은 끝까지 40 ~ 80 cm/s 로 천천히 돌아온다).
배율 곡선(원 프레임 → 재생 배율, 매듭 사이는 출력 시각에 선형 — 속도 단차 없음, 8-3 후속 2026-10-27): 머리 컷 ~ W 시작 1 · W 시작 ~ C 시작 1 → r ·
C r(= clamp(target_peak / P, 1, max_rate)) · C 끝 ~ W 끝 r → recovery_rate(복귀가 없으면 1) · R recovery_rate · 남긴 꼬리 recovery_rate → 1.
매듭 사이 출력 길이 = 원 길이 / 두 끝 배율의 평균이고 Hermite 기울기 = 매듭 배율이라 C++ time_warp 의 사상이 정확히 그 선형 램프다. 전체 새 길이는
정수 프레임으로(출력 시각을 고르게 늘이거나 줄인다 — 반 프레임 안). op = trim(머리 · 꼬리 하나) → time_warp(자른 타임라인 기준) 두 개.
처음 판(구간 등속 retime 조각 · 계단 램프)은 조각 경계마다 속도 단차가 있었다 — 떨림(motion_metrics.zigzag) 최댓값의 원인은 아니었고(경계가 아니라
원본의 빠른 꺾임을 2배로 접은 것 — 공유 노트 phase8-3-followup-design.md §0), 그것은 time_warp antialias(빠를수록 시간 저역 통과)가 줄인다.
"""
from __future__ import annotations

import copy
import math

from . import motion_metrics as mm
from .local_ai import refine

VERSION = 2
DEFAULTS = {
    "mode": "auto",
    "target_peak_cm_s": 1200.0,   # 운영 Vesper 낫 공격 정점 최저(Attack2 1,098 · Attack1 · 3 1,817 · 1,821 — E0) 근처
    "max_rate": 2.0,              # 핵심 구간 가속 상한 — 그 이상은 준비 동작까지 뭉개진다(사용자 판정으로 바꾼다)
    "recovery_rate": 1.5,         # 휘두름 뒤 복귀(자세로 돌아오기)
    # time_warp antialias — σ = c·√(배율² − 1) 원 프레임 가우시안. 설계 때 위치 공간 흉내는 c 0.7 을 골랐지만(사용자 결정 2026-10-27), C++ 실측
    # (로컬 회전을 거른다 — 시험 대상 4건)은 c 0.7 이 떨림 8.8 / 7.4 / 24.3 / 12.8 → 5.2 / 6.3 / 21.0 / 10.3 으로 기준(균일 r 배 기대값 × 0.8)을 3건
    # 넘겼고, c 1.0 이 3.8 / 2.3 / 3.4 / 2.6 · 정점 ×1.67 ~ 1.78(c 0 대비 −8 ~ −10% — 설계 때 c 0.7 로 보인 손실 범위 안) → 1.0(사용자 확정 2026-10-27). 0 = 끔
    "antialias": 1.0,
    "swing": {"core_ratio": 0.5, "edge_ratio": 0.2},
    "still": {"speed_cm_s": 30.0, "min_s": 0.3, "trim_head": True, "keep_head_s": 0.2, "trim_tail": True, "keep_tail_s": 0.3},
}
MIN_PEAK_CM_S = 50.0   # 이보다 느리면 휘두름이 없다(대기 · 서 있기 — 운영 Rifle Idle 정점 26)
MIN_RATE = 1.05        # 이보다 덜 빠르게 하는 가속은 내지 않는다
MAX_ANTIALIAS = 1.5    # C++ MaxTimeWarpAntiAlias 와 같다
ROUND = 4
KNOT_ROUND = 6         # time_warp 매듭(초) — 반올림이 Hermite 할선을 흔들지 않게


class TimingError(ValueError):
    pass


def normalize(raw) -> dict | None:
    """요청 fix.timing — true · {} · 부분 객체 → 기본값을 채운 객체, mode off · false · None → None. 범위를 벗어나면 TimingError(필드, 이유)."""
    if raw is None or raw is False:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raise TimingError("fix.timing", "must be true or an object")
    out = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key not in out:
            raise TimingError(f"fix.timing.{key}", f"unknown key — allowed {sorted(out)}")
        if isinstance(out[key], dict):
            if not isinstance(value, dict):
                raise TimingError(f"fix.timing.{key}", "must be an object")
            extra = sorted(set(value) - set(out[key]))
            if extra:
                raise TimingError(f"fix.timing.{key}.{extra[0]}", f"unknown key — allowed {sorted(out[key])}")
            out[key].update(value)
        else:
            out[key] = value
    if out["mode"] not in ("auto", "off"):
        raise TimingError("fix.timing.mode", "must be auto | off")
    if out["mode"] == "off":
        return None
    _range(out, "target_peak_cm_s", MIN_PEAK_CM_S, 5000.0)
    _range(out, "max_rate", 1.0, 4.0)
    _range(out, "recovery_rate", 1.0, 4.0)
    _range(out, "antialias", 0.0, MAX_ANTIALIAS)
    sw, st = out["swing"], out["still"]
    _range(sw, "core_ratio", 0.05, 0.95, "swing.")
    _range(sw, "edge_ratio", 0.01, sw["core_ratio"], "swing.")
    _range(st, "speed_cm_s", 1.0, 300.0, "still.")
    _range(st, "min_s", 0.0, 10.0, "still.")
    _range(st, "keep_head_s", 0.0, 2.0, "still.")
    _range(st, "keep_tail_s", 0.0, 2.0, "still.")
    for key in ("trim_head", "trim_tail"):
        if not isinstance(st[key], bool):
            raise TimingError(f"fix.timing.still.{key}", "must be a boolean")
    return out


def _range(obj: dict, key: str, lo: float, hi: float, prefix: str = "") -> None:
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise TimingError(f"fix.timing.{prefix}{key}", f"must be a number in [{lo:g}, {hi:g}] (got {value!r})")
    obj[key] = float(value)


def _smooth(values: list[float]) -> list[float]:
    return [v[0] for v in refine.smooth_series([[x] for x in values], 1.0)]


def signals(profile: dict, hands: tuple[str, str], body: list[str], scale: float, fps: float) -> dict:
    """validate_animation profile → 표본별 {span[k] = (프레임 시작, 끝)}, 휘두름 신호(스무딩) · 손 원 신호 · 전신 신호(cm/s ÷ scale)."""
    times = profile.get("times") or []
    speeds = profile.get("speed_cm_s") or {}
    missing = [b for b in hands if not speeds.get(b)]
    if missing:
        raise TimingError("profile", f"no speed track for hand bone(s) {missing}")
    per = int(profile.get("frames_per_sample") or 1)
    spans = []
    for t in times:
        end = int(round(t * fps))
        spans.append((max(0, end - per), end))
    raw = [max(speeds[hands[0]][k], speeds[hands[1]][k]) / scale for k in range(len(times))]
    tracks = [speeds[b] for b in body if speeds.get(b)] or [speeds[h] for h in hands]
    whole = [max(tr[k] for tr in tracks) / scale for k in range(len(times))]
    return {"spans": spans, "hands_raw": raw, "hands": _smooth(raw), "body": whole}


def detect(sig: dict, params: dict, frames: int) -> dict:
    """신호 → 구간(프레임). frames = 마지막 키 번호(길이 × fps)."""
    s, body, spans = sig["hands"], sig["body"], sig["spans"]
    n = len(s)
    out = {"peak": None, "core": None, "swing": None, "head": None, "tail": None, "reason": None}
    if not n:
        out["reason"] = "NO_SAMPLES"
        return out
    k_peak = max(range(n), key=s.__getitem__)
    peak = s[k_peak]
    out["peak"] = {"cm_s": round(peak, 1), "raw_cm_s": round(max(sig["hands_raw"]), 1), "time_frame": spans[k_peak][1], "sample": k_peak}
    if peak < MIN_PEAK_CM_S:
        out["reason"] = "NO_SWING"
        return out
    sw = params["swing"]
    core = [k for k in range(n) if s[k] >= sw["core_ratio"] * peak]
    c0, c1 = core[0], core[-1]
    a, b = c0, c1
    while a > 0 and s[a - 1] >= sw["edge_ratio"] * peak:
        a -= 1
    while b < n - 1 and s[b + 1] >= sw["edge_ratio"] * peak:
        b += 1
    # 머리 · 꼬리 — 처음부터 / 끝까지 이어지는 정지 표본(정점은 넘지 않는다)
    still = params["still"]["speed_cm_s"]
    h = 0
    while h < k_peak and body[h] < still:
        h += 1
    t = n
    while t - 1 > k_peak and body[t - 1] < still:
        t -= 1
    # 국소 최소 쪽으로 넓히되 정지 머리 · 꼬리 안으로는 들어가지 않는다(스무딩 꼬리가 정지 구간에서도 계속 줄어든다)
    while a > max(0, h - 1) and s[a - 1] < s[a]:
        a -= 1
    while b < min(n - 1, t) and s[b + 1] < s[b]:
        b += 1
    out["core"] = [spans[c0][0], spans[c1][1]]
    out["swing"] = [spans[a][0], spans[b][1]]
    if h:
        out["head"] = [0, spans[h - 1][1]]
    if t < n:
        out["tail"] = [spans[t][0], frames]
    return out


POINT_EVENTS = ("swing_start", "swing_peak", "swing_end", "still_start", "still_end")
WINDOW_EVENTS = ("swing", "both_planted")
BOTH_PLANTED_MIN_SAMPLES = 3


def events(profile: dict, *, hands: tuple[str, str], body: list[str], feet: tuple[str, str], scale: float, fps: float, length: float,
           leg_cm: float, up: int = 2, params: dict | None = None) -> dict:
    """사건(초) — Phase 8-4b 지시 목표(fix.body.targets[].at)와 E0 가 쓰는 한 원천. 휘두름 = signals → detect(흐느적 보정과 같은 신호 · 규칙):
    swing_start · swing_peak · swing_end(휘두름이 없으면 None), still_end = 처음부터 이어진 정지(머리)의 끝 · still_start = 끝까지 이어진 정지(꼬리)의
    시작(없으면 None), 구간 swing · both_planted[] = 두 발목이 모두 접지(motion_metrics.detect_contacts)인 표본 구간(BOTH_PLANTED_MIN_SAMPLES 이상)."""
    params = params or normalize(True)
    frames = int(round(length * fps))
    det = detect(signals(profile, hands, body, scale, fps), params, frames)
    sec = lambda f: round(f / fps, ROUND)  # noqa: E731
    swing = det.get("swing")
    out = {"swing_start": sec(swing[0]) if swing else None,
           "swing_peak": sec(det["peak"]["time_frame"]) if swing and det.get("peak") else None,
           "swing_end": sec(swing[1]) if swing else None,
           "still_end": sec(det["head"][1]) if det.get("head") else None,
           "still_start": sec(det["tail"][0]) if det.get("tail") else None,
           "swing": [sec(swing[0]), sec(swing[1])] if swing else None,
           "peak_cm_s": (det.get("peak") or {}).get("cm_s"), "reason": det.get("reason"), "both_planted": []}
    pos, times = profile.get("position_cm") or {}, profile.get("times") or []
    if all(pos.get(b) for b in feet) and times:
        contacts = [mm.detect_contacts(pos[b], times, up, leg_cm) for b in feet]
        both = mm.runs([a and c for a, c in zip(*contacts)], BOTH_PLANTED_MIN_SAMPLES)
        out["both_planted"] = [[round(times[a], ROUND), round(times[c], ROUND)] for a, c in both]
    return out


def _pchip(x: list[float], y: list[float]) -> list[float]:
    """PCHIP 기울기(Fritsch–Butland — 내부 가중 조화 평균, 끝은 세 점 식에 부호 · 3배 제한) — C++ FWarpCurve::PchipSlopes 와 같다."""
    n = len(x)
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    d = [(y[i + 1] - y[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [d[0], d[0]]
    m = [0.0] * n
    for k in range(1, n - 1):
        w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
        m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k]) if d[k - 1] > 0 and d[k] > 0 else 0.0

    def end(h0, h1, d0, d1):
        s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if s * d0 <= 0:
            return 0.0
        return 3 * d0 if d0 * d1 <= 0 and abs(s) > 3 * abs(d0) else s
    m[0], m[-1] = end(h[0], h[1], d[0], d[1]), end(h[-1], h[-2], d[-1], d[-2])
    return m


class WarpCurve:
    """time_warp 사상 — 새 시각 u → 원 시각, 매듭 사이 3차 Hermite(끝 값 = 원 시각, 끝 기울기 = 재생 배율, 없으면 PCHIP). C++ FWarpCurve 와 같은 식."""

    def __init__(self, knots: list, rates: list | None = None):
        self.src = [float(k[0]) for k in knots]
        self.dst = [float(k[1]) for k in knots]
        self.m = [float(r) for r in rates] if rates else _pchip(self.dst, self.src)

    def _at(self, u: float) -> tuple[int, float, float]:
        u = min(max(u, self.dst[0]), self.dst[-1])
        i = 0
        while i + 2 < len(self.dst) and u > self.dst[i + 1]:
            i += 1
        h = self.dst[i + 1] - self.dst[i]
        return i, h, (u - self.dst[i]) / h

    def map(self, u: float) -> float:
        i, h, t = self._at(u)
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * self.src[i] + (t3 - 2 * t2 + t) * h * self.m[i] + (-2 * t3 + 3 * t2) * self.src[i + 1]
                + (t3 - t2) * h * self.m[i + 1])

    def rate(self, u: float) -> float:
        i, h, t = self._at(u)
        t2 = t * t
        return ((6 * t2 - 6 * t) * self.src[i] + (3 * t2 - 4 * t + 1) * h * self.m[i] + (-6 * t2 + 6 * t) * self.src[i + 1]
                + (3 * t2 - 2 * t) * h * self.m[i + 1]) / h

    def forward(self, s: float) -> float:
        """원 시각 → 새 시각(단조 — 이분 탐색)."""
        if s <= self.src[0]:
            return self.dst[0]
        if s >= self.src[-1]:
            return self.dst[-1]
        lo, hi = self.dst[0], self.dst[-1]
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.map(mid) < s:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


def rate_marks(win: dict, r: float, rr: float, has_recovery: bool, head_cut: int, tail_cut: int, recovery_end: int) -> list[tuple[int, float, str]]:
    """배율 곡선의 매듭(원 프레임, 배율, 종류) — 같은 프레임이면 큰 배율 하나(램프 길이 0 이어도 핵심 배율을 지킨다), 머리 · 꼬리 컷 안으로."""
    a, b = win["swing"]
    c0, c1 = win["core"]
    marks = [(head_cut, 1.0, "start"), (a, 1.0, "swing_start"), (c0, r, "core_start"), (c1, r, "core_end"),
             (b, rr if has_recovery else 1.0, "swing_end")]
    if has_recovery:
        marks.append((min(recovery_end, tail_cut), rr, "recovery_end"))
    marks.append((tail_cut, 1.0, "end"))
    out: list[tuple[int, float, str]] = []
    for f, rate, kind in sorted(((min(max(f, head_cut), tail_cut), rate, kind) for f, rate, kind in marks), key=lambda m: m[0]):
        if out and out[-1][0] == f:
            if rate > out[-1][1]:
                out[-1] = (f, rate, kind)
            continue
        out.append((f, rate, kind))
    return out


def plan(profile: dict, *, hands: tuple[str, str], body: list[str], scale: float, fps: float, length: float, params: dict) -> dict:
    """profile → {version, applied, reason, signal, windows(초), rate, recovery_rate, antialias, profile[{kind, at_s, rate}](배율 곡선 매듭), knots
    (time_warp — 자른 타임라인 기준) | None, ops[], warp[[원 시각, 새 시각, 배율]…], cut, length{before, after}}.
    applied 가 거짓이면 ops 는 항등 trim 하나(최종 이름의 새 애셋을 만들기 위해) — reason 이 그 이유."""
    frames = int(round(length * fps))
    sig = signals(profile, hands, body, scale, fps)
    win = detect(sig, params, frames)
    sec = lambda f: round(f / fps, ROUND)  # noqa: E731
    out = {"version": VERSION, "applied": False, "reason": win["reason"], "fps": fps,
           "signal": {"peak_cm_s": (win["peak"] or {}).get("cm_s"), "peak_raw_cm_s": (win["peak"] or {}).get("raw_cm_s"),
                      "peak_time": sec(win["peak"]["time_frame"]) if win["peak"] else None, "samples": len(sig["spans"]),
                      "frames_per_sample": int(profile.get("frames_per_sample") or 1)},
           "windows": {k: [sec(f) for f in win[k]] if win[k] else None for k in ("head", "core", "swing", "tail")},
           "rate": None, "recovery_rate": None, "antialias": params["antialias"], "profile": [], "knots": None, "ops": [],
           "warp": [[0.0, 0.0, 1.0], [round(length, ROUND), round(length, ROUND), 1.0]],
           "length": {"before": round(length, ROUND), "after": round(length, ROUND)}}
    if win["reason"]:
        out["ops"] = [{"op": "trim"}]
        return out
    st = params["still"]
    a, b = win["swing"]
    head_cut = 0
    if st["trim_head"] and win["head"] and win["head"][1] / fps >= st["min_s"]:
        head_cut = min(max(0, win["head"][1] - int(round(st["keep_head_s"] * fps))), a)
    tail_cut = frames
    if st["trim_tail"] and win["tail"] and (frames - win["tail"][0]) / fps >= st["min_s"]:
        tail_cut = max(min(frames, win["tail"][0] + int(round(st["keep_tail_s"] * fps))), b)
    peak = win["peak"]["cm_s"]
    r = min(max(params["target_peak_cm_s"] / peak, 1.0), params["max_rate"])
    rr = params["recovery_rate"]
    recovery_end = max(win["tail"][0], b) if win["tail"] else frames
    # 이미 빠른 휘두름(운영 공격 — 정점 ≥ 목표)은 복귀도 건드리지 않는다: 흐느적이 아니다
    has_recovery = r >= MIN_RATE and rr >= MIN_RATE and min(recovery_end, tail_cut) > b
    ops = []
    if head_cut > 0 or tail_cut < frames:
        ops.append({"op": "trim", **({"start": sec(head_cut)} if head_cut > 0 else {}), **({"end": sec(tail_cut)} if tail_cut < frames else {})})
    marks = rate_marks(win, r, rr, has_recovery, head_cut, tail_cut, recovery_end) if r >= MIN_RATE else [(head_cut, 1.0, "start"), (tail_cut, 1.0, "end")]
    # 매듭 사이 출력 길이 = 원 길이 / 두 끝 배율 평균(선형 램프) → 전체를 정수 프레임으로 올림(출력 시각을 고르게 늘인다 — 배율은 그 역수만큼
    # 낮아져 상한을 넘지 않는다, 1 프레임 미만)
    dst = [0.0]
    for (f0, r0, _), (f1, r1, _) in zip(marks, marks[1:]):
        dst.append(dst[-1] + (f1 - f0) / ((r0 + r1) / 2.0))
    new_frames = max(1, int(math.ceil(dst[-1] - 1e-6)))
    k = new_frames / dst[-1] if dst[-1] > 0 else 1.0
    rates = [m[1] / k for m in marks]
    dst = [d * k for d in dst]
    if r >= MIN_RATE:
        knots = [[round((f - head_cut) / fps, KNOT_ROUND), round(d / fps, KNOT_ROUND)] for (f, _, _), d in zip(marks, dst)]
        knots[-1][1] = round(new_frames / fps, KNOT_ROUND)
        out["knots"] = knots
        ops.append({"op": "time_warp", "knots": knots, "rates": [round(x, KNOT_ROUND) for x in rates], "antialias": params["antialias"]})
    out["profile"] = [{"kind": kind, "at_s": sec(f), "rate": round(x, ROUND)} for (f, _, kind), x in zip(marks, rates)]
    out["rate"] = round(r, ROUND) if r >= MIN_RATE else 1.0
    out["recovery_rate"] = rr if has_recovery else 1.0
    out["cut"] = {"head_s": sec(head_cut), "tail_s": sec(tail_cut)}
    out["warp"] = [[round(f / fps, KNOT_ROUND), round(d / fps, KNOT_ROUND), round(x, KNOT_ROUND)] for (f, _, _), d, x in zip(marks, dst, rates)]
    out["length"]["after"] = round(new_frames / fps, ROUND)
    if not ops:
        out["reason"] = "ALREADY_FAST" if r < MIN_RATE else "NOTHING_TO_CHANGE"
        out["ops"] = [{"op": "trim"}]
        return out
    out["ops"] = ops
    out["applied"] = True
    return out


def summary(profile: dict, *, hands: tuple[str, str], body: list[str], scale: float, fps: float, length: float, params: dict) -> dict:
    """전 · 후 비교 수치 — 휘두름 정점(손목 원 신호 최대 / scale — select swing 과 같은 크기) · 정점 시각 · 정지 머리 · 꼬리 길이(초) · 길이."""
    sig = signals(profile, hands, body, scale, fps)
    still = params["still"]["speed_cm_s"]
    n = len(sig["spans"])
    raw = sig["hands_raw"]
    k = max(range(n), key=raw.__getitem__) if n else None
    head = 0
    while head < n and sig["body"][head] < still:
        head += 1
    tail = n
    while tail > 0 and sig["body"][tail - 1] < still:
        tail -= 1
    frames = int(round(length * fps))
    return {"peak_cm_s": round(raw[k], 1) if k is not None else None, "peak_time": round(sig["spans"][k][1] / fps, ROUND) if k is not None else None,
            "head_still_s": round(sig["spans"][head - 1][1] / fps, ROUND) if head else 0.0,
            "tail_still_s": round((frames - sig["spans"][tail][0]) / fps, ROUND) if tail < n else 0.0, "length": round(length, ROUND)}


def warp_time(warp: list[list[float]], t: float) -> float:
    """원 시각 → 새 시각. warp = plan 의 [[원 시각, 새 시각, 배율]…](time_warp 와 같은 Hermite — 이분 탐색) 또는 [[원, 새]…](선형 — 처음 판 Job
    기록). 자른 곳 밖은 처음 · 끝으로."""
    if t <= warp[0][0]:
        return warp[0][1]
    if t >= warp[-1][0]:
        return warp[-1][1]
    if len(warp[0]) >= 3:
        return WarpCurve([w[:2] for w in warp], [w[2] for w in warp]).forward(t)
    for (t0, n0), (t1, n1) in zip(warp, warp[1:]):
        if t <= t1:
            return n0 + (n1 - n0) * (t - t0) / (t1 - t0) if t1 > t0 else n1
    return warp[-1][1]


def max_rate_step(source_times: list[float], fps: float) -> float:
    """simulate 결과(출력 키 → 원 시각)에서 출력 프레임 사이 재생 배율 변화의 최대 — 속도 단차(계단 retime 이면 조각 경계에서 튄다)."""
    steps = [(b - a) * fps for a, b in zip(source_times, source_times[1:])]
    return max((abs(y - x) for x, y in zip(steps, steps[1:])), default=0.0)


def simulate(ops: list[dict], length: float, fps: float) -> dict:
    """C++ 편집 op 의 시간 의미를 다시 돈다(AnimMcpAnimEditOps.cpp — TimeToKey 반올림 · Retime / TimeWarp 새 길이 = 프레임 반올림 · Trim 키 구간 ·
    키 사이 선형 보간). → {length, source_times(새 키 → 원 시각)} — pytest 가 계획의 warp 와 대조한다."""
    total = int(round(length * fps))
    source = [k / fps for k in range(total + 1)]   # 지금 타임라인의 키 → 원 시각
    for op in ops:
        n = len(source) - 1
        key = lambda t: min(max(int(math.floor(t * fps + 0.5)), 0), n)  # noqa: E731

        def lerp(t: float) -> float:
            x = min(max(t * fps, 0.0), n)
            k0 = min(int(x), n)
            k1 = min(k0 + 1, n)
            return source[k0] + (source[k1] - source[k0]) * (x - k0)

        if op["op"] == "time_warp":
            knots = op["knots"]
            if len(knots) < 2 or abs(knots[0][0]) > 1e-6 or abs(knots[0][1]) > 1e-6 or abs(knots[-1][0] - n / fps) > 0.5 / fps:
                raise TimingError("ops", f"time_warp knots must run [0, 0] … [{n / fps:.4f}, new length] (got {knots[0]} … {knots[-1]})")
            curve = WarpCurve([k[:2] for k in knots[:-1]] + [[n / fps, knots[-1][1]]], op.get("rates"))
            new_len = knots[-1][1]
            frames = max(1, int(math.floor(new_len * fps + 0.5)))
            source = [lerp(curve.map(min(k / fps, new_len))) for k in range(frames + 1)]
            continue
        start = key(op.get("start", 0.0))
        end = key(op["end"]) if op.get("end") is not None else n
        if end - start < 1:
            raise TimingError("ops", f"{op} covers less than one frame")
        if op["op"] == "trim":
            source = source[start:end + 1]
        elif op["op"] == "retime":
            rate = op["rate"]
            seg = (end - start) / fps
            new_len = n / fps - seg + seg / rate
            frames = max(1, int(math.floor(new_len * fps + 0.5)))
            ts, te, new_seg = start / fps, end / fps, seg / rate

            def at(u: float, ts=ts, te=te, new_seg=new_seg, rate=rate) -> float:
                if u <= ts:
                    return u
                if u <= ts + new_seg:
                    return ts + (u - ts) * rate
                return te + (u - ts - new_seg)

            source = [lerp(at(k / fps)) for k in range(frames + 1)]
        else:
            raise TimingError("ops", f"simulate handles trim · retime · time_warp, got {op['op']}")
    return {"length": (len(source) - 1) / fps, "source_times": source}
