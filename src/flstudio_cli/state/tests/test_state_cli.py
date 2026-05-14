"""Click-level integration tests for state CLI surface (v2 only).

Covers ``ping`` (error-code taxonomy), ``doctor`` and the ``state``
command's ``--state-throttle-ms`` / ``--field`` options.
"""

from __future__ import annotations

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestErrorCodeTaxonomy:
    def test_given_no_port_when_ping_then_exit_code_10(
        self,
        runner,
        no_ports,
    ):
        result = runner.invoke(cli, ["ping"], obj={})

        assert result.exit_code == exit_code_for(Env.CODE_PORT_NOT_FOUND)
        assert result.exit_code == 10
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_PORT_NOT_FOUND

    def test_given_matching_port_when_ping_then_ok_envelope(
        self,
        runner,
        matching_port,
    ):
        result = runner.invoke(cli, ["ping"], obj={})

        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["port"] == "flcli virtual"


class TestDoctorCommand:
    def test_given_no_port_when_doctor_then_nonzero_exit(
        self,
        runner,
        no_ports,
        tmp_path,
    ):
        result = runner.invoke(
            cli,
            [
                "doctor",
                "--queue-file",
                str(tmp_path / "pending.json"),
                "--export-file",
                str(tmp_path / "export.json"),
            ],
            obj={},
        )
        assert result.exit_code != 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False


class TestStateThrottleOption:
    def test_given_throttle_flag_dry_run_then_echoes_throttle_in_request(
        self,
        runner,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", "--state-throttle-ms", "100", "state"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["result"]["dry_run"] is True
        assert payload["result"]["request"]["args"]["throttle_ms"] == 100

    def test_given_env_var_throttle_then_used_as_default(
        self,
        runner,
        monkeypatch,
    ):
        monkeypatch.setenv("FLCLI_STATE_THROTTLE_MS", "250")
        result = runner.invoke(
            cli,
            ["--dry-run", "state"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["args"]["throttle_ms"] == 250

    def test_given_default_throttle_dry_run_then_500(self, runner):
        result = runner.invoke(
            cli,
            ["--dry-run", "state"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["args"]["throttle_ms"] == 500

    def test_given_field_with_dotted_path_dry_run_then_field_in_request(
        self,
        runner,
    ):
        result = runner.invoke(
            cli,
            ["--dry-run", "state", "--field", "channels.0.name"],
            obj={},
        )
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["result"]["request"]["args"]["field"] == "channels.0.name"
