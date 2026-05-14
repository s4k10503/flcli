"""Application DTO: feature descriptor for entry-point-based plugin discovery.

Each top-level feature (mixer, plugin, transport, ...) packs its CLI
command list and (optionally) its batch-handler dict into a single
``FEATURE`` constant exposed by a sibling ``feature.py`` module.  The
composition root in :mod:`flstudio_cli.__main__` walks
``entry_points(group="flstudio_cli.features")`` and assembles them
into the global ``CLI`` and ``BATCH_HANDLERS`` registries, so adding
a feature is a folder + one entry-point line away.

The constants intentionally live in ``feature.py`` rather than
``__init__.py``: cross-feature imports through
:mod:`flstudio_cli.shared.domain` would otherwise trigger circular
initialisation when a feature's ``__init__`` runs as a side effect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flstudio_cli.shared.application.handler_workflow import BatchHandler

if TYPE_CHECKING:
    import click


@dataclass(frozen=True, slots=True)
class Feature:
    """Plugin-discoverable bundle of a feature's public surface."""

    name: str
    """Stable identifier (matches the entry-point key)."""

    cli_commands: Sequence[click.Command]
    """Top-level Click commands or groups exposed by this feature."""

    batch_handlers: Mapping[str, BatchHandler] = field(default_factory=dict)
    """Static batch handlers; empty for features that only ship CLI subcommands."""
