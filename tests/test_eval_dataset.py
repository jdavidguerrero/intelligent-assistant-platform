"""Tests for eval/dataset.py — golden dataset structure and invariants.

Validates that the 50-query golden dataset satisfies all structural
requirements: unique IDs, correct counts per sub-domain, non-empty
questions, proper topic/source annotations for non-adversarial queries,
and cross-domain list integrity.
"""

from __future__ import annotations

from eval.dataset import (
    DATASET_BY_ID,
    GOLDEN_DATASET,
    GoldenQuery,
    SubDomain,
)


class TestDatasetSize:
    """Validate the overall dataset size."""

    def test_dataset_has_50_queries(self) -> None:
        """GOLDEN_DATASET must contain exactly 50 entries."""
        assert len(GOLDEN_DATASET) == 50

    def test_dataset_by_id_lookup(self) -> None:
        """DATASET_BY_ID must contain exactly 50 entries (one per unique id)."""
        assert len(DATASET_BY_ID) == 50


class TestDatasetUniqueness:
    """Validate that query identifiers are globally unique."""

    def test_all_ids_unique(self) -> None:
        """No two queries share the same id."""
        ids = [q.id for q in GOLDEN_DATASET]
        assert len(ids) == len(set(ids)), "Duplicate query ids found in GOLDEN_DATASET"

    def test_all_questions_nonempty(self) -> None:
        """Every query must have a non-empty question string."""
        for q in GOLDEN_DATASET:
            assert isinstance(q.question, str), f"{q.id}: question is not a str"
            assert q.question.strip(), f"{q.id}: question is empty or whitespace-only"


class TestSubDomainCounts:
    """Validate per-sub-domain query counts."""

    def _count(self, sub_domain: SubDomain) -> int:
        return sum(1 for q in GOLDEN_DATASET if q.sub_domain == sub_domain)

    def test_subdomain_count_sound_design(self) -> None:
        """sound_design sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.SOUND_DESIGN) == 5

    def test_subdomain_count_arrangement(self) -> None:
        """arrangement sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.ARRANGEMENT) == 5

    def test_subdomain_count_mixing(self) -> None:
        """mixing sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.MIXING) == 5

    def test_subdomain_count_genre(self) -> None:
        """genre sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.GENRE) == 5

    def test_subdomain_count_live_performance(self) -> None:
        """live_performance sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.LIVE_PERFORMANCE) == 5

    def test_subdomain_count_practice(self) -> None:
        """practice sub-domain must have exactly 5 queries."""
        assert self._count(SubDomain.PRACTICE) == 5

    def test_subdomain_count_cross(self) -> None:
        """cross sub-domain must have exactly 10 queries."""
        assert self._count(SubDomain.CROSS) == 10

    def test_subdomain_count_adversarial(self) -> None:
        """adversarial sub-domain must have exactly 10 queries."""
        assert self._count(SubDomain.ADVERSARIAL) == 10


class TestNonAdversarialAnnotations:
    """Non-adversarial queries must carry useful ground-truth annotations."""

    def _non_adversarial(self) -> list[GoldenQuery]:
        return [q for q in GOLDEN_DATASET if not q.adversarial]

    def test_non_adversarial_have_topics(self) -> None:
        """All non-adversarial queries must have at least one expected topic."""
        for q in self._non_adversarial():
            assert (
                len(q.expected_topics) > 0
            ), f"{q.id}: non-adversarial query has empty expected_topics"

    def test_non_adversarial_have_sources(self) -> None:
        """All non-adversarial queries must have at least one expected source."""
        for q in self._non_adversarial():
            assert (
                len(q.expected_sources) > 0
            ), f"{q.id}: non-adversarial query has empty expected_sources"


class TestAdversarialAnnotations:
    """Adversarial queries must have empty topic/source lists."""

    def _adversarial(self) -> list[GoldenQuery]:
        return [q for q in GOLDEN_DATASET if q.adversarial]

    def test_adversarial_have_empty_topics(self) -> None:
        """All adversarial queries must have empty expected_topics."""
        for q in self._adversarial():
            assert (
                q.expected_topics == []
            ), f"{q.id}: adversarial query has non-empty expected_topics"

    def test_adversarial_have_empty_sources(self) -> None:
        """All adversarial queries must have empty expected_sources."""
        for q in self._adversarial():
            assert (
                q.expected_sources == []
            ), f"{q.id}: adversarial query has non-empty expected_sources"

    def test_adversarial_flag_matches_subdomain(self) -> None:
        """Queries with adversarial=True must belong to the ADVERSARIAL sub-domain."""
        for q in self._adversarial():
            assert (
                q.sub_domain == SubDomain.ADVERSARIAL
            ), f"{q.id}: adversarial=True but sub_domain={q.sub_domain}"


class TestCrossDomainAnnotations:
    """Cross-domain queries must reference at least two additional sub-domains."""

    def _cross_queries(self) -> list[GoldenQuery]:
        return [q for q in GOLDEN_DATASET if q.sub_domain == SubDomain.CROSS]

    def test_cross_domain_have_cross_domains_list(self) -> None:
        """All CROSS queries must list at least 2 cross_domains."""
        for q in self._cross_queries():
            assert len(q.cross_domains) >= 2, (
                f"{q.id}: CROSS query has fewer than 2 cross_domains " f"(got {q.cross_domains})"
            )

    def test_cross_domains_are_subdomain_enums(self) -> None:
        """All cross_domains entries must be valid SubDomain enum values."""
        for q in self._cross_queries():
            for domain in q.cross_domains:
                assert isinstance(
                    domain, SubDomain
                ), f"{q.id}: cross_domains contains non-SubDomain value {domain!r}"


class TestDatasetByIdLookup:
    """Validate the DATASET_BY_ID convenience mapping."""

    def test_dataset_by_id_all_ids_reachable(self) -> None:
        """Every query id in GOLDEN_DATASET must be reachable via DATASET_BY_ID."""
        for q in GOLDEN_DATASET:
            assert q.id in DATASET_BY_ID, f"{q.id} missing from DATASET_BY_ID"

    def test_dataset_by_id_values_are_golden_queries(self) -> None:
        """All values in DATASET_BY_ID must be GoldenQuery instances."""
        for key, value in DATASET_BY_ID.items():
            assert isinstance(value, GoldenQuery), f"DATASET_BY_ID[{key!r}] is not a GoldenQuery"

    def test_dataset_by_id_key_matches_query_id(self) -> None:
        """Each key in DATASET_BY_ID must match the .id of its GoldenQuery."""
        for key, value in DATASET_BY_ID.items():
            assert key == value.id, f"Key {key!r} does not match query id {value.id!r}"
