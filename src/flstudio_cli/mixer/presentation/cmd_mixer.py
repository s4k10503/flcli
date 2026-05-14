"""Interface adapter: mixer CLI commands — track volume, pan, name, mute / solo / arm, routing."""

from __future__ import annotations

from typing import Any

import click

from flstudio_cli.shared.presentation.cli_dispatch import (
    _dispatch_command,
    _dispatch_with_track_selector,
    _track_selector_options,
)


def _dispatch_track(
    ctx: click.Context,
    command: str,
    *,
    extra_args: dict[str, Any] | None = None,
) -> None:
    """Dispatch a mixer command resolved through the standard track selector.

    Every selector-using command in this module shares two patterns:

    * ``command_name`` and ``v2_command`` are the same string.
    * The four ``--track*`` flags from :func:`_track_selector_options`
      are forwarded unchanged.

    Click stores those four flags in ``ctx.params`` already, so this
    helper extracts them there and forwards them, keeping the per-command
    callbacks down to a single ``_dispatch_track(ctx, "<cmd>")`` call
    (plus ``extra_args`` for set-style commands).
    """
    params = ctx.params
    _dispatch_with_track_selector(
        ctx,
        command,
        track=params.get("track"),
        track_name=params.get("track_name"),
        track_query=params.get("track_query"),
        track_ref=params.get("track_ref"),
        extra_args=extra_args,
    )


@click.group("mixer", help="Mixer track operations (volume, pan, mute, solo, ...).")
def _mixer_group() -> None:
    pass


@_mixer_group.command("list", help="List all mixer tracks with current state.")
@click.pass_context
def _list_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "mixer_list")


@_mixer_group.group("volume", help="Get or set mixer track volume.")
def _volume_group() -> None:
    pass


@_volume_group.command("get", help="Get mixer track volume (0.0 - 1.0).")
@_track_selector_options
@click.pass_context
def _volume_get_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_volume_get")


@_volume_group.command("set", help="Set mixer track volume (0.0 - 1.0).")
@click.argument("value", type=float)
@_track_selector_options
@click.pass_context
def _volume_set_cmd(
    ctx: click.Context,
    value: float,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_volume_set", extra_args={"value": value})


@_mixer_group.group("pan", help="Get or set mixer track pan.")
def _pan_group() -> None:
    pass


@_pan_group.command("get", help="Get mixer track pan (-1.0 to 1.0).")
@_track_selector_options
@click.pass_context
def _pan_get_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_pan_get")


@_pan_group.command("set", help="Set mixer track pan (-1.0 to 1.0).")
@click.argument("value", type=float)
@_track_selector_options
@click.pass_context
def _pan_set_cmd(
    ctx: click.Context,
    value: float,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_pan_set", extra_args={"value": value})


@_mixer_group.group("name", help="Get or set mixer track name.")
def _name_group() -> None:
    pass


@_name_group.command("get", help="Get mixer track name.")
@_track_selector_options
@click.pass_context
def _name_get_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_name_get")


@_name_group.command("set", help="Set mixer track name (arbitrary UTF-8).")
@click.argument("name_value", metavar="NAME")
@_track_selector_options
@click.pass_context
def _name_set_cmd(
    ctx: click.Context,
    name_value: str,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_name_set", extra_args={"name": name_value})


@_mixer_group.command("mute", help="Toggle mute on a mixer track.")
@_track_selector_options
@click.pass_context
def _mute_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_mute")


@_mixer_group.command("solo", help="Toggle solo on a mixer track.")
@_track_selector_options
@click.pass_context
def _solo_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_solo")


@_mixer_group.command("arm", help="Arm / disarm a mixer track for recording.")
@_track_selector_options
@click.option("--on/--off", "arm_on", default=True, show_default=True)
@click.pass_context
def _arm_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
    arm_on: bool,
) -> None:
    _dispatch_track(ctx, "mixer_arm", extra_args={"on": arm_on})


@_mixer_group.command("route", help="Enable / disable a send route between tracks.")
@click.option("--from", "from_idx", required=True, type=int, help="Source track index.")
@click.option(
    "--to", "to_idx", required=True, type=int, help="Destination track index."
)
@click.option("--on/--off", "route_on", default=True, show_default=True)
@click.pass_context
def _route_cmd(
    ctx: click.Context,
    from_idx: int,
    to_idx: int,
    route_on: bool,
) -> None:
    _dispatch_command(
        ctx,
        "mixer_route_set",
        {"from": from_idx, "to": to_idx, "on": route_on},
    )


@_mixer_group.command(
    "link-to-channel",
    help=(
        "Route the channel rack channel CHANNEL to a mixer track. "
        "Both endpoints must be supplied — the device script selects "
        "them before issuing FL's linkTrackToChannel."
    ),
)
@_track_selector_options
@click.option(
    "--channel",
    "channel",
    type=int,
    required=True,
    help="Channel rack channel index (0-based) to route into the mixer track.",
)
@click.pass_context
def _link_to_channel_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
    channel: int,
) -> None:
    _dispatch_track(ctx, "mixer_link_to_channel", extra_args={"channel": channel})


CLI_COMMANDS: list[click.Command] = [_mixer_group]
