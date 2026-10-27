"""Blender 안 보정 op 실행 — 스무딩 · 다리 풀이(발 간격 + 발 고정) (Phase 8-3, anim_gen/fix_ops.py 사전).

bvh_to_fbx.apply_fixes 가 범위를 정한 액션에 부른다(리타깃 전 소스 골격). 여기는 포즈 읽기 · 키 쓰기만 하고 계산은 순수 모듈 —
간격 · 고정 목표 = anim_gen.foot_fix, 2본 IK · 스무딩 = anim_gen.local_ai.refine, 접지 · 치수 · 비교 수치 = anim_gen.motion_metrics.
좌표는 아마추어 공간(= 월드 — rotate 가 회전을 적용해 객체 변환은 단위), 1 BU = 1 cm, 위 = Z.

기준 포즈 → 로컬: 부모가 있으면 pose = P_pose · (P_rest⁻¹ · B_rest) · basis 라 basis = (P_rest⁻¹ · B_rest)⁻¹ · P_pose⁻¹ · pose(회전만 — 이 사슬은
엉덩 관절 · 무릎 · 발목이 연결 본이라 위치는 부모를 따른다). 오일러는 BVH 채널 순서(rotation_mode) 그대로, 앞 프레임과 이어지게(to_euler compat).
"""
from __future__ import annotations

import bpy
from mathutils import Matrix, Vector

from anim_gen import foot_fix
from anim_gen import motion_metrics as mm
from anim_gen.local_ai import refine

UP = 2
SIDES = ("left", "right")


class FixError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _frames() -> list[int]:
    scene = bpy.context.scene
    return list(range(scene.frame_start, scene.frame_end + 1))


def _m3(m) -> list[list[float]]:
    return [[m[i][j] for j in range(3)] for i in range(3)]


def _rot_path(pb) -> str:
    return {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}.get(pb.rotation_mode, "rotation_euler")


def _current(pb):
    mode = pb.rotation_mode
    if mode == "QUATERNION":
        return pb.rotation_quaternion.copy()
    if mode == "AXIS_ANGLE":
        return None
    return pb.rotation_euler.copy()


def sample(arm, names: list[str]) -> dict:
    """프레임별 본 머리 위치(cm) · 전역 회전(3×3) · 로컬 회전 값(이어 쓰기용)."""
    scene = bpy.context.scene
    out = {n: {"pos": [], "rot": [], "local": [], "basis": []} for n in names}
    for f in _frames():
        scene.frame_set(f)
        for n in names:
            pb = arm.pose.bones[n]
            m = pb.matrix
            out[n]["pos"].append([m[0][3], m[1][3], m[2][3]])
            out[n]["rot"].append(_m3(m.to_3x3().normalized()))
            out[n]["local"].append(_current(pb))
            out[n]["basis"].append(_m3(pb.matrix_basis.to_3x3().normalized()))
    return out


def _basis(pb, pose_rot: Matrix, parent_rot: Matrix | None) -> Matrix:
    bone = pb.bone
    if bone.parent is None:
        return bone.matrix_local.to_3x3().inverted() @ pose_rot
    rest_rel = (bone.parent.matrix_local.inverted() @ bone.matrix_local).to_3x3()
    return rest_rel.inverted() @ parent_rot.inverted() @ pose_rot


def _write(pb, basis: Matrix, frame: int, prev):
    """로컬 회전 키 하나 — 앞 값(prev)과 이어지게. 돌려준 값이 다음 prev."""
    mode = pb.rotation_mode
    if mode == "QUATERNION":
        q = basis.to_quaternion()
        if prev is not None and q.dot(prev) < 0:
            q.negate()
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        return q
    if mode == "AXIS_ANGLE":
        axis, angle = basis.to_quaternion().to_axis_angle()
        pb.rotation_axis_angle = (angle, axis.x, axis.y, axis.z)
        pb.keyframe_insert("rotation_axis_angle", frame=frame)
        return None
    e = basis.to_euler(mode, prev) if prev is not None else basis.to_euler(mode)
    pb.rotation_euler = e
    pb.keyframe_insert("rotation_euler", frame=frame)
    return e


def _fps() -> float:
    scene = bpy.context.scene
    return scene.render.fps / scene.render.fps_base


def smooth(arm, op: dict) -> dict:
    """smooth — 로컬 회전(쿼터니언 부호 연속) · 루트 위치 가우시안. from_s ~ to_s 밖 프레임은 그대로."""
    fps = _fps()
    names = [pb.name for pb in arm.pose.bones] if op["bones"] == "all" else list(op["bones"])
    missing = [n for n in names if n not in arm.pose.bones]
    if missing:
        raise FixError("FIX_BONE_MISSING", f"smooth: no bone(s) {missing} in the converted armature")
    frames = _frames()
    before = sample(arm, [pb.name for pb in arm.pose.bones])
    mats = [[before[n]["basis"][t] for n in names] for t in range(len(frames))]
    smoothed = refine.smooth_rotations(mats, op["sigma_frames"])
    lo = op["from_s"] if op["from_s"] is not None else -1.0
    hi = op["to_s"] if op["to_s"] is not None else 1e9
    inside = [lo - 1e-6 <= (f - frames[0]) / fps <= hi + 1e-6 for f in frames]
    for j, n in enumerate(names):
        pb = arm.pose.bones[n]
        prev = None
        for t, f in enumerate(frames):
            if inside[t]:
                prev = _write(pb, Matrix(smoothed[t][j]), f, prev)
            else:
                prev = before[n]["local"][t]
    roots = [pb for pb in arm.pose.bones if pb.parent is None]
    if op["root"]:
        for pb in roots:
            locs = []
            for f in frames:
                bpy.context.scene.frame_set(f)
                locs.append(list(pb.location))
            for t, (f, v) in enumerate(zip(frames, refine.smooth_series(locs, op["sigma_frames"]))):
                if inside[t]:
                    pb.location = v
                    pb.keyframe_insert("location", frame=f)
    after = sample(arm, [pb.name for pb in arm.pose.bones])
    moved = [mm._dist(a, b) for n in after for a, b in zip(before[n]["pos"], after[n]["pos"])]
    return {"op": "smooth", "sigma_frames": op["sigma_frames"], "bones": len(names), "frames_smoothed": sum(inside),
            "joint_moved_cm": {"p95": mm._r(mm.percentile(moved, 0.95)), "max": mm._r(max(moved) if moved else None)}}


def raise_pelvis(arm, pelvis: str, dz: list[float], parent_rot: list | None) -> dict:
    """골반 위치 키에 위 축(Z) 상승 dz[프레임](소스 cm)을 더한다 — 모든 프레임에 키. 위치는 본의 기준 프레임 기준이라: 루트면 기준 포즈 회전의 역,
    부모가 있으면 (부모 포즈 회전 · 기준 상대 회전)의 역으로 옮긴다. 부모에 붙은(connected) 본은 위치가 무시돼 올릴 수 없다(그대로 두고 보고)."""
    pb = arm.pose.bones[pelvis]
    bone = pb.bone
    if bone.use_connect:
        return {"applied": False, "reason": "PELVIS_CONNECTED"}
    rest = bone.matrix_local.to_3x3() if bone.parent is None else (bone.parent.matrix_local.inverted() @ bone.matrix_local).to_3x3()
    scene = bpy.context.scene
    for t, f in enumerate(_frames()):
        scene.frame_set(f)
        frame_rot = rest if parent_rot is None else Matrix(parent_rot[t]) @ rest
        pb.location = pb.location.copy() + frame_rot.inverted() @ Vector((0.0, 0.0, dz[t]))
        pb.keyframe_insert("location", frame=f)
    return {"applied": True}


def legs(arm, ops: list[dict], cfg: dict) -> dict:
    """stance_width + foot_lock — 한 풀이. cfg = {legs{left{hip, knee, ankle}, right{…}}, target_dims(대상 leg_dims) | None}.

    대상 모델(foot_fix.target_model — 대상 엉덩 = s · 소스 골반 + 골반 회전 변화 · 대상 엉덩 오프셋, 다리 = 소스 뼈 방향 · 대상 길이)이 있으면 그
    공간(대상 cm)에서 접지 · 간격 · 고정을 풀고 방향 변화를 소스 뼈에 입힌다 — 리타깃 뒤 대상 발이 고정된다(실측 2026-10-27: 소스 발만 고정하면 대상
    접지 미끄러짐이 줄지 않았다 — 다리 마디 비율 · 골반 이동 배율 차). 보고 before · after = 대상 예측(리타깃 뒤 Job fix.target 실측과 비교),
    source_before · source_after = 소스 실제.
    stance_width keep_knee_bend(8-3 후속): 풀이 공간에서 구한 골반 상승 dz(foot_fix.pelvis_raise)만큼 IK 의 엉덩 관절을 올리고, 소스 골반 위치 키에
    dz / s(대상 모델이면 Pelvis Motion 배율의 역)를 더한다 — 리타깃 뒤 대상 골반이 dz 오르고 상체가 따라 오른다(손 · 머리의 골반 기준 위치 그대로)."""
    fps = _fps()
    bones = cfg.get("legs") or {}
    if not all(bones.get(s, {}).get(k) for s in SIDES for k in ("hip", "knee", "ankle")):
        raise FixError("FIX_LEGS_UNKNOWN", f"leg bones not resolved: {bones}")
    for s in SIDES:
        b = bones[s]
        for name in (b["hip"], b["knee"], b["ankle"]):
            if name not in arm.pose.bones:
                raise FixError("FIX_LEGS_UNKNOWN", f"no bone '{name}' in the converted armature")
        if arm.pose.bones[b["knee"]].parent.name != b["hip"] or arm.pose.bones[b["ankle"]].parent.name != b["knee"]:
            raise FixError("FIX_LEGS_UNKNOWN", f"{s} leg is not a hip → knee → ankle chain: {b}")
    by = {op["op"]: op for op in ops}
    names = [bones[s][k] for s in SIDES for k in ("hip", "knee", "ankle")]
    parents = sorted({arm.pose.bones[bones[s]["hip"]].parent.name for s in SIDES if arm.pose.bones[bones[s]["hip"]].parent})
    # 골반(엉덩 관절의 부모)의 부모 — 골반 상승을 골반 로컬 위치로 옮길 때 그 프레임의 회전
    grand = arm.pose.bones[parents[0]].parent.name if parents and arm.pose.bones[parents[0]].parent else None
    frames = _frames()
    times = [(f - frames[0]) / fps for f in frames]
    data = sample(arm, names + parents + ([grand] if grand else []))
    rest = {n: list(arm.data.bones[n].head_local) for n in names + parents}
    roles = {"hip_l": bones["left"]["hip"], "hip_r": bones["right"]["hip"], "knee_l": bones["left"]["knee"], "knee_r": bones["right"]["knee"],
             "foot_l": bones["left"]["ankle"], "foot_r": bones["right"]["ankle"], "pelvis": parents[0] if parents else None}
    source_dims = mm.leg_dims(rest, roles)
    target_dims = cfg.get("target_dims")
    pelvis = parents[0] if parents else None
    # Blender 아마추어 공간 = UE 소스 좌표의 (x, −y, z) — bvh_to_fbx.measure 와 같은 규칙
    model = foot_fix.target_model(rest[pelvis], UP, target_dims, axes=(1.0, -1.0, 1.0)) if pelvis else None
    r0_inv = arm.data.bones[pelvis].matrix_local.to_3x3().normalized().inverted() if pelvis else None

    def space_hip(d: dict) -> dict:
        """풀이 공간의 엉덩 관절 — 대상 모델이면 골반 위치 · 회전 변화로 예측한 대상 엉덩 관절, 아니면 소스 그대로."""
        if not model:
            return {s: d[bones[s]["hip"]]["pos"] for s in SIDES}
        deltas = [_m3(Matrix(r) @ r0_inv) for r in d[pelvis]["rot"]]
        return {s: [foot_fix.predict_hip(model, s, p, dl) for p, dl in zip(d[pelvis]["pos"], deltas)] for s in SIDES}
    hip = space_hip(data)
    if model:
        leg_cm, w_cm = model["thigh_cm"] + model["shin_cm"], model["hip_width_cm"]
    else:
        leg_cm, w_cm = source_dims["leg_cm"], source_dims["hip_width_cm"]

    def space_leg(d: dict, hips: dict) -> tuple[dict, dict]:
        """풀이 공간의 무릎 · 발목 — 대상 모델이면 예측한 대상 엉덩 관절에서 소스 뼈 방향 · 대상 길이, 아니면 소스 그대로."""
        knee, ankle = {}, {}
        for s in SIDES:
            if not model:
                knee[s], ankle[s] = d[bones[s]["knee"]]["pos"], d[bones[s]["ankle"]]["pos"]
                continue
            pairs = [foot_fix.target_leg(ht, h, k, a, model) for ht, h, k, a in
                     zip(hips[s], d[bones[s]["hip"]]["pos"], d[bones[s]["knee"]]["pos"], d[bones[s]["ankle"]]["pos"])]
            knee[s], ankle[s] = [p[0] for p in pairs], [p[1] for p in pairs]
        return knee, ankle
    vknee, vankle = space_leg(data, hip)
    contact = {k: (by.get("foot_lock") or {}).get(k, d) for k, d in (("height_ratio", mm.CONTACT_HEIGHT_RATIO), ("speed_ratio", mm.CONTACT_SPEED_RATIO),
                                                                      ("min_frames", mm.CONTACT_MIN_FRAMES))}
    contacts = {s: mm.detect_contacts(vankle[s], times, UP, leg_cm, **contact) for s in SIDES}
    out = {"op": "legs", "ops": [op["op"] for op in ops], "bones": bones, "source_dims": source_dims, "target_dims": target_dims,
           "space": "target_model" if model else "source", "scale": model["scale"] if model else 1.0, "contact": contact,
           "contacts": {s: [[a, b] for a, b in mm.runs(contacts[s])] for s in SIDES}}
    stance_cfg = None
    if "stance_width" in by:
        op = by["stance_width"]
        stance_cfg = {"cap_cm": op["max_ratio"] * w_cm, "min_cm": op["min_ratio"] * w_cm, "max_shift_cm": op["max_shift_cm"],
                      "blend_frames": max(1, round(op["blend_s"] * fps)), "keep_knee_bend": op.get("keep_knee_bend", True)}
    lock_cfg = None
    if "foot_lock" in by:
        lock_cfg = {"feet": by["foot_lock"]["feet"], "blend_frames": by["foot_lock"]["blend_frames"]}
    solved = foot_fix.solve(vankle, hip, contacts, up=UP, stance_cfg=stance_cfg, lock_cfg=lock_cfg)
    out["stance"] = solved["stance"]
    out["pins"] = {s: len(p) for s, p in solved["pins"].items()}
    # 무릎 굽힘 유지 — 풀이 공간의 골반 상승 dz 를 소스 골반 위치 키로(대상 모델이면 ÷ s), IK 는 올린 엉덩 관절에서
    hip_ik = hip
    out["pelvis_raise"] = None
    pr = solved.get("pelvis_raise")
    if pr is not None:
        scale = model["scale"] if model else 1.0
        res = raise_pelvis(arm, pelvis, [d / scale for d in pr["dz"]], data[grand]["rot"] if grand else None) if pelvis else \
            {"applied": False, "reason": "NO_PELVIS"}
        if res["applied"]:
            hip_ik = foot_fix.raised(hip, pr["dz"], UP)
        out["pelvis_raise"] = {**res, "bone": pelvis, "space_cm": {"p50": pr["p50"], "max": pr["max"]}, "frames": pr["frames"],
                               "source_cm_max": mm._r(pr["max"] / scale)}
    lock_rot = bool((by.get("foot_lock") or {}).get("lock_rotation"))
    ik = {"frames": {}, "clamped": {}}
    for s in SIDES:
        b = bones[s]
        pbs = {k: arm.pose.bones[b[k]] for k in ("hip", "knee", "ankle")}
        parent = pbs["hip"].parent.name if pbs["hip"].parent else None
        held = {}
        if lock_rot:
            # 접지 구간마다 발 전역 회전을 그 구간에서 가장 느린 프레임 값으로
            for a, z in mm.runs(contacts[s]):
                k = min(range(a, z + 1), key=lambda f: mm._dist(vankle[s][min(f + 1, z)], vankle[s][f]))
                for f in range(a, z + 1):
                    held[f] = data[b["ankle"]]["rot"][k]
        prev = {k: None for k in pbs}
        changed = clamped = 0
        for t, f in enumerate(frames):
            if not solved["changed"][s][t]:
                for k in pbs:
                    prev[k] = data[b[k]]["local"][t]
                continue
            # 풀이 공간(대상 모델)의 다리에서 푼 방향 변화를 소스 뼈 회전에 그대로 — 뼈 방향이 같으면 리타깃 뒤 대상 다리도 같은 방향
            # 엉덩 관절을 올렸으면 무릎 · 발목도 같이 올린 다리에서(방향 그대로) 목표로 — 올라간 만큼 다리를 편다
            dz = hip_ik[s][t][UP] - hip[s][t][UP]
            lift = lambda p: [p[i] + (dz if i == UP else 0.0) for i in range(3)]  # noqa: E731
            res = foot_fix.swing_two_bone(hip_ik[s][t], lift(vknee[s][t]), lift(vankle[s][t]), data[b["hip"]]["rot"][t], data[b["knee"]]["rot"][t],
                                          solved["targets"][s][t])
            r_hip, r_knee = Matrix(res["r_arm"]), Matrix(res["r_fore"])
            r_ankle = Matrix(held.get(t, data[b["ankle"]]["rot"][t]))
            p_rot = Matrix(data[parent]["rot"][t]) if parent else None
            prev["hip"] = _write(pbs["hip"], _basis(pbs["hip"], r_hip, p_rot), f, prev["hip"])
            prev["knee"] = _write(pbs["knee"], _basis(pbs["knee"], r_knee, r_hip), f, prev["knee"])
            prev["ankle"] = _write(pbs["ankle"], _basis(pbs["ankle"], r_ankle, r_knee), f, prev["ankle"])
            changed += 1
            clamped += bool(res["clamped"])
        ik["frames"][s], ik["clamped"][s] = changed, clamped
    after = sample(arm, names + parents)
    ahip = space_hip(after)
    aknee, aankle = space_leg(after, ahip)
    err = [mm._dist(aankle[s][t], solved["targets"][s][t]) for s in SIDES for t in range(len(frames)) if solved["changed"][s][t]]
    ik["error_max_cm"] = mm._r(max(err) if err else 0.0, 3)
    out["ik"] = ik

    def predicted(knee: dict, ankle: dict, hips: dict) -> dict:
        tracks = {"foot_l": ankle["left"], "foot_r": ankle["right"], "hip_l": hips["left"], "hip_r": hips["right"]}
        return mm.legs_report(tracks, times, UP, leg_cm, contacts={"l": contacts["left"], "r": contacts["right"]}, knees=(knee["left"], knee["right"]))

    def actual(d: dict) -> dict:
        tracks = {"foot_l": d[bones["left"]["ankle"]]["pos"], "foot_r": d[bones["right"]["ankle"]]["pos"],
                  "hip_l": d[bones["left"]["hip"]]["pos"], "hip_r": d[bones["right"]["hip"]]["pos"]}
        return mm.legs_report(tracks, times, UP, source_dims["leg_cm"], contacts={"l": contacts["left"], "r": contacts["right"]},
                              knees=(d[bones["left"]["knee"]]["pos"], d[bones["right"]["knee"]]["pos"]))
    out["before"], out["after"] = predicted(vknee, vankle, hip), predicted(aknee, aankle, ahip)
    out["source_before"], out["source_after"] = actual(data), actual(after)
    return out
