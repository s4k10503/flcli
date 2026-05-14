"""Use case: load a melody from a CSV/MIDI source.

Wraps the domain :class:`Note` factories and the MIDI-file reader Port
so presentation code only deals with one entry point — given a source
string (path or ``"-"`` for stdin), get back a typed
:class:`Outcome` carrying either the validated note list or one of the
:data:`MelodyError` variants.

``Note`` itself is a frozen value object and is allowed to flow back
through the boundary.  Presentation may call ``note.to_dict()`` on the
returned values — that's a value-object accessor, not a domain service
— but it must not call ``Note.parse`` / ``Note.from_entry`` directly.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from flstudio_cli.piano_roll.application.melody_errors import (
    EmptyMelody,
    MelodyError,
    MelodyIOError,
    MelodyNotFound,
    MelodyParseError,
)
from flstudio_cli.shared.domain.note import Note
from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

#: Re-exported so presentation can use ``Note`` as a value type without
#: needing to reach into ``..domain``.  ``Note`` is a frozen value object;
#: passing it through a layer boundary as data is acceptable, but
#: presentation must not call its factory methods (``Note.parse``,
#: ``Note.from_entry``) — that's what :func:`load_melody` is for.
__all__ = ["MidiFileReader", "Note", "load_melody"]

#: Reader Port shape for Standard MIDI Files.  Composition wires this
#: to ``Comp.read_midi_file`` so this module never imports infrastructure.
MidiFileReader = Callable[[str], list[Note]]


def _is_midi_path(source: str) -> bool:
    return source != "-" and source.lower().endswith((".mid", ".midi"))


def load_melody(
    source: str,
    *,
    midi_reader: MidiFileReader,
    read_text: Callable[[str], str],
    iter_lines: Callable[[str], Iterable[str]],
) -> Outcome[list[Note], MelodyError]:
    """Read and parse a melody from a path or ``"-"`` (stdin).

    ``.mid`` / ``.midi`` paths are handed to ``midi_reader``; anything
    else (including stdin) is parsed as the line-based CSV form.

    The two text helpers (``read_text``, ``iter_lines``) are passed in
    so this module does no I/O of its own.  Presentation supplies the
    presentation-layer helpers and the composition-wired MIDI reader.
    """
    try:
        if _is_midi_path(source):
            notes = midi_reader(source)
        else:
            text = read_text(source)
            notes = [Note.parse(line) for line in iter_lines(text)]
    except FileNotFoundError as exc:
        return Err(MelodyNotFound(source=source, reason=str(exc)))
    except OSError as exc:
        return Err(MelodyIOError(source=source, reason=str(exc)))
    except ValueError as exc:
        return Err(MelodyParseError(source=source, reason=str(exc)))

    if not notes:
        return Err(EmptyMelody(source=source))
    return Ok(notes)
