import sys
# 라이플 왼손 IK 파지 소켓 배선 (멱등)
#   1) 총 메시 SKM_RifleScifi_01 의 키트 소켓 LeftHandIK (WeaponRoot 본, 소유 = 총 스켈레톤 SK_RifleScifi) 를 왼손 본 트랜스폼으로 다시 정의 — 키트 원래 값(회전 Yaw 180 = 위치 표식뿐)
#      또는 이 스크립트의 이전 자동값(PREV_AUTO)일 때만 바꾼다. 그 밖의 값이면 그대로(에디터에서 손 모양을 조정한 값 보존), RESET_SOCKET 이면 아래 초기값으로 덮어쓴다.
#      (새 소켓을 만들지 않는 이유: 파이썬에선 SkeletalMeshSocket.SocketName 이 읽기 전용이라 이름을 줄 수 없다 — 2026-10-21 실측)
#   2) BP_Weapon_Rifle(AAstralRangedWeaponActor) 의 LeftHandGripSocket = LeftHandIK → 블루프린트 컴파일 → 저장
# 소켓 = 왼손 본(hand_l) 트랜스폼 그대로. 초기값 = AO 기준 포즈 AS_Vesper_Rifle_AimIdle 프레임 0 의 hand_l 을 무기(WeaponRoot) 공간으로 환산한 값 그대로 —
# 무기 루트 = hand_r 배치(setup/rifle_weapon_grip, 키트 저작 기준)에서 이 손은 이미 핸드가드(키트 LeftHandIK 소켓과 2.9cm)라 조준 Idle 에서 IK 보정이 0 이다.
# (이전 자동값 PREV_AUTO 는 소켓 이중 적용 배치에서 저작 손이 7cm 뒤에 있어 총열 방향으로 7cm 당긴 값이었다 — 2026-10-21 총구 프로브로 배치 오류 확인 뒤 교체)
# 키트의 HandGripTransformLeft 는 손 축이 이 스켈레톤과 달라 손바닥이 핸드가드를 감싸지 않았다(스크린샷).
# 실행은 ue_exec 브릿지 경유 (주의: UE ExecuteFile 모드가 소스 앞부분의 ".p"+"y" 문자열을 파일 경로로 오인하므로 주석에 확장자를 쓰지 말 것)
# 선행: 2026-10-21 C++ 빌드(AAstralWeaponActor::LeftHandGripSocket)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

REVERT = False         # True — BP 소켓 이름을 비운다(왼손 IK 꺼짐). 메시 소켓은 남긴다
RESET_SOCKET = False   # True — 소켓을 아래 초기값으로 덮어쓴다
SOCKET = "LeftHandIK"
KIT_LOC = unreal.Vector(-21.510771, 5.302356, -0.271074)   # 키트 원래 값 — 이 값이면 아직 안 바꾼 것
PREV_AUTO_LOC = unreal.Vector(-21.046881, 4.021411, 2.063029)   # 이전 자동값(이중 적용 배치 기준) — 이 값이면 아직 손으로 조정하지 않은 것
SOCKET_BONE = "WeaponRoot"
SOCKET_LOC = unreal.Vector(-21.684154, 7.324955, 1.768698)
SOCKET_ROT = unreal.Rotator(roll=129.281283, pitch=-8.546929, yaw=-148.074270)

EAL = unreal.EditorAssetLibrary
log = unreal.log
WEAPON_BP = "/Game/Equipment/Weapon/Actor/BP_Weapon_Rifle"
GUN_MESH = "/Game/Assets/Items_CharacterAnims_VFX/Weapon/WeaponMesh/RifleSciFi/SKM_RifleScifi_01"

gun = unreal.load_asset(GUN_MESH)
if not gun:
    raise RuntimeError(f"GRIP_FAIL: load {GUN_MESH}")
sock = gun.find_socket(SOCKET)
if sock is None:
    raise RuntimeError(f"GRIP_FAIL: {GUN_MESH} 에 소켓 {SOCKET} 없음")
# 소켓 이름·본은 파이썬에서 읽기 전용(VisibleAnywhere) — 본은 확인만, 위치·회전·스케일만 쓴다
if str(sock.get_editor_property("bone_name")) != SOCKET_BONE:
    raise RuntimeError(f"GRIP_FAIL: {SOCKET} 본 {sock.get_editor_property('bone_name')} (기대 {SOCKET_BONE}) — 초기값은 {SOCKET_BONE} 기준")
cur_loc = sock.get_editor_property("relative_location")
is_kit = (cur_loc - KIT_LOC).length() < 0.01
is_prev_auto = (cur_loc - PREV_AUTO_LOC).length() < 0.01
if is_kit or is_prev_auto or RESET_SOCKET:
    sock.set_editor_property("relative_location", SOCKET_LOC)
    sock.set_editor_property("relative_rotation", SOCKET_ROT)
    sock.set_editor_property("relative_scale", unreal.Vector(1, 1, 1))
    # 소켓은 메시가 아니라 총 스켈레톤(SK_RifleScifi)에 있을 수 있다 — find_socket 은 메시 → 스켈레톤 순으로 찾는다. 소유 애셋을 저장
    owner = sock.get_outer()
    owner.modify()
    if not EAL.save_loaded_asset(owner, False):
        raise RuntimeError(f"GRIP_FAIL: save {owner.get_path_name()}")
    log(f"GRIP_SOCKET_OWNER_SAVED: {owner.get_path_name()}")
    log(f"GRIP_SOCKET_SET: {GUN_MESH}.{SOCKET} bone={SOCKET_BONE} loc={SOCKET_LOC} rot={SOCKET_ROT} (was kit={is_kit} prev_auto={is_prev_auto})")
else:
    log(f"GRIP_SOCKET_KEPT: {GUN_MESH}.{SOCKET} loc={cur_loc} rot={sock.get_editor_property('relative_rotation')} (조정값 보존)")

bp = unreal.load_asset(WEAPON_BP)
if not bp:
    raise RuntimeError(f"GRIP_FAIL: load {WEAPON_BP}")
want = "None" if REVERT else SOCKET
cdo = unreal.get_default_object(bp.generated_class())
cur = str(cdo.get_editor_property("left_hand_grip_socket"))
if cur != want:
    cdo.set_editor_property("left_hand_grip_socket", "" if REVERT else SOCKET)
    log(f"GRIP_SET: {WEAPON_BP}.LeftHandGripSocket {cur} -> {want}")
else:
    log(f"GRIP_EXISTS: {WEAPON_BP}.LeftHandGripSocket = {cur}")
# CDO 만 바꾸면 스폰된 인스턴스엔 안 들어간다 — BP 생성 클래스는 컴파일 때 "네이티브 부모 기본값과 다른 프로퍼티 목록"
# (CustomPropertyListForPostConstruction)을 만들어 그것만 복사하기 때문(2026-10-21 실측: CDO = 소켓 이름, PIE 인스턴스 = None). 매번 컴파일 → 저장
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
cdo = unreal.get_default_object(bp.generated_class())
after = str(cdo.get_editor_property("left_hand_grip_socket"))
if after != want:
    raise RuntimeError(f"GRIP_FAIL: 컴파일 뒤 CDO 값 {after} (기대 {want})")
if not EAL.save_loaded_asset(bp, False):
    raise RuntimeError(f"GRIP_FAIL: save {WEAPON_BP}")
log(f"GRIP_COMPILED_SAVED: {WEAPON_BP}.LeftHandGripSocket = {after}")
log("GRIP_DONE")
