"""Domain service: pure value types and pure transforms describing piano-roll edit semantics.

An :class:`EditPlan` is a sequence of typed :data:`EditOp` values.  Each
op is a closed sum of the five legal edit kinds; the type system already
rejects anything outside the set, so the interpreter does not need a
string ``mode`` switch or an "unknown op" branch.

Note field updates flow through :class:`NoteUpdate` rather than a
stringly-keyed dict.  ``NoteUpdate(tempo=120)`` is a static error, not a
runtime ``ValueError`` -- *parse, don't validate*.

Everything in this module is pure: no I/O, no FL Studio path knowledge,
no environment variables.  The ``apply_edits`` interpreter composes per-
note transforms with no shared mutable state, making each transform
independently testable.  The matching round-trip I/O lives in
:mod:`flstudio_cli.piano_roll.infrastructure.piano_roll_io`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar, assert_never

from flstudio_cli.shared.domain.note import Note

__all__ = [
    "Delete",
    "EditOp",
    "EditPlan",
    "NoteEdit",
    "NoteUpdate",
    "ScaleLength",
    "SetFields",
    "Shift",
    "Transpose",
    "apply_edits",
]


# --- value types ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoteUpdate:
    """Sparse per-field update applied on top of an existing :class:`Note`.

    Each ``None`` field means "leave that field alone".  The four
    listed names are the *only* valid edit targets, so the type system
    rejects ``NoteUpdate(tempo=120)`` at the call site instead of
    deferring the error to runtime.
    """

    pitch: int | None = None
    velocity: int | None = None
    length: float | None = None
    position: float | None = None

    def applied_to(self, base: Note) -> Note:
        """Return a new Note with the non-``None`` fields overwritten."""
        note = base
        if self.pitch is not None:
            note = note.with_pitch(self.pitch)
        if self.velocity is not None:
            note = note.with_velocity(self.velocity)
        if self.length is not None:
            note = note.with_length(self.length)
        if self.position is not None:
            note = note.with_position(self.position)
        return note

    def is_empty(self) -> bool:
        """True when every field is ``None`` (the update is a no-op)."""
        return (
            self.pitch is None
            and self.velocity is None
            and self.length is None
            and self.position is None
        )


@dataclass(frozen=True, slots=True)
class Delete:
    """Drop a fixed set of note indices from the score."""

    indices: frozenset[int]

    INDEX_LABEL: ClassVar[str] = "delete"

    def in_scope_indices(self) -> Iterable[int]:
        return self.indices


@dataclass(frozen=True, slots=True)
class SetFields:
    """Overwrite specific fields of a single note."""

    index: int
    update: NoteUpdate

    INDEX_LABEL: ClassVar[str] = "set"

    def in_scope_indices(self) -> Iterable[int]:
        return (self.index,)


@dataclass(frozen=True, slots=True)
class Transpose:
    """Add semitones to every in-scope note's pitch."""

    semitones: int
    only: frozenset[int] | None = None

    INDEX_LABEL: ClassVar[str] = "only"

    def in_scope_indices(self) -> Iterable[int]:
        return self.only if self.only is not None else ()


@dataclass(frozen=True, slots=True)
class Shift:
    """Add beats to every in-scope note's position."""

    beats: float
    only: frozenset[int] | None = None

    INDEX_LABEL: ClassVar[str] = "only"

    def in_scope_indices(self) -> Iterable[int]:
        return self.only if self.only is not None else ()


@dataclass(frozen=True, slots=True)
class ScaleLength:
    """Multiply every in-scope note's length by *factor*."""

    factor: float
    only: frozenset[int] | None = None

    INDEX_LABEL: ClassVar[str] = "only"

    def in_scope_indices(self) -> Iterable[int]:
        return self.only if self.only is not None else ()


#: Closed sum of every legal edit operation.  Adding a sixth kind is a
#: deliberate type-system event: every ``match`` site below stops
#: type-checking until the new variant is handled.
EditOp = Delete | SetFields | Transpose | Shift | ScaleLength


@dataclass(frozen=True, slots=True)
class EditPlan:
    """Ordered sequence of :data:`EditOp` values applied left-to-right.

    A plan is just data -- *what* to do, not *how*.  :func:`apply_edits`
    interprets it.  Construct ops directly::

        EditPlan((
            Delete(frozenset({0, 3})),
            Transpose(semitones=12),
            Shift(beats=4.0, only=frozenset({1, 2})),
        ))

    Order matters: ``Delete`` then ``SetFields`` mean the deleted index
    is gone before the set runs; reverse the order and the set fires
    first.  The CLI applies a stable order to keep historical
    behaviour (delete -> set -> bulk).
    """

    ops: tuple[EditOp, ...] = ()


# --- interpreter -----------------------------------------------------------


# A NoteEdit is a pure transform from (index, note) to a new note, or
# to ``None`` to drop the note.  ``apply_edits`` composes a list of
# these into the per-note pipeline -- no shared mutable state, each
# transform is independently testable.
NoteEdit = Callable[[int, Note], Note | None]


def _delete_at(targets: frozenset[int]) -> NoteEdit:
    """Build a transform that drops notes whose index is in *targets*."""

    def edit(index: int, note: Note) -> Note | None:
        return None if index in targets else note

    return edit


def _set_at_index(target: int, update: NoteUpdate) -> NoteEdit:
    """Build a transform that rewrites listed fields on a single index."""

    def edit(index: int, note: Note) -> Note | None:
        if index != target or update.is_empty():
            return note
        return update.applied_to(note)

    return edit


def _scoped_bulk(
    only: frozenset[int] | None,
    transform: Callable[[Note], Note],
) -> NoteEdit:
    """Lift a ``Note -> Note`` transform into a scoped :data:`NoteEdit`."""

    def in_scope(index: int) -> bool:
        return only is None or index in only

    def edit(index: int, note: Note) -> Note | None:
        return transform(note) if in_scope(index) else note

    return edit


def _transpose_note(semitones: int) -> Callable[[Note], Note]:
    return lambda note: note.with_pitch(int(note.pitch) + semitones)


def _shift_note(beats: float) -> Callable[[Note], Note]:
    return lambda note: note.with_position(float(note.position) + beats)


def _scale_length_note(factor: float) -> Callable[[Note], Note]:
    return lambda note: note.with_length(float(note.length) * factor)


def _compile_op(op: EditOp) -> NoteEdit:
    """Map an :data:`EditOp` value onto its corresponding :data:`NoteEdit`.

    Total over the closed :data:`EditOp` sum.  Adding a new variant
    will fail static analysis here until it is handled explicitly.
    """
    match op:
        case Delete(indices=targets):
            return _delete_at(targets)
        case SetFields(index=target, update=update):
            return _set_at_index(target, update)
        case Transpose(semitones=semitones, only=only):
            return _scoped_bulk(only, _transpose_note(semitones))
        case Shift(beats=beats, only=only):
            return _scoped_bulk(only, _shift_note(beats))
        case ScaleLength(factor=factor, only=only):
            return _scoped_bulk(only, _scale_length_note(factor))
        case _ as unreachable:
            assert_never(unreachable)


def _validate_op(op: EditOp, count: int) -> None:
    """Reject out-of-range indices on a single op.

    Each variant exposes the indices it touches via
    :meth:`in_scope_indices` and a diagnostic ``INDEX_LABEL`` class var,
    so this pass is a single bounds check over the union — no
    per-variant branching needed in the validator itself.
    """
    max_index = count - 1
    for i in op.in_scope_indices():
        if not 0 <= i <= max_index:
            raise ValueError(f"{op.INDEX_LABEL} index out of range: {i}")


def _run_pipeline(
    pipeline: tuple[NoteEdit, ...],
    index: int,
    note: Note,
) -> Note | None:
    """Apply each transform in turn; short-circuit once a transform deletes."""
    current: Note | None = note
    for transform in pipeline:
        if current is None:
            return None
        current = transform(index, current)
    return current


def _validate_plan(plan: EditPlan, notes: list[Note]) -> None:
    """Reject any op in *plan* whose indices fall outside ``notes``."""
    count = len(notes)
    for op in plan.ops:
        _validate_op(op, count)


def _compile_plan(plan: EditPlan) -> tuple[NoteEdit, ...]:
    """Translate every op in *plan* into its :data:`NoteEdit` pipeline stage."""
    return tuple(_compile_op(op) for op in plan.ops)


def _apply_plan(pipeline: tuple[NoteEdit, ...], notes: list[Note]) -> list[Note]:
    """Run a compiled *pipeline* over *notes*, dropping any deletions."""
    return [
        result
        for index, note in enumerate(notes)
        if (result := _run_pipeline(pipeline, index, note)) is not None
    ]


def apply_edits(notes: list[Note], plan: EditPlan) -> list[Note]:
    """Interpret an :class:`EditPlan` against a list of :class:`Note`.

    Two passes: validate every op against the input length first, then
    compile each op to a :data:`NoteEdit` and run the resulting
    pipeline over the input.  No shared mutable buffer; each transform
    is a pure function of ``(index, note)``.
    """
    _validate_plan(plan, notes)
    pipeline = _compile_plan(plan)
    return _apply_plan(pipeline, notes)
