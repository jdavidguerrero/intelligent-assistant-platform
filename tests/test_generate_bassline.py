"""Tests for generate_bassline tool."""

from tools.music.generate_bassline import VALID_GENRES, GenerateBassline


class TestGenerateBasslineHappyPath:
    def setup_method(self):
        self.tool = GenerateBassline()

    def test_house_returns_success(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        assert result.success

    def test_all_genres_return_success(self):
        for genre in VALID_GENRES:
            result = self.tool(root="A", genre=genre, bpm=124, bars=1)
            assert result.success, f"Genre {genre} failed"

    def test_returns_piano_roll(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        assert "piano_roll" in result.data
        assert isinstance(result.data["piano_roll"], list)
        assert len(result.data["piano_roll"]) > 0

    def test_returns_step_grid(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        assert "step_grid" in result.data
        assert len(result.data["step_grid"]) == 16  # 16 steps per bar

    def test_two_bars_gives_32_steps(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=2)
        assert len(result.data["step_grid"]) == 32

    def test_events_have_required_fields(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        for event in result.data["piano_roll"]:
            assert "note" in event
            assert "start" in event
            assert "duration" in event
            assert "velocity" in event

    def test_bass_channel_is_1(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        for event in result.data["piano_roll"]:
            assert event["channel"] == 1

    def test_root_stored_in_output(self):
        result = self.tool(root="F#", genre="house", bpm=124, bars=1)
        assert result.data["root"] == "F#"

    def test_flat_root_normalized(self):
        result = self.tool(root="Bb", genre="house", bpm=124, bars=1)
        assert result.success
        assert result.data["root"] == "A#"  # normalized to sharp

    def test_acid_uses_lower_octave(self):
        result = self.tool(root="A", genre="acid", bpm=130, bars=1)
        assert result.data["octave"] <= 2

    def test_events_sorted_by_start(self):
        result = self.tool(root="A", genre="deep house", bpm=120, bars=2)
        starts = [e["start"] for e in result.data["piano_roll"]]
        assert starts == sorted(starts)

    def test_duration_seconds_correct(self):
        bpm = 124
        bars = 2
        result = self.tool(root="A", genre="house", bpm=bpm, bars=bars)
        expected = (bars * 4.0 / bpm) * 60.0
        assert abs(result.data["duration_seconds"] - expected) < 0.01

    def test_notes_in_valid_midi_range(self):
        result = self.tool(root="A", genre="house", bpm=124, bars=1)
        for event in result.data["piano_roll"]:
            assert 0 <= event["note"] <= 127


class TestGenerateBasslineValidation:
    def setup_method(self):
        self.tool = GenerateBassline()

    def test_invalid_root_returns_error(self):
        result = self.tool(root="X#")
        assert not result.success

    def test_invalid_genre_returns_error(self):
        result = self.tool(root="A", genre="bossa techno")
        assert not result.success

    def test_bpm_too_low_returns_error(self):
        result = self.tool(root="A", bpm=20)
        assert not result.success

    def test_bars_too_many_returns_error(self):
        result = self.tool(root="A", bars=16)
        assert not result.success


class TestGenerateBasslineToolMetadata:
    def setup_method(self):
        self.tool = GenerateBassline()

    def test_tool_name(self):
        assert self.tool.name == "generate_bassline"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_valid_genres_includes_acid(self):
        assert "acid" in VALID_GENRES

    def test_valid_genres_includes_deep_house(self):
        assert "deep house" in VALID_GENRES
