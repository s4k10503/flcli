"""SysEx wire protocol — vendor / version constants and v2 framing.

This package is **pure**: no ``mido`` import, no OS calls, no threads.
It defines the wire-level framing (vendor id, protocol version, 7-bit
packing, SysEx frame encode/decode) used by both the CLI transport and
the FL Studio device script.

Layer placement: this is **infrastructure** because the byte-level
framing is a technical detail of how the CLI talks to the device, not
part of the FL Studio musical domain.  Application code never imports
from here directly; composition wires the codec into
:class:`DawController` via :class:`FrameCodec`.

Submodules
----------
_device_portable
    Sandbox-friendly source of the wire constants and frame helpers.
    The body between the BEGIN / END markers is what
    ``scripts/gen_device_protocol.py`` copies into ``device_flcli.py``.
v2
    Host-side typed wrappers around ``_device_portable``: ``SysExFrame``
    dataclass, ``MalformedFrame`` / ``ProtocolMismatch`` exception
    distinction, and the soft size cap on outbound payloads.
"""

from flstudio_cli.shared.infrastructure.protocol._device_portable import (
    SYSEX_PROTOCOL_V2,
    SYSEX_VENDOR_ID,
)
from flstudio_cli.shared.infrastructure.protocol.v2 import (
    MalformedFrame,
    ProtocolMismatch,
    SysExFrame,
    build_command,
    decode_frame,
    encode_frame,
    parse_response,
)

__all__ = [
    "SYSEX_PROTOCOL_V2",
    "SYSEX_VENDOR_ID",
    "MalformedFrame",
    "ProtocolMismatch",
    "SysExFrame",
    "build_command",
    "decode_frame",
    "encode_frame",
    "parse_response",
]
