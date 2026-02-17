"""
Pure chunking module for RAG document processing.

This module provides token-based text chunking functionality without any side effects,
database operations, or network calls. It is designed to be deterministic and testable.

WHY TOKEN-BASED CHUNKING?
-------------------------
Token chunking is preferred over character chunking for several critical reasons:

1. **Model alignment**: LLMs process text as tokens, not characters. A chunk of 512 tokens
   maps directly to model context limits, while 512 characters could be anywhere from
   ~100 to ~500 tokens depending on content.

2. **Predictable context usage**: When you set chunk_size=512 tokens, you know exactly
   how much of the model's context window each chunk will consume. Character-based
   chunking provides no such guarantee.

3. **Consistent semantic density**: Tokens roughly correspond to semantic units (words,
   subwords). A 512-token chunk contains approximately the same amount of "meaning"
   regardless of whether the text uses short or long words.

4. **Accurate overlap control**: Overlap of 50 tokens means 50 tokens of shared context,
   ensuring retrieval doesn't miss information at chunk boundaries. Character overlap
   might cut words in half or provide inconsistent semantic overlap.

5. **Embedding quality**: Embedding models also tokenize internally. Chunking at token
   boundaries ensures the text you embed is exactly what the model processes, avoiding
   edge cases where character boundaries create unexpected token splits.
"""

import hashlib
from dataclasses import dataclass
from typing import overload

import tiktoken

from core.config import ChunkingConfig


def _generate_doc_id(source_path: str, text: str) -> str:
    """
    Generate a stable document ID from source path and content hash.

    Uses SHA-256 of (source_path + text) to create a deterministic identifier.
    """
    content = f"{source_path}:{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Chunk:
    """
    Immutable representation of a text chunk from a document.

    All fields are frozen to ensure chunks are hashable and can be safely
    used in sets or as dict keys.

    Attributes:
        doc_id: Unique identifier for the source document. If not provided
            during chunking, derived from sha256(source_path + text).
        source_path: Full path to the source file.
        source_name: Basename of the source file (derived from source_path).
        chunk_index: Zero-based position of this chunk within the document.
        text: The actual text content of this chunk.
        token_start: Starting token index in the original document (inclusive).
        token_end: Ending token index in the original document (exclusive).
        page_number: Page number in the source PDF (1-based). ``None`` for
            non-paginated formats like Markdown or plain text.
    """

    doc_id: str
    source_path: str
    source_name: str
    chunk_index: int
    text: str
    token_start: int
    token_end: int
    page_number: int | None = None


@overload
def chunk_text(
    text: str,
    *,
    source_path: str,
    doc_id: str | None = None,
    config: ChunkingConfig,
) -> list[Chunk]: ...


@overload
def chunk_text(
    text: str,
    *,
    source_path: str,
    doc_id: str | None = None,
    chunk_size: int = 512,
    overlap: int = 50,
    encoding_name: str = "cl100k_base",
) -> list[Chunk]: ...


def chunk_text(
    text: str,
    *,
    source_path: str,
    doc_id: str | None = None,
    config: ChunkingConfig | None = None,
    chunk_size: int = 512,
    overlap: int = 50,
    encoding_name: str = "cl100k_base",
) -> list[Chunk]:
    """
    Split text into overlapping chunks based on token boundaries.

    This function tokenizes the input text, splits it into chunks of specified
    token size with overlap, then decodes each chunk back to text. This ensures
    chunk sizes are predictable relative to LLM context windows.

    Args:
        text: The input text to chunk.
        source_path: Full path to the source document.
        doc_id: Optional unique identifier for the document. If None, a stable
            ID is derived from sha256(source_path + text).
        config: Optional ChunkingConfig object. If provided, overrides
            chunk_size, overlap, and encoding_name parameters.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
            Ignored if config is provided.
        overlap: Number of tokens to overlap between consecutive chunks.
            Defaults to 50. Must be less than chunk_size. Ignored if config is provided.
        encoding_name: Name of the tiktoken encoding to use.
            Defaults to "cl100k_base" (used by GPT-4, text-embedding-ada-002).
            Ignored if config is provided.

    Returns:
        List of Chunk objects. Empty list if text is empty or whitespace-only.

    Raises:
        ValueError: If overlap >= chunk_size.

    Example:
        >>> from core.config import ChunkingConfig
        >>> config = ChunkingConfig(chunk_size=256, overlap=25)
        >>> chunks = chunk_text(
        ...     "Your long document text here...",
        ...     source_path="/docs/manual.txt",
        ...     config=config,
        ... )
        >>> len(chunks)
        3
    """
    # Use config if provided, otherwise use individual parameters
    if config is not None:
        chunk_size = config.chunk_size
        overlap = config.overlap
        encoding_name = config.encoding_name

    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")

    if not text or text.isspace():
        return []

    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        return []

    # Derive doc_id if not provided
    resolved_doc_id = doc_id if doc_id is not None else _generate_doc_id(source_path, text)

    stride = chunk_size - overlap
    source_name = source_path.rstrip("/").split("/")[-1]

    chunks: list[Chunk] = []
    chunk_index = 0
    token_start = 0

    while token_start < total_tokens:
        token_end = min(token_start + chunk_size, total_tokens)
        chunk_tokens = tokens[token_start:token_end]
        chunk_text_content = encoding.decode(chunk_tokens)

        chunk = Chunk(
            doc_id=resolved_doc_id,
            source_path=source_path,
            source_name=source_name,
            chunk_index=chunk_index,
            text=chunk_text_content,
            token_start=token_start,
            token_end=token_end,
        )
        chunks.append(chunk)

        token_start += stride
        chunk_index += 1

    return chunks
