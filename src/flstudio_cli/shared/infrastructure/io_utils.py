"""Infrastructure adapter: filesystem helpers shared across the integrations layer.

Centralises the "atomic write" pattern (tmp + rename) so callers can't
drift on tmp-suffix conventions or directory-creation behaviour.  Three
writers were doing the same dance with subtly different code paths
before this module existed (``flp.py``, ``piano_roll_io.py``, and
``cmd_state.snapshot_cmd``); they now share one implementation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` via tmp+rename so partial reads are impossible.

    Creates the parent directory if it doesn't yet exist.  The temp file
    lives next to the destination (same filesystem) so ``Path.replace``
    is atomic.
    """
    parent = Path(path).absolute().parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=parent,
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_name = tmp.name
    Path(tmp_name).replace(path)


def atomic_write_text(path: str, text: str, *, encoding: str = "utf-8") -> None:
    """Text equivalent of :func:`atomic_write_bytes`."""
    atomic_write_bytes(path, text.encode(encoding))


def read_text(path: str, *, encoding: str = "utf-8") -> str:
    """Read ``path`` and decode it as text.

    Same exception surface as :meth:`pathlib.Path.read_text`.
    """
    return Path(path).read_text(encoding=encoding)
