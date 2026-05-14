"""Infrastructure adapter: recording transport that wraps a :class:`CommandTransport` and writes a JSONL trace.

Trace format
------------
Each line is a self-contained JSON object (JSONL / JSON Lines).  Every
entry written by this module represents an **outgoing** frame and has
the following shape::

    {
        "t":         <float>,   # seconds since recording started (monotonic)
        "dir":       "out",     # direction -- always "out" for this sink
        "type":      "sysex",   # message type
        "frame_hex": "f07d..."  # full F0..F7 frame as lowercase hex
    }

Response frames (``"dir": "in"``) are appended by the return-port
recorder (if active) with the same schema.  Together, the ``out`` and
``in`` lines form a complete session transcript that
:mod:`~flstudio_cli.shared.infrastructure.transport.replay_sink` can play back
deterministically.
"""

from __future__ import annotations

import json
import time
from typing import Any, TextIO

from flstudio_cli.shared.application.ports import CommandTransport


class RecordingCommandTransport:
    """:class:`CommandTransport` wrapper that logs every outgoing frame to a JSONL trace.

    Each line: {"t": <float>, "dir": "out", "type": "sysex", "frame_hex": "f07d02...f7"}
    """

    def __init__(self, inner: CommandTransport, trace_file: TextIO) -> None:
        self._inner = inner
        self._trace = trace_file
        self._start = time.monotonic()

    def send_frame(self, frame: bytes) -> None:
        self._write_event({"dir": "out", "type": "sysex", "frame_hex": frame.hex()})
        self._inner.send_frame(frame)

    def close(self) -> None:
        self._inner.close()

    def _write_event(self, event: dict[str, Any]) -> None:
        event["t"] = round(time.monotonic() - self._start, 6)
        # The trace file is opened line-buffered upstream (composition layer),
        # so the newline below is the flush point — no explicit flush() needed.
        self._trace.write(json.dumps(event, ensure_ascii=False) + "\n")
