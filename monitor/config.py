from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DIR = ROOT / "private"
PUBLIC_DIR = ROOT / "public"
SERVICES_PRIVATE = PRIVATE_DIR / "services.yaml"
SERVICES_PUBLIC = PUBLIC_DIR / "services.example.yaml"
IP_MAP_PRIVATE = PRIVATE_DIR / "ip_map.yaml"
OBFUSCATE_PRIVATE = PRIVATE_DIR / "obfuscate.yaml"
OBFUSCATE_PUBLIC = PUBLIC_DIR / "obfuscate.example.yaml"
SECRETS_PRIVATE = PRIVATE_DIR / "secrets.env"

SECRET_KEYS = (
    "KUMA_API_KEY",
    "KUMA_USERNAME",
    "KUMA_PASSWORD",
    "KUMA_COOKIE",
)


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


def load_obfuscate_config() -> dict[str, Any]:
    """Screenshot extras. Live file is private; public example is never used live."""
    if not OBFUSCATE_PRIVATE.exists():
        return {}
    return load_yaml(OBFUSCATE_PRIVATE)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _, raw = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return key, value


def load_secrets() -> dict[str, str]:
    """Load private/secrets.env plus matching process environment overrides."""
    values: dict[str, str] = {}
    if SECRETS_PRIVATE.exists():
        for line in SECRETS_PRIVATE.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if parsed and parsed[1]:
                values[parsed[0]] = parsed[1]
    for key in SECRET_KEYS:
        env = os.environ.get(key)
        if env:
            values[key] = env
    return values
