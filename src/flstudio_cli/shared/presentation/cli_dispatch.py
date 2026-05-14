"""Interface adapter: click → application-layer dispatcher adapter.

The substance of v2 dispatch (controller lifecycle, round-trip, error
mapping, track-selector resolution) lives in
:mod:`flstudio_cli.shared.application.cli_dispatcher`.  Each Click-typed
entry point here resolves a :class:`DispatchDeps` from ``ctx.obj`` and
forwards the call; per-feature ``cmd_*.py`` modules talk to this
module so they never have to construct deps themselves.

The FLP-dispatch helper (``_dispatch_flp``) sits alongside the
dispatcher because it adapts user-input errors to envelopes rather
than driving the wire.  Melody-loading helpers used to live here too
but moved to :mod:`flstudio_cli.piano_roll.presentation.melody_helpers`
since piano_roll is their only consumer (avoids a shared→feature
backward dep on ``piano_roll.application``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application import cli_dispatcher as App
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.cli_dispatcher import DispatchDeps
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.presentation.cli_helpers import (
    _OUTPUT,
    PORT_HINT,
    TIMEOUT_HINT,
    _emit_success,
    _fail,
)
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


def _make_controller(ctx: click.Context) -> DawController:
    """Construct a ``DawController`` honouring top-level CLI flags."""
    return Comp.open_daw_controller(
        port_name=ctx.obj["port"],
        return_port_name=ctx.obj.get("return_port"),
    )


def resolve_deps(ctx: click.Context) -> DispatchDeps:
    """Bridge a Click context to the application-layer :class:`DispatchDeps`."""
    return DispatchDeps(
        dry_run=bool(ctx.obj.get("dry_run")),
        open_controller=lambda: _make_controller(ctx),
        output=_OUTPUT,
        resolve_exit_code=exit_code_for,
        timeout_hint=TIMEOUT_HINT,
        port_hint=PORT_HINT,
    )


# --- v2 dispatch wrappers --------------------------------------------------


def _exec_v2(
    ctx: click.Context,
    command_name: str,
    v2_args: dict[str, Any],
    args_echo: dict[str, Any],
    *,
    v2_command: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    return App.exec_v2(
        resolve_deps(ctx),
        command_name,
        v2_args,
        args_echo,
        v2_command=v2_command,
        timeout_ms=timeout_ms,
    )


def _send_v2(
    ctx: click.Context,
    command_name: str,
    v2_args: dict[str, Any] | None = None,
    *,
    v2_command: str | None = None,
    cli_args: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any] | None:
    return App.send_v2(
        resolve_deps(ctx),
        command_name,
        v2_args,
        v2_command=v2_command,
        cli_args=cli_args,
        timeout_ms=timeout_ms,
    )


def _dispatch_command(
    ctx: click.Context,
    command_name: str,
    v2_args: dict[str, Any] | None = None,
    *,
    v2_command: str | None = None,
    cli_args: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
) -> None:
    App.dispatch_command(
        resolve_deps(ctx),
        command_name,
        v2_args,
        v2_command=v2_command,
        cli_args=cli_args,
        timeout_ms=timeout_ms,
    )


def _track_selector_options(f):
    """Decorate a Click command with mutually exclusive track selector flags.

    Adds ``--track/-t``, ``--track-name``, ``--track-query``, and
    ``--track-ref``.  Exactly one must be supplied; validation happens
    inside :func:`flstudio_cli.shared.application.track_selection.parse_track_selector_args`.
    """
    f = click.option(
        "--track-ref", type=str, default=None, help="Track ref JSON (advanced)."
    )(f)
    f = click.option(
        "--track-query",
        type=str,
        default=None,
        help="Case-insensitive substring match on track name.",
    )(f)
    f = click.option("--track-name", type=str, default=None, help="Exact track name.")(
        f
    )
    f = click.option("--track", "-t", type=int, default=None, help="Track index.")(f)
    return f


def _dispatch_with_track_selector(
    ctx: click.Context,
    command_name: str,
    *,
    v2_command: str | None = None,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
    extra_args: dict[str, Any] | None = None,
) -> None:
    App.dispatch_with_track_selector(
        resolve_deps(ctx),
        command_name,
        v2_command=v2_command,
        track=track,
        track_name=track_name,
        track_query=track_query,
        track_ref=track_ref,
        extra_args=extra_args,
    )


# --- FLP dispatch helper ---------------------------------------------------


def _dispatch_flp(
    command_name: str,
    fn: Any,
    args_echo: dict[str, Any],
    *,
    path: str | None = None,
) -> None:
    """Run an FLP operation with standard error handling.

    When *path* is given, a missing target file is reported as
    ``NOT_FOUND`` *before* pyflp is invoked.  This keeps the error
    classification stable when pyflp is not installed (otherwise a
    missing-file scenario would surface through ``RuntimeError`` from
    ``_require_pyflp``).
    """
    if path is not None:
        try:
            Path(path).stat()
        except FileNotFoundError:
            _fail(
                command_name,
                f"file not found: {path}",
                code=Env.CODE_NOT_FOUND,
                args=args_echo,
            )
            return
        except OSError as exc:
            _fail(command_name, str(exc), code=Env.CODE_IO_ERROR, args=args_echo)
            return
    try:
        result = fn()
    except FileNotFoundError as exc:
        _fail(command_name, str(exc), code=Env.CODE_NOT_FOUND, args=args_echo)
        return
    except RuntimeError as exc:
        _fail(command_name, str(exc), code=Env.CODE_INTERNAL, args=args_echo)
        return
    except (OSError, ValueError) as exc:
        _fail(command_name, str(exc), code=Env.CODE_IO_ERROR, args=args_echo)
        return
    _emit_success(command_name, args=args_echo, result=result)
