"""
Tests for core/genre_detector.py

Covers:
- Genre detection for all supported genres
- No detection for generic queries
- Tie-breaking (longer keyword wins)
- has_recipe flag
- recipe_file field
- GenreDetectionResult dataclass immutability
"""

from core.genre_detector import detect_genre


class TestDetectGenre:
    """Tests for detect_genre() function."""

    def test_organic_house_detected(self) -> None:
        result = detect_genre("how do I make organic house music?")
        assert result.genre == "organic house"

    def test_progressive_house_detected(self) -> None:
        result = detect_genre("what's the arrangement for progressive house?")
        assert result.genre == "progressive house"

    def test_deep_house_detected(self) -> None:
        result = detect_genre("how do I mix a deep house track?")
        assert result.genre == "deep house"

    def test_melodic_techno_detected(self) -> None:
        result = detect_genre("tips for melodic techno production")
        assert result.genre == "melodic techno"

    def test_techno_detected(self) -> None:
        result = detect_genre("how do I make hard techno?")
        assert result.genre == "techno"

    def test_acid_detected_via_303(self) -> None:
        result = detect_genre("how do I program a 303 bassline?")
        assert result.genre == "acid"

    def test_no_genre_returns_none(self) -> None:
        result = detect_genre("how do I compress a kick drum?")
        assert result.genre is None

    def test_generic_query_returns_none(self) -> None:
        result = detect_genre("what is reverb?")
        assert result.genre is None

    def test_empty_query_returns_none(self) -> None:
        result = detect_genre("")
        assert result.genre is None

    def test_query_lowercased_in_result(self) -> None:
        result = detect_genre("ORGANIC HOUSE bass design")
        assert result.query == "organic house bass design"

    def test_case_insensitive_detection(self) -> None:
        result = detect_genre("I love DEEP HOUSE music")
        assert result.genre == "deep house"

    def test_votes_dict_present(self) -> None:
        result = detect_genre("organic house bass")
        assert isinstance(result.votes, dict)
        assert "organic house" in result.votes

    def test_detected_genre_has_positive_votes(self) -> None:
        result = detect_genre("organic house track")
        assert result.genre is not None
        assert result.votes[result.genre] > 0

    def test_undetected_query_all_votes_zero(self) -> None:
        result = detect_genre("hello world")
        assert all(v == 0 for v in result.votes.values())


class TestGenreRecipeIntegration:
    """Tests for has_recipe and recipe_file fields."""

    def test_organic_house_has_recipe(self) -> None:
        result = detect_genre("organic house production tips")
        assert result.has_recipe
        assert result.recipe_file == "organic_house"

    def test_progressive_house_has_recipe(self) -> None:
        result = detect_genre("progressive house arrangement")
        assert result.has_recipe
        assert result.recipe_file == "progressive_house"

    def test_melodic_techno_has_recipe(self) -> None:
        result = detect_genre("melodic techno mixing guide")
        assert result.has_recipe
        assert result.recipe_file == "melodic_techno"

    def test_deep_house_has_recipe(self) -> None:
        result = detect_genre("deep house sound design")
        assert result.has_recipe
        assert result.recipe_file == "deep_house"

    def test_techno_no_recipe(self) -> None:
        # Techno has no recipe file yet
        result = detect_genre("techno production")
        assert result.genre == "techno"
        assert not result.has_recipe
        assert result.recipe_file is None

    def test_no_genre_no_recipe(self) -> None:
        result = detect_genre("how do I EQ a kick?")
        assert not result.has_recipe
        assert result.recipe_file is None


class TestGenreDetectionResultImmutability:
    """Tests for frozen dataclass behavior."""

    def test_result_is_frozen(self) -> None:
        result = detect_genre("organic house")
        import pytest

        with pytest.raises((AttributeError, TypeError)):
            result.genre = "deep house"  # type: ignore[misc]

    def test_votes_dict_type(self) -> None:
        result = detect_genre("deep house groove")
        assert isinstance(result.votes, dict)

    def test_has_recipe_is_bool(self) -> None:
        result = detect_genre("organic house")
        assert isinstance(result.has_recipe, bool)
