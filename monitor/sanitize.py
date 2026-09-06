from __future__ import annotations


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Replace real values with fictitious ones. Longer keys win."""
    result = text
    for key in sorted(replacements, key=len, reverse=True):
        result = result.replace(key, replacements[key])
    return result


def leftover_real_values(text: str, replacements: dict[str, str]) -> list[str]:
    """Return real keys that still appear after masking."""
    masked = apply_replacements(text, replacements)
    return [key for key in replacements if key in masked]
