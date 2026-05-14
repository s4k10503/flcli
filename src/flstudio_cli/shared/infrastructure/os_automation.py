"""Infrastructure adapter: OS-level automation for triggering FL Studio Piano Roll scripts.

Simulates a keyboard shortcut to run ``flcli_import.pyscript`` without
manual menu navigation.

Platform dispatch
-----------------
:func:`get_trigger` inspects :func:`platform.system` and returns the
appropriate concrete :class:`PianoRollTrigger`:

* **Windows** -- :class:`WindowsTrigger` uses ``pynput`` to synthesise
  key presses via the Win32 ``SendInput`` API.  ``pynput`` is an
  optional dependency.
* **macOS (Darwin)** -- :class:`MacOSTrigger` shells out to
  ``osascript`` to emit an AppleScript ``keystroke`` event.  Requires
  the terminal to have Accessibility permissions.
* **Linux** -- :class:`LinuxTrigger` shells out to ``xdotool key``
  which synthesises X11 key events.  Only works under X11 (Wayland is
  not supported).
* **Dry-run / test** -- :class:`DryRunTrigger` is a no-op that always
  reports success, selected when ``dry_run=True``.

All shortcuts are validated through :func:`_parse_shortcut` before any
platform-specific code runs, preventing injection of shell or
AppleScript metacharacters.
"""

from __future__ import annotations

import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Protocol

from flstudio_cli.shared.application.automation_errors import InvalidShortcut
from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

__all__ = [
    "DryRunTrigger",
    "InvalidShortcut",
    "LinuxTrigger",
    "MacOSTrigger",
    "PianoRollTrigger",
    "WindowsTrigger",
    "default_shortcut",
    "get_trigger",
    "setup_instructions",
]


class PianoRollTrigger(Protocol):
    """Protocol for triggering the Piano Roll import script."""

    def trigger(self) -> None: ...
    def verify(self, queue_path: str, timeout: float = 5.0) -> bool: ...


_ALLOWED_MODIFIERS = frozenset(
    {
        "ctrl",
        "alt",
        "shift",
        "cmd",
        "command",
        "super",
        "win",
        "meta",
    }
)
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]$|^[Ff]([1-9]|1[0-9]|2[0-4])$")


def _parse_shortcut(shortcut: str) -> tuple[list[str], str]:
    """Parse ``shortcut`` into ``(modifiers, key)`` with strict validation.

    The key must be a single ASCII letter/digit or an ``F1``-``F24``
    function key. Modifiers must be from the allowed set. Anything else
    raises ``ValueError`` - this is the single choke point that prevents
    callers from injecting shell/AppleScript/xdotool metacharacters via
    the ``--shortcut`` CLI flag.
    """
    parts = [p.strip() for p in shortcut.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty shortcut: {shortcut!r}")
    key = parts[-1]
    modifiers = [p.lower() for p in parts[:-1]]
    for mod in modifiers:
        if mod not in _ALLOWED_MODIFIERS:
            raise ValueError(
                f"invalid modifier {mod!r} in shortcut {shortcut!r}; "
                f"allowed: {sorted(_ALLOWED_MODIFIERS)}"
            )
    if not _KEY_PATTERN.match(key):
        raise ValueError(
            f"invalid key {key!r} in shortcut {shortcut!r}; "
            f"must be A-Z, a-z, 0-9, or F1-F24"
        )
    return modifiers, key


def _poll_until_consumed(queue_path: str, timeout: float) -> bool:
    """Poll for evidence that ``flcli_import.pyscript`` ran successfully.

    Two signals count as success, so we tolerate sandboxes (FL Studio
    on macOS) where the script can't ``os.remove`` the queue file:

    * ``queue_path`` no longer exists (the canonical Win/Linux signal).
    * ``queue_path + ".done"`` exists (the marker the pyscript writes
      after a successful import).

    Returns True on success, False on timeout. The ``.done`` marker is
    cleaned up here so the next trigger starts fresh.

    Polling uses exponential backoff (20ms → 200ms cap) so the typical
    fast-finishing script returns within ~20ms instead of paying a flat
    200ms latency on every invocation.
    """
    queue = Path(queue_path)
    done = Path(queue_path + ".done")
    # Stale marker from a previous run would falsely report success.
    done.unlink(missing_ok=True)
    deadline = time.monotonic() + timeout
    interval = 0.02
    while time.monotonic() < deadline:
        if not queue.exists() or done.exists():
            done.unlink(missing_ok=True)
            return True
        time.sleep(interval)
        interval = min(interval * 2, 0.2)
    return False


class _BaseTrigger:
    """Shared lifecycle for every concrete piano-roll trigger.

    Subclasses only override :meth:`trigger`.  Construction parses and
    stores the shortcut once; :meth:`verify` is the same poll across
    every platform.
    """

    def __init__(self, shortcut: str = "ctrl+alt+i") -> None:
        self._modifiers, self._key = _parse_shortcut(shortcut)
        self._shortcut = shortcut

    def trigger(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def verify(self, queue_path: str, timeout: float = 5.0) -> bool:
        return _poll_until_consumed(queue_path, timeout)


def _send_pynput_chord(modifiers: list[str], key: str) -> None:
    """Press ``modifiers`` + ``key`` then release in reverse order via pynput.

    Imports ``pynput`` lazily so the module stays importable on systems
    without it; raises ``RuntimeError`` with an install hint if missing.
    """
    try:
        import pynput.keyboard
    except ImportError as exc:
        raise RuntimeError(
            "pynput is required for Windows auto-trigger. "
            "Install with: pip install pynput"
        ) from exc
    mod_keys = {
        "ctrl": pynput.keyboard.Key.ctrl,
        "alt": pynput.keyboard.Key.alt,
        "shift": pynput.keyboard.Key.shift,
        "cmd": pynput.keyboard.Key.cmd,
        "command": pynput.keyboard.Key.cmd,
        "super": pynput.keyboard.Key.cmd,
        "win": pynput.keyboard.Key.cmd,
        "meta": pynput.keyboard.Key.cmd,
    }
    controller = pynput.keyboard.Controller()
    pressed = [mod_keys[m] for m in modifiers]
    for m in pressed:
        controller.press(m)
    controller.press(key.lower())
    controller.release(key.lower())
    for m in reversed(pressed):
        controller.release(m)


class WindowsTrigger(_BaseTrigger):
    """Send a keyboard shortcut to FL Studio via ``pynput`` (Windows)."""

    def trigger(self) -> None:
        _send_pynput_chord(self._modifiers, self._key)


_APPLESCRIPT_MOD_MAP = {
    "ctrl": "control down",
    "alt": "option down",
    "shift": "shift down",
    "cmd": "command down",
    "command": "command down",
    "super": "command down",
    "win": "command down",
    "meta": "command down",
}


def _build_applescript_keystroke(modifiers: list[str], key: str) -> str:
    """Compose the AppleScript that focuses FL Studio and sends a keystroke.

    ``key`` and ``modifiers`` come from :func:`_parse_shortcut`, so they
    are already restricted to a safe whitelist — the f-string interpolation
    below cannot be used to escape the AppleScript literal.

    FL Studio's macOS bundle is named "FL Studio 2024.app" but its
    running process is "OsxFL"; ``tell application "FL Studio"``
    silently fails to activate either name, so we locate the process via
    System Events instead, which covers any FL Studio version naming.
    """
    mod_str = ", ".join(_APPLESCRIPT_MOD_MAP[m] for m in modifiers)
    return (
        'tell application "System Events"\n'
        '    set flProc to first process whose name is "OsxFL" '
        'or name starts with "FL Studio"\n'
        "    set frontmost of flProc to true\n"
        "end tell\n"
        "delay 0.2\n"
        f'tell application "System Events" to keystroke "{key}" '
        f"using {{{mod_str}}}"
    )


class MacOSTrigger(_BaseTrigger):
    """Send a keyboard shortcut to FL Studio via ``osascript`` (macOS)."""

    def trigger(self) -> None:
        script = _build_applescript_keystroke(self._modifiers, self._key)
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)


class LinuxTrigger(_BaseTrigger):
    """Send a keyboard shortcut to FL Studio via ``xdotool`` (Linux / X11)."""

    def trigger(self) -> None:
        subprocess.run(
            ["xdotool", "key", self._shortcut],
            check=True,
            timeout=5,
        )


class DryRunTrigger(_BaseTrigger):
    """No-op trigger for testing and dry-run mode -- never touches the OS."""

    def __init__(self, shortcut: str = "ctrl+alt+i") -> None:
        # Skip ``_parse_shortcut`` so callers can use the dry-run trigger
        # without committing to a shortcut shape.  Validation, when needed,
        # happens in ``get_trigger`` before the dry-run path is selected.
        self._shortcut = shortcut

    def trigger(self) -> None:
        pass

    def verify(self, queue_path: str, timeout: float = 5.0) -> bool:
        return True


def default_shortcut() -> str:
    """Per-platform default for the auto-trigger keystroke.

    * Windows / Linux: ``ctrl+alt+i`` -- the user assigns this via the
      right-click "Set hotkey" item on the script in Tools → Scripts.
    * macOS: ``cmd+alt+y`` -- FL Studio's built-in **"re-run last
      Piano Roll script"** chord. The macOS build doesn't expose
      per-script hotkey assignment, so we lean on this universal
      shortcut. The user must run ``flcli_import`` from Tools → Scripts
      **once** after launching FL Studio so it becomes "the last
      script"; subsequent ``--auto-trigger`` invocations replay it.
    """
    if platform.system() == "Darwin":
        return "cmd+alt+y"
    return "ctrl+alt+i"


def _trigger_for_system(system: str, shortcut: str) -> PianoRollTrigger:
    """Return the concrete trigger class matching ``system``.

    Defaults to :class:`LinuxTrigger` for any non-Windows / non-Darwin
    string, matching the prior fall-through behaviour.
    """
    if system == "Windows":
        return WindowsTrigger(shortcut)
    if system == "Darwin":
        return MacOSTrigger(shortcut)
    return LinuxTrigger(shortcut)


def get_trigger(
    shortcut: str | None = None,
    *,
    dry_run: bool = False,
) -> Outcome[PianoRollTrigger, InvalidShortcut]:
    """Return a platform-appropriate trigger as an :class:`Outcome`.

    The shortcut is validated unconditionally — even in dry-run mode — so a
    malformed or injection-laced value is rejected up front instead of
    silently being accepted by the no-op trigger.  The validation result
    flows back as ``Err(InvalidShortcut)``; the caller pattern-matches
    on the returned :class:`Outcome` rather than catching :class:`ValueError`.
    """
    resolved_shortcut = shortcut or default_shortcut()
    try:
        _parse_shortcut(resolved_shortcut)
    except ValueError as exc:
        return Err(InvalidShortcut(message=str(exc)))
    if dry_run:
        return Ok(DryRunTrigger())
    return Ok(_trigger_for_system(platform.system(), resolved_shortcut))


def _macos_setup_blocks(shortcut: str) -> tuple[list[str], list[str]]:
    """Return ``(steps, prerequisites)`` for the macOS auto-trigger.

    FL Studio macOS lacks per-script hotkey assignment; we rely on the
    built-in "re-run last Piano Roll script" chord (``cmd+alt+y``) and
    let the user prime it once after launch.
    """
    steps = [
        "1. Open FL Studio and the Piano Roll on the destination channel",
        "2. Run 'Tools → Scripts → flcli_import' once manually so it "
        "becomes the 'last script' that cmd+alt+y replays",
        f"3. Verify: pressing '{shortcut}' in FL Studio re-runs flcli_import",
        "4. After this priming, --auto-trigger works hands-free until you "
        "manually run a different Piano Roll script",
    ]
    prereqs = [
        "Grant terminal accessibility permissions (System Preferences → "
        "Privacy & Security → Accessibility)",
        "osascript is available by default on macOS",
        "Note: per-script hotkey binding is unsupported on FL Studio "
        "macOS -- this command relies on the built-in 'replay last "
        "script' shortcut",
    ]
    return steps, prereqs


def _hotkey_setup_steps(shortcut: str) -> list[str]:
    """Steps for binding ``shortcut`` to ``flcli_import`` on Windows / Linux."""
    return [
        "1. Open FL Studio",
        f"2. Bind keyboard shortcut '{shortcut}' to "
        "'Tools → Scripts → flcli_import' (right-click the script "
        "entry and choose 'Set hotkey')",
        "3. Verify: pressing the shortcut in FL Studio runs flcli_import",
    ]


def _windows_prerequisites() -> list[str]:
    return [
        "Install pynput: pip install pynput",
        "Ensure FL Studio has focus when auto-trigger runs",
    ]


def _linux_prerequisites() -> list[str]:
    return [
        "Install xdotool: sudo apt install xdotool",
        "FL Studio must be running under X11 (Wayland is not supported)",
    ]


def _setup_blocks_for_system(system: str, shortcut: str) -> tuple[list[str], list[str]]:
    """Return ``(steps, prerequisites)`` lists for the given platform."""
    if system == "Darwin":
        return _macos_setup_blocks(shortcut)
    steps = _hotkey_setup_steps(shortcut)
    prereqs = (
        _windows_prerequisites() if system == "Windows" else _linux_prerequisites()
    )
    return steps, prereqs


def setup_instructions(shortcut: str | None = None) -> dict[str, Any]:
    """Return platform-specific setup instructions for the auto-trigger.

    This is the pure data behind ``flcli piano-roll-trigger setup``.
    The returned dict contains ``platform``, ``shortcut``,
    ``prerequisites``, ``steps``, and a ready-to-paste ``test_command``.
    """
    resolved = shortcut or default_shortcut()
    _parse_shortcut(resolved)
    system = platform.system()
    steps, prereqs = _setup_blocks_for_system(system, resolved)

    return {
        "platform": system,
        "shortcut": resolved,
        "prerequisites": prereqs,
        "steps": steps,
        "test_command": (
            f"flcli queue-piano-roll --auto-trigger "
            f"--shortcut '{resolved}' <<< '60,100,1.0,0.0'"
        ),
    }
