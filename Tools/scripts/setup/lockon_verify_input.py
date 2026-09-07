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

# 3단계 — IA_Look_Stick 실재·InputConfig 등록·데드존 확인.
# 바인딩이 bLogIfNotFound=False라 미등록이면 조용히 무반응이고, 데드존이 없으면 Completed가 오지 않아 latch가 안 풀린다
STICK = "/Game/Input/Actions/IA_Look_Stick"
stick = unreal.load_asset(STICK)
log(f"VERIFY_STICK_IA: exists={stick is not None}")
if stick:
    mods = [m.get_class().get_name() for m in stick.get_editor_property("modifiers") if m]
    trigs = [t.get_class().get_name() for t in stick.get_editor_property("triggers") if t]
    log(f"VERIFY_STICK_IA_MODIFIERS: {mods}  TRIGGERS: {trigs}")
    for m in mappings:
        if m.get_editor_property("action") == stick:
            key = m.get_editor_property("key").get_editor_property("key_name")
            mmods = [x.get_class().get_name() for x in m.get_editor_property("modifiers") if x]
            log(f"VERIFY_STICK_MAPPING: {key} modifiers={mmods}")
    in_cfg = any(e.get_editor_property("input_action") == stick for e in cfg.get_editor_property("native_input_actions"))
    log(f"VERIFY_STICK_IN_CFG: {in_cfg}")
    has_deadzone = any("DeadZone" in n for n in mods) or any(
        "DeadZone" in x.get_class().get_name()
        for m in mappings if m.get_editor_property("action") == stick
        for x in m.get_editor_property("modifiers") if x)
    log(f"VERIFY_STICK_DEADZONE: {has_deadzone}")

log("LOCKON_VERIFY_DONE")
