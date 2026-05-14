"""Tests for the device-protocol codegen.

The body of ``shared/infrastructure/protocol/_device_portable.py``
between the BEGIN / END markers is the canonical source for the
protocol section that ``device_flcli.py`` carries.
``scripts/gen_device_protocol.py`` keeps the two in sync; CI runs the
``--check`` flag and refuses to merge a drifted device script.

These tests pin the codegen contract directly so a regression in the
script (broken marker matching, accidental rename) shows up at
pytest time, before CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gen_device_protocol.py"


@pytest.fixture(scope="module")
def gen_module():
    """Load ``scripts/gen_device_protocol.py`` as an importable module."""
    spec = importlib.util.spec_from_file_location("gen_device_protocol", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_device_protocol"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("gen_device_protocol", None)


class TestDeviceProtocolCodegen:
    def test_check_mode_passes_on_unchanged_repo(self, gen_module):
        # If anyone hand-edits the device protocol section the lint job
        # will catch it; pytest also catches it here so contributors
        # see the failure without pushing.
        exit_code = gen_module.main(["--check"])
        assert exit_code == 0, (
            "device_flcli.py protocol section has drifted from "
            "_device_portable.py; run scripts/gen_device_protocol.py "
            "and commit."
        )

    def test_replace_block_substitutes_between_markers(self, gen_module):
        target = (
            "head\n"
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "old line 1\n"
            "old line 2\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n"
            "tail\n"
        )
        new_block = (
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "fresh\n"
            "# === END AUTO-GENERATED PROTOCOL ==="
        )

        result = gen_module._replace_block(target, new_block)

        assert result == (
            "head\n"
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "fresh\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n"
            "tail\n"
        )

    def test_extract_block_returns_marker_inclusive_section(self, gen_module):
        source = (
            "doc\n"
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "body\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n"
            "trailer\n"
        )

        block = gen_module._extract_block(source, "fixture")

        assert block.splitlines() == [
            "# === BEGIN AUTO-GENERATED PROTOCOL ===",
            "body",
            "# === END AUTO-GENERATED PROTOCOL ===",
        ]

    def test_extract_block_raises_on_missing_marker(self, gen_module):
        with pytest.raises(SystemExit, match="missing marker"):
            gen_module._extract_block("no markers here\n", "fixture")

    def test_extract_block_raises_on_inverted_markers(self, gen_module):
        with pytest.raises(SystemExit, match="BEGIN marker at or after"):
            gen_module._extract_block(
                "# === END AUTO-GENERATED PROTOCOL ===\n"
                "# === BEGIN AUTO-GENERATED PROTOCOL ===\n",
                "fixture",
            )

    def test_replace_block_raises_on_duplicate_markers(self, gen_module):
        # Two BEGIN markers means a stale paste was left behind; the
        # codegen would silently leave one of them unchanged.
        target = (
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n"
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n"
        )
        new_block = (
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "fresh\n"
            "# === END AUTO-GENERATED PROTOCOL ==="
        )

        with pytest.raises(SystemExit, match="appears 2 times"):
            gen_module._replace_block(target, new_block)

    def test_main_writes_target_file_when_drifted(
        self, gen_module, tmp_path, monkeypatch
    ):
        # Write mode round-trip: create a target with a stale block,
        # run main(), and verify the block was rewritten.
        source = tmp_path / "_src.py"
        source.write_text(
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "fresh body\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n",
            encoding="utf-8",
        )
        target = tmp_path / "_tgt.py"
        target.write_text(
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "stale body\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(gen_module, "SOURCE", source)
        monkeypatch.setattr(gen_module, "TARGET", target)

        assert gen_module.main([]) == 0
        assert "fresh body" in target.read_text(encoding="utf-8")
        assert "stale body" not in target.read_text(encoding="utf-8")

    def test_main_check_mode_returns_nonzero_on_drift(
        self, gen_module, tmp_path, monkeypatch, capsys
    ):
        source = tmp_path / "_src.py"
        source.write_text(
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "fresh\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n",
            encoding="utf-8",
        )
        target = tmp_path / "_tgt.py"
        target.write_text(
            "# === BEGIN AUTO-GENERATED PROTOCOL ===\n"
            "stale\n"
            "# === END AUTO-GENERATED PROTOCOL ===\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(gen_module, "SOURCE", source)
        monkeypatch.setattr(gen_module, "TARGET", target)

        assert gen_module.main(["--check"]) == 1
        # ``--check`` must not mutate the file.
        assert "stale" in target.read_text(encoding="utf-8")


class TestMarkersInRealSourcesMatchScript:
    """Pin that the script's marker constants appear in both source files.

    A typo in either ``_device_portable.py`` or ``device_flcli.py``
    would otherwise surface only as a confusing "missing marker" CI
    failure; this test fails locally with a clearer message.
    """

    def test_device_portable_carries_both_markers(self, gen_module):
        source = (
            REPO_ROOT
            / "src"
            / "flstudio_cli"
            / "shared"
            / "infrastructure"
            / "protocol"
            / "_device_portable.py"
        ).read_text(encoding="utf-8")
        assert gen_module.BEGIN_MARKER in source
        assert gen_module.END_MARKER in source

    def test_device_flcli_carries_both_markers(self, gen_module):
        target = (
            REPO_ROOT
            / "src"
            / "flstudio_cli"
            / "shared"
            / "infrastructure"
            / "fl_device"
            / "device_flcli.py"
        ).read_text(encoding="utf-8")
        assert gen_module.BEGIN_MARKER in target
        assert gen_module.END_MARKER in target
