# Phase 8-4a E0 — 낫 부착값 읽기(읽기 전용: load_asset · get_editor_property · export_text, 저장 없음 · 더티 전후 기록).
# 원격 실행(UDP)이 안 되는 환경용 에디터 시작 스크립트 — 결과 Tools/mcp/results/p84_weapon_attach.json(gitignore)을 anim_gen_phase8_4_test.py e0 가 읽는다:
#   UnrealEditor-Win64-DebugGame.exe <uproject> -log -unattended -ExecutePythonScript=<이 파일 절대 경로>
# -ExecutePythonScript 는 스크립트가 끝나면 에디터를 닫으므로(EditorPythonExecuter.cpp:73) 끝에서 살려 둔다 — 같은 기동으로 브리지 측정을 잇는다.
# 게임 배치: 무기 메시 월드 = MeshInfo.AttachOffset · ActorsToSpawn[0].AttachTransform · 소켓 상대 · 손 본 (AstralWeaponActor.cpp:74 · AstralEquipmentInstance.cpp:110)
import json
import os
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
OUT = os.path.join(ROOT, "Tools", "mcp", "results", "p84_weapon_attach.json")
FAMILY = "/Game/Equipment/Weapon/DA_EF_Sickle"
DEFINITION = "/Game/Equipment/Weapon/Definition/DA_WD_Sickle1"
HERO_MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
WEAPON = "/Game/Equipment/Weapon/Mesh/SKM_Hero_Sickle"
SOCKET = "WeaponHandR"


def tr(t):
    r = t.rotation.rotator()
    q = t.rotation
    return {"location": [t.translation.x, t.translation.y, t.translation.z], "rotation_pyr": [r.pitch, r.yaw, r.roll],
            "quat_xyzw": [q.x, q.y, q.z, q.w], "scale": [t.scale3d.x, t.scale3d.y, t.scale3d.z]}


def socket_tr(s):
    return tr(unreal.Transform(s.get_editor_property("relative_location"), s.get_editor_property("relative_rotation"), s.get_editor_property("relative_scale")))


def dirty():
    return sorted(p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())


out = {"ok": False}
try:
    out["dirty_before"] = dirty()
    fam = unreal.load_asset(FAMILY)
    spawns = []
    for sp in fam.get_editor_property("ActorsToSpawn"):
        cls = sp.get_editor_property("ActorToSpawn")
        item = {"actor": cls.get_path_name() if cls else None, "attach_socket": str(sp.get_editor_property("AttachSocket")),
                "attach_transform": tr(sp.get_editor_property("AttachTransform")), "holster_socket": str(sp.get_editor_property("HolsterSocket"))}
        if cls:
            cdo = unreal.get_default_object(cls)
            for name in ("LeftHandGripSocket", "TraceStartSocket", "TraceEndSocket"):
                item[name] = str(cdo.get_editor_property(name))
        spawns.append(item)
    out["family"] = {"asset": FAMILY, "actors_to_spawn": spawns}
    mi = unreal.load_asset(DEFINITION).get_editor_property("MeshInfo")
    out["definition"] = {"asset": DEFINITION, "mesh": str(mi.get_editor_property("Mesh")), "attach_offset": tr(mi.get_editor_property("AttachOffset"))}
    sock = unreal.load_asset(HERO_MESH).find_socket(SOCKET)
    out["socket"] = None if sock is None else {"name": SOCKET, "bone": str(sock.get_editor_property("bone_name")), "relative": socket_tr(sock)}
    weapon = unreal.load_asset(WEAPON)
    out["weapon_sockets"] = [{"name": str(weapon.get_socket_by_index(i).get_editor_property("socket_name")),
                              "bone": str(weapon.get_socket_by_index(i).get_editor_property("bone_name")),
                              "relative": socket_tr(weapon.get_socket_by_index(i))} for i in range(weapon.num_sockets())]
    out["dirty_after"] = dirty()
    out["ok"] = True
except Exception as e:  # noqa: BLE001
    out["error"] = f"{e}"
    out["traceback"] = traceback.format_exc()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
unreal.log("P84_WEAPON_ATTACH_DONE")
