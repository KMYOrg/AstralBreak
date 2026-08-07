"""메시 피벗 위치 확인 — 배치 z값을 정하기 위한 읽기 전용 조회."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal

TARGETS = [
    "/Game/Assets/SlashFX/Demo/Meshes/SM_DemoRoomClamp",
    "/Game/Assets/SciFi_VFX/DemoRoom/Meshes/SM_Base_FlatWall",
    "/Engine/BasicShapes/Cylinder",
]

for path in TARGETS:
    m = unreal.load_asset(path)
    if not m:
        unreal.log_error(f"로드 실패: {path}")
        continue
    b = m.get_bounds()
    o, e = b.origin, b.box_extent
    size = [round(e.x * 2, 1), round(e.y * 2, 1), round(e.z * 2, 1)]
    # origin.z == 0 이면 중심 피벗, origin.z == extent.z 이면 밑면 피벗
    if abs(o.z) < 1.0:
        pivot = "중심(center)"
    elif abs(o.z - e.z) < 1.0:
        pivot = "밑면(base)"
    else:
        pivot = f"기타(offset z={o.z:.1f})"
    unreal.log(f"{path.split('/')[-1]:22s} size={size}")
    unreal.log(f"{'':22s} origin=({o.x:.1f}, {o.y:.1f}, {o.z:.1f})  피벗={pivot}")
    unreal.log(f"{'':22s} 장축={'X' if e.x > e.y else 'Y'}")
