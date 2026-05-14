"""Tests for the MidoCommandTransport SysEx wiring.

We replace ``mido.open_output`` with a fake port that records every
``Message`` it receives, then drive the sink through ``send_frame``.
"""

from dataclasses import dataclass, field

import mido
import pytest

from flstudio_cli.shared.infrastructure.transport.midi_sink import (
    MidoCommandTransport,
    resolve_port,
)


@dataclass
class FakeMidoPort:
    sent: list[mido.Message] = field(default_factory=list)
    closed: bool = False

    def send(self, msg: mido.Message) -> None:
        self.sent.append(msg)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_port(monkeypatch):
    port = FakeMidoPort()
    monkeypatch.setattr(mido, "open_output", lambda name: port)
    monkeypatch.setattr(mido, "get_output_names", lambda: ["flcli virtual"])
    return port


class TestMidoCommandTransportSendFrame:
    def test_given_framed_bytes_when_send_frame_then_strips_bookends(self, fake_port):
        sink = MidoCommandTransport("flcli virtual")

        frame = bytes([0xF0, 0x7D, 0x02, 0x00, 0x00, 0x00, 0x01, 0x12, 0x34, 0xF7])
        sink.send_frame(frame)

        sent = fake_port.sent
        assert len(sent) == 1
        assert sent[0].type == "sysex"
        assert tuple(sent[0].data) == (0x7D, 0x02, 0x00, 0x00, 0x00, 0x01, 0x12, 0x34)

    def test_given_missing_start_byte_when_send_frame_then_raises(self, fake_port):
        sink = MidoCommandTransport("flcli virtual")
        with pytest.raises(ValueError, match="0xF0"):
            sink.send_frame(b"\x7d\x02\xf7")


class TestResolvePort:
    def test_given_substring_when_resolve_port_then_returns_full_name(self, fake_port):
        assert resolve_port("flcli", default_name="flcli") == "flcli virtual"

    def test_given_unknown_name_when_resolve_port_then_raises(self, fake_port):
        with pytest.raises(RuntimeError, match="not found"):
            resolve_port("does-not-exist", default_name="does-not-exist")
