"""
Semantic search queries against the chunk_records table.

Uses pgvector's cosine distance operator for approximate nearest neighbor
search over the HNSW index.
"""

from sqlalchemy import select
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
