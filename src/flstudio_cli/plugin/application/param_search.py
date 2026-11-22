"""Use case: map a plugin parameter's 0..1 range to what the plugin shows, and find the value for a target.

FL only exposes a plugin parameter as a normalised value plus the plugin's
own display string ("150 Hz", "-24.0 dB", "Low Tide"). These helpers turn
that into something an LLM or a script can aim with:

* :func:`display_number` pulls the number out of a display string, scaled
  to the base unit (``2.5 kHz`` → 2500).
* :func:`bisect_numeric` finds the normalised value whose display reads a
  target number, assuming the display is monotonic in the value (it may
  rise or fall).
* :func:`find_label` finds the first value whose display is a given label
  (enumerated parameters such as a shape or a mode).

They are pure: the caller passes ``probe(value) -> display``, which sets the
parameter and reads the display back.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from flstudio_cli.shared.utility.seek import SeekError, seek

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def display_number(display: str) -> float | None:
    """The first number in ``display``, in base units, or ``None``.

    ``"2.5 kHz"`` → 2500.0, ``"-24.0 dB"`` → -24.0, ``"350ms"`` → 0.35 is
    *not* applied: only ``k`` (kilo) before ``Hz`` is scaled, because the
    other units FL plugins show (dB, %, ms, s) are already what a user types.
    """
    m = _NUMBER.search(display or "")
    if m is None:
        return None
    value = float(m.group().replace(",", "."))
    rest = display[m.end() :].strip().lower()
    if rest.startswith("khz"):
        value *= 1e3
    return value


def bisect_numeric(
    probe: Callable[[float], str],
    target: float,
    *,
    iterations: int = 16,
    edge_steps: int = 64,
) -> tuple[float, str]:
    """Return ``(value, display)`` closest to ``target``.

    A display may carry a word instead of a number at either end ("Off" at
    the top of a cut-off): the search then starts from the nearest value
    inside, stepping in by ``1 / edge_steps``. Raises ``ValueError`` when no
    numeric range is found, or when ``target`` lies outside it.
    """
    shown: dict[float, str] = {}

    def read(value: float) -> float | None:
        shown[value] = probe(value)
        return display_number(shown[value])

    def numeric_edge(start: int, step: int) -> float | None:
        for i in range(edge_steps // 2):
            value = (start + step * i) / edge_steps
            if read(value) is not None:
                return value
        return None

    lo, hi = numeric_edge(0, 1), numeric_edge(edge_steps, -1)
    if lo is None or hi is None or lo >= hi:
        raise ValueError(
            f"display is not a number (shows {shown.get(0.0)!r} .. {shown.get(1.0)!r})"
        )
    try:
        value, _ = seek(read, target, lo=lo, hi=hi, iterations=iterations)
    except SeekError:
        raise ValueError(
            f"target {target} is outside {shown[lo]!r} .. {shown[hi]!r}"
        ) from None
    return value, probe(value)


def find_label(
    probe: Callable[[float], str], label: str, *, steps: int = 64
) -> tuple[float, str]:
    """Return the first ``(value, display)`` whose display equals ``label``.

    Comparison ignores case and surrounding spaces. Raises ``ValueError``
    with the labels seen when none matches.
    """
    want = label.strip().lower()
    seen: list[str] = []
    for i in range(steps + 1):
        value = i / steps
        disp = probe(value)
        if disp.strip().lower() == want:
            return value, disp
        if disp.strip() and disp.strip() not in seen:
            seen.append(disp.strip())
    listed = ", ".join(seen[:12]) + (
        f", … ({len(seen)} in all)" if len(seen) > 12 else ""
    )
    raise ValueError(f"no value shows {label!r}; seen: {listed}")


def sweep(probe: Callable[[float], str], steps: int) -> list[dict[str, object]]:
    """``steps + 1`` evenly spaced ``{value, display}`` points over 0..1."""
    return [
        {"value": round(i / steps, 6), "display": probe(i / steps).strip()}
        for i in range(steps + 1)
    ]
