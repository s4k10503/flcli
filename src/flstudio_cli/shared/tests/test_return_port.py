"""Tests for the ``ReturnPort`` pending-request table."""

from __future__ import annotations

import json
import threading
import time

import pytest

from flstudio_cli.shared.infrastructure.protocol import v2 as V2
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort


class TestRegisterAndForget:
    def test_given_new_request_id_when_register_then_returns_entry(self) -> None:
        port = FakeReturnPort()
        entry = port.register(42)
        assert entry.event.is_set() is False
        assert entry.response is None

    def test_given_duplicate_request_id_when_register_then_raises(self) -> None:
        port = FakeReturnPort()
        port.register(42)
        with pytest.raises(RuntimeError, match="duplicate request_id"):
            port.register(42)

    def test_given_forget_when_register_same_id_then_succeeds(self) -> None:
        port = FakeReturnPort()
        port.register(42)
        port.forget(42)
        port.register(42)  # should not raise


class TestDeliver:
    def test_given_matching_request_id_when_deliver_then_entry_resolves(self) -> None:
        port = FakeReturnPort()
        entry = port.register(7)
        envelope = {
            "request_id": 7,
            "ok": True,
            "command": "tempo",
            "result": {"bpm": 140.5},
            "error": None,
        }
        port.deliver(envelope)
        result = entry.wait(timeout_seconds=0.1)
        assert result == envelope

    def test_given_unknown_request_id_when_deliver_then_does_not_crash(self) -> None:
        port = FakeReturnPort()
        port.deliver(
            {"request_id": 99, "ok": True, "command": "x", "result": {}, "error": None}
        )
        # No assertion needed — the test passes if this doesn't raise.

    def test_given_malformed_frame_when_deliver_then_silently_dropped(self) -> None:
        port = FakeReturnPort()
        port.register(1)
        # Hand-roll a bad frame: wrong vendor.
        bad = bytes([0xF0, 0x41, 0x02, 0x00, 0x00, 0x00, 0x01, 0xF7])
        port.deliver_frame(bad)  # should not raise
        # The pending entry is still unresolved.
        assert port._pending[1].event.is_set() is False


class TestClose:
    def test_given_pending_entry_when_close_then_wait_raises_connection_reset(
        self,
    ) -> None:
        port = FakeReturnPort()
        entry = port.register(1)
        port.close()
        with pytest.raises(ConnectionResetError):
            entry.wait(timeout_seconds=0.1)

    def test_given_closed_port_when_register_then_raises(self) -> None:
        port = FakeReturnPort()
        port.close()
        with pytest.raises(ConnectionResetError):
            port.register(1)

    def test_given_close_twice_when_no_crash(self) -> None:
        port = FakeReturnPort()
        port.close()
        port.close()  # idempotent


class TestBackgroundDelivery:
    """Exercise the thread-safety guarantees with a real background thread."""

    def test_given_callback_thread_when_deliver_then_waiter_unblocks(self) -> None:
        port = FakeReturnPort()
        entry = port.register(42)

        def deliver_after_delay() -> None:
            time.sleep(0.01)
            port.deliver(
                {
                    "request_id": 42,
                    "ok": True,
                    "command": "tempo",
                    "result": {"bpm": 128.0},
                    "error": None,
                }
            )

        thread = threading.Thread(target=deliver_after_delay)
        thread.start()
        try:
            result = entry.wait(timeout_seconds=1.0)
        finally:
            thread.join()
        assert result["result"]["bpm"] == 128.0

    def test_given_no_delivery_when_wait_then_timeout_error(self) -> None:
        port = FakeReturnPort()
        entry = port.register(1)
        with pytest.raises(TimeoutError, match="within"):
            entry.wait(timeout_seconds=0.02)


class TestDeliverFrameDirectly:
    """Exercise the frame-level receive path that ``MidoReturnPort`` calls."""

    def test_given_encoded_frame_when_deliver_frame_then_entry_resolves(
        self,
    ) -> None:
        port = FakeReturnPort()
        entry = port.register(13)
        envelope = {
            "request_id": 13,
            "ok": True,
            "command": "play",
            "result": {},
            "error": None,
        }
        raw = V2.encode_frame(
            V2.SysExFrame(request_id=13, payload=json.dumps(envelope).encode("utf-8"))
        )
        port.deliver_frame(raw)
        assert entry.wait(timeout_seconds=0.1) == envelope
