"""CLI script: run tier comparison eval and print cost/quality report.

Usage:
    # Run all tiers (requires OPENAI_API_KEY + ANTHROPIC_API_KEY in env):
    python scripts/run_tier_eval.py

    # Skip the local (Anthropic) tier:
    python scripts/run_tier_eval.py --no-local

    # Limit to N queries per tier (useful for quick smoke tests):
    python scripts/run_tier_eval.py --max-queries 5

    # Save JSON results to a file:
    python scripts/run_tier_eval.py --output eval_results/tier_comparison.json

Output:
    ASCII tier comparison table printed to stdout.
    Optional JSON saved to --output path.

Environment variables read:
    OPENAI_API_KEY      — required for fast + standard tiers
    ANTHROPIC_API_KEY   — required for local tier (skipped with --no-local)
    TIER_FAST_MODEL     — default: gpt-4o-mini
    TIER_STANDARD_MODEL — default: gpt-4o
    TIER_LOCAL_MODEL    — default: claude-haiku-4-20250514
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run tier comparison eval across fast / standard / local model tiers."
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        default=False,
        help="Skip the local (Anthropic Haiku) tier.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        metavar="N",
        help="Limit evaluation to the first N queries per tier (smoke test mode).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="PATH",
        help="Write JSON results to this path (e.g. eval_results/tier_comparison.json).",
    )
    return parser.parse_args()


def _build_providers(skip_local: bool) -> dict:
    """Build generation providers for each tier.

    Returns:
        Dict of tier_name → GenerationProvider. Raises if required API key missing.
    """
    from ingestion.generation import AnthropicGenerationProvider, OpenAIGenerationProvider

    providers: dict = {}

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise SystemExit(
            "ERROR: OPENAI_API_KEY is not set. "
            "Set it in your environment before running this script."
        )

    providers["fast"] = OpenAIGenerationProvider(
        model=os.getenv("TIER_FAST_MODEL", "gpt-4o-mini"),
        api_key=openai_key,
    )
    providers["standard"] = OpenAIGenerationProvider(
        model=os.getenv("TIER_STANDARD_MODEL", "gpt-4o"),
        api_key=openai_key,
    )

    if not skip_local:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set — skipping local tier. "
                "Use --no-local to suppress this warning."
            )
        else:
            providers["local"] = AnthropicGenerationProvider(
                model=os.getenv("TIER_LOCAL_MODEL", "claude-haiku-4-20250514"),
            )

    return providers


def _save_json(report, output_path: str) -> None:
    """Serialize TierComparisonReport to JSON and write to disk."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tiers": report.tiers,
        "cost_savings_vs_standard": report.cost_savings_vs_standard,
        "quality_parity": report.quality_parity,
        "mean_latency_ms": report.mean_latency_ms,
        "results": {
            tier: [dataclasses.asdict(r) for r in results]
            for tier, results in report.results.items()
        },
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("Results saved to: %s", path)


def main() -> None:
    args = _parse_args()

    logger.info("Building providers…")
    providers = _build_providers(skip_local=args.no_local)
    logger.info("Tiers: %s", list(providers.keys()))

    from eval.dataset import GOLDEN_DATASET, SubDomain
    from eval.tier_comparison import TierEvalRunner, calculate_routing_savings, render_tier_report

    queries = [q for q in GOLDEN_DATASET if q.sub_domain != SubDomain.ADVERSARIAL]
    if args.max_queries:
        queries = queries[: args.max_queries]
        logger.info("Smoke test mode: using %d queries per tier.", len(queries))
    else:
        logger.info("Running %d queries per tier.", len(queries))

    runner = TierEvalRunner(queries=queries)

    logger.info("Starting tier comparison eval…")
    report = runner.run(providers)

    print(render_tier_report(report))

    savings = calculate_routing_savings(report, baseline_tier="standard")
    print(f"  Routing saves {savings['savings_pct']:.1%} vs always-standard:")
    print(f"    Always-standard: ${savings['baseline_total_usd']:.6f}")
    print(f"    With routing:    ${savings['routing_total_usd']:.6f}\n")

    if args.output:
        _save_json(report, args.output)


if __name__ == "__main__":
    main()
