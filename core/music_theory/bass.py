"""
core/music_theory/bass.py — Bassline generator.

generate_bassline() takes a chord sequence and produces a rhythmic bass line
locked to a 16-step (16th-note) grid. The bass follows the root of each chord
and applies genre-specific rhythmic patterns loaded from the YAML templates.

Algorithm:
    1. Load genre template (cached via _load_template in harmony.py)
    2. Select bass pattern by style ("root", "walk", "sub", "driving", "minimal")
    3. For each bar (one chord per bar):
       a. Compute root MIDI pitch at base_octave
       b. Transpose each template note: pitch = root_midi + semitone_offset
       c. Apply velocity humanization with seeded PRNG (±8 by default)
    4. Optionally add slide/approach notes before chord changes (slides=True)
    5. Return tuple of BassNote objects in (bar, step) order

Bass styles (all YAML templates define these):
    root    — root-focused, quarter-note hits, stable bass foundation
    walk    — walking jazz-style movement through chord tones
    sub     — ultra-deep sustained root (base_octave=1), pure sub bass
    driving — eighth-note root pulse, high energy driving feel
    minimal — single hit per bar on beat 1, maximum space

Slides:
    When slides=True, a short approach note is added 2 steps before each
    chord change (at the previous chord's root). This simulates the "slide"
    that bass players use to connect chord changes — a defining technique
    in house and deep house production.

Design decisions:
    - Pure: no I/O, no global mutable state
    - Deterministic: seeded random.Random(seed) for repeatable humanization
    - Template-driven: all rhythm lives in YAML — code is generic
    - BassNote uses a 16-step grid (step 0-15, 16th-note resolution)
    - base_octave 2 → root of A = MIDI 45 (A2), root of C = MIDI 36 (C2)
    - base_octave 1 → A = MIDI 33 (sub bass register, ~55 Hz)
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from core.music_theory.harmony import _load_template
from core.music_theory.scales import NOTE_NAMES, normalize_note
from core.music_theory.types import BassNote, Chord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VELOCITY_HUMANIZE_RANGE: int = 8  # ±N velocity units per note
_DEFAULT_BASE_OCTAVE: int = 2  # C2 = MIDI 36; A2 = MIDI 45
_SLIDE_STEP: int = 14           # grid position for approach/slide note (2 steps before bar end)
_SLIDE_DURATION: int = 2        # duration of slide note in 16th-note steps
_SLIDE_VELOCITY_RATIO: float = 0.70  # slide note velocity = 70% of bar's loudest note


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_root_midi(root: str, octave: int) -> int:
    """Compute the MIDI pitch for a note name at a given octave.

    MIDI octave numbering: octave 2 starts at MIDI 36 (C2).
    Formula: midi = (octave + 1) * 12 + pitch_class

    Args:
        root:   Note name, e.g. "A", "C#", "Bb"
        octave: MIDI octave number (2 = bass register, 4 = middle)

    Returns:
        MIDI pitch number, clamped to [0, 127].

    Examples:
        >>> _get_root_midi("A", 2)
        45
        >>> _get_root_midi("C", 2)
        36
    """
    pc = NOTE_NAMES.index(normalize_note(root))
    midi = (octave + 1) * 12 + pc
    return max(0, min(127, midi))


def _select_bass_pattern(
    template: dict[str, Any],
    style: str,
) -> dict[str, Any]:
    """Select a bass pattern from the template by style name.

    Falls back to the first available pattern if the requested style
    is not found in the template.

    Args:
        template: Parsed YAML template dict with a 'bass_patterns' key.
        style:    Pattern style, e.g. "root", "walk".

    Returns:
        Bass pattern dict with 'notes' and 'base_octave' keys.

    Raises:
        ValueError: If the template has no bass_patterns at all.
    """
    patterns: list[dict[str, Any]] = template.get("bass_patterns", [])
    if not patterns:
        genre = template.get("genre", "unknown")
        raise ValueError(
            f"Genre template '{genre}' has no bass_patterns defined. "
            "Add a bass_patterns section to the YAML template."
        )

    for p in patterns:
        if p.get("style") == style:
            return p

    # Fallback: first pattern (most common style)
    return patterns[0]


def _add_slides(
    notes: list[BassNote],
    chords: Sequence[Chord],
    *,
    bars: int,
    base_octave: int,
) -> list[BassNote]:
    """Add slide/approach notes before chord changes.

    Places a short BassNote at the previous chord's root, 2 steps before each
    chord change (at step 14 of the bar). This simulates the characteristic
    bass "slide" technique in house music — an approach tone that leads the
    listener's ear into the new chord.

    A slide note is only added when:
        1. The chord root changes (same root = no slide needed)
        2. Step 14 of the previous bar is not already occupied by another note

    Args:
        notes:       Existing bass notes (list, will not be modified in-place).
        chords:      Chord sequence (same as used to generate notes).
        bars:        Total bar count.
        base_octave: Octave for root MIDI pitch computation.

    Returns:
        Sorted list of notes (original + slide notes) by (bar, step).
    """
    existing_positions: set[tuple[int, int]] = {(n.bar, n.step) for n in notes}
    slide_notes: list[BassNote] = []

    for bar_idx in range(1, bars):
        prev_chord = chords[(bar_idx - 1) % len(chords)]
        curr_chord = chords[bar_idx % len(chords)]

        if prev_chord.root == curr_chord.root:
            continue  # Same root — no slide needed

        if (bar_idx - 1, _SLIDE_STEP) in existing_positions:
            continue  # Step already occupied — avoid overlap

        prev_root_midi = _get_root_midi(prev_chord.root, base_octave)

        # Reference velocity from the loudest note in the previous bar
        bar_notes = [n for n in notes if n.bar == bar_idx - 1]
        base_vel = max((n.velocity for n in bar_notes), default=80)
        slide_vel = max(1, round(base_vel * _SLIDE_VELOCITY_RATIO))

        slide_notes.append(
            BassNote(
                pitch_midi=prev_root_midi,
                step=_SLIDE_STEP,
                duration_steps=_SLIDE_DURATION,
                velocity=slide_vel,
                bar=bar_idx - 1,
            )
        )

    all_notes = notes + slide_notes
    all_notes.sort(key=lambda n: (n.bar, n.step))
    return all_notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_bassline(
    chords: Sequence[Chord],
    *,
    bpm: float = 120.0,
    genre: str = "organic house",
    bars: int | None = None,
    style: str = "root",
    humanize: bool = True,
    slides: bool = False,
    seed: int | None = None,
) -> tuple[BassNote, ...]:
    """Generate a bass line from a chord sequence using a genre template.

    Each chord maps to one bar. Template notes are transposed to the chord
    root each bar, producing a melodically correct bass line that follows
    the harmonic rhythm.

    Args:
        chords:    Chord sequence (one chord per bar). If bars > len(chords),
                   the sequence wraps (chords[bar_idx % len(chords)]).
        bpm:       Tempo in BPM — informational, not used in this function
                   but documented for caller context.
        genre:     Genre template name. See available_genres().
        bars:      Total number of bars to generate. Defaults to len(chords).
        style:     Bass pattern style. Available styles (all genres):
                   "root"    — root-focused, stable quarter-note hits
                   "walk"    — walking movement through chord tones
                   "sub"     — ultra-deep sustained root (base_octave 1)
                   "driving" — eighth-note root pulse, high energy
                   "minimal" — single hit per bar on beat 1
        humanize:  If True, applies velocity variation ±8 per note.
                   Recommended for realistic, non-mechanical bass lines.
        slides:    If True, adds approach/slide notes before chord changes.
                   A short note at the previous chord's root is placed 2 steps
                   before the bar boundary, simulating the bass "slide" technique.
                   Only added when the chord root changes and the position is free.
        seed:      Random seed for humanization. Set for reproducibility.
                   None = non-deterministic (different every call).

    Returns:
        Tuple of BassNote objects sorted by (bar, step).
        Empty tuple if chords is empty.

    Raises:
        ValueError: If genre is unknown (propagated from _load_template).
        ValueError: If the genre template has no bass_patterns section.

    Examples:
        >>> from core.music_theory.scales import get_diatonic_chords
        >>> chords = get_diatonic_chords("A", "natural minor")[:4]
        >>> notes = generate_bassline(chords, genre="organic house", seed=42)
        >>> notes[0].pitch_midi  # A2 = MIDI 45
        45
        >>> notes_with_slides = generate_bassline(chords, slides=True, seed=42)
        >>> len(notes_with_slides) >= len(notes)  # slides add notes before chord changes
        True
    """
    if not chords:
        return ()

    template = _load_template(genre)
    pattern = _select_bass_pattern(template, style)

    base_octave: int = int(pattern.get("base_octave", _DEFAULT_BASE_OCTAVE))
    note_templates: list[list[int]] = pattern.get("notes", [])

    n_bars = bars if bars is not None else len(chords)
    rng = random.Random(seed)
    result: list[BassNote] = []

    for bar_idx in range(n_bars):
        chord = chords[bar_idx % len(chords)]
        root_midi = _get_root_midi(chord.root, base_octave)

        for note_def in note_templates:
            if len(note_def) < 4:
                continue  # skip malformed entries

            step: int = int(note_def[0])
            semitone_offset: int = int(note_def[1])
            duration_steps: int = int(note_def[2])
            base_velocity: int = int(note_def[3])

            pitch = max(0, min(127, root_midi + semitone_offset))

            if humanize:
                delta = rng.randint(-_VELOCITY_HUMANIZE_RANGE, _VELOCITY_HUMANIZE_RANGE)
                velocity = max(1, min(127, base_velocity + delta))
            else:
                velocity = max(1, min(127, base_velocity))

            result.append(
                BassNote(
                    pitch_midi=pitch,
                    step=step,
                    duration_steps=duration_steps,
                    velocity=velocity,
                    bar=bar_idx,
                )
            )

    if slides and n_bars > 1:
        result = _add_slides(result, chords, bars=n_bars, base_octave=base_octave)

    return tuple(result)
