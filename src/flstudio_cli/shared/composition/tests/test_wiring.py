"""Sanity tests for the composition (DI) seam.

Why this file exists
--------------------
``shared/composition/`` wires production infrastructure into the
dispatcher.  The runtime path it constructs is exercised end-to-end by
``tests/integration/test_replay.py``, but typo-grade mistakes (a
re-export pointing at the wrong symbol, a feature whose
``BATCH_HANDLERS`` does not reach the merged registry) only surface
when a real CLI subcommand runs.  The tests here pin the *contract* of
the seam itself:

* every per-feature handler dict ends up in the merged registry
* the merged registry only carries handlers that came from a feature
  (no orphan keys snuck in)
* facade re-exports point at the actual underlying callables (the
  facade IS the call, not a wrapper)
* importing ``shared.composition`` performs no I/O — production
  singletons hold callables, not eagerly-evaluated values

Naming follows ``test_given_X_when_Y_then_Z`` so each test reads as a
behavioural specification.  The tests assert *contracts*, not exact
counts (which would brittle-break on every feature addition).
"""

from __future__ import annotations

import dataclasses
from importlib.metadata import entry_points

import pytest

from flstudio_cli.__main__ import ALL_BATCH_HANDLERS
from flstudio_cli.shared import composition as Comp
from flstudio_cli.shared.application.feature_dto import Feature
from flstudio_cli.shared.application.handler_workflow import BatchHandler


def _discover_features() -> list[Feature]:
    return [ep.load() for ep in entry_points(group="flstudio_cli.features")]


class TestHandlerRegistryWiring:
    def test_given_entry_points_when_discover_then_returns_non_empty_features(
        self,
    ) -> None:
        # Behavioural assertion: discovery actually finds something.
        # Avoids a brittle exact-list snapshot — adding a new feature
        # should not break unrelated tests.
        features = _discover_features()
        assert features, "no features discovered — entry-point group misconfigured"
        for feature in features:
            assert isinstance(feature, Feature)
            assert feature.name, "feature has empty name"

    def test_given_feature_handlers_when_merged_then_every_command_is_in_registry(
        self,
    ) -> None:
        # Pins the contract: every command a feature.batch_handlers
        # advertises is actually reachable from the merged registry.
        # Failure here means the composition root dropped a feature.
        for feature in _discover_features():
            for cmd_name in feature.batch_handlers:
                assert cmd_name in ALL_BATCH_HANDLERS, (
                    f"feature {feature.name!r} declares handler {cmd_name!r} "
                    "but the merged registry does not expose it"
                )

    def test_given_merged_registry_when_inspected_then_no_orphan_handlers_present(
        self,
    ) -> None:
        # Inverse of the previous test: every key in the merged registry
        # came either from a feature.batch_handlers or from
        # state.composition.compose() (which adds piano_roll_show).
        feature_keys: set[str] = set()
        for feature in _discover_features():
            feature_keys.update(feature.batch_handlers.keys())

        composition_layered = {"piano_roll_show"}
        expected = feature_keys | composition_layered
        orphans = set(ALL_BATCH_HANDLERS) - expected
        assert not orphans, f"unexpected handlers in merged registry: {sorted(orphans)}"

    def test_given_io_bound_handler_when_composition_runs_then_piano_roll_show_is_wired(
        self,
    ) -> None:
        # state.composition.compose() injects piano_roll_show with the
        # production PianoRollIO. Verify the layered handler reached
        # the merged registry; a refactor that drops the layering would
        # silently lose this command.
        assert "piano_roll_show" in ALL_BATCH_HANDLERS

    @pytest.mark.parametrize("name", sorted(ALL_BATCH_HANDLERS))
    def test_given_registered_command_when_looked_up_then_handler_is_callable(
        self, name: str
    ) -> None:
        handler: BatchHandler = ALL_BATCH_HANDLERS[name]
        assert callable(handler), f"handler {name!r} is not callable"


class TestCompositionFacadeReExports:
    """The facades exist *because* presentation must not import
    infrastructure directly (see [tach.toml](../../../tach.toml) and the
    docstring on `shared/composition/facades.py`).  The contract is
    that ``Comp.X`` IS the underlying callable — not a wrapper that
    could subtly drift from it.  Identity (``is``) is therefore the
    right operator: it pins the contract, not an implementation
    detail.
    """

    def test_given_atomic_write_text_when_used_via_facade_then_it_is_the_real_function(
        self,
    ) -> None:
        from flstudio_cli.shared.infrastructure.io_utils import atomic_write_text

        assert Comp.atomic_write_text is atomic_write_text

    def test_given_read_midi_file_when_used_via_facade_then_it_is_the_real_function(
        self,
    ) -> None:
        from flstudio_cli.piano_roll.infrastructure.midi_reader import read_midi_file

        assert Comp.read_midi_file is read_midi_file

    def test_given_module_facades_when_inspected_then_they_alias_their_source(
        self,
    ) -> None:
        from flstudio_cli.config.infrastructure import config as src_config
        from flstudio_cli.piano_roll.infrastructure import (
            midi_reader as src_midi_reader,
        )
        from flstudio_cli.piano_roll.infrastructure import (
            piano_roll_io as src_pr_io,
        )
        from flstudio_cli.shared.infrastructure import os_automation as src_os
        from flstudio_cli.shared.infrastructure.flp import flp as src_flp

        assert Comp.config is src_config
        assert Comp.midi_reader is src_midi_reader
        assert Comp.piano_roll_io is src_pr_io
        assert Comp.os_automation is src_os
        assert Comp.flp is src_flp


def _all_leaves_are_callable(value: object) -> bool:
    """Recurse into nested dataclasses; every leaf must be callable.

    The PRODUCTION_* singletons are dataclasses-of-dataclasses (e.g.
    ``DoctorEffects.piano_roll_io`` is itself a ``PianoRollIO``).  The
    contract we want to pin is "no leaf is a value computed at import
    time (string, int, opened file, etc.)" — every leaf must be a
    function the caller invokes at use time.
    """
    if dataclasses.is_dataclass(value):
        return all(
            _all_leaves_are_callable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        )
    return callable(value)


class TestProductionSingletonsAreImportClean:
    """The PRODUCTION_* singletons must hold callables (recursively),
    never values computed at import time.  A future regression that,
    e.g., reads a file at module init would silently pin the runtime
    behaviour to whatever was on disk when the package first loaded.
    """

    def test_given_production_piano_roll_io_when_inspected_then_every_leaf_is_callable(
        self,
    ) -> None:
        assert _all_leaves_are_callable(Comp.PRODUCTION_PIANO_ROLL_IO)

    def test_given_production_doctor_effects_when_inspected_then_every_leaf_is_callable(
        self,
    ) -> None:
        assert _all_leaves_are_callable(Comp.PRODUCTION_DOCTOR_EFFECTS)

    def test_given_production_file_system_when_inspected_then_every_leaf_is_callable(
        self,
    ) -> None:
        assert _all_leaves_are_callable(Comp.PRODUCTION_FILE_SYSTEM)


class TestBuildTransportFactorySelection:
    """build_transport branches three ways: replay > record > live.

    The integration tests in ``tests/integration/test_replay.py`` cover
    the happy path of replay end-to-end.  The tests here pin the
    *factory selection* logic — a refactor that, for example,
    swallowed FLCLI_RECORD or inverted the precedence would otherwise
    only surface in production.
    """

    def test_given_replay_env_when_build_transport_then_replay_branch_is_taken(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        trace_path = tmp_path / "trace.jsonl"
        trace_path.write_text("")  # empty trace: load_trace tolerates it

        monkeypatch.setenv("FLCLI_REPLAY", str(trace_path))
        monkeypatch.delenv("FLCLI_RECORD", raising=False)

        from flstudio_cli.shared.composition import build_transport
        from flstudio_cli.shared.infrastructure.transport.replay_sink import (
            ReplayCommandTransport,
            ReplayReturnPort,
        )

        sink, return_port, fh = build_transport()
        try:
            assert isinstance(sink, ReplayCommandTransport)
            assert isinstance(return_port, ReplayReturnPort)
            assert fh is not None
        finally:
            if fh is not None:
                fh.close()

    def test_given_no_env_vars_when_build_transport_then_live_branch_is_taken(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Stub `resolve_port` so we can detect "live path entered"
        # without depending on the host's actual MIDI configuration.
        monkeypatch.delenv("FLCLI_REPLAY", raising=False)
        monkeypatch.delenv("FLCLI_RECORD", raising=False)

        seen: list[str] = []

        def _spy_port(name: str | None, default: str) -> str:
            seen.append(name or default)
            raise RuntimeError("stop here, just checking the live path was taken")

        monkeypatch.setattr(
            "flstudio_cli.shared.composition.transport.resolve_port",
            _spy_port,
        )

        from flstudio_cli.shared.composition import build_transport

        with pytest.raises(RuntimeError, match="stop here"):
            build_transport()
        assert seen, "live MIDI path was not taken"
