"""Tests for suggest_sample_selection tool."""

from tools.music.suggest_sample_selection import (
    VALID_SOUND_ROLES,
    SuggestSampleSelection,
)


class TestSuggestSampleSelectionHappyPath:
    def setup_method(self):
        self.tool = SuggestSampleSelection()

    def test_kick_house_returns_success(self):
        result = self.tool(sound_role="kick", genre="house")
        assert result.success

    def test_all_sound_roles_return_success(self):
        for role in VALID_SOUND_ROLES:
            result = self.tool(sound_role=role, genre="house")
            assert result.success, f"Sound role {role} failed"

    def test_returns_description(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "description" in result.data
        assert isinstance(result.data["description"], str)
        assert len(result.data["description"]) > 10

    def test_returns_hardware_sources(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "hardware_sources" in result.data
        assert isinstance(result.data["hardware_sources"], list)
        assert len(result.data["hardware_sources"]) > 0

    def test_returns_search_keywords(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "search_keywords" in result.data
        assert isinstance(result.data["search_keywords"], list)
        assert len(result.data["search_keywords"]) > 0

    def test_returns_treatment(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "treatment" in result.data

    def test_returns_layering_strategy(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "layering" in result.data

    def test_house_kick_mentions_tr909(self):
        result = self.tool(sound_role="kick", genre="house")
        sources = result.data["hardware_sources"]
        assert any("909" in str(s) or "TR" in str(s) for s in sources)

    def test_acid_bass_mentions_303(self):
        result = self.tool(sound_role="bass", genre="acid")
        assert result.success
        sources = result.data["hardware_sources"]
        assert any("303" in str(s) for s in sources)

    def test_genre_fallback_when_not_available(self):
        # hi_hat only has "house" defined — requesting "techno" should fallback
        result = self.tool(sound_role="hi_hat", genre="techno")
        assert result.success
        assert result.metadata["exact_match"] is False

    def test_exact_match_true_when_available(self):
        result = self.tool(sound_role="kick", genre="house")
        assert result.metadata["exact_match"] is True

    def test_hat_alias_works(self):
        result = self.tool(sound_role="hat", genre="house")
        assert result.success

    def test_hi_hat_alias_works(self):
        result = self.tool(sound_role="hi-hat", genre="house")
        assert result.success

    def test_sound_role_in_output(self):
        result = self.tool(sound_role="bass", genre="deep house")
        assert result.data["sound_role"] == "bass"

    def test_available_genres_in_metadata(self):
        result = self.tool(sound_role="kick", genre="house")
        assert "available_genres_for_role" in result.metadata
        assert isinstance(result.metadata["available_genres_for_role"], list)


class TestSuggestSampleSelectionValidation:
    def setup_method(self):
        self.tool = SuggestSampleSelection()

    def test_invalid_sound_role_returns_error(self):
        result = self.tool(sound_role="vibraphone", genre="house")
        assert not result.success
        assert "sound_role" in result.error.lower() or "vibraphone" in result.error

    def test_invalid_genre_falls_back_gracefully(self):
        result = self.tool(sound_role="kick", genre="kizomba")
        assert result.success  # should fall back, not error


class TestSuggestSampleSelectionToolMetadata:
    def setup_method(self):
        self.tool = SuggestSampleSelection()

    def test_tool_name(self):
        assert self.tool.name == "suggest_sample_selection"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_has_parameters(self):
        assert len(self.tool.parameters) >= 2

    def test_valid_sound_roles_not_empty(self):
        assert len(VALID_SOUND_ROLES) > 0
        assert "kick" in VALID_SOUND_ROLES
        assert "bass" in VALID_SOUND_ROLES
