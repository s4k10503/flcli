"""Interface adapter: state commands — ``ports``, ``ping``, ``doctor``, ``snapshot``, ``diff``,
``state``, ``piano-roll-show``.

IO/effect dependencies (the :class:`PianoRollIO` bundle and the
:class:`DoctorEffects` bundle) are resolved through ``ctx.obj`` —
published by the composition root in :mod:`flstudio_cli.__main__` —
so presentation never reads ``shared.composition.PRODUCTION_*`` at
import time or inside command bodies.
"""

from __future__ import annotations

from typing import Any, Literal

import click

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_dispatch import _send_v2, resolve_deps
from flstudio_cli.shared.presentation.cli_helpers import (
    DEFAULT_STATE_THROTTLE_MS,
    PORT_HINT,
    _emit_success,
    _fail,
    build_args_echo,
)
from flstudio_cli.shared.utility.outcome import Err, Ok
from flstudio_cli.state.application import doctor as Doc
from flstudio_cli.state.application import snapshot_compare as SnapCmp
from flstudio_cli.state.application.live_state import try_fetch_snapshot


@click.command("ports", help="List available MIDI output ports.")
@click.pass_context
def ports_cmd(ctx: click.Context) -> None:
    _emit_success(
        "ports",
        result={"ports": ctx.obj["doctor_effects"].list_output_ports()},
    )


@click.command(
    "ping",
    help="Verify the CLI can find a virtual MIDI port matching "
    "--port. Exit code 10 if the port is not visible.",
)
@click.pass_context
def ping_cmd(ctx: click.Context) -> None:
    diagnostic = Doc.check_midi_port(
        ctx.obj["port"],
        list_output_ports=ctx.obj["doctor_effects"].list_output_ports,
    )
    if not diagnostic.ok:
        _fail(
            "ping",
            diagnostic.message,
            code=Env.CODE_PORT_NOT_FOUND,
            hint=PORT_HINT,
            details=dict(diagnostic.details),
        )
        return
    _emit_success(
        "ping",
        result={
            "port": diagnostic.details.get("matched", [None])[0],
            "available": diagnostic.details.get("available", []),
        },
    )


@click.command(
    "doctor",
    help="Run health checks (MIDI port, piano-roll queue/export) "
    "and return a structured report.",
)
@click.option(
    "--queue-file",
    "queue_file",
    default=None,
    help="Override the pending queue file path.",
)
@click.option(
    "--export-file",
    "export_file",
    default=None,
    help="Override the piano-roll export file path.",
)
@click.pass_context
def doctor_cmd(
    ctx: click.Context,
    queue_file: str | None,
    export_file: str | None,
) -> None:
    # Doctor only checks for section presence/shape, not freshness, so we
    # leave throttle_ms at the device-side default and avoid forcing a
    # full ~1500-API-call rebuild on every doctor run.
    snapshot = try_fetch_snapshot(resolve_deps(ctx))
    diagnostics = Doc.collect_diagnostics(
        effects=ctx.obj["doctor_effects"],
        port_name=ctx.obj["port"],
        queue_path=queue_file,
        export_path=export_file,
        snapshot=snapshot,
    )
    overall = Doc.overall_ok(diagnostics)
    report = {
        "overall_ok": overall,
        "checks": [d.to_dict() for d in diagnostics],
    }
    if overall:
        _emit_success("doctor", result=report)
        return
    first_failure = next(d for d in diagnostics if not d.ok)
    code = (
        Env.CODE_PORT_NOT_FOUND
        if first_failure.name == "midi_port"
        else Env.CODE_NOT_FOUND
    )
    _fail("doctor", first_failure.message, code=code, details=report)


@click.command(
    "snapshot",
    help="Capture a fresh FL Studio state snapshot.  "
    "Forces a device-side refresh (throttle=0).",
)
@click.option(
    "--out",
    "out_path",
    default=None,
    help="Write the snapshot JSON to this file (atomic).",
)
@click.option(
    "--sections",
    default=None,
    help="Comma-separated section filter (e.g. 'mixer,channels,patterns').",
)
@click.option(
    "--pretty", is_flag=True, default=False, help="Pretty-print the JSON output."
)
@click.pass_context
def snapshot_cmd(
    ctx: click.Context,
    out_path: str | None,
    sections: str | None,
    pretty: bool,
) -> None:
    cli_args: dict[str, Any] = {}
    if out_path:
        cli_args["out"] = out_path
    if sections:
        cli_args["sections"] = sections

    snapshot = _send_v2(
        ctx,
        "snapshot",
        {"throttle_ms": 0},
        v2_command="state",
        cli_args=cli_args,
    )
    if snapshot is None:
        return

    if sections:
        allowed = {s.strip() for s in sections.split(",")}
        snapshot = {k: v for k, v in snapshot.items() if k in allowed}

    if out_path:
        write_snapshot_file = ctx.obj["write_snapshot_file"]
        match write_snapshot_file(snapshot, out_path, pretty=pretty):
            case Err(SnapCmp.WriteIOError(reason=reason)):
                _fail(
                    "snapshot",
                    reason,
                    code=Env.CODE_IO_ERROR,
                    args=cli_args,
                )
                return
            case Ok(_):
                _emit_success(
                    "snapshot",
                    args=cli_args,
                    result={"path": out_path, "keys": list(snapshot)},
                )
    else:
        _emit_success("snapshot", args=cli_args, result=snapshot)


@click.command(
    "diff", help="Compare two snapshot JSON files and return a structured change list."
)
@click.argument("before_path", metavar="BEFORE")
@click.argument("after_path", metavar="AFTER")
@click.option(
    "--assert", "assert_path", default=None, help="Path to a JSON assertion spec file."
)
@click.pass_context
def diff_cmd(
    ctx: click.Context,
    before_path: str,
    after_path: str,
    assert_path: str | None,
) -> None:
    args_echo = build_args_echo(
        {"before": before_path, "after": after_path},
        **{"assert": assert_path},
    )

    compare_snapshot_files = ctx.obj["compare_snapshot_files"]
    outcome = compare_snapshot_files(
        before_path,
        after_path,
        assertion_spec_path=assert_path,
    )
    match outcome:
        case Err(SnapCmp.CompareIOError(reason=reason)):
            _fail("diff", reason, code=Env.CODE_NOT_FOUND, args=args_echo)
            return
        case Err(SnapCmp.CompareJSONError(path=bad_path, reason=reason)):
            label = (
                "assertion file"
                if assert_path is not None and bad_path == assert_path
                else "invalid JSON"
            )
            _fail(
                "diff",
                f"{label}: {reason}",
                code=Env.CODE_INVALID_ARGUMENT,
                args=args_echo,
            )
            return
        case Ok(report):
            result: dict[str, Any] = dict(report.diff)
            if report.assertions is not None:
                result["assertions"] = report.assertions
                if report.assertions["failures"]:
                    _fail(
                        "diff",
                        f"{len(report.assertions['failures'])} assertion(s) failed",
                        code=Env.CODE_INVALID_ARGUMENT,
                        args=args_echo,
                        details=result,
                    )
                    return
            _emit_success("diff", args=args_echo, result=result)


@click.command(
    "state",
    help="Query the live FL Studio state synchronously via SysEx.  "
    "Use --field with dotted paths (e.g. 'channels.0.name') "
    "to narrow the response.",
)
@click.option(
    "--field",
    "field_name",
    default=None,
    help="Dotted path into the snapshot "
    "(e.g. 'tempo', 'channels.0.name', 'mixer.tracks').",
)
@click.pass_context
def state_cmd(ctx: click.Context, field_name: str | None) -> None:
    throttle_ms: int = ctx.obj.get("state_throttle_ms", DEFAULT_STATE_THROTTLE_MS)
    cli_args: dict[str, Any] = {}
    v2_args: dict[str, Any] = {"throttle_ms": throttle_ms}
    if field_name is not None:
        cli_args["field"] = field_name
        v2_args["field"] = field_name

    result = _send_v2(ctx, "state", v2_args, cli_args=cli_args)
    if result is not None:
        _emit_success("state", args=cli_args, result=result)


@click.command(
    "piano-roll-show",
    help="Show exported Piano Roll notes from flcli_export.pyscript.",
)
@click.option(
    "--export-file", "export_file", default=None, help="Override the export JSON path."
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    show_default=True,
)
@click.pass_context
def piano_roll_show_cmd(
    ctx: click.Context,
    export_file: str | None,
    output_format: Literal["json", "csv"],
) -> None:
    pr_io = ctx.obj["piano_roll_io"]

    args_echo = build_args_echo({"format": output_format}, export_file=export_file)
    try:
        notes = pr_io.read_exported_notes(export_file)
    except FileNotFoundError as exc:
        _fail(
            "piano_roll_show",
            f"failed to read piano-roll export: {exc}",
            code=Env.CODE_NOT_FOUND,
            args=args_echo,
            hint="run Tools → Scripts → flcli_export in FL Studio first.",
        )
        return
    except (OSError, ValueError, KeyError) as exc:
        _fail(
            "piano_roll_show",
            f"failed to read piano-roll export: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    if output_format == "csv":
        for index, note in enumerate(notes):
            click.echo(
                f"{index},{int(note.pitch)},{int(note.velocity)},"
                f"{float(note.length)},{float(note.position)}"
            )
        return
    _emit_success(
        "piano_roll_show",
        args=args_echo,
        result={
            "export_file": export_file or pr_io.default_export_path(),
            "count": len(notes),
            "notes": [
                {"index": index, **note.to_dict()} for index, note in enumerate(notes)
            ],
        },
    )


CLI_COMMANDS: list[click.Command] = [
    ports_cmd,
    ping_cmd,
    doctor_cmd,
    snapshot_cmd,
    diff_cmd,
    state_cmd,
    piano_roll_show_cmd,
]
