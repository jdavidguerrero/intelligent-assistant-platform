"""
Pydantic schemas for the ``/ask`` endpoint.

Defines request validation and response serialization for the
grounded RAG question-answering endpoint.

Response modes:
  "rag"      — Pure RAG: embed → search → generate with citations.
  "tool"     — Tool execution: intent matched, tool called, result summarized by LLM.
  "degraded" — LLM unavailable: raw pgvector chunks shown directly, no generation.
  "hybrid"   — Tool result injected as context into RAG pipeline (future).
"""

from typing import Any

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
    use_tools: bool = Field(
        default=True,
        description=(
            "Whether to attempt tool routing before RAG. "
            "If True and a tool intent is detected, the tool is executed and its result "
            "is summarized by the LLM. Falls back to pure RAG if no tool matches. "
            "Set to False to force pure RAG (e.g., for knowledge-only queries)."
        ),
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Optional session identifier for per-session rate limiting. "
            "Defaults to 'default' if not provided."
        ),
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
    cache_hit: bool = Field(
        default=False,
        description="True if the response was served from Redis cache (<100ms).",
    )
    embedding_cache_hit: bool = Field(
        default=False,
        description="True if the query embedding was served from in-memory cache.",
    )
    cost_usd: float = Field(
        default=0.0,
        description=(
            "Estimated USD cost for this generation call. "
            "Non-zero only when USE_ROUTING=true. "
            "Calculated from (model, input_tokens, output_tokens) via the cost table."
        ),
    )
    tier: str = Field(
        default="",
        description=(
            "Model tier that generated the response: 'fast', 'standard', or 'local'. "
            "Empty string when USE_ROUTING=false (single-provider mode)."
        ),
    )


class ToolCallRecord(BaseModel):
    """Record of a single tool execution within a request."""

    tool_name: str = Field(..., description="Name of the tool that was called.")
    params: dict[str, Any] = Field(..., description="Parameters passed to the tool.")
    success: bool = Field(..., description="Whether the tool executed successfully.")
    error: str | None = Field(None, description="Error message if success=False.")
    data_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Key fields from tool result data (trimmed for response size).",
    )


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
    mode: str = Field(
        default="rag",
        description=(
            "Response mode: "
            "'rag' (pure retrieval + LLM generation), "
            "'tool' (tool executed + LLM synthesis), "
            "'degraded' (LLM unavailable — raw knowledge base excerpts shown directly), "
            "'hybrid' (tool result + RAG context combined, future)."
        ),
    )
    tool_calls: list[ToolCallRecord] = Field(
        default_factory=list,
        description="Records of tool executions performed during this request.",
    )
