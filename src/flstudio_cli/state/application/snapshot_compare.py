"""Use case: snapshot file I/O and comparison.

Two responsibilities:

* :func:`compare_snapshot_files` — wraps the pure
  :mod:`flstudio_cli.state.domain.snapshot_diff` functions plus the JSON file
  reads presentation used to do inline.  Returns a presentation-friendly
  result DTO and lifts filesystem / JSON errors into a typed sum.
* :func:`write_snapshot_file` — atomic JSON write of a snapshot dict.

Both functions take their filesystem effects through the generic
:class:`FileSystem` Port so this module never imports infrastructure;
composition supplies the wired bundle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from flstudio_cli.shared.application.ports import FileSystem
from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome
from flstudio_cli.state.domain import snapshot_diff as SDiff


@dataclass(frozen=True, slots=True)
class CompareReport:
    """Result of :func:`compare_snapshot_files` with optional assertions."""

    diff: dict[str, Any]
    assertions: dict[str, Any] | None  # ``None`` when no spec path was supplied


@dataclass(frozen=True, slots=True)
class CompareIOError:
    """One of the JSON files did not exist or was unreadable."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class CompareJSONError:
    """One of the JSON files was syntactically invalid."""

    path: str
    reason: str


CompareError = CompareIOError | CompareJSONError


def _load_json(path: str, fs: FileSystem) -> Outcome[dict[str, Any], CompareError]:
    try:
        return Ok(json.loads(fs.read_text(path)))
    except OSError as exc:
        return Err(CompareIOError(path=path, reason=str(exc)))
    except json.JSONDecodeError as exc:
        return Err(CompareJSONError(path=path, reason=str(exc)))


def compare_snapshot_files(
    before_path: str,
    after_path: str,
    *,
    assertion_spec_path: str | None = None,
    fs: FileSystem,
) -> Outcome[CompareReport, CompareError]:
    """Diff two snapshot JSON files and (optionally) check assertions.

    Returns:
        - ``Ok(CompareReport)`` on success.
        - ``Err(CompareIOError)`` if any required file is missing /
          unreadable.
        - ``Err(CompareJSONError)`` if any file is malformed JSON.

    The presentation layer pattern-matches on the result; it never
    catches :class:`json.JSONDecodeError` itself.
    """
    match _load_json(before_path, fs):
        case Err() as failure:
            return failure
        case Ok(before):
            pass
    match _load_json(after_path, fs):
        case Err() as failure:
            return failure
        case Ok(after):
            pass

    diff: dict[str, Any] = SDiff.diff_snapshots(before, after)
    assertions: dict[str, Any] | None = None

    if assertion_spec_path is not None:
        match _load_json(assertion_spec_path, fs):
            case Err() as failure:
                return failure
            case Ok(spec):
                spec_assertions = (
                    spec.get("assertions", []) if isinstance(spec, dict) else []
                )
        failures = SDiff.check_assertions(after, spec_assertions)
        assertions = {
            "total": len(spec_assertions),
            "passed": len(spec_assertions) - len(failures),
            "failures": failures,
        }

    return Ok(CompareReport(diff=diff, assertions=assertions))


@dataclass(frozen=True, slots=True)
class WriteIOError:
    """The destination directory or file could not be written."""

    path: str
    reason: str


def write_snapshot_file(
    snapshot: dict[str, Any],
    path: str,
    *,
    pretty: bool = False,
    fs: FileSystem,
) -> Outcome[None, WriteIOError]:
    """Serialize *snapshot* to JSON and write atomically to *path*.

    The atomic write effect is reached through :class:`FileSystem` so
    application code never imports infrastructure directly.  Returns
    ``Ok(None)`` on success and ``Err(WriteIOError)`` on filesystem
    failure; presentation pattern-matches on the result rather than
    catching :class:`OSError` itself.
    """
    indent = 2 if pretty else None
    data = json.dumps(snapshot, ensure_ascii=False, indent=indent)
    try:
        fs.atomic_write_text(path, data)
    except OSError as exc:
        return Err(WriteIOError(path=path, reason=str(exc)))
    return Ok(None)
