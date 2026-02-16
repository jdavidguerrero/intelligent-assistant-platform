"""
Shared type definitions for the chunking and retrieval system.

This module defines protocols and type aliases that establish contracts
between the pure core/ layer and impure layers (db/, ingestion/, api/).

Naming conventions:
- ChunkData: Pure, immutable chunk from core/chunking.py
- ChunkRecord: Database representation (db/models.py)
- ChunkDict: Dictionary form for serialization/API responses
"""

from typing import Protocol, TypedDict, runtime_checkable


class ChunkDict(TypedDict):
    """
    Dictionary representation of a chunk for serialization.

    Used for JSON responses and inter-layer data transfer.
    """

    doc_id: str
    source_path: str
    source_name: str
    chunk_index: int
    text: str
    token_start: int
    token_end: int


@runtime_checkable
class ChunkProtocol(Protocol):
    """
    Protocol defining the minimal interface for chunk-like objects.

    Both core.chunking.Chunk and db.models.Chunk should satisfy this protocol
    for their overlapping fields. This enables generic functions that work
    with either representation.
    """

    @property
    def doc_id(self) -> str: ...

    @property
    def chunk_index(self) -> int: ...

    @property
    def text(self) -> str: ...


def chunk_to_dict(
    chunk: ChunkProtocol,
    *,
    source_path: str | None = None,
    source_name: str | None = None,
    token_start: int | None = None,
    token_end: int | None = None,
) -> ChunkDict:
    """
    Convert a chunk-like object to a dictionary.

    For core.Chunk objects, all fields are available directly.
    For db.Chunk objects, some fields may need to be passed explicitly
    since the DB model uses different field names.

    Args:
        chunk: Any object satisfying ChunkProtocol.
        source_path: Override or provide source_path if not on chunk.
        source_name: Override or provide source_name if not on chunk.
        token_start: Override or provide token_start if not on chunk.
        token_end: Override or provide token_end if not on chunk.

    Returns:
        ChunkDict with all required fields.

    Raises:
        ValueError: If a required field is missing from both the chunk
            object and the explicit keyword arguments.
    """
    resolved_source_path = source_path or getattr(chunk, "source_path", None)
    if resolved_source_path is None:
        raise ValueError("source_path is required: not found on chunk and not provided as argument")

    resolved_source_name = source_name or getattr(chunk, "source_name", None)
    if resolved_source_name is None:
        raise ValueError("source_name is required: not found on chunk and not provided as argument")

    resolved_token_start = (
        token_start if token_start is not None else getattr(chunk, "token_start", None)
    )
    if resolved_token_start is None:
        raise ValueError("token_start is required: not found on chunk and not provided as argument")

    resolved_token_end = token_end if token_end is not None else getattr(chunk, "token_end", None)
    if resolved_token_end is None:
        raise ValueError("token_end is required: not found on chunk and not provided as argument")

    return ChunkDict(
        doc_id=chunk.doc_id,
        source_path=resolved_source_path,
        source_name=resolved_source_name,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        token_start=resolved_token_start,
        token_end=resolved_token_end,
    )
