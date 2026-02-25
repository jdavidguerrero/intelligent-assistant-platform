"""
core/music_theory/bass.py — Bassline generator.

generate_bassline() takes a chord sequence and produces a rhythmic bass line
locked to a 16-step (16th-note) grid. The bass follows the root of each chord
and applies genre-specific rhythmic patterns loaded from the YAML templates.

Algorithm:
    1. Load genre template (cached via _load_template in harmony.py)
    2. Select bass pattern by style ("root" or "walk")
    3. For each bar (one chord per bar):
       a. Compute root MIDI pitch at base_octave
       b. Transpose each template note: pitch = root_midi + semitone_offset
       c. Apply velocity humanization with seeded PRNG (±8 by default)
    4. Return tuple of BassNote objects in (bar, step) order

Design decisions:
    - Pure: no I/O, no global mutable state
    - Deterministic: seeded random.Random(seed) for repeatable humanization
    - Template-driven: all rhythm lives in YAML — code is generic
    - BassNote uses a 16-step grid (step 0-15, 16th-note resolution)
    - base_octave 2 → root of A = MIDI 45 (A2), root of C = MIDI 36 (C2)
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
        style:     Bass pattern style: "root" (root-focused, stable) or
                   "walk" (more movement between chord tones).
        humanize:  If True, applies velocity variation ±8 per note.
                   Recommended for realistic, non-mechanical bass lines.
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
        >>> len(notes)  # 6 notes/bar × 4 bars
        24
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

    return tuple(result)
