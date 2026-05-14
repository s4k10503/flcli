"""Use case: BatchHandler signature, exception lift, registry merge.

Wires the DTOs in :mod:`handler_dto` and the errors in
:mod:`handler_errors` together as the public batch-handler contract:

* :data:`BatchHandler` -- the callable shape every per-feature
  ``application/handlers.py`` implements.
* :func:`lift_exceptions` -- decorator that lets handler bodies stay
  in the imperative ``raise`` style while still satisfying the typed
  :class:`Outcome` boundary.
* :func:`make_handlers` -- merges per-feature registries with
  collision detection at composition time.

See :mod:`flstudio_cli.batch.application.batch_executor` for the
executor that projects each variant onto the response envelope.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from flstudio_cli.shared.application.handler_dto import HandlerOutput
from flstudio_cli.shared.application.handler_errors import (
    FileIOError,
    FileMissing,
    HandlerError,
    InvalidArgument,
)
from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

__all__ = ["BatchHandler", "lift_exceptions", "make_handlers"]


BatchHandler = Callable[[dict[str, Any]], "Outcome[HandlerOutput, HandlerError]"]


def lift_exceptions(
    fn: Callable[[dict[str, Any]], HandlerOutput],
) -> BatchHandler:
    """Wrap a handler so common exceptions become typed :data:`Err` values.

    The handler body returns a :class:`DeviceCommand` or
    :class:`LocalResult` directly; any of the four "validation-shaped"
    exceptions (``ValueError`` / ``TypeError`` / ``FileNotFoundError`` /
    ``OSError``) are caught and translated into the corresponding
    :data:`HandlerError` variant.  Anything else propagates -- a
    handler bug should not be silently encoded as a user error.
    """

    @functools.wraps(fn)
    def wrapped(args: dict[str, Any]) -> Outcome[HandlerOutput, HandlerError]:
        try:
            return Ok(fn(args))
        except FileNotFoundError as exc:
            return Err(FileMissing(path=str(exc)))
        except OSError as exc:
            return Err(FileIOError(message=str(exc)))
        except (ValueError, TypeError) as exc:
            return Err(InvalidArgument(message=str(exc)))

    return wrapped


def make_handlers(
    *handler_groups: dict[str, BatchHandler],
) -> dict[str, BatchHandler]:
    """Merge per-feature ``BATCH_HANDLERS`` dicts into a single registry.

    Collisions raise :class:`RuntimeError` to fail fast on
    double-registration; the composition root in ``__main__`` calls
    this once with every per-feature dict (plus the DI-bound output of
    each ``composition.compose``) and publishes the result on
    ``ctx.obj`` for ``batch run`` / ``batch stream`` to consume.
    """
    merged: dict[str, BatchHandler] = {}
    for group in handler_groups:
        collisions = merged.keys() & group.keys()
        if collisions:
            raise RuntimeError(f"command(s) registered twice: {sorted(collisions)}")
        merged.update(group)
    return merged
