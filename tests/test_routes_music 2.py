"""
Tests for api/routes/analyze.py and api/routes/generate.py.

Covers:
    POST /analyze/sample  — full audio feature extraction
    POST /analyze/melody  — pYIN melody detection
    POST /generate/chords-from-text — chord progression from key + genre
    POST /generate/bass   — bass line generation
    POST /generate/drums  — drum pattern generation
    POST /generate/full   — complete arrangement pipeline

Strategy:
    - TestClient (synchronous) against the real FastAPI app.
    - Engine I/O patched via patch("api.routes.analyze._get_engine") and
      patch("api.routes.generate._get_engine") so no audio files are loaded.
    - core/ music theory helpers (suggest_progression, generate_bassline,
      generate_pattern) are NOT mocked for happy-path tests — they are pure
      and deterministic.
    - Error-path tests inject exceptions via mock engine methods.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures
from core.music_theory.harmony import suggest_progression
from core.music_theory.types import BassNote, DrumPattern

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared helpers — build realistic mock return values from real types
# ---------------------------------------------------------------------------


def _make_key() -> Key:
    """Return a realistic Key for A minor."""
    return Key(root="A", mode="minor", confidence=0.85)


def _make_spectral() -> SpectralFeatures:
    """Return minimal SpectralFeatures that satisfies all field invariants."""
    return SpectralFeatures(
        chroma=tuple([0.1] * 12),
        rms=0.1,
        onsets_sec=(0.5, 1.0),
        tempo=128.0,
        beat_frames=(10, 20, 30),
    )


def _make_analysis(*, notes: tuple[Note, ...] = ()) -> SampleAnalysis:
    """Return a complete SampleAnalysis with optional melody notes."""
    return SampleAnalysis(
        bpm=128.0,
        key=_make_key(),
        energy=7,
        duration_sec=5.0,
        sample_rate=44100,
        notes=notes,
        spectral=_make_spectral(),
    )


def _make_note(onset_sec: float = 0.5, duration_sec: float = 0.4) -> Note:
    """Return a single Note at A4 (MIDI 69)."""
    return Note(
        pitch_midi=69,
        pitch_name="A4",
        onset_sec=onset_sec,
        duration_sec=duration_sec,
        velocity=80,
    )


def _make_voicing() -> Any:
    """Return a real VoicingResult using the pure core harmony engine."""
    return suggest_progression("A", genre="organic house", bars=4)


def _make_bass_notes() -> tuple[BassNote, ...]:
    """Return a minimal tuple of BassNote objects for mocking generate_bass."""
    from core.music_theory.bass import generate_bassline

    voicing = _make_voicing()
    return generate_bassline(voicing.chords, genre="organic house", seed=0)


def _make_drum_pattern() -> DrumPattern:
    """Return a real DrumPattern from the pure core drum engine."""
    from core.music_theory.drums import generate_pattern

    return generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)


def _make_full_composition() -> Any:
    """Return a FullComposition-like MagicMock with realistic fields."""
    from ingestion.audio_engine import FullComposition

    voicing = _make_voicing()
    analysis = _make_analysis(notes=(_make_note(),))
    bass_notes = _make_bass_notes()
    drum_pattern = _make_drum_pattern()

    return FullComposition(
        analysis=analysis,
        melody_notes=(_make_note(),),
        voicing=voicing,
        bass_notes=bass_notes,
        drum_pattern=drum_pattern,
        bpm=128.0,
        genre="organic house",
        bars=4,
        midi_paths={},
        processing_time_ms=42.5,
    )


# ---------------------------------------------------------------------------
# TestAnalyzeSampleEndpoint
# ---------------------------------------------------------------------------


class TestAnalyzeSampleEndpoint:
    """POST /analyze/sample — full audio feature extraction."""

    _VALID_REQUEST: dict[str, Any] = {
        "file_path": "/tmp/fake_loop.wav",
        "duration": 10.0,
        "include_melody": False,
    }

    def test_analyze_sample_returns_200(self) -> None:
        """Valid request with mocked engine returns HTTP 200."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.return_value = _make_analysis()

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.status_code == 200

    def test_analyze_sample_response_has_bpm(self) -> None:
        """Response body contains bpm == 128.0 from mock analysis."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.return_value = _make_analysis()

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.json()["bpm"] == 128.0

    def test_analyze_sample_response_has_key(self) -> None:
        """Response body key.root == 'A' from mock Key(root='A', mode='minor', ...)."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.return_value = _make_analysis()

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.json()["key"]["root"] == "A"

    def test_analyze_sample_response_has_energy(self) -> None:
        """Response body energy == 7 from mock SampleAnalysis."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.return_value = _make_analysis()

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.json()["energy"] == 7

    def test_analyze_sample_file_not_found_returns_422(self) -> None:
        """FileNotFoundError from engine.analyze_sample → HTTP 422."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.side_effect = FileNotFoundError(
                "No such file: /tmp/missing.wav"
            )

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.status_code == 422

    def test_analyze_sample_unsupported_format_returns_422(self) -> None:
        """ValueError from engine.analyze_sample (bad extension) → HTTP 422."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.side_effect = ValueError("Unsupported audio format: .docx")

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.status_code == 422

    def test_analyze_sample_runtime_error_returns_500(self) -> None:
        """RuntimeError from engine.analyze_sample (decode failure) → HTTP 500."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.analyze_sample.side_effect = RuntimeError("Audio decoding failed")

            response = client.post("/analyze/sample", json=self._VALID_REQUEST)

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# TestAnalyzeMelodyEndpoint
# ---------------------------------------------------------------------------


class TestAnalyzeMelodyEndpoint:
    """POST /analyze/melody — pYIN melody detection."""

    _VALID_REQUEST: dict[str, Any] = {
        "file_path": "/tmp/fake_lead.wav",
        "duration": 10.0,
    }

    def test_analyze_melody_returns_200(self) -> None:
        """Valid request with mocked engine returns HTTP 200."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.extract_melody.return_value = [_make_note(0.5), _make_note(1.0)]

            response = client.post("/analyze/melody", json=self._VALID_REQUEST)

        assert response.status_code == 200

    def test_analyze_melody_response_has_notes(self) -> None:
        """Response body contains a 'notes' list."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.extract_melody.return_value = [_make_note(0.5), _make_note(1.0)]

            response = client.post("/analyze/melody", json=self._VALID_REQUEST)

        data = response.json()
        assert "notes" in data
        assert isinstance(data["notes"], list)

    def test_analyze_melody_response_has_note_count(self) -> None:
        """Response body contains 'note_count' matching the length of 'notes'."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.extract_melody.return_value = [_make_note(0.5), _make_note(1.0)]

            response = client.post("/analyze/melody", json=self._VALID_REQUEST)

        data = response.json()
        assert data["note_count"] == len(data["notes"])

    def test_analyze_melody_file_not_found_returns_422(self) -> None:
        """FileNotFoundError from engine.extract_melody → HTTP 422."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.extract_melody.side_effect = FileNotFoundError(
                "No such file: /tmp/fake_lead.wav"
            )

            response = client.post("/analyze/melody", json=self._VALID_REQUEST)

        assert response.status_code == 422

    def test_analyze_melody_empty_melody(self) -> None:
        """Engine returning empty list → note_count == 0 in response."""
        with patch("api.routes.analyze._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.extract_melody.return_value = []

            response = client.post("/analyze/melody", json=self._VALID_REQUEST)

        data = response.json()
        assert response.status_code == 200
        assert data["note_count"] == 0
        assert data["notes"] == []


# ---------------------------------------------------------------------------
# TestGenerateChordsEndpoint
# ---------------------------------------------------------------------------


class TestGenerateChordsEndpoint:
    """POST /generate/chords-from-text — chord progression from key + genre."""

    _VALID_REQUEST: dict[str, Any] = {
        "key": "A minor",
        "genre": "organic house",
        "bars": 4,
        "mood": "melancholic",
    }

    def test_generate_chords_returns_200(self) -> None:
        """Valid request with valid key + genre → HTTP 200 (no engine mock needed)."""
        response = client.post("/generate/chords-from-text", json=self._VALID_REQUEST)
        assert response.status_code == 200

    def test_generate_chords_returns_progression(self) -> None:
        """Response body contains 'chords' list and 'progression_label' string."""
        response = client.post("/generate/chords-from-text", json=self._VALID_REQUEST)
        data = response.json()

        assert "chords" in data
        assert isinstance(data["chords"], list)
        assert len(data["chords"]) > 0
        assert "progression_label" in data
        assert isinstance(data["progression_label"], str)
        assert len(data["progression_label"]) > 0

    def test_generate_chords_invalid_genre_returns_422(self) -> None:
        """Pydantic field_validator rejects unknown genre → HTTP 422."""
        response = client.post(
            "/generate/chords-from-text",
            json={**self._VALID_REQUEST, "genre": "death metal"},
        )
        assert response.status_code == 422

    def test_generate_chords_invalid_key_returns_422(self) -> None:
        """Empty key string fails _parse_key → HTTP 422 from the route."""
        response = client.post(
            "/generate/chords-from-text",
            json={**self._VALID_REQUEST, "key": ""},
        )
        assert response.status_code == 422

    def test_generate_chords_bars_respected(self) -> None:
        """Request with bars=8 → response bars == 8."""
        response = client.post(
            "/generate/chords-from-text",
            json={**self._VALID_REQUEST, "bars": 8},
        )
        data = response.json()
        assert response.status_code == 200
        assert data["bars"] == 8

    def test_generate_chords_key_in_response(self) -> None:
        """Response key_root is a non-empty string."""
        response = client.post("/generate/chords-from-text", json=self._VALID_REQUEST)
        data = response.json()
        assert "key_root" in data
        assert isinstance(data["key_root"], str)
        assert len(data["key_root"]) > 0


# ---------------------------------------------------------------------------
# TestGenerateBassEndpoint
# ---------------------------------------------------------------------------


class TestGenerateBassEndpoint:
    """POST /generate/bass — bass line for a given key and genre."""

    _VALID_REQUEST: dict[str, Any] = {
        "key": "A minor",
        "genre": "organic house",
        "bars": 4,
        "humanize": False,
        "seed": 0,
    }

    def test_generate_bass_returns_200(self) -> None:
        """Valid request with mocked engine.generate_bass → HTTP 200."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_bass.return_value = _make_bass_notes()

            response = client.post("/generate/bass", json=self._VALID_REQUEST)

        assert response.status_code == 200

    def test_generate_bass_response_has_notes(self) -> None:
        """Response body contains a 'notes' list."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_bass.return_value = _make_bass_notes()

            response = client.post("/generate/bass", json=self._VALID_REQUEST)

        data = response.json()
        assert "notes" in data
        assert isinstance(data["notes"], list)

    def test_generate_bass_invalid_key_returns_422(self) -> None:
        """Key without mode part fails _parse_key → HTTP 422."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine

            response = client.post(
                "/generate/bass",
                json={**self._VALID_REQUEST, "key": "invalid"},
            )

        assert response.status_code == 422

    def test_generate_bass_note_count_matches(self) -> None:
        """Response note_count equals len(notes)."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_bass.return_value = _make_bass_notes()

            response = client.post("/generate/bass", json=self._VALID_REQUEST)

        data = response.json()
        assert data["note_count"] == len(data["notes"])

    def test_generate_bass_humanize_false(self) -> None:
        """humanize=False is accepted and route still returns 200."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_bass.return_value = _make_bass_notes()

            response = client.post(
                "/generate/bass",
                json={**self._VALID_REQUEST, "humanize": False},
            )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestGenerateDrumsEndpoint
# ---------------------------------------------------------------------------


class TestGenerateDrumsEndpoint:
    """POST /generate/drums — drum pattern for a given genre and energy."""

    _VALID_REQUEST: dict[str, Any] = {
        "genre": "organic house",
        "bars": 4,
        "energy": 7,
        "bpm": 128.0,
        "humanize": False,
        "seed": 0,
    }

    def test_generate_drums_returns_200(self) -> None:
        """Valid request with mocked engine.generate_drums → HTTP 200."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_drums.return_value = _make_drum_pattern()

            response = client.post("/generate/drums", json=self._VALID_REQUEST)

        assert response.status_code == 200

    def test_generate_drums_has_hits(self) -> None:
        """Response body 'hits' is a non-empty list."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_drums.return_value = _make_drum_pattern()

            response = client.post("/generate/drums", json=self._VALID_REQUEST)

        data = response.json()
        assert "hits" in data
        assert isinstance(data["hits"], list)
        assert len(data["hits"]) > 0

    def test_generate_drums_invalid_genre_returns_422(self) -> None:
        """Unknown genre rejected by Pydantic field_validator → HTTP 422."""
        response = client.post(
            "/generate/drums",
            json={**self._VALID_REQUEST, "genre": "invalid"},
        )
        assert response.status_code == 422

    def test_generate_drums_hit_count_matches(self) -> None:
        """Response hit_count equals len(hits)."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.generate_drums.return_value = _make_drum_pattern()

            response = client.post("/generate/drums", json=self._VALID_REQUEST)

        data = response.json()
        assert data["hit_count"] == len(data["hits"])


# ---------------------------------------------------------------------------
# TestGenerateFullEndpoint
# ---------------------------------------------------------------------------


class TestGenerateFullEndpoint:
    """POST /generate/full — complete audio → MIDI arrangement pipeline."""

    _VALID_REQUEST: dict[str, Any] = {
        "file_path": "/tmp/fake_loop.wav",
        "genre": "organic house",
        "bars": 4,
        "bpm": None,
        "energy": None,
        "humanize": False,
        "seed": 0,
        "output_dir": None,
    }

    def test_generate_full_returns_200(self) -> None:
        """Valid request with mocked engine.full_pipeline → HTTP 200."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.full_pipeline.return_value = _make_full_composition()

            response = client.post("/generate/full", json=self._VALID_REQUEST)

        assert response.status_code == 200

    def test_generate_full_has_all_fields(self) -> None:
        """Response body contains bpm, key, chords, bass_note_count, drum_hit_count."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.full_pipeline.return_value = _make_full_composition()

            response = client.post("/generate/full", json=self._VALID_REQUEST)

        data = response.json()
        assert "bpm" in data
        assert "key" in data
        assert "chords" in data
        assert "bass_note_count" in data
        assert "drum_hit_count" in data

    def test_generate_full_file_not_found_returns_422(self) -> None:
        """FileNotFoundError from engine.full_pipeline → HTTP 422."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.full_pipeline.side_effect = FileNotFoundError(
                "No such file: /tmp/fake_loop.wav"
            )

            response = client.post("/generate/full", json=self._VALID_REQUEST)

        assert response.status_code == 422

    def test_generate_full_runtime_error_returns_500(self) -> None:
        """RuntimeError from engine.full_pipeline → HTTP 500."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.full_pipeline.side_effect = RuntimeError("Audio decoding failed")

            response = client.post("/generate/full", json=self._VALID_REQUEST)

        assert response.status_code == 500

    def test_generate_full_processing_time_present(self) -> None:
        """Response body contains processing_time_ms >= 0."""
        with patch("api.routes.generate._get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_get.return_value = mock_engine
            mock_engine.full_pipeline.return_value = _make_full_composition()

            response = client.post("/generate/full", json=self._VALID_REQUEST)

        data = response.json()
        assert "processing_time_ms" in data
        assert data["processing_time_ms"] >= 0
