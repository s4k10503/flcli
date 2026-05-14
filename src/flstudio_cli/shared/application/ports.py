"""Application port: onion-architecture inversion seam (Protocols + bundles).

The application layer talks to outer-layer effects (MIDI, file system,
OS) only through the abstractions defined here. Concrete back-ends live
in :mod:`flstudio_cli.shared.infrastructure.transport` and
:mod:`flstudio_cli.shared.infrastructure` and *implement* these
Ports without the application ever importing them.

Style
-----
We favour ``typing.Protocol`` for behaviour surfaces (structural typing
keeps adapters free of explicit base classes) and frozen dataclasses
for *bundles of plain functions* — the functional-style equivalent of
"a record of effects". Composition wiring lives in
:mod:`flstudio_cli.shared.composition`, which is the only module that imports
both Ports and concrete adapters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from flstudio_cli.shared.domain.note import Note

# ---------------------------------------------------------------------------
# Transport Ports (used by DawController)
# ---------------------------------------------------------------------------


class PendingResponse(Protocol):
    """Handle to one in-flight SysEx request awaiting its response envelope."""

    def wait(self, timeout_seconds: float) -> dict[str, Any]: ...


class CommandTransport(Protocol):
    """Outbound transport for command frames addressed to the device.

    The application layer treats every wire format as opaque bytes —
    the concrete shape (SysEx today, JSON-over-WebSocket tomorrow)
    lives behind this Port and a matching :class:`FrameCodec`.
    """

    def send_frame(self, frame: bytes) -> None: ...
    def close(self) -> None: ...


class ReturnPort(Protocol):
    """Inbound channel for SysEx response envelopes from FL Studio.

    The sender thread calls :meth:`register` to obtain a
    :class:`PendingResponse`, then blocks on its ``wait()``. The
    receiver side (rtmidi callback or test harness) is the adapter's
    own concern; from the application's POV only the three methods
    here are visible.
    """

    def register(self, request_id: int) -> PendingResponse: ...
    def forget(self, request_id: int) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class FrameCodec:
    """Wire-format codec injected into :class:`DawController`.

    Functional bundle: ``encode_command_frame`` turns a ``(cmd, args,
    request_id)`` triple into the bytes the sink will send;
    ``request_id_max`` is the upper bound the controller's monotonic
    counter wraps around.

    The application layer never imports the concrete codec — composition
    builds it from :mod:`flstudio_cli.shared.infrastructure.protocol.v2` and
    hands it to the controller through DI.  Tests use the same wired
    codec via a shared fixture.
    """

    encode_command_frame: Callable[[str, dict[str, Any] | None, int], bytes]
    request_id_max: int


# ---------------------------------------------------------------------------
# Realtime piano-roll Port (used by piano_roll.application.note_event_scheduler)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoteEventSink:
    """Functional bundle of realtime MIDI note effects.

    Used by the piano-roll recorder to stream ``note_on`` / ``note_off``
    events on a non-control MIDI channel, plus the eventual ``close()``
    when the session ends.
    """

    send_note_on: Callable[[int, int, int], None]
    """``(pitch, velocity, channel) -> None`` — emit a note-on event."""

    send_note_off: Callable[[int, int, int], None]
    """``(pitch, channel) -> None`` — emit a note-off (velocity is 0)."""

    close: Callable[[], None]


# ---------------------------------------------------------------------------
# Piano-roll file IO Port (used by batch_handlers, doctor, presentation)
# ---------------------------------------------------------------------------


class WriteQueueFile(Protocol):
    """Callable that writes a queue file the FL Studio import script consumes."""

    def __call__(
        self,
        notes: list[Note],
        *,
        path: str | None = None,
        clear_existing: bool = True,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class PianoRollIO:
    """Functional bundle of piano-roll filesystem effects."""

    read_exported_notes: Callable[[str | Path | None], list[Note]]
    write_queue_file: WriteQueueFile
    default_export_path: Callable[[], str]
    default_queue_path: Callable[[], str]


# ---------------------------------------------------------------------------
# MIDI port discovery Port (used by doctor)
# ---------------------------------------------------------------------------


ListOutputPorts = Callable[[], list[str]]
"""Enumerate every MIDI output port currently visible to the process."""


# ---------------------------------------------------------------------------
# Doctor effects bundle
# ---------------------------------------------------------------------------


PyflpProbe = Callable[[], Any | None]
"""Return the imported ``pyflp`` module or ``None`` if not installed."""


# ---------------------------------------------------------------------------
# Generic filesystem Port
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileStat:
    """Subset of ``os.stat_result`` exposed through :class:`FileSystem`.

    Carrying only the fields the application actually consumes keeps
    stdlib structseq types out of the application layer and makes
    fakes trivial to construct.
    """

    mtime: float


@dataclass(frozen=True, slots=True)
class FileSystem:
    """Functional bundle of generic filesystem effects.

    Application code reaches for this Port when a more specialised
    bundle (e.g. :class:`PianoRollIO`) does not already model the
    operation.  Production composition binds the four callables to
    :mod:`flstudio_cli.shared.infrastructure.io_utils` plus stdlib
    ``os`` primitives; tests pass an in-memory fake.

    Each callable mirrors the exception contract of the stdlib it
    wraps so callers can pattern-match on the same error types they
    would have written against ``open`` / ``os.stat`` directly.
    """

    read_text: Callable[[str], str]
    """``path -> str``: same exception surface as ``open(path).read()``."""

    is_file: Callable[[str], bool]
    """``path -> bool``: does the path point at an existing regular file?"""

    file_stat: Callable[[str], FileStat]
    """``path -> FileStat``: same exception contract as :func:`os.stat`."""

    atomic_write_text: Callable[[str, str], None]
    """``(path, text) -> None``: tmp+rename atomic write."""


@dataclass(frozen=True, slots=True)
class DoctorEffects:
    """Bundle of side-effect callables the diagnostics need."""

    list_output_ports: ListOutputPorts
    piano_roll_io: PianoRollIO
    pyflp_probe: PyflpProbe
    fs: FileSystem
