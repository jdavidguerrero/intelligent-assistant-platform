"""
search_by_genre tool — genre-filtered knowledge base retrieval.

Combines two signals:
1. Metadata filter: source_path / source_name / text contains genre keywords
2. Semantic ranking: cosine similarity via pgvector

This hybrid approach is more precise than pure semantic search for genre
queries because "organic house" as a source metadata tag is a stronger
signal than embedding similarity alone.
"""

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import ChunkRecord
from db.search import search_chunks
from db.session import get_session
from tools.base import MusicalTool, ToolParameter, ToolResult

# Domain validation bounds
MAX_GENRE_LENGTH = 100
MAX_QUERY_LENGTH = 500
MIN_TOP_K = 1
MAX_TOP_K = 20

# Known genre synonyms and aliases for query expansion
_GENRE_ALIASES: dict[str, list[str]] = {
    "organic house": ["organic", "organic house", "all day i dream", "adid"],
    "melodic house": ["melodic house", "melodic techno", "lane 8", "anjunadeep"],
    "progressive house": ["progressive house", "progressive", "sultan", "shepard"],
    "techno": ["techno", "industrial", "berghain"],
    "deep house": ["deep house", "deep", "soulful"],
    "acid": ["acid", "303", "acid house", "acid techno"],
}


class SearchByGenre(MusicalTool):
    """
    Search the music production knowledge base filtered by genre.

    Combines metadata filtering (source_path/text contains genre keywords)
    with semantic vector search to surface the most relevant lessons,
    PDFs, and YouTube transcripts for a specific genre.

    Use when the user asks about a specific genre style, production
    technique within a genre, or wants to find genre-specific lessons.

    Example:
        tool = SearchByGenre()
        result = tool(genre="organic house", query="chord progressions", top_k=5)
        # Returns chunks from YouTube transcripts and Pete Tong lessons
        # about organic house chord progressions, ranked by relevance
    """

    def __init__(self, session_factory: Any = None) -> None:
        """
        Args:
            session_factory: SQLAlchemy session factory. Defaults to get_session().
                             Inject a mock session in tests.
        """
        self._session_factory = session_factory or get_session

    @property
    def name(self) -> str:
        return "search_by_genre"

    @property
    def description(self) -> str:
        return (
            "Search the music production knowledge base for a specific genre. "
            "Returns lessons, guides, and transcripts filtered by genre style "
            "(e.g., organic house, melodic techno, progressive house, deep house). "
            "Use when the user asks about production techniques for a specific genre."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Music genre to filter by "
                    "(e.g., 'organic house', 'melodic techno', 'progressive house')"
                ),
                required=True,
            ),
            ToolParameter(
                name="query",
                type=str,
                description=(
                    "Optional specific question or topic within the genre "
                    "(e.g., 'chord progressions', 'mixing kick'). "
                    "If omitted, returns the most relevant general content."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="top_k",
                type=int,
                description=f"Number of results to return ({MIN_TOP_K}–{MAX_TOP_K}). Default: 5",
                required=False,
                default=5,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Search knowledge base filtered by genre.

        Args:
            genre: Genre to filter by
            query: Specific topic/question within the genre (optional)
            top_k: Number of results (1-20)

        Returns:
            ToolResult with list of matched chunks, scores, and sources
        """
        genre: str = (kwargs.get("genre") or "").strip()
        query: str = (kwargs.get("query") or "").strip()
        top_k: int = kwargs.get("top_k") or 5

        # Domain validation
        if not genre:
            return ToolResult(success=False, error="genre cannot be empty")
        if len(genre) > MAX_GENRE_LENGTH:
            return ToolResult(
                success=False,
                error=f"genre too long (max {MAX_GENRE_LENGTH} chars)",
            )
        if len(query) > MAX_QUERY_LENGTH:
            return ToolResult(
                success=False,
                error=f"query too long (max {MAX_QUERY_LENGTH} chars)",
            )
        if top_k < MIN_TOP_K or top_k > MAX_TOP_K:
            return ToolResult(
                success=False,
                error=f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}",
            )

        # Expand genre to aliases for broader matching
        genre_terms = _expand_genre(genre)

        # Build effective query: genre + specific question if provided
        effective_query = f"{genre} {query}".strip() if query else genre

        try:
            session: Session = next(self._session_factory())
            try:
                results = _genre_search(
                    session=session,
                    genre_terms=genre_terms,
                    effective_query=effective_query,
                    top_k=top_k,
                )
            finally:
                session.close()
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Database search failed: {str(e)}",
            )

        # Format results
        chunks = [
            {
                "index": i + 1,
                "source_name": record.source_name,
                "source_path": record.source_path,
                "score": round(score, 4),
                "text_preview": record.text[:200].strip(),
                "page_number": record.page_number,
            }
            for i, (record, score) in enumerate(results)
        ]

        return ToolResult(
            success=True,
            data={
                "genre": genre,
                "query": query,
                "results": chunks,
                "total_found": len(chunks),
            },
            metadata={
                "genre_terms": genre_terms,
                "effective_query": effective_query,
            },
        )


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def _expand_genre(genre: str) -> list[str]:
    """
    Expand a genre name to known aliases for broader matching.

    Pure function — no I/O.

    Args:
        genre: Raw genre string from user

    Returns:
        List of genre terms to match against (always includes original)
    """
    genre_lower = genre.lower().strip()

    # Check for known aliases
    for canonical, aliases in _GENRE_ALIASES.items():
        if genre_lower in canonical or canonical in genre_lower:
            return aliases

    # Unknown genre: use the genre itself + individual words
    words = genre_lower.split()
    terms = [genre_lower] + words
    return list(dict.fromkeys(terms))  # deduplicate preserving order


def _genre_search(
    session: Session,
    genre_terms: list[str],
    effective_query: str,
    top_k: int,
) -> list[tuple[ChunkRecord, float]]:
    """
    Execute genre-filtered semantic search.

    Strategy:
        1. Filter candidates where source_path OR source_name OR text
           contains any genre term (ILIKE)
        2. Among candidates, rank by cosine similarity to effective_query embedding
        3. If no filtered candidates, fall back to pure semantic search

    Args:
        session: Active SQLAlchemy session
        genre_terms: List of genre terms to filter on
        effective_query: Combined genre + query string for embedding
        top_k: Number of results to return

    Returns:
        List of (ChunkRecord, score) tuples
    """
    from ingestion.embeddings import create_embedding_provider

    # Embed the effective query
    provider = create_embedding_provider()
    query_embedding = provider.embed([effective_query])[0]

    # Build genre filter: source_path OR source_name OR text contains any term
    genre_filters = []
    for term in genre_terms:
        genre_filters.extend(
            [
                ChunkRecord.source_path.ilike(f"%{term}%"),
                ChunkRecord.source_name.ilike(f"%{term}%"),
                ChunkRecord.text.ilike(f"%{term}%"),
            ]
        )

    # Fetch genre-filtered candidates (fetch more to rank by similarity)
    fetch_k = min(top_k * 5, 100)
    from sqlalchemy import select

    filter_stmt = select(ChunkRecord).where(or_(*genre_filters)).limit(fetch_k)
    candidates = session.execute(filter_stmt).scalars().all()

    if not candidates:
        # Fallback: pure semantic search (no genre filter)
        return search_chunks(session, query_embedding, top_k=top_k)

    # Rank candidates by cosine similarity to query embedding
    import numpy as np

    q_vec = np.array(query_embedding, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)

    scored: list[tuple[ChunkRecord, float]] = []
    for record in candidates:
        c_vec = np.array(record.embedding, dtype=np.float32)
        c_norm = np.linalg.norm(c_vec)
        if q_norm > 0 and c_norm > 0:
            score = float(np.dot(q_vec, c_vec) / (q_norm * c_norm))
        else:
            score = 0.0
        scored.append((record, score))

    # Sort by similarity descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
