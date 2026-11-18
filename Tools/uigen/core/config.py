"""설정 로더 — config/*.yaml · profiles/*.yaml (설계 §3-2).

저장소 안 경로는 저장소 루트 기준 상대로 적고 repo_path() 로 푼다. 엔진 · 사용자 도구 경로는 절대 경로 그대로.
"""
from __future__ import annotations

import pathlib

import yaml

UIGEN_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = UIGEN_DIR.parents[1]
CONFIG_DIR = UIGEN_DIR / "config"
PROFILE_DIR = UIGEN_DIR / "profiles"


class ConfigError(Exception):
    pass


def load_yaml(path: str | pathlib.Path) -> dict:
    path = pathlib.Path(path)
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def repo_path(value: str | pathlib.Path) -> pathlib.Path:
    """저장소 기준 상대 → 절대. 이미 절대면 그대로."""
    p = pathlib.Path(value)
    return p if p.is_absolute() else REPO_ROOT / p


def load_pipeline(path: str | pathlib.Path | None = None) -> dict:
    cfg = load_yaml(path or CONFIG_DIR / "pipeline.yaml")
    for key in ("paths", "limits", "backends", "textures"):
        if not isinstance(cfg.get(key), dict):
            raise ConfigError(f"pipeline.yaml: '{key}' section is missing")
    return cfg


def load_screens(path: str | pathlib.Path | None = None) -> dict:
    data = load_yaml(path or CONFIG_DIR / "screens.yaml")
    screens = data.get("screens")
    if not isinstance(screens, dict):
        raise ConfigError("screens.yaml: 'screens' mapping is missing")
    return screens


def load_routing(path: str | pathlib.Path | None = None) -> dict:
    data = load_yaml(path or CONFIG_DIR / "routing.yaml")
    if not isinstance(data.get("kinds"), dict):
        raise ConfigError("routing.yaml: 'kinds' mapping is missing")
    return data


def load_profile(name: str, root: str | pathlib.Path | None = None) -> dict:
    path = pathlib.Path(root or PROFILE_DIR) / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"no screen profile '{name}' ({path})")
    data = load_yaml(path)
    if not isinstance(data.get("gates"), dict):
        raise ConfigError(f"{path}: 'gates' mapping is missing")
    return data


def font_roles(cfg: dict, body_family: str | None = None) -> dict[str, dict]:
    """글자 역할 → {family, line_height[, glyph_height, sdf_family]} (1b 후속 D · F). body = 요청 폰트(brief.font) 또는 fonts.default_family
    + fonts.line_height(+ fonts.glyph_height · sdf_family, 또는 fonts.roles.body.sdf_family — 기본 폰트일 때만),
    나머지 = fonts.roles.<역할>{family, line_height, glyph_height?, sdf_family?}.
    family 가 없는 역할은 빠진다(폰트를 아직 임포트하지 않음). glyph_height = 보이는 글자 높이 / 크기(한글 · 숫자 — 실측),
    sdf_family = 같은 폰트의 거리장(SDF) 사본 — 글자 빛(font.glow)을 쓰는 글자만 이것으로 바꾼다."""
    fonts = cfg.get("fonts") or {}
    out: dict[str, dict] = {}

    def entry(family, src: dict) -> dict:
        e = {"family": family, "line_height": dict(src.get("line_height") or {})}
        for k in ("glyph_height", "sdf_family", "weight_density", "typefaces"):     # 1b 후속 K — 굵기 변형 · 굵기별 획 밀도(가장 가까운 굵기)
            if src.get(k):
                e[k] = dict(src[k]) if isinstance(src[k], dict) else (list(src[k]) if isinstance(src[k], list) else src[k])
        return e

    body = body_family or fonts.get("default_family")
    if body:
        default_body = not body_family or body_family == fonts.get("default_family")
        out["body"] = entry(body, fonts if default_body else {"line_height": fonts.get("line_height")})
        rb = (fonts.get("roles") or {}).get("body")
        if default_body and isinstance(rb, dict) and rb.get("sdf_family"):      # 1b 후속 J — fonts.roles.body.sdf_family(Pretendard SDF 사본)
            out["body"]["sdf_family"] = rb["sdf_family"]
    for role, r in (fonts.get("roles") or {}).items():
        if role != "body" and isinstance(r, dict) and r.get("family"):
            out[role] = entry(r["family"], r)
    return out


def line_height_text(table: dict, sep: str = "→") -> str:
    return ", ".join(f"{k}{sep}{v}" for k, v in sorted((int(k), v) for k, v in (table or {}).items()))


def compression_for(asset: dict, cfg: dict) -> str:
    """spec 에셋의 compression → 종류별 기본(pipeline.yaml textures.compression_by_kind) → 전체 기본."""
    textures = cfg["textures"]
    return asset.get("compression") or (textures.get("compression_by_kind") or {}).get(asset.get("kind")) or textures["compression_default"]
