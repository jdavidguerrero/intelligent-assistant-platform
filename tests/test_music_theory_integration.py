"""
Integration tests for core/music_theory/ — Week 11→Week 12 pipeline.

These tests wire together the full pipeline:
    Week 11: detect_melody (mock pYIN) → list[Note]
    Week 12: melody_to_chords → VoicingResult
             optimize_voice_leading → tuple[VoicedChord]

Also verifies:
    - core/music_theory/__init__.py exports are all importable
    - YAML templates load for all genres
    - Full pipeline correctness: A minor melody → Am diatonic harmonization
    - Voice leading reduces movement vs. root-position
    - suggest_chord_progression tool still produces valid output (regression)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.music_theory import (
    Chord,
    Interval,
    Scale,
    VoicedChord,
    VoicingResult,
    available_genres,
    get_diatonic_chords,
    get_pitch_classes,
    get_scale_notes,
    melody_to_chords,
    optimize_voice_leading,
    total_voice_leading_cost,
)

# ---------------------------------------------------------------------------
# Fake Note — mirrors core.audio.types.Note
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeNote:
    pitch_midi: int
    onset_sec: float
    duration_sec: float = 0.5
    pitch_name: str = ""
    velocity: int = 80


# ---------------------------------------------------------------------------
# __init__ exports
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_all_types_importable(self):
        assert Chord is not None
        assert Interval is not None
        assert Scale is not None
        assert VoicingResult is not None
        assert VoicedChord is not None

    def test_all_functions_importable(self):
        assert callable(get_scale_notes)
        assert callable(get_diatonic_chords)
        assert callable(get_pitch_classes)
        assert callable(melody_to_chords)
        assert callable(available_genres)
        assert callable(optimize_voice_leading)
        assert callable(total_voice_leading_cost)


# ---------------------------------------------------------------------------
# Week 11 + Week 12 pipeline: melody → harmony → voiced chords
# ---------------------------------------------------------------------------


class TestMelodyToVoicedChords:
    def _make_a_minor_melody(self) -> list[_FakeNote]:
        """8 bars of A natural minor scale notes, one per bar (2 sec each)."""
        # A minor: A B C D E F G A
        midi_notes = [69, 71, 60, 62, 64, 65, 67, 69]  # A4 B4 C4 D4 E4 F4 G4 A4
        return [_FakeNote(pitch_midi=m, onset_sec=float(i) * 2.0) for i, m in enumerate(midi_notes)]

    def test_full_pipeline_returns_voicing_result(self):
        notes = self._make_a_minor_melody()
        result = melody_to_chords(
            notes,
            key_root="A",
            key_mode="natural minor",
            genre="organic house",
            bars=8,
            total_duration_sec=16.0,
        )
        assert isinstance(result, VoicingResult)
        assert len(result.chords) == 8

    def test_voiced_chords_from_pipeline(self):
        notes = self._make_a_minor_melody()
        result = melody_to_chords(
            notes,
            key_root="A",
            bars=4,
            total_duration_sec=8.0,
        )
        voiced = optimize_voice_leading(result.chords)
        assert len(voiced) == 4
        assert all(isinstance(v, VoicedChord) for v in voiced)

    def test_first_bar_a_notes_map_to_am_chord(self):
        """Bar 0 has only A (pc=9) → should match Am (degree 0)."""
        notes = [_FakeNote(pitch_midi=69, onset_sec=0.0)]  # A4 in bar 0
        result = melody_to_chords(
            notes,
            key_root="A",
            key_mode="natural minor",
            genre="organic house",
            bars=1,
            total_duration_sec=2.0,
        )
        # A is in Am (degree 0) — highest overlap
        assert result.chords[0].degree == 0

    def test_voice_leading_cost_is_non_negative(self):
        notes = self._make_a_minor_melody()
        result = melody_to_chords(notes, key_root="A", bars=4, total_duration_sec=8.0)
        voiced = optimize_voice_leading(result.chords)
        cost = total_voice_leading_cost(voiced)
        assert cost >= 0

    def test_pitch_classes_preserved_through_voice_leading(self):
        """Pitch classes should not change after voice leading optimization."""
        chords = get_diatonic_chords("A", "natural minor", voicing="extended")[:4]
        voiced = optimize_voice_leading(chords)
        for orig, v in zip(chords, voiced, strict=False):
            orig_pcs = frozenset(p % 12 for p in orig.midi_notes)
            opt_pcs = frozenset(p % 12 for p in v.pitches)
            assert orig_pcs == opt_pcs

    def test_all_genres_produce_valid_progressions(self):
        notes = self._make_a_minor_melody()
        for genre in available_genres():
            result = melody_to_chords(
                notes,
                key_root="A",
                genre=genre,
                bars=4,
                total_duration_sec=8.0,
            )
            assert len(result.chords) == 4
            voiced = optimize_voice_leading(result.chords)
            assert len(voiced) == 4


# ---------------------------------------------------------------------------
# Genre template completeness
# ---------------------------------------------------------------------------


class TestGenreTemplates:
    def test_all_5_genres_available(self):
        assert len(available_genres()) == 5

    def test_organic_house_has_4_progressions(self):
        from core.music_theory.harmony import _load_template

        t = _load_template("organic house")
        assert len(t["progressions"]) == 4

    def test_all_templates_have_valid_voicing(self):
        from core.music_theory.harmony import _load_template
        from core.music_theory.scales import VOICING_UPGRADES

        for genre in available_genres():
            t = _load_template(genre)
            assert t["voicing"] in VOICING_UPGRADES


# ---------------------------------------------------------------------------
# Regression: existing tools still work
# ---------------------------------------------------------------------------


class TestRegressions:
    def test_get_scale_notes_unchanged(self):
        notes = get_scale_notes("A", "natural minor")
        assert notes == ("A", "B", "C", "D", "E", "F", "G")

    def test_get_diatonic_chords_a_minor_unchanged(self):
        chords = get_diatonic_chords("A", "natural minor", voicing="triads")
        names = [c.name for c in chords]
        assert names == ["Am", "Bdim", "C", "Dm", "Em", "F", "G"]

    def test_get_pitch_classes_c_major_unchanged(self):
        pcs = get_pitch_classes("C", "major")
        assert pcs == frozenset({0, 2, 4, 5, 7, 9, 11})

    def test_core_midi_chord_resolution_still_works(self):
        """core.midi.resolve_chord unaffected by Week 12 additions."""
        from core.midi import resolve_chord

        voicing = resolve_chord("Am7")
        assert voicing.root == "A"
        assert voicing.quality == "m7"

    def test_week11_audio_types_still_importable(self):
        from core.audio.types import Note

        note = Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80)
        assert note.pitch_midi == 69


# ---------------------------------------------------------------------------
# Voice leading smoke test: quantitative improvement
# ---------------------------------------------------------------------------


class TestVoiceLeadingImprovement:
    def test_smooth_progression_has_low_total_cost(self):
        """A well-voiced common progression should have < 30 total movement."""
        # i - VI - III - VII in A minor (typical organic house)
        chords = get_diatonic_chords("A", "natural minor", voicing="extended")
        # Select degrees 0, 5, 2, 6
        degree_map = {c.degree: c for c in chords}
        progression = [degree_map[d] for d in [0, 5, 2, 6]]
        voiced = optimize_voice_leading(progression)
        cost = total_voice_leading_cost(voiced)
        # Optimized voice leading over 4 chords should be well under 30 semitones
        assert cost < 30, f"Total voice leading cost {cost} seems too high"

    def test_optimized_less_than_root_position(self):
        """Optimized cost ≤ root-position cost for a 7-chord diatonic set."""
        from core.music_theory.voicing import _voice_leading_score

        chords = get_diatonic_chords("C", "major", voicing="extended")

        root_cost = sum(
            _voice_leading_score(
                tuple(chords[i].midi_notes),
                tuple(chords[i + 1].midi_notes),
            )
            for i in range(len(chords) - 1)
        )

        voiced = optimize_voice_leading(chords)
        opt_cost = total_voice_leading_cost(voiced)

        assert opt_cost <= root_cost
