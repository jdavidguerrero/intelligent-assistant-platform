"""
Configuration dataclasses for the chunking system.

These immutable config objects decouple parameter passing from function signatures,
making it easier to define standard configurations and reuse them across pipelines.
"""

from dataclasses import dataclass

# Allowlist of valid tiktoken encodings.
# Kept as a module constant so core/ stays pure (no tiktoken import at config time).
VALID_ENCODINGS: frozenset[str] = frozenset(
    {
        "cl100k_base",
        "p50k_base",
        "p50k_edit",
        "r50k_base",
        "gpt2",
        "o200k_base",
    }
)


@dataclass(frozen=True)
class ChunkingConfig:
    """
    Configuration for text chunking operations.

    Immutable configuration object that can be reused across multiple
    chunk_text() calls. Defines token-based chunking parameters.

    Attributes:
        chunk_size: Maximum number of tokens per chunk. Defaults to 512,
            which balances context richness with embedding model limits.
        overlap: Number of tokens to overlap between consecutive chunks.
            Defaults to 50. Ensures context continuity at chunk boundaries.
        encoding_name: Name of the tiktoken encoding to use.
            Defaults to "cl100k_base" (GPT-4, text-embedding-ada-002).

    Example:
        >>> config = ChunkingConfig(chunk_size=256, overlap=25)
        >>> chunks = chunk_text(text, source_path="/doc.txt", config=config)
    """

    chunk_size: int = 512
    overlap: int = 50
    encoding_name: str = "cl100k_base"

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {self.chunk_size}")
        if self.overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {self.overlap}")
        if self.overlap >= self.chunk_size:
            raise ValueError(
                f"overlap ({self.overlap}) must be less than chunk_size ({self.chunk_size})"
            )
        if self.encoding_name not in VALID_ENCODINGS:
            raise ValueError(
                f"Unknown encoding_name {self.encoding_name!r}, "
                f"valid options: {sorted(VALID_ENCODINGS)}"
            )


# Pre-defined configurations for common use cases

DEFAULT_CONFIG = ChunkingConfig()
"""Default configuration: 512 tokens, 50 overlap, cl100k_base encoding."""

SMALL_CHUNK_CONFIG = ChunkingConfig(chunk_size=256, overlap=25)
"""Smaller chunks for fine-grained retrieval or limited context models."""

LARGE_CHUNK_CONFIG = ChunkingConfig(chunk_size=1024, overlap=100)
"""Larger chunks for documents requiring more context per retrieval."""

NO_OVERLAP_CONFIG = ChunkingConfig(chunk_size=512, overlap=0)
"""No overlap configuration for non-overlapping segmentation."""
