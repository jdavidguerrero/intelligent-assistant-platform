"""
Tests for core/rag/context.py — context block formatting and source lists.

Validates the pure functions that transform retrieved chunks into
numbered context blocks the LLM can reference and cite.
"""

import pytest

from core.rag.context import RetrievedChunk, format_context_block, format_source_list


def _make_chunk(
    text: str = "Sample chunk text.",
    source_name: str = "mixing-secrets.pdf",
    source_path: str = "/data/mixing-secrets.pdf",
    chunk_index: int = 0,
    score: float = 0.85,
    page_number: int | None = 42,
) -> RetrievedChunk:
    """Factory helper for creating test chunks."""
    return RetrievedChunk(
        text=text,
        source_name=source_name,
        source_path=source_path,
        chunk_index=chunk_index,
        score=score,
        page_number=page_number,
    )


class TestRetrievedChunk:
    """Test RetrievedChunk frozen dataclass."""

    def test_creates_with_all_fields(self) -> None:
        chunk = _make_chunk()
        assert chunk.text == "Sample chunk text."
        assert chunk.source_name == "mixing-secrets.pdf"
        assert chunk.score == 0.85
        assert chunk.page_number == 42

    def test_page_number_defaults_to_none(self) -> None:
        chunk = RetrievedChunk(
            text="text",
            source_name="doc.md",
            source_path="/doc.md",
            chunk_index=0,
            score=0.9,
        )
        assert chunk.page_number is None

    def test_frozen(self) -> None:
        chunk = _make_chunk()
        with pytest.raises(AttributeError):
            chunk.text = "changed"  # type: ignore[misc]


class TestFormatContextBlock:
    """Test context block formatting for LLM consumption."""

    def test_single_chunk_with_page(self) -> None:
        chunks = [_make_chunk(text="EQ cuts at 300Hz reduce muddiness.")]
        result = format_context_block(chunks)

        assert "[1]" in result
        assert "mixing-secrets.pdf" in result
        assert "p.42" in result
        assert "score: 0.85" in result
        assert "EQ cuts at 300Hz reduce muddiness." in result

    def test_single_chunk_without_page(self) -> None:
        chunks = [_make_chunk(text="Content here.", page_number=None)]
        result = format_context_block(chunks)

        assert "[1]" in result
        assert "p." not in result
        assert "Content here." in result

    def test_multiple_chunks_numbered_sequentially(self) -> None:
        chunks = [
            _make_chunk(text="First chunk.", score=0.95),
            _make_chunk(text="Second chunk.", source_name="ableton.pdf", score=0.80, page_number=7),
            _make_chunk(
                text="Third chunk.", source_name="theory.pdf", score=0.70, page_number=None
            ),
        ]
        result = format_context_block(chunks)

        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
        assert "First chunk." in result
        assert "Second chunk." in result
        assert "Third chunk." in result

    def test_chunks_separated_by_blank_line(self) -> None:
        chunks = [
            _make_chunk(text="First."),
            _make_chunk(text="Second."),
        ]
        result = format_context_block(chunks)

        # Two chunks should be separated by \n\n
        blocks = result.split("\n\n")
        assert len(blocks) == 2

    def test_empty_chunks_raises(self) -> None:
        with pytest.raises(ValueError, match="chunks must not be empty"):
            format_context_block([])

    def test_score_formatted_to_two_decimals(self) -> None:
        chunks = [_make_chunk(score=0.123456)]
        result = format_context_block(chunks)
        assert "score: 0.12" in result


class TestFormatSourceList:
    """Test source reference list building."""

    def test_single_source(self) -> None:
        chunks = [_make_chunk()]
        sources = format_source_list(chunks)

        assert len(sources) == 1
        assert sources[0]["index"] == 1
        assert sources[0]["source_name"] == "mixing-secrets.pdf"
        assert sources[0]["page_number"] == 42
        assert sources[0]["score"] == 0.85

    def test_deduplicates_same_source_and_page(self) -> None:
        chunks = [
            _make_chunk(source_name="a.pdf", page_number=1),
            _make_chunk(source_name="a.pdf", page_number=1, chunk_index=1),
        ]
        sources = format_source_list(chunks)
        assert len(sources) == 1

    def test_different_pages_not_deduplicated(self) -> None:
        chunks = [
            _make_chunk(source_name="a.pdf", page_number=1),
            _make_chunk(source_name="a.pdf", page_number=2, chunk_index=1),
        ]
        sources = format_source_list(chunks)
        assert len(sources) == 2

    def test_different_sources_not_deduplicated(self) -> None:
        chunks = [
            _make_chunk(source_name="a.pdf", page_number=1),
            _make_chunk(source_name="b.pdf", page_number=1, chunk_index=1),
        ]
        sources = format_source_list(chunks)
        assert len(sources) == 2

    def test_preserves_first_appearance_order(self) -> None:
        chunks = [
            _make_chunk(source_name="first.pdf", page_number=1),
            _make_chunk(source_name="second.pdf", page_number=2, chunk_index=1),
            _make_chunk(source_name="first.pdf", page_number=1, chunk_index=2),  # duplicate
        ]
        sources = format_source_list(chunks)
        assert len(sources) == 2
        assert sources[0]["source_name"] == "first.pdf"
        assert sources[1]["source_name"] == "second.pdf"

    def test_empty_chunks_returns_empty_list(self) -> None:
        sources = format_source_list([])
        assert sources == []

    def test_score_rounded_to_four_decimals(self) -> None:
        chunks = [_make_chunk(score=0.123456789)]
        sources = format_source_list(chunks)
        assert sources[0]["score"] == 0.1235

    def test_none_page_number_in_source(self) -> None:
        chunks = [_make_chunk(page_number=None)]
        sources = format_source_list(chunks)
        assert sources[0]["page_number"] is None
