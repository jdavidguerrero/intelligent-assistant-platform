"""
Tests for core/rag/citations.py — citation extraction and validation.

Validates the regex-based parser and the validation logic that detects
hallucinated source references.
"""

import pytest

from core.rag.citations import CitationResult, extract_citations, validate_citations


class TestExtractCitations:
    """Test citation extraction from LLM responses."""

    def test_single_citation(self) -> None:
        text = "Use a high-pass filter at 30Hz [1]."
        result = extract_citations(text)
        assert result == [1]

    def test_multiple_citations(self) -> None:
        text = "Cut at 300Hz [1] and boost at 5kHz [3]."
        result = extract_citations(text)
        assert result == [1, 3]

    def test_repeated_citations(self) -> None:
        text = "Sidechain [2] is explained in detail [2]."
        result = extract_citations(text)
        assert result == [2, 2]

    def test_no_citations(self) -> None:
        text = "This text has no citations at all."
        result = extract_citations(text)
        assert result == []

    def test_multi_digit_citation(self) -> None:
        text = "According to [42], the ratio should be 4:1."
        result = extract_citations(text)
        assert result == [42]

    def test_citations_in_different_positions(self) -> None:
        text = "[1] At the start, middle [2], and end [3]."
        result = extract_citations(text)
        assert result == [1, 2, 3]

    def test_ignores_non_citation_brackets(self) -> None:
        text = "Use EQ [high-pass] and compression [ratio]."
        result = extract_citations(text)
        assert result == []

    def test_citations_adjacent_to_punctuation(self) -> None:
        text = "Use EQ [1], compression [2], and reverb [3]."
        result = extract_citations(text)
        assert result == [1, 2, 3]

    def test_citations_in_sentence_with_numbers(self) -> None:
        text = "Set ratio to 4:1 [2] at 300Hz [3]."
        result = extract_citations(text)
        assert result == [2, 3]

    def test_empty_string(self) -> None:
        result = extract_citations("")
        assert result == []


class TestValidateCitations:
    """Test citation validation against source map."""

    def test_all_valid_citations(self) -> None:
        result = validate_citations([1, 2, 3], num_sources=5)
        assert result.citations == (1, 2, 3)
        assert result.invalid_citations == ()

    def test_citation_above_range(self) -> None:
        result = validate_citations([1, 6], num_sources=5)
        assert result.citations == (1, 6)
        assert result.invalid_citations == (6,)

    def test_citation_below_range(self) -> None:
        result = validate_citations([0, 1], num_sources=5)
        assert result.citations == (0, 1)
        assert result.invalid_citations == (0,)

    def test_multiple_invalid_citations(self) -> None:
        result = validate_citations([1, 6, 7, 2], num_sources=5)
        assert result.citations == (1, 2, 6, 7)
        assert result.invalid_citations == (6, 7)

    def test_deduplicates_citations(self) -> None:
        result = validate_citations([1, 2, 1, 2], num_sources=5)
        assert result.citations == (1, 2)
        assert result.invalid_citations == ()

    def test_sorts_citations(self) -> None:
        result = validate_citations([3, 1, 2], num_sources=5)
        assert result.citations == (1, 2, 3)

    def test_empty_citations(self) -> None:
        result = validate_citations([], num_sources=5)
        assert result.citations == ()
        assert result.invalid_citations == ()

    def test_all_invalid_citations(self) -> None:
        result = validate_citations([6, 7, 8], num_sources=5)
        assert result.citations == (6, 7, 8)
        assert result.invalid_citations == (6, 7, 8)

    def test_boundary_cases(self) -> None:
        # Citation exactly at boundary
        result = validate_citations([1, 5], num_sources=5)
        assert result.invalid_citations == ()

        # Citation just outside boundary
        result = validate_citations([1, 6], num_sources=5)
        assert result.invalid_citations == (6,)


class TestCitationResult:
    """Test CitationResult frozen dataclass."""

    def test_creates_with_all_fields(self) -> None:
        result = CitationResult(citations=(1, 2, 3), invalid_citations=(5,))
        assert result.citations == (1, 2, 3)
        assert result.invalid_citations == (5,)

    def test_frozen(self) -> None:
        result = CitationResult(citations=(1, 2), invalid_citations=())
        with pytest.raises(AttributeError):
            result.citations = (3, 4)  # type: ignore[misc]
