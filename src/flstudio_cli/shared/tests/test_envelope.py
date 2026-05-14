"""Tests for the application response envelope and error-code taxonomy."""

from __future__ import annotations

from flstudio_cli.shared.application import envelope as Env


class TestSuccessEnvelope:
    def test_given_only_command_when_success_then_returns_minimal_shape(self):
        payload = Env.success("ping")

        assert payload["ok"] is True
        assert payload["command"] == "ping"
        assert payload["args"] == {}
        assert payload["result"] == {}
        assert payload["error"] is None

    def test_given_args_and_result_when_success_then_includes_both(self):
        payload = Env.success(
            "tempo",
            args={"bpm": 140},
            result={"bpm": 140.0, "wire_bytes": 4},
        )

        assert payload["args"] == {"bpm": 140}
        assert payload["result"] == {"bpm": 140.0, "wire_bytes": 4}

    def test_given_none_defaults_when_success_then_coerces_to_empty_dicts(self):
        # None-guarding lets callers skip ceremony for read-only commands.
        payload = Env.success("ports", args=None, result=None)

        assert payload["args"] == {}
        assert payload["result"] == {}


class TestFailureEnvelope:
    def test_given_minimal_failure_then_carries_code_and_message(self):
        payload = Env.failure("note", Env.CODE_INVALID_ARGUMENT, "bad pitch")

        assert payload["ok"] is False
        assert payload["command"] == "note"
        assert payload["result"] is None
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert payload["error"]["message"] == "bad pitch"

    def test_given_hint_when_failure_then_included_in_error(self):
        payload = Env.failure(
            "ping",
            Env.CODE_PORT_NOT_FOUND,
            "no port",
            hint="start LoopMIDI",
        )

        assert payload["error"]["hint"] == "start LoopMIDI"

    def test_given_details_when_failure_then_included_in_error(self):
        payload = Env.failure(
            "doctor",
            Env.CODE_NOT_FOUND,
            "missing state",
            details={"path": "/tmp/nope.json"},
        )

        assert payload["error"]["details"] == {"path": "/tmp/nope.json"}

    def test_given_no_hint_then_error_omits_hint_key(self):
        # Predictable jq patterns: keys only exist when they have a value.
        payload = Env.failure("note", Env.CODE_INVALID_ARGUMENT, "bad")

        assert "hint" not in payload["error"]
        assert "details" not in payload["error"]
