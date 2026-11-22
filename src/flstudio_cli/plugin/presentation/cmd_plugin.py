"""Interface adapter: plugin CLI commands — list / params / param get|set|map|seek / preset."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import click

from flstudio_cli.plugin.application import param_search
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_dispatch import _dispatch_command, _send_v2
from flstudio_cli.shared.presentation.cli_helpers import (
    _emit_success,
    _fail,
    build_args_echo,
)


def _resolve_target(
    command: str, channel: int | None, track: int | None, slot: int | None
) -> tuple[int, int | None] | None:
    """Map ``--channel`` / ``--track`` to FL's (index, slot) pair.

    FL addresses an effect by the *mixer track* index plus a slot, and a
    channel's own plugin by the channel index with slot -1. ``--track``
    names the mixer track directly and defaults to slot 0, so a mixer effect
    no longer has to be reached through ``--channel <track number>``.
    Emits a failure envelope and returns ``None`` unless exactly one of the
    two is given.
    """
    if (channel is None) == (track is None):
        _fail(
            command,
            "give exactly one of --channel or --track",
            code=Env.CODE_INVALID_ARGUMENT,
        )
        return None
    if track is not None:
        if slot is not None and slot < 0:
            _fail(
                command,
                "--track needs an effect slot (0 or more)",
                code=Env.CODE_INVALID_ARGUMENT,
            )
            return None
        return track, 0 if slot is None else slot
    assert channel is not None
    return channel, slot


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
    "list", help="List plugins on a channel (native + effect slots) or a mixer track."
)
@click.option("--channel", "-c", type=int, default=None, help="Channel index.")
@click.option(
    "--track",
    "-t",
    type=int,
    default=None,
    help="Mixer track index, for an effect in its slots (instead of --channel).",
)
@click.pass_context
def _list_cmd(ctx: click.Context, channel: int | None, track: int | None) -> None:
    if (channel is None) == (track is None):
        _fail(
            "plugin_list",
            "give exactly one of --channel or --track",
            code=Env.CODE_INVALID_ARGUMENT,
        )
        return
    if track is not None:
        _dispatch_command(ctx, "plugin_list", {"channel": track, "mixer": True})
    else:
        _dispatch_command(ctx, "plugin_list", {"channel": channel})


@_plugin_group.command(
    "params",
    help="Enumerate plugin parameters with name, value, and display string. "
    "Heavy plugins (Sytrus, Harmor, ...) expose hundreds of params, so the "
    "command paginates by default; use --limit/--offset to scan further.",
)
@click.option("--channel", "-c", type=int, default=None, help="Channel index.")
@click.option(
    "--track",
    "-t",
    type=int,
    default=None,
    help="Mixer track index, for an effect in its slots (instead of --channel).",
)
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
    channel: int | None,
    track: int | None,
    slot: int | None,
    limit: int,
    offset: int,
) -> None:
    target = _resolve_target("plugin_params", channel, track, slot)
    if target is None:
        return
    channel, slot = target
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
@click.option("--channel", "-c", type=int, default=None, help="Channel index.")
@click.option(
    "--track",
    "-t",
    type=int,
    default=None,
    help="Mixer track index, for an effect in its slots (instead of --channel).",
)
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
    channel: int | None,
    track: int | None,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
) -> None:
    target = _resolve_target("plugin_param_get", channel, track, slot)
    if target is None:
        return
    channel, slot = target
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
@click.option("--channel", "-c", type=int, default=None, help="Channel index.")
@click.option(
    "--track",
    "-t",
    type=int,
    default=None,
    help="Mixer track index, for an effect in its slots (instead of --channel).",
)
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
    channel: int | None,
    track: int | None,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
) -> None:
    target = _resolve_target("plugin_param_set", channel, track, slot)
    if target is None:
        return
    channel, slot = target
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


_TARGET_OPTIONS = [
    click.option("--channel", "-c", type=int, default=None, help="Channel index."),
    click.option(
        "--track",
        "-t",
        type=int,
        default=None,
        help="Mixer track index, for an effect in its slots (instead of --channel).",
    ),
    click.option(
        "--slot",
        "-s",
        type=int,
        default=None,
        help="Effect slot index (-1 = native plugin).",
    ),
    click.option(
        "--param", "-p", "param_index", type=int, default=None, help="Parameter index."
    ),
    click.option(
        "--param-name",
        "-n",
        "param_name",
        type=str,
        default=None,
        help="Parameter name (string match).",
    ),
    click.option(
        "--settle-ms",
        type=int,
        default=60,
        show_default=True,
        help="Wait after each set before reading the display back. VST3/CLAP "
        "plugins update their display a moment after the value changes.",
    ),
]


def _target_options(fn: Callable[..., Any]) -> Callable[..., Any]:
    for option in reversed(_TARGET_OPTIONS):
        fn = option(fn)
    return fn


class _Abort(Exception):
    """A round-trip failed (its envelope is already emitted) or this is a dry run."""


def _make_probe(
    ctx: click.Context, command: str, base: dict[str, Any], settle_ms: int
) -> Callable[[float], str]:
    """``probe(value)`` sets the parameter, waits, and returns its display."""

    def probe(value: float) -> str:
        if _send_v2(ctx, "plugin_param_set", {**base, "value": value}) is None:
            raise _Abort
        time.sleep(max(settle_ms, 0) / 1000)
        got = _send_v2(ctx, "plugin_param_get", base)
        if got is None:
            raise _Abort
        return str(got.get("display", ""))

    return probe


def _current(ctx: click.Context, base: dict[str, Any]) -> dict[str, Any] | None:
    return _send_v2(ctx, "plugin_param_get", base)


def _param_base(
    command: str,
    channel: int | None,
    track: int | None,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
) -> dict[str, Any] | None:
    target = _resolve_target(command, channel, track, slot)
    if target is None:
        return None
    index, slot = target
    return _build_param_v2_args(
        command,
        channel=index,
        slot=slot,
        param_index=param_index,
        param_name=param_name,
    )


@_param_group.command(
    "map",
    help="Sweep a parameter over 0..1 and list what the plugin shows at each "
    "step (e.g. 0.25 -> '150 Hz'), then put the value back. Use it to learn "
    "what a parameter does before setting it.",
)
@_target_options
@click.option(
    "--steps",
    type=click.IntRange(1, 256),
    default=16,
    show_default=True,
    help="Number of intervals (steps + 1 points).",
)
@click.pass_context
def _param_map_cmd(
    ctx: click.Context,
    channel: int | None,
    track: int | None,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
    settle_ms: int,
    steps: int,
) -> None:
    command = "plugin_param_map"
    base = _param_base(command, channel, track, slot, param_index, param_name)
    if base is None:
        return
    before = _current(ctx, base)
    if before is None:
        return
    probe = _make_probe(ctx, command, base, settle_ms)
    try:
        points = param_search.sweep(probe, steps)
        probe(float(before["value"]))
    except _Abort:
        return
    _emit_success(
        command,
        args={**base, "steps": steps},
        result={
            "name": before.get("name"),
            "restored": {"value": before["value"], "display": before.get("display")},
            "points": points,
        },
    )


@_param_group.command(
    "seek",
    help="Set a parameter by what the plugin shows: a number in its unit "
    "(--to 150 for '150 Hz', --to -6 for '-6.0 dB', kHz counts as 1000) "
    "or a label (--label 'Low Tide'). Numbers need a display that only "
    "rises or only falls over 0..1.",
)
@_target_options
@click.option("--to", "target", type=float, default=None, help="Target number.")
@click.option("--label", type=str, default=None, help="Target label (exact text).")
@click.pass_context
def _param_seek_cmd(
    ctx: click.Context,
    channel: int | None,
    track: int | None,
    slot: int | None,
    param_index: int | None,
    param_name: str | None,
    settle_ms: int,
    target: float | None,
    label: str | None,
) -> None:
    command = "plugin_param_seek"
    if (target is None) == (label is None):
        _fail(
            command,
            "give exactly one of --to or --label",
            code=Env.CODE_INVALID_ARGUMENT,
        )
        return
    base = _param_base(command, channel, track, slot, param_index, param_name)
    if base is None:
        return
    before = _current(ctx, base)
    if before is None:
        return
    probe = _make_probe(ctx, command, base, settle_ms)
    try:
        if target is not None:
            value, display = param_search.bisect_numeric(probe, target)
        else:
            assert label is not None
            value, display = param_search.find_label(probe, label)
    except _Abort:
        return
    except ValueError as exc:
        try:
            probe(float(before["value"]))
        except _Abort:
            return
        _fail(
            command,
            str(exc),
            code=Env.CODE_INVALID_ARGUMENT,
            args={**base, "to": target, "label": label},
        )
        return
    _emit_success(
        command,
        args={**base, "to": target, "label": label},
        result={
            "name": before.get("name"),
            "value": round(value, 6),
            "display": display.strip(),
            "previous": {"value": before["value"], "display": before.get("display")},
        },
    )


@_plugin_group.command(
    "preset",
    help="Step to the plugin's next or previous preset (FL's own preset list).",
)
@click.argument("direction", type=click.Choice(["next", "prev"]))
@click.option("--channel", "-c", type=int, default=None, help="Channel index.")
@click.option(
    "--track",
    "-t",
    type=int,
    default=None,
    help="Mixer track index, for an effect in its slots (instead of --channel).",
)
@click.option(
    "--slot",
    "-s",
    type=int,
    default=None,
    help="Effect slot index (-1 = native plugin).",
)
@click.pass_context
def _preset_cmd(
    ctx: click.Context,
    direction: str,
    channel: int | None,
    track: int | None,
    slot: int | None,
) -> None:
    target = _resolve_target("plugin_preset", channel, track, slot)
    if target is None:
        return
    index, slot = target
    _dispatch_command(
        ctx,
        "plugin_preset",
        build_args_echo({"channel": index, "direction": direction}, slot=slot),
    )


CLI_COMMANDS: list[click.Command] = [_plugin_group]
