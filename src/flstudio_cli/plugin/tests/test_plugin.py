"""Tests for plugin command builders, batch registration, and response shape."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import ALL_HANDLERS, schedule_response

from flstudio_cli.batch.application import batch as B
from flstudio_cli.plugin.application import handlers as cmds_plugin
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort

# ---------------------------------------------------------------------------
# Batch handler registry
# ---------------------------------------------------------------------------


class TestPluginHandlerRegistry:
    """All plugin commands appear in the per-feature handler dict."""

    @pytest.mark.parametrize(
        "name",
        [
            "plugin_list",
            "plugin_params",
            "plugin_param_get",
            "plugin_param_set",
        ],
    )
    def test_plugin_command_is_known(self, name: str) -> None:
        assert name in cmds_plugin.BATCH_HANDLERS


# ---------------------------------------------------------------------------
# Batch handler argument coercion
# ---------------------------------------------------------------------------


def _expect_command(result: Any) -> B.DeviceCommand:
    assert isinstance(result, B.Ok)
    assert isinstance(result.value, B.DeviceCommand)
    return result.value


def _expect_invalid_argument(result: Any) -> str:
    assert isinstance(result, B.Err)
    assert isinstance(result.error, B.InvalidArgument)
    return result.error.message


class TestPluginHandlerCoercion:
    # -- plugin_list --------------------------------------------------------

    def test_plugin_list_requires_channel(self) -> None:
        assert "channel" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_list({})
        )

    def test_plugin_list_happy_path(self) -> None:
        cmd = _expect_command(cmds_plugin._handle_plugin_list({"channel": 0}))
        assert cmd == B.DeviceCommand("plugin_list", {"channel": 0})

    # -- plugin_params ------------------------------------------------------

    def test_plugin_params_requires_channel(self) -> None:
        assert "channel" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_params({})
        )

    def test_plugin_params_with_slot(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_params({"channel": 2, "slot": 3})
        )
        assert cmd == B.DeviceCommand("plugin_params", {"channel": 2, "slot": 3})

    def test_plugin_params_without_slot(self) -> None:
        cmd = _expect_command(cmds_plugin._handle_plugin_params({"channel": 1}))
        assert cmd == B.DeviceCommand("plugin_params", {"channel": 1})

    # -- plugin_param_get ---------------------------------------------------

    def test_plugin_param_get_requires_channel(self) -> None:
        assert "channel" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_param_get({"param": 0})
        )

    def test_plugin_param_get_requires_param_or_name(self) -> None:
        assert "param" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_param_get({"channel": 0})
        )

    def test_plugin_param_get_by_index(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_get({"channel": 0, "param": 5})
        )
        assert cmd == B.DeviceCommand("plugin_param_get", {"channel": 0, "param": 5})

    def test_plugin_param_get_by_name(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_get(
                {"channel": 0, "param_name": "Cutoff"}
            ),
        )
        assert cmd == B.DeviceCommand(
            "plugin_param_get", {"channel": 0, "param_name": "Cutoff"}
        )

    def test_plugin_param_get_with_slot(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_get({"channel": 1, "slot": 2, "param": 7}),
        )
        assert cmd.args == {"channel": 1, "slot": 2, "param": 7}

    # -- plugin_param_set ---------------------------------------------------

    def test_plugin_param_set_requires_channel(self) -> None:
        assert "channel" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_param_set({"param": 0, "value": 0.5})
        )

    def test_plugin_param_set_requires_param_or_name(self) -> None:
        assert "param" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_param_set({"channel": 0, "value": 0.5})
        )

    def test_plugin_param_set_requires_value(self) -> None:
        assert "value" in _expect_invalid_argument(
            cmds_plugin._handle_plugin_param_set({"channel": 0, "param": 1})
        )

    def test_plugin_param_set_by_index(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_set(
                {"channel": 0, "param": 3, "value": 0.75}
            ),
        )
        assert cmd == B.DeviceCommand(
            "plugin_param_set", {"channel": 0, "param": 3, "value": 0.75}
        )
        assert isinstance(cmd.args["value"], float)

    def test_plugin_param_set_by_name(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_set(
                {"channel": 0, "param_name": "Volume", "value": 0.5}
            ),
        )
        assert cmd == B.DeviceCommand(
            "plugin_param_set",
            {"channel": 0, "param_name": "Volume", "value": 0.5},
        )

    def test_plugin_param_set_with_slot(self) -> None:
        cmd = _expect_command(
            cmds_plugin._handle_plugin_param_set(
                {"channel": 1, "slot": 0, "param": 2, "value": 0.25}
            ),
        )
        assert cmd.args == {"channel": 1, "slot": 0, "param": 2, "value": 0.25}


# ---------------------------------------------------------------------------
# Execute step (dry-run)
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    @pytest.mark.parametrize(
        "name,args,expected_cmd",
        [
            ("plugin_list", {"channel": 0}, "plugin_list"),
            ("plugin_params", {"channel": 0}, "plugin_params"),
            ("plugin_params", {"channel": 1, "slot": 2}, "plugin_params"),
            ("plugin_param_get", {"channel": 0, "param": 5}, "plugin_param_get"),
            (
                "plugin_param_get",
                {"channel": 0, "param_name": "Cutoff"},
                "plugin_param_get",
            ),
            (
                "plugin_param_set",
                {"channel": 0, "param": 3, "value": 0.75},
                "plugin_param_set",
            ),
            (
                "plugin_param_set",
                {"channel": 1, "slot": 0, "param_name": "Vol", "value": 0.5},
                "plugin_param_set",
            ),
        ],
    )
    def test_dry_run_echoes_request(
        self,
        name: str,
        args: dict[str, Any],
        expected_cmd: str,
    ) -> None:
        envelope = B.execute_step(
            B.BatchStep(name=name, args=args),
            controller=None,
            dry_run=True,
            handlers=ALL_HANDLERS,
        )
        assert envelope["ok"] is True
        assert envelope["result"]["dry_run"] is True
        assert envelope["result"]["request"]["cmd"] == expected_cmd


# ---------------------------------------------------------------------------
# Execute step (live round-trip with FakeReturnPort)
# ---------------------------------------------------------------------------


class TestPluginLiveRoundTrip:
    def test_plugin_list_round_trips(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "plugin_list",
                    "result": {
                        "channel": 0,
                        "plugins": [
                            {"slot": -1, "name": "FLEX"},
                            {"slot": 0, "name": "Fruity Reverb 2"},
                        ],
                    },
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="plugin_list", args={"channel": 0}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert len(envelope["result"]["plugins"]) == 2

    def test_plugin_params_round_trips(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "plugin_params",
                    "result": {
                        "plugin_name": "FLEX",
                        "param_count": 2,
                        "params": [
                            {
                                "index": 0,
                                "name": "Master Volume",
                                "value": 0.75,
                                "display": "-2.5 dB",
                            },
                            {
                                "index": 1,
                                "name": "Filter Cutoff",
                                "value": 0.5,
                                "display": "1000 Hz",
                            },
                        ],
                        "channel": 0,
                        "slot": -1,
                    },
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="plugin_params", args={"channel": 0}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["plugin_name"] == "FLEX"
        assert envelope["result"]["param_count"] == 2
        assert len(envelope["result"]["params"]) == 2

    def test_plugin_param_get_round_trips(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "plugin_param_get",
                    "result": {
                        "plugin_name": "FLEX",
                        "channel": 0,
                        "slot": -1,
                        "param": 1,
                        "name": "Filter Cutoff",
                        "value": 0.5,
                        "display": "1000 Hz",
                    },
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(
                    name="plugin_param_get",
                    args={"channel": 0, "param": 1},
                ),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["name"] == "Filter Cutoff"
        assert envelope["result"]["value"] == 0.5
        assert envelope["result"]["display"] == "1000 Hz"

    def test_plugin_param_set_round_trips(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": True,
                    "command": "plugin_param_set",
                    "result": {
                        "plugin_name": "FLEX",
                        "channel": 0,
                        "slot": -1,
                        "param": 1,
                        "name": "Filter Cutoff",
                        "value": 0.75,
                        "display": "1500 Hz",
                    },
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(
                    name="plugin_param_set",
                    args={"channel": 0, "param": 1, "value": 0.75},
                ),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["value"] == 0.75

    def test_plugin_param_get_not_found_passes_through(self, fake_transport) -> None:
        return_port = FakeReturnPort()
        with DawController(
            fake_transport,
            return_port,
            PRODUCTION_FRAME_CODEC,
        ) as controller:
            schedule_response(
                return_port,
                request_id=1,
                envelope={
                    "ok": False,
                    "command": "plugin_param_get",
                    "result": None,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "no plugin at channel=99 slot=-1",
                    },
                },
            )
            envelope = B.execute_step(
                B.BatchStep(
                    name="plugin_param_get",
                    args={"channel": 99, "param": 0},
                ),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "NOT_FOUND"
