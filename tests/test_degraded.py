"""Tests for core/rag/degraded.py — build_degraded_response().

Covers:
- Returns DegradedResponse with mode="degraded"
- No chunks → graceful empty response
- Citations match chunk count
- Text truncation at _MAX_CHARS_PER_CHUNK
- Page number shown when available
- Score formatted in output
- All defined reason codes produce non-empty messages
- Unknown reason falls back to "unknown" message
"""

from __future__ import annotations

import pytest

from core.rag.context import RetrievedChunk
from core.rag.degraded import _MAX_CHARS_PER_CHUNK, DegradedResponse, build_degraded_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    text: str = "Sample text about music production.",
    source_name: str = "bob_katz.pdf",
    source_path: str = "/data/bob_katz.pdf",
    chunk_index: int = 0,
    score: float = 0.85,
    page_number: int | None = 42,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        source_name=source_name,
        source_path=source_path,
        chunk_index=chunk_index,
        score=score,
        page_number=page_number,
    )


# ---------------------------------------------------------------------------
# Return type and basic fields
# ---------------------------------------------------------------------------


class TestDegradedResponseType:
    def test_returns_degraded_response_instance(self) -> None:
        result = build_degraded_response(
            query="How do I sidechain?",
            retrieved_chunks=[_make_chunk()],
        )
        assert isinstance(result, DegradedResponse)

    def test_mode_is_degraded(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[_make_chunk()])
        assert result.mode == "degraded"

    def test_answer_is_non_empty_string(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[_make_chunk()])
        assert isinstance(result.answer, str)
        assert len(result.answer) > 0

    def test_warning_matches_reason(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk()],
            reason="circuit_open",
        )
        assert result.warning == "circuit_open"

    def test_default_reason_is_llm_unavailable(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[_make_chunk()])
        assert result.warning == "llm_unavailable"


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


class TestCitations:
    def test_citations_match_chunk_count(self) -> None:
        chunks = [_make_chunk(chunk_index=i) for i in range(3)]
        result = build_degraded_response(query="test", retrieved_chunks=chunks)
        assert result.citations == [1, 2, 3]

    def test_single_chunk_citation(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[_make_chunk()])
        assert result.citations == [1]

    def test_no_chunks_empty_citations(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[])
        assert result.citations == []

    def test_five_chunks_five_citations(self) -> None:
        chunks = [_make_chunk(chunk_index=i) for i in range(5)]
        result = build_degraded_response(query="test", retrieved_chunks=chunks)
        assert result.citations == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Answer content
# ---------------------------------------------------------------------------


class TestAnswerContent:
    def test_answer_contains_source_name(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(source_name="bob_katz.pdf")],
        )
        assert "bob_katz.pdf" in result.answer

    def test_answer_contains_page_number_when_present(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(page_number=42)],
        )
        assert "p.42" in result.answer

    def test_answer_no_page_info_when_none(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(page_number=None)],
        )
        assert "p." not in result.answer

    def test_answer_contains_score(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(score=0.87)],
        )
        assert "0.87" in result.answer

    def test_answer_contains_chunk_text(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(text="Use high-pass filter at 80Hz.")],
        )
        assert "Use high-pass filter at 80Hz." in result.answer

    def test_answer_contains_citation_bracket(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[_make_chunk()])
        assert "[1]" in result.answer

    def test_answer_contains_intro_message(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk()],
            reason="llm_unavailable",
        )
        # Should contain some human-readable intro (not just raw chunks)
        assert len(result.answer.split("\n")) > 2


# ---------------------------------------------------------------------------
# Text truncation
# ---------------------------------------------------------------------------


class TestTextTruncation:
    def test_long_text_is_truncated(self) -> None:
        long_text = "word " * (_MAX_CHARS_PER_CHUNK // 4)  # well over limit
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(text=long_text)],
        )
        # Truncated text should end with ellipsis
        assert "…" in result.answer

    def test_short_text_not_truncated(self) -> None:
        short_text = "Short passage about EQ."
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(text=short_text)],
        )
        assert short_text in result.answer
        assert "…" not in result.answer

    def test_truncation_does_not_split_words(self) -> None:
        # Text exactly at the boundary followed by a long word
        boundary_text = "a " * ((_MAX_CHARS_PER_CHUNK // 2) - 1) + "verylongwordatend"
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk(text=boundary_text)],
        )
        # Should end with "…" not mid-word
        if "…" in result.answer:
            # The character before "…" should be a space or word boundary
            # (rsplit ensures we don't cut in the middle of a word)
            assert "verylongwordatend" not in result.answer


# ---------------------------------------------------------------------------
# No chunks — graceful empty case
# ---------------------------------------------------------------------------


class TestNoChunks:
    def test_no_chunks_returns_degraded_response(self) -> None:
        result = build_degraded_response(query="How to EQ?", retrieved_chunks=[])
        assert isinstance(result, DegradedResponse)
        assert result.mode == "degraded"

    def test_no_chunks_answer_contains_query(self) -> None:
        result = build_degraded_response(query="How do I sidechain the kick?", retrieved_chunks=[])
        assert "How do I sidechain the kick?" in result.answer

    def test_no_chunks_empty_citations(self) -> None:
        result = build_degraded_response(query="test", retrieved_chunks=[])
        assert result.citations == []


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


class TestReasonCodes:
    @pytest.mark.parametrize(
        "reason",
        ["llm_unavailable", "embedding_unavailable", "search_failed", "circuit_open", "unknown"],
    )
    def test_all_known_reasons_produce_non_empty_answer(self, reason: str) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk()],
            reason=reason,
        )
        assert len(result.answer) > 0
        assert result.warning == reason

    def test_unknown_reason_falls_back_gracefully(self) -> None:
        result = build_degraded_response(
            query="test",
            retrieved_chunks=[_make_chunk()],
            reason="totally_unrecognized_reason",
        )
        # Should not raise — should use fallback message
        assert isinstance(result.answer, str)
        assert result.warning == "totally_unrecognized_reason"


# ---------------------------------------------------------------------------
# Pure function — no side effects
# ---------------------------------------------------------------------------


class TestPurity:
    def test_same_input_same_output(self) -> None:
        chunks = [_make_chunk()]
        r1 = build_degraded_response(query="test", retrieved_chunks=chunks)
        r2 = build_degraded_response(query="test", retrieved_chunks=chunks)
        assert r1.answer == r2.answer
        assert r1.citations == r2.citations

    def test_does_not_mutate_chunks(self) -> None:
        chunk = _make_chunk(text="Original text.")
        original_text = chunk.text
        build_degraded_response(query="test", retrieved_chunks=[chunk])
        assert chunk.text == original_text
