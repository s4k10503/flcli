"""Tests for the :class:`FlCommandPort` Protocol and default adapter.

Two angles:

1. **Wire-format pinning.**  ``DefaultFlCommands`` carries every wire
   string and arg-dict shape the device script understands; if any of
   them drift, every batch handler that calls into the Port produces
   the wrong frame.  The tests below assert each method's
   :class:`DeviceCommand` shape so a typo in the adapter is caught
   without needing FL Studio in the loop.
2. **Substitutability.**  Handlers depend on the Port via the
   :data:`fl` module attribute.  Replacing it with a recording fake
   lets handler-level tests assert intent (which method was called
   with which args) without going through the SysEx wire.
"""

from __future__ import annotations

from typing import Any

import pytest

from flstudio_cli.mixer.application import handlers as mixer_handlers
from flstudio_cli.piano_roll.application import handlers as piano_roll_handlers
from flstudio_cli.plugin.application import handlers as plugin_handlers
from flstudio_cli.project.application import handlers as project_handlers
from flstudio_cli.shared.application.fl_command_port import (
    DefaultFlCommands,
    FlCommandPort,
)
from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.utility.outcome import Ok
from flstudio_cli.state.application import handlers as state_handlers
from flstudio_cli.transport.application import handlers as transport_handlers


@pytest.fixture
def default() -> DefaultFlCommands:
    return DefaultFlCommands()


class TestTransportShapes:
    def test_play(self, default):
        assert default.play() == DeviceCommand("play", {})

    def test_stop(self, default):
        assert default.stop() == DeviceCommand("stop", {})

    def test_record(self, default):
        assert default.record() == DeviceCommand("record", {})

    def test_transport_position_get(self, default):
        assert default.transport_position_get(mode="beats") == DeviceCommand(
            "transport_position_get", {"mode": "beats"}
        )

    def test_transport_position_set(self, default):
        assert default.transport_position_set(
            position=16.5, mode="ticks"
        ) == DeviceCommand(
            "transport_position_set", {"position": 16.5, "mode": "ticks"}
        )

    def test_undo_redo_history(self, default):
        assert default.undo() == DeviceCommand("undo", {})
        assert default.redo() == DeviceCommand("redo", {})
        assert default.undo_history() == DeviceCommand("undo_history", {})


class TestProjectShapes:
    def test_new_pattern(self, default):
        assert default.new_pattern() == DeviceCommand("new_pattern", {})

    def test_tempo(self, default):
        assert default.tempo(bpm=140.0) == DeviceCommand("tempo", {"bpm": 140.0})

    def test_set_step(self, default):
        assert default.set_step(
            channel=1, step=4, on=True, velocity=110
        ) == DeviceCommand(
            "set_step",
            {"channel": 1, "step": 4, "on": True, "velocity": 110},
        )


class TestMixerOptionalFields:
    def test_mixer_arm_without_on_strips_field(self, default):
        # Optional ``on`` is omitted from the wire dict when None so
        # the device-side default (toggle) applies.
        assert default.mixer_arm(track=2) == DeviceCommand("mixer_arm", {"track": 2})

    def test_mixer_arm_with_on_includes_it(self, default):
        assert default.mixer_arm(track=2, on=True) == DeviceCommand(
            "mixer_arm", {"track": 2, "on": True}
        )

    def test_mixer_route_set_uses_wire_field_names(self, default):
        # The Port keeps Python-friendly src/dst at the call site;
        # the wire still expects ``from`` / ``to``.
        assert default.mixer_route_set(src=1, dst=2) == DeviceCommand(
            "mixer_route_set", {"from": 1, "to": 2}
        )


class TestPluginParamSelectorShapes:
    def test_plugin_param_get_by_index(self, default):
        assert default.plugin_param_get(channel=0, param=3) == DeviceCommand(
            "plugin_param_get", {"channel": 0, "param": 3}
        )

    def test_plugin_param_get_by_name_and_slot(self, default):
        assert default.plugin_param_get(
            channel=0, slot=1, param_name="cutoff"
        ) == DeviceCommand(
            "plugin_param_get",
            {"channel": 0, "slot": 1, "param_name": "cutoff"},
        )


# Parametrised wire-format pinning for the remaining Port methods.  A
# single failure here means the adapter and the device script disagree
# on either the command name or the arg-dict shape, which is exactly
# what a future Web frontend would discover at runtime.  Catching it
# here keeps the regression visible without FL Studio in the loop.
@pytest.mark.parametrize(
    "method_name, kwargs, expected",
    [
        # project / pattern / channel
        ("new_project", {}, DeviceCommand("new_project", {})),
        ("new_pattern", {}, DeviceCommand("new_pattern", {})),
        (
            "new_pattern",
            {"name": "Drums"},
            DeviceCommand("new_pattern", {"name": "Drums"}),
        ),
        (
            "select_pattern",
            {"index": 3},
            DeviceCommand("select_pattern", {"index": 3}),
        ),
        (
            "name_pattern",
            {"index": 2, "name": "Bass"},
            DeviceCommand("name_pattern", {"index": 2, "name": "Bass"}),
        ),
        ("channel_rack_focus", {}, DeviceCommand("channel_rack_focus", {})),
        (
            "focus_channel_editor",
            {"channel": 4, "window": "piano_roll"},
            DeviceCommand(
                "focus_channel_editor",
                {"channel": 4, "window": "piano_roll"},
            ),
        ),
        (
            "name_channel",
            {"channel": 1, "name": "kick"},
            DeviceCommand("name_channel", {"channel": 1, "name": "kick"}),
        ),
        (
            "select_channel",
            {"index": 0},
            DeviceCommand("select_channel", {"index": 0}),
        ),
        # mixer
        ("mixer_list", {}, DeviceCommand("mixer_list", {})),
        (
            "mixer_volume_get",
            {"track": 4},
            DeviceCommand("mixer_volume_get", {"track": 4}),
        ),
        (
            "mixer_volume_set",
            {"track": 4, "value": 0.5},
            DeviceCommand("mixer_volume_set", {"track": 4, "value": 0.5}),
        ),
        (
            "mixer_pan_get",
            {"track": 0},
            DeviceCommand("mixer_pan_get", {"track": 0}),
        ),
        (
            "mixer_pan_set",
            {"track": 0, "value": -0.25},
            DeviceCommand("mixer_pan_set", {"track": 0, "value": -0.25}),
        ),
        (
            "mixer_name_get",
            {"track": 2},
            DeviceCommand("mixer_name_get", {"track": 2}),
        ),
        (
            "mixer_name_set",
            {"track": 2, "name": "bus"},
            DeviceCommand("mixer_name_set", {"track": 2, "name": "bus"}),
        ),
        ("mixer_mute", {"track": 1}, DeviceCommand("mixer_mute", {"track": 1})),
        ("mixer_solo", {"track": 1}, DeviceCommand("mixer_solo", {"track": 1})),
        (
            "mixer_link_to_channel",
            {"track": 5, "channel": 0},
            DeviceCommand("mixer_link_to_channel", {"track": 5, "channel": 0}),
        ),
        # plugin
        (
            "plugin_list",
            {"channel": 2},
            DeviceCommand("plugin_list", {"channel": 2}),
        ),
        (
            "plugin_params",
            {"channel": 2},
            DeviceCommand("plugin_params", {"channel": 2}),
        ),
        (
            "plugin_params",
            {"channel": 2, "slot": 1},
            DeviceCommand("plugin_params", {"channel": 2, "slot": 1}),
        ),
        (
            "plugin_param_set",
            {"channel": 0, "value": 0.75, "param": 3},
            DeviceCommand(
                "plugin_param_set",
                {"channel": 0, "value": 0.75, "param": 3},
            ),
        ),
        # transport (the rest)
        ("transport_loop_get", {}, DeviceCommand("transport_loop_get", {})),
        (
            "transport_loop_toggle",
            {},
            DeviceCommand("transport_loop_toggle", {}),
        ),
        # state / piano-roll
        ("state", {}, DeviceCommand("state", {})),
        (
            "state",
            {"field": "tempo"},
            DeviceCommand("state", {"field": "tempo"}),
        ),
        (
            "step_melody",
            {"notes": [{"pitch": 60, "velocity": 100}]},
            DeviceCommand(
                "step_melody",
                {"notes": [{"pitch": 60, "velocity": 100}]},
            ),
        ),
    ],
)
def test_default_fl_command_shape(default, method_name, kwargs, expected):
    """Pin the wire-format produced by every adapter method."""
    method = getattr(default, method_name)
    assert method(**kwargs) == expected


class _RecordingFl:
    """Records every ``fl.*`` invocation without dispatching.

    Stubs are produced lazily by ``__getattr__`` but only for names
    that appear on the :class:`FlCommandPort` Protocol.  This catches
    typo'd handler calls (``fl.mixxer_volume_set(...)``) instead of
    silently recording them.
    """

    _ALLOWED: frozenset[str] = frozenset(
        name for name in vars(FlCommandPort) if not name.startswith("_")
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str):
        if name not in self._ALLOWED:
            raise AttributeError(
                f"FlCommandPort has no method {name!r}; "
                f"expected one of: {sorted(self._ALLOWED)}"
            )

        def _stub(**kwargs: Any) -> DeviceCommand:
            self.calls.append((name, kwargs))
            return DeviceCommand(name, kwargs)

        return _stub


class TestHandlerRoutesThroughPort:
    """Per-feature handler-routing tests with a recording fake.

    Substituting :data:`fl` lets each handler run end-to-end without
    MIDI / SysEx -- the assertions read the recorded call to confirm
    the right Port method ran with the right args.
    """

    def test_mixer_volume_set(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(mixer_handlers, "fl", fake)

        result = mixer_handlers._handle_mixer_volume_set({"track": 5, "value": -3.0})

        assert isinstance(result, Ok)
        assert fake.calls == [("mixer_volume_set", {"track": 5, "value": -3.0})]

    def test_plugin_param_set_with_param_name(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(plugin_handlers, "fl", fake)

        result = plugin_handlers._handle_plugin_param_set(
            {"channel": 0, "param_name": "cutoff", "value": 0.75}
        )

        assert isinstance(result, Ok)
        assert fake.calls == [
            (
                "plugin_param_set",
                {
                    "channel": 0,
                    "value": 0.75,
                    "slot": None,
                    "param": None,
                    "param_name": "cutoff",
                },
            )
        ]

    def test_project_tempo(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(project_handlers, "fl", fake)

        result = project_handlers._handle_tempo({"bpm": 138})

        assert isinstance(result, Ok)
        assert fake.calls == [("tempo", {"bpm": 138.0})]

    def test_transport_position_set(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(transport_handlers, "fl", fake)

        result = transport_handlers._handle_transport_position_set(
            {"position": 16.5, "mode": "ticks"}
        )

        assert isinstance(result, Ok)
        assert fake.calls == [
            ("transport_position_set", {"position": 16.5, "mode": "ticks"})
        ]

    def test_state_with_field(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(state_handlers, "fl", fake)

        result = state_handlers._handle_state({"field": "tempo"})

        assert isinstance(result, Ok)
        assert fake.calls == [("state", {"field": "tempo"})]

    def test_piano_roll_step_melody(self, monkeypatch):
        fake = _RecordingFl()
        monkeypatch.setattr(piano_roll_handlers, "fl", fake)

        result = piano_roll_handlers._handle_step_melody({"notes": [{"pitch": 60}]})

        assert isinstance(result, Ok)
        # Note.from_entry normalises the entry shape so the wire dict
        # carries the full pitch/velocity/length/position record.
        assert len(fake.calls) == 1
        method, kwargs = fake.calls[0]
        assert method == "step_melody"
        assert kwargs["notes"] == [
            {"pitch": 60, "velocity": 100, "length": 1.0, "position": 0.0}
        ]
