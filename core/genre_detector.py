"""
Genre detector for music production queries.

Pure module — no I/O, no side effects, no network.
Given a query string, returns the detected genre or None.

Used by the /ask pipeline to load the appropriate recipe
and inject it as genre_context into the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Genre keyword maps
# ---------------------------------------------------------------------------
# Each genre has a set of keywords that signal intent.
# Multiple matches increase confidence.

_GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "organic house": (
        "organic house",
        "organic",
        "tribal house",
        "afro house",
        "melodic organic",
        "balearic",
    ),
    "melodic house": (
        "melodic house",
        "melodic deep",
        "melodic techno house",
    ),
    "progressive house": (
        "progressive house",
        "prog house",
        "progressive",
    ),
    "deep house": (
        "deep house",
        "deep tech",
        "deep groove",
    ),
    "melodic techno": (
        "melodic techno",
        "melodic dark techno",
        "tale of us",
        "innervisions",
    ),
    "techno": (
        "techno",
        "industrial techno",
        "peak time techno",
        "raw techno",
        "berlin techno",
    ),
    "acid": (
        "acid house",
        "acid techno",
        "acid",
        "303",
        "squelch",
    ),
}

# Recipe filename mapping: genre name → markdown file stem
GENRE_RECIPE_FILES: dict[str, str] = {
    "organic house": "organic_house",
    "progressive house": "progressive_house",
    "melodic techno": "melodic_techno",
    "deep house": "deep_house",
}


@dataclass(frozen=True)
class GenreDetectionResult:
    """Result of genre detection from a query string.

    Attributes:
        query:          Lowercased input query.
        genre:          Best-match genre name, or None if not detected.
        votes:          Vote count per genre.
        has_recipe:     Whether a recipe file exists for the detected genre.
        recipe_file:    Filename stem of the recipe (without .md), or None.
    """

    query: str
    genre: str | None
    votes: dict[str, int]
    has_recipe: bool
    recipe_file: str | None


def detect_genre(query: str) -> GenreDetectionResult:
    """Detect the music genre mentioned in a query.

    Scans the query for genre-specific keywords using a simple voting
    mechanism. The genre with the most keyword matches wins. In the case
    of a tie, the genre with the longer keyword match is preferred.

    Args:
        query: User query string. Case-insensitive.

    Returns:
        GenreDetectionResult with the best-match genre and metadata.
    """
    query_lower = query.lower()
    votes: dict[str, int] = {}

    for genre, keywords in _GENRE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in query_lower)
        votes[genre] = count

    # Find the winner: highest vote count
    max_votes = max(votes.values(), default=0)

    if max_votes == 0:
        return GenreDetectionResult(
            query=query_lower,
            genre=None,
            votes=votes,
            has_recipe=False,
            recipe_file=None,
        )

    # Among genres with max votes, prefer the one with the longer keyword match
    # (e.g. "organic house" beats "organic" when both appear)
    candidates = [g for g, v in votes.items() if v == max_votes]
    winner = max(
        candidates,
        key=lambda g: max((len(kw) for kw in _GENRE_KEYWORDS[g] if kw in query_lower), default=0),
    )

    recipe_file = GENRE_RECIPE_FILES.get(winner)
    return GenreDetectionResult(
        query=query_lower,
        genre=winner,
        votes=votes,
        has_recipe=recipe_file is not None,
        recipe_file=recipe_file,
    )
