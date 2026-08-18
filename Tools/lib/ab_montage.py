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


# ─────────────────────────── 배치 ───────────────────────────

NOTIFY_CLASSES = {
    "GameplayEvent": "/Script/AstralBreak.AstralAnimNotify_GameplayEvent",
    "GameplayEventWindow": "/Script/AstralBreak.AstralAnimNotifyState_GameplayEventWindow",
}


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