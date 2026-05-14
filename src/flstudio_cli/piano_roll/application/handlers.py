"""Use case: piano-roll batch handlers — step-grid melody dispatch."""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import require
from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.application.handler_workflow import (
    BatchHandler,
    lift_exceptions,
)
from flstudio_cli.shared.domain.note import Note


@lift_exceptions
def _handle_step_melody(args: dict[str, Any]) -> DeviceCommand:
    """Schedule a list of notes into the step grid of the selected channel."""
    raw = require(args, "notes")
    if not isinstance(raw, list):
        raise TypeError("'notes' must be a list")
    notes: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise TypeError(f"notes[{index}] must be an object")
        try:
            notes.append(Note.from_entry(entry).to_dict())
        except KeyError as exc:
            raise ValueError(f"notes[{index}] missing {exc.args[0]!r}") from exc
    return fl.step_melody(notes=notes)


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "step_melody": _handle_step_melody,
}
