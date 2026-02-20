"""Tests for generate_rhythm_pattern tool."""

from tools.music.generate_rhythm_pattern import (
    _RHYTHM_PATTERNS,
    PERCUSSION_MIDI,
    VALID_RHYTHMS,
    GenerateRhythmPattern,
)


class TestGenerateRhythmPatternHappyPath:
    def setup_method(self):
        self.tool = GenerateRhythmPattern()

    def test_afrobeat_returns_success(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=1)
        assert result.success
        assert result.data is not None

    def test_son_clave_3_2_returns_success(self):
        result = self.tool(rhythm="son_clave_3_2", bpm=120, bars=1)
        assert result.success

    def test_all_rhythms_return_success(self):
        for rhythm in VALID_RHYTHMS:
            result = self.tool(rhythm=rhythm, bpm=110, bars=1)
            assert result.success, f"Rhythm {rhythm} failed: {result.error}"

    def test_returns_piano_roll_and_step_grid(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=1)
        assert "piano_roll" in result.data
        assert "step_grid" in result.data

    def test_step_grid_has_16_steps_per_bar(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=1)
        for instrument, steps in result.data["step_grid"].items():
            assert len(steps) == 16, f"{instrument} should have 16 steps"

    def test_two_bars_gives_32_steps(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=2)
        for _instrument, steps in result.data["step_grid"].items():
            assert len(steps) == 32

    def test_piano_roll_events_are_on_drum_channel(self):
        result = self.tool(rhythm="bossanova", bpm=100, bars=1)
        for event in result.data["piano_roll"]:
            assert event["channel"] == 9

    def test_events_sorted_by_start(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=2)
        starts = [e["start"] for e in result.data["piano_roll"]]
        assert starts == sorted(starts)

    def test_clave_instrument_in_son_clave_pattern(self):
        result = self.tool(rhythm="son_clave_3_2", bpm=120, bars=1)
        instruments = {e["instrument"] for e in result.data["piano_roll"]}
        assert "clave" in instruments

    def test_duration_seconds_correct(self):
        bpm = 100
        bars = 2
        result = self.tool(rhythm="afrobeat", bpm=bpm, bars=bars)
        expected = (bars * 4.0 / bpm) * 60.0
        assert abs(result.data["duration_seconds"] - expected) < 0.01


class TestGenerateRhythmPatternInstrumentFilter:
    def setup_method(self):
        self.tool = GenerateRhythmPattern()

    def test_filter_single_instrument(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=1, instruments=["conga_low"])
        assert result.success
        instruments_present = {e["instrument"] for e in result.data["piano_roll"]}
        assert instruments_present == {"conga_low"}

    def test_filter_multiple_instruments(self):
        result = self.tool(rhythm="son_clave_3_2", bpm=120, bars=1, instruments=["clave", "shaker"])
        assert result.success
        instruments_present = {e["instrument"] for e in result.data["piano_roll"]}
        assert instruments_present.issubset({"clave", "shaker"})

    def test_invalid_instrument_returns_error(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=1, instruments=["triangle_harp"])
        assert not result.success


class TestGenerateRhythmPatternValidation:
    def setup_method(self):
        self.tool = GenerateRhythmPattern()

    def test_invalid_rhythm_returns_error(self):
        result = self.tool(rhythm="waltz")
        assert not result.success
        assert "waltz" in result.error

    def test_bpm_too_low_returns_error(self):
        result = self.tool(rhythm="afrobeat", bpm=30)
        assert not result.success

    def test_bpm_too_high_returns_error(self):
        result = self.tool(rhythm="afrobeat", bpm=200)
        assert not result.success

    def test_bars_too_many_returns_error(self):
        result = self.tool(rhythm="afrobeat", bpm=100, bars=16)
        assert not result.success


class TestGenerateRhythmPatternToolMetadata:
    def setup_method(self):
        self.tool = GenerateRhythmPattern()

    def test_tool_name(self):
        assert self.tool.name == "generate_rhythm_pattern"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_valid_rhythms_contains_expected(self):
        assert "afrobeat" in VALID_RHYTHMS
        assert "son_clave_3_2" in VALID_RHYTHMS
        assert "bossanova" in VALID_RHYTHMS
        assert "baiao" in VALID_RHYTHMS

    def test_all_pattern_instruments_in_percussion_midi(self):
        for rhythm, pattern in _RHYTHM_PATTERNS.items():
            for instrument in pattern:
                assert (
                    instrument in PERCUSSION_MIDI
                ), f"Instrument {instrument!r} in rhythm {rhythm!r} not in PERCUSSION_MIDI"
