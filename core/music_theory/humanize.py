"""
core/music_theory/humanize.py — Timing and velocity humanization.

Provides three pure functions that apply controlled randomness to musical
sequences, making them sound more human and less mechanical.

Functions:
    humanize_timing   — Applies ±jitter_ms micro-timing offset to each BassNote
    humanize_velocity — Applies ±variation velocity offset to each note or hit
    add_ghost_notes   — Adds low-velocity ghost hits on silent steps

Musical theory behind humanization:
    Perfect quantization makes patterns sound robotic. Live musicians naturally
    deviate from the grid:
        - Timing: ±5–15ms from the beat, creating "feel" and "push/pull"
        - Velocity: ±10–15 units of variation, adding dynamics and breath
        - Ghost notes: soft hits between main hits, adding textural density

    The parameters here map to producer conventions:
        jitter_ms=5  → subtle, "tight" feel (genre: techno)
        jitter_ms=15 → loose, "swung" feel (genre: deep house, jazz)
        variation=8  → controlled dynamics (genre: techno)
        variation=15 → expressive dynamics (genre: afro house, organic house)

Design:
    - All functions are pure: no I/O, no side effects, no external state
    - Seeded random.Random for deterministic reproducibility
    - Returns new immutable frozen dataclasses (via dataclasses.replace)
    - Works with both BassNote and DrumHit (both have velocity + tick_offset)
"""

from __future__ import annotations

import dataclasses
import random
from collections.abc import Sequence

from core.music_theory.types import BassNote, DrumHit

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

_AnyNote = BassNote | DrumHit

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bpm_to_ticks_per_ms(bpm: float, ticks_per_beat: int) -> float:
    """Return ticks per millisecond at the given BPM.

    Formula: beats_per_ms = BPM / 60_000; ticks_per_ms = beats_per_ms × ticks_per_beat

    Args:
        bpm:            Tempo in beats per minute.
        ticks_per_beat: MIDI resolution (ticks per quarter note).

    Returns:
        Float ticks per millisecond.

    Examples:
        >>> _bpm_to_ticks_per_ms(120.0, 480)
        0.96
        >>> _bpm_to_ticks_per_ms(120.0, 960)
        1.92
    """
    beats_per_ms = bpm / 60_000.0
    return beats_per_ms * ticks_per_beat


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def humanize_timing(
    notes: Sequence[BassNote],
    *,
    jitter_ms: float = 5.0,
    bpm: float = 120.0,
    ticks_per_beat: int = 480,
    seed: int | None = None,
) -> tuple[BassNote, ...]:
    """Apply micro-timing jitter to a sequence of BassNote objects.

    Sets the ``tick_offset`` field on each returned note to a random value
    in [-max_ticks, +max_ticks], where max_ticks is derived from jitter_ms.
    Positive offset = slightly late; negative = slightly early.

    The original notes are not modified — this returns new frozen dataclasses.

    Args:
        notes:          Sequence of BassNote objects to humanize.
        jitter_ms:      Maximum timing offset in milliseconds (default 5.0).
                        Actual per-note offset is random in [-jitter_ms, +jitter_ms].
        bpm:            Tempo in BPM, used to convert ms → ticks (default 120.0).
        ticks_per_beat: MIDI resolution in ticks per quarter note (default 480).
        seed:           Random seed for reproducibility. None = non-deterministic.

    Returns:
        Tuple of new BassNote objects with tick_offset set. Length = len(notes).

    Raises:
        ValueError: If jitter_ms < 0.

    Examples:
        >>> notes = (BassNote(pitch_midi=45, step=0, duration_steps=4, velocity=100, bar=0),)
        >>> result = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=42)
        >>> isinstance(result[0].tick_offset, int)
        True
    """
    if jitter_ms < 0:
        raise ValueError(f"jitter_ms must be >= 0, got {jitter_ms}")

    ticks_per_ms = _bpm_to_ticks_per_ms(bpm, ticks_per_beat)
    max_ticks = round(jitter_ms * ticks_per_ms)

    if max_ticks == 0 or not notes:
        return tuple(notes)

    rng = random.Random(seed)
    result: list[BassNote] = []
    for note in notes:
        offset = rng.randint(-max_ticks, max_ticks)
        result.append(dataclasses.replace(note, tick_offset=offset))
    return tuple(result)


def humanize_velocity(
    notes: Sequence[_AnyNote],
    *,
    variation: int = 12,
    seed: int | None = None,
) -> tuple[_AnyNote, ...]:
    """Apply random velocity variation to a sequence of notes or drum hits.

    Adds a random offset in [-variation, +variation] to each note's velocity,
    clamped to the valid MIDI range [1, 127].

    Works with both BassNote and DrumHit sequences. Can be used in combination
    with humanize_timing() for full humanization:

        notes = generate_bassline(chords, ...)
        notes = humanize_timing(notes, jitter_ms=5.0, bpm=120.0)
        notes = humanize_velocity(notes, variation=10)

    Args:
        notes:      Sequence of BassNote or DrumHit objects.
        variation:  Maximum velocity change per note (default 12 = ±12 units).
        seed:       Random seed for reproducibility. None = non-deterministic.

    Returns:
        Tuple of new notes/hits with modified velocities. Length = len(notes).

    Raises:
        ValueError: If variation < 0.

    Examples:
        >>> hits = (DrumHit(instrument="kick", step=0, velocity=110, bar=0),)
        >>> result = humanize_velocity(hits, variation=10, seed=0)
        >>> 100 <= result[0].velocity <= 120
        True
    """
    if variation < 0:
        raise ValueError(f"variation must be >= 0, got {variation}")

    if variation == 0 or not notes:
        return tuple(notes)

    rng = random.Random(seed)
    result: list[_AnyNote] = []
    for note in notes:
        delta = rng.randint(-variation, variation)
        new_velocity = max(1, min(127, note.velocity + delta))
        result.append(dataclasses.replace(note, velocity=new_velocity))
    return tuple(result)


def add_ghost_notes(
    hits: Sequence[DrumHit],
    *,
    probability: float = 0.12,
    velocity_range: tuple[int, int] = (10, 30),
    instruments: frozenset[str] | None = None,
    bars: int = 4,
    steps_per_bar: int = 16,
    seed: int | None = None,
) -> tuple[DrumHit, ...]:
    """Add ghost hits on steps that are currently silent for the given instruments.

    For each (instrument, bar, step) combination not already in ``hits``,
    rolls a probability check. When it passes, a low-velocity ghost hit is
    created at that position.

    This simulates the subtle ghosting that live drummers add — soft hits
    between main hits that add texture without disrupting the groove. Ghost
    notes are typically very quiet (velocity 10–30) and usually placed on
    hi-hat instruments.

    Args:
        hits:           Existing DrumHit sequence to augment.
        probability:    Probability (0.0–1.0) of adding a ghost hit per empty step.
                        Typical range: 0.05–0.20. (default 0.12)
        velocity_range: (min_v, max_v) inclusive velocity range for ghost hits.
                        Keep low (10–30) to preserve the ghost effect. (default (10, 30))
        instruments:    Set of instrument names to add ghosts for.
                        Defaults to frozenset({"hihat_c", "hihat_o"}) if None.
        bars:           Number of bars to consider when scanning empty steps.
        steps_per_bar:  Grid resolution (default 16 = 16th-note grid).
        seed:           Random seed for reproducibility. None = non-deterministic.

    Returns:
        Tuple of all hits (original + ghost hits), sorted by (bar, step).
        If probability=0.0, returns the original hits unchanged.

    Raises:
        ValueError: If probability not in [0.0, 1.0].
        ValueError: If velocity_range min > max.

    Examples:
        >>> hits = (DrumHit(instrument="hihat_c", step=0, velocity=72, bar=0),)
        >>> result = add_ghost_notes(hits, probability=1.0, bars=1, seed=0)
        >>> len(result) > 1  # ghost notes added on empty hi-hat steps
        True
    """
    if not (0.0 <= probability <= 1.0):
        raise ValueError(f"probability must be in [0.0, 1.0], got {probability}")

    v_min, v_max = velocity_range
    if v_min > v_max:
        raise ValueError(
            f"velocity_range min must be <= max, got ({v_min}, {v_max})"
        )

    if probability == 0.0:
        return tuple(hits)

    target_instruments: frozenset[str] = instruments if instruments is not None else frozenset(
        {"hihat_c", "hihat_o"}
    )

    # Build a set of already-occupied (instrument, bar, step) positions
    occupied: frozenset[tuple[str, int, int]] = frozenset(
        (h.instrument, h.bar, h.step) for h in hits
    )

    rng = random.Random(seed)
    ghost_hits: list[DrumHit] = []

    for bar_idx in range(bars):
        for step in range(steps_per_bar):
            for instrument in sorted(target_instruments):  # sorted for determinism
                if (instrument, bar_idx, step) in occupied:
                    continue  # already has a hit — not a ghost position
                if rng.random() < probability:
                    velocity = rng.randint(v_min, v_max)
                    ghost_hits.append(
                        DrumHit(
                            instrument=instrument,
                            step=step,
                            velocity=velocity,
                            bar=bar_idx,
                        )
                    )

    all_hits = list(hits) + ghost_hits
    all_hits.sort(key=lambda h: (h.bar, h.step, h.instrument))
    return tuple(all_hits)
