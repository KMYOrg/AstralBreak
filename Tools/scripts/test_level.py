import unreal, math

log, err = unreal.log, unreal.log_error
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

MAP = "/Game/AstralBreak/_ScriptTest/L_ScriptTest"

def step(label, fn):
    try:
        r = fn()
        log(f"[OK]   {label}" + (f" -> {r}" if r is not None else ""))
        return r
    except Exception as e:
        err(f"[FAIL] {label}: {type(e).__name__}: {e}")
        return None

step("새 레벨", lambda: les.new_level(MAP))

# 바닥 (엔진 기본 큐브)
cube = unreal.load_asset("/Engine/BasicShapes/Cube")
if cube:
    floor = step("바닥 배치",
                 lambda: eas.spawn_actor_from_object(cube, unreal.Vector(0, 0, 0)))
    if floor:
        floor.set_actor_scale3d(unreal.Vector(60, 60, 1))
        floor.set_actor_label("SM_Arena_Floor")

    # 기둥 8개 방사
    for i in range(8):
        a = math.radians(i * 45)
        p = step(f"기둥 {i}", lambda: eas.spawn_actor_from_object(
            cube, unreal.Vector(1200 * math.cos(a), 1200 * math.sin(a), 300)))
        if p:
            p.set_actor_scale3d(unreal.Vector(1, 1, 6))
            p.set_actor_label(f"SM_Pillar_{i:02d}")

# PlayerStart 4개
for i in range(4):
    a = math.radians(i * 90)
    s = step(f"PlayerStart {i}", lambda: eas.spawn_actor_from_class(
        unreal.PlayerStart,
        unreal.Vector(400 * math.cos(a), 400 * math.sin(a), 120),
        unreal.Rotator(0, 0, 0)))
    if s:
        s.set_actor_label(f"PlayerStart_{i}")

step("DirectionalLight", lambda: eas.spawn_actor_from_class(
    unreal.DirectionalLight, unreal.Vector(0, 0, 2000), unreal.Rotator(-45, 0, 0)))
step("SkyLight", lambda: eas.spawn_actor_from_class(
    unreal.SkyLight, unreal.Vector(0, 0, 2000)))
step("NavMeshBounds", lambda: eas.spawn_actor_from_class(
    unreal.NavMeshBoundsVolume, unreal.Vector(0, 0, 0)))

step("저장", lambda: les.save_current_level())

actors = eas.get_all_level_actors()
log(f"=== 배치된 액터 {len(actors)}개 ===")