"""Use case: state and piano-roll-show batch handlers.

``state`` is a regular SysEx command (validated handler that returns a
:class:`DeviceCommand`).

``piano_roll_show`` is special — its handler reads real files through a
:class:`PianoRollIO` bundle and so cannot be a static handler.  It is
exposed as :func:`make_piano_roll_show_handler`, a factory that the
composition root calls with the production :class:`PianoRollIO` to
produce the IO-bound :data:`BatchHandler`.
"""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import optional_string
from flstudio_cli.shared.application.handler_dto import DeviceCommand, LocalResult
from flstudio_cli.shared.application.handler_workflow import (
    BatchHandler,
    lift_exceptions,
)
from flstudio_cli.shared.application.ports import PianoRollIO


@lift_exceptions
def _handle_state(args: dict[str, Any]) -> DeviceCommand:
    """Read FL Studio state, optionally filtered to a single field."""
    return fl.state(field=optional_string(args, "field"))


def make_piano_roll_show_handler(piano_roll_io: PianoRollIO) -> BatchHandler:
    """Bind a :class:`PianoRollIO` bundle into a closure-shaped batch handler.

    Kept as a factory because ``piano_roll_show`` is the only batch
    command that reads files instead of dispatching SysEx; the closure
    injection keeps :class:`PianoRollIO` out of the static handlers dict
    so handler-level tests can run without a wired IO bundle.
    """

    @lift_exceptions
    def _handle_piano_roll_show(args: dict[str, Any]) -> LocalResult:
        export_file = optional_string(args, "export_file")
        notes = piano_roll_io.read_exported_notes(export_file)
        return LocalResult(
            {
                "export_file": export_file or piano_roll_io.default_export_path(),
                "count": len(notes),
                "notes": [
                    {"index": index, **note.to_dict()}
                    for index, note in enumerate(notes)
                ],
            }
        )

    return _handle_piano_roll_show


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "state": _handle_state,
}
