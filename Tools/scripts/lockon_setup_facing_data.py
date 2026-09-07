"""락온 4단계 — 공격 GA BP의 Facing 데이터 세팅.

GA_Hero_BasicAttack_Melee: ComboStages[i].FacingWarpTargetName = BasicMelee.Stage{i} (MaxAssistYaw는 C++ 기본 90 유지).
GA_Hero_MarkFinisher: C++ 기본값(MarkFinisher.Facing / 120)이라 확인만 한다.
워프 이름은 Tools/data/facing_warp.json의 warp_target_name과 일치해야 한다 — ValidateComboStageMontages가 런타임에 대조.
    python Tools/ue_exec.py Tools/scripts/lockon_setup_facing_data.py
"""
import sys, importlib, re
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_blueprint as b; importlib.reload(b)

MELEE_BP = "/Game/AbilitySystem/Abilities/GA_Hero_BasicAttack_Melee"
FINISHER_BP = "/Game/AbilitySystem/Abilities/GA_Hero_MarkFinisher"
STAGE_NAME_FMT = "BasicMelee.Stage{}"

bp = unreal.load_asset(MELEE_BP)
if not bp:
    raise RuntimeError(f"BP 로드 실패: {MELEE_BP}")

cdo = unreal.get_default_object(bp.generated_class())
stages = list(cdo.get_editor_property("combo_stages"))
print(f"== {MELEE_BP}: {len(stages)} stages")

def set_struct_field_via_text(struct, field: str, value: str):
    """EditDefaultsOnly 프로퍼티는 struct 인스턴스에 set_editor_property가 막힌다
    ('cannot be edited on instances'). export_text/import_text로 우회 — CDO 배열에 되돌려 쓰는 건 허용된다."""
    txt = struct.export_text()
    pattern = re.compile(rf"{field}=(\"[^\"]*\"|[^,\)]*)")
    if pattern.search(txt):
        txt = pattern.sub(f'{field}="{value}"', txt, count=1)
    else:
        txt = txt[:-1] + f',{field}="{value}")' if txt.endswith(")") else f'({field}="{value}")'
    struct.import_text(txt)


new_stages = []
for i, stage in enumerate(stages):
    s = unreal.AstralComboStageData(stage) if not isinstance(stage, unreal.AstralComboStageData) else stage
    set_struct_field_via_text(s, "FacingWarpTargetName", STAGE_NAME_FMT.format(i))
    montage = s.get_editor_property("montage")
    print(f"   stage {i}: montage={montage.get_name() if montage else None} "
          f"warp={s.get_editor_property('facing_warp_target_name')} "
          f"max_assist_yaw={s.get_editor_property('max_assist_yaw')}")
    new_stages.append(s)

# 구조체 배열은 값 복사라 통째로 되돌려 써야 CDO에 반영된다
cdo.set_editor_property("combo_stages", new_stages)
print("   compile+save:", b.compile_and_save(bp))

fin = unreal.load_asset(FINISHER_BP)
if fin:
    fcdo = unreal.get_default_object(fin.generated_class())
    print(f"== {FINISHER_BP}: warp={fcdo.get_editor_property('facing_warp_target_name')} "
          f"max_assist_yaw={fcdo.get_editor_property('max_assist_yaw')} "
          f"montage={fcdo.get_editor_property('attack_montage')}")
else:
    print(f"[MISSING] {FINISHER_BP}")
