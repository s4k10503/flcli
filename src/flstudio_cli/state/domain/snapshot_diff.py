"""Domain service: recursive JSON diff and assertion engine for state snapshots.

Used by ``flcli snapshot`` and ``flcli diff`` to compare before/after
states and verify that a batch of commands produced the expected delta.
Pure functions only -- no I/O, no side effects.

Assertion modelling
~~~~~~~~~~~~~~~~~~~
The set of legal operators is a closed sum :data:`AssertionOp` rather
than a string-keyed dispatch dict.  ``assertion_from_dict`` parses the
wire-format ``{"path", "op", "value"}`` dict at the boundary and
returns ``Outcome[Assertion, UnknownOp]`` -- unknown operators are
caught at parse time, not at evaluation time, so the failure path is
both typed and exhaustive (parse, don't validate).

Per-assertion outcomes flow through :data:`AssertionFailure` (also a
closed sum) so :func:`check_assertions` can ``match`` over the
possibilities; the historical dict-shaped return value is preserved at
the boundary via :func:`_failure_to_dict`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, assert_never

from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome

# FL Studio reports float parameters (volume, pan, tempo) with limited
# precision (~6 significant digits).  1e-6 absorbs rounding noise from
# the FL Studio scripting API without masking meaningful changes to
# user-visible knob positions.
_FLOAT_EPSILON: float = 1e-6


def resolve_dotted_path(obj: Any, path: str) -> Any:
    """Walk a dotted path like ``channels.0.name`` through nested dicts/lists.

    Raises :class:`KeyError` for unknown keys and out-of-range indices.
    Snapshots flow through this module as plain ``dict[str, Any]``: the
    device script returns JSON, and the CLI diffs / asserts JSON, so a
    typed FLState would only re-encode shape we never traverse on the
    host side.
    """
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"unknown path segment: {part!r}")
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                raise KeyError(f"list index must be an integer, got {part!r}") from None
            if idx < 0 or idx >= len(current):
                raise KeyError(f"list index {idx} out of range (length {len(current)})")
            current = current[idx]
        else:
            raise KeyError(f"cannot traverse into {type(current).__name__} at {part!r}")
    return current


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two values, tolerating float drift."""
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, abs_tol=_FLOAT_EPSILON)
    return a == b


def diff_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    _prefix: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Return ``{"added": [...], "removed": [...], "changed": [...]}``."""
    acc = _DiffAcc()
    _walk_dict(before, after, _prefix, acc)
    return acc.as_dict()


#: Sentinel for "no value at this key/index" in :func:`_walk_dict` and
#: :func:`_diff_pair`.  Internal implementation detail of the diff walker --
#: not part of any closed sum exposed at the module boundary.
_MISSING: Any = object()


@dataclass(frozen=True, slots=True)
class _DiffAcc:
    """Accumulator for the three diff buckets.

    Bundles the ``added``/``removed``/``changed`` lists so the recursive
    walkers can pass a single argument instead of three parallel lists.
    The dataclass itself is frozen — the lists are mutated via
    ``append`` from the walkers, but the field references never change.
    """

    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {"added": self.added, "removed": self.removed, "changed": self.changed}


def _join_path(prefix: str, segment: str) -> str:
    """Join *prefix* and *segment* with ``.``; the first segment has no dot."""
    return segment if not prefix else f"{prefix}.{segment}"


def _walk_dict(
    before: dict[str, Any],
    after: dict[str, Any],
    prefix: str,
    acc: _DiffAcc,
) -> None:
    """Diff every key in ``before | after`` and dispatch to :func:`_diff_pair`."""
    for key in sorted(set(before) | set(after)):
        _diff_pair(
            _join_path(prefix, key),
            before.get(key, _MISSING),
            after.get(key, _MISSING),
            acc,
        )


def _walk_list(
    before: list[Any],
    after: list[Any],
    prefix: str,
    acc: _DiffAcc,
) -> None:
    """Diff lists element-wise; missing tail elements become add/remove."""
    for i in range(max(len(before), len(after))):
        _diff_pair(
            _join_path(prefix, str(i)),
            before[i] if i < len(before) else _MISSING,
            after[i] if i < len(after) else _MISSING,
            acc,
        )


def _diff_pair(path: str, bv: Any, av: Any, acc: _DiffAcc) -> None:
    """Diff one before/after pair, recursing into matching containers."""
    if bv is _MISSING:
        acc.added.append({"path": path, "value": av})
        return
    if av is _MISSING:
        acc.removed.append({"path": path, "value": bv})
        return
    if isinstance(bv, dict) and isinstance(av, dict):
        _walk_dict(bv, av, path, acc)
        return
    if isinstance(bv, list) and isinstance(av, list):
        _walk_list(bv, av, path, acc)
        return
    if not _values_equal(bv, av):
        acc.changed.append({"path": path, "before": bv, "after": av})


# --- Assertion engine -------------------------------------------------------
#
# The set of legal operators is captured as a closed sum so unknown
# operators surface at parse time rather than evaluation time, and
# ``match`` over :data:`AssertionOp` is exhaustive.


@dataclass(frozen=True, slots=True)
class Eq:
    """Operator: actual equals expected (within float tolerance)."""


@dataclass(frozen=True, slots=True)
class Ne:
    """Operator: actual differs from expected."""


@dataclass(frozen=True, slots=True)
class Gt:
    """Operator: actual is strictly greater than expected."""


@dataclass(frozen=True, slots=True)
class Gte:
    """Operator: actual is greater-than-or-equal to expected."""


@dataclass(frozen=True, slots=True)
class Lt:
    """Operator: actual is strictly less than expected."""


@dataclass(frozen=True, slots=True)
class Lte:
    """Operator: actual is less-than-or-equal to expected."""


@dataclass(frozen=True, slots=True)
class Contains:
    """Operator: ``expected in actual`` (string substring or list membership)."""


#: Closed sum of every legal assertion operator.
AssertionOp = Eq | Ne | Gt | Gte | Lt | Lte | Contains


_OP_NAMES: dict[str, AssertionOp] = {
    "eq": Eq(),
    "ne": Ne(),
    "gt": Gt(),
    "gte": Gte(),
    "lt": Lt(),
    "lte": Lte(),
    "contains": Contains(),
}


def _op_name(op: AssertionOp) -> str:
    """Reverse :data:`_OP_NAMES`; used to render failures back to wire form."""
    match op:
        case Eq():
            return "eq"
        case Ne():
            return "ne"
        case Gt():
            return "gt"
        case Gte():
            return "gte"
        case Lt():
            return "lt"
        case Lte():
            return "lte"
        case Contains():
            return "contains"
        case _ as unreachable:
            assert_never(unreachable)


def _evaluate(op: AssertionOp, actual: Any, expected: Any) -> bool:
    """Apply *op* to ``(actual, expected)``; total over the operator sum."""
    match op:
        case Eq():
            return _values_equal(actual, expected)
        case Ne():
            return not _values_equal(actual, expected)
        case Gt():
            return actual > expected
        case Gte():
            return actual >= expected
        case Lt():
            return actual < expected
        case Lte():
            return actual <= expected
        case Contains():
            return expected in actual
        case _ as unreachable:
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class Assertion:
    """A typed assertion: dotted path, operator, expected value."""

    path: str
    op: AssertionOp
    value: Any


@dataclass(frozen=True, slots=True)
class UnknownOp:
    """Failure: the wire dict carried an unrecognised operator."""

    path: str
    op: str


@dataclass(frozen=True, slots=True)
class PathMissing:
    """Failure: the dotted path could not be resolved against the snapshot."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class OpFailed:
    """Failure: the operator returned False on the resolved value."""

    path: str
    op: AssertionOp
    expected: Any
    actual: Any


#: Closed sum of every legal assertion failure.
AssertionFailure = UnknownOp | PathMissing | OpFailed


def assertion_from_dict(
    data: dict[str, Any],
) -> Outcome[Assertion, UnknownOp]:
    """Parse a wire-format assertion dict into a typed :class:`Assertion`.

    Unknown operators surface as :class:`UnknownOp` here -- the
    failure stays inside the Outcome channel, so the caller does not
    have to wrap the call in try/except.
    """
    path = str(data["path"])
    raw_op = str(data["op"])
    op = _OP_NAMES.get(raw_op)
    if op is None:
        return Err(UnknownOp(path=path, op=raw_op))
    return Ok(Assertion(path=path, op=op, value=data.get("value")))


def _failure_to_dict(failure: AssertionFailure) -> dict[str, Any]:
    """Render a typed failure back to the historical wire shape.

    Boundary helper: lets :func:`check_assertions` keep its
    ``list[dict]`` return type so the CLI and existing tests do not
    have to change their consumption pattern.
    """
    match failure:
        case UnknownOp(path=path, op=op):
            return {"path": path, "reason": f"unknown operator: {op!r}"}
        case PathMissing(path=path, reason=reason):
            return {"path": path, "reason": reason}
        case OpFailed(path=path, op=op, expected=expected, actual=actual):
            return {
                "path": path,
                "op": _op_name(op),
                "expected": expected,
                "actual": actual,
            }
        case _ as unreachable:
            assert_never(unreachable)


def evaluate_assertion(
    snapshot: dict[str, Any],
    assertion: Assertion,
) -> Outcome[None, AssertionFailure]:
    """Run a single typed :class:`Assertion` against *snapshot*."""
    try:
        actual = resolve_dotted_path(snapshot, assertion.path)
    except KeyError as exc:
        return Err(PathMissing(path=assertion.path, reason=str(exc)))
    if not _evaluate(assertion.op, actual, assertion.value):
        return Err(
            OpFailed(
                path=assertion.path,
                op=assertion.op,
                expected=assertion.value,
                actual=actual,
            )
        )
    return Ok(None)


def _run_one_assertion(
    snapshot: dict[str, Any],
    raw: dict[str, Any],
) -> Outcome[None, AssertionFailure]:
    """Parse + evaluate a single wire-format assertion.

    Collapses the parse and evaluation stages into one Outcome so
    :func:`check_assertions` only needs a single ``match`` per item.
    """
    match assertion_from_dict(raw):
        case Err(failure):
            return Err(failure)
        case Ok(assertion):
            return evaluate_assertion(snapshot, assertion)


def check_assertions(
    snapshot: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run wire-format assertions against a snapshot.

    Returns a list of failure dicts in the historical shape (empty =
    everything passed).  Internally each assertion is parsed into the
    typed :class:`Assertion`, evaluated through the closed
    :data:`AssertionOp` sum, and the resulting :data:`AssertionFailure`
    is rendered back through :func:`_failure_to_dict`.
    """
    failures: list[dict[str, Any]] = []
    for raw in assertions:
        match _run_one_assertion(snapshot, raw):
            case Err(failure):
                failures.append(_failure_to_dict(failure))
            case Ok(_):
                pass
    return failures
