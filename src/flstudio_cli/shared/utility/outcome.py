# pyright: strict

"""Utility: outcome type for explicit success / failure return values.

A small two-variant sum that makes the failure channel part of the
type signature instead of an out-of-band exception.  Same idea as Rust
``Result<T, E>`` / Haskell ``Either e a`` / F# ``Result<'a, 'err>``.

Lives under ``shared.utility`` rather than ``shared.domain`` because
``Outcome`` is a foundational generic with no domain meaning — every
layer (domain, application, infrastructure, presentation) consumes it
the same way Rust code consumes ``std::result::Result``.

Why introduce this when Python already has exceptions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure functions become values-in / values-out.  Modelling failure as a
return type rather than an exception means:

* the caller cannot accidentally drop the error -- the type system
  forces an explicit ``match``;
* the **set** of legal failures is captured in a single closed sum
  (see :data:`flstudio_cli.shared.domain.refs.ResolveError`), so
  listing them is exhaustive;
* the imperative shell decides at one well-defined seam how to surface
  the failure -- exception, log line, JSON envelope -- rather than
  every helper guessing.

Exceptions remain the right tool at the *shell* boundary
(``presentation/cli_dispatch`` catches ``ValueError`` / ``OSError``
during the v2 round-trip and lifts them into envelopes); they are
simply not the right tool **inside** pure logic.

Typing note
~~~~~~~~~~~
The parameterised alias :data:`Outcome` is the standard spelling at
use sites: ``Outcome[CompareReport, CompareError]`` rather than the
underlying ``Ok[CompareReport] | Err[CompareError]``.  The alias is
declared with the PEP 695 ``type`` statement (Python 3.12+).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = ["Err", "Ok", "Outcome"]


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Successful outcome carrying a typed value.

    The chain methods (:meth:`map`, :meth:`flat_map`, :meth:`map_err`,
    :meth:`unwrap_or`, :meth:`is_ok`) mirror Rust ``Result`` / Scala
    ``Either``: they let callers compose pure transformations without
    repeating an ``isinstance`` ladder. ``Err`` short-circuits each
    chain so a downstream ``map`` after a failure is a no-op.
    """

    value: T

    def map[U](self, f: Callable[[T], U]) -> Ok[U]:
        return Ok(f(self.value))

    def flat_map[U, E2](self, f: Callable[[T], Ok[U] | Err[E2]]) -> Ok[U] | Err[E2]:
        return f(self.value)

    def map_err(self, _f: Callable[[Any], Any]) -> Ok[T]:
        return self

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def is_ok(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Failed outcome carrying a typed error value."""

    error: E

    def map(self, _f: Callable[[Any], Any]) -> Err[E]:
        return self

    def flat_map(self, _f: Callable[[Any], Any]) -> Err[E]:
        return self

    def map_err[E2](self, f: Callable[[E], E2]) -> Err[E2]:
        return Err(f(self.error))

    def unwrap_or[T](self, default: T) -> T:
        return default

    def is_ok(self) -> bool:
        return False


# PEP 695 parameterised alias.  ``Outcome[T, E]`` is the preferred
# spelling at use sites; the underlying union ``Ok[T] | Err[E]`` remains
# valid for legacy annotations.
type Outcome[T, E] = Ok[T] | Err[E]
