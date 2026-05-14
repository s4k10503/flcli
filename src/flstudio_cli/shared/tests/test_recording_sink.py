"""Tests for the RecordingCommandTransport JSONL-tracing wrapper."""

from __future__ import annotations

import io
import json

from conftest import FakeCommandTransport

from flstudio_cli.shared.infrastructure.protocol import v2 as V2
from flstudio_cli.shared.infrastructure.transport.recording_sink import (
    RecordingCommandTransport,
)


def _make_frame(request_id: int = 1, cmd: str = "tempo") -> bytes:
    payload = V2.build_command(cmd, {"bpm": 120})
    return V2.encode_frame(V2.SysExFrame(request_id=request_id, payload=payload))


class TestRecordingCommandTransportDelegation:
    def test_send_frame_delegates_to_inner_transport(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        frame = _make_frame()
        rec.send_frame(frame)
        assert inner.frames == [frame]

    def test_close_delegates_to_inner_sink(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        rec.close()
        assert inner.closed is True

    def test_multiple_frames_all_delegated(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        frames = [_make_frame(request_id=i) for i in range(3)]
        for f in frames:
            rec.send_frame(f)
        assert inner.frames == frames


class TestRecordingCommandTransportTraceFormat:
    def test_trace_contains_one_line_per_send(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        rec.send_frame(_make_frame(1))
        rec.send_frame(_make_frame(2))
        trace.seek(0)
        lines = [x for x in trace.read().splitlines() if x.strip()]
        assert len(lines) == 2

    def test_trace_line_has_required_fields(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        frame = _make_frame()
        rec.send_frame(frame)
        trace.seek(0)
        entry = json.loads(trace.readline())
        assert entry["dir"] == "out"
        assert entry["type"] == "sysex"
        assert entry["frame_hex"] == frame.hex()
        assert "t" in entry

    def test_frame_hex_is_lowercase_hex(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        frame = _make_frame()
        rec.send_frame(frame)
        trace.seek(0)
        entry = json.loads(trace.readline())
        hex_str = entry["frame_hex"]
        assert hex_str == hex_str.lower()
        assert bytes.fromhex(hex_str) == frame


class TestRecordingCommandTransportTimestamps:
    def test_timestamps_are_monotonically_non_decreasing(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        for i in range(5):
            rec.send_frame(_make_frame(request_id=i))
        trace.seek(0)
        timestamps = []
        for line in trace:
            line = line.strip()
            if line:
                timestamps.append(json.loads(line)["t"])
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_first_timestamp_is_non_negative(self) -> None:
        inner = FakeCommandTransport()
        trace = io.StringIO()
        rec = RecordingCommandTransport(inner, trace)
        rec.send_frame(_make_frame())
        trace.seek(0)
        entry = json.loads(trace.readline())
        assert entry["t"] >= 0.0
