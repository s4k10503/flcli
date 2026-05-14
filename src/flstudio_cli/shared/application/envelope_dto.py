# pyright: strict

"""Application DTO: response envelope shape and error-code taxonomy.

This is the application layer's outbound DTO definition.  Shape and
error-code constants live here; the factory functions that *build*
the envelopes live in :mod:`envelope_factory`.

Automation layers (LLM tool loops, shell scripts, test harnesses)
need stable machine-readable signals to tell retriable failures
(``PORT_NOT_FOUND``, ``IO_ERROR``) apart from permanent ones
(``INVALID_ARGUMENT``, ``UNKNOWN_COMMAND``).  The error codes are
emitted as plain strings so they are cheap to match in jq or a jsonl
reader and immune to int drift between releases.  At the type level
they are a closed :class:`Literal` so a typo at the failure() boundary
is caught by pyright.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

# Bumped when the envelope shape changes in a way consumers can feel.
# Staying at 1 means "strict superset of the original flat shape".
PROTOCOL_VERSION: Final[int] = 1


# Closed set of error codes. Defined as a ``Literal`` so pyright / mypy
# refuse any free-form string at the failure() boundary -- a typo in a
# handler used to slip through and silently degrade to exit code 1 once
# it reached :mod:`flstudio_cli.shared.presentation.exit_codes`.
ErrorCode = Literal[
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "IO_ERROR",
    "PORT_NOT_FOUND",
    "UNKNOWN_COMMAND",
    "PROTOCOL_ERROR",
    "INTERNAL",
    "TIMEOUT",
    "AUTOMATION_FAILED",
]

#: Bad user input caught at the boundary (bounds, missing fields, wrong type).
CODE_INVALID_ARGUMENT: Final[ErrorCode] = "INVALID_ARGUMENT"

#: A file the CLI expected to find (queue, export, state) does not exist.
CODE_NOT_FOUND: Final[ErrorCode] = "NOT_FOUND"

#: File read/write failure (permission denied, disk full, corrupt JSON).
CODE_IO_ERROR: Final[ErrorCode] = "IO_ERROR"

#: No virtual MIDI port matches the requested name. Usually fixed by
#: starting LoopMIDI / enabling the IAC driver / launching FL Studio.
CODE_PORT_NOT_FOUND: Final[ErrorCode] = "PORT_NOT_FOUND"

#: A batch step referenced a command name the registry does not know.
CODE_UNKNOWN_COMMAND: Final[ErrorCode] = "UNKNOWN_COMMAND"

#: Internal encoder error — a bug in the CLI, not the caller.
CODE_PROTOCOL_ERROR: Final[ErrorCode] = "PROTOCOL_ERROR"

#: Catch-all for any unexpected exception. The message preserves the
#: original exception class so bug reports are actionable.
CODE_INTERNAL: Final[ErrorCode] = "INTERNAL"

#: The device script did not respond to a protocol v2 request within
#: the requested timeout window. Typically means FL Studio was busy or
#: the return port is misconfigured.
CODE_TIMEOUT: Final[ErrorCode] = "TIMEOUT"

#: OS-level automation (auto-trigger shortcut, window focus) failed.
#: The queue file was written successfully but the automated import
#: step could not be completed.
CODE_AUTOMATION_FAILED: Final[ErrorCode] = "AUTOMATION_FAILED"

# Derived from the Literal definition so the runtime set and the type
# alias cannot drift -- adding a code in one place automatically updates
# both.
ERROR_CODES: Final[frozenset[ErrorCode]] = frozenset(get_args(ErrorCode))
