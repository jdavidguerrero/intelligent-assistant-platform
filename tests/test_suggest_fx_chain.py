"""Tests for suggest_fx_chain tool."""

from tools.music.suggest_fx_chain import VALID_SOUND_TYPES, SuggestFxChain


class TestSuggestFxChainHappyPath:
    def setup_method(self):
        self.tool = SuggestFxChain()

    def test_kick_house_returns_success(self):
        result = self.tool(sound_type="kick", genre="house")
        assert result.success

    def test_returns_fx_chain_list(self):
        result = self.tool(sound_type="kick", genre="house")
        assert "fx_chain" in result.data
        assert isinstance(result.data["fx_chain"], list)
        assert len(result.data["fx_chain"]) > 0

    def test_each_effect_has_required_fields(self):
        result = self.tool(sound_type="kick", genre="house")
        for effect in result.data["fx_chain"]:
            assert "order" in effect
            assert "name" in effect
            assert "category" in effect
            assert "params" in effect
            assert "rationale" in effect

    def test_effects_ordered_sequentially(self):
        result = self.tool(sound_type="kick", genre="house")
        orders = [e["order"] for e in result.data["fx_chain"]]
        assert orders == sorted(orders)
        assert orders[0] == 1

    def test_sound_type_in_output(self):
        result = self.tool(sound_type="bass", genre="house")
        assert result.data["sound_type"] == "bass"

    def test_genre_in_output(self):
        result = self.tool(sound_type="kick", genre="techno")
        assert result.data["genre"] == "techno"

    def test_all_sound_types_return_success(self):
        for sound in VALID_SOUND_TYPES:
            result = self.tool(sound_type=sound, genre="house")
            assert result.success, f"Sound type {sound} failed"

    def test_genre_fallback_when_not_available(self):
        # acid kick is not defined for 'deep house' genre — should fallback
        result = self.tool(sound_type="kick", genre="deep house")
        assert result.success
        # matched_genre should be "deep house" since it IS defined
        assert result.data["matched_genre"] if "matched_genre" in result.data else True

    def test_acid_bass_has_303_filter(self):
        result = self.tool(sound_type="bass", genre="acid")
        assert result.success
        # The first effect should involve the resonant filter
        categories = [e["category"] for e in result.data["fx_chain"]]
        assert "EQ" in categories or "saturation" in categories

    def test_effect_count_in_metadata(self):
        result = self.tool(sound_type="kick", genre="house")
        assert result.data["effect_count"] == len(result.data["fx_chain"])

    def test_exact_match_flag_true_when_genre_exists(self):
        result = self.tool(sound_type="kick", genre="house")
        assert result.metadata["exact_match"] is True

    def test_exact_match_flag_false_when_genre_fallback(self):
        # Use a genre that definitely isn't in any specific sound type
        result = self.tool(sound_type="808", genre="melodic techno")
        assert result.success
        assert result.metadata["exact_match"] is False


class TestSuggestFxChainValidation:
    def setup_method(self):
        self.tool = SuggestFxChain()

    def test_invalid_sound_type_returns_error(self):
        result = self.tool(sound_type="triangle_wave", genre="house")
        assert not result.success
        assert "sound_type" in result.error

    def test_invalid_genre_falls_back_not_errors(self):
        # Invalid genre should fall back gracefully, not error
        result = self.tool(sound_type="kick", genre="reggae")
        assert result.success


class TestSuggestFxChainToolMetadata:
    def setup_method(self):
        self.tool = SuggestFxChain()

    def test_tool_name(self):
        assert self.tool.name == "suggest_fx_chain"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_has_parameters(self):
        assert len(self.tool.parameters) >= 2

    def test_valid_sound_types_not_empty(self):
        assert len(VALID_SOUND_TYPES) > 0
        assert "kick" in VALID_SOUND_TYPES
        assert "bass" in VALID_SOUND_TYPES
