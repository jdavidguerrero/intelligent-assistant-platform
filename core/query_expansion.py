"""
Query expansion and intent detection for improved retrieval quality.

Implements domain-specific query expansion to improve semantic matching
for specialized music production queries (mastering, mixing, etc.).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryIntent:
    """Detected intent from a search query."""

    category: str  # "mastering", "mixing", "general"
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Matched keywords


def detect_mastering_intent(query: str) -> QueryIntent:
    """
    Detect if query is about mastering/mixing with keyword matching.

    Args:
        query: User search query

    Returns:
        QueryIntent with category, confidence, and matched keywords
    """
    query_lower = query.lower()

    # Mastering-specific keywords (high signal)
    mastering_keywords = [
        "mastering",
        "master",
        "mastering chain",
        "mastering process",
        "loudness",
        "limiting",
        "limiter",
        "final mix",
        "stereo widening",
        "multiband",
    ]

    # Mixing keywords (medium signal, often related to mastering)
    mixing_keywords = [
        "mixing",
        "mix",
        "eq",
        "equalization",
        "compression",
        "compressor",
        "sidechain",
        "reverb",
        "delay",
        "panning",
        "balance",
        "processing",
        "chain",
        "audio processing",
    ]

    matched_mastering = [kw for kw in mastering_keywords if kw in query_lower]
    matched_mixing = [kw for kw in mixing_keywords if kw in query_lower]

    # Determine category and confidence
    if matched_mastering:
        return QueryIntent(
            category="mastering",
            confidence=1.0,
            keywords=matched_mastering,
        )
    elif matched_mixing:
        # Mixing queries often map to mix-mastering category
        return QueryIntent(
            category="mixing",
            confidence=0.8,
            keywords=matched_mixing,
        )
    else:
        return QueryIntent(
            category="general",
            confidence=0.0,
            keywords=[],
        )


def expand_query(query: str, intent: QueryIntent) -> str:
    """
    Expand query with domain-specific terms based on detected intent.

    Args:
        query: Original search query
        intent: Detected intent from detect_mastering_intent()

    Returns:
        Expanded query string with additional context terms
    """
    # No expansion for general queries
    if intent.category == "general":
        return query

    # Add domain context terms based on intent
    expansion_terms: list[str] = []

    if intent.category == "mastering":
        expansion_terms = [
            "mastering",
            "final mix",
            "audio processing",
            "mixing",
        ]
    elif intent.category == "mixing":
        expansion_terms = [
            "mixing",
            "audio processing",
            "production",
        ]

    # Remove terms already in query (case-insensitive)
    query_lower = query.lower()
    unique_additions = [term for term in expansion_terms if term not in query_lower]

    if not unique_additions:
        return query

    # Append expansion terms (space-separated)
    expanded = f"{query} {' '.join(unique_additions)}"
    return expanded
