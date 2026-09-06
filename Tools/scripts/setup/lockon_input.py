import sys, importlib
# 락온 1단계 입력 콘텐츠 — IA_LockOn 생성 + IMC_Default 키 매핑 + DA_Input_Hero_Default NativeInputActions 등록 (멱등)
# 실행은 ue_exec 브릿지 경유 (주의: UE ExecuteFile 모드가 소스 앞부분의 ".p" + "y" 문자열을 파일 경로로 오인하므로 주석에 확장자를 쓰지 말 것)
# 선행: InputTag.LockOn 네이티브 태그가 등록된 C++ 빌드로 에디터가 떠 있어야 한다
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal
import ab_montage as M; importlib.reload(M)

EAL = unreal.EditorAssetLibrary

IA_SRC = "/Game/Input/Actions/IA_Jump"           # bool 액션 템플릿
IA_DST = "/Game/Input/Actions/IA_LockOn"
IMC    = "/Game/Input/Mappings/IMC_Default"
CFG    = "/Game/Input/DA_Input_Hero_Default"
TAG    = "InputTag.LockOn"
KEYS   = ["MiddleMouseButton", "Gamepad_RightThumbstick"]

log = unreal.log

# 0) 태그 등록 검증 — 미등록이면 여기서 중단 (C++ 미빌드 / 구 바이너리 에디터)
M.tag(TAG)
log(f"LOCKON_TAG_OK: {TAG}")

# 1) IA_LockOn — 기존 bool 액션 복제 후 트리거·모디파이어 비움 (C++가 Started로 바인딩)
if EAL.does_asset_exist(IA_DST):
    ia = unreal.load_asset(IA_DST)
    log(f"LOCKON_IA_EXISTS: {IA_DST}")
else:
    ia = EAL.duplicate_asset(IA_SRC, IA_DST)
    if not ia:
        raise RuntimeError(f"LOCKON_FAIL: IA 복제 실패 {IA_SRC} -> {IA_DST}")
    log(f"LOCKON_IA_CREATED: {IA_DST}")

ia.set_editor_property("value_type", unreal.InputActionValueType.BOOLEAN)
ia.set_editor_property("triggers", [])
ia.set_editor_property("modifiers", [])
EAL.save_loaded_asset(ia)

# 2) IMC_Default 키 매핑 (이미 매핑된 키는 건너뜀)
imc = unreal.load_asset(IMC)
if not imc:
    raise RuntimeError(f"LOCKON_FAIL: IMC 로드 실패 {IMC}")

# 5.7: 매핑은 DefaultKeyMappings.Mappings에 산다 (구 Mappings 프로퍼티는 deprecated — 읽으면 빈 배열)
def _lockon_mappings(context):
    data = context.get_editor_property("default_key_mappings")
    return [m for m in data.get_editor_property("mappings") if m.get_editor_property("action") == ia]

mapped = {str(m.get_editor_property("key").get_editor_property("key_name")) for m in _lockon_mappings(imc)}

for key_name in KEYS:
    if key_name in mapped:
        log(f"LOCKON_KEY_EXISTS: {key_name}")
        continue
    try:
        key = unreal.Key(key_name=key_name)
    except Exception:
        key = unreal.Key()
        key.set_editor_property("key_name", key_name)
    imc.map_key(ia, key)
    log(f"LOCKON_KEY_MAPPED: {key_name}")
# MapKey는 패키지를 dirty로 표시하지 않는다 — only_if_is_dirty=False로 강제 저장해야 디스크에 남는다
EAL.save_asset(IMC, only_if_is_dirty=False)

# 3) InputConfig NativeInputActions 등록
cfg = unreal.load_asset(CFG)
if not cfg:
    raise RuntimeError(f"LOCKON_FAIL: InputConfig 로드 실패 {CFG}")

natives = list(cfg.get_editor_property("native_input_actions"))
if any(e.get_editor_property("input_action") == ia for e in natives):
    log("LOCKON_CFG_EXISTS")
else:
    # 내부 프로퍼티가 EditDefaultsOnly라 인스턴스 set_editor_property가 거부될 수 있어 import_text로 통째 구성
    entry = unreal.AstralInputAction()
    entry.import_text(f'(InputAction="{ia.get_path_name()}",InputTag=(TagName="{TAG}"))')
    natives.append(entry)
    cfg.set_editor_property("native_input_actions", natives)
    log("LOCKON_CFG_ADDED")
EAL.save_loaded_asset(cfg)

# 검증 — 저장 후 다시 읽어 출력
ia2 = unreal.load_asset(IA_DST)
log(f"VERIFY_IA: value_type={ia2.get_editor_property('value_type')} triggers={len(ia2.get_editor_property('triggers'))}")

keys_now = [str(m.get_editor_property("key").get_editor_property("key_name"))
            for m in _lockon_mappings(unreal.load_asset(IMC))]
log(f"VERIFY_IMC: {keys_now}")

found = False
for e in unreal.load_asset(CFG).get_editor_property("native_input_actions"):
    act = e.get_editor_property("input_action")
    tag = e.get_editor_property("input_tag")
    if act == ia2:
        found = True
        log(f"VERIFY_CFG: input_action={act.get_name()} tag={tag.get_editor_property('tag_name')}")
if not found:
    log("VERIFY_CFG_FAIL: NativeInputActions에 IA_LockOn 없음")

log("LOCKON_SETUP_DONE")
