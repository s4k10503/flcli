"""Infrastructure adapter: replay transport that reads a JSONL trace and simulates FL Studio responses.

Loading and matching
--------------------
:func:`load_trace` reads a JSONL file (one JSON object per line) and
partitions events by ``"dir"``:

* ``"out"`` events become the expected sequence for
  :class:`ReplayCommandTransport`.
* ``"in"``  events become the pre-scheduled responses for
  :class:`ReplayReturnPort`.

:class:`ReplayCommandTransport` enforces **strict sequential matching**:
every call to :meth:`send_frame` must produce a ``frame_hex`` that is
byte-for-byte identical to the next ``out`` event in the trace.  A
mismatch raises :class:`ReplayMismatchError`.

When a :class:`ReplayReturnPort` is linked, each successful outgoing
match automatically feeds the next ``in`` event into the pending-request
table so that ``send_and_wait`` unblocks exactly as it did during the
original live session.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any, TextIO

from flstudio_cli.shared.infrastructure.transport.return_port import ReturnPort


class ReplayMismatchError(AssertionError):
    """Outgoing frame does not match the recorded trace."""

    def __init__(self, expected_hex: str, actual_hex: str) -> None:
        self.expected_hex = expected_hex
        self.actual_hex = actual_hex
        super().__init__(
            f"frame mismatch: expected {expected_hex[:40]}... got {actual_hex[:40]}..."
        )


class ReplayCommandTransport:
    """:class:`CommandTransport` backed by a recorded JSONL trace.

    Each :meth:`send_frame` call is matched against the next 'out' event
    in the trace. When a :class:`ReplayReturnPort` is linked, the
    corresponding response is automatically fed after each successful
    outgoing match so that ``send_and_wait`` unblocks without manual
    intervention.
    """

    def __init__(
        self,
        out_events: list[dict[str, Any]],
        return_port: ReplayReturnPort | None = None,
    ) -> None:
        self._expected = deque(out_events)
        self._return_port = return_port

    def send_frame(self, frame: bytes) -> None:
        if not self._expected:
            raise ReplayMismatchError("(end of trace)", frame.hex())
        expected = self._expected.popleft()
        expected_hex = expected["frame_hex"]
        actual_hex = frame.hex()
        if expected_hex != actual_hex:
            raise ReplayMismatchError(expected_hex, actual_hex)
        # Auto-feed the next response so send_and_wait unblocks.
        if self._return_port is not None:
            self._return_port.feed_next()

    def close(self) -> None:
        pass


class ReplayReturnPort(ReturnPort):
    """ReturnPort backed by recorded 'in' events from a JSONL trace.

    Incoming frames are fed into the pending-request table so send_and_wait
    unblocks exactly as it did during the live session.
    """

    def __init__(self, in_events: list[dict[str, Any]]) -> None:
        super().__init__()
        self._responses = deque(in_events)

    def feed_next(self) -> bool:
        """Feed the next recorded response into the pending table.
        Returns False if no more responses."""
        if not self._responses:
            return False
        event = self._responses.popleft()
        frame_bytes = bytes.fromhex(event["frame_hex"])
        self.deliver_frame(frame_bytes)
        return True


def load_trace(trace_file: TextIO) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load a JSONL trace and split into (out_events, in_events)."""
    out_events: list[dict[str, Any]] = []
    in_events: list[dict[str, Any]] = []
    for line in trace_file:
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("dir") == "out":
            out_events.append(event)
        elif event.get("dir") == "in":
            in_events.append(event)
    return out_events, in_events
