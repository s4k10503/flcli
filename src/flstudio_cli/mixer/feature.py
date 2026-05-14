"""Composition root: mixer feature plugin (mixer-track volume / pan / name / mute / solo / arm)."""

from __future__ import annotations

from flstudio_cli.mixer.application.handlers import BATCH_HANDLERS
from flstudio_cli.mixer.presentation.cmd_mixer import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(
    name="mixer",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
