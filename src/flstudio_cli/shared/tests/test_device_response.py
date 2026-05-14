"""Tests for the typed v2 device-response parser."""

from __future__ import annotations

from flstudio_cli.shared.application import envelope as Env
from flstudio_cli.shared.application.device_response_dto import DeviceErr, DeviceOk
from flstudio_cli.shared.application.device_response_parser import (
    parse_device_response,
)


class TestParseDeviceResponse:
    def test_ok_with_result(self) -> None:
        envelope = {"ok": True, "result": {"bpm": 140.0}}
        assert parse_device_response(envelope) == DeviceOk(result={"bpm": 140.0})

    def test_ok_without_result_uses_empty_dict(self) -> None:
        assert parse_device_response({"ok": True}) == DeviceOk(result={})

    def test_ok_with_null_result_uses_empty_dict(self) -> None:
        assert parse_device_response({"ok": True, "result": None}) == DeviceOk(
            result={}
        )

    def test_err_with_full_error_object(self) -> None:
        envelope = {
            "ok": False,
            "error": {
                "code": "INTERNAL",
                "message": "boom",
                "hint": "retry",
                "details": {"x": 1},
            },
        }
        assert parse_device_response(envelope) == DeviceErr(
            code="INTERNAL",
            message="boom",
            hint="retry",
            details={"x": 1},
        )

    def test_err_without_hint_or_details(self) -> None:
        envelope = {
            "ok": False,
            "error": {"code": "INVALID_ARGUMENT", "message": "bad"},
        }
        result = parse_device_response(envelope)
        assert isinstance(result, DeviceErr)
        assert result.hint is None
        assert result.details is None

    def test_missing_ok_treated_as_failure(self) -> None:
        """Malformed envelope (no ``ok`` key) collapses to a generic err."""
        result = parse_device_response({})
        assert isinstance(result, DeviceErr)
        assert result.code == Env.CODE_INTERNAL
        assert "device command failed" in result.message

    def test_err_without_error_object_uses_generic(self) -> None:
        result = parse_device_response({"ok": False})
        assert isinstance(result, DeviceErr)
        assert result.code == Env.CODE_INTERNAL
