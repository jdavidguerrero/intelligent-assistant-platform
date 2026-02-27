"""
suggest_chord_progression tool — deterministic music theory engine.

Pure computation: no LLM, no DB, no I/O.
Given a key + mood + genre, returns diatonic chord progressions
with Roman numeral analysis, MIDI notes, and variations.

Designed to run offline — suitable for OpenDock Brain (Teensy) if
ported to C++ with the same lookup tables.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.theory import (
    GENRE_PROGRESSIONS,
    GENRE_VOICING,
    MOOD_DEGREE_WEIGHTS,
    SCALE_FORMULAS,
    build_diatonic_chords,
    build_scale,
    normalize_note,
)

# ---------------------------------------------------------------------------
# Domain validation constants
# ---------------------------------------------------------------------------

VALID_MOODS: frozenset[str] = frozenset(MOOD_DEGREE_WEIGHTS.keys())
VALID_MODES: frozenset[str] = frozenset(SCALE_FORMULAS.keys())
VALID_GENRES: frozenset[str] = frozenset(GENRE_PROGRESSIONS.keys()) | frozenset(["unknown"])
VALID_VOICINGS: frozenset[str] = frozenset(["triads", "seventh", "extended"])
MIN_BARS: int = 1
MAX_BARS: int = 16


class SuggestChordProgression(MusicalTool):
    """
    Suggest diatonic chord progressions for a given key, mood, and genre.

    Uses music theory rules (diatonic harmony, Roman numeral analysis,
    mood weighting) to generate progressions. 100% deterministic —
    no LLM, no database, works offline.

    Returns the primary progression, MIDI notes for each chord,
    Roman numeral analysis, and 2 alternative variations.

    Example:
        tool = SuggestChordProgression()
        result = tool(key="A minor", mood="dark", genre="organic house", bars=4)
        # Returns i-VI-III-VII with Am7, Fmaj7, Cmaj7, Gm7 and MIDI events
    """

    @property
    def name(self) -> str:
        return "suggest_chord_progression"

    @property
    def description(self) -> str:
        return (
            "Suggest diatonic chord progressions for a given musical key, mood, and genre. "
            "Returns the primary progression with Roman numeral analysis, MIDI note numbers "
            "for each chord, and 2 alternative variations. "
            "Use when the user asks about chord progressions, harmony, or wants chord "
            "suggestions for a specific genre or mood. "
            "Supports organic house, melodic house, progressive house, deep house, techno, acid."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="key",
                type=str,
                description=(
                    "Musical key in 'Note mode' format. "
                    "Examples: 'A minor', 'C major', 'F# natural minor', 'Bb dorian'. "
                    "Supported modes: natural minor, major, harmonic minor, dorian."
                ),
                required=True,
            ),
            ToolParameter(
                name="mood",
                type=str,
                description=(
                    f"Emotional mood to guide chord selection. "
                    f"Options: {', '.join(sorted(VALID_MOODS))}. Default: 'dark'."
                ),
                required=False,
                default="dark",
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Music genre for progression style. "
                    f"Options: {', '.join(sorted(GENRE_PROGRESSIONS.keys()))}. "
                    f"Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="bars",
                type=int,
                description=f"Number of bars ({MIN_BARS}–{MAX_BARS}). Default: 4.",
                required=False,
                default=4,
            ),
            ToolParameter(
                name="voicing",
                type=str,
                description=(
                    "Chord voicing complexity. "
                    "'triads': 3-note chords (raw, for Teensy MIDI). "
                    "'seventh': 7th chords (Cmaj7, Am7). "
                    "'extended': 9ths and extensions (Cmaj9, Dm9, organic house sound). "
                    "Default: auto (matches genre)."
                ),
                required=False,
                default="auto",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Generate chord progressions for the given key, mood, genre, and bars.

        Returns:
            ToolResult with progression list, variations, scale notes,
            Roman numeral analysis string, and MIDI notes per chord.
        """
        key: str = (kwargs.get("key") or "").strip()
        mood: str = (kwargs.get("mood") or "dark").strip().lower()
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        bars: int = kwargs.get("bars") if kwargs.get("bars") is not None else 4
        voicing_pref: str = (kwargs.get("voicing") or "auto").strip().lower()

        # -------------------------------------------------------------------
        # Domain validation
        # -------------------------------------------------------------------
        if not key:
            return ToolResult(success=False, error="key cannot be empty")
        if len(key) > 50:
            return ToolResult(success=False, error="key too long (max 50 chars)")

        parsed = _parse_key(key)
        if parsed is None:
            return ToolResult(
                success=False,
                error=(
                    f"Cannot parse key {key!r}. "
                    f"Use format 'Note mode' e.g. 'A minor', 'C major', 'F# dorian'."
                ),
            )
        root, mode = parsed

        if mood not in VALID_MOODS:
            return ToolResult(
                success=False,
                error=f"mood must be one of: {', '.join(sorted(VALID_MOODS))}",
            )
        if genre not in VALID_GENRES:
            # Unknown genre: fall back to neutral
            genre = "unknown"
        if not (MIN_BARS <= bars <= MAX_BARS):
            return ToolResult(
                success=False,
                error=f"bars must be between {MIN_BARS} and {MAX_BARS}",
            )
        if voicing_pref not in VALID_VOICINGS and voicing_pref != "auto":
            return ToolResult(
                success=False,
                error="voicing must be one of: triads, seventh, extended, auto",
            )

        # -------------------------------------------------------------------
        # Resolve voicing: explicit override or genre default
        # -------------------------------------------------------------------
        voicing = voicing_pref if voicing_pref != "auto" else GENRE_VOICING.get(genre, "seventh")

        # -------------------------------------------------------------------
        # Build diatonic chord palette for this key
        # -------------------------------------------------------------------
        try:
            all_chords = build_diatonic_chords(root, mode, voicing)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

        scale_notes = build_scale(root, mode)

        # -------------------------------------------------------------------
        # Select primary progression
        # -------------------------------------------------------------------
        primary_degrees = _select_progression(genre, mood, bars, mode)
        primary = _degrees_to_chords(primary_degrees, all_chords)

        # -------------------------------------------------------------------
        # Build 2 alternative variations
        # -------------------------------------------------------------------
        variations = _build_variations(genre, mood, bars, mode, all_chords, exclude=primary_degrees)

        # -------------------------------------------------------------------
        # Roman numeral analysis string
        # -------------------------------------------------------------------
        roman_str = " – ".join(c["roman"] for c in primary)
        analysis = _describe_progression(primary, mode, mood)

        return ToolResult(
            success=True,
            data={
                "key": f"{root} {mode}",
                "scale": scale_notes,
                "mood": mood,
                "genre": genre,
                "voicing": voicing,
                "bars": bars,
                "progression": primary,
                "roman_analysis": roman_str,
                "analysis": analysis,
                "variations": [
                    {
                        "chords": v,
                        "roman": " – ".join(c["roman"] for c in v),
                    }
                    for v in variations
                ],
            },
            metadata={
                "mode": mode,
                "root": root,
                "diatonic_palette": [c["name"] for c in all_chords],
            },
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_key(key: str) -> tuple[str, str] | None:
    """
    Parse a key string like 'A minor', 'C# natural minor', 'Bb dorian'.

    Returns (root_note, mode) or None if unparseable.
    """
    parts = key.strip().split()
    if len(parts) < 2:
        return None

    # Try root = first word, mode = rest
    root_raw = parts[0]
    mode_raw = " ".join(parts[1:]).lower()

    # Normalize root
    try:
        root = normalize_note(root_raw)
    except ValueError:
        return None

    # Resolve mode aliases
    mode_aliases: dict[str, str] = {
        "minor": "natural minor",
        "natural minor": "natural minor",
        "harmonic minor": "harmonic minor",
        "melodic minor": "melodic minor",
        "major": "major",
        "ionian": "major",
        "dorian": "dorian",
        "phrygian": "phrygian",
        "lydian": "lydian",
        "mixolydian": "mixolydian",
    }

    mode = mode_aliases.get(mode_raw)
    if mode is None:
        return None

    return root, mode


def _select_progression(
    genre: str,
    mood: str,
    bars: int,
    mode: str,
) -> list[int]:
    """
    Select the best progression for given genre + mood.

    Strategy:
        1. If genre has canonical progressions, use the first one (primary)
        2. Adjust length to match bars (repeat or truncate)
        3. If genre unknown, fall back to mood-weighted selection

    Returns list of scale degree indices (0-based).
    """
    genre_progs = GENRE_PROGRESSIONS.get(genre)
    if genre_progs:
        base = genre_progs[0]  # primary progression
    else:
        # Mood-weighted fallback: pick top-weighted degrees
        weights = MOOD_DEGREE_WEIGHTS.get(mood, MOOD_DEGREE_WEIGHTS["neutral"])
        # Sort degrees by weight descending
        sorted_degrees = sorted(weights.keys(), key=lambda d: weights[d], reverse=True)
        # Build a 4-chord progression from the top weighted degrees
        base = sorted_degrees[:4] if len(sorted_degrees) >= 4 else sorted_degrees

    return _fit_to_bars(base, bars)


def _fit_to_bars(degrees: list[int], bars: int) -> list[int]:
    """
    Expand or truncate a progression to exactly `bars` chords.

    Repeats the pattern cyclically if bars > len(degrees).
    """
    if not degrees:
        return [0] * bars
    result = []
    for i in range(bars):
        result.append(degrees[i % len(degrees)])
    return result


def _degrees_to_chords(degrees: list[int], all_chords: list[dict]) -> list[dict]:
    """
    Map a list of scale degree indices to chord dicts.

    Clamps out-of-range degrees to the palette size.
    """
    n = len(all_chords)
    return [all_chords[d % n] for d in degrees]


def _build_variations(
    genre: str,
    mood: str,
    bars: int,
    mode: str,
    all_chords: list[dict],
    exclude: list[int],
) -> list[list[dict]]:
    """
    Build 2 alternative progression variations.

    Pulls from the genre's alternative progressions list,
    excluding the primary one (identified by its degree pattern).
    Falls back to mood-weighted alternatives if not enough.
    """
    genre_progs = GENRE_PROGRESSIONS.get(genre, [])
    variations: list[list[dict]] = []

    for prog in genre_progs[1:]:  # skip index 0 (primary)
        if len(variations) >= 2:
            break
        fitted = _fit_to_bars(prog, bars)
        if fitted != exclude:
            variations.append(_degrees_to_chords(fitted, all_chords))

    # If still need more, add a mood-based variation
    if len(variations) < 2:
        weights = MOOD_DEGREE_WEIGHTS.get(mood, MOOD_DEGREE_WEIGHTS["neutral"])
        # Reverse-sort for the alternative: less-weight degrees first
        alt_degrees = sorted(weights.keys(), key=lambda d: weights[d])
        fitted = _fit_to_bars(alt_degrees, bars)
        if fitted != exclude:
            variations.append(_degrees_to_chords(fitted, all_chords))

    # Guarantee exactly 2 — pad with a simple i-iv-VII-III fallback
    while len(variations) < 2:
        fallback = _fit_to_bars([0, 3, 6, 2], bars)
        variations.append(_degrees_to_chords(fallback, all_chords))

    return variations[:2]


def _describe_progression(chords: list[dict], mode: str, mood: str) -> str:
    """
    Generate a brief human-readable analysis of the progression.

    Args:
        chords: List of chord dicts with 'roman' and 'name' keys
        mode: Scale mode string
        mood: Mood string

    Returns:
        One-line analysis string
    """
    roman = " – ".join(c["roman"] for c in chords)
    names = " – ".join(c["name"] for c in chords)

    # Detect common progressions
    romans_tuple = tuple(c["roman"] for c in chords[:4])
    known_patterns: dict[tuple[str, ...], str] = {
        ("i", "VI", "III", "VII"): "Natural minor with Andalusian cadence feel",
        ("i", "iv", "VII", "III"): "Modal interchange, dark descending motion",
        ("I", "IV", "V", "I"): "Classic tonic–subdominant–dominant cadence",
        ("I", "V", "vi", "IV"): "Pop canon — optimistic, anthemic",
        ("i", "v", "VI", "iv"): "Minor with raised 5th, melancholic tension",
        ("i", "VI", "iv", "VII"): "Ethereal loop, common in ambient house",
    }
    pattern_desc = known_patterns.get(romans_tuple, "Diatonic progression")

    mode_desc = {"natural minor": "natural minor", "major": "major", "dorian": "Dorian mode"}.get(
        mode, mode
    )
    return f"{roman} | {names} | {mode_desc}, {mood} mood — {pattern_desc}"
