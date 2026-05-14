"""Click-level integration tests for config CLI surface (v2 only).

Covers ``config show`` / ``config path`` envelope contracts including the
malformed-env-var rejection path.
"""

from __future__ import annotations

from conftest import parse_first_line as _parse_first_line

from flstudio_cli.__main__ import cli
from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.presentation.exit_codes import exit_code_for


class TestConfigCommand:
    def test_config_show_emits_envelope(self, runner, monkeypatch, tmp_path):
        # Isolate from the user's real config file.
        monkeypatch.setenv("FLCLI_CONFIG", str(tmp_path / "no.toml"))
        result = runner.invoke(cli, ["config", "show"], obj={})
        assert result.exit_code == 0, result.output
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "config_show"
        # Every field should be present with a source tag.
        assert "port" in payload["result"]
        assert payload["result"]["port"]["source"] == "default"

    def test_config_path_emits_envelope(self, runner, monkeypatch, tmp_path):
        monkeypatch.setenv("FLCLI_CONFIG", str(tmp_path / "no.toml"))
        result = runner.invoke(cli, ["config", "path"], obj={})
        assert result.exit_code == 0
        payload = _parse_first_line(result.output)
        assert payload["ok"] is True
        assert payload["command"] == "config_path"
        assert payload["result"]["exists"] is False

    def test_config_show_rejects_malformed_env_var(
        self,
        runner,
        monkeypatch,
        tmp_path,
    ):
        monkeypatch.setenv("FLCLI_CONFIG", str(tmp_path / "no.toml"))
        monkeypatch.setenv("FLCLI_CHANNEL", "not-a-number")
        result = runner.invoke(cli, ["config", "show"], obj={})
        assert result.exit_code == exit_code_for(Env.CODE_INVALID_ARGUMENT)
        payload = _parse_first_line(result.output)
        assert payload["ok"] is False
        assert payload["error"]["code"] == Env.CODE_INVALID_ARGUMENT
        assert "FLCLI_CHANNEL" in payload["error"]["message"]
