import sys, json, os
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_level as L

DATA_DIR = r"D:/UE5Projects/AstralBreak/Tools/data"
SPEC_NAME = "L_RaidArena_Test.layout.json"   # 맵 바꿀 때 여기만 수정
DRY_RUN = False

spec_path = os.path.join(DATA_DIR, SPEC_NAME)
with open(spec_path, encoding="utf-8-sig") as f:
    spec = json.load(f)

unreal.log(f"=== {spec['map']} (mode={spec.get('mode','new')}) "
           f"{'[DRY RUN]' if DRY_RUN else ''} ===")

try:
    r = L.build(spec, dry_run=DRY_RUN)
    unreal.log(f"[OK] {r}")
except Exception as e:
    unreal.log_error(f"[FAIL] {type(e).__name__}: {e}")
    raise