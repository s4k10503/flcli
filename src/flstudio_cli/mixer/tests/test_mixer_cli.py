"""Click-level integration tests for the mixer CLI surface (Issue #10).

Exercises the ``--track`` / ``--track-name`` / ``--track-query`` /
``--track-ref`` selector flags in dry-run and live-resolution modes.
"""

from __future__ import annotations

import threading

import pytest
from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestMixerTrackSelectorDryRun:
    """--track (index) still works in dry-run, produces the same envelope."""

    @pytest.mark.parametrize(
        "subcmd,track_args",
        [
            (["mixer", "volume", "get"], ["--track", "3"]),
            (["mixer", "volume", "set", "0.75"], ["--track", "3"]),
            (["mixer", "pan", "get"], ["--track", "3"]),
            (["mixer", "pan", "set"], ["--track", "3", "--", "-0.5"]),
            (["mixer", "name", "get"], ["--track", "3"]),
            (["mixer", "name", "set", "FX Bus"], ["--track", "3"]),
            (["mixer", "mute"], ["--track", "3"]),
            (["mixer", "solo"], ["--track", "3"]),
            (["mixer", "arm"], ["--track", "3"]),
            (["mixer", "link-to-channel"], ["--track", "3", "--channel", "0"]),
        ],
    )
    def test_given_track_index_dry_run_then_ok(
        self,
        runner,
        subcmd,
        track_args,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", *subcmd, *track_args],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["dry_run"] is True
        assert payload["result"]["request"]["args"]["track"] == 3


class TestMixerTrackSelectorNamedDryRun:
    """--track-name / --track-query emit a deferred resolution preview."""

    def test_given_track_name_dry_run_then_emits_selector_preview(
        self,
        runner,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", "mixer", "volume", "get", "--track-name", "Drums"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["dry_run"] is True
        assert payload["result"]["note"] is not None
        assert payload["args"]["selector"] == {"mode": "name", "name": "Drums"}

    def test_given_track_query_dry_run_then_emits_selector_preview(
        self,
        runner,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", "mixer", "mute", "--track-query", "drum"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["args"]["selector"] == {"mode": "query", "query": "drum"}

    def test_given_track_ref_dry_run_then_emits_selector_preview(
        self,
        runner,
    ):
        ref_json = '{"mode": "index", "index": 5}'
        result = runner.invoke(
            cli,
            ["--dry-run", "mixer", "solo", "--track-ref", ref_json],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["args"]["selector"] == {"mode": "index", "index": 5}


class TestMixerTrackSelectorValidation:
    """Selector flags are mutually exclusive; zero or multiple is an error."""

    def test_given_no_selector_then_invalid_argument(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "mixer", "volume", "get"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "none provided" in payload["error"]["message"]

    def test_given_two_selectors_then_invalid_argument(self, runner):
        result = runner.invoke(
            cli,
            [
                "--dry-run",
                "mixer",
                "volume",
                "get",
                "--track",
                "1",
                "--track-name",
                "Drums",
            ],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert "2 provided" in payload["error"]["message"]

    def test_given_invalid_track_ref_json_then_invalid_argument(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "mixer", "pan", "get", "--track-ref", "{bad json}"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert "invalid --track-ref JSON" in payload["error"]["message"]


class TestMixerTrackSelectorLiveResolution:
    """Named selector resolves via a preliminary mixer_list query."""

    def test_given_track_name_live_then_resolves_and_executes(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        from flstudio_cli.shared.application.controller import DawController
        from flstudio_cli.shared.infrastructure.transport.return_port import (
            FakeReturnPort,
        )

        captured: dict[str, FakeReturnPort] = {}

        def fake_make_controller(ctx):
            return_port = FakeReturnPort()
            captured["return_port"] = return_port
            return DawController(fake_transport, return_port, PRODUCTION_FRAME_CODEC)

        monkeypatch.setattr(
            "flstudio_cli.shared.presentation.cli_dispatch._make_controller",
            fake_make_controller,
        )

        call_count = {"n": 0}
        original_send_and_wait = DawController.send_and_wait

        def send_and_wait_with_response(self, cmd, args=None, timeout_ms=5000):
            rp = captured["return_port"]
            call_count["n"] += 1
            seq = call_count["n"]

            if cmd == "mixer_list":
                # First call: resolution query
                def deliver():
                    rp.deliver(
                        {
                            "request_id": seq,
                            "ok": True,
                            "command": "mixer_list",
                            "result": {
                                "mixer": {
                                    "tracks": [
                                        {"index": 0, "name": "Master"},
                                        {"index": 1, "name": "Drums"},
                                        {"index": 2, "name": "Bass"},
                                    ],
                                },
                            },
                            "error": None,
                        }
                    )

                threading.Timer(0.01, deliver).start()
            else:
                # Second call: actual command
                def deliver():
                    rp.deliver(
                        {
                            "request_id": seq,
                            "ok": True,
                            "command": cmd,
                            "result": {"track": args["track"], "volume": 0.8},
                            "error": None,
                        }
                    )

                threading.Timer(0.01, deliver).start()

            return original_send_and_wait(self, cmd, args, timeout_ms=1000)

        monkeypatch.setattr(
            DawController,
            "send_and_wait",
            send_and_wait_with_response,
        )

        result = runner.invoke(
            cli,
            ["mixer", "volume", "get", "--track-name", "Drums"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["track"] == 1
        assert payload["result"]["volume"] == 0.8

    def test_given_track_name_no_match_then_not_found(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        from flstudio_cli.shared.application.controller import DawController
        from flstudio_cli.shared.infrastructure.transport.return_port import (
            FakeReturnPort,
        )

        captured: dict[str, FakeReturnPort] = {}

        def fake_make_controller(ctx):
            return_port = FakeReturnPort()
            captured["return_port"] = return_port
            return DawController(fake_transport, return_port, PRODUCTION_FRAME_CODEC)

        monkeypatch.setattr(
            "flstudio_cli.shared.presentation.cli_dispatch._make_controller",
            fake_make_controller,
        )

        original_send_and_wait = DawController.send_and_wait

        def send_and_wait_with_response(self, cmd, args=None, timeout_ms=5000):
            rp = captured["return_port"]

            def deliver():
                rp.deliver(
                    {
                        "request_id": 1,
                        "ok": True,
                        "command": "mixer_list",
                        "result": {
                            "mixer": {
                                "tracks": [
                                    {"index": 0, "name": "Master"},
                                ],
                            },
                        },
                        "error": None,
                    }
                )

            threading.Timer(0.01, deliver).start()
            return original_send_and_wait(self, cmd, args, timeout_ms=1000)

        monkeypatch.setattr(
            DawController,
            "send_and_wait",
            send_and_wait_with_response,
        )

        result = runner.invoke(
            cli,
            ["mixer", "volume", "get", "--track-name", "Vocals"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_NOT_FOUND)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_NOT_FOUND
        assert "Vocals" in payload["error"]["message"]
