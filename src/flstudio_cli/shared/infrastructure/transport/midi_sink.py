"""Infrastructure adapter: MIDI-backed implementation of :class:`CommandTransport`.

This is the only module that imports ``mido`` for the **control path**.
(The piano-roll real-time recorder imports ``mido`` separately because
it opens its own output port on a non-control MIDI channel.)

The :class:`MidiPortNotFound` exception type lives in the application
layer (:mod:`flstudio_cli.shared.application.transport_errors`) so
the dispatcher can catch it without importing infrastructure; this
module re-exports it for callers already on the infra side.

Public API
----------
* :class:`MidoCommandTransport` -- concrete transport backed by a real
  ``mido`` output port.
* :class:`MidiPortNotFound` -- typed error for "no port matches"
  (re-exported from application layer).
* :func:`list_output_ports` -- enumerate visible MIDI outputs.
* :func:`resolve_port` -- case-insensitive substring port lookup.
"""

from __future__ import annotations

import mido

from flstudio_cli.shared.application.transport_errors import MidiPortNotFound

__all__ = [
    "MidiPortNotFound",
    "MidoCommandTransport",
    "list_output_ports",
    "resolve_port",
]


def list_output_ports() -> list[str]:
    """Return every MIDI output port visible to the current process."""
    return [str(name) for name in mido.get_output_names()]


def resolve_port(requested_name: str | None, default_name: str) -> str:
    """Find a port whose name contains ``requested_name`` (or ``default_name``).

    Matching is case-insensitive and substring-based so users can pass
    short aliases like ``"flcli"`` instead of the full LoopMIDI /
    IAC driver name.
    """
    search_term = requested_name or default_name
    for available_port in mido.get_output_names():
        if search_term.lower() in available_port.lower():
            return str(available_port)
    raise MidiPortNotFound(
        f"MIDI output port matching {search_term!r} not found. "
        f"Available: {mido.get_output_names()}"
    )


class MidoCommandTransport:
    """:class:`CommandTransport` backed by a real ``mido`` output port."""

    def __init__(self, port_name: str) -> None:
        self._port = mido.open_output(port_name)

    def send_frame(self, frame: bytes) -> None:
        """Send a protocol v2 SysEx frame.

        ``frame`` is the complete ``F0 ... F7`` byte string.  ``mido``
        expects the ``data`` field to exclude the start/end bookends
        (it re-adds them when writing to the wire), so we strip them
        before handing the payload over.
        """
        if len(frame) < 2 or frame[0] != 0xF0 or frame[-1] != 0xF7:
            raise ValueError("SysEx frame must begin with 0xF0 and end with 0xF7")
        self._port.send(mido.Message("sysex", data=tuple(frame[1:-1])))

    def close(self) -> None:
        self._port.close()
