"""Tier comparison evaluator — compare cost and quality across 3 model tiers.

Runs a subset of golden queries against each model tier and computes:
  - Per-tier topic hit rate (quality proxy: does the answer cover expected keywords?)
  - Per-tier mean latency (ms)
  - Per-tier total cost (USD)
  - Cost savings: routing cost vs always-using-standard

Designed to run without a live server — uses the generation providers
directly (no FastAPI), so it can run in CI with mocked providers.

Usage (with real providers):
    from eval.tier_comparison import TierEvalRunner
    from ingestion.generation import OpenAIGenerationProvider, AnthropicGenerationProvider
    from ingestion.router import TaskRouter

    runner = TierEvalRunner()
    report = runner.run({
        "fast":     OpenAIGenerationProvider(model="gpt-4o-mini"),
        "standard": OpenAIGenerationProvider(model="gpt-4o"),
        "local":    AnthropicGenerationProvider(model="claude-haiku-4-20250514"),
    })
    print(render_tier_report(report))
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from core.generation.base import GenerationProvider, GenerationRequest, GenerationResponse, Message
from core.routing.costs import calculate_cost
from core.routing.types import TaskType
from eval.dataset import GOLDEN_DATASET, GoldenQuery, SubDomain

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TierResult:
    """Result for a single query run against one tier.

    Attributes:
        query_id:    GoldenQuery identifier.
        question:    The question text.
        sub_domain:  SubDomain category.
        tier:        Tier name — "fast" | "standard" | "local".
        answer:      LLM-generated answer text.
        latency_ms:  Wall-clock time for the generation call (ms).
        cost_usd:    Estimated USD cost for this call.
        status_code: 200 = success, 500 = exception during generation.
        topic_hit:   True if the answer contains ≥1 expected_topics token.
    """

    query_id: str
    question: str
    sub_domain: str
    tier: str
    answer: str
    latency_ms: float
    cost_usd: float
    status_code: int
    topic_hit: bool


@dataclass
class TierComparisonReport:
    """Aggregated results from running all tiers over the golden query set.

    Attributes:
        tiers:                    List of tier names evaluated.
        results:                  Map of tier_name → list of TierResult.
        cost_savings_vs_standard: Fractional cost savings vs always-standard.
                                  e.g., 0.56 means routing is 56% cheaper.
        quality_parity:           Map of tier_name → topic hit rate (0.0–1.0).
        mean_latency_ms:          Map of tier_name → mean latency (ms).
    """

    tiers: list[str]
    results: dict[str, list[TierResult]]
    cost_savings_vs_standard: float
    quality_parity: dict[str, float]
    mean_latency_ms: dict[str, float]


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------


# Queries used in tier comparison (subset of golden set: factual + creative + realtime)
# Adversarial queries are excluded — they measure refusal, not tier quality.
_EVAL_TASK_TYPE_MAP: dict[str, TaskType] = {
    SubDomain.SOUND_DESIGN.value: "creative",
    SubDomain.ARRANGEMENT.value: "creative",
    SubDomain.MIXING.value: "factual",
    SubDomain.GENRE.value: "factual",
    SubDomain.LIVE_PERFORMANCE.value: "realtime",
    SubDomain.PRACTICE.value: "creative",
    SubDomain.CROSS.value: "creative",
    SubDomain.ADVERSARIAL.value: "factual",  # factual refusals are cheapest
}


class TierEvalRunner:
    """Run golden queries across model tiers and compare cost/quality.

    Providers are injected at run time — no singleton, no env vars.
    This makes the runner fully testable with mocks.

    Args:
        queries: List of GoldenQuery items to evaluate. Defaults to the
                 full golden set minus adversarial queries.
    """

    def __init__(self, queries: list[GoldenQuery] | None = None) -> None:
        if queries is None:
            self._queries = [q for q in GOLDEN_DATASET if q.sub_domain != SubDomain.ADVERSARIAL]
        else:
            self._queries = queries

    def run(
        self,
        providers: dict[str, GenerationProvider],
    ) -> TierComparisonReport:
        """Run all queries against each provider and return a comparison report.

        Args:
            providers: Map of tier_name → GenerationProvider.
                       Expected keys: "fast", "standard", "local".

        Returns:
            TierComparisonReport with aggregated metrics.
        """
        tiers = list(providers.keys())
        all_results: dict[str, list[TierResult]] = {t: [] for t in tiers}

        for tier_name, provider in providers.items():
            for query in self._queries:
                result = self._run_one(tier_name, provider, query)
                all_results[tier_name].append(result)

        # Aggregate metrics
        quality_parity = {t: self._hit_rate(all_results[t]) for t in tiers}
        mean_latency_ms = {t: self._mean_latency(all_results[t]) for t in tiers}

        # Cost savings: compare routing cost vs always-standard
        routing_cost = self._routing_cost(all_results, providers)
        standard_cost = self._total_cost(all_results.get("standard", []))
        if standard_cost > 0:
            savings = (standard_cost - routing_cost) / standard_cost
        else:
            savings = 0.0

        return TierComparisonReport(
            tiers=tiers,
            results=all_results,
            cost_savings_vs_standard=savings,
            quality_parity=quality_parity,
            mean_latency_ms=mean_latency_ms,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_one(
        self,
        tier_name: str,
        provider: GenerationProvider,
        query: GoldenQuery,
    ) -> TierResult:
        """Run a single query against one provider and return a TierResult."""
        system_prompt = (
            "You are a music production assistant. "
            "Answer the question concisely using your knowledge."
        )
        request = GenerationRequest(
            messages=(
                Message(role="system", content=system_prompt),
                Message(role="user", content=query.question),
            ),
            temperature=0.3,
            max_tokens=512,
        )

        t0 = time.perf_counter()
        try:
            response: GenerationResponse = provider.generate(request)
            latency_ms = (time.perf_counter() - t0) * 1000
            cost = calculate_cost(
                response.model,
                response.usage_input_tokens,
                response.usage_output_tokens,
            )
            topic_hit = self._check_topic_hit(response.content, query.expected_topics)
            return TierResult(
                query_id=query.id,
                question=query.question,
                sub_domain=query.sub_domain.value,
                tier=tier_name,
                answer=response.content,
                latency_ms=round(latency_ms, 1),
                cost_usd=cost,
                status_code=200,
                topic_hit=topic_hit,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            return TierResult(
                query_id=query.id,
                question=query.question,
                sub_domain=query.sub_domain.value,
                tier=tier_name,
                answer=f"[ERROR: {exc}]",
                latency_ms=round(latency_ms, 1),
                cost_usd=0.0,
                status_code=500,
                topic_hit=False,
            )

    @staticmethod
    def _check_topic_hit(answer: str, expected_topics: list[str]) -> bool:
        """Return True if answer contains at least one expected topic (case-insensitive)."""
        lower_answer = answer.lower()
        return any(kw.lower() in lower_answer for kw in expected_topics)

    @staticmethod
    def _hit_rate(results: list[TierResult]) -> float:
        """Fraction of results where topic_hit=True. Returns 0.0 if no results."""
        if not results:
            return 0.0
        return round(sum(1 for r in results if r.topic_hit) / len(results), 4)

    @staticmethod
    def _mean_latency(results: list[TierResult]) -> float:
        """Mean latency in ms for successful results. Returns 0.0 if no results."""
        successful = [r for r in results if r.status_code == 200]
        if not successful:
            return 0.0
        return round(sum(r.latency_ms for r in successful) / len(successful), 1)

    @staticmethod
    def _total_cost(results: list[TierResult]) -> float:
        """Sum of cost_usd across all results."""
        return round(sum(r.cost_usd for r in results), 8)

    def _routing_cost(
        self,
        all_results: dict[str, list[TierResult]],
        providers: dict[str, GenerationProvider],
    ) -> float:
        """Estimate cost of routing: each query charged to its optimal tier.

        For each query, the optimal tier is determined by the sub_domain
        (via _EVAL_TASK_TYPE_MAP) and the fallback chain.  If the primary
        tier has results, use that cost; otherwise fall back.
        """
        # Map query_id → optimal tier name based on task type
        _task_to_tier: dict[TaskType, str] = {
            "factual": "fast",
            "creative": "standard",
            "realtime": "local",
        }

        total = 0.0
        for query in self._queries:
            task_type = _EVAL_TASK_TYPE_MAP.get(query.sub_domain.value, "factual")
            optimal_tier = _task_to_tier[task_type]

            # Find the result for this query from the optimal tier
            tier_results = all_results.get(optimal_tier, [])
            matching = [r for r in tier_results if r.query_id == query.id]
            if matching:
                total += matching[0].cost_usd
        return round(total, 8)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_tier_report(report: TierComparisonReport) -> str:
    """Render a TierComparisonReport as a readable ASCII table.

    Args:
        report: Aggregated comparison report from TierEvalRunner.run().

    Returns:
        Multi-line string suitable for terminal output.
    """
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("  TIER COMPARISON REPORT")
    lines.append("=" * 72)

    # Header row
    lines.append(f"{'Tier':<12} {'Quality':<10} {'Latency (ms)':<16} {'Total cost ($)':<16}")
    lines.append("-" * 54)

    for tier in report.tiers:
        quality = report.quality_parity.get(tier, 0.0)
        latency = report.mean_latency_ms.get(tier, 0.0)
        total_cost = sum(r.cost_usd for r in report.results.get(tier, []))
        lines.append(f"{tier:<12} {quality:<10.1%} {latency:<16.1f} {total_cost:<16.6f}")

    lines.append("-" * 54)
    lines.append(f"  Cost savings vs always-standard: " f"{report.cost_savings_vs_standard:.1%}")
    lines.append("=" * 72)

    # Per-subdomain quality breakdown
    lines.append("\n  Quality by sub-domain:")
    lines.append(f"  {'Sub-domain':<20} " + "  ".join(f"{t:<10}" for t in report.tiers))
    lines.append("  " + "-" * (20 + 12 * len(report.tiers)))

    sub_domains: set[str] = set()
    for tier_results in report.results.values():
        for r in tier_results:
            sub_domains.add(r.sub_domain)

    for sd in sorted(sub_domains):
        row = f"  {sd:<20} "
        for tier in report.tiers:
            tier_results = [r for r in report.results.get(tier, []) if r.sub_domain == sd]
            if tier_results:
                hits = sum(1 for r in tier_results if r.topic_hit)
                pct = hits / len(tier_results)
                row += f"{pct:<10.0%}  "
            else:
                row += f"{'N/A':<10}  "
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def calculate_routing_savings(
    report: TierComparisonReport,
    baseline_tier: str = "standard",
) -> dict[str, Any]:
    """Compare actual routing cost vs always-using-baseline.

    Args:
        report:        TierComparisonReport from TierEvalRunner.run().
        baseline_tier: Tier name to use as the always-on baseline.

    Returns:
        Dict with keys:
            savings_pct         — fractional savings (e.g., 0.56 = 56% cheaper)
            baseline_total_usd  — total cost if always using baseline tier
            routing_total_usd   — estimated cost with optimal routing
    """
    baseline_cost = sum(r.cost_usd for r in report.results.get(baseline_tier, []))
    routing_cost_vs_standard = baseline_cost * (1.0 - report.cost_savings_vs_standard)

    savings_pct = report.cost_savings_vs_standard if baseline_cost > 0 else 0.0

    return {
        "savings_pct": round(savings_pct, 4),
        "baseline_total_usd": round(baseline_cost, 8),
        "routing_total_usd": round(routing_cost_vs_standard, 8),
    }
