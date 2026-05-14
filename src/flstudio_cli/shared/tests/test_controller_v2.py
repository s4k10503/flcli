"""Tests for the protocol v2 surface of :class:`DawController`."""

from __future__ import annotations

import threading

import pytest

from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC
from flstudio_cli.shared.infrastructure.protocol import v2 as V2
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort


class TestSendAndWaitGuards:
    def test_given_outside_context_manager_when_send_and_wait_then_raises(
        self,
        fake_transport,
    ) -> None:
        controller = DawController(
            fake_transport, FakeReturnPort(), PRODUCTION_FRAME_CODEC
        )
        with pytest.raises(RuntimeError, match="context manager"):
            controller.send_and_wait("tempo", {"bpm": 120})


class TestSendAndWaitRoundTrip:
    def test_given_response_delivered_then_returns_envelope(
        self, fake_transport
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            response_envelope = {
                "request_id": 1,
                "ok": True,
                "command": "tempo",
                "result": {"bpm": 140.5},
                "error": None,
            }

            def deliver() -> None:
                return_port.deliver(response_envelope)

            timer = threading.Timer(0.01, deliver)
            timer.start()
            response = controller.send_and_wait(
                "tempo",
                {"bpm": 140.5},
                timeout_ms=1000,
            )
            timer.join()

            assert response == response_envelope

        assert len(fake_transport.frames) == 1

    def test_given_no_response_when_timeout_elapses_then_raises(
        self, fake_transport
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport, return_port, PRODUCTION_FRAME_CODEC
        ) as controller:
            with pytest.raises(TimeoutError):
                controller.send_and_wait("tempo", {"bpm": 120}, timeout_ms=20)

    def test_given_multiple_requests_when_each_delivered_then_correlated_by_id(
        self, fake_transport
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport, return_port, PRODUCTION_FRAME_CODEC
        ) as controller:

            def deliver(request_id: int, bpm: float) -> None:
                return_port.deliver(
                    {
                        "request_id": request_id,
                        "ok": True,
                        "command": "tempo",
                        "result": {"bpm": bpm},
                        "error": None,
                    }
                )

            timer1 = threading.Timer(0.01, deliver, args=(1, 100.0))
            timer1.start()
            r1 = controller.send_and_wait("tempo", {"bpm": 100.0}, timeout_ms=1000)
            timer1.join()

            timer2 = threading.Timer(0.01, deliver, args=(2, 200.0))
            timer2.start()
            r2 = controller.send_and_wait("tempo", {"bpm": 200.0}, timeout_ms=1000)
            timer2.join()

            assert r1["result"]["bpm"] == 100.0
            assert r2["result"]["bpm"] == 200.0

    def test_given_close_while_waiting_then_connection_reset(
        self, fake_transport
    ) -> None:
        return_port = FakeReturnPort()
        controller = DawController(fake_transport, return_port, PRODUCTION_FRAME_CODEC)
        with controller:
            results: dict[str, BaseException | None] = {"error": None}

            def worker() -> None:
                try:
                    controller.send_and_wait("tempo", {"bpm": 1}, timeout_ms=5000)
                except BaseException as exc:
                    results["error"] = exc

            thread = threading.Thread(target=worker)
            thread.start()
            threading.Event().wait(0.02)
            return_port.close()
            thread.join(timeout=1.0)

            assert isinstance(results["error"], ConnectionResetError)


class TestRequestIdCounter:
    def test_given_monotonic_when_allocated_then_starts_at_one_and_skips_zero(
        self, fake_transport
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport, return_port, PRODUCTION_FRAME_CODEC
        ) as controller:
            assert controller._next_request_id() == 1
            assert controller._next_request_id() == 2
            assert controller._next_request_id() == 3
            controller._request_id_counter = V2.REQUEST_ID_MAX
            assert controller._next_request_id() == 1
