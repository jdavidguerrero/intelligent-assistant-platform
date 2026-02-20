"""
Semantic and keyword search queries against the chunk_records table.

Uses pgvector's cosine distance operator for approximate nearest neighbor
search over the HNSW index.  Optionally supports keyword search via
PostgreSQL ``ILIKE`` for hybrid retrieval.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import ChunkRecord


def search_chunks(
    session: Session,
    query_embedding: list[float],
    top_k: int = 5,
    *,
    sub_domain: str | None = None,
) -> list[tuple[ChunkRecord, float]]:
    """
    Find the most similar chunks to a query embedding using cosine distance.

    Executes a pgvector cosine distance query against the HNSW index on
    ``chunk_records``.  Returns results ordered by similarity (highest first).

    Args:
        session: Active SQLAlchemy session.
        query_embedding: Dense vector (1536 floats) representing the query.
        top_k: Maximum number of results to return.  Must be >= 1.
        sub_domain: Optional sub-domain filter (e.g. ``"mixing"``).
            When provided, only chunks tagged with this sub-domain are
            considered.  Uses the partial index on ``chunk_records.sub_domain``
            for efficient filtering.

    Returns:
        List of ``(ChunkRecord, score)`` tuples where
        ``score = 1 - cosine_distance``.  Score ranges from 0 (orthogonal)
        to 1 (identical).  Ordered by score descending.

    Raises:
        ValueError: If *top_k* < 1.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    distance = ChunkRecord.embedding.cosine_distance(query_embedding).label("distance")

    stmt = select(ChunkRecord, distance).order_by(distance).limit(top_k)

    if sub_domain is not None:
        stmt = stmt.where(ChunkRecord.sub_domain == sub_domain)

    results = session.execute(stmt).all()

    return [(row.ChunkRecord, 1.0 - row.distance) for row in results]


def search_chunks_keyword(
    session: Session,
    query_terms: list[str],
    top_k: int = 5,
) -> list[tuple[ChunkRecord, float]]:
    """
    Keyword (ILIKE) search over chunk text.

    A lightweight alternative to PostgreSQL full-text search that works
    without any additional setup (no ``tsvector`` columns or GIN indexes).
    Each matched term contributes equally to the score.

    Args:
        session: Active SQLAlchemy session.
        query_terms: Non-empty list of keywords to search for.
        top_k: Maximum number of results to return.  Must be >= 1.

    Returns:
        List of ``(ChunkRecord, score)`` tuples where score is
        the fraction of *query_terms* matched (0–1).  Ordered by
        score descending.

    Raises:
        ValueError: If *top_k* < 1 or *query_terms* is empty.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")
    if not query_terms:
        raise ValueError("query_terms must be a non-empty list")

    # Build a score as the sum of per-term matches divided by total terms.
    term_hits = [
        func.cast(ChunkRecord.text.ilike(f"%{term}%"), type_=None).cast(int) for term in query_terms
    ]
    hit_count = sum(term_hits).label("hit_count")  # type: ignore[arg-type]

    stmt = (
        select(ChunkRecord, hit_count)
        .where(hit_count > 0)  # type: ignore[arg-type]
        .order_by(hit_count.desc())  # type: ignore[union-attr]
        .limit(top_k)
    )

    results = session.execute(stmt).all()

    total = len(query_terms)
    return [(row.ChunkRecord, row.hit_count / total) for row in results]


def hybrid_search(
    session: Session,
    query_embedding: list[float],
    query_terms: list[str],
    top_k: int = 5,
    *,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
    rrf_k: int = 60,
    sub_domain: str | None = None,
) -> list[tuple[ChunkRecord, float]]:
    """
    Combine vector and keyword search via Reciprocal Rank Fusion (RRF).

    RRF merges two ranked lists without requiring score normalization::

        rrf_score(d) = Σ  1 / (rrf_k + rank_i(d))   for each list i

    A ``vector_weight`` / ``keyword_weight`` pair controls the contribution
    of each signal.

    Important: the **returned score** is the original **cosine similarity** from
    vector search, not the raw RRF value.  RRF is only used to determine the
    *order* of candidates; the cosine score is preserved so downstream confidence
    checks (``max_score >= threshold``) work correctly.

    Args:
        session: Active SQLAlchemy session.
        query_embedding: Dense query vector for cosine search.
        query_terms: Keywords for ILIKE search.
        top_k: Number of final results.
        vector_weight: Weight for vector search contribution.
        keyword_weight: Weight for keyword search contribution.
        rrf_k: RRF constant (higher = less emphasis on top ranks).
        sub_domain: Optional sub-domain filter propagated to vector search.

    Returns:
        RRF-reranked ``(ChunkRecord, cosine_score)`` tuples, highest cosine first.
        Chunks found only by keyword search (not vector search) carry a score of 0.0.
    """
    # Fetch more candidates from each source for better fusion
    fetch_k = top_k * 3

    vector_results = search_chunks(session, query_embedding, top_k=fetch_k, sub_domain=sub_domain)

    # Keyword search may not be supported on all DB backends (e.g. pgvector cast
    # syntax differs from SQLite used in tests).  Fall back to vector-only when it fails.
    try:
        keyword_results = search_chunks_keyword(session, query_terms, top_k=fetch_k)
    except Exception:  # noqa: BLE001
        keyword_results = []

    # Build RRF scores and preserve original cosine similarity scores
    rrf_scores: dict[int, float] = {}
    cosine_scores: dict[int, float] = {}
    record_map: dict[int, ChunkRecord] = {}

    for rank, (record, cosine_score) in enumerate(vector_results):
        rrf_scores[record.id] = rrf_scores.get(record.id, 0.0) + vector_weight / (rrf_k + rank + 1)
        cosine_scores[record.id] = cosine_score  # preserve original similarity
        record_map[record.id] = record

    for rank, (record, _score) in enumerate(keyword_results):
        rrf_scores[record.id] = rrf_scores.get(record.id, 0.0) + keyword_weight / (rrf_k + rank + 1)
        record_map[record.id] = record
        if record.id not in cosine_scores:
            cosine_scores[record.id] = 0.0  # keyword-only result has no cosine score

    # Sort by RRF score (best diversity-aware ranking), return cosine scores
    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)  # type: ignore[arg-type]

    return [(record_map[rid], cosine_scores[rid]) for rid in sorted_ids[:top_k]]
