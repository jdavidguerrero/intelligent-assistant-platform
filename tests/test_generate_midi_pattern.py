"""
Tests for generate_midi_pattern tool.

No real MIDI files are written in most tests (output_path omitted).
midiutil-dependent path is tested with a skip guard.
All tests are deterministic and isolated.
"""

import pytest

from tools.music.generate_midi_pattern import (
    GenerateMidiPattern,
    _is_midiutil_available,
    _make_chord_events,
    _make_note_event,
)

# ---------------------------------------------------------------------------
# Tool properties
# ---------------------------------------------------------------------------


class TestGenerateMidiPatternProperties:
    """Test tool interface contract."""

    def test_tool_name(self):
        """Tool name must be exactly 'generate_midi_pattern'."""
        tool = GenerateMidiPattern()
        assert tool.name == "generate_midi_pattern"

    def test_description_mentions_midi_and_piano_roll(self):
        """Description should mention MIDI and piano roll."""
        tool = GenerateMidiPattern()
        desc = tool.description.lower()
        assert "midi" in desc
        assert "piano roll" in desc or "piano_roll" in desc

    def test_has_required_parameters(self):
        """Tool should expose chord_names, bpm, bars_per_chord, style, output_path."""
        tool = GenerateMidiPattern()
        names = [p.name for p in tool.parameters]
        assert "chord_names" in names
        assert "bpm" in names
        assert "bars_per_chord" in names
        assert "style" in names
        assert "output_path" in names

    def test_chord_names_and_bpm_are_required(self):
        """chord_names and bpm must be required parameters."""
        tool = GenerateMidiPattern()
        required = {p.name for p in tool.parameters if p.required}
        assert "chord_names" in required
        assert "bpm" in required

    def test_optional_parameters_have_defaults(self):
        """bars_per_chord, style, output_path should be optional."""
        tool = GenerateMidiPattern()
        optional = {p.name for p in tool.parameters if not p.required}
        assert "bars_per_chord" in optional
        assert "style" in optional
        assert "output_path" in optional


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestGenerateMidiPatternValidation:
    """Test domain-level input validation."""

    _tool = GenerateMidiPattern()

    def test_empty_chord_names_rejected(self):
        """Empty chord_names list should return error."""
        result = self._tool(chord_names=[], bpm=120)
        assert result.success is False
        assert "chord_names" in result.error.lower()

    def test_bpm_too_low_rejected(self):
        """BPM below 60 should return error."""
        result = self._tool(chord_names=["Am"], bpm=59)
        assert result.success is False
        assert "bpm" in result.error.lower()

    def test_bpm_too_high_rejected(self):
        """BPM above 220 should return error."""
        result = self._tool(chord_names=["Am"], bpm=221)
        assert result.success is False

    def test_bars_per_chord_too_low_rejected(self):
        """bars_per_chord=0 should be rejected."""
        result = self._tool(chord_names=["Am"], bpm=120, bars_per_chord=0)
        assert result.success is False
        assert "bars_per_chord" in result.error.lower()

    def test_bars_per_chord_too_high_rejected(self):
        """bars_per_chord > 8 should be rejected."""
        result = self._tool(chord_names=["Am"], bpm=120, bars_per_chord=9)
        assert result.success is False

    def test_invalid_chord_name_rejected(self):
        """Unrecognized chord name should return error."""
        result = self._tool(chord_names=["NotAChord"], bpm=120)
        assert result.success is False

    def test_empty_string_chord_rejected(self):
        """Empty string in chord_names should return error."""
        result = self._tool(chord_names=["Am", ""], bpm=120)
        assert result.success is False

    def test_invalid_chord_style_rejected(self):
        """Unknown chord_style should return error."""
        result = self._tool(chord_names=["Am"], bpm=120, chord_style="jazz_comp")
        assert result.success is False
        assert "chord_style" in result.error.lower()

    def test_missing_bpm_returns_error(self):
        """Missing required bpm should fail base class validation."""
        result = self._tool(chord_names=["Am"])
        assert result.success is False

    def test_wrong_type_bpm_returns_error(self):
        """String passed as bpm should fail type validation."""
        result = self._tool(chord_names=["Am"], bpm="fast")
        assert result.success is False


# ---------------------------------------------------------------------------
# Happy path — piano roll output
# ---------------------------------------------------------------------------


class TestGenerateMidiPatternHappyPath:
    """Test successful MIDI generation (piano roll output)."""

    _tool = GenerateMidiPattern()

    def test_basic_am_progression_returns_success(self):
        """Simple 4-chord progression should return success."""
        result = self._tool(
            chord_names=["Am", "F", "C", "G"],
            bpm=124,
            bars_per_chord=2,
            style="organic house",
        )
        assert result.success is True

    def test_data_has_required_fields(self):
        """Result data must include piano_roll, total_beats, duration_seconds."""
        result = self._tool(chord_names=["Am", "F"], bpm=120)
        assert result.success is True
        for key in ("piano_roll", "total_beats", "duration_seconds", "chord_count", "bpm"):
            assert key in result.data, f"Missing key: {key}"

    def test_piano_roll_is_list(self):
        """piano_roll must be a list."""
        result = self._tool(chord_names=["Am"], bpm=120)
        assert isinstance(result.data["piano_roll"], list)

    def test_piano_roll_not_empty(self):
        """piano_roll should have events for at least one chord."""
        result = self._tool(chord_names=["Am"], bpm=120)
        assert len(result.data["piano_roll"]) > 0

    def test_each_event_has_required_fields(self):
        """Each piano roll event must have note, start, duration, velocity, channel, track."""
        result = self._tool(chord_names=["Am"], bpm=120)
        for event in result.data["piano_roll"]:
            assert "note" in event
            assert "start" in event
            assert "duration" in event
            assert "velocity" in event
            assert "channel" in event
            assert "track" in event

    def test_note_values_in_midi_range(self):
        """All note values should be in MIDI range [0, 127]."""
        result = self._tool(chord_names=["Am", "F", "C", "G"], bpm=120)
        for event in result.data["piano_roll"]:
            assert 0 <= event["note"] <= 127

    def test_velocity_in_valid_range(self):
        """All velocity values should be in [0, 127]."""
        result = self._tool(chord_names=["Am", "F"], bpm=120)
        for event in result.data["piano_roll"]:
            assert 0 <= event["velocity"] <= 127

    def test_start_times_non_negative(self):
        """All event start times should be >= 0."""
        result = self._tool(chord_names=["Am", "F", "C", "G"], bpm=120)
        for event in result.data["piano_roll"]:
            assert event["start"] >= 0

    def test_chord_count_matches_input(self):
        """chord_count should match number of input chords."""
        result = self._tool(chord_names=["Am", "F", "C", "G"], bpm=120)
        assert result.data["chord_count"] == 4

    def test_total_beats_calculation(self):
        """total_beats = chord_count * bars_per_chord * 4."""
        result = self._tool(chord_names=["Am", "F"], bpm=120, bars_per_chord=2)
        # 2 chords × 2 bars × 4 beats = 16 beats
        assert result.data["total_beats"] == 16.0

    def test_duration_seconds_positive(self):
        """duration_seconds must be positive."""
        result = self._tool(chord_names=["Am"], bpm=120)
        assert result.data["duration_seconds"] > 0

    def test_two_tracks_generated(self):
        """Events should come from both 'chords' and 'bass' tracks."""
        result = self._tool(chord_names=["Am", "F"], bpm=120)
        tracks = {e["track"] for e in result.data["piano_roll"]}
        assert "chords" in tracks
        assert "bass" in tracks

    def test_metadata_has_tracks(self):
        """metadata should include tracks list."""
        result = self._tool(chord_names=["Am"], bpm=120)
        assert "tracks" in result.metadata
        assert "chords" in result.metadata["tracks"]
        assert "bass" in result.metadata["tracks"]

    def test_metadata_midi_available_is_bool(self):
        """metadata.midi_available should be a bool."""
        result = self._tool(chord_names=["Am"], bpm=120)
        assert isinstance(result.metadata["midi_available"], bool)

    def test_seventh_chord_accepted(self):
        """7th chords like 'Amaj7', 'Dm7' should parse and generate events."""
        result = self._tool(chord_names=["Amaj7", "Dm7", "Gmaj7"], bpm=120)
        assert result.success is True

    def test_extended_chord_accepted(self):
        """Extended chords like 'Dm9' should parse correctly."""
        result = self._tool(chord_names=["Dm9", "Gmaj9"], bpm=120)
        assert result.success is True

    def test_flat_chord_accepted(self):
        """Flat-root chords like 'Bbm7' should be accepted."""
        result = self._tool(chord_names=["Bbm7", "Eb"], bpm=120)
        assert result.success is True

    def test_chord_style_block(self):
        """block chord_style should return events all starting at same beat."""
        result = self._tool(chord_names=["Am"], bpm=120, chord_style="block")
        assert result.success is True
        chord_events = [e for e in result.data["piano_roll"] if e["track"] == "chords"]
        # All chord notes should start at beat 0
        starts = {e["start"] for e in chord_events}
        assert 0.0 in starts

    def test_chord_style_arpeggiated(self):
        """arpeggiated style should stagger note starts."""
        result = self._tool(chord_names=["Am"], bpm=120, chord_style="arpeggiated")
        assert result.success is True
        chord_events = [e for e in result.data["piano_roll"] if e["track"] == "chords"]
        starts = sorted(e["start"] for e in chord_events)
        # Notes should have different start times
        assert len(set(starts)) > 1

    def test_chord_style_shell(self):
        """shell style should produce fewer chord notes than full voicing."""
        result_block = self._tool(chord_names=["Amaj7"], bpm=120, chord_style="block")
        result_shell = self._tool(chord_names=["Amaj7"], bpm=120, chord_style="shell")
        block_events = [e for e in result_block.data["piano_roll"] if e["track"] == "chords"]
        shell_events = [e for e in result_shell.data["piano_roll"] if e["track"] == "chords"]
        # Shell should have 2 notes (root + top), block has more
        assert len(shell_events) <= len(block_events)

    def test_all_valid_styles_work(self):
        """All registered style values should return success."""
        from tools.music.generate_midi_pattern import _BASS_PATTERNS

        for style in _BASS_PATTERNS:
            if style == "default":
                continue
            result = self._tool(chord_names=["Am", "F"], bpm=120, style=style)
            assert result.success is True, f"style={style!r} failed"

    def test_bpm_echoed_in_result(self):
        """data['bpm'] should echo the input BPM."""
        result = self._tool(chord_names=["Am"], bpm=130)
        assert result.data["bpm"] == 130

    def test_note_name_format(self):
        """note_name field should be non-empty string like 'A4', 'C3'."""
        result = self._tool(chord_names=["Am"], bpm=120)
        for event in result.data["piano_roll"]:
            assert isinstance(event["note_name"], str)
            assert len(event["note_name"]) >= 2  # at least 1 char note + 1 digit octave


# ---------------------------------------------------------------------------
# MIDI file writing
# ---------------------------------------------------------------------------


class TestMidiFileWriting:
    """Test optional MIDI file writing."""

    _tool = GenerateMidiPattern()

    @pytest.mark.skipif(
        not _is_midiutil_available(),
        reason="midiutil not installed — skipping MIDI file tests",
    )
    def test_writes_midi_file(self, tmp_path):
        """When midiutil is available, should write a valid .mid file."""
        output = tmp_path / "test_output.mid"
        result = self._tool(
            chord_names=["Am", "F", "C", "G"],
            bpm=124,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()
        assert output.stat().st_size > 0

    @pytest.mark.skipif(
        not _is_midiutil_available(),
        reason="midiutil not installed",
    )
    def test_midi_file_path_in_metadata(self, tmp_path):
        """midi_file key should appear in metadata when file is written."""
        output = tmp_path / "chords.mid"
        result = self._tool(
            chord_names=["Am", "F"],
            bpm=120,
            output_path=str(output),
        )
        assert result.success is True
        assert "midi_file" in result.metadata

    @pytest.mark.skipif(
        not _is_midiutil_available(),
        reason="midiutil not installed",
    )
    def test_creates_parent_directory(self, tmp_path):
        """Should create nested parent directories for output path."""
        output = tmp_path / "nested" / "deep" / "output.mid"
        result = self._tool(
            chord_names=["Am"],
            bpm=120,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()

    def test_no_output_path_still_succeeds(self):
        """Without output_path, should succeed with piano roll only."""
        result = self._tool(chord_names=["Am", "F"], bpm=120)
        assert result.success is True
        assert "piano_roll" in result.data
        assert "midi_file" not in result.metadata


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


class TestMakeNoteEvent:
    """Test _make_note_event pure function."""

    def test_returns_dict_with_all_keys(self):
        event = _make_note_event(69, 0.0, 1.0, 80, 0, "chords")
        for key in ("track", "note", "note_name", "start", "duration", "velocity", "channel"):
            assert key in event

    def test_correct_note_name_for_a4(self):
        """MIDI 69 = A4."""
        event = _make_note_event(69, 0.0, 1.0, 80, 0, "chords")
        assert event["note_name"] == "A4"

    def test_correct_note_name_for_c4(self):
        """MIDI 60 = C4."""
        event = _make_note_event(60, 0.0, 1.0, 80, 0, "chords")
        assert event["note_name"] == "C4"

    def test_velocity_clamped_to_127(self):
        """Velocity above 127 should be clamped."""
        event = _make_note_event(60, 0.0, 1.0, 200, 0, "chords")
        assert event["velocity"] == 127

    def test_velocity_clamped_to_0(self):
        """Negative velocity should be clamped to 0."""
        event = _make_note_event(60, 0.0, 1.0, -10, 0, "chords")
        assert event["velocity"] == 0

    def test_start_rounded_to_4_decimals(self):
        """start should be rounded to 4 decimal places."""
        event = _make_note_event(60, 1.23456789, 1.0, 80, 0, "chords")
        assert event["start"] == round(1.23456789, 4)

    def test_track_field_preserved(self):
        event = _make_note_event(60, 0.0, 1.0, 80, 1, "bass")
        assert event["track"] == "bass"


class TestMakeChordEvents:
    """Test _make_chord_events pure function."""

    def test_block_all_same_start(self):
        """block style: all notes start at same beat."""
        events = _make_chord_events([60, 64, 67], 0.0, 4.0, "block", 80, 0)
        starts = {e["start"] for e in events}
        assert len(starts) == 1
        assert 0.0 in starts

    def test_arp_staggered_starts(self):
        """arp style: notes have different start times."""
        events = _make_chord_events([60, 64, 67], 0.0, 4.0, "arp", 80, 0)
        starts = [e["start"] for e in events]
        assert len(set(starts)) == 3

    def test_shell_returns_two_notes(self):
        """shell style: only 2 notes (root + top) for 4-note chord."""
        events = _make_chord_events([60, 64, 67, 71], 0.0, 4.0, "shell", 80, 0)
        assert len(events) == 2

    def test_shell_single_note_chord(self):
        """shell style with single note should return 1 event."""
        events = _make_chord_events([60], 0.0, 4.0, "shell", 80, 0)
        assert len(events) == 1

    def test_block_count_matches_notes(self):
        """block style: event count = note count."""
        events = _make_chord_events([60, 64, 67], 0.0, 4.0, "block", 80, 0)
        assert len(events) == 3

    def test_start_offset_applied(self):
        """start_beat offset should be applied to all events."""
        events = _make_chord_events([60], 8.0, 4.0, "block", 80, 0)
        assert events[0]["start"] == 8.0
