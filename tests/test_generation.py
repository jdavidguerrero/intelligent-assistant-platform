"""
Tests for ingestion/generation.py — OpenAI and Anthropic providers.

Uses mocked API clients to test provider logic without real API calls.
Also tests the factory function and system message splitting.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.generation.base import GenerationRequest, GenerationResponse, Message
from ingestion.generation import (
    AnthropicGenerationProvider,
    OpenAIGenerationProvider,
    _split_system_messages,
    create_generation_provider,
)


class TestSplitSystemMessages:
    """Test _split_system_messages utility."""

    def test_no_system_messages(self) -> None:
        msgs = (
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi"),
        )
        system, conversation = _split_system_messages(msgs)
        assert system == ""
        assert len(conversation) == 2

    def test_single_system_message(self) -> None:
        msgs = (
            Message(role="system", content="You are an expert."),
            Message(role="user", content="hello"),
        )
        system, conversation = _split_system_messages(msgs)
        assert system == "You are an expert."
        assert len(conversation) == 1
        assert conversation[0].role == "user"

    def test_multiple_system_messages(self) -> None:
        msgs = (
            Message(role="system", content="Part 1."),
            Message(role="system", content="Part 2."),
            Message(role="user", content="hello"),
        )
        system, conversation = _split_system_messages(msgs)
        assert "Part 1." in system
        assert "Part 2." in system
        assert len(conversation) == 1


class TestOpenAIGenerationProvider:
    """Test OpenAI provider with mocked client."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"})
    @patch("ingestion.generation.openai.OpenAI")
    def test_generate_returns_response(self, mock_openai_cls: MagicMock) -> None:
        # Set up mock
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "Use a high-pass filter."

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o-2025-01-01"

        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        provider = OpenAIGenerationProvider(api_key="sk-test-key")
        req = GenerationRequest(
            messages=(Message(role="user", content="How to EQ vocals?"),),
        )
        resp = provider.generate(req)

        # Assert
        assert isinstance(resp, GenerationResponse)
        assert resp.content == "Use a high-pass filter."
        assert resp.model == "gpt-4o-2025-01-01"
        assert resp.usage_input_tokens == 100
        assert resp.usage_output_tokens == 50

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"})
    @patch("ingestion.generation.openai.OpenAI")
    def test_generate_passes_messages(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "answer"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 0
        mock_usage.completion_tokens = 0
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o"
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIGenerationProvider(api_key="sk-test-key")
        req = GenerationRequest(
            messages=(
                Message(role="system", content="Be helpful."),
                Message(role="user", content="hello"),
            ),
            temperature=0.3,
            max_tokens=1000,
        )
        provider.generate(req)

        # Verify API was called with correct args
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 1000
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"})
    @patch("ingestion.generation.openai.OpenAI")
    def test_api_error_raises_runtime_error(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("rate limit")

        provider = OpenAIGenerationProvider(api_key="sk-test-key")
        req = GenerationRequest(
            messages=(Message(role="user", content="hello"),),
        )
        with pytest.raises(RuntimeError, match="OpenAI generation failed"):
            provider.generate(req)

    def test_missing_api_key_raises(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("ingestion.generation.load_dotenv"),
        ):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIGenerationProvider()


class TestAnthropicGenerationProvider:
    """Test Anthropic provider with mocked client."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    @patch("ingestion.generation.anthropic.Anthropic")
    def test_generate_returns_response(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Apply compression gently."

        mock_usage = MagicMock()
        mock_usage.input_tokens = 200
        mock_usage.output_tokens = 80

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage = mock_usage

        mock_client.messages.create.return_value = mock_response

        provider = AnthropicGenerationProvider(api_key="sk-ant-test")
        req = GenerationRequest(
            messages=(
                Message(role="system", content="You are an expert."),
                Message(role="user", content="How to compress drums?"),
            ),
        )
        resp = provider.generate(req)

        assert isinstance(resp, GenerationResponse)
        assert resp.content == "Apply compression gently."
        assert resp.usage_input_tokens == 200
        assert resp.usage_output_tokens == 80

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    @patch("ingestion.generation.anthropic.Anthropic")
    def test_system_message_extracted(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "answer"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 0
        mock_usage.output_tokens = 0
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage = mock_usage
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicGenerationProvider(api_key="sk-ant-test")
        req = GenerationRequest(
            messages=(
                Message(role="system", content="Expert persona."),
                Message(role="user", content="hello"),
            ),
        )
        provider.generate(req)

        call_kwargs = mock_client.messages.create.call_args[1]
        # System should be passed as separate parameter, not in messages
        assert call_kwargs["system"] == "Expert persona."
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    @patch("ingestion.generation.anthropic.Anthropic")
    def test_api_error_raises_runtime_error(self, mock_anthropic_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("overloaded")

        provider = AnthropicGenerationProvider(api_key="sk-ant-test")
        req = GenerationRequest(
            messages=(Message(role="user", content="hello"),),
        )
        with pytest.raises(RuntimeError, match="Anthropic generation failed"):
            provider.generate(req)

    def test_missing_api_key_raises(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("ingestion.generation.load_dotenv"),
        ):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicGenerationProvider()


class TestCreateGenerationProvider:
    """Test the factory function."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    @patch("ingestion.generation.openai.OpenAI")
    def test_default_is_openai(self, _mock: MagicMock) -> None:
        provider = create_generation_provider(provider="openai", api_key="sk-test")
        assert isinstance(provider, OpenAIGenerationProvider)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    @patch("ingestion.generation.anthropic.Anthropic")
    def test_anthropic_provider(self, _mock: MagicMock) -> None:
        provider = create_generation_provider(provider="anthropic", api_key="sk-ant-test")
        assert isinstance(provider, AnthropicGenerationProvider)

    @patch.dict("os.environ", {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"})
    @patch("ingestion.generation.anthropic.Anthropic")
    def test_reads_env_var(self, _mock: MagicMock) -> None:
        provider = create_generation_provider()
        assert isinstance(provider, AnthropicGenerationProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            create_generation_provider(provider="gemini")
