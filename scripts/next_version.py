#!/usr/bin/env python3
"""Compute the next release version.

Starts at 1.0.0. Each publish increments the last digit.
When a digit would pass 9, it carries: 1.0.9 -> 1.1.0, 1.9.9 -> 2.0.0.
"""

from __future__ import annotations

import json
import subprocess
import sys


def bump(version: str) -> str:
    parts = [int(piece) for piece in version.split(".")]
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[0], parts[1], parts[2]
    patch += 1
    if patch > 9:
        patch = 0
        minor += 1
    if minor > 9:
        minor = 0
        major += 1
    return f"{major}.{minor}.{patch}"


def latest_release_tag() -> str | None:
    result = subprocess.run(
        ["gh", "release", "list", "--limit", "50", "--json", "tagName,isDraft"],
        check=True,
        capture_output=True,
        text=True,
    )
    versions: list[str] = []
    for item in json.loads(result.stdout):
        if item.get("isDraft"):
            continue
        tag = str(item.get("tagName") or "").removeprefix("v")
        pieces = tag.split(".")
        if len(pieces) == 3 and all(piece.isdigit() for piece in pieces):
            versions.append(tag)
    if not versions:
        return None
    versions.sort(key=lambda value: tuple(int(piece) for piece in value.split(".")), reverse=True)
    return versions[0]


def next_version() -> str:
    current = latest_release_tag()
    return "1.0.0" if current is None else bump(current)


def main() -> int:
    sys.stdout.write(next_version() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
