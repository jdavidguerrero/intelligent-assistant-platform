"""REST endpoints for musical memory management."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_embedding_provider, get_memory_store
from api.schemas.memory import (
    CreateMemoryRequest,
    MemoryEntryResponse,
    MemoryListResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from core.memory.types import MemoryType
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.memory_store import MemoryStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])

MemStore = Annotated[MemoryStore, Depends(get_memory_store)]
Embedder = Annotated[OpenAIEmbeddingProvider, Depends(get_embedding_provider)]


def _to_response(entry: MemoryStore) -> MemoryEntryResponse:  # type: ignore[valid-type]
    """Convert a MemoryEntry to a MemoryEntryResponse."""
    return MemoryEntryResponse(
        memory_id=entry.memory_id,  # type: ignore[union-attr]
        memory_type=entry.memory_type,  # type: ignore[union-attr]
        content=entry.content,  # type: ignore[union-attr]
        created_at=entry.created_at,  # type: ignore[union-attr]
        updated_at=entry.updated_at,  # type: ignore[union-attr]
        pinned=entry.pinned,  # type: ignore[union-attr]
        tags=list(entry.tags),  # type: ignore[union-attr]
        source=entry.source,  # type: ignore[union-attr]
    )


@router.get("/", response_model=MemoryListResponse)
def list_memories(
    memory_type: MemoryType | None = None,
    store: MemStore = ...,  # type: ignore[assignment]
) -> MemoryListResponse:
    """List all memory entries, optionally filtered by type."""
    entries = store.list_by_type(memory_type) if memory_type else store.list_all()
    return MemoryListResponse(entries=[_to_response(e) for e in entries], total=len(entries))


@router.post("/", response_model=MemoryEntryResponse, status_code=201)
def create_memory(
    body: CreateMemoryRequest,
    store: MemStore = ...,  # type: ignore[assignment]
    embedder: Embedder = ...,  # type: ignore[assignment]
) -> MemoryEntryResponse:
    """Create a memory entry manually. Embeds content for semantic search."""
    now = datetime.now(UTC)
    entry = store.create_entry(
        memory_type=body.memory_type,
        content=body.content,
        now=now,
        tags=tuple(body.tags),
        source="manual",
        pinned=body.pinned,
    )
    try:
        embeddings = embedder.embed_texts([body.content])
        embedding = embeddings[0] if embeddings else None
    except Exception:
        logger.warning("Failed to embed memory content — saving without embedding")
        embedding = None
    store.save(entry, embedding=embedding)
    return _to_response(entry)


# NOTE: /search POST route is defined BEFORE /{memory_id} GET to ensure FastAPI
# matches the literal path "search" correctly and not as a path parameter.


@router.post("/search", response_model=MemoryListResponse)
def search_memories(
    body: MemorySearchRequest,
    store: MemStore = ...,  # type: ignore[assignment]
    embedder: Embedder = ...,  # type: ignore[assignment]
) -> MemoryListResponse:
    """Find memories semantically relevant to a query."""
    try:
        embeddings = embedder.embed_texts([body.query])
        query_emb = embeddings[0]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from exc

    now = datetime.now(UTC)
    results = store.search_relevant(
        query_embedding=query_emb,
        now=now,
        top_k=body.top_k,
        memory_types=list(body.memory_types) if body.memory_types else None,
    )
    entries = [e for e, _ in results]
    return MemoryListResponse(entries=[_to_response(e) for e in entries], total=len(entries))


@router.get("/{memory_id}", response_model=MemoryEntryResponse)
def get_memory(
    memory_id: str,
    store: MemStore = ...,  # type: ignore[assignment]
) -> MemoryEntryResponse:
    """Fetch a single memory entry by ID."""
    entry = store.get(memory_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id!r}")
    return _to_response(entry)


@router.patch("/{memory_id}", response_model=MemoryEntryResponse)
def update_memory(
    memory_id: str,
    body: UpdateMemoryRequest,
    store: MemStore = ...,  # type: ignore[assignment]
    embedder: Embedder = ...,  # type: ignore[assignment]
) -> MemoryEntryResponse:
    """Update memory content and re-embed for semantic search."""
    try:
        updated = store.update(memory_id, body.content, datetime.now(UTC))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        embeddings = embedder.embed_texts([body.content])
        embedding = embeddings[0] if embeddings else None
        if embedding:
            store.save(updated, embedding=embedding)
    except Exception:
        logger.warning("Re-embedding failed after update — search may be stale")
    return _to_response(updated)


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    store: MemStore = ...,  # type: ignore[assignment]
) -> None:
    """Permanently delete a memory entry."""
    deleted = store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id!r}")


@router.post("/{memory_id}/pin", response_model=MemoryEntryResponse)
def pin_memory(
    memory_id: str,
    store: MemStore = ...,  # type: ignore[assignment]
) -> MemoryEntryResponse:
    """Pin a memory so it never decays regardless of type."""
    ok = store.set_pinned(memory_id, True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id!r}")
    entry = store.get(memory_id)
    assert entry is not None
    return _to_response(entry)


@router.delete("/{memory_id}/pin", response_model=MemoryEntryResponse)
def unpin_memory(
    memory_id: str,
    store: MemStore = ...,  # type: ignore[assignment]
) -> MemoryEntryResponse:
    """Unpin a memory, re-enabling decay."""
    ok = store.set_pinned(memory_id, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id!r}")
    entry = store.get(memory_id)
    assert entry is not None
    return _to_response(entry)
