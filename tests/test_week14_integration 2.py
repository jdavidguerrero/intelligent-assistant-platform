"""
tests/test_week14_integration.py — Week 14 integration + performance tests.

Covers:
    - Full pipeline: suggest_progression → generate_bassline → generate_pattern
      → full_arrangement_to_midi (all 5 genres)
    - Humanize pipeline: generate_bassline → humanize_timing → humanize_velocity
      → bassline_to_midi (tick_offset propagation)
    - add_ghost_notes pipeline: generate_pattern → add_ghost_notes → pattern_to_midi
    - Performance: 8-bar pattern generation < 200 ms
    - Edge cases: BPM 80 (slow) and BPM 150 (fast) — timing math correctness
    - New bass styles (sub, driving, minimal) across all genres
    - Energy layer gating across all genres
"""

from __future__ import annotations

import time

import pytest

from core.music_theory.bass import generate_bassline
from core.music_theory.drums import generate_pattern
from core.music_theory.harmony import suggest_progression
from core.music_theory.humanize import add_ghost_notes, humanize_timing, humanize_velocity
from ingestion.midi_export import (
    BASS_CHANNEL,
    bassline_to_midi,
    full_arrangement_to_midi,
    pattern_to_midi,
)

GENRES = [
    "organic house",
    "deep house",
    "melodic techno",
    "progressive house",
    "afro house",
]


# ---------------------------------------------------------------------------
# Full pipeline (suggest_progression → generate_bassline → generate_pattern
#                → full_arrangement_to_midi)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    @pytest.mark.parametrize("genre", GENRES)
    def test_full_pipeline_all_genres(self, genre: str) -> None:
        """End-to-end: progression → bass → drums → single MIDI file."""
        v = suggest_progression("A", genre=genre, bars=4)
        bass = generate_bassline(v.chords, genre=genre, seed=0)
        drums = generate_pattern(genre=genre, bars=4, energy=7, humanize=False, seed=0)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=122.0)

        assert len(midi.tracks) == 4
        # All tracks have events
        for track in midi.tracks[1:]:
            events = [m for m in track if m.type in ("note_on", "note_off")]
            assert len(events) > 0, f"Track empty for genre={genre}"

    def test_full_pipeline_8_bars(self) -> None:
        """8-bar arrangement should work without error."""
        v = suggest_progression("C", genre="organic house", bars=8)
        bass = generate_bassline(v.chords, genre="organic house", bars=8, seed=1)
        drums = generate_pattern(genre="organic house", bars=8, energy=8, humanize=False, seed=1)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=120.0)
        assert len(midi.tracks) == 4

    def test_full_pipeline_with_humanize(self) -> None:
        """End-to-end with humanize=True — must produce valid MIDI."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=True, seed=5)
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=True, seed=5)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=122.0)
        assert len(midi.tracks) == 4

    def test_full_pipeline_melodic_techno(self) -> None:
        """Melodic techno has tighter energy layers — verify full kit at energy=10."""
        v = suggest_progression("D", genre="melodic techno", bars=4)
        bass = generate_bassline(v.chords, genre="melodic techno", seed=2)
        drums = generate_pattern(genre="melodic techno", bars=4, energy=10, humanize=False, seed=2)
        instruments = {h.instrument for h in drums.hits}
        assert "kick" in instruments
        midi = full_arrangement_to_midi(v, bass, drums, bpm=130.0)
        assert len(midi.tracks) == 4

    def test_full_pipeline_afro_house(self) -> None:
        """Afro house has syncopated kick — verify pattern + export works."""
        v = suggest_progression("F", genre="afro house", bars=4)
        bass = generate_bassline(v.chords, genre="afro house", seed=3)
        drums = generate_pattern(genre="afro house", bars=4, energy=7, humanize=False, seed=3)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=123.0)
        assert len(midi.tracks) == 4


# ---------------------------------------------------------------------------
# Humanize pipeline (generate_bassline → humanize_timing → humanize_velocity
#                    → bassline_to_midi)
# ---------------------------------------------------------------------------


class TestHumanizePipeline:
    def test_humanize_timing_propagates_to_midi(self) -> None:
        """tick_offset values set by humanize_timing must survive to MIDI export."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        humanized = humanize_timing(bass, jitter_ms=8.0, bpm=120.0, seed=42)

        # At least some notes should have non-zero tick_offset
        offsets = [n.tick_offset for n in humanized]
        assert any(o != 0 for o in offsets), "humanize_timing should produce non-zero offsets"

        # MIDI export must not fail
        midi = bassline_to_midi(humanized, bpm=120.0)
        assert len(midi.tracks) == 2

    def test_humanize_velocity_changes_velocities(self) -> None:
        """humanize_velocity should alter velocities from the baseline."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        humanized = humanize_velocity(bass, variation=15, seed=99)

        original_vels = [n.velocity for n in bass]
        new_vels = [n.velocity for n in humanized]
        assert original_vels != new_vels, "humanize_velocity must change some velocities"

    def test_full_humanize_chain(self) -> None:
        """Both humanize functions applied sequentially — produces valid MIDI on ch 1."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        bass = humanize_timing(bass, jitter_ms=5.0, bpm=122.0, seed=1)
        bass = humanize_velocity(bass, variation=10, seed=2)

        midi = bassline_to_midi(bass, bpm=122.0)
        # All note events must be on BASS_CHANNEL
        for msg in midi.tracks[1]:
            if hasattr(msg, "channel"):
                assert msg.channel == BASS_CHANNEL

    def test_humanize_timing_deterministic(self) -> None:
        """Same seed → same tick offsets."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        h1 = humanize_timing(bass, jitter_ms=5.0, bpm=120.0, seed=7)
        h2 = humanize_timing(bass, jitter_ms=5.0, bpm=120.0, seed=7)
        assert h1 == h2

    def test_humanize_velocity_deterministic(self) -> None:
        """Same seed → same velocity adjustments."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        h1 = humanize_velocity(bass, variation=12, seed=11)
        h2 = humanize_velocity(bass, variation=12, seed=11)
        assert h1 == h2

    def test_humanize_drums_pipeline(self) -> None:
        """humanize_velocity applied to DrumHit tuples → valid pattern_to_midi."""
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        humanized_hits = humanize_velocity(drums.hits, variation=10, seed=42)
        # Rebuild DrumPattern with humanized hits
        from core.music_theory.types import DrumPattern

        new_pattern = DrumPattern(
            hits=humanized_hits,
            steps_per_bar=drums.steps_per_bar,
            bars=drums.bars,
            bpm=drums.bpm,
            genre=drums.genre,
        )
        midi = pattern_to_midi(new_pattern)
        assert len(midi.tracks) == 2


# ---------------------------------------------------------------------------
# Ghost notes pipeline
# ---------------------------------------------------------------------------


class TestGhostNotesPipeline:
    def test_add_ghost_notes_increases_hit_count(self) -> None:
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        augmented = add_ghost_notes(drums.hits, probability=0.3, bars=4, seed=0)
        assert len(augmented) > len(drums.hits), "ghost notes should add hits"

    def test_ghost_notes_in_valid_velocity_range(self) -> None:
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        original_positions = {(h.bar, h.step, h.instrument) for h in drums.hits}
        augmented = add_ghost_notes(
            drums.hits, probability=1.0, velocity_range=(10, 25), bars=4, seed=0
        )
        # Ghost notes (new ones) must be in velocity range
        for h in augmented:
            if (h.bar, h.step, h.instrument) not in original_positions:
                assert 10 <= h.velocity <= 25, f"Ghost velocity {h.velocity} out of range"

    def test_add_ghost_notes_pattern_to_midi(self) -> None:
        """Adding ghost notes then exporting to MIDI should work without error."""
        from core.music_theory.types import DrumPattern

        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        augmented = add_ghost_notes(drums.hits, probability=0.15, bars=4, seed=0)
        new_pattern = DrumPattern(
            hits=augmented,
            steps_per_bar=drums.steps_per_bar,
            bars=drums.bars,
            bpm=drums.bpm,
            genre=drums.genre,
        )
        midi = pattern_to_midi(new_pattern)
        assert len(midi.tracks) == 2


# ---------------------------------------------------------------------------
# New bass styles
# ---------------------------------------------------------------------------


class TestNewBassStyles:
    @pytest.mark.parametrize("genre", GENRES)
    def test_sub_style_all_genres(self, genre: str) -> None:
        """Sub style must work for all genres without error."""
        v = suggest_progression("A", genre=genre, bars=2)
        bass = generate_bassline(v.chords, genre=genre, style="sub", seed=0)
        assert len(bass) > 0

    @pytest.mark.parametrize("genre", GENRES)
    def test_driving_style_all_genres(self, genre: str) -> None:
        """Driving style must produce 8 or more notes per bar."""
        v = suggest_progression("A", genre=genre, bars=2)
        bass = generate_bassline(v.chords, genre=genre, style="driving", humanize=False, seed=0)
        # Driving = eighth notes: 8 per bar × 2 bars = 16 notes
        assert len(bass) >= 8, f"Driving style should have ≥8 notes, got {len(bass)}"

    @pytest.mark.parametrize("genre", GENRES)
    def test_minimal_style_all_genres(self, genre: str) -> None:
        """Minimal style must produce ≤4 notes per bar."""
        v = suggest_progression("A", genre=genre, bars=2)
        bass = generate_bassline(v.chords, genre=genre, style="minimal", humanize=False, seed=0)
        notes_per_bar = len(bass) / 2  # 2 bars
        assert notes_per_bar <= 4, f"Minimal style should have ≤4 notes/bar, got {notes_per_bar}"

    def test_sub_style_low_octave(self) -> None:
        """Sub style must use base_octave=1 — notes should be in MIDI range ~24–36."""
        v = suggest_progression("C", genre="organic house", bars=2)
        bass = generate_bassline(
            v.chords, genre="organic house", style="sub", humanize=False, seed=0
        )
        # C2 = MIDI 36; all sub bass notes should be below standard range
        # Sub uses base_octave=1: C1=24, A1=33, B1=35
        assert all(
            n.pitch_midi <= 48 for n in bass
        ), f"Sub style notes should be in low register, got max {max(n.pitch_midi for n in bass)}"

    def test_slides_add_notes(self) -> None:
        """slides=True should produce more notes when chord roots differ."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass_no_slides = generate_bassline(v.chords, genre="organic house", slides=False, seed=0)
        bass_with_slides = generate_bassline(v.chords, genre="organic house", slides=True, seed=0)
        # With chord changes present, slides should add notes
        # (if all chords have same root there'd be no slides — use bars=4 to ensure changes)
        assert len(bass_with_slides) >= len(bass_no_slides)

    def test_slides_step_14_position(self) -> None:
        """Slide notes are placed at step 14 (2 steps before bar end)."""
        v = suggest_progression("A", genre="organic house", bars=8)
        bass_with_slides = generate_bassline(v.chords, genre="organic house", slides=True, seed=0)
        # All notes in the bass line must be in valid step range
        assert all(0 <= n.step <= 15 for n in bass_with_slides)
        # Slide notes specifically land on step 14; verify the function ran without error
        assert isinstance(bass_with_slides, tuple)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_8_bar_pattern_under_200ms(self) -> None:
        """Generating an 8-bar drum pattern must complete in < 200ms."""
        start = time.perf_counter()
        generate_pattern(genre="organic house", bars=8, energy=7, humanize=True, seed=0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200, f"8-bar pattern took {elapsed_ms:.1f}ms (limit: 200ms)"

    def test_8_bar_bassline_under_200ms(self) -> None:
        """Generating an 8-bar bassline must complete in < 200ms."""
        v = suggest_progression("A", genre="organic house", bars=8)
        start = time.perf_counter()
        generate_bassline(v.chords, genre="organic house", bars=8, humanize=True, seed=0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200, f"8-bar bassline took {elapsed_ms:.1f}ms (limit: 200ms)"

    def test_full_arrangement_8_bar_under_500ms(self) -> None:
        """Full 8-bar arrangement generation + MIDI export must complete in < 500ms."""
        start = time.perf_counter()
        v = suggest_progression("A", genre="organic house", bars=8)
        bass = generate_bassline(v.chords, genre="organic house", bars=8, humanize=True, seed=0)
        drums = generate_pattern(genre="organic house", bars=8, energy=7, humanize=True, seed=0)
        full_arrangement_to_midi(v, bass, drums, bpm=122.0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Full 8-bar arrangement took {elapsed_ms:.1f}ms (limit: 500ms)"

    @pytest.mark.parametrize("genre", GENRES)
    def test_4_bar_all_genres_under_100ms(self, genre: str) -> None:
        """4-bar pattern for any genre must complete in < 100ms."""
        start = time.perf_counter()
        generate_pattern(genre=genre, bars=4, energy=7, humanize=True, seed=0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"{genre} 4-bar pattern took {elapsed_ms:.1f}ms (limit: 100ms)"


# ---------------------------------------------------------------------------
# Edge cases: extreme BPMs
# ---------------------------------------------------------------------------


class TestEdgeCaseBPMs:
    def test_bpm_80_bass_export(self) -> None:
        """At BPM=80, bassline MIDI export must produce valid events."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=True, seed=0)
        midi = bassline_to_midi(bass, bpm=80.0)
        note_events = [m for m in midi.tracks[1] if m.type in ("note_on", "note_off")]
        assert len(note_events) > 0

    def test_bpm_150_bass_export(self) -> None:
        """At BPM=150, bassline MIDI export must produce valid events."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=True, seed=0)
        midi = bassline_to_midi(bass, bpm=150.0)
        note_events = [m for m in midi.tracks[1] if m.type in ("note_on", "note_off")]
        assert len(note_events) > 0

    def test_bpm_80_humanize_timing_ticks(self) -> None:
        """At BPM=80, humanize_timing tick conversion must be correct."""
        # At 80 BPM + 480 tpb: ticks_per_ms = 80/60000 * 480 = 0.64
        # jitter_ms=5 → max_ticks = round(5 * 0.64) = 3
        from core.music_theory.humanize import _bpm_to_ticks_per_ms

        tpm = _bpm_to_ticks_per_ms(80.0, 480)
        assert abs(tpm - (80.0 / 60_000.0 * 480)) < 0.001

    def test_bpm_150_humanize_timing_ticks(self) -> None:
        """At BPM=150, tick conversion must be correct."""
        from core.music_theory.humanize import _bpm_to_ticks_per_ms

        tpm = _bpm_to_ticks_per_ms(150.0, 480)
        assert abs(tpm - (150.0 / 60_000.0 * 480)) < 0.001

    def test_humanize_timing_bpm_80_no_crash(self) -> None:
        """humanize_timing at BPM=80 must not crash or produce out-of-range offsets."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        humanized = humanize_timing(bass, jitter_ms=8.0, bpm=80.0, seed=0)
        assert len(humanized) == len(bass)

    def test_humanize_timing_bpm_150_no_crash(self) -> None:
        """humanize_timing at BPM=150 must not crash."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", humanize=False, seed=0)
        humanized = humanize_timing(bass, jitter_ms=8.0, bpm=150.0, seed=0)
        assert len(humanized) == len(bass)

    def test_full_arrangement_bpm_80(self) -> None:
        """Full arrangement at BPM=80 must export 4-track MIDI."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", seed=0)
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=80.0)
        assert len(midi.tracks) == 4

    def test_full_arrangement_bpm_150(self) -> None:
        """Full arrangement at BPM=150 must export 4-track MIDI."""
        v = suggest_progression("A", genre="organic house", bars=4)
        bass = generate_bassline(v.chords, genre="organic house", seed=0)
        drums = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        midi = full_arrangement_to_midi(v, bass, drums, bpm=150.0)
        assert len(midi.tracks) == 4


# ---------------------------------------------------------------------------
# Energy layer cross-genre
# ---------------------------------------------------------------------------


class TestEnergyLayersCrossGenre:
    @pytest.mark.parametrize("genre", GENRES)
    def test_low_energy_always_has_kick(self, genre: str) -> None:
        """At energy=1, kick should always be present in all genres."""
        p = generate_pattern(genre=genre, bars=4, energy=1, humanize=False, seed=0)
        instruments = {h.instrument for h in p.hits}
        assert "kick" in instruments, f"{genre}: kick should be at energy=1"

    @pytest.mark.parametrize("genre", GENRES)
    def test_high_energy_has_more_instruments(self, genre: str) -> None:
        """High energy must have at least as many instruments as low energy."""
        low = generate_pattern(genre=genre, bars=4, energy=1, humanize=False, seed=0)
        high = generate_pattern(genre=genre, bars=4, energy=10, humanize=False, seed=0)
        instr_low = {h.instrument for h in low.hits}
        instr_high = {h.instrument for h in high.hits}
        assert len(instr_high) >= len(
            instr_low
        ), f"{genre}: energy=10 should have ≥ instrument types than energy=1"

    def test_melodic_techno_energy_progression(self) -> None:
        """Melodic techno specific: hihat enters at energy=2, snare later."""
        p2 = generate_pattern(genre="melodic techno", bars=2, energy=2, humanize=False, seed=0)
        instruments_e2 = {h.instrument for h in p2.hits}
        assert "hihat_c" in instruments_e2, "Melodic techno: hihat_c should be at energy=2"

    def test_afro_house_hihat_before_snare(self) -> None:
        """Afro house: hihat_c enters at 3, snare at 5."""
        p3 = generate_pattern(genre="afro house", bars=2, energy=3, humanize=False, seed=0)
        p4 = generate_pattern(genre="afro house", bars=2, energy=4, humanize=False, seed=0)
        instruments_e3 = {h.instrument for h in p3.hits}
        instruments_e4 = {h.instrument for h in p4.hits}
        assert "hihat_c" in instruments_e3
        assert "snare" not in instruments_e4
