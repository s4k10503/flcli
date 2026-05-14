"""Composition root: batch feature plugin (``batch run`` / ``batch stream`` CLI).

Batch is the executor itself, not a batch-handler producer; its
``Feature`` therefore exposes only ``cli_commands``.
"""

from __future__ import annotations

from flstudio_cli.batch.presentation.cmd_batch import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(name="batch", cli_commands=CLI_COMMANDS)
