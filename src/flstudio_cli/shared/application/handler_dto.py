"""Application DTO: successful outputs from a batch handler.

The two variants together form the closed sum :data:`HandlerOutput`,
the "successful" half of the handler outcome.  The error half lives
in :mod:`handler_errors`; the type alias that wires both together
plus the decorator that lifts exceptions into the typed channel live
in :mod:`handler_workflow`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["DeviceCommand", "HandlerOutput", "LocalResult"]


@dataclass(frozen=True, slots=True)
class DeviceCommand:
    """A validated command ready to ship to FL Studio over SysEx.

    The ``cmd`` string and ``args`` dict together form the wire-format
    request the controller will encode.  Producing a ``DeviceCommand``
    is the contract every handler that talks to the device satisfies.
    """

    cmd: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LocalResult:
    """A handler that operates on local state only -- never touches the device.

    Carries the final ``result`` dict the executor will place in the
    success envelope.  Used by handlers like ``piano_roll_show`` whose
    answer comes from a file on disk rather than from FL Studio.
    """

    result: dict[str, Any]


#: Closed sum of every legal successful handler output.
HandlerOutput = DeviceCommand | LocalResult
