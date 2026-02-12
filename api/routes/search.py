"""
Search route for semantic similarity queries.

``POST /search`` — embed query, search pgvector, return ranked results.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider
from api.schemas.search import ResponseMeta, SearchRequest, SearchResponse, SearchResult
from core.query_expansion import detect_mastering_intent, expand_query
from db.rerank import rerank_results
from db.search import search_chunks
from ingestion.embeddings import OpenAIEmbeddingProvider

router = APIRouter(tags=["search"])

DbSession = Annotated[Session, Depends(get_db)]
Embedder = Annotated[OpenAIEmbeddingProvider, Depends(get_embedding_provider)]


@router.post("/search", response_model=SearchResponse)
def search(
    body: SearchRequest,
    db: DbSession,
    embedder: Embedder,
) -> SearchResponse:
    """
    Perform semantic search over ingested document chunks.

    Embeds the query text, runs cosine similarity search against pgvector,
    and returns the top-k most similar chunks with their scores.
    """
    t_start = time.perf_counter()

    # 1. Query expansion: detect intent and expand if needed
    intent = detect_mastering_intent(body.query)
    expanded_query = expand_query(body.query, intent)

    # 2. Embed the (possibly expanded) query text (with caching)
    t_embed = time.perf_counter()
    try:
        embeddings = embedder.embed_texts([expanded_query])
        query_embedding = embeddings[0]
        cache_hit = embedder.last_cache_hit
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate query embedding.",
        ) from exc
    embedding_ms = (time.perf_counter() - t_embed) * 1000

    # 3. Search the database (fetch 3x for reranking diversity)
    t_search = time.perf_counter()
    try:
        raw_results = search_chunks(db, query_embedding, top_k=body.top_k * 3)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Search query failed.",
        ) from exc

    # 4. Apply reranking: authority boost + filename boost + document diversity
    # Add filename boosting for mastering/mixing queries
    filename_keywords = None
    if intent.category in ("mastering", "mixing"):
        filename_keywords = ["mastering", "mixing", "masterclass", "mix-mastering"]

    reranked = rerank_results(
        raw_results,
        top_k=body.top_k,
        max_per_document=1,  # Full diversity: 1 chunk per document
        course_boost=1.15,   # +15% boost for course content
        youtube_boost=1.0,   # No boost for YouTube
        filename_keywords=filename_keywords,
        filename_boost=1.20,  # +20% boost for filename matches
    )

    search_ms = (time.perf_counter() - t_search) * 1000

    # 5. Filter by minimum similarity score
    above_threshold = [(rec, sc) for rec, sc in reranked if sc >= body.min_score]

    # 6. Build response
    search_results = [
        SearchResult(
            score=round(score, 6),
            text=record.text,
            source_name=record.source_name,
            source_path=record.source_path,
            chunk_index=record.chunk_index,
            token_start=record.token_start,
            token_end=record.token_end,
        )
        for record, score in above_threshold
    ]

    reason = "low_confidence" if reranked and not above_threshold else None
    total_ms = (time.perf_counter() - t_start) * 1000

    return SearchResponse(
        query=body.query,
        top_k=body.top_k,
        results=search_results,
        reason=reason,
        meta=ResponseMeta(
            embedding_ms=round(embedding_ms, 2),
            search_ms=round(search_ms, 2),
            total_ms=round(total_ms, 2),
            cache_hit=cache_hit,
        ),
    )
