"""Use case: orchestration entry points for ``batch run`` and ``batch stream``.

The presentation layer parses CLI args and the steps JSON, then hands
the parsed steps + an envelope sink to the runners defined here.  Each
runner owns the controller lifecycle and emits envelopes through
``deps.output`` so a non-Click frontend (Web, TUI) can drive the same
logic by supplying its own :class:`DispatchDeps`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from flstudio_cli.batch.application.batch_executor import (
    run_steps,
    stream_steps,
)
from flstudio_cli.batch.application.batch_parsing import BatchStep
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.cli_dispatcher import (
    DispatchDeps,
    emit_failure,
    emit_success,
)
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.application.handler_workflow import BatchHandler


def execute_batch_run(
    deps: DispatchDeps,
    steps: list[BatchStep],
    *,
    handlers: Mapping[str, BatchHandler],
    stop_on_error: bool,
    args_echo: dict[str, Any],
) -> None:
    """Open a controller (when not in dry-run), run the steps, emit one envelope.

    On a transport-level failure (port missing) emits a single
    ``PORT_NOT_FOUND`` envelope and returns; otherwise summarises the
    per-step responses into one ``batch_run`` envelope -- success when
    every step ok'd, failure with the first step's error code when not.
    """
    responses = _collect_responses(
        deps,
        steps,
        handlers=handlers,
        stop_on_error=stop_on_error,
        args_echo=args_echo,
    )
    if responses is None:
        return

    count = len(responses)
    ok_count = sum(1 for e in responses if e["ok"])
    result_body: dict[str, Any] = {
        "count": count,
        "ok_count": ok_count,
        "responses": responses,
    }

    if ok_count == count:
        emit_success(deps, "batch_run", args=args_echo, result=result_body)
        return

    first_failed = next(e for e in responses if not e["ok"])
    code = first_failed.get("error", {}).get("code", Env.CODE_INTERNAL)
    emit_failure(
        deps,
        "batch_run",
        f"{count - ok_count} step(s) failed",
        code=code,
        args=args_echo,
        details=result_body,
    )


def _collect_responses(
    deps: DispatchDeps,
    steps: list[BatchStep],
    *,
    handlers: Mapping[str, BatchHandler],
    stop_on_error: bool,
    args_echo: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Run *steps* under the right controller (or none) and return the list.

    Returns ``None`` after emitting a transport-level error envelope so
    the caller stops without summarising.
    """
    if deps.dry_run:
        return run_steps(
            steps,
            controller=None,
            dry_run=True,
            stop_on_error=stop_on_error,
            handlers=handlers,
        )
    try:
        with deps.open_controller() as controller:
            return run_steps(
                steps,
                controller=controller,
                dry_run=False,
                stop_on_error=stop_on_error,
                handlers=handlers,
            )
    except RuntimeError as exc:
        emit_failure(
            deps,
            "batch_run",
            str(exc),
            code=Env.CODE_PORT_NOT_FOUND,
            args=args_echo,
            hint=deps.port_hint,
        )
        return None


def execute_batch_stream(
    deps: DispatchDeps,
    lines: Iterable[str],
    *,
    handlers: Mapping[str, BatchHandler],
    emit_line: Callable[[dict[str, Any]], None],
) -> None:
    """Stream JSONL request lines through the executor and emit responses.

    *emit_line* is the per-response sink (the presentation flushes after
    each line so a piped consumer sees responses immediately).  Transport
    errors emit one final ``batch_stream`` failure envelope and exit.
    """
    try:
        if deps.dry_run:
            _drain_stream(
                lines,
                controller=None,
                dry_run=True,
                handlers=handlers,
                emit_line=emit_line,
            )
            return
        with deps.open_controller() as controller:
            _drain_stream(
                lines,
                controller=controller,
                dry_run=False,
                handlers=handlers,
                emit_line=emit_line,
            )
    except RuntimeError as exc:
        emit_failure(
            deps,
            "batch_stream",
            str(exc),
            code=Env.CODE_PORT_NOT_FOUND,
            hint=deps.port_hint,
        )


def _drain_stream(
    lines: Iterable[str],
    *,
    controller: DawController | None,
    dry_run: bool,
    handlers: Mapping[str, BatchHandler],
    emit_line: Callable[[dict[str, Any]], None],
) -> None:
    for response in stream_steps(
        lines,
        controller=controller,
        dry_run=dry_run,
        handlers=handlers,
    ):
        emit_line(response)
