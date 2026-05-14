"""Interface adapter: melody-loading and serialisation helpers for piano-roll commands.

These helpers used to live in :mod:`flstudio_cli.shared.presentation.cli_dispatch`
which made ``shared`` reach into ``piano_roll.application`` for the
melody parser.  Both helpers are only used by ``piano_roll/presentation/``
commands (`step-melody`, `queue-piano-roll`, `read-midi`, edit ops),
so they live alongside their consumers and the dependency arrow stays
``feature → shared``.
"""

from __future__ import annotations

from typing import Any

from flstudio_cli.piano_roll.application.load_melody import Note, load_melody
from flstudio_cli.piano_roll.application.melody_errors import (
    EmptyMelody,
    MelodyIOError,
    MelodyNotFound,
    MelodyParseError,
)
from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_helpers import (
    _fail,
    iter_significant_lines,
    read_text_or_stdin,
)
from flstudio_cli.shared.utility.outcome import Err, Ok


def _notes_to_dicts(notes: list[Note]) -> list[dict[str, Any]]:
    return [n.to_dict() for n in notes]


def _load_melody_or_fail(
    command_name: str,
    source: str,
    args_echo: dict[str, Any],
) -> list[Note] | None:
    """Load a melody via the application use-case; emit error envelope on failure.

    Presentation hands ``load_melody`` the two text helpers (read +
    line-iter) and the composition-wired MIDI reader, then maps the
    :class:`Ok` / :class:`Err` outcome onto the CLI envelope codes.
    """
    match load_melody(
        source,
        midi_reader=Comp.read_midi_file,
        read_text=read_text_or_stdin,
        iter_lines=iter_significant_lines,
    ):
        case Ok(notes):
            return notes
        case Err(MelodyNotFound(reason=reason)):
            _fail(
                command_name,
                f"failed to load melody: {reason}",
                code=Env.CODE_NOT_FOUND,
                args=args_echo,
            )
            return None
        case Err(MelodyIOError(reason=reason) | MelodyParseError(reason=reason)):
            _fail(
                command_name,
                f"failed to load melody: {reason}",
                code=Env.CODE_IO_ERROR,
                args=args_echo,
            )
            return None
        case Err(EmptyMelody()):
            _fail(
                command_name,
                "no notes parsed from input",
                code=Env.CODE_INVALID_ARGUMENT,
                args=args_echo,
            )
            return None
