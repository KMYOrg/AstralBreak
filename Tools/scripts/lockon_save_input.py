# 락온 입력 콘텐츠 강제 저장 — MapKey가 패키지를 dirty로 표시하지 않아 save_loaded_asset(only_if_is_dirty)이 건너뛴 케이스 대응
import unreal

EAL = unreal.EditorAssetLibrary
for path in ("/Game/Input/Mappings/IMC_Default",
             "/Game/Input/Actions/IA_LockOn",
             "/Game/Input/DA_Input_Hero_Default"):
    ok = EAL.save_asset(path, only_if_is_dirty=False)
    unreal.log(f"LOCKON_SAVE: {path} -> {ok}")
unreal.log("LOCKON_SAVE_DONE")
