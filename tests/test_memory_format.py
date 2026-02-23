"""Tests for core/memory/format.py"""

from core.memory.format import format_memory_block
from core.memory.types import MemoryEntry


def _entry(memory_type: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        memory_id="x",
        memory_type=memory_type,  # type: ignore[arg-type]
        content=content,
        created_at="2026-02-21T12:00:00+00:00",
        updated_at="2026-02-21T12:00:00+00:00",
    )


class TestFormatMemoryBlock:
    def test_empty_list_returns_empty_string(self) -> None:
        assert format_memory_block([]) == ""

    def test_single_entry_contains_type_label(self) -> None:
        result = format_memory_block([_entry("preference", "I prefer A minor")])
        assert "[preference]" in result
        assert "I prefer A minor" in result

    def test_header_present_when_nonempty(self) -> None:
        result = format_memory_block([_entry("session", "discovered FM trick")])
        assert "## Your Musical Memory" in result

    def test_multiple_entries_all_appear(self) -> None:
        entries = [
            _entry("preference", "prefer A minor"),
            _entry("session", "FM synthesis discovery"),
            _entry("creative", "try granular on pad"),
        ]
        result = format_memory_block(entries)
        assert "[preference]" in result
        assert "[session]" in result
        assert "[creative]" in result
        assert "FM synthesis discovery" in result

    def test_no_citation_numbers(self) -> None:
        result = format_memory_block([_entry("preference", "test")])
        # Memory blocks must NOT contain [1], [2], etc.
        import re

        assert not re.search(r"\[\d+\]", result)

    def test_each_entry_on_own_line(self) -> None:
        entries = [_entry("preference", "A"), _entry("session", "B")]
        result = format_memory_block(entries)
        lines = result.split("\n")
        bullet_lines = [line for line in lines if line.startswith("- [")]
        assert len(bullet_lines) == 2
