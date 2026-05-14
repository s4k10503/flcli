"""Interface adapter: plugin CLI commands — list / params / param-get / param-set."""

from __future__ import annotations

from typing import Any

import click

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_dispatch import _dispatch_command
from flstudio_cli.shared.presentation.cli_helpers import _fail, build_args_echo


def _build_param_v2_args(
    command: str,
    *,
    channel: int,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Validate the param selector and return the merged ``v2_args`` dict.

    Emits a typed failure envelope and returns ``None`` if neither
    ``--param`` nor ``--param-name`` was supplied; caller should
    ``return`` immediately on that signal.
    """
    if param_index is None and param_name is None:
        _fail(
            command,
            "either --param or --param-name is required",
            code=Env.CODE_INVALID_ARGUMENT,
        )
        return None
    args: dict[str, Any] = {"channel": channel, **(extra or {})}
    if slot is not None:
        args["slot"] = slot
    if param_index is not None:
        args["param"] = param_index
    else:
        args["param_name"] = param_name
    return args


@click.group("plugin", help="Plugin inspection and parameter control.")
def _plugin_group() -> None:
    pass


@_plugin_group.command(
    "list", help="List plugins on a channel (native + effect slots)."
)
@click.option("--channel", "-c", required=True, type=int, help="Channel index.")
@click.pass_context
def _list_cmd(ctx: click.Context, channel: int) -> None:
    _dispatch_command(ctx, "plugin_list", {"channel": channel})


@_plugin_group.command(
    "params",
    help="Enumerate plugin parameters with name, value, and display string. "
    "Heavy plugins (Sytrus, Harmor, ...) expose hundreds of params, so the "
    "command paginates by default; use --limit/--offset to scan further.",
)
@click.option("--channel", "-c", required=True, type=int, help="Channel index.")
@click.option(
    "--slot",
    "-s",
    type=int,
    default=None,
    help="Effect slot index (-1 = native plugin, default).",
)
@click.option(
    "--limit",
    type=int,
    default=64,
    show_default=True,
    help="Max parameters to return in this call. Pass 0 for no cap "
    "(only safe on small plugins -- larger plugins will time out).",
)
@click.option(
    "--offset",
    type=int,
    default=0,
    show_default=True,
    help="Starting parameter index (for paginating through heavy plugins).",
)
@click.pass_context
def _params_cmd(
    ctx: click.Context,
    channel: int,
    slot: int | None,
    limit: int,
    offset: int,
) -> None:
    v2_args = build_args_echo(
        {"channel": channel, "limit": limit, "offset": offset},
        slot=slot,
    )
    # Heavy plugins (Sytrus, Harmor, etc.) expose hundreds of params and
    # the per-param API calls add up — 5 s is too tight. Allow 30 s.
    _dispatch_command(ctx, "plugin_params", v2_args, timeout_ms=30000)


@_plugin_group.group("param", help="Get or set a single plugin parameter.")
def _param_group() -> None:
    pass


@_param_group.command(
    "get",
    help="Get a single plugin parameter (normalised value + display string).",
)
@click.option("--channel", "-c", required=True, type=int, help="Channel index.")
@click.option(
    "--slot",
    "-s",
    type=int,
    default=None,
    help="Effect slot index (-1 = native plugin).",
)
@click.option(
    "--param", "-p", "param_index", type=int, default=None, help="Parameter index."
)
@click.option(
    "--param-name",
    "-n",
    "param_name",
    type=str,
    default=None,
    help="Parameter name (string match).",
)
@click.pass_context
def _param_get_cmd(
    ctx: click.Context,
    channel: int,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
) -> None:
    v2_args = _build_param_v2_args(
        "plugin_param_get",
        channel=channel,
        slot=slot,
        param_index=param_index,
        param_name=param_name,
    )
    if v2_args is None:
        return
    _dispatch_command(ctx, "plugin_param_get", v2_args)


@_param_group.command(
    "set",
    help="Set a plugin parameter value (0.0 - 1.0).",
)
@click.argument("value", type=float)
@click.option("--channel", "-c", required=True, type=int, help="Channel index.")
@click.option(
    "--slot",
    "-s",
    type=int,
    default=None,
    help="Effect slot index (-1 = native plugin).",
)
@click.option(
    "--param", "-p", "param_index", type=int, default=None, help="Parameter index."
)
@click.option(
    "--param-name",
    "-n",
    "param_name",
    type=str,
    default=None,
    help="Parameter name (string match).",
)
@click.pass_context
def _param_set_cmd(
    ctx: click.Context,
    value: float,
    channel: int,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
) -> None:
    v2_args = _build_param_v2_args(
        "plugin_param_set",
        channel=channel,
        slot=slot,
        param_index=param_index,
        param_name=param_name,
        extra={"value": value},
    )
    if v2_args is None:
        return
    _dispatch_command(ctx, "plugin_param_set", v2_args)


CLI_COMMANDS: list[click.Command] = [_plugin_group]
