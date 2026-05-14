# pyright: strict

"""Application DTO: typed error values for the MIDI transport port.

The infrastructure adapter
(:mod:`flstudio_cli.shared.infrastructure.transport.midi_sink`) raises
:class:`MidiPortNotFound` when port resolution fails so the
dispatcher can map it deterministically to ``CODE_PORT_NOT_FOUND``.
``MidiPortNotFound`` subclasses :class:`RuntimeError` so legacy
callers that catch ``RuntimeError`` keep working unchanged.

Onion direction: application owns this contract; infrastructure
imports it when implementing the transport adapter.
"""

from __future__ import annotations


class MidiPortNotFound(RuntimeError):
    """No MIDI port matches the requested name."""
