import sys
# 히어로 ABP 콘텐츠 선행 — AS_Vesper_Rifle_AO_CC 의 additive 기준 포즈 지정 (멱등)
# 실측(2026-10-19): CC 만 RefPoseSeq 가 비어 IsValidAdditive 가 false → AimOffset 샘플로 거부(ADDITIVE_INVALID). 나머지 8개는 AS_Vesper_Rifle_Idle 프레임 0 기준
# 실행은 ue_exec 브릿지 경유 (주의: UE ExecuteFile 모드가 소스 앞부분의 ".p"+"y" 문자열을 파일 경로로 오인하므로 주석에 확장자를 쓰지 말 것).
# 2026-10-19 부터는 MCP Tool set_sequence_additive 가 같은 일을 한다 (build_hero_combat 이 호출) — 이 스크립트는 Python 경로용 대안
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

EAL = unreal.EditorAssetLibrary
log = unreal.log

TARGET = "/Game/Animation/Hero/Vesper/Rifle/Aim/AS_Vesper_Rifle_AO_CC"
BASE = "/Game/Animation/Hero/Vesper/Rifle/Locomotion/AS_Vesper_Rifle_Idle"

seq = unreal.load_asset(TARGET)
base = unreal.load_asset(BASE)
if not seq or not base:
    raise RuntimeError(f"AOCC_FAIL: load {TARGET} / {BASE}")

if seq.get_editor_property("ref_pose_seq") == base and seq.get_editor_property("ref_pose_type") == unreal.AdditiveBasePoseType.ABPT_ANIM_FRAME:
    log(f"AOCC_EXISTS: {TARGET} already based on {BASE}")
else:
    seq.set_editor_property("additive_anim_type", unreal.AdditiveAnimationType.AAT_ROTATION_OFFSET_MESH_SPACE)
    seq.set_editor_property("ref_pose_type", unreal.AdditiveBasePoseType.ABPT_ANIM_FRAME)
    seq.set_editor_property("ref_pose_seq", base)
    seq.set_editor_property("ref_frame_index", 0)
    if not EAL.save_loaded_asset(seq, False):
        raise RuntimeError(f"AOCC_FAIL: save {TARGET}")
    log(f"AOCC_SET: {TARGET} ref_pose_seq={BASE} frame=0")

log(f"AOCC_DONE: skeleton={seq.get_editor_property('skeleton').get_path_name()} additive={seq.get_editor_property('additive_anim_type')} ref={seq.get_editor_property('ref_pose_seq').get_path_name()}")
