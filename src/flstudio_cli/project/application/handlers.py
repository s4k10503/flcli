"""Use case: project / pattern / channel / tempo / step batch handlers."""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import (
    optional_bool,
    optional_int,
    optional_string,
    require_float,
    require_int,
    require_string,
)
from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.application.handler_workflow import (
    BatchHandler,
    lift_exceptions,
)


@lift_exceptions
def _handle_new_project(_args: dict[str, Any]) -> DeviceCommand:
    """Create a new empty FL Studio project."""
    return fl.new_project()


@lift_exceptions
def _handle_new_pattern(args: dict[str, Any]) -> DeviceCommand:
    """Create a new pattern in the current project, optionally with a name."""
    return fl.new_pattern(name=optional_string(args, "name"))


@lift_exceptions
def _handle_select_pattern(args: dict[str, Any]) -> DeviceCommand:
    """Select a pattern by its 1-indexed FL Studio pattern number."""
    return fl.select_pattern(index=require_int(args, "index"))


@lift_exceptions
def _handle_name_pattern(args: dict[str, Any]) -> DeviceCommand:
    """Rename a pattern by its 1-indexed FL Studio pattern number."""
    return fl.name_pattern(
        index=require_int(args, "index"),
        name=require_string(args, "name"),
    )


@lift_exceptions
def _handle_channel_rack_focus(_args: dict[str, Any]) -> DeviceCommand:
    """Focus the Channel Rack window and return the current channel count.

    Used by the ``duplicate-channel`` CLI command as the device-side step
    before the CLI fires the Alt+C hotkey via ``os_automation``.
    """
    return fl.channel_rack_focus()


@lift_exceptions
def _handle_focus_channel_editor(args: dict[str, Any]) -> DeviceCommand:
    """Open the requested editor window for a specific channel."""
    return fl.focus_channel_editor(
        channel=require_int(args, "channel"),
        window=optional_string(args, "window", default="piano_roll"),
    )


@lift_exceptions
def _handle_name_channel(args: dict[str, Any]) -> DeviceCommand:
    """Rename a channel by index."""
    return fl.name_channel(
        channel=require_int(args, "channel"),
        name=require_string(args, "name"),
    )


@lift_exceptions
def _handle_select_channel(args: dict[str, Any]) -> DeviceCommand:
    """Select a channel by its zero-based index."""
    return fl.select_channel(index=require_int(args, "index"))


@lift_exceptions
def _handle_tempo(args: dict[str, Any]) -> DeviceCommand:
    """Set the project tempo in BPM."""
    return fl.tempo(bpm=require_float(args, "bpm"))


@lift_exceptions
def _handle_set_step(args: dict[str, Any]) -> DeviceCommand:
    """Toggle or set a single step in the step sequencer."""
    return fl.set_step(
        channel=require_int(args, "channel"),
        step=require_int(args, "step"),
        on=optional_bool(args, "on", default=True),
        velocity=optional_int(args, "velocity", default=100),
    )


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "new_project": _handle_new_project,
    "new_pattern": _handle_new_pattern,
    "select_pattern": _handle_select_pattern,
    "name_pattern": _handle_name_pattern,
    "channel_rack_focus": _handle_channel_rack_focus,
    "focus_channel_editor": _handle_focus_channel_editor,
    "name_channel": _handle_name_channel,
    "select_channel": _handle_select_channel,
    "tempo": _handle_tempo,
    "set_step": _handle_set_step,
}
