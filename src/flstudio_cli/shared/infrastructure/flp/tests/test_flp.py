"""Tests for the ``flp`` module."""

from __future__ import annotations

import sys

import pytest

from flstudio_cli.shared.domain.note import Note
from flstudio_cli.shared.infrastructure.flp import flp as Flp


class TestAtomicWrite:
    def test_write_and_read_back(self, tmp_path) -> None:
        path = tmp_path / "test_output.bin"
        data = b"hello, atomic world!"
        Flp._atomic_write(str(path), data)
        assert path.read_bytes() == data

    def test_overwrites_existing_file(self, tmp_path) -> None:
        path = tmp_path / "overwrite.bin"
        Flp._atomic_write(str(path), b"first")
        Flp._atomic_write(str(path), b"second")
        assert path.read_bytes() == b"second"

    def test_creates_file_at_path(self, tmp_path) -> None:
        path = tmp_path / "new_file.bin"
        assert not path.exists()
        Flp._atomic_write(str(path), b"data")
        assert path.exists()


class TestRequirePyflp:
    def test_raises_runtime_error_when_not_installed(self, monkeypatch) -> None:
        # Ensure pyflp is not importable
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp._require_pyflp()


class TestFlpInfoWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_info("/nonexistent.flp")


class TestFlpAddNotesWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        notes = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_add_notes("/nonexistent.flp", 0, notes)


class TestFlpClearNotesWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_clear_notes("/nonexistent.flp", 0)


class TestFlpChannelRenameWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_channel_rename("/nonexistent.flp", 0, "NewName")


class TestFlpPatternSetLengthWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_pattern_set_length("/nonexistent.flp", 0, 64)


class TestFlpMixerRouteWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_mixer_route("/nonexistent.flp", 1, 0)


class TestFlpClipCreateWithoutPyflp:
    def test_raises_runtime_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pyflp", None)
        with pytest.raises(RuntimeError, match="pyflp is required"):
            Flp.flp_clip_create("/nonexistent.flp", 0, 0, 0.0)
