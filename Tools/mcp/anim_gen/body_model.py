"""Phase 8-4a — 몸 모델 읽기 · FK · LBS · 반경 지도 조회 (순수 Python — numpy 없음).

원천은 C++ `validate_animation body_clearance{model}`(Plugins/AnimGraphMcp/…/Core/AnimMcpBodyClearance.cpp) 하나다 — 이 모듈은 그 모델을 읽어
C++ 측정과 같은 규칙으로 깊이를 다시 계산한다(8-4b 의 한 풀이 `body_fit` 가 포즈를 바꿔 가며 부른다):

  점(LBS)   — 팔 · 다리 부위 점마다 영향 [본, 가중치, 그 본 기준 포즈 공간 위치] → 프레임 위치 = Σ w · 포즈(로컬 위치). 포즈 = 본의 컴포넌트 공간
              (q[x, y, z, w], t, s) — UE FTransform 과 같은 곱 순서(자식 = 로컬 * 부모: 회전 = 부모 ⊗ 로컬, 위치 = 부모 회전(부모 스케일 ∘ 로컬 위치) + 부모 위치).
  반경 지도 — 축(A · Dir · X · Length, Y = Dir × X) 둘레 (t 칸 × 각도 36 칸)의 최대 반경(int16 0.01 cm, 빈 칸 −1). 점 깊이 = 칸 반경 − 축까지 거리
              (빈 칸은 이웃 3×3 최대 — 각도는 감아 돌고 t 는 자른다). 몸통 칸 이름 = 칸 가운데 t 를 torso_t_bounds(belly · chest)로.
  쌍        — (몸 기준 좌우, 팔 부위, 몸 부위)마다 프레임 깊이 = 그 부위 점 중 가장 깊은 값(부호 있음, 걸리는 칸이 없으면 None).
              다리끼리 = 다리 점 ↔ 반대 넓적다리(칸 가운데 t ≥ leg_thigh_t_min) · 반대 종아리. 손끼리(8-4b, 모델에 hand_l/r · forearm_l/r 지도가
              있으면 — C++ hands) = 팔 점 ↔ 반대 팔 손 · 아래팔 지도(몸 부위 이름 = 지도 이름).
  통계      — C++ PairJson 과 같은 정의(깊이 = max(0, d), 비율의 분모 = 전체 프레임, 백분위 = 선형 보간).
  델타      — bone_deltas 와 같은 뜻: 새 로컬 회전 = Q(Δ) ⊗ 원래(부모 공간 회전 벡터, 관절 그대로), 이동 = 원래 + Δ → 그 본과 자손만 다시 FK.

모델의 몸 지도는 프레임마다 C++ 가 대상 메시 스킨으로 만든 것이라, 팔 · 다리를 옮기는 동안(몸통 · 척추가 그대로면) 그대로 쓴다.
"""
from __future__ import annotations

import base64
import math
import struct

VERSION = 1
ARM_PARTS = ("hand", "forearm", "upper_arm")
LEG_PARTS = ("thigh", "calf")
BODY_PARTS = ("pelvis", "belly", "chest", "thigh_l", "thigh_r", "head_neck")
HAND_MAP_KINDS = ("hand", "forearm")   # 손끼리(8-4b) 지도 — f"{kind}_{좌우}"
SIDES = ("l", "r")
EMPTY_I16 = -32768
ANGLE_BINS = 36


class ModelError(ValueError):
    """모델 JSON 이 이 모듈이 아는 모양이 아니다."""


# ---- 벡터 · 쿼터니언 (x, y, z, w — UE FQuat 과 같은 해밀턴 곱) ----
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def qmul(a, b):
    """a ⊗ b — b 를 먼저 적용한 뒤 a (UE FQuat operator*)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qnormalize(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n) if n > 1e-12 else (0.0, 0.0, 0.0, 1.0)


def qrot(q, v):
    """회전 — v + w·t + q×t, t = 2 q×v (UE FQuat::RotateVector)."""
    x, y, z, w = q
    tx, ty, tz = 2.0 * (y * v[2] - z * v[1]), 2.0 * (z * v[0] - x * v[2]), 2.0 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def from_rotvec_deg(v):
    """회전 벡터(축 × 각°) → 쿼터니언 — bone_deltas rotation_deg 와 같은 뜻."""
    deg = _norm(v)
    if deg == 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    half = math.radians(deg) / 2.0
    s = math.sin(half) / deg
    return (v[0] * s, v[1] * s, v[2] * s, math.cos(half))


def to_rotvec_deg(q):
    """쿼터니언 → 회전 벡터(°, |각| ≤ 180 — w ≥ 0 쪽)."""
    x, y, z, w = qnormalize(q)
    if w < 0.0:
        x, y, z, w = -x, -y, -z, -w
    s = math.sqrt(max(0.0, 1.0 - w * w))
    if s < 1e-12:
        return (0.0, 0.0, 0.0)
    angle = math.degrees(2.0 * math.atan2(s, w))
    return (x / s * angle, y / s * angle, z / s * angle)


# ---- 변환 (q, t, s) — UE FTransform ----
def transform_point(x, p):
    q, t, s = x
    return _add(qrot(q, (p[0] * s[0], p[1] * s[1], p[2] * s[2])), t)


def compose(local, parent):
    """자식 컴포넌트 = local * parent (스케일은 성분별 곱 — 균일 스케일 전제, 회전과 섞인 비균일은 다루지 않는다)."""
    lq, lt, ls = local
    pq, pt, ps = parent
    return (qnormalize(qmul(pq, lq)), transform_point(parent, lt), (ls[0] * ps[0], ls[1] * ps[1], ls[2] * ps[2]))


def relative(child, parent):
    """local = child * parent⁻¹."""
    cq, ct, cs = child
    pq, pt, ps = parent
    inv = qconj(pq)
    d = qrot(inv, _sub(ct, pt))
    return (qnormalize(qmul(inv, cq)), (d[0] / ps[0], d[1] / ps[1], d[2] / ps[2]), (cs[0] / ps[0], cs[1] / ps[1], cs[2] / ps[2]))


# ---- 디코드 ----
def decode_f32(b64: str) -> list[float]:
    raw = base64.b64decode(b64)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def decode_i16(b64: str, unit: float) -> list[float]:
    """int16 LE → cm, 빈 칸(−32768) = −1."""
    raw = base64.b64decode(b64)
    return [-1.0 if v == EMPTY_I16 else v * unit for v in struct.unpack(f"<{len(raw) // 2}h", raw)]


class RadialMap:
    """한 부위 지도의 모든 프레임 — C++ FRadialAxis 와 같은 Locate · Radius."""

    def __init__(self, raw: dict, frames: int):
        self.part = raw["part"]
        self.t_min, self.t_max = float(raw["t_min"]), float(raw["t_max"])
        self.t_bins, self.angle_bins = int(raw["t_bins"]), int(raw["angle_bins"])
        axis = decode_f32(raw["axis_b64"])
        radius = decode_i16(raw["radius_b64"], float(raw["radius_unit_cm"]))
        cells = self.t_bins * self.angle_bins
        if len(axis) != frames * 10 or len(radius) != frames * cells:
            raise ModelError(f"map {self.part}: {len(axis)} axis floats / {len(radius)} radii for {frames} frames × {cells} cells")
        self.axes = []
        for f in range(frames):
            a = axis[f * 10:(f + 1) * 10]
            d, x = (a[3], a[4], a[5]), (a[6], a[7], a[8])
            self.axes.append({"a": (a[0], a[1], a[2]), "dir": d, "x": x, "y": _cross(d, x), "length": a[9]})
        self.radius = [radius[f * cells:(f + 1) * cells] for f in range(frames)]
        self.part_of_t_bin = list(raw.get("part_of_t_bin") or [])

    def bin_center(self, t_bin: int) -> float:
        return self.t_min + (t_bin + 0.5) / self.t_bins * (self.t_max - self.t_min)

    def locate(self, f: int, p) -> tuple[int, int, float] | None:
        """(t 칸, 각도 칸, 축까지 거리) — 축이 없거나 t 가 범위 밖이면 None."""
        ax = self.axes[f]
        length = ax["length"]
        if length <= 0.0:
            return None
        rel = _sub(p, ax["a"])
        along = _dot(rel, ax["dir"])
        t = along / length
        if t < self.t_min or t > self.t_max:
            return None
        radial = _sub(rel, _scale(ax["dir"], along))
        t_bin = min(max(int(math.floor((t - self.t_min) / (self.t_max - self.t_min) * self.t_bins)), 0), self.t_bins - 1)
        angle = math.atan2(_dot(radial, ax["y"]), _dot(radial, ax["x"]))
        a_bin = min(max(int(math.floor((angle + math.pi) / (2.0 * math.pi) * self.angle_bins)), 0), self.angle_bins - 1)
        return t_bin, a_bin, _norm(radial)

    def cell_radius(self, f: int, t_bin: int, a_bin: int) -> float:
        """칸 반경 — 빈 칸이면 이웃 3×3 최대, 없으면 −1."""
        r = self.radius[f]
        own = r[t_bin * self.angle_bins + a_bin]
        if own >= 0.0:
            return own
        best = -1.0
        for dt in (-1, 0, 1):
            tt = t_bin + dt
            if tt < 0 or tt >= self.t_bins:
                continue
            for da in (-1, 0, 1):
                v = r[tt * self.angle_bins + (a_bin + da + self.angle_bins) % self.angle_bins]
                if v > best:
                    best = v
        return best

    def depth(self, f: int, p, min_t: float | None = None) -> tuple[float, int] | None:
        """(부호 있는 깊이 cm, t 칸) — 칸 가운데 t < min_t · 빈 칸(이웃도)이면 None."""
        loc = self.locate(f, p)
        if loc is None:
            return None
        t_bin, a_bin, dist = loc
        if min_t is not None and self.bin_center(t_bin) < min_t:
            return None
        rho = self.cell_radius(f, t_bin, a_bin)
        if rho < 0.0:
            return None
        return rho - dist, t_bin


class BodyModel:
    """C++ model{} 하나 — 프레임 i 는 model.frames[i](원 프레임 번호)에 해당한다."""

    def __init__(self, model: dict):
        if int(model.get("version") or 0) != VERSION:
            raise ModelError(f"model version {model.get('version')} (this reader knows {VERSION})")
        self.raw = model
        self.frames = [int(f) for f in model["frames"]]
        self.times = [float(t) for t in model["times"]]
        self.fps = float(model["fps"])
        self.scale = float(model["scale"])
        self.contact_cm = float(model["contact_cm"])
        self.penetration_cm = float(model["penetration_cm"])
        self.bones = list(model["bones"]["names"])
        self.parents = [int(p) for p in model["bones"]["parents"]]
        self.index = {b: i for i, b in enumerate(self.bones)}
        self.children: list[list[int]] = [[] for _ in self.bones]
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[p].append(i)
        self.roles = model.get("roles") or {}
        n_frames, n_bones = len(self.frames), len(self.bones)
        flat = decode_f32(model["poses"]["b64"])
        if len(flat) != n_frames * n_bones * 10:
            raise ModelError(f"poses: {len(flat)} floats for {n_frames} frames × {n_bones} bones × 10")
        self.poses = []
        for f in range(n_frames):
            row = []
            for b in range(n_bones):
                v = flat[(f * n_bones + b) * 10:(f * n_bones + b + 1) * 10]
                row.append(((v[0], v[1], v[2], v[3]), (v[4], v[5], v[6]), (v[7], v[8], v[9])))
            self.poses.append(row)
        self.points = []
        for pt in model["points"]:
            infl = [(int(i[0]), float(i[1]), (float(i[2]), float(i[3]), float(i[4]))) for i in pt["influences"]]
            self.points.append({"side": pt["side"], "part": pt["part"], "dominant": int(pt["dominant"]), "ref": tuple(pt["ref_cm"]), "influences": infl})
        bounds = model["torso_t_bounds"]
        self.belly_t, self.chest_t = float(bounds["belly"]), float(bounds["chest"])
        self.leg_thigh_t_min = float(model.get("leg_thigh_t_min") or 0.2)
        self.maps = {m["part"]: RadialMap(m, n_frames) for m in model["maps"]}

    # ---- 포즈 ----
    def local_pose(self, f: int) -> list:
        """프레임 f 의 본 로컬(부모 기준) — 부모가 목록 밖(루트)이면 컴포넌트 그대로."""
        comp = self.poses[f]
        return [comp[b] if p < 0 else relative(comp[b], comp[p]) for b, p in enumerate(self.parents)]

    def component_from_local(self, local: list) -> list:
        out = [None] * len(local)
        for b, p in enumerate(self.parents):
            out[b] = local[b] if p < 0 else compose(local[b], out[p])
        return out

    def apply_deltas(self, f: int, deltas: dict) -> list:
        """bone_deltas 와 같은 뜻 — {본 이름: (rotation_deg[3] | None, translation_cm[3] | None)} 을 프레임 f 에 → 새 컴포넌트 포즈."""
        local = self.local_pose(f)
        for name, (rot, trans) in deltas.items():
            b = self.index[name]
            q, t, s = local[b]
            if rot is not None and any(rot):
                q = qnormalize(qmul(from_rotvec_deg(rot), q))
            if trans is not None and any(trans):
                t = _add(t, trans)
            local[b] = (q, t, s)
        return self.component_from_local(local)

    # ---- 점 · 깊이 ----
    def skin(self, pose: list, point: dict):
        x = y = z = 0.0
        for bone, w, lp in point["influences"]:
            px, py, pz = transform_point(pose[bone], lp)
            x += w * px
            y += w * py
            z += w * pz
        return (x, y, z)

    def torso_part(self, t_bin: int) -> str:
        t = self.maps["torso"].bin_center(t_bin)
        return "pelvis" if t < self.belly_t else "belly" if t < self.chest_t else "chest"

    def has_hands(self) -> bool:
        """손끼리 지도(C++ body_clearance hands)가 모두 있는가."""
        return all(f"{k}_{s}" in self.maps for k in HAND_MAP_KINDS for s in SIDES)

    def pair_depths(self, f: int, pose: list | None = None) -> dict:
        """{(side, part, body_part): 부호 있는 깊이 | 없음} — 팔 부위 × 몸 부위, 다리 점이 있으면 다리끼리도, 손끼리 지도가 있으면 팔 점 × 반대 팔 손 ·
        아래팔. pose 를 주면 그 포즈로(풀이 중 — 지도는 원래 포즈 그대로)."""
        pose = pose or self.poses[f]
        out: dict = {}

        def offer(key, d):
            if d is not None and (key not in out or d > out[key]):
                out[key] = d

        torso, head = self.maps.get("torso"), self.maps.get("head_neck")
        hands = self.has_hands()
        for pt in self.points:
            p = self.skin(pose, pt)
            side, part = pt["side"], pt["part"]
            if part in ARM_PARTS:
                if torso:
                    hit = torso.depth(f, p)
                    if hit:
                        offer((side, part, self.torso_part(hit[1])), hit[0])
                for name in ("thigh_l", "thigh_r"):
                    m = self.maps.get(name)
                    hit = m.depth(f, p) if m else None
                    if hit:
                        offer((side, part, name), hit[0])
                hit = head.depth(f, p) if head else None
                if hit:
                    offer((side, part, "head_neck"), hit[0])
                if hands:
                    other = "r" if side == "l" else "l"
                    for kind in HAND_MAP_KINDS:
                        hit = self.maps[f"{kind}_{other}"].depth(f, p)
                        if hit:
                            offer((side, part, f"{kind}_{other}"), hit[0])
            elif part in LEG_PARTS:
                other = "r" if side == "l" else "l"
                m = self.maps.get(f"thigh_{other}")
                hit = m.depth(f, p, self.leg_thigh_t_min) if m else None
                if hit:
                    offer((side, part, f"thigh_{other}"), hit[0])
                m = self.maps.get(f"calf_{other}")
                hit = m.depth(f, p) if m else None
                if hit:
                    offer((side, part, f"calf_{other}"), hit[0])
        return out

    def series(self, poses: list | None = None) -> dict:
        """쌍마다 모델 프레임별 깊이 목록(없으면 None) — poses[i] 를 주면 그 포즈로."""
        keys = [(s, p, b) for s in SIDES for p in ARM_PARTS for b in BODY_PARTS]
        if self.has_hands():
            keys += [(s, p, f"{kind}_{'r' if s == 'l' else 'l'}") for s in SIDES for p in ARM_PARTS for kind in HAND_MAP_KINDS]
        if any(pt["part"] in LEG_PARTS for pt in self.points):
            keys += [(s, p, f"{kind}_{'r' if s == 'l' else 'l'}") for s in SIDES for p in LEG_PARTS for kind in ("thigh", "calf")]
        out = {k: [] for k in keys}
        for i in range(len(self.frames)):
            d = self.pair_depths(i, poses[i] if poses else None)
            for k in keys:
                out[k].append(d.get(k))
        return out


# ---- 통계 · 대조 ----
def percentile(values: list[float], p: float) -> float:
    """선형 보간 백분위(numpy 기본 — C++ AnimMcpStats::Percentile 과 같다), p 0 ~ 100. 빈 목록 0."""
    if not values:
        return 0.0
    v = sorted(values)
    rank = min(max(p, 0.0), 100.0) / 100.0 * (len(v) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (rank - lo)


def pair_stats(depths: list, contact_cm: float, penetration_cm: float) -> dict:
    """C++ PairJson 과 같은 정의 — 깊이 = max(0, d)(None 은 0), 비율의 분모 = 전체 프레임."""
    clipped = [max(0.0, d) if d is not None else 0.0 for d in depths]
    n = max(1, len(depths))
    located = [d for d in depths if d is not None]
    return {"frames_over_contact_pct": round(100.0 * sum(d > contact_cm for d in clipped) / n, 1),
            "frames_over_penetration_pct": round(100.0 * sum(d > penetration_cm for d in clipped) / n, 1),
            "depth_p50": round(percentile(clipped, 50.0), 2), "depth_p95": round(percentile(clipped, 95.0), 2),
            "depth_max": round(max(0.0, max(located)) if located else 0.0, 2), "located_pct": round(100.0 * len(located) / n, 1)}


def compare(model: BodyModel, per_frame: dict, python_series: dict | None = None) -> dict:
    """Python 재현 vs C++ per_frame — 모델 프레임에서 쌍별 |깊이 차|(둘 다 있는 프레임) · 한쪽만 있는 프레임 수 · 관통 % 차(같은 프레임 집합).
    → {pairs: {key: {...}}, diff_p95, diff_max, located_mismatch, penetration_pct_equal}."""
    py = python_series or model.series()
    cpp = {}
    for item in per_frame.get("series") or []:
        part = item.get("arm_part") or item.get("leg_part")
        cpp[(item["side"], part, item["body_part"])] = item["depth"]
    diffs_all, mismatch, pen_equal, pairs = [], 0, True, {}
    for key, values in py.items():
        if key not in cpp:
            continue
        ref = [cpp[key][f] for f in model.frames]
        diffs = [abs(a - b) for a, b in zip(values, ref) if a is not None and b is not None]
        miss = sum((a is None) != (b is None) for a, b in zip(values, ref))
        sp, sc = pair_stats(values, model.contact_cm, model.penetration_cm), pair_stats(ref, model.contact_cm, model.penetration_cm)
        same = sp["frames_over_penetration_pct"] == sc["frames_over_penetration_pct"]
        pen_equal &= same
        mismatch += miss
        diffs_all += diffs
        pairs["|".join(key)] = {"diff_p95": round(percentile(diffs, 95.0), 4), "diff_max": round(max(diffs) if diffs else 0.0, 4), "located_mismatch": miss,
                                "penetration_pct": [sp["frames_over_penetration_pct"], sc["frames_over_penetration_pct"]], "same_pct": same}
    return {"pairs": pairs, "diff_p95": round(percentile(diffs_all, 95.0), 4), "diff_max": round(max(diffs_all) if diffs_all else 0.0, 4),
            "located_mismatch": mismatch, "penetration_pct_equal": pen_equal, "compared_values": len(diffs_all)}
