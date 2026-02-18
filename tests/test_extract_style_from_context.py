"""
Tests for extract_style_from_context tool and artist_style module.

Pure computation — no mocks, no I/O, no DB.
All tests are deterministic and isolated.

Coverage:
  - ArtistStyle schema: immutability, to_suggestion_params, to_midi_params
  - Pure extraction helpers: extract_genre, extract_keys, extract_modes,
    extract_bpm_range, extract_moods, extract_voicing, extract_melody_characteristics,
    extract_texture, compute_confidence, build_artist_style
  - ExtractStyleFromContext tool: interface, validation, happy path, integration
"""

from tools.music.artist_style import (
    ArtistStyle,
    build_artist_style,
    compute_confidence,
    extract_bpm_range,
    extract_genre,
    extract_keys,
    extract_melody_characteristics,
    extract_modes,
    extract_moods,
    extract_texture,
    extract_voicing,
)
from tools.music.extract_style_from_context import (
    ExtractStyleFromContext,
    _confidence_label,
    _list_found_fields,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SEBASTIEN_LEGER_CHUNKS = [
    "Sebastien Leger is well known for dark hypnotic organic house music.",
    "He typically works in A minor or D minor at around 122-126 bpm.",
    "His productions feature extended 9th chord voicings with layered textures.",
    "The melodic lines are stepwise and repetitive, creating an ethereal atmosphere.",
    "His tracks are dreamy and atmospheric with evolving sparse arrangements.",
]

_TECHNO_CHUNKS = [
    "This artist produces hard techno at fast 135-140 bpm.",
    "Typical chord voicings use raw triads, very minimal and tense.",
    "The texture is dense and driving, with energetic uplifting breakdowns.",
    "Key centers are often in D minor or E minor for techno tension.",
]

_EMPTY_CHUNKS = ["No musical information here at all. Just plain text about cooking."]


# ---------------------------------------------------------------------------
# ArtistStyle schema tests
# ---------------------------------------------------------------------------


class TestArtistStyleSchema:
    """Test ArtistStyle frozen dataclass."""

    def test_is_immutable(self):
        """ArtistStyle must be frozen (immutable)."""
        style = ArtistStyle(artist="Test", genre="organic house")
        try:
            style.artist = "Other"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except Exception:
            pass  # Expected — frozen dataclass

    def test_default_fields(self):
        """Fields with defaults should not raise and have sensible values."""
        style = ArtistStyle(artist="Test", genre=None)
        assert style.preferred_keys == []
        assert style.preferred_modes == []
        assert style.bpm_range is None
        assert style.characteristic_moods == []
        assert style.voicing_style is None
        assert style.melody_characteristics == []
        assert style.texture == []
        assert style.confidence == 0.0
        assert style.chunk_count == 0

    def test_to_suggestion_params_full_style(self):
        """to_suggestion_params should use first key, first mode, genre, voicing."""
        style = ArtistStyle(
            artist="Artist",
            genre="organic house",
            preferred_keys=["A", "D"],
            preferred_modes=["natural minor", "dorian"],
            characteristic_moods=["dark", "dreamy"],
            voicing_style="extended",
        )
        params = style.to_suggestion_params()
        assert params["key"] == "A natural minor"
        assert params["mood"] == "dark"
        assert params["genre"] == "organic house"
        assert params["voicing"] == "extended"

    def test_to_suggestion_params_no_mode(self):
        """No preferred_modes → fallback to 'natural minor'."""
        style = ArtistStyle(
            artist="Artist",
            genre="techno",
            preferred_keys=["E"],
            preferred_modes=[],
        )
        params = style.to_suggestion_params()
        assert params["key"] == "E natural minor"

    def test_to_suggestion_params_no_key(self):
        """No preferred_keys → fallback to 'A'."""
        style = ArtistStyle(
            artist="Artist",
            genre="melodic house",
            preferred_keys=[],
            preferred_modes=["dorian"],
        )
        params = style.to_suggestion_params()
        assert params["key"] == "A dorian"

    def test_to_suggestion_params_empty_style(self):
        """Empty style → full fallback values."""
        style = ArtistStyle(artist="Unknown", genre=None)
        params = style.to_suggestion_params()
        assert params["key"] == "A natural minor"
        assert params["mood"] == "neutral"
        assert params["genre"] == "organic house"
        assert params["voicing"] == "auto"

    def test_to_suggestion_params_no_voicing(self):
        """No voicing_style → fallback to 'auto'."""
        style = ArtistStyle(artist="A", genre="techno", voicing_style=None)
        params = style.to_suggestion_params()
        assert params["voicing"] == "auto"

    def test_to_midi_params_with_bpm_range(self):
        """to_midi_params should use midpoint of bpm_range."""
        style = ArtistStyle(artist="A", genre="organic house", bpm_range=(120, 126))
        params = style.to_midi_params()
        assert params["bpm"] == 123
        assert params["style"] == "organic house"

    def test_to_midi_params_no_bpm(self):
        """No bpm_range → fallback to 124."""
        style = ArtistStyle(artist="A", genre="techno")
        params = style.to_midi_params()
        assert params["bpm"] == 124

    def test_to_midi_params_no_genre(self):
        """No genre → style fallback to 'organic house'."""
        style = ArtistStyle(artist="A", genre=None, bpm_range=(130, 140))
        params = style.to_midi_params()
        assert params["style"] == "organic house"

    def test_bpm_midpoint_even_range(self):
        """Midpoint should use integer division."""
        style = ArtistStyle(artist="A", genre=None, bpm_range=(120, 128))
        assert style.to_midi_params()["bpm"] == 124

    def test_bpm_midpoint_odd_range(self):
        """Midpoint of odd range floors to int."""
        style = ArtistStyle(artist="A", genre=None, bpm_range=(121, 128))
        assert style.to_midi_params()["bpm"] == 124  # (121+128)//2 = 124


# ---------------------------------------------------------------------------
# Pure extraction helpers
# ---------------------------------------------------------------------------


class TestExtractGenre:
    """Test extract_genre pure function."""

    def test_organic_house_detected(self):
        assert extract_genre(["organic house music by Sebastien Leger"]) == "organic house"

    def test_techno_detected(self):
        assert extract_genre(["hard techno track at 135 bpm"]) == "techno"

    def test_most_mentioned_wins(self):
        chunks = ["organic house organic house organic house", "techno techno"]
        assert extract_genre(chunks) == "organic house"

    def test_none_when_no_genre(self):
        assert extract_genre(["A minor scale with D and G chords"]) is None

    def test_empty_chunks_returns_none(self):
        assert extract_genre([]) is None

    def test_case_insensitive(self):
        assert extract_genre(["Organic House style"]) == "organic house"


class TestExtractKeys:
    """Test extract_keys pure function."""

    def test_a_minor_detected(self):
        keys = extract_keys(["works in a minor tonality"])
        assert "A" in keys

    def test_multiple_keys(self):
        keys = extract_keys(["plays in a minor or d minor"])
        assert "A" in keys
        assert "D" in keys

    def test_flat_key_normalized(self):
        """Bb should map to A#."""
        keys = extract_keys(["bb minor progression"])
        assert "A#" in keys

    def test_sharp_key_detected(self):
        keys = extract_keys(["f# minor scale"])
        assert "F#" in keys

    def test_empty_chunks(self):
        assert extract_keys([]) == []

    def test_no_keys_returns_empty(self):
        assert extract_keys(["no musical content here"]) == []

    def test_deduplication(self):
        """Same key mentioned multiple times → appears once."""
        keys = extract_keys(["a minor chords", "a major progression"])
        assert keys.count("A") == 1


class TestExtractModes:
    """Test extract_modes pure function."""

    def test_minor_maps_to_natural_minor(self):
        modes = extract_modes(["dark minor sound"])
        assert "natural minor" in modes

    def test_dorian_detected(self):
        modes = extract_modes(["dorian mode vibes"])
        assert "dorian" in modes

    def test_major_detected(self):
        modes = extract_modes(["bright major key"])
        assert "major" in modes

    def test_harmonic_minor_detected_first(self):
        """'harmonic minor' should be detected (longer phrase matched first)."""
        modes = extract_modes(["harmonic minor scale"])
        assert "harmonic minor" in modes
        # harmonic minor appears first in the list (longer match processed first)
        assert modes.index("harmonic minor") == 0

    def test_empty_returns_empty(self):
        assert extract_modes([]) == []

    def test_no_modes_returns_empty(self):
        assert extract_modes(["cooking and recipes"]) == []


class TestExtractBpmRange:
    """Test extract_bpm_range pure function."""

    def test_explicit_bpm_value(self):
        result = extract_bpm_range(["plays at 124 bpm consistently"])
        assert result == (124, 124)

    def test_bpm_range_two_values(self):
        result = extract_bpm_range(["tracks at 122-126 bpm"])
        assert result == (122, 126)

    def test_descriptive_house_tempo(self):
        result = extract_bpm_range(["typical house tempo"])
        assert result is not None
        assert result[0] >= 110
        assert result[1] <= 140

    def test_no_bpm_returns_none(self):
        result = extract_bpm_range(["A minor chords with dark mood"])
        assert result is None

    def test_empty_chunks_returns_none(self):
        assert extract_bpm_range([]) is None

    def test_out_of_range_bpm_ignored(self):
        """BPM values < 60 or > 200 should be filtered."""
        result = extract_bpm_range(["at 30 bpm or 500 bpm"])
        assert result is None

    def test_multiple_bpm_values_min_max(self):
        result = extract_bpm_range(["ranging from 120 bpm to 128 bpm"])
        assert result == (120, 128)

    def test_no_bpm_suffix_not_matched(self):
        """Number without 'bpm' should not match."""
        result = extract_bpm_range(["the track has 32 bars"])
        assert result is None


class TestExtractMoods:
    """Test extract_moods pure function."""

    def test_dark_detected(self):
        moods = extract_moods(["dark hypnotic sound"])
        assert "dark" in moods

    def test_euphoric_detected(self):
        moods = extract_moods(["uplifting euphoric build"])
        assert "euphoric" in moods

    def test_dreamy_detected(self):
        moods = extract_moods(["dreamy atmospheric pad"])
        assert "dreamy" in moods

    def test_tense_detected(self):
        moods = extract_moods(["tense anxious energy"])
        assert "tense" in moods

    def test_deduplication(self):
        """Same mood mentioned via different keywords → appears once."""
        moods = extract_moods(["dark shadowy darker vibes"])
        assert moods.count("dark") == 1

    def test_empty_returns_empty(self):
        assert extract_moods([]) == []

    def test_all_moods_are_valid(self):
        """Extracted moods must be valid for suggest_chord_progression."""
        from tools.music.theory import MOOD_DEGREE_WEIGHTS

        valid = set(MOOD_DEGREE_WEIGHTS.keys())
        moods = extract_moods(["dark dreamy euphoric tense neutral minimal"])
        for mood in moods:
            assert mood in valid


class TestExtractVoicing:
    """Test extract_voicing pure function."""

    def test_extended_from_9th(self):
        voicing = extract_voicing(["uses 9th chord extensions"])
        assert voicing == "extended"

    def test_seventh_detected(self):
        voicing = extract_voicing(["maj7 and min7 chords throughout"])
        assert voicing == "seventh"

    def test_triads_detected(self):
        voicing = extract_voicing(["raw triads, minimal harmony"])
        assert voicing == "triads"

    def test_most_mentioned_wins(self):
        voicing = extract_voicing(["9th 9ths extended extended lush", "triad"])
        assert voicing == "extended"

    def test_none_when_no_voicing(self):
        voicing = extract_voicing(["no chord information here"])
        assert voicing is None

    def test_empty_returns_none(self):
        assert extract_voicing([]) is None


class TestExtractMelodyCharacteristics:
    """Test extract_melody_characteristics pure function."""

    def test_stepwise_detected(self):
        chars = extract_melody_characteristics(["stepwise melodic motion"])
        assert "stepwise" in chars

    def test_arpeggiated_detected(self):
        chars = extract_melody_characteristics(["arpeggio patterns in the lead"])
        assert "arpeggiated" in chars

    def test_repetitive_detected(self):
        chars = extract_melody_characteristics(["repetitive ostinato motif"])
        assert "repetitive" in chars

    def test_empty_returns_empty(self):
        assert extract_melody_characteristics([]) == []

    def test_deduplication(self):
        chars = extract_melody_characteristics(["stepwise smooth conjunct motion"])
        assert chars.count("stepwise") == 1


class TestExtractTexture:
    """Test extract_texture pure function."""

    def test_sparse_detected(self):
        texture = extract_texture(["sparse minimal arrangement"])
        assert "sparse" in texture

    def test_dense_detected(self):
        texture = extract_texture(["layered dense rich sound"])
        assert "dense" in texture

    def test_evolving_detected(self):
        texture = extract_texture(["evolving progressive build"])
        assert "evolving" in texture

    def test_hypnotic_detected(self):
        texture = extract_texture(["hypnotic repetitive groove"])
        assert "hypnotic" in texture

    def test_empty_returns_empty(self):
        assert extract_texture([]) == []


class TestComputeConfidence:
    """Test compute_confidence pure function."""

    def test_empty_style_confidence_zero(self):
        style = ArtistStyle(artist="X", genre=None)
        assert compute_confidence(style) == 0.0

    def test_genre_only_confidence(self):
        style = ArtistStyle(artist="X", genre="organic house")
        assert compute_confidence(style) == 0.20

    def test_full_style_high_confidence(self):
        style = ArtistStyle(
            artist="X",
            genre="organic house",
            preferred_keys=["A"],
            preferred_modes=["natural minor"],
            bpm_range=(122, 126),
            characteristic_moods=["dark"],
            voicing_style="extended",
            melody_characteristics=["stepwise"],
        )
        confidence = compute_confidence(style)
        assert confidence >= 0.95

    def test_confidence_in_range(self):
        """Confidence must always be in [0.0, 1.0]."""
        style = ArtistStyle(
            artist="X",
            genre="organic house",
            preferred_keys=["A", "D", "G"],
            preferred_modes=["natural minor", "dorian"],
            bpm_range=(120, 128),
            characteristic_moods=["dark", "dreamy"],
            voicing_style="extended",
            melody_characteristics=["stepwise", "repetitive"],
        )
        c = compute_confidence(style)
        assert 0.0 <= c <= 1.0


class TestBuildArtistStyle:
    """Test build_artist_style end-to-end."""

    def test_sebastien_leger_profile(self):
        """Full organic house deconstruction chunks should extract well."""
        style = build_artist_style("Sebastien Leger", _SEBASTIEN_LEGER_CHUNKS)
        assert style.artist == "Sebastien Leger"
        assert style.genre == "organic house"
        assert "A" in style.preferred_keys
        assert "natural minor" in style.preferred_modes
        assert style.bpm_range is not None
        assert "dark" in style.characteristic_moods or "dreamy" in style.characteristic_moods
        assert style.voicing_style == "extended"
        assert style.confidence > 0.7
        assert style.chunk_count == len(_SEBASTIEN_LEGER_CHUNKS)

    def test_techno_profile(self):
        """Techno chunks should extract correct genre and voicing."""
        style = build_artist_style("Techno Artist", _TECHNO_CHUNKS)
        assert style.genre == "techno"
        assert style.voicing_style == "triads"
        assert style.bpm_range is not None
        assert style.bpm_range[0] >= 130

    def test_empty_chunks_returns_low_confidence(self):
        """Non-musical text → low confidence, empty fields."""
        style = build_artist_style("Unknown", _EMPTY_CHUNKS)
        assert style.confidence < 0.3
        assert style.genre is None
        assert style.preferred_keys == []

    def test_artist_name_preserved(self):
        style = build_artist_style("Rodriguez Jr.", _SEBASTIEN_LEGER_CHUNKS)
        assert style.artist == "Rodriguez Jr."

    def test_chunk_count_matches_input(self):
        chunks = _SEBASTIEN_LEGER_CHUNKS[:3]
        style = build_artist_style("X", chunks)
        assert style.chunk_count == 3

    def test_to_suggestion_params_usable(self):
        """to_suggestion_params output should be valid for suggest_chord_progression."""
        from tools.music.suggest_chord_progression import SuggestChordProgression

        style = build_artist_style("Sebastien Leger", _SEBASTIEN_LEGER_CHUNKS)
        params = style.to_suggestion_params()
        tool = SuggestChordProgression()
        result = tool(**params, bars=4)
        assert result.success is True, f"suggest_chord_progression failed: {result.error}"

    def test_to_midi_params_usable(self):
        """to_midi_params BPM should be valid for generate_midi_pattern."""
        style = build_artist_style("Sebastien Leger", _SEBASTIEN_LEGER_CHUNKS)
        params = style.to_midi_params()
        assert 60 <= params["bpm"] <= 220


# ---------------------------------------------------------------------------
# Tool interface tests
# ---------------------------------------------------------------------------


class TestExtractStyleFromContextProperties:
    """Test tool interface contract."""

    _tool = ExtractStyleFromContext()

    def test_tool_name(self):
        assert self._tool.name == "extract_style_from_context"

    def test_description_mentions_key_concepts(self):
        desc = self._tool.description.lower()
        assert "style" in desc
        assert "chunk" in desc
        assert "artist" in desc

    def test_has_three_parameters(self):
        names = [p.name for p in self._tool.parameters]
        assert "chunks" in names
        assert "artist" in names
        assert "genre_hint" in names

    def test_chunks_and_artist_required(self):
        required = [p.name for p in self._tool.parameters if p.required]
        assert "chunks" in required
        assert "artist" in required

    def test_genre_hint_optional_with_default(self):
        optional = {p.name: p.default for p in self._tool.parameters if not p.required}
        assert "genre_hint" in optional
        assert optional["genre_hint"] == ""


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestExtractStyleFromContextValidation:
    """Test domain-level input validation."""

    _tool = ExtractStyleFromContext()

    def test_empty_chunks_rejected(self):
        result = self._tool(chunks=[], artist="Test")
        assert result.success is False
        assert "chunks" in result.error.lower()

    def test_none_chunks_rejected(self):
        result = self._tool(artist="Test")
        assert result.success is False

    def test_empty_artist_rejected(self):
        result = self._tool(chunks=["text"], artist="")
        assert result.success is False
        assert "artist" in result.error.lower()

    def test_missing_artist_rejected(self):
        result = self._tool(chunks=["text"])
        assert result.success is False
        assert "artist" in result.error.lower()

    def test_chunks_too_many_rejected(self):
        from tools.music.extract_style_from_context import MAX_CHUNKS

        chunks = ["chunk"] * (MAX_CHUNKS + 1)
        result = self._tool(chunks=chunks, artist="Test")
        assert result.success is False
        assert "chunks" in result.error.lower()

    def test_artist_too_long_rejected(self):
        from tools.music.extract_style_from_context import MAX_ARTIST_LEN

        result = self._tool(chunks=["text"], artist="X" * (MAX_ARTIST_LEN + 1))
        assert result.success is False
        assert "artist" in result.error.lower()

    def test_invalid_chunk_type_rejected(self):
        """Chunk that is a dict (non-coercible) should fail."""
        result = self._tool(chunks=[{"key": "value"}], artist="Test")
        assert result.success is False

    def test_integer_chunks_coerced(self):
        """Integer chunks should be coerced to string (not fail)."""
        result = self._tool(chunks=[123, 456], artist="Test")
        assert result.success is True

    def test_float_chunks_coerced(self):
        """Float chunks should be coerced to string (not fail)."""
        result = self._tool(chunks=[1.5, 2.7], artist="Test")
        assert result.success is True

    def test_not_a_list_rejected(self):
        """chunks must be a list, not a string."""
        result = self._tool(chunks="text chunk", artist="Test")
        assert result.success is False


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


class TestExtractStyleFromContextHappyPath:
    """Test successful style extraction."""

    _tool = ExtractStyleFromContext()

    def test_sebastien_leger_returns_success(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert result.success is True

    def test_result_has_required_fields(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert result.success is True
        required = {
            "artist_style",
            "suggestion_params",
            "midi_params",
            "confidence",
            "confidence_label",
        }
        assert required.issubset(result.data.keys())

    def test_artist_style_has_all_schema_fields(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        as_dict = result.data["artist_style"]
        required_keys = {
            "artist",
            "genre",
            "preferred_keys",
            "preferred_modes",
            "bpm_range",
            "characteristic_moods",
            "voicing_style",
            "melody_characteristics",
            "texture",
            "confidence",
            "chunk_count",
        }
        assert required_keys.issubset(as_dict.keys())

    def test_suggestion_params_has_required_keys(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        params = result.data["suggestion_params"]
        assert "key" in params
        assert "mood" in params
        assert "genre" in params
        assert "voicing" in params

    def test_midi_params_has_required_keys(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        params = result.data["midi_params"]
        assert "bpm" in params
        assert "style" in params

    def test_midi_bpm_in_valid_range(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        bpm = result.data["midi_params"]["bpm"]
        assert 60 <= bpm <= 220

    def test_confidence_in_range(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert 0.0 <= result.data["confidence"] <= 1.0

    def test_high_confidence_for_rich_chunks(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert result.data["confidence"] >= 0.7
        assert result.data["confidence_label"] == "high"

    def test_low_confidence_for_empty_content(self):
        result = self._tool(chunks=_EMPTY_CHUNKS, artist="Unknown")
        assert result.data["confidence"] < 0.3
        assert result.data["confidence_label"] == "low"

    def test_genre_hint_applied_when_not_detected(self):
        """genre_hint should fill in when auto-detection fails."""
        result = self._tool(
            chunks=_EMPTY_CHUNKS,
            artist="Unknown",
            genre_hint="melodic house",
        )
        assert result.success is True
        # genre_hint applied
        assert result.data["artist_style"]["genre"] == "melodic house"

    def test_genre_hint_not_overrides_detected(self):
        """If genre detected from chunks, hint should not override it."""
        result = self._tool(
            chunks=_TECHNO_CHUNKS,
            artist="Techno Artist",
            genre_hint="organic house",
        )
        # Techno is detected from chunks → should NOT be "organic house"
        assert result.data["artist_style"]["genre"] == "techno"

    def test_metadata_has_required_fields(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert "chunk_count" in result.metadata
        assert "genre" in result.metadata
        assert "fields_found" in result.metadata

    def test_chunk_count_in_metadata(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert result.metadata["chunk_count"] == len(_SEBASTIEN_LEGER_CHUNKS)

    def test_fields_found_is_list(self):
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert isinstance(result.metadata["fields_found"], list)

    def test_suggestion_params_feeds_chord_progression(self):
        """Full pipeline: extract style → suggest_chord_progression."""
        from tools.music.suggest_chord_progression import SuggestChordProgression

        extract_result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        assert extract_result.success is True

        params = extract_result.data["suggestion_params"]
        chord_tool = SuggestChordProgression()
        chord_result = chord_tool(**params, bars=4)
        assert chord_result.success is True
        assert len(chord_result.data["progression"]) == 4

    def test_single_chunk_works(self):
        """Single chunk should not crash — may have low confidence."""
        result = self._tool(
            chunks=["organic house track in A minor at 124 bpm with dreamy atmosphere"],
            artist="Artist",
        )
        assert result.success is True

    def test_techno_extracts_correct_profile(self):
        """Techno chunks should map to techno genre and triads voicing."""
        result = self._tool(chunks=_TECHNO_CHUNKS, artist="Techno Producer")
        assert result.success is True
        assert result.data["artist_style"]["genre"] == "techno"
        assert result.data["artist_style"]["voicing_style"] == "triads"

    def test_bpm_range_serialized_as_list(self):
        """bpm_range tuple must be serialized as list in data dict (JSON-safe)."""
        result = self._tool(chunks=_SEBASTIEN_LEGER_CHUNKS, artist="Sebastien Leger")
        bpm_range = result.data["artist_style"]["bpm_range"]
        assert bpm_range is None or isinstance(bpm_range, list)


# ---------------------------------------------------------------------------
# Pure helpers: _confidence_label, _list_found_fields
# ---------------------------------------------------------------------------


class TestConfidenceLabel:
    """Test _confidence_label pure function."""

    def test_high(self):
        assert _confidence_label(0.7) == "high"
        assert _confidence_label(1.0) == "high"
        assert _confidence_label(0.95) == "high"

    def test_medium(self):
        assert _confidence_label(0.3) == "medium"
        assert _confidence_label(0.5) == "medium"
        assert _confidence_label(0.69) == "medium"

    def test_low(self):
        assert _confidence_label(0.0) == "low"
        assert _confidence_label(0.1) == "low"
        assert _confidence_label(0.29) == "low"


class TestListFoundFields:
    """Test _list_found_fields pure function."""

    def test_all_fields_found(self):
        style = ArtistStyle(
            artist="X",
            genre="organic house",
            preferred_keys=["A"],
            preferred_modes=["natural minor"],
            bpm_range=(122, 126),
            characteristic_moods=["dark"],
            voicing_style="extended",
            melody_characteristics=["stepwise"],
            texture=["sparse"],
        )
        fields = _list_found_fields(style)
        assert "genre" in fields
        assert "preferred_keys" in fields
        assert "preferred_modes" in fields
        assert "bpm_range" in fields
        assert "characteristic_moods" in fields
        assert "voicing_style" in fields
        assert "melody_characteristics" in fields
        assert "texture" in fields

    def test_empty_style_no_fields(self):
        style = ArtistStyle(artist="X", genre=None)
        fields = _list_found_fields(style)
        assert fields == []

    def test_only_genre_found(self):
        style = ArtistStyle(artist="X", genre="techno")
        fields = _list_found_fields(style)
        assert fields == ["genre"]

    def test_returns_list(self):
        style = ArtistStyle(artist="X", genre=None)
        assert isinstance(_list_found_fields(style), list)
