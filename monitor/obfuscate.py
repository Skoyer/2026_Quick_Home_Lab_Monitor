"""Screenshot-mode sanitizer: mask LAN details as 192.x.y.z (not the public 10.42.0.x map)."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from monitor.config import load_ip_map, load_obfuscate_config
from monitor.sanitize import apply_replacements

IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
UNC_RE = re.compile(r"\\\\([^\\\s]+)\\([^\\/\s.,;:]+)")
SMB_RE = re.compile(r"(?i)smb://([^/\s]+)/([^/\s.,;:?]+)")
USERINFO_RE = re.compile(
    r"(?i)\b(user(?:name)?|login|account)\s*[:=]\s*([^\s,;\"']+)"
)
USER_AT_HOST_RE = re.compile(
    r"\b([A-Za-z0-9._-]{1,64})@(?=(?:\d{1,3}(?:\.\d{1,3}){3}|192\.x\.y\.|10\.x\.y\.|172\.x\.y\.))"
)
IP_LIKE_KEY_RE = re.compile(r"^\d+(?:\.\d+){0,3}\.?$")
GENERIC_SHARES = {"share", "shared"}

# Screenshot placeholders keep last-octet identity without revealing the LAN.
PLACEHOLDER_192 = "192.x.y."
PLACEHOLDER_10 = "10.x.y."
PLACEHOLDER_172 = "172.x.y."


def _is_ip_like_key(key: str) -> bool:
    return bool(IP_LIKE_KEY_RE.fullmatch(key.strip()))


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def request_wants_obfuscate(
    obfuscate: bool = False,
    header_value: str | None = None,
) -> bool:
    return bool(obfuscate) or _truthy(header_value)


def load_obfuscate_extras() -> dict[str, str]:
    """Share names, hostnames, and usernames from private maps (never IP keys)."""
    extras: dict[str, str] = {}
    for key, value in load_ip_map().items():
        if key and not _is_ip_like_key(key):
            extras[str(key)] = str(value)
    config = load_obfuscate_config()
    for key, value in (config.get("replacements") or {}).items():
        if key:
            extras[str(key)] = str(value)
    return extras


def load_lan_prefixes() -> list[str]:
    prefixes: list[str] = []
    config = load_obfuscate_config()
    for item in config.get("lan_prefixes") or []:
        text = str(item).strip()
        if text:
            prefixes.append(text if text.endswith(".") else f"{text}.")
    for key in load_ip_map():
        parts = str(key).strip().rstrip(".").split(".")
        if len(parts) >= 3 and parts[0] == "192" and parts[1] == "168":
            prefixes.append(".".join(parts[:3]) + ".")
        elif len(parts) >= 3 and parts[0] == "10":
            prefixes.append(".".join(parts[:3]) + ".")
        elif (
            len(parts) >= 3
            and parts[0] == "172"
            and parts[1].isdigit()
            and 16 <= int(parts[1]) <= 31
        ):
            prefixes.append(".".join(parts[:3]) + ".")
    unique: list[str] = []
    seen: set[str] = set()
    for prefix in prefixes:
        if prefix not in seen:
            seen.add(prefix)
            unique.append(prefix)
    return unique


def _thirds_from_prefixes(lan_prefixes: list[str]) -> set[str]:
    """Only 192.168 third octets become parenthesized name hints (a.b) → (x.y.b)."""
    thirds: set[str] = set()
    for prefix in lan_prefixes:
        parts = prefix.rstrip(".").split(".")
        if len(parts) >= 3 and parts[0] == "192" and parts[1] == "168":
            thirds.add(parts[2])
    return thirds


def collect_lan_thirds(payload: Any, lan_prefixes: list[str] | None = None) -> set[str]:
    thirds = _thirds_from_prefixes(lan_prefixes or [])
    blob = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    for match in IPV4_RE.finditer(blob):
        try:
            addr = ipaddress.IPv4Address(match.group(1))
        except ipaddress.AddressValueError:
            continue
        if addr in ipaddress.IPv4Network("192.168.0.0/16"):
            thirds.add(str(addr).split(".")[2])
    return thirds


def _rewrite_lan_hints(text: str, lan_thirds: set[str]) -> str:
    result = text
    for third in sorted(lan_thirds, key=len, reverse=True):
        if not third.isdigit():
            continue
        paren = re.compile(rf"\({re.escape(third)}\.(\d{{1,3}})\)")
        result = paren.sub(r"(x.y.\1)", result)
        if third in {"0", "1"}:
            continue
        bare = re.compile(rf"(?<![\d.xy]){re.escape(third)}\.(\d{{1,3}})(?![\d.])")
        result = bare.sub(r"x.y.\1", result)
    return result


def _rewrite_private_ip(match: re.Match[str]) -> str:
    raw = match.group(1)
    try:
        addr = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError:
        return raw
    if not addr.is_private:
        return raw
    last = str(addr).rsplit(".", 1)[-1]
    if addr in ipaddress.IPv4Network("10.0.0.0/8"):
        return f"{PLACEHOLDER_10}{last}"
    if addr in ipaddress.IPv4Network("172.16.0.0/12"):
        return f"{PLACEHOLDER_172}{last}"
    return f"{PLACEHOLDER_192}{last}"


def _mask_unc(match: re.Match[str]) -> str:
    host, share = match.group(1), match.group(2)
    if share.lower() not in GENERIC_SHARES:
        share = "share"
    return f"\\\\{host}\\{share}"


def _mask_smb(match: re.Match[str]) -> str:
    host, share = match.group(1), match.group(2)
    if share.lower() not in GENERIC_SHARES:
        share = "share"
    return f"smb://{host}/{share}"


def obfuscate_text(
    text: str,
    *,
    extras: dict[str, str] | None = None,
    lan_thirds: set[str] | None = None,
    lan_prefixes: list[str] | None = None,
) -> str:
    """Rewrite one string for screenshots. Extra keys (share/host/user) win first."""
    result = apply_replacements(text, extras or {})
    result = IPV4_RE.sub(_rewrite_private_ip, result)
    for prefix in sorted(lan_prefixes or [], key=len, reverse=True):
        if re.fullmatch(r"\d+\.\d+\.\d+\.", prefix):
            if prefix.startswith("10."):
                result = result.replace(prefix, PLACEHOLDER_10)
            elif prefix.startswith("172."):
                result = result.replace(prefix, PLACEHOLDER_172)
            else:
                result = result.replace(prefix, PLACEHOLDER_192)
    result = _rewrite_lan_hints(result, lan_thirds or set())
    result = UNC_RE.sub(_mask_unc, result)
    result = SMB_RE.sub(_mask_smb, result)
    result = USERINFO_RE.sub(lambda m: f"{m.group(1)}=user", result)
    result = USER_AT_HOST_RE.sub("user@", result)
    return result


def obfuscate_value(
    value: Any,
    *,
    extras: dict[str, str],
    lan_thirds: set[str],
    lan_prefixes: list[str],
) -> Any:
    if isinstance(value, str):
        return obfuscate_text(
            value,
            extras=extras,
            lan_thirds=lan_thirds,
            lan_prefixes=lan_prefixes,
        )
    if isinstance(value, list):
        return [
            obfuscate_value(
                item,
                extras=extras,
                lan_thirds=lan_thirds,
                lan_prefixes=lan_prefixes,
            )
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: obfuscate_value(
                item,
                extras=extras,
                lan_thirds=lan_thirds,
                lan_prefixes=lan_prefixes,
            )
            for key, item in value.items()
        }
    return value


def obfuscate_payload(
    payload: Any,
    *,
    extras: dict[str, str] | None = None,
    lan_prefixes: list[str] | None = None,
) -> Any:
    extras = extras if extras is not None else load_obfuscate_extras()
    prefixes = lan_prefixes if lan_prefixes is not None else load_lan_prefixes()
    thirds = collect_lan_thirds(payload, prefixes)
    result = obfuscate_value(
        payload,
        extras=extras,
        lan_thirds=thirds,
        lan_prefixes=prefixes,
    )
    if isinstance(result, dict):
        result["obfuscated"] = True
    return result
