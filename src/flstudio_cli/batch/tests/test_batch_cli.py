"""Click-level integration tests for batch CLI surface (v2 only).

Covers ``batch run`` and ``batch stream`` plus the cross-command batch
exercising transport / undo handlers under ``--dry-run``.
"""

from __future__ import annotations

import json

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestBatchRunCommand:
    def test_given_dry_run_batch_when_run_then_every_step_reports_ok(self, runner):
        steps = {
            "steps": [
                {"name": "tempo", "args": {"bpm": 128}, "id": "a"},
                {"name": "play", "id": "b"},
            ]
        }
        result = runner.invoke(
            cli,
            ["--dry-run", "batch", "run"],
            input=json.dumps(steps),
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["ok_count"] == 2
        assert [r.get("id") for r in payload["result"]["responses"]] == ["a", "b"]

    def test_given_bad_step_when_batch_run_then_unknown_command(self, runner):
        steps = {"steps": [{"name": "ghost"}]}
        result = runner.invoke(
            cli,
            ["--dry-run", "batch", "run"],
            input=json.dumps(steps),
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_UNKNOWN_COMMAND)

    def test_given_malformed_json_when_batch_run_then_invalid_argument(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "batch", "run"],
            input="{not json",
            obj={},
        )
        assert result.exit_code == 2
        payload = _parse_first_line(result.output)
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT


class TestBatchStreamCommand:
    def test_given_two_jsonl_requests_when_stream_then_two_responses(self, runner):
        stdin = "\n".join(
            [
                json.dumps({"name": "play", "id": "1"}),
                json.dumps({"name": "tempo", "args": {"bpm": 140}, "id": "2"}),
            ]
        )
        result = runner.invoke(
            cli,
            ["--dry-run", "batch", "stream"],
            input=stdin,
            obj={},
        )
        assert result.exit_code == 0
        lines = [line for line in result.output.splitlines() if line.strip()]
        assert len(lines) == 2
        payload_0 = json.loads(lines[0])
        payload_1 = json.loads(lines[1])
        assert payload_0["id"] == "1"
        assert payload_0["ok"] is True
        assert payload_1["id"] == "2"


class TestBatchRunWithNewCommands:
    def test_given_batch_with_transport_commands_dry_run_then_all_ok(self, runner):
        steps = {
            "steps": [
                {"name": "transport_position_get", "args": {"mode": "beats"}},
                {"name": "transport_loop_toggle"},
                {"name": "undo"},
                {"name": "redo"},
                {"name": "undo_history"},
            ]
        }
        result = runner.invoke(
            cli,
            ["--dry-run", "batch", "run"],
            input=json.dumps(steps),
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["ok_count"] == 5
