"""Infrastructure adapter: read Standard MIDI Files into the domain :class:`Note` model.

The rest of the codebase is strictly output-oriented: commands build
message streams and ship them at a live port or state file. This module
is the only inbound bridge — it turns a ``.mid`` file into the same
validated ``list[Note]`` the ``step-melody``/``queue-piano-roll``/
``piano-roll`` commands already consume, so a user can hand the CLI an
existing MIDI file instead of the ad-hoc CSV format.
"""

from __future__ import annotations

from pathlib import Path

import mido

from flstudio_cli.shared.domain import midi_types as D
from flstudio_cli.shared.domain.note import Note


def _clamp_velocity(raw_velocity: int) -> int:
    # Some DAWs export velocity 0 as a note_off shortcut; by the time we
    # get here that's already been filtered, but incoming files may
    # still contain out-of-range values we want to coerce instead of
    # rejecting the whole file.
    return max(1, min(127, int(raw_velocity)))


def read_midi_file(
    source: str | Path,
    *,
    track_index: int | None = None,
) -> list[Note]:
    """Parse ``source`` and return every note as a validated :class:`Note`.

    * ``position`` and ``length`` are expressed in beats, using the
      file's ``ticks_per_beat`` header — tempo changes are ignored
      because the domain model is tempo-agnostic.
    * When ``track_index`` is ``None`` (the default) notes from every
      track are merged and sorted by start position; otherwise only the
      requested track is returned.
    * Notes still sounding at end-of-file get a length derived from the
      final tick so they aren't silently dropped.
    """
    midi_file = mido.MidiFile(str(source))
    ticks_per_beat = midi_file.ticks_per_beat
    if ticks_per_beat <= 0:
        raise ValueError(
            f"invalid MIDI file: ticks_per_beat must be positive, got {ticks_per_beat}"
        )

    if track_index is not None:
        if not 0 <= track_index < len(midi_file.tracks):
            raise ValueError(
                f"track_index {track_index} out of range "
                f"(file has {len(midi_file.tracks)} tracks)"
            )
        selected_tracks = [midi_file.tracks[track_index]]
    else:
        selected_tracks = list(midi_file.tracks)

    collected: list[tuple[float, Note]] = []

    for track in selected_tracks:
        absolute_tick = 0
        # key: (pitch, channel) -> (start_tick, velocity)
        open_notes: dict[tuple[int, int], tuple[int, int]] = {}

        for message in track:
            absolute_tick += message.time

            is_note_on = message.type == "note_on" and message.velocity > 0
            is_note_off = message.type == "note_off" or (
                message.type == "note_on" and message.velocity == 0
            )
            if not (is_note_on or is_note_off):
                continue

            key = (int(message.note), int(getattr(message, "channel", 0)))

            if is_note_on:
                # Overlapping identical pitch on the same channel: close
                # the previous instance at the current tick before
                # starting a new one, matching how most DAWs render.
                if key in open_notes:
                    start_tick, raw_velocity = open_notes.pop(key)
                    collected.append(
                        _build_note(
                            pitch=key[0],
                            raw_velocity=raw_velocity,
                            start_tick=start_tick,
                            end_tick=absolute_tick,
                            ticks_per_beat=ticks_per_beat,
                        )
                    )
                open_notes[key] = (absolute_tick, int(message.velocity))
                continue

            # note_off
            if key not in open_notes:
                continue
            start_tick, raw_velocity = open_notes.pop(key)
            collected.append(
                _build_note(
                    pitch=key[0],
                    raw_velocity=raw_velocity,
                    start_tick=start_tick,
                    end_tick=absolute_tick,
                    ticks_per_beat=ticks_per_beat,
                )
            )

        # Dangling note_ons at EOF: close them at the last seen tick so
        # they don't silently disappear from the melody.
        for (pitch_value, _channel), (start_tick, raw_velocity) in open_notes.items():
            collected.append(
                _build_note(
                    pitch=pitch_value,
                    raw_velocity=raw_velocity,
                    start_tick=start_tick,
                    end_tick=max(absolute_tick, start_tick + 1),
                    ticks_per_beat=ticks_per_beat,
                )
            )

    collected.sort(key=lambda entry: (entry[0], int(entry[1].pitch)))
    return [note for _position, note in collected]


def _build_note(
    *,
    pitch: int,
    raw_velocity: int,
    start_tick: int,
    end_tick: int,
    ticks_per_beat: int,
) -> tuple[float, Note]:
    position_beats = start_tick / ticks_per_beat
    length_beats = max(end_tick - start_tick, 1) / ticks_per_beat
    note = Note(
        pitch=D.pitch(int(pitch)),
        velocity=D.velocity(_clamp_velocity(raw_velocity)),
        length=D.beats(length_beats),
        position=D.beats(position_beats),
    )
    return position_beats, note
