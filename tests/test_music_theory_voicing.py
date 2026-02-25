"""
Tests for core/music_theory/voicing.py — voice leading optimizer.

Validates:
    - _generate_voicing_candidates: span constraint, range constraint
    - _parallel_fifth_count: detection logic
    - _voice_leading_score: semitone counting + penalty
    - optimize_voice_leading: first chord anchor, movement minimization
    - total_voice_leading_cost: summation
    - Edge cases: empty input, single chord, mismatched voicing sizes
"""

from core.music_theory.scales import get_diatonic_chords
from core.music_theory.voicing import (
    VoicedChord,
    _generate_voicing_candidates,
    _parallel_fifth_count,
    _voice_leading_score,
    optimize_voice_leading,
    total_voice_leading_cost,
)

# ---------------------------------------------------------------------------
# _generate_voicing_candidates
# ---------------------------------------------------------------------------


class TestGenerateVoicingCandidates:
    def test_triad_has_candidates(self):
        # A minor: pcs 9, 0, 4 (A, C, E)
        candidates = _generate_voicing_candidates((9, 0, 4))
        assert len(candidates) > 0

    def test_all_candidates_within_range(self):
        candidates = _generate_voicing_candidates((0, 4, 7), midi_low=48, midi_high=72)
        for combo in candidates:
            for p in combo:
                assert 48 <= p <= 72

    def test_span_constraint_respected(self):
        candidates = _generate_voicing_candidates((0, 4, 7), max_span=12)
        for combo in candidates:
            assert combo[-1] - combo[0] <= 12

    def test_candidates_are_sorted_ascending(self):
        candidates = _generate_voicing_candidates((9, 0, 4))
        for combo in candidates:
            assert list(combo) == sorted(combo)

    def test_pitch_classes_correct(self):
        candidates = _generate_voicing_candidates((0, 4, 7))  # C major pcs
        for combo in candidates:
            pcs = tuple(p % 12 for p in combo)
            # All 3 pcs present (0, 4, 7 in some order)
            assert set(pcs) == {0, 4, 7}

    def test_empty_when_no_valid_octave(self):
        # pc=0 (C) can always be placed, but very tight range might fail
        # If midi_low > midi_high, no candidates
        candidates = _generate_voicing_candidates((0, 4, 7), midi_low=80, midi_high=60)
        assert candidates == []


# ---------------------------------------------------------------------------
# _parallel_fifth_count
# ---------------------------------------------------------------------------


class TestParallelFifthCount:
    def test_no_parallel_fifths(self):
        # (60,63) → (61,64): minor-third intervals throughout, no fifths
        count = _parallel_fifth_count((60, 63), (61, 64))
        assert count == 0

    def test_parallel_fifths_detected(self):
        # C→G parallel: (60, 67) → (62, 69) = both move up 2, maintain 5th
        count = _parallel_fifth_count((60, 67), (62, 69))
        assert count == 1

    def test_contrary_motion_no_penalty(self):
        # 60→62 (+2), 67→65 (-2): contrary motion → no parallel fifths
        count = _parallel_fifth_count((60, 67), (62, 65))
        assert count == 0

    def test_mismatched_lengths_returns_zero(self):
        count = _parallel_fifth_count((60, 64, 67), (65, 69))
        assert count == 0


# ---------------------------------------------------------------------------
# _voice_leading_score
# ---------------------------------------------------------------------------


class TestVoiceLeadingScore:
    def test_identical_chords_score_zero(self):
        pitches = (60, 64, 67)
        assert _voice_leading_score(pitches, pitches) == 0

    def test_semitone_movement_counted(self):
        # (60,63)→(61,64): each voice moves 1 semitone, no parallel fifths → total = 2
        score = _voice_leading_score((60, 63), (61, 64))
        assert score == 2

    def test_larger_movement_scores_higher(self):
        small = _voice_leading_score((60, 64, 67), (61, 65, 68))
        large = _voice_leading_score((60, 64, 67), (67, 71, 74))
        assert large > small

    def test_empty_inputs_score_zero(self):
        assert _voice_leading_score((), ()) == 0
        assert _voice_leading_score((60, 64), ()) == 0

    def test_parallel_fifth_adds_penalty(self):
        # Normal movement score with no parallel fifths
        normal = _voice_leading_score((60, 67), (62, 65))  # contrary motion
        # Movement with parallel fifths
        parallel = _voice_leading_score((60, 67), (62, 69))
        # Parallel version should have a higher score due to penalty
        assert parallel > normal


# ---------------------------------------------------------------------------
# optimize_voice_leading
# ---------------------------------------------------------------------------


class TestOptimizeVoiceLeading:
    def test_empty_returns_empty_tuple(self):
        result = optimize_voice_leading([])
        assert result == ()

    def test_single_chord_returns_single_voiced_chord(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading([chords[0]])
        assert len(result) == 1
        assert isinstance(result[0], VoicedChord)

    def test_output_length_matches_input(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading(chords)
        assert len(result) == len(chords)

    def test_all_results_are_voiced_chords(self):
        chords = get_diatonic_chords("C", "major")
        result = optimize_voice_leading(chords)
        for v in result:
            assert isinstance(v, VoicedChord)

    def test_first_chord_movement_is_zero(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading(chords)
        assert result[0].movement == 0

    def test_subsequent_chords_have_nonneg_movement(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading(chords)
        for v in result:
            assert v.movement >= 0

    def test_pitches_are_sorted_ascending(self):
        chords = get_diatonic_chords("C", "major", voicing="extended")
        result = optimize_voice_leading(chords)
        for v in result:
            assert list(v.pitches) == sorted(v.pitches)

    def test_pitches_within_midi_range(self):
        chords = get_diatonic_chords("A", "natural minor", voicing="seventh")
        result = optimize_voice_leading(chords)
        for v in result:
            for p in v.pitches:
                assert 0 <= p <= 127

    def test_pitch_classes_match_original_chord(self):
        """Optimization should not change which notes are in the chord."""
        chords = get_diatonic_chords("C", "major")
        result = optimize_voice_leading(chords)
        for orig, voiced in zip(chords, result, strict=False):
            orig_pcs = frozenset(p % 12 for p in orig.midi_notes)
            opt_pcs = frozenset(p % 12 for p in voiced.pitches)
            assert (
                orig_pcs == opt_pcs
            ), f"Chord {orig.name}: pitch classes changed after optimization"

    def test_chord_name_preserved(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading(chords)
        for orig, voiced in zip(chords, result, strict=False):
            assert voiced.name == orig.name

    def test_total_movement_less_than_root_position(self):
        """Optimized voice leading should have lower total movement than
        always using root position voicings."""
        chords = get_diatonic_chords("C", "major", voicing="extended")

        # Root-position total movement
        root_movement = sum(
            _voice_leading_score(
                tuple(chords[i].midi_notes),
                tuple(chords[i + 1].midi_notes),
            )
            for i in range(len(chords) - 1)
        )

        # Optimized movement
        result = optimize_voice_leading(chords)
        optimized_movement = total_voice_leading_cost(result)

        assert optimized_movement <= root_movement

    def test_custom_midi_range(self):
        chords = get_diatonic_chords("C", "major")
        result = optimize_voice_leading(chords, midi_low=48, midi_high=72)
        for v in result:
            for p in v.pitches:
                assert 48 <= p <= 72

    def test_returns_tuple(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading(chords)
        assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# total_voice_leading_cost
# ---------------------------------------------------------------------------


class TestTotalVoiceLeadingCost:
    def test_empty_sequence_returns_zero(self):
        assert total_voice_leading_cost([]) == 0

    def test_single_chord_returns_zero(self):
        chords = get_diatonic_chords("A", "natural minor")
        result = optimize_voice_leading([chords[0]])
        assert total_voice_leading_cost(result) == 0

    def test_sum_of_movements(self):
        chords = get_diatonic_chords("A", "natural minor")[:4]
        result = optimize_voice_leading(chords)
        expected = sum(v.movement for v in result)
        assert total_voice_leading_cost(result) == expected

    def test_returns_int(self):
        chords = get_diatonic_chords("C", "major")[:3]
        result = optimize_voice_leading(chords)
        cost = total_voice_leading_cost(result)
        assert isinstance(cost, int)
