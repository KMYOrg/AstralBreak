"""락온 4단계 — 공격 몽타주에 MotionWarping(회전 전용) 밴드 배치.

Tools/data/facing_warp.json 스펙을 읽어 각 몽타주의 "Facing" 트랙을 비우고 다시 배치한다 (재실행 멱등).
밴드 종료 시각 튜닝(완료 기준 5 — 곡선 휨)은 JSON 값을 바꾸고 재실행한다.
    python Tools/ue_exec.py Tools/scripts/lockon_apply_facing_warp.py
실행 전 .uasset 커밋 권고.
"""
import sys, importlib, json, pathlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as m; importlib.reload(m)

SPEC_PATH = pathlib.Path(r"D:/UE5Projects/AstralBreak/Tools/data/facing_warp.json")
spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))

track = spec.get("track", "Facing")
defaults = spec.get("defaults", {})

for entry in spec["montages"]:
    path = entry["montage"]
    mon = unreal.load_asset(path)
    if not mon:
        print(f"[MISSING] {path}")
        continue

    removed = m.clear_track(mon, track)
    extra = {k: entry.get(k, defaults[k]) for k in m.MOTION_WARPING_MODIFIER_KEYS
             if k in entry or k in defaults}
    m.add_motion_warping_window(
        mon, track, entry["start"], entry["duration"], entry["warp_target_name"],
        warp_rotation=entry.get("warp_rotation", defaults.get("warp_rotation", True)),
        warp_translation=entry.get("warp_translation", defaults.get("warp_translation", False)),
        **extra)
    saved = m.save(mon)
    print(f"== {path}  cleared={removed} saved={saved}")
    for e in m.describe_notifies(mon):
        print("   ", json.dumps(e, ensure_ascii=False))
