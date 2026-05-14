"""Tests for flstudio_cli.config.infrastructure.config."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from flstudio_cli.config.infrastructure.config import (
    ConfigError,
    ConfigValue,
    ResolvedConfig,
    _coerce_env,
    _get_from_config,
    find_config_file,
    load_config_file,
    resolve,
)

# ---------------------------------------------------------------------------
# ConfigValue
# ---------------------------------------------------------------------------


class TestConfigValue:
    def test_construction(self) -> None:
        cv = ConfigValue(value="hello", source="cli")
        assert cv.value == "hello"
        assert cv.source == "cli"

    def test_to_dict(self) -> None:
        cv = ConfigValue(value=42, source="env:FLCLI_PORT")
        assert cv.to_dict() == {"value": 42, "source": "env:FLCLI_PORT"}

    def test_frozen(self) -> None:
        cv = ConfigValue(value="x", source="default")
        with pytest.raises(AttributeError):
            cv.value = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ResolvedConfig
# ---------------------------------------------------------------------------


class TestResolvedConfig:
    def _make(self, **overrides: Any) -> ResolvedConfig:
        defaults = {
            "port": ConfigValue(None, "default"),
            "return_port": ConfigValue(None, "default"),
            "channel": ConfigValue(0, "default"),
            "dry_run": ConfigValue(False, "default"),
            "state_throttle_ms": ConfigValue(500, "default"),
            "state_path": ConfigValue(None, "default"),
            "queue_path": ConfigValue(None, "default"),
            "export_path": ConfigValue(None, "default"),
            "stop_on_error": ConfigValue(True, "default"),
        }
        defaults.update(overrides)
        return ResolvedConfig(**defaults)

    def test_construction(self) -> None:
        rc = self._make()
        assert rc.port.value is None
        assert rc.channel.value == 0
        assert rc.stop_on_error.value is True

    def test_to_dict_keys(self) -> None:
        rc = self._make()
        d = rc.to_dict()
        expected_keys = {
            "port",
            "return_port",
            "channel",
            "dry_run",
            "state_throttle_ms",
            "state_path",
            "queue_path",
            "export_path",
            "stop_on_error",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self) -> None:
        rc = self._make(port=ConfigValue("my-port", "cli"))
        d = rc.to_dict()
        assert d["port"] == {"value": "my-port", "source": "cli"}


# ---------------------------------------------------------------------------
# find_config_file
# ---------------------------------------------------------------------------


class TestFindConfigFile:
    def test_no_file_returns_none(self, tmp_path: Path) -> None:
        # Nothing exists at the default location or override
        assert find_config_file(str(tmp_path / "nonexistent.toml")) is None

    def test_override_returns_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / "custom.toml"
        cfg.write_text("")
        assert find_config_file(str(cfg)) == str(cfg)

    def test_default_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg_dir = tmp_path / ".flcli"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "config.toml"
        cfg_file.write_text("")
        monkeypatch.setattr(
            "flstudio_cli.config.infrastructure.config._DEFAULT_CONFIG_FILE",
            str(cfg_file),
        )
        # Clear FLCLI_CONFIG so it doesn't interfere
        monkeypatch.delenv("FLCLI_CONFIG", raising=False)
        assert find_config_file() == str(cfg_file)

    def test_env_var_override(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "env_config.toml"
        cfg.write_text("")
        monkeypatch.setenv("FLCLI_CONFIG", str(cfg))
        assert find_config_file() == str(cfg)

    def test_env_var_nonexistent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLCLI_CONFIG", "/no/such/file.toml")
        assert find_config_file() is None


# ---------------------------------------------------------------------------
# load_config_file
# ---------------------------------------------------------------------------


class TestLoadConfigFile:
    def test_valid_toml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            textwrap.dedent("""\
            [default]
            port = "my-midi"
            channel = 5

            [paths]
            state = "/tmp/state.json"

            [batch]
            stop_on_error = false
            state_throttle_ms = 250
        """)
        )
        data = load_config_file(str(cfg))
        assert data["default"]["port"] == "my-midi"
        assert data["default"]["channel"] == 5
        assert data["paths"]["state"] == "/tmp/state.json"
        assert data["batch"]["stop_on_error"] is False
        assert data["batch"]["state_throttle_ms"] == 250


# ---------------------------------------------------------------------------
# _coerce_env
# ---------------------------------------------------------------------------


class TestCoerceEnv:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1", True),
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("yes", True),
            ("Yes", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("", False),
        ],
    )
    def test_bool(self, raw: str, expected: bool) -> None:
        assert _coerce_env("dry_run", raw) is expected

    def test_int(self) -> None:
        assert _coerce_env("state_throttle_ms", "250") == 250
        assert _coerce_env("channel", "10") == 10

    def test_str(self) -> None:
        assert _coerce_env("port", "my-port") == "my-port"


# ---------------------------------------------------------------------------
# _get_from_config
# ---------------------------------------------------------------------------


class TestGetFromConfig:
    def test_default_section(self) -> None:
        config = {"default": {"port": "midi-out", "channel": 3}}
        assert _get_from_config(config, "port") == "midi-out"
        assert _get_from_config(config, "channel") == 3

    def test_paths_section(self) -> None:
        config = {"paths": {"state": "/s", "queue": "/q", "export": "/e"}}
        assert _get_from_config(config, "state_path") == "/s"
        assert _get_from_config(config, "queue_path") == "/q"
        assert _get_from_config(config, "export_path") == "/e"

    def test_batch_section(self) -> None:
        config = {"batch": {"stop_on_error": False, "state_throttle_ms": 100}}
        assert _get_from_config(config, "stop_on_error") is False
        assert _get_from_config(config, "state_throttle_ms") == 100

    def test_missing_key(self) -> None:
        assert _get_from_config({}, "port") is None
        assert _get_from_config({}, "state_path") is None
        assert _get_from_config({}, "stop_on_error") is None


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

_FLCLI_ENV_VARS = (
    "FLCLI_PORT",
    "FLCLI_RETURN_PORT",
    "FLCLI_CHANNEL",
    "FLCLI_DRY_RUN",
    "FLCLI_STATE_THROTTLE_MS",
    "FLCLI_STATE_PATH",
    "FLCLI_QUEUE_PATH",
    "FLCLI_EXPORT_PATH",
    "FLCLI_STOP_ON_ERROR",
    "FLCLI_CONFIG",
)
"""All FLCLI_* environment variables that can influence config resolution."""


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every FLCLI_* env var so ``resolve()`` starts from a known state."""
    for env_var in _FLCLI_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


@pytest.mark.usefixtures("_clean_env")
class TestResolve:
    def test_defaults_only(self) -> None:
        """No config file, no env vars, no CLI args -> all defaults."""
        rc = resolve(config_path="/nonexistent/path.toml")
        assert rc.port.value is None
        assert rc.port.source == "default"
        assert rc.channel.value == 0
        assert rc.channel.source == "default"
        assert rc.dry_run.value is False
        assert rc.state_throttle_ms.value == 500
        assert rc.stop_on_error.value is True

    def test_config_file_values(self, tmp_path: Path) -> None:
        """Config file values are picked up."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            textwrap.dedent("""\
            [default]
            port = "from-toml"
            channel = 7

            [paths]
            state = "/tmp/s.json"

            [batch]
            stop_on_error = false
        """)
        )
        rc = resolve(config_path=str(cfg))
        assert rc.port.value == "from-toml"
        assert rc.port.source == f"config:{cfg}"
        assert rc.channel.value == 7
        assert rc.channel.source == f"config:{cfg}"
        assert rc.state_path.value == "/tmp/s.json"
        assert rc.stop_on_error.value is False

    def test_env_overrides_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Env vars beat config file values."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            textwrap.dedent("""\
            [default]
            port = "from-toml"
        """)
        )
        monkeypatch.setenv("FLCLI_PORT", "from-env")
        rc = resolve(config_path=str(cfg))
        assert rc.port.value == "from-env"
        assert rc.port.source == "env:FLCLI_PORT"

    def test_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI flags beat env vars."""
        monkeypatch.setenv("FLCLI_PORT", "from-env")
        rc = resolve(
            cli_args={"port": "from-cli"},
            config_path="/nonexistent.toml",
        )
        assert rc.port.value == "from-cli"
        assert rc.port.source == "cli"

    def test_full_priority_chain(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI > env > config > default — one key per layer."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            textwrap.dedent("""\
            [default]
            port = "config-port"
            return_port = "config-return"
            channel = 3
        """)
        )
        # env overrides config for return_port
        monkeypatch.setenv("FLCLI_RETURN_PORT", "env-return")
        # CLI overrides everything for port
        rc = resolve(
            cli_args={"port": "cli-port"},
            config_path=str(cfg),
        )
        # CLI wins for port
        assert rc.port.value == "cli-port"
        assert rc.port.source == "cli"
        # Env wins for return_port
        assert rc.return_port.value == "env-return"
        assert rc.return_port.source == "env:FLCLI_RETURN_PORT"
        # Config wins for channel (no CLI or env)
        assert rc.channel.value == 3
        assert rc.channel.source == f"config:{cfg}"
        # Default wins for dry_run (nothing set)
        assert rc.dry_run.value is False
        assert rc.dry_run.source == "default"

    def test_malformed_config_file_ignored(self, tmp_path: Path) -> None:
        """A broken TOML file is silently ignored (falls to defaults)."""
        cfg = tmp_path / "bad.toml"
        cfg.write_text("this is not valid TOML [[[")
        rc = resolve(config_path=str(cfg))
        assert rc.port.source == "default"

    def test_env_bool_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var booleans coerce correctly."""
        monkeypatch.setenv("FLCLI_DRY_RUN", "true")
        monkeypatch.setenv("FLCLI_STOP_ON_ERROR", "0")
        rc = resolve(config_path="/nonexistent.toml")
        assert rc.dry_run.value is True
        assert rc.stop_on_error.value is False

    def test_env_int_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var integers coerce correctly."""
        monkeypatch.setenv("FLCLI_STATE_THROTTLE_MS", "250")
        monkeypatch.setenv("FLCLI_CHANNEL", "10")
        rc = resolve(config_path="/nonexistent.toml")
        assert rc.state_throttle_ms.value == 250
        assert rc.state_throttle_ms.source == "env:FLCLI_STATE_THROTTLE_MS"
        assert rc.channel.value == 10
        assert rc.channel.source == "env:FLCLI_CHANNEL"

    def test_env_int_malformed_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Malformed integer env var raises ConfigError, not a bare ValueError.

        The CLI catches ConfigError to emit a clean envelope; a bare
        ValueError would surface as an untyped traceback instead.
        """
        monkeypatch.setenv("FLCLI_CHANNEL", "notanumber")
        with pytest.raises(ConfigError, match="FLCLI_CHANNEL"):
            resolve(config_path="/nonexistent.toml")
