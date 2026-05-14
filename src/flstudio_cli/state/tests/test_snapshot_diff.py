"""Tests for the snapshot_diff module (diff walker + assertion engine)."""

from __future__ import annotations

import pytest

from flstudio_cli.state.domain.snapshot_diff import (
    check_assertions,
    diff_snapshots,
    resolve_dotted_path,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_FULL_SNAPSHOT: dict = {
    "tempo": 128.0,
    "song_position": {"beats": 4.0, "ms": 2000.0},
    "channels": [
        {"index": 0, "name": "Kick"},
        {"index": 1, "name": "Snare"},
    ],
    "mixer": {
        "tracks": [
            {"index": 0, "name": "Master"},
            {"index": 1, "name": "Kick Bus"},
        ],
        "routing": [[1, 0]],
    },
}

# ---------------------------------------------------------------------------
# diff_snapshots
# ---------------------------------------------------------------------------


class TestDiffSnapshots:
    def test_identical_dicts_produce_empty_diff(self) -> None:
        before = {"tempo": 128.0, "is_playing": False}
        result = diff_snapshots(before, dict(before))
        assert result == {"added": [], "removed": [], "changed": []}

    def test_added_key(self) -> None:
        before: dict = {"tempo": 128.0}
        after = {"tempo": 128.0, "is_recording": True}
        result = diff_snapshots(before, after)
        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "is_recording"
        assert result["added"][0]["value"] is True
        assert result["removed"] == []
        assert result["changed"] == []

    def test_removed_key(self) -> None:
        before = {"tempo": 128.0, "old_field": 42}
        after: dict = {"tempo": 128.0}
        result = diff_snapshots(before, after)
        assert len(result["removed"]) == 1
        assert result["removed"][0]["path"] == "old_field"

    def test_changed_scalar(self) -> None:
        before = {"tempo": 120.0}
        after = {"tempo": 140.0}
        result = diff_snapshots(before, after)
        assert len(result["changed"]) == 1
        assert result["changed"][0] == {
            "path": "tempo",
            "before": 120.0,
            "after": 140.0,
        }

    def test_nested_dict_diff(self) -> None:
        before = {"mixer": {"tracks": [], "routing": [[1, 0]]}}
        after = {"mixer": {"tracks": [], "routing": [[1, 0], [2, 0]]}}
        result = diff_snapshots(before, after)
        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "mixer.routing.1"

    def test_nested_dict_changed(self) -> None:
        before = {"song_position": {"beats": 0.0, "ms": 0.0}}
        after = {"song_position": {"beats": 4.0, "ms": 2000.0}}
        result = diff_snapshots(before, after)
        assert len(result["changed"]) == 2
        paths = {c["path"] for c in result["changed"]}
        assert paths == {"song_position.beats", "song_position.ms"}

    def test_list_element_changed(self) -> None:
        before = {"channels": [{"name": "Kick"}, {"name": "Snare"}]}
        after = {"channels": [{"name": "Kick"}, {"name": "Clap"}]}
        result = diff_snapshots(before, after)
        assert len(result["changed"]) == 1
        assert result["changed"][0]["path"] == "channels.1.name"
        assert result["changed"][0]["before"] == "Snare"
        assert result["changed"][0]["after"] == "Clap"

    def test_list_element_added(self) -> None:
        before = {"patterns": [{"name": "A"}]}
        after = {"patterns": [{"name": "A"}, {"name": "B"}]}
        result = diff_snapshots(before, after)
        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "patterns.1"

    def test_list_element_removed(self) -> None:
        before = {"patterns": [{"name": "A"}, {"name": "B"}]}
        after = {"patterns": [{"name": "A"}]}
        result = diff_snapshots(before, after)
        assert len(result["removed"]) == 1
        assert result["removed"][0]["path"] == "patterns.1"

    def test_float_tolerance(self) -> None:
        before = {"volume": 0.75}
        after = {"volume": 0.75 + 1e-9}
        result = diff_snapshots(before, after)
        assert result["changed"] == []

    def test_float_beyond_tolerance(self) -> None:
        before = {"volume": 0.75}
        after = {"volume": 0.76}
        result = diff_snapshots(before, after)
        assert len(result["changed"]) == 1

    def test_empty_dicts(self) -> None:
        result = diff_snapshots({}, {})
        assert result == {"added": [], "removed": [], "changed": []}

    def test_complex_mixed_diff(self) -> None:
        before = {
            "tempo": 120.0,
            "mixer": {
                "tracks": [
                    {"index": 0, "name": "Master", "volume": 0.8},
                ],
            },
        }
        after = {
            "tempo": 140.0,
            "is_playing": True,
            "mixer": {
                "tracks": [
                    {"index": 0, "name": "Master", "volume": 1.0},
                ],
            },
        }
        result = diff_snapshots(before, after)
        assert len(result["added"]) == 1
        assert result["added"][0]["path"] == "is_playing"
        assert len(result["changed"]) == 2
        changed_paths = {c["path"] for c in result["changed"]}
        assert changed_paths == {"tempo", "mixer.tracks.0.volume"}


# ---------------------------------------------------------------------------
# check_assertions
# ---------------------------------------------------------------------------


class TestCheckAssertions:
    @pytest.fixture()
    def snapshot(self) -> dict:
        return {
            "tempo": 140.0,
            "is_playing": True,
            "channels": [
                {"index": 0, "name": "Kick", "volume": 0.78},
                {"index": 1, "name": "Snare", "volume": 0.65},
            ],
            "mixer": {
                "tracks": [
                    {"index": 0, "name": "Master", "volume": 1.0},
                ],
            },
        }

    def test_eq_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "eq", "value": 140.0},
            ],
        )
        assert failures == []

    def test_eq_fail(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "eq", "value": 120.0},
            ],
        )
        assert len(failures) == 1
        assert failures[0]["actual"] == 140.0

    def test_ne_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "ne", "value": 120.0},
            ],
        )
        assert failures == []

    def test_gt_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "gt", "value": 100.0},
            ],
        )
        assert failures == []

    def test_gte_pass_equal(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "gte", "value": 140.0},
            ],
        )
        assert failures == []

    def test_lt_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "channels.0.volume", "op": "lt", "value": 1.0},
            ],
        )
        assert failures == []

    def test_lte_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "mixer.tracks.0.volume", "op": "lte", "value": 1.0},
            ],
        )
        assert failures == []

    def test_contains_pass(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "channels.0.name", "op": "contains", "value": "Kic"},
            ],
        )
        assert failures == []

    def test_contains_fail(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "channels.0.name", "op": "contains", "value": "Bass"},
            ],
        )
        assert len(failures) == 1

    def test_unknown_path(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "nonexistent", "op": "eq", "value": 42},
            ],
        )
        assert len(failures) == 1
        assert "unknown path" in failures[0]["reason"]

    def test_unknown_operator(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "regex", "value": ".*"},
            ],
        )
        assert len(failures) == 1
        assert "unknown operator" in failures[0]["reason"]

    def test_multiple_assertions_mixed(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "eq", "value": 140.0},
                {"path": "is_playing", "op": "eq", "value": False},
                {"path": "channels.0.name", "op": "eq", "value": "Kick"},
            ],
        )
        assert len(failures) == 1
        assert failures[0]["path"] == "is_playing"

    def test_deep_nested_path(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "mixer.tracks.0.name", "op": "eq", "value": "Master"},
            ],
        )
        assert failures == []

    def test_float_tolerance_in_eq(self, snapshot: dict) -> None:
        failures = check_assertions(
            snapshot,
            [
                {"path": "tempo", "op": "eq", "value": 140.0 + 1e-9},
            ],
        )
        assert failures == []


# ---------------------------------------------------------------------------
# resolve_dotted_path
# ---------------------------------------------------------------------------


class TestResolveDottedPath:
    def test_top_level_key(self) -> None:
        assert resolve_dotted_path(_FULL_SNAPSHOT, "tempo") == 128.0

    def test_nested_dict(self) -> None:
        assert resolve_dotted_path(_FULL_SNAPSHOT, "song_position.beats") == 4.0

    def test_list_index(self) -> None:
        assert resolve_dotted_path(_FULL_SNAPSHOT, "channels.0.name") == "Kick"

    def test_deep_path(self) -> None:
        assert resolve_dotted_path(_FULL_SNAPSHOT, "mixer.tracks.1.name") == "Kick Bus"

    def test_routing_path(self) -> None:
        assert resolve_dotted_path(_FULL_SNAPSHOT, "mixer.routing.0") == [1, 0]

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown path segment"):
            resolve_dotted_path(_FULL_SNAPSHOT, "nonexistent")

    def test_unknown_nested_key_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown path segment"):
            resolve_dotted_path(_FULL_SNAPSHOT, "channels.0.nonexistent")

    def test_list_index_out_of_range_raises(self) -> None:
        with pytest.raises(KeyError, match="out of range"):
            resolve_dotted_path(_FULL_SNAPSHOT, "channels.99.name")

    def test_non_integer_list_index_raises(self) -> None:
        with pytest.raises(KeyError, match="integer"):
            resolve_dotted_path(_FULL_SNAPSHOT, "channels.abc")

    def test_traverse_into_scalar_raises(self) -> None:
        with pytest.raises(KeyError, match="cannot traverse"):
            resolve_dotted_path(_FULL_SNAPSHOT, "tempo.sub")
