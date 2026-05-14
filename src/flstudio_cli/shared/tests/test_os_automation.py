"""Tests for the ``os_automation`` module."""

from __future__ import annotations

import platform

import pytest

from flstudio_cli.shared.application.automation_errors import InvalidShortcut
from flstudio_cli.shared.infrastructure import os_automation
from flstudio_cli.shared.utility.outcome import Err, Ok


class TestDryRunTrigger:
    def test_trigger_does_not_raise(self) -> None:
        trigger = os_automation.DryRunTrigger()
        trigger.trigger()  # should not raise

    def test_verify_returns_true(self, tmp_path) -> None:
        trigger = os_automation.DryRunTrigger()
        assert trigger.verify(str(tmp_path / "nonexistent.json")) is True

    def test_verify_returns_true_even_when_file_exists(self, tmp_path) -> None:
        path = tmp_path / "queue.json"
        path.write_text("{}")
        trigger = os_automation.DryRunTrigger()
        assert trigger.verify(str(path)) is True


class TestGetTrigger:
    def test_dry_run_returns_dry_run_trigger(self) -> None:
        result = os_automation.get_trigger(dry_run=True)
        assert isinstance(result, Ok)
        assert isinstance(result.value, os_automation.DryRunTrigger)

    def test_dry_run_with_custom_shortcut(self) -> None:
        result = os_automation.get_trigger("ctrl+shift+x", dry_run=True)
        assert isinstance(result, Ok)
        assert isinstance(result.value, os_automation.DryRunTrigger)

    def test_returns_platform_specific_trigger(self, monkeypatch) -> None:
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        result = os_automation.get_trigger()
        assert isinstance(result, Ok)
        assert isinstance(result.value, os_automation.WindowsTrigger)

        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        result = os_automation.get_trigger()
        assert isinstance(result, Ok)
        assert isinstance(result.value, os_automation.MacOSTrigger)

        monkeypatch.setattr(platform, "system", lambda: "Linux")
        result = os_automation.get_trigger()
        assert isinstance(result, Ok)
        assert isinstance(result.value, os_automation.LinuxTrigger)

    def test_invalid_shortcut_returns_err(self) -> None:
        result = os_automation.get_trigger("ctrl+$(evil)", dry_run=True)
        assert isinstance(result, Err)
        assert isinstance(result.error, InvalidShortcut)


class TestWindowsTrigger:
    def test_construction(self) -> None:
        t = os_automation.WindowsTrigger()
        assert t._shortcut == "ctrl+alt+i"

    def test_custom_shortcut(self) -> None:
        t = os_automation.WindowsTrigger("ctrl+shift+f5")
        assert t._shortcut == "ctrl+shift+f5"

    def test_verify_returns_true_when_file_absent(self, tmp_path) -> None:
        t = os_automation.WindowsTrigger()
        assert t.verify(str(tmp_path / "gone.json"), timeout=0.1) is True

    def test_verify_returns_false_when_file_persists(self, tmp_path) -> None:
        path = tmp_path / "still_here.json"
        path.write_text("{}")
        t = os_automation.WindowsTrigger()
        assert t.verify(str(path), timeout=0.3) is False


class TestMacOSTrigger:
    def test_construction(self) -> None:
        t = os_automation.MacOSTrigger()
        assert t._shortcut == "ctrl+alt+i"

    def test_custom_shortcut(self) -> None:
        t = os_automation.MacOSTrigger("cmd+shift+i")
        assert t._shortcut == "cmd+shift+i"


class TestLinuxTrigger:
    def test_construction(self) -> None:
        t = os_automation.LinuxTrigger()
        assert t._shortcut == "ctrl+alt+i"

    def test_custom_shortcut(self) -> None:
        t = os_automation.LinuxTrigger("super+i")
        assert t._shortcut == "super+i"

    def test_verify_returns_true_when_file_absent(self, tmp_path) -> None:
        t = os_automation.LinuxTrigger()
        assert t.verify(str(tmp_path / "gone.json"), timeout=0.1) is True

    def test_verify_returns_false_when_file_persists(self, tmp_path) -> None:
        path = tmp_path / "still_here.json"
        path.write_text("{}")
        t = os_automation.LinuxTrigger()
        assert t.verify(str(path), timeout=0.3) is False


class TestShortcutValidation:
    """Shortcut parsing rejects anything that could inject into AppleScript,
    xdotool, or pynput. This is a security boundary — keep these strict.
    """

    @pytest.mark.parametrize(
        "valid",
        [
            "ctrl+alt+i",
            "ctrl+shift+F5",
            "cmd+i",
            "shift+a",
            "ctrl+alt+shift+j",
            "super+i",
            "win+a",
            "F1",
        ],
    )
    def test_accepts_valid_shortcuts(self, valid: str) -> None:
        _mods, key = os_automation._parse_shortcut(valid)
        assert key in valid or key.lower() in valid.lower()

    @pytest.mark.parametrize(
        "malicious",
        [
            # AppleScript injection: keystroke "x"; do shell script "rm -rf /"
            'x"; do shell script "rm -rf /"',
            # Shell metacharacters
            "ctrl+alt+$(whoami)",
            "ctrl+alt+;ls",
            # Newlines that could escape the quoted string
            "ctrl+alt+i\nrm",
            # Backslash escapes
            "ctrl+alt+\\",
            # Quotation marks
            'ctrl+alt+"',
            # Unknown modifiers
            "foo+i",
            "ctrl+bar+i",
            # Multi-char non-function keys
            "ctrl+abc",
            "ctrl+F99",
            # Empty
            "",
            "+",
            "+++",
        ],
    )
    def test_rejects_malicious_or_invalid(self, malicious: str) -> None:
        with pytest.raises(ValueError):
            os_automation._parse_shortcut(malicious)

    def test_windows_trigger_rejects_injection_at_construction(self) -> None:
        with pytest.raises(ValueError):
            os_automation.WindowsTrigger('x"; echo pwned; "')

    def test_macos_trigger_rejects_injection_at_construction(self) -> None:
        with pytest.raises(ValueError):
            os_automation.MacOSTrigger('x"; do shell script "echo pwned"')

    def test_linux_trigger_rejects_injection_at_construction(self) -> None:
        with pytest.raises(ValueError):
            os_automation.LinuxTrigger("ctrl+$(whoami)")


class TestSetupInstructions:
    """Tests for the setup_instructions helper."""

    def test_returns_dict_with_required_keys(self) -> None:
        info = os_automation.setup_instructions()
        assert "platform" in info
        assert "shortcut" in info
        assert "prerequisites" in info
        assert "steps" in info
        assert "test_command" in info

    def test_default_shortcut(self) -> None:
        info = os_automation.setup_instructions()
        assert info["shortcut"] == os_automation.default_shortcut()

    def test_custom_shortcut(self) -> None:
        info = os_automation.setup_instructions("ctrl+shift+F5")
        assert info["shortcut"] == "ctrl+shift+F5"

    def test_invalid_shortcut_raises(self) -> None:
        with pytest.raises(ValueError):
            os_automation.setup_instructions("ctrl+$(evil)")

    def test_prerequisites_is_list(self) -> None:
        info = os_automation.setup_instructions()
        assert isinstance(info["prerequisites"], list)
        assert len(info["prerequisites"]) > 0

    def test_steps_is_list(self) -> None:
        info = os_automation.setup_instructions()
        assert isinstance(info["steps"], list)
        assert len(info["steps"]) > 0
