"""Tests for the ReplayCommandTransport, ReplayReturnPort, and load_trace helpers."""

from __future__ import annotations

import io
import json

import pytest
from conftest import FakeCommandTransport

from flstudio_cli.shared.infrastructure.protocol import v2 as V2
from flstudio_cli.shared.infrastructure.transport.recording_sink import (
    RecordingCommandTransport,
)
from flstudio_cli.shared.infrastructure.transport.replay_sink import (
    ReplayCommandTransport,
    ReplayMismatchError,
    ReplayReturnPort,
    load_trace,
)


def _make_frame(request_id: int = 1, cmd: str = "tempo") -> bytes:
    payload = V2.build_command(cmd, {"bpm": 120})
    return V2.encode_frame(V2.SysExFrame(request_id=request_id, payload=payload))


def _make_response_frame(request_id: int, command: str = "tempo") -> bytes:
    envelope = {
        "request_id": request_id,
        "ok": True,
        "command": command,
        "result": {"bpm": 120},
        "error": None,
    }
    payload = json.dumps(envelope).encode("utf-8")
    return V2.encode_frame(V2.SysExFrame(request_id=request_id, payload=payload))


class TestReplayCommandTransportMatch:
    def test_matching_frame_succeeds(self) -> None:
        frame = _make_frame(1)
        sink = ReplayCommandTransport([{"frame_hex": frame.hex()}])
        sink.send_frame(frame)  # should not raise

    def test_multiple_matching_frames_succeed(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        events = [{"frame_hex": f.hex()} for f in frames]
        sink = ReplayCommandTransport(events)
        for f in frames:
            sink.send_frame(f)  # should not raise

    def test_close_is_noop(self) -> None:
        sink = ReplayCommandTransport([])
        sink.close()  # should not raise


class TestReplayCommandTransportMismatch:
    def test_mismatched_frame_raises_replay_mismatch_error(self) -> None:
        frame_a = _make_frame(1, cmd="tempo")
        frame_b = _make_frame(2, cmd="play")
        sink = ReplayCommandTransport([{"frame_hex": frame_a.hex()}])
        with pytest.raises(ReplayMismatchError) as exc_info:
            sink.send_frame(frame_b)
        assert exc_info.value.expected_hex == frame_a.hex()
        assert exc_info.value.actual_hex == frame_b.hex()

    def test_extra_send_after_trace_exhausted_raises(self) -> None:
        frame = _make_frame(1)
        sink = ReplayCommandTransport([{"frame_hex": frame.hex()}])
        sink.send_frame(frame)
        with pytest.raises(ReplayMismatchError) as exc_info:
            sink.send_frame(frame)
        assert exc_info.value.expected_hex == "(end of trace)"

    def test_send_on_empty_trace_raises(self) -> None:
        sink = ReplayCommandTransport([])
        with pytest.raises(ReplayMismatchError):
            sink.send_frame(_make_frame())


class TestReplayReturnPort:
    def test_feed_next_delivers_response_to_pending_entry(self) -> None:
        resp_frame = _make_response_frame(7)
        port = ReplayReturnPort([{"frame_hex": resp_frame.hex()}])
        entry = port.register(7)
        assert port.feed_next() is True
        result = entry.wait(timeout_seconds=0.1)
        assert result["ok"] is True
        assert result["request_id"] == 7

    def test_feed_next_returns_false_when_exhausted(self) -> None:
        port = ReplayReturnPort([])
        assert port.feed_next() is False

    def test_multiple_responses_feed_in_order(self) -> None:
        frames = [_make_response_frame(i) for i in range(3)]
        events = [{"frame_hex": f.hex()} for f in frames]
        port = ReplayReturnPort(events)
        entries = [port.register(i) for i in range(3)]
        for _ in range(3):
            port.feed_next()
        for i, entry in enumerate(entries):
            result = entry.wait(timeout_seconds=0.1)
            assert result["request_id"] == i


class TestLoadTrace:
    def test_splits_out_and_in_events(self) -> None:
        lines = [
            json.dumps({"t": 0.0, "dir": "out", "type": "sysex", "frame_hex": "aa"}),
            json.dumps({"t": 0.1, "dir": "in", "type": "sysex", "frame_hex": "bb"}),
            json.dumps({"t": 0.2, "dir": "out", "type": "sysex", "frame_hex": "cc"}),
        ]
        trace = io.StringIO("\n".join(lines) + "\n")
        out_events, in_events = load_trace(trace)
        assert len(out_events) == 2
        assert len(in_events) == 1
        assert out_events[0]["frame_hex"] == "aa"
        assert out_events[1]["frame_hex"] == "cc"
        assert in_events[0]["frame_hex"] == "bb"

    def test_skips_blank_lines(self) -> None:
        lines = [
            json.dumps({"t": 0.0, "dir": "out", "type": "sysex", "frame_hex": "aa"}),
            "",
            "   ",
            json.dumps({"t": 0.1, "dir": "in", "type": "sysex", "frame_hex": "bb"}),
        ]
        trace = io.StringIO("\n".join(lines) + "\n")
        out_events, in_events = load_trace(trace)
        assert len(out_events) == 1
        assert len(in_events) == 1

    def test_empty_trace_returns_empty_lists(self) -> None:
        trace = io.StringIO("")
        out_events, in_events = load_trace(trace)
        assert out_events == []
        assert in_events == []


class TestRoundTrip:
    def test_recording_trace_can_be_replayed_by_replay_sink(self) -> None:
        # Record a session.
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        frames = [_make_frame(request_id=i) for i in range(3)]
        for f in frames:
            rec.send_frame(f)

        # Load the trace.
        trace.seek(0)
        out_events, in_events = load_trace(trace)
        assert len(out_events) == 3
        assert len(in_events) == 0

        # Replay with the same frames -- should not raise.
        sink = ReplayCommandTransport(out_events)
        for f in frames:
            sink.send_frame(f)
