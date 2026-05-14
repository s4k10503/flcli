"""Composition root: transport selection and lifecycle wiring.

Selects the appropriate :class:`CommandTransport` / :class:`ReturnPort`
pair based on environment variables (``FLCLI_REPLAY``, ``FLCLI_RECORD``)
and exposes ``open_daw_controller`` and ``open_piano_roll_note_sink``
convenience constructors that hand the application a fully wired
session.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO, Any

from flstudio_cli.shared.application import midi_routing as P
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.application.ports import (
    CommandTransport,
    FrameCodec,
    NoteEventSink,
    ReturnPort,
)
from flstudio_cli.shared.infrastructure.protocol import v2 as _V2
from flstudio_cli.shared.infrastructure.transport.midi_sink import (
    MidoCommandTransport,
    resolve_port,
)
from flstudio_cli.shared.infrastructure.transport.return_port import MidoReturnPort


def _encode_command_frame_v2(
    cmd: str,
    args: dict[str, Any] | None,
    request_id: int,
) -> bytes:
    payload = _V2.build_command(cmd, args)
    return _V2.encode_frame(_V2.SysExFrame(request_id=request_id, payload=payload))


#: Production codec: protocol v2 wire format wired from infrastructure.
PRODUCTION_FRAME_CODEC: FrameCodec = FrameCodec(
    encode_command_frame=_encode_command_frame_v2,
    request_id_max=_V2.REQUEST_ID_MAX,
)


def _live_transport(port_name: str | None) -> CommandTransport:
    return MidoCommandTransport(resolve_port(port_name, P.DEFAULT_PORT_NAME))


def _live_return_port(return_port_name: str | None) -> ReturnPort:
    return MidoReturnPort(
        resolve_port(return_port_name, P.DEFAULT_RETURN_PORT_NAME),
    )


def build_transport(
    port_name: str | None = None,
    return_port_name: str | None = None,
) -> tuple[CommandTransport, ReturnPort, IO[Any] | None]:
    """Build ``(transport, return_port, trace_file_handle)`` from env + args.

    Priority: ``FLCLI_REPLAY`` > ``FLCLI_RECORD`` > default (live MIDI).
    The caller owns all three returned resources and is responsible for
    closing them (``DawController.__exit__`` does this in the common path).
    """
    replay_path = os.environ.get("FLCLI_REPLAY")
    record_path = os.environ.get("FLCLI_RECORD")

    if replay_path:
        from flstudio_cli.shared.infrastructure.transport.replay_sink import (
            ReplayCommandTransport,
            ReplayReturnPort,
            load_trace,
        )

        fh: IO[Any] = Path(replay_path).open()  # noqa: SIM115
        out_events, in_events = load_trace(fh)
        rp: ReturnPort = ReplayReturnPort(in_events)
        transport: CommandTransport = ReplayCommandTransport(out_events, return_port=rp)
        return transport, rp, fh

    if record_path:
        from flstudio_cli.shared.infrastructure.transport.recording_sink import (
            RecordingCommandTransport,
        )

        # Line-buffered so a Ctrl-C / crash mid-run still leaves the trace
        # readable through the last completed event, without paying for an
        # explicit ``flush`` on every outgoing frame.
        fh = Path(record_path).open("w", buffering=1)  # noqa: SIM115
        transport = RecordingCommandTransport(_live_transport(port_name), fh)
        return transport, _live_return_port(return_port_name), fh

    return _live_transport(port_name), _live_return_port(return_port_name), None


def open_daw_controller(
    port_name: str | None = None,
    return_port_name: str | None = None,
) -> DawController:
    """Build a fully-wired :class:`DawController` ready for ``with`` use."""
    transport, return_port, trace_fh = build_transport(
        port_name=port_name,
        return_port_name=return_port_name,
    )
    return DawController(
        transport, return_port, PRODUCTION_FRAME_CODEC, _trace_fh=trace_fh
    )


def open_piano_roll_note_sink(port_name: str | None) -> NoteEventSink:
    """Open a mido output port and return it as a :class:`NoteEventSink`.

    Bridges the application's note-event Port to a real ``mido`` port so
    the realtime recorder doesn't need to import ``mido`` itself.
    """
    import mido as _mido

    resolved = resolve_port(port_name, P.DEFAULT_PORT_NAME)
    port = _mido.open_output(resolved)

    def _send(kind: str, pitch: int, velocity: int, channel: int) -> None:
        port.send(_mido.Message(kind, note=pitch, velocity=velocity, channel=channel))

    return NoteEventSink(
        send_note_on=lambda p, v, c: _send("note_on", p, v, c),
        send_note_off=lambda p, v, c: _send("note_off", p, v, c),
        close=port.close,
    )
