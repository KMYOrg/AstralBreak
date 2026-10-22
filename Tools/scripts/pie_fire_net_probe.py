import sys
# 원거리 사격 네트워크 타이밍 PIE 프로브 — 리슨 서버 + 클라 N, 패킷 지연 에뮬레이션 아래에서 클라 입력 사격의 시각표를 잰다:
# 클라(소유 폰) 활성화 · 조준 태그 · 몸 정렬 · 발사(어빌리티 종료) / 서버(원격 폰) 활성화 · 조준 태그 · 투사체 생성과 방향.
# 모드는 소스 첫 줄 뒤 상수로 고른다(드라이버가 정규식으로 바꾼다): begin · lag · deny · client_switch · face_away · record · dump · end
# 실행은 ue_exec 브릿지 경유 (주석에 확장자를 쓰지 말 것 — ExecuteFile 경로 오인)
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
import glob
import math
import os
import time
import unreal

STEP = "dump"
LABEL = ""
NUM_PLAYERS = 3       # 리슨 호스트 포함
LAG_MS = 0            # lag: 모든 PIE 월드(서버·클라)의 송신 지연 — 0 이면 NetEmulation.Off
LOSS = 0              # lag: 클라 월드 송신 패킷 손실 %(비신뢰성 ServerUpdateCamera·ServerMove 가 빠진다 — 신뢰성 RPC 는 재전송)
DROP_CAMERA = 0       # lag: 클라의 ServerUpdateCamera(비신뢰성 카메라 보고)만 이 % 버린다 — 서버 카메라 캐시가 낡는 고장 주입
DENY = 0              # deny: 서버가 다음 N 번의 클라 활성화를 거부(AbilitySystem.DenyClientActivations — 예측 롤백 시험)
FACE_YAW = 175.0      # face_away: 카메라 Yaw = 몸 + 이 값
PRESS_TIMES = [0.0]   # record: 기록 시작 기준 사격 입력 주입 시각(초)
FLICK_YAW = 0.0       # record: 마지막 입력과 같은 틱에 카메라 Yaw 를 이만큼 꺾는다(플릭 직후 발사 — 허용각 밖이면 몸 정렬 뒤 발사)
FLICK_PITCH = 0.0     # record: 같은 틱에 카메라 Pitch 도 이만큼(Pitch 는 몸 정렬과 무관 — 그 프레임에 바로 발사)
HOST = False          # face_away·record: 리슨 호스트(서버 월드 로컬 폰)도 같이 돌리고 쏜다

IA_SWITCH = "/Game/Input/Actions/IA_SwitchCombatStyle"
IA_FIRE = "/Game/Input/Actions/IA_Attack_Basic"
TAG_ACTIVE = "Ability.Attack.Basic.Ranged"
TAG_AIM = "State.Ranged.Aiming"
ALIGN_TOL = 10.0      # GA FireAlignToleranceYaw 기본값

log = unreal.log
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def owned_tags(asc):
    if not asc:
        return ""
    return unreal.GameplayTagLibrary.get_debug_string_from_gameplay_tag_container(unreal.GameplayTagLibrary.get_owned_gameplay_tags(asc))


def pie_worlds():
    worlds = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
    if not worlds:
        raise RuntimeError("PIE_NO_WORLD")
    return sorted(worlds, key=lambda w: w.get_name())


def server_world():
    for w in pie_worlds():
        if unreal.SystemLibrary.is_server(w):
            return w
    raise RuntimeError("PIE_NO_SERVER_WORLD")


def client_worlds():
    return [w for w in pie_worlds() if not unreal.SystemLibrary.is_server(w)]


def heroes(world):
    return sorted(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AstralCharacter_Hero), key=lambda a: a.get_name())


def local_hero(world):
    return next((a for a in heroes(world) if a.is_locally_controlled()), None)


def yaw_gap(a):
    return abs((a.get_control_rotation().yaw - a.get_actor_rotation().yaw + 180.0) % 360.0 - 180.0)


def yaw_pitch(v):
    return math.degrees(math.atan2(v.y, v.x)), math.degrees(math.atan2(v.z, math.hypot(v.x, v.y)))


def angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, u.normal().dot(v.normal())))))


def weapon_muzzle(a):
    for w in a.get_attached_actors():
        if isinstance(w, unreal.AstralRangedWeaponActor):
            m = w.get_component_by_class(unreal.SkeletalMeshComponent)
            if m and m.does_socket_exist("Muzzle"):
                return w, m.get_socket_location("Muzzle")
    return None, None


def camera_aim_point(world, a):
    # 그 월드의 컨트롤러 카메라로 본 조준점 — AstralRangedAim::ComputeCameraAimPoint 재현(총구 투영 시작 · Visibility · 총구 뒤면 원거리)
    weapon, muzzle = weapon_muzzle(a)
    ctrl = a.get_controller()
    if muzzle is None or not ctrl:
        return None
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


def inject(world, action):
    subs = list(unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem))
    sub = next((s for s in subs if s.get_world() == world), None)
    if sub:
        sub.inject_input_vector_for_action(action, unreal.Vector(1.0, 0.0, 0.0), [], [])
    return sub is not None


def play_settings():
    return unreal.find_object(None, "/Script/UnrealEd.Default__LevelEditorPlaySettings")


def editor_log():
    # 이 에디터 자기 로그(read_automation_results 와 같은 방식) — 서버 GA 의 "[Ranged] ... Report=" 줄(보고 검증 결과·각)을 읽는다
    candidates = glob.glob(os.path.join(unreal.Paths.project_log_dir(), "AstralBreak*.log"))
    return max(candidates, key=os.path.getmtime) if candidates else None


if STEP == "begin":
    settings = play_settings()
    unreal._fn_saved = (settings.get_editor_property("RunUnderOneProcess"), settings.get_editor_property("PlayNumberOfClients"))
    settings.set_editor_property("RunUnderOneProcess", True)
    settings.set_editor_property("PlayNumberOfClients", NUM_PLAYERS)
    LES.editor_request_begin_play()
    log(f"PIE_FN_BEGIN players={NUM_PLAYERS} saved={unreal._fn_saved}")

elif STEP == "end":
    # 지연 설정은 프로세스 전역(Persistent)이라 다음 PIE 넷 드라이버에도 붙는다 — 끄고 내린다
    for w in pie_worlds():
        unreal.SystemLibrary.execute_console_command(w, "NetEmulation.Off")
        unreal.SystemLibrary.execute_console_command(w, "NetEmulation.DropNothing")
    unreal.SystemLibrary.execute_console_command(server_world(), "AbilitySystem.DenyClientActivations 0")
    LES.editor_request_end_play()
    saved = getattr(unreal, "_fn_saved", None)
    if saved:
        settings = play_settings()
        settings.set_editor_property("RunUnderOneProcess", saved[0])
        settings.set_editor_property("PlayNumberOfClients", saved[1])
    log(f"PIE_FN_END restored={saved}")

elif STEP == "lag":
    for w in pie_worlds():
        unreal.SystemLibrary.execute_console_command(w, f"NetEmulation.PktLag {LAG_MS}" if LAG_MS > 0 else "NetEmulation.Off")
    if LOSS > 0:
        for w in client_worlds():
            unreal.SystemLibrary.execute_console_command(w, f"NetEmulation.PktLoss {LOSS}")
    if DROP_CAMERA > 0:
        # 엔진 인자는 "통과" 확률이다(NetEmulationHelper.cpp:254 — 난수 ≤ 인자면 보내고 아니면 이름이 맞을 때 버림, 0 이하는 기본 20) → 100 − 원하는 버림 %
        keep = max(100.0 - DROP_CAMERA, 0.001)
        for w in client_worlds():
            unreal.SystemLibrary.execute_console_command(w, f"NetEmulation.DropUnreliableRPC ServerUpdateCamera {keep}")
    # 수락된 보고는 Verbose 로만 남는다 — 정상 차이 분포를 보려고 켠다
    unreal.SystemLibrary.execute_console_command(server_world(), "Log LogAstralAbilitySystem Verbose")
    log(f"PIE_FN_LAG {LAG_MS}ms on {len(pie_worlds())} worlds (each direction), client loss {LOSS}%, camera report drop {DROP_CAMERA}%")

elif STEP == "deny":
    unreal.SystemLibrary.execute_console_command(server_world(), f"AbilitySystem.DenyClientActivations {DENY}")
    log(f"PIE_FN_DENY next {DENY} client activations")

elif STEP == "client_switch":
    action = unreal.load_asset(IA_SWITCH)
    for w in client_worlds() + ([server_world()] if HOST else []):
        log(f"PIE_FN_SWITCH {w.get_name()} injected={inject(w, action)}")

elif STEP == "face_away":
    # 클라 월드의 로컬 폰 — 카메라(컨트롤러) Yaw 만 몸 + FACE_YAW. 비조준이면 정지한 몸은 돌지 않는다. 컨트롤 회전은 이동 패킷으로 서버에 간다
    for w in client_worlds() + ([server_world()] if HOST else []):
        a = local_hero(w)
        if a:
            ay = a.get_actor_rotation().yaw
            a.get_controller().set_control_rotation(unreal.Rotator(0.0, 0.0, ay + FACE_YAW))
            log(f"PIE_FN_FACE_AWAY {w.get_name()} {a.get_name()} actor_yaw={ay:.1f} control_yaw={ay + FACE_YAW:.1f} tags={owned_tags(a.get_astral_ability_system_component())}")

elif STEP == "record":
    # 매 프레임(slate pre-tick) 표본 — 상태가 바뀐 순간만 남긴다. 사격 입력은 PRESS_TIMES 에 주입(주입 다음 입력 틱에 Started)
    sw = server_world()
    cws = client_worlds()
    shooters = cws + ([sw] if HOST else [])
    action = unreal.load_asset(IA_FIRE)
    t0 = time.perf_counter()
    pending = sorted(PRESS_TIMES)
    state = {}          # (머신, 폰) → {active, aim, aligned}
    events = []         # (t, 머신, 폰, 이벤트, 값)
    shots = []          # 서버 투사체 (t, 이름, 발사자, 방향, 생성 위치, 서버 control yaw/pitch, 발사자 몸 yaw)
    seen = set(p.get_name() for p in unreal.GameplayStatics.get_all_actors_of_class(sw, unreal.AstralProjectile))
    fires = []          # 클라 발사가 쓴 카메라 (t, 클라, 카메라 조준점, 카메라 yaw/pitch, 폰 위치, 카메라 전방)
    frames = [0]
    flicked = [False]
    provisional = {}    # 머신 → (월드, 주입 콜백의 카메라 스냅샷)

    # 콜백은 월드 틱 뒤(프레임 끝)라 이 순간의 카메라 = 다음 프레임 발사가 읽을 카메라 캐시(GetPlayerViewPoint 는 프레임 끝에 갱신되는 캐시)
    def snapshot(t, machine, a):
        cam_loc, cam_rot = a.get_controller().get_player_view_point()
        return (t, machine, camera_aim_point(a.get_world(), a), cam_rot.yaw, cam_rot.pitch, a.get_actor_location(), cam_rot.get_forward_vector())

    def machine_of(w):
        return "host" if w == sw else f"client{cws.index(w)}"

    def watch(t, machine, a, want_local):
        if a.is_locally_controlled() != want_local:
            return
        if want_local and machine == "server":
            machine = "host"
        tags = owned_tags(a.get_astral_ability_system_component())
        key = (machine, a.get_name())
        st = state.setdefault(key, {"active": False, "aim": False, "aligned": None})
        active, aim = TAG_ACTIVE in tags, TAG_AIM in tags
        aligned = yaw_gap(a) <= ALIGN_TOL
        if active != st["active"]:
            events.append((t, machine, a.get_name(), "active", int(active)))
            if not active and want_local:
                # 정렬을 기다린 발사 — 즉발 경로는 발사한 프레임에 끝난다. 플릭 뒤 카메라는 멈춰 있어 이 순간 카메라 = 발사가 쓴 카메라
                fires.append(snapshot(t, machine, a))
        if aim != st["aim"]:
            events.append((t, machine, a.get_name(), "aim", int(aim)))
        if aligned != st["aligned"]:
            events.append((t, machine, a.get_name(), "aligned", int(aligned)))
        st.update(active=active, aim=aim, aligned=aligned)

    def on_tick(dt):
        t = time.perf_counter() - t0
        frames[0] += 1
        # 주입 다음 프레임에 활성화 → (정렬돼 있으면) 발사 → 종료가 한 프레임 안에 끝나 active 전이가 안 잡힌다 — 그 발사가 쓴 카메라는 주입 콜백의 스냅샷
        for machine, (w, snap) in provisional.items():
            a = local_hero(w)
            if a and TAG_ACTIVE not in owned_tags(a.get_astral_ability_system_component()) and not state.get((machine, a.get_name()), {}).get("active"):
                fires.append(snap)
        provisional.clear()
        if pending and t >= pending[0]:
            if len(pending) == 1 and (FLICK_YAW != 0.0 or FLICK_PITCH != 0.0) and not flicked[0]:
                # 플릭은 사격 한 프레임 앞 — 같은 콜백에 넣으면 클라 자신도 플릭 전 카메라 캐시로 쏜다(실제 플레이의 "본 화면 그대로" 와 같다)
                flicked[0] = True
                for cw in shooters:
                    a = local_hero(cw)
                    if a:
                        r = a.get_control_rotation()
                        a.get_controller().set_control_rotation(unreal.Rotator(0.0, r.pitch + FLICK_PITCH, r.yaw + FLICK_YAW))
                        events.append((t, machine_of(cw), a.get_name(), "flick", 1))
            else:
                pending.pop(0)
                for cw in shooters:
                    a = local_hero(cw)
                    events.append((t, cw.get_name(), a.get_name() if a else "-", "inject", int(inject(cw, action))))
                    if a:
                        provisional[machine_of(cw)] = (cw, snapshot(t, machine_of(cw), a))
        for p in unreal.GameplayStatics.get_all_actors_of_class(sw, unreal.AstralProjectile):
            if p.get_name() in seen:
                continue
            seen.add(p.get_name())
            inst = p.get_instigator()
            ctrl_rot = inst.get_control_rotation() if inst else unreal.Rotator()
            # 서버가 아는 그 플레이어의 카메라(원격이면 ServerUpdateCamera 캐시) — 발사 순간 이 값과 클라 카메라의 차가 "서버 카메라 지연"
            cam_rot = inst.get_controller().get_player_view_point()[1] if inst and inst.get_controller() else unreal.Rotator()
            shots.append((t, p.get_name(), inst.get_name() if inst else "-", p.get_velocity(), p.get_actor_location(),
                          ctrl_rot.yaw, ctrl_rot.pitch, inst.get_actor_rotation().yaw if inst else float("nan"), cam_rot.get_forward_vector()))
        for a in heroes(sw):
            watch(t, "server", a, False)
            if HOST:
                watch(t, "server", a, True)
        for i, cw in enumerate(cws):
            for a in heroes(cw):
                watch(t, f"client{i}", a, True)
                if HOST:
                    # 관찰자 — 이 클라 화면의 다른 폰(시뮬 프록시: 다른 클라·호스트). 조준 태그는 서버 복제(Minimal)로만 온다
                    watch(t, f"client{i}-sim", a, False)

    log_path = editor_log()
    unreal._fn_rec = dict(events=events, shots=shots, fires=fires, frames=frames, t0=t0, label=LABEL,
                          log_path=log_path, log_offset=os.path.getsize(log_path) if log_path else 0)
    unreal._fn_handle = unreal.register_slate_pre_tick_callback(on_tick)
    log(f"PIE_FN_RECORD[{LABEL}] presses={PRESS_TIMES} flick=({FLICK_YAW},{FLICK_PITCH}) clients={len(cws)}")

elif STEP == "dump":
    unreal.unregister_slate_pre_tick_callback(unreal._fn_handle)
    rec = unreal._fn_rec
    span = time.perf_counter() - rec["t0"]
    lab = rec["label"]
    log(f"PIE_FN_DUMP[{lab}] frames={rec['frames'][0]} span={span:.2f}s ({rec['frames'][0] / max(span, 1e-3):.0f}Hz) events={len(rec['events'])} shots={len(rec['shots'])}")
    for t, machine, pawn, kind, value in rec["events"]:
        log(f"PIE_FN_EV[{lab}] t={t:.3f} {machine} {pawn} {kind}={value}")
    for t, name, inst, v, loc, cyaw, cpitch, body, scam in rec["shots"]:
        vy, vp = yaw_pitch(v)
        sy, sp = yaw_pitch(scam)
        log(f"PIE_FN_SHOT[{lab}] t={t:.3f} {name} instigator={inst} proj=({vy:.1f},{vp:.1f}) server_ctrl=({cyaw:.1f},{cpitch:.1f}) server_cam=({sy:.1f},{sp:.1f}) server_body_yaw={body:.1f}")
    # 클라 발사 순간의 카메라 조준점 ↔ 서버 투사체 방향. 짝 = 그 뒤 1초 안에 그 폰 근처(3m)에서 생긴 첫 투사체 (월드마다 액터 이름이 달라 위치로 짝짓는다)
    # cam_div = 클라 발사 순간 카메라 ↔ 투사체 생성 순간 서버 카메라 (검증 허용각의 근거)
    used = set()
    for t, machine, target, cyaw, cpitch, pawn_loc, cfwd in rec["fires"]:
        cand = [s for s in rec["shots"] if s[1] not in used and t - 0.05 <= s[0] <= t + 1.0 and (s[4] - pawn_loc).length() < 300.0]
        if not cand or target is None:
            log(f"PIE_FN_FIRE[{lab}] t={t:.3f} {machine} cam=({cyaw:.1f},{cpitch:.1f}) shot=none")
            continue
        s = cand[0]
        used.add(s[1])
        ty, tp = yaw_pitch(target - s[4])
        log(f"PIE_FN_FIRE[{lab}] t={t:.3f} {machine} cam=({cyaw:.1f},{cpitch:.1f}) shot_t={s[0]:.3f} lag={s[0] - t:.3f} "
            f"want=({ty:.1f},{tp:.1f}) dir_err={angle(s[3], target - s[4]):.2f}deg cam_div={angle(cfwd, s[8]):.2f}deg")
    # 서버 GA 가 남긴 보고 검증(원격 플레이어 자유 조준 발사마다 1줄) — Report=Accepted/Clamped/Rejected · Divergence=보고 ↔ 서버 컨트롤 회전
    if rec.get("log_path"):
        with open(rec["log_path"], "rb") as f:
            f.seek(rec["log_offset"])
            for line in f.read().decode("utf-8", errors="replace").splitlines():
                if "[Ranged]" in line and "Report=" in line:
                    log(f"PIE_FN_REPORT[{lab}] {line.strip()[-110:]}")
