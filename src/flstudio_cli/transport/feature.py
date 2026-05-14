"""Composition root: transport feature plugin (playback / position / loop / undo-redo CLI)."""

from __future__ import annotations

from flstudio_cli.shared.application.feature_dto import Feature
from flstudio_cli.transport.application.handlers import BATCH_HANDLERS
from flstudio_cli.transport.presentation.cmd_transport import CLI_COMMANDS

FEATURE = Feature(
    name="transport",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
