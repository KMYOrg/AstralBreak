"""빌드 결과 검증 — AB_Generated 액터의 실제 월드 배치를 수치로 확인한다 (읽기 전용)."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import math
import unreal
from collections import defaultdict

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
GEN = unreal.Name("AB_Generated")

groups = defaultdict(list)
others = []

for a in eas.get_all_level_actors():
    if not a:
        continue
    if GEN in list(a.get_editor_property("tags")):
        label = a.get_actor_label()
        key = label.rsplit("_", 1)[0] if label[-2:].isdigit() else label
        groups[key].append(a)
    else:
        others.append(a.get_actor_label())

unreal.log("=== AB_Generated 액터 ===")
for key in sorted(groups):
    actors = groups[key]
    a0 = actors[0]
    org, ext = a0.get_actor_bounds(False)
    size = [round(ext.x * 2), round(ext.y * 2), round(ext.z * 2)]
    zs = sorted({round(x.get_actor_location().z) for x in actors})
    # 액터 원점 기준 반지름 (피벗 보정 전 값) / 메시 실제 중심 반지름 (보정 후 결과)
    radii = sorted({round(math.hypot(x.get_actor_location().x,
                                     x.get_actor_location().y)) for x in actors})
    mesh_r = sorted({round(math.hypot(x.get_actor_bounds(False)[0].x,
                                      x.get_actor_bounds(False)[0].y)) for x in actors})
    yaw = round(a0.get_actor_rotation().yaw, 1)
    unreal.log(f"{key:18s} x{len(actors):<3d} 크기={size}  z={zs}")
    unreal.log(f"{'':18s}      액터R={radii}  메시중심R={mesh_r}  yaw[0]={yaw}")

mn = [1e9] * 3
mx = [-1e9] * 3
for actors in groups.values():
    for a in actors:
        org, ext = a.get_actor_bounds(False)
        for i, (o, e) in enumerate(((org.x, ext.x), (org.y, ext.y), (org.z, ext.z))):
            mn[i] = min(mn[i], o - e)
            mx[i] = max(mx[i], o + e)

unreal.log(f"\n생성물 전체 범위(cm): X[{mn[0]:.0f}, {mx[0]:.0f}]  "
           f"Y[{mn[1]:.0f}, {mx[1]:.0f}]  Z[{mn[2]:.0f}, {mx[2]:.0f}]")
unreal.log(f"태그 없는(템플릿/수동) 액터 {len(others)}개: {others}")
