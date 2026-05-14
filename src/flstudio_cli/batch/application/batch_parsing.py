"""Use case: parse a JSON / JSONL batch payload into validated steps.

Single responsibility: convert raw JSON (decoded dicts/lists or JSONL
strings) into validated :class:`BatchStep` instances.  No execution
logic, no handler knowledge -- just structural validation.

Failures stay inside ``Err(ParseError)`` so callers can pattern-match
on the :data:`Outcome` without a ``try`` block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from flstudio_cli.shared.utility.outcome import Err, Ok, Outcome


@dataclass(frozen=True, slots=True)
class BatchStep:
    """A single entry in a batch payload.

    ``name`` picks a handler from the handler registry; ``args`` is a
    free-form dict passed through to it.  ``step_id`` is echoed back
    in the response envelope so streaming clients can correlate
    requests with responses even if they are pipelined.
    """

    name: str
    args: dict[str, Any]
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class ParseError:
    """Typed parser failure.

    ``message`` is the human-readable description; the wire envelope
    surfaces it under ``CODE_INVALID_ARGUMENT`` once the parser's
    caller projects this Outcome onto a response.
    """

    message: str


def _validate_raw_step(
    raw: dict[str, Any], label: str
) -> Outcome[BatchStep, ParseError]:
    """Validate a single raw step dict into ``Ok(BatchStep)`` / ``Err``.

    ``label`` is used in error messages (e.g. ``"step 3"`` or
    ``"stream line"``).
    """
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        return Err(ParseError(f"{label} missing 'name'"))
    args = raw.get("args") or {}
    if not isinstance(args, dict):
        return Err(ParseError(f"{label} 'args' must be an object"))
    step_id_raw = raw.get("id")
    if step_id_raw is not None and not isinstance(step_id_raw, str):
        return Err(ParseError(f"{label} 'id' must be a string"))
    return Ok(BatchStep(name=name, args=dict(args), step_id=step_id_raw))


def parse_steps(payload: Any) -> Outcome[list[BatchStep], ParseError]:
    """Coerce a decoded JSON document into a validated list of steps.

    Accepts either a bare list ``[{"name": ..., "args": ...}, ...]``
    or an object with a ``"steps"`` key wrapping the list.  Unknown
    keys on each step are ignored so the format stays extensible.
    """
    if isinstance(payload, dict):
        raw_steps = payload.get("steps")
        if raw_steps is None:
            return Err(ParseError("batch payload missing 'steps' list"))
    else:
        raw_steps = payload
    if not isinstance(raw_steps, list):
        return Err(ParseError("batch 'steps' must be a list"))

    steps: list[BatchStep] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            return Err(
                ParseError(f"step {index} must be an object, got {type(raw).__name__}")
            )
        match _validate_raw_step(raw, f"step {index}"):
            case Ok(step):
                steps.append(step)
            case Err() as err:
                return err
    return Ok(steps)


def parse_stream_line(line: str) -> Outcome[BatchStep, ParseError]:
    """Parse one JSONL line from ``batch stream`` into ``Ok(BatchStep)`` / ``Err``.

    A stream line is a single step object, not a wrapping list.
    """
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError as exc:
        return Err(ParseError(f"invalid JSON: {exc}"))
    if not isinstance(decoded, dict):
        return Err(ParseError("stream line must be a JSON object"))
    return _validate_raw_step(decoded, "stream line")
