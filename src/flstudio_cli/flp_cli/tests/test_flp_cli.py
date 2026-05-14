"""Click-level integration tests for the ``flp`` CLI subcommands.

These tests do NOT require pyflp — they exercise the pre-pyflp error
paths (missing file, missing library) to pin the envelope contract.
"""

from __future__ import annotations

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestFlpCliCommands:
    def test_flp_info_nonexistent_file_returns_not_found_envelope(
        self,
        runner,
        tmp_path,
    ):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(cli, ["flp", "info", str(missing)], obj={})
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_info"
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND
        assert payload["args"]["path"] == str(missing)

    def test_flp_notes_add_nonexistent_file_returns_not_found_envelope(
        self,
        runner,
        tmp_path,
    ):
        missing = tmp_path / "nope.flp"
        json_src = tmp_path / "notes.json"
        json_src.write_text("[]")
        result = runner.invoke(
            cli,
            [
                "flp",
                "notes",
                "add",
                str(missing),
                "--channel",
                "0",
                "--from-json",
                str(json_src),
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_notes_add"
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND

    def test_flp_notes_add_missing_json_source_returns_envelope(
        self,
        runner,
        tmp_path,
    ):
        # The FLP exists but the --from-json file doesn't.
        flp = tmp_path / "project.flp"
        flp.write_bytes(b"FLhd")  # placeholder; we fail before parsing
        missing_json = tmp_path / "missing.json"
        result = runner.invoke(
            cli,
            [
                "flp",
                "notes",
                "add",
                str(flp),
                "--channel",
                "0",
                "--from-json",
                str(missing_json),
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND

    def test_flp_notes_clear_nonexistent_file_returns_not_found_envelope(
        self,
        runner,
        tmp_path,
    ):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            ["flp", "notes", "clear", str(missing), "--channel", "0"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_notes_clear"
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND


class TestFlpChannelRename:
    def test_nonexistent_file_returns_not_found(self, runner, tmp_path):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            ["flp", "channel", "rename", str(missing), "--channel", "0", "NewName"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_channel_rename"
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND


class TestFlpPatternSetLength:
    def test_nonexistent_file_returns_not_found(self, runner, tmp_path):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            ["flp", "pattern", "set-length", str(missing), "--pattern", "0", "64"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_pattern_set_length"


class TestFlpMixerRoute:
    def test_nonexistent_file_returns_not_found(self, runner, tmp_path):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            ["flp", "mixer", "route", str(missing), "--from", "1", "--to", "0"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_mixer_route"


class TestFlpClipCreate:
    def test_nonexistent_file_returns_not_found(self, runner, tmp_path):
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            [
                "flp",
                "clip",
                "create",
                str(missing),
                "--track",
                "0",
                "--pattern",
                "0",
                "--position",
                "0.0",
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_clip_create"


class TestFlpNotesAddInputValidation:
    """Pin the ``flp notes add`` input-resolution envelope contract.

    Exercises ``_resolve_notes_input``: missing source, malformed JSON
    content and the CSV-stdin happy path that hands off to
    :func:`_dispatch_flp`.
    """

    def test_missing_both_sources_returns_invalid_argument(
        self,
        runner,
        tmp_path,
    ):
        flp = tmp_path / "project.flp"
        flp.write_bytes(b"FLhd")  # placeholder; we fail before parsing
        result = runner.invoke(
            cli,
            ["flp", "notes", "add", str(flp), "--channel", "0"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_notes_add"
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "--from-json" in payload["error"]["message"]

    def test_malformed_json_content_returns_invalid_argument(
        self,
        runner,
        tmp_path,
    ):
        flp = tmp_path / "project.flp"
        flp.write_bytes(b"FLhd")
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not json")
        result = runner.invoke(
            cli,
            [
                "flp",
                "notes",
                "add",
                str(flp),
                "--channel",
                "0",
                "--from-json",
                str(bad_json),
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_notes_add"
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT

    def test_csv_stdin_source_reaches_dispatch(self, runner, tmp_path):
        # With a non-existent FLP path, dispatch fails with NOT_FOUND —
        # proving the CSV branch of ``_resolve_notes_input`` parsed the
        # stdin payload successfully and handed control to the dispatcher.
        missing = tmp_path / "nope.flp"
        result = runner.invoke(
            cli,
            [
                "flp",
                "notes",
                "add",
                str(missing),
                "--channel",
                "0",
                "--from-csv",
                "-",
            ],
            input="60,100,1.0,0.0\n",
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "flp_notes_add"
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND
