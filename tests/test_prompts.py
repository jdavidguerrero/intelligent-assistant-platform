"""
Tests for core/rag/prompts.py — system and user prompt templates.

Validates that prompts contain the critical instructions for grounded
RAG behavior: citation rules, grounding constraints, and refusal behavior.
"""

import pytest

from core.rag.prompts import SYSTEM_PROMPT, build_system_prompt, build_user_prompt


class TestSystemPrompt:
    """Test the system prompt content and structure."""

    def test_contains_music_production_persona(self) -> None:
        assert "music production" in SYSTEM_PROMPT.lower()

    def test_contains_citation_instructions(self) -> None:
        """The LLM must know how to cite sources."""
        assert "[1]" in SYSTEM_PROMPT
        assert "[2]" in SYSTEM_PROMPT

    def test_contains_grounding_constraint(self) -> None:
        """The LLM must be told to answer ONLY from context."""
        assert "ONLY" in SYSTEM_PROMPT
        assert "context" in SYSTEM_PROMPT.lower()

    def test_contains_refusal_instruction(self) -> None:
        """The LLM must know when to refuse."""
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "don't have enough information" in prompt_lower or "do not fabricate" in prompt_lower

    def test_contains_do_not_fabricate(self) -> None:
        assert "Do NOT fabricate" in SYSTEM_PROMPT

    def test_build_system_prompt_returns_same(self) -> None:
        """build_system_prompt() should return the static prompt."""
        assert build_system_prompt() == SYSTEM_PROMPT


class TestBuildUserPrompt:
    """Test user prompt construction."""

    def test_includes_query(self) -> None:
        result = build_user_prompt(
            query="How should I EQ my kick?",
            context_block="[1] (source.pdf) Some context.",
        )
        assert "How should I EQ my kick?" in result

    def test_includes_context_block(self) -> None:
        context = "[1] (mixing.pdf, p.12, score: 0.9)\nEQ the kick at 60Hz."
        result = build_user_prompt(query="question", context_block=context)
        assert "[1] (mixing.pdf, p.12, score: 0.9)" in result
        assert "EQ the kick at 60Hz." in result

    def test_has_context_section_header(self) -> None:
        result = build_user_prompt(query="q", context_block="ctx")
        assert "## Context" in result

    def test_has_question_section_header(self) -> None:
        result = build_user_prompt(query="q", context_block="ctx")
        assert "## Question" in result

    def test_citation_instruction_in_context_section(self) -> None:
        """The user prompt should remind about citations."""
        result = build_user_prompt(query="q", context_block="ctx")
        assert "[1]" in result or "cite" in result.lower()

    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError, match="query must be a non-empty"):
            build_user_prompt(query="", context_block="ctx")

    def test_whitespace_only_query_raises(self) -> None:
        with pytest.raises(ValueError, match="query must be a non-empty"):
            build_user_prompt(query="   ", context_block="ctx")

    def test_empty_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context_block must be a non-empty"):
            build_user_prompt(query="question", context_block="")

    def test_whitespace_only_context_raises(self) -> None:
        with pytest.raises(ValueError, match="context_block must be a non-empty"):
            build_user_prompt(query="question", context_block="   \n  ")

    def test_context_before_question(self) -> None:
        """Context should appear before the question in the prompt."""
        result = build_user_prompt(query="my question", context_block="my context")
        ctx_pos = result.index("my context")
        q_pos = result.index("my question")
        assert ctx_pos < q_pos
