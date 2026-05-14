"""Use case: best-effort live-state fetch for diagnostics."""

from __future__ import annotations

from typing import Any

from flstudio_cli.shared.application.cli_dispatcher import DispatchDeps
from flstudio_cli.shared.application.fl_command_port import fl


def try_fetch_snapshot(deps: DispatchDeps) -> dict[str, Any] | None:
    """Best-effort live state fetch for diagnostics.

    Returns the inner ``state`` payload when the device replies ok and
    ``None`` on any error (port missing, timeout, dry-run, malformed
    envelope).  Doctor falls back to its file-based checks when the
    snapshot is unavailable, so a None return is never fatal.
    """
    if deps.dry_run:
        return None
    try:
        with deps.open_controller() as controller:
            resp = controller.send_command(fl.state())
    except (RuntimeError, TimeoutError):
        return None
    if not resp.get("ok"):
        return None
    result_payload = resp.get("result") or {}
    return result_payload.get("state") or result_payload
