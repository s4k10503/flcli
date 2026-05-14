"""Application DTO: parser for raw device-response envelopes.

Every consumer that interprets a v2 response would otherwise repeat
``response.get("ok")`` / ``response.get("error")`` probing.  This
parser collapses the probing into a single seam that returns a typed
:data:`DeviceResponse` sum.

The parser is permissive on missing keys: the device script has been
seen to emit slightly malformed envelopes when it panics.  An
envelope without ``ok`` (or with ``ok=True`` but no ``result``) falls
back to an empty result dict, and a missing ``error`` collapses to a
generic :class:`DeviceErr` with ``code=INTERNAL``.  The failure path
stays inside the typed channel rather than spilling into ``KeyError``.
"""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.device_response_dto import (
    DeviceErr,
    DeviceOk,
    DeviceResponse,
)

__all__ = ["parse_device_response"]


def parse_device_response(envelope: dict[str, Any]) -> DeviceResponse:
    """Project a raw wire envelope onto the typed :data:`DeviceResponse` sum."""
    if envelope.get("ok"):
        return DeviceOk(result=envelope.get("result") or {})
    error = envelope.get("error") or {}
    return DeviceErr(
        code=error.get("code", Env.CODE_INTERNAL),
        message=error.get("message", "device command failed"),
        hint=error.get("hint"),
        details=error.get("details"),
    )
