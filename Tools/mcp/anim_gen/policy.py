"""비용·실행 정책 (지침서 §6) — policy.default.json(추적) ← Saved/AnimGen/policy.json(로컬, 딥 머지) ← 요청 모드.

정책 파일에 두지 않는 것: 출력 경로(ini GenerationOutputPaths 가 유일한 기준)와 덮어쓰기 허용(C++ 가 항상 금지),
API 키(환경 변수만). set_generation_policy 는 이런 키를 FORBIDDEN_KEY 로 거부한다.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

from .envelope import AnimGenError, diag

DEFAULT_FILE = pathlib.Path(__file__).with_name("policy.default.json")
LOCAL_NAME = "policy.json"

FREE_ONLY = "FREE_ONLY"
FREE_FIRST = "FREE_FIRST"
QUALITY_FIRST = "QUALITY_FIRST"
MODES = (FREE_ONLY, FREE_FIRST, QUALITY_FIRST)

# 키 → 검사기. 중첩 dict 는 하위 스키마
SCHEMA = {
    "mode": ("enum", MODES),
    "billing": {
        "paid_api_enabled": ("bool",),
        "require_explicit_approval": ("const", True),  # 승인 없는 유료 호출은 금지(§16-5) — true 만 받는다
        "max_cost_per_job_usd": ("number", 0.0, None),
        "max_total_cost_usd": ("number", 0.0, None),
    },
    "execution": {
        "max_generation_attempts": ("int", 1, 10),
        "allow_fallback": ("bool",),
        "preserve_intermediate_results": ("bool",),
        "subprocess_timeout_seconds": ("number", 10, 3600),  # 로컬 서브프로세스 단계(blender · local_ai) — 넘으면 끝내고 GENERATION_FAILED TIMEOUT
    },
    "paths": {
        "blender_executable": ("str",),
        "kimodo_python": ("str",),    # local_ai(Phase 5) — Kimodo 전용 venv 의 python.exe (Tools/mcp/.venv 와 따로)
        "kimodo_hf_cache": ("str",),  # local_ai — 체크포인트 · 텍스트 인코더가 든 Hugging Face 캐시(HF_HUB_CACHE). 실행은 오프라인
    },
}
_FORBIDDEN = re.compile(r"(output|candidate_root|overwrite|api_key|apikey|token|secret|password)", re.IGNORECASE)


def _check_value(path: str, spec: tuple, value) -> None:
    kind = spec[0]
    bad = None
    if kind == "enum" and value not in spec[1]:
        bad = f"must be one of {list(spec[1])}"
    elif kind == "bool" and not isinstance(value, bool):
        bad = "must be true or false"
    elif kind == "const" and value != spec[1]:
        raise AnimGenError("BAD_REQUEST", f"'{path}' can only be {json.dumps(spec[1])}", reason="FORBIDDEN_VALUE", key=path)
    elif kind == "str" and not isinstance(value, str):
        bad = "must be a string"
    elif kind in ("number", "int"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind == "int" and not isinstance(value, int)):
            bad = f"must be {'an integer' if kind == 'int' else 'a number'}"
        elif (spec[1] is not None and value < spec[1]) or (spec[2] is not None and value > spec[2]):
            bad = f"must be in [{spec[1]}, {spec[2] if spec[2] is not None else '∞'}]"
    if bad:
        raise AnimGenError("BAD_REQUEST", f"'{path}' {bad}", reason="BAD_VALUE", key=path, value=value)


def validate(data: dict, schema: dict = SCHEMA, prefix: str = "") -> None:
    """모르는 키 · 금지 키 · 잘못된 값 → BAD_REQUEST (부분 패치도 같은 검사)."""
    if not isinstance(data, dict):
        raise AnimGenError("BAD_REQUEST", f"'{prefix or 'policy'}' must be an object", reason="BAD_VALUE")
    for key, value in data.items():
        path = f"{prefix}{key}"
        if _FORBIDDEN.search(key):
            raise AnimGenError("BAD_REQUEST", f"'{path}' cannot be set in the generation policy — output paths come only from the "
                               "[AnimGraphMcp] ini (get_editor_status.generation), overwriting is always off, API keys come only from "
                               "environment variables", reason="FORBIDDEN_KEY", key=path)
        if key not in schema:
            raise AnimGenError("BAD_REQUEST", f"Unknown policy key '{path}'", reason="UNKNOWN_KEY", key=path,
                               allowed=sorted(schema.keys()))
        spec = schema[key]
        if isinstance(spec, dict):
            validate(value, spec, prefix=f"{path}.")
        else:
            _check_value(path, spec, value)


def deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_default() -> dict:
    data = json.loads(DEFAULT_FILE.read_text(encoding="utf-8"))
    validate(data)
    return data


def local_path(state_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(state_dir) / LOCAL_NAME


def load_local(state_dir: pathlib.Path) -> dict:
    path = local_path(state_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def effective(state_dir: pathlib.Path) -> dict:
    return deep_merge(load_default(), load_local(state_dir))


def set_local(state_dir: pathlib.Path, patch: dict | None, reset: bool = False) -> dict:
    """로컬 덮어쓰기 파일만 쓴다. reset 이면 로컬 값을 비우고 patch 를 적용한다."""
    patch = patch or {}
    validate(patch)
    local = {} if reset else load_local(state_dir)
    merged_local = deep_merge(local, patch)
    validate(deep_merge(load_default(), merged_local))
    path = local_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged_local, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return effective(state_dir)


def resolve_mode(policy: dict, requested: str | None) -> tuple[str, list[dict]]:
    """요청 단위 모드. 정책이 FREE_ONLY 면 벗어날 수 없다(POLICY_CLAMPED)."""
    mode = policy["mode"]
    if not requested or requested == mode:
        return mode, []
    if requested not in MODES:
        raise AnimGenError("BAD_REQUEST", f"generation_policy must be one of {list(MODES)}", reason="BAD_VALUE", value=requested)
    if mode == FREE_ONLY:
        return FREE_ONLY, [diag("warning", "POLICY_CLAMPED", f"Policy mode is FREE_ONLY; the request's {requested} is ignored")]
    return requested, []


def paid_block_reason(policy: dict, mode: str) -> str | None:
    """유료 Provider 를 쓸 수 없는 이유(없으면 None)."""
    if mode == FREE_ONLY:
        return "POLICY_FREE_ONLY"
    if not policy["billing"]["paid_api_enabled"]:
        return "PAID_API_DISABLED"
    return None
