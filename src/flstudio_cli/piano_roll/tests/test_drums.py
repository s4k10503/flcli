"""Tests for the GM drum-name → MIDI pitch map.

This file pins the *contract* of the friendly drum names the CLI accepts
(e.g. ``--drum kick`` resolves to pitch 36).  Without these tests a
typo or accidental reordering of the constant could silently change
which note plays for ``kick`` / ``snare`` / etc.
"""

from __future__ import annotations

from flstudio_cli.piano_roll.domain.drums import DRUMS


class TestGmDrumMappings:
    def test_kick_resolves_to_gm_acoustic_bass_drum(self) -> None:
        assert DRUMS["kick"] == 36

    def test_snare_resolves_to_gm_acoustic_snare(self) -> None:
        assert DRUMS["snare"] == 38

    def test_clap_resolves_to_gm_hand_clap(self) -> None:
        assert DRUMS["clap"] == 39

    def test_chh_resolves_to_gm_closed_hi_hat(self) -> None:
        assert DRUMS["chh"] == 42

    def test_ohh_resolves_to_gm_open_hi_hat(self) -> None:
        assert DRUMS["ohh"] == 46

    def test_every_value_is_in_valid_midi_pitch_range(self) -> None:
        # Pitches must be 0..127 to be sendable as MIDI note-on.
        for name, pitch in DRUMS.items():
            assert 0 <= pitch <= 127, f"{name!r} maps to invalid pitch {pitch}"
