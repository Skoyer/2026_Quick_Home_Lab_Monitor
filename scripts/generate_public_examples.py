"""Create sanitized public examples from private configs and docs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monitor.config import (  # noqa: E402
    IP_MAP_PRIVATE,
    PRIVATE_DIR,
    PUBLIC_DIR,
    SERVICES_PRIVATE,
    load_ip_map,
)
from monitor.sanitize import apply_replacements, leftover_real_values  # noqa: E402

PUBLIC_SERVICES = PUBLIC_DIR / "services.example.yaml"
PUBLIC_IP_MAP = PUBLIC_DIR / "ip_map.example.yaml"
PUBLIC_ARCH = PUBLIC_DIR / "docs" / "home-lab-architecture.example.md"

EXAMPLE_IP_MAP = """# Example mapping schema. Real mappings stay in private/ip_map.yaml.
# The left side is a stand-in for a private LAN, not a real host in this repo.
replacements:
  "192.168.1.10": "10.42.0.10"
  "192.168.1.20": "10.42.0.20"
  "192.168.1.": "10.42.0."
"""

EXAMPLE_ARCH = """# Example home lab architecture (public)

This is a fictitious example for the GitHub repository. Real addresses,
passwords, and inventory live only in the local `private/` folder.

## Example LAN

- Network: `10.42.0.0/24`
- Monitoring dashboard: workstation bound to `127.0.0.1:8080`

## Example services

| Service | Example address | Health check |
| --- | --- | --- |
| LM Studio | `http://10.42.0.10:1234` | `GET /v1/models` |
| Ollama | `http://10.42.0.20:11434` | `GET /api/version` |

## Internet reachability

The dashboard probes a few public HTTPS endpoints and treats the check
as healthy when a configured majority succeed.
"""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    replacements = load_ip_map()
    if not replacements:
        raise SystemExit(f"Missing mapping file: {IP_MAP_PRIVATE}")
    if not SERVICES_PRIVATE.exists():
        raise SystemExit(f"Missing private services file: {SERVICES_PRIVATE}")

    raw_services = SERVICES_PRIVATE.read_text(encoding="utf-8")
    body = raw_services.split("\n\n", 1)[-1] if "\n\n" in raw_services else raw_services
    masked_services = apply_replacements(
        "# Example service map for the public repository.\n"
        "# Hosts below are fictitious. Copy this file to private/services.yaml\n"
        "# and replace example hosts with your real LAN values.\n\n"
        + body,
        replacements,
    )
    leftovers = leftover_real_values(masked_services, replacements)
    if leftovers:
        raise SystemExit(f"Refusing to write public example; leftover real values: {leftovers}")

    write_text(PUBLIC_SERVICES, masked_services)
    write_text(PUBLIC_IP_MAP, EXAMPLE_IP_MAP)
    write_text(PUBLIC_ARCH, EXAMPLE_ARCH)

    private_docs = PRIVATE_DIR / "docs"
    if private_docs.exists():
        for src in private_docs.glob("*.md"):
            masked = apply_replacements(src.read_text(encoding="utf-8"), replacements)
            leftover = leftover_real_values(masked, replacements)
            if leftover:
                raise SystemExit(f"{src.name} still contains real values: {leftover}")

    print(f"Wrote {PUBLIC_SERVICES.relative_to(ROOT)}")
    print(f"Wrote {PUBLIC_IP_MAP.relative_to(ROOT)}")
    print(f"Wrote {PUBLIC_ARCH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
