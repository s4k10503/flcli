"""Domain value object: typed value vocabulary for the MIDI domain.

Nominal types via :func:`typing.NewType` plus runtime *smart
constructors* that validate at the boundary.  Combining the two gives
us nominal typing in mypy and a single, central place where every
value bound is enforced.

Design rationale
~~~~~~~~~~~~~~~~
Each NewType (``Pitch``, ``Velocity``, ...) is erased at runtime, so
there is zero overhead in production.  The corresponding lowercase
smart constructor (``pitch()``, ``velocity()``, ...) performs the one-
time range check at the system boundary (CLI args, JSON payloads) and
returns the NewType wrapper.  Once a value has been constructed, all
downstream code can trust the invariants without re-checking.
"""

from __future__ import annotations

import math
from typing import NewType, assert_never

__all__ = [
    "BPM",
    "Beats",
    "CCNumber",
    "CCValue",
    "ChannelIndex",
    "MidiChannel",
    "PatternIndex",
    "Pitch",
    "StepIndex",
    "TrackIndex",
    "Velocity",
    "assert_never",
    "beats",
    "bpm",
    "cc_number",
    "cc_value",
    "channel_index",
    "midi_channel",
    "pattern_index",
    "pitch",
    "step_index",
    "track_index",
    "velocity",
]

# --- Nominal types ----------------------------------------------------------

Pitch = NewType("Pitch", int)
Velocity = NewType("Velocity", int)
MidiChannel = NewType("MidiChannel", int)
CCNumber = NewType("CCNumber", int)
CCValue = NewType("CCValue", int)
BPM = NewType("BPM", float)
PatternIndex = NewType("PatternIndex", int)
TrackIndex = NewType("TrackIndex", int)
ChannelIndex = NewType("ChannelIndex", int)
StepIndex = NewType("StepIndex", int)
Beats = NewType("Beats", float)


# --- Smart constructors -----------------------------------------------------


def _check_int_range(name: str, value: int, lo: int, hi: int) -> int:
    """Validate that *value* is a plain ``int`` within [*lo*, *hi*].

    Booleans are rejected because ``isinstance(True, int)`` is ``True``
    in Python, yet a boolean is never a valid MIDI value.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int, got {type(value).__name__}")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def _check_float_range(
    name: str,
    value: float,
    lo: float | None,
    hi: float | None,
) -> float:
    """Validate that *value* is a finite number within optional bounds.

    Booleans and non-numeric types are rejected.  *lo* / *hi* of
    ``None`` means unbounded on that side.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if lo is not None and value < lo:
        raise ValueError(f"{name} must be at least {lo}, got {value}")
    if hi is not None and value > hi:
        raise ValueError(f"{name} must be at most {hi}, got {value}")
    return float(value)


def pitch(value: int) -> Pitch:
    """Construct a validated MIDI pitch (0--127)."""
    return Pitch(_check_int_range("pitch", value, 0, 127))


def velocity(value: int) -> Velocity:
    """Construct a validated MIDI velocity (0--127)."""
    return Velocity(_check_int_range("velocity", value, 0, 127))


def midi_channel(value: int) -> MidiChannel:
    """Construct a validated MIDI channel (0--15)."""
    return MidiChannel(_check_int_range("midi_channel", value, 0, 15))


def cc_number(value: int) -> CCNumber:
    """Construct a validated MIDI CC number (0--127)."""
    return CCNumber(_check_int_range("cc_number", value, 0, 127))


def cc_value(value: int) -> CCValue:
    """Construct a validated MIDI CC value (0--127)."""
    return CCValue(_check_int_range("cc_value", value, 0, 127))


def bpm(value: float) -> BPM:
    """Construct a validated BPM value (1--999)."""
    return BPM(_check_float_range("bpm", value, 1, 999))


def pattern_index(value: int) -> PatternIndex:
    """Construct a validated pattern index (1--999, FL Studio is 1-indexed)."""
    return PatternIndex(_check_int_range("pattern_index", value, 1, 999))


def track_index(value: int) -> TrackIndex:
    """Construct a validated playlist track index (1--127, FL Studio is 1-indexed)."""
    return TrackIndex(_check_int_range("track_index", value, 1, 127))


def channel_index(value: int) -> ChannelIndex:
    """Construct a validated channel index (0--127).

    Constrained to 0--127 because the wire protocol carries channel
    selection inside a single CC-value byte.
    """
    return ChannelIndex(_check_int_range("channel_index", value, 0, 127))


def step_index(value: int) -> StepIndex:
    """Construct a validated step index (0--63).

    The device decoder writes into a 64-step grid; values above 63
    would be silently dropped, so we reject them at the boundary.
    """
    return StepIndex(_check_int_range("step_index", value, 0, 63))


def beats(value: float) -> Beats:
    """Construct a validated beat-position or duration (non-negative, finite)."""
    return Beats(_check_float_range("beats", value, 0, None))
