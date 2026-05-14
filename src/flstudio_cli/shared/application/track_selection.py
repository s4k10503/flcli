"""Use case: track selection across the four CLI selector flags.

The CLI exposes ``--track``, ``--track-name``, ``--track-query``, and
``--track-ref`` for every mixer command.  Presentation must:

1. Validate exactly one is supplied.
2. For named/query selectors, send a ``mixer_list`` query first and
   resolve the snapshot to a concrete integer index.
3. Pass the resolved index plus the original selector echo through to
   the SysEx command.

Steps 1 and 2 are domain concerns (``refs.require_exactly_one_selector``
and ``refs.resolve_mixer_track``); step 3 is wire-format detail.  This
module is the single application seam where presentation hands off the
four CLI flags and gets back a presentation-friendly DTO + a concrete
resolver call.

Presentation imports only from here, never from ``..domain.refs``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from flstudio_cli.shared.domain.refs import (
    ByName,
    ByQuery,
    Selector,
    require_exactly_one_selector,
    resolve_mixer_track,
    selector_to_dict,
)

#: The four discriminators presentation sees back from
#: :func:`parse_track_selector_args`.  ``"index"`` is a fast path; the
#: other three need a live ``mixer_list`` resolution.
TrackSelectionMode = Literal["index", "name", "query", "ref"]


@dataclass(frozen=True, slots=True)
class TrackSelection:
    """Resolution-ready track address.

    *value* is an ``int`` for the ``"index"`` mode and a wire-format
    selector dict for the other three modes.  Presentation never has
    to construct domain selector types directly.
    """

    mode: TrackSelectionMode
    value: int | dict[str, Any]


class TrackSelectorError(ValueError):
    """Validation failure for the four CLI track-selector flags."""


def parse_track_selector_args(
    *,
    track: int | None,
    track_name: str | None,
    track_query: str | None,
    track_ref: str | None,
) -> TrackSelection:
    """Validate the four flags and return a presentation-ready DTO.

    Raises :class:`TrackSelectorError` when zero or more than one flag
    is supplied, or when ``--track-ref`` carries malformed JSON.
    """
    try:
        mode, value = require_exactly_one_selector(
            track=track,
            track_name=track_name,
            track_query=track_query,
            track_ref=track_ref,
        )
    except ValueError as exc:
        raise TrackSelectorError(str(exc)) from exc

    if mode == "track":
        return TrackSelection(mode="index", value=int(value))
    if mode == "track_name":
        sel: Selector = ByName(str(value))
        return TrackSelection(mode="name", value=selector_to_dict(sel))
    if mode == "track_query":
        sel = ByQuery(str(value))
        return TrackSelection(mode="query", value=selector_to_dict(sel))
    if mode == "track_ref":
        try:
            ref_dict = json.loads(str(value))
        except (ValueError, TypeError) as exc:
            raise TrackSelectorError(f"invalid --track-ref JSON: {exc}") from exc
        return TrackSelection(mode="ref", value=ref_dict)
    raise TrackSelectorError(f"unknown selector mode: {mode!r}")  # pragma: no cover


def resolve_track_index(
    selection: TrackSelection, mixer_snapshot: dict[str, Any]
) -> int:
    """Resolve a non-index :class:`TrackSelection` against ``mixer_list`` output.

    For ``mode == "index"`` this is a passthrough; otherwise the
    snapshot's ``tracks`` list is searched by name / query / ref dict.
    Raises :class:`ValueError` (the same error class
    :func:`resolve_mixer_track` raises) when no track matches.
    """
    if selection.mode == "index":
        assert isinstance(selection.value, int)
        return selection.value
    assert isinstance(selection.value, dict)
    return resolve_mixer_track(selection.value, mixer_snapshot)
