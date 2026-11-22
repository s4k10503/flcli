"""Interface adapter: mixer CLI commands — track volume, pan, name, mute / solo / arm, routing."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import click

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_dispatch import (
    _dispatch_command,
    _dispatch_with_track_selector,
    _send_v2,
    _track_selector_options,
)
from flstudio_cli.shared.presentation.cli_helpers import _emit_success, _fail
from flstudio_cli.shared.utility.seek import SeekError, seek


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


# --- built-in EQ, sends, stereo, polarity, meters ---------------------------


@_mixer_group.group("eq", help="Built-in three-band EQ of a mixer track.")
def _eq_group() -> None:
    pass


@_eq_group.command("get", help="Show every band: gain (dB), frequency (Hz), bandwidth.")
@_track_selector_options
@click.pass_context
def _eq_get_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_eq_get")


_SETTLE_OPTION = click.option(
    "--settle-ms",
    type=int,
    default=60,
    show_default=True,
    help="Wait after each set before reading back (FL applies it a moment later).",
)


class _Abort(Exception):
    """A round-trip failed (its envelope is already emitted) or this is a dry run."""


def _round_trip(
    ctx: click.Context, command: str, args: dict[str, Any]
) -> dict[str, Any]:
    got = _send_v2(ctx, command, args)
    if got is None:
        raise _Abort
    return got


def _settle(settle_ms: int) -> None:
    time.sleep(max(settle_ms, 0) / 1000)


@_eq_group.command(
    "set",
    help="Set one band of a track's built-in EQ. Give gain in dB (--gain-db) "
    "or normalised (--gain, 0.5 = 0 dB), frequency in Hz (--freq-hz) or "
    "normalised (--freq), and/or --bandwidth (0.0 - 1.0). Band 0 is the low "
    "shelf, 1 the peak, 2 the high shelf. dB and Hz are found by setting and "
    "reading back, so they take about a second each.",
)
@click.option("--track", "-t", required=True, type=int, help="Mixer track index.")
@click.option("--band", "-b", required=True, type=int, help="Band index (0 - 2).")
@click.option("--gain-db", type=float, default=None, help="Gain in dB (-18 - 18).")
@click.option("--gain", type=float, default=None, help="Gain, normalised (0.5 = 0 dB).")
@click.option("--freq-hz", type=float, default=None, help="Frequency in Hz.")
@click.option("--freq", type=float, default=None, help="Frequency, normalised.")
@click.option("--bandwidth", type=float, default=None, help="Bandwidth, normalised.")
@_SETTLE_OPTION
@click.pass_context
def _eq_set_cmd(
    ctx: click.Context,
    track: int,
    band: int,
    gain_db: float | None,
    gain: float | None,
    freq_hz: float | None,
    freq: float | None,
    bandwidth: float | None,
    settle_ms: int,
) -> None:
    command = "mixer_eq_set"
    args = {
        k: v
        for k, v in {
            "track": track,
            "band": band,
            "gain_db": gain_db,
            "gain": gain,
            "freq_hz": freq_hz,
            "freq": freq,
            "bandwidth": bandwidth,
        }.items()
        if v is not None
    }
    if (gain_db is not None and gain is not None) or (
        freq_hz is not None and freq is not None
    ):
        _fail(
            command,
            "give a gain and a frequency at most once each",
            code=Env.CODE_INVALID_ARGUMENT,
        )
        return
    plain = {k: args[k] for k in ("gain", "freq", "bandwidth") if k in args}
    if len(args) == 2:
        _fail(command, "nothing to set", code=Env.CODE_INVALID_ARGUMENT)
        return

    def read_band() -> dict[str, Any]:
        _settle(settle_ms)
        bands = _round_trip(ctx, "mixer_eq_get", {"track": track})["bands"]
        return next(b for b in bands if b["band"] == band)

    def seeker(key: str, shown: str) -> Callable[[float], float | None]:
        def read(value: float) -> float | None:
            _round_trip(ctx, command, {"track": track, "band": band, key: value})
            return float(read_band()[shown])

        return read

    try:
        if plain:
            _round_trip(ctx, command, {"track": track, "band": band, **plain})
        if gain_db is not None:
            seek(seeker("gain", "gain_db"), gain_db)
        if freq_hz is not None:
            seek(seeker("freq", "freq_hz"), freq_hz)
        result = read_band()
    except _Abort:
        return
    except SeekError as exc:
        _fail(command, str(exc), code=Env.CODE_INVALID_ARGUMENT, args=args)
        return
    _emit_success(command, args=args, result={"track": track, **result})


@_mixer_group.group("send", help="Send level between two tracks (sidechain sends too).")
def _send_group() -> None:
    pass


@_send_group.command("get", help="Show whether a send is on and its level.")
@click.option("--from", "from_idx", required=True, type=int, help="Source track index.")
@click.option(
    "--to", "to_idx", required=True, type=int, help="Destination track index."
)
@click.pass_context
def _send_get_cmd(ctx: click.Context, from_idx: int, to_idx: int) -> None:
    _dispatch_command(ctx, "mixer_send_get", {"from": from_idx, "to": to_idx})


@_send_group.command("set", help="Set a send level (0.0 - 1.0; 0.8 is 0 dB).")
@click.argument("level", type=float)
@click.option("--from", "from_idx", required=True, type=int, help="Source track index.")
@click.option(
    "--to", "to_idx", required=True, type=int, help="Destination track index."
)
@click.pass_context
def _send_set_cmd(ctx: click.Context, level: float, from_idx: int, to_idx: int) -> None:
    _dispatch_command(
        ctx, "mixer_send_set", {"from": from_idx, "to": to_idx, "level": level}
    )


@_mixer_group.group("stereo", help="Stereo separation of a mixer track.")
def _stereo_group() -> None:
    pass


@_stereo_group.command("get", help="Get stereo separation (-1.0 - 1.0).")
@_track_selector_options
@click.pass_context
def _stereo_get_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> None:
    _dispatch_track(ctx, "mixer_stereo_get")


@_stereo_group.command(
    "set",
    help="Set stereo separation (-1.0 - 1.0). As FL shows it: one end is mono, "
    "0 leaves the signal as it is.",
)
@click.argument("value", type=float)
@click.option("--track", "-t", required=True, type=int, help="Mixer track index.")
@_SETTLE_OPTION
@click.pass_context
def _stereo_set_cmd(
    ctx: click.Context, value: float, track: int, settle_ms: int
) -> None:
    command = "mixer_stereo_set"
    try:
        _round_trip(ctx, command, {"track": track, "value": value})
        _settle(settle_ms)
        result = _round_trip(ctx, "mixer_stereo_get", {"track": track})
    except _Abort:
        return
    _emit_success(command, args={"track": track, "value": value}, result=result)


@_mixer_group.command(
    "polarity", help="Show, or set with --on/--off, polarity inversion."
)
@_track_selector_options
@click.option("--on/--off", "polarity_on", default=None)
@click.pass_context
def _polarity_cmd(
    ctx: click.Context,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
    polarity_on: bool | None,
) -> None:
    extra = {} if polarity_on is None else {"on": polarity_on}
    _dispatch_track(ctx, "mixer_polarity", extra_args=extra)


@_mixer_group.command(
    "peaks",
    help="Read the peak meters right now (linear, 1.0 = 0 dBFS). Meaningful "
    "while the song plays; --track can be repeated.",
)
@click.option("--track", "-t", "tracks", type=int, multiple=True, help="Track index.")
@click.pass_context
def _peaks_cmd(ctx: click.Context, tracks: tuple[int, ...]) -> None:
    _dispatch_command(ctx, "mixer_peaks", {"tracks": list(tracks)} if tracks else {})


CLI_COMMANDS: list[click.Command] = [_mixer_group]
