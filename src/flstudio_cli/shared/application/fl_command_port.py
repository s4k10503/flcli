"""Application port: typed port for FL Studio device commands.

Wire-format strings live here, not at every batch handler's call
site.  The Port concentrates the device contract in one place so:

* renaming a wire command is a single-method change in the default
  adapter;
* a handler that calls ``fl.mixxer_volume_set(...)`` is rejected by
  pyright at build time, not at runtime;
* tests inject a recording fake that records calls without standing
  in as a SysEx wire.

The Port methods return a plain :class:`DeviceCommand`; the executor
remains responsible for actually sending it to the device.  This
keeps handlers pure (no I/O) so their tests still run without MIDI.
"""

from __future__ import annotations

from typing import Any, Protocol

from flstudio_cli.shared.application.handler_dto import DeviceCommand
from flstudio_cli.shared.application.transport_modes import PositionMode


class FlCommandPort(Protocol):
    """Typed device-command surface used by every batch handler.

    Each method carries the wire-format name and arg-dict shape so
    handlers express *intent* (``fl.play()``) rather than wire format
    (``DeviceCommand("play", {})``).
    """

    # --- transport ---------------------------------------------------------

    def play(self) -> DeviceCommand: ...
    def stop(self) -> DeviceCommand: ...
    def record(self) -> DeviceCommand: ...
    def transport_position_get(self, *, mode: PositionMode) -> DeviceCommand: ...
    def transport_position_set(
        self, *, position: float, mode: PositionMode
    ) -> DeviceCommand: ...
    def transport_loop_get(self) -> DeviceCommand: ...
    def transport_loop_toggle(self) -> DeviceCommand: ...
    def undo(self) -> DeviceCommand: ...
    def redo(self) -> DeviceCommand: ...
    def undo_history(self) -> DeviceCommand: ...

    # --- project / pattern / channel --------------------------------------

    def new_project(self) -> DeviceCommand: ...
    def new_pattern(self, *, name: str | None = None) -> DeviceCommand: ...
    def select_pattern(self, *, index: int) -> DeviceCommand: ...
    def name_pattern(self, *, index: int, name: str) -> DeviceCommand: ...
    def channel_rack_focus(self) -> DeviceCommand: ...
    def focus_channel_editor(self, *, channel: int, window: str) -> DeviceCommand: ...
    def name_channel(self, *, channel: int, name: str) -> DeviceCommand: ...
    def select_channel(self, *, index: int) -> DeviceCommand: ...
    def tempo(self, *, bpm: float) -> DeviceCommand: ...
    def set_step(
        self,
        *,
        channel: int,
        step: int,
        on: bool,
        velocity: int,
    ) -> DeviceCommand: ...

    # --- mixer ------------------------------------------------------------

    def mixer_list(self) -> DeviceCommand: ...
    def mixer_volume_get(self, *, track: int) -> DeviceCommand: ...
    def mixer_volume_set(self, *, track: int, value: float) -> DeviceCommand: ...
    def mixer_pan_get(self, *, track: int) -> DeviceCommand: ...
    def mixer_pan_set(self, *, track: int, value: float) -> DeviceCommand: ...
    def mixer_name_get(self, *, track: int) -> DeviceCommand: ...
    def mixer_name_set(self, *, track: int, name: str) -> DeviceCommand: ...
    def mixer_mute(self, *, track: int) -> DeviceCommand: ...
    def mixer_solo(self, *, track: int) -> DeviceCommand: ...
    def mixer_arm(self, *, track: int, on: bool | None = None) -> DeviceCommand: ...
    def mixer_route_set(
        self, *, src: int, dst: int, on: bool | None = None
    ) -> DeviceCommand: ...
    def mixer_link_to_channel(self, *, track: int, channel: int) -> DeviceCommand: ...

    # --- plugin -----------------------------------------------------------

    def plugin_list(self, *, channel: int) -> DeviceCommand: ...
    def plugin_params(
        self,
        *,
        channel: int,
        slot: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> DeviceCommand: ...
    def plugin_param_get(
        self,
        *,
        channel: int,
        slot: int | None = None,
        param: int | None = None,
        param_name: str | None = None,
    ) -> DeviceCommand: ...
    def plugin_param_set(
        self,
        *,
        channel: int,
        value: float,
        slot: int | None = None,
        param: int | None = None,
        param_name: str | None = None,
    ) -> DeviceCommand: ...

    # --- piano-roll -------------------------------------------------------

    def step_melody(self, *, notes: list[dict[str, Any]]) -> DeviceCommand: ...

    # --- state ------------------------------------------------------------

    def state(self, *, field: str | None = None) -> DeviceCommand: ...


def _drop_none[V](d: dict[str, V | None]) -> dict[str, V]:
    """Return *d* without the ``None`` values.

    Several wire commands accept optional fields whose absence is the
    intended sentinel (e.g. ``mixer_arm`` without ``on`` toggles).
    Constructing the dict from the keyword args and stripping ``None``
    keeps the methods declarative; the PEP 695 type parameter preserves
    the value type at the call site (no ``object`` widening).
    """
    return {k: v for k, v in d.items() if v is not None}


class DefaultFlCommands:
    """Production :class:`FlCommandPort`: builds plain :class:`DeviceCommand`.

    No state, no I/O -- a singleton fits.  The names mirror the wire
    format one-to-one so a renamed wire command shows up as a renamed
    method here, caught by pyright at every call site.
    """

    # --- transport ---------------------------------------------------------

    def play(self) -> DeviceCommand:
        return DeviceCommand("play", {})

    def stop(self) -> DeviceCommand:
        return DeviceCommand("stop", {})

    def record(self) -> DeviceCommand:
        return DeviceCommand("record", {})

    def transport_position_get(self, *, mode: PositionMode) -> DeviceCommand:
        return DeviceCommand("transport_position_get", {"mode": mode})

    def transport_position_set(
        self, *, position: float, mode: PositionMode
    ) -> DeviceCommand:
        return DeviceCommand(
            "transport_position_set", {"position": position, "mode": mode}
        )

    def transport_loop_get(self) -> DeviceCommand:
        return DeviceCommand("transport_loop_get", {})

    def transport_loop_toggle(self) -> DeviceCommand:
        return DeviceCommand("transport_loop_toggle", {})

    def undo(self) -> DeviceCommand:
        return DeviceCommand("undo", {})

    def redo(self) -> DeviceCommand:
        return DeviceCommand("redo", {})

    def undo_history(self) -> DeviceCommand:
        return DeviceCommand("undo_history", {})

    # --- project / pattern / channel --------------------------------------

    def new_project(self) -> DeviceCommand:
        return DeviceCommand("new_project", {})

    def new_pattern(self, *, name: str | None = None) -> DeviceCommand:
        args: dict[str, object] = {}
        if name is not None:
            args["name"] = name
        return DeviceCommand("new_pattern", args)

    def select_pattern(self, *, index: int) -> DeviceCommand:
        return DeviceCommand("select_pattern", {"index": index})

    def name_pattern(self, *, index: int, name: str) -> DeviceCommand:
        return DeviceCommand("name_pattern", {"index": index, "name": name})

    def channel_rack_focus(self) -> DeviceCommand:
        return DeviceCommand("channel_rack_focus", {})

    def focus_channel_editor(self, *, channel: int, window: str) -> DeviceCommand:
        return DeviceCommand(
            "focus_channel_editor", {"channel": channel, "window": window}
        )

    def name_channel(self, *, channel: int, name: str) -> DeviceCommand:
        return DeviceCommand("name_channel", {"channel": channel, "name": name})

    def select_channel(self, *, index: int) -> DeviceCommand:
        return DeviceCommand("select_channel", {"index": index})

    def tempo(self, *, bpm: float) -> DeviceCommand:
        return DeviceCommand("tempo", {"bpm": bpm})

    def set_step(
        self, *, channel: int, step: int, on: bool, velocity: int
    ) -> DeviceCommand:
        return DeviceCommand(
            "set_step",
            {"channel": channel, "step": step, "on": on, "velocity": velocity},
        )

    # --- mixer ------------------------------------------------------------

    def mixer_list(self) -> DeviceCommand:
        return DeviceCommand("mixer_list", {})

    def mixer_volume_get(self, *, track: int) -> DeviceCommand:
        return DeviceCommand("mixer_volume_get", {"track": track})

    def mixer_volume_set(self, *, track: int, value: float) -> DeviceCommand:
        return DeviceCommand("mixer_volume_set", {"track": track, "value": value})

    def mixer_pan_get(self, *, track: int) -> DeviceCommand:
        return DeviceCommand("mixer_pan_get", {"track": track})

    def mixer_pan_set(self, *, track: int, value: float) -> DeviceCommand:
        return DeviceCommand("mixer_pan_set", {"track": track, "value": value})

    def mixer_name_get(self, *, track: int) -> DeviceCommand:
        return DeviceCommand("mixer_name_get", {"track": track})

    def mixer_name_set(self, *, track: int, name: str) -> DeviceCommand:
        return DeviceCommand("mixer_name_set", {"track": track, "name": name})

    def mixer_mute(self, *, track: int) -> DeviceCommand:
        return DeviceCommand("mixer_mute", {"track": track})

    def mixer_solo(self, *, track: int) -> DeviceCommand:
        return DeviceCommand("mixer_solo", {"track": track})

    def mixer_arm(self, *, track: int, on: bool | None = None) -> DeviceCommand:
        return DeviceCommand("mixer_arm", _drop_none({"track": track, "on": on}))

    def mixer_route_set(
        self, *, src: int, dst: int, on: bool | None = None
    ) -> DeviceCommand:
        # Wire field names use ``from`` / ``to``; the Port keeps Python
        # keyword-friendly ``src`` / ``dst`` so call sites don't fight
        # the language reserved word.
        return DeviceCommand(
            "mixer_route_set", _drop_none({"from": src, "to": dst, "on": on})
        )

    def mixer_link_to_channel(self, *, track: int, channel: int) -> DeviceCommand:
        return DeviceCommand(
            "mixer_link_to_channel", {"track": track, "channel": channel}
        )

    # --- plugin -----------------------------------------------------------

    def plugin_list(self, *, channel: int) -> DeviceCommand:
        return DeviceCommand("plugin_list", {"channel": channel})

    def plugin_params(
        self,
        *,
        channel: int,
        slot: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> DeviceCommand:
        return DeviceCommand(
            "plugin_params",
            _drop_none(
                {"channel": channel, "slot": slot, "limit": limit, "offset": offset}
            ),
        )

    def plugin_param_get(
        self,
        *,
        channel: int,
        slot: int | None = None,
        param: int | None = None,
        param_name: str | None = None,
    ) -> DeviceCommand:
        return DeviceCommand(
            "plugin_param_get",
            _drop_none(
                {
                    "channel": channel,
                    "slot": slot,
                    "param": param,
                    "param_name": param_name,
                }
            ),
        )

    def plugin_param_set(
        self,
        *,
        channel: int,
        value: float,
        slot: int | None = None,
        param: int | None = None,
        param_name: str | None = None,
    ) -> DeviceCommand:
        return DeviceCommand(
            "plugin_param_set",
            _drop_none(
                {
                    "channel": channel,
                    "slot": slot,
                    "param": param,
                    "param_name": param_name,
                    "value": value,
                }
            ),
        )

    # --- piano-roll -------------------------------------------------------

    def step_melody(self, *, notes: list[dict[str, Any]]) -> DeviceCommand:
        return DeviceCommand("step_melody", {"notes": notes})

    # --- state ------------------------------------------------------------

    def state(self, *, field: str | None = None) -> DeviceCommand:
        return DeviceCommand("state", _drop_none({"field": field}))


#: Module-level singleton, named ``fl`` so handler call sites read
#: as ``fl.play()`` / ``fl.mixer_volume_set(...)``.  The instance is
#: stateless and pure, so a single module attribute suffices; tests
#: substitute via ``monkeypatch.setattr`` on the feature module that
#: imports it.
fl: FlCommandPort = DefaultFlCommands()
