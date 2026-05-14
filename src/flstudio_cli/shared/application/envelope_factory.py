# pyright: strict

"""Application DTO: factory functions that build response envelopes.

The envelope shape and error-code taxonomy live in
:mod:`envelope_dto`; this module provides the two constructors every
emission site uses (success / failure) so the wire shape is built in
exactly one place.
"""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.envelope_dto import ErrorCode


def success(
    command: str,
    *,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured success envelope.

    Used by *new* commands (``ping``, ``doctor``, ``batch``). Existing
    commands still emit the legacy flat shape for backward compatibility
    but can be migrated one at a time without breaking callers, because
    the flat shape is a strict subset of this one modulo the nested
    ``result`` dict.
    """
    return {
        "ok": True,
        "command": command,
        "args": args or {},
        "result": result or {},
        "error": None,
    }


def failure(
    command: str,
    code: ErrorCode,
    message: str,
    *,
    args: dict[str, Any] | None = None,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured failure envelope with a stable error code.

    ``hint`` is the human fix ("start LoopMIDI and create a port named
    flcli"), ``details`` carries any machine-readable context (available
    ports, failing field names, etc.). Either can be omitted; the error
    object only includes keys that have a value so jq patterns stay
    predictable.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if hint is not None:
        error["hint"] = hint
    if details is not None:
        error["details"] = details
    return {
        "ok": False,
        "command": command,
        "args": args or {},
        "result": None,
        "error": error,
    }
