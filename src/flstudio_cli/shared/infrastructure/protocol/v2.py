"""Infrastructure adapter: sysEx framing for protocol v2 (bidirectional transport).

The pure byte-level helpers (``pack_7bit`` / ``unpack_7bit`` /
``encode_request_id`` / ``decode_request_id``) delegate to
:mod:`flstudio_cli.shared.infrastructure.protocol._device_portable`,
which is the canonical implementation copied verbatim into the FL
Studio device script by ``scripts/gen_device_protocol.py``.  This
module wraps those helpers with the host-only contracts the typed
callers depend on:

* the :class:`SysExFrame` dataclass and the soft size cap on
  outbound payloads;
* :class:`MalformedFrame` / :class:`ProtocolMismatch` exception
  types instead of plain :class:`ValueError`, so callers can
  distinguish a wrong protocol version from any other framing
  failure;
* strict bookend validation on inbound frames (the device's
  ``_v2_decode_frame`` is more lenient because FL Studio sometimes
  strips the ``F0``/``F7`` bookends from ``event.sysex``).

Wire layout
-----------

Every protocol v2 frame is a single MIDI SysEx message::

    F0 7D 02 <rid0> <rid1> <rid2> <rid3> <packed_payload...> F7

``7D``
    Official non-commercial/educational manufacturer ID. One byte, 7-bit
    clean, no need for the three-byte extended form.
``02``
    Protocol version. The device script rejects any frame whose version
    byte is not exactly ``2`` with :class:`ProtocolMismatch`, so a stray
    v1 client cannot accidentally corrupt a v2 session.
``<rid0..3>``
    28-bit monotonic ``request_id`` assigned by the CLI, MSB-first, each
    byte ``<= 0x7F``. 2**28 distinct ids per session is comfortable even
    for a long ``batch stream`` run.
``<packed_payload>``
    UTF-8 JSON, packed 8 -> 7 bits by the canonical Roland-style scheme
    (see :func:`pack_7bit`). The guarantee is: after packing, no byte in
    the payload region has its high bit set, so the SysEx frame survives
    every MIDI transport on the planet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from flstudio_cli.shared.infrastructure.protocol import _device_portable as _portable

# --- Wire constants --------------------------------------------------------

SYSEX_START: Final[int] = 0xF0
SYSEX_END: Final[int] = 0xF7

#: Official non-commercial / educational manufacturer ID (one byte).
VENDOR_ID: Final[int] = _portable.SYSEX_VENDOR_ID

#: Current protocol version. Bumped if the frame layout ever changes.
PROTOCOL_VERSION_V2: Final[int] = _portable.SYSEX_PROTOCOL_V2

REQUEST_ID_BYTES: Final[int] = _portable.SYSEX_REQUEST_ID_BYTES
#: Derived from ``REQUEST_ID_BYTES`` so the wire bit-budget cannot
#: drift if a future device change widens the request id.
REQUEST_ID_BITS: Final[int] = REQUEST_ID_BYTES * 7
REQUEST_ID_MAX: Final[int] = _portable.SYSEX_REQUEST_ID_MAX

#: Soft cap on packed payload size. Keeps frames within the typical USB
#: MIDI stack buffer (~4 KB). Larger responses are expected to carry a
#: ``"truncated": true`` flag; pagination is out of scope for v2.
MAX_PACKED_PAYLOAD_BYTES: Final[int] = 4096


# --- Exceptions ------------------------------------------------------------


class ProtocolMismatch(ValueError):
    """Raised when a frame carries a non-V2 version byte."""


class MalformedFrame(ValueError):
    """Raised when a frame is structurally invalid."""


# --- Data ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SysExFrame:
    """A decoded protocol v2 frame: request id + raw (unpacked) JSON bytes."""

    request_id: int
    payload: bytes


# --- 8 -> 7 bit packing ----------------------------------------------------
#
# These are thin wrappers around the device-portable implementations.
# The host-side ``unpack_7bit`` re-raises ``ValueError`` as
# ``MalformedFrame`` so consumers can distinguish wire-format errors
# from generic value errors.


def pack_7bit(data: bytes) -> bytes:
    """Pack 8-bit data into 7-bit safe SysEx payload bytes.

    Round-trips exactly with :func:`unpack_7bit`; the output is
    guaranteed 7-bit clean.
    """
    return _portable._v2_pack_7bit(data)


def unpack_7bit(packed: bytes) -> bytes:
    """Inverse of :func:`pack_7bit`.

    Raises :class:`MalformedFrame` if the input is malformed (a byte
    with its high bit set, or a lone MSB byte with no following data).
    """
    try:
        return _portable._v2_unpack_7bit(packed)
    except ValueError as exc:
        raise MalformedFrame(str(exc)) from exc


# --- Request id ------------------------------------------------------------


def encode_request_id(request_id: int) -> bytes:
    """Encode a 28-bit request id as 4 MSB-first 7-bit bytes."""
    return _portable._v2_encode_request_id(request_id)


def decode_request_id(four_bytes: bytes) -> int:
    """Inverse of :func:`encode_request_id`."""
    try:
        return _portable._v2_decode_request_id(four_bytes)
    except ValueError as exc:
        raise MalformedFrame(str(exc)) from exc


# --- Frame encode / decode -------------------------------------------------


def _check_packed_payload_size(packed_len: int) -> None:
    """Enforce the soft cap on packed payload size for outbound frames."""
    if packed_len > MAX_PACKED_PAYLOAD_BYTES:
        raise ValueError(
            f"packed payload exceeds soft limit of "
            f"{MAX_PACKED_PAYLOAD_BYTES} bytes (got {packed_len})"
        )


def encode_frame(frame: SysExFrame) -> bytes:
    """Build the full ``F0..F7`` wire bytes for a frame.

    Every byte between ``F0`` and ``F7`` (exclusive) is guaranteed 7-bit
    clean by construction.
    """
    packed = pack_7bit(frame.payload)
    _check_packed_payload_size(len(packed))
    out = bytearray()
    out.append(SYSEX_START)
    out.append(VENDOR_ID)
    out.append(PROTOCOL_VERSION_V2)
    out.extend(encode_request_id(frame.request_id))
    out.extend(packed)
    out.append(SYSEX_END)
    return bytes(out)


def _validate_frame_header(raw: bytes) -> None:
    """Validate the SysEx bookends, vendor id, and protocol version.

    Stricter than the device-side ``_v2_decode_frame`` -- the host is
    talking to a real serial wire and never gets a stripped frame, so
    a missing bookend really is a structural error.  Raises
    :class:`MalformedFrame` for structural problems and
    :class:`ProtocolMismatch` for a wrong version byte.
    """
    minimum_frame_length = 2 + 1 + 1 + REQUEST_ID_BYTES  # F0 vendor ver rid F7
    if len(raw) < minimum_frame_length:
        raise MalformedFrame(f"frame too short: {len(raw)} bytes")
    if raw[0] != SYSEX_START:
        raise MalformedFrame(f"missing SysEx start byte (got 0x{raw[0]:02x})")
    if raw[-1] != SYSEX_END:
        raise MalformedFrame(f"missing SysEx end byte (got 0x{raw[-1]:02x})")
    if raw[1] != VENDOR_ID:
        raise MalformedFrame(
            f"unexpected vendor id 0x{raw[1]:02x} (want 0x{VENDOR_ID:02x})"
        )
    if raw[2] != PROTOCOL_VERSION_V2:
        raise ProtocolMismatch(
            f"protocol version 0x{raw[2]:02x} does not match "
            f"supported 0x{PROTOCOL_VERSION_V2:02x}"
        )


def decode_frame(raw: bytes) -> SysExFrame:
    """Validate ``F0 7D 02 <rid> <packed> F7`` and return a :class:`SysExFrame`."""
    _validate_frame_header(raw)
    request_id = decode_request_id(raw[3 : 3 + REQUEST_ID_BYTES])
    payload = unpack_7bit(raw[3 + REQUEST_ID_BYTES : -1])
    return SysExFrame(request_id=request_id, payload=payload)


# --- High-level JSON helpers -----------------------------------------------


def build_command(cmd: str, args: dict[str, Any] | None = None) -> bytes:
    """Serialise a v2 command payload to JSON bytes.

    The result is suitable for :attr:`SysExFrame.payload`. Matches the
    shape the device script's :class:`V2Dispatcher` expects::

        {"cmd": "tempo", "args": {"bpm": 140.5}}
    """
    body: dict[str, Any] = {"cmd": cmd}
    if args:
        body["args"] = args
    else:
        body["args"] = {}
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def parse_response(payload: bytes) -> dict[str, Any]:
    """Parse a response payload emitted by the device script.

    Decoded shape::

        {"request_id": int, "ok": bool, "command": str,
         "result": dict | None, "error": dict | None}

    Raises :class:`MalformedFrame` if the payload is not valid JSON or
    not a JSON object.
    """
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedFrame(f"response payload is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise MalformedFrame(
            f"response payload must be a JSON object, got {type(decoded).__name__}"
        )
    return decoded
