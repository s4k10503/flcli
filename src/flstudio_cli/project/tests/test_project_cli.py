"""Click-level integration tests for project CLI surface (v2 only).

Covers ``tempo``, ``new-project``, ``new-pattern``, ``select-pattern``,
``duplicate-channel``, ``name-channel``, ``select-channel`` and ``step``.  The
dry-run paths exercise no MIDI port, while the end-to-end
:class:`TestNameChannelEndToEnd` test stubs the controller via
:class:`FakeReturnPort`.
"""

from __future__ import annotations

import threading

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC


class TestDryRunTempo:
    def test_given_tempo_dry_run_when_invoked_then_emits_request_preview(
        self,
        runner,
    ):
        result = runner.invoke(cli, ["--dry-run", "tempo", "140"], obj={})

        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "tempo"
        assert payload["args"] == {"bpm": 140.0}
        assert payload["result"]["dry_run"] is True
        assert payload["result"]["request"]["cmd"] == "tempo"
        assert payload["result"]["request"]["args"]["bpm"] == 140.0
        assert payload["error"] is None


class TestDryRunProjectCommands:
    """Dry-run smoke tests for the remaining project-axis commands."""

    def test_new_project_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "new-project"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "new_project"
        assert payload["result"]["request"]["cmd"] == "new_project"

    def test_new_pattern_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "new-pattern"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "new_pattern"

    def test_select_pattern_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "select-pattern", "3"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "select_pattern"
        assert payload["result"]["request"]["args"]["index"] == 3

    def test_duplicate_channel_dry_run(self, runner):
        # The duplicate-channel CLI command sends ``channel_rack_focus`` as
        # its first SysEx; in dry-run mode that initial preview is what
        # gets emitted (the Alt+C automation step is skipped via
        # DryRunTrigger).
        result = runner.invoke(cli, ["--dry-run", "duplicate-channel"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "channel_rack_focus"
        assert payload["result"]["request"]["cmd"] == "channel_rack_focus"

    def test_select_channel_dry_run(self, runner):
        result = runner.invoke(cli, ["--dry-run", "select-channel", "2"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "select_channel"
        assert payload["result"]["request"]["args"]["index"] == 2

    def test_new_pattern_dry_run_with_name(self, runner):
        result = runner.invoke(
            cli, ["--dry-run", "new-pattern", "--name", "Drums"], obj={}
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "new_pattern"
        assert payload["result"]["request"]["args"]["name"] == "Drums"

    def test_name_pattern_dry_run(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "name-pattern", "2", "--name", "Verse"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "name_pattern"
        args = payload["result"]["request"]["args"]
        assert args["index"] == 2
        assert args["name"] == "Verse"

    def test_focus_channel_editor_dry_run_default_window(self, runner):
        result = runner.invoke(cli, ["--dry-run", "focus-channel-editor", "3"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "focus_channel_editor"
        args = payload["result"]["request"]["args"]
        assert args["channel"] == 3
        assert args["window"] == "piano_roll"

    def test_focus_channel_editor_dry_run_plugin_window(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "focus-channel-editor", "0", "--window", "plugin"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["args"]["window"] == "plugin"

    def test_step_dry_run_with_velocity(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "step", "1", "4", "1", "--velocity", "120"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "set_step"
        args = payload["result"]["request"]["args"]
        assert args["channel"] == 1
        assert args["step"] == 4
        assert args["on"] is True
        assert args["velocity"] == 120


class TestNameChannelEndToEnd:
    def test_given_name_channel_with_string_then_round_trips(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        from flstudio_cli.shared.application.controller import DawController
        from flstudio_cli.shared.infrastructure.transport.return_port import (
            FakeReturnPort,
        )

        captured: dict[str, FakeReturnPort] = {}

        def fake_make_controller(ctx):
            return_port = FakeReturnPort()
            captured["return_port"] = return_port
            return DawController(fake_transport, return_port, PRODUCTION_FRAME_CODEC)

        monkeypatch.setattr(
            "flstudio_cli.shared.presentation.cli_dispatch._make_controller",
            fake_make_controller,
        )

        original_send_and_wait = DawController.send_and_wait

        def send_and_wait_with_response(self, cmd, args=None, timeout_ms=5000):
            rp = captured["return_port"]

            def deliver():
                rp.deliver(
                    {
                        "request_id": 1,
                        "ok": True,
                        "command": cmd,
                        "result": {"channel": args["channel"], "name": args["name"]},
                        "error": None,
                    }
                )

            threading.Timer(0.01, deliver).start()
            return original_send_and_wait(self, cmd, args, timeout_ms=1000)

        monkeypatch.setattr(
            DawController,
            "send_and_wait",
            send_and_wait_with_response,
        )

        result = runner.invoke(
            cli,
            ["name-channel", "3", "--name", "my synth bass"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["name"] == "my synth bass"
        assert payload["result"]["channel"] == 3


def _install_channel_count_controller(monkeypatch, fake_transport, counts):
    """Stub the DAW controller so each ``channel_rack_focus`` call returns
    the next value in ``counts``. Returns the call-counter dict so tests
    can assert how many SysEx round-trips happened.
    """
    from flstudio_cli.shared.application.controller import DawController
    from flstudio_cli.shared.infrastructure.transport.return_port import (
        FakeReturnPort,
    )

    captured: dict[str, FakeReturnPort] = {}

    def fake_make_controller(ctx):
        return_port = FakeReturnPort()
        captured["return_port"] = return_port
        return DawController(fake_transport, return_port, PRODUCTION_FRAME_CODEC)

    monkeypatch.setattr(
        "flstudio_cli.shared.presentation.cli_dispatch._make_controller",
        fake_make_controller,
    )

    original_send_and_wait = DawController.send_and_wait
    state = {"call": 0}

    def send_and_wait_with_response(self, cmd, args=None, timeout_ms=5000):
        rp = captured["return_port"]
        i = state["call"]
        state["call"] += 1
        result = {"count": counts[i]} if i < len(counts) else {"count": None}

        def deliver():
            rp.deliver(
                {
                    "request_id": 1,
                    "ok": True,
                    "command": cmd,
                    "result": result,
                    "error": None,
                }
            )

        threading.Timer(0.01, deliver).start()
        return original_send_and_wait(self, cmd, args, timeout_ms=1000)

    monkeypatch.setattr(
        DawController,
        "send_and_wait",
        send_and_wait_with_response,
    )
    return state


class _StubTrigger:
    """In-memory replacement for an ``os_automation`` trigger.

    ``trigger()`` either records a hit or raises the preconfigured
    exception; ``verify`` is unused by ``duplicate-channel`` but kept
    for protocol compatibility.
    """

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = 0
        self._exc = exc

    def trigger(self) -> None:
        self.calls += 1
        if self._exc is not None:
            raise self._exc

    def verify(self, queue_path: str, timeout: float = 5.0) -> bool:
        return True


def _patch_os_automation(monkeypatch, stub_trigger):
    """Replace the wired-in ``os_automation`` module so ``get_trigger``
    returns ``Ok(stub_trigger)`` and ``default_shortcut`` is stable.

    The root CLI group reads ``os_automation`` from
    ``flstudio_cli.__main__`` at invocation time, so patching the
    binding there is the smallest hook that affects every command.
    """
    from flstudio_cli.shared.utility.outcome import Ok

    class _StubAutomation:
        @staticmethod
        def get_trigger(shortcut=None, dry_run=False):
            return Ok(stub_trigger)

        @staticmethod
        def default_shortcut() -> str:
            return "alt+c"

    monkeypatch.setattr(
        "flstudio_cli.__main__.os_automation",
        _StubAutomation(),
    )


class TestDuplicateChannelEndToEnd:
    def test_success_increments_count(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        # before=4, after=5 → ok:true
        state = _install_channel_count_controller(monkeypatch, fake_transport, [4, 5])
        stub = _StubTrigger()
        _patch_os_automation(monkeypatch, stub)

        result = runner.invoke(cli, ["duplicate-channel"], obj={})

        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "duplicate_channel"
        assert payload["result"]["ok"] is True
        assert payload["result"]["before_count"] == 4
        assert payload["result"]["count"] == 5
        assert payload["result"]["shortcut"] == "alt+c"
        assert state["call"] == 2
        assert stub.calls == 1

    def test_no_change_reports_ok_false(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        # Trigger fires but FL ignored it (e.g. Channel Rack not focused
        # before keystroke landed): before == after.
        _install_channel_count_controller(monkeypatch, fake_transport, [4, 4])
        stub = _StubTrigger()
        _patch_os_automation(monkeypatch, stub)

        result = runner.invoke(cli, ["duplicate-channel"], obj={})

        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True  # envelope ok=true; only result.ok is false
        assert payload["result"]["ok"] is False
        assert payload["result"]["before_count"] == 4
        assert payload["result"]["count"] == 4

    def test_automation_failure_surfaces_hint(
        self,
        runner,
        monkeypatch,
        fake_transport,
    ):
        import subprocess

        from flstudio_cli.shared.application import envelope as Env
        from flstudio_cli.shared.presentation.exit_codes import exit_code_for

        _install_channel_count_controller(monkeypatch, fake_transport, [4, 4])
        stub = _StubTrigger(
            exc=subprocess.CalledProcessError(1, ["osascript"]),
        )
        _patch_os_automation(monkeypatch, stub)

        result = runner.invoke(cli, ["duplicate-channel"], obj={})

        assert result.exit_code == exit_code_for(Env.CODE_AUTOMATION_FAILED)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_AUTOMATION_FAILED
        assert "Accessibility" in payload["error"]["hint"]
        # The Alt+C path was attempted exactly once; we never reach the
        # second focus round-trip.
        assert stub.calls == 1
