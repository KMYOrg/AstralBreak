"""M3 단위 D — 수호병 회피(RVO) + RaidMap 스포너 1개 (설계 Docs/Design/m3-enemy-ai.md §11 ④ · ⑤) — 에디터 안에서 돈다.

    UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=<이 파일> -unattended -stdout -FullStdOutLogOutput

먼저 있어야 하는 것: C++ 빌드(AAstralEnemySpawner), /Game/Characters/Enemy/BP_Enemy_Guardian (enemy_guardian_assets.py · enemy_guardian_c2_assets.py)

이 스크립트가 하는 것 (다시 돌려도 스포너는 하나다 — 이 스크립트의 꼬리표가 붙은 스포너를 지우고 다시 놓는다. 값을 고쳐 다시 돌리면 된다):
    BP_Enemy_Guardian      CharacterMovement 의 bUseRVOAvoidance 만 켠다 (반경 · 가중치는 엔진 기본값 그대로)
    /Game/Maps/RaidMap     AAstralEnemySpawner 1개 — 적 클래스 · 스폰 지점 3 · 발동 상자. 맵의 다른 액터는 건드리지 않는다

배치는 astral-ue-level 스킬의 헬퍼(Tools/lib/ab_level.py 의 spawn_class)로 한다. RaidMap 은 레이아웃 JSON 이 없는 맵이라 build() 는 쓰지 않는다
(build 의 rebuild 는 AB_Generated 액터를 전부 지운다 — 기둥 · PlayerStart 가 그 꼬리표를 달고 있다).

값은 전부 잠정이다(§0-4). 결과는 Tools/mcp/results/enemy_spawner_raidmap.json 에 쓴다(Saved 는 읽을 수 없다).
"""
import json
import math
import sys
import traceback

import unreal

sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import importlib

import ab_blueprint as B
import ab_level as L

importlib.reload(B)
importlib.reload(L)

RESULT_PATH = r"D:/UE5Projects/AstralBreak/Tools/mcp/results/enemy_spawner_raidmap.json"

ENEMY_PATH = "/Game/Characters/Enemy/BP_Enemy_Guardian"
MAP_PATH = "/Game/Maps/RaidMap"
SPAWNER_CLASS = "/Script/AstralBreak.AstralEnemySpawner"
SPAWNER_TAG = "AB_EnemySpawner"          # 이 스크립트가 놓은 스포너 — 다시 돌릴 때 이것만 지운다
SPAWNER_LABEL = "EnemySpawner_Guardian_01"

# ─── 잠정값 ───
# RaidMap (읽은 값): 바닥 8000 × 8000 (원점 중심, z = 0), 기둥 12개가 반경 1600 의 고리, PlayerStart 1개 (460, 0, 120) 가 −X 를 본다,
# NavMeshBounds ±3500. 스포너는 시작 지점의 정면(−X) 쪽, 기둥 고리 바깥에 둔다 — 도착만 해서는 상자에 닿지 않는다.
SPAWNER_LOCATION = (-2600.0, 0.0, 150.0)   # 상자 중심 (상자가 루트). z 150 = 상자 반높이 → 바닥부터 300
SPAWNER_YAW = 0.0                          # 적이 보는 방향 — +X (플레이어가 오는 쪽)
BOX_EXTENT = (500.0, 700.0, 150.0)         # 발동 상자 반크기 — x −3100 ~ −2100, y ±700
# 스폰 지점 — 스포너 기준 상대 위치. 상자의 안쪽 끝(플레이어가 들어오는 +X 변에서 700 ~ 850 cm)에 삼각형으로, 서로 300 · 300 · 520 cm
SPAWN_POINTS = [(-350.0, 0.0, -150.0), (-200.0, -260.0, -150.0), (-200.0, 260.0, -150.0)]
USE_RVO_AVOIDANCE = True

eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
result = {"ok": False, "steps": {}, "errors": []}


def v3(v):
    return [round(v.x, 1), round(v.y, 1), round(v.z, 1)]


def step_guardian_rvo():
    bp = unreal.load_asset(ENEMY_PATH)
    if not bp:
        raise RuntimeError(f"BP 없음: {ENEMY_PATH}")
    movement = unreal.get_default_object(bp.generated_class()).get_editor_property("character_movement")
    info = {"path": ENEMY_PATH, "before": bool(movement.get_editor_property("use_rvo_avoidance"))}
    movement.set_editor_property("use_rvo_avoidance", USE_RVO_AVOIDANCE)
    info["saved"] = B.compile_and_save(bp)

    saved = unreal.get_default_object(bp.generated_class()).get_editor_property("character_movement")
    info["use_rvo_avoidance"] = bool(saved.get_editor_property("use_rvo_avoidance"))
    info["avoidance_consideration_radius"] = saved.get_editor_property("avoidance_consideration_radius")
    info["avoidance_weight"] = saved.get_editor_property("avoidance_weight")
    info["max_walk_speed"] = saved.get_editor_property("max_walk_speed")
    if info["use_rvo_avoidance"] != USE_RVO_AVOIDANCE:
        raise RuntimeError("bUseRVOAvoidance 가 저장되지 않았다")
    return info


def spawners_in_level():
    class_name = SPAWNER_CLASS.rsplit(".", 1)[1]
    return [a for a in eas.get_all_level_actors() if a and a.get_class().get_name() == class_name]


def describe_spawner(actor, world):
    box = actor.get_editor_property("trigger_box")
    location = actor.get_actor_location()
    extent = box.get_editor_property("box_extent")
    transform = actor.get_actor_transform()
    info = {
        "label": actor.get_actor_label(),
        "location": v3(location),
        "yaw": round(actor.get_actor_rotation().yaw, 1),
        "tags": [str(t) for t in actor.get_editor_property("tags")],
        "enemy_class": str(actor.get_editor_property("enemy_class").get_path_name()) if actor.get_editor_property("enemy_class") else None,
        "activate_on_begin_play": bool(actor.get_editor_property("activate_on_begin_play")),
        "box_extent": v3(extent),
        "box_world_min": [round(location.x - extent.x, 1), round(location.y - extent.y, 1), round(location.z - extent.z, 1)],
        "box_world_max": [round(location.x + extent.x, 1), round(location.y + extent.y, 1), round(location.z + extent.z, 1)],
        "spawn_points_relative": [v3(p) for p in actor.get_editor_property("spawn_points")],
        "spawn_points_world": [],
        "player_starts": [],
    }

    # 스폰 지점 — 월드 좌표와 에디터 월드의 NavMesh 투영(런타임에도 스포너가 같은 투영을 한다)
    for point in actor.get_editor_property("spawn_points"):
        world_point = unreal.MathLibrary.transform_location(transform, point)
        entry = {"world": v3(world_point)}
        try:
            projected = unreal.NavigationSystemV1.project_point_to_navigation(world, world_point, None, None, unreal.Vector(100.0, 100.0, 300.0))
            entry["nav"] = v3(projected) if projected else None
        except Exception as error:  # noqa: BLE001
            entry["nav_error"] = str(error)
        info["spawn_points_world"].append(entry)
    points = [e["world"] for e in info["spawn_points_world"]]
    info["spawn_point_spacing"] = [round(math.dist(points[i], points[j]), 1) for i in range(len(points)) for j in range(i + 1, len(points))]

    # 상자와 PlayerStart 사이 거리 (상자 표면까지, cm) — 파티 흐름 시험이 도착만 해서는 닿지 않아야 한다
    for other in eas.get_all_level_actors():
        if other and other.get_class().get_name() == "PlayerStart":
            p = other.get_actor_location()
            dx = max(abs(p.x - location.x) - extent.x, 0.0)
            dy = max(abs(p.y - location.y) - extent.y, 0.0)
            dz = max(abs(p.z - location.z) - extent.z, 0.0)
            info["player_starts"].append({"label": other.get_actor_label(), "location": v3(p), "distance_to_box": round(math.sqrt(dx * dx + dy * dy + dz * dz), 1)})
    info["nearest_player_start_distance"] = min((s["distance_to_box"] for s in info["player_starts"]), default=None)
    return info


def step_raid_map():
    enemy_class = unreal.load_class(None, f"{ENEMY_PATH}.{ENEMY_PATH.rsplit('/', 1)[1]}_C")
    if not enemy_class or not unreal.load_class(None, SPAWNER_CLASS):
        raise RuntimeError("BP_Enemy_Guardian 클래스 또는 AstralEnemySpawner 클래스 없음 — 빌드 확인")
    if not les.load_level(MAP_PATH):
        raise RuntimeError(f"맵 로드 실패: {MAP_PATH}")

    info = {"map": MAP_PATH, "actors_before": len(eas.get_all_level_actors())}

    # 다시 돌려도 하나 — 이 스크립트의 꼬리표가 붙은 스포너만 지운다. 손으로 놓은 스포너가 있으면 그대로 두고 알린다
    removed = 0
    for actor in spawners_in_level():
        if unreal.Name(SPAWNER_TAG) in list(actor.get_editor_property("tags")):
            eas.destroy_actor(actor)
            removed += 1
    info["removed_previous"] = removed
    info["other_spawners"] = [a.get_actor_label() for a in spawners_in_level()]

    spawner = L.spawn_class(SPAWNER_CLASS, SPAWNER_LOCATION, (0.0, SPAWNER_YAW, 0.0), label=SPAWNER_LABEL, props={
        "enemy_class": enemy_class,
        "spawn_points": [unreal.Vector(*p) for p in SPAWN_POINTS],
        "activate_on_begin_play": False,
    })
    tags = list(spawner.get_editor_property("tags"))
    tags.append(unreal.Name(SPAWNER_TAG))
    spawner.set_editor_property("tags", tags)
    spawner.get_editor_property("trigger_box").set_editor_property("box_extent", unreal.Vector(*BOX_EXTENT))

    info["saved"] = les.save_current_level()
    if not info["saved"]:
        raise RuntimeError("RaidMap 저장 실패")

    # 디스크에서 다시 읽어 확인한다 (ab_level.build 와 같은 순서)
    les.load_level(MAP_PATH)
    world = ues.get_editor_world()
    spawners = spawners_in_level()
    info["actors_after"] = len(eas.get_all_level_actors())
    info["spawner_count"] = len(spawners)
    if len(spawners) != 1 + len(info["other_spawners"]):
        raise RuntimeError(f"스포너 수가 맞지 않는다: {len(spawners)}")
    info["spawner"] = describe_spawner(next(a for a in spawners if unreal.Name(SPAWNER_TAG) in list(a.get_editor_property("tags"))), world)
    if any(e.get("nav") is None for e in info["spawner"]["spawn_points_world"]):
        result["errors"].append("NavMesh 에 내려지지 않는 스폰 지점이 있다 — SPAWN_POINTS 를 고친다")
    return info


def main():
    for name, fn in (("guardian_rvo", step_guardian_rvo), ("raid_map", step_raid_map)):
        try:
            result["steps"][name] = fn()
        except Exception as error:  # noqa: BLE001
            result["errors"].append(f"{name}: {error}")
            result["steps"][name] = {"error": str(error), "trace": traceback.format_exc()}
            break
    result["ok"] = not result["errors"]
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    unreal.log(f"ENEMY_SPAWNER_RAIDMAP {'OK' if result['ok'] else 'FAIL'} -> {RESULT_PATH}")


main()
