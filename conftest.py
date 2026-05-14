"""Shared fixtures for the flcli test suite.

Fixtures defined here are automatically available to every test file under
``tests/``.  Keep this module focused on **truly shared** helpers —
test-file-specific helpers belong next to the tests that use them.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

import mido
import pytest
from click.testing import CliRunner

from flstudio_cli.__main__ import ALL_BATCH_HANDLERS
from flstudio_cli.batch.application import batch as B
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort

# ---------------------------------------------------------------------------
# Handler registry mirror
# ---------------------------------------------------------------------------

#: Merged handler dict matching the production composition root in
#: ``flstudio_cli.__main__``: every per-feature ``BATCH_HANDLERS`` dict
#: (mixer / plugin / project / transport / piano_roll / state) plus the
#: IO-bound ``piano_roll_show`` handler bound by
#: ``state.composition.compose``.  Tests that drive ``B.execute_step``
#: directly pass this so every command stays dispatchable.
ALL_HANDLERS: dict[str, B.BatchHandler] = ALL_BATCH_HANDLERS

# ---------------------------------------------------------------------------
# In-memory test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeCommandTransport:
    """In-memory ``CommandTransport`` capturing every outgoing frame.

    Use this wherever production code expects an object with
    ``send_frame(frame)`` and ``close()`` methods.
    """

    frames: list[bytes] = field(default_factory=list)
    closed: bool = False

    def send_frame(self, frame: bytes) -> None:
        self.frames.append(bytes(frame))

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_transport() -> FakeCommandTransport:
    """Provide a fresh :class:`FakeCommandTransport` that records frames in memory."""
    return FakeCommandTransport()


# ---------------------------------------------------------------------------
# Click CLI runner
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click ``CliRunner`` for invoking CLI commands without I/O."""
    return CliRunner()


# ---------------------------------------------------------------------------
# MIDI port monkeypatches
# ---------------------------------------------------------------------------


@pytest.fixture
def no_ports(monkeypatch):
    """Monkeypatch ``mido.get_output_names`` to return an empty list.

    Use this to simulate an environment where no MIDI output ports are
    visible — e.g. to test error-handling for missing hardware.
    """
    monkeypatch.setattr(mido, "get_output_names", lambda: [])


@pytest.fixture
def matching_port(monkeypatch):
    """Monkeypatch ``mido.get_output_names`` to return ``["flcli virtual"]``.

    Use this to simulate an environment with exactly one port whose name
    matches the default substring search (``"flcli"``).
    """
    monkeypatch.setattr(mido, "get_output_names", lambda: ["flcli virtual"])


# ---------------------------------------------------------------------------
# Doctor effects bundle
# ---------------------------------------------------------------------------


@pytest.fixture
def doctor_effects():
    """Provide the production :class:`DoctorEffects` bundle.

    Doctor's ``check_*`` and :func:`collect_diagnostics` functions
    require a :class:`DoctorEffects` (or its constituent ports);
    tests that exercise the real ``list_output_ports`` /
    ``piano_roll_io`` adapters but mock ``mido`` underneath grab this
    bundle directly from composition.
    """
    from flstudio_cli.shared.composition import PRODUCTION_DOCTOR_EFFECTS

    return PRODUCTION_DOCTOR_EFFECTS


# ---------------------------------------------------------------------------
# Recording Output adapter
# ---------------------------------------------------------------------------


@dataclass
class RecordingOutput:
    """In-memory :class:`Output` that captures envelopes and exit codes.

    Application-layer flows emit envelopes through ``deps.output``;
    tests substitute this recorder so the failure path no longer
    raises :class:`SystemExit` and assertions can read what was
    emitted.
    """

    envelopes: list[dict[str, Any]] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)

    def emit_envelope(self, envelope: dict[str, Any]) -> None:
        self.envelopes.append(envelope)

    def exit_failure(self, exit_code: int) -> None:
        self.exit_codes.append(exit_code)


# ---------------------------------------------------------------------------
# Response scheduling helper
# ---------------------------------------------------------------------------


def schedule_response(
    return_port: FakeReturnPort,
    request_id: int,
    envelope: dict[str, Any],
) -> threading.Timer:
    """Deliver a fake device response on a short timer (test helper).

    Creates a 10 ms timer that calls ``return_port.deliver`` with the
    given *envelope* (augmented with *request_id*).  Returns the timer
    so callers can ``join()`` it if needed.
    """
    envelope = dict(envelope)
    envelope["request_id"] = request_id
    timer = threading.Timer(0.01, lambda: return_port.deliver(envelope))
    timer.start()
    return timer


# ---------------------------------------------------------------------------
# CLI output parsing
# ---------------------------------------------------------------------------


def parse_first_line(output: str) -> dict:
    """Parse the first line of CLI output as a JSON object.

    Most ``flcli`` commands emit a single JSON envelope on stdout.
    This helper grabs the first non-empty line and decodes it —
    handy for asserting on envelope fields in Click integration tests.
    """
    return json.loads(output.strip().splitlines()[0])
