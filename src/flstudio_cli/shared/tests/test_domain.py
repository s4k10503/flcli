"""Tests for the smart constructors in :mod:`flstudio_cli.shared.domain.midi_types`
and the validation behaviour of :class:`Note`.
"""

from __future__ import annotations

import pytest

from flstudio_cli.shared.domain import midi_types as D
from flstudio_cli.shared.domain.note import Note


class TestPitchConstructor:
    def test_given_value_in_range_when_pitch_then_returns_value(self):
        assert D.pitch(60) == 60

    @pytest.mark.parametrize("bad", [-1, 128, 999])
    def test_given_out_of_range_when_pitch_then_raises_value_error(self, bad):
        with pytest.raises(ValueError, match="must be in"):
            D.pitch(bad)

    def test_given_bool_when_pitch_then_raises_type_error(self):
        with pytest.raises(TypeError, match="must be int"):
            D.pitch(True)  # type: ignore[arg-type]


class TestVelocityConstructor:
    @pytest.mark.parametrize("bad", [-1, 128])
    def test_given_out_of_range_when_velocity_then_raises(self, bad):
        with pytest.raises(ValueError, match="must be in"):
            D.velocity(bad)


class TestBpmConstructor:
    def test_given_positive_when_bpm_then_returns_float(self):
        assert D.bpm(140) == 140.0

    @pytest.mark.parametrize("bad", [0, -1, -200, 0.4, 0.999])
    def test_given_below_one_when_bpm_then_raises(self, bad):
        with pytest.raises(ValueError, match="at least 1"):
            D.bpm(bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_given_nan_or_inf_when_bpm_then_raises(self, bad):
        with pytest.raises(ValueError, match="finite"):
            D.bpm(bad)

    def test_given_value_above_999_when_bpm_then_raises(self):
        with pytest.raises(ValueError, match="at most"):
            D.bpm(1000)


class TestMidiChannelConstructor:
    @pytest.mark.parametrize("bad", [-1, 16, 100])
    def test_given_out_of_range_when_midi_channel_then_raises(self, bad):
        with pytest.raises(ValueError, match="must be in"):
            D.midi_channel(bad)


class TestStepIndexConstructor:
    def test_given_value_above_63_when_step_index_then_raises(self):
        with pytest.raises(ValueError, match="must be in"):
            D.step_index(64)


class TestPatternIndexConstructor:
    def test_given_zero_when_pattern_index_then_raises(self):
        with pytest.raises(ValueError, match="must be in"):
            D.pattern_index(0)


class TestNoteValidation:
    def test_given_pitch_above_127_when_note_of_then_raises(self):
        with pytest.raises(ValueError):
            Note.of(pitch=128)

    def test_given_negative_velocity_when_note_of_then_raises(self):
        with pytest.raises(ValueError):
            Note.of(pitch=60, velocity=-1)

    def test_given_negative_length_when_note_of_then_raises(self):
        with pytest.raises(ValueError):
            Note.of(pitch=60, length=-0.5)

    @pytest.mark.parametrize("length", [float("nan"), float("inf")])
    def test_given_non_finite_length_when_note_of_then_raises(self, length):
        with pytest.raises(ValueError, match="finite"):
            Note.of(pitch=60, length=length)


class TestNoteWithUpdaters:
    """Per-field copy methods preserve immutability and re-validate."""

    def test_with_pitch_returns_new_instance_with_updated_pitch(self):
        original = Note.of(pitch=60, velocity=100, length=1.0, position=0.5)
        updated = original.with_pitch(72)
        assert int(updated.pitch) == 72
        # other fields untouched
        assert int(updated.velocity) == 100
        assert float(updated.length) == 1.0
        assert float(updated.position) == 0.5
        # original unchanged (frozen)
        assert int(original.pitch) == 60

    def test_with_velocity_replaces_field(self):
        n = Note.of(pitch=60).with_velocity(64)
        assert int(n.velocity) == 64

    def test_with_length_replaces_field(self):
        n = Note.of(pitch=60).with_length(0.25)
        assert float(n.length) == 0.25

    def test_with_position_replaces_field(self):
        n = Note.of(pitch=60).with_position(2.5)
        assert float(n.position) == 2.5

    def test_with_pitch_revalidates(self):
        with pytest.raises(ValueError):
            Note.of(pitch=60).with_pitch(128)

    def test_with_velocity_revalidates(self):
        with pytest.raises(ValueError):
            Note.of(pitch=60).with_velocity(-1)

    def test_with_length_revalidates(self):
        with pytest.raises(ValueError):
            Note.of(pitch=60).with_length(-0.1)

    def test_with_position_revalidates_finite(self):
        with pytest.raises(ValueError, match="finite"):
            Note.of(pitch=60).with_position(float("inf"))


class TestExhaustiveAssertNever:
    def test_given_unreachable_when_assert_never_then_raises(self):
        with pytest.raises(AssertionError):
            D.assert_never("oops")  # type: ignore[arg-type]
