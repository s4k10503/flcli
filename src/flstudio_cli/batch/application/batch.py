"""Use case: re-exports the public surface of the batch sub-modules.

* :mod:`.batch_parsing`   — ``BatchStep``, ``ParseError``,
  ``parse_steps``, ``parse_stream_line``.
* :mod:`.batch_executor`  — ``execute_step``, ``run_steps``,
  ``stream_steps``.
* :mod:`flstudio_cli.shared.application.handler_dto` — successful
  outputs (``DeviceCommand`` / ``LocalResult`` / ``HandlerOutput``).
* :mod:`flstudio_cli.shared.application.handler_errors` — typed
  failure variants (``InvalidArgument`` / ``FileMissing`` /
  ``FileIOError`` / ``HandlerError``).
* :mod:`flstudio_cli.shared.application.handler_workflow` — the
  ``BatchHandler`` callable shape, ``lift_exceptions``, and
  ``make_handlers`` registry merge.

(Per-feature ``BATCH_HANDLERS`` dicts live in each feature's
``application/handlers.py``; argument-coercion primitives live in
:mod:`flstudio_cli.shared.application.handler_args`.)
"""

from __future__ import annotations

from flstudio_cli.batch.application.batch_executor import (
    execute_step,
    run_steps,
    stream_steps,
)
from flstudio_cli.batch.application.batch_parsing import (
    BatchStep,
    ParseError,
    parse_steps,
    parse_stream_line,
)
from flstudio_cli.shared.application.handler_dto import (
    DeviceCommand,
    HandlerOutput,
    LocalResult,
)
from flstudio_cli.shared.application.handler_errors import (
    FileIOError,
    FileMissing,
    HandlerError,
    InvalidArgument,
)
from flstudio_cli.shared.application.handler_workflow import (
    BatchHandler,
    make_handlers,
)
from flstudio_cli.shared.utility.outcome import Err, Ok

__all__ = [
    "BatchHandler",
    "BatchStep",
    "DeviceCommand",
    "Err",
    "FileIOError",
    "FileMissing",
    "HandlerError",
    "HandlerOutput",
    "InvalidArgument",
    "LocalResult",
    "Ok",
    "ParseError",
    "execute_step",
    "make_handlers",
    "parse_steps",
    "parse_stream_line",
    "run_steps",
    "stream_steps",
]
