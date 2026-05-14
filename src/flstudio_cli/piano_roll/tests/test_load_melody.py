"""Tests for the melody loader use-case.

``load_melody`` is the single entry point presentation calls when it
needs to turn a ``source`` string (path or ``"-"``) into a list of
:class:`Note`.  It returns ``Ok[list[Note]]`` on success or
``Err[MelodyError]`` on failure (one of four typed variants), so each
variant deserves an explicit test both as documentation and as
regression bait.

The loader takes its three I/O effects (MIDI reader + text reader +
line iterator) as injected callables, so tests can pass simple stub
functions and never touch real files.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from flstudio_cli.piano_roll.application.load_melody import Note, load_melody
from flstudio_cli.piano_roll.application.melody_errors import (
    EmptyMelody,
    MelodyIOError,
    MelodyNotFound,
    MelodyParseError,
)
from flstudio_cli.shared.utility.outcome import Err, Ok


def _iter_significant_lines(text: str) -> Iterable[str]:
    """Mirror the production iter_lines: drop blanks and ``#`` comments."""
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def _refuse_midi_reader(_path: str) -> list[Note]:
    """MIDI reader that rejects being called — for non-.mid sources."""
    raise AssertionError("MIDI reader was invoked for a non-MIDI source")


def _refuse_text_reader(_path: str) -> str:
    """Text reader that rejects being called — for .mid sources."""
    raise AssertionError("Text reader was invoked for a MIDI source")


class TestCsvHappyPath:
    def test_given_csv_text_when_load_then_returns_parsed_notes(self) -> None:
        result = load_melody(
            "score.csv",
            midi_reader=_refuse_midi_reader,
            read_text=lambda _path: "60,100,1.0,0.0\n62,90,0.5,1.0\n",
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Ok)
        notes = result.value
        assert [int(n.pitch) for n in notes] == [60, 62]
        assert float(notes[1].length) == 0.5

    def test_given_stdin_dash_source_when_load_then_uses_text_reader(self) -> None:
        # "-" is the conventional stdin marker; loader must not treat it as
        # a MIDI path even though there's no extension.
        text_reader_calls: list[str] = []

        def _record(path: str) -> str:
            text_reader_calls.append(path)
            return "60,100,1.0,0.0\n"

        result = load_melody(
            "-",
            midi_reader=_refuse_midi_reader,
            read_text=_record,
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Ok)
        assert text_reader_calls == ["-"]


class TestMidiHappyPath:
    @pytest.mark.parametrize("ext", [".mid", ".midi", ".MID", ".Midi"])
    def test_given_midi_extension_when_load_then_uses_midi_reader(
        self, ext: str
    ) -> None:
        # Case-insensitive extension match — `.MID` must work like `.mid`.
        canned = [Note.of(pitch=60, velocity=100, length=1.0, position=0.0)]
        midi_reader_calls: list[str] = []

        def _record(path: str) -> list[Note]:
            midi_reader_calls.append(path)
            return canned

        result = load_melody(
            f"song{ext}",
            midi_reader=_record,
            read_text=_refuse_text_reader,
            iter_lines=_iter_significant_lines,
        )
        assert result == Ok(canned)
        assert midi_reader_calls == [f"song{ext}"]


class TestErrorSum:
    """Each error variant has its own raising condition; lock it in."""

    def test_given_missing_path_when_load_then_returns_melody_not_found(self) -> None:
        def _missing(_path: str) -> str:
            raise FileNotFoundError("[Errno 2] No such file or directory: 'x'")

        result = load_melody(
            "missing.csv",
            midi_reader=_refuse_midi_reader,
            read_text=_missing,
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, MelodyNotFound)
        assert result.error.source == "missing.csv"
        assert "No such file" in result.error.reason

    def test_given_unreadable_path_when_load_then_returns_melody_io_error(
        self,
    ) -> None:
        def _permission_denied(_path: str) -> str:
            raise PermissionError("[Errno 13] Permission denied: 'x'")

        result = load_melody(
            "locked.csv",
            midi_reader=_refuse_midi_reader,
            read_text=_permission_denied,
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, MelodyIOError)
        assert result.error.source == "locked.csv"

    def test_given_malformed_csv_when_load_then_returns_melody_parse_error(
        self,
    ) -> None:
        result = load_melody(
            "bad.csv",
            midi_reader=_refuse_midi_reader,
            read_text=lambda _path: "60,100,oops,0.0\n",
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, MelodyParseError)
        assert result.error.source == "bad.csv"

    def test_given_malformed_midi_when_load_then_returns_melody_parse_error(
        self,
    ) -> None:
        def _bad_midi(_path: str) -> list[Note]:
            raise ValueError("not a valid SMF header")

        result = load_melody(
            "broken.mid",
            midi_reader=_bad_midi,
            read_text=_refuse_text_reader,
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, MelodyParseError)
        assert result.error.source == "broken.mid"

    def test_given_csv_with_only_blanks_when_load_then_returns_empty_melody(
        self,
    ) -> None:
        result = load_melody(
            "blank.csv",
            midi_reader=_refuse_midi_reader,
            read_text=lambda _path: "\n# this is a comment\n   \n",
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, EmptyMelody)
        assert result.error.source == "blank.csv"

    def test_given_midi_returning_no_notes_when_load_then_returns_empty_melody(
        self,
    ) -> None:
        result = load_melody(
            "silent.mid",
            midi_reader=lambda _path: [],
            read_text=_refuse_text_reader,
            iter_lines=_iter_significant_lines,
        )
        assert isinstance(result, Err)
        assert isinstance(result.error, EmptyMelody)
