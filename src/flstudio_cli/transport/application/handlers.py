"""Use case: transport batch handlers — playback, position, loop, undo / redo.

Argument-shape contracts are spelled out as :class:`typing.TypedDict`
literals (e.g. :data:`TransportPositionSetArgs`) so handler bodies can
reference field names through a typed view of the wire payload instead
of treating it as a free-form ``dict[str, Any]``.  The runtime
validation still flows through :mod:`handler_args` — pyright sees the
TypedDict for refactor safety, the runtime sees the same boundary
checks it always did.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict, cast

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import (
    ArgsLike,
    optional_string,
    require_float,
)
from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.application.handler_workflow import (
    BatchHandler,
    lift_exceptions,
)
from flstudio_cli.shared.application.transport_modes import (
    VALID_POSITION_MODES,
    PositionMode,
)


class TransportPositionGetArgs(TypedDict, total=False):
    """Wire payload for ``transport_position_get``.

    Every field is optional (``total=False``) — ``mode`` defaults to
    ``"beats"`` when omitted.
    """

    mode: PositionMode


class TransportPositionSetArgs(TypedDict):
    """Wire payload for ``transport_position_set``."""

    position: float
    mode: NotRequired[PositionMode]


@lift_exceptions
def _handle_play(_args: dict[str, Any]) -> DeviceCommand:
    return fl.play()


@lift_exceptions
def _handle_stop(_args: dict[str, Any]) -> DeviceCommand:
    return fl.stop()


@lift_exceptions
def _handle_record(_args: dict[str, Any]) -> DeviceCommand:
    return fl.record()


def _validate_position_mode(args: ArgsLike) -> PositionMode:
    """Return the validated ``mode`` string, defaulting to ``"beats"``."""
    mode = optional_string(args, "mode", default="beats")
    if mode not in VALID_POSITION_MODES:
        raise ValueError(f"'mode' must be one of {sorted(VALID_POSITION_MODES)}")
    return cast(PositionMode, mode)


@lift_exceptions
def _handle_transport_position_get(args: dict[str, Any]) -> DeviceCommand:
    """Read the current transport position.

    Validates ``args`` against :data:`TransportPositionGetArgs`; the
    cast is sound because ``_validate_position_mode`` already enforces
    the runtime contract before any field is consumed.
    """
    typed: TransportPositionGetArgs = cast(TransportPositionGetArgs, args)
    return fl.transport_position_get(mode=_validate_position_mode(typed))


@lift_exceptions
def _handle_transport_position_set(args: dict[str, Any]) -> DeviceCommand:
    """Set the transport position."""
    typed: TransportPositionSetArgs = cast(TransportPositionSetArgs, args)
    return fl.transport_position_set(
        position=require_float(typed, "position"),
        mode=_validate_position_mode(typed),
    )


@lift_exceptions
def _handle_transport_loop_get(_args: dict[str, Any]) -> DeviceCommand:
    """Read the current loop-mode state."""
    return fl.transport_loop_get()


@lift_exceptions
def _handle_transport_loop_toggle(_args: dict[str, Any]) -> DeviceCommand:
    """Toggle loop mode on or off."""
    return fl.transport_loop_toggle()


@lift_exceptions
def _handle_undo(_args: dict[str, Any]) -> DeviceCommand:
    """Undo the last action in FL Studio."""
    return fl.undo()


@lift_exceptions
def _handle_redo(_args: dict[str, Any]) -> DeviceCommand:
    """Redo the previously undone action."""
    return fl.redo()


@lift_exceptions
def _handle_undo_history(_args: dict[str, Any]) -> DeviceCommand:
    """Retrieve the undo history list."""
    return fl.undo_history()


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "play": _handle_play,
    "stop": _handle_stop,
    "record": _handle_record,
    "transport_position_get": _handle_transport_position_get,
    "transport_position_set": _handle_transport_position_set,
    "transport_loop_get": _handle_transport_loop_get,
    "transport_loop_toggle": _handle_transport_loop_toggle,
    "undo": _handle_undo,
    "redo": _handle_redo,
    "undo_history": _handle_undo_history,
}
