"""Tests for the batch execution path."""

from __future__ import annotations

from typing import Any

from conftest import ALL_HANDLERS, schedule_response

from flstudio_cli.batch.application import batch as B
from flstudio_cli.project.application import handlers as cmds_project
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort
from flstudio_cli.state.application import handlers as cmds_state
from flstudio_cli.transport.application import handlers as cmds_transport

# ---------------------------------------------------------------------------
# Test helpers for the typed handler outcomes
# ---------------------------------------------------------------------------


def _expect_command(result: Any) -> B.DeviceCommand:
    """Unwrap an ``Ok[DeviceCommand]`` or fail loudly."""
    assert isinstance(result, B.Ok), f"expected Ok(...), got {result!r}"
    assert isinstance(result.value, B.DeviceCommand), (
        f"expected DeviceCommand, got {result.value!r}"
    )
    return result.value


def _expect_invalid_argument(result: Any) -> str:
    """Unwrap an ``Err[InvalidArgument]`` and return its message."""
    assert isinstance(result, B.Err), f"expected Err(...), got {result!r}"
    assert isinstance(result.error, B.InvalidArgument), (
        f"expected InvalidArgument, got {result.error!r}"
    )
    return result.error.message


class TestHandlerRegistry:
    def test_handler_names_are_unique_strings(self) -> None:
        assert all(isinstance(name, str) for name in ALL_HANDLERS)
        assert len(ALL_HANDLERS) == len(set(ALL_HANDLERS))

    def test_tempo_handler_coerces_bpm_to_float(self) -> None:
        cmd = _expect_command(cmds_project._handle_tempo({"bpm": 140}))
        assert cmd == B.DeviceCommand("tempo", {"bpm": 140.0})

    def test_name_channel_requires_string_name(self) -> None:
        message = _expect_invalid_argument(
            cmds_project._handle_name_channel({"channel": 0, "name": 42})
        )
        assert "string" in message

    def test_name_channel_happy_path(self) -> None:
        cmd = _expect_command(
            cmds_project._handle_name_channel({"channel": 3, "name": "my synth bass"})
        )
        assert cmd == B.DeviceCommand(
            "name_channel", {"channel": 3, "name": "my synth bass"}
        )

    def test_set_step_defaults_on_and_velocity(self) -> None:
        cmd = _expect_command(cmds_project._handle_set_step({"channel": 1, "step": 4}))
        assert cmd == B.DeviceCommand(
            "set_step",
            {"channel": 1, "step": 4, "on": True, "velocity": 100},
        )

    def test_state_without_field_returns_empty_args(self) -> None:
        cmd = _expect_command(cmds_state._handle_state({}))
        assert cmd == B.DeviceCommand("state", {})

    def test_state_with_field_passes_it_through(self) -> None:
        cmd = _expect_command(cmds_state._handle_state({"field": "tempo"}))
        assert cmd == B.DeviceCommand("state", {"field": "tempo"})

    def test_transport_position_get_defaults_to_beats(self) -> None:
        cmd = _expect_command(cmds_transport._handle_transport_position_get({}))
        assert cmd == B.DeviceCommand("transport_position_get", {"mode": "beats"})

    def test_transport_position_get_accepts_ticks(self) -> None:
        cmd = _expect_command(
            cmds_transport._handle_transport_position_get({"mode": "ticks"})
        )
        assert cmd == B.DeviceCommand("transport_position_get", {"mode": "ticks"})

    def test_transport_position_get_rejects_invalid_mode(self) -> None:
        message = _expect_invalid_argument(
            cmds_transport._handle_transport_position_get({"mode": "invalid"})
        )
        assert "mode" in message

    def test_transport_position_set_requires_position(self) -> None:
        message = _expect_invalid_argument(
            cmds_transport._handle_transport_position_set({"mode": "beats"})
        )
        assert "position" in message

    def test_transport_position_set_happy_path(self) -> None:
        cmd = _expect_command(
            cmds_transport._handle_transport_position_set(
                {"position": 16.5, "mode": "beats"}
            )
        )
        assert cmd == B.DeviceCommand(
            "transport_position_set", {"position": 16.5, "mode": "beats"}
        )

    def test_transport_loop_get_returns_command(self) -> None:
        cmd = _expect_command(cmds_transport._handle_transport_loop_get({}))
        assert cmd == B.DeviceCommand("transport_loop_get", {})

    def test_transport_loop_toggle_returns_command(self) -> None:
        cmd = _expect_command(cmds_transport._handle_transport_loop_toggle({}))
        assert cmd == B.DeviceCommand("transport_loop_toggle", {})

    def test_undo_returns_command(self) -> None:
        cmd = _expect_command(cmds_transport._handle_undo({}))
        assert cmd == B.DeviceCommand("undo", {})

    def test_redo_returns_command(self) -> None:
        cmd = _expect_command(cmds_transport._handle_redo({}))
        assert cmd == B.DeviceCommand("redo", {})

    def test_undo_history_returns_command(self) -> None:
        cmd = _expect_command(cmds_transport._handle_undo_history({}))
        assert cmd == B.DeviceCommand("undo_history", {})

    def test_handlers_include_migrated_transport_commands(self) -> None:
        for expected in (
            "transport_position_get",
            "transport_position_set",
            "transport_loop_get",
            "transport_loop_toggle",
            "undo",
            "redo",
            "undo_history",
        ):
            assert expected in cmds_transport.BATCH_HANDLERS

    def test_handlers_include_migrated_project_commands(self) -> None:
        for expected in (
            "new_project",
            "new_pattern",
            "select_pattern",
            "name_pattern",
            "channel_rack_focus",
            "focus_channel_editor",
            "name_channel",
            "select_channel",
            "tempo",
            "set_step",
        ):
            assert expected in cmds_project.BATCH_HANDLERS

    def test_state_handler_is_known(self) -> None:
        assert "state" in cmds_state.BATCH_HANDLERS

    def test_all_handlers_unions_features_and_di_composition(self) -> None:
        """``ALL_HANDLERS`` covers every feature plus DI-bound handlers.

        Mirrors the merge ``__main__`` does at startup: each feature's
        ``BATCH_HANDLERS`` plus the IO-bound ``piano_roll_show``
        produced by ``state.composition.compose``.
        """
        names = set(ALL_HANDLERS)
        assert "step_melody" in names  # piano_roll feature
        assert "state" in names  # state feature
        assert "tempo" in names  # project feature
        assert "piano_roll_show" in names  # state composition (DI)


class TestExecuteStepSuccess:
    def test_given_tempo_step_when_device_responds_ok_then_envelope_succeeds(
        self,
        fake_transport,
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "tempo",
                    "result": {"bpm": 140.5},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="tempo", args={"bpm": 140.5}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["bpm"] == 140.5

    def test_given_name_channel_with_string_then_round_trips(
        self,
        fake_transport,
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "name_channel",
                    "result": {"channel": 3, "name": "my synth bass"},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(
                    name="name_channel", args={"channel": 3, "name": "my synth bass"}
                ),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["name"] == "my synth bass"

    def test_given_state_field_tempo_then_synchronous_round_trip(
        self,
        fake_transport,
    ) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "state",
                    "result": {"field": "tempo", "value": 128.0},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="state", args={"field": "tempo"}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["value"] == 128.0


class TestExecuteStepErrors:
    def test_given_unknown_command_returns_unknown_command_envelope(
        self,
        fake_transport,
    ) -> None:
        with DawController(
            fake_transport,
            FakeReturnPort(),
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            envelope = B.execute_step(
                B.BatchStep(name="no_such_command", args={}),
                controller=controller,
                dry_run=False,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == Env.CODE_UNKNOWN_COMMAND

    def test_given_missing_required_arg_returns_invalid_argument(
        self,
        fake_transport,
    ) -> None:
        with DawController(
            fake_transport,
            FakeReturnPort(),
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            envelope = B.execute_step(
                B.BatchStep(name="tempo", args={}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "bpm" in envelope["error"]["message"]

    def test_given_non_string_name_returns_invalid_argument(
        self, fake_transport
    ) -> None:
        with DawController(
            fake_transport,
            FakeReturnPort(),
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            envelope = B.execute_step(
                B.BatchStep(name="name_channel", args={"channel": 0, "name": 42}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == Env.CODE_INVALID_ARGUMENT

    def test_given_no_response_returns_timeout_envelope(self, fake_transport) -> None:
        with DawController(
            fake_transport,
            FakeReturnPort(),
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            envelope = _execute_with_short_timeout(
                B.BatchStep(name="tempo", args={"bpm": 120}),
                controller,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == Env.CODE_TIMEOUT

    def test_given_device_error_envelope_is_propagated(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": False,
                    "command": "tempo",
                    "result": None,
                    "error": {"code": "INTERNAL", "message": "boom"},
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="tempo", args={"bpm": 120}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "INTERNAL"
        assert envelope["error"]["message"] == "boom"


def _execute_with_short_timeout(
    step: B.BatchStep,
    controller: DawController,
) -> dict[str, Any]:
    original = controller.send_and_wait

    def short(
        cmd: str,
        args: dict[str, Any] | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        return original(cmd, args, timeout_ms=20)

    controller.send_and_wait = short  # type: ignore[method-assign]
    try:
        return B.execute_step(
            step,
            controller=controller,
            dry_run=False,
            handlers=ALL_HANDLERS,
        )
    finally:
        controller.send_and_wait = original  # type: ignore[method-assign]


class TestDryRunEchosRequest:
    def test_given_dry_run_then_echoes_cmd_and_args(self, fake_transport) -> None:
        envelope = B.execute_step(
            B.BatchStep(name="tempo", args={"bpm": 140}),
            controller=None,
            dry_run=True,
            handlers=ALL_HANDLERS,
        )
        assert envelope["ok"] is True
        assert envelope["result"]["dry_run"] is True
        assert envelope["result"]["request"]["cmd"] == "tempo"
        assert envelope["result"]["request"]["args"]["bpm"] == 140.0


class TestRunStepsPreValidation:
    """``run_steps`` validates every step before sending anything to the device.

    A typo'd field or unknown command in step *N* should abort the whole
    batch with no controller traffic for steps 1..N-1, so the device
    state never partially reflects an invalid input.
    """

    def test_given_unknown_command_then_aborts_before_first_send(
        self, fake_transport
    ) -> None:
        sent: list[bytes] = []
        original_send = fake_transport.send_frame

        def record(frame: bytes) -> None:
            sent.append(frame)
            original_send(frame)

        fake_transport.send_frame = record  # type: ignore[method-assign]

        envelopes = B.run_steps(
            [
                B.BatchStep(name="tempo", args={"bpm": 140}),
                B.BatchStep(name="trakc.set_volume", args={"track": 1}),
            ],
            controller=None,
            dry_run=True,
            stop_on_error=False,
            handlers=ALL_HANDLERS,
        )

        assert sent == []
        assert len(envelopes) == 1
        assert envelopes[0]["ok"] is False
        assert envelopes[0]["error"]["code"] == "UNKNOWN_COMMAND"

    def test_given_invalid_argument_then_aborts_before_first_send(
        self, fake_transport
    ) -> None:
        sent: list[bytes] = []
        original_send = fake_transport.send_frame

        def record(frame: bytes) -> None:
            sent.append(frame)
            original_send(frame)

        fake_transport.send_frame = record  # type: ignore[method-assign]

        envelopes = B.run_steps(
            [
                B.BatchStep(name="tempo", args={"bpm": 140}),
                B.BatchStep(name="tempo", args={}),
            ],
            controller=None,
            dry_run=True,
            stop_on_error=False,
            handlers=ALL_HANDLERS,
        )

        assert sent == []
        assert len(envelopes) == 1
        assert envelopes[0]["ok"] is False
        assert envelopes[0]["error"]["code"] == "INVALID_ARGUMENT"

    def test_given_all_valid_then_dispatches_every_step(self, fake_transport) -> None:
        envelopes = B.run_steps(
            [
                B.BatchStep(name="tempo", args={"bpm": 120}),
                B.BatchStep(name="tempo", args={"bpm": 140}),
            ],
            controller=None,
            dry_run=True,
            stop_on_error=False,
            handlers=ALL_HANDLERS,
        )
        assert len(envelopes) == 2
        assert all(e["ok"] for e in envelopes)
