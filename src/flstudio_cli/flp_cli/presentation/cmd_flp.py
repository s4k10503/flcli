"""Interface adapter: ``flcli flp`` — offline FLP file operations via pyflp."""

from __future__ import annotations

import json
from typing import Any

import click

from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_dispatch import _dispatch_flp
from flstudio_cli.shared.presentation.cli_helpers import _fail, build_args_echo

Flp = Comp.flp


# --- module-private helpers ------------------------------------------------


def _resolve_notes_input(
    json_file: str | None,
    csv_source: str | None,
    args_echo: dict[str, Any],
) -> list[Any] | None:
    """Validate and parse the notes input for ``flp notes add``.

    Returns the parsed notes list, or ``None`` after emitting a failure
    envelope when the input is missing or unparsable.
    """
    if not json_file and not csv_source:
        _fail(
            "flp_notes_add",
            "either --from-json or --from-csv is required",
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return None
    try:
        if json_file:
            return Flp.parse_notes_json(json_file)
        if csv_source:
            return Flp.parse_notes_csv(csv_source)
    except FileNotFoundError as exc:
        _fail(
            "flp_notes_add",
            f"json file not found: {exc}",
            code=Env.CODE_NOT_FOUND,
            args=args_echo,
        )
        return None
    except (ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        _fail(
            "flp_notes_add",
            f"failed to parse notes: {exc}",
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return None
    return None


# --- click command surface -------------------------------------------------


@click.group("flp", help="Offline FLP file operations via pyflp.")
def group() -> None:
    pass


@group.command("info", help="Show basic info about an FLP file.")
@click.argument("path", type=str)
def info_cmd(path: str) -> None:
    _dispatch_flp(
        "flp_info",
        lambda: Flp.flp_info(path),
        {"path": path},
        path=path,
    )


@group.group("notes", help="Piano roll note operations on FLP files.")
def notes_group() -> None:
    pass


@notes_group.command("add", help="Add notes to a channel's piano roll.")
@click.argument("path", type=str)
@click.option("--channel", "-c", required=True, type=int)
@click.option("--pattern", "-p", type=int, default=None)
@click.option(
    "--from-json",
    "json_file",
    type=str,
    default=None,
    help="JSON file with notes array.",
)
@click.option(
    "--from-csv",
    "csv_source",
    type=str,
    default=None,
    help="CSV source ('-' for stdin).",
)
def notes_add_cmd(
    path: str,
    channel: int,
    pattern: int | None,
    json_file: str | None,
    csv_source: str | None,
) -> None:
    args_echo = build_args_echo({"path": path, "channel": channel}, pattern=pattern)
    notes = _resolve_notes_input(json_file, csv_source, args_echo)
    if notes is None:
        return

    _dispatch_flp(
        "flp_notes_add",
        lambda: Flp.flp_add_notes(path, channel, notes, pattern=pattern),
        args_echo,
        path=path,
    )


@notes_group.command("clear", help="Clear notes from a channel's piano roll.")
@click.argument("path", type=str)
@click.option("--channel", "-c", required=True, type=int)
@click.option("--pattern", "-p", type=int, default=None)
def notes_clear_cmd(path: str, channel: int, pattern: int | None) -> None:
    args_echo = build_args_echo({"path": path, "channel": channel}, pattern=pattern)
    _dispatch_flp(
        "flp_notes_clear",
        lambda: Flp.flp_clear_notes(path, channel, pattern=pattern),
        args_echo,
        path=path,
    )


@group.group("channel", help="Channel operations on FLP files.")
def channel_group() -> None:
    pass


@channel_group.command("rename", help="Rename a channel in an FLP file.")
@click.argument("path", type=str)
@click.option("--channel", "-c", required=True, type=int)
@click.argument("name", type=str)
def channel_rename_cmd(path: str, channel: int, name: str) -> None:
    _dispatch_flp(
        "flp_channel_rename",
        lambda: Flp.flp_channel_rename(path, channel, name),
        {"path": path, "channel": channel, "name": name},
        path=path,
    )


@group.group("pattern", help="Pattern operations on FLP files.")
def pattern_group() -> None:
    pass


@pattern_group.command("set-length", help="Set a pattern's length (in steps).")
@click.argument("path", type=str)
@click.option("--pattern", "-p", required=True, type=int)
@click.argument("length", type=int)
def pattern_set_length_cmd(path: str, pattern: int, length: int) -> None:
    _dispatch_flp(
        "flp_pattern_set_length",
        lambda: Flp.flp_pattern_set_length(path, pattern, length),
        {"path": path, "pattern": pattern, "length": length},
        path=path,
    )


@group.group("mixer", help="Mixer operations on FLP files.")
def mixer_group() -> None:
    pass


@mixer_group.command("route", help="Enable/disable a mixer send route.")
@click.argument("path", type=str)
@click.option(
    "--from", "from_track", required=True, type=int, help="Source track index."
)
@click.option(
    "--to", "to_track", required=True, type=int, help="Destination track index."
)
@click.option("--on/--off", "enabled", default=True, show_default=True)
def mixer_route_cmd(
    path: str,
    from_track: int,
    to_track: int,
    enabled: bool,
) -> None:
    _dispatch_flp(
        "flp_mixer_route",
        lambda: Flp.flp_mixer_route(
            path,
            from_track,
            to_track,
            enabled=enabled,
        ),
        {"path": path, "from": from_track, "to": to_track, "enabled": enabled},
        path=path,
    )


@group.group("clip", help="Playlist clip operations on FLP files.")
def clip_group() -> None:
    pass


@clip_group.command("create", help="Place a pattern clip on a playlist track.")
@click.argument("path", type=str)
@click.option("--track", "-t", required=True, type=int, help="Playlist track index.")
@click.option("--pattern", "-p", required=True, type=int, help="Pattern index.")
@click.option("--position", required=True, type=float, help="Start position (beats).")
@click.option("--length", type=float, default=None, help="Clip length (beats).")
def clip_create_cmd(
    path: str,
    track: int,
    pattern: int,
    position: float,
    length: float | None,
) -> None:
    args_echo = build_args_echo(
        {"path": path, "track": track, "pattern": pattern, "position": position},
        length=length,
    )
    _dispatch_flp(
        "flp_clip_create",
        lambda: Flp.flp_clip_create(
            path,
            track,
            pattern,
            position,
            length=length,
        ),
        args_echo,
        path=path,
    )


CLI_COMMANDS: list[click.Command] = [group]
