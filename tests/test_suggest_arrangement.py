"""Tests for suggest_arrangement tool."""

from tools.music.suggest_arrangement import VALID_GENRES, SuggestArrangement


class TestSuggestArrangementHappyPath:
    def setup_method(self):
        self.tool = SuggestArrangement()

    def test_house_returns_success(self):
        result = self.tool(genre="house")
        assert result.success

    def test_all_genres_return_success(self):
        for genre in VALID_GENRES:
            result = self.tool(genre=genre)
            assert result.success, f"Genre {genre} failed"

    def test_returns_sections(self):
        result = self.tool(genre="house")
        assert "sections" in result.data
        assert isinstance(result.data["sections"], list)
        assert len(result.data["sections"]) > 0

    def test_sections_have_required_fields(self):
        result = self.tool(genre="house")
        for section in result.data["sections"]:
            assert "section" in section
            assert "bars" in section
            assert "energy" in section
            assert "elements" in section
            assert "notes" in section

    def test_bars_are_tuple_of_two_ints(self):
        result = self.tool(genre="house")
        for section in result.data["sections"]:
            bars = section["bars"]
            assert isinstance(bars, tuple | list)
            assert len(bars) == 2
            assert bars[0] < bars[1]

    def test_sections_are_contiguous(self):
        result = self.tool(genre="house")
        sections = result.data["sections"]
        for i in range(len(sections) - 1):
            current_end = sections[i]["bars"][1]
            next_start = sections[i + 1]["bars"][0]
            assert (
                next_start == current_end + 1
            ), f"Gap between {sections[i]['section']} and {sections[i+1]['section']}"

    def test_energy_in_range_1_to_10(self):
        for genre in VALID_GENRES:
            result = self.tool(genre=genre)
            for section in result.data["sections"]:
                assert (
                    1 <= section["energy"] <= 10
                ), f"Energy {section['energy']} out of range in {section['section']}"

    def test_returns_energy_curve(self):
        result = self.tool(genre="house")
        assert "energy_curve" in result.data
        assert isinstance(result.data["energy_curve"], list)

    def test_returns_dj_mix_points(self):
        result = self.tool(genre="house")
        assert "dj_mix_points" in result.data
        assert len(result.data["dj_mix_points"]) > 0

    def test_intro_is_first_section(self):
        result = self.tool(genre="house")
        first = result.data["sections"][0]
        assert "Intro" in first["section"] or first["bars"][0] == 1

    def test_total_bars_matches_last_section(self):
        result = self.tool(genre="house")
        total_bars = result.data["total_bars"]
        last_section = result.data["sections"][-1]
        assert total_bars == last_section["bars"][1]

    def test_outro_has_dj_mix_out_note(self):
        result = self.tool(genre="house")
        outro = result.data["sections"][-1]
        assert outro["dj_note"] is not None
        assert "MIX OUT" in outro["dj_note"].upper()

    def test_elements_are_booleans(self):
        result = self.tool(genre="house")
        for section in result.data["sections"]:
            for element, active in section["elements"].items():
                assert isinstance(
                    active, bool
                ), f"Element {element} in {section['section']} is not bool"

    def test_techno_has_long_peak_section(self):
        result = self.tool(genre="techno")
        peak_sections = [s for s in result.data["sections"] if "Peak" in s["section"]]
        assert len(peak_sections) > 0
        peak = peak_sections[0]
        bars_range = peak["bars"][1] - peak["bars"][0]
        assert bars_range >= 32  # Techno peak is long

    def test_organic_house_intro_has_no_kick(self):
        result = self.tool(genre="organic house")
        intro = result.data["sections"][0]
        assert intro["elements"]["kick"] is False


class TestSuggestArrangementValidation:
    def setup_method(self):
        self.tool = SuggestArrangement()

    def test_invalid_genre_returns_error(self):
        result = self.tool(genre="cumbia house")
        assert not result.success
        assert "genre" in result.error.lower() or "cumbia" in result.error


class TestSuggestArrangementToolMetadata:
    def setup_method(self):
        self.tool = SuggestArrangement()

    def test_tool_name(self):
        assert self.tool.name == "suggest_arrangement"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_valid_genres_contains_expected(self):
        assert "house" in VALID_GENRES
        assert "techno" in VALID_GENRES
        assert "organic house" in VALID_GENRES
