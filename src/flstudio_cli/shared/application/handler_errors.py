"""Application DTO: typed validation failures emitted by batch handlers.

Each variant maps deterministically to one envelope error code; the
:func:`lift_exceptions` decorator in :mod:`handler_workflow` is the
seam that converts the matching Python exception into the right
variant.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FileIOError", "FileMissing", "HandlerError", "InvalidArgument"]


@dataclass(frozen=True, slots=True)
class InvalidArgument:
    """Bad input -- wrong type, out-of-range value, missing required field.

    Maps to envelope code ``INVALID_ARGUMENT`` (exit 2).
    """

    message: str


@dataclass(frozen=True, slots=True)
class FileMissing:
    """A file the handler expected to read does not exist.

    Maps to envelope code ``NOT_FOUND`` (exit 3).
    """

    path: str


@dataclass(frozen=True, slots=True)
class FileIOError:
    """A filesystem I/O error during handler execution.

    Maps to envelope code ``IO_ERROR`` (exit 4).
    """

    message: str


#: Closed sum: every legal handler-side failure is one of these.
HandlerError = InvalidArgument | FileMissing | FileIOError
