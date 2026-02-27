"""Tests for eval/tier_comparison.py — TierEvalRunner unit tests.

All tests mock the generation providers — no real API calls.
Tests cover:
- TierResult fields populated correctly on success + failure
- TierComparisonReport structure and field types
- Quality hit-rate calculation
- Cost savings > 40% vs always-standard (analytical verification)
- Fallback scenario: one tier down, report still completes
- render_tier_report() returns a non-empty string
- calculate_routing_savings() math
"""

from __future__ import annotations

from unittest.mock import MagicMock

from core.generation.base import GenerationProvider, GenerationResponse
from eval.dataset import GOLDEN_DATASET, GoldenQuery, SubDomain
from eval.tier_comparison import (
    TierEvalRunner,
    calculate_routing_savings,
    render_tier_report,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _good_provider(
    content: str = "attack decay sustain release",
    model: str = "gpt-4o-mini",
    input_tokens: int = 200,
    output_tokens: int = 80,
) -> MagicMock:
    """Mock provider that always succeeds and returns content containing topic words."""
    provider = MagicMock(spec=GenerationProvider)
    provider.generate.return_value = GenerationResponse(
        content=content,
        model=model,
        usage_input_tokens=input_tokens,
        usage_output_tokens=output_tokens,
    )
    return provider


def _failing_provider() -> MagicMock:
    """Mock provider that always raises RuntimeError."""
    provider = MagicMock(spec=GenerationProvider)
    provider.generate.side_effect = RuntimeError("provider unavailable")
    return provider


def _simple_queries(n: int = 3) -> list[GoldenQuery]:
    """Return n non-adversarial queries from the golden dataset."""
    return [q for q in GOLDEN_DATASET if not q.adversarial][:n]


# ---------------------------------------------------------------------------
# TierEvalRunner — single tier
# ---------------------------------------------------------------------------


class TestTierEvalRunnerSingleTier:
    def test_success_result_has_correct_fields(self) -> None:
        """A successful generation populates TierResult correctly."""
        queries = _simple_queries(1)
        runner = TierEvalRunner(queries=queries)
        provider = _good_provider(content="attack decay sustain release")

        report = runner.run({"fast": provider})

        assert len(report.results["fast"]) == 1
        result = report.results["fast"][0]
        assert result.query_id == queries[0].id
        assert result.tier == "fast"
        assert result.status_code == 200
        assert result.latency_ms >= 0.0
        assert result.cost_usd >= 0.0
        assert isinstance(result.topic_hit, bool)

    def test_failure_result_has_status_500(self) -> None:
        """When the provider raises, status_code=500 and topic_hit=False."""
        queries = _simple_queries(1)
        runner = TierEvalRunner(queries=queries)

        report = runner.run({"fast": _failing_provider()})

        result = report.results["fast"][0]
        assert result.status_code == 500
        assert result.topic_hit is False
        assert "[ERROR:" in result.answer

    def test_topic_hit_true_when_keyword_in_answer(self) -> None:
        """topic_hit=True when answer contains at least one expected_topics item."""
        # sd_001 expects ["attack", "decay", "sustain", "release", "envelope"]
        sd_query = next(q for q in GOLDEN_DATASET if q.id == "sd_001")
        runner = TierEvalRunner(queries=[sd_query])
        # Answer contains "attack"
        provider = _good_provider(content="attack is the first phase")

        report = runner.run({"fast": provider})
        assert report.results["fast"][0].topic_hit is True

    def test_topic_hit_false_when_no_keyword_in_answer(self) -> None:
        """topic_hit=False when answer contains none of the expected_topics."""
        sd_query = next(q for q in GOLDEN_DATASET if q.id == "sd_001")
        runner = TierEvalRunner(queries=[sd_query])
        # Answer is completely off-topic
        provider = _good_provider(content="I cannot answer that question")

        report = runner.run({"fast": provider})
        assert report.results["fast"][0].topic_hit is False

    def test_cost_usd_zero_for_unknown_model(self) -> None:
        """cost_usd=0.0 when the model is not in the cost table."""
        queries = _simple_queries(1)
        runner = TierEvalRunner(queries=queries)
        provider = _good_provider(model="unknown-model-xyz")

        report = runner.run({"fast": provider})
        assert report.results["fast"][0].cost_usd == 0.0

    def test_cost_usd_positive_for_gpt4o_mini(self) -> None:
        """cost_usd > 0 when model is gpt-4o-mini."""
        queries = _simple_queries(1)
        runner = TierEvalRunner(queries=queries)
        provider = _good_provider(model="gpt-4o-mini", input_tokens=500, output_tokens=200)

        report = runner.run({"fast": provider})
        assert report.results["fast"][0].cost_usd > 0.0


# ---------------------------------------------------------------------------
# TierEvalRunner — multiple tiers
# ---------------------------------------------------------------------------


class TestTierEvalRunnerMultipleTiers:
    def test_all_tiers_run_over_same_queries(self) -> None:
        """Each tier runs over the same set of queries."""
        queries = _simple_queries(3)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
            "local": _good_provider(model="claude-haiku-4-20250514"),
        }
        report = runner.run(providers)

        for tier in ["fast", "standard", "local"]:
            assert len(report.results[tier]) == 3

    def test_report_has_correct_tiers(self) -> None:
        """TierComparisonReport.tiers matches provider keys."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)

        assert set(report.tiers) == {"fast", "standard"}

    def test_quality_parity_in_range(self) -> None:
        """quality_parity values are in [0.0, 1.0] for all tiers."""
        queries = _simple_queries(5)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(content="attack decay sustain release"),
            "standard": _good_provider(content="attack decay sustain release"),
        }
        report = runner.run(providers)

        for tier in report.tiers:
            assert 0.0 <= report.quality_parity[tier] <= 1.0

    def test_mean_latency_non_negative(self) -> None:
        """mean_latency_ms is >= 0.0 for all tiers."""
        queries = _simple_queries(3)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)

        for tier in report.tiers:
            assert report.mean_latency_ms[tier] >= 0.0

    def test_one_tier_down_still_completes(self) -> None:
        """If one tier always fails, report still contains results for working tiers."""
        queries = _simple_queries(3)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _failing_provider(),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)

        # fast tier all failed
        fast_results = report.results["fast"]
        assert all(r.status_code == 500 for r in fast_results)
        # standard tier all succeeded
        standard_results = report.results["standard"]
        assert all(r.status_code == 200 for r in standard_results)


# ---------------------------------------------------------------------------
# Cost savings projection
# ---------------------------------------------------------------------------


class TestCostSavingsProjection:
    def test_fast_cheaper_than_standard(self) -> None:
        """gpt-4o-mini costs less than gpt-4o for the same tokens."""
        from core.routing.costs import calculate_cost

        fast_cost = calculate_cost("gpt-4o-mini", 1000, 500)
        standard_cost = calculate_cost("gpt-4o", 1000, 500)
        assert fast_cost < standard_cost

    def test_routing_saves_more_than_40_percent_analytically(self) -> None:
        """Analytical savings: 60% factual (fast) + 35% creative (standard) + 5% realtime (local)
        should save >40% vs always-standard.

        This mirrors the projected mix from the Week 9 spec:
          60% factual  → gpt-4o-mini ($0.15/$0.60 per M)
          35% creative → gpt-4o ($2.50/$10.00 per M)
          5% realtime  → claude-haiku ($0.80/$4.00 per M)
        vs. 100% gpt-4o.

        We use 100 queries × 200 input + 100 output tokens each as representative load.
        """
        from core.routing.costs import calculate_cost

        total_queries = 100
        input_tok = 200
        output_tok = 100

        # Always standard
        always_standard_cost = total_queries * calculate_cost("gpt-4o", input_tok, output_tok)

        # Routing distribution
        factual_n = 60
        creative_n = 35
        realtime_n = 5

        routing_cost = (
            factual_n * calculate_cost("gpt-4o-mini", input_tok, output_tok)
            + creative_n * calculate_cost("gpt-4o", input_tok, output_tok)
            + realtime_n * calculate_cost("claude-haiku-4-20250514", input_tok, output_tok)
        )

        savings = (always_standard_cost - routing_cost) / always_standard_cost
        assert savings >= 0.40, (
            f"Expected >= 40% savings but got {savings:.1%}. "
            f"Standard: ${always_standard_cost:.6f}, routing: ${routing_cost:.6f}"
        )

    def test_cost_savings_vs_standard_in_range(self) -> None:
        """cost_savings_vs_standard is between -1.0 and 1.0."""
        queries = _simple_queries(4)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini", input_tokens=200, output_tokens=80),
            "standard": _good_provider(model="gpt-4o", input_tokens=200, output_tokens=80),
            "local": _good_provider(
                model="claude-haiku-4-20250514", input_tokens=200, output_tokens=80
            ),
        }
        report = runner.run(providers)

        assert -1.0 <= report.cost_savings_vs_standard <= 1.0


# ---------------------------------------------------------------------------
# calculate_routing_savings
# ---------------------------------------------------------------------------


class TestCalculateRoutingSavings:
    def test_returns_expected_keys(self) -> None:
        """Returns dict with savings_pct, baseline_total_usd, routing_total_usd."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)
        savings = calculate_routing_savings(report)

        assert "savings_pct" in savings
        assert "baseline_total_usd" in savings
        assert "routing_total_usd" in savings

    def test_savings_pct_in_range(self) -> None:
        """savings_pct is in [-1.0, 1.0]."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)
        savings = calculate_routing_savings(report)

        assert -1.0 <= savings["savings_pct"] <= 1.0

    def test_no_standard_tier_returns_zero_savings(self) -> None:
        """If baseline_tier has no results, savings_pct=0.0."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {"fast": _good_provider(model="gpt-4o-mini")}
        report = runner.run(providers)

        # baseline_tier="standard" has no results
        savings = calculate_routing_savings(report, baseline_tier="standard")
        assert savings["savings_pct"] == 0.0
        assert savings["baseline_total_usd"] == 0.0


# ---------------------------------------------------------------------------
# render_tier_report
# ---------------------------------------------------------------------------


class TestRenderTierReport:
    def test_returns_non_empty_string(self) -> None:
        """render_tier_report() returns a non-empty string."""
        queries = _simple_queries(3)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)
        rendered = render_tier_report(report)

        assert isinstance(rendered, str)
        assert len(rendered) > 100

    def test_rendered_report_contains_tier_names(self) -> None:
        """Rendered report contains all tier names."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)
        rendered = render_tier_report(report)

        assert "fast" in rendered
        assert "standard" in rendered

    def test_rendered_report_contains_savings_line(self) -> None:
        """Rendered report includes a cost savings line."""
        queries = _simple_queries(2)
        runner = TierEvalRunner(queries=queries)
        providers = {
            "fast": _good_provider(model="gpt-4o-mini"),
            "standard": _good_provider(model="gpt-4o"),
        }
        report = runner.run(providers)
        rendered = render_tier_report(report)

        assert "savings" in rendered.lower() or "%" in rendered


# ---------------------------------------------------------------------------
# Default query set (no adversarial)
# ---------------------------------------------------------------------------


class TestDefaultQuerySet:
    def test_default_excludes_adversarial(self) -> None:
        """TierEvalRunner default queries exclude adversarial entries."""
        runner = TierEvalRunner()
        for q in runner._queries:
            assert q.sub_domain != SubDomain.ADVERSARIAL
            assert not q.adversarial

    def test_default_query_count(self) -> None:
        """Default query set has 40 queries (50 total − 10 adversarial)."""
        runner = TierEvalRunner()
        # The golden dataset has 50 queries, 10 of which are adversarial
        assert len(runner._queries) == 40

    def test_custom_queries_used(self) -> None:
        """Custom query list is used when provided."""
        queries = _simple_queries(3)
        runner = TierEvalRunner(queries=queries)
        assert len(runner._queries) == 3
