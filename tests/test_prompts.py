"""
Tests for core/rag/prompts.py — system and user prompt templates.

Validates that prompts contain the critical instructions for grounded
RAG behavior: citation rules, grounding constraints, and refusal behavior.

Day 2 additions:
- build_system_prompt with genre_context (genre recipe injection)
- build_system_prompt with active_sub_domains (focus area scoping)
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


class TestBuildSystemPromptDay2:
    """Tests for the genre_context and active_sub_domains extensions (Day 2)."""

    def test_no_args_returns_base_prompt(self) -> None:
        """Calling with no args still returns the unmodified base prompt."""
        assert build_system_prompt() == SYSTEM_PROMPT

    def test_none_args_returns_base_prompt(self) -> None:
        """Explicit None args produce the same result as no args."""
        assert build_system_prompt(genre_context=None, active_sub_domains=None) == SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # active_sub_domains
    # ------------------------------------------------------------------

    def test_active_sub_domains_adds_focus_section(self) -> None:
        result = build_system_prompt(active_sub_domains=["mixing"])
        assert "## Focus Areas" in result

    def test_active_sub_domains_lists_all_provided(self) -> None:
        result = build_system_prompt(active_sub_domains=["mixing", "genre_analysis"])
        assert "mixing" in result
        assert "genre_analysis" in result

    def test_active_sub_domains_extends_base(self) -> None:
        """Base prompt content is preserved when sub_domains are added."""
        result = build_system_prompt(active_sub_domains=["arrangement"])
        assert "ONLY" in result  # grounding constraint still present
        assert "Do NOT fabricate" in result  # refusal still present

    def test_empty_sub_domains_list_no_focus_section(self) -> None:
        """Empty list is falsy — no Focus Areas section should be added."""
        result = build_system_prompt(active_sub_domains=[])
        assert "## Focus Areas" not in result

    def test_active_sub_domains_longer_than_base(self) -> None:
        result = build_system_prompt(active_sub_domains=["mixing"])
        assert len(result) > len(SYSTEM_PROMPT)

    def test_single_sub_domain_appears_in_focus_text(self) -> None:
        result = build_system_prompt(active_sub_domains=["sound_design"])
        assert "sound_design" in result

    def test_multiple_sub_domains_joined_with_comma(self) -> None:
        """The domains appear in a comma-separated list."""
        result = build_system_prompt(active_sub_domains=["mixing", "arrangement", "genre_analysis"])
        # All three should be present
        assert "mixing" in result
        assert "arrangement" in result
        assert "genre_analysis" in result

    # ------------------------------------------------------------------
    # genre_context
    # ------------------------------------------------------------------

    def test_genre_context_adds_genre_reference_section(self) -> None:
        result = build_system_prompt(genre_context="BPM: 124. Typical keys: A minor.")
        assert "## Genre Reference" in result

    def test_genre_context_content_included_verbatim(self) -> None:
        recipe = "BPM range: 120–128. Typical keys: A minor, D minor."
        result = build_system_prompt(genre_context=recipe)
        assert recipe in result

    def test_genre_context_extends_base(self) -> None:
        result = build_system_prompt(genre_context="Some recipe.")
        assert len(result) > len(SYSTEM_PROMPT)

    def test_empty_string_genre_context_no_section(self) -> None:
        """Empty string is falsy — Genre Reference section should not appear."""
        result = build_system_prompt(genre_context="")
        assert "## Genre Reference" not in result

    def test_none_genre_context_no_section(self) -> None:
        result = build_system_prompt(genre_context=None)
        assert "## Genre Reference" not in result

    def test_genre_context_after_focus_areas(self) -> None:
        """Genre Reference section should appear after Focus Areas."""
        result = build_system_prompt(
            genre_context="recipe text",
            active_sub_domains=["genre_analysis"],
        )
        focus_pos = result.index("## Focus Areas")
        genre_pos = result.index("## Genre Reference")
        assert focus_pos < genre_pos

    # ------------------------------------------------------------------
    # combined
    # ------------------------------------------------------------------

    def test_both_args_returns_longest_prompt(self) -> None:
        no_args = build_system_prompt()
        with_sub = build_system_prompt(active_sub_domains=["mixing"])
        with_both = build_system_prompt(
            genre_context="recipe",
            active_sub_domains=["mixing"],
        )
        assert len(with_both) > len(with_sub) > len(no_args)

    def test_both_sections_present_when_both_provided(self) -> None:
        result = build_system_prompt(
            genre_context="BPM: 128",
            active_sub_domains=["genre_analysis", "mixing"],
        )
        assert "## Focus Areas" in result
        assert "## Genre Reference" in result

    def test_returns_string_type(self) -> None:
        assert isinstance(build_system_prompt(genre_context="x", active_sub_domains=["y"]), str)


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
