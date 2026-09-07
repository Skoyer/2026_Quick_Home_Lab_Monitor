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
PUBLIC_OBFUSCATE = PUBLIC_DIR / "obfuscate.example.yaml"
PUBLIC_ARCH = PUBLIC_DIR / "docs" / "home-lab-architecture.example.md"

EXAMPLE_IP_MAP = """# Example mapping schema. Real mappings stay in private/ip_map.yaml.
# The left side is a stand-in for a private LAN, not a real host in this repo.
replacements:
  "192.168.1.10": "10.42.0.10"
  "192.168.1.20": "10.42.0.20"
  "192.168.1.30": "10.42.0.30"
  "192.168.1.40": "10.42.0.40"
  "192.168.1.": "10.42.0."
"""

EXAMPLE_OBFUSCATE = """# Example extra replacements for screenshot Obfuscate mode.
# Copy to private/obfuscate.yaml and add real share names / hostnames / usernames.
# RFC1918 IPv4 addresses are rewritten automatically:
#   192.168.a.b → 192.x.y.b  (last octet kept so hosts stay distinct in screenshots)
#   10.a.b.c    → 10.x.y.c
#   172.16–31   → 172.x.y.<last>
# Do not put live inventory here. Screenshot mode does not use the 10.42.0.x GitHub map.
replacements:
  labshare: shared
  workstation-01: workstation
  mcp-01: kuma-host
  example-user: user
lan_prefixes:
  - "192.168.1."
"""

EXAMPLE_ARCH = """# Example home lab architecture (public)

This is a fictitious example for the GitHub repository. Real addresses,
passwords, and inventory live only in the local `private/` folder.

## Example LAN

- Network: `10.42.0.0/24`
- Monitoring dashboard: workstation bound to all interfaces (`0.0.0.0:8000`); LAN clients use `http://10.42.0.10:8000`

## Example services

| Service | Example address | Health check |
| --- | --- | --- |
| LM Studio | `http://10.42.0.10:1234` | `GET /v1/models` |
| Ollama | `http://10.42.0.20:11434` | `GET /api/version` |
| Uptime Kuma (mcp-01) | `http://10.42.0.40:3001` | Public status page `ping-networkinfrastructure` (heartbeat JSON), then LM Studio summary |
| NAS files | `Z:` → `\\\\10.42.0.30\\shared` | Mapped drive listing |

## Uptime Kuma (also in this lab)

The example lab also runs Uptime Kuma on **mcp-01** with embedded
MariaDB. This dashboard does not clone Kuma's heartbeat UI. It ingests
structured Kuma status from the published status page
`http://10.42.0.40:3001/status/ping-networkinfrastructure` (slug
`ping-networkinfrastructure` is not an IP) and optionally asks LM Studio
to summarize it. Prometheus `/metrics` is not required. ICMP (gateway,
Orbi Main, Orbi satellites), history, Critical tags, retries, and
notifications stay in Kuma. See `docs/COMPARE_TO_UPTIME_KUMA.md`.

## Internet reachability

The dashboard probes a few public HTTPS endpoints and treats the check
as healthy when a configured majority succeed.

## NAS files

The example share is a mapped `Z:` drive on `\\\\10.42.0.30\\shared`.
The dashboard lists that drive; it does not store NAS credentials.
Reconnect the share with your existing PowerShell/login script if the
drive is missing.
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
    write_text(PUBLIC_OBFUSCATE, EXAMPLE_OBFUSCATE)
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
    print(f"Wrote {PUBLIC_OBFUSCATE.relative_to(ROOT)}")
    print(f"Wrote {PUBLIC_ARCH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
