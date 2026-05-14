"""Use case: plugin batch handlers — list / params / param-get / param-set."""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.application.handler_args import (
    optional_int,
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
def _handle_plugin_list(args: dict[str, Any]) -> DeviceCommand:
    """List plugins loaded on a channel."""
    return fl.plugin_list(channel=require_int(args, "channel"))


@lift_exceptions
def _handle_plugin_params(args: dict[str, Any]) -> DeviceCommand:
    """List all parameters of a plugin on a channel."""
    return fl.plugin_params(
        channel=require_int(args, "channel"),
        slot=optional_int(args, "slot"),
        limit=optional_int(args, "limit"),
        offset=optional_int(args, "offset"),
    )


def _resolve_param_selector(args: dict[str, Any]) -> tuple[int | None, str | None]:
    """Validate that exactly one of ``param`` / ``param_name`` is supplied."""
    if "param" in args:
        return require_int(args, "param"), None
    if "param_name" in args:
        return None, require_string(args, "param_name")
    raise ValueError("either 'param' or 'param_name' is required")


@lift_exceptions
def _handle_plugin_param_get(args: dict[str, Any]) -> DeviceCommand:
    """Read the value of a single plugin parameter."""
    param, param_name = _resolve_param_selector(args)
    return fl.plugin_param_get(
        channel=require_int(args, "channel"),
        slot=optional_int(args, "slot"),
        param=param,
        param_name=param_name,
    )


@lift_exceptions
def _handle_plugin_param_set(args: dict[str, Any]) -> DeviceCommand:
    """Write a new value to a single plugin parameter."""
    param, param_name = _resolve_param_selector(args)
    return fl.plugin_param_set(
        channel=require_int(args, "channel"),
        value=require_float(args, "value"),
        slot=optional_int(args, "slot"),
        param=param,
        param_name=param_name,
    )


BATCH_HANDLERS: dict[str, BatchHandler] = {
    "plugin_list": _handle_plugin_list,
    "plugin_params": _handle_plugin_params,
    "plugin_param_get": _handle_plugin_param_get,
    "plugin_param_set": _handle_plugin_param_set,
}
