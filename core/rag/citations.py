"""
Citation extraction and validation for RAG responses.

The LLM is instructed to cite sources using bracketed numbers like [1], [2].
This module parses those citations from the generated text and validates
them against the source map to detect hallucinated references.

Pure functions — no I/O, no side effects.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CitationResult:
    """Result of citation extraction and validation.

    Attributes:
        citations: List of citation indices found in the text (e.g., [1, 2, 5]).
        invalid_citations: Citations that don't map to any provided source.
            Empty if all citations are valid.
    """

    citations: tuple[int, ...]
    invalid_citations: tuple[int, ...]


def extract_citations(text: str) -> list[int]:
    """Extract citation indices from LLM-generated text.

    Finds all bracketed numbers like [1], [2], [42] in the text.
    Returns them as integers in order of appearance (may contain duplicates).

    Args:
        text: The generated response text.

    Returns:
        List of citation indices (e.g., [1, 2, 1, 5]).
        Empty list if no citations found.

    Examples:
        >>> extract_citations("Use EQ [1] and compression [2].")
        [1, 2]
        >>> extract_citations("Apply sidechain [3] with a ratio of 4:1 [3].")
        [3, 3]
        >>> extract_citations("No citations here.")
        []
    """
    # Match [<number>] pattern
    # Use \b word boundary to avoid matching things like [1.5] or [1a]
    pattern = r"\[(\d+)\]"
    matches = re.findall(pattern, text)
    return [int(m) for m in matches]


def validate_citations(citations: list[int], num_sources: int) -> CitationResult:
    """Validate that all citations map to actual sources.

    A citation is valid if its index is in the range [1, num_sources].
    The LLM is given sources numbered [1], [2], ..., [num_sources].

    Args:
        citations: List of citation indices extracted from the response.
        num_sources: Number of sources provided to the LLM.

    Returns:
        CitationResult with unique citations and any invalid indices.

    Examples:
        >>> validate_citations([1, 2, 1], num_sources=3)
        CitationResult(citations=(1, 2), invalid_citations=())
        >>> validate_citations([1, 5, 2], num_sources=3)
        CitationResult(citations=(1, 2, 5), invalid_citations=(5,))
        >>> validate_citations([], num_sources=5)
        CitationResult(citations=(), invalid_citations=())
    """
    unique_citations = tuple(sorted(set(citations)))
    invalid = tuple(c for c in unique_citations if c < 1 or c > num_sources)
    return CitationResult(citations=unique_citations, invalid_citations=invalid)
