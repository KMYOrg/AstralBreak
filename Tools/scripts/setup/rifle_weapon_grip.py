import sys
# 라이플 파지 배치 (멱등) — 무기 루트(WeaponRoot)를 손 본 hand_r 에 그대로 붙인다 = 애니 키트의 저작 기준
#   (조준 애니 AS_IdleRifleAiming_02 의 ik_hand_gun == hand_r, 이 배치에서 저작 왼손 hand_l 이 키트 LeftHandIK 소켓과 2.9cm)
#   1) DA_EF_Rifle.ActorsToSpawn[*].AttachSocket: WeaponHandR → hand_r (WeaponHandR 는 낫 계열과 공유하는 소켓 — 회전이 있어 라이플 저작 기준과 다르다)
#   2) DA_WD_Rifle1.MeshInfo.AttachOffset: 소켓 상대값과 같은 값(이중 적용)이면 → 항등. 다른 값이면 조정값으로 보고 건드리지 않는다
# 근거(2026-10-21 총구 프로브 pie_muzzle_probe_run): 이전 배치는 소켓 + 같은 값의 AttachOffset 이 두 번 적용돼 정지 조준에서 총열이 발사 방향보다
#   Yaw +10.3 · Pitch +4.9 (hand_r 그대로면 2.3°). 홀스터는 별도 HolsterOffset(bOverrideHolsterOffset)이라 영향 없음
# 왼손 파지 소켓은 무기 공간이라 이 배치에 맞춰 다시 정의한다 — setup/rifle_left_hand_grip (RESET 없이도 이전 자동값이면 갱신)
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import unreal

REVERT = False   # True — 이전 배치(WeaponHandR + 소켓 상대값 AttachOffset)로 되돌린다

EAL = unreal.EditorAssetLibrary
log = unreal.log
FAMILY = "/Game/Equipment/Weapon/DA_EF_Rifle"
DEFINITION = "/Game/Equipment/Weapon/Definition/DA_WD_Rifle1"
HERO_MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_02"
OLD_SOCKET = "WeaponHandR"
HAND_BONE = "hand_r"


def same_transform(a, b, tol=1e-3):
    return (a.translation - b.translation).length() < tol and a.rotation.angular_distance(b.rotation) < 1e-4


hero = unreal.load_asset(HERO_MESH)
sock = hero.find_socket(OLD_SOCKET) if hero else None
if sock is None:
    raise RuntimeError(f"RIFLE_GRIP_FAIL: {HERO_MESH} 에 소켓 {OLD_SOCKET} 없음")
sock_rel = unreal.Transform(sock.get_editor_property("relative_location"), sock.get_editor_property("relative_rotation"), sock.get_editor_property("relative_scale"))

# 1) 계열 — 손 부착 소켓
fam = unreal.load_asset(FAMILY)
spawns = fam.get_editor_property("ActorsToSpawn")
want_socket = OLD_SOCKET if REVERT else HAND_BONE
changed = False
for i, sp in enumerate(spawns):
    cur = str(sp.get_editor_property("AttachSocket"))
    if cur in (OLD_SOCKET, HAND_BONE) and cur != want_socket:
        # 구조체 멤버가 EditDefaultsOnly 라 파이썬 set_editor_property 가 거부한다("cannot be edited on instances") — 텍스트 export/import 로 바꾼다
        sp.import_text(sp.export_text().replace(f'AttachSocket="{cur}"', f'AttachSocket="{want_socket}"'))
        if str(sp.get_editor_property("AttachSocket")) != want_socket:
            raise RuntimeError(f"RIFLE_GRIP_FAIL: [{i}] AttachSocket 텍스트 교체 실패 — {sp.export_text()}")
        spawns[i] = sp
        changed = True
        log(f"RIFLE_GRIP_SOCKET: {FAMILY}.ActorsToSpawn[{i}].AttachSocket {cur} -> {want_socket}")
    else:
        log(f"RIFLE_GRIP_SOCKET_KEPT: [{i}] {cur}")
    if not same_transform(sp.get_editor_property("AttachTransform"), unreal.Transform()):
        log(f"RIFLE_GRIP_WARN: [{i}] AttachTransform 가 항등이 아니다 — 배치가 hand_r 그대로가 아님 {sp.get_editor_property('AttachTransform')}")
if changed:
    fam.set_editor_property("ActorsToSpawn", spawns)
    if not EAL.save_loaded_asset(fam, False):
        raise RuntimeError(f"RIFLE_GRIP_FAIL: save {FAMILY}")

# 2) 변형 — 메시 자세값
wd = unreal.load_asset(DEFINITION)
mi = wd.get_editor_property("MeshInfo")
off = mi.get_editor_property("AttachOffset")
want_off = sock_rel if REVERT else unreal.Transform()
if same_transform(off, want_off):
    log(f"RIFLE_GRIP_OFFSET_KEPT: {DEFINITION}.AttachOffset = {off.rotation.rotator()} {off.translation}")
elif REVERT or same_transform(off, sock_rel):
    # 위와 같은 이유로 텍스트 교체 — MeshInfo 텍스트 안의 AttachOffset=(현재 값) 을 새 값으로
    old_text, new_text = f"AttachOffset={off.export_text()}", f"AttachOffset={want_off.export_text()}"
    mi_text = mi.export_text()
    if old_text not in mi_text:
        raise RuntimeError(f"RIFLE_GRIP_FAIL: MeshInfo 텍스트에서 AttachOffset 을 찾지 못함 — {mi_text[:300]}")
    mi.import_text(mi_text.replace(old_text, new_text))
    if not same_transform(mi.get_editor_property("AttachOffset"), want_off):
        raise RuntimeError(f"RIFLE_GRIP_FAIL: AttachOffset 텍스트 교체 실패 — {mi.export_text()[:300]}")
    wd.set_editor_property("MeshInfo", mi)
    if not EAL.save_loaded_asset(wd, False):
        raise RuntimeError(f"RIFLE_GRIP_FAIL: save {DEFINITION}")
    log(f"RIFLE_GRIP_OFFSET: {DEFINITION}.AttachOffset -> {want_off.rotation.rotator()} {want_off.translation}")
else:
    log(f"RIFLE_GRIP_OFFSET_CUSTOM: {DEFINITION}.AttachOffset 가 소켓 이중 적용값도 항등도 아니다 — 조정값으로 보고 유지 {off.rotation.rotator()} {off.translation}")
log("RIFLE_GRIP_DONE")
