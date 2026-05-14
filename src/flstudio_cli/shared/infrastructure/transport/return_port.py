"""Infrastructure adapter: return-path MIDI port for protocol v2.

The CLI opens the device script's second virtual MIDI port (``flcli-rx``)
as an *input* so the device script can push SysEx response envelopes
back to the CLI in real time. ``mido`` delivers incoming messages on an
rtmidi background thread via a callback, so the response plumbing is
necessarily concurrent.

Design
------

- Each in-flight request owns its own :class:`threading.Event` (not a
  shared condition variable). The callback thread looks up the pending
  entry under ``_lock``, stamps the response onto it, and sets the
  event. Waiters use ``event.wait(timeout_s)`` with no coordination
  between each other.
- :class:`ReturnPort` is a thin abstract base so tests can substitute
  :class:`FakeReturnPort` without opening a real MIDI input port. The
  ``MidoReturnPort`` subclass is the only one that imports ``mido``.
- ``close()`` fires every pending event with a :class:`ConnectionResetError`
  so any in-flight ``send_and_wait`` unblocks instead of hanging forever
  when ``DawController`` exits.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from flstudio_cli.shared.infrastructure.protocol import v2 as V2


@dataclass
class _PendingEntry:
    """One in-flight ``send_and_wait`` request.

    The **sender thread** blocks on ``event``; the **receiver thread**
    (rtmidi callback or test harness) calls :meth:`resolve` / :meth:`fail`
    to stamp the result and unblock the sender.
    """

    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    error: BaseException | None = None

    def resolve(self, response: dict[str, Any]) -> None:
        self.response = response
        self.event.set()

    def fail(self, exc: BaseException) -> None:
        self.error = exc
        self.event.set()

    def wait(self, timeout_seconds: float) -> dict[str, Any]:
        acquired = self.event.wait(timeout_seconds)
        if not acquired:
            raise TimeoutError(
                f"no protocol v2 response received within {timeout_seconds:.3f}s"
            )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class ReturnPort:
    """Pending-request table shared between the sender and the receiver thread.

    Subclasses plug in the transport: :class:`MidoReturnPort` opens a
    real ``mido`` input; :class:`FakeReturnPort` lets tests feed frames
    directly via :meth:`deliver`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[int, _PendingEntry] = {}
        self._closed = False

    # --- Sender-side API (called from the CLI thread) ---------------------

    def register(self, request_id: int) -> _PendingEntry:
        with self._lock:
            if self._closed:
                raise ConnectionResetError("return port is closed")
            if request_id in self._pending:
                raise RuntimeError(f"duplicate request_id {request_id} already pending")
            entry = _PendingEntry()
            self._pending[request_id] = entry
            return entry

    def forget(self, request_id: int) -> None:
        with self._lock:
            self._pending.pop(request_id, None)

    def close(self) -> None:
        """Fail every pending request and release any receiver resources.

        Idempotent: calling ``close()`` twice is a no-op on the second
        call. Subclasses override :meth:`_close_transport` to release
        their own resources (real MIDI input port, etc.).
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()
        for entry in pending:
            entry.fail(ConnectionResetError("return port closed while waiting"))
        self._close_transport()

    def _close_transport(self) -> None:
        """Hook for subclasses to release transport-level resources."""

    # --- Receiver-side API (called from the rtmidi background thread) ----

    def deliver_frame(self, raw_frame: bytes) -> None:
        """Decode an incoming ``F0..F7`` frame and resolve the pending entry.

        Silently drops frames that don't match a known ``request_id``
        (late responses after ``forget``) or are malformed. Never raises
        — the caller is a MIDI callback on a background thread and a
        raise there would tear down the entire I/O loop.
        """
        try:
            frame = V2.decode_frame(raw_frame)
            envelope = V2.parse_response(frame.payload)
        except (V2.MalformedFrame, V2.ProtocolMismatch, json.JSONDecodeError):
            return
        request_id = envelope.get("request_id")
        if not isinstance(request_id, int):
            request_id = frame.request_id
        with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is not None:
            entry.resolve(envelope)


class MidoReturnPort(ReturnPort):
    """Concrete :class:`ReturnPort` backed by a ``mido`` input port.

    Threading model
    ---------------
    ``mido.open_input(..., callback=...)`` spawns an **rtmidi background
    thread** that invokes :meth:`_on_message` for every incoming MIDI
    message.  The callback filters for SysEx, reconstructs the
    ``F0..F7`` frame (``mido`` strips the bookends), and hands it to
    :meth:`deliver_frame` which resolves the matching
    :class:`_PendingEntry` under ``_lock``.

    Because the callback runs on a foreign thread, :meth:`_on_message`
    never raises -- any decode error is silently swallowed so the rtmidi
    loop stays alive.
    """

    def __init__(self, port_name: str) -> None:
        super().__init__()
        # Import locally so the pure test path never triggers a mido dependency.
        import mido

        self._port = mido.open_input(port_name, callback=self._on_message)

    def _on_message(self, message: Any) -> None:
        if getattr(message, "type", None) != "sysex":
            return
        # mido's sysex Message.data excludes the F0/F7 bookends, but
        # ``decode_frame`` expects them. Rebuild the full frame.
        raw = b"\xf0" + bytes(message.data) + b"\xf7"
        self.deliver_frame(raw)

    def _close_transport(self) -> None:
        try:
            self._port.close()
        except Exception:
            # Real MIDI ports sometimes raise on close in exotic edge
            # cases; swallow so shutdown stays idempotent.
            pass


class FakeReturnPort(ReturnPort):
    """Test double: accept frames fed manually via :meth:`deliver`.

    Threading model
    ---------------
    Unlike :class:`MidoReturnPort` there is **no background thread**.
    Tests call :meth:`deliver` from the same thread that later calls
    ``entry.wait()``.  Because the entry is resolved *before* ``wait``
    is called, the ``Event`` is already set and ``wait`` returns
    immediately.  This makes tests fully deterministic with no timing
    sensitivity.

    :meth:`deliver` encodes the supplied envelope dict into a real v2
    SysEx frame and routes it through :meth:`ReturnPort.deliver_frame`
    so the production decode path is exercised end-to-end.
    """

    def __init__(self) -> None:
        super().__init__()
        self.delivered: list[dict[str, Any]] = []

    def deliver(self, envelope: dict[str, Any]) -> None:
        """Encode ``envelope`` as a v2 frame and hand it to the dispatcher."""
        self.delivered.append(envelope)
        request_id = envelope.get("request_id", 0)
        payload = json.dumps(envelope).encode("utf-8")
        frame = V2.encode_frame(V2.SysExFrame(request_id=request_id, payload=payload))
        self.deliver_frame(frame)
