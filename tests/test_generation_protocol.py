"""
Tests for core/generation/base.py — protocol and data types.

Validates the Message, GenerationRequest, GenerationResponse frozen
dataclasses and the GenerationProvider protocol (structural typing).
"""

from dataclasses import FrozenInstanceError

import pytest

from core.generation.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    Message,
)


class TestMessage:
    """Test Message frozen dataclass."""

    def test_valid_roles(self) -> None:
        for role in ("system", "user", "assistant"):
            msg = Message(role=role, content="hello")
            assert msg.role == role
            assert msg.content == "hello"

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(ValueError, match="role must be one of"):
            Message(role="admin", content="hello")

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="content must be a non-empty string"):
            Message(role="user", content="")

    def test_frozen(self) -> None:
        msg = Message(role="user", content="hello")
        with pytest.raises(FrozenInstanceError):
            msg.content = "changed"  # type: ignore[misc]


class TestGenerationRequest:
    """Test GenerationRequest frozen dataclass."""

    def test_valid_request(self) -> None:
        msg = Message(role="user", content="What is EQ?")
        req = GenerationRequest(messages=(msg,))
        assert req.messages == (msg,)
        assert req.temperature == 0.7
        assert req.max_tokens == 2048

    def test_custom_parameters(self) -> None:
        msg = Message(role="user", content="hello")
        req = GenerationRequest(messages=(msg,), temperature=0.0, max_tokens=500)
        assert req.temperature == 0.0
        assert req.max_tokens == 500

    def test_empty_messages_raises(self) -> None:
        with pytest.raises(ValueError, match="messages must contain at least one"):
            GenerationRequest(messages=())

    def test_temperature_too_high_raises(self) -> None:
        msg = Message(role="user", content="hello")
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationRequest(messages=(msg,), temperature=2.5)

    def test_temperature_negative_raises(self) -> None:
        msg = Message(role="user", content="hello")
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationRequest(messages=(msg,), temperature=-0.1)

    def test_max_tokens_zero_raises(self) -> None:
        msg = Message(role="user", content="hello")
        with pytest.raises(ValueError, match="max_tokens must be a positive"):
            GenerationRequest(messages=(msg,), max_tokens=0)

    def test_frozen(self) -> None:
        msg = Message(role="user", content="hello")
        req = GenerationRequest(messages=(msg,))
        with pytest.raises(FrozenInstanceError):
            req.temperature = 1.0  # type: ignore[misc]


class TestGenerationResponse:
    """Test GenerationResponse frozen dataclass."""

    def test_valid_response(self) -> None:
        resp = GenerationResponse(
            content="Use a high-pass filter at 30Hz.",
            model="gpt-4o",
            usage_input_tokens=500,
            usage_output_tokens=100,
        )
        assert resp.content == "Use a high-pass filter at 30Hz."
        assert resp.model == "gpt-4o"
        assert resp.usage_input_tokens == 500
        assert resp.usage_output_tokens == 100

    def test_frozen(self) -> None:
        resp = GenerationResponse(
            content="answer", model="gpt-4o", usage_input_tokens=0, usage_output_tokens=0
        )
        with pytest.raises(FrozenInstanceError):
            resp.content = "changed"  # type: ignore[misc]


class TestGenerationProtocol:
    """Test GenerationProvider protocol satisfaction."""

    def test_class_with_generate_satisfies_protocol(self) -> None:
        class FakeProvider:
            def generate(self, request: GenerationRequest) -> GenerationResponse:
                return GenerationResponse(
                    content="fake", model="fake", usage_input_tokens=0, usage_output_tokens=0
                )

        provider = FakeProvider()
        assert isinstance(provider, GenerationProvider)

    def test_class_without_generate_does_not_satisfy(self) -> None:
        class NotAProvider:
            def do_something(self) -> str:
                return "nope"

        assert not isinstance(NotAProvider(), GenerationProvider)

    def test_fake_provider_can_be_called(self) -> None:
        class FakeProvider:
            def generate(self, request: GenerationRequest) -> GenerationResponse:
                return GenerationResponse(
                    content=f"Answer to: {request.messages[0].content}",
                    model="test-model",
                    usage_input_tokens=10,
                    usage_output_tokens=5,
                )

        provider = FakeProvider()
        msg = Message(role="user", content="How to sidechain?")
        req = GenerationRequest(messages=(msg,))
        resp = provider.generate(req)
        assert "sidechain" in resp.content
        assert resp.model == "test-model"
