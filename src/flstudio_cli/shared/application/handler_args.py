"""Use case: argument-coercion helpers shared by every feature's BATCH_HANDLERS.

Each per-feature ``<feature>/application/handlers.py`` validates its
incoming ``dict[str, Any]`` payload through these helpers before
forwarding to the typed :class:`FlCommandPort` wrapper.  Missing keys
raise :class:`ValueError`; type mismatches raise :class:`TypeError`.
The :func:`~flstudio_cli.shared.application.handler_workflow.lift_exceptions`
decorator catches both and lifts them into the typed
:class:`Err[InvalidArgument]` channel of the handler outcome, so the
distinction is invisible to callers but lets ``ruff`` (TRY004) keep the
type-vs-value boundary honest.

This module lives in ``shared.application`` rather than under any
single feature so the dependency arrow stays
``feature → shared``; previously these helpers were exported from
``batch.application.batch_handlers``, which made every feature import
``batch`` (see #114).
"""

# pyright: strict

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, overload

__all__ = [
    "ArgsLike",
    "optional_bool",
    "optional_int",
    "optional_string",
    "require",
    "require_bool",
    "require_float",
    "require_int",
    "require_string",
]


#: Read-only view of a wire payload — accepts both raw ``dict[str, Any]``
#: and a per-handler :class:`typing.TypedDict` view of the same data.
ArgsLike = Mapping[str, Any]


def require(args: ArgsLike, key: str) -> Any:
    """Return *args[key]* or raise :class:`ValueError` if missing."""
    if key not in args:
        raise ValueError(f"missing required argument: {key!r}")
    return args[key]


def require_string(args: ArgsLike, key: str) -> str:
    """Return *args[key]* as a :class:`str`, raising :class:`TypeError` on mismatch."""
    value = require(args, key)
    if not isinstance(value, str):
        raise TypeError(f"{key!r} must be a string")
    return value


def require_int(args: ArgsLike, key: str) -> int:
    """Return *args[key]* as an :class:`int`, raising :class:`TypeError` on mismatch."""
    value = require(args, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key!r} must be a number")
    return int(value)


def require_float(args: ArgsLike, key: str) -> float:
    """Return *args[key]* as a :class:`float`, raising :class:`TypeError` on mismatch."""
    value = require(args, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key!r} must be a number")
    return float(value)


def require_bool(args: ArgsLike, key: str) -> bool:
    """Return *args[key]* validated as a :class:`bool`, raising :class:`TypeError` on mismatch.

    Strict: a non-bool value (e.g. the string ``"false"`` from a hand-edited
    JSON file) raises :class:`TypeError` rather than being silently coerced
    to ``True``.
    """
    value = require(args, key)
    if not isinstance(value, bool):
        raise TypeError(f"{key!r} must be a boolean")
    return value


@overload
def optional_int(args: ArgsLike, key: str) -> int | None: ...
@overload
def optional_int(args: ArgsLike, key: str, *, default: int) -> int: ...
def optional_int(args: ArgsLike, key: str, *, default: int | None = None) -> int | None:
    """Return :func:`require_int` for *key*, falling back to *default* if absent."""
    return require_int(args, key) if key in args else default


@overload
def optional_string(args: ArgsLike, key: str) -> str | None: ...
@overload
def optional_string(args: ArgsLike, key: str, *, default: str) -> str: ...
def optional_string(
    args: ArgsLike, key: str, *, default: str | None = None
) -> str | None:
    """Return :func:`require_string` for *key*, falling back to *default* if absent."""
    return require_string(args, key) if key in args else default


@overload
def optional_bool(args: ArgsLike, key: str) -> bool | None: ...
@overload
def optional_bool(args: ArgsLike, key: str, *, default: bool) -> bool: ...
def optional_bool(
    args: ArgsLike, key: str, *, default: bool | None = None
) -> bool | None:
    """Return :func:`require_bool` for *key*, falling back to *default* if absent."""
    return require_bool(args, key) if key in args else default
