"""Probe configured services using the private (or example) map."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monitor.checks import run_all_checks  # noqa: E402
from monitor.config import services_config_path  # noqa: E402


async def main() -> int:
    print(f"Using {services_config_path()}")
    payload = await run_all_checks()
    print(json.dumps(payload, indent=2))
    failed = [check["id"] for check in payload["checks"] if check["state"] == "down"]
    if failed:
        print(f"DOWN: {', '.join(failed)}")
        return 1
    print("All configured checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
