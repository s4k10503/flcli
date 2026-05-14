"""Composition root: presentation-facing infrastructure facades.

The CLI / Presentation layer never imports
``flstudio_cli.shared.infrastructure`` directly — it goes through the
composition package. These facades simply re-export the relevant
infrastructure modules so the dependency graph in ``__main__`` and
the per-feature ``presentation/cmd_*.py`` modules stays
inward-pointing.

Keeping these as plain module re-exports (rather than wrapping every
function) avoids accidental drift between the CLI surface and the
underlying adapter; the DI seam is enforced at the *import boundary*,
not by re-implementing each call.
"""

from __future__ import annotations

from flstudio_cli.config.infrastructure import config
from flstudio_cli.piano_roll.infrastructure import midi_reader, piano_roll_io
from flstudio_cli.shared.infrastructure import os_automation
from flstudio_cli.shared.infrastructure.flp import flp
from flstudio_cli.shared.infrastructure.io_utils import atomic_write_text

# Convenient direct re-exports for the most-used helpers, so call sites
# read as ``Comp.read_midi_file(path)`` instead of the longer module path.
read_midi_file = midi_reader.read_midi_file

__all__ = [
    "atomic_write_text",
    "config",
    "flp",
    "midi_reader",
    "os_automation",
    "piano_roll_io",
    "read_midi_file",
]
