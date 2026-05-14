"""Infrastructure adapter: device-portable protocol v2 framing.

This module is the canonical source for the protocol v2 helpers that
live inside ``device_flcli.py``.  ``scripts/gen_device_protocol.py``
copies the body of this file verbatim between the
``# === BEGIN AUTO-GENERATED PROTOCOL ===`` /
``# === END AUTO-GENERATED PROTOCOL ===`` markers in the device
script, removing the manual sync pre-#89 PRs needed.

Style constraints (kept narrow on purpose):

* No type hints, no ``__future__`` imports, no ``Final`` aliases --
  the file is pasted into FL Studio's embedded Python sandbox where
  the simplest dialect avoids surprises.
* No imports from ``typing`` or ``dataclasses``.
* Only ``ValueError`` is raised; the host side wraps these in
  :class:`MalformedFrame` / :class:`ProtocolMismatch` separately.
* Function names carry the ``_v2_`` prefix that the device's
  ``OnSysEx`` handler expects.

Round-trip equivalence with the host's typed implementation is
pinned by ``shared/infrastructure/fl_device/tests/test_device_v2.py``,
so any drift between this module and ``protocol/v2.py`` shows up as
a test failure.
"""

# === BEGIN AUTO-GENERATED PROTOCOL ===

SYSEX_VENDOR_ID = 0x7D
SYSEX_PROTOCOL_V2 = 2
SYSEX_REQUEST_ID_BYTES = 4
SYSEX_REQUEST_ID_MAX = (1 << 28) - 1


def _v2_pack_7bit(data):
    """Pack 8-bit bytes into 7-bit SysEx-safe bytes (Roland-style)."""
    if not data:
        return b""
    out = bytearray()
    index = 0
    length = len(data)
    while index < length:
        block = data[index : index + 7]
        msb_byte = 0
        for block_index, source_byte in enumerate(block):
            if source_byte & 0x80:
                msb_byte |= 1 << block_index
        out.append(msb_byte)
        for source_byte in block:
            out.append(source_byte & 0x7F)
        index += 7
    return bytes(out)


def _v2_unpack_7bit(packed):
    """Inverse of ``_v2_pack_7bit``. Raises ``ValueError`` on malformed input."""
    if not packed:
        return b""
    for byte in packed:
        if byte & 0x80:
            raise ValueError("packed payload byte has high bit set")
    out = bytearray()
    index = 0
    length = len(packed)
    while index < length:
        msb_byte = packed[index]
        index += 1
        remaining = length - index
        block_len = 7 if remaining >= 7 else remaining
        if block_len == 0:
            raise ValueError("trailing MSB byte with no data bytes")
        for byte_index in range(block_len):
            data_byte = packed[index + byte_index]
            if msb_byte & (1 << byte_index):
                data_byte |= 0x80
            out.append(data_byte)
        index += block_len
    return bytes(out)


def _v2_encode_request_id(request_id):
    if request_id < 0 or request_id > SYSEX_REQUEST_ID_MAX:
        raise ValueError("request_id out of range")
    return bytes(
        (request_id >> (7 * (SYSEX_REQUEST_ID_BYTES - 1 - i))) & 0x7F
        for i in range(SYSEX_REQUEST_ID_BYTES)
    )


def _v2_decode_request_id(four_bytes):
    if len(four_bytes) != SYSEX_REQUEST_ID_BYTES:
        raise ValueError("request id must be 4 bytes")
    value = 0
    for byte in four_bytes:
        if byte & 0x80:
            raise ValueError("request id byte has high bit set")
        value = (value << 7) | byte
    return value


def _v2_encode_frame(request_id, payload_bytes):
    """Encode ``F0 7D 02 <rid> <packed_payload> F7``."""
    out = bytearray()
    out.append(0xF0)
    out.append(SYSEX_VENDOR_ID)
    out.append(SYSEX_PROTOCOL_V2)
    out.extend(_v2_encode_request_id(request_id))
    out.extend(_v2_pack_7bit(payload_bytes))
    out.append(0xF7)
    return bytes(out)


def _v2_decode_frame(raw):
    """Validate and decode a v2 frame. Returns ``(request_id, payload_bytes)``.

    Accepts either the full ``F0 ... F7`` byte string or the interior
    bytes; FL Studio builds differ in whether they preserve the
    bookends on ``event.sysex``.
    """
    if not raw:
        raise ValueError("empty SysEx frame")
    buffer = raw
    if buffer[0] != 0xF0 or buffer[-1] != 0xF7:
        buffer = bytes([0xF0]) + bytes(buffer) + bytes([0xF7])
    if len(buffer) < 2 + 1 + 1 + SYSEX_REQUEST_ID_BYTES:
        raise ValueError("frame too short")
    if buffer[1] != SYSEX_VENDOR_ID:
        raise ValueError("unexpected vendor id")
    if buffer[2] != SYSEX_PROTOCOL_V2:
        raise ValueError("protocol version mismatch")
    rid = _v2_decode_request_id(buffer[3 : 3 + SYSEX_REQUEST_ID_BYTES])
    packed = buffer[3 + SYSEX_REQUEST_ID_BYTES : -1]
    payload = _v2_unpack_7bit(packed)
    return rid, payload


# === END AUTO-GENERATED PROTOCOL ===
