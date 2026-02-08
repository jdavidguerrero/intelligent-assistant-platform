"""
Search route for semantic similarity queries.

``POST /search`` — embed query, search pgvector, return ranked results.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider
from api.schemas.search import SearchRequest, SearchResponse, SearchResult
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
    # 1. Embed the query text
    try:
        embeddings = embedder.embed_texts([body.query])
        query_embedding = embeddings[0]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate query embedding.",
        ) from exc

    # 2. Search the database
    try:
        results = search_chunks(db, query_embedding, top_k=body.top_k)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Search query failed.",
        ) from exc

    # 3. Build response
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
        for record, score in results
    ]

    return SearchResponse(
        query=body.query,
        top_k=body.top_k,
        results=search_results,
    )
