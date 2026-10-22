import sys
# 진단 — 라이플 점프 자세 PIE 프로브 (2026-10-22): 조준·비조준 점프에서 상체가 지상 기준 자세를 유지하는지, 왼손이 언제 총을 놓고 다시 잡는지.
# 모드는 소스 첫 줄 뒤 STEP 상수로 고른다: begin · arm(낫 → 총) · record(매 틱 기록 시작) · mark(구간 이름) · jump(구간 표식 + 점프 입력) ·
# input(기록 콜백의 자동 사격 간격 · 전진 입력 바꾸기) · dump · end. 드라이버 = pie_jump_probe_run
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import math
import unreal

STEP = "sample"
AUTO_FIRE = 0.0   # record · input: > 0 이면 기록 콜백이 이 간격(초)마다 사격 GA — 조준(AimHold 2초)을 유지한다
MOVE_FWD = 0.0    # input: 기록 콜백이 매 틱 카메라 앞 방향 이동 입력(크기)을 넣는다 — 달리기 점프
MARK = ""

log = unreal.log
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
SWITCH_GA = "/Game/AbilitySystem/Abilities/GA_Hero_SwitchCombatStyle.GA_Hero_SwitchCombatStyle_C"
FIRE_GA = "/Game/AbilitySystem/Abilities/GA_Hero_BasicAttack_Projectile.GA_Hero_BasicAttack_Projectile_C"
GRIP_SOCKET = "LeftHandIK"      # 총 메시의 왼손 파지 소켓 (BP_Weapon_Rifle.LeftHandGripSocket)
CHEST_BONE = "spine_05"         # 상체 자세 기준 본 — 손·총구 위치를 이 본 공간에서 지상 기준과 비교한다
CURVE = "DisableLHandIK"        # = UAstralAnimInstance::LeftHandIKDisableCurve


def heroes():
    # 서버(첫 PIE) 월드의 로컬 조종 히어로 — 다인원 PIE 면 원격 폰도 같은 월드에 있다
    world = UES.get_game_world()
    if not world:
        raise RuntimeError("PIE_NO_WORLD")
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralCharacter_Hero)
    local = [a for a in actors if a.is_locally_controlled()]
    return world, local or actors


def weapon_mesh(a):
    for w in a.get_attached_actors():
        if isinstance(w, unreal.AstralRangedWeaponActor):
            m = w.get_component_by_class(unreal.SkeletalMeshComponent)
            if m and m.does_socket_exist("Muzzle"):
                return w, m
    return None, None


def vec_angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, u.normal().dot(v.normal())))))


def prop(obj, name, default=float("nan")):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


if STEP == "begin":
    # 백그라운드 에디터 스로틀 해제 (pie_aim_probe 와 같다)
    perf = unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings") or unreal.load_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")
    if perf:
        perf.set_editor_property("bThrottleCPUWhenNotForeground", False)
    LES.editor_request_begin_play()
    log("PIE_BEGIN_REQUESTED")

elif STEP == "end":
    LES.editor_request_end_play()
    log("PIE_END_REQUESTED")

elif STEP == "arm":
    world, actors = heroes()
    for a in actors:
        asc = a.get_astral_ability_system_component()
        log(f"PIE_ARM {a.get_name()} switch={asc.try_activate_ability_by_class(unreal.load_class(None, SWITCH_GA), True)}")

elif STEP == "mark":
    unreal._jp_mark = MARK
    log(f"PIE_MARK_SET {MARK}")

elif STEP == "jump":
    # 점프 입력 = ACharacter::Jump (GA_Hero_Jump 의 CharacterJumpStart 와 같은 호출) — 0.25초 뒤 기록 콜백이 StopJumping(입력 뗌)
    unreal._jp_jump = True
    unreal._jp_mark = MARK or "jump"
    log("PIE_JUMP_REQ")

elif STEP == "input":
    unreal._jp_autofire = AUTO_FIRE
    unreal._jp_move = MOVE_FWD
    log(f"PIE_INPUT autofire={AUTO_FIRE} move={MOVE_FWD}")

elif STEP == "record":
    world, actors = heroes()
    a = actors[0]
    mesh = a.get_editor_property("mesh")
    fire_cls = unreal.load_class(None, FIRE_GA)
    samples = []
    marks = []
    clock = [0.0]
    last_fire = [-10.0]
    jump_t = [None]
    wpn = [None, None]
    unreal._jp_mark = None
    unreal._jp_jump = False
    unreal._jp_autofire = AUTO_FIRE
    unreal._jp_move = 0.0

    def on_tick(dt):
        clock[0] += dt
        t = clock[0]
        if unreal._jp_mark:
            marks.append((t, unreal._jp_mark))
            unreal._jp_mark = None
        if unreal._jp_jump:
            unreal._jp_jump = False
            a.jump()
            jump_t[0] = t
        if jump_t[0] is not None and t - jump_t[0] > 0.25:
            a.stop_jumping()
            jump_t[0] = None
        if unreal._jp_autofire > 0.0 and t - last_fire[0] >= unreal._jp_autofire:
            last_fire[0] = t
            a.get_astral_ability_system_component().try_activate_ability_by_class(fire_cls, True)
        if unreal._jp_move != 0.0:
            cy = math.radians(a.get_controller().get_control_rotation().yaw)
            a.add_movement_input(unreal.Vector(math.cos(cy), math.sin(cy), 0.0), unreal._jp_move, False)
        if not wpn[1] or not wpn[1].does_socket_exist("Muzzle"):
            wpn[0], wpn[1] = weapon_mesh(a)
        anim = mesh.get_anim_instance()
        if not anim:
            return
        hr = mesh.get_socket_location("hand_r")
        hl = mesh.get_socket_location("hand_l")
        chest = mesh.get_socket_transform(CHEST_BONE, unreal.RelativeTransformSpace.RTS_WORLD)
        grip_err, vs_cam, gun_pitch, mz_c = float("nan"), float("nan"), float("nan"), None
        if wpn[1]:
            if wpn[1].does_socket_exist(GRIP_SOCKET):
                grip_err = (wpn[1].get_socket_location(GRIP_SOCKET) - hl).length()   # 왼손 ↔ 파지 소켓 — IK 알파 1 이면 0
            mx = wpn[1].get_socket_transform("Muzzle", unreal.RelativeTransformSpace.RTS_WORLD)
            f = mx.rotation.get_axis_x()
            _, cam_rot = a.get_controller().get_player_view_point()
            vs_cam = vec_angle(f, cam_rot.get_forward_vector())   # 총열 ↔ 카메라 방향 (시차 없는 자세 오차)
            gun_pitch = math.degrees(math.atan2(f.z, math.hypot(f.x, f.y)))
            mz_c = chest.inverse_transform_location(mx.translation)
        samples.append((t, prop(anim, "bIsInAir", False), prop(anim, "bIsAiming", False), a.get_velocity().z,
                        (hr - hl).length(), grip_err, vs_cam, gun_pitch,
                        chest.inverse_transform_location(hr), chest.inverse_transform_location(hl), mz_c,   # 8·9·10 상체 공간 손·총구
                        prop(anim, "LeftHandIKAlpha"), prop(anim, "AimPoseAlpha"), anim.get_curve_value(CURVE), prop(anim, "HandsFreeAlpha")))

    unreal._jp_samples = samples
    unreal._jp_marks = marks
    unreal._jp_handle = unreal.register_slate_pre_tick_callback(on_tick)   # pre-tick: 지난 프레임 애님 작업이 끝난 뒤
    log(f"PIE_RECORD_STARTED {a.get_name()} role={a.get_local_role()}")

elif STEP == "dump":
    try:
        unreal.unregister_slate_pre_tick_callback(unreal._jp_handle)
    except Exception:
        pass   # 재덤프 — 기록은 unreal 모듈 속성에 남아 있다
    samples = unreal._jp_samples
    marks = unreal._jp_marks
    log(f"PIE_DUMP n={len(samples)} marks={[(round(t, 2), m) for t, m in marks]}")

    def avg(xs):
        xs = [x for x in xs if x == x]
        return sum(xs) / len(xs) if xs else float("nan")

    def vavg(vs):
        vs = [x for x in vs if x is not None]
        return unreal.Vector(avg([x.x for x in vs]), avg([x.y for x in vs]), avg([x.z for x in vs])) if vs else None

    # 지상 기준 = 'ground_X' 구간(표식 0.5초 뒤 ~ 다음 표식) 평균 — 'jump_X' 구간의 공중 자세를 같은 조준 상태의 지상 자세와 비교한다
    segs = []
    refs = {}
    for i, (t0, name) in enumerate(marks):
        t1 = marks[i + 1][0] if i + 1 < len(marks) else samples[-1][0] + 1e-3
        segs.append((t0, t1, name))
        if name.startswith("ground"):
            seg = [s for s in samples if t0 + 0.5 <= s[0] < t1]
            refs[name] = (vavg([s[8] for s in seg]), vavg([s[9] for s in seg]), vavg([s[10] for s in seg]))
            log(f"PIE_REF {name} n={len(seg)} aim={avg([s[2] for s in seg]):.2f} hands={avg([s[4] for s in seg]):.1f} grip_err={avg([s[5] for s in seg]):.1f} "
                f"vsCam={avg([s[6] for s in seg]):.1f} gunPitch={avg([s[7] for s in seg]):.1f} lhAlpha={avg([s[11] for s in seg]):.2f} aimPose={avg([s[12] for s in seg]):.2f}")

    def dev(s, ref):
        # 상체 편차 = 두 손 위치(가슴 공간)의 지상 기준과의 거리 합, 총구 위치 편차
        if not ref or ref[0] is None:
            return float("nan"), float("nan")
        m = (s[10] - ref[2]).length() if (s[10] is not None and ref[2] is not None) else float("nan")
        return (s[8] - ref[0]).length() + (s[9] - ref[1]).length(), m

    for t0, t1, name in segs:
        if not name.startswith("jump"):
            continue
        ref = refs.get(name.replace("jump", "ground"))
        seg = [s for s in samples if t0 <= s[0] < t1]
        air = [s for s in seg if s[1]]
        if not air:
            log(f"PIE_JUMPSEG {name}: no air samples")
            continue
        devs = [dev(s, ref) for s in air]
        t_up, t_down = air[0][0], air[-1][0]
        # 왼손 IK 알파 시점 — 이륙 뒤 0.5 아래로 · 착지 뒤 0.5 위로 (비조준 기대: 놓았다가 다시 잡음)
        rel = next((s[0] - t_up for s in seg if s[0] >= t_up and s[11] < 0.5), float("nan"))
        reg = next((s[0] - t_down for s in seg if s[0] > t_down and s[11] >= 0.5), float("nan"))
        # 손 속도(가슴 공간) — 놓고 잡는 전환·착지 스냅이 튀면 봉우리가 뾰족하다. 이륙 0.2초 전 ~ 착지 0.8초 뒤만(뒤의 조준 만료 전환은 빼고)
        win = [s for s in seg if t_up - 0.2 <= s[0] <= t_down + 0.8]

        def top_speed(idx, lo, hi):
            w = [s for s in win if lo <= s[0] <= hi]
            v = [((cur[idx] - prev[idx]).length() / max(cur[0] - prev[0], 1e-4), cur[0] - t_up) for prev, cur in zip(w, w[1:])]
            return max(v) if v else (float("nan"), float("nan"))

        lh_top = top_speed(9, t_up - 0.2, t_down + 0.8)
        # 이륙(이륙 전후 0.45초) · 착지(착지 뒤 0.4초) 구간의 오른손·왼손 최대 속도
        spd = {name: (top_speed(8, lo, hi)[0], top_speed(9, lo, hi)[0]) for name, lo, hi in (("takeoff", t_up - 0.1, t_up + 0.35), ("landing", t_down, t_down + 0.4))}
        r_dev = [(s[8] - ref[0]).length() for s in air] if ref and ref[0] is not None else [float("nan")]
        log(f"PIE_JUMPSEG {name} air={t_down - t_up:.2f}s aim_air={avg([s[2] for s in air]):.2f} aimPose_air={avg([s[12] for s in air]):.2f} "
            f"lhAlpha_air={avg([s[11] for s in air]):.2f}[{min(s[11] for s in air):.2f},{max(s[11] for s in air):.2f}] curve_air={avg([s[13] for s in air]):.2f} "
            f"grip_err={avg([s[5] for s in air]):.1f} max={max(s[5] for s in air):.1f} hands={avg([s[4] for s in air]):.1f} "
            f"vsCam={avg([s[6] for s in air]):.1f} max={max(s[6] for s in air):.1f} gunPitch[{min(s[7] for s in air):.0f},{max(s[7] for s in air):.0f}] "
            f"ubDev={avg([d[0] for d in devs]):.1f} max={max(d[0] for d in devs):.1f} muzzleDev={avg([d[1] for d in devs]):.1f} "
            f"lhRelease={rel:.2f}s lhRegrip={reg:.2f}s lhSpeedMax={lh_top[0]:.0f}cm/s@{lh_top[1]:.2f}")
        log(f"PIE_JUMPHANDS {name} rightHandDev={avg(r_dev):.1f} max={max(r_dev):.1f}cm handsFree_air={avg([s[14] for s in air]):.2f} "
            f"speed(r/l cm/s) takeoff={spd['takeoff'][0]:.0f}/{spd['takeoff'][1]:.0f} landing={spd['landing'][0]:.0f}/{spd['landing'][1]:.0f}")
        # 타임라인 0.05초 간격 — 이륙 0.2초 전 ~ 착지 0.8초 뒤
        nxt = t_up - 0.2
        for s in seg:
            if t_up - 0.2 <= s[0] <= t_down + 0.8 and s[0] >= nxt:
                d = dev(s, ref)
                log(f"PIE_JTL {name} dt={s[0] - t_up:+.2f} air={int(s[1])} aim={int(s[2])} aimPose={s[12]:.2f} curve={s[13]:.2f} lhAlpha={s[11]:.2f} grip_err={s[5]:.1f} "
                    f"hands={s[4]:.1f} vsCam={s[6]:.1f} gunPitch={s[7]:.0f} ubDev={d[0]:.1f} mzDev={d[1]:.1f}")
                nxt = s[0] + 0.05
    log("PIE_DUMP_DONE")

else:
    world, actors = heroes()
    for a in actors:
        anim = a.get_editor_property("mesh").get_anim_instance()
        log(f"PIE_SAMPLE {a.get_name()} aim={prop(anim, 'bIsAiming')} air={prop(anim, 'bIsInAir')} lhAlpha={prop(anim, 'LeftHandIKAlpha')} aimPose={prop(anim, 'AimPoseAlpha')}")
