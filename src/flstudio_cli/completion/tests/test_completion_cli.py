"""Click-level integration tests for completion CLI surface (v2 only).

Covers ``completion show`` and ``completion install`` — happy paths plus
failure paths (subprocess errors, unsupported shells, write-target
failures).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestCompletionShow:
    def test_completion_show_emits_envelope(self, runner, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0] if args else [],
                returncode=0,
                stdout="# bash completion script\n",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = runner.invoke(
            cli,
            ["completion", "show", "--shell", "bash"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "completion_show"
        assert payload["args"] == {"shell": "bash"}
        assert "bash completion script" in payload["result"]["script"]
        assert payload["result"]["shell"] == "bash"

    def test_completion_show_handles_subprocess_failure(
        self,
        runner,
        monkeypatch,
    ):
        def fake_run(*args, **kwargs):
            raise OSError("no such binary")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = runner.invoke(
            cli,
            ["completion", "show", "--shell", "zsh"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INTERNAL)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_INTERNAL
        assert payload["args"] == {"shell": "zsh"}


class TestCompletionInstall:
    def test_install_writes_script_to_target(self, runner, monkeypatch, tmp_path):
        # Redirect HOME so the install target resolves under tmp_path.
        monkeypatch.setenv("HOME", str(tmp_path))

        captured: dict[str, str] = {}

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0] if args else [],
                returncode=0,
                stdout="# fish completion script\n",
                stderr="",
            )

        def fake_atomic_write(path: str, content: str) -> None:
            captured["path"] = path
            captured["content"] = content
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content)

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            "flstudio_cli.completion.presentation.cmd_completion.Comp.atomic_write_text",
            fake_atomic_write,
        )

        result = runner.invoke(
            cli,
            ["completion", "install", "--shell", "fish"],
            obj={},
        )
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "completion_install"
        assert payload["args"] == {"shell": "fish"}
        assert payload["result"]["shell"] == "fish"
        assert payload["result"]["path"].endswith(
            ".config/fish/completions/flcli.fish",
        )
        assert captured["content"] == "# fish completion script\n"

    def test_install_rejects_unsupported_shell(
        self,
        runner,
        monkeypatch,
    ):
        # Click's Choice would normally reject this, so we bypass by
        # spoofing $SHELL to a value not in _INSTALL_TARGETS.  The
        # resolver returns the raw name and the command emits an
        # ``invalid argument`` envelope.
        monkeypatch.setenv("SHELL", "/usr/bin/tcsh")

        result = runner.invoke(cli, ["completion", "install"], obj={})

        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "completion_install"
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "tcsh" in payload["error"]["message"]

    def test_install_handles_subprocess_failure(
        self,
        runner,
        monkeypatch,
        tmp_path,
    ):
        monkeypatch.setenv("HOME", str(tmp_path))

        def fake_run(*args, **kwargs):
            raise OSError("no such binary")

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = runner.invoke(
            cli,
            ["completion", "install", "--shell", "bash"],
            obj={},
        )
        assert result.exit_code == exit_code_for(Env.CODE_INTERNAL)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["command"] == "completion_install"
        assert payload["error"]["code"] == Env.CODE_INTERNAL
