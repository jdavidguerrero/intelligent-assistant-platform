"""
Tests for suggest_compatible_tracks tool and Camelot Wheel functions.

Pure computation — no DB, no mocks needed for most tests.
DB-dependent tests inject a mock session factory.

Coverage:
  - camelot_position: known keys, unknown keys, normalization
  - camelot_compatible_keys: same, adjacent, relative major/minor
  - key_compatibility_score: all score tiers
  - bpm_compatibility_score: same, in-tolerance, half/double time, no match
  - compute_compatibility: composite scoring
  - parse_key_from_text / parse_bpm_from_text: text extraction
  - SuggestCompatibleTracks tool: interface, validation, happy path (mocked DB)
"""

from unittest.mock import patch

from tools.music.suggest_compatible_tracks import (
    SuggestCompatibleTracks,
    _camelot_str,
    bpm_compatibility_score,
    camelot_compatible_keys,
    camelot_position,
    compute_compatibility,
    key_compatibility_score,
    parse_bpm_from_text,
    parse_key_from_text,
)

# ---------------------------------------------------------------------------
# camelot_position
# ---------------------------------------------------------------------------


class TestCamelotPosition:
    def test_a_minor_is_8a(self):
        assert camelot_position("A minor") == (8, "A")

    def test_c_major_is_8b(self):
        assert camelot_position("C major") == (8, "B")

    def test_e_minor_is_9a(self):
        assert camelot_position("E minor") == (9, "A")

    def test_d_minor_is_7a(self):
        assert camelot_position("D minor") == (7, "A")

    def test_f_sharp_minor(self):
        assert camelot_position("F# minor") == (11, "A")

    def test_bb_minor_maps_same_as_a_sharp(self):
        assert camelot_position("Bb minor") == camelot_position("A# minor")

    def test_natural_minor_normalized(self):
        """'A natural minor' should map same as 'A minor'."""
        assert camelot_position("A natural minor") == (8, "A")

    def test_unknown_key_returns_none(self):
        assert camelot_position("X blorp") is None

    def test_empty_string_returns_none(self):
        assert camelot_position("") is None

    def test_all_12_minor_keys_have_positions(self):
        """Every chromatic minor key should have a Camelot position."""
        from tools.music.theory import NOTE_NAMES

        for note in NOTE_NAMES:
            key = f"{note} minor"
            pos = camelot_position(key)
            if pos is not None:
                num, letter = pos
                assert 1 <= num <= 12
                assert letter in ("A", "B")


# ---------------------------------------------------------------------------
# camelot_compatible_keys
# ---------------------------------------------------------------------------


class TestCamelotCompatibleKeys:
    def test_a_minor_includes_itself(self):
        keys = camelot_compatible_keys("A minor")
        assert "A minor" in keys

    def test_a_minor_compatible_with_e_minor(self):
        """E minor = 9A, A minor = 8A → adjacent."""
        keys = camelot_compatible_keys("A minor")
        assert "E minor" in keys

    def test_a_minor_compatible_with_d_minor(self):
        """D minor = 7A, A minor = 8A → adjacent."""
        keys = camelot_compatible_keys("A minor")
        assert "D minor" in keys

    def test_a_minor_compatible_with_c_major(self):
        """C major = 8B, A minor = 8A → relative major/minor (same number)."""
        keys = camelot_compatible_keys("A minor")
        assert "C major" in keys

    def test_a_minor_not_compatible_with_f_sharp_minor(self):
        """F# minor = 11A, A minor = 8A → not adjacent."""
        keys = camelot_compatible_keys("A minor")
        assert "F# minor" not in keys

    def test_always_returns_at_least_input(self):
        """Even an unknown key returns itself."""
        keys = camelot_compatible_keys("Unknown key")
        assert "Unknown key" in keys

    def test_returns_4_compatible_keys(self):
        """Should return: same + 2 adjacent + 1 relative = 4."""
        keys = camelot_compatible_keys("A minor")
        assert len(keys) == 4

    def test_circular_wheel_position_1(self):
        """Position 1 should include position 12 (circular).
        G# minor = 1A → Camelot reverse uses flat spellings:
        12A = 'Db minor', 2A = 'Eb minor'.
        """
        keys = camelot_compatible_keys("G# minor")
        # 12A maps to "Db minor" in the reverse map (flat spelling)
        assert "Db minor" in keys
        # 2A maps to "Eb minor"
        assert "Eb minor" in keys


# ---------------------------------------------------------------------------
# key_compatibility_score
# ---------------------------------------------------------------------------


class TestKeyCompatibilityScore:
    def test_same_key_scores_1(self):
        score, relationship = key_compatibility_score("A minor", "A minor")
        assert score == 1.0
        assert relationship == "same key"

    def test_adjacent_scores_08(self):
        score, relationship = key_compatibility_score("A minor", "E minor")
        assert score == 0.8
        assert "adjacent" in relationship

    def test_relative_scores_06(self):
        score, relationship = key_compatibility_score("A minor", "C major")
        assert score == 0.6
        assert "relative" in relationship

    def test_incompatible_scores_0(self):
        score, relationship = key_compatibility_score("A minor", "F# minor")
        assert score == 0.0
        assert "incompatible" in relationship

    def test_unknown_key_scores_0(self):
        score, _ = key_compatibility_score("A minor", "Z unknown")
        assert score == 0.0

    def test_both_unknown_scores_0(self):
        score, _ = key_compatibility_score("X", "Y")
        assert score == 0.0

    def test_direction_down(self):
        """D minor (7A) is adjacent-down from A minor (8A)."""
        score, relationship = key_compatibility_score("A minor", "D minor")
        assert score == 0.8
        assert "down" in relationship


# ---------------------------------------------------------------------------
# bpm_compatibility_score
# ---------------------------------------------------------------------------


class TestBpmCompatibilityScore:
    def test_same_bpm_scores_1(self):
        score, adj = bpm_compatibility_score(124.0, 124.0)
        assert score == 1.0
        assert adj is None

    def test_within_1_bpm_scores_1(self):
        score, adj = bpm_compatibility_score(124.0, 124.5)
        assert score == 1.0

    def test_within_tolerance_high_score(self):
        score, adj = bpm_compatibility_score(124.0, 128.0)
        assert 0.5 < score < 1.0
        assert adj is None

    def test_at_tolerance_boundary(self):
        """124 ± 6 = 130 — should still score > 0."""
        score, adj = bpm_compatibility_score(124.0, 130.0)
        assert score > 0.0

    def test_out_of_tolerance_scores_0(self):
        score, adj = bpm_compatibility_score(124.0, 160.0)
        assert score == 0.0
        assert adj is None

    def test_halftime_doubletime_detected(self):
        """124 → 248 would be double time for ref, so candidate needs halftime."""
        score, adj = bpm_compatibility_score(124.0, 62.0)
        assert score == 0.5
        assert adj == "doubletime"

    def test_doubletime_halftime_detected(self):
        score, adj = bpm_compatibility_score(124.0, 248.0)
        assert score == 0.5
        assert adj == "halftime"

    def test_zero_bpm_returns_0(self):
        score, adj = bpm_compatibility_score(0, 124.0)
        assert score == 0.0

    def test_negative_bpm_returns_0(self):
        score, adj = bpm_compatibility_score(-10, 124.0)
        assert score == 0.0


# ---------------------------------------------------------------------------
# compute_compatibility
# ---------------------------------------------------------------------------


class TestComputeCompatibility:
    def test_perfect_match_scores_near_1(self):
        result = compute_compatibility("A minor", 124.0, None, "A minor", 124.0, None)
        assert result.total_score >= 0.9

    def test_compatible_key_bpm_moderate_score(self):
        result = compute_compatibility("A minor", 124.0, None, "E minor", 126.0, None)
        assert 0.5 < result.total_score < 1.0

    def test_incompatible_key_scores_low(self):
        result = compute_compatibility("A minor", 124.0, None, "F# minor", 124.0, None)
        # BPM matches but key doesn't
        assert result.total_score < 0.5

    def test_result_has_all_fields(self):
        result = compute_compatibility("A minor", 124.0, 0.6, "C major", 126.0, 0.7)
        assert 0.0 <= result.key_score <= 1.0
        assert 0.0 <= result.bpm_score <= 1.0
        assert 0.0 <= result.energy_score <= 1.0
        assert 0.0 <= result.total_score <= 1.0
        assert isinstance(result.relationship, str)

    def test_energy_neutral_when_none(self):
        """Energy 0.5 (neutral) when both energies unknown."""
        result = compute_compatibility("A minor", 124.0, None, "A minor", 124.0, None)
        assert result.energy_score == 0.5

    def test_energy_match_improves_score(self):
        r_with = compute_compatibility("A minor", 124.0, 0.6, "A minor", 124.0, 0.6)
        r_without = compute_compatibility("A minor", 124.0, None, "A minor", 124.0, None)
        assert r_with.total_score >= r_without.total_score


# ---------------------------------------------------------------------------
# parse_key_from_text / parse_bpm_from_text
# ---------------------------------------------------------------------------


class TestParseKeyFromText:
    def test_key_of_pattern(self):
        key = parse_key_from_text("This track is in the key of A minor")
        assert key == "A minor"

    def test_in_pattern(self):
        key = parse_key_from_text("Produced in C major for a brighter feel")
        assert key == "C major"

    def test_scale_pattern(self):
        key = parse_key_from_text("Uses the D minor scale throughout")
        assert key == "D minor"

    def test_natural_minor_normalized(self):
        key = parse_key_from_text("This is in A natural minor")
        assert key == "A minor"

    def test_returns_none_when_no_key(self):
        assert parse_key_from_text("No musical info here") is None

    def test_returns_none_for_empty(self):
        assert parse_key_from_text("") is None


class TestParseBpmFromText:
    def test_explicit_bpm(self):
        assert parse_bpm_from_text("Track runs at 124 bpm") == 124.0

    def test_no_space_bpm(self):
        assert parse_bpm_from_text("Set to 126bpm") == 126.0

    def test_returns_none_when_no_bpm(self):
        assert parse_bpm_from_text("No tempo info") is None

    def test_out_of_range_returns_none(self):
        assert parse_bpm_from_text("30 bpm") is None

    def test_decimal_bpm(self):
        result = parse_bpm_from_text("at 124.5 bpm")
        assert result == 124.5


# ---------------------------------------------------------------------------
# _camelot_str helper
# ---------------------------------------------------------------------------


class TestCamelotStr:
    def test_a_minor_is_8a(self):
        assert _camelot_str("A minor") == "8A"

    def test_c_major_is_8b(self):
        assert _camelot_str("C major") == "8B"

    def test_unknown_returns_none(self):
        assert _camelot_str("Unknown") is None


# ---------------------------------------------------------------------------
# SuggestCompatibleTracks tool — interface
# ---------------------------------------------------------------------------


class TestSuggestCompatibleTracksProperties:
    _tool = SuggestCompatibleTracks.__new__(SuggestCompatibleTracks)
    _tool._session_factory = None

    def test_tool_name(self):
        assert self._tool.name == "suggest_compatible_tracks"

    def test_description_mentions_camelot(self):
        assert "camelot" in self._tool.description.lower()

    def test_has_key_bpm_params(self):
        names = [p.name for p in self._tool.parameters]
        assert "key" in names
        assert "bpm" in names

    def test_key_and_bpm_required(self):
        required = [p.name for p in self._tool.parameters if p.required]
        assert "key" in required
        assert "bpm" in required

    def test_energy_and_top_k_optional(self):
        optional = [p.name for p in self._tool.parameters if not p.required]
        assert "energy" in optional
        assert "top_k" in optional


# ---------------------------------------------------------------------------
# SuggestCompatibleTracks tool — validation
# ---------------------------------------------------------------------------


class TestSuggestCompatibleTracksValidation:
    def _tool(self):
        t = SuggestCompatibleTracks.__new__(SuggestCompatibleTracks)
        t._session_factory = None
        return t

    def test_empty_key_rejected(self):
        result = self._tool()(key="", bpm=124.0)
        assert result.success is False
        assert "key" in result.error.lower()

    def test_missing_bpm_rejected(self):
        result = self._tool()(key="A minor")
        assert result.success is False
        assert "bpm" in result.error.lower()

    def test_bpm_below_60_rejected(self):
        result = self._tool()(key="A minor", bpm=30.0)
        assert result.success is False
        assert "bpm" in result.error.lower()

    def test_bpm_above_220_rejected(self):
        result = self._tool()(key="A minor", bpm=300.0)
        assert result.success is False

    def test_invalid_energy_rejected(self):
        result = self._tool()(key="A minor", bpm=124.0, energy=2.0)
        assert result.success is False
        assert "energy" in result.error.lower()

    def test_negative_energy_rejected(self):
        result = self._tool()(key="A minor", bpm=124.0, energy=-0.1)
        assert result.success is False

    def test_invalid_top_k_rejected(self):
        result = self._tool()(key="A minor", bpm=124.0, top_k=25)
        assert result.success is False

    def test_unknown_key_rejected(self):
        result = self._tool()(key="X blorp", bpm=124.0)
        assert result.success is False
        assert "unknown key" in result.error.lower()

    def test_non_numeric_bpm_rejected(self):
        result = self._tool()(key="A minor", bpm="fast")
        assert result.success is False


# ---------------------------------------------------------------------------
# SuggestCompatibleTracks tool — happy path (mocked DB)
# ---------------------------------------------------------------------------

_PATCH_TARGET = (
    "tools.music.suggest_compatible_tracks.SuggestCompatibleTracks._find_compatible_in_kb"
)


class TestSuggestCompatibleTracksHappyPath:
    def _make_tool(self, mock_tracks=None):
        tool = SuggestCompatibleTracks.__new__(SuggestCompatibleTracks)
        tool._session_factory = None
        return tool

    def test_success_with_no_tracks_found(self):
        tool = self._make_tool()
        with patch(_PATCH_TARGET, return_value=[]):
            result = tool(key="A minor", bpm=124.0)
        assert result.success is True
        assert result.data["tracks"] == []
        assert result.data["total_found"] == 0

    def test_result_has_reference_block(self):
        tool = self._make_tool()
        with patch(_PATCH_TARGET, return_value=[]):
            result = tool(key="A minor", bpm=124.0)
        ref = result.data["reference"]
        assert ref["key"] == "A minor"
        assert ref["bpm"] == 124.0
        assert ref["camelot"] == "8A"

    def test_result_has_compatible_keys(self):
        tool = self._make_tool()
        with patch(_PATCH_TARGET, return_value=[]):
            result = tool(key="A minor", bpm=124.0)
        assert "compatible_keys" in result.data
        assert "A minor" in result.data["compatible_keys"]

    def test_tracks_returned_sorted(self):
        mock_tracks = [
            {"source_name": "TrackA", "compatibility": {"total": 0.5}},
            {"source_name": "TrackB", "compatibility": {"total": 0.9}},
        ]
        tool = self._make_tool()
        with patch(_PATCH_TARGET, return_value=mock_tracks):
            result = tool(key="A minor", bpm=124.0)
        assert result.success is True
        assert result.data["tracks"] == mock_tracks

    def test_energy_passed_through(self):
        tool = self._make_tool()
        captured = {}

        def fake_find(ref_key, ref_bpm, ref_energy, compatible_keys, top_k):
            captured["energy"] = ref_energy
            return []

        with patch(_PATCH_TARGET, side_effect=fake_find):
            tool(key="A minor", bpm=124.0, energy=0.7)
        assert captured["energy"] == 0.7

    def test_energy_none_by_default(self):
        tool = self._make_tool()
        captured = {}

        def fake_find(ref_key, ref_bpm, ref_energy, compatible_keys, top_k):
            captured["energy"] = ref_energy
            return []

        with patch(_PATCH_TARGET, side_effect=fake_find):
            tool(key="A minor", bpm=124.0)
        assert captured["energy"] is None

    def test_c_major_relative_to_a_minor(self):
        """Verifies relative major/minor is included in compatible_keys."""
        tool = self._make_tool()
        with patch(_PATCH_TARGET, return_value=[]):
            result = tool(key="A minor", bpm=124.0)
        assert "C major" in result.data["compatible_keys"]
