"""Use case: ``flcli doctor`` — health / diagnostics checks.

A small, side-effect-free diagnostic collector that inspects the
pieces the CLI depends on (virtual MIDI ports, piano-roll queue/export
files) and returns a structured report. Under protocol v2 the state
snapshot is fetched synchronously via SysEx, so the ``state.json``
freshness check is gone.

Onion seam
----------
Each side-effecting check (MIDI port enumeration, queue/export path
resolution) takes its dependency as a required Callable parameter,
and :func:`collect_diagnostics` requires a :class:`DoctorEffects`
bundle.  Production wiring is the composition root's responsibility
(``__main__`` resolves it through ``ctx.obj``); the application
module itself never imports composition or infrastructure.
"""

from __future__ import annotations

import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from flstudio_cli.shared.application.midi_routing import DEFAULT_PORT_NAME
from flstudio_cli.shared.application.ports import (
    DoctorEffects,
    FileSystem,
    ListOutputPorts,
    PianoRollIO,
    PyflpProbe,
)

# ---------------------------------------------------------------------------
# Core value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Outcome of a single health check."""

    name: str
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "message": self.message,
            "details": dict(self.details),
        }


def _make_check(name: str) -> Callable[..., Diagnostic]:
    """Return a builder that produces :class:`Diagnostic` envelopes for *name*.

    All checkers in this module produce 2-4 :class:`Diagnostic` instances
    that share the same ``name`` field; binding it here eliminates that
    repetition at every call site without changing behaviour.
    """

    def _build(
        ok: bool,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> Diagnostic:
        return Diagnostic(name=name, ok=ok, message=message, details=details or {})

    return _build


@dataclass(frozen=True, slots=True)
class DiagnosticSpec:
    """Declarative description of one diagnostic check.

    *ctx_key* is the key looked up in the context dict passed to
    :func:`collect_diagnostics`.  ``None`` means the check takes no
    arguments (e.g. informational checks like ``auto_trigger``).

    *critical* marks whether a failure should cause the overall doctor
    report to be considered unhealthy (informational checks like
    ``auto_trigger`` and ``pyflp`` set this to ``False``).
    """

    name: str
    description: str
    check_fn: Callable[..., Diagnostic]
    ctx_key: str | None = None
    critical: bool = True


# ---------------------------------------------------------------------------
# Individual check functions (pure, tested directly by name)
# ---------------------------------------------------------------------------


def check_midi_port(
    port_name: str | None,
    *,
    list_output_ports: ListOutputPorts,
) -> Diagnostic:
    """Verify that a visible MIDI output port matches *port_name*.

    Relevant whenever the CLI needs to send MIDI to FL Studio.  Performs
    a case-insensitive substring match against the available output ports.
    """
    search_term = (port_name or DEFAULT_PORT_NAME).lower()
    available_ports = list_output_ports()
    matches = [p for p in available_ports if search_term in p.lower()]
    diag = _make_check("midi_port")
    base_details = {"searched_for": search_term, "available": available_ports}
    if not available_ports:
        return diag(False, "no MIDI output ports visible to this process", base_details)
    if not matches:
        return diag(False, f"no port matches {search_term!r}", base_details)
    return diag(
        True,
        f"port matches: {matches[0]}",
        {**base_details, "matched": matches},
    )


def check_piano_roll_queue(
    queue_path: str | None = None,
    *,
    piano_roll_io: PianoRollIO,
    fs: FileSystem,
) -> Diagnostic:
    """Check whether a pending piano-roll queue file exists.

    A missing file is normal (steady state); a present file means the
    user should run the FL Studio import script.
    """
    resolved = queue_path or piano_roll_io.default_queue_path()
    diag = _make_check("piano_roll_queue")
    if not fs.is_file(resolved):
        return diag(True, "no pending queue file (steady state)", {"path": resolved})
    return diag(
        True,
        "pending queue file present",
        {
            "path": resolved,
            "hint": "run Tools → Scripts → flcli_import in FL Studio's "
            "Piano Roll to consume it.",
        },
    )


def check_piano_roll_export(
    export_path: str | None = None,
    *,
    piano_roll_io: PianoRollIO,
    fs: FileSystem,
) -> Diagnostic:
    """Check whether a piano-roll export file exists and is readable.

    Relevant after running the FL Studio export script.  Reports the
    file's mtime when present.
    """
    resolved = export_path or piano_roll_io.default_export_path()
    diag = _make_check("piano_roll_export")
    # Single stat covers both "exists?" and "mtime?" with one syscall
    # and no TOCTOU window between the checks.
    try:
        st = fs.file_stat(resolved)
    except FileNotFoundError:
        return diag(
            True,
            "no piano-roll export file yet",
            {
                "path": resolved,
                "hint": "run Tools → Scripts → flcli_export in FL Studio.",
            },
        )
    except OSError as exc:
        return diag(False, f"export file unreadable: {exc}", {"path": resolved})
    return diag(True, "export file present", {"path": resolved, "mtime": st.mtime})


def check_song_position(snapshot: dict | None) -> Diagnostic:
    """Verify that ``song_position`` is readable from a live state snapshot.

    *snapshot* should be the ``result.state`` dict returned by the
    ``state`` v2 command.  When no snapshot is available (e.g. no MIDI
    port) the check is skipped with an informational message.
    """
    diag = _make_check("song_position")
    if snapshot is None:
        return diag(
            True,
            "skipped (no live snapshot available)",
            {"hint": "connect to FL Studio to verify song_position"},
        )
    position = snapshot.get("song_position")
    if position is None:
        return diag(
            False,
            "song_position is null in state snapshot",
            {"snapshot_keys": list(snapshot.keys())},
        )
    return diag(
        True,
        f"song_position readable: {position}",
        {"song_position": position},
    )


# --- Snapshot-section checks (channels / patterns / mixer) -----------------


def _check_snapshot_section(
    snapshot: dict | None,
    section: str,
    label: str,
) -> Diagnostic:
    """Generic checker for an expanded state section.

    Returns ok=True when the section is present and non-null, ok=False
    when it is null or missing, and a neutral skip when no snapshot is
    available.
    """
    diag = _make_check(label)
    if snapshot is None:
        return diag(
            True,
            f"skipped (no live snapshot for {section})",
            {"hint": "connect to FL Studio to verify " + section},
        )
    value = snapshot.get(section)
    if value is None:
        return diag(
            False,
            f"{section} is null in state snapshot",
            {"snapshot_keys": list(snapshot.keys())},
        )
    count = len(value) if isinstance(value, list) else None
    details: dict[str, Any] = {section: "present"}
    if count is not None:
        details["count"] = count
    return diag(
        True,
        f"{section} section present"
        + (f" ({count} items)" if count is not None else ""),
        details,
    )


def check_channels_section(snapshot: dict | None) -> Diagnostic:
    """Check that the ``channels`` section is present in the state snapshot."""
    return _check_snapshot_section(snapshot, "channels", "state_channels")


def check_patterns_section(snapshot: dict | None) -> Diagnostic:
    """Check that the ``patterns`` section is present in the state snapshot."""
    return _check_snapshot_section(snapshot, "patterns", "state_patterns")


def check_mixer_section(snapshot: dict | None) -> Diagnostic:
    """Check that the ``mixer`` section is present in the state snapshot."""
    return _check_snapshot_section(snapshot, "mixer", "state_mixer")


# --- Informational (always ok) checks -------------------------------------


def _check_auto_trigger_windows(diag: Callable[..., Diagnostic]) -> Diagnostic:
    try:
        import pynput  # noqa: F401

        return diag(True, "pynput available")
    except ImportError:
        return diag(True, "pynput not installed (optional)", {"installed": False})


def _check_auto_trigger_linux(diag: Callable[..., Diagnostic]) -> Diagnostic:
    if shutil.which("xdotool"):
        return diag(True, "xdotool available")
    return diag(True, "xdotool not found (optional)", {"installed": False})


def check_auto_trigger() -> Diagnostic:
    """Check whether OS automation prerequisites are available.

    Informational only (ok=True always) because auto-trigger is an
    optional feature — its absence should not fail the overall report.
    """
    diag = _make_check("auto_trigger")
    system = platform.system()
    if system == "Windows":
        return _check_auto_trigger_windows(diag)
    if system == "Darwin":
        return diag(True, "osascript available (macOS)")
    return _check_auto_trigger_linux(diag)


def check_pyflp(*, pyflp_probe: PyflpProbe) -> Diagnostic:
    """Check whether *pyflp* is importable.

    Informational only (ok=True always) — pyflp is an optional
    dependency required only for ``flp`` commands.
    """
    pyflp = pyflp_probe()
    diag = _make_check("pyflp")
    if pyflp is None:
        return diag(
            True,
            "pyflp not installed (optional)",
            {"installed": False, "hint": "required for flp commands"},
        )
    version = getattr(pyflp, "__version__", "unknown")
    return diag(True, f"pyflp {version} available")


# ---------------------------------------------------------------------------
# Diagnostic spec registry — the single source of truth for ordering
# ---------------------------------------------------------------------------

DIAGNOSTIC_SPECS: tuple[DiagnosticSpec, ...] = (
    DiagnosticSpec(
        "midi_port", "MIDI output port reachable", check_midi_port, ctx_key="port_name"
    ),
    DiagnosticSpec(
        "piano_roll_queue",
        "Piano-roll queue file status",
        check_piano_roll_queue,
        ctx_key="queue_path",
    ),
    DiagnosticSpec(
        "piano_roll_export",
        "Piano-roll export file status",
        check_piano_roll_export,
        ctx_key="export_path",
    ),
    DiagnosticSpec(
        "song_position",
        "Song position readable from snapshot",
        check_song_position,
        ctx_key="snapshot",
    ),
    DiagnosticSpec(
        "state_channels",
        "Channels section in snapshot",
        check_channels_section,
        ctx_key="snapshot",
    ),
    DiagnosticSpec(
        "state_patterns",
        "Patterns section in snapshot",
        check_patterns_section,
        ctx_key="snapshot",
    ),
    DiagnosticSpec(
        "state_mixer",
        "Mixer section in snapshot",
        check_mixer_section,
        ctx_key="snapshot",
    ),
    DiagnosticSpec(
        "auto_trigger",
        "OS automation tool available",
        check_auto_trigger,
        critical=False,
    ),
    DiagnosticSpec("pyflp", "pyflp importable", check_pyflp, critical=False),
)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _bind_effect_checks(
    bundle: DoctorEffects,
) -> dict[str, Callable[..., Diagnostic]]:
    """Pre-bind effects-using checkers to *bundle* for spec dispatch."""

    return {
        "midi_port": lambda port: check_midi_port(
            port, list_output_ports=bundle.list_output_ports
        ),
        "piano_roll_queue": lambda path: check_piano_roll_queue(
            path, piano_roll_io=bundle.piano_roll_io, fs=bundle.fs
        ),
        "piano_roll_export": lambda path: check_piano_roll_export(
            path, piano_roll_io=bundle.piano_roll_io, fs=bundle.fs
        ),
        "pyflp": lambda: check_pyflp(pyflp_probe=bundle.pyflp_probe),
    }


def _run_spec(
    spec: DiagnosticSpec,
    bound: dict[str, Callable[..., Diagnostic]],
    ctx: dict[str, Any],
) -> Diagnostic:
    """Dispatch a single :class:`DiagnosticSpec` against the bound registry."""
    fn = bound.get(spec.name, spec.check_fn)
    if spec.ctx_key is None:
        return fn()
    return fn(ctx[spec.ctx_key])


def collect_diagnostics(
    *,
    effects: DoctorEffects,
    port_name: str | None = None,
    queue_path: str | None = None,
    export_path: str | None = None,
    snapshot: dict | None = None,
) -> list[Diagnostic]:
    """Run every registered check and return results in spec order.

    ``snapshot`` is an optional state dict from a live ``state`` query.
    When provided, additional sanity checks (e.g. ``song_position``,
    ``channels``, ``patterns``, ``mixer``) are executed against it.

    ``effects`` is a required :class:`DoctorEffects` bundle: callers
    (the composition root in production, fakes in tests) must construct
    and pass it explicitly.
    """
    bound = _bind_effect_checks(effects)
    ctx: dict[str, Any] = {
        "port_name": port_name,
        "queue_path": queue_path,
        "export_path": export_path,
        "snapshot": snapshot,
    }
    return [_run_spec(spec, bound, ctx) for spec in DIAGNOSTIC_SPECS]


_CRITICAL_DIAGNOSTIC_NAMES: frozenset[str] = frozenset(
    s.name for s in DIAGNOSTIC_SPECS if s.critical
)


def overall_ok(diagnostics: list[Diagnostic]) -> bool:
    """Return True when every *critical* diagnostic passed.

    Non-critical (informational) specs are excluded from the
    healthy/unhealthy decision so that optional features like
    ``auto_trigger`` and ``pyflp`` cannot fail the overall report.
    """
    return all(d.ok for d in diagnostics if d.name in _CRITICAL_DIAGNOSTIC_NAMES)
