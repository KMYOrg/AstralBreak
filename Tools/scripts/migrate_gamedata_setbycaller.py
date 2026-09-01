import sys, importlib
# DA_GameData 마이그레이션 — 구 soft class ptr 3개 → FAstralSetByCallerEffect 구조체 3개 (Phase A 상태에서 1회 실행)
# 실행은 ue_exec 브릿지 경유 (주의: UE ExecuteFile 모드가 소스 앞부분의 ".p" + "y" 문자열을 파일 경로로 오인하므로 주석에 확장자를 쓰지 말 것)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as M; importlib.reload(M)

ASSET = "/Game/System/DA_GameData"

PAIRS = [
    # (구 프로퍼티, 새 구조체 프로퍼티, SetByCaller 태그 — AstralSetByCallerGameplayTags.cpp와 일치)
    ("UltGainGameplayEffect_SetByCaller",      "UltGain",      "SetByCaller.UltGain"),
    ("MarkGainGameplayEffect_SetByCaller",     "MarkGain",     "SetByCaller.MarkGain"),
    ("StaminaDrainGameplayEffect_SetByCaller", "StaminaDrain", "SetByCaller.StaminaDrain"),
]

da = unreal.load_asset(ASSET)
if not da:
    raise RuntimeError(f"MIGRATE_FAIL: 애셋 로드 실패 {ASSET}")

migrated = 0
for old_prop, new_prop, tag_str in PAIRS:
    old_cls = da.get_editor_property(old_prop)
    if not old_cls:
        unreal.log_warning(f"MIGRATE_SKIP: {old_prop} 값이 비어 있음")
        continue

    M.tag(tag_str)  # 태그 등록 검증 — 미등록이면 예외

    # 내부 프로퍼티가 EditDefaultsOnly라 set_editor_property는 인스턴스 편집 거부 — import_text로 통째 구성
    s = unreal.AstralSetByCallerEffect()
    s.import_text(f'(Effect="{old_cls.get_path_name()}",SetByCallerTag=(TagName="{tag_str}"))')
    da.set_editor_property(new_prop, s)
    migrated += 1
    unreal.log(f"MIGRATE_OK: {new_prop} <- {old_cls.get_path_name()} + {tag_str}")

saved = unreal.EditorAssetLibrary.save_asset(ASSET, only_if_is_dirty=False)
unreal.log(f"MIGRATE_SAVE: {saved} (이전 {migrated}건)")

# 저장 후 재검증 — 새 필드 읽어서 출력
for _, new_prop, tag_str in PAIRS:
    v = da.get_editor_property(new_prop)
    eff = v.get_editor_property("Effect")
    tag = v.get_editor_property("SetByCallerTag")
    ok = bool(eff) and str(tag.get_editor_property("tag_name")) == tag_str
    unreal.log(f"VERIFY_{'OK' if ok else 'FAIL'}: {new_prop} Effect={eff.get_path_name() if eff else None} Tag={tag.get_editor_property('tag_name')}")
