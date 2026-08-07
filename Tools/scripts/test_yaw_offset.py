"""radial()의 yaw_offset 검증 — 스폰 없이 생성기 출력만 확인한다."""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import importlib
import ab_level as L
importlib.reload(L)   # 에디터가 구버전을 캐시했을 수 있다

unreal_log = __import__("unreal").log

# 1) 하위 호환 — yaw_offset 미지정이면 기존 동작 그대로
base = list(L.radial(4, 1000))
unreal_log("[1] yaw_offset 미지정 (기존 동작)")
for loc, rot in base:
    unreal_log(f"    loc=({loc[0]:8.1f},{loc[1]:8.1f},{loc[2]:6.1f})  yaw={rot[1]:7.1f}")

# 2) yaw_offset=90 — 장축이 접선 방향
tang = list(L.radial(4, 1000, yaw_offset=90))
unreal_log("[2] yaw_offset=90 (접선)")
for loc, rot in tang:
    unreal_log(f"    loc=({loc[0]:8.1f},{loc[1]:8.1f},{loc[2]:6.1f})  yaw={rot[1]:7.1f}")

# 3) face_center와 조합
fc = list(L.radial(4, 1000, face_center=True, yaw_offset=90))
unreal_log("[3] face_center=True + yaw_offset=90")
for loc, rot in fc:
    unreal_log(f"    yaw={rot[1]:7.1f}")

# 4) 위치는 yaw_offset에 영향받지 않아야 한다
same_loc = all(a[0] == b[0] for a, b in zip(base, tang))
delta_ok = all(abs((b[1][1] - a[1][1]) - 90) < 1e-9 for a, b in zip(base, tang))
unreal_log(f"\n위치 불변: {same_loc}   yaw 차이가 정확히 +90: {delta_ok}")

# 5) JSON 경로(_build_entry)가 yaw_offset을 실제로 전달하는지
import inspect
src = inspect.getsource(L._build_entry)
unreal_log(f"_build_entry가 yaw_offset 전달: {'yaw_offset' in src}")
