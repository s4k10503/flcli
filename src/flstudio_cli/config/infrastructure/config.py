"""Infrastructure adapter: TOML-based user configuration with layered resolution.

Resolution priority (highest -> lowest):
    1. CLI flags (``--port``, ``--dry-run``, etc.)
    2. Environment variables (``FLCLI_PORT``, ``FLCLI_STATE_THROTTLE_MS``, etc.)
    3. Config file (``~/.flcli/config.toml`` or ``$FLCLI_CONFIG``)
    4. Hard-coded defaults

Environment variable mapping
-----------------------------
==========================  ========================  =====
Key                         Env var                   Type
==========================  ========================  =====
port                        FLCLI_PORT                str
return_port                 FLCLI_RETURN_PORT         str
channel                     FLCLI_CHANNEL             int
dry_run                     FLCLI_DRY_RUN             bool
state_throttle_ms           FLCLI_STATE_THROTTLE_MS   int
state_path                  FLCLI_STATE_PATH          str
queue_path                  FLCLI_QUEUE_PATH          str
export_path                 FLCLI_EXPORT_PATH         str
stop_on_error               FLCLI_STOP_ON_ERROR       bool
==========================  ========================  =====

Booleans are coerced from ``"1"``/``"true"``/``"yes"`` (case-insensitive);
everything else is ``False``.  Invalid integers raise :class:`ConfigError`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_FILE = str(Path.home() / ".flcli" / "config.toml")


@dataclass(frozen=True, slots=True)
class ConfigValue:
    """A resolved config value with its origin."""

    value: Any
    source: str  # e.g. "cli", "env:FLCLI_PORT", "default"

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source}


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    port: ConfigValue
    return_port: ConfigValue
    channel: ConfigValue
    dry_run: ConfigValue
    state_throttle_ms: ConfigValue
    state_path: ConfigValue
    queue_path: ConfigValue
    export_path: ConfigValue
    stop_on_error: ConfigValue

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return asdict(self)


def find_config_file(override: str | None = None) -> str | None:
    """Return the config file path, or None if it doesn't exist."""
    if override:
        return override if Path(override).is_file() else None
    env_path = os.environ.get("FLCLI_CONFIG")
    if env_path:
        return env_path if Path(env_path).is_file() else None
    default = _DEFAULT_CONFIG_FILE
    return default if Path(default).is_file() else None


def load_config_file(path: str) -> dict[str, Any]:
    """Load and parse a TOML config file."""
    with Path(path).open("rb") as fh:
        return tomllib.load(fh)


@dataclass(frozen=True, slots=True)
class _KeySpec:
    """Per-key resolution metadata: default value, env-var name, expected type."""

    default: Any
    env_var: str
    type_: type


_KEYS: dict[str, _KeySpec] = {
    "port": _KeySpec(None, "FLCLI_PORT", str),
    "return_port": _KeySpec(None, "FLCLI_RETURN_PORT", str),
    "channel": _KeySpec(0, "FLCLI_CHANNEL", int),
    "dry_run": _KeySpec(False, "FLCLI_DRY_RUN", bool),
    "state_throttle_ms": _KeySpec(500, "FLCLI_STATE_THROTTLE_MS", int),
    "state_path": _KeySpec(None, "FLCLI_STATE_PATH", str),
    "queue_path": _KeySpec(None, "FLCLI_QUEUE_PATH", str),
    "export_path": _KeySpec(None, "FLCLI_EXPORT_PATH", str),
    "stop_on_error": _KeySpec(True, "FLCLI_STOP_ON_ERROR", bool),
}


class ConfigError(ValueError):
    """Raised when an env var or config file value fails type coercion."""


def _coerce_env(key: str, raw: str) -> Any:
    """Coerce an env var string to the appropriate type.

    Raises :class:`ConfigError` on malformed input so the CLI can emit a
    clean envelope error instead of a bare ``ValueError`` traceback.
    """
    spec = _KEYS[key]
    if spec.type_ is bool:
        return raw.lower() in ("1", "true", "yes")
    if spec.type_ is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(
                f"env var {spec.env_var}={raw!r} is not a valid integer"
            ) from exc
    return raw


def _get_from_config(config: dict[str, Any], key: str) -> Any | None:
    """Look up a key in the TOML config structure.

    Config structure:
    [default]
    port = "..."
    channel = 0
    dry_run = false

    [paths]
    state = "..."
    queue = "..."
    export = "..."

    [batch]
    stop_on_error = true
    state_throttle_ms = 250
    """
    # Path keys live under [paths]
    path_keys = {"state_path": "state", "queue_path": "queue", "export_path": "export"}
    if key in path_keys:
        return config.get("paths", {}).get(path_keys[key])
    # Batch keys under [batch]
    batch_keys = {"stop_on_error", "state_throttle_ms"}
    if key in batch_keys:
        val = config.get("batch", {}).get(key)
        if val is not None:
            return val
    # Everything else under [default]
    return config.get("default", {}).get(key)


def resolve(
    *,
    cli_args: dict[str, Any] | None = None,
    config_path: str | None = None,
) -> ResolvedConfig:
    """Resolve config from all sources. Pure function (reads env vars)."""
    cli = cli_args or {}

    # Load config file if available
    config_file_path = find_config_file(config_path)
    config: dict[str, Any] = {}
    if config_file_path:
        try:
            config = load_config_file(config_file_path)
        except (OSError, tomllib.TOMLDecodeError):
            pass

    results: dict[str, ConfigValue] = {}
    for key, spec in _KEYS.items():
        # Priority 1: CLI flags (None means not provided)
        cli_val = cli.get(key)
        if cli_val is not None:
            results[key] = ConfigValue(value=cli_val, source="cli")
            continue

        # Priority 2: Environment variables
        env_raw = os.environ.get(spec.env_var)
        if env_raw is not None:
            results[key] = ConfigValue(
                value=_coerce_env(key, env_raw),
                source=f"env:{spec.env_var}",
            )
            continue

        # Priority 3: Config file
        if config_file_path:
            file_val = _get_from_config(config, key)
            if file_val is not None:
                results[key] = ConfigValue(
                    value=file_val,
                    source=f"config:{config_file_path}",
                )
                continue

        # Priority 4: Default
        results[key] = ConfigValue(value=spec.default, source="default")

    return ResolvedConfig(**results)
