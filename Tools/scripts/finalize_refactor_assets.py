# 마무리: DA_Hero_Hub_Vesper 삭제 + 리다이렉터 정리 + 최종 상태 검증 (읽기 위주)
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary
AR = unreal.AssetRegistryHelpers.get_asset_registry()

def refs_of(pkg):
    return [str(r) for r in (AR.get_referencers(unreal.Name(pkg), unreal.AssetRegistryDependencyOptions()) or [])]

# 1. DA_Hero_Hub_Vesper 삭제
p = "/Game/Characters/Hero/Data/DA_Hero_Hub_Vesper"
if EAL.does_asset_exist(p):
    r = refs_of(p)
    if r:
        print(f"[HOLD] DA_Hero_Hub_Vesper 참조 잔존: {r} — 삭제 보류")
    else:
        print(f"[{'OK' if EAL.delete_asset(p) else 'FAIL'}] DA_Hero_Hub_Vesper 삭제")
else:
    print("[OK] DA_Hero_Hub_Vesper 이미 없음")

# 2. 개명 리다이렉터 정리 (참조 0이면)
rd = "/Game/Characters/Hero/Data/DA_Hero_Raid_Vesper"
if EAL.does_asset_exist(rd):
    r = refs_of(rd)
    if r:
        print(f"[HOLD] 리다이렉터 참조 잔존: {r} — 에디터 Fix Up Redirectors 권장")
    else:
        print(f"[{'OK' if EAL.delete_asset(rd) else 'FAIL'}] 리다이렉터 삭제")
else:
    print("[OK] 리다이렉터 없음")

# 3. BP_Hero_Vesper_Hub 참조 현황 (E-6 판단용 — 삭제는 사용자 결정)
print(f"[Info] BP_Hero_Vesper_Hub 참조자: {refs_of('/Game/Characters/Hero/BP_Hero_Vesper_Hub') or '없음'}")

# 4. 최종 검증
for gm in ["/Game/GameModes/BP_AstralGameMode_Hub", "/Game/GameModes/BP_AstralGameMode_Raid"]:
    cdo = unreal.get_default_object(EAL.load_asset(gm).generated_class())
    gs = cdo.get_editor_property("game_state_class")
    pd = cdo.get_editor_property("default_pawn_data")
    print(f"[Verify] {gm.split('/')[-1]}: GSC={gs.get_name() if gs else 'None'} PawnData={pd.get_name() if pd else 'None'}")

for gsp in ["/Game/GameModes/BP_AstralGameState_Hub", "/Game/GameModes/BP_AstralGameState_Raid"]:
    cdo = unreal.get_default_object(EAL.load_asset(gsp).generated_class())
    pol = cdo.get_editor_property("equipment_policy")
    ctx = [s.get_name() for s in cdo.get_editor_property("context_ability_sets") if s]
    print(f"[Verify] {gsp.split('/')[-1]}: Policy={pol} Context={ctx}")

pd = EAL.load_asset("/Game/Characters/Hero/Data/DA_Hero_Vesper")
print(f"[Verify] DA_Hero_Vesper: sets={[s.get_name() for s in pd.get_editor_property('ability_sets') if s]} pawn={pd.get_editor_property('pawn_class').get_name()}")

ga = EAL.load_asset("/Game/AbilitySystem/Abilities/GA_Hero_UltGainOnDamaged")
cdo = unreal.get_default_object(ga.generated_class())
print(f"[Verify] GA_Hero_UltGainOnDamaged: GainRatio={cdo.get_editor_property('gain_ratio')}")
print("FINALIZE_DONE")
