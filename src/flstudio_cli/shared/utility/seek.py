"""Find the normalised value (0..1) at which FL reads back a target number.

FL exposes many controls only as 0..1 while showing them in dB, Hz and so
on, through a curve the API does not publish. When that curve only rises
or only falls, a bisection on the read-back finds the value for a target.
The caller passes ``read(value)``, which sets the control, waits for FL to
apply it, and returns the number FL then shows (``None`` if it shows none).
"""

from __future__ import annotations

from collections.abc import Callable


class SeekError(ValueError):
    """The target cannot be reached: no number, or outside the range."""


def seek(
    read: Callable[[float], float | None],
    target: float,
    *,
    lo: float = 0.0,
    hi: float = 1.0,
    iterations: int = 16,
) -> tuple[float, float]:
    """Return ``(value, reading)`` with the reading closest to ``target``.

    Searches ``lo .. hi`` (by default the whole 0..1 range).
    """
    low_reading, high_reading = read(lo), read(hi)
    if low_reading is None or high_reading is None:
        raise SeekError(f"the read-back is not a number at {lo} or {hi}")
    low, high = sorted((low_reading, high_reading))
    if not low <= target <= high:
        raise SeekError(f"target {target} is outside {low_reading} .. {high_reading}")
    rising = high_reading >= low_reading
    best = (lo, low_reading)
    if abs(high_reading - target) < abs(low_reading - target):
        best = (hi, high_reading)
    for _ in range(iterations):
        mid = (lo + hi) / 2
        reading = read(mid)
        if reading is None:
            break
        if abs(reading - target) < abs(best[1] - target):
            best = (mid, reading)
        if (reading < target) == rising:
            lo = mid
        else:
            hi = mid
    return best
