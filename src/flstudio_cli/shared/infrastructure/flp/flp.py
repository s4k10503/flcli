"""Infrastructure adapter: FLP file manipulation via pyflp.

Provides offline reading/writing of FL Studio project files (.flp)
for features that have no runtime API path: arbitrary piano-roll notes,
playlist clip insertion, pattern length, full mixer routing.

Lazy ``pyflp`` import
---------------------
``pyflp`` is an **optional** dependency -- it is only needed when the
user invokes an FLP-related command, so it is not declared as a hard
requirement.  Every public function calls :func:`_require_pyflp` (or
enters :func:`_open_flp`) on first use, which attempts the import and
raises a clear :class:`RuntimeError` with installation instructions if
the package is missing.  This keeps the rest of the CLI fully functional
even when ``pyflp`` is not installed.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from flstudio_cli.shared.domain.note import Note
from flstudio_cli.shared.infrastructure.io_utils import atomic_write_bytes

_DEFAULT_PPQ = 96


def try_import_pyflp() -> Any:
    """Return the imported ``pyflp`` module, or ``None`` if unavailable.

    Use this in optional contexts (e.g. ``doctor``) where a missing
    install should not raise.  Hard dependencies should call
    :func:`_require_pyflp` instead.
    """
    try:
        import pyflp

        return pyflp
    except ImportError:
        return None


def _require_pyflp():
    """Import and return the ``pyflp`` module, or raise with install instructions."""
    pyflp = try_import_pyflp()
    if pyflp is None:
        raise RuntimeError(
            "pyflp is required for FLP file operations. Install with: pip install pyflp"
        )
    return pyflp


def parse_notes_json(path: str) -> list[Note]:
    """Parse an array of note objects from a JSON file."""
    with Path(path).open() as fh:
        raw = json.load(fh)
    return [Note.from_entry(entry) for entry in raw]


def parse_notes_csv(source: str) -> list[Note]:
    """Parse ``pitch,velocity,length,position`` lines from a path or '-' (stdin).

    Trailing fields default to (100, 1.0, 0.0).  Blank lines and ``#``
    comments are skipped so the format is hand-editable.
    """
    text = sys.stdin.read() if source == "-" else Path(source).read_text()
    return [
        Note.parse_csv_lenient(line)
        for raw_line in text.splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]


# Backwards-compatible alias retained for the tests under
# ``tests/test_flp.py::TestAtomicWrite``.  New code should call the shared
# helper in :mod:`flstudio_cli.shared.infrastructure.io_utils`.
_atomic_write = atomic_write_bytes


@contextmanager
def _open_flp(path: str) -> Generator[Any, None, None]:
    """Parse an FLP, yield the project, then save atomically on exit."""
    pyflp = _require_pyflp()
    project = pyflp.parse(path)
    yield project
    data = project.save() if hasattr(project, "save") else None
    if data:
        _atomic_write(path, data)


def _check_index(
    index: int,
    count: int,
    label: str,
    *,
    show_range: bool = True,
) -> None:
    """Raise ``ValueError`` if ``index`` is outside ``[0, count)``.

    When ``show_range`` is true the error includes ``(0-{count - 1})``;
    a few older call sites historically omitted that hint, so we keep
    them bug-compatible by passing ``show_range=False``.
    """
    if index < 0 or index >= count:
        if show_range:
            raise ValueError(f"{label} {index} out of range (0-{count - 1})")
        raise ValueError(f"{label} {index} out of range")


def _ppq(project: Any) -> int:
    """Return the project's PPQ, falling back to the pyflp default."""
    return project.ppq if hasattr(project, "ppq") else _DEFAULT_PPQ


def _resolve_pattern(project: Any, pattern: int | None) -> Any:
    """Return the requested pattern, or the first one when ``pattern`` is ``None``.

    Validates the index when supplied; returns ``None`` if the project
    has no patterns at all.
    """
    patterns = list(project.patterns)
    if pattern is None:
        return patterns[0] if patterns else None
    _check_index(pattern, len(patterns), "pattern", show_range=False)
    return patterns[pattern]


def _channel_summaries(project: Any) -> list[dict[str, Any]]:
    """Return ``[{index, name}, ...]`` for every channel on ``project``."""
    return [
        {"index": i, "name": getattr(ch, "name", None)}
        for i, ch in enumerate(project.channels)
    ]


def _pattern_summaries(project: Any) -> list[dict[str, Any]]:
    """Return ``[{index, name}, ...]`` for every pattern on ``project``."""
    return [
        {"index": getattr(p, "index", i), "name": getattr(p, "name", None)}
        for i, p in enumerate(project.patterns)
    ]


def _mixer_track_count(project: Any) -> int:
    """Count mixer tracks; ``0`` if the mixer is not iterable."""
    mixer = project.mixer
    return sum(1 for _ in mixer) if hasattr(mixer, "__iter__") else 0


def flp_info(path: str) -> dict[str, Any]:
    """Read basic metadata from an FLP file (read-only, no save).

    Returns a dict containing ``path``, ``tempo``, ``channel_count``,
    ``channels``, ``pattern_count``, ``patterns``, and
    ``mixer_track_count`` where available.
    """
    pyflp = _require_pyflp()
    project = pyflp.parse(path)
    info: dict[str, Any] = {
        "path": path,
        "tempo": float(project.tempo) if hasattr(project, "tempo") else None,
    }
    if hasattr(project, "channels"):
        channels = _channel_summaries(project)
        info["channel_count"] = len(channels)
        info["channels"] = channels
    if hasattr(project, "patterns"):
        patterns = _pattern_summaries(project)
        info["pattern_count"] = len(patterns)
        info["patterns"] = patterns
    if hasattr(project, "mixer"):
        info["mixer_track_count"] = _mixer_track_count(project)
    return info


def _append_notes(pat: Any, notes: list[Note], ppq: int) -> int:
    """Append ``notes`` to ``pat.notes`` (converted to ticks); return count added."""
    try:
        from pyflp._models import Note as PyflpNote
    except ImportError as exc:
        raise RuntimeError(
            "pyflp note model is unavailable "
            "(pyflp._models.Note could not be imported); "
            "check that the installed pyflp version is supported"
        ) from exc
    added = 0
    for note in notes:
        n = PyflpNote()
        n.key = int(note.pitch)
        n.velocity = int(note.velocity)
        n.length = int(float(note.length) * ppq)
        n.position = int(float(note.position) * ppq)
        pat.notes.append(n)
        added += 1
    return added


def flp_add_notes(
    path: str,
    channel: int,
    notes: list[Note],
    pattern: int | None = None,
) -> dict[str, Any]:
    """Append ``notes`` to the piano roll of ``channel`` in the FLP at ``path``.

    If ``pattern`` is ``None``, notes are added to the first pattern.
    Returns a summary dict with the number of notes actually added.
    """
    with _open_flp(path) as project:
        _check_index(channel, sum(1 for _ in project.channels), "channel")
        pat = _resolve_pattern(project, pattern)

        added = 0
        if pat is not None and hasattr(pat, "notes"):
            added = _append_notes(pat, notes, _ppq(project))

    return {
        "path": path,
        "channel": channel,
        "notes_added": added,
    }


def flp_clear_notes(
    path: str,
    channel: int,
    pattern: int | None = None,
) -> dict[str, Any]:
    """Remove every note from ``channel``'s piano roll in the given pattern.

    If ``pattern`` is ``None``, the first pattern is cleared.  Returns
    a summary dict with the count of notes removed.
    """
    with _open_flp(path) as project:
        pat = _resolve_pattern(project, pattern)

        cleared = 0
        if pat is not None and hasattr(pat, "notes"):
            cleared = len(list(pat.notes))
            pat.notes.clear()

    return {
        "path": path,
        "channel": channel,
        "notes_cleared": cleared,
    }


def flp_channel_rename(
    path: str,
    channel: int,
    name: str,
) -> dict[str, Any]:
    """Rename channel ``channel`` to ``name`` in the FLP at ``path``.

    Returns a dict with both the old and new names for confirmation.
    """
    with _open_flp(path) as project:
        channels = list(project.channels)
        _check_index(channel, len(channels), "channel")
        old_name = getattr(channels[channel], "name", None)
        channels[channel].name = name

    return {
        "path": path,
        "channel": channel,
        "old_name": old_name,
        "new_name": name,
    }


def flp_pattern_set_length(
    path: str,
    pattern: int,
    length: int,
) -> dict[str, Any]:
    """Set pattern ``pattern`` to ``length`` steps in the FLP at ``path``.

    Returns a dict with the old and new lengths.
    """
    with _open_flp(path) as project:
        patterns = list(project.patterns)
        _check_index(pattern, len(patterns), "pattern")
        pat = patterns[pattern]
        old_length = getattr(pat, "length", None)
        if hasattr(pat, "length"):
            pat.length = length

    return {
        "path": path,
        "pattern": pattern,
        "old_length": old_length,
        "new_length": length,
    }


def flp_mixer_route(
    path: str,
    from_track: int,
    to_track: int,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    """Enable or disable the mixer send from ``from_track`` to ``to_track``.

    Operates on the FLP at ``path``.  Returns a confirmation dict.
    """
    with _open_flp(path) as project:
        if not hasattr(project, "mixer"):
            raise ValueError("FLP file has no mixer section")

        mixer_tracks = list(project.mixer) if hasattr(project.mixer, "__iter__") else []
        n = len(mixer_tracks)
        _check_index(from_track, n, "from_track")
        _check_index(to_track, n, "to_track")

        src = mixer_tracks[from_track]
        if hasattr(src, "routes") and hasattr(src.routes, "__setitem__"):
            src.routes[to_track] = enabled

    return {
        "path": path,
        "from_track": from_track,
        "to_track": to_track,
        "enabled": enabled,
    }


def _first_arrangement_track(project: Any, track: int) -> Any:
    """Return ``project.arrangements[0].tracks[track]`` or ``None`` if unreachable."""
    if not hasattr(project, "arrangements"):
        return None
    arrangements = list(project.arrangements)
    if not arrangements:
        return None
    arrangement = arrangements[0]
    if not hasattr(arrangement, "tracks"):
        return None
    tracks = list(arrangement.tracks)
    if track >= len(tracks):
        return None
    return tracks[track]


def _append_playlist_item(
    arr_track: Any,
    pattern: int,
    pos_ticks: int,
    len_ticks: int | None,
) -> bool:
    """Try to append a ``PlaylistItem`` to ``arr_track.items``.

    Swallows ``ImportError``/``AttributeError`` to match historical
    behaviour for older/newer pyflp versions that don't expose the
    expected internals.  Returns ``True`` on success.
    """
    if not hasattr(arr_track, "items"):
        return False
    try:
        from pyflp._models import PlaylistItem

        item = PlaylistItem()
        item.pattern = pattern
        item.position = pos_ticks
        if len_ticks is not None and hasattr(item, "length"):
            item.length = len_ticks
        arr_track.items.append(item)
        return True
    except (ImportError, AttributeError):
        return False


def flp_clip_create(
    path: str,
    track: int,
    pattern: int,
    position: float,
    length: float | None = None,
) -> dict[str, Any]:
    """Insert a playlist clip for ``pattern`` at ``position`` beats on ``track``.

    If ``length`` is ``None``, the clip uses the pattern's native length.
    Operates on the first arrangement in the FLP at ``path``.
    """
    with _open_flp(path) as project:
        patterns = list(project.patterns)
        _check_index(pattern, len(patterns), "pattern")

        ppq = _ppq(project)
        pos_ticks = int(position * ppq)
        len_ticks = int(length * ppq) if length is not None else None

        created = False
        arr_track = _first_arrangement_track(project, track)
        if arr_track is not None:
            created = _append_playlist_item(arr_track, pattern, pos_ticks, len_ticks)

    return {
        "path": path,
        "track": track,
        "pattern": pattern,
        "position": position,
        "length": length,
        "created": created,
    }
