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
                 "source_facing"}
# Phase 4 — blender Provider 가 변환할 모션 파일
MOTION_FILE_DEFAULTS = {"path": None, "unit": "auto", "facing": "auto", "range": None, "axis_forward": "-Z", "axis_up": "Y"}
FACINGS = ("auto", "keep", "+X", "-X", "+Y", "-Y")
# 후처리로 다루는 제약 → 한계 코드. 그 밖의 참 제약은 CONSTRAINT_UNSUPPORTED
CONSTRAINT_LIMITATIONS = {"two_hand_weapon_grip": "GRIP_NOT_VALIDATED", "foot_contact": "FOOT_CONTACT_NOT_ENFORCED"}
DEFAULTS = {
    "target_mesh": None, "hero": None, "family": None, "description": "", "duration_seconds": None, "frame_rate": None,
    "loop": None, "root_motion_mode": "auto", "reference_animations": [], "search": None, "edits": None, "retarget": {},
    "constraints": {}, "generation_policy": None, "provider": "auto", "integrate_anim_bp": False, "motion_file": None,
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
    # 소스가 보는 UE 축 — auto 면 소스 스켈레톤 기준 포즈로 잰다, keep 이면 정면을 맞추지 않는다
    if retarget.get("source_facing", "auto") not in FACINGS:
        raise _bad("retarget.source_facing", f"must be one of {list(FACINGS)} (UE axes the source faces)")
    for key in ("source_mesh", "existing_source_rig", "existing_target_rig", "existing_retargeter"):
        if retarget.get(key):
            retarget[key] = package_path(retarget[key])
    req["retarget"] = retarget

    req["motion_file"] = _motion_file(req["motion_file"])

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


def final_asset_path(req: dict) -> str:
    return f"{req['output_path']}/{req['animation_name']}"


def root_motion_flag(req: dict) -> bool | None:
    return {"on": True, "off": False}.get(req["root_motion_mode"])
