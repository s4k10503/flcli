"""Domain value object: stable references and resolution for channels, mixer tracks, and patterns.

A *Ref* identifies one item inside a snapshot.  Three addressing modes
are supported -- numeric index, exact name, case-insensitive substring
search -- and each is its own value type:

* :class:`ByIndex` -- direct numeric index.
* :class:`ByName`  -- exact name match.
* :class:`ByQuery` -- case-insensitive substring search.

These three form a closed sum type :data:`Selector`.  ``match`` over a
:data:`Selector` is exhaustive (mypy / pyright will complain about a
missed case), so adding a fourth addressing mode in the future cannot
silently fall through.

Why split the discriminator from the value
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The previous shape was a single dataclass with four fields::

    @dataclass
    class ChannelRef:
        mode: str  # "index" | "name" | "query"
        index: int | None
        name: str | None
        query: str | None

That is *easy* (familiar, JSON-shaped) but not *simple* in Rich
Hickey's sense: it twines the discriminator with three optional value
slots, three of which are always ``None``.  ``ChannelRef(mode="name",
index=5)`` was structurally legal yet semantically nonsense.

The new design un-twines the discriminator from the value: each
selector variant carries exactly the data it needs, and a single
:class:`Selector` is held by the four nominally distinct outer Refs
(:class:`ChannelRef`, :class:`MixerTrackRef`, :class:`PatternRef`,
:class:`PluginSlotRef`).  Cross-domain mixups remain a type error
without runtime cost; illegal combinations are no longer expressible.

The wire format (``{"mode": "...", "<mode>": ...}``) is still the
boundary representation used for ``--track-ref`` JSON args and snapshot
input -- :func:`selector_from_dict` / :func:`selector_to_dict` handle
the conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Final, Self, assert_never

from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

__all__ = [
    "Ambiguous",
    "ByIndex",
    "ByName",
    "ByQuery",
    "ChannelRef",
    "MixerTrackRef",
    "NotFound",
    "PatternRef",
    "PluginSlotRef",
    "ResolveError",
    "Selector",
    "UnknownMode",
    "format_resolve_error",
    "require_exactly_one_selector",
    "resolve_channel",
    "resolve_channel_outcome",
    "resolve_mixer_track",
    "resolve_mixer_track_outcome",
    "resolve_pattern",
    "resolve_pattern_outcome",
    "selector_from_dict",
    "selector_to_dict",
]


# ---------------------------------------------------------------------------
# Selector sum type (closed: exactly three variants)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ByIndex:
    """Selector variant: address by zero-based numeric index."""

    index: int


@dataclass(frozen=True, slots=True)
class ByName:
    """Selector variant: address by exact name match."""

    name: str


@dataclass(frozen=True, slots=True)
class ByQuery:
    """Selector variant: address by case-insensitive substring search."""

    query: str


#: Closed sum of every legal addressing mode.  Adding a fourth mode is
#: a deliberate type-system event: every ``match`` site below stops
#: type-checking until the new variant is handled.
Selector = ByIndex | ByName | ByQuery


# ---------------------------------------------------------------------------
# Selector boundary I/O (wire <-> typed value)
# ---------------------------------------------------------------------------

_MODE_INDEX: Final[str] = "index"
_MODE_NAME: Final[str] = "name"
_MODE_QUERY: Final[str] = "query"


def selector_from_dict(data: dict[str, Any], *, kind: str = "ref") -> Selector:
    """Parse a wire-format ref dict into a typed :data:`Selector`.

    *kind* is woven into the error message so callers see ``"unknown
    channel ref mode"`` rather than a generic ``"unknown ref mode"``.

    The wire format is the historical shape ``{"mode": "<name>",
    "<name>": <value>}``; extra keys (e.g. legacy ``None`` fillers from
    pre-refactor dataclass dumps) are tolerated.
    """
    mode = data.get("mode")
    if mode == _MODE_INDEX:
        return ByIndex(int(data["index"]))
    if mode == _MODE_NAME:
        return ByName(str(data["name"]))
    if mode == _MODE_QUERY:
        return ByQuery(str(data["query"]))
    raise ValueError(f"unknown {kind} ref mode: {mode!r}")


def selector_to_dict(selector: Selector) -> dict[str, Any]:
    """Render a typed :data:`Selector` back to the wire format.

    The output is *narrow*: only the discriminator and the variant's
    own field, no ``None`` placeholders for the other variants.
    """
    match selector:
        case ByIndex(index):
            return {"mode": _MODE_INDEX, "index": index}
        case ByName(name):
            return {"mode": _MODE_NAME, "name": name}
        case ByQuery(query):
            return {"mode": _MODE_QUERY, "query": query}
        case _ as unreachable:
            assert_never(unreachable)


# ---------------------------------------------------------------------------
# Nominally distinct outer Refs (each holds one Selector)
# ---------------------------------------------------------------------------
#
# The four concrete refs are structurally identical but typed distinctly
# so a ``ChannelRef`` cannot be silently passed where a ``PatternRef`` is
# expected.  They share one ``_BaseRef`` body that holds the ``by``
# field plus the ``to_dict`` / ``from_dict`` boundary methods; each
# subclass only declares its diagnostic ``KIND`` string.
#
# Dataclass ``__eq__`` compares ``self.__class__`` so instances of
# different subclasses are unequal even with identical ``by`` values --
# the nominal-distinctness invariant is preserved.


@dataclass(frozen=True, slots=True)
class _BaseRef:
    by: Selector

    KIND: ClassVar[str] = "ref"

    def to_dict(self) -> dict[str, Any]:
        return selector_to_dict(self.by)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(selector_from_dict(data, kind=cls.KIND))


@dataclass(frozen=True, slots=True)
class ChannelRef(_BaseRef):
    """Reference to a channel rack slot."""

    KIND: ClassVar[str] = "channel"


@dataclass(frozen=True, slots=True)
class MixerTrackRef(_BaseRef):
    """Reference to a mixer track."""

    KIND: ClassVar[str] = "mixer track"


@dataclass(frozen=True, slots=True)
class PatternRef(_BaseRef):
    """Reference to a pattern."""

    KIND: ClassVar[str] = "pattern"


@dataclass(frozen=True, slots=True)
class PluginSlotRef(_BaseRef):
    """Reference to a plugin slot."""

    KIND: ClassVar[str] = "plugin slot"


# ---------------------------------------------------------------------------
# Selector validation -- "exactly one of these may be set"
# ---------------------------------------------------------------------------


def require_exactly_one_selector(**kwargs: Any) -> tuple[str, Any]:
    """Validate that exactly one selector keyword is non-``None``.

    Returns ``(mode, value)`` for the single provided selector.  Raises
    :class:`ValueError` when zero or more than one are given.

    Used by the CLI to enforce mutual exclusion across flags like
    ``--track`` / ``--track-name`` / ``--track-query`` / ``--track-ref``.
    """
    provided = {k: v for k, v in kwargs.items() if v is not None}
    if len(provided) == 0:
        names = ", ".join(sorted(kwargs))
        raise ValueError(
            f"exactly one selector required but none provided "
            f"(expected one of: {names})"
        )
    if len(provided) > 1:
        names = ", ".join(sorted(provided))
        raise ValueError(
            f"exactly one selector required but {len(provided)} provided: {names}"
        )
    mode, value = next(iter(provided.items()))
    return mode, value


# ---------------------------------------------------------------------------
# Resolve errors -- closed sum
# ---------------------------------------------------------------------------
#
# Every resolver failure is one of these three.  Adding a fourth kind
# requires updating :func:`format_resolve_error`'s ``match`` -- the
# type-checker enforces it.


@dataclass(frozen=True, slots=True)
class NotFound:
    """No item in the snapshot matched the selector.

    ``selector`` carries the original query so the shell can render a
    rich error message.  In practice ``selector`` is always
    :class:`ByName` or :class:`ByQuery`; :class:`ByIndex` cannot fail
    in this resolver because the resolver does not bounds-check
    indices (consistent with the pre-refactor behaviour).
    """

    kind: str
    selector: Selector


@dataclass(frozen=True, slots=True)
class Ambiguous:
    """A name match returned multiple items."""

    kind: str
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class UnknownMode:
    """A wire-format dict carried an unrecognised ``mode`` discriminator."""

    kind: str
    mode: Any


#: Closed sum: every legal ``resolve_*_outcome`` failure is one of these.
ResolveError = NotFound | Ambiguous | UnknownMode


def format_resolve_error(error: ResolveError) -> str:
    """Render a :data:`ResolveError` as the human-readable string the
    pre-Outcome resolvers used to raise inside :class:`ValueError`.

    Centralising the message format here means the shell layer (and
    the backward-compat exception shims below) all agree on wording.
    """
    match error:
        case NotFound(kind=kind, selector=selector):
            match selector:
                case ByName(name=name):
                    return f"no {kind} with name {name!r}"
                case ByQuery(query=query):
                    return f"no {kind} matching query {query!r}"
                case ByIndex(index=index):
                    # Unreachable in practice (ByIndex never reports
                    # NotFound), but the match must be total over the
                    # Selector sum.
                    return f"index {index} out of range for {kind}"
                case _ as unreachable_selector:
                    assert_never(unreachable_selector)
        case Ambiguous(kind=kind, name=name, count=count):
            return f"ambiguous: {count} {kind}s match name {name!r}"
        case UnknownMode(kind=kind, mode=mode):
            return f"unknown {kind} ref mode: {mode!r}"
        case _ as unreachable_error:
            assert_never(unreachable_error)


# ---------------------------------------------------------------------------
# Outcome-returning resolvers (the *new* domain API)
# ---------------------------------------------------------------------------
#
# Each ``resolve_*_outcome`` returns ``Outcome[int, ResolveError]``.
# The success/failure channel is part of the type signature, so a
# caller cannot accidentally drop the error.  Pattern-match the result
# at the use site::
#
#     match resolve_channel_outcome(ref, snapshot):
#         case Ok(value):  ...
#         case Err(error): ...


def _resolve_by_name(
    items: list[dict[str, Any]],
    name: str,
    kind: str,
) -> Outcome[int, ResolveError]:
    matches = [item for item in items if item.get("name") == name]
    if len(matches) == 0:
        return Err(NotFound(kind=kind, selector=ByName(name)))
    if len(matches) > 1:
        return Err(Ambiguous(kind=kind, name=name, count=len(matches)))
    return Ok(matches[0]["index"])


def _resolve_by_query(
    items: list[dict[str, Any]],
    query: str,
    kind: str,
) -> Outcome[int, ResolveError]:
    lower = query.lower()
    for item in items:
        if lower in item.get("name", "").lower():
            return Ok(item["index"])
    return Err(NotFound(kind=kind, selector=ByQuery(query)))


def _resolve_selector(
    selector: Selector,
    items: list[dict[str, Any]],
    kind: str,
) -> Outcome[int, ResolveError]:
    """Exhaustive dispatch on the :data:`Selector` sum type."""
    match selector:
        case ByIndex(index):
            return Ok(index)
        case ByName(name):
            return _resolve_by_name(items, name, kind)
        case ByQuery(query):
            return _resolve_by_query(items, query, kind)
        case _ as unreachable:
            assert_never(unreachable)


def _coerce(ref: Any, kind: str) -> Outcome[Selector, ResolveError]:
    """Accept typed Refs, raw Selectors, or wire dicts.

    Wire dicts may carry an unrecognised ``mode`` -- this function
    catches that as an :class:`UnknownMode` :data:`Err` rather than an
    exception, so the failure stays inside the Outcome channel.
    """
    if isinstance(ref, ByIndex | ByName | ByQuery):
        return Ok(ref)
    if isinstance(ref, ChannelRef | MixerTrackRef | PatternRef | PluginSlotRef):
        return Ok(ref.by)
    if isinstance(ref, dict):
        try:
            return Ok(selector_from_dict(ref, kind=kind))
        except ValueError:
            return Err(UnknownMode(kind=kind, mode=ref.get("mode")))
    raise TypeError(f"cannot resolve {kind} ref from {type(ref).__name__}")


def resolve_channel_outcome(
    ref: ChannelRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> Outcome[int, ResolveError]:
    """Resolve a channel ref to ``Ok(index)`` or ``Err(ResolveError)``."""
    match _coerce(ref, "channel"):
        case Err() as err:
            return err
        case Ok(selector):
            return _resolve_selector(selector, snapshot["channels"], "channel")


def resolve_mixer_track_outcome(
    ref: MixerTrackRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> Outcome[int, ResolveError]:
    """Resolve a mixer track ref to ``Ok(index)`` or ``Err(ResolveError)``."""
    match _coerce(ref, "mixer track"):
        case Err() as err:
            return err
        case Ok(selector):
            return _resolve_selector(
                selector, snapshot["mixer"]["tracks"], "mixer track"
            )


def resolve_pattern_outcome(
    ref: PatternRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> Outcome[int, ResolveError]:
    """Resolve a pattern ref to ``Ok(index)`` or ``Err(ResolveError)``."""
    match _coerce(ref, "pattern"):
        case Err() as err:
            return err
        case Ok(selector):
            return _resolve_selector(selector, snapshot["patterns"], "pattern")


# ---------------------------------------------------------------------------
# Exception-raising shims (the *shell* convenience API)
# ---------------------------------------------------------------------------
#
# The CLI shell layer is built around try/except for control flow, so
# we keep a thin shim that raises ``ValueError`` on ``Err``.  The
# message format goes through :func:`format_resolve_error` so both
# paths agree.  In-process code that wants the typed error should call
# the ``*_outcome`` variants above directly.


def _unwrap(outcome: Outcome[int, ResolveError]) -> int:
    match outcome:
        case Ok(value):
            return value
        case Err(error):
            raise ValueError(format_resolve_error(error))


def resolve_channel(
    ref: ChannelRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> int:
    """Exception-raising shim around :func:`resolve_channel_outcome`."""
    return _unwrap(resolve_channel_outcome(ref, snapshot))


def resolve_mixer_track(
    ref: MixerTrackRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> int:
    """Exception-raising shim around :func:`resolve_mixer_track_outcome`."""
    return _unwrap(resolve_mixer_track_outcome(ref, snapshot))


def resolve_pattern(
    ref: PatternRef | Selector | dict[str, Any],
    snapshot: dict[str, Any],
) -> int:
    """Exception-raising shim around :func:`resolve_pattern_outcome`."""
    return _unwrap(resolve_pattern_outcome(ref, snapshot))
