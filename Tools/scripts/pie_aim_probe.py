import sys
# 진단 — PIE 에서 히어로를 찾아 조준 상태 파이프라인(태그 → AnimInstance bIsAiming → 회전 모드 → 레이어 링크)을 읽는다.
# 모드는 소스 첫 줄 뒤 STEP 상수로 고른다: begin(PIE 시작) · arm(라이플 스타일 태그 + AimHold GE 30초 적용) · sample(값 읽기) · end(PIE 종료)
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import math
import unreal

STEP = "sample"

log = unreal.log
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
RIFLE_LAYERS = "/Game/Animation/Hero/ABP_HeroLayers_Rifle"
PROPS = ("bIsAiming", "AimYaw", "AimPitch", "Speed", "MovementDirection", "bHasMovementInput",
         "RootYawOffset", "bWantsTurnInPlace", "bTurnInPlaceRotationFinished", "TurnInPlaceKind", "TurnInPlaceAnimTime", "TurnYawCurveValue")
TURN_YAW = 90.0   # turn 단계에서 컨트롤러 Yaw 에 더하는 각 — 조준 중엔 몸이 따라 돌고 RootYawOffset 이 −TURN_YAW 로 누적돼야 한다
SPIN_STEP = 2.0   # spin 단계: 틱당 회전량(도)
AIM_YAW_OFF = 0.0   # aim 단계: 컨트롤러 Yaw − 액터 Yaw
AIM_PITCH = 0.0     # aim 단계: 컨트롤러 Pitch
MARK = ""           # mark 단계: 기록 콜백에 남길 구간 이름 (dump 의 PIE_POSE 가 구간별 평균을 낸다)
AUTO_FIRE = 0.0     # record 단계: > 0 이면 기록 콜백이 이 간격(초)마다 사격 GA 를 활성화 — 단계 지연과 무관하게 조준(AimHold 2초)을 유지
MOVE = (0.0, 0.0, 0.0)   # move 단계: (앞, 오른쪽, 초) — 기록 콜백이 카메라 Yaw 기준으로 그 방향 이동 입력을 넣는다 (조준 strafe)
TIMELINE = True          # dump 의 PIE_S 타임라인 출력 — 총구 프로브는 끈다(원격 실행 응답 크기)
SEG_SKIP = 0.5           # PIE_MUZZLE_SEG: 표식 뒤 이 시간(초)부터 다음 표식까지 평균. 이름이 * 로 끝나면 0 (회전·이동 과도 구간 전체)
SEG_TIMELINE = ""        # PIE_MUZZLE_TL: 쉼표로 고른 구간 이름의 총구 지표 타임라인(0.05초 간격)
# 총구 축 지표 — 소켓 +X 가 총열 방향(SKM_RifleScifi_01: WeaponRoot 기준 (−63.5, 0, 7.5) · Yaw 180, 총열이 WeaponRoot −X 로 뻗음)
WEAPON_MUZZLE = "Muzzle"
GRIP = "current"    # grip 단계(진단 전용): 무기 메시 배치를 PIE 월드에서만 바꾼다 — current · socket_only · bone
AIM_TRACE_RANGE = 10000.0   # = UAstralGA_Hero_BasicAttack_Ranged::AimTraceRange
# 자세 지표용 본 — 가슴 기울기 = spine_01 → neck_01, 목 기울기 = neck_01 → head (카메라 Yaw 프레임에서 앞/옆 기울기, 도)
POSE_BONES = ("pelvis", "spine_01", "neck_01", "head")
CONSOLE_CMD = ""    # console 단계(진단 전용): PIE 월드에서 실행할 콘솔 명령 — 드라이버가 환경변수 PROBE_CONSOLE 로 넣는다


SWITCH_GA = "/Game/AbilitySystem/Abilities/GA_Hero_SwitchCombatStyle.GA_Hero_SwitchCombatStyle_C"
FIRE_GA = "/Game/AbilitySystem/Abilities/GA_Hero_BasicAttack_Projectile.GA_Hero_BasicAttack_Projectile_C"


def owned_tags(asc):
    # Python 에선 FGameplayTag 를 이름으로 만들 수 없다(TagName 읽기 전용) — ASC(IGameplayTagAssetInterface) 의 보유 태그를 문자열로 읽는다
    return unreal.GameplayTagLibrary.get_debug_string_from_gameplay_tag_container(unreal.GameplayTagLibrary.get_owned_gameplay_tags(asc))


def heroes():
    # 서버(첫 PIE) 월드의 로컬 조종 히어로만 — Play 설정이 리슨 서버 다인원이면 원격 플레이어 폰도 같은 월드에 있어
    # 샘플이 두 폰 사이를 오가며 섞인다(2026-10-20: 발 속도 98만cm/s). 없으면(비정상) 전부
    world = UES.get_game_world()
    if not world:
        raise RuntimeError("PIE_NO_WORLD")
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralCharacter_Hero)
    local = [a for a in actors if a.is_locally_controlled()]
    return world, local or actors


def dump_anim(label, anim):
    if not anim:
        log(f"PIE_{label}: None")
        return
    vals = {p: anim.get_editor_property(p) for p in PROPS}
    log(f"PIE_{label}: {anim.get_class().get_name()} {vals}")


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def vec_angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, u.normal().dot(v.normal())))))


def yaw_pitch(v):
    return math.degrees(math.atan2(v.y, v.x)), math.degrees(math.atan2(v.z, math.hypot(v.x, v.y)))


def weapon_mesh(a):
    # 손에 든 원거리 무기 — 히어로에 붙은 AstralRangedWeaponActor 중 총구 소켓이 있는 메시 (홀스터의 낫은 근접 무기 클래스)
    for w in a.get_attached_actors():
        if isinstance(w, unreal.AstralRangedWeaponActor):
            m = w.get_component_by_class(unreal.SkeletalMeshComponent)
            if m and m.does_socket_exist(WEAPON_MUZZLE):
                return w, m
    return None, None


def aim_point(world, a, weapon, ctrl, muzzle):
    # ResolveShot 자유 조준 재현(ComputeAimTarget): 카메라 레이 위 총구 투영점부터 트레이스한 조준점. 실제 발사 방향 = 총구 → 이 점
    cam_loc, cam_rot = ctrl.get_player_view_point()
    d = cam_rot.get_forward_vector()
    start = cam_loc + d * max((muzzle - cam_loc).dot(d), 0.0)
    target = start + d * AIM_TRACE_RANGE
    hit_name = "-"
    hit = unreal.SystemLibrary.line_trace_single(world, start, target, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [a, weapon], unreal.DrawDebugTrace.NONE, True)
    if hit:
        h = hit.to_tuple()
        if h[0]:
            target = h[5]
            hit_name = h[9].get_class().get_name() if h[9] else "?"
    if (target - muzzle).normal().dot(d) <= 0.0:
        target = muzzle + d * AIM_TRACE_RANGE
    return target, d, hit_name


def muzzle_metric(world, a, weapon, wmesh, target=None, cam_dir=None):
    # 총구 축 지표 = (총열 ↔ 발사 방향 3D 각, Yaw 오차, Pitch 오차, 총열 ↔ 카메라 방향 3D 각, 조준점 거리, 트레이스가 맞은 액터 클래스, 총열 Yaw − 액터 Yaw).
    # 오차 부호 = 총열 − 발사 방향. target 을 주면(멀티: 서버가 쏘는 조준점) 그 점으로, 아니면 이 폰 컨트롤러의 카메라 레이로 구한다
    xf = wmesh.get_socket_transform(WEAPON_MUZZLE, unreal.RelativeTransformSpace.RTS_WORLD)
    m = xf.translation
    f = xf.rotation.get_axis_x()
    hit_name = "given"
    if target is None:
        target, cam_dir, hit_name = aim_point(world, a, weapon, a.get_controller(), m)
    w = target - m
    fy, fp = yaw_pitch(f)
    wy, wp = yaw_pitch(w)
    cy, cp = yaw_pitch(cam_dir) if cam_dir is not None else (float("nan"), float("nan"))
    # 7·8 총열 − 카메라 방향 Yaw/Pitch (시차 없는 자세 오차 — 조준점이 멀면 발사 방향과 같다)
    return (vec_angle(f, w), wrap180(fy - wy), fp - wp, vec_angle(f, cam_dir) if cam_dir is not None else float("nan"), w.length(), hit_name,
            wrap180(fy - a.get_actor_rotation().yaw), wrap180(fy - cy), fp - cp)


if STEP == "begin":
    # 백그라운드 에디터는 CPU 절약으로 8Hz 로 돈다 — 프로브 동안 끈다 (실측: 3초에 24틱). 에디터 설정이라 세션 안에서만 유효
    # EditorPerformanceSettings 는 파이썬 래퍼가 없다 — CDO 를 경로로 찾아 리플렉션으로 끈다 (실측 OK)
    perf = unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings") or unreal.load_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")
    if perf:
        perf.set_editor_property("bThrottleCPUWhenNotForeground", False)
    LES.editor_request_begin_play()
    log("PIE_BEGIN_REQUESTED")

elif STEP == "end":
    LES.editor_request_end_play()
    log("PIE_END_REQUESTED")

elif STEP == "turn":
    # 제자리 회전 유발 — 컨트롤러 Yaw 를 한 번에 TURN_YAW 만큼 돌린다 (조준 중 = 컨트롤러 Yaw 추종이라 액터가 따라 돈다)
    world, actors = heroes()
    for a in actors:
        ctrl = a.get_controller()
        r = ctrl.get_control_rotation()
        ctrl.set_control_rotation(unreal.Rotator(r.roll, r.pitch, r.yaw + TURN_YAW))
        # 파이썬 PIE 에선 PlayerTick 의 UpdateRotation 이 액터를 돌리지 않았다(실측: ctrl −90, actor −180 유지) — 실제 플레이는 마우스 입력이 돌린다.
        # 제자리 회전의 입력은 액터 Yaw 델타이므로 액터도 같이 돌린다 (같은 자극)
        ar = a.get_actor_rotation()
        a.set_actor_rotation(unreal.Rotator(ar.roll, ar.pitch, ar.yaw + TURN_YAW), False)
        log(f"PIE_TURN: {a.get_name()} control_yaw {r.yaw:.1f} -> {r.yaw + TURN_YAW:.1f} actor_yaw {ar.yaw:.1f} -> {a.get_actor_rotation().yaw:.1f}")

elif STEP == "aim":
    # AimOffset 단독 검사 — 액터는 두고 컨트롤러만 액터 Yaw + AIM_YAW_OFF / Pitch AIM_PITCH 로 (파이썬 PIE 에선 몸이 컨트롤러를 안 따라간다)
    world, actors = heroes()
    for a in actors:
        ctrl = a.get_controller()
        ay = a.get_actor_rotation().yaw
        ctrl.set_control_rotation(unreal.Rotator(0.0, float(AIM_PITCH), ay + float(AIM_YAW_OFF)))
        log(f"PIE_AIM: actor_yaw={ay:.1f} control=(yaw {ay + AIM_YAW_OFF:.1f}, pitch {AIM_PITCH})")

elif STEP == "spin":
    # 마우스식 점진 회전 — 기록 콜백이 틱마다 SPIN_STEP 만큼 컨트롤러·액터 Yaw 를 돌린다 (총 TURN_YAW, 음수면 왼쪽)
    unreal._turn_spin = [abs(float(TURN_YAW)), math.copysign(float(SPIN_STEP), float(TURN_YAW))]
    log(f"PIE_SPIN_START total={TURN_YAW} step={SPIN_STEP}")

elif STEP == "mark":
    unreal._turn_mark = MARK
    log(f"PIE_MARK_SET {MARK}")

elif STEP == "grip":
    # 진단 전용 — 이 PIE 월드의 손에 든 원거리 무기 메시 상대 트랜스폼만 바꾼다(애셋 무변경, 스타일 전환·재부착 시 원래 값으로 돌아간다).
    # GRIP: "current"(변경 없음) · "socket_only"(AttachOffset 항등 — 소켓만) · "bone"(소켓 상쇄 — 무기 루트 = 부착 본, 애니 키트 저작 기준)
    world, actors = heroes()
    for a in actors:
        weapon, wm = weapon_mesh(a)
        if not wm:
            log(f"PIE_GRIP {a.get_name()}: no ranged weapon")
            continue
        root = weapon.get_editor_property("root_component")
        sock = root.get_attach_socket_name()
        parent = root.get_attach_parent()
        sock_rel = parent.get_socket_transform(sock, unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
        if GRIP == "socket_only":
            wm.set_relative_transform(unreal.Transform(), False, False)
        elif GRIP == "bone":
            wm.set_relative_transform(sock_rel.inverse(), False, False)
        log(f"PIE_GRIP {a.get_name()} mode={GRIP} socket={sock} socket_rel_rot={sock_rel.rotation.rotator()} mesh_rel_rot={wm.get_relative_transform().rotation.rotator()}")

elif STEP == "console":
    # 진단 전용 — PIE 월드에서 콘솔 명령(세미콜론 구분). 튜닝 변형은 `set ABP_Hero_Combat_C TurnInPlaceSettings (...)` — PIE 중엔 PIE 객체에만 들어간다
    # (BP 인스턴스는 CDO 를 복사하지 않고 컴파일 때의 커스텀 목록만 받아 CDO 메모리 수정은 안 먹는다). 애셋 무변경
    world, actors = heroes()
    for cmd in [c.strip() for c in CONSOLE_CMD.split(";") if c.strip()]:
        unreal.SystemLibrary.execute_console_command(world, cmd)
        log(f"PIE_CONSOLE {cmd}")
    for a in actors:
        anim = a.get_editor_property("mesh").get_anim_instance()
        log(f"PIE_CONSOLE_CHECK {a.get_name()} TurnInPlaceSettings={anim.get_editor_property('TurnInPlaceSettings').export_text()}")

elif STEP == "move":
    # 조준 이동(strafe) — 기록 콜백이 MOVE[2] 초 동안 매 틱 카메라 Yaw 기준 (앞, 오른쪽) 이동 입력을 넣는다
    unreal._move = [float(MOVE[0]), float(MOVE[1]), float(MOVE[2])]
    log(f"PIE_MOVE_START {MOVE}")

elif STEP == "face_away":
    # 등진 사격 준비 — 컨트롤러 Yaw 만 액터 + TURN_YAW 로 (비조준이면 몸은 이동 방향 추종이라 정지 중엔 안 돈다). 기록 콜백에 표식을 남긴다
    world, actors = heroes()
    for a in actors:
        ctrl = a.get_controller()
        ay = a.get_actor_rotation().yaw
        ctrl.set_control_rotation(unreal.Rotator(0.0, 0.0, ay + TURN_YAW))
        log(f"PIE_FACE_AWAY: actor_yaw={ay:.1f} control_yaw={ay + TURN_YAW:.1f}")
    unreal._turn_mark = "face_away"

elif STEP == "fire":
    # 조준 유지 — AimHold GE 는 발사마다 2초. 드라이버가 기록 중 주기적으로 부른다 (arm 과 같은 게임 스레드 원격 실행 경로)
    world, actors = heroes()
    fire_cls = unreal.load_class(None, FIRE_GA)
    for a in actors:
        asc = a.get_astral_ability_system_component()
        log(f"PIE_FIRE: {asc.try_activate_ability_by_class(fire_cls, True)} tags={owned_tags(asc)}")

elif STEP == "record":
    # 매 에디터 틱마다 제자리 회전 값을 모은다 (dump 단계가 로그로 쏟는다). 호출 사이 상태는 unreal 모듈 속성에 남긴다
    world, actors = heroes()
    rifle_cls = unreal.load_asset(RIFLE_LAYERS).generated_class()
    samples = []
    clock = [0.0]
    ticks = [0]
    marks = []          # (t, 이름) — face_away 등 단계 시점
    shots = []          # (t, 투사체 속도 Yaw, 속도 벡터, 그 틱 총구 축 ↔ 투사체 3D 각) — 새로 나타난 투사체
    seen_projectiles = set(p.get_name() for p in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralProjectile))
    weapons = {}        # 히어로 이름 → (무기 액터, 메시) — 스타일 전환으로 바뀌면 다시 찾는다

    unreal._turn_spin = [0.0, 0.0]
    unreal._turn_mark = None
    unreal._move = [0.0, 0.0, 0.0]

    def flat_yaw(v):
        return math.degrees(math.atan2(v.y, v.x))

    def lean(v, yaw):
        # 수직 기준 앞/옆 기울기(도) — v 를 카메라 Yaw 프레임(앞 · 오른쪽 · 위)으로 돌려서. 위를 향한 본 사슬이면 (0, 0) 이 꼿꼿
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        f, r = v.x * c + v.y * s, -v.x * s + v.y * c
        return math.degrees(math.atan2(f, v.z)), math.degrees(math.atan2(r, v.z))

    fire_cls = unreal.load_class(None, FIRE_GA)
    last_fire = [0.0]

    m0 = actors[0].get_editor_property("mesh") if actors else None
    missing = [b for b in POSE_BONES if m0 and m0.get_bone_index(b) < 0]
    if missing:
        log(f"PIE_POSE_BONES_MISSING {missing}")

    def on_tick(dt):
        clock[0] += dt
        ticks[0] += 1
        if unreal._turn_mark:
            marks.append((clock[0], unreal._turn_mark))
            unreal._turn_mark = None
        if AUTO_FIRE > 0.0 and clock[0] - last_fire[0] >= AUTO_FIRE:
            last_fire[0] = clock[0]
            for a in actors:
                a.get_astral_ability_system_component().try_activate_ability_by_class(fire_cls, True)
        for a in actors:
            wpn = weapons.get(a.get_name())
            if not wpn or not wpn[1] or not wpn[1].does_socket_exist(WEAPON_MUZZLE):
                weapons[a.get_name()] = weapon_mesh(a)
        for p in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralProjectile):
            if p.get_name() not in seen_projectiles:
                seen_projectiles.add(p.get_name())
                v = p.get_velocity()
                wm = weapons.get(actors[0].get_name(), (None, None))[1] if actors else None
                barrel = wm.get_socket_transform(WEAPON_MUZZLE, unreal.RelativeTransformSpace.RTS_WORLD).rotation.get_axis_x() if wm else None
                shots.append((clock[0], flat_yaw(v), v, vec_angle(barrel, v) if barrel is not None and v.length() > 1.0 else float("nan")))
        mv = unreal._move
        if mv[2] > 0.0:
            mv[2] -= dt
            for a in actors:
                cy = math.radians(a.get_controller().get_control_rotation().yaw)
                a.add_movement_input(unreal.Vector(math.cos(cy) * mv[0] - math.sin(cy) * mv[1], math.sin(cy) * mv[0] + math.cos(cy) * mv[1], 0.0), 1.0, False)
        spin = unreal._turn_spin
        for a in actors:
            if spin[0] > 0.0:
                step = math.copysign(min(abs(spin[1]), spin[0]), spin[1])
                spin[0] -= abs(step)
                ctrl = a.get_controller()
                r = ctrl.get_control_rotation()
                ctrl.set_control_rotation(unreal.Rotator(r.roll, r.pitch, r.yaw + step))
                ar = a.get_actor_rotation()
                a.set_actor_rotation(unreal.Rotator(ar.roll, ar.pitch, ar.yaw + step), False)
            mesh = a.get_editor_property("mesh")
            anim = mesh.get_anim_instance()
            if not anim:
                continue
            linked = mesh.get_linked_anim_layer_instance_by_class(rifle_cls)
            # 상태 이름은 읽지 않는다 — call_method("GetCurrentStateName") 를 부른 실행은 세 번 모두 에디터가 크래시(2026-10-20, 로그는 권한상 미확인).
            # 값(kind/wants/fin/animT/curve)으로 상태를 판단한다
            st = linked.get_name() if linked else "-"   # 링크 인스턴스 이름 — 바뀌면 재링크, "-" 면 링크 해제 (기본 근접 구현이 보인다)
            samples.append((clock[0], a.get_actor_rotation().yaw, anim.get_editor_property("RootYawOffset"), str(anim.get_editor_property("TurnInPlaceKind")).split(".")[-1],
                            anim.get_editor_property("bWantsTurnInPlace"), anim.get_editor_property("bTurnInPlaceRotationFinished"), anim.get_editor_property("TurnInPlaceAnimTime"),
                            anim.get_editor_property("TurnYawCurveValue"), anim.get_editor_property("AimYaw"), st,
                            anim.get_editor_property("bIsAiming"), anim.is_any_montage_playing(), a.get_controller().get_control_rotation().yaw,
                            anim.get_editor_property("TurnInPlaceDebugWeight"), anim.get_editor_property("TurnInPlaceDebugRemaining"),
                            anim.get_editor_property("bTurnInPlaceAccumulating"),
                            (mesh.get_socket_location("hand_r") - mesh.get_socket_location("hand_l")).length(),   # 두 손 거리 — 총을 쥔 손이 벌어지면 팔 자세 붕괴
                            # 17 링크(공급자) 인스턴스의 AimYaw — AimOffset 이 실제로 읽는 값 (메인 AimYaw 와 같아야 한다)
                            linked.get_editor_property("AimYaw") if linked else float("nan"),
                            # 18·19 발 월드 위치 — 디딘 발이 미끄러지거나 순간 이동하면 속도 스파이크
                            mesh.get_socket_location("foot_l"), mesh.get_socket_location("foot_r"),
                            # 20 총 방향 근사 = 오른손(그립) → 왼손(총열) 의 수평 Yaw — 카메라 Yaw 와의 차가 일정하면 상체가 카메라를 따른다
                            flat_yaw(mesh.get_socket_location("hand_l") - mesh.get_socket_location("hand_r")),
                            # 21 AimPitch(메인) · 22 가슴 기울기(앞, 옆) · 23 목 기울기(앞, 옆) — 카메라 Yaw 프레임. 옆 기울기는 조준 자세에서 0 근처여야 한다
                            anim.get_editor_property("AimPitch"),
                            lean(mesh.get_socket_location("neck_01") - mesh.get_socket_location("spine_01"), a.get_controller().get_control_rotation().yaw),
                            lean(mesh.get_socket_location("head") - mesh.get_socket_location("neck_01"), a.get_controller().get_control_rotation().yaw),
                            # 24 총 Pitch 근사 = 오른손 → 왼손 선의 수직 각 (카메라 Pitch 를 따라야 한다)
                            (lambda v: math.degrees(math.atan2(v.z, math.hypot(v.x, v.y))))(mesh.get_socket_location("hand_l") - mesh.get_socket_location("hand_r")),
                            # 25 총구 축 지표(muzzle_metric — 3D 각 · Yaw · Pitch 오차 · 총열↔카메라 · 조준점 거리), 무기 없으면 None · 26 Speed
                            muzzle_metric(world, a, *weapons[a.get_name()]) if weapons.get(a.get_name(), (None, None))[1] else None,
                            anim.get_editor_property("Speed")))

    # 오프셋 클램프 — dump 의 PIE_CLAMP(클램프에 붙은 프레임) 기준값. 메인 인스턴스의 현재 설정(클래스 기본값)
    try:
        unreal._turn_clamp = actors[0].get_editor_property("mesh").get_anim_instance().get_editor_property("TurnInPlaceSettings").get_editor_property("root_yaw_offset_clamp")
    except Exception:
        unreal._turn_clamp = None
    unreal._turn_samples = samples
    unreal._turn_marks = marks
    unreal._turn_shots = shots
    unreal._turn_handle = unreal.register_slate_pre_tick_callback(on_tick)   # pre-tick: 지난 프레임 애님 작업 완료 뒤 → 한 프레임으로 정합
    log("PIE_RECORD_STARTED")

elif STEP == "dump":
    try:
        unreal.unregister_slate_pre_tick_callback(unreal._turn_handle)
    except Exception:
        pass   # 재덤프 — 이미 해제됨 (기록은 unreal 모듈 속성에 남아 있다)
    samples = unreal._turn_samples
    log(f"PIE_DUMP: {len(samples)} samples")
    # 액터가 돌지 않은 프레임 사이의 오프셋 점프 최대치 — 커브·재진입 버그의 지표 (한 프레임에 90·180 뛰면 "휙")
    worst = (0.0, 0.0)
    for prev, cur in zip(samples, samples[1:]):
        dyaw = abs(((cur[1] - prev[1]) + 180.0) % 360.0 - 180.0)
        if dyaw < 1.0:
            doff = abs(cur[2] - prev[2])
            if doff > worst[0]:
                worst = (doff, cur[0])
    log(f"PIE_JUMP max_offset_step_without_actor_turn={worst[0]:.1f} at t={worst[1]:.2f}")
    hd_max = max(samples, key=lambda x: x[16])
    log(f"PIE_HANDS max_dist={hd_max[16]:.0f} at t={hd_max[0]:.2f} (Rifle_Idle 26 · AO 19~33 · 턴 클립 29)")
    # 링크 인스턴스 변화 — 재링크/해제 시점
    last = None
    for smp in samples:
        if smp[9] != last:
            log(f"PIE_LINK t={smp[0]:.2f} linked={smp[9]}")
            last = smp[9]
    def wrap(a):
        return (a + 180.0) % 360.0 - 180.0

    # 링크 인스턴스 AimYaw — AimOffset 이 읽는 값이 메인과 같은가 (예전 버그: 링크는 RootYawOffset 을 안 빼 ≈ 0)
    linked_diff = [abs(wrap(s[8] - s[17])) for s in samples if s[10] and not math.isnan(s[17])]
    log(f"PIE_AIMYAW_LINKED max|main-linked|={max(linked_diff) if linked_diff else float('nan'):.2f} over {len(linked_diff)} aiming samples")
    # 총 방향 − 카메라 Yaw — 조준 중 이 차의 폭이 작으면 상체가 카메라를 따른다 (예전: 오프셋만큼 벌어짐)
    gun = [wrap(s[20] - s[12]) for s in samples if s[10]]
    if gun:
        log(f"PIE_GUN gun_minus_camera min={min(gun):.1f} max={max(gun):.1f} range={max(gun) - min(gun):.1f} (aiming samples {len(gun)})")
    # 발 속도 — 샘플 간 이동 / dt. 정지 회전 중 디딘 발은 ~0, 스텝은 완만한 봉우리, 클립 재시작 스냅은 뾰족한 스파이크
    feet = []
    for prev, cur in zip(samples, samples[1:]):
        dt = max(cur[0] - prev[0], 1e-4)
        vl = (cur[18] - prev[18]).length() / dt
        vr = (cur[19] - prev[19]).length() / dt
        feet.append((cur[0], vl, vr, cur))
    if feet:
        top = sorted(feet, key=lambda x: max(x[1], x[2]), reverse=True)[:5]
        for t, vl, vr, smp in top:
            log(f"PIE_FEET t={t:.2f} foot_l={vl:.0f}cm/s foot_r={vr:.0f}cm/s kind={smp[3]} wants={int(smp[4])} fin={int(smp[5])} animT={smp[6]:.2f} off={smp[2]:.1f}")
        # 순간 이동(> 500cm/s) 전후 3샘플 — 발 위치(액터 기준)·오프셋·커브로 원인을 본다
        idx = {id(f[3]): i for i, f in enumerate(feet)}
        shown = set()
        for t, vl, vr, smp in sorted(feet, key=lambda x: max(x[1], x[2]), reverse=True)[:3]:
            if max(vl, vr) < 500.0 or t in shown:
                continue
            i0 = idx[id(smp)]
            for j in range(max(i0 - 3, 0), min(i0 + 4, len(feet))):
                tj, vlj, vrj, sj = feet[j]
                shown.add(tj)
                log(f"PIE_SPIKE{'>' if j == i0 else ' '} t={tj:.3f} l={vlj:.0f} r={vrj:.0f} yaw={sj[1]:.1f} off={sj[2]:.1f} kind={sj[3]} wants={int(sj[4])} fin={int(sj[5])} "
                    f"animT={sj[6]:.3f} w={sj[13]:.2f} rem={sj[14]:.1f} curve={sj[7]:.1f} foot_r=({sj[19].x:.0f},{sj[19].y:.0f},{sj[19].z:.0f})")
        # 두 발 동시 이동 — 자연스러운 스텝은 한 발이 디뎌 있다(min ≈ 0). 둘 다 빠르면 포즈 스냅(클립 재시작 관성 블렌드)·미끄러짐
        both = sorted(feet, key=lambda x: min(x[1], x[2]), reverse=True)[:5]
        for t, vl, vr, smp in both:
            log(f"PIE_FEET_BOTH t={t:.2f} min_foot={min(vl, vr):.0f}cm/s (l={vl:.0f} r={vr:.0f}) kind={smp[3]} wants={int(smp[4])} fin={int(smp[5])} animT={smp[6]:.2f} acc={int(smp[15])}")
        # 회전 구간 종료(fin 상승) 뒤 두 발이 자리 잡는 시간 — 연속 3샘플 동안 둘 다 5cm/s 미만
        for i in range(1, len(samples)):
            if samples[i][5] and not samples[i - 1][5]:
                t_fin = samples[i][0]
                calm, settle = 0, None
                for t, vl, vr, _ in feet:
                    if t <= t_fin:
                        continue
                    calm = calm + 1 if max(vl, vr) < 5.0 else 0
                    if calm >= 3:
                        settle = t - t_fin
                        break
                log(f"PIE_SETTLE fin_at={t_fin:.2f} feet_settled_after={'%.2f' % settle if settle is not None else 'never'}s")
                # fin 뒤 0.8초 발 속도 타임라인(0.05초 간격) — 재진입 게이트(ReentryMinRecoveryTime) 튜닝용
                tl, next_t = [], t_fin
                for t, vl, vr, smp in feet:
                    if t_fin < t <= t_fin + 0.8 and t >= next_t:
                        tl.append(f"{t - t_fin:.2f}:{vl:.0f}/{vr:.0f}{'*' if smp[4] else ''}")
                        next_t = t + 0.05
                log(f"PIE_SETTLE_TL fin_at={t_fin:.2f} dt:l/r(*=wants) " + " ".join(tl))
    # 턴 클립 선택 — wants 상승 에지마다 고른 클립과 그때 오프셋 (클램프·180 임계 튜닝: 180 클립이 실제로 나오는가)
    turns = [(cur[0], cur[3].split(":")[0], cur[2]) for prev, cur in zip(samples, samples[1:]) if cur[4] and not prev[4]]
    log(f"PIE_TURNS n={len(turns)} " + " ".join(f"{t:.2f}:{k}@{o:.0f}" for t, k, o in turns[:20]))
    # 클램프 미끄러짐 — 누적 중인데 오프셋이 클램프에 붙어 있으면 액터가 더 돈 만큼 메시가 월드에서 돈다(디딘 발이 끌린다).
    # 그 프레임들의 액터 Yaw 변화 합 = 발 대신 미끄러진 각, 그동안 두 발 중 느린 발 속도(둘 다 움직이면 미끄러짐)
    clamp_val = getattr(unreal, "_turn_clamp", None)
    if clamp_val:
        slid, n_cl, min_feet = 0.0, 0, []
        for (t, vl, vr, cur), prev in zip(feet, samples):
            if cur[15] and abs(cur[2]) >= clamp_val - 0.05:
                slid += abs(wrap(cur[1] - prev[1]))
                n_cl += 1
                min_feet.append(min(vl, vr))
        min_feet.sort()
        mean_feet = sum(min_feet) / len(min_feet) if min_feet else float("nan")
        log(f"PIE_CLAMP clamp={clamp_val:.0f} clamped_frames={n_cl} slid_deg={slid:.1f} min_foot mean={mean_feet:.0f} max={min_feet[-1] if min_feet else float('nan'):.0f}cm/s")
    marks = getattr(unreal, "_turn_marks", [])
    for t, name in marks:
        log(f"PIE_MARK t={t:.2f} {name}")
    # 구간별 자세 — 표식 뒤 0.6~1.1초(다음 표식 전) 평균. 오프셋·조준각이 같은 조건에서 손 거리·기울기를 비교한다
    def avg(xs):
        return sum(xs) / len(xs) if xs else float("nan")
    for i, (t0, name) in enumerate(marks):
        t1 = min(marks[i + 1][0] if i + 1 < len(marks) else samples[-1][0], t0 + 1.1)
        seg = [s for s in samples if t0 + 0.6 <= s[0] < t1 and s[10]]
        if not seg:
            log(f"PIE_POSE {name}: no aiming samples")
            continue
        log(f"PIE_POSE {name:<10} n={len(seg):3d} off={avg([s[2] for s in seg]):6.1f} aimYaw={avg([s[8] for s in seg]):6.1f} aimPitch={avg([s[21] for s in seg]):6.1f} "
            f"hands={avg([s[16] for s in seg]):5.1f} chest(f,s)=({avg([s[22][0] for s in seg]):6.1f},{avg([s[22][1] for s in seg]):6.1f}) "
            f"neck(f,s)=({avg([s[23][0] for s in seg]):6.1f},{avg([s[23][1] for s in seg]):6.1f}) gunYaw-cam={avg([wrap(s[20] - s[12]) for s in seg]):6.1f} gunPitch={avg([s[24] for s in seg]):6.1f} kind={seg[-1][3]}")
    # 전체 조준 구간의 최악값 — 손 거리 최소/최대, 가슴·목 옆 기울기 최대
    aim_s = [s for s in samples if s[10]]
    if aim_s:
        for label, key in (("hands_min", lambda s: -s[16]), ("hands_max", lambda s: s[16]), ("chest_side", lambda s: abs(s[22][1])), ("neck_side", lambda s: abs(s[23][1]))):
            s = max(aim_s, key=key)
            log(f"PIE_WORST {label}: t={s[0]:.2f} hands={s[16]:.1f} chest=({s[22][0]:.1f},{s[22][1]:.1f}) neck=({s[23][0]:.1f},{s[23][1]:.1f}) off={s[2]:.1f} aimYaw={s[8]:.1f} aimPitch={s[21]:.1f} kind={s[3]} wants={int(s[4])} fin={int(s[5])} animT={s[6]:.2f}")
    # 발사 — 새 투사체가 나타난 틱의 몸·카메라·총 방향 (몸이 돈 뒤 나가야 한다)
    # 원격 실행 응답 크기 한도 — 자동 사격이면 발사 줄이 수십 개라 앞 10개만
    shots_all = getattr(unreal, "_turn_shots", [])
    for t, vyaw, _, muzzle_vs_proj in shots_all[:10]:
        smp = min(samples, key=lambda s: abs(s[0] - t))
        log(f"PIE_SHOT t={t:.2f} proj_yaw={vyaw:.1f} actor_yaw={smp[1]:.1f} camera_yaw={smp[12]:.1f} body_gap={wrap(smp[12] - smp[1]):.1f} "
            f"mesh_gap={wrap(smp[12] - (smp[1] + smp[2])):.1f} gun_minus_proj={wrap(smp[20] - vyaw):.1f} muzzle_vs_proj={muzzle_vs_proj:.1f} off={smp[2]:.1f} acc={int(smp[15])}")
    # 총구 축 ↔ 실제 투사체 — 발사 틱의 총열 전방과 투사체 속도 3D 각 (총구 지표가 실제 탄도와 같은 것을 재는지)
    mvp = [s[3] for s in shots_all if not math.isnan(s[3])]
    if mvp:
        mvp.sort()
        log(f"PIE_MUZZLE_SHOTS n={len(mvp)} mean={sum(mvp) / len(mvp):.2f} p50={mvp[len(mvp) // 2]:.2f} max={mvp[-1]:.2f}")

    # 총구 축 지표 — 조준 중 샘플의 총열 ↔ 발사 방향(총구 → 카메라 조준점) 각
    def mstats(seg):
        e = sorted(s[25][0] for s in seg)
        if not e:
            return "n=0"
        return (f"n={len(e):4d} err3d mean={sum(e) / len(e):5.2f} p95={e[min(len(e) - 1, int(len(e) * 0.95))]:5.2f} max={e[-1]:5.2f} "
                f"yawErr={avg([s[25][1] for s in seg]):6.2f} pitchErr={avg([s[25][2] for s in seg]):6.2f} vsCam={avg([s[25][3] for s in seg]):5.2f} "
                f"(y{avg([s[25][7] for s in seg]):6.2f} p{avg([s[25][8] for s in seg]):6.2f} max{max(s[25][3] for s in seg):5.1f}) "
                f"aimYaw[{min(s[8] for s in seg):6.1f},{max(s[8] for s in seg):6.1f}] aimPitch[{min(s[21] for s in seg):5.1f},{max(s[21] for s in seg):5.1f}] "
                f"off[{min(s[2] for s in seg):6.1f},{max(s[2] for s in seg):6.1f}] dist={avg([s[25][4] for s in seg]):6.0f} barrelYaw-actor={avg([s[25][6] for s in seg]):6.1f}")
    aim_m = [s for s in samples if s[10] and s[25]]
    if aim_m:
        log(f"PIE_MUZZLE_ALL     {mstats(aim_m)}")
        # 상황별 — 턴 클립 회전 구간(커브 가중 > 0) · AO Yaw 범위 밖(|AimYaw| > 90) · 이동(strafe) · 나머지(정지 조준)
        buckets = (("turn_rot", lambda s: s[13] > 0.001), ("ao_sat", lambda s: abs(s[8]) > 90.0), ("moving", lambda s: s[26] > 10.0),
                   ("static", lambda s: s[13] <= 0.001 and abs(s[8]) <= 90.0 and s[26] <= 10.0))
        for name, pred in buckets:
            seg = [s for s in aim_m if pred(s)]
            log(f"PIE_MUZZLE_BUCKET {name:<9} {mstats(seg)}")
        for i, (t0, name) in enumerate(marks):
            t1 = marks[i + 1][0] if i + 1 < len(marks) else samples[-1][0] + 1e-3
            skip = 0.0 if name.endswith("*") else SEG_SKIP
            seg = [s for s in aim_m if t0 + skip <= s[0] < t1]
            log(f"PIE_MUZZLE_SEG {name:<12} {mstats(seg)}")
            if name in SEG_TIMELINE.split(","):
                next_t = t0
                for s in [s for s in aim_m if t0 <= s[0] < t1]:
                    if s[0] >= next_t:
                        log(f"PIE_MUZZLE_TL {name} dt={s[0] - t0:.2f} err3d={s[25][0]:.2f} (y{s[25][1]:.2f} p{s[25][2]:.2f}) vsCam={s[25][3]:.2f} dist={s[25][4]:.0f} hit={s[25][5]} "
                            f"aimPitch={s[21]:.1f} aimYaw={s[8]:.1f} off={s[2]:.1f} speed={s[26]:.0f}")
                        next_t = s[0] + 0.05
            if name.endswith("*") and seg:
                # 과도 구간의 자세 오차(총열 ↔ 카메라) 최악 2 — 그 순간 오프셋·턴 상태
                for s in sorted(seg, key=lambda s: s[25][3], reverse=True)[:2]:
                    log(f"PIE_MUZZLE_SEG_WORST {name:<12} t={s[0] - t0:.2f}s vsCam={s[25][3]:.1f} (y{s[25][7]:.1f} p{s[25][8]:.1f}) aimYaw={s[8]:.1f} off={s[2]:.1f} "
                        f"kind={s[3].split(':')[0]} wants={int(s[4])} w={s[13]:.2f} fin={int(s[5])} animT={s[6]:.2f} speed={s[26]:.0f}")
        for s in sorted(aim_m, key=lambda s: s[25][0], reverse=True)[:5]:
            log(f"PIE_MUZZLE_WORST t={s[0]:.2f} err3d={s[25][0]:.2f} yawErr={s[25][1]:.2f} pitchErr={s[25][2]:.2f} aimYaw={s[8]:.1f} aimPitch={s[21]:.1f} off={s[2]:.1f} "
                f"kind={s[3]} w={s[13]:.2f} fin={int(s[5])} speed={s[26]:.0f} dist={s[25][4]:.0f} hit={s[25][5]}")
        near = {}
        for s in aim_m:
            if s[25][4] < 300.0:
                near[s[25][5]] = near.get(s[25][5], 0) + 1
        log(f"PIE_MUZZLE_NEAR_HITS (조준점 < 3m, 클래스별 샘플 수) {near}")
    elif samples:
        log("PIE_MUZZLE_ALL no aiming samples with a ranged weapon")

    # 타임라인 줄 수 상한 ~200 — 원격 실행 클라이언트는 8KB 미만 조각을 받으면 끝으로 보고 끊어서(remote_execution _receive_message) 큰 응답이 무작위로 잘린다
    every = max(6, len(samples) // 200) if TIMELINE else len(samples) + 1
    for i, smp in enumerate(samples):
        if not TIMELINE:
            break
        if i % every == 0 or i == len(samples) - 1:
            t, yaw, off, kind, wants, fin, at, cv, aimyaw, st, aiming, mont, cyaw, w, rem, acc, hd = smp[:17]
            log(f"PIE_S t={t:.2f} yaw={yaw:.1f} cam={cyaw:.1f} off={off:.1f} kind={kind} wants={int(wants)} fin={int(fin)} acc={int(acc)} animT={at:.2f} curve={cv:.1f} w={w:.2f} rem={rem:.1f} aimYaw={aimyaw:.1f} linkedAimYaw={smp[17]:.1f} gun-cam={wrap(smp[20] - cyaw):.1f} aim={int(aiming)} hands={hd:.0f} "
                f"aimPitch={smp[21]:.1f} chest=({smp[22][0]:.0f},{smp[22][1]:.0f}) neck=({smp[23][0]:.0f},{smp[23][1]:.0f})")

else:
    world, actors = heroes()
    log(f"PIE_HEROES: {len(actors)}")
    for a in actors:
        asc = a.get_astral_ability_system_component()   # AbilitySystemBlueprintLibrary 는 Python 에 노출되지 않는다
        mesh = a.get_editor_property("mesh")
        cmc = a.get_editor_property("character_movement")
        if STEP == "arm":
            # 실제 경로 그대로 — 전환 GA(근접 → 원거리) 와 원거리 기본 공격 GA 를 클래스로 활성화 (입력 없이). 공격 GA 가 서버에서 AimHold GE 를 적용해야 한다
            switch_cls = unreal.load_class(None, SWITCH_GA)
            fire_cls = unreal.load_class(None, FIRE_GA)
            sw = asc.try_activate_ability_by_class(switch_cls, True)
            log(f"PIE_ARM_SWITCH: {sw} tags={owned_tags(asc)}")
            fi = asc.try_activate_ability_by_class(fire_cls, True)
            log(f"PIE_ARM_FIRE: {fi} tags={owned_tags(asc)}")
        log(f"PIE_ACTOR: {a.get_name()} role={a.get_local_role()} asc={asc is not None}")
        if asc:
            log(f"PIE_TAGS: {owned_tags(asc)} active_ge={len(asc.get_active_effects(unreal.GameplayEffectQuery()))}")
        log(f"PIE_ROT: orient={cmc.get_editor_property('orient_rotation_to_movement')} ctrl_yaw={a.get_editor_property('use_controller_rotation_yaw')}")
        main_anim = mesh.get_anim_instance()
        dump_anim("MAIN", main_anim)
        rifle_cls = unreal.load_asset(RIFLE_LAYERS).generated_class()
        linked = mesh.get_linked_anim_layer_instance_by_class(rifle_cls)
        dump_anim("LINKED_RIFLE", linked)
        # (상태 이름 조회는 제거 — record 단계 주석 참조)
    log("PIE_PROBE_DONE")
