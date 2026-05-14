"""Application DTO: whitelist of transport position modes the CLI accepts.

This is an **application** concern — it's a use-case-level contract
(``which strings does ``flcli transport position`` accept?``).  It is
not a wire-format detail and not a musical-domain concern: the device
script keeps its own mapping from these strings to FL Studio API
constants.

Lives in ``shared.application`` because both the typed Port signature
in :mod:`flstudio_cli.shared.application.fl_command_port` and the
transport feature's per-handler validation consume it; placing the
type in either side alone would force a backward dep across feature
and shared layers.

The two sides must stay in sync.  Adding a fourth mode here without
updating the device script's ``_POSITION_MODES`` dict makes the new
flag value a NOT_FOUND at runtime; the reverse leaves it un-exposed
in the CLI surface.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

#: Closed sum of accepted ``--mode`` values.  Drives both the runtime
#: whitelist (``VALID_POSITION_MODES``) and the typed Port signatures
#: in :mod:`flstudio_cli.shared.application.fl_command_port`, so a
#: typo in either place is rejected at type-check time.
PositionMode = Literal["beats", "ticks", "ms", "abs-ticks"]

VALID_POSITION_MODES: Final[frozenset[str]] = frozenset(get_args(PositionMode))
