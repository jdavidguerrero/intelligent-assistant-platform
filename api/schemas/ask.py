"""
Pydantic schemas for the ``/ask`` endpoint.

Defines request validation and response serialization for the
grounded RAG question-answering endpoint.
"""

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    """Request body for ``POST /ask``."""

    query: str = Field(
        ...,
        max_length=4000,
        description="The question to answer using the knowledge base.",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature (0=deterministic, 1=creative).",
    )
    max_tokens: int = Field(
        default=2048,
        ge=1,
        le=4096,
        description="Maximum tokens in the generated response.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of source chunks to retrieve for context.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for top chunk. Request fails if below this.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        """Validate that query is not empty or whitespace-only."""
        if not v.strip():
            raise ValueError("query must be a non-empty string")
        return v


class SourceReference(BaseModel):
    """A source document reference with page number and relevance score."""

    index: int = Field(..., description="Citation index (e.g., [1], [2]).")
    source_name: str = Field(..., description="Source document filename.")
    source_path: str = Field(..., description="Full path to source document.")
    page_number: int | None = Field(
        None,
        description="Page number for PDFs (1-based), null for text files.",
    )
    score: float = Field(..., description="Cosine similarity score (0-1).")


class UsageMetadata(BaseModel):
    """Token usage and timing metadata for observability."""

    input_tokens: int = Field(..., description="Tokens consumed (query + context).")
    output_tokens: int = Field(..., description="Tokens generated (response).")
    total_tokens: int = Field(..., description="Sum of input + output tokens.")
    embedding_ms: float = Field(..., description="Time to embed query (milliseconds).")
    search_ms: float = Field(..., description="Time for vector search (milliseconds).")
    generation_ms: float = Field(..., description="Time for LLM generation (milliseconds).")
    total_ms: float = Field(..., description="Total request duration (milliseconds).")
    model: str = Field(..., description="LLM model identifier that generated the response.")


class AskResponse(BaseModel):
    """Response body for ``POST /ask``."""

    query: str = Field(..., description="The original question.")
    answer: str = Field(..., description="The generated answer with inline citations [1], [2].")
    sources: list[SourceReference] = Field(
        ...,
        description="Ordered list of source documents cited in the answer.",
    )
    citations: list[int] = Field(
        ...,
        description="Unique citation indices found in the answer.",
    )
    reason: str | None = Field(
        None,
        description=(
            "Set to 'insufficient_knowledge' if top_score < confidence_threshold. "
            "Set to 'invalid_citations' if LLM cited non-existent sources."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g., 'reranking_failed', 'invalid_citations').",
    )
    usage: UsageMetadata = Field(..., description="Token usage and timing metadata.")
