"""Use case: thin imperative shell around the command / response transport.

Onion-architecture seam: the controller talks to outer-layer effects
through the :mod:`flstudio_cli.shared.application.ports` Protocols and bundles
only — :class:`CommandTransport`, :class:`ReturnPort`, and
:class:`FrameCodec`.
Concrete back-ends live in
:mod:`flstudio_cli.shared.infrastructure.transport` and
:mod:`flstudio_cli.shared.infrastructure.protocol`; they are wired in by the
composition root in :mod:`flstudio_cli.shared.composition`.  The controller
itself never imports infrastructure, so swapping the wire format
(future v3) needs no application change.

The only public write method is :meth:`send_and_wait`: it asks the
codec for a ready-to-send frame, registers a pending entry on the
return port, blocks on the entry's :meth:`PendingResponse.wait`, and
returns the decoded response envelope.  Timeouts raise
:class:`TimeoutError`; the CLI layer maps that to the stable
``CODE_TIMEOUT`` error code.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import IO, Any, Self

from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.application.ports import (
    CommandTransport,
    FrameCodec,
    ReturnPort,
)


def _safely_close(
    close: Callable[[], object],
    expected: tuple[type[BaseException], ...],
) -> None:
    """Run ``close()`` and swallow only the exception types listed.

    Used by :meth:`DawController.__exit__` so the three resource-close
    calls share one try/except shape and one explicit allowlist.
    """
    try:
        close()
    except expected:
        pass


class DawController:
    """Context-managed entry point for sending commands to a DAW.

    The class itself is DAW-agnostic: it speaks the wire protocol
    defined by :class:`FrameCodec` to whichever device script answers
    on the configured ports.
    """

    def __init__(
        self,
        transport: CommandTransport,
        return_port: ReturnPort,
        codec: FrameCodec,
        *,
        _trace_fh: IO[Any] | None = None,
    ) -> None:
        self._transport = transport
        self._return_port = return_port
        self._codec = codec
        self._trace_fh = _trace_fh

        self._entered = False
        self._request_id_counter = 0
        self._counter_lock = threading.Lock()

    # --- lifecycle --------------------------------------------------------

    def __enter__(self) -> Self:
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._entered = False

        # Close the return port *before* the transport so any in-flight
        # ``send_and_wait`` unblocks via ConnectionResetError instead of
        # hanging forever on the waiter event.  ``OSError`` / ``RuntimeError``
        # are the realistic shutdown noise from the rtmidi adapters when
        # the underlying handle has already gone away; anything else
        # (KeyboardInterrupt, programmer bug) still propagates.
        _safely_close(self._return_port.close, (OSError, RuntimeError))
        _safely_close(self._transport.close, (OSError, RuntimeError))
        if self._trace_fh is not None:
            _safely_close(self._trace_fh.close, (OSError,))
            self._trace_fh = None

    # --- send_and_wait ----------------------------------------------------

    def _next_request_id(self) -> int:
        with self._counter_lock:
            self._request_id_counter = (
                self._request_id_counter + 1
            ) & self._codec.request_id_max
            # Skip zero so a forgotten ``request_id`` field in a response
            # doesn't collide with a real in-flight request.
            if self._request_id_counter == 0:
                self._request_id_counter = 1
            return self._request_id_counter

    def send_and_wait(
        self,
        cmd: str,
        args: dict[str, Any] | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Send a command frame and block until a response arrives.

        Raises :class:`TimeoutError` if no response arrives within
        ``timeout_ms``. The caller layer is responsible for mapping
        that to the ``TIMEOUT`` error code.
        """
        if not self._entered:
            raise RuntimeError("DawController must be used as a context manager")

        request_id = self._next_request_id()
        entry = self._return_port.register(request_id)
        frame_bytes = self._codec.encode_command_frame(cmd, args, request_id)
        try:
            self._transport.send_frame(frame_bytes)
            return entry.wait(timeout_seconds=timeout_ms / 1000.0)
        finally:
            self._return_port.forget(request_id)

    def send_command(
        self, command: DeviceCommand, *, timeout_ms: int = 5000
    ) -> dict[str, Any]:
        """Send a :class:`DeviceCommand` and block until a response arrives.

        Convenience wrapper over :meth:`send_and_wait` for callers that
        already hold a typed :class:`DeviceCommand` (e.g. anything routed
        through :class:`FlCommandPort`); keeps the ``cmd`` / ``args``
        unpacking out of feature-level call sites.
        """
        return self.send_and_wait(command.cmd, command.args, timeout_ms=timeout_ms)
