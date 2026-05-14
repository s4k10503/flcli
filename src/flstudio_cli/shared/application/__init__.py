"""Application layer — use cases, ports, DTOs.

The application layer orchestrates use cases by coordinating domain
types and infrastructure ports.  It never imports infrastructure
directly; concrete adapters are injected by ``shared.composition`` at
the seam.

The cross-layer role-tag taxonomy (9 canonical DDD / CA tags) lives
in :mod:`flstudio_cli` (the package root).  This docstring refines
**file-naming** within the application layer.

File-naming refinement (within ``application/``)
------------------------------------------------
The same role tag covers several file shapes; the file name should
make the SRP slice clear.

==================  ====================  ===================================
Role tag            File-name pattern     Examples
==================  ====================  ===================================
Use case            Action-implying noun  ``cli_dispatcher.py``,
                    or verb_noun, no      ``controller.py``,
                    ``_usecase`` suffix.  ``batch_executor.py``,
                                          ``load_melody.py``,
                                          ``snapshot_compare.py``,
                                          ``realtime_record.py``,
                                          ``track_selection.py``.
Use case            Per-feature command   ``mixer/application/handlers.py``,
(handlers form)     registry.             ``transport/application/handlers.py``.
Use case            Use-case scaffolding  ``handler_args.py``,
(scaffolding)       (helpers, decorators, ``handler_workflow.py``,
                    facades).             ``batch.py``.
Application port    ``*_port.py`` or      ``fl_command_port.py``,
                    grouped in            ``output_port.py``, ``ports.py``.
                    ``ports.py``.
Application DTO     ``*_dto.py``.         ``handler_dto.py``,
                                          ``envelope_dto.py``,
                                          ``device_response_dto.py``,
                                          ``feature_dto.py``.
Application DTO     ``*_errors.py``       ``handler_errors.py``,
(typed errors)      (typed Err sums).     ``automation_errors.py``,
                                          ``transport_errors.py``,
                                          ``melody_errors.py``.
Application DTO     Topical noun for      ``midi_routing.py``,
(constants)         wire-level            ``transport_modes.py``.
                    enumerations.
Application DTO     Topical noun +        ``envelope_factory.py``,
(factory / parser)  ``_factory`` /        ``device_response_parser.py``.
                    ``_parser``.
Application DTO     Same name as the      ``envelope.py``
(facade re-export)  concept it wraps,     (re-exports envelope_dto +
                    no implementation.    envelope_factory).
==================  ====================  ===================================

Use-case files use descriptive verb-noun names (no ``_usecase.py``
suffix); the docstring role tag covers grep-ability.
"""
