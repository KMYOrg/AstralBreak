"""Phase 8-4b — body_fit 테스트용 합성 몸 모델(C++ body_clearance{model, hands} 모양). 8-4a model_fixture 보다 크다: 양팔(쇄골 · 손가락 한 마디) ·
척추 3마디 · 목 · 머리 · 두 다리 · 손 · 아래팔 지도(hands).

골격(기준 포즈 로컬 회전 = 항등 — 점 영향 로컬 위치 = 점 − 본 기준 위치): 몸 왼쪽 = +X, 앞 = +Y, 위 = +Z(Vesper 와 같다). 팔은 몸 옆(x ±18)으로 내려뜨림.
프레임 = {본: 부모 공간 회전 벡터(°)} · 선택 "pelvis_t": 이동(cm). 지도는 프레임마다 그 포즈로 축을 잡고 반경은 고정(원통):
몸통 = 엉덩 중점 → 척추 끝 반경 10, 넓적다리 = 엉덩 → 무릎 6.5, 머리목 = 목 → 머리 + 15 반경 8, 손 = 손목 → 손 로컬 (0, 0, −10) 반경 2.5,
아래팔 = 팔꿈치 → 손목 반경 3.5.
"""
from __future__ import annotations

import math

from model_fixture import f32, i16

from anim_gen import body_model as bm

BONES = []
PARENTS = []
REST = []


def _bone(name: str, parent: str | None, t) -> None:
    BONES.append(name)
    PARENTS.append(BONES.index(parent) if parent else -1)
    REST.append(tuple(float(x) for x in t))


_bone("root", None, (0, 0, 0))
_bone("pelvis", "root", (0, 0, 95))
_bone("spine_01", "pelvis", (0, 0, 10))
_bone("spine_02", "spine_01", (0, 0, 15))
_bone("spine_05", "spine_02", (0, 0, 20))
_bone("neck_01", "spine_05", (0, 0, 8))
_bone("head", "neck_01", (0, 0, 10))
for _s, _x in (("l", 1.0), ("r", -1.0)):
    _bone(f"clavicle_{_s}", "spine_05", (4 * _x, 0, 0))
    _bone(f"upperarm_{_s}", f"clavicle_{_s}", (14 * _x, 0, 0))
    _bone(f"lowerarm_{_s}", f"upperarm_{_s}", (0, 0, -26))
    _bone(f"hand_{_s}", f"lowerarm_{_s}", (0, 0, -26))
    _bone(f"middle_01_{_s}", f"hand_{_s}", (0, 0, -8))
for _s, _x in (("l", 1.0), ("r", -1.0)):
    _bone(f"thigh_{_s}", "pelvis", (9 * _x, 0, -5))
    _bone(f"calf_{_s}", f"thigh_{_s}", (0, 0, -42))
    _bone(f"foot_{_s}", f"calf_{_s}", (0, 0, -40))

HEAD_TOP_LOCAL = (0.0, 0.0, 15.0)
HAND_TIP_LOCAL = (0.0, 0.0, -10.0)
RADIUS = {"torso": 10.0, "thigh": 5.0, "head_neck": 8.0, "hand": 2.5, "forearm": 3.5}


def fk(frame: dict) -> list:
    """컴포넌트 공간 (q, t, s) — 로컬 = Q(회전 벡터°) ⊗ 항등, 펠비스 이동 = pelvis_t."""
    out = []
    for b, (p, t) in enumerate(zip(PARENTS, REST)):
        q = bm.from_rotvec_deg(frame.get(BONES[b], (0.0, 0.0, 0.0)))
        if BONES[b] == "pelvis" and frame.get("pelvis_t"):
            t = bm._add(t, tuple(frame["pelvis_t"]))
        local = (q, t, (1.0, 1.0, 1.0))
        out.append(local if p < 0 else bm.compose(local, out[p]))
    return out


def rest_pos(bone: str):
    return fk({})[BONES.index(bone)][1]


def _points() -> list:
    pts = []

    def add(side, part, bone, offs):
        b = BONES.index(bone)
        base = rest_pos(bone)
        for o in offs:
            pts.append({"side": side, "part": part, "dominant": b, "ref_cm": list(bm._add(base, o)), "influences": [[b, 1.0, *o]]})
    for s in ("l", "r"):
        ring = [(r * math.cos(a), r * math.sin(a)) for r in (2.0,) for a in (k * math.pi / 3 for k in range(6))]
        add(s, "hand", f"hand_{s}", [(x, y, z) for x, y in ring for z in (0.0, -3.0, -6.0)])
        ring = [(3.0 * math.cos(a), 3.0 * math.sin(a)) for a in (k * math.pi / 4 for k in range(8))]
        add(s, "forearm", f"lowerarm_{s}", [(x, y, z) for x, y in ring for z in (-5.0, -12.0, -19.0)])
        add(s, "upper_arm", f"upperarm_{s}", [(x, y, z) for x, y in ring for z in (-14.0, -20.0)])
    return pts


def _axis_frame(a, b, lateral):
    d = bm._sub(b, a)
    length = bm._norm(d)
    d = bm._scale(d, 1.0 / length)
    x = bm._sub(lateral, bm._scale(d, bm._dot(lateral, d)))
    if bm._norm(x) < 1e-6:
        x = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
        x = bm._sub(x, bm._scale(d, bm._dot(x, d)))
    x = bm._scale(x, 1.0 / bm._norm(x))
    return [*a, *d, *x, length]


def make_model(frames: list[dict] | None = None, *, poses: list | None = None, hands: bool = True, fps: float = 30.0) -> dict:
    """frames(본 → 회전 벡터°) 또는 poses(프레임별 컴포넌트 (q, t, s) — bone_deltas 를 적용한 뒤 애셋 흉내)로 모델 JSON."""
    all_poses = poses if poses is not None else [fk(fr) for fr in frames]
    poses_f32, maps = [], {}
    defs = {"torso": (-0.25, 1.05, 40, "torso"), "thigh_l": (-0.15, 1.0, 30, "thigh"), "thigh_r": (-0.15, 1.0, 30, "thigh"),
            "head_neck": (-0.1, 1.0, 24, "head_neck")}
    if hands:
        defs.update({"hand_l": (-0.15, 1.05, 12, "hand"), "hand_r": (-0.15, 1.05, 12, "hand"), "forearm_l": (-0.1, 1.05, 14, "forearm"),
                     "forearm_r": (-0.1, 1.05, 14, "forearm")})
    for name in defs:
        maps[name] = {"axis": [], "radius": []}
    idx = BONES.index
    for pose in all_poses:
        for q, t, s in pose:
            poses_f32 += [*q, *t, *s]
        pos = lambda b: pose[idx(b)][1]  # noqa: E731
        lateral = bm._sub(pos("upperarm_l"), pos("upperarm_r"))
        axes = {"torso": (bm._scale(bm._add(pos("thigh_l"), pos("thigh_r")), 0.5), pos("spine_05")),
                "thigh_l": (pos("thigh_l"), pos("calf_l")), "thigh_r": (pos("thigh_r"), pos("calf_r")),
                "head_neck": (pos("neck_01"), bm.transform_point(pose[idx("head")], HEAD_TOP_LOCAL))}
        if hands:
            for s in ("l", "r"):
                axes[f"hand_{s}"] = (pos(f"hand_{s}"), bm.transform_point(pose[idx(f"hand_{s}")], HAND_TIP_LOCAL))
                axes[f"forearm_{s}"] = (pos(f"lowerarm_{s}"), pos(f"hand_{s}"))
        for name, (lo, hi, bins, kind) in defs.items():
            a, b = axes[name]
            maps[name]["axis"] += _axis_frame(a, b, lateral)
            maps[name]["radius"] += [RADIUS[kind]] * (bins * 36)
    labels = []
    for t in range(40):
        c = -0.25 + (t + 0.5) / 40 * 1.3
        labels.append("pelvis" if c < 0.2 else "belly" if c < 0.5 else "chest")
    maps_out = []
    for name, (lo, hi, bins, _) in defs.items():
        item = {"part": name, "t_min": lo, "t_max": hi, "t_bins": bins, "angle_bins": 36, "axis_b64": f32(maps[name]["axis"]), "radius_unit_cm": 0.01,
                "radius_b64": i16(maps[name]["radius"])}
        if name == "torso":
            item["part_of_t_bin"] = labels
        maps_out.append(item)
    n = len(all_poses)
    return {"version": 1, "mesh": "/Game/Test/SK_Synthetic", "scale": 0.95, "contact_cm": 0.95, "penetration_cm": 1.9, "fps": fps, "frames_total": n,
            "frames": list(range(n)), "times": [i / fps for i in range(n)], "bones": {"names": list(BONES), "parents": list(PARENTS)},
            "roles": {"arms": [{"side": s, "clavicle": f"clavicle_{s}", "upper": f"upperarm_{s}", "elbow": f"lowerarm_{s}", "wrist": f"hand_{s}", "twist": []}
                               for s in ("l", "r")],
                      "legs": [{"side": s, "thigh": f"thigh_{s}", "knee": f"calf_{s}", "foot": f"foot_{s}"} for s in ("l", "r")],
                      "pelvis": "pelvis", "spine_top": "spine_05", "spine": ["spine_01", "spine_02", "spine_05"], "neck_root": "neck_01", "head": "head",
                      "head_top_local_cm": list(HEAD_TOP_LOCAL)},
            "poses": {"layout": "f32 [frame][bone] qx qy qz qw tx ty tz sx sy sz", "b64": f32(poses_f32)},
            "influence_layout": "[bone, weight, local_x, local_y, local_z]", "points": _points(), "torso_t_bounds": {"belly": 0.2, "chest": 0.5},
            "leg_thigh_t_min": 0.2, "maps": maps_out, "b64_bytes": 0, "seconds": 0.0}


def blend(a: dict, b: dict, w: float) -> dict:
    keys = set(a) | set(b)
    return {k: tuple(x + (y - x) * w for x, y in zip(a.get(k, (0.0, 0.0, 0.0)), b.get(k, (0.0, 0.0, 0.0)))) for k in keys}


def bump(base: dict, peak: dict, n: int = 30, lo: int = 12, hi: int = 17, ramp: int = 5) -> list[dict]:
    """base → (ramp 프레임 동안 선형) → peak(lo ~ hi) → base — 이어지는 동작(실제 애니처럼 프레임 사이가 매끈)."""
    out = []
    for i in range(n):
        w = 1.0 if lo <= i <= hi else (i - (lo - ramp)) / ramp if lo - ramp <= i < lo else ((hi + ramp) - i) / ramp if hi < i <= hi + ramp else 0.0
        out.append(blend(base, peak, w))
    return out


def pairs_cpp(model: dict, poses: list | None = None) -> dict:
    """C++ body_clearance parts{pairs[], hands{pairs[]}} 모양 — body_fit.measure(같은 지도 규칙)로."""
    from anim_gen import body_fit as bf
    m = bf.measure(bm.BodyModel(model), poses)
    body, hands = [], []
    for key, st in m["pairs"].items():
        side, part, body_part = key.split("|")
        item = {"side": side, "arm_part": part, "body_part": body_part, "frames_over_contact_pct": st["frames_over_contact_pct"],
                "frames_over_penetration_pct": st["frames_over_penetration_pct"], "depth_p50": st["depth_p50"], "depth_p95": st["depth_p95"],
                "depth_max": st["depth_max"], "located_pct": st["located_pct"], "worst": {}}
        (hands if body_part.startswith(("hand_", "forearm_")) else body).append(item)
    return {"pairs": body, "hands": {"pairs": hands}}


def into_body(deg: float) -> dict:
    """왼 위팔을 앞 축(+Y) 둘레로 deg° — 손 · 아래팔이 몸통 쪽(−X)으로 든다(18° 면 손이 골반 · 넓적다리 안 ≈ 10 cm)."""
    return {"upperarm_l": (0.0, deg, 0.0)}


def grip_front(extra: dict | None = None) -> dict:
    """양손을 가슴 앞(y ≈ 43)에서 모은 자세 — 위팔을 앞으로 들고(+X 축 둘레 60°) 안으로 22°, 팔꿈치 60°. 두 손목 간격 8 cm, 몸과 떨어짐."""
    f = {"upperarm_l": (60.0, 0.0, 22.0), "lowerarm_l": (60.0, 0.0, 0.0), "upperarm_r": (60.0, 0.0, -22.0), "lowerarm_r": (60.0, 0.0, 0.0)}
    f.update(extra or {})
    return f


def grip_close(extra: dict | None = None) -> dict:
    """양손을 배 앞에 붙여 모은 자세 — 손 · 아래팔이 몸통 원통을 ≈ 2.6 cm 뚫는다(손목 (±5.9, 8.6, 114)), 두 손목 간격 11.8 cm(파지 띠 안),
    손끼리는 떨어짐."""
    f = {"upperarm_l": (-30.0, 0.0, 20.0), "lowerarm_l": (110.0, 0.0, 20.0), "upperarm_r": (-30.0, 0.0, -20.0), "lowerarm_r": (110.0, 0.0, -20.0)}
    f.update(extra or {})
    return f
