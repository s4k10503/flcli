"""Tests for the POSIX exit-code projection of the CLI."""

from __future__ import annotations

import pytest

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestExitCodeMapping:
    @pytest.mark.parametrize(
        "code, expected",
        [
            (Env.CODE_INVALID_ARGUMENT, 2),
            (Env.CODE_NOT_FOUND, 3),
            (Env.CODE_IO_ERROR, 4),
            (Env.CODE_PORT_NOT_FOUND, 10),
            (Env.CODE_UNKNOWN_COMMAND, 20),
            (Env.CODE_PROTOCOL_ERROR, 30),
            (Env.CODE_INTERNAL, 99),
        ],
    )
    def test_known_code_maps_to_distinct_exit_code(self, code, expected):
        assert exit_code_for(code) == expected

    def test_unknown_code_falls_back_to_generic_one(self):
        # Regression guard: unrecognised codes collapse to 1 so a
        # caller that forgets to register a new code still fails loudly.
        assert exit_code_for("NOT_A_REAL_CODE") == 1

    def test_every_exposed_code_has_an_exit_mapping(self):
        # Every constant exposed in ERROR_CODES must project to a
        # non-generic exit code. This is what makes "different error =
        # different exit code" a promise the automation layer can rely on.
        for code in Env.ERROR_CODES:
            assert exit_code_for(code) != 1
