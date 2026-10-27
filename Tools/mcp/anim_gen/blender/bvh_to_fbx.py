"""Blender 헤드리스 BVH → FBX 변환 — anim-gen-mcp blender Provider 가 서브프로세스로 띄운다 (지침서 §14 Phase 4).

    blender.exe -b --factory-startup --python-exit-code 3 -P bvh_to_fbx.py -- <args.json>

Blender 의 Python 에서 돈다(서버가 import 하지 않는다). 단위 · 회전 · 범위 · fps 는 Provider 가 anim_gen/bvh.py 로 정해
args.json 에 넣고, 여기서는 적용만 한다. 결과는 report.json(임시 파일 → os.replace) — 실패해도 쓴다. 종료 코드 0 = 성공,
2 = 알려진 실패(report 에 코드), 3 = 잡지 못한 예외(--python-exit-code).

설정 근거:
- 장면 단위 1 BU = 1 cm(scale_length 0.01) + 임포트 global_scale = cm/단위 → FBX 단위 계수 1 · 노드 스케일 1
  (io_scene_fbx export_fbx_bin.py: unit_scale = 100 × scale_length, FBX_SCALE_NONE 이면 그만큼만 노드에 곱한다).
- 아마추어 객체 이름 'Armature' → Interchange 가 루트 위 널을 뼈에서 뺀다(FbxScene.cpp) → 루트 본 = BVH 루트.
- Interchange 는 스킨 메시가 없으면 새 스켈레톤을 만들지 않는다(InterchangeGenericSkeletalMeshPipeline.cpp ·
  InterchangeGenericAnimationPipeline.cpp) → 본마다 가중치 1.0 인 가는 기둥 메시를 붙인다(Persona 에서 막대 인형으로 보인다).
- 정면 회전은 회전만 적용한다 — 포즈 키는 본 로컬 공간이라 루트 이동도 같이 돈다. 스케일 적용은 위치 키를 바꾸지 않아 쓰지 않는다.
- 기준 포즈를 바닥(가장 낮은 점 z = 0)에 맞추고 루트 위치 키에서 같은 만큼 뺀다(ground) — 소스 골반이 바닥 높이면 리타깃 이동이 튄다.
- args.rest_fbx 가 있으면 첫 프레임이 기준 포즈인 FBX 도 쓴다(export_rest_fbx) — Interchange 가 깊은 본의 바인드 포즈를 무효로 보면
  애니 첫 프레임을 기준 포즈로 삼기 때문에, 스켈레톤은 이 파일로 만든다.

Phase 5: 범위를 정한 뒤 보정 op(args.fix)를 돌리고, FBX 를 내보낸 뒤 args.review 가 있으면 같은 실행에서
프레임 렌더 비교를 한다(review_render.py). 렌더가 실패해도 변환은 성공이다 — report.review.ok = false 로 남긴다.
Phase 8-3: 보정 op 사전(smooth · stance_width · foot_lock — anim_gen/fix_ops.py, 실행 blender/fix_legs.py). args.fix_legs = 다리 본 · 대상 치수.

Phase 8-1: args.items[{bvh, fbx, rest_fbx?, review?}] 가 있으면 생성 후보 여럿을 이 한 실행에서 차례로 변환한다(각각 clear_scene 부터 —
단위 · 회전 · 범위 · fps 는 공통). report 는 첫 항목 값 + items[] (기준 포즈 FBX 는 첫 항목만 — 모든 후보가 같은 SOMA 표준 T 포즈).
"""
import json
import math
import os
import pathlib
import sys
import time
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector


class ConvertError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def write_json(path, data):
    path = pathlib.Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def clear_scene():
    """--factory-startup 장면의 큐브 · 카메라 · 라이트를 지운다(후보를 이어서 변환하면 앞 항목의 아마추어 · 액션도)."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for armature in list(bpy.data.armatures):
        bpy.data.armatures.remove(armature)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def import_bvh(args):
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.01
    result = bpy.ops.import_anim.bvh(
        filepath=args["bvh"], target="ARMATURE", global_scale=args["cm_per_unit"], frame_start=1, use_fps_scale=False,
        update_scene_fps=True, update_scene_duration=True, use_cyclic=False, rotate_mode="NATIVE",
        axis_forward=args["axis_forward"], axis_up=args["axis_up"])
    if "FINISHED" not in result:
        raise ConvertError("BVH_IMPORT_FAILED", f"import_anim.bvh returned {sorted(result)}")
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        raise ConvertError("BVH_IMPORT_FAILED", f"expected one armature, found {len(arms)}")
    arm = arms[0]
    arm.name = "Armature"
    arm.data.name = "Armature"
    return arm


def rotate(arm, degrees):
    if abs(degrees) < 1e-9:
        return
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    arm.matrix_world = Matrix.Rotation(math.radians(degrees), 4, "Z") @ arm.matrix_world
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    refresh(arm)


def ground(arm):
    """기준 포즈의 가장 낮은 점을 z = 0 으로 올리고, 루트 본 위치 키에서 같은 만큼 뺀다(애니의 월드 위치는 그대로).
    BVH 루트 OFFSET 은 보통 0 이라 기준 포즈의 골반이 바닥 높이에 있다 — 리타기터 Pelvis Motion op 는 소스 골반 높이가
    0 에 가까우면 높이를 1 로 두고 이동을 그 배수만큼 키운다(PelvisMotionOp.cpp:183-196)."""
    zs = [v.z for bone in arm.data.bones for v in (bone.head_local, bone.tail_local)]
    lift = -min(zs)
    if abs(lift) < 1e-4:
        return 0.0
    arm.data.transform(Matrix.Translation((0.0, 0.0, lift)))
    action = arm.animation_data.action if arm.animation_data else None
    for bone in arm.data.bones:
        if bone.parent is not None:
            continue
        # 포즈 위치는 본 기준 포즈 공간 — 월드 +lift 를 그 공간으로 옮겨 뺀다
        delta = bone.matrix_local.to_3x3().inverted() @ Vector((0.0, 0.0, lift))
        path = f'pose.bones["{bpy.utils.escape_identifier(bone.name)}"].location'
        for index in range(3):
            curve = action.fcurves.find(path, index=index) if action else None
            if curve is None:
                arm.pose.bones[bone.name].location[index] -= delta[index]
                continue
            for key in curve.keyframe_points:
                key.co.y -= delta[index]
                key.handle_left.y -= delta[index]
                key.handle_right.y -= delta[index]
    refresh(arm)
    return round(lift, 4)


def refresh(arm):
    """Armature.transform 뒤 포즈 평가는 태그를 달아야 새 기준 포즈를 쓴다(안 하면 측정이 이전 값을 읽는다)."""
    arm.data.update_tag()
    arm.update_tag(refresh={"DATA", "OBJECT"})
    bpy.context.view_layer.update()


def set_range(arm, args):
    """BVH 프레임 [first, last] → 장면 0 .. last-first (FBX 시간이 0 에서 시작). fps 는 Provider 가 정한 값으로 맞춘다.
    임포터는 frame_start 를 1 이상으로만 받아 BVH 0 프레임이 첫 키 프레임(1)에 놓인다 — 실제 첫 키 기준으로 옮긴다."""
    scene = bpy.context.scene
    first, last = int(args["first"]), int(args["last"])
    action = arm.animation_data.action if arm.animation_data else None
    if action is None or not any(len(c.keyframe_points) for c in action.fcurves):
        raise ConvertError("NO_ACTION", "the BVH produced no animation keys")
    shift = min(k.co.x for c in action.fcurves for k in c.keyframe_points) + first
    if shift:
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                key.co.x -= shift
                key.handle_left.x -= shift
                key.handle_right.x -= shift
    scene.frame_start = 0
    scene.frame_end = last - first
    fps = float(args["fps"])
    scene.render.fps = max(1, int(round(fps)))
    scene.render.fps_base = scene.render.fps / fps
    refresh(arm)
    return action


def apply_fixes(arm, ops, legs_cfg=None):
    """범위를 정한 액션에 보정 op(Phase 8-3 — 사전 · 기본값 · 순서는 anim_gen/fix_ops.py, 실행은 blender/fix_legs.py). 순서 고정: smooth → 다리 풀이
    (stance_width + foot_lock 한 번). 모르는 op 는 하나도 적용하지 않고 실패한다(계획이 막았어야 한다). legs_cfg = provider 가 정한 다리 본 · 대상 치수."""
    if not ops:
        return []
    from anim_gen import fix_ops
    from anim_gen.blender import fix_legs
    unknown = [op.get("op") for op in ops if op.get("op") not in fix_ops.OPS]
    if unknown:
        raise ConvertError("UNSUPPORTED_FIX_OP", f"fix ops {unknown} are not in this script's dictionary {sorted(fix_ops.OPS)}")
    applied = []
    try:
        for op in ops:
            if op["op"] == "smooth":
                applied.append(fix_legs.smooth(arm, op))
        leg_ops = [op for op in ops if op["op"] in fix_ops.LEG_OPS]
        if leg_ops:
            applied.append(fix_legs.legs(arm, leg_ops, legs_cfg or {}))
    except fix_legs.FixError as err:
        raise ConvertError(err.code, str(err)) from None
    refresh(arm)
    return applied


def review(arm, mesh, cfg, out):
    """FBX 를 내보낸 뒤의 프레임 렌더 비교 — 어떤 실패든 report.review 로만 남긴다(FBX 는 이미 끝났다)."""
    try:
        from anim_gen.blender import review_render
        return review_render.render(arm, mesh, cfg, out)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"code": getattr(exc, "code", "REVIEW_EXCEPTION"), "message": f"{type(exc).__name__}: {exc}",
                                       "trace": traceback.format_exc(limit=8)}}


def proxy_mesh(arm, args):
    """본마다 head → tail 사각 기둥(8 정점) — 그 본의 버텍스 그룹에 1.0. 모든 본이 FBX 클러스터(바인드 포즈)를 갖는다."""
    cfg = args.get("proxy_mesh") or {}
    min_width, ratio = float(cfg.get("min_width_cm", 0.5)), float(cfg.get("width_ratio", 0.08))
    bm = bmesh.new()
    bones = list(arm.data.bones)
    for bone in bones:
        head, tail = bone.head_local.copy(), bone.tail_local.copy()
        axis = tail - head
        length = axis.length
        d = axis.normalized() if length > 1e-6 else Vector((0.0, 0.0, 1.0))
        half = max(min_width, length * ratio) / 2.0
        if length <= 1e-6:
            tail = head + d * half * 2.0
        u = d.orthogonal().normalized()
        v = d.cross(u)
        verts = [bm.verts.new(p + (su * u + sv * v) * half) for p in (head, tail) for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        for face in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            bm.faces.new([verts[k] for k in face])
    mesh = bpy.data.meshes.new("BvhProxy")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("BvhProxy", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = arm
    for i, bone in enumerate(bones):
        group = obj.vertex_groups.new(name=bone.name)
        group.add(list(range(i * 8, i * 8 + 8)), 1.0, "REPLACE")
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm
    return obj


def measure(arm):
    """기준 포즈를 UE 좌표(x, -y, z)로 — anim_gen/bvh.py 의 같은 함수로 키 · 정면을 잰다(Provider 계산과 끝에서 끝까지 대조)."""
    from anim_gen import bvh as bvh_math
    segments = []
    for bone in arm.data.bones:
        h, t = bone.head_local, bone.tail_local
        segments.append(((h.x, -h.y, h.z), (t.x, -t.y, t.z)))
    roots = [b.name for b in arm.data.bones if b.parent is None]
    return {"bones": len(arm.data.bones), "roots": roots, "rest_height_cm": round(bvh_math.height(segments), 3),
            "facing": bvh_math.facing(segments)}


def root_path(arm):
    """루트 본의 첫 · 끝 프레임 위치(UE 좌표) — 정면 회전이 루트 이동에도 적용됐는지 대조한다."""
    scene = bpy.context.scene
    root = next(b for b in arm.pose.bones if b.parent is None)
    out = {"bone": root.name}
    for label, frame in (("first", scene.frame_start), ("last", scene.frame_end)):
        scene.frame_set(frame)
        head = arm.matrix_world @ root.head
        out[label] = [round(head.x, 3), round(-head.y, 3), round(head.z, 3)]
    scene.frame_set(scene.frame_start)
    return out


def export_fbx(path):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.export_scene.fbx(
        filepath=path, use_selection=False, object_types={"ARMATURE", "MESH"},
        global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", axis_forward="-Z", axis_up="Y",
        use_space_transform=True, bake_space_transform=False,
        use_mesh_modifiers=False, mesh_smooth_type="FACE", use_custom_props=False,
        add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", use_armature_deform_only=False, armature_nodetype="NULL",
        bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0,
        path_mode="AUTO", embed_textures=False, use_metadata=True)
    if "FINISHED" not in result or not os.path.isfile(path):
        raise ConvertError("FBX_EXPORT_FAILED", f"export_scene.fbx returned {sorted(result)}")


ROTATION_PATHS = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}


def export_rest_fbx(arm, path):
    """기준 포즈 FBX(같은 아마추어 · 프록시 메시, 기준 포즈 그대로인 2프레임 애니) — 이것으로 스켈레톤을 만들고 동작 FBX 는 그 스켈레톤에
    애니만 가져온다. Interchange 는 깊은 본(SOMA 손가락 둘째 마디 아래, 계층 깊이 10 이상)이 있으면 바인드 포즈를 무효로 보고 time zero
    (= 애니 첫 프레임)로 다시 바인드한다(InterchangeSkeletalMeshFactory.cpp:792-808, 허용 오차 0.0001 FbxScene.cpp IsValidBindPose)
    → 소스 기준 포즈가 BVH 기준(T 포즈)이 아니라 첫 프레임이 된다. 이 파일은 첫 프레임이 기준 포즈다.
    애니를 아예 빼지 않는 것은 import_animation_file 이 애니 없는 FBX 를 NO_ANIMATION 으로 거부하기 때문."""
    scene = bpy.context.scene
    action = arm.animation_data.action if arm.animation_data else None
    span = (scene.frame_start, scene.frame_end)
    if arm.animation_data is None:
        arm.animation_data_create()
    rest = bpy.data.actions.new("Rest")
    arm.animation_data.action = rest
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
        for frame in (0, 1):
            pb.keyframe_insert("location", frame=frame)
            pb.keyframe_insert(ROTATION_PATHS.get(pb.rotation_mode, "rotation_euler"), frame=frame)
    scene.frame_start, scene.frame_end = 0, 1
    refresh(arm)
    try:
        export_fbx(path)
    finally:
        arm.animation_data.action = action
        bpy.data.actions.remove(rest)
        scene.frame_start, scene.frame_end = span
        scene.frame_set(scene.frame_start)
        refresh(arm)


def convert(args):
    sys.path.insert(0, args["package_dir"])
    clear_scene()
    arm = import_bvh(args)
    rotate(arm, float(args.get("rotate_z_deg", 0.0)))
    lift = ground(arm)
    action = set_range(arm, args)
    fixes = apply_fixes(arm, args.get("fix") or [], args.get("fix_legs"))
    mesh = proxy_mesh(arm, args)
    out = measure(arm)
    out["root_path"] = root_path(arm)
    export_fbx(args["fbx"])
    if args.get("rest_fbx"):
        export_rest_fbx(arm, args["rest_fbx"])
        out.update({"rest_fbx": args["rest_fbx"], "rest_fbx_bytes": os.path.getsize(args["rest_fbx"])})
    scene = bpy.context.scene
    out.update({"fbx": args["fbx"], "fbx_bytes": os.path.getsize(args["fbx"]), "action": action.name,
                "frames": {"start": scene.frame_start, "end": scene.frame_end, "keys": scene.frame_end - scene.frame_start + 1,
                           "fps": round(scene.render.fps / scene.render.fps_base, 6)},
                "proxy_mesh": {"vertices": len(mesh.data.vertices), "groups": len(mesh.vertex_groups)},
                "rotate_z_deg": float(args.get("rotate_z_deg", 0.0)), "cm_per_unit": args["cm_per_unit"], "ground_lift_cm": lift,
                "fix": {"applied": fixes}})
    if args.get("review"):
        out["review"] = review(arm, mesh, args["review"], out)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print("usage: blender -b -P bvh_to_fbx.py -- <args.json>")
        sys.exit(2)
    args = json.loads(pathlib.Path(argv[0]).read_text(encoding="utf-8"))
    report = {"ok": False, "blender": bpy.app.version_string, "args": argv[0]}
    t0 = time.time()
    try:
        if args.get("items"):
            items = []
            for item in args["items"]:
                t1 = time.time()
                one = convert({**args, "rest_fbx": None, "review": None, **item})
                items.append({**one, "bvh": item["bvh"], "seconds": round(time.time() - t1, 3)})
            report.update({k: v for k, v in items[0].items() if k != "seconds"})
            report["items"] = items
        else:
            report.update(convert(args))
        report["ok"] = True
    except ConvertError as err:
        report["error"] = {"code": err.code, "message": str(err)}
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 report 로 남긴다
        report["error"] = {"code": "BLENDER_EXCEPTION", "message": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=8)}
    report["seconds"] = round(time.time() - t0, 3)
    write_json(args["report"], report)
    print(f"bvh_to_fbx: ok={report['ok']} {report.get('error', {}).get('code', '')} {report['seconds']}s")
    if not report["ok"]:
        sys.exit(2)


main()
