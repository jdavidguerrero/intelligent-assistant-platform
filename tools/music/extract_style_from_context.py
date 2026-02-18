"""
extract_style_from_context tool — build an ArtistStyle from RAG context chunks.

This tool is the bridge between the knowledge base (retrieved chunks from
YouTube deconstructions, producer interviews, genre analyses) and the music
generation pipeline (suggest_chord_progression + generate_midi_pattern).

Pipeline position:
  search_by_genre(query="Sebastien Leger organic house style chords")
      → retrieves ranked context chunks from pgvector knowledge base
      → extract_style_from_context(chunks=chunks, artist="Sebastien Leger")
      → ArtistStyle(preferred_keys=["A","D"], voicing="extended", ...)
      → suggest_chord_progression(**style.to_suggestion_params(), bars=4)
      → generate_midi_pattern(chord_names=[...], **style.to_midi_params())

Key design decisions:
  - No LLM calls — pure keyword/pattern extraction from chunk text.
    This makes the tool deterministic, offline-capable, and testable.
  - Chunks are raw strings (as returned by search_by_genre's result.data["results"]).
  - confidence score (0-1) tells the caller how much info was found.
    Low confidence (<0.3) suggests calling search_by_genre with a broader query.
  - to_suggestion_params() / to_midi_params() on ArtistStyle provide
    a direct mapping to downstream tool parameters.

Example:
    tool = ExtractStyleFromContext()
    result = tool(
        chunks=[
            "Sebastien Leger is known for his dark, hypnotic organic house...",
            "Typically plays in A minor at 122-126 BPM with extended 9th chords...",
        ],
        artist="Sebastien Leger",
        genre_hint="organic house",
    )
    # result.data["style_params"] → ready for suggest_chord_progression
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.artist_style import ArtistStyle, build_artist_style

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

MIN_CHUNKS: int = 1
MAX_CHUNKS: int = 50
MAX_ARTIST_LEN: int = 100
MAX_CHUNK_LEN: int = 5000  # characters per chunk — longer chunks are truncated

# Minimum confidence to consider extraction "useful"
CONFIDENCE_THRESHOLD_LOW: float = 0.3
CONFIDENCE_THRESHOLD_HIGH: float = 0.7


class ExtractStyleFromContext(MusicalTool):
    """
    Extract musical style parameters from RAG context chunks.

    Analyzes text chunks retrieved from the knowledge base to identify:
    - Preferred keys and scale modes
    - Characteristic BPM range
    - Emotional moods
    - Chord voicing complexity
    - Melodic and textural characteristics

    Returns structured ArtistStyle data ready to feed into
    suggest_chord_progression and generate_midi_pattern.

    Designed to work offline (no LLM) — uses keyword matching and scoring
    for deterministic, testable extraction.

    Example:
        tool = ExtractStyleFromContext()
        result = tool(
            chunks=["Known for hypnotic organic house with dark 9th chord voicings..."],
            artist="Sebastien Leger",
        )
        # result.data["suggestion_params"] → pass directly to suggest_chord_progression
        # result.data["midi_params"] → pass directly to generate_midi_pattern
    """

    @property
    def name(self) -> str:
        return "extract_style_from_context"

    @property
    def description(self) -> str:
        return (
            "Extract musical style parameters from text chunks retrieved by search_by_genre. "
            "Analyzes RAG context (YouTube deconstructions, producer profiles, genre analyses) "
            "to identify preferred keys, modes, BPM range, moods, and chord voicing for an artist. "
            "Returns structured parameters ready to pass to suggest_chord_progression "
            "and generate_midi_pattern. "
            "Use when user asks for chords or MIDI 'in the style of' a specific artist or producer."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="chunks",
                type=list,
                description=(
                    "List of text chunks from the knowledge base, as returned by search_by_genre "
                    "result.data['results'][i]['content']. "
                    f"Must have {MIN_CHUNKS}–{MAX_CHUNKS} chunks. "
                    "Longer chunks are automatically truncated to avoid noise."
                ),
                required=True,
            ),
            ToolParameter(
                name="artist",
                type=str,
                description=(
                    "Artist or producer name to identify in context. "
                    "Used for metadata and logging only — does not affect extraction. "
                    f"Max {MAX_ARTIST_LEN} characters. "
                    "Examples: 'Sebastien Leger', 'Innellea', 'Rodriguez Jr.'"
                ),
                required=True,
            ),
            ToolParameter(
                name="genre_hint",
                type=str,
                description=(
                    "Optional genre hint to seed extraction if genre is not found in chunks. "
                    "Examples: 'organic house', 'melodic house', 'techno'. "
                    "Default: None (auto-detect from chunks)."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Extract musical style parameters from text chunks.

        Returns:
            ToolResult with:
                data:
                    artist_style:      Full ArtistStyle as dict
                    suggestion_params: Dict ready for suggest_chord_progression
                    midi_params:       Dict ready for generate_midi_pattern
                    confidence:        0.0–1.0 extraction confidence
                    confidence_label:  "high" | "medium" | "low"
                metadata:
                    chunk_count:       Number of chunks analyzed
                    genre:             Detected genre (or hint if not detected)
                    fields_found:      List of which fields were successfully extracted
        """
        chunks: list = kwargs.get("chunks") or []
        artist: str = (kwargs.get("artist") or "").strip()
        genre_hint: str = (kwargs.get("genre_hint") or "").strip().lower()

        # -------------------------------------------------------------------
        # Domain validation
        # -------------------------------------------------------------------
        if not chunks:
            return ToolResult(success=False, error="chunks cannot be empty")
        if not isinstance(chunks, list):
            return ToolResult(success=False, error="chunks must be a list of strings")
        if len(chunks) > MAX_CHUNKS:
            return ToolResult(
                success=False,
                error=f"chunks too large (max {MAX_CHUNKS} chunks, got {len(chunks)})",
            )
        if not artist:
            return ToolResult(success=False, error="artist cannot be empty")
        if len(artist) > MAX_ARTIST_LEN:
            return ToolResult(
                success=False,
                error=f"artist name too long (max {MAX_ARTIST_LEN} chars)",
            )

        # Validate chunks are strings — accept int/float but coerce, reject objects
        clean_chunks: list[str] = []
        for i, chunk in enumerate(chunks):
            if isinstance(chunk, str):
                clean_chunks.append(chunk[:MAX_CHUNK_LEN])
            elif isinstance(chunk, int | float):
                clean_chunks.append(str(chunk)[:MAX_CHUNK_LEN])
            else:
                return ToolResult(
                    success=False,
                    error=f"chunks[{i}] must be a string, got {type(chunk).__name__}",
                )

        # -------------------------------------------------------------------
        # Extract style from chunks
        # -------------------------------------------------------------------
        style = build_artist_style(artist=artist, chunks=clean_chunks)

        # Apply genre_hint if auto-detection failed
        if style.genre is None and genre_hint:
            style = ArtistStyle(
                artist=style.artist,
                genre=genre_hint,
                preferred_keys=style.preferred_keys,
                preferred_modes=style.preferred_modes,
                bpm_range=style.bpm_range,
                characteristic_moods=style.characteristic_moods,
                voicing_style=style.voicing_style,
                melody_characteristics=style.melody_characteristics,
                texture=style.texture,
                confidence=style.confidence,
                chunk_count=style.chunk_count,
            )

        # -------------------------------------------------------------------
        # Build response
        # -------------------------------------------------------------------
        confidence_label = _confidence_label(style.confidence)
        fields_found = _list_found_fields(style)

        # Serialize ArtistStyle to dict (frozen dataclass → plain dict)
        artist_style_dict = {
            "artist": style.artist,
            "genre": style.genre,
            "preferred_keys": style.preferred_keys,
            "preferred_modes": style.preferred_modes,
            "bpm_range": list(style.bpm_range) if style.bpm_range else None,
            "characteristic_moods": style.characteristic_moods,
            "voicing_style": style.voicing_style,
            "melody_characteristics": style.melody_characteristics,
            "texture": style.texture,
            "confidence": style.confidence,
            "chunk_count": style.chunk_count,
        }

        return ToolResult(
            success=True,
            data={
                "artist_style": artist_style_dict,
                "suggestion_params": style.to_suggestion_params(),
                "midi_params": style.to_midi_params(),
                "confidence": style.confidence,
                "confidence_label": confidence_label,
            },
            metadata={
                "chunk_count": len(clean_chunks),
                "genre": style.genre,
                "fields_found": fields_found,
                "confidence_threshold": CONFIDENCE_THRESHOLD_LOW,
            },
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _confidence_label(confidence: float) -> str:
    """
    Convert numeric confidence to human-readable label.

    Args:
        confidence: Float in [0.0, 1.0]

    Returns:
        "high" (≥ 0.7), "medium" (≥ 0.3), or "low" (< 0.3)
    """
    if confidence >= CONFIDENCE_THRESHOLD_HIGH:
        return "high"
    if confidence >= CONFIDENCE_THRESHOLD_LOW:
        return "medium"
    return "low"


def _list_found_fields(style: ArtistStyle) -> list[str]:
    """
    Return a list of field names that were successfully extracted.

    Args:
        style: ArtistStyle instance

    Returns:
        List of field name strings
    """
    found = []
    if style.genre:
        found.append("genre")
    if style.preferred_keys:
        found.append("preferred_keys")
    if style.preferred_modes:
        found.append("preferred_modes")
    if style.bpm_range:
        found.append("bpm_range")
    if style.characteristic_moods:
        found.append("characteristic_moods")
    if style.voicing_style:
        found.append("voicing_style")
    if style.melody_characteristics:
        found.append("melody_characteristics")
    if style.texture:
        found.append("texture")
    return found
