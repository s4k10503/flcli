"""Infrastructure adapter: round-trip I/O between FL Studio's Piano Roll and the CLI.

``flcli_export.pyscript`` writes the current Piano Roll score to a JSON
file; this module parses that file back into validated :class:`Note`
objects, and serialises a list of :class:`Note` back into the queue
file ``flcli_import.pyscript`` consumes.

Pure edit semantics (``EditPlan`` / ``apply_edits`` and friends) live
in :mod:`flstudio_cli.piano_roll.domain.edit_ops`; this module is the
infrastructure side of the same feature -- absolute paths, JSON
serialisation, atomic writes.

The CLI only touches plain files -- FL Studio remains the sole writer
of its own score, and the user triggers the scripts manually.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flstudio_cli.shared.domain.note import Note
from flstudio_cli.shared.infrastructure.io_utils import atomic_write_text

DEFAULT_EXPORT_FILENAME = "piano_roll_export.json"
DEFAULT_QUEUE_FILENAME = "pending_notes.json"


def _piano_roll_scripts_dir() -> Path:
    """FL Studio's Piano Roll scripts folder.

    Both ``flcli_import.pyscript`` and ``flcli_export.pyscript`` live
    here, and the CLI writes its queue/export data files alongside them
    so the pyscripts can read them with **relative** filenames -- FL
    Studio's embedded Python sandbox cannot open files via absolute
    paths (``_io.FileIO`` returns NULL), but relative paths resolved
    against the script's own directory work.
    """
    return (
        Path.home()
        / "Documents"
        / "Image-Line"
        / "FL Studio"
        / "Settings"
        / "Piano roll scripts"
    )


def default_export_path() -> str:
    override = os.environ.get("FLCLI_EXPORT_PATH")
    if override:
        return override
    return str(_piano_roll_scripts_dir() / DEFAULT_EXPORT_FILENAME)


def default_queue_path() -> str:
    override = os.environ.get("FLCLI_QUEUE_PATH")
    if override:
        return override
    return str(_piano_roll_scripts_dir() / DEFAULT_QUEUE_FILENAME)


def read_exported_notes(source: str | Path | None = None) -> list[Note]:
    """Load the JSON produced by ``flcli_export.pyscript``.

    The returned list is ordered by the ``index`` field so callers can
    address notes by stable indices that match what FL Studio showed.
    """
    path = Path(source if source is not None else default_export_path())
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    raw_notes = payload.get("notes") or []
    # Preserve the exporter's index ordering. If the file was hand-
    # edited and indices are missing, fall back to file order.
    indexed: list[tuple[int, Note]] = [
        (int(entry.get("index", position_in_file)), Note.from_entry(entry))
        for position_in_file, entry in enumerate(raw_notes)
    ]
    indexed.sort(key=lambda pair: pair[0])
    return [note for _index, note in indexed]


def prepare_queue_payload(
    notes: list[Note],
    clear_existing: bool = True,
) -> dict[str, Any]:
    """Build the queue-file JSON payload without touching the filesystem.

    This is the pure-data half of :func:`write_queue_file`.  Useful for
    testing serialisation logic in isolation or for embedding the
    payload in a larger structure without writing to disk.

    Returns a dict ready to be passed to :func:`json.dump`.
    """
    return {
        "version": 1,
        "clear_existing": clear_existing,
        "consume": True,
        "notes": [note.to_dict() for note in notes],
    }


def write_queue_file(
    notes: list[Note],
    *,
    path: str | None = None,
    clear_existing: bool = True,
) -> str:
    """Write a queue file that ``flcli_import.pyscript`` will consume.

    ``clear_existing=True`` (the default for round-trip edits) tells
    the importer to delete everything in the Piano Roll first, so the
    edited list replaces the score instead of stacking on top of it.

    Delegates to :func:`prepare_queue_payload` for serialisation and
    performs an atomic write (tmp + rename) to avoid partial reads.
    """
    target_path = path or default_queue_path()
    payload = prepare_queue_payload(notes, clear_existing)
    atomic_write_text(target_path, json.dumps(payload, ensure_ascii=False))
    return target_path
