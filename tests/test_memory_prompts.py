"""Tests for memory_context parameter in build_system_prompt()."""
from __future__ import annotations

from core.rag.prompts import build_system_prompt


class TestBuildSystemPromptMemoryContext:
    def test_memory_context_none_unchanged(self) -> None:
        """Default call and explicit None produce identical output."""
        base = build_system_prompt()
        with_none = build_system_prompt(memory_context=None)
        assert base == with_none

    def test_memory_context_empty_string_unchanged(self) -> None:
        """Empty string memory_context does not alter the prompt."""
        base = build_system_prompt()
        with_empty = build_system_prompt(memory_context="")
        assert base == with_empty

    def test_memory_context_injected_when_provided(self) -> None:
        """A non-empty memory_context block appears verbatim in the prompt."""
        block = "## Your Musical Memory\n- [preference] I prefer A minor"
        result = build_system_prompt(memory_context=block)
        assert "## Your Musical Memory" in result
        assert "[preference]" in result
        assert "I prefer A minor" in result

    def test_memory_context_after_genre_reference(self) -> None:
        """Memory context is always injected after the genre reference section."""
        genre_ctx = "## Genre Reference\nTechno: 130-145 BPM"
        memory_ctx = "## Your Musical Memory\n- [preference] A minor"
        result = build_system_prompt(genre_context=genre_ctx, memory_context=memory_ctx)
        genre_pos = result.index("Genre Reference")
        memory_pos = result.index("Your Musical Memory")
        assert genre_pos < memory_pos

    def test_memory_context_after_focus_areas_when_no_genre(self) -> None:
        """Memory context is injected after focus areas when no genre recipe is set."""
        sub_domains = ["mixing", "mastering"]
        memory_ctx = "## Your Musical Memory\n- [growth] improving EQ skills"
        result = build_system_prompt(
            active_sub_domains=sub_domains, memory_context=memory_ctx
        )
        focus_pos = result.index("Focus Areas")
        memory_pos = result.index("Your Musical Memory")
        assert focus_pos < memory_pos

    def test_memory_context_all_types_appear(self) -> None:
        """All four memory types render correctly when present in the block."""
        block = (
            "## Your Musical Memory\n"
            "- [preference] prefer A minor\n"
            "- [session] discovered FM trick\n"
            "- [growth] improved EQ skills\n"
            "- [creative] try granular reverb"
        )
        result = build_system_prompt(memory_context=block)
        for label in ("[preference]", "[session]", "[growth]", "[creative]"):
            assert label in result

    def test_base_prompt_still_contains_citation_rules(self) -> None:
        """Existing citation rules survive the new parameter addition."""
        result = build_system_prompt()
        assert "[1]" in result or "citation" in result.lower() or "cite" in result.lower()

    def test_all_three_params_combined(self) -> None:
        """All three optional params can be supplied simultaneously."""
        result = build_system_prompt(
            genre_context="Organic House recipe",
            active_sub_domains=["mixing"],
            memory_context="## Your Musical Memory\n- [preference] prefer A minor",
        )
        assert "Organic House recipe" in result
        assert "mixing" in result
        assert "Your Musical Memory" in result
