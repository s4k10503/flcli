# name=flcli
"""Infrastructure adapter: FL Studio MIDI Scripting controller for flstudio-cli (protocol v2).

Place this file in:
    Documents/Image-Line/FL Studio/Settings/Hardware/flcli/device_flcli.py

Protocol v2 is a pure SysEx request/response scheme:

* ``OnSysEx`` decodes the incoming ``F0 7D 02 <rid> <packed_json> F7``
  frame, looks the JSON ``cmd`` up in :class:`V2Dispatcher`, and
  replies via ``device.midiOutSysex()`` on the return port (``flcli-rx``).
* ``FLStudioBackend`` is the single seam around FL Studio's Python API
  (SRP + DIP), so handlers can be unit-tested by stubbing the backend.
* ``V2Dispatcher`` maps string command names to stateless handlers
  that return plain ``dict`` result payloads. Every dispatch is
  try/except-wrapped so a handler bug can't tear down the MIDI thread.

The pack/unpack and frame encode/decode helpers are intentionally
inlined (~60 lines) because the FL Studio Python sandbox cannot import
``flstudio_cli.shared.infrastructure.protocol.v2``. The two implementations are kept in sync
via ``tests/test_device_v2.py`` which stubs the FL Studio modules and
checks that the device-side output matches the host-side module
byte-for-byte on a shared set of vectors.

Realtime piano-roll recording (``flcli piano-roll``) streams notes on
:data:`PIANO_ROLL_MIDI_CHANNEL` via a different code path (the CLI
opens its own ``mido`` output). Because this script defines no
``OnMidiMsg``, FL Studio handles those events through its standard
MIDI recorder.
"""

import json
import time

import channels
import device
import general
import midi
import mixer
import patterns
import plugins
import transport
import ui

# === Error codes (must stay in sync with envelope.py on the CLI side) =======

CODE_INVALID_ARGUMENT = "INVALID_ARGUMENT"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_INTERNAL = "INTERNAL"

# Per-call info prints land on the FL Studio script console synchronously on the
# MIDI thread; under heavy command streams (e.g. ``batch stream``) the I/O
# starves the rtmidi callback. Errors and one-shot events still print
# unconditionally — only the per-frame chatter is gated here.
DEBUG = False


# === Error signalling =======================================================


class _HandlerError(Exception):
    """Raised by a handler to surface a specific error code (e.g. NOT_FOUND)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# === FL Studio facade =======================================================


class FLStudioBackend:
    """Single seam between this script and FL Studio's Python API."""

    # --- Transport -------------------------------------------------------

    def play(self):
        transport.start()

    def stop(self):
        transport.stop()

    def record(self):
        # globalTransport(FPT_Record, ...) blocked the MIDI thread; the
        # dedicated transport.record() toggle is the official path.
        transport.record()

    def is_recording(self):
        try:
            return bool(transport.isRecording())
        except Exception:
            return False

    def get_song_position(self, mode):
        return transport.getSongPos(mode)

    def set_song_position(self, position, mode):
        transport.setSongPos(position, mode)

    def get_loop_mode(self):
        return transport.getLoopMode()

    def toggle_loop_mode(self):
        transport.setLoopMode()

    # --- Undo / redo -----------------------------------------------------

    def undo(self):
        general.undoUp()

    def redo(self):
        general.undoDown()

    def get_undo_history_count(self):
        return general.getUndoHistoryCount()

    def get_undo_history_last(self):
        return general.getUndoHistoryLast()

    # --- Project / pattern / channel -------------------------------------

    def new_project(self):
        try:
            transport.globalTransport(midi.FPT_New, 1)
        except Exception:
            pass

    def new_pattern(self, name=None):
        index = patterns.patternCount() + 1
        # Empty string resets the name to FL's default; we keep the legacy
        # "flcli" sentinel when the caller doesn't supply one so existing
        # batch scripts behave the same as before this change.
        label = name if name is not None else "flcli"
        patterns.setPatternName(index, label)
        patterns.jumpToPattern(index)
        return index

    def select_pattern(self, index):
        patterns.jumpToPattern(index)

    def set_pattern_name(self, index, name):
        patterns.setPatternName(index, name)

    def pattern_count(self):
        try:
            return int(patterns.patternCount())
        except Exception:
            return 0

    def channel_count(self):
        try:
            return int(channels.channelCount())
        except Exception:
            return 0

    def focus_channel_rack(self):
        # ui.copy()/paste() do not duplicate Channel Rack entries on macOS;
        # the working path is the FL hotkey (Alt+C) which the CLI fires via
        # osascript after we surface the Channel Rack here.
        try:
            ui.showWindow(midi.widChannelRack)
        except Exception:
            pass
        try:
            ui.setFocused(midi.widChannelRack)
        except Exception:
            pass

    def focus_channel_editor(self, channel_index, window):
        # Select the requested channel first so the editor that opens
        # operates on the right rack entry. ``window`` picks between the
        # Piano Roll and the channel's plugin/sampler editor.
        try:
            channels.selectOneChannel(channel_index)
        except Exception:
            pass
        if window == "piano_roll":
            try:
                ui.showWindow(midi.widPianoRoll)
            except Exception:
                pass
            try:
                ui.setFocused(midi.widPianoRoll)
            except Exception:
                pass
        elif window == "plugin":
            try:
                channels.focusEditor(channel_index)
            except Exception:
                pass

    def name_channel(self, channel, name):
        try:
            channels.setChannelName(channel, name)
        except Exception:
            pass

    def select_channel(self, channel):
        try:
            channels.selectOneChannel(channel)
        except Exception:
            pass

    def selected_channel(self):
        try:
            return channels.selectedChannel()
        except Exception:
            return 0

    # --- Tempo -----------------------------------------------------------

    def set_tempo_bpm(self, bpm):
        # FL Studio stores tempo as BPM * 1000.
        general.processRECEvent(
            midi.REC_Tempo,
            int(bpm * 1000),
            midi.REC_Control | midi.REC_UpdateControl,
        )

    # --- Step sequencer --------------------------------------------------

    def set_grid_bit(self, channel, step, value):
        channels.setGridBit(channel, step, 1 if value else 0)

    def set_step_velocity(self, channel, step, value):
        try:
            channels.setStepLevel(channel, step, value / 127.0)
        except Exception:
            pass

    # --- Mixer -----------------------------------------------------------

    def mixer_track_count(self):
        try:
            return mixer.trackCount()
        except Exception:
            return 127

    def mixer_get_track_volume(self, index):
        return mixer.getTrackVolume(index)

    def mixer_set_track_volume(self, index, value):
        mixer.setTrackVolume(index, value)

    def mixer_get_track_pan(self, index):
        return mixer.getTrackPan(index)

    def mixer_set_track_pan(self, index, value):
        mixer.setTrackPan(index, value)

    def mixer_get_track_name(self, index):
        return mixer.getTrackName(index)

    def mixer_set_track_name(self, index, name):
        mixer.setTrackName(index, name)

    def mixer_is_track_muted(self, index):
        return bool(mixer.isTrackMuted(index))

    def mixer_mute_track(self, index, value=-1):
        # value=-1 → toggle, 1 → mute, 0 → unmute (per official API stubs).
        # The dispatcher uses the explicit on/off form to avoid a race
        # where ``isTrackMuted`` read back the pre-toggle value on the
        # MIDI thread.
        mixer.muteTrack(index, value)

    def mixer_is_track_solo(self, index):
        return bool(mixer.isTrackSolo(index))

    def mixer_solo_track(self, index):
        mixer.soloTrack(index)

    def mixer_is_track_armed(self, index):
        try:
            return bool(mixer.isTrackArmed(index))
        except Exception:
            return False

    def mixer_arm_track(self, index, arm):
        try:
            mixer.armTrack(index, 1 if arm else 0)
        except Exception:
            pass

    def mixer_get_route_send_active(self, from_idx, to_idx):
        return bool(mixer.getRouteSendActive(from_idx, to_idx))

    def mixer_set_route_to(self, from_idx, to_idx, enabled):
        # FL Studio renamed this API across versions; fall back to whatever
        # the current ``mixer`` module exposes.
        flag = 1 if enabled else 0
        for name in ("setRouteToTrackIndex", "setRouteTo", "setRoute"):
            fn = getattr(mixer, name, None)
            if fn is None:
                continue
            try:
                fn(from_idx, to_idx, flag)
            except TypeError:
                # Two-arg variant (older API: from, to → toggles).
                fn(from_idx, to_idx)
            try:
                mixer.afterRoutingChanged()
            except Exception:
                pass
            return
        raise AttributeError(
            "mixer routing API unavailable (no setRouteToTrackIndex / setRouteTo / setRoute)"
        )

    def mixer_link_to_channel(self, track_index, channel_index):
        # Official linkTrackToChannel takes a single ``mode`` arg
        # (ROUTE_ToThis = 0) and operates on the *currently selected*
        # channel and mixer track. The CLI surface (``mixer
        # link-to-channel --channel N --track M``) therefore has to
        # select both endpoints first before issuing the route call.
        try:
            channels.selectOneChannel(channel_index)
        except Exception:
            pass
        try:
            mixer.setActiveTrack(track_index)
        except Exception:
            pass
        try:
            mixer.linkTrackToChannel(0)
        except Exception:
            pass

    def mixer_selected_track(self):
        try:
            return mixer.trackNumber()
        except Exception:
            return 0

    def mixer_track_info(self, index):
        """Return a dict with a single mixer track's state."""
        info = {"index": index}

        def safe(name, fn):
            try:
                info[name] = fn()
            except Exception:
                info[name] = None

        safe("name", lambda: mixer.getTrackName(index))
        safe("volume", lambda: round(mixer.getTrackVolume(index), 4))
        safe("pan", lambda: round(mixer.getTrackPan(index), 4))
        safe("mute", lambda: bool(mixer.isTrackMuted(index)))
        safe("solo", lambda: bool(mixer.isTrackSolo(index)))
        return info

    def mixer_list_tracks(self):
        """Return a list of dicts for every mixer track."""
        count = self.mixer_track_count()
        return [self.mixer_track_info(i) for i in range(count)]

    # --- Plugins ---------------------------------------------------------

    def plugin_get_name(self, channel, slot=-1):
        return plugins.getPluginName(channel, slot)

    def plugin_get_param_count(self, channel, slot=-1):
        return plugins.getParamCount(channel, slot)

    def plugin_get_param_name(self, param, channel, slot=-1):
        return plugins.getParamName(param, channel, slot)

    def plugin_get_param_value(self, param, channel, slot=-1):
        return plugins.getParamValue(param, channel, slot)

    def plugin_set_param_value(self, value, param, channel, slot=-1):
        plugins.setParamValue(value, param, channel, slot)

    def plugin_get_param_value_string(self, param, channel, slot=-1):
        return plugins.getParamValueString(param, channel, slot)

    # --- State snapshot --------------------------------------------------

    def __init__(self):
        self._cached_snapshot = None
        self._snapshot_time = 0.0

    def snapshot(self, throttle_ms=500, sections=None):
        """Collect a best-effort dict of the current FL Studio state.

        Each field and section is wrapped in its own try/except so
        that an API change in one area never breaks the rest of the
        snapshot.  Results are cached for ``throttle_ms`` to keep
        polling cheap when snapshots are large.

        *sections* is an optional set of top-level keys to build.
        When given, only those sections are evaluated — the rest are
        skipped, which avoids hundreds of API calls on the FL Studio
        MIDI thread when only a scalar like ``tempo`` is needed.
        A full snapshot (``sections=None``) is always cached; partial
        snapshots are not.
        """
        # Full-snapshot cache
        if sections is None:
            now = time.time()
            elapsed = now - self._snapshot_time
            if (
                self._cached_snapshot is not None
                and elapsed >= 0
                and elapsed * 1000 < throttle_ms
            ):
                return self._cached_snapshot

        snap = {}

        def safe(name, fn, target=None):
            dest = snap if target is None else target
            try:
                dest[name] = fn()
            except Exception:
                dest[name] = None

        def _want(name):
            return sections is None or name in sections

        # --- scalar fields -------------------------------------------
        if _want("tempo"):
            safe("tempo", lambda: mixer.getCurrentTempo() / 1000.0)
        if _want("current_pattern"):
            safe("current_pattern", lambda: patterns.patternNumber())
        if _want("pattern_count"):
            safe("pattern_count", lambda: patterns.patternCount())
        if _want("selected_channel"):
            safe("selected_channel", lambda: channels.selectedChannel())
        if _want("channel_count"):
            safe("channel_count", lambda: channels.channelCount())
        if _want("is_playing"):
            safe("is_playing", lambda: bool(transport.isPlaying()))
        if _want("is_recording"):
            safe("is_recording", lambda: bool(transport.isRecording()))

        # --- song position (structured) ------------------------------
        if _want("song_position"):

            def _song_position():
                result = {}
                beats_mode = getattr(midi, "SONGLENGTH_BEATS", None)
                if beats_mode is not None:
                    result["beats"] = transport.getSongPos(beats_mode)
                else:
                    abs_mode = getattr(midi, "SONGLENGTH_ABSTICKS", None)
                    ppq = general.getRecPPQ() if abs_mode is not None else 0
                    if abs_mode is not None and ppq:
                        result["beats"] = transport.getSongPos(abs_mode) / ppq
                ms_mode = getattr(midi, "SONGLENGTH_MS", None)
                if ms_mode is not None:
                    result["ms"] = transport.getSongPos(ms_mode)
                return result

            safe("song_position", _song_position)

        # --- channels ------------------------------------------------
        if _want("channels"):

            def _channels():
                count = channels.channelCount()
                result = []
                for i in range(count):
                    ch = {"index": i}
                    safe("name", lambda i=i: channels.getChannelName(i), ch)
                    safe("color", lambda i=i: channels.getChannelColor(i), ch)
                    safe(
                        "volume", lambda i=i: round(channels.getChannelVolume(i), 4), ch
                    )
                    safe("pan", lambda i=i: round(channels.getChannelPan(i), 4), ch)
                    safe(
                        "target_fx_track", lambda i=i: channels.getTargetFxTrack(i), ch
                    )
                    safe("plugin_name", lambda i=i: plugins.getPluginName(i), ch)
                    result.append(ch)
                return result

            safe("channels", _channels)

        # --- patterns ------------------------------------------------
        if _want("patterns"):

            def _patterns():
                count = patterns.patternCount()
                result = []
                for i in range(1, count + 1):
                    pat = {"index": i}
                    safe("name", lambda i=i: patterns.getPatternName(i), pat)
                    safe("color", lambda i=i: patterns.getPatternColor(i), pat)
                    result.append(pat)
                return result

            safe("patterns", _patterns)

        # --- mixer ---------------------------------------------------
        if _want("mixer"):

            def _mixer():
                count = mixer.trackCount()
                tracks = []
                for i in range(count):
                    track = {"index": i}
                    safe("name", lambda i=i: mixer.getTrackName(i), track)
                    safe("volume", lambda i=i: round(mixer.getTrackVolume(i), 4), track)
                    safe("pan", lambda i=i: round(mixer.getTrackPan(i), 4), track)
                    safe("mute", lambda i=i: bool(mixer.isTrackMuted(i)), track)
                    safe("solo", lambda i=i: bool(mixer.isTrackSolo(i)), track)
                    tracks.append(track)
                # Scan routing only for the master destination (track 0)
                # to avoid O(N^2) cost with 127 tracks.
                routing = []
                for src in range(1, count):
                    try:
                        if mixer.getRouteSendActive(src, 0):
                            routing.append([src, 0])
                    except Exception:
                        pass
                # Non-master routes: only between tracks with non-default names
                named = [
                    t["index"] for t in tracks if t.get("name") and t["index"] != 0
                ]
                for src in named:
                    for dst in named:
                        if src != dst:
                            try:
                                if mixer.getRouteSendActive(src, dst):
                                    routing.append([src, dst])
                            except Exception:
                                pass
                return {"tracks": tracks, "routing": routing}

            safe("mixer", _mixer)

        snap["updated_at"] = time.time()

        # Only cache full snapshots
        if sections is None:
            self._cached_snapshot = snap
            self._snapshot_time = now
        return snap


# === Protocol v2 (SysEx) =====================================================
#
# The FL Studio Python sandbox cannot import ``flstudio_cli.shared.infrastructure.protocol.v2``,
# so we carry a short copy of the pack/unpack and frame encode/decode
# helpers here. The block between the markers below is **generated**
# from ``shared/infrastructure/protocol/_device_portable.py`` by
# ``scripts/gen_device_protocol.py``; do not edit it by hand. The CI
# step in ``ci.yml`` runs the generator and ``git diff --exit-code``
# so a manual edit fails fast.

# === BEGIN AUTO-GENERATED PROTOCOL ===

SYSEX_VENDOR_ID = 0x7D
SYSEX_PROTOCOL_V2 = 2
SYSEX_REQUEST_ID_BYTES = 4
SYSEX_REQUEST_ID_MAX = (1 << 28) - 1


def _v2_pack_7bit(data):
    """Pack 8-bit bytes into 7-bit SysEx-safe bytes (Roland-style)."""
    if not data:
        return b""
    out = bytearray()
    index = 0
    length = len(data)
    while index < length:
        block = data[index : index + 7]
        msb_byte = 0
        for block_index, source_byte in enumerate(block):
            if source_byte & 0x80:
                msb_byte |= 1 << block_index
        out.append(msb_byte)
        for source_byte in block:
            out.append(source_byte & 0x7F)
        index += 7
    return bytes(out)


def _v2_unpack_7bit(packed):
    """Inverse of ``_v2_pack_7bit``. Raises ``ValueError`` on malformed input."""
    if not packed:
        return b""
    for byte in packed:
        if byte & 0x80:
            raise ValueError("packed payload byte has high bit set")
    out = bytearray()
    index = 0
    length = len(packed)
    while index < length:
        msb_byte = packed[index]
        index += 1
        remaining = length - index
        block_len = 7 if remaining >= 7 else remaining
        if block_len == 0:
            raise ValueError("trailing MSB byte with no data bytes")
        for byte_index in range(block_len):
            data_byte = packed[index + byte_index]
            if msb_byte & (1 << byte_index):
                data_byte |= 0x80
            out.append(data_byte)
        index += block_len
    return bytes(out)


def _v2_encode_request_id(request_id):
    if request_id < 0 or request_id > SYSEX_REQUEST_ID_MAX:
        raise ValueError("request_id out of range")
    return bytes(
        (request_id >> (7 * (SYSEX_REQUEST_ID_BYTES - 1 - i))) & 0x7F
        for i in range(SYSEX_REQUEST_ID_BYTES)
    )


def _v2_decode_request_id(four_bytes):
    if len(four_bytes) != SYSEX_REQUEST_ID_BYTES:
        raise ValueError("request id must be 4 bytes")
    value = 0
    for byte in four_bytes:
        if byte & 0x80:
            raise ValueError("request id byte has high bit set")
        value = (value << 7) | byte
    return value


def _v2_encode_frame(request_id, payload_bytes):
    """Encode ``F0 7D 02 <rid> <packed_payload> F7``."""
    out = bytearray()
    out.append(0xF0)
    out.append(SYSEX_VENDOR_ID)
    out.append(SYSEX_PROTOCOL_V2)
    out.extend(_v2_encode_request_id(request_id))
    out.extend(_v2_pack_7bit(payload_bytes))
    out.append(0xF7)
    return bytes(out)


def _v2_decode_frame(raw):
    """Validate and decode a v2 frame. Returns ``(request_id, payload_bytes)``.

    Accepts either the full ``F0 ... F7`` byte string or the interior
    bytes; FL Studio builds differ in whether they preserve the
    bookends on ``event.sysex``.
    """
    if not raw:
        raise ValueError("empty SysEx frame")
    buffer = raw
    if buffer[0] != 0xF0 or buffer[-1] != 0xF7:
        buffer = bytes([0xF0]) + bytes(buffer) + bytes([0xF7])
    if len(buffer) < 2 + 1 + 1 + SYSEX_REQUEST_ID_BYTES:
        raise ValueError("frame too short")
    if buffer[1] != SYSEX_VENDOR_ID:
        raise ValueError("unexpected vendor id")
    if buffer[2] != SYSEX_PROTOCOL_V2:
        raise ValueError("protocol version mismatch")
    rid = _v2_decode_request_id(buffer[3 : 3 + SYSEX_REQUEST_ID_BYTES])
    packed = buffer[3 + SYSEX_REQUEST_ID_BYTES : -1]
    payload = _v2_unpack_7bit(packed)
    return rid, payload


# === END AUTO-GENERATED PROTOCOL ===


class V2Dispatcher:
    """Protocol v2 command dispatcher keyed by string command name.

    Each handler takes an ``args`` dict and returns a ``result`` dict
    (any JSON-serialisable value). Exceptions become ``INTERNAL``
    error responses so a handler bug can never crash the MIDI callback.
    """

    def __init__(self):
        self._handlers = {}

    def register(self, name, fn):
        self._handlers[name] = fn

    def dispatch(self, cmd, args):
        fn = self._handlers.get(cmd)
        if fn is None:
            return {
                "ok": False,
                "result": None,
                "error": {
                    "code": "UNKNOWN_COMMAND",
                    "message": "unknown v2 command: " + str(cmd),
                },
            }
        try:
            result = fn(args or {})
        except _HandlerError as exc:
            return {
                "ok": False,
                "result": None,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "result": None,
                "error": {
                    "code": "INTERNAL",
                    "message": exc.__class__.__name__ + ": " + str(exc),
                },
            }
        return {"ok": True, "result": result, "error": None}


# === Wiring =================================================================


def _build_v2_dispatcher(backend):
    """Construct the protocol v2 string-keyed dispatcher."""
    dispatcher = V2Dispatcher()

    def _play(args):
        backend.play()
        return {}

    def _stop(args):
        backend.stop()
        return {}

    def _record(args):
        was_recording = backend.is_recording()
        backend.record()
        return {"recording": not was_recording}

    def _new_project(args):
        backend.new_project()
        return {}

    def _new_pattern(args):
        name = args.get("name")
        if name is not None:
            name = str(name)
        index = backend.new_pattern(name)
        return {"index": index, "name": name if name is not None else "flcli"}

    def _select_pattern(args):
        backend.select_pattern(int(args["index"]))
        return {"index": int(args["index"])}

    def _name_pattern(args):
        index = int(args["index"])
        name = str(args["name"])
        backend.set_pattern_name(index, name)
        return {"index": index, "name": name}

    def _channel_rack_focus(args):
        backend.focus_channel_rack()
        return {"count": backend.channel_count()}

    def _focus_channel_editor(args):
        channel = int(args["channel"])
        window = str(args.get("window", "piano_roll"))
        backend.focus_channel_editor(channel, window)
        return {"channel": channel, "window": window}

    def _name_channel(args):
        channel = int(args["channel"])
        name = str(args["name"])
        backend.name_channel(channel, name)
        return {"channel": channel, "name": name}

    def _select_channel(args):
        backend.select_channel(int(args["index"]))
        return {"index": int(args["index"])}

    def _tempo(args):
        bpm = float(args["bpm"])
        backend.set_tempo_bpm(bpm)
        return {"bpm": bpm}

    def _set_step(args):
        channel = int(args["channel"])
        step = int(args["step"])
        on = bool(args.get("on", True))
        velocity = int(args.get("velocity", 100))
        backend.set_grid_bit(channel, step, 1 if on else 0)
        if on:
            backend.set_step_velocity(channel, step, velocity)
        return {"channel": channel, "step": step, "on": on, "velocity": velocity}

    def _step_melody(args):
        """Paint a list of notes onto the selected channel's step grid.

        ``length`` and ``position`` are in beats; the grid is 1/16 so
        each beat covers 4 steps. Pitch is deliberately ignored — the
        step grid has no pitch dimension, so this handler only
        communicates rhythmic placement and velocity.
        """
        raw_notes = args.get("notes") or []
        channel = backend.selected_channel()
        painted = 0
        for entry in raw_notes:
            pitch = int(entry.get("pitch", 60))  # noqa: F841 - accepted but unused
            velocity = int(entry.get("velocity", 100))
            length_beats = float(entry.get("length", 1.0))
            position_beats = float(entry.get("position", 0.0))
            start = int(round(position_beats * 4))
            count = max(1, int(round(length_beats * 4)))
            for step in range(start, start + count):
                if 0 <= step < 64:
                    backend.set_grid_bit(channel, step, 1)
                    backend.set_step_velocity(channel, step, velocity)
                    painted += 1
        return {"channel": channel, "steps_painted": painted}

    def _resolve_dotted_path(obj, path):
        """Walk a dotted path like 'channels.0.name' through dicts/lists."""
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    raise KeyError("unknown path segment: '" + part + "'")
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                except ValueError:
                    raise KeyError("list index must be an integer, got '" + part + "'")
                if idx < 0 or idx >= len(current):
                    raise KeyError(
                        "list index "
                        + str(idx)
                        + " out of range (length "
                        + str(len(current))
                        + ")"
                    )
                current = current[idx]
            else:
                raise KeyError(
                    "cannot traverse into "
                    + type(current).__name__
                    + " at '"
                    + part
                    + "'"
                )
        return current

    def _state(args):
        throttle_ms = int(args.get("throttle_ms", 500))
        field = args.get("field")
        # When a field is requested, only build the top-level section it
        # references so we skip hundreds of API calls on the MIDI thread.
        sections = None
        if field is not None:
            top_key = field.split(".")[0]
            sections = {top_key}
        snap = backend.snapshot(throttle_ms=throttle_ms, sections=sections)
        if field is None:
            return {"state": snap}
        value = _resolve_dotted_path(snap, field)
        return {"field": field, "value": value}

    # --- Mixer ----------------------------------------------------------

    def _mixer_list(args):
        return {"tracks": backend.mixer_list_tracks()}

    def _mixer_volume_get(args):
        track = int(args["track"])
        vol = backend.mixer_get_track_volume(track)
        return {"track": track, "volume": round(vol, 4)}

    def _mixer_volume_set(args):
        track = int(args["track"])
        value = float(args["value"])
        backend.mixer_set_track_volume(track, value)
        return {"track": track, "volume": round(value, 4)}

    def _mixer_pan_get(args):
        track = int(args["track"])
        pan = backend.mixer_get_track_pan(track)
        return {"track": track, "pan": round(pan, 4)}

    def _mixer_pan_set(args):
        track = int(args["track"])
        value = float(args["value"])
        backend.mixer_set_track_pan(track, value)
        return {"track": track, "pan": round(value, 4)}

    def _mixer_name_get(args):
        track = int(args["track"])
        name = backend.mixer_get_track_name(track)
        return {"track": track, "name": name}

    def _mixer_name_set(args):
        track = int(args["track"])
        name = str(args["name"])
        backend.mixer_set_track_name(track, name)
        return {"track": track, "name": name}

    def _mixer_mute(args):
        track = int(args["track"])
        was_muted = backend.mixer_is_track_muted(track)
        new_value = 0 if was_muted else 1
        backend.mixer_mute_track(track, new_value)
        return {"track": track, "mute": bool(new_value)}

    def _mixer_solo(args):
        track = int(args["track"])
        backend.mixer_solo_track(track)
        solo = backend.mixer_is_track_solo(track)
        return {"track": track, "solo": solo}

    def _mixer_arm(args):
        track = int(args["track"])
        arm = bool(args.get("on", True))
        backend.mixer_arm_track(track, arm)
        return {"track": track, "armed": arm}

    def _mixer_route_set(args):
        from_idx = int(args["from"])
        to_idx = int(args["to"])
        enabled = bool(args.get("on", True))
        backend.mixer_set_route_to(from_idx, to_idx, enabled)
        return {"from": from_idx, "to": to_idx, "on": enabled}

    def _mixer_link_to_channel(args):
        track = int(args["track"])
        channel = int(args["channel"])
        backend.mixer_link_to_channel(track, channel)
        return {"track": track, "channel": channel}

    # --- Plugin ---------------------------------------------------------

    def _plugin_list(args):
        channel = int(args["channel"])
        found = []
        # Native plugin (slot -1)
        try:
            name = backend.plugin_get_name(channel, -1)
            if name:
                found.append({"slot": -1, "name": name})
        except Exception:
            pass
        # Effect slots are allocated contiguously; once two consecutive slots
        # are empty we can stop probing instead of hammering the FL API ten
        # times per request on the MIDI thread.
        empty_streak = 0
        for slot in range(10):
            try:
                name = backend.plugin_get_name(channel, slot)
            except Exception:
                name = None
            if name:
                found.append({"slot": slot, "name": name})
                empty_streak = 0
            else:
                empty_streak += 1
                if empty_streak >= 2:
                    break
        return {"channel": channel, "plugins": found}

    def _require_plugin(channel, slot):
        """Return the plugin name or raise NOT_FOUND."""
        try:
            name = backend.plugin_get_name(channel, slot)
        except Exception:
            name = None
        if not name:
            raise _HandlerError(
                CODE_NOT_FOUND,
                f"no plugin at channel={channel} slot={slot}",
            )
        return name

    # ``(channel, slot) -> (plugin_name, {param_name: index})``.  Heavy synths
    # like Sytrus / Harmor expose hundreds of params, and resolving by
    # ``param_name`` walks them all on the MIDI thread.  Caching keyed on the
    # plugin name means a follow-up ``set`` on the same plugin is O(1); a
    # plugin swap (different name in the same slot) invalidates automatically.
    _param_name_cache = {}

    def _resolve_param_index(channel, slot, args):
        """Return the integer parameter index from ``param`` or ``param_name``."""
        if "param" in args:
            return int(args["param"])
        param_name = str(args["param_name"])

        cache_key = (channel, slot)
        try:
            current_plugin = backend.plugin_get_name(channel, slot)
        except Exception:
            current_plugin = None
        cached = _param_name_cache.get(cache_key)
        if cached is not None and cached[0] == current_plugin:
            idx = cached[1].get(param_name)
            if idx is not None:
                return idx

        try:
            count = backend.plugin_get_param_count(channel, slot)
        except Exception:
            raise _HandlerError(
                CODE_NOT_FOUND,
                f"parameter named {param_name!r} not found on channel={channel} slot={slot}",
            )
        name_to_index = {}
        match_index = None
        for i in range(count):
            try:
                fl_name = backend.plugin_get_param_name(i, channel, slot)
            except Exception:
                continue
            if fl_name:
                name_to_index[fl_name] = i
                if match_index is None and fl_name == param_name:
                    match_index = i
        _param_name_cache[cache_key] = (current_plugin, name_to_index)
        if match_index is not None:
            return match_index
        raise _HandlerError(
            CODE_NOT_FOUND,
            f"parameter named {param_name!r} not found on channel={channel} slot={slot}",
        )

    def _plugin_params(args):
        channel = int(args["channel"])
        slot = int(args.get("slot", -1))
        offset = int(args.get("offset", 0))
        limit_raw = args.get("limit")
        plugin_name = _require_plugin(channel, slot)
        try:
            param_count = backend.plugin_get_param_count(channel, slot)
        except Exception:
            param_count = 0
        # Heavy plugins (Sytrus / Harmor) expose hundreds of params and
        # both per-param API calls *and* the resulting SysEx payload add
        # up. Cap the response size so the round-trip stays under the
        # CLI's timeout. Callers can paginate via offset+limit.
        default_limit = 64
        limit = int(limit_raw) if limit_raw is not None else default_limit
        if limit < 0:
            limit = 0
        end = min(param_count, max(0, offset) + limit) if limit else param_count
        params = []
        for i in range(max(0, offset), end):
            entry = {"index": i, "name": None, "value": None, "display": None}
            try:
                entry["name"] = backend.plugin_get_param_name(i, channel, slot)
                entry["value"] = round(
                    backend.plugin_get_param_value(i, channel, slot),
                    6,
                )
                entry["display"] = backend.plugin_get_param_value_string(
                    i,
                    channel,
                    slot,
                )
            except Exception:
                pass
            params.append(entry)
        return {
            "plugin_name": plugin_name,
            "param_count": param_count,
            "offset": offset,
            "limit": limit,
            "returned": len(params),
            "params": params,
            "channel": channel,
            "slot": slot,
        }

    def _plugin_param_get(args):
        channel = int(args["channel"])
        slot = int(args.get("slot", -1))
        plugin_name = _require_plugin(channel, slot)
        param = _resolve_param_index(channel, slot, args)
        try:
            name = backend.plugin_get_param_name(param, channel, slot)
            value = backend.plugin_get_param_value(param, channel, slot)
            display = backend.plugin_get_param_value_string(param, channel, slot)
        except Exception:
            raise _HandlerError(
                CODE_NOT_FOUND,
                f"parameter {param} not found on channel={channel} slot={slot}",
            )
        return {
            "plugin_name": plugin_name,
            "channel": channel,
            "slot": slot,
            "param": param,
            "name": name,
            "value": round(value, 6),
            "display": display,
        }

    def _plugin_param_set(args):
        channel = int(args["channel"])
        slot = int(args.get("slot", -1))
        value = float(args["value"])
        plugin_name = _require_plugin(channel, slot)
        param = _resolve_param_index(channel, slot, args)
        try:
            backend.plugin_set_param_value(value, param, channel, slot)
        except Exception as exc:
            raise _HandlerError(
                CODE_INTERNAL,
                f"failed to set parameter {param}: {exc}",
            )
        try:
            name = backend.plugin_get_param_name(param, channel, slot)
            readback = backend.plugin_get_param_value(param, channel, slot)
            display = backend.plugin_get_param_value_string(param, channel, slot)
        except Exception:
            name = None
            readback = value
            display = None
        return {
            "plugin_name": plugin_name,
            "channel": channel,
            "slot": slot,
            "param": param,
            "name": name,
            "value": round(readback, 6),
            "display": display,
        }

    dispatcher.register("plugin_list", _plugin_list)
    dispatcher.register("plugin_params", _plugin_params)
    dispatcher.register("plugin_param_get", _plugin_param_get)
    dispatcher.register("plugin_param_set", _plugin_param_set)

    # --- Transport position / loop / undo --------------------------------

    _BEATS_FALLBACK = "__beats_from_absticks__"
    _POSITION_MODES = {}
    for _mode_name, _attr_name in (
        ("ticks", "SONGLENGTH_TICKS"),
        ("ms", "SONGLENGTH_MS"),
        ("abs-ticks", "SONGLENGTH_ABSTICKS"),
    ):
        _mode_val = getattr(midi, _attr_name, None)
        if _mode_val is not None:
            _POSITION_MODES[_mode_name] = _mode_val
    _beats_const = getattr(midi, "SONGLENGTH_BEATS", None)
    if _beats_const is not None:
        _POSITION_MODES["beats"] = _beats_const
    elif "abs-ticks" in _POSITION_MODES:
        _POSITION_MODES["beats"] = _BEATS_FALLBACK

    def _resolve_position_mode(args):
        mode_name = str(args.get("mode", "beats"))
        fl_mode = _POSITION_MODES.get(mode_name)
        if fl_mode is None:
            raise _HandlerError(
                CODE_INVALID_ARGUMENT,
                "unknown position mode: " + mode_name,
            )
        return mode_name, fl_mode

    def _transport_position_get(args):
        mode_name, fl_mode = _resolve_position_mode(args)
        if fl_mode == _BEATS_FALLBACK:
            ppq = general.getRecPPQ() or 0
            if not ppq:
                raise _HandlerError(CODE_INTERNAL, "PPQ unavailable for beats fallback")
            abs_ticks = backend.get_song_position(_POSITION_MODES["abs-ticks"])
            position = abs_ticks / ppq
        else:
            position = backend.get_song_position(fl_mode)
        return {"position": position, "mode": mode_name}

    def _transport_position_set(args):
        mode_name, fl_mode = _resolve_position_mode(args)
        position = float(args["position"])
        if fl_mode == _BEATS_FALLBACK:
            ppq = general.getRecPPQ() or 0
            if not ppq:
                raise _HandlerError(CODE_INTERNAL, "PPQ unavailable for beats fallback")
            backend.set_song_position(position * ppq, _POSITION_MODES["abs-ticks"])
        else:
            backend.set_song_position(position, fl_mode)
        return {"position": position, "mode": mode_name}

    def _transport_loop_get(args):
        mode = backend.get_loop_mode()
        return {"loop_mode": mode}

    def _transport_loop_toggle(args):
        backend.toggle_loop_mode()
        mode = backend.get_loop_mode()
        return {"loop_mode": mode}

    def _undo(args):
        backend.undo()
        return {}

    def _redo(args):
        backend.redo()
        return {}

    def _undo_history(args):
        count = backend.get_undo_history_count()
        last = backend.get_undo_history_last()
        return {"count": count, "last": last}

    dispatcher.register("transport_position_get", _transport_position_get)
    dispatcher.register("transport_position_set", _transport_position_set)
    dispatcher.register("transport_loop_get", _transport_loop_get)
    dispatcher.register("transport_loop_toggle", _transport_loop_toggle)
    dispatcher.register("undo", _undo)
    dispatcher.register("redo", _redo)
    dispatcher.register("undo_history", _undo_history)

    dispatcher.register("play", _play)
    dispatcher.register("stop", _stop)
    dispatcher.register("record", _record)
    dispatcher.register("new_project", _new_project)
    dispatcher.register("new_pattern", _new_pattern)
    dispatcher.register("select_pattern", _select_pattern)
    dispatcher.register("name_pattern", _name_pattern)
    dispatcher.register("channel_rack_focus", _channel_rack_focus)
    dispatcher.register("focus_channel_editor", _focus_channel_editor)
    dispatcher.register("name_channel", _name_channel)
    dispatcher.register("select_channel", _select_channel)
    dispatcher.register("tempo", _tempo)
    dispatcher.register("set_step", _set_step)
    dispatcher.register("step_melody", _step_melody)
    dispatcher.register("state", _state)
    dispatcher.register("mixer_list", _mixer_list)
    dispatcher.register("mixer_volume_get", _mixer_volume_get)
    dispatcher.register("mixer_volume_set", _mixer_volume_set)
    dispatcher.register("mixer_pan_get", _mixer_pan_get)
    dispatcher.register("mixer_pan_set", _mixer_pan_set)
    dispatcher.register("mixer_name_get", _mixer_name_get)
    dispatcher.register("mixer_name_set", _mixer_name_set)
    dispatcher.register("mixer_mute", _mixer_mute)
    dispatcher.register("mixer_solo", _mixer_solo)
    dispatcher.register("mixer_arm", _mixer_arm)
    dispatcher.register("mixer_route_set", _mixer_route_set)
    dispatcher.register("mixer_link_to_channel", _mixer_link_to_channel)
    return dispatcher


_BACKEND = FLStudioBackend()
_V2_DISPATCH = _build_v2_dispatcher(_BACKEND)


# === FL Studio entry points =================================================


def OnInit():
    print("[flcli] controller initialised (protocol v2)")


def _handle_sysex_event(event, source):
    """Decode the SysEx frame, dispatch, reply.

    Some FL Studio versions deliver ``event.sysex`` populated only via
    ``OnMidiIn`` (not ``OnSysEx``), so both callbacks funnel through
    here. ``source`` is just a label for log lines.
    """
    raw_sysex = getattr(event, "sysex", None)
    if raw_sysex is None:
        return False
    try:
        raw = bytes(raw_sysex)
    except Exception as exc:
        print("[flcli] " + source + ": cannot read sysex:", exc)
        return False
    try:
        request_id, payload = _v2_decode_frame(raw)
    except Exception as exc:
        print("[flcli] " + source + ": malformed frame:", exc)
        return True
    try:
        request = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        print("[flcli] " + source + ": bad JSON payload:", exc)
        return True
    cmd = request.get("cmd")
    if not cmd:
        return True
    args = request.get("args") or {}
    if DEBUG:
        print("[flcli] " + source + ": cmd=" + str(cmd) + " rid=" + str(request_id))
    response = _V2_DISPATCH.dispatch(cmd, args)
    response["request_id"] = request_id
    response["command"] = cmd
    try:
        reply_payload = json.dumps(response).encode("utf-8")
        reply_frame = _v2_encode_frame(request_id, reply_payload)
        device.midiOutSysex(reply_frame)
        if DEBUG:
            print(
                "[flcli] "
                + source
                + ": reply sent "
                + str(len(reply_frame))
                + " bytes via port="
                + str(device.getPortNumber())
            )
    except Exception as exc:
        print("[flcli] " + source + ": reply failed:", exc)
    try:
        event.handled = True
    except Exception:
        pass
    return True


def OnMidiIn(event):
    _handle_sysex_event(event, "OnMidiIn")


def OnSysEx(event):
    _handle_sysex_event(event, "OnSysEx")
