"""Use case: realtime piano-roll note-event scheduler.

FL Studio's MIDI Scripting API does not allow inserting arbitrary
notes into the piano roll. The only reliable way to land pitched,
arbitrarily-timed notes in a pattern is to *record* them through a
normal MIDI input while the transport is running.

This module schedules ``note_on`` / ``note_off`` events on a
non-control MIDI channel and pushes them to a
:class:`~flstudio_cli.shared.application.ports.NoteEventSink` -- the
application-layer Port that hides ``mido`` from the application code.
The device script (``device_flcli.py``) ignores events on that channel
so FL Studio receives them as plain controller input and writes them
into the selected channel's piano roll.

The scheduler is intentionally simple — a sorted event list with
``time.sleep`` between events. Real DAW-grade jitter compensation
isn't worth the complexity for an LLM-driven batch tool; we just need
the notes to land in the right musical positions.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from flstudio_cli.shared.application import midi_routing as P
from flstudio_cli.shared.application.ports import NoteEventSink
from flstudio_cli.shared.domain.note import Note

#: Factory that opens a fresh :class:`NoteEventSink` for the given port.
#: Composition (``__main__``) injects the production implementation;
#: tests pass a fake.
NoteSinkFactory = Callable[[str | None], NoteEventSink]


@dataclass(frozen=True, slots=True)
class _ScheduledEvent:
    time_seconds: float
    is_note_on: bool
    pitch: int
    velocity: int


def _build_event_schedule(
    notes: Sequence[Note],
    seconds_per_beat: float,
) -> list[_ScheduledEvent]:
    events: list[_ScheduledEvent] = []
    for note in notes:
        start = float(note.position) * seconds_per_beat
        end = start + max(0.01, float(note.length) * seconds_per_beat)
        events.append(_ScheduledEvent(start, True, int(note.pitch), int(note.velocity)))
        events.append(_ScheduledEvent(end, False, int(note.pitch), 0))
    # note_off must precede a simultaneous note_on of the same pitch so
    # FL doesn't merge them; sort key keeps note_offs first on ties.
    events.sort(key=lambda event: (event.time_seconds, event.is_note_on))
    return events


def record_to_piano_roll(
    sink: NoteEventSink,
    notes: Sequence[Note],
    bpm: float,
    *,
    sleep=None,
) -> float:
    """Stream ``notes`` to ``sink`` with realtime timing.

    Returns the total wall-clock duration of the streamed sequence in
    seconds. Caller is responsible for putting FL Studio into record
    mode beforehand and stopping it afterwards.
    """
    if bpm <= 0:
        raise ValueError(f"bpm must be positive, got {bpm}")
    import time as _time

    do_sleep = sleep or _time.sleep
    seconds_per_beat = 60.0 / bpm
    schedule = _build_event_schedule(notes, seconds_per_beat)
    if not schedule:
        return 0.0
    start_wall_clock = _time.monotonic()
    for event in schedule:
        target = start_wall_clock + event.time_seconds
        delay = target - _time.monotonic()
        if delay > 0:
            do_sleep(delay)
        if event.is_note_on:
            sink.send_note_on(
                event.pitch,
                event.velocity,
                P.PIANO_ROLL_MIDI_CHANNEL,
            )
        else:
            sink.send_note_off(
                event.pitch,
                event.velocity,
                P.PIANO_ROLL_MIDI_CHANNEL,
            )
    return schedule[-1].time_seconds


def open_port_and_record(
    sink_factory: NoteSinkFactory,
    port_name: str | None,
    notes: Sequence[Note],
    bpm: float,
) -> float:
    """Open a sink via *sink_factory* and stream ``notes`` to it.

    Convenience wrapper that owns the sink lifecycle so the CLI layer
    never needs to import ``mido`` directly.  Returns the total
    duration in seconds (see :func:`record_to_piano_roll`).
    """
    sink = sink_factory(port_name)
    try:
        return record_to_piano_roll(sink, notes, bpm)
    finally:
        sink.close()
