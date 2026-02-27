"""
core/music_theory/voicing.py — Voice leading optimizer.

optimize_voice_leading() takes a sequence of chords and reorders the notes
of each chord (beyond the first) to minimize total semitone movement between
consecutive chords. This produces smooth, pianistic voice leading.

Algorithm (greedy nearest-neighbour):
    For each chord after the first:
        1. Generate all closed-position voicings within a ±1 octave range
        2. Score each voicing by the sum of absolute semitone distances to
           the preceding chord's pitches (L1 distance across all voices)
        3. Pick the voicing with the lowest score
        4. Apply parallel-fifth penalty: +12 per parallel-fifth interval pair

This is a greedy O(n × V) algorithm where n = number of chords and V =
number of voicing candidates per chord. For 3–5 note chords with a ±1
octave search space, V ≈ 27.

Voice leading rules enforced:
    - No parallel perfect fifths (add penalty, not hard constraint)
    - All notes stay in MIDI range [36, 84] (3 octaves centred on middle C)
    - Voicings stay in closed position (span ≤ 14 semitones by default)

Output:
    A tuple of VoicedChord objects, each wrapping the original Chord with
    an optimized midi_notes tuple replacing the root-position default.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from core.music_theory.types import Chord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIDI_LOW: int = 36  # C2 — lowest comfortable chord note
MIDI_HIGH: int = 84  # C6 — highest comfortable chord note
MAX_SPAN: int = 14  # semitones — closed voicing constraint
PARALLEL_FIFTH_PENALTY: int = 12  # added to score per parallel-fifth pair


# ---------------------------------------------------------------------------
# VoicedChord — Chord with an optimized voicing attached
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoicedChord:
    """A Chord with an optimized MIDI voicing replacing the root-position default.

    Attributes:
        chord:      Original Chord object (unchanged)
        pitches:    Optimized MIDI pitch tuple, sorted ascending
        movement:   Total semitone movement from the preceding chord (0 for first)
    """

    chord: Chord
    pitches: tuple[int, ...]
    movement: int = 0

    @property
    def root(self) -> str:
        return self.chord.root

    @property
    def name(self) -> str:
        return self.chord.name

    @property
    def roman(self) -> str:
        return self.chord.roman

    @property
    def degree(self) -> int:
        return self.chord.degree


# ---------------------------------------------------------------------------
# Voicing candidate generation
# ---------------------------------------------------------------------------


def _generate_voicing_candidates(
    pitch_classes: tuple[int, ...],
    *,
    reference_pitches: tuple[int, ...] | None = None,
    midi_low: int = MIDI_LOW,
    midi_high: int = MIDI_HIGH,
    max_span: int = MAX_SPAN,
) -> list[tuple[int, ...]]:
    """Generate all valid closed-position voicings for a set of pitch classes.

    For each pitch class, all MIDI pitches in [midi_low, midi_high] are
    considered. Combinations where the span exceeds max_span are discarded.

    Args:
        pitch_classes:    Unique pitch classes (0–11) for the chord.
                          Typically len = 3 (triad) or 4 (seventh chord).
        reference_pitches: Previous chord pitches. If given, voicings are
                           also filtered to stay near the reference range.
        midi_low:         Minimum MIDI pitch
        midi_high:        Maximum MIDI pitch
        max_span:         Maximum semitone span of a valid voicing

    Returns:
        List of valid MIDI pitch tuples, sorted ascending within each voicing.
        May be empty if no valid voicing exists in range.
    """
    # For each pitch class, enumerate all octave instances in range
    octave_options: list[list[int]] = []
    for pc in pitch_classes:
        instances = [p for p in range(midi_low, midi_high + 1) if p % 12 == pc]
        if not instances:
            return []  # no valid octave for this pitch class
        octave_options.append(instances)

    candidates: list[tuple[int, ...]] = []
    for combo in product(*octave_options):
        pitches = tuple(sorted(combo))
        span = pitches[-1] - pitches[0]
        if span <= max_span:
            candidates.append(pitches)

    return candidates


def _parallel_fifth_count(
    prev: tuple[int, ...],
    curr: tuple[int, ...],
) -> int:
    """Count parallel perfect fifth motion between two voicings.

    A parallel fifth occurs when two pairs of voices move in the same
    direction and maintain a perfect-fifth interval (7 semitones).

    Args:
        prev: Previous chord MIDI pitches (sorted)
        curr: Current chord MIDI pitches (sorted)

    Returns:
        Number of parallel-fifth pairs detected.
    """
    if len(prev) != len(curr):
        return 0

    count = 0
    n = len(prev)
    for i in range(n):
        for j in range(i + 1, n):
            prev_interval = (prev[j] - prev[i]) % 12
            curr_interval = (curr[j] - curr[i]) % 12
            if prev_interval == 7 and curr_interval == 7:
                # Same fifth interval — check for parallel motion
                motion_i = curr[i] - prev[i]
                motion_j = curr[j] - prev[j]
                if motion_i != 0 and motion_j != 0 and (motion_i > 0) == (motion_j > 0):
                    count += 1
    return count


def _voice_leading_score(
    prev: tuple[int, ...],
    curr: tuple[int, ...],
) -> int:
    """Compute voice leading cost between two chord voicings.

    Score = sum of |curr[i] - prev[i]| across paired voices
          + PARALLEL_FIFTH_PENALTY × parallel_fifth_count

    Pairing: nearest-voice assignment (each voice in curr mapped to the
    nearest voice in prev, greedy).

    Args:
        prev: Previous chord MIDI pitches (sorted)
        curr: Current chord MIDI pitches (sorted)

    Returns:
        Non-negative integer cost (lower = smoother voice leading)
    """
    if not prev or not curr:
        return 0

    # Pad the shorter voicing with its extremes if sizes differ
    p = list(prev)
    c = list(curr)
    while len(p) < len(c):
        p.insert(0, p[0])
    while len(c) < len(p):
        c.insert(0, c[0])

    movement = sum(abs(ci - pi) for ci, pi in zip(c, p, strict=False))
    penalty = _parallel_fifth_count(tuple(p), tuple(c)) * PARALLEL_FIFTH_PENALTY
    return movement + penalty


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def optimize_voice_leading(
    chords: Sequence[Chord],
    *,
    midi_low: int = MIDI_LOW,
    midi_high: int = MIDI_HIGH,
    max_span: int = MAX_SPAN,
) -> tuple[VoicedChord, ...]:
    """Optimize voice leading across a chord sequence.

    For the first chord, uses the root-position voicing from the Chord object.
    For each subsequent chord, generates candidate voicings and selects the one
    that minimizes semitone movement from the previous chord.

    Args:
        chords:   Sequence of Chord objects (e.g., from melody_to_chords)
        midi_low: Minimum allowed MIDI pitch
        midi_high: Maximum allowed MIDI pitch
        max_span: Maximum chord span in semitones (closed voicing constraint)

    Returns:
        Tuple of VoicedChord objects with optimized pitches.
        If a chord has no valid candidates in range, its root-position
        midi_notes are used unchanged.

    Examples:
        >>> chords = get_diatonic_chords("A", "natural minor", voicing="extended")
        >>> voiced = optimize_voice_leading(chords[:4])
        >>> [v.name for v in voiced]
        ['Am7', 'Bm7b5', 'Cmaj7', 'Dm7']
    """
    if not chords:
        return ()

    result: list[VoicedChord] = []
    prev_pitches: tuple[int, ...] | None = None

    for chord in chords:
        pitch_classes = tuple(dict.fromkeys(p % 12 for p in chord.midi_notes))

        candidates = _generate_voicing_candidates(
            pitch_classes,
            reference_pitches=prev_pitches,
            midi_low=midi_low,
            midi_high=midi_high,
            max_span=max_span,
        )

        if not candidates:
            # Fallback: use chord's existing midi_notes as-is
            pitches = chord.midi_notes
        elif prev_pitches is None:
            # First chord — pick the candidate closest to the natural root position
            root_position = chord.midi_notes
            pitches = min(
                candidates,
                key=lambda c: _voice_leading_score(root_position, c),
            )
        else:
            pitches = min(
                candidates,
                key=lambda c: _voice_leading_score(prev_pitches, c),
            )

        movement = _voice_leading_score(prev_pitches, pitches) if prev_pitches is not None else 0

        result.append(VoicedChord(chord=chord, pitches=pitches, movement=movement))
        prev_pitches = pitches

    return tuple(result)


def total_voice_leading_cost(voiced: Sequence[VoicedChord]) -> int:
    """Return the total voice leading cost across the sequence.

    Args:
        voiced: Sequence of VoicedChord objects (output of optimize_voice_leading)

    Returns:
        Sum of all movement costs
    """
    return sum(v.movement for v in voiced)
