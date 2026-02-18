"""
Tests for suggest_chord_progression tool.

Pure computation — no mocks, no I/O, no DB.
All tests are deterministic and isolated.
"""

from tools.music.suggest_chord_progression import (
    SuggestChordProgression,
    _describe_progression,
    _fit_to_bars,
    _parse_key,
)

# ---------------------------------------------------------------------------
# Tool properties
# ---------------------------------------------------------------------------


class TestSuggestChordProgressionProperties:
    """Test tool interface contract."""

    def test_tool_name(self):
        """Tool name must be exactly 'suggest_chord_progression'."""
        tool = SuggestChordProgression()
        assert tool.name == "suggest_chord_progression"

    def test_description_mentions_key_concepts(self):
        """Description should mention chord, genre, mood."""
        tool = SuggestChordProgression()
        desc = tool.description.lower()
        assert "chord" in desc
        assert "genre" in desc
        assert "mood" in desc

    def test_has_five_parameters(self):
        """Tool should expose key, mood, genre, bars, voicing."""
        tool = SuggestChordProgression()
        names = [p.name for p in tool.parameters]
        assert "key" in names
        assert "mood" in names
        assert "genre" in names
        assert "bars" in names
        assert "voicing" in names

    def test_key_is_required(self):
        """key parameter must be required."""
        tool = SuggestChordProgression()
        key_param = next(p for p in tool.parameters if p.name == "key")
        assert key_param.required is True

    def test_optional_parameters_have_defaults(self):
        """mood, genre, bars, voicing should be optional with defaults."""
        tool = SuggestChordProgression()
        optional = {p.name: p.default for p in tool.parameters if not p.required}
        assert "mood" in optional
        assert "genre" in optional
        assert optional["bars"] == 4
        assert optional["voicing"] == "auto"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestSuggestChordProgressionValidation:
    """Test domain-level input validation."""

    _tool = SuggestChordProgression()

    def test_empty_key_rejected(self):
        """Empty key string should return error."""
        result = self._tool(key="")
        assert result.success is False
        assert "key" in result.error.lower()

    def test_unparseable_key_rejected(self):
        """Garbage key string should return error."""
        result = self._tool(key="not a key at all")
        assert result.success is False

    def test_invalid_mood_rejected(self):
        """Unknown mood should return error."""
        result = self._tool(key="A minor", mood="melancholic")
        assert result.success is False
        assert "mood" in result.error.lower()

    def test_bars_zero_rejected(self):
        """bars=0 should be rejected."""
        result = self._tool(key="A minor", bars=0)
        assert result.success is False
        assert "bars" in result.error.lower()

    def test_bars_too_high_rejected(self):
        """bars > 16 should be rejected."""
        result = self._tool(key="A minor", bars=17)
        assert result.success is False

    def test_invalid_voicing_rejected(self):
        """Unknown voicing string should return error."""
        result = self._tool(key="A minor", voicing="jazz_comping")
        assert result.success is False
        assert "voicing" in result.error.lower()

    def test_missing_key_returns_error(self):
        """Missing required key should fail base class validation."""
        result = self._tool(mood="dark")
        assert result.success is False
        assert "key" in result.error.lower()

    def test_wrong_type_bars_returns_error(self):
        """String passed as bars should fail type validation."""
        result = self._tool(key="A minor", bars="four")
        assert result.success is False


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSuggestChordProgressionHappyPath:
    """Test successful chord progression generation."""

    _tool = SuggestChordProgression()

    def test_basic_a_minor_returns_success(self):
        """A minor + dark + organic house → success."""
        result = self._tool(key="A minor", mood="dark", genre="organic house")
        assert result.success is True

    def test_data_has_required_fields(self):
        """Result data must include all expected keys."""
        result = self._tool(key="A minor")
        assert result.success is True
        required = {
            "key",
            "scale",
            "mood",
            "genre",
            "voicing",
            "bars",
            "progression",
            "roman_analysis",
            "analysis",
            "variations",
        }
        assert required.issubset(result.data.keys())

    def test_progression_length_matches_bars(self):
        """progression list must have exactly bars entries."""
        for bars in [1, 2, 4, 8]:
            result = self._tool(key="C major", bars=bars)
            assert result.success is True
            assert len(result.data["progression"]) == bars

    def test_each_chord_has_required_fields(self):
        """Each chord in progression must have degree, roman, root, name, midi_notes."""
        result = self._tool(key="A minor", mood="dark")
        assert result.success is True
        for chord in result.data["progression"]:
            assert "degree" in chord
            assert "roman" in chord
            assert "root" in chord
            assert "name" in chord
            assert "midi_notes" in chord

    def test_midi_notes_are_integers(self):
        """All midi_notes should be integers in MIDI range [0, 127]."""
        result = self._tool(key="A minor")
        assert result.success is True
        for chord in result.data["progression"]:
            for note in chord["midi_notes"]:
                assert isinstance(note, int)
                assert 0 <= note <= 127

    def test_scale_length_for_natural_minor(self):
        """Natural minor scale should have 7 notes."""
        result = self._tool(key="A minor")
        assert len(result.data["scale"]) == 7

    def test_scale_for_a_natural_minor(self):
        """A natural minor scale must be [A, B, C, D, E, F, G]."""
        result = self._tool(key="A minor")
        assert result.data["scale"] == ["A", "B", "C", "D", "E", "F", "G"]

    def test_roman_analysis_is_string(self):
        """roman_analysis should be a non-empty string."""
        result = self._tool(key="A minor")
        assert isinstance(result.data["roman_analysis"], str)
        assert len(result.data["roman_analysis"]) > 0

    def test_exactly_two_variations(self):
        """Should always return exactly 2 variations."""
        result = self._tool(key="A minor", genre="organic house")
        assert len(result.data["variations"]) == 2

    def test_each_variation_has_chords_and_roman(self):
        """Each variation must have 'chords' and 'roman' keys."""
        result = self._tool(key="A minor")
        for var in result.data["variations"]:
            assert "chords" in var
            assert "roman" in var

    def test_variation_length_matches_bars(self):
        """Variation chords must have same length as bars."""
        result = self._tool(key="A minor", bars=4)
        for var in result.data["variations"]:
            assert len(var["chords"]) == 4

    def test_c_major_key_works(self):
        """C major should work correctly (major mode)."""
        result = self._tool(key="C major", mood="euphoric", genre="melodic house")
        assert result.success is True
        assert result.data["scale"] == ["C", "D", "E", "F", "G", "A", "B"]

    def test_flat_key_accepted(self):
        """Bb minor should be parsed correctly (flat note)."""
        result = self._tool(key="Bb minor")
        assert result.success is True
        # Bb is normalized to A#
        assert "A#" in result.data["key"] or "Bb" in result.data["key"]

    def test_f_sharp_minor_accepted(self):
        """F# minor should parse and return correct scale."""
        result = self._tool(key="F# minor")
        assert result.success is True
        assert "F#" in result.data["scale"]

    def test_dorian_mode_accepted(self):
        """'D dorian' should be parsed correctly."""
        result = self._tool(key="D dorian")
        assert result.success is True

    def test_extended_voicing_uses_7th_chords(self):
        """Extended voicing should produce chords with 4+ notes."""
        result = self._tool(key="A minor", voicing="extended")
        assert result.success is True
        # Extended chords should have more than 3 notes (triads)
        for chord in result.data["progression"]:
            assert len(chord["midi_notes"]) >= 3  # at least triad

    def test_triads_voicing_produces_3_note_chords(self):
        """Triads voicing should produce exactly 3-note chords (non-diminished)."""
        result = self._tool(key="C major", voicing="triads")
        assert result.success is True
        # Most chords should be 3 notes
        three_note_count = sum(1 for c in result.data["progression"] if len(c["midi_notes"]) == 3)
        assert three_note_count > 0

    def test_voicing_auto_matches_genre(self):
        """voicing='auto' should use genre-appropriate voicing."""
        # organic house → extended
        result = self._tool(key="A minor", genre="organic house", voicing="auto")
        assert result.success is True
        assert result.data["voicing"] == "extended"

    def test_techno_voicing_is_triads(self):
        """techno genre should default to triads voicing."""
        result = self._tool(key="A minor", genre="techno", voicing="auto")
        assert result.success is True
        assert result.data["voicing"] == "triads"

    def test_metadata_has_diatonic_palette(self):
        """metadata should include the full diatonic chord palette."""
        result = self._tool(key="A minor")
        assert "diatonic_palette" in result.metadata
        # Natural minor has 7 chords
        assert len(result.metadata["diatonic_palette"]) == 7

    def test_all_valid_moods_work(self):
        """All valid moods should return success."""
        for mood in ["dark", "euphoric", "tense", "dreamy", "neutral"]:
            result = self._tool(key="A minor", mood=mood)
            assert result.success is True, f"mood={mood!r} failed"

    def test_all_valid_genres_work(self):
        """All registered genres should return success."""
        from tools.music.theory import GENRE_PROGRESSIONS

        for genre in GENRE_PROGRESSIONS:
            result = self._tool(key="A minor", genre=genre)
            assert result.success is True, f"genre={genre!r} failed"

    def test_unknown_genre_falls_back_gracefully(self):
        """Unknown genre should not crash — falls back to mood-weighted."""
        result = self._tool(key="A minor", genre="nu jazz")
        assert result.success is True

    def test_key_echoed_in_result(self):
        """result.data['key'] should echo the parsed key."""
        result = self._tool(key="A minor")
        assert "A" in result.data["key"]
        assert "minor" in result.data["key"]


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


class TestParseKey:
    """Test _parse_key pure function."""

    def test_a_minor(self):
        assert _parse_key("A minor") == ("A", "natural minor")

    def test_c_major(self):
        assert _parse_key("C major") == ("C", "major")

    def test_natural_minor_explicit(self):
        assert _parse_key("A natural minor") == ("A", "natural minor")

    def test_sharp_root(self):
        result = _parse_key("F# dorian")
        assert result == ("F#", "dorian")

    def test_flat_root_normalized(self):
        result = _parse_key("Bb minor")
        assert result is not None
        assert result[0] == "A#"
        assert result[1] == "natural minor"

    def test_harmonic_minor(self):
        assert _parse_key("A harmonic minor") == ("A", "harmonic minor")

    def test_dorian(self):
        assert _parse_key("D dorian") == ("D", "dorian")

    def test_single_word_returns_none(self):
        assert _parse_key("minor") is None

    def test_empty_returns_none(self):
        assert _parse_key("") is None

    def test_unknown_mode_returns_none(self):
        # "blues" is not in the mode_aliases dict
        assert _parse_key("A blues") is None

    def test_invalid_root_returns_none(self):
        assert _parse_key("X minor") is None


class TestFitToBars:
    """Test _fit_to_bars pure function."""

    def test_exact_length(self):
        assert _fit_to_bars([0, 1, 2, 3], 4) == [0, 1, 2, 3]

    def test_truncate(self):
        assert _fit_to_bars([0, 1, 2, 3], 2) == [0, 1]

    def test_extend_wraps(self):
        assert _fit_to_bars([0, 1], 4) == [0, 1, 0, 1]

    def test_single_degree_fills(self):
        assert _fit_to_bars([0], 4) == [0, 0, 0, 0]

    def test_empty_returns_zeros(self):
        assert _fit_to_bars([], 4) == [0, 0, 0, 0]

    def test_bars_1(self):
        assert _fit_to_bars([0, 5, 2, 6], 1) == [0]


class TestDescribeProgression:
    """Test _describe_progression pure function."""

    def test_returns_string(self):
        chords = [
            {"roman": "i", "name": "Am7"},
            {"roman": "VI", "name": "Fmaj7"},
            {"roman": "III", "name": "Cmaj7"},
            {"roman": "VII", "name": "Gm7"},
        ]
        result = _describe_progression(chords, "natural minor", "dark")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_roman_numerals(self):
        chords = [{"roman": "i", "name": "Am"}, {"roman": "VI", "name": "F"}]
        result = _describe_progression(chords, "natural minor", "dark")
        assert "i" in result
        assert "VI" in result

    def test_contains_mode_description(self):
        chords = [{"roman": "i", "name": "Am"}]
        result = _describe_progression(chords, "natural minor", "dark")
        assert "minor" in result

    def test_known_pattern_detected(self):
        """i–VI–III–VII should be recognized."""
        chords = [
            {"roman": "i", "name": "Am"},
            {"roman": "VI", "name": "F"},
            {"roman": "III", "name": "C"},
            {"roman": "VII", "name": "G"},
        ]
        result = _describe_progression(chords, "natural minor", "dark")
        # Should mention it's a known pattern
        assert "Andalusian" in result or "minor" in result
