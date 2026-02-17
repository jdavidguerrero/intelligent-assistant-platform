"""
Context assembly for RAG — format retrieved chunks for LLM consumption.

Pure functions that transform retrieval results into structured text
blocks the LLM can reference and cite. No I/O, no side effects.

The numbered format ``[1]``, ``[2]`` enables the LLM to produce
inline citations like ``"According to [1], you should..."`` which
downstream code can validate against the source map.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk retrieved from the vector store with its relevance score.

    This is the bridge between the search layer (which returns DB records)
    and the RAG layer (which needs formatted context). Keeping it as a
    pure frozen dataclass decouples context formatting from SQLAlchemy.

    Attributes:
        text: The chunk text content.
        source_name: Source document filename (e.g. ``"mixing-secrets.pdf"``).
        source_path: Full path to the source document.
        chunk_index: Zero-based chunk index within the document.
        score: Cosine similarity score (0.0 to 1.0).
        page_number: 1-based page number for PDFs, ``None`` for text files.
    """

    text: str
    source_name: str
    source_path: str
    chunk_index: int
    score: float
    page_number: int | None = None


def format_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks as a numbered context block for the LLM.

    Each chunk is rendered as::

        [1] (source_name, p.42, score: 0.89)
        The chunk text content...

    Args:
        chunks: Ordered list of retrieved chunks (highest relevance first).
            Must not be empty.

    Returns:
        A single string with all chunks formatted and numbered,
        separated by blank lines.

    Raises:
        ValueError: If chunks is empty.
    """
    if not chunks:
        raise ValueError("chunks must not be empty")

    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        header = _format_chunk_header(i, chunk)
        blocks.append(f"{header}\n{chunk.text}")

    return "\n\n".join(blocks)


def format_source_list(chunks: list[RetrievedChunk]) -> list[dict[str, str | int | float | None]]:
    """Build a deduplicated source reference list from retrieved chunks.

    Returns one entry per unique (source_name, page_number) pair,
    preserving the order of first appearance. This is used in the
    ``/ask`` response to show which documents were consulted.

    Args:
        chunks: List of retrieved chunks.

    Returns:
        List of source reference dicts with keys:
        ``index``, ``source_name``, ``source_path``, ``page_number``, ``score``.
    """
    seen: set[tuple[str, int | None]] = set()
    sources: list[dict[str, str | int | float | None]] = []

    for i, chunk in enumerate(chunks, start=1):
        key = (chunk.source_name, chunk.page_number)
        if key not in seen:
            seen.add(key)
            sources.append(
                {
                    "index": i,
                    "source_name": chunk.source_name,
                    "source_path": chunk.source_path,
                    "page_number": chunk.page_number,
                    "score": round(chunk.score, 4),
                }
            )

    return sources


def _format_chunk_header(index: int, chunk: RetrievedChunk) -> str:
    """Build the header line for a single chunk in the context block.

    Format: ``[1] (source_name, p.42, score: 0.89)``
    If page_number is None, the page part is omitted.
    """
    parts = [chunk.source_name]
    if chunk.page_number is not None:
        parts.append(f"p.{chunk.page_number}")
    parts.append(f"score: {chunk.score:.2f}")
    metadata = ", ".join(parts)
    return f"[{index}] ({metadata})"
