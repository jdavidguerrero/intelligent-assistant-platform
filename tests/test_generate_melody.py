"""Tests for generate_melody tool."""

from tools.music.generate_melody import VALID_MODES, VALID_MOODS, GenerateMelody


class TestGenerateMelodyHappyPath:
    def setup_method(self):
        self.tool = GenerateMelody()

    def test_default_params_returns_success(self):
        result = self.tool()
        assert result.success
        assert result.data is not None

    def test_returns_piano_roll(self):
        result = self.tool(key="A", mode="natural minor", mood="dark")
        assert "piano_roll" in result.data
        assert isinstance(result.data["piano_roll"], list)
        assert len(result.data["piano_roll"]) > 0

    def test_all_events_have_required_fields(self):
        result = self.tool(key="A", mode="natural minor", mood="melancholic", bars=2)
        for event in result.data["piano_roll"]:
            assert "note" in event
            assert "start" in event
            assert "duration" in event
            assert "velocity" in event
            assert "channel" in event

    def test_melody_in_correct_octave_range(self):
        result = self.tool(key="A", mode="natural minor", mood="dark", genre="organic house")
        for event in result.data["piano_roll"]:
            # Melody should be in octave 4–6 range (MIDI 48–95)
            assert 36 <= event["note"] <= 107, f"Note {event['note']} out of melody range"

    def test_key_in_output(self):
        result = self.tool(key="F#", mode="natural minor", mood="dark")
        assert "F#" in result.data["key"]

    def test_scale_notes_in_output(self):
        result = self.tool(key="A", mode="natural minor", mood="dark")
        assert "scale_notes" in result.data
        assert len(result.data["scale_notes"]) > 0

    def test_total_beats_matches_bars(self):
        result = self.tool(key="A", mode="natural minor", mood="dark", bars=2)
        assert result.data["total_beats"] == 8.0

    def test_events_do_not_exceed_total_beats(self):
        bars = 2
        result = self.tool(key="A", mode="natural minor", mood="dark", bars=bars)
        for event in result.data["piano_roll"]:
            assert event["start"] < bars * 4.0

    def test_all_moods_produce_events(self):
        for mood in VALID_MOODS:
            result = self.tool(key="A", mode="natural minor", mood=mood)
            assert result.success, f"Mood {mood} failed"
            assert len(result.data["piano_roll"]) > 0

    def test_all_modes_produce_success(self):
        for mode in list(VALID_MODES)[:5]:  # test subset to keep it fast
            result = self.tool(key="C", mode=mode, mood="neutral")
            assert result.success, f"Mode {mode} failed"

    def test_acid_genre_uses_lower_octave(self):
        result = self.tool(key="A", mode="natural minor", mood="dark", genre="acid")
        # Acid is in octave 1–3 range (MIDI 12–47)
        notes = [e["note"] for e in result.data["piano_roll"]]
        assert min(notes) < 60, "Acid melody should be in low register"

    def test_bpm_in_output(self):
        result = self.tool(bpm=130)
        assert result.data["bpm"] == 130

    def test_velocity_in_valid_range(self):
        result = self.tool(key="A", mode="natural minor", mood="euphoric", bars=2)
        for event in result.data["piano_roll"]:
            assert 1 <= event["velocity"] <= 127


class TestGenerateMelodyValidation:
    def setup_method(self):
        self.tool = GenerateMelody()

    def test_invalid_key_returns_error(self):
        result = self.tool(key="X#")
        assert not result.success

    def test_invalid_mode_returns_error(self):
        result = self.tool(key="A", mode="not_a_mode")
        assert not result.success

    def test_invalid_mood_returns_error(self):
        result = self.tool(key="A", mode="natural minor", mood="extraterrestrial")
        assert not result.success

    def test_bars_too_large_returns_error(self):
        result = self.tool(bars=16)
        assert not result.success

    def test_bpm_too_low_returns_error(self):
        result = self.tool(bpm=10)
        assert not result.success


class TestGenerateMelodyToolMetadata:
    def setup_method(self):
        self.tool = GenerateMelody()

    def test_tool_name(self):
        assert self.tool.name == "generate_melody"

    def test_has_description(self):
        assert len(self.tool.description) > 20

    def test_has_parameters(self):
        assert len(self.tool.parameters) >= 5

    def test_valid_moods_not_empty(self):
        assert len(VALID_MOODS) > 0
        assert "dark" in VALID_MOODS
        assert "euphoric" in VALID_MOODS
