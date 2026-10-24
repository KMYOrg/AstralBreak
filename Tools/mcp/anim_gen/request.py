"""생성 요청 정규화·검증 (지침서 §9, 개정 6). 자연어 해석은 Claude Code 가 하고 여기는 구조화된 요청만 받는다."""
from __future__ import annotations

import copy
import os
import re

from . import bvh
from .editor import package_path
from .envelope import AnimGenError, diag

CATEGORIES = ("idle", "locomotion", "weapon_action", "full_body_new")
ROOT_MOTION_MODES = ("auto", "on", "off")
REQUIRED = ("target_skeleton", "animation_name", "output_path", "motion_category")
SEARCH_KEYS = {"query", "path_prefix", "asset_class", "min_length", "max_length", "root_motion", "additive", "loop", "tags", "limit"}
RETARGET_KEYS = {"source_mesh", "existing_source_rig", "existing_target_rig", "existing_retargeter", "source_pelvis", "source_chains", "ops",
                 "source_facing", "align_mode"}
# create_ik_retargeter align_mode — per_bone: 뼈 수 같은 체인 FK 1:1 + 본 대 본 · 체인 끝 정렬(엔진 정렬은 같은 param 끼리 짝지어
# 관절 비율이 다르면 팔꿈치 굽힘이 덜 전달된다). match_existing 의 기본, default ops 는 정렬하지 않아 engine 만
ALIGN_MODES = ("per_bone", "engine")
# Phase 4 — blender Provider 가 변환할 모션 파일
MOTION_FILE_DEFAULTS = {"path": None, "unit": "auto", "facing": "auto", "range": None, "axis_forward": "-Z", "axis_up": "Y"}
FACINGS = ("auto", "keep", "+X", "-X", "+Y", "-Y")
# Phase 5 — AI 생성 Provider(local_ai) 설정. prompt 는 모델이 읽는 영어 문장(description 은 기록만)
GENERATION_DEFAULTS = {"seed": None, "samples": 1, "steps": 100, "postprocess": "auto", "pick": 0, "constraints": []}
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
DEFAULTS = {
    "target_mesh": None, "hero": None, "family": None, "description": "", "duration_seconds": None, "frame_rate": None,
    "loop": None, "root_motion_mode": "auto", "reference_animations": [], "search": None, "edits": None, "retarget": {},
    "constraints": {}, "generation_policy": None, "provider": "auto", "integrate_anim_bp": False, "motion_file": None,
    "prompt": None, "generation": None, "review": None, "fix": None,
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

    if not isinstance(req["constraints"], dict):
        raise _bad("constraints", "must be an object of flags")
    if not isinstance(req["provider"], str) or not req["provider"]:
        raise _bad("provider", "must be 'auto' or a provider name")

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


def _review(raw) -> dict | None:
    """review{render{times[] | count, views[], reference_images[]}} — 형식만 본다(시각 범위 · 이미지 루트 · 존재는 blender 계획)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"render"} or not isinstance(raw["render"], dict):
        raise _bad("review", "must be {render{times[] | count, views?, reference_images?}}")
    render = raw["render"]
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
    return {"render": render}


def _fix(raw) -> dict:
    """fix{ops[{op, ...}]} — blender 변환 단계의 보정 op. 형식만 본다 — 지원 여부는 blender 계획(op 사전, Phase 5 는 비어 있다)."""
    fix = {} if raw is None else raw
    if not isinstance(fix, dict):
        raise _bad("fix", "must be {ops[]}")
    extra = sorted(set(fix) - {"ops"})
    if extra:
        raise _bad(f"fix.{extra[0]}", f"unknown key(s) {extra}", reason="UNKNOWN_FIELD", allowed=["ops"])
    ops = fix.get("ops", [])
    if not isinstance(ops, list) or not all(isinstance(o, dict) and isinstance(o.get("op"), str) and o["op"] for o in ops):
        raise _bad("fix.ops", "must be a list of {op, ...}")
    return {"ops": ops}


def final_asset_path(req: dict) -> str:
    return f"{req['output_path']}/{req['animation_name']}"


def root_motion_flag(req: dict) -> bool | None:
    return {"on": True, "off": False}.get(req["root_motion_mode"])
