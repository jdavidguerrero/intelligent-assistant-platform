"""
Result reranking for search quality improvements.

Implements document diversity and authority-based boosting
to improve perceived search quality and business value.
"""

from db.models import ChunkRecord


def infer_content_type(source_path: str) -> str:
    """
    Infer content type from source path.

    Args:
        source_path: Full path to source document

    Returns:
        "course" for structured educational content,
        "youtube" for video tutorials,
        "unknown" for others
    """
    if "/courses/" in source_path:
        return "course"
    if "/youtube/" in source_path:
        return "youtube"
    return "unknown"


def apply_authority_boost(
    results: list[tuple[ChunkRecord, float]],
    course_boost: float = 1.1,
    youtube_boost: float = 1.0,
) -> list[tuple[ChunkRecord, float]]:
    """
    Apply authority-based score boosting.

    Business rule: Prefer structured course content over YouTube
    when similarity scores are comparable.

    Args:
        results: List of (ChunkRecord, similarity_score) from search
        course_boost: Multiplier for course content (default: 1.1 = +10%)
        youtube_boost: Multiplier for YouTube content (default: 1.0 = no boost)

    Returns:
        Same results with adjusted scores
    """
    boosted = []

    for record, score in results:
        content_type = infer_content_type(record.source_path)

        if content_type == "course":
            adjusted_score = min(1.0, score * course_boost)  # Cap at 1.0
        elif content_type == "youtube":
            adjusted_score = score * youtube_boost
        else:
            adjusted_score = score

        boosted.append((record, adjusted_score))

    # Re-sort by adjusted scores
    boosted.sort(key=lambda x: x[1], reverse=True)

    return boosted


def apply_filename_boost(
    results: list[tuple[ChunkRecord, float]],
    boost_keywords: list[str] | None = None,
    boost_multiplier: float = 1.10,
) -> list[tuple[ChunkRecord, float]]:
    """
    Apply score boost to results whose filename contains specific keywords.

    Useful for boosting relevance when filename contains query-related terms
    (e.g., "masterclass", "mastering", "mixing").

    Args:
        results: List of (ChunkRecord, similarity_score) from search
        boost_keywords: Keywords to match in source_name (case-insensitive)
        boost_multiplier: Multiplier for matching results (default: 1.10 = +10%)

    Returns:
        Same results with adjusted scores, re-sorted
    """
    if not boost_keywords:
        return results

    boosted = []

    for record, score in results:
        source_lower = record.source_name.lower()

        # Check if any keyword matches filename
        has_match = any(keyword.lower() in source_lower for keyword in boost_keywords)

        if has_match:
            adjusted_score = min(1.0, score * boost_multiplier)  # Cap at 1.0
        else:
            adjusted_score = score

        boosted.append((record, adjusted_score))

    # Re-sort by adjusted scores
    boosted.sort(key=lambda x: x[1], reverse=True)

    return boosted


def enforce_document_diversity(
    results: list[tuple[ChunkRecord, float]],
    max_per_document: int = 1,
    top_k: int = 5,
) -> list[tuple[ChunkRecord, float]]:
    """
    Enforce maximum chunks per document in results.

    Business rule: Top-k should show diverse documents,
    not multiple chunks from the same source.

    Args:
        results: List of (ChunkRecord, similarity_score) sorted by score
        max_per_document: Maximum chunks allowed per source_path (default: 1)
        top_k: Desired number of final results

    Returns:
        Filtered results with document diversity enforced
    """
    seen_documents: dict[str, int] = {}
    diverse_results = []

    for record, score in results:
        doc_count = seen_documents.get(record.source_path, 0)

        if doc_count < max_per_document:
            diverse_results.append((record, score))
            seen_documents[record.source_path] = doc_count + 1

            if len(diverse_results) >= top_k:
                break

    return diverse_results


def rerank_results(
    results: list[tuple[ChunkRecord, float]],
    top_k: int = 5,
    max_per_document: int = 1,
    course_boost: float = 1.1,
    youtube_boost: float = 1.0,
    filename_keywords: list[str] | None = None,
    filename_boost: float = 1.10,
) -> list[tuple[ChunkRecord, float]]:
    """
    Full reranking pipeline: authority boost + filename boost + document diversity.

    Args:
        results: Raw results from search_chunks
        top_k: Desired number of final results
        max_per_document: Max chunks per document (1 = full diversity)
        course_boost: Authority multiplier for course content
        youtube_boost: Authority multiplier for YouTube content
        filename_keywords: Optional keywords to boost in filenames
        filename_boost: Multiplier for filename keyword matches

    Returns:
        Reranked results optimized for quality and diversity
    """
    # Step 1: Apply authority-based boosting
    boosted = apply_authority_boost(results, course_boost, youtube_boost)

    # Step 2: Apply filename-based boosting (if keywords provided)
    if filename_keywords:
        boosted = apply_filename_boost(boosted, filename_keywords, filename_boost)

    # Step 3: Enforce document diversity
    diverse = enforce_document_diversity(boosted, max_per_document, top_k)

    return diverse
