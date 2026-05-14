"""Application DTO: typed wire response from FL Studio over protocol v2.

The controller's ``send_and_wait`` returns a raw envelope dict because
the wire format is JSON-shaped and the transport layer cares about
nothing more.  Every consumer that interprets the response (the batch
executor, the CLI shell helpers) ``match``-es on the typed sum defined
here so the success / failure branches are exhaustive.

The parser that converts a raw dict into one of these variants lives
in :mod:`device_response_parser`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["DeviceErr", "DeviceOk", "DeviceResponse"]


@dataclass(frozen=True, slots=True)
class DeviceOk:
    """Success branch of a v2 device response."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceErr:
    """Failure branch of a v2 device response.

    ``code`` is one of the :mod:`flstudio_cli.shared.application.envelope_dto`
    constants when the device emits a recognised error; an unknown code
    is preserved verbatim so the executor can still surface it.
    """

    code: str
    message: str
    hint: str | None = None
    details: dict[str, Any] | None = None


#: Closed sum of every legal v2 device response.
DeviceResponse = DeviceOk | DeviceErr
