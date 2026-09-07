"""AstralBreak 몽타주 자동화 헬퍼. UE 5.7 실측 검증 완료.

확인된 제약:
  - 슬롯 이름 변경 불가 (slot_anim_tracks 미노출) -> DefaultSlot 고정
  - 다중 섹션 구성 불가 (composite_sections 미노출) -> 몽타주 1개당 1섹션
  - FGameplayEventData의 instigator/target/context_handle/target_data 는
    런타임 전용이므로 에디터에서 건드리지 않는다
"""
import unreal

_at = unreal.AssetToolsHelpers.get_asset_tools()
_eal = unreal.EditorAssetLibrary
_abl = unreal.AnimationLibrary


# ─────────────────────────── 태그 ───────────────────────────

def tag(s: str) -> unreal.GameplayTag:
    """문자열 -> FGameplayTag. 미등록 태그면 예외."""
    t = unreal.GameplayTag()
    t.import_text(s)
    if not unreal.GameplayTagLibrary.is_gameplay_tag_valid(t):
        raise RuntimeError(f"등록되지 않은 GameplayTag: {s}")
    return t


def make_event_data(magnitude: float = 0.0, optional_object=None,
                    optional_object2=None, event_tag=None) -> unreal.GameplayEventData:
    """FGameplayEventData 중 에디터에서 의미 있는 필드만 채운다."""
    d = unreal.GameplayEventData()
    d.set_editor_property("event_magnitude", magnitude)
    if optional_object is not None:
        d.set_editor_property("optional_object", optional_object)
    if optional_object2 is not None:
        d.set_editor_property("optional_object2", optional_object2)
    if event_tag is not None:
        d.set_editor_property("event_tag", event_tag)
    return d


# ─────────────────────────── 생성 ───────────────────────────

def _mk_blend(time: float, option=None) -> unreal.AlphaBlend:
    ab = unreal.AlphaBlend()
    ab.set_editor_property("blend_time", time)
    if option is not None:
        ab.set_editor_property("blend_option", option)
    return ab


def create_montage(src_anim_path: str, dst_dir: str, montage_name: str,
                   blend_in: float = 0.10, blend_out: float = 0.20,
                   blend_out_trigger: float = 0.0, sync_group: str = "",
                   overwrite: bool = False) -> unreal.AnimMontage:
    """AnimSequence 하나로 단일 슬롯 몽타주를 생성한다."""
    seq = unreal.load_asset(src_anim_path)
    if not seq:
        raise RuntimeError(f"소스 애니메이션 없음: {src_anim_path}")

    dst = f"{dst_dir}/{montage_name}"
    if _eal.does_asset_exist(dst):
        if not overwrite:
            raise RuntimeError(f"이미 존재 (overwrite=True 필요): {dst}")
        _eal.delete_asset(dst)

    fac = unreal.AnimMontageFactory()
    fac.set_editor_property("target_skeleton", seq.get_editor_property("skeleton"))
    fac.set_editor_property("source_animation", seq)

    mon = _at.create_asset(montage_name, dst_dir, unreal.AnimMontage, fac)
    if not mon:
        raise RuntimeError(f"몽타주 생성 실패: {dst}")

    mon.set_editor_property("blend_in", _mk_blend(blend_in))
    mon.set_editor_property("blend_out", _mk_blend(blend_out))
    mon.set_editor_property("blend_out_trigger_time", blend_out_trigger)
    if sync_group:
        mon.set_editor_property("sync_group", sync_group)

    # 팩토리가 만든 빈 기본 트랙 정리
    for t in list(_abl.get_animation_notify_track_names(mon)):
        if str(t).isdigit() and not _abl.get_animation_notify_events_for_track(mon, t):
            _abl.remove_animation_notify_track(mon, t)

    return mon


# ─────────────────────────── Notify ───────────────────────────

def ensure_track(montage, track_name: str, color=(1.0, 1.0, 1.0, 1.0)) -> None:
    if not _abl.is_valid_anim_notify_track_name(montage, track_name):
        _abl.add_animation_notify_track(montage, track_name, unreal.LinearColor(*color))


def clear_track(montage, track_name: str) -> int:
    """트랙의 모든 notify 제거. 재실행 멱등성 확보용."""
    if not _abl.is_valid_anim_notify_track_name(montage, track_name):
        return 0
    return _abl.remove_animation_notify_events_by_track(montage, track_name)


def add_notify(montage, track_name: str, time: float,
               notify_class_path: str, **props):
    cls = unreal.load_class(None, notify_class_path)
    if not cls:
        raise RuntimeError(f"Notify 클래스 로드 실패: {notify_class_path}")
    ensure_track(montage, track_name)
    n = _abl.add_animation_notify_event(montage, track_name, time, cls)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def add_notify_state(montage, track_name: str, start: float, duration: float,
                     state_class_path: str, **props):
    cls = unreal.load_class(None, state_class_path)
    if not cls:
        raise RuntimeError(f"NotifyState 클래스 로드 실패: {state_class_path}")
    ensure_track(montage, track_name)
    ns = _abl.add_animation_notify_state_event(montage, track_name, start, duration, cls)
    for k, v in props.items():
        ns.set_editor_property(k, v)
    return ns


MOTION_WARPING_CLASS = "/Script/MotionWarping.AnimNotifyState_MotionWarping"


def add_motion_warping_window(montage, track_name: str, start: float, duration: float,
                              warp_target_name: str, warp_rotation: bool = True,
                              warp_translation: bool = False, **modifier_props):
    """MotionWarping 밴드 배치 (락온 4단계 — 회전 전용 방향 보정).

    설정값은 NotifyState가 아니라 그 안의 RootMotionModifier 서브오브젝트에 있다
    (엔진이 SkewWarp를 기본 서브오브젝트로 만들어 둔다 — 새로 만들지 않는다).
    warp_translation 기본 False: 워프 타겟 위치가 아바타 현재 위치라 병진 워프가 켜지면
    전진 루트모션이 제자리로 수렴한다.
    modifier_props: rotation_method / warp_max_rotation_rate / warp_rotation_time_multiplier 등 추가 프로퍼티
    """
    ns = add_notify_state(montage, track_name, start, duration, MOTION_WARPING_CLASS)
    modifier = ns.get_editor_property("root_motion_modifier")
    if modifier is None:
        raise RuntimeError("MotionWarping NotifyState에 root_motion_modifier가 없다 (엔진 기본 서브오브젝트 누락)")
    modifier.set_editor_property("warp_target_name", warp_target_name)
    modifier.set_editor_property("warp_rotation", warp_rotation)
    modifier.set_editor_property("warp_translation", warp_translation)
    for k, v in modifier_props.items():
        modifier.set_editor_property(k, v)
    return ns


# ─────────────────────────── 저장/검증 ───────────────────────────

def save(montage) -> bool:
    return _eal.save_loaded_asset(montage)


def describe(montage) -> dict:
    return {
        "path": montage.get_path_name(),
        "length": round(montage.get_play_length(), 4),
        "sections": [str(montage.get_section_name(i))
                     for i in range(montage.get_num_sections())],
        "tracks": [str(t) for t in _abl.get_animation_notify_track_names(montage)],
        "notify_count": len(_abl.get_animation_notify_events(montage)),
    }


def _safe_prop(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return None


def describe_notifies(montage) -> list:
    """모든 notify/notify state를 [트랙, 클래스, 시작, 종료, 주요 프로퍼티]로 덤프한다.
    밴드 배치 검증(워프 밴드가 WeaponTrace 시작 전에 끝나는가 등)과 probe용.
    실측: FAnimNotifyEvent는 시간·트랙 프로퍼티가 Python에 안 나온다 — AnimationLibrary의
    get_anim_notify_event_trigger_time / duration과 트랙별 조회로 우회."""
    out = []
    for track in _abl.get_animation_notify_track_names(montage):
        for ev in _abl.get_animation_notify_events_for_track(montage, track):
            state = _safe_prop(ev, "notify_state_class")
            notify = _safe_prop(ev, "notify")
            obj = state or notify
            start = float(_abl.get_anim_notify_event_trigger_time(ev))
            duration = float(_abl.get_anim_notify_event_duration(ev)) if state else 0.0
            entry = {
                "track": str(track),
                "class": obj.get_class().get_name() if obj else "?",
                "start": round(start, 4),
                "end": round(start + duration, 4),
            }
            if obj:
                for key in ("begin_event_tag", "end_event_tag", "event_tag"):
                    v = _safe_prop(obj, key)
                    if v is not None:
                        entry[key] = str(_safe_prop(v, "tag_name"))
                mod = _safe_prop(obj, "root_motion_modifier")
                if mod is not None:
                    entry["modifier"] = mod.get_class().get_name()
                    for key in ("warp_target_name", "warp_rotation", "warp_translation",
                                "rotation_type", "rotation_method", "warp_max_rotation_rate",
                                "warp_rotation_time_multiplier"):
                        v = _safe_prop(mod, key)
                        if v is not None:
                            entry[key] = str(v)
            out.append(entry)
    out.sort(key=lambda e: e["start"])
    return out


# ─────────────────────────── 배치 ───────────────────────────

NOTIFY_CLASSES = {
    "GameplayEvent": "/Script/AstralBreak.AstralAnimNotify_GameplayEvent",
    "GameplayEventWindow": "/Script/AstralBreak.AstralAnimNotifyState_GameplayEventWindow",
    "MotionWarping": MOTION_WARPING_CLASS,
}

# MotionWarping 스펙에서 modifier로 전달되는 키 (NotifyState가 아니라 서브오브젝트 프로퍼티)
MOTION_WARPING_MODIFIER_KEYS = ("rotation_method", "warp_max_rotation_rate",
                                "warp_rotation_time_multiplier")


def build_from_spec(spec: dict, dry_run: bool = False) -> dict:
    """JSON 스펙 하나로 몽타주 1개를 생성한다.

    {
      "source": "/Game/Animation/Hero/Anims/Attacks/AS_Hero_Attack1",
      "dst_dir": "/Game/Animation/Hero/Montages",
      "name": "AM_Hero_Attack1",
      "blend_in": 0.08, "blend_out": 0.20,
      "notifies": [
        {"type": "GameplayEventWindow", "track": "Combat",
         "start": 0.30, "duration": 0.25,
         "begin_event_tag": "GameplayEvent.WeaponTrace.Begin",
         "end_event_tag": "GameplayEvent.WeaponTrace.End",
         "magnitude": 1.0}
      ]
    }
    """
    name = spec["name"]
    if dry_run:
        return {"dry_run": True, "name": name,
                "notifies": len(spec.get("notifies", []))}

    mon = create_montage(
        src_anim_path=spec["source"],
        dst_dir=spec["dst_dir"],
        montage_name=name,
        blend_in=spec.get("blend_in", 0.10),
        blend_out=spec.get("blend_out", 0.20),
        blend_out_trigger=spec.get("blend_out_trigger", 0.0),
        sync_group=spec.get("sync_group", ""),
        overwrite=spec.get("overwrite", True),
    )

    tracks = {n.get("track", "Combat") for n in spec.get("notifies", [])}
    for t in tracks:
        clear_track(mon, t)

    for n in spec.get("notifies", []):
        if n["type"] == "MotionWarping":
            # {"type": "MotionWarping", "track": "Facing", "start": 0.0, "duration": 0.2,
            #  "warp_target_name": "BasicMelee.Stage0", "warp_rotation": true, "warp_translation": false}
            extra = {k: n[k] for k in MOTION_WARPING_MODIFIER_KEYS if k in n}
            add_motion_warping_window(mon, n.get("track", "Facing"), n["start"], n["duration"],
                                      n["warp_target_name"],
                                      warp_rotation=n.get("warp_rotation", True),
                                      warp_translation=n.get("warp_translation", False),
                                      **extra)
            continue

        cls_path = NOTIFY_CLASSES.get(n["type"], n["type"])
        props = {}
        for key in ("event_tag", "begin_event_tag", "end_event_tag"):
            if key in n:
                props[key] = tag(n[key])
        if "magnitude" in n:
            props["event_data"] = make_event_data(magnitude=n["magnitude"])

        if "duration" in n:
            add_notify_state(mon, n.get("track", "Combat"),
                             n["start"], n["duration"], cls_path, **props)
        else:
            add_notify(mon, n.get("track", "Combat"), n["start"], cls_path, **props)

    save(mon)
    return describe(mon)