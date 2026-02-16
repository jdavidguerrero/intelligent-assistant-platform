"""
Pydantic schemas for the ``/search`` endpoint.

Defines request validation and response serialization models.
"""

from pydantic import BaseModel, Field, field_validator


class ResponseMeta(BaseModel):
    """Performance timing metadata."""

    embedding_ms: float = Field(..., description="Time to generate query embedding (milliseconds).")
    search_ms: float = Field(..., description="Time for database search (milliseconds).")
    total_ms: float = Field(..., description="Total request duration (milliseconds).")
    cache_hit: bool = Field(
        ..., description="True if embedding was retrieved from cache, False if API call was made."
    )
    request_id: str = Field(..., description="Unique identifier for this request (UUID4).")


class SearchRequest(BaseModel):
    """Request body for ``POST /search``."""

    query: str = Field(
        ..., max_length=4000, description="The search query text. Must be non-empty."
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of results to return (1–20).",
    )
    min_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity threshold (0–1). Results below this are discarded.",
    )
    use_mmr: bool = Field(
        default=False,
        description="Use Maximal Marginal Relevance for diversity instead of document-count filter.",
    )
    mmr_lambda: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="MMR trade-off: 1.0 = pure relevance, 0.0 = pure diversity. Only used when use_mmr=True.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        """Validate that query is not empty or whitespace-only."""
        if not v.strip():
            raise ValueError("query must be a non-empty string")
        return v


class SearchResult(BaseModel):
    """A single search result with similarity score and chunk metadata."""

    score: float = Field(..., description="Cosine similarity score (0–1).")
    text: str = Field(..., description="Chunk text content.")
    source_name: str = Field(..., description="Source document filename.")
    source_path: str = Field(..., description="Full path to the source document.")
    chunk_index: int = Field(..., description="Zero-based chunk index within the document.")
    token_start: int = Field(
        ..., description="Starting token index in original document (inclusive)."
    )
    token_end: int = Field(..., description="Ending token index in original document (exclusive).")


class SearchResponse(BaseModel):
    """Response body for ``POST /search``."""

    query: str = Field(..., description="The original search query.")
    top_k: int = Field(..., description="Number of results requested.")
    results: list[SearchResult] = Field(..., description="Ranked search results.")
    reason: str | None = Field(
        default=None,
        description="Set to 'low_confidence' when all results were below min_score.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g. reranking fallback).",
    )
    meta: ResponseMeta = Field(..., description="Performance timing metadata.")
