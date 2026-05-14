# pyright: strict

"""Application DTO: re-exports the envelope DTO + factories.

Callers idiomatically import this as ``from ... import envelope as Env``
and reach for both the wire-shape constants (``Env.CODE_*``) and the
factory functions (``Env.success`` / ``Env.failure``) through a single
namespace.

The actual definitions live in two single-role modules so a maintainer
finds DTOs vs. factory functions without scrolling:

* :mod:`flstudio_cli.shared.application.envelope_dto` -- ``ErrorCode``,
  ``CODE_*`` constants, ``PROTOCOL_VERSION``, ``ERROR_CODES``.
* :mod:`flstudio_cli.shared.application.envelope_factory` -- ``success``
  and ``failure`` constructors.

This module is intentionally a re-export only — never define new
functions or types here.  Add them to the matching ``_dto`` /
``_factory`` module instead.
"""

from __future__ import annotations

from flstudio_cli.shared.application.envelope_dto import (
    CODE_AUTOMATION_FAILED,
    CODE_INTERNAL,
    CODE_INVALID_ARGUMENT,
    CODE_IO_ERROR,
    CODE_NOT_FOUND,
    CODE_PORT_NOT_FOUND,
    CODE_PROTOCOL_ERROR,
    CODE_TIMEOUT,
    CODE_UNKNOWN_COMMAND,
    ERROR_CODES,
    PROTOCOL_VERSION,
    ErrorCode,
)
from flstudio_cli.shared.application.envelope_factory import failure, success

__all__ = [
    "CODE_AUTOMATION_FAILED",
    "CODE_INTERNAL",
    "CODE_INVALID_ARGUMENT",
    "CODE_IO_ERROR",
    "CODE_NOT_FOUND",
    "CODE_PORT_NOT_FOUND",
    "CODE_PROTOCOL_ERROR",
    "CODE_TIMEOUT",
    "CODE_UNKNOWN_COMMAND",
    "ERROR_CODES",
    "PROTOCOL_VERSION",
    "ErrorCode",
    "failure",
    "success",
]
