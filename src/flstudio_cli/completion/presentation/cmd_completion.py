"""Interface adapter: ``flcli completion`` — shell completion helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click

from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_helpers import _emit_success, _fail

_SUPPORTED_SHELLS = ("bash", "zsh", "fish")
_INSTALL_TARGETS: dict[str, str] = {
    "bash": "~/.bash_completion.d/flcli",
    "zsh": "~/.zfunc/_flcli",
    "fish": "~/.config/fish/completions/flcli.fish",
}


def _resolve_shell(explicit: str | None) -> str:
    """Return *explicit* (when given) else best-effort detection from ``$SHELL``."""
    return explicit or os.environ.get("SHELL", "").rsplit("/", 1)[-1] or "bash"


def _get_completion_script(shell_name: str) -> str:
    """Run Click's completion machinery and return the script text."""
    result = subprocess.run(
        ["flcli"],
        env={**os.environ, "_FLCLI_COMPLETE": f"{shell_name}_source"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout


@click.group("completion", help="Shell completion helpers.")
def group() -> None:
    pass


@group.command("show", help="Print the completion script.")
@click.option(
    "--shell",
    type=click.Choice(_SUPPORTED_SHELLS),
    default=None,
    help="Shell type (auto-detected if omitted).",
)
def show_cmd(shell: str | None) -> None:
    shell_name = _resolve_shell(shell)
    args_echo = {"shell": shell_name}
    try:
        script = _get_completion_script(shell_name)
    except (subprocess.SubprocessError, OSError) as exc:
        _fail("completion_show", str(exc), code=Env.CODE_INTERNAL, args=args_echo)
        return
    _emit_success(
        "completion_show",
        args=args_echo,
        result={"shell": shell_name, "script": script},
    )


@group.command("install", help="Install shell completion.")
@click.option(
    "--shell",
    type=click.Choice(_SUPPORTED_SHELLS),
    default=None,
    help="Shell type (auto-detected if omitted).",
)
def install_cmd(shell: str | None) -> None:
    shell_name = _resolve_shell(shell)
    args_echo = {"shell": shell_name}
    target_template = _INSTALL_TARGETS.get(shell_name)
    if not target_template:
        _fail(
            "completion_install",
            f"unsupported shell: {shell_name}",
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return
    target = str(Path(target_template).expanduser())
    try:
        script = _get_completion_script(shell_name)
        Comp.atomic_write_text(target, script)
    except (subprocess.SubprocessError, OSError) as exc:
        _fail("completion_install", str(exc), code=Env.CODE_INTERNAL, args=args_echo)
        return
    _emit_success(
        "completion_install",
        args=args_echo,
        result={"shell": shell_name, "path": target},
    )


CLI_COMMANDS: list[click.Command] = [group]
