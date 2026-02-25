"""
Tests for core/music_theory/types.py — frozen dataclass invariants.

Validates:
    - Chord, Scale, Interval, VoicingResult are immutable
    - Field validation raises ValueError on bad input
    - Computed properties (Scale.label, Scale.pitch_classes, VoicingResult.chord_names)
    - VoicingResult.progression_label
"""

import pytest

from core.music_theory.scales import get_diatonic_chords
from core.music_theory.types import Chord, Interval, Scale, VoicingResult

# ---------------------------------------------------------------------------
# Interval
# ---------------------------------------------------------------------------


class TestInterval:
    def test_creation(self):
        iv = Interval(semitones=7, name="perfect fifth")
        assert iv.semitones == 7
        assert iv.name == "perfect fifth"

    def test_frozen(self):
        iv = Interval(semitones=4, name="major third")
        with pytest.raises((TypeError, AttributeError)):
            iv.semitones = 5  # type: ignore[misc]

    def test_hashable(self):
        iv = Interval(semitones=12, name="octave")
        _ = {iv}  # should not raise

    def test_equality(self):
        a = Interval(semitones=7, name="fifth")
        b = Interval(semitones=7, name="fifth")
        assert a == b

    def test_negative_semitones_allowed(self):
        iv = Interval(semitones=-7, name="descending fifth")
        assert iv.semitones == -7

    def test_zero_semitones_allowed(self):
        iv = Interval(semitones=0, name="unison")
        assert iv.semitones == 0

    def test_out_of_range_semitones_raises(self):
        with pytest.raises(ValueError, match="semitones"):
            Interval(semitones=25, name="too large")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            Interval(semitones=5, name="")


# ---------------------------------------------------------------------------
# Chord
# ---------------------------------------------------------------------------


class TestChord:
    def _make_chord(self, **kwargs) -> Chord:
        defaults = {
            "root": "A",
            "quality": "minor",
            "name": "Am",
            "roman": "i",
            "degree": 0,
            "midi_notes": (57, 60, 64),
        }
        defaults.update(kwargs)
        return Chord(**defaults)

    def test_creation(self):
        chord = self._make_chord()
        assert chord.root == "A"
        assert chord.quality == "minor"
        assert chord.name == "Am"
        assert chord.roman == "i"
        assert chord.degree == 0
        assert chord.midi_notes == (57, 60, 64)

    def test_frozen(self):
        chord = self._make_chord()
        with pytest.raises((TypeError, AttributeError)):
            chord.root = "B"  # type: ignore[misc]

    def test_hashable(self):
        chord = self._make_chord()
        _ = {chord}

    def test_equality(self):
        a = self._make_chord()
        b = self._make_chord()
        assert a == b

    def test_invalid_degree_raises(self):
        with pytest.raises(ValueError, match="degree"):
            self._make_chord(degree=-1)
        with pytest.raises(ValueError, match="degree"):
            self._make_chord(degree=12)

    def test_invalid_midi_pitch_raises(self):
        with pytest.raises(ValueError, match="MIDI pitch"):
            self._make_chord(midi_notes=(200, 60, 64))

    def test_empty_root_raises(self):
        with pytest.raises(ValueError, match="root"):
            self._make_chord(root="")

    def test_empty_quality_raises(self):
        with pytest.raises(ValueError, match="quality"):
            self._make_chord(quality="")

    def test_midi_notes_is_tuple(self):
        chord = self._make_chord()
        assert isinstance(chord.midi_notes, tuple)


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


class TestScale:
    def _make_scale(self, **kwargs) -> Scale:
        defaults = {
            "root": "A",
            "mode": "natural minor",
            "notes": ("A", "B", "C", "D", "E", "F", "G"),
        }
        defaults.update(kwargs)
        return Scale(**defaults)

    def test_creation(self):
        s = self._make_scale()
        assert s.root == "A"
        assert s.mode == "natural minor"
        assert len(s.notes) == 7

    def test_frozen(self):
        s = self._make_scale()
        with pytest.raises((TypeError, AttributeError)):
            s.root = "B"  # type: ignore[misc]

    def test_label_property(self):
        s = self._make_scale()
        assert s.label == "A natural minor"

    def test_label_major(self):
        s = self._make_scale(root="C", mode="major", notes=("C", "D", "E", "F", "G", "A", "B"))
        assert s.label == "C major"

    def test_pitch_classes(self):
        s = self._make_scale()  # A natural minor: A B C D E F G
        pcs = s.pitch_classes
        assert isinstance(pcs, frozenset)
        # A=9, B=11, C=0, D=2, E=4, F=5, G=7
        assert pcs == frozenset({9, 11, 0, 2, 4, 5, 7})

    def test_hashable(self):
        s = self._make_scale()
        _ = {s}

    def test_notes_is_tuple(self):
        s = self._make_scale()
        assert isinstance(s.notes, tuple)

    def test_empty_root_raises(self):
        with pytest.raises(ValueError, match="root"):
            self._make_scale(root="")

    def test_empty_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            self._make_scale(mode="")

    def test_empty_notes_raises(self):
        with pytest.raises(ValueError, match="notes"):
            self._make_scale(notes=())


# ---------------------------------------------------------------------------
# VoicingResult
# ---------------------------------------------------------------------------


class TestVoicingResult:
    def _make_result(self, **kwargs) -> VoicingResult:
        chords = get_diatonic_chords("A", "natural minor")[:4]
        defaults = {
            "chords": chords,
            "key_root": "A",
            "key_mode": "natural minor",
            "genre": "organic house",
            "bars": 4,
        }
        defaults.update(kwargs)
        return VoicingResult(**defaults)

    def test_creation(self):
        r = self._make_result()
        assert r.key_root == "A"
        assert r.key_mode == "natural minor"
        assert r.genre == "organic house"
        assert r.bars == 4
        assert len(r.chords) == 4

    def test_frozen(self):
        r = self._make_result()
        with pytest.raises((TypeError, AttributeError)):
            r.key_root = "C"  # type: ignore[misc]

    def test_chord_names_property(self):
        r = self._make_result()
        names = r.chord_names
        assert isinstance(names, tuple)
        assert all(isinstance(n, str) for n in names)
        assert len(names) == 4

    def test_progression_label_no_roman_labels(self):
        r = self._make_result()
        label = r.progression_label
        assert isinstance(label, str)
        assert " - " in label

    def test_progression_label_with_roman_labels(self):
        r = self._make_result(roman_labels=("i", "VI", "III", "VII"))
        assert r.progression_label == "i - VI - III - VII"

    def test_empty_chords_raises(self):
        with pytest.raises(ValueError, match="chords"):
            self._make_result(chords=())

    def test_empty_key_root_raises(self):
        with pytest.raises(ValueError, match="key_root"):
            self._make_result(key_root="")

    def test_zero_bars_raises(self):
        with pytest.raises(ValueError, match="bars"):
            self._make_result(bars=0)

    def test_negative_bars_raises(self):
        with pytest.raises(ValueError, match="bars"):
            self._make_result(bars=-1)

    def test_hashable(self):
        r = self._make_result()
        _ = {r}
