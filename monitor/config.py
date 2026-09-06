from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DIR = ROOT / "private"
PUBLIC_DIR = ROOT / "public"
SERVICES_PRIVATE = PRIVATE_DIR / "services.yaml"
SERVICES_PUBLIC = PUBLIC_DIR / "services.example.yaml"
IP_MAP_PRIVATE = PRIVATE_DIR / "ip_map.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def services_config_path() -> Path:
    if SERVICES_PRIVATE.exists():
        return SERVICES_PRIVATE
    if SERVICES_PUBLIC.exists():
        return SERVICES_PUBLIC
    raise FileNotFoundError(
        "No services config found. Copy public/services.example.yaml "
        "to private/services.yaml and edit it."
    )


def load_services_config() -> dict[str, Any]:
    return load_yaml(services_config_path())


def load_ip_map() -> dict[str, str]:
    if not IP_MAP_PRIVATE.exists():
        return {}
    data = load_yaml(IP_MAP_PRIVATE)
    replacements = data.get("replacements") or {}
    return {str(key): str(value) for key, value in replacements.items()}
