"""Validate the device script's inlined protocol v2 helpers.

The device script can't import ``flstudio_cli.shared.infrastructure.protocol.v2`` because it
runs inside FL Studio's Python sandbox where the host package is not
on ``sys.path``. Instead it carries a short copy of the pack/unpack
and frame encode/decode logic. This test stubs out every FL Studio
module, imports the device script as a plain Python module, and
asserts that the two implementations produce byte-identical output
for a battery of payloads.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from flstudio_cli.shared.infrastructure.protocol import v2 as V2

DEVICE_FILE = Path(__file__).resolve().parents[1] / "device_flcli.py"

_FL_STUB_MODULES = (
    "channels",
    "device",
    "general",
    "midi",
    "mixer",
    "patterns",
    "plugins",
    "transport",
    "ui",
)


def _install_fl_stubs() -> None:
    """Register dummy modules for every FL Studio API the device script imports."""
    for name in _FL_STUB_MODULES:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    # Minimal attributes the device script touches at *import* time
    # (all other usage is inside functions that we don't call here).
    midi = sys.modules["midi"]
    midi.MIDI_NOTEON = 0x90
    midi.MIDI_CONTROLCHANGE = 0xB0
    midi.REC_Tempo = 0
    midi.REC_Control = 0
    midi.REC_UpdateControl = 0
    midi.FPT_Record = 0
    midi.FPT_New = 0
    midi.widChannelRack = 0
    midi.SONGLENGTH_BEATS = 0
    midi.SONGLENGTH_TICKS = 1
    midi.SONGLENGTH_MS = 2
    midi.SONGLENGTH_ABSTICKS = 3

    # Patterns/channels/mixer/transport need the absolute minimum so
    # ``_build_router`` / ``_build_v2_dispatcher`` can construct without
    # touching FL Studio. The snapshot function wraps each call in
    # try/except so missing attributes are tolerated.
    patterns = sys.modules["patterns"]
    patterns.patternCount = lambda: 2
    patterns.patternNumber = lambda: 1
    patterns.setPatternName = lambda *a, **kw: None
    patterns.jumpToPattern = lambda *a, **kw: None
    patterns.getPatternName = lambda i: {1: "Verse", 2: "Chorus"}.get(i, "")
    patterns.getPatternColor = lambda i: {1: 255, 2: 16711680}.get(i, 0)

    channels = sys.modules["channels"]
    channels.selectedChannel = lambda: 0
    channels.channelCount = lambda: 2
    channels.selectOneChannel = lambda *a, **kw: None
    channels.setChannelName = lambda *a, **kw: None
    channels.setGridBit = lambda *a, **kw: None
    channels.setStepLevel = lambda *a, **kw: None
    channels.getChannelName = lambda i: ["Kick", "Snare"][i] if i < 2 else ""
    channels.getChannelColor = lambda i: [16711680, 255][i] if i < 2 else 0
    channels.getChannelVolume = lambda i: [0.78, 0.65][i] if i < 2 else 0.0
    channels.getChannelPan = lambda i: 0.0
    channels.getTargetFxTrack = lambda i: i + 1 if i < 2 else 0

    mixer = sys.modules["mixer"]
    mixer.getCurrentTempo = lambda: 120000
    mixer.trackCount = lambda: 4
    mixer.getTrackVolume = lambda index: 0.8
    mixer.setTrackVolume = lambda index, value: None
    mixer.getTrackPan = lambda index: 0.0
    mixer.setTrackPan = lambda index, value: None
    mixer.getTrackName = lambda index: f"Track {index}"
    mixer.setTrackName = lambda index, name: None
    mixer.isTrackMuted = lambda index: 0
    mixer.muteTrack = lambda index: None
    mixer.isTrackSolo = lambda index: 0
    mixer.soloTrack = lambda index: None
    mixer.isTrackArmed = lambda index: 0
    mixer.armTrack = lambda index, arm: None
    mixer.getRouteSendActive = lambda from_idx, to_idx: 0
    mixer.setRouteToTrackIndex = lambda from_idx, to_idx, enabled: None
    mixer.linkTrackToChannel = lambda channel, track: None
    mixer.trackNumber = lambda: 0

    plg = sys.modules["plugins"]
    plg.getPluginName = lambda channel, slot=-1, use_global=False: (
        {0: "FPC", 1: "DirectWave"}.get(channel, "") if slot == -1 else ""
    )
    plg.getParamCount = lambda channel, slot=-1: 0
    plg.getParamName = lambda param, channel, slot=-1: ""
    plg.getParamValue = lambda param, channel, slot=-1: 0.0
    plg.setParamValue = lambda value, param, channel, slot=-1, pickup=0: None
    plg.getParamValueString = lambda param, channel, slot=-1: ""

    transport = sys.modules["transport"]
    transport.isPlaying = lambda: 0
    transport.isRecording = lambda: 0
    transport.start = lambda: None
    transport.stop = lambda: None
    transport.globalTransport = lambda *a, **kw: None
    transport.getSongPos = lambda mode=0: {0: 0.0, 2: 0.0}.get(mode, 0.0)
    transport.setSongPos = lambda position, mode=0: None
    transport.getLoopMode = lambda: 0
    transport.setLoopMode = lambda: None

    general = sys.modules["general"]
    general.processRECEvent = lambda *a, **kw: None
    general.undoUp = lambda: None
    general.undoDown = lambda: None
    general.getUndoHistoryCount = lambda: 0
    general.getUndoHistoryLast = lambda: 0

    ui = sys.modules["ui"]
    ui.showWindow = lambda *a, **kw: None
    ui.hideWindow = lambda *a, **kw: None

    device = sys.modules["device"]
    device.midiOutSysex = lambda payload: None


@pytest.fixture(scope="module")
def device_module():
    """Import ``device_flcli.py`` as a plain Python module."""
    _install_fl_stubs()
    spec = importlib.util.spec_from_file_location("device_flcli", DEVICE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["device_flcli"] = module
    spec.loader.exec_module(module)
    return module


class TestDispatcherParityWithFlCommandPort:
    """The device dispatcher must register exactly the FlCommandPort surface.

    Issue #92 centralised the host-side wire format as the
    :class:`FlCommandPort` Protocol; the device's
    ``_build_v2_dispatcher`` is the receiving side of the same
    contract.  A new command added to one side without the other is
    a wire-protocol bug that would only surface at runtime in
    FL Studio.  This test fails fast in CI instead.

    Why parity instead of codegen
    -----------------------------
    Full handler-body codegen (Issue #69 case A) would require
    expressing the FL Studio API calls in a host-side DSL, which is
    impractical because the device script's handlers depend on
    runtime FL Studio state that has no host counterpart.  Parity
    assertion gives the same drift-detection guarantee at a fraction
    of the cost: adding a command remains a two-place edit (Port
    method + device handler) and forgetting either side fails this
    test immediately.
    """

    def test_registered_command_names_match_fl_command_port(self, device_module):
        from flstudio_cli.shared.application.fl_command_port import FlCommandPort

        port_methods = {
            name
            for name in vars(FlCommandPort)
            if not name.startswith("_") and callable(vars(FlCommandPort)[name])
        }

        dispatcher = device_module._build_v2_dispatcher(device_module.FLStudioBackend())
        device_handlers = set(dispatcher._handlers)

        only_in_port = port_methods - device_handlers
        only_in_device = device_handlers - port_methods
        assert not only_in_port, (
            "FlCommandPort declares methods the device script does not "
            f"register: {sorted(only_in_port)}.  Add a "
            "``dispatcher.register(...)`` call in ``_build_v2_dispatcher`` "
            "for each."
        )
        assert not only_in_device, (
            "device script registers commands the FlCommandPort does not "
            f"declare: {sorted(only_in_device)}.  Add a method to "
            "``FlCommandPort`` and ``DefaultFlCommands`` for each."
        )


class TestDeviceInlinedHelpersMatchHost:
    @pytest.mark.parametrize(
        "payload",
        [
            b"",
            b"\x01",
            bytes(range(7)),
            bytes(range(8)),
            bytes(range(14)),
            bytes(range(50)),
            b"\xff" * 32,
            b"\x00" * 32,
            b'{"cmd":"tempo","args":{"bpm":140.5}}',
            "鍵盤".encode(),
        ],
    )
    def test_pack_7bit_matches_host(self, device_module, payload: bytes) -> None:
        assert device_module._v2_pack_7bit(payload) == V2.pack_7bit(payload)

    @pytest.mark.parametrize(
        "payload",
        [b"", b"\x01", bytes(range(14)), b"\xff" * 32],
    )
    def test_unpack_7bit_matches_host(self, device_module, payload: bytes) -> None:
        packed = V2.pack_7bit(payload)
        assert device_module._v2_unpack_7bit(packed) == V2.unpack_7bit(packed)

    @pytest.mark.parametrize("request_id", [0, 1, 127, 128, 16384, V2.REQUEST_ID_MAX])
    def test_encode_request_id_matches_host(
        self, device_module, request_id: int
    ) -> None:
        assert device_module._v2_encode_request_id(request_id) == V2.encode_request_id(
            request_id
        )

    @pytest.mark.parametrize(
        "request_id,payload",
        [
            (0, b""),
            (1, b'{"cmd":"play","args":{}}'),
            (42, b'{"cmd":"tempo","args":{"bpm":140.5}}'),
            (
                12345,
                b'{"cmd":"name_channel","args":{"channel":3,"name":"my synth bass"}}',
            ),
        ],
    )
    def test_encode_frame_matches_host(
        self, device_module, request_id: int, payload: bytes
    ) -> None:
        host_frame = V2.encode_frame(
            V2.SysExFrame(request_id=request_id, payload=payload)
        )
        device_frame = device_module._v2_encode_frame(request_id, payload)
        assert host_frame == device_frame

    def test_decode_frame_round_trips_host_encoded_frame(self, device_module) -> None:
        payload = b'{"cmd":"tempo","args":{"bpm":140.5}}'
        host_frame = V2.encode_frame(V2.SysExFrame(request_id=99, payload=payload))
        rid, decoded_payload = device_module._v2_decode_frame(host_frame)
        assert rid == 99
        assert decoded_payload == payload

    def test_decode_frame_accepts_interior_bytes_without_bookends(
        self, device_module
    ) -> None:
        """FL Studio may strip or preserve the F0/F7 bookends depending on
        the build. The device helper normalises both cases."""
        payload = b'{"cmd":"play","args":{}}'
        host_frame = V2.encode_frame(V2.SysExFrame(request_id=7, payload=payload))
        interior = host_frame[1:-1]
        rid, decoded_payload = device_module._v2_decode_frame(interior)
        assert rid == 7
        assert decoded_payload == payload


class TestDeviceDispatcher:
    def test_unknown_command_returns_error_envelope(self, device_module) -> None:
        dispatcher = device_module.V2Dispatcher()
        result = dispatcher.dispatch("no_such_command", {})
        assert result["ok"] is False
        assert result["error"]["code"] == "UNKNOWN_COMMAND"

    def test_handler_exception_becomes_internal_error(self, device_module) -> None:
        dispatcher = device_module.V2Dispatcher()

        def handler(args):
            raise ValueError("boom")

        dispatcher.register("bad", handler)
        result = dispatcher.dispatch("bad", {})
        assert result["ok"] is False
        assert result["error"]["code"] == "INTERNAL"
        assert "boom" in result["error"]["message"]

    def test_happy_path_returns_ok_envelope(self, device_module) -> None:
        dispatcher = device_module.V2Dispatcher()
        dispatcher.register("echo", lambda args: {"echoed": args.get("x")})
        result = dispatcher.dispatch("echo", {"x": 42})
        assert result == {
            "ok": True,
            "result": {"echoed": 42},
            "error": None,
        }

    def test_wired_dispatcher_has_expected_commands(self, device_module) -> None:
        # ``_V2_DISPATCH`` is constructed at module import time.
        commands = set(device_module._V2_DISPATCH._handlers.keys())
        expected = {
            "play",
            "stop",
            "record",
            "transport_position_get",
            "transport_position_set",
            "transport_loop_get",
            "transport_loop_toggle",
            "undo",
            "redo",
            "undo_history",
            "new_project",
            "new_pattern",
            "select_pattern",
            "channel_rack_focus",
            "focus_channel_editor",
            "name_pattern",
            "name_channel",
            "select_channel",
            "tempo",
            "set_step",
            "state",
            "mixer_list",
            "mixer_volume_get",
            "mixer_volume_set",
            "mixer_pan_get",
            "mixer_pan_set",
            "mixer_name_get",
            "mixer_name_set",
            "mixer_mute",
            "mixer_solo",
            "mixer_arm",
            "mixer_route_set",
            "mixer_link_to_channel",
        }
        assert expected.issubset(commands)


class TestExpandedSnapshot:
    """Verify the expanded state snapshot from the device module."""

    def test_snapshot_contains_all_sections(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        # Force fresh snapshot by setting throttle to 0.
        snap = backend.snapshot(throttle_ms=0)
        assert "tempo" in snap
        assert "song_position" in snap
        assert "channels" in snap
        assert "patterns" in snap
        assert "mixer" in snap
        assert "updated_at" in snap

    def test_song_position_is_structured(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap = backend.snapshot(throttle_ms=0)
        pos = snap["song_position"]
        assert isinstance(pos, dict)
        assert "beats" in pos
        assert "ms" in pos

    def test_channels_populated(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap = backend.snapshot(throttle_ms=0)
        ch_list = snap["channels"]
        assert isinstance(ch_list, list)
        assert len(ch_list) == 2
        assert ch_list[0]["name"] == "Kick"
        assert ch_list[0]["index"] == 0
        assert ch_list[1]["name"] == "Snare"

    def test_channels_have_plugin_name(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap = backend.snapshot(throttle_ms=0)
        assert snap["channels"][0]["plugin_name"] == "FPC"
        assert snap["channels"][1]["plugin_name"] == "DirectWave"

    def test_patterns_populated(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap = backend.snapshot(throttle_ms=0)
        pat_list = snap["patterns"]
        assert isinstance(pat_list, list)
        assert len(pat_list) == 2
        assert pat_list[0]["index"] == 1
        assert pat_list[0]["name"] == "Verse"

    def test_mixer_populated(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap = backend.snapshot(throttle_ms=0)
        mx = snap["mixer"]
        assert isinstance(mx, dict)
        assert "tracks" in mx
        assert "routing" in mx
        assert len(mx["tracks"]) == 4  # stub returns trackCount()=4

    def test_snapshot_throttle_caches(self, device_module) -> None:
        """Two rapid calls with a large throttle should return the same object."""
        backend = device_module.FLStudioBackend()
        snap1 = backend.snapshot(throttle_ms=60000)
        snap2 = backend.snapshot(throttle_ms=60000)
        assert snap1 is snap2

    def test_snapshot_throttle_zero_forces_refresh(self, device_module) -> None:
        backend = device_module.FLStudioBackend()
        snap1 = backend.snapshot(throttle_ms=0)
        snap2 = backend.snapshot(throttle_ms=0)
        assert snap1 is not snap2


class TestStateHandlerDottedPath:
    """Verify the state v2 handler supports dotted field paths."""

    def test_full_state_returned_when_no_field(self, device_module) -> None:
        result = device_module._V2_DISPATCH.dispatch("state", {})
        assert result["ok"] is True
        assert "state" in result["result"]

    def test_top_level_field(self, device_module) -> None:
        result = device_module._V2_DISPATCH.dispatch(
            "state",
            {"field": "tempo", "throttle_ms": 0},
        )
        assert result["ok"] is True
        assert result["result"]["field"] == "tempo"
        assert isinstance(result["result"]["value"], float)

    def test_dotted_path_into_channels(self, device_module) -> None:
        result = device_module._V2_DISPATCH.dispatch(
            "state",
            {"field": "channels.0.name", "throttle_ms": 0},
        )
        assert result["ok"] is True
        assert result["result"]["value"] == "Kick"

    def test_dotted_path_into_mixer_tracks(self, device_module) -> None:
        result = device_module._V2_DISPATCH.dispatch(
            "state",
            {"field": "mixer.tracks.0.name", "throttle_ms": 0},
        )
        assert result["ok"] is True
        assert result["result"]["value"] == "Track 0"

    def test_unknown_path_returns_error(self, device_module) -> None:
        result = device_module._V2_DISPATCH.dispatch(
            "state",
            {"field": "nonexistent", "throttle_ms": 0},
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "INTERNAL"


class TestPluginHandlers:
    """Mixer-effect listing and parameter writes on the device side."""

    def test_param_set_passes_no_pickup(self, device_module, monkeypatch) -> None:
        plg = sys.modules["plugins"]
        calls = []
        monkeypatch.setattr(plg, "getPluginName", lambda ch, slot=-1, *a: "ebbline")
        monkeypatch.setattr(plg, "getParamName", lambda p, ch, slot=-1: "Shape")
        monkeypatch.setattr(plg, "getParamValue", lambda p, ch, slot=-1: 0.0)
        monkeypatch.setattr(plg, "setParamValue", lambda *args: calls.append(args))
        result = device_module._V2_DISPATCH.dispatch(
            "plugin_param_set", {"channel": 5, "slot": 0, "param": 5, "value": 0.5}
        )
        assert result["ok"] is True, result
        # value, param, index, slot, pickup mode (0 = apply as sent)
        assert calls == [(0.5, 5, 5, 0, 0)]
        # The plugin still reports the old value: flagged, not hidden.
        assert result["result"]["requested"] == 0.5
        assert result["result"]["pending"] is True

    def test_list_mixer_track_skips_the_channel_plugin(
        self, device_module, monkeypatch
    ) -> None:
        plg = sys.modules["plugins"]
        names = {(5, -1): "FLEX", (5, 0): "ebbline"}
        monkeypatch.setattr(
            plg, "getPluginName", lambda ch, slot=-1, *a: names.get((ch, slot), "")
        )
        as_track = device_module._V2_DISPATCH.dispatch(
            "plugin_list", {"channel": 5, "mixer": True}
        )
        assert as_track["result"] == {
            "track": 5,
            "plugins": [{"slot": 0, "name": "ebbline"}],
        }
        as_channel = device_module._V2_DISPATCH.dispatch("plugin_list", {"channel": 5})
        assert as_channel["result"]["plugins"][0] == {"slot": -1, "name": "FLEX"}


class TestFocusChannelEditor:
    """Opening the Piano Roll for a channel must retarget an open one."""

    def test_piano_roll_is_hidden_then_shown(self, device_module, monkeypatch) -> None:
        ui = sys.modules["ui"]
        chans = sys.modules["channels"]
        calls = []
        monkeypatch.setattr(
            chans, "selectOneChannel", lambda i: calls.append(("select", i))
        )
        monkeypatch.setattr(ui, "hideWindow", lambda w: calls.append(("hide", w)))
        monkeypatch.setattr(ui, "showWindow", lambda w: calls.append(("show", w)))
        monkeypatch.setattr(ui, "setFocused", lambda w: None, raising=False)
        monkeypatch.setattr(sys.modules["midi"], "widPianoRoll", 3, raising=False)
        result = device_module._V2_DISPATCH.dispatch(
            "focus_channel_editor", {"channel": 6, "window": "piano_roll"}
        )
        assert result["ok"] is True, result
        piano = 3
        # Select first, then hide and show so FL reopens it on channel 6.
        assert calls == [("select", 6), ("hide", piano), ("show", piano)]


class TestMixerEqSendStereo:
    """Built-in EQ, sends, stereo, polarity, meters and presets on the device."""

    @pytest.fixture
    def eq(self, device_module, monkeypatch):
        mx = sys.modules["mixer"]
        state = {"gain": 0.5, "freq": 0.5, "bw": 0.267}

        def gain(track, band, mode=0):
            return (state["gain"] - 0.5) * 36 if mode == 1 else state["gain"]

        def freq(track, band, mode=0):
            return 20 * 1000 ** state["freq"] if mode == 1 else state["freq"]

        for name, fn in {
            "getEqBandCount": lambda: 3,
            "getEqGain": gain,
            "getEqFrequency": freq,
            "getEqBandwidth": lambda track, band: state["bw"],
            "setEqGain": lambda t, b, v: state.__setitem__("gain", v),
            "setEqFrequency": lambda t, b, v: state.__setitem__("freq", v),
            "setEqBandwidth": lambda t, b, v: state.__setitem__("bw", v),
        }.items():
            monkeypatch.setattr(mx, name, fn, raising=False)
        return state

    def test_eq_set_answers_with_what_was_asked(self, device_module, eq) -> None:
        # FL applies the change after the handler returns, so the handler
        # must not report a read-back as the new value.
        result = device_module._V2_DISPATCH.dispatch(
            "mixer_eq_set", {"track": 5, "band": 0, "gain": 0.25, "freq": 0.1}
        )
        assert result["ok"] is True, result
        assert result["result"] == {
            "track": 5,
            "band": 0,
            "requested": {"gain": 0.25, "freq": 0.1},
        }
        assert eq["gain"] == 0.25 and eq["freq"] == 0.1

    def test_eq_rejects_a_band_out_of_range(self, device_module, eq) -> None:
        result = device_module._V2_DISPATCH.dispatch(
            "mixer_eq_set", {"track": 5, "band": 3, "gain": 0.4}
        )
        assert result["ok"] is False
        assert result["error"]["code"] == device_module.CODE_INVALID_ARGUMENT

    def test_eq_get_lists_every_band(self, device_module, eq) -> None:
        result = device_module._V2_DISPATCH.dispatch("mixer_eq_get", {"track": 1})
        assert [b["band"] for b in result["result"]["bands"]] == [0, 1, 2]

    def test_send_level_round_trips(self, device_module, monkeypatch) -> None:
        mx = sys.modules["mixer"]
        levels = {}
        monkeypatch.setattr(
            mx,
            "setRouteToLevel",
            lambda s, d, v: levels.__setitem__((s, d), v),
            raising=False,
        )
        monkeypatch.setattr(
            mx, "getRouteToLevel", lambda s, d: levels.get((s, d), 0.0), raising=False
        )
        monkeypatch.setattr(mx, "getRouteSendActive", lambda s, d: 1)
        result = device_module._V2_DISPATCH.dispatch(
            "mixer_send_set", {"from": 1, "to": 5, "level": 0.8}
        )
        assert result["result"] == {"from": 1, "to": 5, "active": 1, "level": 0.8}

    def test_polarity_and_stereo(self, device_module, monkeypatch) -> None:
        mx = sys.modules["mixer"]
        state = {"rev": 0, "sep": 0.0}
        monkeypatch.setattr(
            mx,
            "revTrackPolarity",
            lambda i, v: state.__setitem__("rev", v),
            raising=False,
        )
        monkeypatch.setattr(
            mx, "isTrackRevPolarity", lambda i: state["rev"], raising=False
        )
        monkeypatch.setattr(
            mx,
            "setTrackStereoSep",
            lambda i, v: state.__setitem__("sep", v),
            raising=False,
        )
        monkeypatch.setattr(
            mx, "getTrackStereoSep", lambda i: state["sep"], raising=False
        )
        pol = device_module._V2_DISPATCH.dispatch(
            "mixer_polarity", {"track": 2, "on": True}
        )
        assert pol["result"] == {"track": 2, "reversed": True}
        st = device_module._V2_DISPATCH.dispatch(
            "mixer_stereo_set", {"track": 2, "value": -0.5}
        )
        assert st["result"] == {"track": 2, "requested": -0.5}
        assert state["sep"] == -0.5

    def test_peaks_for_named_tracks(self, device_module, monkeypatch) -> None:
        mx = sys.modules["mixer"]
        monkeypatch.setattr(
            mx,
            "getTrackPeaks",
            lambda i, mode: 0.5 if mode == 0 else 0.25,
            raising=False,
        )
        result = device_module._V2_DISPATCH.dispatch("mixer_peaks", {"tracks": [1, 5]})
        assert result["result"]["peaks"] == [
            {
                "track": 1,
                "left": 0.5,
                "right": 0.25,
                "left_db": -6.0,
                "right_db": -12.0,
            },
            {
                "track": 5,
                "left": 0.5,
                "right": 0.25,
                "left_db": -6.0,
                "right_db": -12.0,
            },
        ]

    def test_preset_steps_the_right_way(self, device_module, monkeypatch) -> None:
        plg = sys.modules["plugins"]
        calls = []
        monkeypatch.setattr(plg, "getPluginName", lambda ch, slot=-1, *a: "FLEX")
        monkeypatch.setattr(
            plg, "nextPreset", lambda c, s: calls.append("next"), raising=False
        )
        monkeypatch.setattr(
            plg, "prevPreset", lambda c, s: calls.append("prev"), raising=False
        )
        monkeypatch.setattr(plg, "getPresetCount", lambda c, s: 12, raising=False)
        result = device_module._V2_DISPATCH.dispatch(
            "plugin_preset", {"channel": 6, "direction": "prev"}
        )
        assert calls == ["prev"]
        assert result["result"]["preset_count"] == 12
