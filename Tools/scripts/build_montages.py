import sys, json, os
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_montage as m

DRY_RUN = os.environ.get("AB_DRY_RUN", "0") == "1"
SPEC = r"D:/UE5Projects/AstralBreak/Tools/data/montages.json"

with open(SPEC, encoding="utf-8-sig") as f:
    data = json.load(f)

unreal.log(f"=== 몽타주 {len(data['montages'])}개 "
           f"{'[DRY RUN]' if DRY_RUN else ''} ===")

ok = fail = 0
for spec in data["montages"]:
    try:
        r = m.build_from_spec(spec, dry_run=DRY_RUN)
        unreal.log(f"[OK]   {r}")
        ok += 1
    except Exception as e:
        unreal.log_error(f"[FAIL] {spec.get('name')}: {type(e).__name__}: {e}")
        fail += 1

unreal.log(f"=== 완료: 성공 {ok}, 실패 {fail} ===")
if fail:
    raise SystemExit(1)