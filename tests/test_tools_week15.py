"""
tests/test_tools_week15.py — Tests for Week 15 MCP tools.

Covers:
    - AnalyzeSample tool (analyze_sample.py)
    - ExtractMelody tool (extract_melody.py)
    - GenerateFullArrangement tool (generate_full_arrangement.py)
    - AbletonInsertNotes tool (ableton_insert_notes.py)
    - AbletonInsertDrums tool (ableton_insert_drums.py)

All tests mock I/O (audio files, OSC sockets). No filesystem access,
no network, no audio stack required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sample_analysis_mock() -> MagicMock:
    """Build a MagicMock that looks like SampleAnalysis."""
    key_mock = MagicMock()
    key_mock.root = "A"
    key_mock.mode = "minor"
    key_mock.confidence = 0.87
    key_mock.label = "A minor"

    spectral_mock = MagicMock()
    spectral_mock.chroma = tuple([0.1] * 12)
    spectral_mock.rms = 0.08
    spectral_mock.tempo = 128.0
    spectral_mock.onsets_sec = (0.5, 1.0, 1.5)

    analysis = MagicMock()
    analysis.bpm = 128.0
    analysis.key = key_mock
    analysis.energy = 7
    analysis.duration_sec = 5.0
    analysis.sample_rate = 44100
    analysis.notes = ()
    analysis.spectral = spectral_mock
    return analysis


def _make_note_mock(
    pitch_midi: int = 69, onset_sec: float = 0.0, duration_sec: float = 0.5
) -> MagicMock:
    n = MagicMock()
    n.pitch_midi = pitch_midi
    n.pitch_name = "A4"
    n.onset_sec = onset_sec
    n.duration_sec = duration_sec
    n.velocity = 80
    return n


def _make_composition_mock() -> MagicMock:
    """Build a MagicMock that looks like FullComposition."""
    from core.music_theory.bass import generate_bassline
    from core.music_theory.drums import generate_pattern
    from core.music_theory.harmony import suggest_progression

    voicing = suggest_progression("A", genre="organic house", bars=4)
    bass = generate_bassline(voicing.chords, genre="organic house", seed=0)
    drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)

    comp = MagicMock()
    comp.bpm = 128.0
    comp.genre = "organic house"
    comp.bars = 4
    comp.voicing = voicing
    comp.bass_notes = bass
    comp.drum_pattern = drums
    comp.melody_notes = ()
    comp.midi_paths = {}
    comp.processing_time_ms = 42.5

    analysis = _make_sample_analysis_mock()
    comp.analysis = analysis

    return comp


# ---------------------------------------------------------------------------
# TestAnalyzeSampleTool
# ---------------------------------------------------------------------------


class TestAnalyzeSampleTool:
    """Tests for tools/music/analyze_sample.py — AnalyzeSample tool."""

    def test_tool_name(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        assert tool.name == "analyze_sample"

    def test_tool_has_description(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        assert len(tool.description) > 20

    def test_empty_file_path_returns_error(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        result = tool(file_path="")
        assert not result.success
        assert "file_path" in (result.error or "")

    def test_successful_analysis_returns_bpm(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        analysis = _make_sample_analysis_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.return_value = analysis
            result = tool(file_path="/tmp/test.mp3")
        assert result.success
        assert result.data["bpm"] == 128.0

    def test_successful_analysis_returns_key(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        analysis = _make_sample_analysis_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.return_value = analysis
            result = tool(file_path="/tmp/test.mp3")
        assert result.success
        assert result.data["key"]["root"] == "A"
        assert result.data["key"]["mode"] == "minor"
        assert result.data["key"]["label"] == "A minor"

    def test_successful_analysis_returns_energy(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        analysis = _make_sample_analysis_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.return_value = analysis
            result = tool(file_path="/tmp/test.mp3")
        assert result.success
        assert result.data["energy"] == 7

    def test_file_not_found_returns_error(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.side_effect = FileNotFoundError("not found")
            result = tool(file_path="/nonexistent/file.mp3")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_unsupported_format_returns_error(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.side_effect = ValueError("Unsupported")
            result = tool(file_path="/tmp/test.xyz")
        assert not result.success

    def test_metadata_contains_file(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        analysis = _make_sample_analysis_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.analyze_sample.return_value = analysis
            result = tool(file_path="/tmp/test.mp3")
        assert result.metadata is not None
        assert result.metadata["file"] == "/tmp/test.mp3"

    def test_include_melody_true_passed_to_engine(self) -> None:
        from tools.music.analyze_sample import AnalyzeSample

        tool = AnalyzeSample()
        analysis = _make_sample_analysis_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.analyze_sample.return_value = analysis
            tool(file_path="/tmp/test.mp3", include_melody=True)
        mock_engine.analyze_sample.assert_called_once_with(
            "/tmp/test.mp3", duration=30.0, include_melody=True
        )


# ---------------------------------------------------------------------------
# TestExtractMelodyTool
# ---------------------------------------------------------------------------


class TestExtractMelodyTool:
    """Tests for tools/music/extract_melody.py — ExtractMelody tool."""

    def test_tool_name(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        assert tool.name == "extract_melody"

    def test_empty_file_path_returns_error(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        result = tool(file_path="")
        assert not result.success

    def test_successful_extraction_returns_notes(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        notes = [_make_note_mock(69, 0.0, 0.5), _make_note_mock(72, 0.5, 0.5)]
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.extract_melody.return_value = notes
            result = tool(file_path="/tmp/test.mp3")
        assert result.success
        assert result.data["note_count"] == 2
        assert len(result.data["notes"]) == 2

    def test_notes_have_required_fields(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        notes = [_make_note_mock(69, 0.0, 0.5)]
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.extract_melody.return_value = notes
            result = tool(file_path="/tmp/test.mp3")
        note = result.data["notes"][0]
        assert "pitch_midi" in note
        assert "pitch_name" in note
        assert "onset_sec" in note
        assert "duration_sec" in note
        assert "velocity" in note

    def test_empty_melody_returns_zero_count(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.extract_melody.return_value = []
            result = tool(file_path="/tmp/test.mp3")
        assert result.success
        assert result.data["note_count"] == 0
        assert result.data["notes"] == []

    def test_file_not_found_returns_error(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.extract_melody.side_effect = FileNotFoundError("missing")
            result = tool(file_path="/missing/file.mp3")
        assert not result.success

    def test_metadata_has_algorithm(self) -> None:
        from tools.music.extract_melody import ExtractMelody

        tool = ExtractMelody()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.extract_melody.return_value = []
            result = tool(file_path="/tmp/test.mp3")
        assert result.metadata is not None
        assert result.metadata["algorithm"] == "pYIN"


# ---------------------------------------------------------------------------
# TestGenerateFullArrangementTool
# ---------------------------------------------------------------------------


class TestGenerateFullArrangementTool:
    """Tests for tools/music/generate_full_arrangement.py."""

    def test_tool_name(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        assert tool.name == "generate_full_arrangement"

    def test_empty_file_path_returns_error(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        result = tool(file_path="")
        assert not result.success

    def test_invalid_genre_returns_error(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        result = tool(file_path="/tmp/test.mp3", genre="not_a_genre")
        assert not result.success
        assert "genre" in (result.error or "")

    def test_invalid_bars_returns_error(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        result = tool(file_path="/tmp/test.mp3", bars=0)
        assert not result.success

    def test_successful_pipeline_returns_data(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        comp = _make_composition_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_pipeline.return_value = comp
            result = tool(file_path="/tmp/test.mp3", genre="organic house")
        assert result.success
        assert result.data["bpm"] == 128.0
        assert result.data["genre"] == "organic house"

    def test_successful_pipeline_returns_chords(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        comp = _make_composition_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_pipeline.return_value = comp
            result = tool(file_path="/tmp/test.mp3")
        assert len(result.data["chords"]) > 0
        chord = result.data["chords"][0]
        assert "name" in chord
        assert "roman" in chord

    def test_file_not_found_returns_error(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_pipeline.side_effect = FileNotFoundError("gone")
            result = tool(file_path="/gone/file.mp3")
        assert not result.success

    def test_invalid_bpm_returns_error(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        result = tool(file_path="/tmp/test.mp3", bpm=5.0)
        assert not result.success
        assert "bpm" in (result.error or "")

    def test_metadata_has_genre_and_key(self) -> None:
        from tools.music.generate_full_arrangement import GenerateFullArrangement

        tool = GenerateFullArrangement()
        comp = _make_composition_mock()
        with patch("ingestion.audio_engine.AudioAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_pipeline.return_value = comp
            result = tool(file_path="/tmp/test.mp3")
        assert result.metadata is not None
        assert "genre" in result.metadata
        assert "key" in result.metadata


# ---------------------------------------------------------------------------
# TestAbletonInsertNotesTool
# ---------------------------------------------------------------------------


class TestAbletonInsertNotesTool:
    """Tests for tools/music/ableton_insert_notes.py — AbletonInsertNotes."""

    def test_tool_name(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        assert tool.name == "ableton_insert_notes"

    def test_empty_notes_returns_error(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        result = tool(notes=[])
        assert not result.success

    def test_invalid_pitch_midi_returns_error(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 200, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80}]
        result = tool(notes=notes)
        assert not result.success
        assert "pitch_midi" in (result.error or "")

    def test_zero_duration_returns_error(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.0, "velocity": 80}]
        result = tool(notes=notes)
        assert not result.success
        assert "duration_sec" in (result.error or "")

    def test_missing_pythonosc_returns_error(self) -> None:
        """ImportError when python-osc not installed → error with install hint."""
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80}]
        with patch.dict("sys.modules", {"pythonosc": None, "pythonosc.udp_client": None}):
            result = tool(notes=notes)
        assert not result.success
        assert "python-osc" in (result.error or "")

    def test_osc_connection_error_returns_error(self) -> None:
        """OSError (Ableton not running) → user-friendly error."""
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80}]
        mock_client = MagicMock()
        mock_client.send_message.side_effect = OSError("connection refused")
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            result = tool(notes=notes)
        assert not result.success
        assert "11002" in (result.error or "")

    def test_successful_send_returns_note_count(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [
            {"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80},
            {"pitch_midi": 72, "onset_sec": 0.5, "duration_sec": 0.5, "velocity": 75},
        ]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            result = tool(notes=notes, bpm=128.0)
        assert result.success
        assert result.data["note_count"] == 2
        assert result.data["bpm"] == 128.0

    def test_osc_messages_sent_for_each_note(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [
            {"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80},
            {"pitch_midi": 72, "onset_sec": 0.5, "duration_sec": 0.5, "velocity": 75},
        ]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            tool(notes=notes, bpm=120.0)
        # clear + 2 note messages + commit = 4 calls
        assert mock_client.send_message.call_count == 4

    def test_velocity_override_applied(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 10}]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            tool(notes=notes, bpm=120.0, velocity=100)
        # Find the /note/add call and check velocity
        call_args = mock_client.send_message.call_args_list
        note_calls = [c for c in call_args if c[0][0] == "/note/add"]
        assert len(note_calls) == 1
        assert note_calls[0][0][1][3] == 100  # velocity = 100 (override)

    def test_zero_bpm_returns_error(self) -> None:
        from tools.music.ableton_insert_notes import AbletonInsertNotes

        tool = AbletonInsertNotes()
        notes = [{"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80}]
        result = tool(notes=notes, bpm=0.0)
        assert not result.success


# ---------------------------------------------------------------------------
# TestAbletonInsertDrumsTool
# ---------------------------------------------------------------------------


class TestAbletonInsertDrumsTool:
    """Tests for tools/music/ableton_insert_drums.py — AbletonInsertDrums."""

    def test_tool_name(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        assert tool.name == "ableton_insert_drums"

    def test_empty_hits_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        result = tool(hits=[])
        assert not result.success

    def test_invalid_instrument_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "cowbell", "step": 0, "velocity": 100, "bar": 0}]
        result = tool(hits=hits)
        assert not result.success
        assert "instrument" in (result.error or "").lower()

    def test_step_out_of_range_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "kick", "step": 16, "velocity": 100, "bar": 0}]
        result = tool(hits=hits)
        assert not result.success

    def test_negative_bar_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "kick", "step": 0, "velocity": 100, "bar": -1}]
        result = tool(hits=hits)
        assert not result.success

    def test_missing_pythonosc_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "kick", "step": 0, "velocity": 100, "bar": 0}]
        with patch.dict("sys.modules", {"pythonosc": None, "pythonosc.udp_client": None}):
            result = tool(hits=hits)
        assert not result.success
        assert "python-osc" in (result.error or "")

    def test_osc_connection_error_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "kick", "step": 0, "velocity": 100, "bar": 0}]
        mock_client = MagicMock()
        mock_client.send_message.side_effect = OSError("refused")
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            result = tool(hits=hits)
        assert not result.success
        assert "11003" in (result.error or "")

    def test_successful_send_returns_hit_count(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [
            {"instrument": "kick", "step": 0, "velocity": 100, "bar": 0},
            {"instrument": "snare", "step": 4, "velocity": 90, "bar": 0},
            {"instrument": "hihat_c", "step": 2, "velocity": 70, "bar": 0},
        ]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            result = tool(hits=hits, bpm=128.0, bars=1)
        assert result.success
        assert result.data["hit_count"] == 3
        assert result.data["bpm"] == 128.0

    def test_osc_messages_sent_for_each_hit(self) -> None:
        """clear + N hit messages + commit = N+2 total send_message calls."""
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [
            {"instrument": "kick", "step": 0, "velocity": 100, "bar": 0},
            {"instrument": "snare", "step": 4, "velocity": 90, "bar": 0},
        ]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            tool(hits=hits, bpm=120.0, bars=1)
        # clear (1) + 2 hits + commit (1) = 4 total calls
        assert mock_client.send_message.call_count == 4

    def test_gm_note_mapping_kick_is_36(self) -> None:
        """Kick drum must map to GM note 36."""
        from tools.music.ableton_insert_drums import _GM_DRUM_NOTES

        assert _GM_DRUM_NOTES["kick"] == 36

    def test_gm_note_mapping_snare_is_38(self) -> None:
        from tools.music.ableton_insert_drums import _GM_DRUM_NOTES

        assert _GM_DRUM_NOTES["snare"] == 38

    def test_gm_note_mapping_hihat_c_is_42(self) -> None:
        from tools.music.ableton_insert_drums import _GM_DRUM_NOTES

        assert _GM_DRUM_NOTES["hihat_c"] == 42

    def test_all_valid_instruments_accepted(self) -> None:
        """All 5 instrument names should be accepted without error."""
        from tools.music.ableton_insert_drums import _GM_DRUM_NOTES, AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [
            {"instrument": instr, "step": 0, "velocity": 80, "bar": 0} for instr in _GM_DRUM_NOTES
        ]
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SimpleUDPClient = MagicMock(return_value=mock_client)
        with patch.dict(
            "sys.modules", {"pythonosc": MagicMock(), "pythonosc.udp_client": mock_module}
        ):
            result = tool(hits=hits, bpm=120.0)
        assert result.success
        assert result.data["hit_count"] == len(_GM_DRUM_NOTES)

    def test_invalid_bars_returns_error(self) -> None:
        from tools.music.ableton_insert_drums import AbletonInsertDrums

        tool = AbletonInsertDrums()
        hits = [{"instrument": "kick", "step": 0, "velocity": 100, "bar": 0}]
        result = tool(hits=hits, bpm=120.0, bars=0)
        assert not result.success
