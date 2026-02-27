"""
Tests for core/audio/types.py — frozen dataclass invariants.

Validates:
    - All types are frozen (immutable)
    - Field types and defaults are correct
    - Key.label computed property works
    - SampleAnalysis.notes/spectral optional fields
"""

import pytest

from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures

# ---------------------------------------------------------------------------
# Note
# ---------------------------------------------------------------------------


class TestNote:
    def test_note_creation(self):
        """Note can be created with all required fields."""
        note = Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80)
        assert note.pitch_midi == 69
        assert note.pitch_name == "A4"
        assert note.onset_sec == 0.0
        assert note.duration_sec == 0.5
        assert note.velocity == 80

    def test_note_is_frozen(self):
        """Note is immutable — mutation raises TypeError."""
        note = Note(pitch_midi=60, pitch_name="C4", onset_sec=0.0, duration_sec=0.25, velocity=64)
        with pytest.raises((TypeError, AttributeError)):
            note.pitch_midi = 61  # type: ignore[misc]

    def test_note_equality(self):
        """Two Notes with same fields are equal."""
        a = Note(pitch_midi=69, pitch_name="A4", onset_sec=1.0, duration_sec=0.5, velocity=90)
        b = Note(pitch_midi=69, pitch_name="A4", onset_sec=1.0, duration_sec=0.5, velocity=90)
        assert a == b

    def test_note_inequality(self):
        """Notes with different pitch are not equal."""
        a = Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80)
        b = Note(pitch_midi=70, pitch_name="A#4", onset_sec=0.0, duration_sec=0.5, velocity=80)
        assert a != b

    def test_note_hashable(self):
        """Frozen dataclasses must be hashable."""
        note = Note(pitch_midi=60, pitch_name="C4", onset_sec=0.0, duration_sec=0.5, velocity=64)
        _ = {note}  # should not raise

    def test_note_in_tuple(self):
        """Notes can be stored in tuples (for SampleAnalysis.notes)."""
        notes = (
            Note(pitch_midi=60, pitch_name="C4", onset_sec=0.0, duration_sec=0.5, velocity=64),
            Note(pitch_midi=64, pitch_name="E4", onset_sec=0.5, duration_sec=0.5, velocity=70),
        )
        assert len(notes) == 2
        assert notes[0].pitch_midi == 60


# ---------------------------------------------------------------------------
# Key
# ---------------------------------------------------------------------------


class TestKey:
    def test_key_creation(self):
        """Key stores root, mode, confidence."""
        key = Key(root="A", mode="minor", confidence=0.85)
        assert key.root == "A"
        assert key.mode == "minor"
        assert key.confidence == 0.85

    def test_key_label_minor(self):
        """Key.label returns '<root> minor' for minor keys."""
        key = Key(root="A", mode="minor", confidence=0.9)
        assert key.label == "A minor"

    def test_key_label_major(self):
        """Key.label returns '<root> major' for major keys."""
        key = Key(root="C#", mode="major", confidence=0.75)
        assert key.label == "C# major"

    def test_key_is_frozen(self):
        """Key is immutable."""
        key = Key(root="C", mode="major", confidence=0.8)
        with pytest.raises((TypeError, AttributeError)):
            key.root = "D"  # type: ignore[misc]

    def test_key_label_is_property_not_field(self):
        """Key.label is computed — not stored as a separate field."""
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(Key)}
        assert "label" not in field_names

    def test_key_hashable(self):
        """Key is hashable."""
        key = Key(root="F#", mode="minor", confidence=0.7)
        _ = {key}

    def test_flat_root_key_label(self):
        """Flat root notes format correctly."""
        key = Key(root="Bb", mode="minor", confidence=0.88)
        assert key.label == "Bb minor"


# ---------------------------------------------------------------------------
# SpectralFeatures
# ---------------------------------------------------------------------------


class TestSpectralFeatures:
    def _make_spectral(self) -> SpectralFeatures:
        return SpectralFeatures(
            chroma=tuple([1.0 / 12] * 12),
            rms=0.1,
            onsets_sec=(0.5, 1.0, 1.5),
            tempo=128.0,
            beat_frames=(0, 22, 44, 66),
        )

    def test_spectral_creation(self):
        sf = self._make_spectral()
        assert len(sf.chroma) == 12
        assert sf.rms == pytest.approx(0.1)
        assert sf.tempo == 128.0

    def test_spectral_is_frozen(self):
        sf = self._make_spectral()
        with pytest.raises((TypeError, AttributeError)):
            sf.tempo = 130.0  # type: ignore[misc]

    def test_chroma_is_tuple(self):
        """chroma stored as tuple (hashable, not list)."""
        sf = self._make_spectral()
        assert isinstance(sf.chroma, tuple)

    def test_onsets_are_tuple(self):
        sf = self._make_spectral()
        assert isinstance(sf.onsets_sec, tuple)

    def test_beat_frames_are_tuple(self):
        sf = self._make_spectral()
        assert isinstance(sf.beat_frames, tuple)


# ---------------------------------------------------------------------------
# SampleAnalysis
# ---------------------------------------------------------------------------


class TestSampleAnalysis:
    def _make_key(self) -> Key:
        return Key(root="A", mode="minor", confidence=0.85)

    def test_sample_analysis_minimal(self):
        """SampleAnalysis with just required fields — notes and spectral default."""
        sa = SampleAnalysis(
            bpm=128.0,
            key=self._make_key(),
            energy=7,
            duration_sec=30.0,
            sample_rate=44100,
        )
        assert sa.bpm == 128.0
        assert sa.energy == 7
        assert sa.notes == ()  # default empty tuple
        assert sa.spectral is None

    def test_sample_analysis_is_frozen(self):
        sa = SampleAnalysis(
            bpm=120.0,
            key=self._make_key(),
            energy=5,
            duration_sec=10.0,
            sample_rate=44100,
        )
        with pytest.raises((TypeError, AttributeError)):
            sa.bpm = 130.0  # type: ignore[misc]

    def test_sample_analysis_with_notes(self):
        """Notes tuple preserved in SampleAnalysis."""
        notes = (
            Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80),
            Note(pitch_midi=71, pitch_name="B4", onset_sec=0.5, duration_sec=0.5, velocity=75),
        )
        sa = SampleAnalysis(
            bpm=120.0,
            key=self._make_key(),
            energy=6,
            duration_sec=5.0,
            sample_rate=44100,
            notes=notes,
        )
        assert len(sa.notes) == 2
        assert sa.notes[0].pitch_midi == 69

    def test_sample_analysis_with_spectral(self):
        """SpectralFeatures stored in SampleAnalysis."""
        spectral = SpectralFeatures(
            chroma=tuple([0.0] * 12),
            rms=0.05,
            onsets_sec=(),
            tempo=120.0,
            beat_frames=(),
        )
        sa = SampleAnalysis(
            bpm=120.0,
            key=self._make_key(),
            energy=4,
            duration_sec=10.0,
            sample_rate=44100,
            spectral=spectral,
        )
        assert sa.spectral is not None
        assert sa.spectral.tempo == 120.0

    def test_notes_default_is_empty_tuple(self):
        """Default notes field is an empty tuple, not None."""
        sa = SampleAnalysis(
            bpm=90.0,
            key=self._make_key(),
            energy=3,
            duration_sec=8.0,
            sample_rate=22050,
        )
        assert sa.notes == ()
        assert isinstance(sa.notes, tuple)
