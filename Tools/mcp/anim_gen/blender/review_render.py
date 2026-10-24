"""프레임 렌더 비교 — bvh_to_fbx.py 가 FBX 를 내보낸 뒤 같은 Blender 실행 안에서 부른다 (지침서 §14 Phase 5 · request.review.render).

Blender 의 Python 에서 돈다(서버가 import 하지 않는다). 보이는 것은 변환된 소스 골격(본마다 기둥 더미 메시)이지 Vesper 가 아니다.
- 색: 이름으로 가른 왼쪽 본 파랑 · 오른쪽 빨강 · 가운데 회색, 부모 없는 루트 본 호박색(가늘게), 머리 앞 초록 코(그 프레임의 정면),
  바닥(z = 0) 회색 띠.
- 카메라: Workbench · 정사영. 정면 = 기준 포즈가 보는 쪽에서(골격의 왼쪽이 화면 오른쪽), 측면 = 골격의 오른쪽에서(정면이 화면 오른쪽).
  전 프레임의 포즈 범위(최대 bounds_max_samples 프레임을 고르게 + 렌더 프레임)에 한 번 맞춰 고정한다 — 이동 · 높이 변화가 그대로 보인다.
- 출력: (시각 × 뷰) PNG <view>_<frame>.png 와 sheet.png(행 = 시각, 열 = 뷰 + 레퍼런스 이미지) — 픽셀은 numpy 로 이어 붙인다.
FBX 를 내보낸 뒤에만 장면에 재질 · 카메라 · 표식을 더한다(FBX 에 들어가지 않는다).
"""
import math
import pathlib
import re
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

BACKGROUND = (0.96, 0.96, 0.96)
GAP_COLOR = (0.3, 0.3, 0.3)
GAP_PX = 6
COLORS = {"left": (0.12, 0.32, 0.95), "right": (0.92, 0.18, 0.12), "center": (0.55, 0.55, 0.55), "root": (0.95, 0.65, 0.05),
          "nose": (0.05, 0.7, 0.2), "floor": (0.72, 0.72, 0.72), "label": (0.08, 0.08, 0.08)}
LEGEND = "left bones blue, right bones red, center gray, root bone thin amber, green nose = facing, gray strip = floor z 0"
# 이름의 Left/Right 낱말, 또는 구분자 사이 · 앞(LHipJoint) · 끝(foot_l)의 L/R 한 글자
_SIDES = {"left": (re.compile("left", re.IGNORECASE), re.compile(r"(?:^|[_\-.\s])[Ll](?:[_\-.\s]|$)|^L(?=[A-Z0-9])")),
          "right": (re.compile("right", re.IGNORECASE), re.compile(r"(?:^|[_\-.\s])[Rr](?:[_\-.\s]|$)|^R(?=[A-Z0-9])"))}
_FACING_UE = {"+X": (1.0, 0.0), "-X": (-1.0, 0.0), "+Y": (0.0, 1.0), "-Y": (0.0, -1.0)}


class ReviewError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def side_of(name):
    for side, (word, letter) in _SIDES.items():
        if word.search(name) or letter.search(name):
            return side
    return "center"


def ue(v):
    return [round(float(v[0]), 3), round(-float(v[1]), 3), round(float(v[2]), 3)]


def material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    return mat


def facing_vector(info):
    """기준 포즈 정면(UE 축 → Blender: y 부호 반대). 축을 못 쟀으면 측정 벡터, 그것도 없으면 UE +Y 로 가정한다."""
    facing = info.get("facing") or {}
    if facing.get("axis") in _FACING_UE:
        x, y = _FACING_UE[facing["axis"]]
        return Vector((x, -y, 0.0)), facing["axis"]
    vx, vy = (facing.get("vector") or [0.0, 0.0])[:2]
    if math.hypot(vx, vy) > 1e-6:
        return Vector((vx, -vy, 0.0)).normalized(), "measured"
    return Vector((0.0, -1.0, 0.0)), "assumed +Y"


def color_proxy(arm, proxy, mats, height):
    """기둥 면마다 그 정점 그룹(본) 이름으로 좌 · 우 · 가운데 재질. 부모 없는 본(루트 · Kimodo Root 래퍼)은 호박색 가는 막대로 —
    기둥 폭은 본 길이 비례라 바닥 → 골반 래퍼가 다리를 가린다(FBX 는 이미 내보냈다 — 렌더에서만 가늘게)."""
    mesh = proxy.data
    order = ["center", "left", "right", "root"]
    for key in order:
        mesh.materials.append(mats[key])
    groups = {g.index: g.name for g in proxy.vertex_groups}
    counts = {key: set() for key in order}
    thin = max(0.5, 0.006 * height) * math.sqrt(2.0)  # 단면 대각 반지름
    for poly in mesh.polygons:
        vertex = mesh.vertices[poly.vertices[0]]
        name = groups[vertex.groups[0].group] if vertex.groups else ""
        bone = arm.data.bones.get(name)
        side = "root" if bone is not None and bone.parent is None else side_of(name)
        counts[side].add(name)
        poly.material_index = order.index(side)
    for name in counts["root"]:
        bone = arm.data.bones[name]
        axis = bone.tail_local - bone.head_local
        d = axis.normalized() if axis.length > 1e-6 else Vector((0.0, 0.0, 1.0))
        index = proxy.vertex_groups[name].index
        for vertex in mesh.vertices:
            if not any(g.group == index for g in vertex.groups):
                continue
            on_axis = bone.head_local + d * (vertex.co - bone.head_local).dot(d)
            radial = vertex.co - on_axis
            if radial.length > thin:
                vertex.co = on_axis + radial * (thin / radial.length)
    return {key: sorted(names) if key == "root" else len(names) for key, names in counts.items()}


def head_bone(arm):
    bones = list(arm.data.bones)
    exact = [b for b in bones if b.name.lower() == "head"]
    if exact:
        return exact[0]
    named = [b for b in bones if "head" in b.name.lower() and not re.search(r"end|top|nub|site", b.name, re.IGNORECASE)]
    return named[0] if named else max(bones, key=lambda b: b.head_local.z)


def box(bm, center, half):
    verts = [bm.verts.new(center + Vector((sx * half[0], sy * half[1], sz * half[2]))) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    for face in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([verts[k] for k in face])


def mesh_object(name, build, mat, parent=None):
    bm = bmesh.new()
    build(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def nose(arm, forward, height, mat):
    """머리 본 앞 작은 상자(머리 본 가중치 1.0) — 그 프레임에 골격이 보는 쪽."""
    bone = head_bone(arm)
    center = (bone.head_local + bone.tail_local) / 2 + forward * (0.07 * height)
    half = 0.022 * height
    obj = mesh_object("ReviewNose", lambda bm: box(bm, center, (half, half, half)), mat, parent=arm)
    group = obj.vertex_groups.new(name=bone.name)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    obj.modifiers.new("Armature", "ARMATURE").object = arm
    return bone.name


def sample_frames(scene, extra, cap):
    first, last = scene.frame_start, scene.frame_end
    step = max(1, math.ceil((last - first + 1) / max(1, cap)))
    return sorted(set(range(first, last + 1, step)) | {last} | set(extra))


def pose_points(arm, frames):
    scene = bpy.context.scene
    world = arm.matrix_world
    points = []
    for frame in frames:
        scene.frame_set(frame)
        for pb in arm.pose.bones:
            points.append(tuple(world @ pb.head))
            points.append(tuple(world @ pb.tail))
    return np.asarray(points, dtype=np.float64)


def frame_view(points, look, right, cfg):
    """정사영 카메라를 점 구름에 맞춘다 — 셀 높이 고정, 폭은 범위 비율(1/max_aspect ~ max_aspect)."""
    up = Vector((0.0, 0.0, 1.0))
    u = points @ np.asarray(right)
    v = points @ np.asarray(up)
    d = points @ np.asarray(look)
    margin = float(cfg["margin"])
    umin, umax = float(u.min()), float(u.max())
    vmin, vmax = min(float(v.min()), 0.0), float(v.max())  # 바닥(z = 0)은 늘 보이게
    need_w = max(umax - umin, 1.0) * (1 + 2 * margin)
    need_h = max(vmax - vmin, 1.0) * (1 + 2 * margin)
    h_px = int(cfg["cell_height_px"])
    aspect = min(max(need_w / need_h, 1.0 / float(cfg["max_aspect"])), float(cfg["max_aspect"]))
    w_px = max(2, int(round(h_px * aspect / 2)) * 2)
    r = w_px / h_px
    scale = max(need_w, need_h * r) if w_px >= h_px else max(need_h, need_w / r)
    ext_w, ext_h = (scale, scale / r) if w_px >= h_px else (scale * r, scale)
    depth = float(d.max() - d.min())
    distance = 100.0 + depth
    center = right * ((umin + umax) / 2) + up * ((vmin + vmax) / 2) + look * (float(d.min()) - distance)
    return {"center": center, "scale": scale, "extent": (ext_w, ext_h), "resolution": (w_px, h_px), "clip_end": depth + 2 * distance}


def camera(name, look, right, fit, label_mat):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = fit["scale"]
    data.sensor_fit = "AUTO"
    data.clip_start = 0.5
    data.clip_end = fit["clip_end"]
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    up = Vector((0.0, 0.0, 1.0))
    rot = Matrix((right, up, -look)).transposed()  # 열 = 카메라 로컬 X(오른쪽) · Y(위) · Z(뒤 — 카메라는 −Z 를 본다)
    obj.matrix_world = Matrix.Translation(fit["center"]) @ rot.to_4x4()
    # 왼쪽 위 글자(뷰 · 시각 · 프레임) — 카메라 바로 앞에 붙여 골격에 가리지 않는다
    ext_w, ext_h = fit["extent"]
    size = ext_h * 0.045
    curve = bpy.data.curves.new(f"{name}Label", type="FONT")
    curve.size = size
    curve.materials.append(label_mat)
    label = bpy.data.objects.new(f"{name}Label", curve)
    bpy.context.scene.collection.objects.link(label)
    label.parent = obj
    label.location = (-ext_w / 2 + size * 0.5, ext_h / 2 - size * 1.3, -1.0)
    return obj, label


def setup_render(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("ReviewWorld")
    scene.world.color = BACKGROUND
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "MATERIAL"
    shading.show_object_outline = True
    shading.object_outline_color = (0.0, 0.0, 0.0)
    shading.show_shadows = False
    shading.show_cavity = False


def read_rgb(path, size=None):
    """PNG/JPG → (h, w, 3) float, 위 → 아래 행. 투명은 배경색 위에 얹는다. size 면 Blender 로 줄인 뒤 읽는다."""
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        if size is not None:
            img.scale(*size)
        w, h = img.size
        if w == 0 or h == 0:
            raise ReviewError("IMAGE_UNREADABLE", f"{path}: no pixels")
        channels = img.channels
        px = np.empty(w * h * channels, dtype=np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    arr = px.reshape(h, w, channels)[::-1]
    if channels == 1:
        rgb, alpha = np.repeat(arr, 3, axis=2), None
    elif channels == 2:
        rgb, alpha = np.repeat(arr[:, :, :1], 3, axis=2), arr[:, :, 1:2]
    else:
        rgb, alpha = arr[:, :, :3], arr[:, :, 3:4] if channels >= 4 else None
    if alpha is not None:
        rgb = rgb * alpha + np.asarray(BACKGROUND, dtype=np.float32) * (1.0 - alpha)
    return rgb


def image_size(path):
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        return tuple(img.size)
    finally:
        bpy.data.images.remove(img)


def reference_cell(path, width, height):
    """레퍼런스 이미지를 (width, height) 셀 가운데에 비율을 지켜 넣는다."""
    w, h = image_size(path)
    if not w or not h:
        raise ReviewError("IMAGE_UNREADABLE", f"{path}: no pixels")
    s = min(width / w, height / h)
    fit = (max(1, int(round(w * s))), max(1, int(round(h * s))))
    rgb = read_rgb(path, fit)
    cell = np.empty((height, width, 3), dtype=np.float32)
    cell[:] = BACKGROUND
    y, x = (height - rgb.shape[0]) // 2, (width - rgb.shape[1]) // 2
    cell[y:y + rgb.shape[0], x:x + rgb.shape[1]] = rgb
    return cell


def missing_cell(width, height):
    """읽지 못한 레퍼런스 — 회색 바탕에 X."""
    cell = np.empty((height, width, 3), dtype=np.float32)
    cell[:] = (0.85, 0.85, 0.85)
    n = max(width, height)
    t = np.linspace(0.0, 1.0, 4 * n)
    for ys in (t * (height - 1), (1 - t) * (height - 1)):
        yi, xi = ys.astype(int), (t * (width - 1)).astype(int)
        for k in range(-2, 3):
            cell[np.clip(yi + k, 0, height - 1), xi] = (0.4, 0.4, 0.4)
    return cell


def save_sheet(rows, widths, height, path):
    """rows[r][c] = (height, widths[c], 3) → 사이 간격을 둔 한 장. Blender 이미지 버퍼(아래 → 위 RGBA)로 PNG 저장."""
    total_w = sum(widths) + GAP_PX * (len(widths) + 1)
    total_h = height * len(rows) + GAP_PX * (len(rows) + 1)
    sheet = np.empty((total_h, total_w, 4), dtype=np.float32)
    sheet[:, :, :3] = GAP_COLOR
    sheet[:, :, 3] = 1.0
    for r, cells in enumerate(rows):
        y = GAP_PX + r * (height + GAP_PX)
        x = GAP_PX
        for c, cell in enumerate(cells):
            sheet[y:y + height, x:x + widths[c], :3] = cell
            x += widths[c] + GAP_PX
    img = bpy.data.images.new("ReviewSheet", total_w, total_h, alpha=False)
    try:
        img.pixels.foreach_set(np.ascontiguousarray(sheet[::-1]).ravel())
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)
    if not pathlib.Path(path).is_file():
        raise ReviewError("SHEET_NOT_WRITTEN", f"{path} was not written")
    return [total_w, total_h]


def render(arm, proxy, cfg, info):
    """cfg = args.review {times, views, reference_images, dir, cell_height_px, max_aspect, margin, bounds_max_samples}.
    info = 변환 측정값(facing · rest_height_cm). → report.review."""
    t0 = time.time()
    scene = bpy.context.scene
    out_dir = pathlib.Path(cfg["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = scene.render.fps / scene.render.fps_base
    rows = []
    for t in cfg["times"]:
        want = int(round(float(t) * fps)) + scene.frame_start
        frame = min(max(want, scene.frame_start), scene.frame_end)
        rows.append({"time": float(t), "frame": frame, "frame_time": round((frame - scene.frame_start) / fps, 4), "clamped": frame != want})
    height = float(info.get("rest_height_cm") or 170.0)
    forward, facing_from = facing_vector(info)
    up = Vector((0.0, 0.0, 1.0))
    right_of_body = forward.cross(up).normalized()

    mats = {key: material(f"Review_{key}", rgb) for key, rgb in COLORS.items()}
    sides = color_proxy(arm, proxy, mats, height)
    nose_bone = nose(arm, forward, height, mats["nose"])
    frames = sample_frames(scene, [r["frame"] for r in rows], int(cfg["bounds_max_samples"]))
    points = pose_points(arm, frames)
    lo, hi = points.min(axis=0), points.max(axis=0)
    pad = 0.15 * height
    floor_t = max(0.5, 0.01 * height)
    floor_center = Vector((float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2, -floor_t / 2))
    floor_half = (float(hi[0] - lo[0]) / 2 + pad, float(hi[1] - lo[1]) / 2 + pad, floor_t / 2)
    mesh_object("ReviewFloor", lambda bm: box(bm, floor_center, floor_half), mats["floor"])

    setup_render(scene)
    views = {}
    for view in cfg["views"]:
        # 정면: 골격 앞에서 뒤로(카메라 오른쪽 = 골격의 왼쪽), 측면: 골격 오른쪽에서 왼쪽으로(카메라 오른쪽 = 골격 정면)
        look = -forward if view == "front" else -right_of_body
        cam_right = look.cross(up).normalized()
        fit = frame_view(points, look, cam_right, cfg)
        obj, label = camera(f"Review_{view}", look, cam_right, fit, mats["label"])
        views[view] = {"obj": obj, "label": label, "fit": fit, "look": look}

    images = []
    for r, row in enumerate(rows):
        scene.frame_set(row["frame"])
        for view in cfg["views"]:
            v = views[view]
            for other in views.values():
                other["label"].hide_render = other is not v
            v["label"].data.body = f"{view}   t {row['frame_time']:.2f}s   frame {row['frame']}"
            scene.camera = v["obj"]
            scene.render.resolution_x, scene.render.resolution_y = v["fit"]["resolution"]
            path = out_dir / f"{view}_{row['frame']:05d}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if not path.is_file():
                raise ReviewError("RENDER_NOT_WRITTEN", f"{path} was not written")
            images.append({"row": r, "time": row["time"], "frame": row["frame"], "view": view, "path": path.as_posix()})

    # 비교 시트: 행 = 시각, 열 = 뷰 + 레퍼런스(같은 그림을 모든 행에). 긴 변이 sheet_max_px 를 넘으면 칸을 줄인다(프레임 PNG 는 원래 크기)
    cell_h = int(cfg["cell_height_px"])
    max_aspect = float(cfg["max_aspect"])
    columns = [{"kind": "view", "view": view, "width": views[view]["fit"]["resolution"][0]} for view in cfg["views"]]
    warnings = []
    for path in cfg.get("reference_images") or []:
        try:
            w, h = image_size(path)
            aspect = min(max(w / h, 1.0 / max_aspect), max_aspect) if w and h else 1.0
        except Exception:  # noqa: BLE001 — 아래에서 다시 읽다 실패하면 X 칸
            aspect = 1.0
        columns.append({"kind": "reference", "path": path, "width": max(2, int(round(cell_h * aspect)))})
    gaps_w, gaps_h = GAP_PX * (len(columns) + 1), GAP_PX * (len(rows) + 1)
    limit = float(cfg.get("sheet_max_px") or 1e9)
    scale = min(1.0, (limit - gaps_w) / sum(c["width"] for c in columns), (limit - gaps_h) / (cell_h * len(rows)))
    sheet_h = max(2, int(cell_h * scale))  # 내림 — 반올림이 쌓여 한도를 넘지 않게
    widths = [max(2, int(c["width"] * scale)) for c in columns]
    ref_cells = []
    for column, width in zip(columns, widths):
        if column["kind"] != "reference":
            continue
        try:
            ref_cells.append(reference_cell(column["path"], width, sheet_h))
        except Exception as exc:  # noqa: BLE001 — 읽지 못한 그림은 X 칸으로 두고 알린다
            ref_cells.append(missing_cell(width, sheet_h))
            warnings.append({"code": "REFERENCE_UNREADABLE", "message": f"{column['path']}: {type(exc).__name__}: {exc}"})
    grid = []
    for r in range(len(rows)):
        cells = [read_rgb(i["path"], None if scale == 1.0 else (width, sheet_h))
                 for i, width in zip([i for i in images if i["row"] == r], widths)]
        grid.append(cells + ref_cells)
    sheet = out_dir / "sheet.png"
    size = save_sheet(grid, widths, sheet_h, sheet)

    camera_info = {view: {"look": ue(v["look"]), "ortho_scale_cm": round(v["fit"]["scale"], 3), "resolution": list(v["fit"]["resolution"]),
                          "cm_per_px": round(v["fit"]["extent"][1] / v["fit"]["resolution"][1], 4)} for view, v in views.items()}
    return {"ok": True, "dir": out_dir.as_posix(), "frames": images, "sheet": sheet.as_posix(),
            "layout": {"rows": rows, "columns": [dict(c, sheet_width=w) for c, w in zip(columns, widths)], "cell_height": sheet_h,
                       "gap": GAP_PX, "size": size, "scale": round(scale, 4)},
            "camera": camera_info, "facing_from": facing_from, "nose_bone": nose_bone, "sides": sides,
            "bounds": {"min": [min(a, b) for a, b in zip(ue(lo), ue(hi))], "max": [max(a, b) for a, b in zip(ue(lo), ue(hi))],
                       "frames_sampled": len(frames)},
            "colors": {**{k: [round(c, 3) for c in rgb] for k, rgb in COLORS.items()}, "legend": LEGEND},
            "warnings": warnings, "seconds": round(time.time() - t0, 3)}
