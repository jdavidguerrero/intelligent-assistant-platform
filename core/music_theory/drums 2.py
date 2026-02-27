"""
core/music_theory/drums.py — Drum pattern generator.

generate_pattern() takes genre, BPM, bar count and energy level, and
produces a DrumPattern from the YAML template. Fills are applied
automatically on phrase boundaries (every N bars as defined in template).

Algorithm:
    1. Load genre template (cached)
    2. Parse drum_patterns: velocity_base, grid, fill
    3. For each bar (0 to bars-1):
       a. Determine if this bar triggers a fill
          (bar_idx + 1) % every_n_bars == 0 → use fill grid
          otherwise → use base grid
       b. For each instrument, iterate 16 steps
       c. Where grid[step] == 1, create a DrumHit
       d. Apply velocity: base_velocity × energy_factor + humanization
    4. Sort hits by (bar, step) and return DrumPattern

Fill trigger: the LAST bar of each N-bar phrase gets the fill.
    4-bar phrase: bars 0,1,2 = normal; bar 3 = fill
    This matches the standard "4-bar phrase" structure in electronic music.

Energy factor: energy (0–10) maps to a velocity multiplier:
    energy=0 → 0.5  (very quiet, ghostly)
    energy=5 → 0.85 (moderate)
    energy=10 → 1.0  (full power)

Ghost notes: when energy ≥ 3, hi-hats that are "off" (grid=0) occasionally
get a soft ghost hit (velocity ~25% of base). This adds the subtle texture
that separates programmed from human-feel patterns.

Design:
    - Pure function — no I/O, no global mutable state
    - Seeded PRNG for deterministic humanization and ghost notes
    - Template-driven: rhythm lives in YAML
"""

from __future__ import annotations

import random
from typing import Any

from core.music_theory.harmony import _load_template
from core.music_theory.types import DrumHit, DrumPattern

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STEPS_PER_BAR: int = 16  # 16th-note resolution
_GHOST_PROBABILITY: float = 0.12  # 12% chance of ghost hi-hat per silent step
_GHOST_VELOCITY_RATIO: float = 0.25  # ghost = 25% of base hihat velocity
_HUMANIZE_RANGE: int = 6  # ±6 velocity units per hit

# Energy → velocity multiplier: interpolated from 0.50 at e=0 to 1.0 at e=10
_ENERGY_MULTIPLIER_MIN: float = 0.50
_ENERGY_MULTIPLIER_MAX: float = 1.00


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _energy_to_multiplier(energy: int) -> float:
    """Map energy (0–10) to a velocity multiplier (0.50–1.00).

    Args:
        energy: Integer energy level, 0 (quietest) to 10 (loudest).

    Returns:
        Float multiplier in [0.50, 1.00].
    """
    clamped = max(0, min(10, energy))
    t = clamped / 10.0
    return _ENERGY_MULTIPLIER_MIN + t * (_ENERGY_MULTIPLIER_MAX - _ENERGY_MULTIPLIER_MIN)


def _apply_velocity(
    base: int,
    multiplier: float,
    rng: random.Random,
    humanize: bool,
) -> int:
    """Compute final velocity from base, energy multiplier and humanization.

    Args:
        base:       Base velocity from template (0–127).
        multiplier: Energy scaling factor.
        rng:        Seeded random instance for humanization.
        humanize:   If True, adds random ±_HUMANIZE_RANGE offset.

    Returns:
        Integer velocity clamped to [1, 127].
    """
    v = round(base * multiplier)
    if humanize:
        v += rng.randint(-_HUMANIZE_RANGE, _HUMANIZE_RANGE)
    return max(1, min(127, v))


def _get_active_instruments(
    energy_layers: dict[int | str, list[str]],
    energy: int,
) -> frozenset[str] | None:
    """Return the set of instruments active at the given energy level.

    Each key in energy_layers is a minimum energy threshold; the value is the
    list of instruments that activate at or above that threshold. Thresholds
    are additive — instruments from lower thresholds remain active at higher
    energy levels.

    Returns None when energy_layers is empty, meaning all instruments in the
    grid are active regardless of energy (backward-compatible with templates
    that don't define energy_layers).

    Args:
        energy_layers: Dict of {threshold: [instruments]} from the YAML template.
        energy:        Current energy level (0–10).

    Returns:
        frozenset of active instrument names, or None if no layers defined.

    Examples:
        >>> layers = {1: ["kick"], 3: ["snare"], 5: ["hihat_c"]}
        >>> _get_active_instruments(layers, 4)
        frozenset({'kick', 'snare'})
        >>> _get_active_instruments({}, 7) is None
        True
    """
    if not energy_layers:
        return None  # No energy_layers defined → all instruments active

    active: set[str] = set()
    for threshold_raw, instruments in sorted(energy_layers.items(), key=lambda kv: int(kv[0])):
        if energy >= int(threshold_raw):
            active.update(instruments)
    return frozenset(active)


def _grid_for_bar(
    bar_idx: int,
    every_n_bars: int,
    base_grid: dict[str, list[int]],
    fill_grid: dict[str, list[int]],
) -> dict[str, list[int]]:
    """Choose the correct grid (base or fill) for a given bar index.

    Fill triggers on the LAST bar of each N-bar phrase:
        bar_idx=3 with every_n_bars=4 → fill (3+1) % 4 == 0

    Args:
        bar_idx:      0-indexed bar number.
        every_n_bars: Phrase length — fill on last bar of each phrase.
        base_grid:    Normal beat grid per instrument.
        fill_grid:    Fill override grid per instrument.

    Returns:
        Grid dict to use for this bar.
    """
    if every_n_bars > 0 and (bar_idx + 1) % every_n_bars == 0:
        return fill_grid
    return base_grid


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pattern(
    *,
    bpm: float = 120.0,
    genre: str = "organic house",
    bars: int = 4,
    energy: int = 7,
    humanize: bool = True,
    seed: int | None = None,
) -> DrumPattern:
    """Generate a drum pattern from a genre template.

    Produces a DrumPattern with hits for all instruments across `bars` bars.
    Fill patterns replace the base grid on the last bar of each phrase
    (phrase length defined by template's fill.every_n_bars).

    Ghost hi-hat notes are added on silent steps when energy >= 3 and
    humanize=True, simulating the subtle texture of live drumming.

    Args:
        bpm:       Tempo in BPM. Stored in the DrumPattern for MIDI export.
        genre:     Genre template name. See available_genres().
        bars:      Number of bars to generate (default 4).
        energy:    Energy level 0–10. Controls velocity scaling.
                   0 = ghost-quiet, 5 = moderate, 10 = full power.
        humanize:  If True, applies velocity variation and ghost notes.
        seed:      Random seed. Set for reproducible patterns.

    Returns:
        DrumPattern with all hits sorted by (bar, step).

    Raises:
        ValueError: If genre is unknown, bars <= 0, or energy out of range.
        ValueError: If template has no drum_patterns section.

    Examples:
        >>> p = generate_pattern(bpm=123.0, genre="organic house", bars=4)
        >>> isinstance(p, DrumPattern)
        True
        >>> len(p.hits) > 0
        True
    """
    if bars <= 0:
        raise ValueError(f"bars must be > 0, got {bars}")
    if not (0 <= energy <= 10):
        raise ValueError(f"energy must be in [0, 10], got {energy}")

    template = _load_template(genre)
    drum_data: dict[str, Any] = template.get("drum_patterns", {})
    if not drum_data:
        raise ValueError(
            f"Genre template '{template.get('genre', genre)}' has no drum_patterns section."
        )

    velocity_base: dict[str, int] = drum_data.get("velocity_base", {})
    base_grid: dict[str, list[int]] = drum_data.get("grid", {})
    fill_data: dict[str, Any] = drum_data.get("fill", {})
    prob_section: dict[str, list[float]] = drum_data.get("probability", {})
    energy_layers: dict[int | str, list[str]] = drum_data.get("energy_layers", {})

    every_n_bars: int = int(fill_data.get("every_n_bars", 4))
    fill_grid: dict[str, list[int]] = {
        k: v for k, v in fill_data.items() if k != "every_n_bars" and isinstance(v, list)
    }

    # Determine which instruments are active at this energy level
    active_instruments = _get_active_instruments(energy_layers, energy)

    multiplier = _energy_to_multiplier(energy)
    rng = random.Random(seed)
    hits: list[DrumHit] = []

    for bar_idx in range(bars):
        # Track fill vs. base so probability only applies to base grid bars.
        # Fills must always play as written — they are intentional phrase accents.
        is_fill_bar = every_n_bars > 0 and (bar_idx + 1) % every_n_bars == 0
        grid = fill_grid if is_fill_bar else base_grid

        for instrument, pattern in grid.items():
            # Skip instruments that are not active at this energy level
            if active_instruments is not None and instrument not in active_instruments:
                continue

            base_vel = velocity_base.get(instrument, 90)
            prob_list: list[float] = prob_section.get(instrument, [])

            for step, hit_flag in enumerate(pattern):
                if step >= _STEPS_PER_BAR:
                    break

                if hit_flag == 1:
                    # Probability: only applied to base bars and only when humanize=True,
                    # because probability-based skips are a form of humanization.
                    # Fill bars and humanize=False always play every grid hit.
                    if humanize and not is_fill_bar and prob_list and step < len(prob_list):
                        prob = float(prob_list[step])
                        if prob < 1.0 and rng.random() >= prob:
                            continue

                    velocity = _apply_velocity(base_vel, multiplier, rng, humanize)
                    hits.append(
                        DrumHit(
                            instrument=instrument,
                            step=step,
                            velocity=velocity,
                            bar=bar_idx,
                        )
                    )
                elif (
                    humanize
                    and energy >= 3
                    and instrument in ("hihat_c", "hihat_o")
                    and rng.random() < _GHOST_PROBABILITY
                ):
                    # Ghost hi-hat: silent step gets a very soft hit
                    ghost_vel = max(1, round(base_vel * _GHOST_VELOCITY_RATIO * multiplier))
                    hits.append(
                        DrumHit(
                            instrument=instrument,
                            step=step,
                            velocity=ghost_vel,
                            bar=bar_idx,
                        )
                    )

    # Sort by bar, then step for deterministic ordering
    hits.sort(key=lambda h: (h.bar, h.step))

    return DrumPattern(
        hits=tuple(hits),
        steps_per_bar=_STEPS_PER_BAR,
        bars=bars,
        bpm=bpm,
        genre=genre,
    )
