"""Composition (DI) layer — the only place that imports infrastructure.

Onion architecture: ``flstudio_cli.shared.application`` and
``flstudio_cli.shared.domain`` do not import from
``flstudio_cli.shared.infrastructure``. The CLI / Presentation layer also
does not import it directly. Everything that touches MIDI, the file
system, OS automation, or optional native libraries flows through the
modules in this package.

Sub-modules
-----------
* :mod:`.effects` -- production-bound :class:`PianoRollIO` and
  :class:`DoctorEffects` bundles wired from the integration adapters.
* :mod:`.transport` -- ``CommandTransport`` / ``ReturnPort`` selection
  (replay / record / live), :func:`open_daw_controller`, and
  :func:`open_piano_roll_note_sink`.
* :mod:`.facades` -- presentation-facing re-exports of the relevant
  per-feature ``*.infrastructure`` modules (config, MIDI reader,
  piano-roll IO) and ``shared.infrastructure.*`` modules (FLP, OS
  automation) so the CLI never imports them directly.

Everything below is exposed at the package root for ergonomic
``from . import composition as Comp`` use sites.
"""

from __future__ import annotations

from flstudio_cli.shared.composition.effects import (
    PRODUCTION_DOCTOR_EFFECTS,
    PRODUCTION_FILE_SYSTEM,
    PRODUCTION_PIANO_ROLL_IO,
    compare_snapshot_files,
    write_snapshot_file,
)
from flstudio_cli.shared.composition.facades import (
    atomic_write_text,
    config,
    flp,
    midi_reader,
    os_automation,
    piano_roll_io,
    read_midi_file,
)
from flstudio_cli.shared.composition.transport import (
    build_transport,
    open_daw_controller,
    open_piano_roll_note_sink,
)

__all__ = [
    "PRODUCTION_DOCTOR_EFFECTS",
    "PRODUCTION_FILE_SYSTEM",
    "PRODUCTION_PIANO_ROLL_IO",
    "atomic_write_text",
    "build_transport",
    "compare_snapshot_files",
    "config",
    "flp",
    "midi_reader",
    "open_daw_controller",
    "open_piano_roll_note_sink",
    "os_automation",
    "piano_roll_io",
    "read_midi_file",
    "write_snapshot_file",
]
