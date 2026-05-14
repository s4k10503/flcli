"""Pure domain types for FL Studio state representation.

This package contains only frozen dataclasses and pure functions --
no I/O, no threading, no side effects.  Every module can be imported
and tested without a running FL Studio instance or MIDI stack.

The ``Ok`` / ``Err`` outcome types live one level up at
:mod:`flstudio_cli.shared.utility.outcome` because they are
layer-free generics (Rust ``Result`` analogue), not domain concepts.

Submodules
----------
midi_types
    Nominal NewType wrappers and smart constructors for MIDI values
    (Pitch, Velocity, BPM, etc.).
note
    Immutable ``Note`` dataclass with boundary validation.
refs
    Stable reference types (ChannelRef, MixerTrackRef, ...) built on
    a closed ``Selector`` sum, plus snapshot-based resolver functions.
"""

from flstudio_cli.shared.domain.midi_types import (
    BPM,
    Beats,
    CCNumber,
    CCValue,
    ChannelIndex,
    MidiChannel,
    PatternIndex,
    Pitch,
    StepIndex,
    TrackIndex,
    Velocity,
)
from flstudio_cli.shared.domain.note import Note
from flstudio_cli.shared.domain.refs import (
    ByIndex,
    ByName,
    ByQuery,
    ChannelRef,
    MixerTrackRef,
    PatternRef,
    PluginSlotRef,
    Selector,
)

__all__ = [
    "BPM",
    "Beats",
    "ByIndex",
    "ByName",
    "ByQuery",
    "CCNumber",
    "CCValue",
    "ChannelIndex",
    "ChannelRef",
    "MidiChannel",
    "MixerTrackRef",
    "Note",
    "PatternIndex",
    "PatternRef",
    "Pitch",
    "PluginSlotRef",
    "Selector",
    "StepIndex",
    "TrackIndex",
    "Velocity",
]
