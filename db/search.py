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
) -> list[tuple[ChunkRecord, float]]:
    """
    Find the most similar chunks to a query embedding using cosine distance.

    Executes a pgvector cosine distance query against the HNSW index on
    ``chunk_records``.  Returns results ordered by similarity (highest first).

    Args:
        session: Active SQLAlchemy session.
        query_embedding: Dense vector (1536 floats) representing the query.
        top_k: Maximum number of results to return.  Must be >= 1.

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
) -> list[tuple[ChunkRecord, float]]:
    """
    Combine vector and keyword search via Reciprocal Rank Fusion (RRF).

    RRF merges two ranked lists without requiring score normalization::

        rrf_score(d) = Σ  1 / (rrf_k + rank_i(d))   for each list i

    A ``vector_weight`` / ``keyword_weight`` pair controls the contribution
    of each signal.

    Args:
        session: Active SQLAlchemy session.
        query_embedding: Dense query vector for cosine search.
        query_terms: Keywords for ILIKE search.
        top_k: Number of final results.
        vector_weight: Weight for vector search contribution.
        keyword_weight: Weight for keyword search contribution.
        rrf_k: RRF constant (higher = less emphasis on top ranks).

    Returns:
        Fused ``(ChunkRecord, rrf_score)`` tuples, highest first.
    """
    # Fetch more candidates from each source for better fusion
    fetch_k = top_k * 3

    vector_results = search_chunks(session, query_embedding, top_k=fetch_k)
    keyword_results = search_chunks_keyword(session, query_terms, top_k=fetch_k)

    # Build RRF scores keyed by ChunkRecord.id
    rrf_scores: dict[int, float] = {}
    record_map: dict[int, ChunkRecord] = {}

    for rank, (record, _score) in enumerate(vector_results):
        rrf_scores[record.id] = rrf_scores.get(record.id, 0.0) + vector_weight / (rrf_k + rank + 1)
        record_map[record.id] = record

    for rank, (record, _score) in enumerate(keyword_results):
        rrf_scores[record.id] = rrf_scores.get(record.id, 0.0) + keyword_weight / (rrf_k + rank + 1)
        record_map[record.id] = record

    # Sort by fused score descending
    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)  # type: ignore[arg-type]

    return [(record_map[rid], rrf_scores[rid]) for rid in sorted_ids[:top_k]]
