"""Click-level integration tests for transport CLI surface (v2 only).

Covers ``play``, ``stop``, ``record``, ``transport-position``,
``transport-loop``, ``undo``, ``redo`` and ``undo-history`` — every
command is exercised under ``--dry-run`` so no MIDI port is opened.
"""

from __future__ import annotations

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli


class TestDryRunPlayback:
    """Smoke tests for the simple play / stop / record commands."""

    def test_play_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "play"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "play"
        assert payload["result"]["request"]["cmd"] == "play"

    def test_stop_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "stop"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "stop"
        assert payload["result"]["request"]["cmd"] == "stop"

    def test_record_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "record"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "record"
        assert payload["result"]["request"]["cmd"] == "record"


class TestDryRunTransportPosition:
    def test_given_position_get_dry_run_when_invoked_then_emits_preview(
        self,
        runner,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", "transport-position", "get"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "transport_position"
        assert payload["result"]["dry_run"] is True
        assert payload["result"]["request"]["cmd"] == "transport_position_get"
        assert payload["result"]["request"]["args"]["mode"] == "beats"

    def test_given_position_get_with_ticks_then_mode_passed(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "transport-position", "get", "--mode", "ticks"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["args"]["mode"] == "ticks"

    def test_given_position_set_dry_run_then_emits_preview(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "transport-position", "set", "16.5"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["request"]["cmd"] == "transport_position_set"
        assert payload["result"]["request"]["args"]["position"] == 16.5
        assert payload["result"]["request"]["args"]["mode"] == "beats"


class TestDryRunTransportLoop:
    def test_given_loop_get_dry_run_then_ok(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "transport-loop", "get"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["request"]["cmd"] == "transport_loop_get"

    def test_given_loop_toggle_dry_run_then_ok(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "transport-loop", "toggle"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["cmd"] == "transport_loop_toggle"


class TestDryRunUndoRedo:
    def test_given_undo_dry_run_then_ok(self, runner):
        result = runner.invoke(cli, ["--dry-run", "undo"], obj={})
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "undo"
        assert payload["result"]["request"]["cmd"] == "undo"

    def test_given_redo_dry_run_then_ok(self, runner):
        result = runner.invoke(cli, ["--dry-run", "redo"], obj={})
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "redo"
        assert payload["result"]["request"]["cmd"] == "redo"

    def test_given_undo_history_dry_run_then_ok(self, runner):
        result = runner.invoke(cli, ["--dry-run", "undo-history"], obj={})
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "undo_history"
        assert payload["result"]["request"]["cmd"] == "undo_history"
