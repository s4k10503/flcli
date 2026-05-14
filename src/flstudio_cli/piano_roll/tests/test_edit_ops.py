"""Tests for :mod:`flstudio_cli.piano_roll.domain.edit_ops`."""

from __future__ import annotations

import pytest

from flstudio_cli.piano_roll.domain.edit_ops import (
    Delete,
    EditPlan,
    NoteUpdate,
    ScaleLength,
    SetFields,
    Shift,
    Transpose,
    apply_edits,
)
from flstudio_cli.shared.domain.note import Note


def test_delete_and_transpose():
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=62, velocity=100, length=1.0, position=1.0),
        Note.of(pitch=64, velocity=100, length=1.0, position=2.0),
    ]
    plan = EditPlan((Delete(frozenset({1})), Transpose(semitones=12)))

    result = apply_edits(notes, plan)

    assert [int(n.pitch) for n in result] == [72, 76]
    assert [float(n.position) for n in result] == [0.0, 2.0]


def test_set_fields():
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=62, velocity=100, length=1.0, position=1.0),
    ]
    plan = EditPlan(
        (
            SetFields(index=0, update=NoteUpdate(pitch=67, velocity=80)),
            SetFields(index=1, update=NoteUpdate(length=0.25)),
        )
    )

    result = apply_edits(notes, plan)

    assert int(result[0].pitch) == 67
    assert int(result[0].velocity) == 80
    assert float(result[1].length) == 0.25
    assert int(result[1].pitch) == 62  # unchanged


def test_only_restricts_bulk_ops():
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=62, velocity=100, length=1.0, position=1.0),
        Note.of(pitch=64, velocity=100, length=1.0, position=2.0),
    ]
    plan = EditPlan((Transpose(semitones=7, only=frozenset({1})),))

    result = apply_edits(notes, plan)

    assert [int(n.pitch) for n in result] == [60, 69, 64]


def test_shift_and_scale_length():
    notes = [Note.of(pitch=60, velocity=100, length=2.0, position=1.0)]
    plan = EditPlan((Shift(beats=0.5), ScaleLength(factor=0.5)))

    result = apply_edits(notes, plan)

    assert float(result[0].position) == 1.5
    assert float(result[0].length) == 1.0


def test_out_of_range_delete_raises():
    notes = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]

    with pytest.raises(ValueError, match="delete index"):
        apply_edits(notes, EditPlan((Delete(frozenset({5})),)))


def test_out_of_range_set_raises():
    notes = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]

    with pytest.raises(ValueError, match="set index"):
        apply_edits(notes, EditPlan((SetFields(index=5, update=NoteUpdate(pitch=60)),)))


def test_out_of_range_only_raises():
    notes = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]

    with pytest.raises(ValueError, match="only index"):
        apply_edits(notes, EditPlan((Transpose(semitones=1, only=frozenset({9})),)))


def test_pipeline_composes_in_order():
    """Ops execute left-to-right in the tuple they're declared in."""
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=62, velocity=100, length=1.0, position=1.0),
        Note.of(pitch=64, velocity=100, length=1.0, position=2.0),
        Note.of(pitch=65, velocity=100, length=1.0, position=3.0),
    ]
    plan = EditPlan(
        (
            Delete(frozenset({1})),
            SetFields(index=2, update=NoteUpdate(velocity=80)),
            Transpose(semitones=12, only=frozenset({0, 2})),
        )
    )

    result = apply_edits(notes, plan)

    # index 1 dropped; transpose only applies to original {0, 2};
    # set_fields targets original index 2 (still present)
    assert [int(n.pitch) for n in result] == [72, 76, 65]
    assert int(result[1].velocity) == 80


def test_empty_plan_is_identity():
    notes = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]

    assert apply_edits(notes, EditPlan()) == notes


def test_note_update_empty_is_no_op():
    """An all-None NoteUpdate leaves the note untouched."""
    note = Note.of(pitch=60, velocity=100, length=1.0, position=0.0)
    plan = EditPlan((SetFields(index=0, update=NoteUpdate()),))

    assert apply_edits([note], plan) == [note]


def test_note_update_applied_to_overwrites_only_set_fields():
    base = Note.of(pitch=60, velocity=100, length=1.0, position=0.0)
    update = NoteUpdate(pitch=72, length=0.5)

    new = update.applied_to(base)

    assert int(new.pitch) == 72
    assert int(new.velocity) == 100  # unchanged
    assert float(new.length) == 0.5
    assert float(new.position) == 0.0  # unchanged


def test_set_after_delete_skips_deleted():
    """Order matters: Delete first means SetFields hits empty slot."""
    notes = [
        Note.of(pitch=60, velocity=100, length=1.0, position=0.0),
        Note.of(pitch=62, velocity=100, length=1.0, position=1.0),
    ]
    plan = EditPlan(
        (
            Delete(frozenset({0})),
            SetFields(index=0, update=NoteUpdate(pitch=99)),
        )
    )

    result = apply_edits(notes, plan)

    # index 0 was deleted, set targets original index 0 -> no-op for surviving notes
    assert len(result) == 1
    assert int(result[0].pitch) == 62
