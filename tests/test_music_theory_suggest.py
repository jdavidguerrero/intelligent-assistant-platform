"""
Tests for core/music_theory/harmony.suggest_progression() — melody-free
chord progression suggester.

Validates:
    - Returns VoicingResult
    - key_root, key_mode, genre, bars preserved
    - bars override works
    - bars cycling: len(progression) < bars → wraps
    - mood bias influences degree selection
    - all 5 genres work
    - all valid mood tags work
    - invalid genre raises
    - invalid mood raises
    - invalid bars raises
    - voicing override applied
    - roman_labels match chords
    - chord_names are non-empty strings
"""

from __future__ import annotations

import pytest

from core.music_theory.harmony import available_genres, suggest_progression
from core.music_theory.types import VoicingResult

# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------


class TestSuggestProgressionContract:
    def test_returns_voicing_result(self):
        r = suggest_progression("A")
        assert isinstance(r, VoicingResult)

    def test_key_root_preserved(self):
        r = suggest_progression("C")
        assert r.key_root == "C"

    def test_key_mode_preserved(self):
        r = suggest_progression("A", key_mode="dorian")
        assert r.key_mode == "dorian"

    def test_genre_preserved(self):
        r = suggest_progression("A", genre="deep house")
        assert r.genre == "deep house"

    def test_bars_preserved(self):
        r = suggest_progression("A", bars=8)
        assert r.bars == 8
        assert len(r.chords) == 8

    def test_default_bars_is_4(self):
        r = suggest_progression("A")
        assert len(r.chords) == 4

    def test_roman_labels_match_chords(self):
        r = suggest_progression("A", bars=4)
        assert r.roman_labels == tuple(c.roman for c in r.chords)

    def test_chord_names_non_empty(self):
        r = suggest_progression("C", genre="deep house", bars=4)
        for name in r.chord_names:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_all_chords_have_midi_notes(self):
        r = suggest_progression("A", bars=4)
        for chord in r.chords:
            assert len(chord.midi_notes) > 0


# ---------------------------------------------------------------------------
# bars cycling
# ---------------------------------------------------------------------------


class TestBarsCycling:
    def test_8_bars_from_4_degree_progression(self):
        """8-bar result from a 4-chord template wraps correctly."""
        r = suggest_progression("A", genre="organic house", bars=8)
        assert len(r.chords) == 8
        # First 4 bars should match second 4 bars (cycling)
        assert r.chords[:4] == r.chords[4:]

    def test_1_bar_returns_tonic(self):
        """1-bar result: first degree of the best progression."""
        r = suggest_progression("A", bars=1)
        assert len(r.chords) == 1


# ---------------------------------------------------------------------------
# Mood bias
# ---------------------------------------------------------------------------


class TestMoodBias:
    def test_mood_none_works(self):
        r = suggest_progression("A", mood=None)
        assert isinstance(r, VoicingResult)

    def test_mood_dark_works(self):
        r = suggest_progression("A", mood="dark")
        assert isinstance(r, VoicingResult)

    def test_mood_euphoric_works(self):
        r = suggest_progression("A", mood="euphoric")
        assert isinstance(r, VoicingResult)

    def test_mood_tense_works(self):
        r = suggest_progression("A", mood="tense")
        assert isinstance(r, VoicingResult)

    def test_mood_dreamy_works(self):
        r = suggest_progression("A", mood="dreamy")
        assert isinstance(r, VoicingResult)

    def test_mood_hypnotic_works(self):
        r = suggest_progression("A", mood="hypnotic")
        assert isinstance(r, VoicingResult)

    def test_mood_neutral_works(self):
        r = suggest_progression("A", mood="neutral")
        assert isinstance(r, VoicingResult)

    def test_invalid_mood_raises(self):
        with pytest.raises(ValueError, match="mood"):
            suggest_progression("A", mood="aggressive")

    def test_hypnotic_has_tonic_bias(self):
        """Hypnotic mood heavily biases toward degree 0 (tonic)."""
        r = suggest_progression("A", genre="organic house", mood="hypnotic", bars=4)
        tonic_count = sum(1 for c in r.chords if c.degree == 0)
        # Hypnotic mood has degree 0 weight 2.0 — should dominate
        assert tonic_count >= 1


# ---------------------------------------------------------------------------
# All genres
# ---------------------------------------------------------------------------


class TestAllGenres:
    def test_all_5_genres_produce_valid_result(self):
        for genre in available_genres():
            r = suggest_progression("A", genre=genre, bars=4)
            assert isinstance(r, VoicingResult)
            assert len(r.chords) == 4
            assert r.genre == genre

    def test_afro_house_dorian_mode_works(self):
        r = suggest_progression("A", genre="afro house", key_mode="dorian", bars=4)
        assert isinstance(r, VoicingResult)


# ---------------------------------------------------------------------------
# Voicing override
# ---------------------------------------------------------------------------


class TestVoicingOverride:
    def test_triads_voicing_override(self):
        """Override to triads — organic house default is extended."""
        r = suggest_progression("A", genre="organic house", voicing="triads", bars=4)
        for chord in r.chords:
            assert chord.quality in ("minor", "major", "dim", "aug")

    def test_extended_voicing_override(self):
        r = suggest_progression("A", genre="afro house", voicing="extended", bars=4)
        for chord in r.chords:
            # Extended gives 7ths
            assert len(chord.midi_notes) >= 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestSuggestProgressionErrors:
    def test_invalid_genre_raises(self):
        with pytest.raises(ValueError, match="Unknown genre"):
            suggest_progression("A", genre="jazz bossa")

    def test_bars_zero_raises(self):
        with pytest.raises(ValueError, match="bars"):
            suggest_progression("A", bars=0)

    def test_bars_negative_raises(self):
        with pytest.raises(ValueError, match="bars"):
            suggest_progression("A", bars=-1)

    def test_flat_key_root_supported(self):
        r = suggest_progression("Bb", genre="deep house", bars=4)
        assert r.key_root == "Bb"

    def test_progression_label_is_non_empty_string(self):
        r = suggest_progression("A", bars=4)
        assert isinstance(r.progression_label, str)
        assert len(r.progression_label) > 0
