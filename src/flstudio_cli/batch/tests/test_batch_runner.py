"""Tests for ``execute_batch_run`` driven by an in-memory Output.

These tests exercise the application-layer runner directly --
no Click ``CliRunner`` involved -- so a future Web frontend can rely on
the same code path passing without re-routing through stdout / SystemExit.
The recorder substitutes for ``Output``: failure paths capture the
exit code instead of raising :class:`SystemExit`.
"""

from __future__ import annotations

from contextlib import contextmanager

from conftest import ALL_HANDLERS, RecordingOutput

from flstudio_cli.batch.application import batch as B
from flstudio_cli.batch.application.batch_runner import execute_batch_run
from flstudio_cli.shared.application.cli_dispatcher import DispatchDeps


def _make_deps(output: RecordingOutput, *, dry_run: bool = True) -> DispatchDeps:
    """Build a DispatchDeps that never opens a real controller.

    Tests that don't actually need to send wire frames pass dry_run=True
    so the runner returns dry-run envelopes without ever entering the
    controller context.
    """

    @contextmanager
    def _refuse_controller():
        raise AssertionError("controller must not be opened in dry-run tests")
        yield  # pragma: no cover

    return DispatchDeps(
        dry_run=dry_run,
        open_controller=_refuse_controller,
        output=output,
        resolve_exit_code=lambda code: 99 if code == "INTERNAL" else 2,
        timeout_hint="(test) timeout hint",
        port_hint="(test) port hint",
    )


class TestExecuteBatchRunDryRun:
    def test_all_steps_ok_emits_single_success_summary(self):
        output = RecordingOutput()
        deps = _make_deps(output, dry_run=True)
        steps = [
            B.BatchStep(name="tempo", args={"bpm": 120}),
            B.BatchStep(name="tempo", args={"bpm": 140}),
        ]

        execute_batch_run(
            deps,
            steps,
            handlers=ALL_HANDLERS,
            stop_on_error=True,
            args_echo={"steps_file": "-", "stop_on_error": True},
        )

        assert len(output.envelopes) == 1
        envelope = output.envelopes[0]
        assert envelope["ok"] is True
        assert envelope["command"] == "batch_run"
        assert envelope["result"]["count"] == 2
        assert envelope["result"]["ok_count"] == 2
        assert output.exit_codes == []

    def test_unknown_command_aborts_before_any_dispatch(self):
        output = RecordingOutput()
        deps = _make_deps(output, dry_run=True)
        steps = [
            B.BatchStep(name="trakc.set_volume", args={"track": 1}),
        ]

        execute_batch_run(
            deps,
            steps,
            handlers=ALL_HANDLERS,
            stop_on_error=True,
            args_echo={"steps_file": "-", "stop_on_error": True},
        )

        # batch_executor.run_steps already aborts on validation failure;
        # the runner sees a single error envelope and reports a failure
        # summary with no SystemExit-equivalent leak.
        assert len(output.envelopes) == 1
        envelope = output.envelopes[0]
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "UNKNOWN_COMMAND"
        assert output.exit_codes == [2]
