"""Composition root: piano-roll feature plugin (realtime / queued note writes + offline melody)."""

from __future__ import annotations

from flstudio_cli.piano_roll.application.handlers import BATCH_HANDLERS
from flstudio_cli.piano_roll.presentation.cmd_piano_roll import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(
    name="piano_roll",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
