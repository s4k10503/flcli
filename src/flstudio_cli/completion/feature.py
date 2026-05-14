"""Composition root: completion feature plugin (``flcli completion`` shell completion)."""

from __future__ import annotations

from flstudio_cli.completion.presentation.cmd_completion import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(name="completion", cli_commands=CLI_COMMANDS)
