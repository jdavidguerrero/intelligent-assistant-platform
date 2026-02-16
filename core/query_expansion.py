"""
Query expansion and intent detection for improved retrieval quality.

Implements domain-specific query expansion to improve semantic matching
for specialized music production queries (mastering, mixing, etc.).

Design:
    - ``DomainConfig`` defines each domain's keywords, expansion terms,
      and scoring metadata — open/closed principle.
    - ``detect_intents()`` returns *all* matching domains (multi-intent),
      sorted by weighted score.
    - ``expand_query()`` uses the top-ranked intent(s) for expansion.
    - The old ``detect_mastering_intent()`` is kept for backward compat.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryIntent:
    """Detected intent from a search query."""

    category: str  # domain name (e.g. "mastering", "mixing", "general")
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Matched keywords


@dataclass(frozen=True)
class DomainConfig:
    """Configuration for a single domain in the intent registry.

    Attributes:
        name: Domain identifier (e.g. ``"mastering"``).
        keywords: Positive-signal keywords to match in query.
        expansion_terms: Terms appended to the query when this domain matches.
        base_confidence: Maximum confidence when all keywords match.
        negative_keywords: Keywords that *exclude* this domain if present.
    """

    name: str
    keywords: list[str]
    expansion_terms: list[str]
    base_confidence: float = 1.0
    negative_keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Intent registry — add new domains here, no function changes required
# ---------------------------------------------------------------------------

DOMAIN_REGISTRY: list[DomainConfig] = [
    DomainConfig(
        name="mastering",
        keywords=[
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
        ],
        expansion_terms=[
            "mastering",
            "final mix",
            "audio processing",
            "mixing",
        ],
        base_confidence=1.0,
        negative_keywords=[
            "python",
            "java",
            "coding",
            "programming",
            "git",
            "docker",
        ],
    ),
    DomainConfig(
        name="mixing",
        keywords=[
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
        ],
        expansion_terms=[
            "mixing",
            "audio processing",
            "production",
        ],
        base_confidence=0.8,
        negative_keywords=[
            "python",
            "java",
            "coding",
            "programming",
            "git",
            "docker",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def _score_domain(query_lower: str, domain: DomainConfig) -> QueryIntent | None:
    """Score a single domain against the query.

    Returns ``None`` if no keywords matched or a negative keyword is present.
    Otherwise returns a ``QueryIntent`` with confidence proportional to the
    fraction of keywords matched, scaled by ``domain.base_confidence``.
    """
    # Check negative keywords first
    for neg in domain.negative_keywords:
        if neg in query_lower:
            return None

    matched = [kw for kw in domain.keywords if kw in query_lower]
    if not matched:
        return None

    # Confidence = (matched / total) * base_confidence
    ratio = len(matched) / len(domain.keywords)
    confidence = round(min(1.0, ratio * domain.base_confidence), 4)

    return QueryIntent(
        category=domain.name,
        confidence=confidence,
        keywords=matched,
    )


def detect_intents(
    query: str,
    *,
    domains: list[DomainConfig] | None = None,
) -> list[QueryIntent]:
    """Detect *all* matching intents for a query, sorted by confidence desc.

    This is the **multi-intent** replacement for ``detect_mastering_intent``.

    Args:
        query: User search query.  Must be non-empty.
        domains: Optional override of the domain registry.

    Returns:
        Sorted list of ``QueryIntent`` (highest confidence first).
        Empty list when no domain matches → treat as ``"general"``.

    Raises:
        ValueError: If *query* is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    registry = domains if domains is not None else DOMAIN_REGISTRY
    query_lower = query.lower()

    intents: list[QueryIntent] = []
    for domain in registry:
        intent = _score_domain(query_lower, domain)
        if intent is not None:
            intents.append(intent)

    # Sort by confidence descending, then by category name for determinism
    intents.sort(key=lambda i: (-i.confidence, i.category))
    return intents


def detect_mastering_intent(query: str) -> QueryIntent:
    """Detect if query is about mastering/mixing with keyword matching.

    Backward-compatible wrapper around ``detect_intents()``.

    Args:
        query: User search query.

    Returns:
        Single ``QueryIntent`` — the top match, or a ``"general"`` fallback.
    """
    if not query or not query.strip():
        return QueryIntent(category="general", confidence=0.0, keywords=[])

    intents = detect_intents(query)

    if intents:
        return intents[0]

    return QueryIntent(category="general", confidence=0.0, keywords=[])


def expand_query(query: str, intent: QueryIntent) -> str:
    """Expand query with domain-specific terms based on detected intent.

    Looks up the intent's category in ``DOMAIN_REGISTRY`` to find the
    matching expansion terms.  Falls back to no expansion if the domain
    is ``"general"`` or not found.

    Args:
        query: Original search query.
        intent: Detected intent (from ``detect_mastering_intent`` or
            ``detect_intents``).

    Returns:
        Expanded query string with additional context terms appended.

    Raises:
        ValueError: If *query* is ``None``.
    """
    if query is None:
        raise ValueError("query must not be None")

    if intent.category == "general":
        return query

    # Find expansion terms from registry
    expansion_terms: list[str] = []
    for domain in DOMAIN_REGISTRY:
        if domain.name == intent.category:
            expansion_terms = domain.expansion_terms
            break

    if not expansion_terms:
        return query

    # Remove terms already in query (case-insensitive)
    query_lower = query.lower()
    unique_additions = [term for term in expansion_terms if term not in query_lower]

    if not unique_additions:
        return query

    return f"{query} {' '.join(unique_additions)}"
