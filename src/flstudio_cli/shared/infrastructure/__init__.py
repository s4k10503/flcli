"""Infrastructure layer — every external concern lives here.

Onion architecture: the ``application`` and ``domain`` layers never
import from this package directly. Concrete adapters are wired up by
the composition root in :mod:`flstudio_cli.shared.composition`, which is the
only inward-facing module allowed to reach in here.

Sub-packages
------------
protocol
    Pure SysEx wire format (constants, v2 framing) for the FL Studio
    device script. No I/O, no ``mido`` import — but still
    infrastructure because it is a transport-specific concern that
    would be replaced wholesale if we swapped MIDI for another
    transport.
transport
    Command/response transport adapters: ``CommandTransport`` /
    ``ReturnPort`` implementations backed by ``mido``, plus the
    recording / replay decorators used for deterministic tests.
flp
    FLP file manipulation via ``pyflp`` (read-only project introspection
    plus the patch helpers used by the ``flp`` CLI group).
fl_device
    Host-side fixtures and the codegen-shared device script that the
    CLI exchanges SysEx frames with.

Modules
-------
io_utils
    Atomic file write helper used by snapshot/queue persistence.
os_automation
    OS-level keyboard automation used by the realtime piano-roll
    record flow.
"""
