"""루트모션 폰 충돌 정책 밴드 배치 — Tools/data/pawn_collision.json 스펙.

각 몽타주의 "PawnCollision" 트랙을 비우고 다시 배치한다 (재실행 멱등). 튜닝은 JSON 값을 바꾸고 재실행.
    python Tools/ue_exec.py Tools/scripts/apply_pawn_collision_bands.py
실행 전 .uasset 커밋 권고.
"""
import sys, importlib, json, pathlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as m; importlib.reload(m)

SPEC_PATH = pathlib.Path(r"D:/UE5Projects/AstralBreak/Tools/data/pawn_collision.json")
spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
track = spec.get("track", "PawnCollision")

for entry in spec["montages"]:
    path = entry["montage"]
    mon = unreal.load_asset(path)
    if not mon:
        print(f"[MISSING] {path}")
        continue

    length = float(mon.get_play_length())
    removed = m.clear_track(mon, track)
    for band in entry["bands"]:
        start = float(band.get("start", 0.0))
        duration = band.get("duration")
        duration = (length - start) if duration is None else float(duration)
        m.add_pawn_collision_window(mon, track, start, duration, band.get("policy", "StopOnHit"))
    saved = m.save(mon)
    print(f"== {path}  length={round(length, 4)} cleared={removed} saved={saved}")
    for e in m.describe_notifies(mon):
        if e["track"] == track:
            print("   ", json.dumps(e, ensure_ascii=False))
