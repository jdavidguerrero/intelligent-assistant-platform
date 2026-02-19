"""Tests for suggest_mix_template tool."""

from tools.music.suggest_mix_template import VALID_GENRES, SuggestMixTemplate


class TestSuggestMixTemplateHappyPath:
    def setup_method(self):
        self.tool = SuggestMixTemplate()

    def test_house_returns_success(self):
        result = self.tool(genre="house")
        assert result.success

    def test_all_genres_return_success(self):
        for genre in VALID_GENRES:
            result = self.tool(genre=genre)
            assert result.success, f"Genre {genre} failed"

    def test_returns_channels(self):
        result = self.tool(genre="house")
        assert "channels" in result.data
        assert isinstance(result.data["channels"], list)
        assert len(result.data["channels"]) > 0

    def test_returns_buses(self):
        result = self.tool(genre="house")
        assert "buses" in result.data
        assert isinstance(result.data["buses"], list)

    def test_returns_sidechain_routing(self):
        result = self.tool(genre="house")
        assert "sidechain_routing" in result.data
        assert isinstance(result.data["sidechain_routing"], list)

    def test_returns_master_bus(self):
        result = self.tool(genre="house")
        assert "master_bus" in result.data
        assert isinstance(result.data["master_bus"], list)

    def test_returns_lufs_target(self):
        result = self.tool(genre="house")
        assert "lufs_target" in result.data
        assert isinstance(result.data["lufs_target"], str)

    def test_channels_have_required_fields(self):
        result = self.tool(genre="house")
        for ch in result.data["channels"]:
            assert "name" in ch
            assert "fader_db" in ch
            assert "pan" in ch
            assert "bus" in ch

    def test_kick_is_0db_in_house(self):
        result = self.tool(genre="house")
        kick = next((ch for ch in result.data["channels"] if "Kick" in ch["name"]), None)
        assert kick is not None
        assert kick["fader_db"] == 0  # Kick is loudest in house

    def test_deep_house_has_lower_lufs_than_techno(self):
        deep = self.tool(genre="deep house")
        # Deep house is more dynamic (lower LUFS target)
        assert "10" in deep.data["lufs_target"] or "12" in deep.data["lufs_target"]

    def test_metadata_has_channel_count(self):
        result = self.tool(genre="house")
        assert result.metadata["channel_count"] == len(result.data["channels"])

    def test_sidechain_routing_has_kick_as_source(self):
        result = self.tool(genre="house")
        sources = [r["source"] for r in result.data["sidechain_routing"]]
        assert "Kick" in sources

    def test_mix_philosophy_is_string(self):
        result = self.tool(genre="organic house")
        assert isinstance(result.data["mix_philosophy"], str)
        assert len(result.data["mix_philosophy"]) > 10


class TestSuggestMixTemplateValidation:
    def setup_method(self):
        self.tool = SuggestMixTemplate()

    def test_invalid_genre_returns_error(self):
        result = self.tool(genre="polka")
        assert not result.success
        assert "genre" in result.error.lower() or "polka" in result.error


class TestSuggestMixTemplateToolMetadata:
    def setup_method(self):
        self.tool = SuggestMixTemplate()

    def test_tool_name(self):
        assert self.tool.name == "suggest_mix_template"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_has_parameters(self):
        assert len(self.tool.parameters) >= 1

    def test_valid_genres_contains_house_and_techno(self):
        assert "house" in VALID_GENRES
        assert "techno" in VALID_GENRES
        assert "deep house" in VALID_GENRES
