"""Use case: realtime piano-roll record session.

Owns the full record session: arm transport, open the realtime note
sink, stream the melody, then unarm.  The transport SysEx commands
flow through ``deps.open_controller``; the note stream flows through
the composition-supplied sink factory.  Success / failure envelopes
emit through ``deps.output``.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from flstudio_cli.piano_roll.application import note_event_scheduler as PR
from flstudio_cli.piano_roll.application.note_event_scheduler import NoteSinkFactory
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.cli_dispatcher import (
    DispatchDeps,
    emit_failure,
    emit_success,
)
from flstudio_cli.shared.application.fl_command_port import fl
from flstudio_cli.shared.domain.note import Note


def execute_realtime_record(
    deps: DispatchDeps,
    notes: Sequence[Note],
    *,
    bpm: float,
    lead_in: float,
    auto_transport: bool,
    open_note_sink: NoteSinkFactory,
    port_name: str | None,
    args_echo: dict[str, Any],
) -> None:
    """Record a melody into FL Studio's piano roll via realtime MIDI.

    Owns the controller / sink lifecycles end-to-end; emits exactly one
    envelope on completion (success or failure).
    """
    try:
        if auto_transport:
            _start_record_session(deps, bpm)
            if lead_in > 0:
                time.sleep(lead_in)

        duration_seconds = PR.open_port_and_record(
            open_note_sink, port_name, notes, bpm
        )

        if auto_transport:
            time.sleep(0.2)
            _stop_record_session(deps)
    except TimeoutError as exc:
        emit_failure(
            deps,
            "piano_roll",
            str(exc),
            code=Env.CODE_TIMEOUT,
            args=args_echo,
            hint=deps.timeout_hint,
        )
        return
    except RuntimeError as exc:
        emit_failure(
            deps,
            "piano_roll",
            str(exc),
            code=Env.CODE_PORT_NOT_FOUND,
            args=args_echo,
            hint=deps.port_hint,
        )
        return
    except (ValueError, TypeError) as exc:
        emit_failure(
            deps,
            "piano_roll",
            str(exc),
            code=Env.CODE_INVALID_ARGUMENT,
            args=args_echo,
        )
        return

    emit_success(
        deps,
        "piano_roll",
        args=args_echo,
        result={
            "count": len(notes),
            "bpm": bpm,
            "duration_seconds": round(duration_seconds, 3),
        },
    )


def _start_record_session(deps: DispatchDeps, bpm: float) -> None:
    """Set tempo, arm record, and start playback before the note stream."""
    with deps.open_controller() as controller:
        for cmd in (fl.tempo(bpm=bpm), fl.record(), fl.play()):
            controller.send_command(cmd)


def _stop_record_session(deps: DispatchDeps) -> None:
    """Stop playback and un-arm record after the note stream completes."""
    with deps.open_controller() as controller:
        for cmd in (fl.stop(), fl.record()):
            controller.send_command(cmd)
