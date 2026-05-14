"""Composition root: state feature plugin (live snapshot, diff, doctor, piano-roll-show CLI).

The static ``state`` handler is exposed here.  ``piano_roll_show`` reads
files through a :class:`PianoRollIO` bundle and is layered on by the
composition root via :mod:`flstudio_cli.state.composition` after
entry-point discovery.
"""

from __future__ import annotations

from flstudio_cli.shared.application.feature_dto import Feature
from flstudio_cli.state.application.handlers import BATCH_HANDLERS
from flstudio_cli.state.presentation.cmd_state import CLI_COMMANDS

FEATURE = Feature(
    name="state",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
