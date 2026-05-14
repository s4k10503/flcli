"""Transport layer — every adapter that speaks to FL Studio (or a fake).

Modules
-------
midi_sink
    Concrete :class:`~flstudio_cli.shared.application.ports.CommandTransport`
    backed by ``mido`` (:class:`MidoCommandTransport`), plus port discovery
    helpers (``list_output_ports``, ``resolve_port``).
return_port
    Thread-safe pending-request table that pairs outgoing frames with
    their response envelopes via ``request_id``.
recording_sink
    Decorator that wraps any transport and writes a JSONL trace of every
    outgoing frame for later replay or debugging.
replay_sink
    The inverse of ``recording_sink``: replays a previously recorded
    JSONL trace so integration tests can run deterministically without a
    live MIDI port.
"""
