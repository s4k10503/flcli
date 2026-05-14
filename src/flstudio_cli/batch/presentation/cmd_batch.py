"""Interface adapter: ``flcli batch`` — multi-step JSON / JSONL execution."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from flstudio_cli.batch.application import batch as B
from flstudio_cli.batch.application.batch_parsing import ParseError
from flstudio_cli.batch.application.batch_runner import (
    execute_batch_run,
    execute_batch_stream,
)
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.cli_dispatcher import emit_failure
from flstudio_cli.shared.presentation.cli_dispatch import resolve_deps
from flstudio_cli.shared.presentation.cli_helpers import (
    _print_json_line,
    read_text_or_stdin,
)
from flstudio_cli.shared.utility.outcome import Err, Ok


def _resolve_handlers(ctx: click.Context) -> dict[str, B.BatchHandler]:
    """Pull the handler dict assembled by the composition root in ``__main__``."""
    handlers = ctx.obj.get("batch_handlers")
    if handlers is None:
        raise RuntimeError(
            "batch_handlers missing from ctx.obj; the composition root in "
            "__main__ must populate it."
        )
    return handlers


@click.group("batch", help="Run multiple commands in a single MIDI session.")
def group() -> None:
    pass


def _load_steps_payload(source: str) -> Any:
    return json.loads(read_text_or_stdin(source))


@group.command(
    "run",
    help="Execute a list of steps from a JSON file (or stdin with '-').",
)
@click.option("--steps-file", "steps_file", default="-", show_default=True)
@click.option(
    "--stop-on-error/--continue-on-error",
    "stop_on_error",
    default=True,
    show_default=True,
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    steps_file: str,
    stop_on_error: bool,
) -> None:
    deps = resolve_deps(ctx)
    args_echo = {"steps_file": steps_file, "stop_on_error": stop_on_error}
    try:
        payload = _load_steps_payload(steps_file)
    except FileNotFoundError as exc:
        emit_failure(
            deps,
            "batch_run",
            f"steps file: {exc}",
            code=Env.CODE_NOT_FOUND,
            args=args_echo,
        )
        return
    except OSError as exc:
        emit_failure(
            deps,
            "batch_run",
            f"steps file: {exc}",
            code=Env.CODE_IO_ERROR,
            args=args_echo,
        )
        return
    except json.JSONDecodeError as exc:
        emit_failure(
            deps,
            "batch_run",
            f"invalid JSON: {exc}",
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return
    match B.parse_steps(payload):
        case Ok(steps):
            pass
        case Err(ParseError(message=message)):
            emit_failure(
                deps,
                "batch_run",
                message,
                code=Env.CODE_INVALID_ARGUMENT,
                args=args_echo,
            )
            return

    execute_batch_run(
        deps,
        steps,
        handlers=_resolve_handlers(ctx),
        stop_on_error=stop_on_error,
        args_echo=args_echo,
    )


@group.command(
    "stream",
    help="Read one JSONL request per line from stdin and emit one JSONL "
    "response per line.",
)
@click.pass_context
def stream_cmd(ctx: click.Context) -> None:
    deps = resolve_deps(ctx)

    def emit_line(response: dict[str, Any]) -> None:
        _print_json_line(response)
        try:
            sys.stdout.flush()
        except ValueError:
            pass

    execute_batch_stream(
        deps,
        sys.stdin,
        handlers=_resolve_handlers(ctx),
        emit_line=emit_line,
    )


CLI_COMMANDS: list[click.Command] = [group]
