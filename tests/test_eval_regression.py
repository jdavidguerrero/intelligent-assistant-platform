"""Tests for eval/regression.py — baseline comparison, regression/improvement detection.

All comparison logic is pure (no I/O except save_baseline/load_baseline).
File I/O tests use pytest's tmp_path fixture for isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.regression import (
    MetricDelta,
    compare,
    load_baseline,
    save_baseline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_baseline(
    overall_pass_rate: float = 0.80,
    mixing_pass_rate: float = 0.80,
    arrangement_pass_rate: float = 0.80,
) -> dict:
    """Build a minimal eval report dict resembling report_to_dict() output."""
    return {
        "total_queries": 50,
        "overall_pass_rate": overall_pass_rate,
        "adversarial_pass_rate": 1.0,
        "overall_precision_at_5": 0.80,
        "overall_recall_at_5": 0.75,
        "overall_mrr": 0.85,
        "overall_musical_accuracy": 3.5,
        "overall_relevance": 3.5,
        "overall_actionability": 3.0,
        "mean_latency_ms": 250.0,
        "run_metadata": {},
        "sub_domain_summaries": {
            "mixing": {
                "sub_domain": "mixing",
                "total": 5,
                "passed": 4,
                "partial": 0,
                "failed": 1,
                "pass_rate": mixing_pass_rate,
                "topic_hit_rate": 0.80,
                "precision_at_5": 0.80,
                "recall_at_5": 0.75,
                "mrr_score": 0.85,
                "musical_accuracy": 0.0,
                "relevance": 0.0,
                "actionability": 0.0,
                "mean_latency_ms": 200.0,
            },
            "arrangement": {
                "sub_domain": "arrangement",
                "total": 5,
                "passed": 4,
                "partial": 0,
                "failed": 1,
                "pass_rate": arrangement_pass_rate,
                "topic_hit_rate": 0.80,
                "precision_at_5": 0.80,
                "recall_at_5": 0.75,
                "mrr_score": 0.85,
                "musical_accuracy": 0.0,
                "relevance": 0.0,
                "actionability": 0.0,
                "mean_latency_ms": 220.0,
            },
        },
        "query_scores": [],
    }


# ---------------------------------------------------------------------------
# MetricDelta
# ---------------------------------------------------------------------------

class TestMetricDelta:
    """Unit tests for the MetricDelta value object."""

    def test_delta_positive(self) -> None:
        """delta = current - baseline, positive when current > baseline."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.7, current=0.85)
        assert d.delta == pytest.approx(0.15)

    def test_delta_negative(self) -> None:
        """delta is negative when current < baseline."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.85, current=0.70)
        assert d.delta == pytest.approx(-0.15)

    def test_is_regression_when_negative(self) -> None:
        """is_regression is True when delta < 0."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.80, current=0.60)
        assert d.is_regression is True

    def test_is_regression_false_when_positive(self) -> None:
        """is_regression is False when delta >= 0."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.60, current=0.80)
        assert d.is_regression is False

    def test_direction_up(self) -> None:
        """direction is '▲' when delta > 0.001."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.60, current=0.80)
        assert d.direction == "▲"

    def test_direction_down(self) -> None:
        """direction is '▼' when delta < -0.001."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.80, current=0.60)
        assert d.direction == "▼"

    def test_direction_stable(self) -> None:
        """direction is '─' when |delta| <= 0.001."""
        d = MetricDelta(metric="pass_rate", sub_domain="mixing", baseline=0.80, current=0.8005)
        assert d.direction == "─"


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------

class TestCompare:
    """Tests for compare() — the core regression-detection function."""

    def test_no_regression_identical(self) -> None:
        """Identical baseline and current produce zero regressions."""
        baseline = _make_baseline()
        current = _make_baseline()
        report = compare(baseline, current, threshold=0.05)
        assert len(report.regressions) == 0
        assert report.has_regressions is False

    def test_regression_detected(self) -> None:
        """A pass_rate drop of more than threshold is detected as a regression."""
        baseline = _make_baseline(overall_pass_rate=0.80)
        current = _make_baseline(overall_pass_rate=0.70)  # drop = 0.10 > threshold=0.05
        report = compare(baseline, current, threshold=0.05)
        assert report.has_regressions is True
        regression_metrics = [d.metric for d in report.regressions]
        assert "overall_pass_rate" in regression_metrics

    def test_improvement_detected(self) -> None:
        """A pass_rate increase of more than threshold is detected as an improvement."""
        baseline = _make_baseline(overall_pass_rate=0.70)
        current = _make_baseline(overall_pass_rate=0.80)  # gain = 0.10 > threshold=0.05
        report = compare(baseline, current, threshold=0.05)
        assert len(report.improvements) > 0
        improvement_metrics = [d.metric for d in report.improvements]
        assert "overall_pass_rate" in improvement_metrics

    def test_threshold_respected_small_drop(self) -> None:
        """A drop smaller than the threshold is NOT classified as a regression."""
        baseline = _make_baseline(overall_pass_rate=0.80)
        current = _make_baseline(overall_pass_rate=0.76)  # drop = 0.04 < threshold=0.05
        report = compare(baseline, current, threshold=0.05)
        overall_regressions = [d for d in report.regressions if d.metric == "overall_pass_rate"]
        assert len(overall_regressions) == 0

    def test_threshold_respected_exact_boundary(self) -> None:
        """A drop exactly equal to the threshold is NOT a regression (strictly less than).

        Uses a custom threshold that eliminates floating-point rounding issues
        by choosing values where the drop is unambiguously equal to the threshold.
        """
        # Use threshold=0.10 and a drop of exactly 0.10 (0.90 - 0.80 = 0.10)
        baseline = _make_baseline(overall_pass_rate=0.90)
        current = _make_baseline(overall_pass_rate=0.80)  # drop = 0.10
        report = compare(baseline, current, threshold=0.10)
        # delta = current - baseline = 0.80 - 0.90 = -0.10
        # regressions require delta < -threshold → -0.10 < -0.10 → False
        overall_regressions = [d for d in report.regressions if d.metric == "overall_pass_rate"]
        assert len(overall_regressions) == 0

    def test_subdomain_regression_detected(self) -> None:
        """Sub-domain level regression is detected when mixing pass_rate drops."""
        baseline = _make_baseline(mixing_pass_rate=0.80)
        current = _make_baseline(mixing_pass_rate=0.60)  # drop = 0.20 > threshold
        report = compare(baseline, current, threshold=0.05)
        assert report.has_regressions is True
        mixing_regressions = [
            d for d in report.regressions
            if d.sub_domain == "mixing" and d.metric == "pass_rate"
        ]
        assert len(mixing_regressions) == 1

    def test_has_regressions_property(self) -> None:
        """has_regressions returns True only when the regressions list is non-empty."""
        baseline = _make_baseline(overall_pass_rate=0.80)
        current_ok = _make_baseline(overall_pass_rate=0.80)
        current_bad = _make_baseline(overall_pass_rate=0.60)

        ok_report = compare(baseline, current_ok, threshold=0.05)
        bad_report = compare(baseline, current_bad, threshold=0.05)

        assert ok_report.has_regressions is False
        assert bad_report.has_regressions is True

    def test_deltas_list_non_empty(self) -> None:
        """compare() always produces at least some deltas (overall + sub-domain)."""
        baseline = _make_baseline()
        current = _make_baseline()
        report = compare(baseline, current)
        assert len(report.deltas) > 0

    def test_custom_metrics_parameter(self) -> None:
        """Passing a custom metrics list restricts sub-domain comparison to those keys."""
        baseline = _make_baseline(mixing_pass_rate=0.80)
        current = _make_baseline(mixing_pass_rate=0.60)
        # Only compare precision_at_5 (not pass_rate) for sub-domains
        report = compare(baseline, current, threshold=0.05, metrics=["precision_at_5"])
        # pass_rate sub-domain regression should NOT be in regressions list
        mixing_pass_regressions = [
            d for d in report.regressions
            if d.sub_domain == "mixing" and d.metric == "pass_rate"
        ]
        assert len(mixing_pass_regressions) == 0


# ---------------------------------------------------------------------------
# RegressionReport.render()
# ---------------------------------------------------------------------------

class TestRegressionReportRender:
    """Tests for the text rendering of RegressionReport."""

    def test_render_shows_regressions_detected(self) -> None:
        """Rendered text contains 'REGRESSIONS DETECTED' when regressions exist."""
        baseline = _make_baseline(overall_pass_rate=0.80)
        current = _make_baseline(overall_pass_rate=0.60)
        report = compare(baseline, current, threshold=0.05)
        rendered = report.render()
        assert "REGRESSIONS DETECTED" in rendered

    def test_render_shows_no_regressions_when_clean(self) -> None:
        """Rendered text mentions 'No regressions' when no regressions exist."""
        baseline = _make_baseline()
        current = _make_baseline()
        report = compare(baseline, current, threshold=0.05)
        rendered = report.render()
        assert "No regressions" in rendered

    def test_render_shows_threshold(self) -> None:
        """Rendered text includes the threshold value."""
        baseline = _make_baseline()
        current = _make_baseline()
        report = compare(baseline, current, threshold=0.05)
        rendered = report.render()
        assert "5.0%" in rendered

    def test_render_is_string(self) -> None:
        """render() must return a str."""
        report = compare(_make_baseline(), _make_baseline())
        assert isinstance(report.render(), str)

    def test_render_shows_improvements(self) -> None:
        """Rendered text shows improvements section when improvements exist."""
        baseline = _make_baseline(overall_pass_rate=0.60)
        current = _make_baseline(overall_pass_rate=0.80)
        report = compare(baseline, current, threshold=0.05)
        rendered = report.render()
        assert "Improvements" in rendered


# ---------------------------------------------------------------------------
# save_baseline() / load_baseline()
# ---------------------------------------------------------------------------

class TestBaselinePersistence:
    """File I/O tests for save_baseline() and load_baseline()."""

    def test_save_and_load_baseline(self, tmp_path: Path) -> None:
        """Saving then loading a baseline dict gives an identical result."""
        path = tmp_path / "results" / "baseline.json"
        data = _make_baseline()
        save_baseline(data, path)
        loaded = load_baseline(path)
        assert loaded == data

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """save_baseline creates intermediate directories if they don't exist."""
        path = tmp_path / "deeply" / "nested" / "dir" / "baseline.json"
        save_baseline({"overall_pass_rate": 0.8}, path)
        assert path.exists()

    def test_save_writes_valid_json(self, tmp_path: Path) -> None:
        """The file written by save_baseline must be valid JSON."""
        path = tmp_path / "baseline.json"
        data = _make_baseline()
        save_baseline(data, path)
        raw = path.read_text()
        parsed = json.loads(raw)
        assert parsed["overall_pass_rate"] == pytest.approx(data["overall_pass_rate"])

    def test_load_baseline_returns_dict(self, tmp_path: Path) -> None:
        """load_baseline must return a dict."""
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"overall_pass_rate": 0.75}))
        result = load_baseline(path)
        assert isinstance(result, dict)
        assert result["overall_pass_rate"] == pytest.approx(0.75)

    def test_load_baseline_accepts_string_path(self, tmp_path: Path) -> None:
        """load_baseline accepts a string path in addition to a Path object."""
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"overall_pass_rate": 0.9}))
        result = load_baseline(str(path))
        assert result["overall_pass_rate"] == pytest.approx(0.9)
