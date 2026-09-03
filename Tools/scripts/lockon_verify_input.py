# 락온 입력 콘텐츠 검증 — IMC_Default의 DefaultKeyMappings(5.7 신규 구조)에서 IA_LockOn 매핑을 읽는다
import unreal

EAL = unreal.EditorAssetLibrary
IA  = "/Game/Input/Actions/IA_LockOn"
IMC = "/Game/Input/Mappings/IMC_Default"
CFG = "/Game/Input/DA_Input_Hero_Default"
log = unreal.log

ia = unreal.load_asset(IA)
log(f"VERIFY_IA: exists={ia is not None} value_type={ia.get_editor_property('value_type') if ia else None}")

imc = unreal.load_asset(IMC)
data = imc.get_editor_property("default_key_mappings")
mappings = data.get_editor_property("mappings")
log(f"VERIFY_IMC_TOTAL: {len(mappings)}")
lockon_keys = []
for m in mappings:
    act = m.get_editor_property("action")
    key = m.get_editor_property("key").get_editor_property("key_name")
    if act == ia:
        lockon_keys.append(str(key))
log(f"VERIFY_IMC_LOCKON_KEYS: {lockon_keys}")

cfg = unreal.load_asset(CFG)
for e in cfg.get_editor_property("native_input_actions"):
    act = e.get_editor_property("input_action")
    tag = e.get_editor_property("input_tag").get_editor_property("tag_name")
    log(f"VERIFY_CFG_NATIVE: {act.get_name() if act else None} -> {tag}")

log("LOCKON_VERIFY_DONE")
