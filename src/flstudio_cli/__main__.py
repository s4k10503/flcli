"""Composition root: LLM-friendly CLI entry point (protocol v2 — SysEx only).

Every command — successful or not — prints a single-line JSON
document in the uniform envelope shape::

    {"ok": bool,
     "command": str,
     "args": {...},
     "result": {...} | null,
     "error": null | {"code": str, "message": str, "hint"?: str, "details"?: {...}}}

Successes populate ``result``; failures populate ``error`` and leave
``result`` null. The envelope shape and error-code taxonomy live in
:mod:`flstudio_cli.shared.application.envelope`; the POSIX exit-code projection
that lets shell scripts distinguish "fix your args" (``2``) from
"start FL Studio" (``10``) from "timeout" (``12``) lives in
:mod:`flstudio_cli.shared.presentation.exit_codes`.

Composition root
----------------
This module is the single composition root.  It walks
``entry_points(group="flstudio_cli.features")`` to discover every
feature's :class:`~flstudio_cli.shared.application.feature_dto.Feature`
constant, then concatenates their ``cli_commands`` and merges their
``batch_handlers`` dicts into the runtime registries.  The IO-bound
``piano_roll_show`` handler is layered on top via
:mod:`flstudio_cli.state.composition`.  The merged handler dict is
published on ``ctx.obj`` so ``batch run`` / ``batch stream`` can read
it without re-importing the feature graph.
"""

from __future__ import annotations

import os
from importlib.metadata import entry_points

import click

from flstudio_cli import __version__
from flstudio_cli.batch.application import batch as B
from flstudio_cli.shared.application.feature_dto import Feature
from flstudio_cli.shared.composition import (
    PRODUCTION_DOCTOR_EFFECTS,
    PRODUCTION_PIANO_ROLL_IO,
    compare_snapshot_files,
    open_piano_roll_note_sink,
    os_automation,
    read_midi_file,
    write_snapshot_file,
)
from flstudio_cli.shared.presentation.cli_helpers import DEFAULT_STATE_THROTTLE_MS
from flstudio_cli.state import composition as _state_composition

# --- feature discovery ------------------------------------------------------


def _discover_features() -> list[Feature]:
    """Load every plugin registered under the ``flstudio_cli.features`` group."""
    return [ep.load() for ep in entry_points(group="flstudio_cli.features")]


_FEATURES: list[Feature] = _discover_features()


# ``piano_roll_show`` is layered on top of the discovered features
# because it needs PianoRollIO injection -- shipping it as a static
# FEATURE.batch_handlers entry would couple the entry-point surface to
# composition-time dependencies.
ALL_BATCH_HANDLERS: dict[str, B.BatchHandler] = B.make_handlers(
    *(dict(f.batch_handlers) for f in _FEATURES),
    _state_composition.compose(piano_roll_io=PRODUCTION_PIANO_ROLL_IO),
)

# --- root group -------------------------------------------------------------


@click.group(help="LLM-friendly CLI to drive FL Studio via a virtual MIDI port.")
@click.version_option(__version__)
@click.option(
    "--port",
    "port_name",
    default=None,
    help="Substring of the MIDI output port name (default: 'flcli').",
)
@click.option(
    "--return-port",
    "return_port_name",
    default=None,
    help="Substring of the return port name (default: 'flcli-rx').",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Preview the SysEx request that would be sent without opening a MIDI port.",
)
@click.option(
    "--state-throttle-ms",
    "state_throttle_ms",
    type=int,
    default=None,
    help="Minimum interval (ms) between device-side state snapshot "
    "refreshes. Env: FLCLI_STATE_THROTTLE_MS (default: 500).",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    hidden=True,
    help="Override config file path.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    port_name: str | None,
    return_port_name: str | None,
    dry_run: bool,
    state_throttle_ms: int | None,
    config_path: str | None,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["port"] = port_name
    ctx.obj["return_port"] = return_port_name
    ctx.obj["dry_run"] = dry_run
    ctx.obj["config_path"] = config_path
    ctx.obj["batch_handlers"] = ALL_BATCH_HANDLERS
    # Composition root publishes IO/effect dependencies on ctx.obj so
    # presentation modules can resolve them at command-invocation time
    # (without import-time bindings to ``shared.composition``).
    ctx.obj["piano_roll_io"] = PRODUCTION_PIANO_ROLL_IO
    ctx.obj["doctor_effects"] = PRODUCTION_DOCTOR_EFFECTS
    ctx.obj["os_automation"] = os_automation
    ctx.obj["read_midi_file"] = read_midi_file
    ctx.obj["open_piano_roll_note_sink"] = open_piano_roll_note_sink
    ctx.obj["write_snapshot_file"] = write_snapshot_file
    ctx.obj["compare_snapshot_files"] = compare_snapshot_files
    if state_throttle_ms is not None:
        ctx.obj["state_throttle_ms"] = state_throttle_ms
    else:
        env_val = os.environ.get("FLCLI_STATE_THROTTLE_MS")
        ctx.obj["state_throttle_ms"] = (
            int(env_val) if env_val is not None else DEFAULT_STATE_THROTTLE_MS
        )


# --- subcommand registration -----------------------------------------------

for _feature in _FEATURES:
    for _command in _feature.cli_commands:
        cli.add_command(_command)


if __name__ == "__main__":  # pragma: no cover
    cli(obj={})
