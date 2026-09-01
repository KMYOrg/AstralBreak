import sys, importlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as M; importlib.reload(M)

log = unreal.log

da = unreal.load_asset("/Game/System/DA_GameData")
log(f"asset: {da}")

old_cls = da.get_editor_property("UltGainGameplayEffect_SetByCaller")
log(f"old UltGain GE: {old_cls.get_path_name() if old_cls else None}")

# 1) 생성자 키워드 인자
try:
    s = unreal.AstralSetByCallerEffect(effect=old_cls, set_by_caller_tag=M.tag("SetByCaller.UltGain"))
    log(f"CTOR_OK: {s.export_text()}")
except Exception as e:
    log(f"CTOR_FAIL: {e}")
    s = None

# 2) import_text
try:
    s2 = unreal.AstralSetByCallerEffect()
    s2.import_text(f'(Effect="{old_cls.get_path_name()}",SetByCallerTag=(TagName="SetByCaller.UltGain"))')
    log(f"IMPORT_OK: {s2.export_text()}")
    if s is None:
        s = s2
except Exception as e:
    log(f"IMPORT_FAIL: {e}")

# 3) 외부 프로퍼티(da.UltGain) 설정 가능 여부 (저장 안 함)
try:
    da.set_editor_property("UltGain", s)
    log(f"OUTER_SET_OK: {da.get_editor_property('UltGain').export_text()}")
except Exception as e:
    log(f"OUTER_SET_FAIL: {e}")
