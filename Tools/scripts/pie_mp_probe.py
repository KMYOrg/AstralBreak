import sys
# 멀티플레이 PIE 진단 — 한 프로세스에 리슨 서버 + 클라 N 을 띄우고, 머신(월드)마다 각 히어로의 애니 상태를 읽는다:
# 넷 역할 · 전투 스타일 태그 · 링크된 Rifle 공급자 레이어 유무 · 메인/공급자 인스턴스 bIsAiming.
# 모드는 소스 첫 줄 뒤 STEP 상수로 고른다: begin · sample · switch(서버에서 전 히어로 스타일 전환 GA) · fire(서버에서 사격 GA) · end
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import math
import unreal

STEP = "sample"
LABEL = ""
NUM_PLAYERS = 3   # 리슨 호스트 포함 플레이어 수
FACE_YAW = 175.0  # client_face_away: 카메라 Yaw = 몸 + 이 값
POSE_YAW = 0.0    # pose_turn: 호스트 폰 컨트롤러·액터 Yaw 에 더할 각 (제자리 회전 오프셋 −POSE_YAW 를 만든다)
POSE_PITCH = 0.0  # pose_turn: 호스트 컨트롤러 Pitch
GRIP = "current"  # grip_all(진단 전용): current · socket_only · bone — pie_aim_probe GRIP 과 같다
IA_SWITCH = "/Game/Input/Actions/IA_SwitchCombatStyle"
IA_FIRE = "/Game/Input/Actions/IA_Attack_Basic"

log = unreal.log
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
RIFLE_LAYERS = "/Game/Animation/Hero/ABP_HeroLayers_Rifle"
SWITCH_GA = "/Game/AbilitySystem/Abilities/GA_Hero_SwitchCombatStyle.GA_Hero_SwitchCombatStyle_C"
FIRE_GA = "/Game/AbilitySystem/Abilities/GA_Hero_BasicAttack_Projectile.GA_Hero_BasicAttack_Projectile_C"


def owned_tags(asc):
    if not asc:
        return "<no ASC>"
    return unreal.GameplayTagLibrary.get_debug_string_from_gameplay_tag_container(unreal.GameplayTagLibrary.get_owned_gameplay_tags(asc))


def pie_worlds():
    worlds = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
    if not worlds:
        raise RuntimeError("PIE_NO_WORLD")
    return sorted(worlds, key=lambda w: w.get_name())


def heroes(world):
    return sorted(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralCharacter_Hero), key=lambda a: a.get_name())


def server_world():
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            return w
    raise RuntimeError("PIE_NO_SERVER_WORLD")


def yaw_pitch(v):
    return math.degrees(math.atan2(v.y, v.x)), math.degrees(math.atan2(v.z, math.hypot(v.x, v.y)))


def weapon_mesh(a):
    # 손에 든 원거리 무기 메시 (총구 소켓 +X = 총열 방향 — pie_aim_probe 와 같은 정의)
    for w in a.get_attached_actors():
        if isinstance(w, unreal.AstralRangedWeaponActor):
            m = w.get_component_by_class(unreal.SkeletalMeshComponent)
            if m and m.does_socket_exist("Muzzle"):
                return w, m
    return None, None


def server_aim_point(world, a):
    # 서버가 이 폰의 발사에 쓰는 조준점 — ComputeAimTarget 재현(서버 컨트롤러의 카메라 POV: 원격 플레이어는 ServerUpdateCamera 보고값)
    weapon, wm = weapon_mesh(a)
    ctrl = a.get_controller()
    if not wm or not ctrl:
        return None
    muzzle = wm.get_socket_location("Muzzle")
    cam_loc, cam_rot = ctrl.get_player_view_point()
    d = cam_rot.get_forward_vector()
    start = cam_loc + d * max((muzzle - cam_loc).dot(d), 0.0)
    target = start + d * 10000.0
    hit = unreal.SystemLibrary.line_trace_single(world, start, target, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [a, weapon], unreal.DrawDebugTrace.NONE, True)
    if hit and hit.to_tuple()[0]:
        target = hit.to_tuple()[5]
    if (target - muzzle).normal().dot(d) <= 0.0:
        target = muzzle + d * 10000.0
    return target


def muzzle_vs(a, target):
    # (총열 ↔ 총구→target 3D 각, Yaw 오차, Pitch 오차, 총열 ↔ 이 월드의 BaseAimRotation 3D 각) — 오차 부호 = 총열 − 기준
    _, wm = weapon_mesh(a)
    if not wm or target is None:
        return None
    xf = wm.get_socket_transform("Muzzle", unreal.RelativeTransformSpace.RTS_WORLD)
    f = xf.rotation.get_axis_x()
    w = (target - xf.translation).normal()
    b = a.get_base_aim_rotation().get_forward_vector()
    fy, fp = yaw_pitch(f)
    wy, wp = yaw_pitch(w)
    ang = lambda u, v: math.degrees(math.acos(max(-1.0, min(1.0, u.dot(v)))))
    return ang(f, w), (fy - wy + 180.0) % 360.0 - 180.0, fp - wp, ang(f, b)


def play_settings():
    # LevelEditorPlaySettings 는 파이썬 래퍼가 없다 — CDO 를 경로로 찾아 C++ 프로퍼티 이름으로 접근한다.
    # PlayNetMode(EPlayNetMode)는 파이썬으로 변환되지 않아 읽기·쓰기 불가 — 사용자 설정이 리슨 서버(1)임을 전제한다(2026-10-20 확인)
    return unreal.find_object(None, "/Script/UnrealEd.Default__LevelEditorPlaySettings")


if STEP == "begin":
    settings = play_settings()
    # 이 에디터 세션 메모리에만 반영(설정 파일에 저장하지 않는다) — end 단계가 되돌린다
    unreal._mp_saved = (settings.get_editor_property("RunUnderOneProcess"), settings.get_editor_property("PlayNumberOfClients"))
    settings.set_editor_property("RunUnderOneProcess", True)
    settings.set_editor_property("PlayNumberOfClients", NUM_PLAYERS)
    perf = unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings") or unreal.load_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")
    if perf:
        perf.set_editor_property("bThrottleCPUWhenNotForeground", False)
    LES.editor_request_begin_play()
    log(f"PIE_MP_BEGIN_REQUESTED players={NUM_PLAYERS} saved={unreal._mp_saved}")

elif STEP == "end":
    LES.editor_request_end_play()
    saved = getattr(unreal, "_mp_saved", None)
    if saved:
        settings = play_settings()
        settings.set_editor_property("RunUnderOneProcess", saved[0])
        settings.set_editor_property("PlayNumberOfClients", saved[1])
    log(f"PIE_MP_END restored={saved}")

elif STEP in ("switch", "fire"):
    # 서버 월드의 호스트 폰(로컬 조종)만 발동 — 클라 화면에선 시뮬 프록시로 보인다.
    # ⚠️ 클라 월드에서 파이썬으로 GA 를 직접 발동하면 에디터가 크래시했다(2026-10-20, 로그는 Saved 권한으로 미확인) — 쓰지 않는다.
    # 서버가 원격 폰의 LocalPredicted GA 를 대신 발동(try_activate 원격 허용)해도 스타일이 바뀌지 않았다
    cls = unreal.load_class(None, SWITCH_GA if STEP == "switch" else FIRE_GA)
    for a in heroes(server_world()):
        if not a.is_locally_controlled():
            continue
        asc = a.get_astral_ability_system_component()
        ok = asc.try_activate_ability_by_class(cls, True) if asc else None
        log(f"PIE_MP_{STEP.upper()} host {a.get_name()} activated={ok} tags={owned_tags(asc)}")

elif STEP in ("client_switch", "client_fire"):
    # 클라 월드의 로컬 플레이어에 Enhanced Input 주입 — 실제 입력 경로(InputComponent → ASC 입력 태그 → ProcessAbilityInput).
    # 다음 입력 틱에 Started(누름), 그다음 틱에 주입이 없으니 Completed(뗌) = 클릭 1회
    # SubsystemBlueprintLibrary 는 파이썬에 없다 — 로컬 플레이어 입력 서브시스템을 객체 순회로 찾아 월드로 맞춘다 (PIE 월드당 로컬 플레이어 1)
    action = unreal.load_asset(IA_SWITCH if STEP == "client_switch" else IA_FIRE)
    subs = list(unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem))
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            continue
        sub = next((s for s in subs if s.get_world() == w), None)
        local = [a for a in heroes(w) if a.is_locally_controlled()]
        if not sub or not local:
            log(f"PIE_MP_INJECT {STEP} {w.get_name()} — subsystem={sub is not None} local_pawn={len(local)}")
            continue
        sub.inject_input_vector_for_action(action, unreal.Vector(1.0, 0.0, 0.0), [], [])
        log(f"PIE_MP_INJECT {STEP} {w.get_name()} {local[0].get_name()} tags={owned_tags(local[0].get_astral_ability_system_component())}")

elif STEP == "client_face_away":
    # 클라 월드의 로컬 폰 — 카메라(컨트롤러) Yaw 만 몸 + FACE_YAW 로. 비조준이면 몸은 이동 방향 추종이라 정지 중엔 안 돈다. 컨트롤 회전은 이동 패킷으로 서버에 간다
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            continue
        for a in heroes(w):
            if not a.is_locally_controlled():
                continue
            ay = a.get_actor_rotation().yaw
            a.get_controller().set_control_rotation(unreal.Rotator(0.0, 0.0, ay + FACE_YAW))
            log(f"PIE_MP_FACE_AWAY {w.get_name()} {a.get_name()} actor_yaw={ay:.1f} control_yaw={ay + FACE_YAW:.1f}")

elif STEP == "client_snap_body":
    # 경합 재현 — 클라 쪽 몸만 카메라 방향으로 미리 돌린다(회전은 이동 패킷으로 서버에 가지 않는다 → 서버 쪽 몸은 여전히 등짐).
    # = "클라가 서버보다 먼저 정렬된" 경우를 결정적으로 만든다: 클라는 즉시 발사·종료, 서버는 자기 정렬을 기다린다
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            continue
        for a in heroes(w):
            if not a.is_locally_controlled():
                continue
            r = a.get_actor_rotation()
            a.set_actor_rotation(unreal.Rotator(r.roll, r.pitch, a.get_control_rotation().yaw), False)
            log(f"PIE_MP_SNAP_BODY {w.get_name()} {a.get_name()} actor_yaw={a.get_actor_rotation().yaw:.1f}")

elif STEP == "shots_before":
    # 서버 월드 투사체 생성을 매 틱 기록 — 곧바로 맞아 사라지는 투사체도 잡는다(1초 뒤 스냅샷은 놓친다)
    world = server_world()
    clients = [w for w in pie_worlds() if not unreal.SystemLibrary.is_server(w)]
    seen = set(p.get_name() for p in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralProjectile))
    shots, clock = [], [0.0]
    alive = {}      # 서버 투사체 이름 → [shot 인덱스, 마지막 위치]
    deaths = []     # (t, 이름, 수명, 마지막 위치)
    client_seen = {w.get_name() + str(i): set() for i, w in enumerate(clients)}
    client_events = []   # (t, 클라 월드, 투사체 이름) — 복제로 나타난 시각
    timeline = {}        # "머신:폰" → {aim: 조준 태그 첫 시각, aligned: 그 뒤 몸 정렬 첫 시각}
    unreal._mp_timeline = timeline

    def on_tick(dt):
        clock[0] += dt
        current = {p.get_name(): p for p in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralProjectile)}
        for name, p in current.items():
            if name in seen:
                if name in alive:
                    alive[name][1] = p.get_actor_location()
                continue
            seen.add(name)
            v = p.get_velocity()
            inst = p.get_instigator()
            loc = p.get_actor_location()
            # 생성 위치를 발사자 기준(전방·우측 cm)으로 — 총구가 몸 앞이면 전방 +, 옆·뒤면 작거나 음수
            if inst:
                rel = loc - inst.get_actor_location()
                fwd, right = inst.get_actor_forward_vector(), inst.get_actor_right_vector()
                local = (rel.x * fwd.x + rel.y * fwd.y, rel.x * right.x + rel.y * right.y)
            else:
                local = (float("nan"), float("nan"))
            shots.append((clock[0], name, inst.get_name() if inst else "-", math.degrees(math.atan2(v.y, v.x)),
                          inst.get_actor_rotation().yaw if inst else float("nan"), inst.get_control_rotation().yaw if inst else float("nan"), local))
            alive[name] = [len(shots) - 1, loc]
        for name in [n for n in alive if n not in current]:
            idx, last = alive.pop(name)
            deaths.append((clock[0], name, clock[0] - shots[idx][0], last))
        for i, cw in enumerate(clients):
            key = cw.get_name() + str(i)
            for p in unreal.GameplayStatics.get_all_actors_of_class(cw, unreal.AstralProjectile):
                if p.get_name() not in client_seen[key]:
                    client_seen[key].add(p.get_name())
                    client_events.append((clock[0], f"client{i}", p.get_name()))
        # 정렬 타임라인 — 서버의 원격 폰과 각 클라의 로컬 폰: 조준 태그 도착·몸 정렬(10도) 첫 시각
        for label, w, want_local in [("server", world, False)] + [(f"client{i}", cw, True) for i, cw in enumerate(clients)]:
            for a in heroes(w):
                if a.is_locally_controlled() != want_local:
                    continue
                key = f"{label}:{a.get_name()}"
                ev = timeline.setdefault(key, {})
                if "aim" not in ev and "State.Ranged.Aiming" in owned_tags(a.get_astral_ability_system_component()):
                    ev["aim"] = clock[0]
                gap = abs((a.get_control_rotation().yaw - a.get_actor_rotation().yaw + 180.0) % 360.0 - 180.0)
                if "aim" in ev and "aligned" not in ev and gap <= 10.0:
                    ev["aligned"] = clock[0]

    unreal._mp_shots = shots
    unreal._mp_deaths = deaths
    unreal._mp_client_events = client_events
    unreal._mp_shot_handle = unreal.register_slate_pre_tick_callback(on_tick)
    log(f"PIE_MP_SHOTS_BEFORE existing={len(seen)}")

elif STEP == "shots_after":
    # 서버 월드에 새로 생긴 투사체(판정은 서버만 만든다) — 클릭 1회에 클라당 1발이어야 한다. 발사자 몸·카메라 Yaw 와 투사체 방향 비교
    unreal.unregister_slate_pre_tick_callback(unreal._mp_shot_handle)
    world = server_world()
    shots = unreal._mp_shots
    log(f"PIE_MP_SHOTS_AFTER new={len(shots)}")
    for t, name, inst, pyaw, body, ctrl, local in shots:
        log(f"PIE_MP_SHOT t={t:.3f} {name} instigator={inst} proj_yaw={pyaw:.1f} body_yaw_at_spawn={body:.1f} control_yaw={ctrl:.1f} "
            f"spawn_fwd={local[0]:.0f} spawn_right={local[1]:.0f}")
    for t, name, life, last in unreal._mp_deaths:
        log(f"PIE_MP_SHOT_DIED t={t:.3f} {name} lifetime={life:.3f}s last=({last.x:.0f},{last.y:.0f},{last.z:.0f})")
    for t, cw, name in unreal._mp_client_events:
        log(f"PIE_MP_SHOT_ON_CLIENT t={t:.3f} {cw} {name}")
    for key, ev in sorted(unreal._mp_timeline.items()):
        log(f"PIE_MP_TIMELINE {key} aim_tag={ev.get('aim', float('nan')):.3f} aligned={ev.get('aligned', float('nan')):.3f}")
    for a in heroes(world):
        log(f"PIE_MP_SERVER_BODY {a.get_name()} local={int(a.is_locally_controlled())} actor_yaw={a.get_actor_rotation().yaw:.1f} "
            f"control_yaw={a.get_control_rotation().yaw:.1f} tags={owned_tags(a.get_astral_ability_system_component())}")

elif STEP == "pose_turn":
    # 서버 월드 호스트 폰 — 컨트롤러 Pitch 와 Yaw(+POSE_YAW), 액터 Yaw 도 같이(조준 중 누적 → RootYawOffset ≈ −POSE_YAW). 클라 화면엔 이동·RemoteViewPitch 복제로 간다
    for a in heroes(server_world()):
        if not a.is_locally_controlled():
            continue
        ctrl = a.get_controller()
        r = ctrl.get_control_rotation()
        ctrl.set_control_rotation(unreal.Rotator(0.0, POSE_PITCH, r.yaw + POSE_YAW))
        ar = a.get_actor_rotation()
        a.set_actor_rotation(unreal.Rotator(ar.roll, ar.pitch, ar.yaw + POSE_YAW), False)
        # 같은 단계에서 사격 — 멀티 PIE 는 단계 하나가 ~0.7초라 따로 부르면 AimHold 2초가 풀린다(풀렸다 다시 조준하면 진입 피벗이 오프셋을 지운다)
        ok = a.get_astral_ability_system_component().try_activate_ability_by_class(unreal.load_class(None, FIRE_GA), True)
        log(f"PIE_MP_POSE_TURN host {a.get_name()} yaw+={POSE_YAW} pitch={POSE_PITCH} fire={ok}")

elif STEP == "client_pose_turn":
    # 클라 월드의 로컬 폰 — 컨트롤러 Pitch(POSE_PITCH)·Yaw(몸 + POSE_YAW) 를 주고 같은 단계에서 사격 입력 주입(조준 유지).
    # 다른 클라 화면엔 시뮬 프록시로, 서버엔 원격 플레이어(카메라 = ServerUpdateCamera 보고값)로 보인다 — 관찰자 조준점 복제 경로 검증
    action = unreal.load_asset(IA_FIRE)
    subs = list(unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem))
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            continue
        sub = next((s for s in subs if s.get_world() == w), None)
        for a in heroes(w):
            if not a.is_locally_controlled():
                continue
            ay = a.get_actor_rotation().yaw
            a.get_controller().set_control_rotation(unreal.Rotator(0.0, POSE_PITCH, ay + POSE_YAW))
            if sub:
                sub.inject_input_vector_for_action(action, unreal.Vector(1.0, 0.0, 0.0), [], [])
            log(f"PIE_MP_CLIENT_POSE {w.get_name()} {a.get_name()} pitch={POSE_PITCH} yaw+={POSE_YAW} fire={'Y' if sub else '-'}")

elif STEP == "grip_all":
    # 진단 전용 — 모든 PIE 월드의 손에 든 원거리 무기 메시 배치만 바꾼다(애셋 무변경, 재부착 시 원래대로). pie_aim_probe 의 grip 과 같은 정의
    for w in pie_worlds():
        for a in heroes(w):
            weapon, wm = weapon_mesh(a)
            if not wm:
                continue
            root = weapon.get_editor_property("root_component")
            sock_rel = root.get_attach_parent().get_socket_transform(root.get_attach_socket_name(), unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
            if GRIP == "socket_only":
                wm.set_relative_transform(unreal.Transform(), False, False)
            elif GRIP == "bone":
                wm.set_relative_transform(sock_rel.inverse(), False, False)
            log(f"PIE_MP_GRIP {w.get_name()} {a.get_name()} mode={GRIP}")

elif STEP == "pose_sample":
    # 머신(월드)마다 각 히어로의 조준 자세 — 오프셋 · AimYaw/Pitch · 두 손 거리 · 손 선 Pitch(총 Pitch 근사). 같은 폰은 모든 월드에서 같아야 한다
    # 총구 축: muzzle = 그 월드 총열 ↔ (그 월드 총구 → 서버 조준점) 각(Yaw·Pitch 오차) · vsBase = 총열 ↔ 그 월드 BaseAimRotation (시뮬 프록시는 RemoteViewPitch)
    # 같은 폰이라도 월드마다 액터 이름이 다르다 — 서버 폰과는 위치로 짝짓는다(같은 맵·같은 좌표)
    sw = server_world()
    server_targets = [(a.get_actor_location(), server_aim_point(sw, a)) for a in heroes(sw)]

    def server_target_for(pawn):
        loc = pawn.get_actor_location()
        return min(server_targets, key=lambda st: (st[0] - loc).length())[1] if server_targets else None

    for w in pie_worlds():
        machine = "SERVER" if unreal.SystemLibrary.is_server(w) else "CLIENT"
        for a in heroes(w):
            mesh = a.get_editor_property("mesh")
            main = mesh.get_anim_instance()
            if not main:
                continue
            d = mesh.get_socket_location("hand_l") - mesh.get_socket_location("hand_r")
            log(f"PIE_MP_POSE[{LABEL}] {w.get_name()}({machine}) {a.get_name()} role={str(a.get_local_role()).split('.')[-1]} aim={int(main.get_editor_property('bIsAiming'))} "
                f"off={main.get_editor_property('RootYawOffset'):.1f} aimYaw={main.get_editor_property('AimYaw'):.1f} aimPitch={main.get_editor_property('AimPitch'):.1f} "
                f"hands={d.length():.1f} gunPitch={math.degrees(math.atan2(d.z, math.hypot(d.x, d.y))):.1f} "
                f"acc={int(main.get_editor_property('bTurnInPlaceAccumulating'))} speed={main.get_editor_property('Speed'):.0f} input={int(main.get_editor_property('bHasMovementInput'))} "
                f"actor_yaw={a.get_actor_rotation().yaw:.1f} ctrl_yaw={a.get_control_rotation().yaw:.1f}")
            mv = muzzle_vs(a, server_target_for(a)) if main.get_editor_property("bIsAiming") else None
            if mv:
                log(f"PIE_MP_MUZZLE[{LABEL}] {w.get_name()}({machine}) {a.get_name()} role={str(a.get_local_role()).split('.')[-1]} "
                    f"muzzle={mv[0]:.2f} (y{mv[1]:.2f} p{mv[2]:.2f}) vsBase={mv[3]:.2f} baseAim={a.get_base_aim_rotation().pitch:.1f}/{a.get_base_aim_rotation().yaw:.1f}")

elif STEP == "sample":
    rifle_cls = unreal.load_asset(RIFLE_LAYERS).generated_class()
    for w in pie_worlds():
        machine = "SERVER" if unreal.SystemLibrary.is_server(w) else "CLIENT"
        for a in heroes(w):
            mesh = a.get_editor_property("mesh")
            main = mesh.get_anim_instance()
            linked = mesh.get_linked_anim_layer_instance_by_class(rifle_cls)
            asc = a.get_astral_ability_system_component()
            log(f"PIE_MP[{LABEL}] {w.get_name()}({machine}) {a.get_name()} role={str(a.get_local_role()).split('.')[-1]} "
                f"style={[t for t in owned_tags(asc).split(', ') if 'CombatStyle' in t or 'Aiming' in t]} "
                f"rifle_layer={'Y' if linked else '-'} main_aim={int(main.get_editor_property('bIsAiming')) if main else '?'} "
                f"layer_aim={int(linked.get_editor_property('bIsAiming')) if linked else '-'} "
                f"ctrl_desired={int(a.get_editor_property('character_movement').get_editor_property('use_controller_desired_rotation'))}")
