"""Tests for eval/retrieval_metrics.py — precision, recall, MRR, and aggregation.

All functions are pure (no I/O), so every test is fully deterministic.
NaN-handling semantics are verified explicitly for the adversarial case where
expected_sources is empty.
"""

from __future__ import annotations

import math

import pytest

from eval.retrieval_metrics import aggregate_metrics, mrr, precision_at_k, recall_at_k


class TestPrecisionAtK:
    """Unit tests for precision_at_k()."""

    def test_precision_perfect(self) -> None:
        """All K returned sources match expected → precision = 1.0."""
        sources = ["pete-tong-course.pdf", "mixing-guide.pdf", "synthesis-basics.pdf"]
        expected = ["pete-tong", "mixing", "synthesis"]
        result = precision_at_k(sources, expected, k=3)
        assert result == pytest.approx(1.0)

    def test_precision_none(self) -> None:
        """No returned sources match any expected pattern → precision = 0.0."""
        sources = ["random-doc.pdf", "unrelated.txt"]
        expected = ["pete-tong", "mixing"]
        result = precision_at_k(sources, expected, k=5)
        assert result == pytest.approx(0.0)

    def test_precision_partial(self) -> None:
        """2 out of 5 top-K sources are relevant → precision = 0.4."""
        sources = [
            "pete-tong-course.pdf",  # relevant (matches "pete-tong")
            "unrelated-a.pdf",
            "mixing-guide.pdf",      # relevant (matches "mixing")
            "unrelated-b.pdf",
            "unrelated-c.pdf",
        ]
        expected = ["pete-tong", "mixing"]
        result = precision_at_k(sources, expected, k=5)
        assert result == pytest.approx(0.4)

    def test_precision_respects_k(self) -> None:
        """Only the first K sources are evaluated; sources beyond K are ignored."""
        sources = [
            "unrelated-a.pdf",
            "unrelated-b.pdf",
            "pete-tong-course.pdf",  # rank 3 — outside k=2
        ]
        expected = ["pete-tong"]
        # With k=2, only first 2 are evaluated — both unrelated → 0.0
        assert precision_at_k(sources, expected, k=2) == pytest.approx(0.0)
        # With k=3, third source matches → 1/3
        assert precision_at_k(sources, expected, k=3) == pytest.approx(1 / 3)

    def test_precision_empty_returned_sources(self) -> None:
        """Empty returned_sources list → precision = 0.0."""
        assert precision_at_k([], ["pete-tong"], k=5) == pytest.approx(0.0)

    def test_precision_empty_expected_sources(self) -> None:
        """Empty expected_sources (adversarial query) → precision = 0.0."""
        assert precision_at_k(["pete-tong.pdf"], [], k=5) == pytest.approx(0.0)

    def test_precision_k_zero(self) -> None:
        """k=0 is a degenerate case → precision = 0.0."""
        assert precision_at_k(["pete-tong.pdf"], ["pete-tong"], k=0) == pytest.approx(0.0)

    def test_precision_case_insensitive(self) -> None:
        """Source matching is case-insensitive."""
        sources = ["Pete-Tong-Course.PDF"]
        expected = ["pete-tong"]
        assert precision_at_k(sources, expected, k=1) == pytest.approx(1.0)


class TestRecallAtK:
    """Unit tests for recall_at_k()."""

    def test_recall_perfect(self) -> None:
        """All expected sources found in top-K → recall = 1.0."""
        sources = ["pete-tong-v1.pdf", "mixing-guide.pdf"]
        expected = ["pete-tong", "mixing"]
        assert recall_at_k(sources, expected, k=5) == pytest.approx(1.0)

    def test_recall_none(self) -> None:
        """None of the expected sources found → recall = 0.0."""
        sources = ["unrelated-a.pdf", "unrelated-b.pdf"]
        expected = ["pete-tong", "mixing"]
        assert recall_at_k(sources, expected, k=5) == pytest.approx(0.0)

    def test_recall_partial(self) -> None:
        """1 out of 2 expected sources found → recall = 0.5."""
        sources = ["pete-tong-course.pdf", "unrelated.pdf"]
        expected = ["pete-tong", "mixing"]
        assert recall_at_k(sources, expected, k=5) == pytest.approx(0.5)

    def test_recall_empty_expected(self) -> None:
        """Empty expected_sources → recall is NaN (adversarial; undefined)."""
        result = recall_at_k(["pete-tong.pdf"], [], k=5)
        assert math.isnan(result)

    def test_recall_respects_k(self) -> None:
        """Sources beyond rank K are not considered for recall."""
        sources = [
            "unrelated-a.pdf",   # rank 1
            "pete-tong.pdf",     # rank 2
            "mixing-guide.pdf",  # rank 3 — outside k=2
        ]
        expected = ["pete-tong", "mixing"]
        # k=2: only ranks 1-2 evaluated → 1 match ("pete-tong") out of 2 expected → 0.5
        assert recall_at_k(sources, expected, k=2) == pytest.approx(0.5)

    def test_recall_case_insensitive(self) -> None:
        """Source pattern matching is case-insensitive."""
        sources = ["PETE-TONG-COURSE.PDF"]
        expected = ["pete-tong"]
        assert recall_at_k(sources, expected, k=5) == pytest.approx(1.0)


class TestMRR:
    """Unit tests for mrr()."""

    def test_mrr_first_relevant(self) -> None:
        """First source is relevant → MRR = 1.0."""
        sources = ["pete-tong-course.pdf", "unrelated.pdf"]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(1.0)

    def test_mrr_second_relevant(self) -> None:
        """Second source is relevant → MRR = 0.5."""
        sources = ["unrelated.pdf", "pete-tong-course.pdf"]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(0.5)

    def test_mrr_third_relevant(self) -> None:
        """Third source is relevant → MRR = 1/3."""
        sources = ["unrelated-a.pdf", "unrelated-b.pdf", "pete-tong-course.pdf"]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(1 / 3)

    def test_mrr_none_relevant(self) -> None:
        """No relevant source in the list → MRR = 0.0."""
        sources = ["unrelated-a.pdf", "unrelated-b.pdf"]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(0.0)

    def test_mrr_empty_expected(self) -> None:
        """Empty expected_sources → MRR is NaN (adversarial; undefined)."""
        result = mrr(["pete-tong.pdf"], [])
        assert math.isnan(result)

    def test_mrr_empty_returned(self) -> None:
        """Empty returned sources list with non-empty expected → MRR = 0.0."""
        assert mrr([], ["pete-tong"]) == pytest.approx(0.0)

    def test_mrr_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        sources = ["PETE-TONG.PDF"]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(1.0)

    def test_mrr_returns_first_match(self) -> None:
        """When multiple sources match, MRR uses the rank of the FIRST match."""
        sources = [
            "unrelated.pdf",
            "pete-tong-vol1.pdf",  # rank 2 — first match
            "pete-tong-vol2.pdf",  # rank 3 — later match, ignored
        ]
        expected = ["pete-tong"]
        assert mrr(sources, expected) == pytest.approx(0.5)


class TestAggregateMetrics:
    """Unit tests for aggregate_metrics()."""

    def test_aggregate_basic(self) -> None:
        """Simple mean aggregation across a list of metric dicts."""
        data = [
            {"precision_at_5": 1.0, "recall_at_5": 0.5},
            {"precision_at_5": 0.0, "recall_at_5": 0.5},
        ]
        result = aggregate_metrics(data)
        assert result["precision_at_5"] == pytest.approx(0.5)
        assert result["recall_at_5"] == pytest.approx(0.5)

    def test_aggregate_ignores_nan(self) -> None:
        """NaN values are excluded from the mean calculation."""
        data = [
            {"recall_at_5": math.nan},
            {"recall_at_5": 0.8},
            {"recall_at_5": 0.6},
        ]
        result = aggregate_metrics(data)
        # Only 0.8 and 0.6 contribute → mean = 0.7
        assert result["recall_at_5"] == pytest.approx(0.7)

    def test_aggregate_all_nan_produces_nan(self) -> None:
        """When all values for a key are NaN the aggregated result is NaN."""
        data = [
            {"recall_at_5": math.nan},
            {"recall_at_5": math.nan},
        ]
        result = aggregate_metrics(data)
        assert math.isnan(result["recall_at_5"])

    def test_aggregate_empty_list(self) -> None:
        """Empty results list → returns empty dict."""
        assert aggregate_metrics([]) == {}

    def test_aggregate_custom_metric_keys(self) -> None:
        """metric_keys parameter filters which keys are aggregated."""
        data = [
            {"precision_at_5": 1.0, "recall_at_5": 0.5, "mrr": 0.8},
            {"precision_at_5": 0.5, "recall_at_5": 1.0, "mrr": 0.4},
        ]
        result = aggregate_metrics(data, metric_keys=["precision_at_5", "mrr"])
        assert "precision_at_5" in result
        assert "mrr" in result
        assert "recall_at_5" not in result

    def test_aggregate_single_value(self) -> None:
        """Single-element list → aggregated value equals that single value."""
        data = [{"precision_at_5": 0.75}]
        result = aggregate_metrics(data)
        assert result["precision_at_5"] == pytest.approx(0.75)
