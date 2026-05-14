"""Tests for the snapshot file I/O + comparison use-case.

``compare_snapshot_files`` and ``write_snapshot_file`` reach the
filesystem only through the injected :class:`FileSystem` Port, so the
tests here pass an in-memory fake instead of touching disk.  Each
typed-error variant in the result sums (``CompareIOError`` /
``CompareJSONError`` / ``WriteIOError``) gets an explicit test as both
documentation and regression bait.

Pure dict-diff behaviour itself lives in
``state/domain/snapshot_diff.py`` and is covered by
``test_snapshot_diff.py``; this file's job is the I/O lifting and
result-DTO contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from flstudio_cli.shared.application.ports import FileStat, FileSystem
from flstudio_cli.shared.utility.outcome import Err, Ok
from flstudio_cli.state.application.snapshot_compare import (
    CompareIOError,
    CompareJSONError,
    WriteIOError,
    compare_snapshot_files,
    write_snapshot_file,
)


@dataclass
class _InMemoryFs:
    """Minimal FileSystem stand-in backed by a dict.

    Just enough surface to drive snapshot_compare; mirrors the stdlib
    exception contract so the tests exercise the same except-paths the
    production FileSystem would.
    """

    files: dict[str, str]

    def read_text(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def is_file(self, path: str) -> bool:
        return path in self.files

    def file_stat(self, path: str) -> FileStat:
        if path not in self.files:
            raise FileNotFoundError(path)
        return FileStat(mtime=0.0)

    def atomic_write_text(self, path: str, text: str) -> None:
        self.files[path] = text

    def as_port(self) -> FileSystem:
        return FileSystem(
            read_text=self.read_text,
            is_file=self.is_file,
            file_stat=self.file_stat,
            atomic_write_text=self.atomic_write_text,
        )


def _denying_fs(error: Exception) -> FileSystem:
    """A FileSystem whose read_text always raises *error*."""

    def _raise(_path: str) -> str:
        raise error

    return FileSystem(
        read_text=_raise,
        is_file=lambda _p: True,
        file_stat=lambda _p: FileStat(mtime=0.0),
        atomic_write_text=lambda _p, _t: None,
    )


# --- compare_snapshot_files: happy paths -------------------------------------


class TestCompareReportHappyPath:
    def test_given_identical_snapshots_when_compare_then_diff_is_empty(self) -> None:
        fs = _InMemoryFs(
            files={
                "before.json": json.dumps({"tempo": 128.0, "is_playing": False}),
                "after.json": json.dumps({"tempo": 128.0, "is_playing": False}),
            }
        )
        outcome = compare_snapshot_files("before.json", "after.json", fs=fs.as_port())
        assert isinstance(outcome, Ok)
        report = outcome.value
        assert report.diff == {"added": [], "removed": [], "changed": []}
        assert report.assertions is None

    def test_given_changed_field_when_compare_then_diff_lists_the_change(self) -> None:
        fs = _InMemoryFs(
            files={
                "before.json": json.dumps({"tempo": 120.0}),
                "after.json": json.dumps({"tempo": 140.0}),
            }
        )
        outcome = compare_snapshot_files("before.json", "after.json", fs=fs.as_port())
        assert isinstance(outcome, Ok)
        report = outcome.value
        assert len(report.diff["changed"]) == 1
        change = report.diff["changed"][0]
        assert change["path"] == "tempo"
        assert change["before"] == 120.0
        assert change["after"] == 140.0

    def test_given_assertion_spec_when_compare_then_assertion_summary_present(
        self,
    ) -> None:
        fs = _InMemoryFs(
            files={
                "before.json": json.dumps({"tempo": 120.0}),
                "after.json": json.dumps({"tempo": 140.0}),
                "spec.json": json.dumps(
                    {"assertions": [{"path": "tempo", "op": "eq", "value": 140.0}]}
                ),
            }
        )
        outcome = compare_snapshot_files(
            "before.json",
            "after.json",
            assertion_spec_path="spec.json",
            fs=fs.as_port(),
        )
        assert isinstance(outcome, Ok)
        report = outcome.value
        assert report.assertions is not None
        assert report.assertions["total"] == 1
        assert report.assertions["passed"] == 1
        assert report.assertions["failures"] == []


# --- compare_snapshot_files: error sums --------------------------------------


class TestCompareErrorSum:
    def test_given_missing_before_when_compare_then_returns_compare_io_error(
        self,
    ) -> None:
        fs = _InMemoryFs(files={"after.json": json.dumps({})})
        outcome = compare_snapshot_files("missing.json", "after.json", fs=fs.as_port())
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, CompareIOError)
        assert outcome.error.path == "missing.json"

    def test_given_missing_after_when_compare_then_returns_compare_io_error(
        self,
    ) -> None:
        fs = _InMemoryFs(files={"before.json": json.dumps({})})
        outcome = compare_snapshot_files("before.json", "missing.json", fs=fs.as_port())
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, CompareIOError)
        assert outcome.error.path == "missing.json"

    def test_given_unreadable_before_when_compare_then_returns_compare_io_error(
        self,
    ) -> None:
        fs = _denying_fs(PermissionError("denied"))
        outcome = compare_snapshot_files("locked.json", "ignored.json", fs=fs)
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, CompareIOError)

    def test_given_malformed_json_when_compare_then_returns_compare_json_error(
        self,
    ) -> None:
        fs = _InMemoryFs(
            files={
                "before.json": "{not valid json",
                "after.json": json.dumps({}),
            }
        )
        outcome = compare_snapshot_files("before.json", "after.json", fs=fs.as_port())
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, CompareJSONError)
        assert outcome.error.path == "before.json"

    def test_given_missing_spec_when_compare_then_returns_compare_io_error(
        self,
    ) -> None:
        fs = _InMemoryFs(
            files={
                "before.json": json.dumps({}),
                "after.json": json.dumps({}),
            }
        )
        outcome = compare_snapshot_files(
            "before.json",
            "after.json",
            assertion_spec_path="missing-spec.json",
            fs=fs.as_port(),
        )
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, CompareIOError)
        assert outcome.error.path == "missing-spec.json"


# --- write_snapshot_file -----------------------------------------------------


class TestWriteSnapshot:
    def test_given_writable_path_when_write_then_returns_ok_and_persists_json(
        self,
    ) -> None:
        fs = _InMemoryFs(files={})
        outcome = write_snapshot_file({"tempo": 128.0}, "out.json", fs=fs.as_port())
        assert isinstance(outcome, Ok)
        assert outcome.value is None
        assert json.loads(fs.files["out.json"]) == {"tempo": 128.0}

    def test_given_pretty_flag_when_write_then_emits_indented_json(self) -> None:
        fs = _InMemoryFs(files={})
        write_snapshot_file({"a": 1}, "out.json", pretty=True, fs=fs.as_port())
        # indent=2 → newlines + spaces; cheap heuristic check that it's
        # not the compact single-line form.
        body = fs.files["out.json"]
        assert "\n" in body
        assert "  " in body

    def test_given_unwritable_path_when_write_then_returns_write_io_error(
        self,
    ) -> None:
        def _raise(_path: str, _text: str) -> None:
            raise PermissionError("read-only filesystem")

        fs = FileSystem(
            read_text=lambda _p: "",
            is_file=lambda _p: False,
            file_stat=lambda _p: FileStat(mtime=0.0),
            atomic_write_text=_raise,
        )
        outcome = write_snapshot_file({"a": 1}, "/ro/out.json", fs=fs)
        assert isinstance(outcome, Err)
        assert isinstance(outcome.error, WriteIOError)
        assert outcome.error.path == "/ro/out.json"
        assert "read-only" in outcome.error.reason


# --- assertion_spec edge case (defensive) ------------------------------------


class TestAssertionSpecEdgeCases:
    @pytest.mark.parametrize("non_dict_spec", ["[]", "42", '"a string"'])
    def test_given_spec_not_an_object_when_compare_then_assertions_count_zero(
        self,
        non_dict_spec: str,
    ) -> None:
        # snapshot_compare tolerates a non-dict assertion spec by
        # treating it as "no assertions" — pin that behaviour.
        fs = _InMemoryFs(
            files={
                "before.json": json.dumps({}),
                "after.json": json.dumps({}),
                "spec.json": non_dict_spec,
            }
        )
        outcome = compare_snapshot_files(
            "before.json",
            "after.json",
            assertion_spec_path="spec.json",
            fs=fs.as_port(),
        )
        assert isinstance(outcome, Ok)
        report = outcome.value
        # `spec.get("assertions", [])` falls through; total = 0
        summary: dict[str, Any] = report.assertions or {}
        assert summary["total"] == 0
