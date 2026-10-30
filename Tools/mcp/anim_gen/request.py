"""생성 요청 정규화·검증 (지침서 §9, 개정 6). 자연어 해석은 Claude Code 가 하고 여기는 구조화된 요청만 받는다."""
from __future__ import annotations

import copy
import os
import re

from . import body_fit, bvh, selection, timing, weapon as weapon_req
from .editor import package_path
from .envelope import AnimGenError, diag

CATEGORIES = ("idle", "locomotion", "weapon_action", "full_body_new")
ROOT_MOTION_MODES = ("auto", "on", "off")
REQUIRED = ("target_skeleton", "animation_name", "output_path", "motion_category")
SEARCH_KEYS = {"query", "path_prefix", "asset_class", "min_length", "max_length", "root_motion", "additive", "loop", "tags", "limit"}
RETARGET_KEYS = {"source_mesh", "existing_source_rig", "existing_target_rig", "existing_retargeter", "source_pelvis", "source_chains", "ops",
                 "source_facing", "align_mode", "body_clearance"}
# create_ik_retargeter align_mode — per_bone: 뼈 수 같은 체인 FK 1:1 + 본 대 본 · 체인 끝 정렬(엔진 정렬은 같은 param 끼리 짝지어
# 관절 비율이 다르면 팔꿈치 굽힘이 덜 전달된다). match_existing 의 기본, default ops 는 정렬하지 않아 engine 만
ALIGN_MODES = ("per_bone", "engine")
# retarget_animations body_clearance — 대상 메시 몸(허리 · 골반 · 넓적다리)에 손 · 아래팔이 들어가는지. resolve: 관통한 프레임만 어깨 둘레
# 최소 회전으로 위팔을 고친다(소스 어깨 반폭 대비 대상 엉덩 · 옷 부피가 크면 같은 팔 각도로 손이 몸에 들어간다 — 2026-10-25 CMU → Vesper 관통
# 프레임 49 · 73% → 0 · 0%) · measure: 검증에만 · off. 요청이 비우면 계획이 정한다(Phase 8-1): two_hand_weapon_grip 이면 measure(위팔 보정이
# 양손을 벌리지 않게 — 2026-10-26 E1: 같은 seed 에서 resolve 가 손목 간격을 p50 1.9 cm 더 벌렸다), 아니면 resolve
BODY_CLEARANCE_MODES = ("resolve", "measure", "off")
# Phase 4 — blender Provider 가 변환할 모션 파일
MOTION_FILE_DEFAULTS = {"path": None, "unit": "auto", "facing": "auto", "range": None, "axis_forward": "-Z", "axis_up": "Y"}
FACINGS = ("auto", "keep", "+X", "-X", "+Y", "-Y")
# Phase 5 — AI 생성 Provider(local_ai) 설정. prompt 는 모델이 읽는 영어 문장(description 은 기록만)
# options: Provider 이름 → 그 Provider 만 읽는 설정(Phase 6 — {"external.meshy": {"mode": "prime" | "swift"}}). 다른 Provider 는 무시하고,
# 값의 검사는 그 Provider 의 계획 단계가 한다(이름은 라우터가 레지스트리로 검사)
# Phase 8-1 — candidates: seed, seed+1, … 후보 수(1 ~ 6 — 1 이면 지금 단일 실행) · refine: 요청 플래그(constraints.two_hand_weapon_grip ·
# foot_contact)를 local_ai 2차 생성 제약으로(local_ai/refine.py) · select: 후보 선별 가중치(selection.py)
REFINE_DEFAULTS = {"mode": "auto", "grip": {"lead_hand": "right", "target": "meet", "spacing_cm": None, "target_spacing_cm": None, "from_s": None,
                                            "to_s": None}, "keyframe_step": 3}
SPACING_MAX_CM = 100.0
GENERATION_DEFAULTS = {"seed": None, "samples": 1, "steps": 100, "postprocess": "auto", "pick": 0, "constraints": [], "options": {},
                       "candidates": 1, "refine": REFINE_DEFAULTS, "select": {"weights": None}}
MAX_CANDIDATES = 6
CONSTRAINT_KEYS = {"root_path": ({"points"}, set()), "keep_pose": ({"npz", "times"}, {"part"}), "kimodo_raw": ({"path"}, set())}
POSE_PARTS = ("full", "left_hand", "right_hand", "left_foot", "right_foot")
PROMPT_MAX = 500
# 후처리로 다루는 제약 → 한계 코드. 그 밖의 참 제약은 CONSTRAINT_UNSUPPORTED
CONSTRAINT_LIMITATIONS = {"two_hand_weapon_grip": "GRIP_NOT_VALIDATED", "foot_contact": "FOOT_CONTACT_NOT_ENFORCED"}
# Phase 5 — blender 변환 단계의 프레임 렌더 비교(review.render)와 보정 단계 자리(fix). 시각은 변환된 클립 기준 초(0 = 첫 프레임)
REVIEW_VIEWS = ("front", "side")
REVIEW_RENDER_DEFAULTS = {"times": None, "count": None, "views": list(REVIEW_VIEWS), "reference_images": []}
REVIEW_DEFAULT_COUNT = 4
REVIEW_MAX_ROWS = 12          # 행(시각) × 뷰 = 렌더 수 — 한 Blender 실행이 기한 안에 끝나게
REVIEW_MAX_REFERENCES = 4
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
# Phase 8-2 — 대상 메시 캡처(review.capture → 플러그인 capture_animation). 행 = render 시각(render 가 있을 때) 또는 times | count,
# sequence = 움직임용 연속 프레임(APNG 로 잇는다, false = 시트만), compare = render 가 있으면 소스 골격 칸을 붙인 비교 시트
REVIEW_CAPTURE_KEYS = {"times", "count", "views", "mesh", "sequence", "compare"}
REVIEW_SEQUENCE_DEFAULTS = {"fps": 15, "cell_height_px": 320, "max_frames": 150}
# Phase 7 — 포장(package: 시퀀스 additive · 몽타주 · BlendSpace)과 AnimBP 연결(anim_bp). 출력은 output_path(허용 목록), 쓰기는 플러그인의
# 옵트인 generation_guard 아래에서. 자리표시는 문자열 값 전체가 그것일 때만 바꾼다 — $asset = 최종 시퀀스(재사용이면 그 애셋)
PLACEHOLDERS = ("$asset", "$montage", "$blendspace")
PACKAGE_KEYS = ("additive", "montage", "blendspace")
ADDITIVE_TYPES = ("LocalSpaceBase", "RotationOffsetMeshSpace")
REF_POSE_TYPES = ("RefPose", "AnimScaled", "AnimFrame", "LocalAnimFrame")
# AnimFrame · AnimScaled 는 기준 시퀀스가 있어야 유효하다(UAnimSequence::IsValidAdditive, AnimSequence.cpp:2627-2639) — 기본은 자기 프레임(LocalAnimFrame 0)
ADDITIVE_DEFAULTS = {"additive_type": "LocalSpaceBase", "ref_pose_type": "LocalAnimFrame", "ref_frame_index": 0, "ref_pose_sequence": None}
MONTAGE_DEFAULTS = {"name": None, "slot": "DefaultSlot", "blend_in": None, "blend_out": None, "sections": None}
BLENDSPACE_DEFAULTS = {"name": None, "dimensions": 1, "axes": None, "samples": None, "aim_offset": False}
AXIS_KEYS = {"name", "min", "max", "grid", "snap", "wrap"}
ANIM_BP_DEFAULTS = {"asset_path": None, "operations": [], "scenario": None, "smoke": True}
SCENARIO_KEYS = {"montage", "expect", "wait_frames", "set_variables", "mesh", "map"}
DEFAULTS = {
    "target_mesh": None, "hero": None, "family": None, "description": "", "duration_seconds": None, "frame_rate": None,
    "loop": None, "root_motion_mode": "auto", "reference_animations": [], "search": None, "edits": None, "retarget": {},
    "constraints": {}, "generation_policy": None, "provider": "auto", "integrate_anim_bp": False, "motion_file": None,
    "prompt": None, "generation": None, "review": None, "fix": None, "package": None, "anim_bp": None,
    # Phase 8-4c — 손에 든 무기(weapon.py). 장비 데이터는 Claude Code 가 읽어 넣는다(플러그인 · anim_gen 은 읽지 않는다 — §8)
    "weapon": None,
}
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _bad(field: str, message: str, reason: str = "BAD_FIELD", **details) -> AnimGenError:
    return AnimGenError("BAD_REQUEST", f"request.{field}: {message}", reason=reason, field=field, **details)


def _number(req: dict, key: str, positive: bool = True) -> None:
    value = req.get(key)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (positive and value <= 0):
        raise _bad(key, "must be a positive number")


def normalize(raw: dict) -> tuple[dict, list[dict]]:
    """→ (정규화된 요청, diagnostics). 모르는 필드는 거부한다(오타가 조용히 무시되지 않게)."""
    if not isinstance(raw, dict):
        raise AnimGenError("BAD_REQUEST", "request must be an object", reason="BAD_FIELD")
    diagnostics: list[dict] = []
    if "save" in raw:
        raise _bad("save", "save is an argument of generate_motion, not part of the request", reason="UNKNOWN_FIELD")
    unknown = sorted(set(raw) - set(DEFAULTS) - set(REQUIRED))
    if unknown:
        raise _bad(unknown[0], f"unknown field(s) {unknown}", reason="UNKNOWN_FIELD", allowed=sorted(set(DEFAULTS) | set(REQUIRED)))
    req = copy.deepcopy(DEFAULTS)
    req.update(copy.deepcopy(raw))
    for key in REQUIRED:
        if not req.get(key):
            raise _bad(key, "is required", reason="MISSING_FIELD")

    if req["motion_category"] not in CATEGORIES:
        raise _bad("motion_category", f"must be one of {list(CATEGORIES)}", value=req["motion_category"])
    if not _NAME.match(req["animation_name"]):
        raise _bad("animation_name", "must be an asset name (letters, digits, '_')", value=req["animation_name"])
    if req["root_motion_mode"] not in ROOT_MOTION_MODES:
        raise _bad("root_motion_mode", f"must be one of {list(ROOT_MOTION_MODES)}")
    for key in ("duration_seconds", "frame_rate"):
        _number(req, key)
    if req["loop"] is not None and not isinstance(req["loop"], bool):
        raise _bad("loop", "must be true, false or null")
    if not isinstance(req["integrate_anim_bp"], bool):
        raise _bad("integrate_anim_bp", "must be true or false")

    for key in ("target_skeleton", "target_mesh"):
        if req[key]:
            req[key] = package_path(req[key])
    req["output_path"] = package_path(req["output_path"])
    if not req["output_path"].startswith("/"):
        raise _bad("output_path", "must be a content folder such as /Game/Animation/Generated/Vesper")

    refs = req["reference_animations"] or []
    if not isinstance(refs, list) or not all(isinstance(r, str) and r for r in refs):
        raise _bad("reference_animations", "must be a list of asset paths")
    req["reference_animations"] = [package_path(r) for r in refs]

    search = req["search"]
    if search is not None:
        if not isinstance(search, dict):
            raise _bad("search", "must be an object")
        extra = sorted(set(search) - SEARCH_KEYS)
        if extra:
            raise _bad(f"search.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(SEARCH_KEYS))

    edits = req["edits"]
    if edits is not None:
        if not isinstance(edits, dict) or set(edits) - {"source", "operations"}:
            raise _bad("edits", "must be {source?, operations[]}")
        ops = edits.get("operations")
        if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
            raise _bad("edits.operations", "must be a non-empty list of {op, ...} (Phase 2 op dictionary)")
        source = package_path(edits.get("source")) if edits.get("source") else None
        if source:
            # 편집 소스 = 기존 모션 소스. 참조와 다르면 어느 쪽을 쓸지 모호하다
            if req["reference_animations"] and req["reference_animations"][0] != source:
                raise _bad("edits.source", "differs from reference_animations[0] — give one source", reason="CONFLICTING_SOURCE")
            if not req["reference_animations"]:
                req["reference_animations"] = [source]
        req["edits"] = {"operations": ops}

    retarget = req["retarget"] or {}
    if not isinstance(retarget, dict):
        raise _bad("retarget", "must be an object")
    extra = sorted(set(retarget) - RETARGET_KEYS)
    if extra:
        raise _bad(f"retarget.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(RETARGET_KEYS))
    if retarget.get("ops", "match_existing") not in ("match_existing", "default"):
        raise _bad("retarget.ops", "must be match_existing (default) or default")
    ops = retarget.get("ops", "match_existing")
    align = retarget.get("align_mode", "per_bone" if ops == "match_existing" else "engine")
    if align not in ALIGN_MODES:
        raise _bad("retarget.align_mode", f"must be one of {list(ALIGN_MODES)}")
    if align == "per_bone" and ops != "match_existing":
        raise _bad("retarget.align_mode", "per_bone refines the auto-aligned target pose — only with ops match_existing", reason="ALIGN_MODE_WITHOUT_ALIGN")
    retarget["align_mode"] = align
    if retarget.get("body_clearance") is not None and retarget["body_clearance"] not in BODY_CLEARANCE_MODES:
        raise _bad("retarget.body_clearance", f"must be one of {list(BODY_CLEARANCE_MODES)} (omit it and the plan decides: measure with "
                   "two_hand_weapon_grip, else resolve)")
    retarget["body_clearance"] = retarget.get("body_clearance")
    # 소스가 보는 UE 축 — auto 면 소스 스켈레톤 기준 포즈로 잰다, keep 이면 정면을 맞추지 않는다
    if retarget.get("source_facing", "auto") not in FACINGS:
        raise _bad("retarget.source_facing", f"must be one of {list(FACINGS)} (UE axes the source faces)")
    for key in ("source_mesh", "existing_source_rig", "existing_target_rig", "existing_retargeter"):
        if retarget.get(key):
            retarget[key] = package_path(retarget[key])
    req["retarget"] = retarget

    req["motion_file"] = _motion_file(req["motion_file"])
    if req["prompt"] is not None and (not isinstance(req["prompt"], str) or not req["prompt"].strip() or len(req["prompt"]) > PROMPT_MAX):
        raise _bad("prompt", f"must be a non-empty English sentence for the model (≤ {PROMPT_MAX} characters)")
    req["prompt"] = req["prompt"].strip() if req["prompt"] else None
    req["generation"] = _generation(req["generation"])
    req["review"] = _review(req["review"])
    req["fix"] = _fix(req["fix"])
    req["weapon"] = _weapon(req["weapon"], req["fix"], raw.get("fix"))

    if not isinstance(req["constraints"], dict):
        raise _bad("constraints", "must be an object of flags")
    if not isinstance(req["provider"], str) or not req["provider"]:
        raise _bad("provider", "must be 'auto' or a provider name")

    req["package"] = _package(req["package"], req)
    req["anim_bp"] = _anim_bp(req["anim_bp"], req["integrate_anim_bp"])
    _check_placeholders(req)

    # 명명 규칙 AS_<영웅>_<계열>_<동작> — 강제하지 않고 알린다
    expected = "_".join(t for t in ("AS", req["hero"], req["family"]) if t) + "_"
    if not req["animation_name"].startswith(expected):
        diagnostics.append(diag("warning", "NAME_RULE", f"animation_name '{req['animation_name']}' does not follow AS_<Hero>_<Family>_<Action> "
                                f"(expected prefix '{expected}')"))
    return req, diagnostics


def _motion_file(raw) -> dict | None:
    """motion_file{path, unit, facing, range, axis_forward, axis_up} — 문자열이면 path. 형식만 본다(루트 · 파일 내용은 blender 계획 단계)."""
    if raw is None:
        return None
    mf = {"path": raw} if isinstance(raw, str) else raw
    if not isinstance(mf, dict):
        raise _bad("motion_file", "must be a path or {path, unit?, facing?, range?, axis_forward?, axis_up?}")
    extra = sorted(set(mf) - set(MOTION_FILE_DEFAULTS))
    if extra:
        raise _bad(f"motion_file.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(MOTION_FILE_DEFAULTS))
    mf = {**MOTION_FILE_DEFAULTS, **mf}
    path = mf["path"]
    if not isinstance(path, str) or not path.strip() or not os.path.isabs(path.strip()):
        raise _bad("motion_file.path", "must be an absolute file path (under [AnimGraphMcp] ImportSourceRoots)")
    mf["path"] = os.path.normpath(path.strip()).replace("\\", "/")
    unit = mf["unit"]
    if not (unit in ("auto", *bvh.UNITS_CM) or (isinstance(unit, (int, float)) and not isinstance(unit, bool) and unit > 0)):
        raise _bad("motion_file.unit", f"must be auto, {', '.join(bvh.UNITS_CM)} or a positive number (cm per file unit)")
    if mf["facing"] not in FACINGS:
        raise _bad("motion_file.facing", f"must be one of {list(FACINGS)} (UE axes)")
    rng = mf["range"]
    if rng is not None and (not isinstance(rng, dict) or set(rng) - {"start", "end"}
                            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rng.values())):
        raise _bad("motion_file.range", "must be {start?, end?} in seconds")
    try:
        bvh.axis_matrix(mf["axis_forward"], mf["axis_up"])
    except bvh.BvhError as err:
        raise _bad("motion_file.axis_forward", err.message) from None
    return mf


def _int(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _seconds(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _generation(raw) -> dict:
    """generation{seed?, samples 1~4, steps 10~1000, postprocess auto|on|off, pick, constraints[]} — 형식만 본다(파일 · 프레임 범위는 local_ai 계획)."""
    gen = {} if raw is None else raw
    if not isinstance(gen, dict):
        raise _bad("generation", "must be an object")
    extra = sorted(set(gen) - set(GENERATION_DEFAULTS))
    if extra:
        raise _bad(f"generation.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(GENERATION_DEFAULTS))
    gen = {**copy.deepcopy(GENERATION_DEFAULTS), **gen}
    if gen["seed"] is not None and not _int(gen["seed"], 0, 2 ** 31 - 1):
        raise _bad("generation.seed", "must be an integer in [0, 2^31 - 1] (omit it and the plan pins one)")
    if not _int(gen["samples"], 1, 4):
        raise _bad("generation.samples", "must be an integer in [1, 4]")
    if not _int(gen["steps"], 10, 1000):
        raise _bad("generation.steps", "must be an integer in [10, 1000] (diffusion steps, default 100)")
    if gen["postprocess"] not in ("auto", "on", "off"):
        raise _bad("generation.postprocess", "must be auto, on or off")
    if not _int(gen["pick"], 0, gen["samples"] - 1):
        raise _bad("generation.pick", f"must be an integer in [0, samples - 1 = {gen['samples'] - 1}] (the sample that is retargeted)")
    options = gen["options"]
    if not isinstance(options, dict) or not all(isinstance(k, str) and k and isinstance(v, dict) for k, v in options.items()):
        raise _bad("generation.options", "must be {<provider name>: {...}} — settings only that provider reads, e.g. {\"external.meshy\": {\"mode\": \"swift\"}}")
    if not _int(gen["candidates"], 1, MAX_CANDIDATES):
        raise _bad("generation.candidates", f"must be an integer in [1, {MAX_CANDIDATES}] — seeds seed, seed+1, … in one Kimodo run, the select step picks one")
    if gen["candidates"] > 1 and gen["samples"] > 1:
        raise _bad("generation.candidates", "candidates (one sample per seed) and samples (several samples of one seed) do not mix — give one",
                   reason="CONFLICTING_FIELDS")
    gen["refine"] = _refine(gen["refine"])
    gen["select"] = _select(gen["select"])
    items = gen["constraints"]
    if not isinstance(items, list):
        raise _bad("generation.constraints", "must be a list of {type: root_path | keep_pose | kimodo_raw, ...}")
    for k, c in enumerate(items):
        where = f"generation.constraints[{k}]"
        if not isinstance(c, dict) or c.get("type") not in CONSTRAINT_KEYS:
            raise _bad(where, f"type must be one of {sorted(CONSTRAINT_KEYS)}")
        required, optional = CONSTRAINT_KEYS[c["type"]]
        missing, unknown = sorted(required - set(c)), sorted(set(c) - required - optional - {"type"})
        if missing or unknown:
            raise _bad(where, f"{c['type']} needs {sorted(required)} (optional {sorted(optional) or 'none'}) — missing {missing}, unknown {unknown}")
        if c["type"] == "root_path":
            points = c["points"]
            if not isinstance(points, list) or not points:
                raise _bad(f"{where}.points", "must be a non-empty list of {t, forward_cm, left_cm, yaw_deg?}")
            for j, p in enumerate(points):
                ok = (isinstance(p, dict) and not set(p) - {"t", "forward_cm", "left_cm", "yaw_deg"} and _seconds(p.get("t"))
                      and all(isinstance(p.get(key), (int, float)) and not isinstance(p.get(key), bool) for key in ("forward_cm", "left_cm"))
                      and (p.get("yaw_deg") is None or (isinstance(p["yaw_deg"], (int, float)) and not isinstance(p["yaw_deg"], bool))))
                if not ok:
                    raise _bad(f"{where}.points[{j}]", "must be {t (s, ≥ 0), forward_cm, left_cm, yaw_deg? (+ = turn left)} — character-relative")
        else:
            key = "npz" if c["type"] == "keep_pose" else "path"
            suffix = ".npz" if key == "npz" else ".json"
            path = c[key]
            if not isinstance(path, str) or not os.path.isabs(path) or not path.lower().endswith(suffix):
                raise _bad(f"{where}.{key}", f"must be an absolute {suffix} path under [AnimGraphMcp] ImportSourceRoots")
            c[key] = os.path.normpath(path).replace("\\", "/")
            if c["type"] == "keep_pose":
                if not isinstance(c["times"], list) or not c["times"] or not all(_seconds(t) for t in c["times"]):
                    raise _bad(f"{where}.times", "must be a non-empty list of seconds (≥ 0) on the generated timeline")
                if c.get("part", "full") not in POSE_PARTS:
                    raise _bad(f"{where}.part", f"must be one of {list(POSE_PARTS)}")
    return gen


def _refine(raw) -> dict:
    """generation.refine{mode auto|off, grip{lead_hand, target meet|lead, spacing_cm | target_spacing_cm, from_s, to_s}, keyframe_step 1~10} — 형식만
    (프레임 범위 · 간격 사상은 local_ai 계획)."""
    if not isinstance(raw, dict):
        raise _bad("generation.refine", "must be {mode?, grip?, keyframe_step?}")
    extra = sorted(set(raw) - set(REFINE_DEFAULTS))
    if extra:
        raise _bad(f"generation.refine.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(REFINE_DEFAULTS))
    out = {**copy.deepcopy(REFINE_DEFAULTS), **{k: v for k, v in raw.items() if k != "grip"}}
    if out["mode"] not in ("auto", "off"):
        raise _bad("generation.refine.mode", "must be auto (a second generation pass for the converted flags) or off (flags stay limitations)")
    if not _int(out["keyframe_step"], 1, 10):
        raise _bad("generation.refine.keyframe_step", "must be an integer in [1, 10] (constraint every n frames)")
    grip = raw.get("grip") or {}
    if not isinstance(grip, dict):
        raise _bad("generation.refine.grip", "must be {lead_hand?, target?, spacing_cm? | target_spacing_cm?, from_s?, to_s?}")
    extra = sorted(set(grip) - set(REFINE_DEFAULTS["grip"]))
    if extra:
        raise _bad(f"generation.refine.grip.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(REFINE_DEFAULTS["grip"]))
    g = {**REFINE_DEFAULTS["grip"], **grip}
    if g["lead_hand"] not in ("left", "right"):
        raise _bad("generation.refine.grip.lead_hand", "must be left or right (the hand nearer the guard)")
    if g["target"] not in ("meet", "lead"):
        raise _bad("generation.refine.grip.target", "must be meet (move both wrists into reach, default) or lead (keep the lead hand path — comparison)")
    # 상한 100 cm — 자루 무기(Vesper 낫: 운영 애니 양손 구간 손목 간격 50 ~ 78 cm, p50 55 ~ 66)까지. 둘 다 비우면 검 손잡이(주 손 너클 폭 + 1 cm).
    # spacing_cm = 생성 골격(Kimodo SOMA) 간격, target_spacing_cm = 대상 메시 간격 — 계획이 간격 사상(motion_metrics.gap_map)으로 다른 쪽을 정한다
    if g["spacing_cm"] is not None and g["target_spacing_cm"] is not None:
        raise _bad("generation.refine.grip.target_spacing_cm", "give spacing_cm (generation skeleton) or target_spacing_cm (target mesh), not both",
                   reason="CONFLICTING_FIELDS")
    if g["spacing_cm"] is not None and not (_num(g["spacing_cm"]) and 0 < g["spacing_cm"] <= SPACING_MAX_CM):
        raise _bad("generation.refine.grip.spacing_cm", f"must be null (lead knuckle width + 1 cm — a sword hilt) or a number in (0, {SPACING_MAX_CM:g}] "
                   "(wrist-to-wrist on the generation skeleton along the pass-1 wrist line — the target mesh gets a different gap; prefer target_spacing_cm)")
    if g["target_spacing_cm"] is not None and not (_num(g["target_spacing_cm"]) and 0 < g["target_spacing_cm"] <= SPACING_MAX_CM):
        raise _bad("generation.refine.grip.target_spacing_cm", f"must be null or a number in (0, {SPACING_MAX_CM:g}] (wrist-to-wrist on the target mesh "
                   "— e.g. 55 ~ 65 for a two-handed polearm like Vesper's scythe; the plan converts it to the generation spacing)")
    for key in ("from_s", "to_s"):
        if g[key] is not None and not _seconds(g[key]):
            raise _bad(f"generation.refine.grip.{key}", "must be null or seconds ≥ 0 on the generated timeline")
    if g["from_s"] is not None and g["to_s"] is not None and g["from_s"] > g["to_s"]:
        raise _bad("generation.refine.grip.from_s", "must not be after to_s")
    out["grip"] = g
    return out


def _select(raw) -> dict:
    """generation.select{weights{grip, stance, swing, attack, clearance, breakage}} — 키 6개만, 0 이상(selection.check_weights)."""
    if not isinstance(raw, dict) or set(raw) - {"weights"}:
        raise _bad("generation.select", "must be {weights?{" + ", ".join(selection.WEIGHTS) + "}}")
    weights = raw.get("weights")
    if weights is not None:
        try:
            weights = selection.check_weights(weights)
        except selection.WeightError as err:
            raise _bad("generation.select.weights", str(err)) from None
    return {"weights": weights}


def _review(raw) -> dict | None:
    """review{render?{times[] | count, views[], reference_images[]}, capture?{…}} — 형식만 본다(시각 범위 · 이미지 루트 · 존재는 계획).
    하나 이상. 빠진 쪽은 키가 없다(render 만이면 개정 8 과 같은 모양)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw or set(raw) - {"render", "capture"}:
        raise _bad("review", "must be {render?{times[] | count, views?, reference_images?}, capture?{…}} with at least one")
    out: dict = {}
    if raw.get("render") is not None:
        out["render"] = _review_render(raw["render"])
    if raw.get("capture") not in (None, False):
        out["capture"] = _review_capture(raw["capture"], out.get("render"))
    if not out:
        raise _bad("review", "needs render or capture")
    return out


def _review_capture(raw, render: dict | None) -> dict:
    """review.capture — true 또는 {times? | count?, views?, mesh?, sequence?{fps, cell_height_px, max_frames} | false, compare?}.
    render 가 있으면 행은 render 시각을 따른다(times · count 를 주면 CONFLICTING_FIELDS — 두 시트가 같은 행이어야 나란히 본다)."""
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raise _bad("review.capture", "must be true or {times? | count?, views?, mesh?, sequence?, compare?}")
    extra = sorted(set(raw) - REVIEW_CAPTURE_KEYS)
    if extra:
        raise _bad(f"review.capture.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(REVIEW_CAPTURE_KEYS))
    cap = {"times": raw.get("times"), "count": raw.get("count"), "views": raw.get("views"), "mesh": raw.get("mesh"),
           "sequence": raw.get("sequence", True), "compare": raw.get("compare", True)}
    if cap["times"] is not None and cap["count"] is not None:
        raise _bad("review.capture.times", "give times or count, not both", reason="CONFLICTING_FIELDS")
    if render is not None and (cap["times"] is not None or cap["count"] is not None):
        raise _bad("review.capture.times", "with review.render the capture rows follow the render times — leave times / count out", reason="CONFLICTING_FIELDS")
    if cap["times"] is not None:
        if not isinstance(cap["times"], list) or not 1 <= len(cap["times"]) <= REVIEW_MAX_ROWS or not all(_seconds(t) for t in cap["times"]):
            raise _bad("review.capture.times", f"must be 1 to {REVIEW_MAX_ROWS} seconds (≥ 0) on the final clip (0 = its first frame)")
        cap["times"] = [float(t) for t in cap["times"]]
    elif render is None:
        cap["count"] = REVIEW_DEFAULT_COUNT if cap["count"] is None else cap["count"]
        if not _int(cap["count"], 1, REVIEW_MAX_ROWS):
            raise _bad("review.capture.count", f"must be an integer in [1, {REVIEW_MAX_ROWS}] (evenly spaced, first and last frame included)")
    if cap["views"] is None:
        cap["views"] = list(render["views"]) if render is not None else list(REVIEW_VIEWS)
    views = cap["views"]
    if not isinstance(views, list) or not views or len(set(views)) != len(views) or not set(views) <= set(REVIEW_VIEWS):
        raise _bad("review.capture.views", f"must be a non-empty list of distinct {list(REVIEW_VIEWS)}")
    if cap["mesh"] is not None:
        if not isinstance(cap["mesh"], str) or not cap["mesh"].startswith("/"):
            raise _bad("review.capture.mesh", "must be a SkeletalMesh path (omit it to use target_mesh)")
        cap["mesh"] = package_path(cap["mesh"])
    seq = cap["sequence"]
    if seq is False or seq is None:
        cap["sequence"] = None
    else:
        seq = {} if seq is True else seq
        if not isinstance(seq, dict) or set(seq) - set(REVIEW_SEQUENCE_DEFAULTS):
            raise _bad("review.capture.sequence", f"must be true, false or {{{', '.join(REVIEW_SEQUENCE_DEFAULTS)}}}")
        seq = {**REVIEW_SEQUENCE_DEFAULTS, **seq}
        if not _int(seq["fps"], 1, 30) or not _int(seq["cell_height_px"], 64, 1024) or not _int(seq["max_frames"], 1, 300):
            raise _bad("review.capture.sequence", "fps 1 ~ 30, cell_height_px 64 ~ 1024, max_frames 1 ~ 300 (integers)")
        cap["sequence"] = seq
    if not isinstance(cap["compare"], bool):
        raise _bad("review.capture.compare", "must be true or false")
    return cap


def _review_render(render) -> dict:
    """review.render — 개정 8 규칙 그대로(blender 변환 단계의 소스 골격 렌더)."""
    if not isinstance(render, dict):
        raise _bad("review", "must be {render{times[] | count, views?, reference_images?}}")
    extra = sorted(set(render) - set(REVIEW_RENDER_DEFAULTS))
    if extra:
        raise _bad(f"review.render.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(REVIEW_RENDER_DEFAULTS))
    render = {**copy.deepcopy(REVIEW_RENDER_DEFAULTS), **render}
    if render["times"] is not None and render["count"] is not None:
        raise _bad("review.render.times", "give times or count, not both", reason="CONFLICTING_FIELDS")
    if render["times"] is not None:
        times = render["times"]
        if not isinstance(times, list) or not 1 <= len(times) <= REVIEW_MAX_ROWS or not all(_seconds(t) for t in times):
            raise _bad("review.render.times", f"must be 1 to {REVIEW_MAX_ROWS} seconds (≥ 0) on the converted clip (0 = its first frame)")
        render["times"] = [float(t) for t in times]
    else:
        render["count"] = REVIEW_DEFAULT_COUNT if render["count"] is None else render["count"]
        if not _int(render["count"], 1, REVIEW_MAX_ROWS):
            raise _bad("review.render.count", f"must be an integer in [1, {REVIEW_MAX_ROWS}] (evenly spaced, first and last frame included)")
    views = render["views"]
    if not isinstance(views, list) or not views or len(set(views)) != len(views) or not set(views) <= set(REVIEW_VIEWS):
        raise _bad("review.render.views", f"must be a non-empty list of distinct {list(REVIEW_VIEWS)}")
    refs = render["reference_images"]
    if not isinstance(refs, list) or len(refs) > REVIEW_MAX_REFERENCES:
        raise _bad("review.render.reference_images", f"must be a list of at most {REVIEW_MAX_REFERENCES} image paths")
    for k, path in enumerate(refs):
        if not isinstance(path, str) or not os.path.isabs(path.strip()) or not path.strip().lower().endswith(IMAGE_SUFFIXES):
            raise _bad(f"review.render.reference_images[{k}]", "must be an absolute .png / .jpg path under [AnimGraphMcp] ImportSourceRoots")
    render["reference_images"] = [os.path.normpath(p.strip()).replace("\\", "/") for p in refs]
    return render


def _fix(raw) -> dict:
    """fix{ops[{op, ...}], timing?, body?} — ops = blender 변환 단계의 보정 op(형식만 본다 — 지원 여부는 blender 계획의 op 사전).
    timing(Phase 8-3) = 리타깃 뒤 대상 시퀀스의 흐느적 보정(timing.py — 휘두름 가속 · 정지 머리/꼬리 트림), 기본값을 채운다.
    body(Phase 8-4b) = 리타깃 · timing 뒤 대상 시퀀스의 몸 전체 한 풀이(body_fit.py — 관통 · 파지 keep · 지시 목표 targets[]). 자연어 지시를 목표로
    바꾸는 것은 Claude Code — 여기는 구조만 본다. 꺼져 있으면 키가 없다(켜지 않은 요청의 계획은 앞 개정과 같다)."""
    fix = {} if raw is None else raw
    if not isinstance(fix, dict):
        raise _bad("fix", "must be {ops[], timing?, body?}")
    extra = sorted(set(fix) - {"ops", "timing", "body"})
    if extra:
        raise _bad(f"fix.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=["ops", "timing", "body"])
    ops = fix.get("ops", [])
    if not isinstance(ops, list) or not all(isinstance(o, dict) and isinstance(o.get("op"), str) and o["op"] for o in ops):
        raise _bad("fix.ops", "must be a list of {op, ...}")
    try:
        timing_cfg = timing.normalize(fix.get("timing"))
    except timing.TimingError as err:
        raise _bad(err.args[0], err.args[1]) from None
    try:
        body_cfg = body_fit.normalize(fix.get("body"))
    except body_fit.BodyFitError as err:
        raise _bad(err.field, err.message, reason=err.reason) from None
    return {"ops": ops, **({"timing": timing_cfg} if timing_cfg else {}), **({"body": body_cfg} if body_cfg else {})}


def _weapon(raw, fix: dict, raw_fix) -> dict | None:
    """weapon(Phase 8-4c) — 형식만 본다(소켓 · 손가락 체인이 메시에 있는지는 계획 · 실행이 플러그인으로). fix.body 가 있으면 파지 주 손을 무기의
    lead_hand 로 맞춘다(요청이 fix.body.grip.lead_hand 를 따로 주고 다르면 CONFLICTING_FIELDS)."""
    try:
        weapon = weapon_req.normalize(raw)
    except weapon_req.WeaponError as err:
        raise _bad(err.field, err.message, reason=err.reason) from None
    body = fix.get("body")
    if weapon and body:
        given = (((raw_fix or {}).get("body") or {}) if isinstance((raw_fix or {}).get("body"), dict) else {}).get("grip") or {}
        if isinstance(given, dict) and given.get("lead_hand") not in (None, weapon["lead_hand"]):
            raise _bad("fix.body.grip.lead_hand", f"differs from weapon.lead_hand {weapon['lead_hand']} — the weapon is held by its lead hand",
                       reason="CONFLICTING_FIELDS")
        body["grip"]["lead_hand"] = weapon["lead_hand"]
    return weapon


def _num(value, low: float | None = None) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (low is None or value >= low)


def _keys(obj, allowed, field: str) -> dict:
    if not isinstance(obj, dict):
        raise _bad(field, "must be an object")
    extra = sorted(set(obj) - set(allowed))
    if extra:
        raise _bad(f"{field}.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=sorted(allowed))
    return obj


def _asset_ref(value, field: str, allowed: tuple[str, ...] = ("$asset",)) -> str:
    """애셋 경로 또는 자리표시(allowed) — 경로는 패키지 경로로."""
    if isinstance(value, str) and value in allowed:
        return value
    if not isinstance(value, str) or not value.strip().startswith("/"):
        raise _bad(field, f"must be an asset path or one of {list(allowed)}")
    return package_path(value)


def montage_name(req: dict) -> str:
    """package.montage.name 생략 = animation_name 의 AS_ → AM_ (명명 규칙 .claude/plans/anim-asset-naming.md)."""
    name = req["animation_name"]
    return "AM_" + (name[3:] if name.startswith("AS_") else name)


def _package(raw, req: dict) -> dict | None:
    """package{additive?, montage?, blendspace?} — 형식만 본다(스켈레톤 슬롯 · 샘플 존재 · 이름 충돌은 계획 단계)."""
    if raw is None:
        return None
    pkg = _keys(raw, PACKAGE_KEYS, "package")
    if not pkg:
        raise _bad("package", f"needs at least one of {list(PACKAGE_KEYS)}", reason="MISSING_FIELD")
    out: dict = {}
    if pkg.get("additive") is not None:
        add = {**ADDITIVE_DEFAULTS, **_keys(pkg["additive"], ADDITIVE_DEFAULTS, "package.additive")}
        if add["additive_type"] not in ADDITIVE_TYPES:
            raise _bad("package.additive.additive_type", f"must be one of {list(ADDITIVE_TYPES)}")
        if add["ref_pose_type"] not in REF_POSE_TYPES:
            raise _bad("package.additive.ref_pose_type", f"must be one of {list(REF_POSE_TYPES)}")
        if not _int(add["ref_frame_index"], 0, 100000):
            raise _bad("package.additive.ref_frame_index", "must be an integer ≥ 0")
        if add["ref_pose_sequence"] is not None:
            add["ref_pose_sequence"] = _asset_ref(add["ref_pose_sequence"], "package.additive.ref_pose_sequence")
        elif add["ref_pose_type"] in ("AnimScaled", "AnimFrame"):
            raise _bad("package.additive.ref_pose_sequence", f"ref_pose_type {add['ref_pose_type']} needs a base pose sequence ('$asset' = the sequence "
                       "itself) — UAnimSequence::IsValidAdditive is false without one", reason="MISSING_FIELD")
        out["additive"] = add
    names = {req["animation_name"]: "animation_name"}
    if pkg.get("montage") is not None:
        mon = {**MONTAGE_DEFAULTS, **_keys(pkg["montage"], MONTAGE_DEFAULTS, "package.montage")}
        mon["name"] = mon["name"] or montage_name(req)
        if not isinstance(mon["name"], str) or not _NAME.match(mon["name"]):
            raise _bad("package.montage.name", "must be an asset name (letters, digits, '_')")
        if not isinstance(mon["slot"], str) or not _NAME.match(mon["slot"]):
            raise _bad("package.montage.slot", "must be a slot name registered in the target skeleton (e.g. DefaultSlot, UpperBody)")
        for key in ("blend_in", "blend_out"):
            if mon[key] is not None and not _num(mon[key], 0):
                raise _bad(f"package.montage.{key}", "must be seconds ≥ 0")
        if mon["sections"] is not None:
            secs = mon["sections"]
            if not isinstance(secs, list) or not secs:
                raise _bad("package.montage.sections", "must be a non-empty list of {name, start, next?}")
            for k, s in enumerate(secs):
                _keys(s, {"name", "start", "next"}, f"package.montage.sections[{k}]")
                if not isinstance(s.get("name"), str) or not s["name"].strip() or not _num(s.get("start"), 0) \
                        or (s.get("next") is not None and not isinstance(s["next"], str)):
                    raise _bad(f"package.montage.sections[{k}]", "must be {name, start (s, ≥ 0), next? (section name; its own name = loop)}")
        if mon["name"] in names:
            raise _bad("package.montage.name", f"'{mon['name']}' is already the {names[mon['name']]}", reason="DUPLICATE_NAME")
        names[mon["name"]] = "montage name"
        out["montage"] = mon
    if pkg.get("blendspace") is not None:
        bs = {**BLENDSPACE_DEFAULTS, **_keys(pkg["blendspace"], BLENDSPACE_DEFAULTS, "package.blendspace")}
        if not isinstance(bs["name"], str) or not _NAME.match(bs["name"]):
            raise _bad("package.blendspace.name", "is required — an asset name such as BS_Vesper_Rifle_Walk1D", reason="MISSING_FIELD")
        if bs["dimensions"] not in (1, 2) or isinstance(bs["dimensions"], bool):
            raise _bad("package.blendspace.dimensions", "must be 1 or 2")
        axes = bs["axes"]
        if not isinstance(axes, list) or len(axes) != bs["dimensions"]:
            raise _bad("package.blendspace.axes", f"must list {bs['dimensions']} axis object(s) {{name, min, max, grid?, snap?, wrap?}}")
        for k, a in enumerate(axes):
            _keys(a, AXIS_KEYS, f"package.blendspace.axes[{k}]")
            if not isinstance(a.get("name"), str) or not a["name"] or not _num(a.get("min")) or not _num(a.get("max")) or a["max"] <= a["min"]:
                raise _bad(f"package.blendspace.axes[{k}]", "must be {name, min, max (> min), grid?, snap?, wrap?}")
        samples = bs["samples"]
        if not isinstance(samples, list) or not samples:
            raise _bad("package.blendspace.samples", "must be a non-empty list of {animation ('$asset' or a path), value[]}")
        for k, s in enumerate(samples):
            _keys(s, {"animation", "value"}, f"package.blendspace.samples[{k}]")
            s["animation"] = _asset_ref(s.get("animation"), f"package.blendspace.samples[{k}].animation")
            value = s.get("value")
            if not isinstance(value, list) or len(value) != bs["dimensions"] or not all(_num(v) for v in value):
                raise _bad(f"package.blendspace.samples[{k}].value", f"must be {bs['dimensions']} number(s)")
            for axis, v in zip(axes, value):
                if not axis["min"] <= v <= axis["max"]:
                    raise _bad(f"package.blendspace.samples[{k}].value", f"{v} is outside axis '{axis['name']}' [{axis['min']}, {axis['max']}]",
                               reason="OUT_OF_RANGE")
        if not isinstance(bs["aim_offset"], bool):
            raise _bad("package.blendspace.aim_offset", "must be true or false")
        if bs["name"] in names:
            raise _bad("package.blendspace.name", f"'{bs['name']}' is already the {names[bs['name']]}", reason="DUPLICATE_NAME")
        out["blendspace"] = bs
    return out


def _anim_bp(raw, integrate: bool) -> dict | None:
    """anim_bp{asset_path, operations[], scenario?, smoke} — integrate_anim_bp 가 참일 때만 읽는다(애셋만 요청하면 AnimBP 를 건드리지 않는다)."""
    if not integrate:
        if raw is not None:
            raise _bad("anim_bp", "is given but integrate_anim_bp is false — set integrate_anim_bp: true to connect, or drop anim_bp",
                       reason="CONFLICTING_FIELDS")
        return None
    if raw is None:
        raise _bad("anim_bp", "integrate_anim_bp is true but anim_bp {asset_path, operations?, scenario?, smoke?} is missing", reason="MISSING_FIELD")
    abp = {**ANIM_BP_DEFAULTS, **_keys(raw, ANIM_BP_DEFAULTS, "anim_bp")}
    if not isinstance(abp["asset_path"], str) or not abp["asset_path"].startswith("/"):
        raise _bad("anim_bp.asset_path", "is required — the Animation Blueprint to connect (anim_gen writes only a test copy)", reason="MISSING_FIELD")
    abp["asset_path"] = package_path(abp["asset_path"])
    ops = abp["operations"]
    if not isinstance(ops, list) or not all(isinstance(o, dict) and isinstance(o.get("op"), str) and o["op"] for o in ops):
        raise _bad("anim_bp.operations", "must be a list of apply_graph_operations ops {op, ...} (empty = check playback only)")
    if not isinstance(abp["smoke"], bool):
        raise _bad("anim_bp.smoke", "must be true or false")
    scn = abp["scenario"]
    if scn is not None:
        scn = _keys(scn, SCENARIO_KEYS, "anim_bp.scenario")
        if scn.get("montage") is not None:
            scn["montage"] = _asset_ref(scn["montage"], "anim_bp.scenario.montage", ("$montage",))
        if scn.get("wait_frames") is not None and not _int(scn["wait_frames"], 1, 600):
            raise _bad("anim_bp.scenario.wait_frames", "must be an integer in [1, 600]")
        if scn.get("expect") is not None:
            exp = _keys(scn["expect"], {"state_machines", "slots_active"}, "anim_bp.scenario.expect")
            if exp.get("state_machines") is not None and not isinstance(exp["state_machines"], dict):
                raise _bad("anim_bp.scenario.expect.state_machines", "must be {machine: state}")
            if exp.get("slots_active") is not None and not (isinstance(exp["slots_active"], list) and all(isinstance(s, str) for s in exp["slots_active"])):
                raise _bad("anim_bp.scenario.expect.slots_active", "must be a list of slot names")
        if scn.get("set_variables") is not None and not isinstance(scn["set_variables"], dict):
            raise _bad("anim_bp.scenario.set_variables", "must be {variable: value}")
        for key in ("mesh", "map"):
            if scn.get(key) is not None:
                scn[key] = _asset_ref(scn[key], f"anim_bp.scenario.{key}", ())
        abp["scenario"] = scn
    return abp


def placeholder_uses(obj, where: str = "") -> list[tuple[str, str]]:
    """문자열 값 전체가 '$이름' 인 곳 — (위치, 자리표시)."""
    if isinstance(obj, str):
        return [(where, obj)] if re.fullmatch(r"\$[A-Za-z_]+", obj) else []
    if isinstance(obj, dict):
        return [u for k, v in obj.items() for u in placeholder_uses(v, f"{where}.{k}" if where else k)]
    if isinstance(obj, list):
        return [u for i, v in enumerate(obj) for u in placeholder_uses(v, f"{where}[{i}]")]
    return []


def bind_placeholders(obj, bindings: dict):
    """자리표시를 실제 경로로 — 문자열 값 전체가 자리표시일 때만(부분 문자열은 그대로)."""
    if isinstance(obj, str):
        return bindings.get(obj, obj)
    if isinstance(obj, dict):
        return {k: bind_placeholders(v, bindings) for k, v in obj.items()}
    if isinstance(obj, list):
        return [bind_placeholders(v, bindings) for v in obj]
    return obj


def _check_placeholders(req: dict) -> None:
    """$montage · $blendspace 는 그 포장 단계가 있을 때만, 모르는 자리표시는 거부(오타가 조용히 문자열로 남지 않게)."""
    pkg = req["package"] or {}
    bound = {"$asset"} | ({"$montage"} if pkg.get("montage") else set()) | ({"$blendspace"} if pkg.get("blendspace") else set())
    uses = placeholder_uses(pkg, "package") + placeholder_uses(req["anim_bp"] or {}, "anim_bp")
    for where, name in uses:
        if name not in PLACEHOLDERS:
            raise _bad(where, f"unknown placeholder {name} (known: {list(PLACEHOLDERS)})", reason="UNKNOWN_PLACEHOLDER")
        if name not in bound:
            raise _bad(where, f"{name} needs package.{name[1:]} in the same request", reason="PLACEHOLDER_UNBOUND")


def final_asset_path(req: dict) -> str:
    return f"{req['output_path']}/{req['animation_name']}"


def root_motion_flag(req: dict) -> bool | None:
    return {"on": True, "off": False}.get(req["root_motion_mode"])
