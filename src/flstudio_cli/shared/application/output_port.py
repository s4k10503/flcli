"""Application port: framework-agnostic envelope output Protocol.

Every command finishes by emitting one JSON envelope (success or
failure). The CLI prints that envelope to stdout and, on failure,
maps the error code to a POSIX exit code. A future Web frontend
would instead serialise the envelope into an HTTP response and map
the error code to an HTTP status.

:class:`Output` captures the two operations both frontends share:

* :meth:`Output.emit_envelope` -- hand the built envelope (success or
  failure) to the frontend.
* :meth:`Output.exit_failure` -- terminate the request with the given
  POSIX exit code (CLI) or status (Web).

The CLI adapter lives in
:mod:`flstudio_cli.shared.presentation.cli_helpers`
(``_ClickJsonLineOutput``); tests substitute an in-memory recorder so
the failure path no longer raises :class:`SystemExit`.
"""

# pyright: strict

from __future__ import annotations

from typing import Any, Protocol


class Output(Protocol):
    """Frontend-agnostic envelope output surface.

    Implementations may print, return, or otherwise transmit the
    envelope; they may also raise or set status to terminate the
    request. The two halves are separate so callers can choose to
    emit a failure envelope without exiting (useful for batch).
    """

    def emit_envelope(self, envelope: dict[str, Any]) -> None: ...
    def exit_failure(self, exit_code: int) -> None: ...
