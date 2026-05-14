"""Tests that exercise the :class:`Output` Protocol abstraction.

The production CLI uses ``_ClickJsonLineOutput`` and most tests reach
the same surface through Click's ``CliRunner``; nothing else proves
that the abstraction is actually substitutable.  These tests pin that
property by installing an in-memory recorder via :func:`use_output`
and asserting that ``_emit_success`` / ``_fail`` route through the
protocol cleanly -- the failure path no longer raises
:class:`SystemExit` because the recorder's ``exit_failure`` is a
no-op.
"""

from __future__ import annotations

from conftest import RecordingOutput

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_helpers import (
    _emit_success,
    _fail,
    use_output,
)


class TestUseOutput:
    def test_emits_route_only_to_inner_recorder(self):
        outer = RecordingOutput()
        inner = RecordingOutput()

        with use_output(outer):
            _emit_success("first", result={})
            with use_output(inner):
                _emit_success("nested", result={})
            _emit_success("last", result={})

        assert [e["command"] for e in outer.envelopes] == ["first", "last"]
        assert [e["command"] for e in inner.envelopes] == ["nested"]

    def test_restores_previous_sink_when_body_raises(self):
        recorder = RecordingOutput()
        outer = RecordingOutput()

        class _Boom(Exception):
            pass

        with use_output(outer):
            try:
                with use_output(recorder):
                    raise _Boom
            except _Boom:
                pass
            _emit_success("after_boom", result={})

        # The inner sink saw nothing post-raise; the outer sink is the
        # one that captured the post-boom emit, proving restoration.
        assert recorder.envelopes == []
        assert [e["command"] for e in outer.envelopes] == ["after_boom"]


class TestEmitSuccessRoutesThroughOutput:
    def test_envelope_shape_and_no_exit(self):
        recorder = RecordingOutput()
        with use_output(recorder):
            _emit_success("ping", args={"echo": 1}, result={"pong": True})

        assert len(recorder.envelopes) == 1
        envelope = recorder.envelopes[0]
        assert envelope["ok"] is True
        assert envelope["command"] == "ping"
        assert envelope["args"] == {"echo": 1}
        assert envelope["result"] == {"pong": True}
        assert recorder.exit_codes == []


class TestFailRoutesThroughOutputWithoutSystemExit:
    def test_emits_failure_envelope_and_calls_exit_failure(self):
        recorder = RecordingOutput()
        with use_output(recorder):
            _fail(
                "ping",
                "no port",
                code=Env.CODE_PORT_NOT_FOUND,
                hint="start LoopMIDI",
            )

        assert len(recorder.envelopes) == 1
        envelope = recorder.envelopes[0]
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "PORT_NOT_FOUND"
        assert envelope["error"]["message"] == "no port"
        assert envelope["error"]["hint"] == "start LoopMIDI"
        assert recorder.exit_codes == [10]

    def test_default_code_is_invalid_argument(self):
        recorder = RecordingOutput()
        with use_output(recorder):
            _fail("note", "bad pitch")

        assert recorder.envelopes[0]["error"]["code"] == "INVALID_ARGUMENT"
        assert recorder.exit_codes == [2]
