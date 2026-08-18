"""AstralBreak 레벨 블록아웃 자동화. UE 5.7 실측 검증 완료.

설계 원칙:
  - 레벨은 JSON에서 매번 재생성한다 (.umap은 git diff가 안 되므로 JSON이 진실)
  - 스크립트가 만든 액터만 지운다 (수동 배치물 보존)
"""
import math
import unreal

_les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
_eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
_eal = unreal.EditorAssetLibrary

GEN_TAG = "AB_Generated"   # 스크립트 생성 액터 식별용

_SHAPES = {
    "cube":     "/Engine/BasicShapes/Cube",
    "cylinder": "/Engine/BasicShapes/Cylinder",
    "sphere":   "/Engine/BasicShapes/Sphere",
    "cone":     "/Engine/BasicShapes/Cone",
    "plane":    "/Engine/BasicShapes/Plane",
}

_CLASSES = {
    "PlayerStart":          unreal.PlayerStart,
    "DirectionalLight":     unreal.DirectionalLight,
    "SkyLight":             unreal.SkyLight,
    "PointLight":           unreal.PointLight,
    "SpotLight":            unreal.SpotLight,
    "NavMeshBoundsVolume":  unreal.NavMeshBoundsVolume,
    "TargetPoint":          unreal.TargetPoint,
    "TriggerBox":           unreal.TriggerBox,
    "TriggerSphere":        unreal.TriggerSphere,
    "PostProcessVolume":    unreal.PostProcessVolume,
}


# ─────────────────────── 유틸 ───────────────────────

def _vec(v, default=(0, 0, 0)):
    if v is None:
        v = default
    return unreal.Vector(float(v[0]), float(v[1]), float(v[2]))


def _rot(v, default=(0, 0, 0)):
    """(pitch, yaw, roll) 튜플 → unreal.Rotator.

    주의: unreal.Rotator의 생성자는 (roll, pitch, yaw) 순서다 (실측 확인).
    JSON 스키마와 패턴 생성기는 에디터 표기와 같은 (pitch, yaw, roll)을 쓰므로
    위치 인자로 그대로 넘기면 yaw가 pitch로 들어가 액터가 넘어진다.
    """
    if v is None:
        v = default
    return unreal.Rotator(float(v[2]), float(v[0]), float(v[1]))


def _tag_actor(actor, label: str):
    actor.set_actor_label(label)
    tags = list(actor.get_editor_property("tags"))
    tags.append(unreal.Name(GEN_TAG))
    actor.set_editor_property("tags", tags)
    return actor


# ─────────────────────── 스폰 ───────────────────────

def spawn_mesh(shape_or_path: str, location, rotation=None, scale=None,
               label: str = "SM_Generated"):
    path = _SHAPES.get(shape_or_path, shape_or_path)
    mesh = unreal.load_asset(path)
    if not mesh:
        raise RuntimeError(f"메시 로드 실패: {path}")
    a = _eas.spawn_actor_from_object(mesh, _vec(location), _rot(rotation))
    if scale:
        a.set_actor_scale3d(_vec(scale, (1, 1, 1)))
    return _tag_actor(a, label)


def spawn_class(class_name: str, location, rotation=None, scale=None,
                label: str = None, props: dict = None):
    cls = _CLASSES.get(class_name)
    if not cls:
        cls = unreal.load_class(None, class_name)
    if not cls:
        raise RuntimeError(f"클래스 로드 실패: {class_name}")
    a = _eas.spawn_actor_from_class(cls, _vec(location), _rot(rotation))
    if scale:
        a.set_actor_scale3d(_vec(scale, (1, 1, 1)))
    if props:
        for k, v in props.items():
            a.set_editor_property(k, v)
    return _tag_actor(a, label or class_name)


# ─────────────────────── 패턴 ───────────────────────

def radial(count: int, radius: float, z: float = 0.0,
           start_deg: float = 0.0, face_center: bool = False,
           yaw_offset: float = 0.0):
    """방사 배치 좌표/회전 생성기. (location, rotation) 튜플을 yield.

    기본은 액터의 +X가 반지름 바깥을 향한다. face_center면 안쪽.
    yaw_offset은 거기서 추가로 돌린다 — 장축이 X인 벽/차폐물을 접선 방향으로
    세울 때 90을 준다 (안 주면 벽이 아니라 바큇살이 된다).
    """
    for i in range(count):
        deg = start_deg + i * (360.0 / count)
        rad = math.radians(deg)
        loc = (radius * math.cos(rad), radius * math.sin(rad), z)
        yaw = (deg + 180 if face_center else deg) + yaw_offset
        yield loc, (0, yaw, 0)


def grid(cols: int, rows: int, spacing: float, z: float = 0.0, centered: bool = True):
    ox = -(cols - 1) * spacing / 2 if centered else 0
    oy = -(rows - 1) * spacing / 2 if centered else 0
    for r in range(rows):
        for c in range(cols):
            yield (ox + c * spacing, oy + r * spacing, z), (0, 0, 0)


# ─────────────────────── 빌드 ───────────────────────

def clear_generated() -> int:
    """스크립트가 만든 액터만 제거. 수동 배치물은 보존."""
    n = 0
    for a in _eas.get_all_level_actors():
        if not a:
            continue
        if unreal.Name(GEN_TAG) in list(a.get_editor_property("tags")):
            _eas.destroy_actor(a)
            n += 1
    return n


def build(spec: dict, dry_run: bool = False) -> dict:
    """JSON 스펙으로 레벨을 생성/재생성한다."""
    if dry_run:
        return {"dry_run": True, "map": spec.get("map"),
                "entries": len(spec.get("actors", []))}

    map_path = spec["map"]
    mode = spec.get("mode", "new")   # new | rebuild

    if mode == "new":
        _les.new_level(map_path)
    else:
        if not _eal.does_asset_exist(map_path):
            raise RuntimeError(f"레벨 없음 (mode=new 필요): {map_path}")
        _les.load_level(map_path)
        removed = clear_generated()
        unreal.log(f"  기존 생성 액터 {removed}개 제거")

    created = 0
    for entry in spec.get("actors", []):
        created += _build_entry(entry)

    _les.save_current_level()
    _les.load_level(map_path)          # 디스크에서 다시 읽어 상태 확정
    return {"map": map_path, "created": created,
            "total": len(_eas.get_all_level_actors())}


def _build_entry(e: dict) -> int:
    kind = e.get("kind", "mesh")
    pattern = e.get("pattern")

    # 패턴 배치
    if pattern:
        p = pattern
        if p["type"] == "radial":
            gen = radial(p["count"], p["radius"], p.get("z", 0.0),
                         p.get("start_deg", 0.0), p.get("face_center", False),
                         p.get("yaw_offset", 0.0))
        elif p["type"] == "grid":
            gen = grid(p["cols"], p["rows"], p["spacing"], p.get("z", 0.0))
        elif p["type"] == "line":
            gen = line(p["count"], p["start"], p["end"], p.get("face_path", False))
        elif p["type"] == "rect_ring":
            gen = rect_ring(p["cols"], p["rows"], p["spacing"], p.get("z", 0.0))
        elif p["type"] == "explicit":
            gen = explicit(p["points"])
        else:
            raise RuntimeError(f"알 수 없는 패턴: {p['type']}")

        n = 0
        for i, (loc, rot) in enumerate(gen):
            label = f"{e.get('label', 'Actor')}_{i:02d}"
            if kind == "mesh":
                spawn_mesh(e["shape"], loc, rot, e.get("scale"), label)
            else:
                spawn_class(e["class"], loc, rot, e.get("scale"), label, e.get("props"))
            n += 1
        return n

    # 단일 배치
    label = e.get("label")
    if kind == "mesh":
        spawn_mesh(e["shape"], e.get("location"), e.get("rotation"),
                   e.get("scale"), label or "SM_Generated")
    else:
        spawn_class(e["class"], e.get("location"), e.get("rotation"),
                    e.get("scale"), label, e.get("props"))
    return 1


def line(count: int, start, end, face_path: bool = False):
    """두 점 사이 균등 배치. 복도 기둥, 벽 모듈, 가로등 등."""
    sx, sy, sz = start
    ex, ey, ez = end
    yaw = math.degrees(math.atan2(ey - sy, ex - sx))
    for i in range(count):
        t = i / max(count - 1, 1)
        loc = (sx + (ex - sx) * t, sy + (ey - sy) * t, sz + (ez - sz) * t)
        yield loc, (0, yaw if face_path else 0, 0)


def rect_ring(cols: int, rows: int, spacing: float, z: float = 0.0):
    """사각 링 배치. 방 둘레 벽, 울타리 등."""
    ox, oy = -(cols - 1) * spacing / 2, -(rows - 1) * spacing / 2
    for r in range(rows):
        for c in range(cols):
            if 0 < r < rows - 1 and 0 < c < cols - 1:
                continue          # 내부는 비움
            yield (ox + c * spacing, oy + r * spacing, z), (0, 0, 0)


def explicit(points: list):
    """좌표를 직접 나열. 불규칙 배치용."""
    for p in points:
        yield tuple(p.get("location", (0, 0, 0))), tuple(p.get("rotation", (0, 0, 0)))