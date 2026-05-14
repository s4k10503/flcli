"""Tests for :mod:`flstudio_cli.piano_roll.infrastructure.piano_roll_io`."""

from __future__ import annotations

import json

from flstudio_cli.piano_roll.infrastructure.piano_roll_io import (
    read_exported_notes,
    write_queue_file,
)
from flstudio_cli.shared.domain.note import Note


def _write_export(tmp_path, notes_payload, ppq=96):
    path = tmp_path / "export.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "ppq": ppq,
                "notes": notes_payload,
            }
        )
    )
    return path


def test_read_exported_notes_sorted_by_index(tmp_path):
    path = _write_export(
        tmp_path,
        [
            {"index": 1, "pitch": 64, "velocity": 90, "length": 0.5, "position": 1.0},
            {"index": 0, "pitch": 60, "velocity": 100, "length": 1.0, "position": 0.0},
        ],
    )

    notes = read_exported_notes(path)

    assert [int(n.pitch) for n in notes] == [60, 64]


def test_write_queue_file_roundtrip(tmp_path):
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=64, velocity=90, length=0.5, position=1.0),
    ]
    target = tmp_path / "queue.json"

    write_queue_file(notes, path=str(target), clear_existing=True)

    payload = json.loads(target.read_text())
    assert payload["clear_existing"] is True
    assert payload["consume"] is True
    assert [n["pitch"] for n in payload["notes"]] == [60, 64]
