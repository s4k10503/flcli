"""Tests for seeking a normalised value by its read-back."""

from __future__ import annotations

import pytest

from flstudio_cli.shared.utility.seek import SeekError, seek


def test_rising_curve():
    value, reading = seek(lambda v: 10 * 1600**v, 80)
    assert abs(reading - 80) < 0.1
    assert 0 < value < 1


def test_falling_curve():
    _, reading = seek(lambda v: 18 - 36 * v, -12)
    assert abs(reading + 12) < 0.01


def test_end_points_are_reachable():
    assert seek(lambda v: 36 * v - 18, 18) == (1.0, 18.0)


def test_out_of_range():
    with pytest.raises(SeekError, match="outside"):
        seek(lambda v: v, 2)


def test_no_number():
    with pytest.raises(SeekError, match="not a number"):
        seek(lambda v: None, 0)
