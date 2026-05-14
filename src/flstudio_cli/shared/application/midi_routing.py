# pyright: strict

"""Application DTO: MIDI routing — CLI-side contract with the device script.

These are **application-level** constants because they describe the
CLI's agreement with FL Studio (which port name to default to, which
channel carries control vs. piano-roll traffic).  They are *not*
wire-format details (those live in
:mod:`flstudio_cli.shared.infrastructure.protocol._device_portable`)
and *not* musical-domain knowledge (drum names live in
:mod:`flstudio_cli.piano_roll.domain.drums`).

The typed error :class:`MidiPortNotFound` lives in
:mod:`flstudio_cli.shared.application.transport_errors` to keep this
module free of error definitions.

Onion direction: application owns this contract; composition reads it
when wiring transport adapters.  No layer points outward.
"""

from __future__ import annotations

from typing import Final

#: Default output port name the CLI opens for sending commands.
DEFAULT_PORT_NAME: Final[str] = "flcli"

#: Default *input* port name the CLI opens to receive SysEx responses.
DEFAULT_RETURN_PORT_NAME: Final[str] = "flcli-rx"

#: Channel the device script listens on for control traffic.
CONTROL_MIDI_CHANNEL: Final[int] = 0

#: Realtime piano-roll recording uses this channel so events bypass
#: the device script entirely and reach FL Studio's standard MIDI
#: recorder.
PIANO_ROLL_MIDI_CHANNEL: Final[int] = 1
