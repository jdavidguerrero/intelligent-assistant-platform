"""
Tests for analyze_track tool.
"""

from tools.music.analyze_track import AnalyzeTrack


class TestAnalyzeTrack:
    """Test analyze_track tool."""

    def test_tool_properties(self):
        """Tool should have correct name and description."""
        tool = AnalyzeTrack()

        assert tool.name == "analyze_track"
        assert "BPM" in tool.description
        assert "key" in tool.description
        assert len(tool.parameters) == 1
        assert tool.parameters[0].name == "file_path"

    def test_extract_bpm_from_filename(self):
        """Should extract BPM from various filename patterns."""
        tool = AnalyzeTrack()

        test_cases = [
            ("track_128bpm.mp3", 128),
            ("128 bpm track.mp3", 128),
            ("song-125-aminor.mp3", 125),
            ("140_hardstyle.wav", 140),
            ("track.mp3", "unknown"),  # No BPM
            ("10bpm.mp3", "unknown"),  # BPM too low (< 20)
            ("500bpm.mp3", "unknown"),  # BPM too high (> 300)
        ]

        for filename, expected_bpm in test_cases:
            result = tool(file_path=filename)
            assert result.success is True
            assert result.data["bpm"] == expected_bpm, f"Failed for {filename}"

    def test_extract_key_from_filename(self):
        """Should extract musical key from filename."""
        tool = AnalyzeTrack()

        test_cases = [
            ("track_Aminor.mp3", "A minor"),
            ("song_C#major.mp3", "C# major"),
            ("Dbm_track.mp3", "Db minor"),
            ("F#maj_song.wav", "F# major"),
            ("track_Gmaj.mp3", "G major"),
            ("track.mp3", "unknown"),  # No key
        ]

        for filename, expected_key in test_cases:
            result = tool(file_path=filename)
            assert result.success is True
            assert result.data["key"] == expected_key, f"Failed for {filename}"

    def test_extract_energy_from_filename(self):
        """Should extract energy level from filename."""
        tool = AnalyzeTrack()

        test_cases = [
            ("track_energy8.mp3", 8),
            ("high-energy-banger.mp3", 8),
            ("medium-energy-track.mp3", 5),
            ("low-energy-ambient.mp3", 3),
            ("track.mp3", "unknown"),  # No energy
        ]

        for filename, expected_energy in test_cases:
            result = tool(file_path=filename)
            assert result.success is True
            assert result.data["energy"] == expected_energy, f"Failed for {filename}"

    def test_full_metadata_extraction(self):
        """Should extract all metadata when available."""
        tool = AnalyzeTrack()

        result = tool(file_path="progressive_house_128bpm_Aminor_energy7.mp3")

        assert result.success is True
        assert result.data["bpm"] == 128
        assert result.data["key"] == "A minor"
        assert result.data["energy"] == 7
        assert result.data["confidence"] == "high"  # All 3 fields found

    def test_partial_metadata(self):
        """Should handle partial metadata gracefully."""
        tool = AnalyzeTrack()

        result = tool(file_path="track_128bpm.mp3")  # Only BPM

        assert result.success is True
        assert result.data["bpm"] == 128
        assert result.data["key"] == "unknown"
        assert result.data["energy"] == "unknown"
        assert result.data["confidence"] == "low"  # Only 1 field found

    def test_no_metadata(self):
        """Should handle tracks with no metadata."""
        tool = AnalyzeTrack()

        result = tool(file_path="track.mp3")

        assert result.success is True
        assert result.data["bpm"] == "unknown"
        assert result.data["key"] == "unknown"
        assert result.data["energy"] == "unknown"
        assert result.data["confidence"] == "none"

    def test_confidence_levels(self):
        """Should calculate correct confidence levels."""
        tool = AnalyzeTrack()

        # High confidence (all 3 fields)
        result = tool(file_path="track_128bpm_Aminor_energy8.mp3")
        assert result.data["confidence"] == "high"

        # Medium confidence (2 fields)
        result = tool(file_path="track_128bpm_Aminor.mp3")
        assert result.data["confidence"] == "medium"

        # Low confidence (1 field)
        result = tool(file_path="track_128bpm.mp3")
        assert result.data["confidence"] == "low"

        # No confidence (0 fields)
        result = tool(file_path="track.mp3")
        assert result.data["confidence"] == "none"

    def test_missing_file_path(self):
        """Should fail validation when file_path is missing."""
        tool = AnalyzeTrack()

        result = tool()  # No file_path provided

        assert result.success is False
        assert "Required parameter 'file_path' is missing" in result.error

    def test_metadata_source(self):
        """Should include metadata about analysis method."""
        tool = AnalyzeTrack()

        result = tool(file_path="track_128bpm.mp3")

        assert result.success is True
        assert result.metadata["source"] == "filename_parsing"
        assert result.metadata["method"] == "deterministic"

    def test_real_world_filenames(self):
        """Should handle real-world filename patterns."""
        tool = AnalyzeTrack()

        real_filenames = [
            "Lane 8 - Brightest Lights (128 bpm, A minor).mp3",
            "progressive_house_128_aminor_high-energy.wav",
            "track-001-125bpm-Cmajor.flac",
            "My Production [128 BPM] [Gminor].mp3",
        ]

        for filename in real_filenames:
            result = tool(file_path=filename)
            assert result.success is True
            # At least BPM should be found
            assert result.data["bpm"] != "unknown" or result.data["key"] != "unknown"
