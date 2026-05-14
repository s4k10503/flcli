"""Cross-feature presentation helpers.

Per-feature Click ``Command`` / ``Group`` objects live with their
feature (``<feature>/presentation/cmd_<feature>.py``) and are
discovered via the ``flstudio_cli.features`` entry-point group;
:mod:`flstudio_cli.__main__` walks that registry rather than
importing each module by name.

This sub-package houses the cross-feature glue:

* :mod:`cli_helpers` -- the active :class:`Output` adapter, envelope
  emission (``_emit_success`` / ``_fail``), hint constants, and shared
  text-IO helpers.
* :mod:`cli_dispatch` -- Click-typed wrappers around the application
  layer's :class:`DispatchDeps`-based dispatcher (also home to the
  FLP / melody-loading helpers that map typed errors onto envelopes).
* :mod:`exit_codes` -- POSIX exit-code projection for the CLI process.

Composition rules: sub-modules import application services and the
composition layer only -- never ``flstudio_cli.shared.infrastructure``
directly.
"""
