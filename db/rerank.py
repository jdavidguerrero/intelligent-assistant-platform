"""
Result reranking for search quality improvements.

Implements document diversity, authority-based boosting, and MMR
(Maximal Marginal Relevance) to improve perceived search quality
and business value.
"""

import numpy as np

from db.models import ChunkRecord


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity in the range [-1, 1].
    """
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


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


def mmr_rerank(
    results: list[tuple[ChunkRecord, float]],
    query_embedding: list[float],
    *,
    lambda_: float = 0.7,
    top_k: int = 5,
) -> list[tuple[ChunkRecord, float]]:
    """Select results via Maximal Marginal Relevance (MMR).

    MMR balances **relevance** (similarity to query) against
    **diversity** (dissimilarity to already-selected results).

    ``score_mmr = lambda_ * relevance - (1 - lambda_) * max_redundancy``

    Args:
        results: Candidate ``(ChunkRecord, similarity_score)`` pairs.
            Each ``ChunkRecord`` must have a populated ``embedding`` attribute.
        query_embedding: The query's embedding vector.
        lambda_: Trade-off parameter (0–1).  1.0 = pure relevance,
            0.0 = pure diversity.  Default 0.7.
        top_k: Number of results to return.

    Returns:
        Up to *top_k* ``(ChunkRecord, score)`` tuples reranked by MMR.
    """
    if not results:
        return []

    candidates = list(results)
    selected: list[tuple[ChunkRecord, float]] = []

    while len(selected) < top_k and candidates:
        best_mmr = float("-inf")
        best_idx = 0

        for i, (record, relevance) in enumerate(candidates):
            # Max similarity to any already-selected result
            if selected:
                redundancy = max(
                    _cosine_similarity(record.embedding, sel_rec.embedding)
                    for sel_rec, _ in selected
                )
            else:
                redundancy = 0.0

            mmr_score = lambda_ * relevance - (1.0 - lambda_) * redundancy

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        chosen_record, chosen_score = candidates.pop(best_idx)
        selected.append((chosen_record, chosen_score))

    return selected


def rerank_results(
    results: list[tuple[ChunkRecord, float]],
    top_k: int = 5,
    max_per_document: int = 1,
    course_boost: float = 1.1,
    youtube_boost: float = 1.0,
    filename_keywords: list[str] | None = None,
    filename_boost: float = 1.10,
    query_embedding: list[float] | None = None,
    mmr_lambda: float = 0.7,
    use_mmr: bool = False,
) -> list[tuple[ChunkRecord, float]]:
    """
    Full reranking pipeline: authority boost + filename boost + diversity.

    When ``use_mmr`` is True and ``query_embedding`` is provided, the
    diversity step uses MMR instead of the simpler document-count filter.

    Args:
        results: Raw results from search_chunks
        top_k: Desired number of final results
        max_per_document: Max chunks per document (1 = full diversity)
        course_boost: Authority multiplier for course content
        youtube_boost: Authority multiplier for YouTube content
        filename_keywords: Optional keywords to boost in filenames
        filename_boost: Multiplier for filename keyword matches
        query_embedding: Query vector (required when ``use_mmr=True``)
        mmr_lambda: MMR trade-off parameter (0=diversity, 1=relevance)
        use_mmr: If True, use MMR for diversity instead of document-count

    Returns:
        Reranked results optimized for quality and diversity
    """
    # Step 1: Apply authority-based boosting
    boosted = apply_authority_boost(results, course_boost, youtube_boost)

    # Step 2: Apply filename-based boosting (if keywords provided)
    if filename_keywords:
        boosted = apply_filename_boost(boosted, filename_keywords, filename_boost)

    # Step 3: Enforce diversity (MMR or document-count)
    if use_mmr and query_embedding is not None:
        diverse = mmr_rerank(
            boosted,
            query_embedding,
            lambda_=mmr_lambda,
            top_k=top_k,
        )
    else:
        diverse = enforce_document_diversity(boosted, max_per_document, top_k)

    return diverse
