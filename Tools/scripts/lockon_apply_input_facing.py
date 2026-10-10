"""락온 7단계 — 공격 몽타주에 입력 회전 창(UAstralAnimNotifyState_InputFacing) 배치.

Tools/data/input_facing.json 스펙을 읽어 각 몽타주의 "InputFacing" 트랙을 비우고 다시 배치한다 (재실행 멱등).
창 시각·튜닝 값은 JSON을 바꾸고 재실행한다.
    python Tools/ue_exec.py Tools/scripts/lockon_apply_input_facing.py
실행 전 .uasset 커밋 권고. 에디터는 새 C++ 빌드(UAstralAnimNotifyState_InputFacing 포함)로 떠 있어야 한다.
"""
import sys, importlib, json, pathlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as m; importlib.reload(m)

SPEC_PATH = pathlib.Path(r"D:/UE5Projects/AstralBreak/Tools/data/input_facing.json")
spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))

track = spec.get("track", "InputFacing")
defaults = spec.get("defaults", {})

if not unreal.load_class(None, m.INPUT_FACING_CLASS):
    raise RuntimeError(f"클래스 없음: {m.INPUT_FACING_CLASS} — 에디터가 새 빌드로 떠 있는지 확인")

for entry in spec["montages"]:
    path = entry["montage"]
    mon = unreal.load_asset(path)
    if not mon:
        print(f"[MISSING] {path}")
        continue

    removed = m.clear_track(mon, track)
    settings = {k: entry.get(k, defaults[k]) for k in m.INPUT_FACING_SETTING_KEYS
                if k in entry or k in defaults}
    m.add_input_facing_window(mon, track, entry["start"], entry["duration"], **settings)
    saved = m.save(mon)
    print(f"== {path}  cleared={removed} saved={saved}")
    for e in m.describe_notifies(mon):
        print("   ", json.dumps(e, ensure_ascii=False))
