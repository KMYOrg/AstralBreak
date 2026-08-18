# 리팩터링 E-5/D-3 애셋 작업 — GA BP·GameState BP 생성 + 배선 + PawnData 통합
import sys, importlib
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_blueprint as B; importlib.reload(B)

EAL = unreal.EditorAssetLibrary
OK = []
FAIL = []

def step(name, fn):
    try:
        r = fn()
        OK.append(name)
        print(f"[OK] {name}" + (f" -> {r}" if r not in (None, [],) else ""))
        return r
    except Exception as e:
        FAIL.append((name, str(e)))
        print(f"[FAIL] {name}: {e}")
        return None

# ---------- 1. GA_Hero_UltGainOnDamaged BP ----------
GA_PATH = "/Game/AbilitySystem/Abilities/GA_Hero_UltGainOnDamaged"

def make_ga():
    if EAL.does_asset_exist(GA_PATH):
        return "이미 존재 — 스킵"
    bp = B.create_bp(GA_PATH, "/Script/AstralBreak.AstralGA_Hero_UltGainOnDamaged")
    fails = B.set_defaults(bp, {"GainRatio": 0.5})
    if fails:
        raise RuntimeError(f"set_defaults 실패 키: {fails}")
    EAL.save_asset(GA_PATH)
    return "생성 + GainRatio=0.5"
step("GA_Hero_UltGainOnDamaged 생성", make_ga)

# ---------- 2. DA_AbilitySet_Vesper 에 등록 ----------
def register_ga():
    ga_bp = EAL.load_asset(GA_PATH)
    ga_cls = ga_bp.generated_class()
    ds = EAL.load_asset("/Game/AbilitySystem/AbilitySets/Hero/DA_AbilitySet_Vesper")
    arr = list(ds.get_editor_property("granted_gameplay_abilities"))
    for e in arr:
        ab = e.get_editor_property("ability")
        if ab and ab.get_name() == ga_cls.get_name():
            return "이미 등록 — 스킵"
    entry = unreal.AstralAbilitySet_GameplayAbility()
    entry.set_editor_property("ability", ga_cls)
    entry.set_editor_property("ability_level", 1)
    arr.append(entry)
    ds.set_editor_property("granted_gameplay_abilities", arr)
    EAL.save_loaded_asset(ds)
    return f"등록 완료 (총 {len(arr)}개)"
step("DA_AbilitySet_Vesper 등록", register_ga)

# ---------- 3. GameState BP 2개 생성 + ContextAbilitySets ----------
GS_HUB = "/Game/GameModes/BP_AstralGameState_Hub"
GS_RAID = "/Game/GameModes/BP_AstralGameState_Raid"

def make_gs(path, parent, context_set_path):
    if not EAL.does_asset_exist(path):
        B.create_bp(path, parent)
    bp = EAL.load_asset(path)
    cdo = unreal.get_default_object(bp.generated_class())
    ctx = EAL.load_asset(context_set_path)
    cdo.set_editor_property("context_ability_sets", [ctx])
    EAL.save_loaded_asset(bp)
    return f"ContextAbilitySets=[{ctx.get_name()}]"
step("BP_AstralGameState_Hub 생성", lambda: make_gs(GS_HUB, "/Script/AstralBreak.AstralHubGameState", "/Game/AbilitySystem/AbilitySets/DA_AbilitySet_Hub"))
step("BP_AstralGameState_Raid 생성", lambda: make_gs(GS_RAID, "/Script/AstralBreak.AstralGameState", "/Game/AbilitySystem/AbilitySets/DA_AbilitySet_Default"))

# ---------- 4. PawnData 정리: Default 세트 제거 (문맥 축으로 이동했으므로) ----------
PD_OLD = "/Game/Characters/Hero/Data/DA_Hero_Raid_Vesper"
PD_NEW = "/Game/Characters/Hero/Data/DA_Hero_Vesper"

def trim_pawndata_sets():
    ds = EAL.load_asset(PD_OLD if EAL.does_asset_exist(PD_OLD) else PD_NEW)
    sets = [s for s in ds.get_editor_property("ability_sets") if s and s.get_name() != "DA_AbilitySet_Default"]
    ds.set_editor_property("ability_sets", sets)
    EAL.save_loaded_asset(ds)
    return f"남은 세트: {[s.get_name() for s in sets]}"
step("PawnData 히어로 축 정리", trim_pawndata_sets)

# ---------- 5. 개명: DA_Hero_Raid_Vesper -> DA_Hero_Vesper ----------
def rename_pd():
    if EAL.does_asset_exist(PD_NEW):
        return "이미 존재 — 스킵"
    if not EAL.rename_asset(PD_OLD, PD_NEW):
        raise RuntimeError("rename 실패")
    return "개명 완료 (리다이렉터 생성됨)"
step("PawnData 개명", rename_pd)

# ---------- 6. GameMode 배선 ----------
def wire_gm(gm_path, gs_path, pd_path):
    gm = EAL.load_asset(gm_path)
    cdo = unreal.get_default_object(gm.generated_class())
    cdo.set_editor_property("game_state_class", EAL.load_asset(gs_path).generated_class())
    cdo.set_editor_property("default_pawn_data", EAL.load_asset(pd_path))
    EAL.save_loaded_asset(gm)
    return "GSC+PawnData 배선"
step("Hub GameMode 배선", lambda: wire_gm("/Game/GameModes/BP_AstralGameMode_Hub", GS_HUB, PD_NEW))
step("Raid GameMode 배선", lambda: wire_gm("/Game/GameModes/BP_AstralGameMode_Raid", GS_RAID, PD_NEW))

# ---------- 7. DA_Hero_Hub_Vesper 삭제 (참조 해제 후) ----------
def delete_hub_pd():
    p = "/Game/Characters/Hero/Data/DA_Hero_Hub_Vesper"
    if not EAL.does_asset_exist(p):
        return "이미 없음 — 스킵"
    deps = unreal.AssetRegistryHelpers.get_asset_registry().get_referencers(unreal.Name(p), unreal.AssetRegistryDependencyOptions())
    if deps:
        raise RuntimeError(f"아직 참조 존재: {[str(d) for d in deps]} — 삭제 보류")
    if not EAL.delete_asset(p):
        raise RuntimeError("delete_asset 실패")
    return "삭제 완료"
step("DA_Hero_Hub_Vesper 삭제", delete_hub_pd)

print("=== 요약 ===")
print(f"성공 {len(OK)}: {OK}")
print(f"실패 {len(FAIL)}: {FAIL}")
print("BUILD_REFACTOR_DONE")
