"""Application DTO: typed failure variants returned by :func:`load_melody`.

The four variants below form the closed sum :data:`MelodyError`.
Each carries the ``source`` for diagnostics; ``reason`` carries the
underlying exception message where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EmptyMelody",
    "MelodyError",
    "MelodyIOError",
    "MelodyNotFound",
    "MelodyParseError",
]


@dataclass(frozen=True, slots=True)
class MelodyNotFound:
    """The source path does not exist."""

    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class MelodyIOError:
    """The source path exists but could not be read (permissions, etc.)."""

    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class MelodyParseError:
    """The CSV / MIDI body was malformed."""

    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class EmptyMelody:
    """Source produced zero notes."""

    source: str


MelodyError = MelodyNotFound | MelodyIOError | MelodyParseError | EmptyMelody
