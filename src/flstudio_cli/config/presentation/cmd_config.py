"""Interface adapter: ``flcli config`` — show resolved configuration."""

from __future__ import annotations

import click

from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.cli_helpers import _emit_success, _fail

Cfg = Comp.config


@click.group("config", help="Show resolved configuration.")
def group() -> None:
    pass


@group.command("show", help="Print the resolved config with source info.")
@click.pass_context
def show_cmd(ctx: click.Context) -> None:
    try:
        resolved = Cfg.resolve(
            cli_args={
                "port": ctx.obj.get("port"),
                "return_port": ctx.obj.get("return_port"),
                "dry_run": ctx.obj.get("dry_run") or None,
                "state_throttle_ms": ctx.obj.get("state_throttle_ms"),
            },
            config_path=ctx.obj.get("config_path"),
        )
    except Cfg.ConfigError as exc:
        _fail("config_show", str(exc), code=Env.CODE_INVALID_ARGUMENT)
        return
    _emit_success("config_show", result=resolved.to_dict())


@group.command("path", help="Print the config file path in use.")
@click.pass_context
def path_cmd(ctx: click.Context) -> None:
    path = Cfg.find_config_file(ctx.obj.get("config_path"))
    _emit_success("config_path", result={"path": path, "exists": path is not None})


CLI_COMMANDS: list[click.Command] = [group]
