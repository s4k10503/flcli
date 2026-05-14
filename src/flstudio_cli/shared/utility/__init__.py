"""Layer-free utility types and helpers.

This package hosts foundational types that aren't conceptually part of
any one architectural layer — analogues of what Rust ships in ``std``
or Haskell in ``base``.  Domain, application, infrastructure, and
presentation may all import freely from here without violating the
onion direction, because nothing in here represents a layer.

Currently:

* :mod:`.outcome` -- :class:`Ok` / :class:`Err` (Result / Either type).

Adding new modules here should be reserved for genuinely cross-cutting
primitives.  Anything carrying domain meaning belongs in
``shared.domain``; anything talking to ports belongs in
``shared.application``.
"""

from __future__ import annotations
