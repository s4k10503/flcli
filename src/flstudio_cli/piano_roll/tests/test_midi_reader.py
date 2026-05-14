"""Tests for :mod:`flstudio_cli.piano_roll.infrastructure.midi_reader`."""

from __future__ import annotations

import mido
import pytest

from flstudio_cli.piano_roll.infrastructure.midi_reader import read_midi_file


def _write_midi(tmp_path, tracks: list[list[mido.Message]], ticks_per_beat: int = 480):
    midi_file = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    for messages in tracks:
        track = mido.MidiTrack()
        track.extend(messages)
        midi_file.tracks.append(track)
    path = tmp_path / "sample.mid"
    midi_file.save(str(path))
    return path


def test_reads_single_note(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=60, velocity=100, time=0),
                mido.Message("note_off", note=60, velocity=0, time=480),
            ]
        ],
    )

    notes = read_midi_file(path)

    assert len(notes) == 1
    note = notes[0]
    assert int(note.pitch) == 60
    assert int(note.velocity) == 100
    assert float(note.position) == 0.0
    assert float(note.length) == 1.0


def test_note_on_with_zero_velocity_is_treated_as_note_off(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=64, velocity=90, time=0),
                mido.Message("note_on", note=64, velocity=0, time=240),
            ]
        ],
    )

    notes = read_midi_file(path)

    assert len(notes) == 1
    assert float(notes[0].length) == 0.5
    assert int(notes[0].velocity) == 90


def test_merges_tracks_and_sorts_by_position(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=60, velocity=100, time=480),
                mido.Message("note_off", note=60, velocity=0, time=480),
            ],
            [
                mido.Message("note_on", note=72, velocity=80, time=0),
                mido.Message("note_off", note=72, velocity=0, time=240),
            ],
        ],
    )

    notes = read_midi_file(path)

    assert [int(n.pitch) for n in notes] == [72, 60]
    assert [float(n.position) for n in notes] == [0.0, 1.0]


def test_track_index_filter(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=60, velocity=100, time=0),
                mido.Message("note_off", note=60, velocity=0, time=480),
            ],
            [
                mido.Message("note_on", note=72, velocity=80, time=0),
                mido.Message("note_off", note=72, velocity=0, time=240),
            ],
        ],
    )

    only_second = read_midi_file(path, track_index=1)

    assert len(only_second) == 1
    assert int(only_second[0].pitch) == 72


def test_invalid_track_index(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=60, velocity=100, time=0),
                mido.Message("note_off", note=60, velocity=0, time=480),
            ]
        ],
    )

    with pytest.raises(ValueError, match="track_index"):
        read_midi_file(path, track_index=5)


def test_dangling_note_on_is_closed_at_eof(tmp_path):
    path = _write_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=67, velocity=100, time=0),
                # no matching note_off
            ]
        ],
    )

    notes = read_midi_file(path)

    assert len(notes) == 1
    assert float(notes[0].length) > 0
