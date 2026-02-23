"""Memory formatting for prompt injection — pure function."""

from __future__ import annotations

from core.memory.types import MemoryEntry


def format_memory_block(entries: list[MemoryEntry]) -> str:
    """Format active memory entries as a system prompt section.

    Mirrors the genre_context injection pattern in build_system_prompt().
    Memory entries use bullet format with type labels — NO citation
    numbers ([1], [2]) because memories are personal context, not
    verifiable sources.

    Args:
        entries: Active (non-expired) memory entries to inject.

    Returns:
        Formatted "## Your Musical Memory\\n- [type] content" string,
        or empty string if entries is empty.

    Example:
        >>> format_memory_block([entry_a, entry_b])
        '## Your Musical Memory\\n- [preference] You prefer A minor.\\n- [session] ...'
    """
    if not entries:
        return ""
    lines = [f"- [{e.memory_type}] {e.content}" for e in entries]
    return "## Your Musical Memory\n" + "\n".join(lines)
