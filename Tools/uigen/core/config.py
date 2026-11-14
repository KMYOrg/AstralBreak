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


def compression_for(asset: dict, cfg: dict) -> str:
    """spec 에셋의 compression → 종류별 기본(pipeline.yaml textures.compression_by_kind) → 전체 기본."""
    textures = cfg["textures"]
    return asset.get("compression") or (textures.get("compression_by_kind") or {}).get(asset.get("kind")) or textures["compression_default"]
