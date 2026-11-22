"""Click-level tests for the plugin commands' --channel / --track targeting.

Run under ``--dry-run`` so no MIDI port is opened; the emitted request shows
the (index, slot) pair FL Studio will be asked for.
"""

from __future__ import annotations

import pytest
from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli


def _request(runner, *argv: str) -> dict:
    result = runner.invoke(cli, ["--dry-run", "plugin", *argv], obj={})
    payload = _parse_first_line(result.output)
    assert payload["ok"] is True, result.output
    return payload["result"]["request"]


def _error(runner, *argv: str) -> dict:
    result = runner.invoke(cli, ["--dry-run", "plugin", *argv], obj={})
    payload = _parse_first_line(result.output)
    assert payload["ok"] is False, result.output
    return payload["error"]


class TestTrackTargetsMixerEffects:
    def test_param_set_with_track_addresses_the_mixer_slot(self, runner):
        req = _request(runner, "param", "set", "0.5", "--track", "5", "-n", "Shape")
        assert req["cmd"] == "plugin_param_set"
        assert req["args"] == {
            "channel": 5,
            "value": 0.5,
            "slot": 0,
            "param_name": "Shape",
        }

    def test_param_get_with_track_keeps_an_explicit_slot(self, runner):
        req = _request(runner, "param", "get", "--track", "3", "--slot", "2", "-p", "7")
        assert req["args"] == {"channel": 3, "slot": 2, "param": 7}

    def test_params_with_track_defaults_to_slot_zero(self, runner):
        req = _request(runner, "params", "--track", "5")
        assert req["args"]["channel"] == 5
        assert req["args"]["slot"] == 0

    def test_list_with_track_asks_for_mixer_slots_only(self, runner):
        req = _request(runner, "list", "--track", "5")
        assert req["args"] == {"channel": 5, "mixer": True}

    def test_channel_still_addresses_the_native_plugin(self, runner):
        req = _request(runner, "param", "get", "--channel", "4", "-p", "3")
        assert req["args"] == {"channel": 4, "param": 3}


class TestTargetValidation:
    @pytest.mark.parametrize(
        "argv",
        [
            ("param", "set", "0.5", "-n", "Shape"),
            ("param", "set", "0.5", "--channel", "1", "--track", "5", "-n", "Shape"),
            ("params",),
            ("list", "--channel", "1", "--track", "2"),
        ],
    )
    def test_needs_exactly_one_target(self, runner, argv):
        err = _error(runner, *argv)
        assert err["code"] == "INVALID_ARGUMENT"
        assert "--channel or --track" in err["message"]

    def test_track_refuses_the_native_slot(self, runner):
        err = _error(runner, "param", "get", "--track", "5", "--slot", "-1", "-p", "0")
        assert err["code"] == "INVALID_ARGUMENT"
