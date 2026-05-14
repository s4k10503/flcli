"""Interface adapter: project / pattern / channel / tempo / step CLI commands."""

from __future__ import annotations

import subprocess
import time
from typing import Any

import click

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.automation_errors import InvalidShortcut
from flstudio_cli.shared.presentation.cli_dispatch import (
    _dispatch_command,
    _send_v2,
)
from flstudio_cli.shared.presentation.cli_helpers import _emit_success, _fail
from flstudio_cli.shared.utility.outcome import Err, Ok


@click.command("new-project", help="Create a new empty project.")
@click.pass_context
def _new_project_cmd(ctx: click.Context) -> None:
    _dispatch_command(ctx, "new_project")


@click.command("new-pattern", help="Add a new pattern, optionally with --name.")
@click.option(
    "--name",
    "name_value",
    default=None,
    help="Pattern name (any UTF-8). Omit to keep the legacy 'flcli' label.",
)
@click.pass_context
def _new_pattern_cmd(ctx: click.Context, name_value: str | None) -> None:
    args: dict[str, Any] = {}
    if name_value is not None:
        args["name"] = name_value
    _dispatch_command(ctx, "new_pattern", args)


@click.command("select-pattern", help="Select the pattern at INDEX (1-indexed).")
@click.argument("index", type=int)
@click.pass_context
def _select_pattern_cmd(ctx: click.Context, index: int) -> None:
    _dispatch_command(ctx, "select_pattern", {"index": index})


@click.command("name-pattern", help="Rename the pattern at INDEX (1-indexed).")
@click.argument("index", type=int)
@click.option(
    "--name",
    "name_value",
    required=True,
    help="The new pattern name (arbitrary UTF-8).",
)
@click.pass_context
def _name_pattern_cmd(ctx: click.Context, index: int, name_value: str) -> None:
    _dispatch_command(ctx, "name_pattern", {"index": index, "name": name_value})


_DUPLICATE_CHANNEL_SHORTCUT = "alt+c"
# Delay between focusing the Channel Rack and firing the hotkey. macOS needs
# the window-server activation to land before the keystroke registers; 0.3s
# matches the dwell used by the piano-roll auto-trigger path.
_DUPLICATE_CHANNEL_FOCUS_DELAY_S = 0.3
# After Alt+C, FL Studio re-renders the rack asynchronously. Poll the state
# read-back for a short window so the diff reflects the new channel.
_DUPLICATE_CHANNEL_VERIFY_DELAY_S = 0.4


@click.command(
    "duplicate-channel",
    help=(
        "Duplicate the currently selected channel. Sends Alt+C to FL Studio "
        "(the official Channel Rack 'Clone' hotkey) after focusing the rack. "
        "macOS requires the terminal to have Accessibility permission."
    ),
)
@click.pass_context
def _duplicate_channel_cmd(ctx: click.Context) -> None:
    command = "duplicate_channel"
    args_echo: dict[str, Any] = {}

    focus_response = _send_v2(ctx, "channel_rack_focus")
    if focus_response is None:
        # Dry-run already emitted the preview envelope.
        return
    before_count = focus_response.get("count")

    os_automation = ctx.obj["os_automation"]
    dry_run = bool(ctx.obj and ctx.obj.get("dry_run"))
    match os_automation.get_trigger(_DUPLICATE_CHANNEL_SHORTCUT, dry_run=dry_run):
        case Ok(trigger):
            pass
        case Err(InvalidShortcut(message=message)):
            _fail(
                command,
                f"invalid shortcut: {message}",
                code=Env.CODE_INVALID_ARGUMENT,
                args=args_echo,
            )
            return
        case _:
            # Forward-safety: if get_trigger ever grows a new Err variant,
            # surface it instead of falling through with `trigger` unbound.
            _fail(
                command,
                "unexpected os_automation outcome",
                code=Env.CODE_INTERNAL,
                args=args_echo,
            )
            return

    time.sleep(_DUPLICATE_CHANNEL_FOCUS_DELAY_S)
    try:
        trigger.trigger()
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        _fail(
            command,
            f"failed to send Alt+C: {exc}",
            code=Env.CODE_AUTOMATION_FAILED,
            args=args_echo,
            hint=(
                "Grant Accessibility permission to the terminal "
                "(System Settings → Privacy & Security → Accessibility)."
            ),
        )
        return

    time.sleep(_DUPLICATE_CHANNEL_VERIFY_DELAY_S)
    after_response = _send_v2(ctx, "channel_rack_focus")
    after_count = after_response.get("count") if after_response else None

    ok_inserted = (
        isinstance(before_count, int)
        and isinstance(after_count, int)
        and after_count > before_count
    )
    _emit_success(
        command,
        args=args_echo,
        result={
            "ok": ok_inserted,
            "count": after_count,
            "before_count": before_count,
            "shortcut": _DUPLICATE_CHANNEL_SHORTCUT,
        },
    )


@click.command(
    "name-channel",
    help="Set a channel's name. Arbitrary UTF-8 strings are supported.",
)
@click.argument("channel", type=int)
@click.option(
    "--name",
    "name_value",
    required=True,
    help="The channel name (arbitrary UTF-8 string).",
)
@click.pass_context
def _name_channel_cmd(ctx: click.Context, channel: int, name_value: str) -> None:
    _dispatch_command(ctx, "name_channel", {"channel": channel, "name": name_value})


@click.command("select-channel", help="Select a channel by index.")
@click.argument("index", type=int)
@click.pass_context
def _select_channel_cmd(ctx: click.Context, index: int) -> None:
    _dispatch_command(ctx, "select_channel", {"index": index})


@click.command(
    "focus-channel-editor",
    help=(
        "Open and focus an editor for the channel at INDEX. "
        "Use --window piano-roll to surface the Piano Roll (default), "
        "or --window plugin to focus the channel's sampler/plugin editor."
    ),
)
@click.argument("index", type=int)
@click.option(
    "--window",
    type=click.Choice(["piano-roll", "plugin"]),
    default="piano-roll",
    show_default=True,
    help="Which editor to focus.",
)
@click.pass_context
def _focus_channel_editor_cmd(ctx: click.Context, index: int, window: str) -> None:
    _dispatch_command(
        ctx,
        "focus_channel_editor",
        {"channel": index, "window": window.replace("-", "_")},
    )


@click.command("tempo", help="Set the project tempo (BPM).")
@click.argument("bpm", type=float)
@click.pass_context
def _tempo_cmd(ctx: click.Context, bpm: float) -> None:
    _dispatch_command(ctx, "tempo", {"bpm": bpm})


@click.command("step", help="Toggle a step: CHANNEL STEP ON (on=1/0).")
@click.argument("channel", type=int)
@click.argument("step", type=int)
@click.argument("on", type=int)
@click.option("--velocity", "-v", default=100, show_default=True, type=int)
@click.pass_context
def _step_cmd(
    ctx: click.Context,
    channel: int,
    step: int,
    on: int,
    velocity: int,
) -> None:
    _dispatch_command(
        ctx,
        "set_step",
        {"channel": channel, "step": step, "on": bool(on), "velocity": velocity},
    )


CLI_COMMANDS: list[click.Command] = [
    _new_project_cmd,
    _new_pattern_cmd,
    _select_pattern_cmd,
    _name_pattern_cmd,
    _duplicate_channel_cmd,
    _name_channel_cmd,
    _select_channel_cmd,
    _focus_channel_editor_cmd,
    _tempo_cmd,
    _step_cmd,
]
