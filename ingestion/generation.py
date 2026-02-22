"""
LLM generation providers — OpenAI and Anthropic implementations.

Implements the ``GenerationProvider`` protocol from core using
the OpenAI and Anthropic APIs. Lives in ingestion/ because it
performs network I/O (core/ must remain pure).

Usage::

    provider = create_generation_provider()  # reads LLM_PROVIDER env var
    response = provider.generate(request)
"""

import os
from collections.abc import Iterator

import anthropic
import openai
from dotenv import load_dotenv

from core.generation.base import GenerationRequest, GenerationResponse, Message


class OpenAIGenerationProvider:
    """
    Generation provider backed by OpenAI's chat completion API.

    Reads ``OPENAI_API_KEY`` from the environment. Model name is
    configurable (default: ``gpt-4o``).

    Satisfies the ``GenerationProvider`` protocol.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        *,
        api_key: str | None = None,
    ) -> None:
        load_dotenv()
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY must be set in the environment or passed explicitly")
        self._client = openai.OpenAI(api_key=resolved_key)
        self._model = model

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a completion via OpenAI chat API.

        Args:
            request: Generation request with messages, temperature, max_tokens.

        Returns:
            GenerationResponse with content and usage metadata.

        Raises:
            RuntimeError: If the API call fails.
        """
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI generation failed: {exc}") from exc

        choice = response.choices[0]
        usage = response.usage

        return GenerationResponse(
            content=choice.message.content or "",
            model=response.model,
            usage_input_tokens=usage.prompt_tokens if usage else 0,
            usage_output_tokens=usage.completion_tokens if usage else 0,
        )


    def generate_stream(self, request: GenerationRequest) -> Iterator[str]:
        """Stream text chunks from OpenAI chat completions API.

        Uses OpenAI's streaming mode (``stream=True``) to yield text deltas
        as they arrive. Suitable for Server-Sent Events (SSE) delivery.

        Args:
            request: Generation request with messages, temperature, max_tokens.

        Yields:
            Non-empty text delta strings from the completion stream.

        Raises:
            RuntimeError: If the streaming API call fails.
        """
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise RuntimeError(f"OpenAI streaming failed: {exc}") from exc


class AnthropicGenerationProvider:
    """
    Generation provider backed by Anthropic's Messages API.

    Reads ``ANTHROPIC_API_KEY`` from the environment. Model name is
    configurable (default: ``claude-sonnet-4-20250514``).

    Satisfies the ``GenerationProvider`` protocol.

    Note: Anthropic's API separates system prompt from messages.
    If the first message has role ``"system"``, it is extracted
    and passed as the ``system`` parameter.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        *,
        api_key: str | None = None,
    ) -> None:
        load_dotenv()
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set in the environment or passed explicitly"
            )
        self._client = anthropic.Anthropic(api_key=resolved_key)
        self._model = model

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a completion via Anthropic Messages API.

        Extracts system messages from the conversation (Anthropic requires
        them as a separate ``system`` parameter) and sends the remaining
        user/assistant messages in the ``messages`` list.

        Args:
            request: Generation request with messages, temperature, max_tokens.

        Returns:
            GenerationResponse with content and usage metadata.

        Raises:
            RuntimeError: If the API call fails.
        """
        system_text, conversation = _split_system_messages(request.messages)

        messages = [{"role": m.role, "content": m.content} for m in conversation]

        try:
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            if system_text:
                kwargs["system"] = system_text

            response = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise RuntimeError(f"Anthropic generation failed: {exc}") from exc

        # Anthropic returns content as a list of blocks
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return GenerationResponse(
            content=content,
            model=response.model,
            usage_input_tokens=response.usage.input_tokens,
            usage_output_tokens=response.usage.output_tokens,
        )


    def generate_stream(self, request: GenerationRequest) -> Iterator[str]:
        """Stream text chunks from Anthropic Messages API.

        Uses Anthropic's streaming context manager to yield text deltas
        as they arrive. Suitable for Server-Sent Events (SSE) delivery.

        Args:
            request: Generation request with messages, temperature, max_tokens.

        Yields:
            Non-empty text delta strings from the completion stream.

        Raises:
            RuntimeError: If the streaming API call fails.
        """
        system_text, conversation = _split_system_messages(request.messages)
        messages = [{"role": m.role, "content": m.content} for m in conversation]
        try:
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            if system_text:
                kwargs["system"] = system_text

            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as exc:
            raise RuntimeError(f"Anthropic streaming failed: {exc}") from exc


def _split_system_messages(
    messages: tuple[Message, ...],
) -> tuple[str, tuple[Message, ...]]:
    """Separate system messages from conversation messages.

    Anthropic's API requires the system prompt as a separate parameter,
    not as a message in the conversation. This function extracts all
    system messages, concatenates them, and returns the remaining
    user/assistant messages.

    Args:
        messages: Full message tuple including system messages.

    Returns:
        Tuple of (system_text, remaining_messages).
    """
    system_parts: list[str] = []
    conversation: list[Message] = []

    for msg in messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        else:
            conversation.append(msg)

    system_text = "\n\n".join(system_parts)
    return system_text, tuple(conversation)


def create_generation_provider(
    provider: str | None = None,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> OpenAIGenerationProvider | AnthropicGenerationProvider:
    """Factory: create a generation provider based on configuration.

    Reads ``LLM_PROVIDER`` from the environment if *provider* is not
    specified. Defaults to ``"openai"`` if the env var is unset.

    Args:
        provider: Provider name — ``"openai"`` or ``"anthropic"``.
        model: Optional model override. Uses provider defaults if omitted.
        api_key: Optional API key override. Reads from env if omitted.

    Returns:
        A concrete generation provider satisfying ``GenerationProvider``.

    Raises:
        ValueError: If provider name is not recognized.
    """
    load_dotenv()
    resolved_provider = (provider or os.environ.get("LLM_PROVIDER", "openai")).lower().strip()

    if resolved_provider == "openai":
        kwargs: dict = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        return OpenAIGenerationProvider(**kwargs)

    if resolved_provider == "anthropic":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        return AnthropicGenerationProvider(**kwargs)

    raise ValueError(
        f"Unknown LLM_PROVIDER: {resolved_provider!r}. " "Supported values: 'openai', 'anthropic'."
    )
