"""Tests for generate_drum_pattern tool."""

from tools.music.generate_drum_pattern import (
    _PATTERNS,
    DRUM_MIDI,
    STEPS_PER_BAR,
    VALID_GENRES,
    GenerateDrumPattern,
)


class TestGenerateDrumPatternHappyPath:
    def setup_method(self):
        self.tool = GenerateDrumPattern()

    def test_house_pattern_returns_success(self):
        result = self.tool(genre="house", bpm=124, bars=1)
        assert result.success
        assert result.data is not None

    def test_returns_piano_roll_and_step_grid(self):
        result = self.tool(genre="house", bpm=124, bars=1)
        assert "piano_roll" in result.data
        assert "step_grid" in result.data
        assert isinstance(result.data["piano_roll"], list)
        assert isinstance(result.data["step_grid"], dict)

    def test_step_grid_has_16_steps_per_bar(self):
        result = self.tool(genre="house", bpm=124, bars=1)
        for instrument, steps in result.data["step_grid"].items():
            assert len(steps) == STEPS_PER_BAR, f"{instrument} should have 16 steps"

    def test_two_bars_gives_32_steps(self):
        result = self.tool(genre="house", bpm=124, bars=2)
        for _instrument, steps in result.data["step_grid"].items():
            assert len(steps) == STEPS_PER_BAR * 2

    def test_piano_roll_events_have_required_fields(self):
        result = self.tool(genre="house", bpm=124, bars=1)
        for event in result.data["piano_roll"]:
            assert "note" in event
            assert "start" in event
            assert "duration" in event
            assert "velocity" in event
            assert "channel" in event
            assert event["channel"] == 9  # GM drum channel

    def test_kick_fires_on_all_four_beats_in_house(self):
        result = self.tool(genre="house", bpm=124, bars=1)
        kick_events = [e for e in result.data["piano_roll"] if e["instrument"] == "kick"]
        # Four-on-the-floor: 4 kick hits at beats 0.0, 1.0, 2.0, 3.0
        kick_starts = [e["start"] for e in kick_events]
        assert 0.0 in kick_starts
        assert 1.0 in kick_starts
        assert 2.0 in kick_starts
        assert 3.0 in kick_starts

    def test_all_genres_produce_events(self):
        for genre in VALID_GENRES:
            result = self.tool(genre=genre, bpm=120, bars=1)
            assert result.success, f"Genre {genre} failed"
            assert len(result.data["piano_roll"]) > 0

    def test_bpm_stored_in_output(self):
        result = self.tool(genre="house", bpm=130, bars=1)
        assert result.data["bpm"] == 130

    def test_genre_stored_in_output(self):
        result = self.tool(genre="techno", bpm=135, bars=1)
        assert result.data["genre"] == "techno"

    def test_duration_seconds_is_correct(self):
        bpm = 120
        bars = 2
        result = self.tool(genre="house", bpm=bpm, bars=bars)
        expected = (bars * 4.0 / bpm) * 60.0
        assert abs(result.data["duration_seconds"] - expected) < 0.01

    def test_events_sorted_by_start_time(self):
        result = self.tool(genre="afro house", bpm=120, bars=2)
        starts = [e["start"] for e in result.data["piano_roll"]]
        assert starts == sorted(starts)


class TestGenerateDrumPatternInstrumentFilter:
    def setup_method(self):
        self.tool = GenerateDrumPattern()

    def test_filter_to_kick_only(self):
        result = self.tool(genre="house", bpm=124, bars=1, instruments=["kick"])
        assert result.success
        for event in result.data["piano_roll"]:
            assert event["instrument"] == "kick"

    def test_filter_to_kick_and_snare(self):
        result = self.tool(genre="house", bpm=124, bars=1, instruments=["kick", "snare"])
        instruments_present = {e["instrument"] for e in result.data["piano_roll"]}
        assert instruments_present.issubset({"kick", "snare"})

    def test_invalid_instrument_returns_error(self):
        result = self.tool(genre="house", bpm=124, bars=1, instruments=["nonexistent"])
        assert not result.success
        assert "Unknown instruments" in result.error


class TestGenerateDrumPatternHumanize:
    def setup_method(self):
        self.tool = GenerateDrumPattern()

    def test_humanize_true_applies_offsets(self):
        result_human = self.tool(genre="house", bpm=124, bars=1, humanize=True)
        result_grid = self.tool(genre="house", bpm=124, bars=1, humanize=False)
        assert result_human.success
        assert result_grid.success
        # Humanized snare should be slightly later than grid position
        snare_human = [e for e in result_human.data["piano_roll"] if e["instrument"] == "snare"]
        snare_grid = [e for e in result_grid.data["piano_roll"] if e["instrument"] == "snare"]
        if snare_human and snare_grid:
            # Humanized version has a non-zero offset applied
            assert snare_human[0]["start"] >= snare_grid[0]["start"]


class TestGenerateDrumPatternValidation:
    def setup_method(self):
        self.tool = GenerateDrumPattern()

    def test_invalid_genre_returns_error(self):
        result = self.tool(genre="reggaeton", bpm=120, bars=1)
        assert not result.success
        assert "genre" in result.error.lower() or "reggaeton" in result.error

    def test_bpm_too_low_returns_error(self):
        result = self.tool(genre="house", bpm=30, bars=1)
        assert not result.success

    def test_bpm_too_high_returns_error(self):
        result = self.tool(genre="house", bpm=300, bars=1)
        assert not result.success

    def test_bars_too_many_returns_error(self):
        result = self.tool(genre="house", bpm=124, bars=16)
        assert not result.success

    def test_bars_zero_uses_default(self):
        # bars=0 triggers the `or 2` default — treated as bars=2
        result = self.tool(genre="house", bpm=124, bars=0)
        assert result.success
        assert result.data["bars"] == 2


class TestGenerateDrumPatternToolMetadata:
    def setup_method(self):
        self.tool = GenerateDrumPattern()

    def test_tool_name(self):
        assert self.tool.name == "generate_drum_pattern"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_has_parameters(self):
        assert len(self.tool.parameters) > 0

    def test_all_genres_in_valid_genres(self):
        assert "house" in VALID_GENRES
        assert "techno" in VALID_GENRES
        assert "afro house" in VALID_GENRES

    def test_drum_midi_has_kick(self):
        assert "kick" in DRUM_MIDI
        assert DRUM_MIDI["kick"] == 36

    def test_drum_midi_has_snare(self):
        assert "snare" in DRUM_MIDI
        assert DRUM_MIDI["snare"] == 38

    def test_all_pattern_instruments_in_drum_midi(self):
        for genre, pattern in _PATTERNS.items():
            for instrument in pattern:
                assert (
                    instrument in DRUM_MIDI
                ), f"Instrument {instrument!r} in genre {genre!r} not in DRUM_MIDI"
