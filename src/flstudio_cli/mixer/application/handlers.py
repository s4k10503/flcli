"""Use case: mixer batch handlers — track volume, pan, name, mute / solo / arm, routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import (
    optional_bool,
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
def _handle_mixer_list(_args: dict[str, Any]) -> DeviceCommand:
    """List all mixer tracks."""
    return fl.mixer_list()


def _make_mixer_field_handlers(
    get_call: Callable[[int], DeviceCommand],
    set_call: Callable[..., DeviceCommand],
    set_value_key: str,
    set_value_validator: Callable[[dict[str, Any], str], Any],
) -> tuple[BatchHandler, BatchHandler]:
    """Build a ``(getter, setter)`` handler pair for a per-track mixer field.

    *get_call* / *set_call* are lambdas that defer the ``fl.*`` lookup
    to invocation time so module-level monkey-patching of :data:`fl`
    is visible to every dispatch.
    """

    @lift_exceptions
    def getter(args: dict[str, Any]) -> DeviceCommand:
        return get_call(require_int(args, "track"))

    @lift_exceptions
    def setter(args: dict[str, Any]) -> DeviceCommand:
        return set_call(
            track=require_int(args, "track"),
            **{set_value_key: set_value_validator(args, set_value_key)},
        )

    return getter, setter


_handle_mixer_volume_get, _handle_mixer_volume_set = _make_mixer_field_handlers(
    lambda track: fl.mixer_volume_get(track=track),
    lambda **kw: fl.mixer_volume_set(**kw),
    "value",
    require_float,
)
_handle_mixer_pan_get, _handle_mixer_pan_set = _make_mixer_field_handlers(
    lambda track: fl.mixer_pan_get(track=track),
    lambda **kw: fl.mixer_pan_set(**kw),
    "value",
    require_float,
)
_handle_mixer_name_get, _handle_mixer_name_set = _make_mixer_field_handlers(
    lambda track: fl.mixer_name_get(track=track),
    lambda **kw: fl.mixer_name_set(**kw),
    "name",
    require_string,
)


@lift_exceptions
def _handle_mixer_mute(args: dict[str, Any]) -> DeviceCommand:
    """Toggle mute on a mixer track."""
    return fl.mixer_mute(track=require_int(args, "track"))


@lift_exceptions
def _handle_mixer_solo(args: dict[str, Any]) -> DeviceCommand:
    """Toggle solo on a mixer track."""
    return fl.mixer_solo(track=require_int(args, "track"))


@lift_exceptions
def _handle_mixer_arm(args: dict[str, Any]) -> DeviceCommand:
    """Arm or disarm a mixer track for recording."""
    return fl.mixer_arm(
        track=require_int(args, "track"),
        on=optional_bool(args, "on"),
    )


@lift_exceptions
def _handle_mixer_route_set(args: dict[str, Any]) -> DeviceCommand:
    """Set or unset a routing path between two mixer tracks."""
    return fl.mixer_route_set(
        src=require_int(args, "from"),
        dst=require_int(args, "to"),
        on=optional_bool(args, "on"),
    )


@lift_exceptions
def _handle_mixer_link_to_channel(args: dict[str, Any]) -> DeviceCommand:
    """Route a channel rack channel to a mixer track."""
    return fl.mixer_link_to_channel(
        track=require_int(args, "track"),
        channel=require_int(args, "channel"),
    )


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "mixer_list": _handle_mixer_list,
    "mixer_volume_get": _handle_mixer_volume_get,
    "mixer_volume_set": _handle_mixer_volume_set,
    "mixer_pan_get": _handle_mixer_pan_get,
    "mixer_pan_set": _handle_mixer_pan_set,
    "mixer_name_get": _handle_mixer_name_get,
    "mixer_name_set": _handle_mixer_name_set,
    "mixer_mute": _handle_mixer_mute,
    "mixer_solo": _handle_mixer_solo,
    "mixer_arm": _handle_mixer_arm,
    "mixer_route_set": _handle_mixer_route_set,
    "mixer_link_to_channel": _handle_mixer_link_to_channel,
}
