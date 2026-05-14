"""Click-level integration tests for piano-roll CLI surface (v2 only).

Covers ``piano-roll-trigger setup`` and the ``--auto-trigger`` flag on
``queue-piano-roll`` — including the shortcut validation paths.
"""

from __future__ import annotations

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestPianoRollTriggerSetup:
    def test_setup_emits_instructions(self, runner):
        result = runner.invoke(
            cli,
            ["piano-roll-trigger", "setup"],
            obj={},
        )
        from flstudio_cli.shared.infrastructure import os_automation

        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "piano_roll_trigger_setup"
        assert "steps" in payload["result"]
        assert "prerequisites" in payload["result"]
        assert payload["result"]["shortcut"] == os_automation.default_shortcut()

    def test_setup_custom_shortcut(self, runner):
        result = runner.invoke(
            cli,
            ["piano-roll-trigger", "setup", "--shortcut", "ctrl+shift+F5"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["result"]["shortcut"] == "ctrl+shift+F5"

    def test_setup_invalid_shortcut(self, runner):
        result = runner.invoke(
            cli,
            ["piano-roll-trigger", "setup", "--shortcut", "ctrl+$(evil)"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT


class TestQueuePianoRollAutoTrigger:
    def test_dry_run_auto_trigger_uses_dry_run_trigger(self, runner, tmp_path):
        melody = tmp_path / "melody.txt"
        melody.write_text("60,100,1.0,0.0\n62,100,1.0,1.0\n")
        queue = tmp_path / "pending.json"
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "queue-piano-roll",
                str(melody),
                "--queue-file",
                str(queue),
                "--auto-trigger",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "queue_piano_roll"
        from flstudio_cli.shared.infrastructure import os_automation

        # DryRunTrigger.verify returns True unconditionally.
        assert payload["result"]["auto_triggered"] is True
        assert payload["args"]["auto_trigger"] is True
        assert payload["args"]["shortcut"] == os_automation.default_shortcut()

    def test_auto_trigger_rejects_invalid_shortcut(self, runner, tmp_path):
        melody = tmp_path / "melody.txt"
        melody.write_text("60,100,1.0,0.0\n")
        queue = tmp_path / "pending.json"
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "queue-piano-roll",
                str(melody),
                "--queue-file",
                str(queue),
                "--auto-trigger",
                "--shortcut",
                'ctrl+alt+"; echo pwned; "',
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "shortcut" in payload["error"]["message"].lower()


class TestQueuePianoRollChannelTarget:
    """--channel surfaces focus_channel_editor before writing the queue."""

    def test_dry_run_with_channel_emits_focus_preview(self, runner, tmp_path):
        # In dry-run, the focus_channel_editor send_v2 is the first wire
        # interaction; the queue file is never written, so the preview
        # envelope is what surfaces.
        melody = tmp_path / "melody.txt"
        melody.write_text("60,100,1.0,0.0\n")
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "queue-piano-roll",
                str(melody),
                "--channel",
                "4",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "focus_channel_editor"
        args = payload["result"]["request"]["args"]
        assert args["channel"] == 4
        assert args["window"] == "piano_roll"
