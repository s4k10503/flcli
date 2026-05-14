"""Interface adapter: transport CLI commands — playback, position, loop, undo / redo."""

from __future__ import annotations

import click

from flstudio_cli.shared.application.transport_modes import VALID_POSITION_MODES
from flstudio_cli.shared.presentation.cli_dispatch import _dispatch_command

_POSITION_MODE_CHOICES = click.Choice(sorted(VALID_POSITION_MODES))


# --- play / stop / record --------------------------------------------------


@click.command(name="play", help="Start playback.")
@click.pass_context
def _play_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "play")


@click.command(name="stop", help="Stop playback.")
@click.pass_context
def _stop_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "stop")


@click.command(name="record", help="Toggle recording.")
@click.pass_context
def _record_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "record")


# --- transport-position group ---------------------------------------------


@click.group("transport-position", help="Get or set the playhead position.")
def _position_group() -> None:
    pass


@_position_group.command("get", help="Get the current playhead position.")
@click.option(
    "--mode",
    "mode",
    type=_POSITION_MODE_CHOICES,
    default="beats",
    show_default=True,
    help="Position unit (beats, ticks, ms, abs-ticks).",
)
@click.pass_context
def _position_get_cmd(ctx: click.Context, mode: str) -> None:
    _dispatch_command(
        ctx,
        "transport_position",
        {"mode": mode},
        v2_command="transport_position_get",
    )


@_position_group.command("set", help="Set the playhead position.")
@click.argument("value", type=float)
@click.option(
    "--mode",
    "mode",
    type=_POSITION_MODE_CHOICES,
    default="beats",
    show_default=True,
    help="Position unit (beats, ticks, ms, abs-ticks).",
)
@click.pass_context
def _position_set_cmd(ctx: click.Context, value: float, mode: str) -> None:
    _dispatch_command(
        ctx,
        "transport_position",
        {"position": value, "mode": mode},
        v2_command="transport_position_set",
    )


# --- transport-loop group --------------------------------------------------


@click.group("transport-loop", help="Get or toggle the loop mode.")
def _loop_group() -> None:
    pass


@_loop_group.command("get", help="Get the current loop mode.")
@click.pass_context
def _loop_get_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "transport_loop", v2_command="transport_loop_get")


@_loop_group.command("toggle", help="Cycle the loop mode.")
@click.pass_context
def _loop_toggle_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "transport_loop", v2_command="transport_loop_toggle")


# --- undo / redo / undo-history --------------------------------------------


@click.command(name="undo", help="Undo the last action.")
@click.pass_context
def _undo_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "undo")


@click.command(name="redo", help="Redo the last undone action.")
@click.pass_context
def _redo_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "redo")


@click.command(
    name="undo-history",
    help="Show undo history summary (count and last entry).",
)
@click.pass_context
def _undo_history_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "undo_history")


CLI_COMMANDS: list[click.Command] = [
    _play_cmd,
    _stop_cmd,
    _record_cmd,
    _position_group,
    _loop_group,
    _undo_cmd,
    _redo_cmd,
    _undo_history_cmd,
]
