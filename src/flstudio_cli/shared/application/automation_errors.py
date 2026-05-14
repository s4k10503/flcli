# pyright: strict

"""Application DTO: typed error values for the OS-automation port.

The infrastructure adapter
(:mod:`flstudio_cli.shared.infrastructure.os_automation`) returns these
through :class:`Err` channels rather than raising, so presentation can
pattern-match on the result without taking a forbidden dependency on
the infrastructure layer.

Onion direction: application owns these contracts; infrastructure
imports them when implementing the trigger factory.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InvalidShortcut:
    """Typed error for a malformed ``--shortcut`` value."""

    message: str
