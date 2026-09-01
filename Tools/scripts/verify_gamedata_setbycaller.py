import unreal
# Phase B 이후 최종 검증 — 구 프로퍼티 삭제 상태에서 구조체 3개가 디스크로부터 정상 로드되는지

da = unreal.load_asset("/Game/System/DA_GameData")
if not da:
    raise RuntimeError("VERIFY_FAIL: DA_GameData 로드 실패")

EXPECT = [
    ("UltGain", "SetByCaller.UltGain"),
    ("MarkGain", "SetByCaller.MarkGain"),
    ("StaminaDrain", "SetByCaller.StaminaDrain"),
]

all_ok = True
for prop, tag_str in EXPECT:
    v = da.get_editor_property(prop)
    eff = v.get_editor_property("Effect")
    tag = str(v.get_editor_property("SetByCallerTag").get_editor_property("tag_name"))
    ok = bool(eff) and tag == tag_str
    all_ok = all_ok and ok
    unreal.log(f"VERIFY_{'OK' if ok else 'FAIL'}: {prop} Effect={eff.get_path_name() if eff else None} Tag={tag}")

# 구 프로퍼티가 정말 사라졌는지 (예외가 나야 정상)
try:
    da.get_editor_property("UltGainGameplayEffect_SetByCaller")
    unreal.log("OLD_PROP_STILL_EXISTS (비정상)")
except Exception:
    unreal.log("OLD_PROP_REMOVED (정상)")

unreal.log(f"RESULT: {'ALL_OK' if all_ok else 'HAS_FAILURES'}")
