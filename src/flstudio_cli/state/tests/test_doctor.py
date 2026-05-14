"""Tests for the ``flcli doctor`` health-check collectors."""

from __future__ import annotations

import mido

from flstudio_cli.state.application import doctor as Doc


class TestCheckMidiPort:
    def test_given_no_visible_ports_when_check_then_fails(
        self,
        no_ports,
        doctor_effects,
    ):
        result = Doc.check_midi_port(
            None, list_output_ports=doctor_effects.list_output_ports
        )
        assert result.ok is False
        assert "no MIDI output ports" in result.message

    def test_given_matching_port_when_check_then_ok(
        self,
        matching_port,
        doctor_effects,
    ):
        result = Doc.check_midi_port(
            None, list_output_ports=doctor_effects.list_output_ports
        )
        assert result.ok is True
        assert result.details["matched"] == ["flcli virtual"]

    def test_given_mismatching_port_when_check_then_fails(
        self,
        monkeypatch,
        doctor_effects,
    ):
        monkeypatch.setattr(mido, "get_output_names", lambda: ["IAC other"])
        result = Doc.check_midi_port(
            "flcli", list_output_ports=doctor_effects.list_output_ports
        )
        assert result.ok is False
        assert "flcli" in result.message


class TestCheckPianoRollQueue:
    def test_given_missing_queue_when_check_then_ok_neutral(
        self,
        tmp_path,
        doctor_effects,
    ):
        result = Doc.check_piano_roll_queue(
            str(tmp_path / "pending.json"),
            piano_roll_io=doctor_effects.piano_roll_io,
            fs=doctor_effects.fs,
        )
        assert result.ok is True
        assert "no pending" in result.message

    def test_given_present_queue_when_check_then_ok_with_hint(
        self,
        tmp_path,
        doctor_effects,
    ):
        path = tmp_path / "pending.json"
        path.write_text("{}")
        result = Doc.check_piano_roll_queue(
            str(path),
            piano_roll_io=doctor_effects.piano_roll_io,
            fs=doctor_effects.fs,
        )
        assert result.ok is True
        assert "hint" in result.details


class TestCheckSongPosition:
    def test_given_no_snapshot_then_ok_skipped(self):
        result = Doc.check_song_position(None)
        assert result.ok is True
        assert "skipped" in result.message

    def test_given_snapshot_with_position_then_ok(self):
        result = Doc.check_song_position({"song_position": 16.5})
        assert result.ok is True
        assert result.details["song_position"] == 16.5

    def test_given_snapshot_with_null_position_then_fails(self):
        result = Doc.check_song_position({"song_position": None})
        assert result.ok is False
        assert "null" in result.message

    def test_given_snapshot_missing_position_key_then_fails(self):
        result = Doc.check_song_position({"tempo": 120.0})
        assert result.ok is False


class TestCheckChannelsSection:
    def test_given_no_snapshot_then_ok_skipped(self):
        result = Doc.check_channels_section(None)
        assert result.ok is True
        assert "skipped" in result.message

    def test_given_channels_present_then_ok(self):
        result = Doc.check_channels_section(
            {
                "channels": [{"index": 0, "name": "Kick"}],
            }
        )
        assert result.ok is True
        assert "1 items" in result.message

    def test_given_channels_null_then_fails(self):
        result = Doc.check_channels_section({"channels": None})
        assert result.ok is False


class TestCheckPatternsSection:
    def test_given_patterns_present_then_ok(self):
        result = Doc.check_patterns_section(
            {
                "patterns": [{"index": 1, "name": "Verse"}],
            }
        )
        assert result.ok is True

    def test_given_patterns_null_then_fails(self):
        result = Doc.check_patterns_section({"patterns": None})
        assert result.ok is False


class TestCheckMixerSection:
    def test_given_mixer_present_then_ok(self):
        result = Doc.check_mixer_section(
            {
                "mixer": {"tracks": [], "routing": []},
            }
        )
        assert result.ok is True
        assert "present" in result.message

    def test_given_mixer_null_then_fails(self):
        result = Doc.check_mixer_section({"mixer": None})
        assert result.ok is False


class TestCollectDiagnostics:
    def test_given_all_missing_when_collect_then_midi_port_is_first(
        self,
        tmp_path,
        no_ports,
        doctor_effects,
    ):
        diagnostics = Doc.collect_diagnostics(
            effects=doctor_effects,
            queue_path=str(tmp_path / "pending.json"),
            export_path=str(tmp_path / "export.json"),
        )
        assert [d.name for d in diagnostics] == [
            "midi_port",
            "piano_roll_queue",
            "piano_roll_export",
            "song_position",
            "state_channels",
            "state_patterns",
            "state_mixer",
            "auto_trigger",
            "pyflp",
        ]
        assert Doc.overall_ok(diagnostics) is False

    def test_given_everything_ok_when_collect_then_overall_ok_true(
        self,
        tmp_path,
        matching_port,
        doctor_effects,
    ):
        diagnostics = Doc.collect_diagnostics(
            effects=doctor_effects,
            queue_path=str(tmp_path / "pending.json"),
            export_path=str(tmp_path / "export.json"),
        )
        assert Doc.overall_ok(diagnostics) is True
