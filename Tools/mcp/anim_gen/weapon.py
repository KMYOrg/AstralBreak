"""Phase 8-4c — 손에 든 무기(요청 weapon): 요청 정규화 · 메시 사실(플러그인 inspect_skeleton)로 무기 공간 값 풀기 (순수 Python — numpy 없음).

플러그인 · anim_gen 은 장비 데이터(DA)를 읽지 않는다 — 배치(부착 소켓 · offset) · 손잡이(선분 · 소켓) · 보조 손 회전 · 무기 끝은 요청이 준다
(Claude Code 가 장비 데이터를 읽어 넣는다 — 지침서 §8). 소켓 변환 · 무기 메시 기하 · 손가락 체인은 메시 사실이라 플러그인 inspect_skeleton 결과를 읽는다:

  부착      — 무기 메시 공간 → 부착 본(소켓의 본) 공간 = compose(offset, 소켓 상대) (UE: 무기 메시 = AttachOffset · AttachTransform · 소켓 · 손 본 —
              E0 · capture_animation attachments 와 같은 식). attach.bone 이면 소켓 = 항등.
  손잡이    — 무기 메시 공간 선분(from → to — 보조 손바닥 점이 미끄러질 수 있다). socket 이면 길이 0(소켓 회전 = 보조 손 회전), sockets 면 두 소켓 위치.
              소켓은 무기 본 상대라 그 본의 기준 포즈(ref_component)로 메시 공간에 옮긴다.
  보조 손   — 손바닥 점 = 손목 · 가운데 손가락 뿌리 중점(손가락 체인 제안 {Side}Middle 시작 — 이름 추측 아님, E0 와 같은 점). 회전 = 무기 공간
              쿼터니언(x, y, z, w) ± rotation_tol_deg, null(기본)이면 그 클립의 원래 상대 회전(운영 낫 왼손은 자루를 감아 쥐지 않아 한 회전 근거가
              없다 — 8-4c 실측). 쥠 축(검지 → 새끼 뿌리)은 기록만.
  기록 점   — 무기-몸 관통 기록(제약 아님)용 geometry 단면 근사: 자루 = 좁은 단면 중심 직선(handle_line — E0 와 같은 규칙) 위 점 + 반경, 그 밖
              단면(날 · 머리)은 둘째 축 방향 격자(두께의 절반 = 반경) — 단면 상자를 채운 것으로 보므로 휜 날은 과대로 잡힐 수 있다.
"""
from __future__ import annotations

import copy
import math

from . import body_model as bm

SIDES = {"left": "l", "right": "r"}
KEYS = {"mesh", "attach", "lead_hand", "grips", "tip"}
GRIP_KEYS = {"hand", "segment", "socket", "sockets", "rotation", "rotation_tol_deg", "runtime_ik"}
GRIP_DEFAULTS = {"rotation": None, "rotation_tol_deg": 10.0, "runtime_ik": False}
HANDLE_MAX_WIDTH_CM = 20.0    # 자루 = 정점이 있고 둘째 · 셋째 축 폭이 이 안인 단면(날 단면은 100 cm 넘는다 — E0 와 같은 값)
RECORD_STEP_CM = 5.0          # 기록 점 간격
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")


class WeaponError(ValueError):
    """요청 weapon · 메시 사실 오류 — (필드, 메시지, reason)."""

    def __init__(self, field: str, message: str, reason: str = "BAD_FIELD"):
        super().__init__(field, message)
        self.field, self.message, self.reason = field, message, reason


def _num(v, lo: float = -1e5, hi: float = 1e5) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _vec(v, n: int = 3) -> bool:
    return isinstance(v, list) and len(v) == n and all(_num(x) for x in v)


def _name(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


# ---- 요청 ----
def normalize(raw) -> dict | None:
    """요청 weapon → 기본값을 채운 객체(None 이면 None). 잘못이면 WeaponError(필드, 이유)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise WeaponError("weapon", "must be {mesh, attach{socket | bone, offset?}, lead_hand?, grips?[], tip?}")
    extra = sorted(set(raw) - KEYS)
    if extra:
        raise WeaponError(f"weapon.{extra[0]}", f"unknown key — allowed {sorted(KEYS)}", "UNKNOWN_FIELD")
    w = copy.deepcopy(raw)
    if not _name(w.get("mesh")):
        raise WeaponError("weapon.mesh", "must be the weapon SkeletalMesh path", "MISSING_FIELD")
    att = w.get("attach")
    if not isinstance(att, dict) or set(att) - {"socket", "bone", "offset"} or len({"socket", "bone"} & set(att)) != 1 or not _name(att.get("socket") or att.get("bone")):
        raise WeaponError("weapon.attach", "must be {socket | bone, offset?{location, rotation[pitch, yaw, roll], scale}} — DA AttachSocket · AttachOffset ∘ AttachTransform")
    off = att.get("offset") or {}
    if not isinstance(off, dict) or set(off) - {"location", "rotation", "scale"}:
        raise WeaponError("weapon.attach.offset", "must be {location?, rotation?, scale?}")
    att["offset"] = {"location": off.get("location", [0.0, 0.0, 0.0]), "rotation": off.get("rotation", [0.0, 0.0, 0.0]), "scale": off.get("scale", [1.0, 1.0, 1.0])}
    for key, value in att["offset"].items():
        if not _vec(value) or (key == "scale" and min(value) <= 0):
            raise WeaponError(f"weapon.attach.offset.{key}", "must be [x, y, z] numbers (scale > 0)")
    w["attach"] = att
    w["lead_hand"] = w.get("lead_hand", "right")
    if w["lead_hand"] not in SIDES:
        raise WeaponError("weapon.lead_hand", "must be left | right (the hand the weapon is attached to)")
    grips = w.get("grips", [])
    if not isinstance(grips, list):
        raise WeaponError("weapon.grips", "must be a list")
    out = []
    for i, g in enumerate(grips):
        out.append(_grip(i, g, w["lead_hand"]))
    hands = [g["hand"] for g in out]
    if len(set(hands)) != len(hands):
        raise WeaponError("weapon.grips", "one grip per hand", "DUPLICATE_ID")
    w["grips"] = out
    tip = w.get("tip")
    if tip is not None and not (isinstance(tip, dict) and len(tip) == 1 and (_name(tip.get("socket")) or _vec(tip.get("point_cm")))):
        raise WeaponError("weapon.tip", "must be null, {socket: name} or {point_cm: [x, y, z]} (weapon mesh space)")
    w["tip"] = tip
    return w


def _grip(i: int, raw, lead: str) -> dict:
    where = f"weapon.grips[{i}]"
    if not isinstance(raw, dict):
        raise WeaponError(where, "must be an object")
    extra = sorted(set(raw) - GRIP_KEYS)
    if extra:
        raise WeaponError(f"{where}.{extra[0]}", f"unknown key — allowed {sorted(GRIP_KEYS)}", "UNKNOWN_FIELD")
    g = {**copy.deepcopy(GRIP_DEFAULTS), **copy.deepcopy(raw)}
    if g.get("hand") not in SIDES:
        raise WeaponError(f"{where}.hand", "must be left | right")
    if g["hand"] == lead:
        raise WeaponError(f"{where}.hand", "the lead hand holds the weapon by its attach socket — grips are for the other hand")
    forms = [k for k in ("segment", "socket", "sockets") if g.get(k) is not None]
    if len(forms) > 1:
        raise WeaponError(where, "give one of segment | socket | sockets", "CONFLICTING_FIELDS")
    seg = g.get("segment")
    if seg is not None and not (isinstance(seg, dict) and set(seg) == {"from", "to"} and _vec(seg["from"]) and _vec(seg["to"])):
        raise WeaponError(f"{where}.segment", "must be {from: [x, y, z], to: [x, y, z]} (weapon mesh space cm)")
    if g.get("socket") is not None and not _name(g["socket"]):
        raise WeaponError(f"{where}.socket", "must be a weapon mesh socket name")
    if g.get("sockets") is not None and not (isinstance(g["sockets"], list) and len(g["sockets"]) == 2 and all(_name(s) for s in g["sockets"])):
        raise WeaponError(f"{where}.sockets", "must be [from_socket, to_socket]")
    rot = g["rotation"]
    if rot is not None:
        if not _vec(rot, 4) or math.sqrt(sum(x * x for x in rot)) < 1e-6:
            raise WeaponError(f"{where}.rotation", "must be null or [x, y, z, w] (the hand's rotation in weapon mesh space)")
        g["rotation"] = list(bm.qnormalize(tuple(float(x) for x in rot)))
    if not _num(g["rotation_tol_deg"], 0.0, 90.0):
        raise WeaponError(f"{where}.rotation_tol_deg", "must be a number in [0, 90]")
    if not isinstance(g["runtime_ik"], bool):
        raise WeaponError(f"{where}.runtime_ik", "must be a boolean (true = a runtime IK — e.g. the rifle LeftHandGripSocket — drives this hand)")
    if not forms and not g["runtime_ik"]:
        raise WeaponError(where, "needs segment | socket | sockets (or runtime_ik: true)", "MISSING_FIELD")
    g["form"] = forms[0] if forms else None
    return g


def off_grip(weapon: dict | None) -> dict | None:
    """보조 손(주 손이 아닌 손)의 grip — 없으면 None."""
    if not weapon:
        return None
    return next((g for g in weapon["grips"] if g["hand"] != weapon["lead_hand"]), None)


def attachment(weapon: dict) -> dict:
    """capture_animation attachments 한 항목 — 요청 weapon 의 메시 · 부착 소켓(또는 본) · offset."""
    att = weapon["attach"]
    out = {"mesh": weapon["mesh"], "offset": copy.deepcopy(att["offset"])}
    if att.get("socket"):
        out["socket"] = att["socket"]
    else:
        out["bone"] = att["bone"]
    return out


# ---- 변환 ----
def quat_from_rotator(r) -> tuple:
    """UE FRotator::Quaternion — [pitch, yaw, roll]° → (x, y, z, w)."""
    sp, cp = math.sin(math.radians(r[0]) / 2.0), math.cos(math.radians(r[0]) / 2.0)
    sy, cy = math.sin(math.radians(r[1]) / 2.0), math.cos(math.radians(r[1]) / 2.0)
    sr, cr = math.sin(math.radians(r[2]) / 2.0), math.cos(math.radians(r[2]) / 2.0)
    return (cr * sp * sy - sr * cp * cy, -cr * sp * cy - sr * cp * sy, cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def transform_of(location, rotation_pyr, scale=(1.0, 1.0, 1.0)) -> tuple:
    return (quat_from_rotator(rotation_pyr), tuple(float(v) for v in location), tuple(float(v) for v in scale))


def _socket(info: dict, name: str, owner: str | None = None) -> dict | None:
    for s in info.get("sockets") or []:
        if s.get("name") == name and (owner is None or s.get("owner") == owner):
            return s
    return None


def mesh_socket(info: dict, name: str) -> tuple | None:
    """무기 메시 소켓 → 메시(컴포넌트) 공간 변환 — 소켓 상대 · 그 본의 기준 포즈(ref_component)."""
    s = _socket(info, name, "mesh") or _socket(info, name)
    if s is None or s.get("location") is None:
        return None
    bones = {b.get("name"): b.get("ref_component") or {} for b in info.get("bones") or []}
    ref = bones.get(s.get("bone")) or {}
    parent = transform_of(ref.get("t") or [0.0, 0.0, 0.0], ref.get("r") or [0.0, 0.0, 0.0], ref.get("s") or [1.0, 1.0, 1.0])
    return bm.compose(transform_of(s["location"], s.get("rotation") or [0.0, 0.0, 0.0]), parent)


def handle_line(geometry: dict) -> dict | None:
    """좁은 단면(정점 > 0 · 폭 ≤ HANDLE_MAX_WIDTH_CM) 중심으로 맞춘 자루 선 — 첫 주축 위치 u 에 대한 둘째 · 셋째 축 중심의 최소제곱 직선(E0 와 같은 규칙).
    → point · dir(첫 주축 쪽 부호) · extent(선 위 좌표 [최소, 최대] cm) · radius(그 단면 폭 중 작은 쪽 절반의 중앙값) | 단면이 둘 미만이면 None."""
    a0, a1, a2 = (tuple(a["axis"]) for a in geometry["principal_axes"])
    c = tuple(geometry["centroid"])
    rows = [((s["from_cm"] + s["to_cm"]) / 2.0, s["center_cm"][0], s["center_cm"][1], s) for s in geometry["slices"]["items"]
            if s["vertices"] > 0 and max(s["width_cm"]) <= HANDLE_MAX_WIDTH_CM]
    if len(rows) < 2:
        return None
    n = len(rows)
    mu, m1, m2 = (sum(r[i] for r in rows) / n for i in range(3))
    suu = sum((r[0] - mu) ** 2 for r in rows)
    if suu <= 1e-9:
        return None
    k1 = sum((r[0] - mu) * (r[1] - m1) for r in rows) / suu
    k2 = sum((r[0] - mu) * (r[2] - m2) for r in rows) / suu
    point = bm._add(bm._add(bm._add(c, bm._scale(a0, mu)), bm._scale(a1, m1)), bm._scale(a2, m2))
    v = bm._add(bm._add(a0, bm._scale(a1, k1)), bm._scale(a2, k2))
    length = bm._norm(v)
    extent = ((min(r[3]["from_cm"] for r in rows) - mu) * length, (max(r[3]["to_cm"] for r in rows) - mu) * length)
    radii = sorted(min(r[3]["width_cm"]) / 2.0 for r in rows)
    return {"point": point, "dir": bm._scale(v, 1.0 / length), "extent": extent, "radius": radii[len(radii) // 2],
            "slices": [[r[3]["from_cm"], r[3]["to_cm"], r[3]["vertices"], max(r[3]["width_cm"])] for r in rows]}


def record_points(geometry: dict) -> tuple[list[dict], dict | None]:
    """무기-몸 기록 점(무기 메시 공간) — 자루 선 위 RECORD_STEP_CM 간격(반경 = 자루 반경) + 자루가 아닌 단면의 둘째 축 격자(반경 = 셋째 축 폭 절반)."""
    handle = handle_line(geometry)
    pts = []
    if handle:
        lo, hi = handle["extent"]
        k = max(1, int(math.ceil((hi - lo) / RECORD_STEP_CM)))
        for i in range(k + 1):
            u = lo + (hi - lo) * i / k
            pts.append({"p": list(bm._add(handle["point"], bm._scale(handle["dir"], u))), "r": handle["radius"], "part": "handle"})
    a0, a1, a2 = (tuple(a["axis"]) for a in geometry["principal_axes"])
    c = tuple(geometry["centroid"])
    for s in geometry["slices"]["items"]:
        if s["vertices"] <= 0 or max(s["width_cm"]) <= HANDLE_MAX_WIDTH_CM:
            continue
        u = (s["from_cm"] + s["to_cm"]) / 2.0
        w1, w2 = s["width_cm"]
        k = max(1, int(math.ceil(w1 / RECORD_STEP_CM)))
        for i in range(k + 1):
            v1 = s["center_cm"][0] - w1 / 2.0 + w1 * i / k
            p = bm._add(bm._add(bm._add(c, bm._scale(a0, u)), bm._scale(a1, v1)), bm._scale(a2, s["center_cm"][1]))
            pts.append({"p": list(p), "r": w2 / 2.0, "part": "head"})
    return pts, handle


def _chain_start(chains: list[dict], side: str, finger: str) -> str | None:
    prefix = "Left" if side == "l" else "Right"
    return next((c.get("start") for c in chains if c.get("name") == f"{prefix}{finger}"), None)


def hand_tree(target_info: dict, side: str) -> dict:
    """그 쪽 손가락 체인 시작 본(대상 메시 inspect_skeleton suggest_finger_chains — 이름 추측 없음) → {thumb, index, middle, ring, pinky: 본 | None}."""
    chains = (target_info.get("finger_chain_suggestion") or {}).get("chains") or []
    return {f.lower(): _chain_start(chains, side, f) for f in FINGERS}


def finger_roots(target_info: dict | None) -> dict:
    """손바닥 · 손목 굽힘의 손가락 뿌리 — 쪽마다 {Side}Middle 체인 시작(없는 쪽은 뺀다). body_fit 의 보조 손목 굽힘 상한(8-4c 후속)이 쓴다."""
    out = {}
    for side in ("l", "r"):
        middle = hand_tree(target_info or {}, side)["middle"]
        if middle:
            out[side] = middle
    return out


# ---- 풀기 ----
def resolve(weapon: dict, target_info: dict, weapon_info: dict) -> dict:
    """요청 weapon + 대상 메시 inspect(details · suggest_finger_chains) + 무기 메시 inspect(details · geometry) → body_fit 이 쓰는 값(무기 메시 공간 cm ·
    부착 본 공간 변환). 소켓 · 손가락 체인이 없으면 WeaponError(reason WEAPON_GRIP_UNKNOWN · WEAPON_ATTACH_UNKNOWN · WEAPON_TIP_UNKNOWN)."""
    att = weapon["attach"]
    if att.get("socket"):
        s = _socket(target_info, att["socket"])
        if s is None or s.get("location") is None:
            raise WeaponError("weapon.attach.socket", f"socket {att['socket']} is not on the target mesh / skeleton", "WEAPON_ATTACH_UNKNOWN")
        bone, socket_rel = s["bone"], {"location": s["location"], "rotation": s.get("rotation") or [0.0, 0.0, 0.0]}
    else:
        bone, socket_rel = att["bone"], {"location": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]}
    off = att["offset"]
    local = bm.compose(transform_of(off["location"], off["rotation"], off["scale"]), transform_of(socket_rel["location"], socket_rel["rotation"]))
    lead = SIDES[weapon["lead_hand"]]
    out = {"mesh": weapon["mesh"], "bone": bone, "socket": att.get("socket"), "socket_rel": socket_rel, "offset": copy.deepcopy(off),
           "local": [list(local[0]), list(local[1]), list(local[2])], "lead": lead, "grip": None, "tip": None, "tip_from": None, "hand": None,
           "points": [], "handle": None}
    g = off_grip(weapon)
    if g is not None:
        side = SIDES[g["hand"]]
        item = {"hand": side, "from": None, "to": None, "rotation": g["rotation"], "tol_deg": float(g["rotation_tol_deg"]), "runtime_ik": g["runtime_ik"],
                "form": g["form"]}
        if g["form"] == "segment":
            item["from"], item["to"] = list(g["segment"]["from"]), list(g["segment"]["to"])
        elif g["form"] in ("socket", "sockets"):
            names = [g["socket"]] if g["form"] == "socket" else list(g["sockets"])
            xs = [mesh_socket(weapon_info, n) for n in names]
            missing = [n for n, x in zip(names, xs) if x is None]
            if missing:
                raise WeaponError(f"weapon.grips.{g['hand']}", f"socket(s) {missing} not on {weapon['mesh']}", "WEAPON_GRIP_UNKNOWN")
            item["from"], item["to"] = list(xs[0][1]), list(xs[-1][1])
            if item["rotation"] is None and g["form"] == "socket":
                item["rotation"] = list(xs[0][0])
        if not g["runtime_ik"]:
            hand = hand_tree(target_info, side)
            if not hand["middle"]:
                raise WeaponError(f"weapon.grips.{g['hand']}", f"no {('Left' if side == 'l' else 'Right')}Middle finger chain on the target mesh — "
                                  "the palm point (wrist · middle finger root) needs it", "WEAPON_GRIP_UNKNOWN")
            out["hand"] = hand
        out["grip"] = item
    tip = weapon.get("tip")
    if tip:
        if tip.get("socket"):
            x = mesh_socket(weapon_info, tip["socket"])
            if x is None:
                raise WeaponError("weapon.tip.socket", f"socket {tip['socket']} not on {weapon['mesh']}", "WEAPON_TIP_UNKNOWN")
            out["tip"], out["tip_from"] = list(x[1]), f"socket {tip['socket']}"
        else:
            out["tip"], out["tip_from"] = list(tip["point_cm"]), "point"
    geometry = weapon_info.get("geometry")
    if geometry:
        pts, handle = record_points(geometry)
        out["points"] = pts
        if handle:
            out["handle"] = {"point": [round(v, 3) for v in handle["point"]], "dir": [round(v, 5) for v in handle["dir"]],
                             "extent_cm": [round(v, 2) for v in handle["extent"]], "radius_cm": round(handle["radius"], 2)}
    return out
