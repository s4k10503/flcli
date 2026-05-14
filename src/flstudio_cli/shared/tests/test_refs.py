"""Tests for the typed selector sum type and resolver functions.

Refs are now ``ChannelRef(by=Selector)`` where ``Selector`` is the
closed sum ``ByIndex | ByName | ByQuery``.  Wire-format dict input is
still accepted at the boundary (``--track-ref`` JSON, snapshot data),
so the dict-based resolver tests below stay representative of the CLI
surface.
"""

from __future__ import annotations

import dataclasses

import pytest

from flstudio_cli.shared.domain.refs import (
    Ambiguous,
    ByIndex,
    ByName,
    ByQuery,
    ChannelRef,
    MixerTrackRef,
    NotFound,
    PatternRef,
    PluginSlotRef,
    UnknownMode,
    format_resolve_error,
    require_exactly_one_selector,
    resolve_channel,
    resolve_channel_outcome,
    resolve_mixer_track,
    resolve_mixer_track_outcome,
    resolve_pattern,
    resolve_pattern_outcome,
    selector_from_dict,
    selector_to_dict,
)
from flstudio_cli.shared.utility.outcome import Err, Ok

SNAPSHOT = {
    "channels": [
        {"index": 0, "name": "Kick"},
        {"index": 1, "name": "Snare"},
        {"index": 2, "name": "Hi-Hat"},
    ],
    "patterns": [
        {"index": 1, "name": "Verse"},
        {"index": 2, "name": "Chorus"},
    ],
    "mixer": {
        "tracks": [
            {"index": 0, "name": "Master"},
            {"index": 1, "name": "Drums"},
            {"index": 2, "name": "Bass"},
        ]
    },
}


# ---------------------------------------------------------------------------
# Selector variants
# ---------------------------------------------------------------------------


class TestSelectorVariants:
    def test_by_index_holds_only_an_index(self) -> None:
        sel = ByIndex(3)
        assert sel.index == 3

    def test_by_name_holds_only_a_name(self) -> None:
        sel = ByName("Kick")
        assert sel.name == "Kick"

    def test_by_query_holds_only_a_query(self) -> None:
        sel = ByQuery("kick")
        assert sel.query == "kick"

    def test_variants_are_frozen(self) -> None:
        sel = ByIndex(3)
        with pytest.raises(dataclasses.FrozenInstanceError):
            sel.index = 4  # type: ignore[misc]

    def test_variants_compare_by_value(self) -> None:
        assert ByIndex(3) == ByIndex(3)
        assert ByName("Kick") == ByName("Kick")
        assert ByIndex(0) != ByName("0")


class TestSelectorFromDict:
    def test_index_round_trip(self) -> None:
        sel = selector_from_dict({"mode": "index", "index": 5})
        assert sel == ByIndex(5)
        assert selector_to_dict(sel) == {"mode": "index", "index": 5}

    def test_name_round_trip(self) -> None:
        sel = selector_from_dict({"mode": "name", "name": "Kick"})
        assert sel == ByName("Kick")
        assert selector_to_dict(sel) == {"mode": "name", "name": "Kick"}

    def test_query_round_trip(self) -> None:
        sel = selector_from_dict({"mode": "query", "query": "kick"})
        assert sel == ByQuery("kick")
        assert selector_to_dict(sel) == {"mode": "query", "query": "kick"}

    def test_unknown_mode_includes_kind_in_message(self) -> None:
        with pytest.raises(ValueError, match="unknown channel ref mode"):
            selector_from_dict({"mode": "regex"}, kind="channel")

    def test_legacy_filler_keys_ignored(self) -> None:
        """Old wide-tuple dumps with None fillers still parse."""
        sel = selector_from_dict(
            {"mode": "index", "index": 2, "name": None, "query": None}
        )
        assert sel == ByIndex(2)


# ---------------------------------------------------------------------------
# Outer Refs
# ---------------------------------------------------------------------------


class TestChannelRef:
    def test_construction_wraps_a_selector(self) -> None:
        ref = ChannelRef(ByIndex(3))
        assert ref.by == ByIndex(3)

    def test_frozen(self) -> None:
        ref = ChannelRef(ByName("Kick"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.by = ByName("Snare")  # type: ignore[misc]

    def test_round_trip_to_dict_is_narrow(self) -> None:
        """Wire format only carries the discriminator and the active variant."""
        ref = ChannelRef(ByQuery("kick"))
        d = ref.to_dict()
        assert d == {"mode": "query", "query": "kick"}
        assert ChannelRef.from_dict(d) == ref


class TestMixerTrackRef:
    def test_construction_wraps_a_selector(self) -> None:
        ref = MixerTrackRef(ByIndex(0))
        assert ref.by == ByIndex(0)

    def test_round_trip_to_dict(self) -> None:
        ref = MixerTrackRef(ByName("Drums"))
        d = ref.to_dict()
        assert d == {"mode": "name", "name": "Drums"}
        assert MixerTrackRef.from_dict(d) == ref


class TestPatternRef:
    def test_construction_wraps_a_selector(self) -> None:
        ref = PatternRef(ByName("Chorus"))
        assert ref.by == ByName("Chorus")

    def test_round_trip_to_dict(self) -> None:
        ref = PatternRef(ByIndex(5))
        d = ref.to_dict()
        assert d == {"mode": "index", "index": 5}
        assert PatternRef.from_dict(d) == ref


class TestPluginSlotRef:
    def test_construction_wraps_a_selector(self) -> None:
        ref = PluginSlotRef(ByQuery("sytrus"))
        assert ref.by == ByQuery("sytrus")

    def test_round_trip_to_dict(self) -> None:
        ref = PluginSlotRef(ByName("Sytrus"))
        d = ref.to_dict()
        assert d == {"mode": "name", "name": "Sytrus"}
        assert PluginSlotRef.from_dict(d) == ref


class TestNominalDistinctness:
    """Different Refs are not interchangeable even though their shape is identical."""

    def test_channel_ref_and_pattern_ref_are_not_equal(self) -> None:
        assert ChannelRef(ByIndex(0)) != PatternRef(ByIndex(0))


# ---------------------------------------------------------------------------
# resolve_channel -- accepts typed Refs, raw Selectors, and wire dicts
# ---------------------------------------------------------------------------


class TestResolveChannel:
    def test_by_index_typed(self) -> None:
        assert resolve_channel(ChannelRef(ByIndex(2)), SNAPSHOT) == 2

    def test_by_name_typed(self) -> None:
        assert resolve_channel(ChannelRef(ByName("Snare")), SNAPSHOT) == 1

    def test_by_query_typed(self) -> None:
        assert resolve_channel(ChannelRef(ByQuery("hat")), SNAPSHOT) == 2

    def test_by_query_case_insensitive(self) -> None:
        assert resolve_channel(ChannelRef(ByQuery("KICK")), SNAPSHOT) == 0

    def test_accepts_raw_selector(self) -> None:
        assert resolve_channel(ByIndex(2), SNAPSHOT) == 2

    def test_accepts_legacy_dict(self) -> None:
        assert resolve_channel({"mode": "index", "index": 2}, SNAPSHOT) == 2
        assert resolve_channel({"mode": "name", "name": "Snare"}, SNAPSHOT) == 1
        assert resolve_channel({"mode": "query", "query": "hat"}, SNAPSHOT) == 2

    def test_name_no_match(self) -> None:
        with pytest.raises(ValueError, match="no channel with name"):
            resolve_channel(ChannelRef(ByName("Bass")), SNAPSHOT)

    def test_query_no_match(self) -> None:
        with pytest.raises(ValueError, match="no channel matching query"):
            resolve_channel(ChannelRef(ByQuery("zzz")), SNAPSHOT)

    def test_name_ambiguous(self) -> None:
        snapshot = {
            "channels": [
                {"index": 0, "name": "Kick"},
                {"index": 1, "name": "Kick"},
            ],
        }
        with pytest.raises(ValueError, match=r"ambiguous.*2.*channels"):
            resolve_channel(ChannelRef(ByName("Kick")), snapshot)

    def test_unknown_mode_in_dict(self) -> None:
        with pytest.raises(ValueError, match="unknown channel ref mode"):
            resolve_channel({"mode": "regex", "regex": ".*"}, SNAPSHOT)


# ---------------------------------------------------------------------------
# resolve_mixer_track
# ---------------------------------------------------------------------------


class TestResolveMixerTrack:
    def test_by_index_typed(self) -> None:
        assert resolve_mixer_track(MixerTrackRef(ByIndex(0)), SNAPSHOT) == 0

    def test_by_name_typed(self) -> None:
        assert resolve_mixer_track(MixerTrackRef(ByName("Bass")), SNAPSHOT) == 2

    def test_by_query_typed(self) -> None:
        assert resolve_mixer_track(MixerTrackRef(ByQuery("drum")), SNAPSHOT) == 1

    def test_by_query_case_insensitive(self) -> None:
        assert resolve_mixer_track(MixerTrackRef(ByQuery("MASTER")), SNAPSHOT) == 0

    def test_accepts_legacy_dict(self) -> None:
        assert resolve_mixer_track({"mode": "name", "name": "Bass"}, SNAPSHOT) == 2

    def test_name_no_match(self) -> None:
        with pytest.raises(ValueError, match="no mixer track with name"):
            resolve_mixer_track(MixerTrackRef(ByName("Vocals")), SNAPSHOT)

    def test_query_no_match(self) -> None:
        with pytest.raises(ValueError, match="no mixer track matching query"):
            resolve_mixer_track(MixerTrackRef(ByQuery("zzz")), SNAPSHOT)

    def test_name_ambiguous(self) -> None:
        snapshot = {
            "mixer": {
                "tracks": [
                    {"index": 0, "name": "Drums"},
                    {"index": 1, "name": "Drums"},
                ],
            },
        }
        with pytest.raises(ValueError, match=r"ambiguous.*2.*mixer tracks"):
            resolve_mixer_track(MixerTrackRef(ByName("Drums")), snapshot)

    def test_unknown_mode_in_dict(self) -> None:
        with pytest.raises(ValueError, match="unknown mixer track ref mode"):
            resolve_mixer_track({"mode": "glob"}, SNAPSHOT)


# ---------------------------------------------------------------------------
# resolve_pattern
# ---------------------------------------------------------------------------


class TestResolvePattern:
    def test_by_index_typed(self) -> None:
        assert resolve_pattern(PatternRef(ByIndex(1)), SNAPSHOT) == 1

    def test_by_name_typed(self) -> None:
        assert resolve_pattern(PatternRef(ByName("Chorus")), SNAPSHOT) == 2

    def test_by_query_typed(self) -> None:
        assert resolve_pattern(PatternRef(ByQuery("ver")), SNAPSHOT) == 1

    def test_by_query_case_insensitive(self) -> None:
        assert resolve_pattern(PatternRef(ByQuery("CHORUS")), SNAPSHOT) == 2

    def test_accepts_legacy_dict(self) -> None:
        assert resolve_pattern({"mode": "name", "name": "Chorus"}, SNAPSHOT) == 2

    def test_name_no_match(self) -> None:
        with pytest.raises(ValueError, match="no pattern with name"):
            resolve_pattern(PatternRef(ByName("Bridge")), SNAPSHOT)

    def test_query_no_match(self) -> None:
        with pytest.raises(ValueError, match="no pattern matching query"):
            resolve_pattern(PatternRef(ByQuery("zzz")), SNAPSHOT)

    def test_name_ambiguous(self) -> None:
        snapshot = {
            "patterns": [
                {"index": 1, "name": "Verse"},
                {"index": 2, "name": "Verse"},
            ],
        }
        with pytest.raises(ValueError, match=r"ambiguous.*2.*patterns"):
            resolve_pattern(PatternRef(ByName("Verse")), snapshot)

    def test_unknown_mode_in_dict(self) -> None:
        with pytest.raises(ValueError, match="unknown pattern ref mode"):
            resolve_pattern({"mode": "xpath"}, SNAPSHOT)


# ---------------------------------------------------------------------------
# require_exactly_one_selector -- unchanged in this refactor
# ---------------------------------------------------------------------------


class TestRequireExactlyOneSelector:
    def test_zero_selectors_raises(self) -> None:
        with pytest.raises(ValueError, match="none provided"):
            require_exactly_one_selector(index=None, name=None, query=None)

    def test_multiple_selectors_raises(self) -> None:
        with pytest.raises(ValueError, match="2 provided"):
            require_exactly_one_selector(index=3, name="Kick", query=None)

    def test_all_three_raises(self) -> None:
        with pytest.raises(ValueError, match="3 provided"):
            require_exactly_one_selector(index=0, name="Kick", query="kick")

    def test_one_selector_index(self) -> None:
        mode, value = require_exactly_one_selector(index=5, name=None, query=None)
        assert mode == "index"
        assert value == 5

    def test_one_selector_name(self) -> None:
        mode, value = require_exactly_one_selector(index=None, name="Snare", query=None)
        assert mode == "name"
        assert value == "Snare"

    def test_one_selector_query(self) -> None:
        mode, value = require_exactly_one_selector(index=None, name=None, query="hat")
        assert mode == "query"
        assert value == "hat"

    def test_ref_selector(self) -> None:
        """Extra keyword like 'ref' should also work."""
        mode, value = require_exactly_one_selector(
            index=None,
            name=None,
            query=None,
            ref={"mode": "index", "index": 0},
        )
        assert mode == "ref"
        assert value == {"mode": "index", "index": 0}

    def test_zero_with_no_kwargs_raises(self) -> None:
        with pytest.raises(ValueError, match="none provided"):
            require_exactly_one_selector()


# ---------------------------------------------------------------------------
# Outcome-returning resolvers
# ---------------------------------------------------------------------------


class TestResolveChannelOutcome:
    def test_ok_for_index(self) -> None:
        result = resolve_channel_outcome(ChannelRef(ByIndex(2)), SNAPSHOT)
        assert result == Ok(2)

    def test_ok_for_name(self) -> None:
        result = resolve_channel_outcome(ChannelRef(ByName("Snare")), SNAPSHOT)
        assert result == Ok(1)

    def test_err_not_found_by_name(self) -> None:
        result = resolve_channel_outcome(ChannelRef(ByName("Bass")), SNAPSHOT)
        assert result == Err(NotFound(kind="channel", selector=ByName("Bass")))

    def test_err_not_found_by_query(self) -> None:
        result = resolve_channel_outcome(ChannelRef(ByQuery("zzz")), SNAPSHOT)
        assert result == Err(NotFound(kind="channel", selector=ByQuery("zzz")))

    def test_err_ambiguous(self) -> None:
        snapshot = {
            "channels": [
                {"index": 0, "name": "Kick"},
                {"index": 1, "name": "Kick"},
            ],
        }
        result = resolve_channel_outcome(ChannelRef(ByName("Kick")), snapshot)
        assert result == Err(Ambiguous(kind="channel", name="Kick", count=2))

    def test_err_unknown_mode_in_dict(self) -> None:
        result = resolve_channel_outcome({"mode": "regex"}, SNAPSHOT)
        assert result == Err(UnknownMode(kind="channel", mode="regex"))


class TestResolveMixerTrackOutcome:
    def test_ok_for_query(self) -> None:
        result = resolve_mixer_track_outcome(MixerTrackRef(ByQuery("drum")), SNAPSHOT)
        assert result == Ok(1)

    def test_err_carries_kind(self) -> None:
        result = resolve_mixer_track_outcome(MixerTrackRef(ByName("Vocals")), SNAPSHOT)
        assert isinstance(result, Err)
        assert isinstance(result.error, NotFound)
        assert result.error.kind == "mixer track"


class TestResolvePatternOutcome:
    def test_ok_for_name(self) -> None:
        result = resolve_pattern_outcome(PatternRef(ByName("Verse")), SNAPSHOT)
        assert result == Ok(1)

    def test_err_carries_kind(self) -> None:
        result = resolve_pattern_outcome(PatternRef(ByName("Bridge")), SNAPSHOT)
        assert isinstance(result, Err)
        assert isinstance(result.error, NotFound)
        assert result.error.kind == "pattern"


class TestFormatResolveError:
    """Error messages match the historical strings the exception shim raises."""

    def test_not_found_by_name(self) -> None:
        err = NotFound(kind="channel", selector=ByName("Bass"))
        assert format_resolve_error(err) == "no channel with name 'Bass'"

    def test_not_found_by_query(self) -> None:
        err = NotFound(kind="mixer track", selector=ByQuery("zzz"))
        assert format_resolve_error(err) == "no mixer track matching query 'zzz'"

    def test_ambiguous(self) -> None:
        err = Ambiguous(kind="pattern", name="Verse", count=2)
        assert format_resolve_error(err) == "ambiguous: 2 patterns match name 'Verse'"

    def test_unknown_mode(self) -> None:
        err = UnknownMode(kind="channel", mode="regex")
        assert format_resolve_error(err) == "unknown channel ref mode: 'regex'"


class TestExceptionShimAgreement:
    """The exception-raising shim must use the same wording as format_resolve_error."""

    def test_shim_message_matches_format_helper(self) -> None:
        err = NotFound(kind="channel", selector=ByName("Bass"))
        with pytest.raises(ValueError) as exc_info:
            resolve_channel(ChannelRef(ByName("Bass")), SNAPSHOT)
        assert str(exc_info.value) == format_resolve_error(err)
