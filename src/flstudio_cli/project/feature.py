"""Composition root: project feature plugin (project / pattern / channel / tempo / step CLI)."""

from __future__ import annotations

from flstudio_cli.project.application.handlers import BATCH_HANDLERS
from flstudio_cli.project.presentation.cmd_project import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(
    name="project",
    cli_commands=CLI_COMMANDS,
    batch_handlers=BATCH_HANDLERS,
)
