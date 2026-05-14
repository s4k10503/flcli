"""Use case: click-agnostic dispatch core for v2 round-trips.

The application layer drives a v2 command end-to-end without importing
``click`` or reading from a global :class:`Output` sink.  Every ambient
dependency is explicit on :class:`DispatchDeps`:

* ``open_controller`` -- composition-supplied factory returning a
  context-managed :class:`DawController`.
* ``output`` -- the :class:`Output` adapter that emits envelopes and
  terminates failed requests; tests pass an in-memory recorder.
* ``resolve_exit_code`` -- frontend-supplied mapping from an
  :data:`Env.ErrorCode` to a POSIX / HTTP exit code, kept out of this
  module because exit codes are a frontend concern.
* ``timeout_hint`` / ``port_hint`` -- user-facing remediation strings
  that reference CLI-specific names (``flcli-rx``, LoopMIDI, ...).
  Keeping them on deps lets a Web frontend swap in different wording
  without touching this module.

The four orchestration entry points (:func:`exec_v2`, :func:`send_v2`,
:func:`dispatch_command`, :func:`dispatch_with_track_selector`) own
the wire / envelope contract; presentation modules adapt
``click.Context`` to :class:`DispatchDeps` and call them.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application import track_selection as TrackSel
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.application.device_response_dto import DeviceErr, DeviceOk
from flstudio_cli.shared.application.device_response_parser import (
    parse_device_response,
)
from flstudio_cli.shared.application.output_port import Output
from flstudio_cli.shared.application.track_selection import TrackSelectorError
from flstudio_cli.shared.application.transport_errors import MidiPortNotFound

OpenController = Callable[[], AbstractContextManager[DawController]]
ResolveExitCode = Callable[[Env.ErrorCode], int]


@dataclass(frozen=True, slots=True)
class DispatchDeps:
    """Bundle of frontend-supplied dependencies the dispatcher needs."""

    dry_run: bool
    open_controller: OpenController
    output: Output
    resolve_exit_code: ResolveExitCode
    timeout_hint: str
    port_hint: str


# --- envelope emission ------------------------------------------------------


def emit_success(
    deps: DispatchDeps,
    command: str,
    *,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    deps.output.emit_envelope(Env.success(command, args=args, result=result))


def emit_failure(
    deps: DispatchDeps,
    command: str,
    message: str,
    *,
    code: Env.ErrorCode = Env.CODE_INVALID_ARGUMENT,
    args: dict[str, Any] | None = None,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    deps.output.emit_envelope(
        Env.failure(command, code, message, args=args, hint=hint, details=details)
    )
    deps.output.exit_failure(deps.resolve_exit_code(code))


# --- v2 round-trip ----------------------------------------------------------


def exec_v2(
    deps: DispatchDeps,
    command_name: str,
    v2_args: dict[str, Any],
    args_echo: dict[str, Any],
    *,
    v2_command: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """Run one v2 round-trip and return the response result dict.

    ``v2_command`` defaults to ``command_name``; pass it explicitly only
    when the user-facing CLI label and the wire command name differ
    (e.g. ``snapshot`` -> wire ``state``).

    Emits an error envelope and returns ``None`` on transport failure or
    a non-ok response.  In dry-run mode echoes the request envelope and
    returns ``None`` without opening the controller.
    """
    wire_cmd = v2_command if v2_command is not None else command_name
    if deps.dry_run:
        emit_success(
            deps,
            command_name,
            args=args_echo,
            result={
                "dry_run": True,
                "request": {"cmd": wire_cmd, "args": v2_args},
            },
        )
        return None

    try:
        with deps.open_controller() as controller:
            if timeout_ms is None:
                response = controller.send_and_wait(wire_cmd, v2_args)
            else:
                response = controller.send_and_wait(
                    wire_cmd, v2_args, timeout_ms=timeout_ms
                )
    except TimeoutError as exc:
        emit_failure(
            deps,
            command_name,
            str(exc),
            code=Env.CODE_TIMEOUT,
            args=args_echo,
            hint=deps.timeout_hint,
        )
        return None
    except MidiPortNotFound as exc:
        emit_failure(
            deps,
            command_name,
            str(exc),
            code=Env.CODE_PORT_NOT_FOUND,
            args=args_echo,
            hint=deps.port_hint,
        )
        return None

    match parse_device_response(response):
        case DeviceOk(result=result):
            return result
        case DeviceErr(code=code, message=message, hint=hint, details=details):
            emit_failure(
                deps,
                command_name,
                message,
                code=cast(Env.ErrorCode, code),
                args=args_echo,
                hint=hint,
                details=details,
            )
            return None


def send_v2(
    deps: DispatchDeps,
    command_name: str,
    v2_args: dict[str, Any] | None = None,
    *,
    v2_command: str | None = None,
    cli_args: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    """Run a v2 round-trip; return the result dict (or ``None`` on failure).

    ``v2_command`` defaults to ``command_name``; pass it explicitly only
    when the CLI label and the wire command differ.

    On error, an envelope is already emitted by :func:`exec_v2`; callers
    receive ``None`` and should simply ``return``.  ``cli_args`` is
    echoed in the envelope's ``args`` field; if omitted it defaults to
    ``v2_args``.
    """
    resolved_args: dict[str, Any] = dict(cli_args or v2_args or {})
    resolved_v2: dict[str, Any] = dict(v2_args or {})
    return exec_v2(
        deps,
        command_name,
        resolved_v2,
        resolved_args,
        v2_command=v2_command,
        timeout_ms=timeout_ms,
    )


def dispatch_command(
    deps: DispatchDeps,
    command_name: str,
    v2_args: dict[str, Any] | None = None,
    *,
    v2_command: str | None = None,
    cli_args: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
) -> None:
    """Send a v2 command and emit the merged ``args + result`` success envelope.

    ``v2_command`` defaults to ``command_name``; pass it explicitly only
    when the CLI label and the wire command differ.

    Thin wrapper over :func:`send_v2` for the common "fire and emit"
    pattern.
    """
    resolved_args: dict[str, Any] = dict(cli_args or v2_args or {})
    result = send_v2(
        deps,
        command_name,
        v2_args,
        v2_command=v2_command,
        cli_args=resolved_args,
        timeout_ms=timeout_ms,
    )
    if result is None:
        return
    emit_success(
        deps, command_name, args=resolved_args, result={**resolved_args, **result}
    )


# --- track-selector dispatch ----------------------------------------------


def dispatch_with_track_selector(
    deps: DispatchDeps,
    command_name: str,
    *,
    v2_command: str | None = None,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
    extra_args: dict[str, Any] | None = None,
) -> None:
    """Like :func:`dispatch_command` but resolves the track selector first.

    ``v2_command`` defaults to ``command_name`` when omitted.

    For ``--track`` the index is passed through unchanged.  Named
    selectors send a ``mixer_list`` query first to resolve the name to
    an integer index, then run the actual command -- both round-trips
    happen inside one controller session so the rtmidi callback never
    races a port-close.
    """
    wire_cmd = v2_command if v2_command is not None else command_name
    try:
        selection = TrackSel.parse_track_selector_args(
            track=track,
            track_name=track_name,
            track_query=track_query,
            track_ref=track_ref,
        )
    except TrackSelectorError as exc:
        emit_failure(deps, command_name, str(exc), code=Env.CODE_INVALID_ARGUMENT)
        return

    extra = dict(extra_args or {})

    if selection.mode == "index":
        extra["track"] = selection.value
        dispatch_command(deps, command_name, extra, v2_command=v2_command)
        return

    if deps.dry_run:
        emit_success(
            deps,
            command_name,
            args={"selector": selection.value, **extra},
            result={
                "dry_run": True,
                "note": "track selector requires live resolution via mixer_list",
                "request": {"cmd": wire_cmd, "args": extra},
            },
        )
        return

    try:
        with deps.open_controller() as controller:
            state_resp = controller.send_and_wait("mixer_list")
            snapshot = state_resp.get("result", {})
            track_idx = TrackSel.resolve_track_index(selection, snapshot)
            extra["track"] = track_idx
            response = controller.send_and_wait(wire_cmd, extra)
    except TimeoutError as exc:
        emit_failure(
            deps, command_name, str(exc), code=Env.CODE_TIMEOUT, hint=deps.timeout_hint
        )
        return
    except MidiPortNotFound as exc:
        emit_failure(
            deps,
            command_name,
            str(exc),
            code=Env.CODE_PORT_NOT_FOUND,
            hint=deps.port_hint,
        )
        return
    except ValueError as exc:
        emit_failure(deps, command_name, str(exc), code=Env.CODE_NOT_FOUND)
        return

    match parse_device_response(response):
        case DeviceErr(code=code, message=message, hint=hint, details=details):
            emit_failure(
                deps,
                command_name,
                message,
                code=cast(Env.ErrorCode, code),
                hint=hint,
                details=details,
            )
            return
        case DeviceOk(result=device_result):
            result = dict(extra)
            result.update(device_result)
            emit_success(deps, command_name, args=extra, result=result)
