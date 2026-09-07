"""Fail CI if tracked files contain live home-lab markers."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Live inventory that must never appear as a contiguous string in git.
# Split so this file does not fail its own scan.
FORBIDDEN = (
    "192.168." + "55.",
    "homevt" + "share",
    "Tim" + "Desktop25",
    "mcp" + "-01",
    "ping-network" + "infrastructure",
)


def test_tracked_files_have_no_live_lan_markers():
    listed = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        text=True,
    ).split("\0")
    tracked = [item for item in listed if item]
    hits: list[str] = []
    for rel in tracked:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN:
            if marker in text:
                hits.append(f"{rel}: {marker}")
    assert hits == [], "live home-lab markers in tracked files:\n" + "\n".join(hits)
