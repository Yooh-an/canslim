"""
Configuration loading helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r") as handle:
        return json.load(handle)


def load_config_file(config_path: str, profile: Optional[str] = None) -> Dict[str, Any]:
    """
    Load a configuration file with optional profile overrides.

    Supported patterns:
    - Plain JSON config file
    - JSON config file with `extends`
    - Base config + `--profile` that resolves to `config/profiles/<profile>.json`
    """
    path = Path(config_path).expanduser().resolve()
    config = _load_with_extends(path)

    if profile:
        profile_path = path.parent / "profiles" / f"{profile}.json"
        profile_config = _load_with_extends(profile_path)
        config = _deep_merge(config, profile_config)
        config["profile_name"] = profile
    else:
        config.setdefault("profile_name", config.get("profile_name", "default"))

    return config


def _load_with_extends(config_path: Path) -> Dict[str, Any]:
    config = _read_json(config_path)
    extends = config.pop("extends", None)
    if not extends:
        return config

    parent_path = (config_path.parent / extends).resolve()
    parent_config = _load_with_extends(parent_path)
    return _deep_merge(parent_config, config)
