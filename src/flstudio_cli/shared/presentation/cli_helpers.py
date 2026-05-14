"""Interface adapter: envelope emission and shared text-IO helpers for the CLI.

Thin presentation adapter: every helper here writes through a single
:class:`Output` sink so a future non-Click frontend can substitute its
own envelope channel (HTTP response, TUI buffer, etc.).

Dispatch flow, controller lifecycle, and typed-error mapping live in
:mod:`flstudio_cli.shared.presentation.cli_dispatch`; this module
intentionally stays out of the wire format.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.output_port import Output
from flstudio_cli.shared.presentation.exit_codes import exit_code_for

#: Default cap on state-snapshot refresh frequency (ms).  Surfaced here
#: so the root CLI group and the ``state`` command share one source.
DEFAULT_STATE_THROTTLE_MS = 500

#: User-facing hint emitted on a return-port timeout.  Public so other
#: presentation modules (cmd_state, cmd_piano_roll, cmd_batch, batch_executor)
#: can reuse the same wording instead of inventing their own.
TIMEOUT_HINT = (
    "FL Studio did not respond on the return port. "
    "Check that 'flcli-rx' exists and the device script is loaded."
)
#: User-facing hint when one of the virtual MIDI ports is missing.
PORT_HINT = (
    "create virtual MIDI ports 'flcli' and 'flcli-rx' "
    "(LoopMIDI on Windows, IAC Driver on macOS) and re-run."
)


# --- output adapter ---------------------------------------------------------


class _ClickJsonLineOutput:
    """``Output`` adapter that routes through :func:`click.echo`.

    Used by the production CLI. ``click.echo`` honours Click's
    stdout-redirection conventions (e.g. ``CliRunner.invoke``), which
    the test suite relies on; raw ``sys.stdout.write`` would bypass
    that and break the test runner.
    """

    def emit_envelope(self, envelope: dict[str, Any]) -> None:
        click.echo(json.dumps(envelope, ensure_ascii=False))

    def exit_failure(self, exit_code: int) -> None:
        raise SystemExit(exit_code)


#: Shared output sink for every helper in this module.  Swapping the
#: module-level binding is how a future presentation frontend would
#: redirect envelope flow without touching the helpers themselves.
_OUTPUT: Output = _ClickJsonLineOutput()


def set_output(output: Output) -> None:
    """Replace the active :class:`Output` adapter (testing / Web frontend)."""
    global _OUTPUT
    _OUTPUT = output


@contextmanager
def use_output(output: Output):
    """Temporarily install *output* as the active sink, restoring on exit.

    Tests use this to capture envelopes without going through Click's
    :class:`CliRunner`; the cleanup runs even when the body raises
    :class:`SystemExit` (which a real ``Output.exit_failure`` would).
    """
    previous = _OUTPUT
    set_output(output)
    try:
        yield output
    finally:
        set_output(previous)


# --- envelope emission ------------------------------------------------------


def _print_json_line(payload: dict[str, Any]) -> None:
    """Emit a raw envelope dict through the active :class:`Output`.

    Used by ``batch stream`` which has already-built envelopes from the
    application layer and just needs to push them out the same channel
    as :func:`_emit_success` and :func:`_fail`.
    """
    _OUTPUT.emit_envelope(payload)


def _emit_success(
    command: str,
    *,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    _OUTPUT.emit_envelope(Env.success(command, args=args, result=result))


def _fail(
    command: str,
    message: str,
    *,
    code: Env.ErrorCode = Env.CODE_INVALID_ARGUMENT,
    args: dict[str, Any] | None = None,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    _OUTPUT.emit_envelope(
        Env.failure(
            command,
            code,
            message,
            args=args,
            hint=hint,
            details=details,
        )
    )
    _OUTPUT.exit_failure(exit_code_for(code))


# --- args-echo builder ------------------------------------------------------


def build_args_echo(
    base: dict[str, Any] | None = None,
    /,
    **optional: Any,
) -> dict[str, Any]:
    """Build an envelope ``args`` dict, dropping keys whose value is ``None``.

    The CLI envelope omits unset optional flags from its ``args`` payload
    rather than echoing ``null``; this helper centralises the conditional
    insertion that several presentation modules used to repeat inline.
    """
    echo: dict[str, Any] = dict(base) if base else {}
    echo.update({k: v for k, v in optional.items() if v is not None})
    return echo


# --- shared text-IO helpers ------------------------------------------------


def read_text_or_stdin(source: str, *, encoding: str = "utf-8") -> str:
    """Read text from a path, or from stdin when ``source`` is ``"-"``."""
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding=encoding)


def iter_significant_lines(text: str) -> Iterator[str]:
    """Yield stripped lines, dropping blank lines and ``#`` comments.

    Used by every place that consumes hand-edited line input (melody
    CSV, batch step lists, etc.) so the format stays consistent.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line
