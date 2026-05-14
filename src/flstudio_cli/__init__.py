"""LLM-friendly CLI for FL Studio .flp projects.

Architecture
------------
Clean / Onion architecture with five layers plus per-feature packages
and a layer-free utility module:

* ``shared/utility/`` — layer-free generics (Outcome / Result-like).
* ``<feature>/domain/`` — Value Objects and Domain Services (DDD).
* ``<feature>/application/`` — Use Cases, Ports, DTOs.
* ``<feature>/infrastructure/`` — Adapters that implement Application
  Ports (MIDI, FLP, OS automation, file system, wire protocol).
* ``shared/composition/`` — Composition Root (DI wiring).
* ``<feature>/presentation/`` — Interface Adapters (CA): Click commands
  and CLI-side helpers.

Dependency direction is enforced by tach (see ``tach.toml``).

File-level role-tag convention
------------------------------
Every non-test ``.py`` module opens its docstring with one of the
nine canonical DDD / Clean-Architecture role tags below.  Grepping
for the pattern ``^[A-Z][a-zA-Z ]+:`` at the start of a triple-quoted
docstring returns one match per file.

==========================  ===========================================
Role tag                    Layer / DDD-CA term
==========================  ===========================================
``Composition root:``       Composition Root (Mark Seemann's DI term).
                            Covers ``__main__.py``, ``composition/*.py``,
                            and per-feature ``feature.py`` descriptors —
                            all DI / wiring concerns.
``Use case:``               Use Case (CA) ≡ Application Service (DDD).
                            Application orchestration: single-shot
                            actions, stateful coordinators, batch
                            command handlers, and use-case scaffolding
                            (``handler_args``, ``handler_workflow``,
                            facade re-exports such as ``batch.py``).
``Application port:``       Port (Hexagonal).  Protocol / callable
                            bundle that infrastructure implements.
``Application DTO:``        Data-Transfer Object.  Covers ``*_dto.py``,
                            typed errors (``*_errors.py``), wire-level
                            constants, factories / parsers that build
                            DTOs, and DTO facade re-exports such as
                            ``envelope.py``.
``Domain value object:``    Value Object (DDD).  Frozen dataclass or
                            ``NewType`` vocabulary.
``Domain service:``         Domain Service (DDD).  Pure operations over
                            domain types (``edit_ops``,
                            ``snapshot_diff``).
``Infrastructure adapter:`` Adapter (Hexagonal).  Concrete impl of an
                            Application Port — covers transport sinks,
                            file-format adapters, OS automation, wire
                            codecs, filesystem utilities, and the FL
                            Studio sandbox script.
``Interface adapter:``      Interface Adapter (CA).  Click commands
                            (``cmd_*.py``) and CLI-side helpers
                            (``cli_dispatch``, ``cli_helpers``,
                            ``exit_codes``, ``melody_helpers``).
``Utility:``                Layer-free generic (the Outcome /
                            Result-like type).  Importable from any
                            layer; analogue of Rust ``std::result``.
==========================  ===========================================

Per-layer convention doc
------------------------
Each layer's package docstring (e.g.
:mod:`flstudio_cli.shared.application`) refines these rules with
file-naming guidance specific to that layer (e.g. ``*_dto.py``
suffix, action-implying use-case names).
"""

__version__ = "0.1.0"
