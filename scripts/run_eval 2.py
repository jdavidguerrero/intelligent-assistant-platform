#!/usr/bin/env python
"""Musical Intelligence Evaluation Pipeline — one-command runner.

Usage
-----
    # Full evaluation (all 50 queries + LLM judge + report)
    python scripts/run_eval.py

    # Skip LLM judge (faster, no extra API cost)
    python scripts/run_eval.py --no-judge

    # Run specific sub-domain only
    python scripts/run_eval.py --domain sound_design

    # Compare against saved baseline
    python scripts/run_eval.py --compare eval_results/baseline.json

    # Save current run as new baseline
    python scripts/run_eval.py --save-baseline eval_results/baseline.json

    # Adversarial queries only
    python scripts/run_eval.py --adversarial-only

Exit codes
----------
    0  — success, no regressions
    1  — regressions detected (when --compare is used)
    2  — evaluation errors
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from eval.dataset import GOLDEN_DATASET, SubDomain  # noqa: E402
from eval.judge import LLMJudge  # noqa: E402
from eval.regression import compare, load_baseline, save_baseline  # noqa: E402
from eval.report import build_report, render_report, report_to_dict, score_results  # noqa: E402
from eval.runner import EvalRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Musical Intelligence Evaluation Pipeline")
    p.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM-as-judge scoring (faster, cheaper)",
    )
    p.add_argument(
        "--domain",
        choices=[d.value for d in SubDomain],
        default=None,
        help="Run only queries from this sub-domain",
    )
    p.add_argument(
        "--adversarial-only",
        action="store_true",
        help="Run only adversarial queries",
    )
    p.add_argument(
        "--compare",
        metavar="BASELINE_JSON",
        default=None,
        help="Compare against saved baseline and detect regressions",
    )
    p.add_argument(
        "--save-baseline",
        metavar="OUTPUT_JSON",
        default=None,
        help="Save current run as baseline for future regression checks",
    )
    p.add_argument(
        "--output",
        metavar="OUTPUT_JSON",
        default=None,
        help="Save full report JSON to this path",
    )
    p.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.58,
        help="Confidence threshold for /ask endpoint (default: 0.58)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve per query (default: 5)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="Sleep between queries to avoid LLM rate limits (default: 3.0s)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-query progress",
    )
    return p.parse_args()


def main() -> int:  # noqa: C901
    args = parse_args()

    print()
    print("=" * 65)
    print("  Musical Intelligence Evaluation Pipeline")
    print("=" * 65)
    print(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Build dataset subset
    dataset = GOLDEN_DATASET
    if args.adversarial_only:
        dataset = [q for q in dataset if q.adversarial]
        print(f"  Mode: adversarial-only ({len(dataset)} queries)")
    elif args.domain:
        dataset = [q for q in dataset if q.sub_domain.value == args.domain]
        print(f"  Mode: domain={args.domain} ({len(dataset)} queries)")
    else:
        print(f"  Mode: full evaluation ({len(dataset)} queries)")

    if not dataset:
        print("  ERROR: No queries matched the filters.")
        return 2

    print(f"  Confidence threshold : {args.confidence_threshold}")
    print(f"  Top-K                : {args.top_k}")
    print(f"  LLM judge            : {'enabled' if not args.no_judge else 'disabled'}")
    print(f"  Query delay          : {args.delay}s")
    print()

    # Step 1: Run queries
    print("Step 1/3 — Executing queries...")
    runner = EvalRunner(
        confidence_threshold=args.confidence_threshold,
        top_k=args.top_k,
        query_delay_s=args.delay,
    )
    t0 = time.perf_counter()
    results = runner.run(dataset=dataset, verbose=args.verbose)
    query_elapsed = time.perf_counter() - t0

    success_count = sum(1 for r in results if r.success or r.correctly_refused)
    print(
        f"  Completed {len(results)} queries in {query_elapsed:.1f}s "
        f"({success_count}/{len(results)} succeeded)"
    )
    print()

    # Step 2: LLM judge scoring
    judge_scores = None
    if not args.no_judge:
        print("Step 2/3 — LLM-as-judge scoring...")
        judge = LLMJudge(model="gpt-4o-mini")
        if not judge.available:
            print("  WARNING: LLM judge unavailable — skipping scoring.")
        else:
            judge_scores = []
            for i, r in enumerate(results, 1):
                if r.query.adversarial:
                    score = judge.score_adversarial(r.status_code, r.answer)
                elif r.success and r.answer:
                    score = judge.score(r.query.question, r.answer)
                else:
                    from eval.judge import JudgeScore  # noqa: PLC0415

                    score = JudgeScore(
                        musical_accuracy=0,
                        relevance=0,
                        actionability=0,
                        reasoning="No answer to evaluate.",
                        verdict="FAIL",
                    )
                judge_scores.append(score)
                if args.verbose:
                    print(
                        f"  [{i:02d}/{len(results)}] {r.query.id}: "
                        f"acc={score.musical_accuracy} rel={score.relevance} "
                        f"act={score.actionability} → {score.verdict}"
                    )
            print(f"  Judge scoring complete ({len(judge_scores)} queries)")
    else:
        print("Step 2/3 — LLM judge: skipped")
    print()

    # Step 3: Build report
    print("Step 3/3 — Building report...")
    query_scores = score_results(results, judge_scores)
    run_metadata = {
        "timestamp": datetime.now().isoformat(),
        "total_queries": len(dataset),
        "confidence_threshold": args.confidence_threshold,
        "top_k": args.top_k,
        "judge_enabled": not args.no_judge,
        "query_elapsed_s": round(query_elapsed, 2),
    }
    report = build_report(query_scores, run_metadata=run_metadata)
    report_dict = report_to_dict(report)
    print()

    # Print report
    print(render_report(report))

    # Save output
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report_dict, f, indent=2)
        print(f"  Report saved → {args.output}")

    if args.save_baseline:
        save_baseline(report_dict, args.save_baseline)
        print(f"  Baseline saved → {args.save_baseline}")
        print()

    # Regression comparison
    exit_code = 0
    if args.compare:
        try:
            baseline = load_baseline(args.compare)
            regression_report = compare(baseline, report_dict, threshold=0.05)
            print(regression_report.render())
            if regression_report.has_regressions:
                print("  ⚠  REGRESSIONS DETECTED — exiting with code 1")
                exit_code = 1
            else:
                print("  ✓  No regressions detected")
        except FileNotFoundError:
            print(f"  WARNING: Baseline not found at {args.compare} — skipping regression check")

    print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
