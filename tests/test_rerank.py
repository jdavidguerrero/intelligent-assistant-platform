"""
Tests for db/rerank.py — authority boost, filename boost, diversity, and MMR.

All tests are deterministic — no database, no network.
"""

from unittest.mock import MagicMock

import pytest

from db.rerank import (
    _cosine_similarity,
    apply_authority_boost,
    apply_filename_boost,
    enforce_document_diversity,
    infer_content_type,
    mmr_rerank,
    rerank_results,
)


def _rec(
    source_path: str = "/data/courses/school/doc.md",
    source_name: str = "doc.md",
    embedding: list[float] | None = None,
    **kw: object,
) -> MagicMock:
    """Build a lightweight mock ChunkRecord."""
    rec = MagicMock()
    rec.source_path = source_path
    rec.source_name = source_name
    rec.embedding = embedding or [0.0] * 3
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


# ---------------------------------------------------------------------------
# infer_content_type
# ---------------------------------------------------------------------------


class TestInferContentType:
    def test_course(self) -> None:
        assert infer_content_type("/data/courses/school/topic.md") == "course"

    def test_youtube(self) -> None:
        assert infer_content_type("/data/youtube/video.md") == "youtube"

    def test_unknown(self) -> None:
        assert infer_content_type("/data/other/file.md") == "unknown"


# ---------------------------------------------------------------------------
# apply_authority_boost
# ---------------------------------------------------------------------------


class TestAuthorityBoost:
    def test_course_gets_boosted(self) -> None:
        rec = _rec(source_path="/data/courses/school/mix.md")
        result = apply_authority_boost([(rec, 0.80)], course_boost=1.1)
        assert result[0][1] == pytest.approx(0.88, abs=0.001)

    def test_youtube_not_boosted_by_default(self) -> None:
        rec = _rec(source_path="/data/youtube/vid.md")
        result = apply_authority_boost([(rec, 0.80)])
        assert result[0][1] == pytest.approx(0.80)

    def test_score_capped_at_1(self) -> None:
        rec = _rec(source_path="/data/courses/school/mix.md")
        result = apply_authority_boost([(rec, 0.95)], course_boost=1.2)
        assert result[0][1] <= 1.0

    def test_resort_after_boost(self) -> None:
        c = _rec(source_path="/data/courses/school/a.md")
        y = _rec(source_path="/data/youtube/b.md")
        results = [(y, 0.82), (c, 0.78)]
        boosted = apply_authority_boost(results, course_boost=1.1)
        # course (0.78 * 1.1 = 0.858) should now rank above youtube (0.82)
        assert boosted[0][0].source_path == c.source_path


# ---------------------------------------------------------------------------
# apply_filename_boost
# ---------------------------------------------------------------------------


class TestFilenameBoost:
    def test_matching_keyword_boosts(self) -> None:
        rec = _rec(source_name="mastering-chain.md")
        result = apply_filename_boost([(rec, 0.80)], ["mastering"], 1.10)
        assert result[0][1] == pytest.approx(0.88, abs=0.001)

    def test_no_keywords_returns_unchanged(self) -> None:
        rec = _rec(source_name="random.md")
        result = apply_filename_boost([(rec, 0.75)], None)
        assert result[0][1] == pytest.approx(0.75)

    def test_case_insensitive(self) -> None:
        rec = _rec(source_name="MIXING-Basics.md")
        result = apply_filename_boost([(rec, 0.70)], ["mixing"], 1.10)
        assert result[0][1] > 0.70


# ---------------------------------------------------------------------------
# enforce_document_diversity
# ---------------------------------------------------------------------------


class TestDocumentDiversity:
    def test_limits_per_document(self) -> None:
        r1 = _rec(source_path="/a.md")
        r2 = _rec(source_path="/a.md")
        r3 = _rec(source_path="/b.md")
        results = [(r1, 0.9), (r2, 0.85), (r3, 0.80)]
        diverse = enforce_document_diversity(results, max_per_document=1, top_k=5)
        paths = [r.source_path for r, _ in diverse]
        assert paths == ["/a.md", "/b.md"]

    def test_respects_top_k(self) -> None:
        records = [(_rec(source_path=f"/{i}.md"), 0.9 - i * 0.01) for i in range(10)]
        diverse = enforce_document_diversity(records, max_per_document=1, top_k=3)
        assert len(diverse) == 3


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0


# ---------------------------------------------------------------------------
# mmr_rerank
# ---------------------------------------------------------------------------


class TestMMR:
    def test_empty_results(self) -> None:
        assert mmr_rerank([], [1.0, 0.0]) == []

    def test_returns_top_k(self) -> None:
        records = [
            (_rec(embedding=[1.0, 0.0, 0.0]), 0.9),
            (_rec(embedding=[0.9, 0.1, 0.0]), 0.85),
            (_rec(embedding=[0.0, 1.0, 0.0]), 0.80),
        ]
        result = mmr_rerank(records, [1.0, 0.0, 0.0], top_k=2)
        assert len(result) == 2

    def test_lambda_1_is_pure_relevance(self) -> None:
        """With lambda=1.0, MMR equals simple top-k by score."""
        r_high = _rec(embedding=[1.0, 0.0])
        r_low = _rec(embedding=[0.0, 1.0])
        results = [(r_high, 0.9), (r_low, 0.5)]
        ranked = mmr_rerank(results, [1.0, 0.0], lambda_=1.0, top_k=2)
        assert ranked[0][1] == 0.9
        assert ranked[1][1] == 0.5

    def test_lambda_0_promotes_diversity(self) -> None:
        """With lambda=0, MMR should prefer the most dissimilar result second."""
        # Two similar embeddings and one very different
        r_a = _rec(embedding=[1.0, 0.0, 0.0])
        r_b = _rec(embedding=[0.99, 0.01, 0.0])  # very similar to a
        r_c = _rec(embedding=[0.0, 0.0, 1.0])  # very different from a
        results = [(r_a, 0.9), (r_b, 0.89), (r_c, 0.50)]
        ranked = mmr_rerank(results, [1.0, 0.0, 0.0], lambda_=0.0, top_k=3)
        # First pick = r_a (highest score, no redundancy penalty)
        # Second pick should be r_c (dissimilar to r_a), not r_b
        assert ranked[1][1] == 0.50  # r_c's original score


# ---------------------------------------------------------------------------
# rerank_results (orchestrator)
# ---------------------------------------------------------------------------


class TestRerankResults:
    def test_default_uses_document_diversity(self) -> None:
        r1 = _rec(source_path="/data/courses/school/a.md")
        r2 = _rec(source_path="/data/courses/school/a.md")
        r3 = _rec(source_path="/data/courses/school/b.md")
        results = [(r1, 0.9), (r2, 0.85), (r3, 0.80)]
        reranked = rerank_results(results, top_k=5, use_mmr=False)
        paths = [r.source_path for r, _ in reranked]
        # diversity filter: max 1 per doc
        assert len(set(paths)) == len(paths)

    def test_mmr_flag_activates_mmr(self) -> None:
        r1 = _rec(embedding=[1.0, 0.0, 0.0])
        r2 = _rec(embedding=[0.99, 0.01, 0.0])
        r3 = _rec(embedding=[0.0, 0.0, 1.0])
        results = [(r1, 0.9), (r2, 0.89), (r3, 0.50)]
        reranked = rerank_results(
            results,
            top_k=3,
            use_mmr=True,
            query_embedding=[1.0, 0.0, 0.0],
            mmr_lambda=0.3,
        )
        assert len(reranked) == 3

    def test_mmr_without_embedding_falls_back(self) -> None:
        """use_mmr=True but no query_embedding → uses document diversity."""
        r1 = _rec(source_path="/a.md")
        r2 = _rec(source_path="/b.md")
        results = [(r1, 0.9), (r2, 0.8)]
        reranked = rerank_results(results, top_k=2, use_mmr=True)
        assert len(reranked) == 2
