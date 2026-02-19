"""
suggest_scale tool — recommend a scale for a given genre and mood.

Pure computation: no LLM, no DB, no I/O.
Given a genre + mood (+ optional root note), returns:
  - Recommended scale name + formula
  - All notes in the scale
  - Camelot Wheel position
  - Compatible keys for mixing
  - Common chord degrees to use
  - Why this scale fits the genre/mood combination
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.theory import (
    SCALE_FORMULAS,
    build_scale,
    normalize_note,
)

# ---------------------------------------------------------------------------
# Genre + mood → recommended scale
# ---------------------------------------------------------------------------

# Each entry: (scale_mode, rationale)
_GENRE_MOOD_SCALE: dict[str, dict[str, tuple[str, str]]] = {
    "organic house": {
        "dark": ("natural minor", "Natural minor anchors the organic feel — earthy and grounded"),
        "melancholic": ("natural minor", "Minor thirds create the introspective, emotional depth"),
        "dreamy": ("dorian", "Dorian's raised 6th adds brightness without losing the minor feel"),
        "euphoric": ("dorian", "Dorian is lighter than natural minor — works for uplifting moments"),
        "neutral": ("natural minor", "Natural minor is the default tonal center for organic house"),
    },
    "melodic house": {
        "dark": ("natural minor", "Deep minor tonality for emotional impact"),
        "melancholic": ("natural minor", "Classic melodic house sadness"),
        "dreamy": ("dorian", "Dorian gives the floating, slightly hopeful quality"),
        "euphoric": ("major", "Major scale for peak energy melodic moments"),
        "neutral": ("dorian", "Dorian sits between minor and major — ideal for melodic house"),
    },
    "progressive house": {
        "dark": ("natural minor", "Tension-building minor for the long build arc"),
        "melancholic": ("natural minor", "Emotional journey through natural minor"),
        "dreamy": ("dorian", "Dorian gives airy, expansive feel for long arrangements"),
        "euphoric": ("major", "Major scale anthems for peak festival moments"),
        "neutral": ("natural minor", "Natural minor drives the epic progression feel"),
    },
    "deep house": {
        "dark": ("natural minor", "Moody, late-night minor feel"),
        "melancholic": ("dorian", "Dorian's raised 6th gives the soulful, jazzy quality"),
        "dreamy": ("dorian", "Warm Dorian works perfectly with Rhodes and pads"),
        "euphoric": ("major", "Bright major for uplifting deep house"),
        "neutral": ("dorian", "Dorian is the jazz-influenced backbone of deep house"),
    },
    "melodic techno": {
        "dark": ("natural minor", "Natural minor for the hypnotic, dark driving feel"),
        "melancholic": ("natural minor", "Minor gives the introspective, cinematic quality"),
        "dreamy": ("dorian", "Dorian for slightly brighter, less oppressive textures"),
        "euphoric": ("natural minor", "Even euphoric techno stays in minor — the drive comes from rhythm"),
        "neutral": ("natural minor", "Natural minor is the primary tonality of melodic techno"),
    },
    "techno": {
        "dark": ("phrygian", "Phrygian's flat-2 creates maximum tension and industrial menace"),
        "melancholic": ("natural minor", "Straightforward minor for darker techno"),
        "dreamy": ("natural minor", "Stripped back — techno rarely goes dreamy"),
        "euphoric": ("natural minor", "Minor even when euphoric — energy from rhythm not harmony"),
        "neutral": ("natural minor", "Natural minor is the standard"),
    },
    "acid": {
        "dark": ("natural minor", "Classic acid minor tonality"),
        "melancholic": ("natural minor", "Minor for the squelching, melancholic acid lines"),
        "dreamy": ("dorian", "Dorian for a more hopeful, hypnotic acid feel"),
        "euphoric": ("major", "Major for the rare bright acid moments"),
        "neutral": ("natural minor", "Natural minor drives the acid bassline"),
    },
}

# Default root notes per genre (common starting points)
_GENRE_DEFAULT_ROOT: dict[str, str] = {
    "organic house": "A",
    "melodic house": "A",
    "progressive house": "A",
    "deep house": "A",
    "melodic techno": "F#",
    "techno": "A",
    "acid": "A",
}

# Camelot Wheel positions: (note, mode) → (number, letter)
# Only covers the most common combinations
_CAMELOT: dict[tuple[str, str], str] = {
    ("A", "natural minor"): "8A",
    ("A#", "natural minor"): "3A",
    ("B", "natural minor"): "10A",
    ("C", "natural minor"): "5A",
    ("C#", "natural minor"): "12A",
    ("D", "natural minor"): "7A",
    ("D#", "natural minor"): "2A",
    ("E", "natural minor"): "9A",
    ("F", "natural minor"): "4A",
    ("F#", "natural minor"): "11A",
    ("G", "natural minor"): "6A",
    ("G#", "natural minor"): "1A",
    ("C", "major"): "8B",
    ("G", "major"): "9B",
    ("D", "major"): "10B",
    ("A", "major"): "11B",
    ("E", "major"): "12B",
    ("B", "major"): "1B",
    ("F#", "major"): "2B",
    ("C#", "major"): "3B",
    ("G#", "major"): "4B",
    ("D#", "major"): "5B",
    ("A#", "major"): "6B",
    ("F", "major"): "7B",
    # Dorian shares the Camelot position with its relative (treated as minor)
    ("A", "dorian"): "9A",
    ("D", "dorian"): "2A",
    ("E", "dorian"): "4A",
    ("G", "dorian"): "6A",
    ("B", "dorian"): "11A",
    ("F#", "dorian"): "3A",
}

# Adjacent Camelot positions for harmonic mixing compatibility
_CAMELOT_ADJACENT: dict[str, list[str]] = {
    "8A": ["8B", "7A", "9A"],
    "3A": ["3B", "2A", "4A"],
    "10A": ["10B", "9A", "11A"],
    "5A": ["5B", "4A", "6A"],
    "12A": ["12B", "11A", "1A"],
    "7A": ["7B", "6A", "8A"],
    "2A": ["2B", "1A", "3A"],
    "9A": ["9B", "8A", "10A"],
    "4A": ["4B", "3A", "5A"],
    "11A": ["11B", "10A", "12A"],
    "6A": ["6B", "5A", "7A"],
    "1A": ["1B", "12A", "2A"],
    "8B": ["8A", "7B", "9B"],
    "9B": ["9A", "8B", "10B"],
    "10B": ["10A", "9B", "11B"],
    "11B": ["11A", "10B", "12B"],
    "12B": ["12A", "11B", "1B"],
    "1B": ["1A", "12B", "2B"],
    "2B": ["2A", "1B", "3B"],
    "3B": ["3A", "2B", "4B"],
    "4B": ["4A", "3B", "5B"],
    "5B": ["5A", "4B", "6B"],
    "6B": ["6A", "5B", "7B"],
    "7B": ["7A", "6B", "8B"],
}

# Recommended chord degrees per scale mode (0-based scale degrees)
_SCALE_CHORD_DEGREES: dict[str, dict[str, str]] = {
    "natural minor": {
        "i (tonic)": "Root chord — home base",
        "III (mediant)": "Bright contrast, emotional lift",
        "iv (subdominant)": "Tension before resolution back to i",
        "VI (submediant)": "The major chord that defines minor tonality",
        "VII (subtonic)": "Driving, unresolved — perfect loop ending",
    },
    "major": {
        "I (tonic)": "Root chord — bright, resolved",
        "IV (subdominant)": "Movement and tension",
        "V (dominant)": "Classic tension-resolution",
        "vi (relative minor)": "Emotional depth within major context",
    },
    "dorian": {
        "i (tonic)": "Minor root with ambiguity",
        "II (supertonic)": "The Dorian signature — major II chord",
        "IV (subdominant)": "Major IV in a minor key — the jazz-house sound",
        "VII (subtonic)": "Strong, unresolved movement",
    },
    "phrygian": {
        "i (tonic)": "Dark minor tonic",
        "II (flat-2)": "The Phrygian signature — creates maximum tension",
        "VII (subtonic)": "Resolution before re-entering tonic",
    },
}

VALID_GENRES: frozenset[str] = frozenset(_GENRE_MOOD_SCALE.keys())
VALID_MOODS: frozenset[str] = frozenset(
    {mood for moods in _GENRE_MOOD_SCALE.values() for mood in moods}
)


class SuggestScale(MusicalTool):
    """
    Suggest the best scale for a given genre and mood.

    Returns the recommended scale name, all notes, Camelot Wheel position,
    compatible keys for mixing, and guidance on which chord degrees to use.

    100% deterministic — no LLM, no database, works offline.
    """

    @property
    def name(self) -> str:
        return "suggest_scale"

    @property
    def description(self) -> str:
        return (
            "Suggest the best musical scale for a given genre and mood. "
            "Returns the scale name (e.g. 'A natural minor'), all notes, "
            "Camelot Wheel position for DJ mixing, compatible adjacent keys, "
            "and recommended chord degrees to use. "
            "Use when the user asks which scale or key to use for a track, "
            "or wants to know what key fits a specific genre and mood. "
            f"Supported genres: {', '.join(sorted(VALID_GENRES))}. "
            f"Supported moods: {', '.join(sorted(VALID_MOODS))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Music genre. Options: {', '.join(sorted(VALID_GENRES))}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="mood",
                type=str,
                description=(
                    f"Emotional mood. Options: {', '.join(sorted(VALID_MOODS))}. "
                    "Default: 'dark'."
                ),
                required=False,
                default="dark",
            ),
            ToolParameter(
                name="root",
                type=str,
                description=(
                    "Optional root note (e.g. 'A', 'F#', 'Bb'). "
                    "If omitted, the most common root for the genre is used."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Suggest the scale for the given genre + mood + optional root.

        Returns:
            ToolResult with scale name, notes, Camelot position,
            compatible keys, chord degree guidance, and rationale.
        """
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        mood: str = (kwargs.get("mood") or "dark").strip().lower()
        root_raw: str = (kwargs.get("root") or "").strip()

        # Validate genre
        if genre not in VALID_GENRES:
            return ToolResult(
                success=False,
                error=(
                    f"genre must be one of: {', '.join(sorted(VALID_GENRES))}. "
                    f"Got: {genre!r}"
                ),
            )

        # Validate mood
        genre_moods = _GENRE_MOOD_SCALE[genre]
        if mood not in genre_moods:
            valid_moods = list(genre_moods.keys())
            return ToolResult(
                success=False,
                error=(
                    f"mood must be one of: {', '.join(valid_moods)} for {genre}. "
                    f"Got: {mood!r}"
                ),
            )

        # Resolve root
        if root_raw:
            try:
                root = normalize_note(root_raw)
            except ValueError:
                return ToolResult(
                    success=False,
                    error=f"Cannot parse root note {root_raw!r}. Use e.g. 'A', 'F#', 'Bb'.",
                )
        else:
            root = _GENRE_DEFAULT_ROOT.get(genre, "A")

        # Look up recommended scale
        mode, rationale = genre_moods[mood]

        # Build the scale notes
        try:
            scale_notes = build_scale(root, mode)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        # Camelot Wheel lookup
        camelot = _CAMELOT.get((root, mode), "unknown")
        compatible_keys = _CAMELOT_ADJACENT.get(camelot, [])

        # Chord degree guidance
        chord_degrees = _SCALE_CHORD_DEGREES.get(mode, {})

        # Full key name
        key_name = f"{root} {mode}"

        return ToolResult(
            success=True,
            data={
                "key": key_name,
                "root": root,
                "mode": mode,
                "scale_notes": scale_notes,
                "camelot_position": camelot,
                "compatible_camelot_keys": compatible_keys,
                "chord_degrees": chord_degrees,
                "genre": genre,
                "mood": mood,
                "rationale": rationale,
                "formula": list(SCALE_FORMULAS.get(mode, ())),
            },
            metadata={
                "scale_length": len(scale_notes),
                "camelot_known": camelot != "unknown",
            },
        )
