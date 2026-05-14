"""Composition root: DI wiring for state's IO-bound batch handler(s).

Most state handlers are static and shipped via
:data:`flstudio_cli.state.FEATURE` through the entry-point discovery
mechanism.  ``piano_roll_show`` is the exception: it reads files
through a :class:`PianoRollIO` bundle, so its handler is constructed
via the
:func:`~flstudio_cli.state.application.handlers.make_piano_roll_show_handler`
factory.

This module is the only place inside the *state* feature that knows
about :class:`PianoRollIO`; the composition root in ``__main__`` calls
:func:`compose` with the production IO bundle and layers the result on
top of the entry-point-discovered static handlers.
"""

from __future__ import annotations

from flstudio_cli.shared.application.handler_workflow import BatchHandler
from flstudio_cli.shared.application.ports import PianoRollIO
from flstudio_cli.state.application.handlers import make_piano_roll_show_handler


def compose(*, piano_roll_io: PianoRollIO) -> dict[str, BatchHandler]:
    """Return state's DI-bound batch handlers (just ``piano_roll_show``)."""
    return {
        "piano_roll_show": make_piano_roll_show_handler(piano_roll_io),
    }
