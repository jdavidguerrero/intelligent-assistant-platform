"""
core/music_theory/harmony.py — Melody harmonization engine.

melody_to_chords() is the main algorithm:
    1. Segment notes by bar boundaries
    2. Extract pitch classes per segment
    3. Match each segment to diatonic chords (highest overlap score)
    4. Apply genre template preferences (reorder/weight candidates)
    5. Return a VoicingResult with the winning chord per bar

YAML Genre Templates
--------------------
Located in core/music_theory/templates/<genre>.yaml.
Loaded lazily on first call (module-level cache).
Templates encode genre-specific chord degree sequences and voicing styles.

Design decisions:
    - melody_to_chords() is pure (no I/O, no random) — templates are loaded
      once and cached as frozen dicts.  pyyaml is a stdlib-like dependency
      that only does parsing — no network, no FS writes.
    - The function never raises on partial melody data; empty or ambiguous
      bars fall back to the tonic chord (degree 0).
    - Pitch class overlap scoring: count how many melody pitch classes are
      contained in the chord's pitch classes.  Ties broken by degree preference
      from the genre template (lower index = higher preference).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from core.music_theory.scales import get_diatonic_chords
from core.music_theory.types import Chord, VoicingResult

# ---------------------------------------------------------------------------
# YAML loading — lazy, cached, pure after first load
# ---------------------------------------------------------------------------

_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"

# Canonical genre name → slug used as filename
_GENRE_SLUGS: dict[str, str] = {
    "organic house": "organic_house",
    "deep house": "deep_house",
    "melodic techno": "melodic_techno",
    "progressive house": "progressive_house",
    "afro house": "afro_house",
}


@functools.cache
def _load_template(genre: str) -> dict[str, Any]:
    """Load and cache a YAML genre template by genre name.

    Args:
        genre: Genre name, e.g. "organic house"

    Returns:
        Parsed YAML dict

    Raises:
        ValueError: If genre is unknown or template file is missing
    """
    try:
        import yaml  # pyyaml — optional dependency
    except ImportError as exc:
        raise ImportError(
            "pyyaml is required for genre templates. " "Install with: pip install pyyaml"
        ) from exc

    slug = _GENRE_SLUGS.get(genre.lower())
    if slug is None:
        available = sorted(_GENRE_SLUGS)
        raise ValueError(f"Unknown genre {genre!r}. Available: {available}")

    template_path = _TEMPLATES_DIR / f"{slug}.yaml"
    if not template_path.exists():
        raise ValueError(f"Template file not found: {template_path}")

    with template_path.open() as fh:
        data = yaml.safe_load(fh)

    return data  # type: ignore[return-value]


def available_genres() -> list[str]:
    """Return the list of available genre template names."""
    return sorted(_GENRE_SLUGS)


# ---------------------------------------------------------------------------
# Pitch-class overlap scoring
# ---------------------------------------------------------------------------


def _overlap_score(
    melody_pcs: frozenset[int],
    chord: Chord,
) -> int:
    """Count how many melody pitch classes are in the chord's pitch classes.

    Args:
        melody_pcs: Set of pitch classes from melody notes in a segment
        chord:      Diatonic Chord to score against

    Returns:
        Number of overlapping pitch classes (0 to len(melody_pcs))
    """
    if not melody_pcs:
        return 0
    chord_pcs = frozenset(p % 12 for p in chord.midi_notes)
    return len(melody_pcs & chord_pcs)


def _best_chord_for_segment(
    melody_pcs: frozenset[int],
    diatonic_chords: tuple[Chord, ...],
    preferred_degrees: list[int],
) -> Chord:
    """Select the best-matching chord for a set of melody pitch classes.

    Scoring:
        - Primary: pitch class overlap count (higher = better)
        - Tiebreak: position in preferred_degrees (lower index = better)
        - Final fallback: tonic (degree 0)

    Args:
        melody_pcs:       Pitch classes from melody in this bar
        diatonic_chords:  All 7 diatonic chords for the key
        preferred_degrees: Ordered list of degree preferences from genre template

    Returns:
        Best matching Chord
    """
    if not melody_pcs:
        # No melody — return tonic
        return diatonic_chords[0]

    # Build preference rank: degree → rank (lower = more preferred)
    degree_rank: dict[int, int] = {d: i for i, d in enumerate(preferred_degrees)}
    max_rank = len(preferred_degrees)

    best_chord = diatonic_chords[0]
    best_score = -1
    best_rank = max_rank

    for chord in diatonic_chords:
        score = _overlap_score(melody_pcs, chord)
        rank = degree_rank.get(chord.degree, max_rank)
        if score > best_score or (score == best_score and rank < best_rank):
            best_score = score
            best_rank = rank
            best_chord = chord

    return best_chord


# ---------------------------------------------------------------------------
# Bar segmentation
# ---------------------------------------------------------------------------


def _segment_notes_by_bar(
    notes: list[Any],  # list[Note] from core.audio.types
    bars: int,
    total_duration_sec: float,
) -> list[frozenset[int]]:
    """Segment note pitch classes into per-bar buckets.

    Args:
        notes:              List of Note objects (onset_sec, pitch_midi)
        bars:               Number of bars to split into
        total_duration_sec: Total duration of the audio segment in seconds

    Returns:
        List of frozensets (one per bar), each containing MIDI pitch classes
        (0–11) of notes that start in that bar.
    """
    if total_duration_sec <= 0 or bars <= 0:
        return [frozenset()] * max(bars, 1)

    bar_duration = total_duration_sec / bars
    buckets: list[set[int]] = [set() for _ in range(bars)]

    for note in notes:
        onset = getattr(note, "onset_sec", 0.0)
        pitch = getattr(note, "pitch_midi", 0)
        bar_idx = min(int(onset / bar_duration), bars - 1)
        buckets[bar_idx].add(pitch % 12)

    return [frozenset(b) for b in buckets]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def melody_to_chords(
    notes: list[Any],
    *,
    key_root: str,
    key_mode: str = "natural minor",
    genre: str = "organic house",
    bars: int = 4,
    total_duration_sec: float | None = None,
    voicing: str | None = None,
) -> VoicingResult:
    """Harmonize a melody by matching notes to diatonic chords.

    Algorithm:
        1. Load genre template (cached after first call)
        2. Build diatonic chord set for (key_root, key_mode, voicing)
        3. Segment melody notes by bar boundaries
        4. For each bar: score diatonic chords by pitch-class overlap,
           then apply genre degree preferences as a tiebreaker
        5. Return VoicingResult with one chord per bar

    Args:
        notes:              List of Note objects (from core.audio.melody.detect_melody)
                            Each must have .onset_sec and .pitch_midi attributes.
                            May be empty — empty bars fall back to tonic.
        key_root:           Tonal centre, e.g. "A", "C#"
        key_mode:           Scale mode, e.g. "natural minor", "dorian"
        genre:              Genre template name. See available_genres().
        bars:               Number of bars in the progression (default 4)
        total_duration_sec: Total audio duration in seconds.
                            If None, inferred from the last note offset.
        voicing:            Override voicing style ("triads", "seventh", "extended").
                            If None, uses the genre template default.

    Returns:
        VoicingResult with one Chord per bar.

    Raises:
        ValueError: If key_root, key_mode, genre, or bars is invalid.

    Examples:
        >>> result = melody_to_chords(notes, key_root="A", genre="organic house")
        >>> result.chord_names
        ('Am7', 'Fmaj7', 'C', 'Gm7')
        >>> result.progression_label
        'i - VI - III - VII'
    """
    if bars <= 0:
        raise ValueError(f"bars must be > 0, got {bars}")

    # Load genre template
    template = _load_template(genre)
    template_voicing: str = voicing or template.get("voicing", "triads")

    # Build diatonic chords
    diatonic = get_diatonic_chords(key_root, key_mode, voicing=template_voicing)

    # Extract preferred degree order from all template progressions
    # (weighted by their 'weight' field)
    preferred_degrees = _extract_preferred_degrees(template)

    # Determine total duration for bar segmentation
    if total_duration_sec is None or total_duration_sec <= 0:
        if notes:
            last = max(
                getattr(n, "onset_sec", 0.0) + getattr(n, "duration_sec", 0.0) for n in notes
            )
            total_duration_sec = max(last, 1.0)
        else:
            total_duration_sec = float(bars * 2)  # 2 seconds per bar as fallback

    # Segment notes into per-bar pitch class sets
    bar_pcs = _segment_notes_by_bar(notes, bars, total_duration_sec)

    # Score each bar and select best chord
    selected: list[Chord] = []
    for _bar_idx, pcs in enumerate(bar_pcs):
        chord = _best_chord_for_segment(pcs, diatonic, preferred_degrees)
        selected.append(chord)

    roman_labels = tuple(c.roman for c in selected)

    return VoicingResult(
        chords=tuple(selected),
        key_root=key_root,
        key_mode=key_mode,
        genre=genre,
        bars=bars,
        roman_labels=roman_labels,
    )


# ---------------------------------------------------------------------------
# Mood → degree bias weights
# ---------------------------------------------------------------------------

# Maps mood tags to preferred scale degrees.
# Degrees with higher weight are more likely to be chosen when the mood matches.
# Based on harmonic function theory:
#   - "dark": emphasize minor tonic (0) and subdominant (3)
#   - "euphoric": emphasis on VI (5) and VII (6) for lift
#   - "tense": dominant (4) and leading-tone area (4, 6)
#   - "dreamy": mediant (2) and submediant (5) for ambiguity
#   - "hypnotic": repetition → tonic bias (0)
_MOOD_DEGREE_WEIGHTS: dict[str, dict[int, float]] = {
    "dark": {0: 1.5, 3: 1.3, 6: 1.1, 5: 0.8},
    "euphoric": {5: 1.5, 6: 1.3, 2: 1.1, 0: 0.9},
    "tense": {4: 1.5, 6: 1.3, 3: 1.1, 0: 0.8},
    "dreamy": {2: 1.5, 5: 1.3, 0: 1.1, 3: 0.9},
    "hypnotic": {0: 2.0, 5: 1.2, 3: 1.1, 6: 1.0},
    "neutral": {},  # no bias — pure genre preference
}


def suggest_progression(
    key_root: str,
    *,
    key_mode: str = "natural minor",
    genre: str = "organic house",
    mood: str | None = None,
    bars: int = 4,
    voicing: str | None = None,
) -> VoicingResult:
    """Suggest a chord progression without a melody, using genre templates and mood.

    Unlike melody_to_chords(), this function requires no input notes.
    It selects the highest-weighted progression from the genre template,
    optionally biased by a mood tag.

    Algorithm:
        1. Load genre template
        2. Score each progression by:
           a. Template weight
           b. Mood-degree affinity (if mood provided)
        3. Pick the highest-scoring progression
        4. Cycle its degree sequence to fill `bars` bars
        5. Return a VoicingResult

    Args:
        key_root:  Tonal centre, e.g. "A", "C#", "Bb"
        key_mode:  Scale mode, e.g. "natural minor", "dorian"
        genre:     Genre template name. See available_genres().
        mood:      Optional mood bias: "dark", "euphoric", "tense",
                   "dreamy", "hypnotic", "neutral". If None, uses pure
                   genre weights.
        bars:      Number of bars in the output progression.
        voicing:   Voicing override. None → use template default.

    Returns:
        VoicingResult with one Chord per bar.

    Raises:
        ValueError: If genre, key_root, key_mode, or bars is invalid.
        ValueError: If mood is not a recognized mood tag.

    Examples:
        >>> result = suggest_progression("A", genre="organic house", mood="dark")
        >>> result.progression_label
        'i - VI - III - VII'
        >>> result.key_root
        'A'
    """
    if bars <= 0:
        raise ValueError(f"bars must be > 0, got {bars}")

    valid_moods = set(_MOOD_DEGREE_WEIGHTS) | {None}
    if mood not in valid_moods:
        raise ValueError(f"Unknown mood {mood!r}. Valid: {sorted(m for m in _MOOD_DEGREE_WEIGHTS)}")

    template = _load_template(genre)
    template_voicing: str = voicing or template.get("voicing", "triads")
    diatonic = get_diatonic_chords(key_root, key_mode, voicing=template_voicing)

    # Score progressions from the template
    mood_weights = _MOOD_DEGREE_WEIGHTS.get(mood or "neutral", {})
    progressions = template.get("progressions", [])

    if not progressions:
        # Fallback: tonic repeated
        best_degrees = [0] * bars
    else:
        # Score each progression: template_weight × avg(mood_affinity per degree)
        def _prog_score(prog: dict[str, Any]) -> float:
            w = float(prog.get("weight", 1))
            degrees = prog.get("degrees", [0])
            if not degrees:
                return w
            mood_bonus = sum(mood_weights.get(d, 1.0) for d in degrees) / len(degrees)
            return w * mood_bonus

        best_prog = max(progressions, key=_prog_score)
        best_degrees = best_prog.get("degrees", [0])

    # Cycle the degree sequence to fill `bars` bars
    degree_map = {c.degree: c for c in diatonic}
    selected: list = []
    for i in range(bars):
        degree = best_degrees[i % len(best_degrees)]
        chord = degree_map.get(degree, diatonic[0])
        selected.append(chord)

    roman_labels = tuple(c.roman for c in selected)

    return VoicingResult(
        chords=tuple(selected),
        key_root=key_root,
        key_mode=key_mode,
        genre=genre,
        bars=bars,
        roman_labels=roman_labels,
    )


def _extract_preferred_degrees(template: dict[str, Any]) -> list[int]:
    """Extract a weighted, deduplicated degree preference list from a template.

    Progressions with higher weight contribute more to the preference ranking.
    Degrees that appear in more progressions and at earlier positions are preferred.

    Args:
        template: Parsed YAML template dict

    Returns:
        List of scale degrees in preference order (most preferred first)
    """
    progressions = template.get("progressions", [])
    if not progressions:
        return list(range(7))  # all degrees equally weighted

    # Score: degree → weighted sum of (weight × inverse position)
    degree_scores: dict[int, float] = {}
    for prog in progressions:
        degrees = prog.get("degrees", [])
        weight = prog.get("weight", 1)
        for pos, degree in enumerate(degrees):
            # Earlier position in a progression = higher preference
            position_bonus = 1.0 / (pos + 1)
            degree_scores[degree] = degree_scores.get(degree, 0.0) + weight * position_bonus

    # Sort by score descending, then by degree index ascending as tiebreak
    sorted_degrees = sorted(
        degree_scores.keys(),
        key=lambda d: (-degree_scores[d], d),
    )
    return sorted_degrees
