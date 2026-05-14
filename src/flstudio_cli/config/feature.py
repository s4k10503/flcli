"""Composition root: config feature plugin (persistent CLI defaults: ``flcli config get/set``)."""

from __future__ import annotations

from flstudio_cli.config.presentation.cmd_config import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(name="config", cli_commands=CLI_COMMANDS)
