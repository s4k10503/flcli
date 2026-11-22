"""Tests for mapping a plugin parameter's display and seeking a target."""

from __future__ import annotations

import math

import pytest

from flstudio_cli.plugin.application import param_search as S


def _hz(value: float) -> str:
    """A log-scaled cutoff: 20 Hz at 0, 20 kHz at 1."""
    hz = 20 * math.pow(1000, value)
    return f"{hz / 1000:.2f} kHz" if hz >= 1000 else f"{hz:.0f} Hz"


def _db_falling(value: float) -> str:
    return f"{-60 * value:.1f} dB"


class TestDisplayNumber:
    @pytest.mark.parametrize(
        "display,expected",
        [
            ("150 Hz", 150.0),
            ("2.5 kHz", 2500.0),
            ("-24.0 dB", -24.0),
            ("+3,5 dB", 3.5),
            ("55%", 55.0),
            ("Low Tide", None),
            ("", None),
        ],
    )
    def test_reads_the_number(self, display, expected):
        assert S.display_number(display) == expected


class TestBisectNumeric:
    def test_finds_a_rising_log_frequency(self):
        value, display = S.bisect_numeric(_hz, 150)
        assert abs(S.display_number(display) - 150) <= 1
        assert 0 < value < 1

    def test_crosses_into_khz(self):
        _, display = S.bisect_numeric(_hz, 5000)
        assert display.endswith("kHz")
        assert abs(S.display_number(display) - 5000) <= 10

    def test_finds_a_falling_display(self):
        value, display = S.bisect_numeric(_db_falling, -12)
        assert display == "-12.0 dB"
        assert abs(value - 0.2) < 0.001

    def test_skips_a_word_at_the_top_end(self):
        def cut(value: float) -> str:
            return "Off" if value == 1 else f"{0.5 + 20 * value:.1f}kHz"

        _, display = S.bisect_numeric(cut, 5000)
        assert display == "5.0kHz"

    def test_rejects_a_target_out_of_range(self):
        with pytest.raises(ValueError, match="outside"):
            S.bisect_numeric(_hz, 5)

    def test_rejects_a_label_display(self):
        with pytest.raises(ValueError, match="not a number"):
            S.bisect_numeric(lambda v: "Off", 1)


class TestFindLabel:
    _SHAPES = ("Low Tide", "Pump", "Saw", "Square")

    def _shape(self, value: float) -> str:
        return self._SHAPES[min(int(value * 4), 3)]

    def test_finds_the_first_value_with_the_label(self):
        value, display = S.find_label(self._shape, "saw")
        assert display == "Saw"
        assert self._shape(value) == "Saw"

    def test_lists_what_it_saw(self):
        with pytest.raises(ValueError, match="Low Tide, Pump, Saw, Square"):
            S.find_label(self._shape, "Sine")


def test_sweep_has_steps_plus_one_points():
    points = S.sweep(_db_falling, 4)
    assert [p["value"] for p in points] == [0, 0.25, 0.5, 0.75, 1]
    assert points[-1]["display"] == "-60.0 dB"
