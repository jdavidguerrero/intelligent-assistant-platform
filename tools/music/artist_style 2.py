"""
ArtistStyle schema and pure extraction helpers.

Pure module — no I/O, no LLM calls, no DB.
Used by extract_style_from_context to structure musical parameters
extracted from RAG context chunks (YouTube deconstructions, articles, etc.)

Design principles:
  - ArtistStyle is an immutable value object (frozen dataclass).
  - All helpers are pure functions: same input → same output.
  - Extraction uses keyword matching + scoring, not regex heuristics.
  - Unknown / undetermined fields default to None (not "unknown" strings).

Integration flow:
  search_by_genre(artist_query)
      → retrieves context chunks from knowledge base
      → extract_style_from_context(chunks, artist)
      → ArtistStyle(key_centers, bpm_range, voicing, progressions, ...)
      → suggest_chord_progression(key=..., mood=..., genre=...)
      → generate_midi_pattern(chord_names=..., bpm=..., style=...)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.music.theory import (
    GENRE_PROGRESSIONS,
    MOOD_DEGREE_WEIGHTS,
    NOTE_NAMES,
)

# Valid moods derived from theory module
VALID_MOODS_SET: frozenset[str] = frozenset(MOOD_DEGREE_WEIGHTS.keys())

# ---------------------------------------------------------------------------
# Domain constants for text extraction
# ---------------------------------------------------------------------------

# Keyword → musical key center (pitch class name)
_KEY_KEYWORDS: dict[str, str] = {
    "a minor": "A",
    "a major": "A",
    "b minor": "B",
    "b major": "B",
    "c minor": "C",
    "c major": "C",
    "d minor": "D",
    "d major": "D",
    "e minor": "E",
    "e major": "E",
    "f minor": "F",
    "f major": "F",
    "g minor": "G",
    "g major": "G",
    "a# minor": "A#",
    "a# major": "A#",
    "bb minor": "A#",
    "bb major": "A#",
    "c# minor": "C#",
    "c# major": "C#",
    "db minor": "C#",
    "db major": "C#",
    "d# minor": "D#",
    "d# major": "D#",
    "eb minor": "D#",
    "eb major": "D#",
    "f# minor": "F#",
    "f# major": "F#",
    "gb minor": "F#",
    "gb major": "F#",
    "g# minor": "G#",
    "g# major": "G#",
    "ab minor": "G#",
    "ab major": "G#",
}

# Mode keywords in text
_MODE_KEYWORDS: dict[str, str] = {
    "dorian": "dorian",
    "minor": "natural minor",
    "natural minor": "natural minor",
    "harmonic minor": "harmonic minor",
    "melodic minor": "melodic minor",
    "phrygian": "phrygian",
    "lydian": "lydian",
    "mixolydian": "mixolydian",
    "major": "major",
}

# BPM range keywords: maps phrase → (min_bpm, max_bpm)
_BPM_RANGE_KEYWORDS: dict[str, tuple[int, int]] = {
    "very slow": (60, 90),
    "slow": (80, 100),
    "mid tempo": (110, 128),
    "medium tempo": (110, 128),
    "mid-tempo": (110, 128),
    "house tempo": (120, 128),
    "techno tempo": (128, 145),
    "fast": (130, 150),
    "very fast": (140, 174),
}

# Mood keywords — must match VALID_MOODS_SET from theory
_MOOD_KEYWORDS: dict[str, str] = {
    "dark": "dark",
    "darker": "dark",
    "shadowy": "dark",
    "melancholic": "dark",
    "euphoric": "euphoric",
    "uplifting": "euphoric",
    "energetic": "euphoric",
    "bright": "euphoric",
    "tense": "tense",
    "tension": "tense",
    "anxious": "tense",
    "dreamy": "dreamy",
    "ethereal": "dreamy",
    "atmospheric": "dreamy",
    "floaty": "dreamy",
    "hypnotic": "dreamy",
    "neutral": "neutral",
    "minimal": "neutral",
}

# Voicing / harmonic complexity keywords
_VOICING_KEYWORDS: dict[str, str] = {
    "extended": "extended",
    "9th": "extended",
    "9ths": "extended",
    "11th": "extended",
    "13th": "extended",
    "complex harmony": "extended",
    "rich harmony": "extended",
    "lush": "extended",
    "seventh": "seventh",
    "7th": "seventh",
    "7ths": "seventh",
    "maj7": "seventh",
    "min7": "seventh",
    "triads": "triads",
    "triad": "triads",
    "simple chords": "triads",
    "raw": "triads",
    "minimal chords": "triads",
}

# Genre keywords
_GENRE_KEYWORDS: set[str] = set(GENRE_PROGRESSIONS.keys())

# Melody characteristics keywords
_MELODY_KEYWORDS: dict[str, str] = {
    "stepwise": "stepwise",
    "conjunct": "stepwise",
    "smooth": "stepwise",
    "leaping": "leaping",
    "disjunct": "leaping",
    "arpeggiated": "arpeggiated",
    "arpeggio": "arpeggiated",
    "repetitive": "repetitive",
    "looping": "repetitive",
    "ostinato": "repetitive",
    "pentatonic": "pentatonic",
    "chromatic": "chromatic",
}

# Texture keywords (for production style context)
_TEXTURE_KEYWORDS: dict[str, str] = {
    "sparse": "sparse",
    "minimal": "sparse",
    "stripped": "sparse",
    "dense": "dense",
    "layered": "dense",
    "rich": "dense",
    "full": "dense",
    "hypnotic": "hypnotic",
    "repetitive": "hypnotic",
    "evolving": "evolving",
    "progressive": "evolving",
    "building": "evolving",
}


# ---------------------------------------------------------------------------
# ArtistStyle schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtistStyle:
    """
    Immutable musical style profile for an artist or genre.

    Extracted from RAG context chunks (YouTube deconstructions, articles,
    producer interviews) and used to inform chord progression and MIDI generation.

    Fields set to None indicate the information was not found in context.
    Fields with list type default to empty list when not found.

    Usage:
        style = ArtistStyle(
            artist="Sebastien Leger",
            genre="organic house",
            preferred_keys=["A", "D", "G"],
            preferred_modes=["natural minor", "dorian"],
            bpm_range=(120, 126),
            characteristic_moods=["dreamy", "dark"],
            voicing_style="extended",
            melody_characteristics=["stepwise", "repetitive"],
            texture=["evolving", "sparse"],
            confidence=0.72,
            chunk_count=5,
        )
    """

    artist: str
    genre: str | None

    # Harmonic profile
    preferred_keys: list[str] = field(default_factory=list)
    preferred_modes: list[str] = field(default_factory=list)

    # Rhythmic profile
    bpm_range: tuple[int, int] | None = None

    # Emotional palette
    characteristic_moods: list[str] = field(default_factory=list)

    # Chord complexity
    voicing_style: str | None = None  # "triads" | "seventh" | "extended"

    # Melodic profile
    melody_characteristics: list[str] = field(default_factory=list)

    # Production texture
    texture: list[str] = field(default_factory=list)

    # Meta
    confidence: float = 0.0  # 0.0–1.0: how much context supported this style
    chunk_count: int = 0  # Number of context chunks analyzed

    def to_suggestion_params(self) -> dict:
        """
        Convert ArtistStyle to parameters for suggest_chord_progression.

        Returns a dict with keys ready to pass to SuggestChordProgression:
            key, mood, genre, voicing

        Falls back to sensible defaults when fields are None/empty.

        Example:
            params = style.to_suggestion_params()
            result = tool(**params, bars=4)
        """
        # Pick best key: first preferred key + first preferred mode
        if self.preferred_keys and self.preferred_modes:
            key = f"{self.preferred_keys[0]} {self.preferred_modes[0]}"
        elif self.preferred_keys:
            key = f"{self.preferred_keys[0]} natural minor"
        elif self.preferred_modes:
            key = f"A {self.preferred_modes[0]}"
        else:
            key = "A natural minor"

        # Pick best mood
        mood = self.characteristic_moods[0] if self.characteristic_moods else "neutral"

        # Genre with fallback
        genre = self.genre or "organic house"

        # Voicing with fallback
        voicing = self.voicing_style or "auto"

        return {
            "key": key,
            "mood": mood,
            "genre": genre,
            "voicing": voicing,
        }

    def to_midi_params(self) -> dict:
        """
        Convert ArtistStyle to parameters for generate_midi_pattern.

        Returns a dict with keys: bpm, style
        (chord_names must come from suggest_chord_progression output).

        Falls back to genre defaults when bpm_range is None.
        """
        # Use midpoint of BPM range
        if self.bpm_range:
            bpm = (self.bpm_range[0] + self.bpm_range[1]) // 2
        else:
            bpm = 124  # organic house default

        return {
            "bpm": bpm,
            "style": self.genre or "organic house",
        }


# ---------------------------------------------------------------------------
# Pure extraction helpers
# ---------------------------------------------------------------------------


def extract_genre(chunks: list[str]) -> str | None:
    """
    Identify the most-mentioned genre across all chunks.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        Genre string if found (matching GENRE_PROGRESSIONS keys), else None
    """
    text = "\n".join(chunks).lower()
    counts: dict[str, int] = {}
    for genre in _GENRE_KEYWORDS:
        count = text.count(genre)
        if count > 0:
            counts[genre] = count
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def extract_keys(chunks: list[str]) -> list[str]:
    """
    Extract mentioned musical keys (pitch classes) from text chunks.

    Deduplicates results while preserving order of first occurrence.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        Ordered list of pitch class names (e.g. ["A", "D", "G"])
    """
    text = "\n".join(chunks).lower()
    found: list[str] = []
    seen: set[str] = set()
    for phrase, root in _KEY_KEYWORDS.items():
        if phrase in text and root not in seen:
            found.append(root)
            seen.add(root)
    # Also look for standalone note names (e.g. "key of A", "root A")
    for note in NOTE_NAMES:
        for pattern in (f"key of {note.lower()}", f"root {note.lower()}", f"in {note.lower()}"):
            if pattern in text and note not in seen:
                found.append(note)
                seen.add(note)
    return found


def extract_modes(chunks: list[str]) -> list[str]:
    """
    Extract mentioned scale modes from text chunks.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        Ordered list of mode strings (e.g. ["natural minor", "dorian"])
    """
    text = "\n".join(chunks).lower()
    found: list[str] = []
    seen: set[str] = set()
    # Check longer phrases first to avoid substring collisions (e.g. "natural minor" before "minor")
    for phrase in sorted(_MODE_KEYWORDS.keys(), key=len, reverse=True):
        mode = _MODE_KEYWORDS[phrase]
        if phrase in text and mode not in seen:
            found.append(mode)
            seen.add(mode)
    return found


def extract_bpm_range(chunks: list[str]) -> tuple[int, int] | None:
    """
    Extract BPM range from text chunks.

    Checks for explicit BPM numbers first (e.g. "120 bpm", "125bpm"),
    then falls back to descriptive phrases (e.g. "house tempo").

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        (min_bpm, max_bpm) tuple if found, else None
    """
    import re

    text = "\n".join(chunks).lower()

    # Try range pattern first: "122-126 bpm", "120 to 128 bpm"
    range_pattern = re.compile(r"\b(\d{2,3})\s*[-–to]+\s*(\d{2,3})\s*bpm\b")
    range_matches = range_pattern.findall(text)
    if range_matches:
        values = []
        for lo, hi in range_matches:
            lo_i, hi_i = int(lo), int(hi)
            if 60 <= lo_i <= 200:
                values.append(lo_i)
            if 60 <= hi_i <= 200:
                values.append(hi_i)
        if values:
            return (min(values), max(values))

    # Try to find explicit BPM values: "120 bpm", "124bpm", "at 126", etc.
    bpm_pattern = re.compile(r"\b(\d{2,3})\s*bpm\b")
    matches = bpm_pattern.findall(text)
    if matches:
        values = [int(m) for m in matches if 60 <= int(m) <= 200]
        if values:
            return (min(values), max(values))

    # Fall back to descriptive keywords
    for phrase, bpm_range in _BPM_RANGE_KEYWORDS.items():
        if phrase in text:
            return bpm_range

    return None


def extract_moods(chunks: list[str]) -> list[str]:
    """
    Extract emotional mood descriptors from text chunks.

    Only returns moods that are valid for suggest_chord_progression.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        Ordered list of mood strings (from VALID_MOODS_SET)
    """
    text = "\n".join(chunks).lower()
    found: list[str] = []
    seen: set[str] = set()
    for keyword, mood in _MOOD_KEYWORDS.items():
        if keyword in text and mood not in seen and mood in VALID_MOODS_SET:
            found.append(mood)
            seen.add(mood)
    return found


def extract_voicing(chunks: list[str]) -> str | None:
    """
    Extract chord voicing complexity from text chunks.

    Returns the most-mentioned voicing style.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        Voicing string ("triads" | "seventh" | "extended") or None
    """
    text = "\n".join(chunks).lower()
    counts: dict[str, int] = {"triads": 0, "seventh": 0, "extended": 0}
    for keyword, voicing in _VOICING_KEYWORDS.items():
        if keyword in text:
            counts[voicing] += text.count(keyword)
    total = sum(counts.values())
    if total == 0:
        return None
    return max(counts, key=lambda k: counts[k])


def extract_melody_characteristics(chunks: list[str]) -> list[str]:
    """
    Extract melodic profile descriptors from text chunks.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        List of melody characteristic strings
    """
    text = "\n".join(chunks).lower()
    found: list[str] = []
    seen: set[str] = set()
    for keyword, char in _MELODY_KEYWORDS.items():
        if keyword in text and char not in seen:
            found.append(char)
            seen.add(char)
    return found


def extract_texture(chunks: list[str]) -> list[str]:
    """
    Extract production texture descriptors from text chunks.

    Args:
        chunks: List of text chunks from knowledge base

    Returns:
        List of texture strings
    """
    text = "\n".join(chunks).lower()
    found: list[str] = []
    seen: set[str] = set()
    for keyword, texture in _TEXTURE_KEYWORDS.items():
        if keyword in text and texture not in seen:
            found.append(texture)
            seen.add(texture)
    return found


def compute_confidence(style: ArtistStyle) -> float:
    """
    Compute confidence score (0.0–1.0) for an ArtistStyle based on field coverage.

    Confidence reflects how much information was successfully extracted.
    Each field group contributes a weighted fraction.

    Weights:
        - genre found:              0.20
        - preferred_keys found:     0.20
        - preferred_modes found:    0.15
        - bpm_range found:          0.15
        - characteristic_moods:     0.15
        - voicing_style found:      0.10
        - melody_characteristics:   0.05

    Args:
        style: Partially or fully populated ArtistStyle

    Returns:
        Float in [0.0, 1.0]
    """
    score = 0.0
    if style.genre:
        score += 0.20
    if style.preferred_keys:
        score += 0.20
    if style.preferred_modes:
        score += 0.15
    if style.bpm_range:
        score += 0.15
    if style.characteristic_moods:
        score += 0.15
    if style.voicing_style:
        score += 0.10
    if style.melody_characteristics:
        score += 0.05
    return round(score, 2)


def build_artist_style(artist: str, chunks: list[str]) -> ArtistStyle:
    """
    Build an ArtistStyle from raw text chunks.

    Runs all extraction helpers and computes confidence.
    This is the main entry point for pure style extraction.

    Args:
        artist: Artist or producer name (used for metadata only)
        chunks: List of text chunks from knowledge base

    Returns:
        ArtistStyle with extracted fields and confidence score
    """
    genre = extract_genre(chunks)
    preferred_keys = extract_keys(chunks)
    preferred_modes = extract_modes(chunks)
    bpm_range = extract_bpm_range(chunks)
    characteristic_moods = extract_moods(chunks)
    voicing_style = extract_voicing(chunks)
    melody_characteristics = extract_melody_characteristics(chunks)
    texture = extract_texture(chunks)

    # Build partial style to compute confidence
    partial = ArtistStyle(
        artist=artist,
        genre=genre,
        preferred_keys=preferred_keys,
        preferred_modes=preferred_modes,
        bpm_range=bpm_range,
        characteristic_moods=characteristic_moods,
        voicing_style=voicing_style,
        melody_characteristics=melody_characteristics,
        texture=texture,
        confidence=0.0,  # placeholder
        chunk_count=len(chunks),
    )
    confidence = compute_confidence(partial)

    # Return final immutable style with computed confidence
    return ArtistStyle(
        artist=partial.artist,
        genre=partial.genre,
        preferred_keys=partial.preferred_keys,
        preferred_modes=partial.preferred_modes,
        bpm_range=partial.bpm_range,
        characteristic_moods=partial.characteristic_moods,
        voicing_style=partial.voicing_style,
        melody_characteristics=partial.melody_characteristics,
        texture=partial.texture,
        confidence=confidence,
        chunk_count=partial.chunk_count,
    )
