"""Interface adapter: ``flcli`` piano-roll, melody, and import-trigger commands.

IO/effect dependencies (the :class:`PianoRollIO` bundle, the
``os_automation`` module, the ``read_midi_file`` callable, and the
piano-roll note-sink factory) are resolved through ``ctx.obj`` —
published by the composition root in :mod:`flstudio_cli.__main__` —
so presentation never binds to :mod:`flstudio_cli.shared.composition`
at import time.
"""

from __future__ import annotations

import subprocess
from typing import Any, Literal

import click

from flstudio_cli.piano_roll.application.realtime_record import execute_realtime_record
from flstudio_cli.piano_roll.domain.edit_ops import (
    Delete,
    EditOp,
    EditPlan,
    NoteUpdate,
    ScaleLength,
    SetFields,
    Shift,
    Transpose,
    apply_edits,
)
from flstudio_cli.piano_roll.presentation.melody_helpers import (
    _load_melody_or_fail,
    _notes_to_dicts,
)
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.automation_errors import InvalidShortcut
from flstudio_cli.shared.presentation.cli_dispatch import (
    _dispatch_command,
    _send_v2,
    resolve_deps,
)
from flstudio_cli.shared.presentation.cli_helpers import (
    _emit_success,
    _fail,
    build_args_echo,
)
from flstudio_cli.shared.utility.outcome import Err, Ok

# ---------------------------------------------------------------------------
# read-midi (JSON / CSV preview of a Standard MIDI File)
# ---------------------------------------------------------------------------


@click.command(
    "read-midi",
    help="Parse a Standard MIDI File and print its notes as JSON.",
)
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--track",
    "track_index",
    type=int,
    default=None,
    help="Only read the given track index (default: merge all tracks).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    show_default=True,
    help="'csv' emits the pitch,velocity,length,position lines Note.parse accepts.",
)
@click.pass_context
def read_midi_cmd(
    ctx: click.Context,
    path: str,
    track_index: int | None,
    output_format: Literal["json", "csv"],
) -> None:
    args_echo = build_args_echo(
        {"path": path, "format": output_format}, track=track_index
    )
    read_midi_file = ctx.obj["read_midi_file"]
    try:
        notes = read_midi_file(path, track_index=track_index)
    except FileNotFoundError as exc:
        _fail(
            "read_midi",
            f"failed to read midi file: {exc}",
            code=Env.CODE_NOT_FOUND,
            args=args_echo,
        )
        return
    except (OSError, ValueError) as exc:
        _fail(
            "read_midi",
            f"failed to read midi file: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    if output_format == "csv":
        for note in notes:
            click.echo(
                f"{int(note.pitch)},{int(note.velocity)},"
                f"{float(note.length)},{float(note.position)}"
            )
        return
    _emit_success(
        "read_midi",
        args=args_echo,
        result={
            "path": path,
            "count": len(notes),
            "notes": _notes_to_dicts(notes),
        },
    )


# ---------------------------------------------------------------------------
# step-melody (write notes to step grid via SysEx)
# ---------------------------------------------------------------------------


@click.command(
    "step-melody",
    help="Write a melody onto the selected channel's STEP GRID via SysEx. "
    "Each note is quantised to 1/16 steps. SOURCE is a file path; "
    "'-' for stdin.",
)
@click.argument("source", type=str, default="-")
@click.pass_context
def step_melody_cmd(ctx: click.Context, source: str) -> None:
    args_echo = {"source": source}
    notes = _load_melody_or_fail("step_melody", source, args_echo)
    if notes is None:
        return
    _dispatch_command(
        ctx,
        "step_melody",
        {"notes": _notes_to_dicts(notes)},
        cli_args={"source": source, "count": len(notes)},
    )


# ---------------------------------------------------------------------------
# queue-piano-roll (write a queue file for flcli_import.pyscript)
# ---------------------------------------------------------------------------


@click.command(
    "queue-piano-roll",
    help="Queue a melody for the flcli_import Piano Roll Script.",
)
@click.argument("source", type=str, default="-")
@click.option(
    "--queue-file", "queue_file", default=None, help="Override the JSON queue path."
)
@click.option(
    "--clear/--no-clear",
    "clear_existing",
    default=False,
    show_default=True,
    help="Have the Piano Roll Script delete existing notes first.",
)
@click.option(
    "--auto-trigger/--no-auto-trigger",
    "auto_trigger",
    default=False,
    show_default=True,
    help="Automatically trigger flcli_import via OS automation.",
)
@click.option(
    "--shortcut",
    default=None,
    help="Keyboard shortcut to send. Default per platform: "
    "ctrl+alt+i (Windows/Linux) bound to flcli_import via right-click; "
    "cmd+alt+y (macOS) replays the last Piano Roll script (run "
    "flcli_import manually once first to prime it).",
)
@click.option(
    "--channel",
    "target_channel",
    type=int,
    default=None,
    help=(
        "Channel rack index to receive the import. The device script "
        "selects this channel and opens its Piano Roll before the queue "
        "file is written, so the user doesn't have to double-click the "
        "channel manually before running flcli_import."
    ),
)
@click.pass_context
def queue_piano_roll_cmd(
    ctx: click.Context,
    source: str,
    queue_file: str | None,
    clear_existing: bool,
    auto_trigger: bool,
    shortcut: str | None,
    target_channel: int | None,
) -> None:
    pr_io = ctx.obj["piano_roll_io"]
    os_automation = ctx.obj["os_automation"]
    args_echo = build_args_echo(
        {"source": source, "clear_existing": clear_existing},
        queue_file=queue_file,
        auto_trigger=True if auto_trigger else None,
        shortcut=(shortcut or os_automation.default_shortcut())
        if auto_trigger
        else None,
        channel=target_channel,
    )
    notes = _load_melody_or_fail("queue_piano_roll", source, args_echo)
    if notes is None:
        return
    if target_channel is not None:
        focus_response = _send_v2(
            ctx,
            "focus_channel_editor",
            {"channel": target_channel, "window": "piano_roll"},
        )
        if focus_response is None:
            # Dry-run already emitted the preview; the actual send_v2
            # also emits a failure envelope on transport error, in
            # which case the SystemExit aborts this command.
            return
    try:
        written_path = pr_io.write_queue_file(
            notes,
            path=queue_file,
            clear_existing=clear_existing,
        )
    except OSError as exc:
        _fail(
            "queue_piano_roll",
            f"failed to write queue file: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    result: dict[str, Any] = {
        "count": len(notes),
        "queue_file": written_path,
        "next_step": "In FL Studio, open the Piano Roll and run "
        "Tools → Scripts → flcli_import.",
    }
    if auto_trigger:
        dry_run = bool(ctx.obj and ctx.obj.get("dry_run"))
        match os_automation.get_trigger(shortcut, dry_run=dry_run):
            case Ok(trigger):
                pass
            case Err(InvalidShortcut(message=message)):
                _fail(
                    "queue_piano_roll",
                    f"invalid shortcut: {message}",
                    code=Env.CODE_INVALID_ARGUMENT,
                    args=args_echo,
                )
                return
        try:
            trigger.trigger()
            if trigger.verify(written_path):
                result["auto_triggered"] = True
                result["next_step"] = "Notes imported automatically."
            else:
                result["auto_triggered"] = False
                result["next_step"] = (
                    "Auto-trigger sent but queue file still present. Check FL Studio."
                )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            _fail(
                "queue_piano_roll",
                f"auto-trigger failed: {exc}",
                code=Env.CODE_AUTOMATION_FAILED,
                args=args_echo,
                details={"queue_file": written_path, "count": len(notes)},
                hint="The queue file was written; trigger the import "
                "manually via Tools → Scripts → flcli_import.",
            )
            return
    _emit_success("queue_piano_roll", args=args_echo, result=result)


# ---------------------------------------------------------------------------
# piano-roll-show / piano-roll-edit (offline export → queue round-trip)
# ---------------------------------------------------------------------------


_SET_FIELD_NAMES: frozenset[str] = frozenset(
    {"pitch", "velocity", "length", "position"}
)


def _parse_indices(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(token) for token in raw.split(",") if token.strip()]


def _parse_set_assignment(raw: str) -> SetFields:
    """Parse ``INDEX:field=value[,field=value...]`` into a typed ``SetFields`` op.

    Unknown field names are rejected at parse time (parse, don't
    validate); the resulting :class:`NoteUpdate` only carries values
    for the fields the user actually named.
    """
    if ":" not in raw:
        raise click.BadParameter(
            f"--set expects 'INDEX:field=value[,field=value...]', got {raw!r}"
        )
    index_str, rest = raw.split(":", 1)
    fields: dict[str, float] = {}
    for assignment in rest.split(","):
        assignment = assignment.strip()
        if not assignment:
            continue
        if "=" not in assignment:
            raise click.BadParameter(
                f"--set field must be 'field=value', got {assignment!r}"
            )
        key, value = assignment.split("=", 1)
        key = key.strip()
        if key not in _SET_FIELD_NAMES:
            raise click.BadParameter(
                f"unknown note field {key!r}; "
                f"expected any of {sorted(_SET_FIELD_NAMES)}"
            )
        fields[key] = float(value.strip())
    update = NoteUpdate(
        pitch=int(fields["pitch"]) if "pitch" in fields else None,
        velocity=int(fields["velocity"]) if "velocity" in fields else None,
        length=fields.get("length"),
        position=fields.get("position"),
    )
    return SetFields(index=int(index_str), update=update)


@click.command(
    "piano-roll-edit",
    help="Apply pinpoint edits to the exported Piano Roll notes and queue "
    "the result for flcli_import.pyscript.",
)
@click.option("--export-file", "export_file", default=None)
@click.option("--queue-file", "queue_file", default=None)
@click.option(
    "--delete", "delete_raw", default=None, help="Comma-separated indices to remove."
)
@click.option(
    "--set",
    "set_raw",
    multiple=True,
    help="'INDEX:field=value[,field=value...]'. Repeatable.",
)
@click.option("--transpose", type=int, default=0, show_default=True)
@click.option("--shift", type=float, default=0.0, show_default=True)
@click.option("--scale-length", type=float, default=1.0, show_default=True)
@click.option("--only", "only_raw", default=None)
@click.option("--clear/--no-clear", "clear_existing", default=True, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def piano_roll_edit_cmd(
    ctx: click.Context,
    export_file: str | None,
    queue_file: str | None,
    delete_raw: str | None,
    set_raw: tuple[str, ...],
    transpose: int,
    shift: float,
    scale_length: float,
    only_raw: str | None,
    clear_existing: bool,
    dry_run: bool,
) -> None:
    pr_io = ctx.obj["piano_roll_io"]
    args_echo = build_args_echo(
        {
            "transpose": transpose,
            "shift": shift,
            "scale_length": scale_length,
            "clear_existing": clear_existing,
            "dry_run": dry_run,
        },
        export_file=export_file,
        queue_file=queue_file,
        delete=delete_raw,
        set=list(set_raw) if set_raw else None,
        only=only_raw,
    )
    try:
        notes = pr_io.read_exported_notes(export_file)
    except FileNotFoundError as exc:
        _fail(
            "piano_roll_edit",
            f"failed to read export: {exc}",
            code=Env.CODE_NOT_FOUND,
            args=args_echo,
            hint="run flcli_export in FL Studio first.",
        )
        return
    except (OSError, ValueError, KeyError) as exc:
        _fail(
            "piano_roll_edit",
            f"failed to read export: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    try:
        only_set = frozenset(_parse_indices(only_raw)) if only_raw is not None else None
        ops: list[EditOp] = []
        delete_indices = frozenset(_parse_indices(delete_raw))
        if delete_indices:
            ops.append(Delete(indices=delete_indices))
        ops.extend(_parse_set_assignment(raw) for raw in set_raw)
        if transpose != 0:
            ops.append(Transpose(semitones=transpose, only=only_set))
        if shift != 0.0:
            ops.append(Shift(beats=shift, only=only_set))
        if scale_length != 1.0:
            ops.append(ScaleLength(factor=scale_length, only=only_set))
        plan = EditPlan(ops=tuple(ops))
        edited = apply_edits(notes, plan)
    except (ValueError, TypeError, click.BadParameter) as exc:
        _fail(
            "piano_roll_edit",
            f"edit failed: {exc}",
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return
    edited_payload = _notes_to_dicts(edited)
    if dry_run:
        _emit_success(
            "piano_roll_edit",
            args=args_echo,
            result={
                "dry_run": True,
                "count": len(edited),
                "notes": edited_payload,
            },
        )
        return
    try:
        written_path = pr_io.write_queue_file(
            edited,
            path=queue_file,
            clear_existing=clear_existing,
        )
    except OSError as exc:
        _fail(
            "piano_roll_edit",
            f"failed to write queue: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    _emit_success(
        "piano_roll_edit",
        args=args_echo,
        result={
            "count": len(edited),
            "queue_file": written_path,
            "clear_existing": clear_existing,
            "next_step": "run flcli_import in FL Studio.",
        },
    )


# ---------------------------------------------------------------------------
# piano-roll (realtime recording into the piano roll)
# ---------------------------------------------------------------------------


@click.command(
    "piano-roll",
    help="Record a melody into the piano roll of the selected channel "
    "via realtime MIDI input.",
)
@click.argument("source", type=str, default="-")
@click.option("--bpm", type=float, default=120.0, show_default=True)
@click.option("--lead-in", type=float, default=0.5, show_default=True)
@click.option("--auto-transport/--no-auto-transport", default=True, show_default=True)
@click.pass_context
def piano_roll_cmd(
    ctx: click.Context,
    source: str,
    bpm: float,
    lead_in: float,
    auto_transport: bool,
) -> None:
    args_echo = {
        "source": source,
        "bpm": bpm,
        "lead_in": lead_in,
        "auto_transport": auto_transport,
    }
    notes = _load_melody_or_fail("piano_roll", source, args_echo)
    if notes is None:
        return

    execute_realtime_record(
        resolve_deps(ctx),
        notes,
        bpm=bpm,
        lead_in=lead_in,
        auto_transport=auto_transport,
        open_note_sink=ctx.obj["open_piano_roll_note_sink"],
        port_name=ctx.obj["port"],
        args_echo=args_echo,
    )


# ---------------------------------------------------------------------------
# piano-roll-trigger (auto-trigger setup info)
# ---------------------------------------------------------------------------


@click.group("piano-roll-trigger", help="Manage the auto-trigger shortcut.")
def trigger_group() -> None:
    pass


@trigger_group.command(
    "setup",
    help="Display setup instructions for the auto-trigger shortcut.",
)
@click.option(
    "--shortcut",
    default=None,
    help="The keyboard shortcut to configure. Defaults to ctrl+alt+i "
    "on Windows/Linux and cmd+alt+y (re-run last script) on macOS.",
)
@click.pass_context
def trigger_setup_cmd(ctx: click.Context, shortcut: str | None) -> None:
    args_echo = {"shortcut": shortcut}
    os_automation = ctx.obj["os_automation"]
    try:
        info = os_automation.setup_instructions(shortcut)
    except ValueError as exc:
        _fail(
            "piano_roll_trigger_setup",
            str(exc),
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return
    _emit_success("piano_roll_trigger_setup", args=args_echo, result=info)


CLI_COMMANDS: list[click.Command] = [
    read_midi_cmd,
    step_melody_cmd,
    queue_piano_roll_cmd,
    piano_roll_edit_cmd,
    piano_roll_cmd,
    trigger_group,
]
