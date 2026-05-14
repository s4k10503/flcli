"""Use case: batch step execution engine.

Single responsibility: take validated :class:`BatchStep` instances and
run them through the typed handler workflow (validation -> dispatch ->
envelope).  Produces structured response envelopes for every step.

The handler call is now a *workflow* in the FDM sense::

    BatchStep
       \\
        v
    handler(step.args) : Outcome[HandlerOutput, HandlerError]
       \\
        +---- Err -> typed envelope (INVALID_ARGUMENT / NOT_FOUND / IO_ERROR)
        |
        +---- Ok(LocalResult)   -> success envelope from local result
        |
        +---- Ok(DeviceCommand) -> ship over SysEx -> success or device error

Every transition is an exhaustive ``match`` over a closed sum, so a
new handler outcome variant is a deliberate type-system event.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, assert_never, cast

from flstudio_cli.batch.application.batch_parsing import (
    BatchStep,
    ParseError,
    parse_stream_line,
)
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.application.device_response_dto import DeviceErr, DeviceOk
from flstudio_cli.shared.application.device_response_parser import (
    parse_device_response,
)
from flstudio_cli.shared.application.handler_dto import (
    DeviceCommand,
    HandlerOutput,
    LocalResult,
)
from flstudio_cli.shared.application.handler_errors import (
    FileIOError,
    FileMissing,
    HandlerError,
    InvalidArgument,
)
from flstudio_cli.shared.application.handler_workflow import BatchHandler
from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

# --- Envelope helpers -------------------------------------------------------


def _error_envelope(
    step: BatchStep,
    code: Env.ErrorCode,
    message: str,
    *,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = Env.failure(
        step.name,
        code,
        message,
        args=step.args,
        hint=hint,
        details=details,
    )
    if step.step_id is not None:
        payload["id"] = step.step_id
    return payload


def _success_envelope(
    step: BatchStep,
    result: dict[str, Any],
) -> dict[str, Any]:
    payload = Env.success(step.name, args=step.args, result=result)
    if step.step_id is not None:
        payload["id"] = step.step_id
    return payload


# --- HandlerError -> envelope mapping ---------------------------------------


def _handler_error_envelope(
    step: BatchStep,
    error: HandlerError,
) -> dict[str, Any]:
    """Project a typed :data:`HandlerError` onto the matching envelope code.

    Exhaustive over the closed sum: a new :data:`HandlerError` variant
    fails static analysis here until it is given an explicit mapping.
    """
    match error:
        case InvalidArgument(message=message):
            return _error_envelope(step, Env.CODE_INVALID_ARGUMENT, message)
        case FileMissing(path=path):
            return _error_envelope(step, Env.CODE_NOT_FOUND, path)
        case FileIOError(message=message):
            return _error_envelope(step, Env.CODE_IO_ERROR, message)
        case _ as unreachable:
            assert_never(unreachable)


# --- Step execution ---------------------------------------------------------


def execute_step(
    step: BatchStep,
    *,
    controller: DawController | None,
    dry_run: bool,
    handlers: Mapping[str, BatchHandler] | None = None,
) -> dict[str, Any]:
    """Execute one batch step and return its response envelope.

    The handler returns a typed Outcome.  ``Err`` variants project to
    typed error envelopes; ``Ok(LocalResult)`` goes straight to a
    success envelope; ``Ok(DeviceCommand)`` is dispatched through the
    controller (or echoed under ``--dry-run``).

    ``handlers`` defaults to an empty dict; callers should pass the
    merged per-feature registry built by
    :func:`~flstudio_cli.shared.application.handler_workflow.make_handlers`
    (the composition root in ``__main__`` does this and publishes the
    result on ``ctx.obj['batch_handlers']``).
    """
    registry = handlers if handlers is not None else {}
    handler = registry.get(step.name)
    if handler is None:
        return _unknown_command_envelope(step)

    return _envelope_from_outcome(
        step,
        handler(step.args),
        controller=controller,
        dry_run=dry_run,
    )


def _unknown_command_envelope(step: BatchStep) -> dict[str, Any]:
    """Envelope for a batch step whose name is not in the handler registry."""
    return _error_envelope(
        step,
        Env.CODE_UNKNOWN_COMMAND,
        f"unknown batch command: {step.name}",
        hint="see `flcli doctor` for the list of supported commands.",
    )


def _envelope_from_outcome(
    step: BatchStep,
    outcome: Outcome[HandlerOutput, HandlerError],
    *,
    controller: DawController | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Project a handler :data:`Outcome` onto its response envelope.

    Exhaustive over the ``Ok``/``Err`` sum, then over the closed
    ``Ok`` payload sum (``LocalResult`` vs ``DeviceCommand``).
    """
    match outcome:
        case Err(error):
            return _handler_error_envelope(step, error)
        case Ok(output):
            match output:
                case LocalResult(result=result):
                    return _success_envelope(step, result)
                case DeviceCommand(cmd=cmd, args=cmd_args):
                    return _dispatch_device_command(
                        step, cmd, cmd_args, controller=controller, dry_run=dry_run
                    )
                case _ as unreachable_output:
                    assert_never(unreachable_output)
        case _ as unreachable_outcome:
            assert_never(unreachable_outcome)


def _dispatch_device_command(
    step: BatchStep,
    cmd: str,
    args: dict[str, Any],
    *,
    controller: DawController | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Send a validated :class:`DeviceCommand` over the controller (or dry-run).

    All transport-layer failures (timeout, port closed) are surfaced
    as envelopes here -- the *handler* is pure validation, the
    *executor* owns the I/O concerns.
    """
    if dry_run:
        return _dry_run_preview_envelope(step, cmd, args)
    if controller is None:
        return _no_controller_envelope(step)
    try:
        raw_response = controller.send_and_wait(cmd, args)
    except TimeoutError as exc:
        return _timeout_envelope(step, exc)
    except ConnectionResetError as exc:
        return _error_envelope(step, Env.CODE_PORT_NOT_FOUND, str(exc))
    return _envelope_from_device_response(step, raw_response)


def _dry_run_preview_envelope(
    step: BatchStep,
    cmd: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Echo the wire-format request without dispatching it."""
    return _success_envelope(
        step,
        {"dry_run": True, "request": {"cmd": cmd, "args": args}},
    )


def _no_controller_envelope(step: BatchStep) -> dict[str, Any]:
    """Envelope for a device step issued without an open controller."""
    return _error_envelope(
        step,
        Env.CODE_PORT_NOT_FOUND,
        "MIDI port not open; cannot dispatch step",
        hint="open a controller before executing steps, or pass --dry-run to preview.",
    )


def _timeout_envelope(step: BatchStep, exc: TimeoutError) -> dict[str, Any]:
    """Envelope for a controller timeout while waiting for the device reply."""
    return _error_envelope(
        step,
        Env.CODE_TIMEOUT,
        str(exc),
        hint="FL Studio did not respond on the v2 return port.",
    )


def _envelope_from_device_response(
    step: BatchStep,
    raw_response: dict[str, Any],
) -> dict[str, Any]:
    """Parse a device response and project it onto a success/error envelope."""
    match parse_device_response(raw_response):
        case DeviceOk(result=result):
            return _success_envelope(step, result)
        case DeviceErr(code=code, message=message, hint=hint, details=details):
            # The device may return a code outside ``ErrorCode`` (per the
            # parse_device_response contract); the envelope preserves the
            # raw string and exit_code_for falls back to 1.
            return _error_envelope(
                step,
                cast(Env.ErrorCode, code),
                message,
                hint=hint,
                details=details,
            )


# --- Multi-step runners -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class _UnknownCommand:
    """Sentinel slot for a step whose name is not in the handler registry."""


_UNKNOWN: _UnknownCommand = _UnknownCommand()

#: One pre-validated step's cached outcome.  Holding the handler's
#: :data:`Outcome` verbatim lets the dispatch pass reuse it without
#: invoking the handler twice (some handlers, like ``piano_roll_show``,
#: read files during construction).  ``_UnknownCommand`` covers the
#: registry-miss case as a third closed variant rather than overloading
#: ``None``.
_OutcomeSlot = Outcome[HandlerOutput, HandlerError] | _UnknownCommand


def _pre_validate(
    steps: Sequence[BatchStep],
    registry: Mapping[str, BatchHandler],
) -> list[_OutcomeSlot]:
    """Call every handler once to surface validation errors upfront.

    Handlers may read files during preparation (the piano-roll export
    handler does), but they never dispatch ``DeviceCommand`` payloads
    -- the controller is only touched in the dispatch phase, so a
    downstream validation failure cannot leak FL Studio state changes.
    """
    cached: list[_OutcomeSlot] = []
    for step in steps:
        handler = registry.get(step.name)
        cached.append(_UNKNOWN if handler is None else handler(step.args))
    return cached


def _partition_validated(
    steps: Sequence[BatchStep],
    cached: Sequence[_OutcomeSlot],
) -> tuple[list[dict[str, Any]], list[tuple[BatchStep, Ok[HandlerOutput]]]]:
    """Split a pre-validated batch into (errors, ok-pairs).

    Returns:
        - error envelopes for every failing step (unknown command or
          handler ``Err``);
        - ``(step, Ok)`` pairs for every step that validated cleanly.

    Either list may be empty; callers test the error list to decide
    whether to abort the batch or proceed to dispatch.
    """
    errors: list[dict[str, Any]] = []
    validated: list[tuple[BatchStep, Ok[HandlerOutput]]] = []
    for step, slot in zip(steps, cached, strict=True):
        match slot:
            case _UnknownCommand():
                errors.append(_unknown_command_envelope(step))
            case Err(error=error):
                errors.append(_handler_error_envelope(step, error))
            case Ok():
                validated.append((step, slot))
    return errors, validated


def run_steps(
    steps: Sequence[BatchStep],
    *,
    controller: DawController | None,
    dry_run: bool,
    stop_on_error: bool,
    handlers: Mapping[str, BatchHandler] | None = None,
) -> list[dict[str, Any]]:
    """Run a finite list of steps and collect their response envelopes.

    Two-phase execution:

    1. **Pre-validate.**  Every handler is invoked once with its step
       args and the resulting :data:`Outcome` is cached.  Handlers do
       not touch the controller, so unknown commands and bad fields
       fail before any FL Studio state change.  If *any* step fails
       validation the whole batch is abandoned with no controller I/O;
       only the error envelopes for the failing steps are emitted.
    2. **Dispatch.**  When every step validated, project each cached
       :data:`Outcome` to its envelope, sending ``DeviceCommand``
       payloads through the controller.  ``stop_on_error`` halts the
       loop at the first device-side / transport failure.

    Streaming callers (``batch stream``) get fail-as-you-go semantics
    instead -- see :func:`stream_steps`.
    """
    registry = handlers if handlers is not None else {}
    cached = _pre_validate(steps, registry)
    errors, validated = _partition_validated(steps, cached)
    if errors:
        return errors

    responses: list[dict[str, Any]] = []
    for step, outcome in validated:
        envelope = _envelope_from_outcome(
            step, outcome, controller=controller, dry_run=dry_run
        )
        responses.append(envelope)
        if stop_on_error and not envelope["ok"]:
            break
    return responses


def stream_steps(
    lines: Iterable[str],
    *,
    controller: DawController | None,
    dry_run: bool,
    handlers: Mapping[str, BatchHandler] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one response envelope per JSONL request line.

    Blank lines and comments (``# ...``) are skipped so a user can
    hand-drive the stream from a terminal.  Malformed lines yield an
    ``INVALID_ARGUMENT`` envelope instead of raising -- a single bad
    line should not tear down a long-lived stream session.
    """
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match parse_stream_line(line):
            case Ok(step):
                yield execute_step(
                    step,
                    controller=controller,
                    dry_run=dry_run,
                    handlers=handlers,
                )
            case Err(ParseError(message=message)):
                yield Env.failure(
                    "stream",
                    Env.CODE_INVALID_ARGUMENT,
                    f"failed to parse stream line: {message}",
                )
