#!/usr/bin/env python3
"""Regenerate the protocol section of ``device_flcli.py`` in place.

The block between ``# === BEGIN AUTO-GENERATED PROTOCOL ===`` and
``# === END AUTO-GENERATED PROTOCOL ===`` in
``shared/infrastructure/fl_device/device_flcli.py`` mirrors the body
of ``shared/infrastructure/protocol/_device_portable.py``.  This
script copies the latter into the former; CI runs it and refuses to
proceed if ``git diff --exit-code device_flcli.py`` is non-empty.

Run manually with::

    uv run python scripts/gen_device_protocol.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    REPO_ROOT
    / "src"
    / "flstudio_cli"
    / "shared"
    / "infrastructure"
    / "protocol"
    / "_device_portable.py"
)
TARGET = (
    REPO_ROOT
    / "src"
    / "flstudio_cli"
    / "shared"
    / "infrastructure"
    / "fl_device"
    / "device_flcli.py"
)

BEGIN_MARKER = "# === BEGIN AUTO-GENERATED PROTOCOL ==="
END_MARKER = "# === END AUTO-GENERATED PROTOCOL ==="


def _find_unique_marker(lines: list[str], marker: str, label: str) -> int:
    """Return the single index where *marker* appears, raising on drift.

    Two markers in the same file (e.g. a stale paste left behind) is
    almost certainly a bug -- partial regeneration would silently leave
    one of them unchanged.  Refuse to run instead.
    """
    matches = [i for i, line in enumerate(lines) if line.strip() == marker]
    if not matches:
        raise SystemExit(f"{label}: missing marker {marker!r}")
    if len(matches) > 1:
        raise SystemExit(
            f"{label}: marker {marker!r} appears {len(matches)} times "
            f"(at lines {[i + 1 for i in matches]}); expected exactly one"
        )
    return matches[0]


def _extract_block(text: str, label: str) -> str:
    """Return the body between BEGIN_MARKER and END_MARKER (inclusive)."""
    lines = text.splitlines()
    begin = _find_unique_marker(lines, BEGIN_MARKER, label)
    end = _find_unique_marker(lines, END_MARKER, label)
    if begin >= end:
        raise SystemExit(f"{label}: BEGIN marker at or after END marker")
    return "\n".join(lines[begin : end + 1])


def _replace_block(target_text: str, new_block: str) -> str:
    """Substitute the block between markers in *target_text* with *new_block*."""
    lines = target_text.splitlines(keepends=True)
    begin = _find_unique_marker(lines, BEGIN_MARKER, "device_flcli.py")
    end = _find_unique_marker(lines, END_MARKER, "device_flcli.py")
    if begin >= end:
        raise SystemExit("device_flcli.py: BEGIN marker at or after END marker")
    new_lines = [line + "\n" for line in new_block.splitlines()]
    return "".join(lines[:begin] + new_lines + lines[end + 1 :])


def main(argv: list[str]) -> int:
    check_only = "--check" in argv

    source_text = SOURCE.read_text(encoding="utf-8")
    block = _extract_block(source_text, str(SOURCE))

    target_text = TARGET.read_text(encoding="utf-8")
    new_target = _replace_block(target_text, block)

    if new_target == target_text:
        return 0

    if check_only:
        sys.stderr.write(
            f"{TARGET} is out of sync with {SOURCE}; "
            "run scripts/gen_device_protocol.py and commit the result.\n"
        )
        return 1

    TARGET.write_text(new_target, encoding="utf-8")
    sys.stderr.write(f"Updated {TARGET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
