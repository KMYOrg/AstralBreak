"""엄폐물 후보 메시의 콜리전 구성 확인 — 읽기 전용.

투사체(ECC_WorldStatic Block)와 조준 트레이스(ECC_Visibility)가 실제로 막히는지는
단순 콜리전 프리미티브가 결정한다. 바운딩 박스가 아니다.
"""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal

TARGETS = [
    "/Game/Assets/SlashFX/Demo/Meshes/SM_DemoRoomClamp",
    "/Game/Assets/SciFi_VFX/DemoRoom/Meshes/SM_Base_FlatWall",
]

for path in TARGETS:
    m = unreal.load_asset(path)
    if not m:
        unreal.log_error(f"로드 실패: {path}")
        continue

    name = path.split("/")[-1]
    bs = m.get_editor_property("body_setup")
    unreal.log(f"=== {name} ===")

    if not bs:
        unreal.log("  body_setup 없음 → 단순 콜리전 0개 (복잡 형상만)")
        continue

    flag = bs.get_editor_property("collision_trace_flag")
    unreal.log(f"  collision_trace_flag = {flag}")

    geom = bs.get_editor_property("agg_geom")
    boxes = list(geom.get_editor_property("box_elems"))
    convex = list(geom.get_editor_property("convex_elems"))
    spheres = list(geom.get_editor_property("sphere_elems"))
    sphyl = list(geom.get_editor_property("sphyl_elems"))

    unreal.log(f"  단순 콜리전: box={len(boxes)}  convex={len(convex)} "
               f"sphere={len(spheres)}  capsule={len(sphyl)}")

    for i, b in enumerate(boxes):
        c = b.get_editor_property("center")
        unreal.log(f"    box[{i}] center=({c.x:.1f},{c.y:.1f},{c.z:.1f}) "
                   f"XYZ=({b.get_editor_property('x'):.1f},"
                   f"{b.get_editor_property('y'):.1f},"
                   f"{b.get_editor_property('z'):.1f})")

    total = len(boxes) + len(convex) + len(spheres) + len(sphyl)
    if total == 0:
        unreal.log("  ⚠ 단순 콜리전 없음 — CTF_UseComplexAsSimple이 아니면 통과해버린다")
