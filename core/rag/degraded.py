"""Degraded response builder for graceful degradation.

When the LLM is unavailable (circuit open, timeout, quota exhausted),
we still have the retrieved chunks from pgvector. This module formats
those chunks into a useful response without LLM generation.

Design principle
----------------
A raw chunk response is always better than a 500 error during a
production session. The musician can still read the source material
and continue working. "I couldn't generate a polished answer, but here's
what I found" beats "Internal Server Error" every time.

The degraded response:
  - Flags mode="degraded" so the client knows it's not a full answer
  - Formats chunks as numbered source excerpts with page numbers
  - Includes a human-readable explanation of why it's degraded
  - Returns the same citations/sources structure as a normal response

Pure function — no I/O, no external calls.

Usage::

    from core.rag.degraded import build_degraded_response

    response = build_degraded_response(
        query="How do I sidechain the kick?",
        retrieved_chunks=chunks,
        reason="llm_unavailable",
    )
"""

from __future__ import annotations

from dataclasses import dataclass

from core.rag.context import RetrievedChunk

# ---------------------------------------------------------------------------
# Degradation reasons — maps to human-readable messages
# ---------------------------------------------------------------------------

_REASON_MESSAGES: dict[str, str] = {
    "llm_unavailable": (
        "The AI model is temporarily unavailable. "
        "Here's what I found in your knowledge base — "
        "the relevant passages are shown directly:"
    ),
    "embedding_unavailable": (
        "The embedding service is temporarily unavailable. "
        "I couldn't perform a fresh search, but here's a cached result:"
    ),
    "search_failed": (
        "The vector search failed. "
        "I couldn't retrieve results from your knowledge base right now."
    ),
    "circuit_open": (
        "The AI model has been unavailable for several requests in a row. "
        "Showing raw knowledge base excerpts while the service recovers:"
    ),
    "unknown": ("Something went wrong. " "Here's what I found in your knowledge base:"),
}

_MAX_CHARS_PER_CHUNK = 600  # Truncate long chunks to keep response readable
_DEGRADED_MODEL = "degraded-mode"


@dataclass(frozen=True)
class DegradedResponse:
    """Result of building a degraded response from raw chunks.

    Attributes:
        answer: Formatted text with source excerpts.
        citations: List of citation indices that appear in the answer.
        mode: Always "degraded".
        warning: Human-readable explanation for the degradation.
    """

    answer: str
    citations: list[int]
    mode: str
    warning: str


def build_degraded_response(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
    reason: str = "llm_unavailable",
) -> DegradedResponse:
    """Build a degraded response directly from retrieved chunks, without LLM.

    Formats the top chunks as numbered source excerpts so the musician
    can still get useful information even when the LLM is unavailable.

    Args:
        query: The original user query (used for context in the header).
        retrieved_chunks: Chunks from pgvector, already reranked.
        reason: Why we're in degraded mode. One of:
            "llm_unavailable", "embedding_unavailable",
            "search_failed", "circuit_open", "unknown".

    Returns:
        DegradedResponse with formatted answer and citation list.

    Example output::

        The AI model is temporarily unavailable. Here's what I found
        in your knowledge base — the relevant passages are shown directly:

        [1] bob_katz_mastering.pdf — p.45 (score: 0.89)
        For Spotify, aim for -14 LUFS integrated loudness. The true peak
        limit should be -1 dBTP to prevent inter-sample peaks after
        lossy encoding...

        [2] pete_tong_masterclass.pdf — p.12 (score: 0.84)
        Streaming platforms normalize to different targets: Spotify -14 LUFS,
        Apple Music -16 LUFS, YouTube -14 LUFS...
    """
    intro = _REASON_MESSAGES.get(reason, _REASON_MESSAGES["unknown"])

    if not retrieved_chunks:
        return DegradedResponse(
            answer=(
                f"{intro}\n\n"
                "Unfortunately, no relevant passages were found for your query:\n"
                f'"{query}"'
            ),
            citations=[],
            mode="degraded",
            warning=reason,
        )

    lines: list[str] = [intro, ""]
    citations: list[int] = []

    for i, chunk in enumerate(retrieved_chunks, start=1):
        citations.append(i)

        # Header: source name + page + score
        page_info = f" — p.{chunk.page_number}" if chunk.page_number else ""
        score_info = f" (score: {chunk.score:.2f})"
        header = f"[{i}] {chunk.source_name}{page_info}{score_info}"

        # Truncate long chunks for readability
        text = chunk.text.strip()
        if len(text) > _MAX_CHARS_PER_CHUNK:
            text = text[:_MAX_CHARS_PER_CHUNK].rsplit(" ", 1)[0] + "…"

        lines.append(header)
        lines.append(text)
        lines.append("")  # blank line between chunks

    answer = "\n".join(lines).rstrip()

    return DegradedResponse(
        answer=answer,
        citations=citations,
        mode="degraded",
        warning=reason,
    )
