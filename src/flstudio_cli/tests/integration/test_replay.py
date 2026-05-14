"""Integration tests that replay a recorded JSONL trace without FL Studio.

These tests use the ``FLCLI_REPLAY`` env-var mechanism in
:func:`build_transport` to drive the controller against a pre-recorded
trace fixture. No MIDI port is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flstudio_cli.shared.composition import build_transport, open_daw_controller
from flstudio_cli.shared.infrastructure.transport.replay_sink import (
    ReplayCommandTransport,
    ReplayReturnPort,
    load_trace,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
BATCH_SESSION = FIXTURE_DIR / "batch_session.jsonl"


class TestReplayFixtureExists:
    def test_fixture_file_is_present(self) -> None:
        assert BATCH_SESSION.is_file(), f"fixture not found at {BATCH_SESSION}"

    def test_fixture_has_both_directions(self) -> None:
        with BATCH_SESSION.open() as fh:
            out_events, in_events = load_trace(fh)
        assert len(out_events) > 0, "fixture has no outgoing frames"
        assert len(in_events) > 0, "fixture has no incoming frames"


class TestReplayViaController:
    """Replay the batch_session fixture through a real DawController."""

    @pytest.fixture()
    def replay_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLCLI_REPLAY", str(BATCH_SESSION))

    def test_tempo_command_replays(self, replay_env: None) -> None:
        with open_daw_controller() as ctrl:
            resp = ctrl.send_and_wait("tempo", {"bpm": 128})
            assert resp["ok"] is True
            assert resp["command"] == "tempo"
            assert resp["result"]["bpm"] == 128

    def test_full_session_replays_in_order(self, replay_env: None) -> None:
        with open_daw_controller() as ctrl:
            r1 = ctrl.send_and_wait("tempo", {"bpm": 128})
            assert r1["ok"] is True

            r2 = ctrl.send_and_wait("play")
            assert r2["ok"] is True
            assert r2["result"]["is_playing"] is True

            r3 = ctrl.send_and_wait("state")
            assert r3["ok"] is True
            assert r3["result"]["tempo"] == 128.0
            assert r3["result"]["is_playing"] is True

            r4 = ctrl.send_and_wait("stop")
            assert r4["ok"] is True
            assert r4["result"]["is_playing"] is False


class TestReplayViaEnvVar:
    """Verify the env-var based sink selection in build_transport."""

    def test_replay_env_var_selects_replay_sink(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FLCLI_REPLAY", str(BATCH_SESSION))
        sink, return_port, trace_fh = build_transport()
        try:
            assert isinstance(sink, ReplayCommandTransport)
            assert isinstance(return_port, ReplayReturnPort)
        finally:
            if trace_fh is not None:
                trace_fh.close()

    def test_given_no_env_vars_when_build_transport_then_falls_through_to_live_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With neither env var set, build_transport reaches the live MIDI path.

        Stubs `resolve_port` to raise so the test is deterministic
        regardless of the host's MIDI configuration.  The previous
        version relied on `mido.get_output_names()` returning an empty
        list, which fails on a developer Mac with FL Studio open
        (a real MIDI port is then available, build_transport succeeds,
        and `pytest.raises(Exception)` fails).  Mocking the seam pins
        the test to the build_transport contract instead of the host.
        """
        monkeypatch.delenv("FLCLI_REPLAY", raising=False)
        monkeypatch.delenv("FLCLI_RECORD", raising=False)

        def _no_port(_name: str | None, _default: str) -> str:
            raise RuntimeError("no matching MIDI port (stubbed)")

        monkeypatch.setattr(
            "flstudio_cli.shared.composition.transport.resolve_port",
            _no_port,
        )

        with pytest.raises(RuntimeError, match="no matching MIDI port"):
            build_transport()


class TestRecordingViaEnvVar:
    """Verify that FLCLI_RECORD wraps the sink in RecordingCommandTransport."""

    def test_record_env_var_creates_trace_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from conftest import FakeCommandTransport

        from flstudio_cli.shared.infrastructure.transport.recording_sink import (
            RecordingCommandTransport,
        )
        from flstudio_cli.shared.infrastructure.transport.return_port import (
            FakeReturnPort,
        )

        trace_path = tmp_path / "trace.jsonl"
        monkeypatch.setenv("FLCLI_RECORD", str(trace_path))
        monkeypatch.delenv("FLCLI_REPLAY", raising=False)

        monkeypatch.setattr(
            "flstudio_cli.shared.composition.transport.MidoCommandTransport",
            lambda port_name: FakeCommandTransport(),
        )
        monkeypatch.setattr(
            "flstudio_cli.shared.composition.transport.MidoReturnPort",
            lambda port_name: FakeReturnPort(),
        )
        monkeypatch.setattr(
            "flstudio_cli.shared.composition.transport.resolve_port",
            lambda name, default: name or default,
        )

        sink, _return_port, trace_fh = build_transport()
        try:
            assert isinstance(sink, RecordingCommandTransport)
        finally:
            if trace_fh is not None:
                trace_fh.close()

        # Trace file should exist (even if empty)
        assert trace_path.exists()
