"""Composition root: plugin feature plugin (plugin discovery + parameter inspection / control)."""

from __future__ import annotations

from flstudio_cli.plugin.application.handlers import BATCH_HANDLERS
from flstudio_cli.plugin.presentation.cmd_plugin import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(
    name="plugin",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
