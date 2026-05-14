"""Interface adapter: POSIX exit-code projection for the CLI process.

Translates an :mod:`flstudio_cli.shared.application.envelope` error code into
a stable POSIX exit status so shell-script callers can branch on it
without parsing JSON. Lives in the presentation layer because POSIX
process exit codes are a CLI process-level concern, not part of the
application's response DTO.
"""

# pyright: strict

from __future__ import annotations

from typing import Final, get_args

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.envelope import ErrorCode

# Distinct values so a shell-script caller can branch on them without
# parsing JSON. The numbers are stable: they may get new friends in
# the future but never reshuffled. Keys are typed as ``str`` because
# envelopes deserialised from JSON reach this lookup; the closed-set
# guarantee is enforced by the import-time check below.
_EXIT_CODES: Final[dict[str, int]] = {
    Env.CODE_INVALID_ARGUMENT: 2,
    Env.CODE_NOT_FOUND: 3,
    Env.CODE_IO_ERROR: 4,
    Env.CODE_PORT_NOT_FOUND: 10,
    Env.CODE_TIMEOUT: 12,
    Env.CODE_UNKNOWN_COMMAND: 20,
    Env.CODE_PROTOCOL_ERROR: 30,
    Env.CODE_AUTOMATION_FAILED: 31,
    Env.CODE_INTERNAL: 99,
}

# Catch additions to the ``ErrorCode`` Literal that forget to extend
# ``_EXIT_CODES``. Runs at import time so the failure is loud and early.
_missing = set(get_args(ErrorCode)) - _EXIT_CODES.keys()
if _missing:  # pragma: no cover - defensive
    raise RuntimeError(
        f"_EXIT_CODES is missing entries for ErrorCode members: {sorted(_missing)}"
    )
del _missing


def exit_code_for(error_code: str) -> int:
    """Map an ``ERROR_CODE`` constant to a POSIX exit code.

    Unknown codes collapse to the legacy catch-all (``1``) so a caller
    that forgets to register a new code still fails loudly instead of
    silently returning success.
    """
    return _EXIT_CODES.get(error_code, 1)
