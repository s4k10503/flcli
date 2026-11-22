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


class TestPreset:
    def test_preset_next_on_a_channel(self, runner):
        req = _request(runner, "preset", "next", "--channel", "6")
        assert req["cmd"] == "plugin_preset"
        assert req["args"] == {"channel": 6, "direction": "next"}

    def test_preset_prev_on_a_mixer_slot(self, runner):
        req = _request(runner, "preset", "prev", "--track", "3", "--slot", "1")
        assert req["args"] == {"channel": 3, "direction": "prev", "slot": 1}


class _FakePlugin:
    """Stands in for FL: one parameter whose display is a log cutoff."""

    def __init__(self, value: float = 0.3) -> None:
        self.value = value
        self.sets: list[float] = []

    def display(self) -> str:
        hz = 20 * 1000**self.value
        return f"{hz / 1000:.2f} kHz" if hz >= 1000 else f"{hz:.0f} Hz"

    def send(self, ctx, command, args=None, **_kw):
        if command == "plugin_param_set":
            self.value = float(args["value"])
            self.sets.append(self.value)
        return {"name": "Cutoff", "value": self.value, "display": self.display()}


@pytest.fixture
def fake_plugin(monkeypatch):
    from flstudio_cli.plugin.presentation import cmd_plugin

    plugin = _FakePlugin()
    monkeypatch.setattr(cmd_plugin, "_send_v2", plugin.send)
    return plugin


def _live(runner, *argv: str) -> dict:
    result = runner.invoke(cli, ["plugin", "param", *argv], obj={})
    return _parse_first_line(result.output)


class TestParamMapAndSeek:
    def test_map_lists_displays_and_restores(self, runner, fake_plugin):
        out = _live(
            runner, "map", "-c", "4", "-n", "Cutoff", "--steps", "4", "--settle-ms", "0"
        )
        assert out["ok"] is True, out
        points = out["result"]["points"]
        assert [p["display"] for p in points] == [
            "20 Hz",
            "112 Hz",
            "632 Hz",
            "3.56 kHz",
            "20.00 kHz",
        ]
        assert fake_plugin.value == 0.3  # put back

    def test_seek_sets_by_hz(self, runner, fake_plugin):
        out = _live(
            runner, "seek", "-c", "4", "-n", "Cutoff", "--to", "150", "--settle-ms", "0"
        )
        assert out["ok"] is True, out
        assert out["result"]["display"] == "150 Hz"
        assert out["result"]["previous"]["value"] == 0.3

    def test_seek_out_of_range_restores_and_fails(self, runner, fake_plugin):
        out = _live(
            runner, "seek", "-c", "4", "-n", "Cutoff", "--to", "5", "--settle-ms", "0"
        )
        assert out["ok"] is False
        assert "outside" in out["error"]["message"]
        assert fake_plugin.value == 0.3

    def test_seek_needs_to_or_label(self, runner, fake_plugin):
        out = _live(runner, "seek", "-c", "4", "-n", "Cutoff")
        assert out["ok"] is False
        assert fake_plugin.sets == []

    def test_dry_run_only_previews_the_first_read(self, runner):
        req = _request(runner, "param", "seek", "-c", "4", "-p", "2", "--to", "150")
        assert req["cmd"] == "plugin_param_get"
