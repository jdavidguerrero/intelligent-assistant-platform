"""
Tests for tools/music/suggest_scale.py

Covers:
- Happy path: valid genre + mood → correct scale
- Root note override
- Camelot Wheel position lookup
- Compatible keys
- Chord degree guidance present
- Error cases: invalid genre, invalid mood, invalid root
"""

from tools.music.suggest_scale import SuggestScale

tool = SuggestScale()


class TestSuggestScaleHappyPath:
    """Core functionality tests."""

    def test_organic_house_dark_returns_natural_minor(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        assert result.data["mode"] == "natural minor"

    def test_organic_house_dreamy_returns_dorian(self) -> None:
        result = tool(genre="organic house", mood="dreamy")
        assert result.success
        assert result.data["mode"] == "dorian"

    def test_deep_house_melancholic_returns_dorian(self) -> None:
        result = tool(genre="deep house", mood="melancholic")
        assert result.success
        assert result.data["mode"] == "dorian"

    def test_melodic_techno_dark_returns_natural_minor(self) -> None:
        result = tool(genre="melodic techno", mood="dark")
        assert result.success
        assert result.data["mode"] == "natural minor"

    def test_progressive_house_euphoric_returns_major(self) -> None:
        result = tool(genre="progressive house", mood="euphoric")
        assert result.success
        assert result.data["mode"] == "major"

    def test_techno_dark_returns_phrygian(self) -> None:
        result = tool(genre="techno", mood="dark")
        assert result.success
        assert result.data["mode"] == "phrygian"

    def test_result_includes_scale_notes(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        notes = result.data["scale_notes"]
        assert isinstance(notes, list)
        assert len(notes) == 7  # natural minor has 7 notes

    def test_result_includes_key_name(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        assert "natural minor" in result.data["key"]

    def test_result_includes_rationale(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        assert isinstance(result.data["rationale"], str)
        assert len(result.data["rationale"]) > 10

    def test_result_includes_chord_degrees(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        assert isinstance(result.data["chord_degrees"], dict)
        assert len(result.data["chord_degrees"]) > 0

    def test_result_includes_genre_and_mood(self) -> None:
        result = tool(genre="deep house", mood="dreamy")
        assert result.success
        assert result.data["genre"] == "deep house"
        assert result.data["mood"] == "dreamy"

    def test_result_includes_formula(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        formula = result.data["formula"]
        assert isinstance(formula, list)
        assert formula[0] == 0  # always starts from root


class TestSuggestScaleRootOverride:
    """Tests for the optional root parameter."""

    def test_default_root_organic_house_is_a(self) -> None:
        result = tool(genre="organic house", mood="dark")
        assert result.success
        assert result.data["root"] == "A"

    def test_custom_root_f_sharp(self) -> None:
        result = tool(genre="melodic techno", mood="dark", root="F#")
        assert result.success
        assert result.data["root"] == "F#"
        assert "F#" in result.data["key"]

    def test_custom_root_d_minor(self) -> None:
        result = tool(genre="deep house", mood="melancholic", root="D")
        assert result.success
        assert result.data["root"] == "D"
        notes = result.data["scale_notes"]
        assert notes[0] == "D"  # root is first note

    def test_flat_root_normalized_to_sharp(self) -> None:
        result = tool(genre="organic house", mood="dark", root="Bb")
        assert result.success
        # Bb normalizes to A#
        assert result.data["root"] == "A#"

    def test_invalid_root_returns_error(self) -> None:
        result = tool(genre="organic house", mood="dark", root="Z")
        assert not result.success
        assert "root" in result.error.lower() or "note" in result.error.lower()


class TestSuggestScaleCamelot:
    """Tests for Camelot Wheel integration."""

    def test_a_natural_minor_camelot_is_8a(self) -> None:
        result = tool(genre="organic house", mood="dark", root="A")
        assert result.success
        assert result.data["camelot_position"] == "8A"

    def test_f_sharp_natural_minor_camelot_is_11a(self) -> None:
        result = tool(genre="melodic techno", mood="dark", root="F#")
        assert result.success
        assert result.data["camelot_position"] == "11A"

    def test_compatible_keys_are_adjacent_camelot(self) -> None:
        result = tool(genre="organic house", mood="dark", root="A")
        assert result.success
        compatible = result.data["compatible_camelot_keys"]
        assert isinstance(compatible, list)
        # 8A neighbors: 8B, 7A, 9A
        assert "8B" in compatible
        assert "7A" in compatible
        assert "9A" in compatible

    def test_unknown_camelot_position_handled_gracefully(self) -> None:
        # Phrygian has limited Camelot coverage — should not crash
        result = tool(genre="techno", mood="dark", root="A")
        assert result.success
        # Position may be "unknown" but result should still succeed
        assert "camelot_position" in result.data


class TestSuggestScaleErrorHandling:
    """Tests for invalid input handling."""

    def test_invalid_genre_returns_error(self) -> None:
        result = tool(genre="reggae", mood="dark")
        assert not result.success
        assert "genre" in result.error.lower()

    def test_invalid_mood_returns_error(self) -> None:
        result = tool(genre="organic house", mood="aggressive")
        assert not result.success
        assert "mood" in result.error.lower()

    def test_result_data_none_on_failure(self) -> None:
        result = tool(genre="invalid_genre", mood="dark")
        assert not result.success
        assert result.data is None or result.data == {}

    def test_all_genres_work_with_dark_mood(self) -> None:
        """Smoke test: every genre should return a valid result for 'dark'."""
        from tools.music.suggest_scale import VALID_GENRES

        for genre in VALID_GENRES:
            result = tool(genre=genre, mood="dark")
            assert result.success, f"Failed for genre={genre!r}: {result.error}"


class TestSuggestScaleToolMetadata:
    """Tests for MusicalTool protocol compliance."""

    def test_name_is_suggest_scale(self) -> None:
        assert tool.name == "suggest_scale"

    def test_description_is_non_empty(self) -> None:
        assert len(tool.description) > 20

    def test_parameters_list_non_empty(self) -> None:
        assert len(tool.parameters) >= 2

    def test_genre_param_not_required(self) -> None:
        genre_param = next((p for p in tool.parameters if p.name == "genre"), None)
        assert genre_param is not None
        assert not genre_param.required

    def test_mood_param_not_required(self) -> None:
        mood_param = next((p for p in tool.parameters if p.name == "mood"), None)
        assert mood_param is not None
        assert not mood_param.required
