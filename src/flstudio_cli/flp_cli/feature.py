"""Composition root: FLP CLI feature plugin (``flcli flp`` subcommands for offline ``.flp`` editing).

The parser itself lives at
:mod:`flstudio_cli.shared.infrastructure.flp.flp` (it is a file-format
adapter, not a CLI feature); this module only carries the Click
surface.
"""

from __future__ import annotations

from flstudio_cli.flp_cli.presentation.cmd_flp import CLI_COMMANDS
from flstudio_cli.shared.application.feature_dto import Feature

FEATURE = Feature(name="flp", cli_commands=CLI_COMMANDS)
