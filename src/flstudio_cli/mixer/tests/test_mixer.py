"""Tests for mixer command builders, batch registration, and response shape."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import ALL_HANDLERS, schedule_response

from flstudio_cli.batch.application import batch as B
from flstudio_cli.mixer.application import handlers as cmds_mixer
from flstudio_cli.shared.application.controller import DawController
from flstudio_cli.shared.composition.transport import PRODUCTION_FRAME_CODEC
from flstudio_cli.shared.infrastructure.transport.return_port import FakeReturnPort

# ---------------------------------------------------------------------------
# Batch handler registry
# ---------------------------------------------------------------------------


class TestMixerHandlerRegistry:
    """All mixer commands appear in the per-feature handler dict."""

    @pytest.mark.parametrize(
        "name",
        [
            "mixer_list",
            "mixer_volume_get",
            "mixer_volume_set",
            "mixer_pan_get",
            "mixer_pan_set",
            "mixer_name_get",
            "mixer_name_set",
            "mixer_mute",
            "mixer_solo",
            "mixer_arm",
            "mixer_route_set",
            "mixer_link_to_channel",
        ],
    )
    def test_mixer_command_is_known(self, name: str) -> None:
        assert name in cmds_mixer.BATCH_HANDLERS


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


class TestMixerHandlerCoercion:
    def test_mixer_list_returns_no_args(self) -> None:
        assert _expect_command(cmds_mixer._handle_mixer_list({})) == B.DeviceCommand(
            "mixer_list", {}
        )

    def test_mixer_volume_get_requires_track(self) -> None:
        assert "track" in _expect_invalid_argument(
            cmds_mixer._handle_mixer_volume_get({})
        )

    def test_mixer_volume_set_coerces_value_to_float(self) -> None:
        cmd = _expect_command(
            cmds_mixer._handle_mixer_volume_set({"track": 1, "value": 80})
        )
        assert cmd == B.DeviceCommand("mixer_volume_set", {"track": 1, "value": 80.0})
        assert isinstance(cmd.args["value"], float)

    def test_mixer_pan_set_coerces_value(self) -> None:
        cmd = _expect_command(
            cmds_mixer._handle_mixer_pan_set({"track": 2, "value": -50})
        )
        assert cmd.args == {"track": 2, "value": -50.0}

    def test_mixer_name_set_requires_string_name(self) -> None:
        assert "string" in _expect_invalid_argument(
            cmds_mixer._handle_mixer_name_set({"track": 0, "name": 42})
        )

    def test_mixer_name_set_happy_path(self) -> None:
        cmd = _expect_command(
            cmds_mixer._handle_mixer_name_set({"track": 3, "name": "Bass"})
        )
        assert cmd == B.DeviceCommand("mixer_name_set", {"track": 3, "name": "Bass"})

    def test_mixer_mute_requires_track(self) -> None:
        assert "track" in _expect_invalid_argument(cmds_mixer._handle_mixer_mute({}))

    def test_mixer_arm_passes_on_through(self) -> None:
        cmd = _expect_command(cmds_mixer._handle_mixer_arm({"track": 5, "on": False}))
        assert cmd.args == {"track": 5, "on": False}

    def test_mixer_route_set_requires_from_and_to(self) -> None:
        assert "from" in _expect_invalid_argument(
            cmds_mixer._handle_mixer_route_set({"to": 0})
        )

    def test_mixer_route_set_happy_path(self) -> None:
        cmd = _expect_command(
            cmds_mixer._handle_mixer_route_set({"from": 1, "to": 0, "on": True})
        )
        assert cmd == B.DeviceCommand(
            "mixer_route_set", {"from": 1, "to": 0, "on": True}
        )

    def test_mixer_link_to_channel_requires_track(self) -> None:
        assert "track" in _expect_invalid_argument(
            cmds_mixer._handle_mixer_link_to_channel({})
        )

    def test_mixer_link_to_channel_requires_channel(self) -> None:
        assert "channel" in _expect_invalid_argument(
            cmds_mixer._handle_mixer_link_to_channel({"track": 5})
        )


# ---------------------------------------------------------------------------
# Execute step (dry-run)
# ---------------------------------------------------------------------------


class TestMixerDryRun:
    @pytest.mark.parametrize(
        "name,args,expected_cmd",
        [
            ("mixer_list", {}, "mixer_list"),
            ("mixer_volume_get", {"track": 0}, "mixer_volume_get"),
            ("mixer_volume_set", {"track": 1, "value": 0.75}, "mixer_volume_set"),
            ("mixer_pan_get", {"track": 2}, "mixer_pan_get"),
            ("mixer_pan_set", {"track": 3, "value": -0.5}, "mixer_pan_set"),
            ("mixer_name_get", {"track": 4}, "mixer_name_get"),
            ("mixer_name_set", {"track": 5, "name": "FX Bus"}, "mixer_name_set"),
            ("mixer_mute", {"track": 6}, "mixer_mute"),
            ("mixer_solo", {"track": 7}, "mixer_solo"),
            ("mixer_arm", {"track": 8, "on": True}, "mixer_arm"),
            ("mixer_route_set", {"from": 1, "to": 0, "on": True}, "mixer_route_set"),
            (
                "mixer_link_to_channel",
                {"track": 9, "channel": 0},
                "mixer_link_to_channel",
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


class TestMixerLiveRoundTrip:
    def test_mixer_volume_set_round_trips(self, fake_transport) -> None:
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
                    "command": "mixer_volume_set",
                    "result": {"track": 1, "volume": 0.75},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="mixer_volume_set", args={"track": 1, "value": 0.75}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["volume"] == 0.75

    def test_mixer_name_set_round_trips(self, fake_transport) -> None:
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
                    "command": "mixer_name_set",
                    "result": {"track": 3, "name": "Drums"},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="mixer_name_set", args={"track": 3, "name": "Drums"}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["name"] == "Drums"

    def test_mixer_list_round_trips(self, fake_transport) -> None:
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
                    "command": "mixer_list",
                    "result": {
                        "tracks": [
                            {
                                "index": 0,
                                "name": "Master",
                                "volume": 1.0,
                                "pan": 0.0,
                                "mute": False,
                                "solo": False,
                            },
                        ]
                    },
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(name="mixer_list", args={}),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert len(envelope["result"]["tracks"]) == 1

    def test_mixer_route_set_round_trips(self, fake_transport) -> None:
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
                    "command": "mixer_route_set",
                    "result": {"from": 1, "to": 0, "on": True},
                    "error": None,
                },
            )
            envelope = B.execute_step(
                B.BatchStep(
                    name="mixer_route_set", args={"from": 1, "to": 0, "on": True}
                ),
                controller=controller,
                dry_run=False,
                handlers=ALL_HANDLERS,
            )
        assert envelope["ok"] is True
        assert envelope["result"]["on"] is True
