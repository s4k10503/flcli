"""Domain value object: immutable, validated domain model for a single musical note.

A ``Note`` is a frozen dataclass whose fields are typed with the
nominal MIDI wrappers from :mod:`.midi_types`.  Validation runs both
in the convenience constructor :meth:`Note.of` *and* in
``__post_init__``, so even direct ``Note(...)`` construction with raw
ints/floats is guaranteed to reject out-of-range values.
"""

# pyright: strict

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Self

from flstudio_cli.shared.domain import midi_types as D


@dataclass(frozen=True, slots=True)
class Note:
    pitch: D.Pitch
    velocity: D.Velocity
    length: D.Beats
    position: D.Beats

    def __post_init__(self) -> None:
        # Re-validate even when callers bypass Note.of and construct
        # the dataclass directly with raw ints/floats. This is the
        # only way to keep the encoder a true pure function of valid
        # values.
        D.pitch(self.pitch)
        D.velocity(self.velocity)
        D.beats(self.length)
        D.beats(self.position)

    def to_dict(self) -> dict[str, int | float]:
        """Canonical JSON-safe serialisation used by CLI, batch, and I/O layers."""
        return {
            "pitch": int(self.pitch),
            "velocity": int(self.velocity),
            "length": float(self.length),
            "position": float(self.position),
        }

    @classmethod
    def of(
        cls,
        pitch: int,
        velocity: int = 100,
        length: float = 1.0,
        position: float = 0.0,
    ) -> Self:
        """Validating constructor for untyped boundaries (CLI, JSON)."""
        return cls(
            pitch=D.pitch(pitch),
            velocity=D.velocity(velocity),
            length=D.beats(length),
            position=D.beats(position),
        )

    @classmethod
    def parse(cls, csv_spec: str) -> Self:
        """Parse a ``"pitch,velocity,length,position"`` CSV line."""
        tokens = [token.strip() for token in csv_spec.split(",")]
        match tokens:
            case [pitch_str, velocity_str, length_str, position_str]:
                return cls.of(
                    pitch=int(pitch_str),
                    velocity=int(velocity_str),
                    length=float(length_str),
                    position=float(position_str),
                )
            case _:
                raise ValueError(
                    f"expected 'pitch,velocity,length,position', got: {csv_spec!r}"
                )

    @classmethod
    def parse_csv_lenient(cls, csv_spec: str) -> Self:
        """Parse a CSV line with defaults filled in for missing trailing columns.

        Accepts any of ``pitch``, ``pitch,velocity``, ``pitch,velocity,length``,
        ``pitch,velocity,length,position``.  Missing fields fall back to the
        same defaults as :meth:`Note.of`.
        """
        parts = [p.strip() for p in csv_spec.split(",")]
        if not parts or not parts[0]:
            raise ValueError(f"empty CSV line: {csv_spec!r}")
        return cls.of(
            pitch=int(parts[0]),
            velocity=int(parts[1]) if len(parts) > 1 and parts[1] else 100,
            length=float(parts[2]) if len(parts) > 2 and parts[2] else 1.0,
            position=float(parts[3]) if len(parts) > 3 and parts[3] else 0.0,
        )

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> Self:
        """Build a :class:`Note` from a JSON-style ``{pitch, velocity?, length?, position?}`` dict.

        Missing optional fields fall back to the same defaults as
        :meth:`Note.of`.  Raises :class:`KeyError` when ``pitch`` is
        absent and :class:`ValueError`/``TypeError`` when a field cannot
        be coerced.
        """
        return cls.of(
            pitch=int(entry["pitch"]),
            velocity=int(entry.get("velocity", 100)),
            length=float(entry.get("length", 1.0)),
            position=float(entry.get("position", 0.0)),
        )

    # ----- per-field updaters ------------------------------------------------
    # ``__post_init__`` re-validates every field on every construction, so the
    # raw int/float passed here is bound-checked before the new instance
    # escapes the call.  Edit-op interpreters (piano_roll/domain/edit_ops.py)
    # use these to express transforms without restating the three fields they
    # are not touching.

    def with_pitch(self, pitch: int) -> Self:
        """Return a copy with *pitch* replaced (re-validated)."""
        return replace(self, pitch=D.Pitch(pitch))

    def with_velocity(self, velocity: int) -> Self:
        """Return a copy with *velocity* replaced (re-validated)."""
        return replace(self, velocity=D.Velocity(velocity))

    def with_length(self, length: float) -> Self:
        """Return a copy with *length* replaced (re-validated)."""
        return replace(self, length=D.Beats(length))

    def with_position(self, position: float) -> Self:
        """Return a copy with *position* replaced (re-validated)."""
        return replace(self, position=D.Beats(position))
