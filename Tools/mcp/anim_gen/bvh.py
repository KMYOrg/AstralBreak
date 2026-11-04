"""BVH 헤더 읽기 · 기준 포즈 · 단위 추정 · 정면 방향 (지침서 §14 Phase 4).

Blender 없이 계획 단계와 pytest 에서 돈다. Blender 쪽(blender/bvh_to_fbx.py)은 여기서 정한 값(cm/단위 · Z 회전)을 그대로 쓴다.
좌표: BVH 는 단위 정보가 없고 Y-up 이 관례다. 축 변환은 Blender BVH 임포터의 axis_conversion(forward → +Y, up → +Z)과 같은 규칙,
Blender → UE 는 (x, -y, z) — FBX 내보내기 기본 축(-Z 앞 · Y 위) + Interchange ConvertScene(FbxConvert.cpp) + 왼손 좌표 뒤집기.
"""
from __future__ import annotations

import dataclasses
import math
import pathlib

MAX_BYTES = 256 * 1024 * 1024
# 사람 키로 그럴듯한 범위(cm) — 이 범위에 들어오는 표준 단위를 고르고, 없으면 정규화한다
HUMAN_HEIGHT_CM = (120.0, 230.0)
NORMALIZED_HEIGHT_CM = 170.0
UNITS_CM = {"cm": 1.0, "m": 100.0, "inch": 2.54, "mm": 0.1}
# 발 영역 = 바닥 + 키 × 이 비율 아래. 축에서 이만큼 넘게 벗어나면 방향을 모른다고 본다
FOOT_REGION = 0.15
AXIS_TOLERANCE_DEG = 30.0
# 바닥 · 꼭대기에서 뺄 외톨이 본: p5 ~ p95 폭의 이 배수보다 더 바깥 (본이 적은 BVH 에서 머리가 잘리지 않게 넉넉히)
OUTLIER_MARGIN = 1.0
AXES_UE = {"+X": (1.0, 0.0), "-X": (-1.0, 0.0), "+Y": (0.0, 1.0), "-Y": (0.0, -1.0)}
_AXIS_VEC = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


class BvhError(Exception):
    def __init__(self, reason: str, message: str, **details):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details


@dataclasses.dataclass
class Joint:
    name: str
    parent: int                        # 루트는 -1
    offset: tuple[float, float, float]
    channels: list[str]
    end_site: tuple[float, float, float] | None = None


@dataclasses.dataclass
class BvhInfo:
    joints: list[Joint]
    frames: int
    frame_time: float
    rows: int
    channel_count: int
    warnings: list[dict]

    @property
    def fps(self) -> float:
        return 1.0 / self.frame_time

    @property
    def duration(self) -> float:
        """UE 와 같은 정의 — 키 N 개 = (N - 1) 프레임 길이."""
        return max(self.frames - 1, 0) * self.frame_time


# ---- 읽기 ----
def read(path: str | pathlib.Path) -> BvhInfo:
    path = pathlib.Path(path)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise BvhError("TOO_LARGE", f"{path.name} is {size} bytes (limit {MAX_BYTES})", bytes=size)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tokens: list[str] = []
    motion_line = None
    for i, line in enumerate(lines):
        if line.strip().upper() == "MOTION":
            motion_line = i
            break
        tokens += line.split()
    if motion_line is None:
        raise BvhError("NO_MOTION", f"{path.name}: no MOTION section")
    joints = _parse_hierarchy(tokens, path.name)
    frames, frame_time, data_start = _parse_motion_header(lines, motion_line, path.name)
    channel_count = sum(len(j.channels) for j in joints)
    rows = 0
    for n, line in enumerate(lines[data_start:], start=data_start + 1):
        values = line.split()
        if not values:
            continue
        if len(values) != channel_count:
            raise BvhError("BAD_ROW", f"{path.name}:{n}: {len(values)} values, the hierarchy has {channel_count} channels",
                           line=n, values=len(values), channels=channel_count)
        rows += 1
    if rows < frames:
        raise BvhError("TRUNCATED", f"{path.name}: header says {frames} frames, found {rows} rows", frames=frames, rows=rows)
    return BvhInfo(joints=joints, frames=frames, frame_time=frame_time, rows=rows, channel_count=channel_count,
                   warnings=_warnings(joints, frames, rows))


def _parse_hierarchy(tokens: list[str], name: str) -> list[Joint]:
    if not tokens or tokens[0].upper() != "HIERARCHY":
        raise BvhError("NO_HIERARCHY", f"{name}: does not start with HIERARCHY")
    joints: list[Joint] = []
    stack: list[int] = []   # 열린 관절 (End Site 는 -2)
    i = 1

    def number(k: int) -> float:
        try:
            return float(tokens[k])
        except (IndexError, ValueError):
            raise BvhError("BAD_HIERARCHY", f"{name}: expected a number at token {k}") from None

    while i < len(tokens):
        tok = tokens[i]
        upper = tok.upper()
        if upper in ("ROOT", "JOINT"):
            if upper == "ROOT" and joints:
                raise BvhError("MULTIPLE_ROOTS", f"{name}: more than one ROOT — one skeleton per file")
            if i + 2 >= len(tokens) or tokens[i + 2] != "{":
                raise BvhError("BAD_HIERARCHY", f"{name}: '{tok}' needs a name and '{{'")
            parent = stack[-1] if stack else -1
            if upper == "JOINT" and parent < 0:
                raise BvhError("BAD_HIERARCHY", f"{name}: JOINT {tokens[i + 1]} outside a joint")
            joints.append(Joint(name=tokens[i + 1], parent=parent, offset=(0.0, 0.0, 0.0), channels=[]))
            stack.append(len(joints) - 1)
            i += 3
        elif upper == "END":
            if i + 2 >= len(tokens) or tokens[i + 1].upper() != "SITE" or tokens[i + 2] != "{" or not stack or stack[-1] < 0:
                raise BvhError("BAD_HIERARCHY", f"{name}: malformed End Site")
            stack.append(-2)
            i += 3
        elif upper == "OFFSET":
            if not stack:
                raise BvhError("BAD_HIERARCHY", f"{name}: OFFSET outside a joint")
            offset = (number(i + 1), number(i + 2), number(i + 3))
            if stack[-1] == -2:
                joints[stack[-2]].end_site = offset
            else:
                joints[stack[-1]].offset = offset
            i += 4
        elif upper == "CHANNELS":
            if not stack or stack[-1] < 0:
                raise BvhError("BAD_HIERARCHY", f"{name}: CHANNELS outside a joint")
            count = int(number(i + 1))
            joints[stack[-1]].channels = tokens[i + 2:i + 2 + count]
            i += 2 + count
        elif tok == "}":
            if not stack:
                raise BvhError("BAD_HIERARCHY", f"{name}: unbalanced '}}'")
            stack.pop()
            i += 1
        else:
            raise BvhError("BAD_HIERARCHY", f"{name}: unexpected token '{tok}'")
    if stack or not joints:
        raise BvhError("BAD_HIERARCHY", f"{name}: hierarchy is empty or not closed")
    seen: set[str] = set()
    for joint in joints:
        if joint.name in seen:
            raise BvhError("DUPLICATE_JOINT", f"{name}: joint name '{joint.name}' appears twice", joint=joint.name)
        seen.add(joint.name)
    return joints


def _parse_motion_header(lines: list[str], motion_line: int, name: str) -> tuple[int, float, int]:
    frames = frame_time = None
    k = motion_line + 1
    while k < len(lines) and (frames is None or frame_time is None):
        line = lines[k].strip()
        k += 1
        if not line:
            continue
        key, _, value = line.partition(":")
        try:
            if key.strip().lower() == "frames":
                frames = int(value)
            elif key.strip().lower() == "frame time":
                frame_time = float(value)
            else:
                break
        except ValueError:
            raise BvhError("BAD_MOTION_HEADER", f"{name}: bad '{line}'") from None
    if frames is None or frame_time is None or frames < 1 or not frame_time > 0:
        raise BvhError("BAD_MOTION_HEADER", f"{name}: MOTION needs 'Frames: N' (N >= 1) and 'Frame Time: t' (t > 0)")
    return frames, frame_time, k


def _warnings(joints: list[Joint], frames: int, rows: int) -> list[dict]:
    out = []
    moving = [j.name for j in joints[1:] if any(c.lower().endswith("position") for c in j.channels)]
    if moving:
        out.append({"code": "JOINT_POSITION_CHANNELS", "message": f"{len(moving)} non-root joint(s) have position channels — "
                    "Blender keeps them only on unconnected bones", "joints": moving[:10]})
    spaced = [j.name for j in joints if ":" in j.name]
    if spaced:
        out.append({"code": "NAMESPACED_NAMES", "message": "joint names with ':' lose the namespace on FBX import (bKeepFbxNamespace=false)",
                    "joints": spaced[:10]})
    if rows > frames:
        out.append({"code": "EXTRA_ROWS", "message": f"{rows} data rows for {frames} frames — the extra rows are ignored"})
    return out


# ---- 기준 포즈 · 좌표 ----
def axis_matrix(forward: str = "-Z", up: str = "Y") -> tuple[tuple[float, ...], ...]:
    """BVH 좌표 → Blender 좌표 행렬의 행(right, forward, up). Blender axis_conversion 과 같은 규칙: forward → +Y, up → +Z, x = y × z."""
    f, u = _signed_axis(forward), _signed_axis(up)
    if abs(sum(a * b for a, b in zip(f, u))) > 1e-9:
        raise BvhError("BAD_AXES", f"axis_forward {forward} and axis_up {up} must be different axes")
    r = (f[1] * u[2] - f[2] * u[1], f[2] * u[0] - f[0] * u[2], f[0] * u[1] - f[1] * u[0])
    return r, f, u


def _signed_axis(text: str) -> tuple[float, float, float]:
    text = (text or "").strip().upper()
    sign = -1.0 if text.startswith("-") else 1.0
    vec = _AXIS_VEC.get(text.lstrip("+-"))
    if vec is None:
        raise BvhError("BAD_AXES", f"axis '{text}' must be one of X, Y, Z, -X, -Y, -Z")
    return tuple(sign * v for v in vec)


def to_ue(p, matrix) -> tuple[float, float, float]:
    """BVH 점 → UE 좌표(Blender → UE 는 y 뒤집기)."""
    bx, by, bz = (sum(row[k] * p[k] for k in range(3)) for row in matrix)
    return bx, -by, bz


def rest_segments(info: BvhInfo, forward: str = "-Z", up: str = "Y") -> list[tuple[tuple, tuple]]:
    """기준 포즈(회전 0)의 부모 → 자식 · 관절 → End Site 선분, UE 좌표(BVH 단위)."""
    matrix = axis_matrix(forward, up)
    heads: list[tuple[float, float, float]] = []
    for joint in info.joints:
        base = heads[joint.parent] if joint.parent >= 0 else (0.0, 0.0, 0.0)
        heads.append(tuple(b + o for b, o in zip(base, joint.offset)))
    segments = []
    for k, joint in enumerate(info.joints):
        if joint.parent >= 0:
            segments.append((to_ue(heads[joint.parent], matrix), to_ue(heads[k], matrix)))
        if joint.end_site is not None:
            tail = tuple(h + e for h, e in zip(heads[k], joint.end_site))
            segments.append((to_ue(heads[k], matrix), to_ue(tail, matrix)))
    if not segments:  # 관절 하나뿐
        segments.append((to_ue(heads[0], matrix), to_ue(heads[0], matrix)))
    return segments


def skeleton_segments(bones: list[dict]) -> list[tuple[tuple, tuple]]:
    """inspect_skeleton(details) 의 bones[{name, parent, ref_component{t}}] → 부모 → 자식 선분 (UE 컴포넌트 좌표, cm)."""
    pos = {b["name"]: tuple(b["ref_component"]["t"]) for b in bones if b.get("ref_component")}
    return [(pos[b["parent"]], pos[b["name"]]) for b in bones if b.get("parent") in pos and b["name"] in pos]


def height(segments) -> float:
    zs = [p[2] for seg in segments for p in seg]
    return max(zs) - min(zs)


# ---- 단위 ----
def resolve_unit(unit, rest_height_units: float) -> dict:
    """unit = auto | cm | m | mm | inch | 숫자(cm/단위). auto 는 기준 포즈 키가 사람 키가 되는 표준 단위, 없으면 키를 170cm 로 정규화."""
    if isinstance(unit, (int, float)) and not isinstance(unit, bool):
        if unit <= 0:
            raise BvhError("BAD_UNIT", "unit as a number is centimeters per BVH unit and must be > 0")
        mode, factor, normalized = "explicit", float(unit), False
    elif unit in UNITS_CM:
        mode, factor, normalized = unit, UNITS_CM[unit], False
    elif unit in (None, "auto"):
        if rest_height_units <= 0:
            raise BvhError("BAD_UNIT", "the rest pose has no height — give unit explicitly")
        lo, hi = HUMAN_HEIGHT_CM
        found = next((u for u, f in UNITS_CM.items() if lo <= rest_height_units * f <= hi), None)
        if found:
            mode, factor, normalized = f"auto:{found}", UNITS_CM[found], False
        else:
            mode, factor, normalized = "auto:normalized", NORMALIZED_HEIGHT_CM / rest_height_units, True
    else:
        raise BvhError("BAD_UNIT", f"unit must be auto, {', '.join(UNITS_CM)} or a number (cm per unit) — got {unit!r}")
    return {"mode": mode, "cm_per_unit": round(factor, 6), "normalized": normalized,
            "rest_height_units": round(rest_height_units, 4), "rest_height_cm": round(rest_height_units * factor, 2)}


# ---- 정면 방향 ----
def _vertical_range(zs: list[float]) -> tuple[float, float, int]:
    """바닥 · 꼭대기 — p5 ~ p95 폭보다 더 떨어진 외톨이 본은 뺀다(SB 의 FX 본이 z −2217cm 에 있어 발 영역이 비었다). 뺀 점 수도."""
    s = sorted(zs)
    lo, hi = s[int(0.05 * (len(s) - 1))], s[int(0.95 * (len(s) - 1))]
    margin = OUTLIER_MARGIN * (hi - lo)
    kept = [z for z in s if lo - margin <= z <= hi + margin]
    return kept[0], kept[-1], len(s) - len(kept)


def _nearest_axis(sx: float, sy: float, scale: float, empty_reason: str) -> dict:
    if scale <= 0 or math.hypot(sx, sy) < 1e-3 * scale:
        return {"axis": None, "reason": empty_reason, "vector": [round(sx, 3), round(sy, 3)], "deviation_deg": None}
    angle = math.degrees(math.atan2(sy, sx))
    best, deviation = min(((name, abs(_wrap(angle - math.degrees(math.atan2(v[1], v[0]))))) for name, v in AXES_UE.items()),
                          key=lambda item: item[1])
    ok = deviation <= AXIS_TOLERANCE_DEG
    return {"axis": best if ok else None, "reason": None if ok else "OFF_AXIS", "vector": [round(sx, 3), round(sy, 3)],
            "angle_deg": round(angle, 2), "deviation_deg": round(deviation, 2)}


def facing(segments) -> dict:
    """발 영역(바닥 + 키 × 15% 아래)에 양 끝이 다 있는 선분의 수평 벡터 합 — 좌우 대칭 성분(IK 발 루트 → 양발 등)은 상쇄되고
    발목 → 발가락 방향만 남는다. 가장 가까운 UE 축으로 맞추고, 30° 넘게 벗어나면 axis = None."""
    floor, top, outliers = _vertical_range([p[2] for seg in segments for p in seg])
    h = top - floor
    limit = floor + FOOT_REGION * h
    sx = sy = 0.0
    for a, b in segments:
        if floor <= a[2] <= limit and floor <= b[2] <= limit:
            sx += b[0] - a[0]
            sy += b[1] - a[1]
    return {**_nearest_axis(sx, sy, h, "NO_FOOT_SEGMENTS"), "outliers": outliers}


def lateral_facing(positions: dict[str, tuple], chains: list[dict]) -> dict:
    """좌우 체인(이름 Left*/Right* 쌍)의 시작 본 위치 차 = 왼쪽 방향 L → 정면 = L 을 +Z 로 90° 돌린 (−L.y, L.x)
    (UE 마네킹 · Vesper: 왼쪽 +X · 정면 +Y). 발 모양과 무관한 교차 확인 — 쌍이 없으면 axis = None."""
    by_name = {c["name"].lower(): c for c in chains or [] if c.get("name") and c.get("start")}
    lx = ly = 0.0
    pairs = []
    for name, chain in by_name.items():
        if not name.startswith("left"):
            continue
        right = by_name.get("right" + name[4:])
        if right and chain["start"] in positions and right["start"] in positions:
            a, b = positions[chain["start"]], positions[right["start"]]
            lx += a[0] - b[0]
            ly += a[1] - b[1]
            pairs.append(chain["name"])
    out = _nearest_axis(-ly, lx, math.hypot(lx, ly) or 0.0, "NO_LEFT_RIGHT_CHAINS")
    return {**out, "pairs": sorted(pairs)}


def bone_positions(bones: list[dict]) -> dict[str, tuple]:
    """inspect_skeleton(details) 의 bones → {이름: 컴포넌트 위치}."""
    return {b["name"]: tuple(b["ref_component"]["t"]) for b in bones if b.get("ref_component")}


def ue_yaw_deg(source_axis: str, target_axis: str) -> float:
    """source(UE 축)를 target 으로 돌리는 +Z 회전(도) — FQuat(UpVector, yaw) 와 같은 부호(+X → +Y 가 +90). (-180, 180]."""
    sx, sy = AXES_UE[source_axis]
    tx, ty = AXES_UE[target_axis]
    deg = round(math.degrees(math.atan2(sx * ty - sy * tx, sx * tx + sy * ty)), 6) + 0.0
    return 180.0 if deg <= -180.0 else deg


def blender_rotation_deg(source_axis: str, target_axis: str) -> float:
    """source(UE 축)를 target(UE 축)으로 돌리는 Blender Z 회전(도, 오른손). UE (x, y) = Blender (x, -y) 라 부호가 UE 요와 반대다."""
    sx, sy = AXES_UE[source_axis]
    tx, ty = AXES_UE[target_axis]
    sy, ty = -sy, -ty
    deg = round(math.degrees(math.atan2(sx * ty - sy * tx, sx * tx + sy * ty)), 6) + 0.0
    return 180.0 if deg <= -180.0 else deg  # (-180, 180] — 반 바퀴는 항상 +180


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


# ---- 범위 ----
def frame_range(info: BvhInfo, rng: dict | None) -> dict:
    """{start, end}(초) → BVH 프레임 [first, last] (0 기준, 양 끝 포함). 없으면 전체."""
    last = info.frames - 1
    if not rng:
        return {"first": 0, "last": last, "frames": info.frames, "duration": round(info.duration, 4)}
    start, end = rng.get("start", 0.0), rng.get("end", info.duration)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (start, end)) or not 0 <= start < end:
        raise BvhError("BAD_RANGE", f"range needs 0 <= start < end (seconds), got {rng}")
    first = int(round(start / info.frame_time))
    stop = min(int(round(end / info.frame_time)), last)
    if first >= stop:
        raise BvhError("BAD_RANGE", f"range {rng} is outside the clip (0 .. {info.duration:.3f}s)", duration=round(info.duration, 4))
    return {"first": first, "last": stop, "frames": stop - first + 1, "duration": round((stop - first) * info.frame_time, 4)}


def align_to_rate(frames: dict, fps: float, rate: float | None) -> dict:
    """요청 rate 로 리샘플할 때 길이를 그 rate 의 프레임 경계에 맞춘다 — 경계에 안 맞으면 Interchange 가 시작·끝을 가까운 프레임으로
    반올림해 길이가 반 프레임까지 늘거나 준다(import_animation_file 이 bSnapToClosestFrameBoundary 를 켬, LENGTH_SNAPPED —
    InterchangeGenericAnimationPipeline.cpp:751-807). 대신 끝을 몇 소스 프레임 당겨(fps/gcd 미만) 소스 프레임 그대로 끝나게 한다.
    정수 fps 가 아니면 맞출 수 없어 unaligned — 리샘플하지 않는다."""
    out = dict(frames, aligned_to=None, trimmed_frames=0, unaligned=False)
    if not rate or abs(rate - fps) < 1e-6:
        return out
    if fps != int(fps) or rate != int(rate):
        out["unaligned"] = True
        return out
    unit = int(fps) // math.gcd(int(fps), int(rate))
    span = frames["last"] - frames["first"]
    aligned = span // unit * unit
    if aligned <= 0:
        raise BvhError("BAD_RANGE", f"the clip ({span + 1} frames at {fps:g} fps) is shorter than one frame at {rate:g} fps")
    out.update(last=frames["first"] + aligned, frames=aligned + 1, duration=round(aligned / fps, 4), aligned_to=rate, trimmed_frames=span - aligned)
    return out


def summary(info: BvhInfo) -> dict:
    """계획에 고정해 보여 줄 헤더 요약 — 관절 계층은 수동 체인(retarget.source_chains) 제안용."""
    return {"joints": [{"name": j.name, "parent": info.joints[j.parent].name if j.parent >= 0 else None} for j in info.joints],
            "joint_count": len(info.joints), "root": info.joints[0].name, "end_sites": sum(1 for j in info.joints if j.end_site is not None),
            "channels": info.channel_count, "frames": info.frames, "frame_time": info.frame_time, "fps": round(info.fps, 4),
            "duration": round(info.duration, 4), "warnings": info.warnings}
