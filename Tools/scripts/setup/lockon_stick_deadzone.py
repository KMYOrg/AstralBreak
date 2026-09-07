# 락온 3단계 — IA_Look_Stick 데드존 모디파이어 추가 (멱등).
# 데드존이 없으면 스틱 드리프트로 값이 0에 못 가 Completed가 오지 않고 전환 latch가 안 풀린다.
# 기존 Negate 모디파이어는 건드리지 않고 축별 플래그만 출력한다 (X가 뒤집혀 있으면 스틱 전환 방향도 뒤집힌다)
import unreal

EAL = unreal.EditorAssetLibrary
IA = "/Game/Input/Actions/IA_Look_Stick"
log = unreal.log

ia = unreal.load_asset(IA)
if not ia:
    raise RuntimeError(f"STICK_FAIL: 로드 실패 {IA}")

mods = [m for m in ia.get_editor_property("modifiers") if m]
for m in mods:
    cls = m.get_class().get_name()
    if cls == "InputModifierNegate":
        log(f"STICK_NEGATE_FLAGS: x={m.get_editor_property('x')} y={m.get_editor_property('y')} z={m.get_editor_property('z')}")
    elif cls == "InputModifierDeadZone":
        log(f"STICK_DEADZONE_EXISTS: lower={m.get_editor_property('lower_threshold')} upper={m.get_editor_property('upper_threshold')} type={m.get_editor_property('type')}")

if not any(m.get_class().get_name() == "InputModifierDeadZone" for m in mods):
    # 엔진 기본값(lower 0.2 / upper 1.0 / Radial)을 그대로 쓴다 — 이 객체의 프로퍼티는 Python에서 편집이 거부된다 (템플릿 취급)
    dz = unreal.InputModifierDeadZone(outer=ia)
    # 데드존을 맨 앞에 — 원시 축값에 적용한 뒤 Negate가 부호를 다룬다
    mods.insert(0, dz)
    ia.set_editor_property("modifiers", mods)
    EAL.save_loaded_asset(ia)
    log("STICK_DEADZONE_ADDED: engine defaults (radial 0.2 / 1.0)")

ia2 = unreal.load_asset(IA)
log(f"VERIFY_STICK_MODIFIERS: {[m.get_class().get_name() for m in ia2.get_editor_property('modifiers') if m]}")
log("STICK_SETUP_DONE")
