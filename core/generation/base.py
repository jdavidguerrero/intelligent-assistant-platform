"""
Generation provider protocol for the RAG pipeline.

Defines the contract that all LLM generation implementations must satisfy.
This module is pure — no I/O, no network calls, no side effects.
Concrete implementations (e.g., OpenAI, Anthropic) live in ingestion/.

Follows the same structural-typing pattern as ``EmbeddingProvider``:
any class with the right method signature satisfies the protocol
without inheriting from it.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    """A single message in a conversation.

    Attributes:
        role: One of ``"system"``, ``"user"``, or ``"assistant"``.
        content: The text content of the message.
    """

    role: str
    content: str

    def __post_init__(self) -> None:
        """Validate that role is one of the allowed values."""
        allowed = {"system", "user", "assistant"}
        if self.role not in allowed:
            raise ValueError(f"role must be one of {allowed}, got {self.role!r}")
        if not self.content:
            raise ValueError("content must be a non-empty string")


@dataclass(frozen=True)
class GenerationRequest:
    """Request to generate a completion from a list of messages.

    Attributes:
        messages: Ordered list of messages forming the conversation.
            Must contain at least one message.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
            Must be between 0.0 and 2.0.
        max_tokens: Maximum tokens in the generated response.
            Must be a positive integer.
    """

    messages: tuple[Message, ...]
    temperature: float = 0.7
    max_tokens: int = 2048

    def __post_init__(self) -> None:
        """Validate request parameters."""
        if not self.messages:
            raise ValueError("messages must contain at least one Message")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be a positive integer, got {self.max_tokens}")


@dataclass(frozen=True)
class GenerationResponse:
    """Response from a generation provider.

    Attributes:
        content: The generated text.
        model: The model identifier that produced the response.
        usage_input_tokens: Number of input tokens consumed.
        usage_output_tokens: Number of output tokens generated.
    """

    content: str
    model: str
    usage_input_tokens: int
    usage_output_tokens: int


@runtime_checkable
class GenerationProvider(Protocol):
    """
    Protocol for LLM generation providers.

    Any class that implements ``generate`` with the correct signature
    can be used as a generation backend in the RAG pipeline.

    Follows the same pattern as ``EmbeddingProvider``:
    structural typing, no inheritance required.
    """

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        Generate a completion from the given messages.

        Args:
            request: A ``GenerationRequest`` containing the conversation
                messages, temperature, and max_tokens.

        Returns:
            A ``GenerationResponse`` with the generated text and usage metadata.

        Raises:
            RuntimeError: If the generation API call fails.
        """
        ...

    def generate_stream(self, request: GenerationRequest) -> Iterator[str]:
        """
        Stream a completion as an iterator of text chunks.

        Yields text deltas as they arrive from the LLM API, enabling
        Server-Sent Events (SSE) streaming in the API layer.

        Args:
            request: A ``GenerationRequest`` containing the conversation
                messages, temperature, and max_tokens.

        Yields:
            String fragments of the generated response.

        Raises:
            RuntimeError: If the streaming API call fails.
        """
        ...
