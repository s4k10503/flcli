"""Composition root: production-bound effect bundles for the application Ports.

Functional-style DI: each effect bundle is a frozen dataclass of plain
callables, constructed once at startup. Application code receives these
via injection (or via ``doctor``'s lazy default) and never imports
infrastructure directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flstudio_cli.piano_roll.infrastructure import (
    piano_roll_io as _piano_roll_io_module,
)
from flstudio_cli.shared.application.ports import (
    DoctorEffects,
    FileStat,
    FileSystem,
    PianoRollIO,
)
from flstudio_cli.shared.infrastructure.flp.flp import (
    try_import_pyflp as _try_import_pyflp,
)
from flstudio_cli.shared.infrastructure.io_utils import (
    atomic_write_text as _atomic_write_text,
)
from flstudio_cli.shared.infrastructure.io_utils import read_text as _read_text
from flstudio_cli.shared.infrastructure.transport.midi_sink import (
    list_output_ports as _list_output_ports,
)
from flstudio_cli.shared.utility.outcome import Outcome
from flstudio_cli.state.application import snapshot_compare as _SnapCmp


def _file_stat(path: str) -> FileStat:
    return FileStat(mtime=Path(path).stat().st_mtime)


def _is_file(path: str) -> bool:
    return Path(path).is_file()


PRODUCTION_FILE_SYSTEM: FileSystem = FileSystem(
    read_text=_read_text,
    is_file=_is_file,
    file_stat=_file_stat,
    atomic_write_text=_atomic_write_text,
)

PRODUCTION_PIANO_ROLL_IO: PianoRollIO = PianoRollIO(
    read_exported_notes=_piano_roll_io_module.read_exported_notes,
    write_queue_file=_piano_roll_io_module.write_queue_file,
    default_export_path=_piano_roll_io_module.default_export_path,
    default_queue_path=_piano_roll_io_module.default_queue_path,
)

PRODUCTION_DOCTOR_EFFECTS: DoctorEffects = DoctorEffects(
    list_output_ports=_list_output_ports,
    piano_roll_io=PRODUCTION_PIANO_ROLL_IO,
    pyflp_probe=_try_import_pyflp,
    fs=PRODUCTION_FILE_SYSTEM,
)


def compare_snapshot_files(
    before_path: str,
    after_path: str,
    *,
    assertion_spec_path: str | None = None,
) -> Outcome[_SnapCmp.CompareReport, _SnapCmp.CompareError]:
    """Composition-wired :func:`snapshot_compare.compare_snapshot_files`."""
    return _SnapCmp.compare_snapshot_files(
        before_path,
        after_path,
        assertion_spec_path=assertion_spec_path,
        fs=PRODUCTION_FILE_SYSTEM,
    )


def write_snapshot_file(
    snapshot: dict[str, Any],
    path: str,
    *,
    pretty: bool = False,
) -> Outcome[None, _SnapCmp.WriteIOError]:
    """Composition-wired :func:`snapshot_compare.write_snapshot_file`."""
    return _SnapCmp.write_snapshot_file(
        snapshot,
        path,
        pretty=pretty,
        fs=PRODUCTION_FILE_SYSTEM,
    )
