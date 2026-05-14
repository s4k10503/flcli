"""Tests for the pure protocol v2 SysEx framing module."""

from __future__ import annotations

import json

import pytest

from flstudio_cli.shared.infrastructure.protocol import v2 as V2

# ---------------------------------------------------------------------------
# pack_7bit / unpack_7bit
# ---------------------------------------------------------------------------


class TestPack7Bit:
    def test_given_empty_bytes_when_pack_then_returns_empty(self) -> None:
        assert V2.pack_7bit(b"") == b""

    @pytest.mark.parametrize(
        "source,expected",
        [
            # 1 byte with no high bit -> MSB byte 0x00 followed by the byte.
            (b"\x01", b"\x00\x01"),
            # 1 byte with high bit set -> MSB byte bit 0 set, low 7 bits follow.
            (b"\x81", b"\x01\x01"),
            # 7 bytes all high-bit-clear -> MSB byte 0 then the 7 bytes.
            (bytes(range(7)), b"\x00" + bytes(range(7))),
            # 7 bytes all high-bit-set -> MSB byte 0x7F then low 7 bits.
            (b"\x80\x81\x82\x83\x84\x85\x86", b"\x7f\x00\x01\x02\x03\x04\x05\x06"),
        ],
    )
    def test_given_fixed_vector_when_pack_then_matches_expected(
        self, source: bytes, expected: bytes
    ) -> None:
        assert V2.pack_7bit(source) == expected

    def test_given_packed_output_when_checked_then_every_byte_is_7bit_clean(
        self,
    ) -> None:
        source = bytes(range(256))
        packed = V2.pack_7bit(source)
        assert all(byte <= 0x7F for byte in packed)

    @pytest.mark.parametrize(
        "size",
        [0, 1, 6, 7, 8, 14, 49, 50, 255, 1000],
    )
    def test_given_varied_sizes_when_round_trip_then_identity(self, size: int) -> None:
        source = bytes((i * 31 + 7) % 256 for i in range(size))
        assert V2.unpack_7bit(V2.pack_7bit(source)) == source

    def test_given_all_zero_bytes_when_round_trip_then_identity(self) -> None:
        source = bytes(64)
        assert V2.unpack_7bit(V2.pack_7bit(source)) == source

    def test_given_all_ff_bytes_when_round_trip_then_identity(self) -> None:
        source = b"\xff" * 64
        assert V2.unpack_7bit(V2.pack_7bit(source)) == source

    def test_given_alternating_high_bit_when_round_trip_then_identity(self) -> None:
        source = bytes((0xFF if i % 2 == 0 else 0x00) for i in range(128))
        assert V2.unpack_7bit(V2.pack_7bit(source)) == source


class TestUnpack7Bit:
    def test_given_empty_input_when_unpack_then_returns_empty(self) -> None:
        assert V2.unpack_7bit(b"") == b""

    def test_given_byte_with_high_bit_when_unpack_then_raises_malformed(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="high bit"):
            V2.unpack_7bit(b"\x00\x80")

    def test_given_lone_msb_byte_with_no_data_when_unpack_then_raises(self) -> None:
        # A bare 0x00 MSB byte with no following bytes means the producer
        # lied about having data. Reject instead of silently returning ''.
        with pytest.raises(V2.MalformedFrame, match="trailing MSB byte"):
            V2.unpack_7bit(b"\x00")


# ---------------------------------------------------------------------------
# encode_request_id / decode_request_id
# ---------------------------------------------------------------------------


class TestRequestId:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, b"\x00\x00\x00\x00"),
            (1, b"\x00\x00\x00\x01"),
            (127, b"\x00\x00\x00\x7f"),
            (128, b"\x00\x00\x01\x00"),
            (0xFFFFFFF, b"\x7f\x7f\x7f\x7f"),  # 2**28 - 1
        ],
    )
    def test_given_value_when_encode_then_matches_msb_first(
        self, value: int, expected: bytes
    ) -> None:
        assert V2.encode_request_id(value) == expected

    @pytest.mark.parametrize("value", [0, 1, 127, 128, 16384, 0x7FFFFFF])
    def test_given_value_when_round_trip_then_identity(self, value: int) -> None:
        assert V2.decode_request_id(V2.encode_request_id(value)) == value

    def test_given_negative_when_encode_then_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            V2.encode_request_id(-1)

    def test_given_overflow_when_encode_then_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            V2.encode_request_id(V2.REQUEST_ID_MAX + 1)

    def test_given_wrong_length_when_decode_then_raises(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="4 bytes"):
            V2.decode_request_id(b"\x00\x00\x00")

    def test_given_high_bit_when_decode_then_raises(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="high bit"):
            V2.decode_request_id(b"\x00\x00\x00\x80")


# ---------------------------------------------------------------------------
# encode_frame / decode_frame
# ---------------------------------------------------------------------------


class TestEncodeFrame:
    def test_given_empty_payload_when_encode_then_has_bookends_vendor_version_rid(
        self,
    ) -> None:
        frame = V2.SysExFrame(request_id=0, payload=b"")
        wire = V2.encode_frame(frame)
        assert wire[0] == V2.SYSEX_START
        assert wire[1] == V2.VENDOR_ID
        assert wire[2] == V2.PROTOCOL_VERSION_V2
        assert wire[3:7] == b"\x00\x00\x00\x00"
        assert wire[-1] == V2.SYSEX_END

    def test_given_frame_when_encode_then_interior_bytes_are_7bit_clean(self) -> None:
        frame = V2.SysExFrame(
            request_id=12345,
            payload=json.dumps({"cmd": "tempo", "args": {"bpm": 140.5}}).encode(
                "utf-8"
            ),
        )
        wire = V2.encode_frame(frame)
        interior = wire[1:-1]  # drop F0 / F7 bookends
        assert all(byte <= 0x7F for byte in interior)

    def test_given_payload_larger_than_soft_limit_when_encode_then_raises(self) -> None:
        huge = b"a" * (V2.MAX_PACKED_PAYLOAD_BYTES + 1)
        with pytest.raises(ValueError, match="soft limit"):
            V2.encode_frame(V2.SysExFrame(request_id=1, payload=huge))


class TestDecodeFrame:
    @pytest.mark.parametrize(
        "payload",
        [
            b"",
            b'{"cmd":"play","args":{}}',
            b'{"cmd":"tempo","args":{"bpm":140.5}}',
            b'{"cmd":"name_channel","args":{"channel":3,"name":"my synth bass"}}',
            json.dumps({"cmd": "state", "args": {"field": "tempo"}}).encode("utf-8"),
        ],
    )
    def test_given_frame_when_round_trip_then_identity(self, payload: bytes) -> None:
        original = V2.SysExFrame(request_id=42, payload=payload)
        decoded = V2.decode_frame(V2.encode_frame(original))
        assert decoded == original

    @pytest.mark.parametrize("request_id", [0, 1, 127, 16384, V2.REQUEST_ID_MAX])
    def test_given_request_id_boundary_when_round_trip_then_matches(
        self, request_id: int
    ) -> None:
        original = V2.SysExFrame(request_id=request_id, payload=b"x")
        decoded = V2.decode_frame(V2.encode_frame(original))
        assert decoded.request_id == request_id

    def test_given_too_short_when_decode_then_raises_malformed(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="too short"):
            V2.decode_frame(b"\xf0\xf7")

    def test_given_missing_start_byte_when_decode_then_raises(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="start byte"):
            V2.decode_frame(b"\x00" + b"\x7d\x02\x00\x00\x00\x00" + b"\xf7")

    def test_given_missing_end_byte_when_decode_then_raises(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="end byte"):
            V2.decode_frame(b"\xf0\x7d\x02\x00\x00\x00\x00\x00")

    def test_given_wrong_vendor_when_decode_then_raises(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="vendor id"):
            V2.decode_frame(b"\xf0\x41\x02\x00\x00\x00\x00\xf7")

    def test_given_wrong_version_when_decode_then_raises_protocol_mismatch(
        self,
    ) -> None:
        with pytest.raises(V2.ProtocolMismatch, match="version"):
            V2.decode_frame(b"\xf0\x7d\x03\x00\x00\x00\x00\xf7")


# ---------------------------------------------------------------------------
# build_command / parse_response
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_given_cmd_with_args_when_build_then_round_trips_through_json(self) -> None:
        payload = V2.build_command("tempo", {"bpm": 140.5})
        decoded = json.loads(payload.decode("utf-8"))
        assert decoded == {"cmd": "tempo", "args": {"bpm": 140.5}}

    def test_given_cmd_without_args_when_build_then_args_is_empty_dict(self) -> None:
        payload = V2.build_command("play")
        decoded = json.loads(payload.decode("utf-8"))
        assert decoded == {"cmd": "play", "args": {}}

    def test_given_unicode_name_when_build_then_utf8_encoded(self) -> None:
        payload = V2.build_command("name_channel", {"channel": 0, "name": "鍵盤"})
        decoded = json.loads(payload.decode("utf-8"))
        assert decoded["args"]["name"] == "鍵盤"


class TestParseResponse:
    def test_given_valid_envelope_when_parse_then_returns_dict(self) -> None:
        raw = json.dumps(
            {
                "request_id": 42,
                "ok": True,
                "command": "tempo",
                "result": {"bpm": 140.5},
                "error": None,
            }
        ).encode("utf-8")
        envelope = V2.parse_response(raw)
        assert envelope["ok"] is True
        assert envelope["request_id"] == 42
        assert envelope["result"]["bpm"] == 140.5

    def test_given_invalid_json_when_parse_then_raises_malformed(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="valid JSON"):
            V2.parse_response(b"{not json")

    def test_given_non_object_when_parse_then_raises_malformed(self) -> None:
        with pytest.raises(V2.MalformedFrame, match="JSON object"):
            V2.parse_response(b"42")
