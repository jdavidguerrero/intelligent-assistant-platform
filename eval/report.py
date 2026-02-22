"""Evaluation report generator.

Takes the raw ``QueryResult`` list + optional ``JudgeScore`` list and
produces:
  - Per-query scored row
  - Per-sub-domain accuracy breakdown
  - Retrieval metrics (Precision@5, Recall@5, MRR) per sub-domain
  - LLM judge scores per sub-domain
  - One-page text summary

All report functions are pure — no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dataset import SCORED_SUBDOMAINS, SubDomain
from .retrieval_metrics import mrr, precision_at_k, recall_at_k

if TYPE_CHECKING:
    from .judge import JudgeScore
    from .runner import QueryResult


@dataclass
class QueryScore:
    """Aggregated scores for a single query."""

    query_id: str
    sub_domain: str
    difficulty: str
    adversarial: bool
    status_code: int
    topic_hit: bool
    precision_at_5: float
    recall_at_5: float
    mrr_score: float
    musical_accuracy: float  # from LLM judge, 0 if not available
    relevance: float  # from LLM judge, 0 if not available
    actionability: float  # from LLM judge, 0 if not available
    verdict: str  # PASS | PARTIAL | FAIL | REFUSED (adversarial)
    latency_ms: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class SubDomainSummary:
    """Aggregated metrics for one sub-domain."""

    sub_domain: str
    total: int
    passed: int
    partial: int
    failed: int
    pass_rate: float  # passed / total
    topic_hit_rate: float
    precision_at_5: float
    recall_at_5: float
    mrr_score: float
    musical_accuracy: float  # mean judge score
    relevance: float
    actionability: float
    mean_latency_ms: float


@dataclass
class EvalReport:
    """Full evaluation report."""

    query_scores: list[QueryScore]
    sub_domain_summaries: dict[str, SubDomainSummary]
    adversarial_pass_rate: float  # fraction of adversarial queries correctly refused
    overall_pass_rate: float  # fraction of non-adversarial queries that PASS
    overall_precision_at_5: float
    overall_recall_at_5: float
    overall_mrr: float
    overall_musical_accuracy: float
    overall_relevance: float
    overall_actionability: float
    mean_latency_ms: float
    total_queries: int
    run_metadata: dict = field(default_factory=dict)


def score_results(
    results: list[QueryResult],
    judge_scores: list[JudgeScore] | None = None,
) -> list[QueryScore]:
    """Convert raw ``QueryResult`` + optional judge scores into ``QueryScore`` list.

    Parameters
    ----------
    results:
        Output from ``EvalRunner.run()``.
    judge_scores:
        Parallel list of ``JudgeScore`` objects.  Pass ``None`` to skip
        judge scoring (all judge fields will be 0).
    """
    scores: list[QueryScore] = []

    for i, r in enumerate(results):
        judge = judge_scores[i] if judge_scores else None

        # Retrieval metrics
        p5 = precision_at_k(r.sources, r.query.expected_sources, k=5)
        rc5 = recall_at_k(r.sources, r.query.expected_sources, k=5)
        mrr_val = mrr(r.sources, r.query.expected_sources)

        # Verdict
        if r.query.adversarial:
            verdict = "REFUSED" if r.correctly_refused else "FAIL"
        elif judge:
            verdict = judge.verdict
        else:
            # Fallback verdict: PASS if HTTP 200 + at least one topic hit
            if r.success and r.topic_hit():
                verdict = "PASS"
            elif r.success:
                verdict = "PARTIAL"
            else:
                verdict = "FAIL"

        scores.append(
            QueryScore(
                query_id=r.query.id,
                sub_domain=r.query.sub_domain.value,
                difficulty=r.query.difficulty.value,
                adversarial=r.query.adversarial,
                status_code=r.status_code,
                topic_hit=r.topic_hit(),
                precision_at_5=p5,
                recall_at_5=0.0 if math.isnan(rc5) else rc5,
                mrr_score=0.0 if math.isnan(mrr_val) else mrr_val,
                musical_accuracy=float(judge.musical_accuracy) if judge else 0.0,
                relevance=float(judge.relevance) if judge else 0.0,
                actionability=float(judge.actionability) if judge else 0.0,
                verdict=verdict,
                latency_ms=r.latency_ms,
                warnings=r.warnings,
            )
        )

    return scores


def _safe_mean(values: list[float]) -> float:
    valid = [v for v in values if not math.isnan(v)]
    return sum(valid) / len(valid) if valid else 0.0


def build_report(
    query_scores: list[QueryScore],
    run_metadata: dict | None = None,
) -> EvalReport:
    """Build the full ``EvalReport`` from a list of ``QueryScore``."""

    # Per-sub-domain summaries
    sub_domain_summaries: dict[str, SubDomainSummary] = {}

    for domain in list(SubDomain):
        domain_scores = [s for s in query_scores if s.sub_domain == domain.value]
        if not domain_scores:
            continue

        non_adv = [s for s in domain_scores if not s.adversarial]
        passed = sum(1 for s in domain_scores if s.verdict in ("PASS", "REFUSED"))
        partial = sum(1 for s in domain_scores if s.verdict == "PARTIAL")
        failed = sum(1 for s in domain_scores if s.verdict == "FAIL")

        sub_domain_summaries[domain.value] = SubDomainSummary(
            sub_domain=domain.value,
            total=len(domain_scores),
            passed=passed,
            partial=partial,
            failed=failed,
            pass_rate=passed / len(domain_scores) if domain_scores else 0.0,
            topic_hit_rate=_safe_mean([1.0 if s.topic_hit else 0.0 for s in non_adv]),
            precision_at_5=_safe_mean([s.precision_at_5 for s in non_adv]),
            recall_at_5=_safe_mean([s.recall_at_5 for s in non_adv]),
            mrr_score=_safe_mean([s.mrr_score for s in non_adv]),
            musical_accuracy=_safe_mean(
                [s.musical_accuracy for s in domain_scores if s.musical_accuracy > 0]
            ),
            relevance=_safe_mean([s.relevance for s in domain_scores if s.relevance > 0]),
            actionability=_safe_mean(
                [s.actionability for s in domain_scores if s.actionability > 0]
            ),
            mean_latency_ms=_safe_mean([s.latency_ms for s in domain_scores]),
        )

    # Overall metrics (non-adversarial)
    non_adv_all = [s for s in query_scores if not s.adversarial]
    adv_all = [s for s in query_scores if s.adversarial]

    adversarial_pass = (
        sum(1 for s in adv_all if s.verdict == "REFUSED") / len(adv_all) if adv_all else 0.0
    )
    overall_pass = (
        sum(1 for s in non_adv_all if s.verdict == "PASS") / len(non_adv_all)
        if non_adv_all
        else 0.0
    )

    return EvalReport(
        query_scores=query_scores,
        sub_domain_summaries=sub_domain_summaries,
        adversarial_pass_rate=adversarial_pass,
        overall_pass_rate=overall_pass,
        overall_precision_at_5=_safe_mean([s.precision_at_5 for s in non_adv_all]),
        overall_recall_at_5=_safe_mean([s.recall_at_5 for s in non_adv_all]),
        overall_mrr=_safe_mean([s.mrr_score for s in non_adv_all]),
        overall_musical_accuracy=_safe_mean(
            [s.musical_accuracy for s in non_adv_all if s.musical_accuracy > 0]
        ),
        overall_relevance=_safe_mean([s.relevance for s in non_adv_all if s.relevance > 0]),
        overall_actionability=_safe_mean(
            [s.actionability for s in non_adv_all if s.actionability > 0]
        ),
        mean_latency_ms=_safe_mean([s.latency_ms for s in query_scores]),
        total_queries=len(query_scores),
        run_metadata=run_metadata or {},
    )


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def render_report(report: EvalReport) -> str:
    """Render a one-page text summary of the evaluation report."""
    lines: list[str] = []

    lines += [
        "=" * 70,
        "  Musical Intelligence Evaluation Report",
        "=" * 70,
        "",
    ]

    # Overall summary
    lines += [
        "OVERALL SUMMARY",
        "-" * 50,
        f"  Total queries      : {report.total_queries}",
        f"  Non-adversarial pass rate : {report.overall_pass_rate * 100:.1f}%",
        f"  Adversarial refusal rate  : {report.adversarial_pass_rate * 100:.1f}%",
        f"  Overall Precision@5: {report.overall_precision_at_5:.3f}",
        f"  Overall Recall@5   : {report.overall_recall_at_5:.3f}",
        f"  Overall MRR        : {report.overall_mrr:.3f}",
    ]

    has_judge = report.overall_musical_accuracy > 0
    if has_judge:
        lines += [
            f"  Musical Accuracy   : {report.overall_musical_accuracy:.2f}/5",
            f"  Relevance          : {report.overall_relevance:.2f}/5",
            f"  Actionability      : {report.overall_actionability:.2f}/5",
        ]
    lines += [
        f"  Mean latency       : {report.mean_latency_ms:.0f}ms",
        "",
    ]

    # Per-sub-domain breakdown
    lines += [
        "PER-SUB-DOMAIN BREAKDOWN",
        "-" * 50,
    ]

    domain_order = [d.value for d in SCORED_SUBDOMAINS] + ["cross", "adversarial"]
    header = f"  {'Domain':<18} {'Pass%':>6}  {'P@5':>5}  {'R@5':>5}  {'MRR':>5}"
    if has_judge:
        header += f"  {'Acc':>4}  {'Rel':>4}  {'Act':>4}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for domain_val in domain_order:
        s = report.sub_domain_summaries.get(domain_val)
        if not s:
            continue
        row = (
            f"  {s.sub_domain:<18} {s.pass_rate * 100:>5.1f}%"
            f"  {s.precision_at_5:>5.3f}"
            f"  {s.recall_at_5:>5.3f}"
            f"  {s.mrr_score:>5.3f}"
        )
        if has_judge:
            row += (
                f"  {s.musical_accuracy:>4.1f}"
                f"  {s.relevance:>4.1f}"
                f"  {s.actionability:>4.1f}"
            )
        lines.append(row)

    lines += [""]

    # Failing queries
    failures = [s for s in report.query_scores if s.verdict == "FAIL"]
    if failures:
        lines += [
            "FAILING QUERIES",
            "-" * 50,
        ]
        for s in failures:
            lines.append(f"  [{s.query_id}] ({s.sub_domain}, {s.difficulty}) → verdict={s.verdict}")
        lines.append("")

    # Weak areas
    lines += [
        "WEAKEST SUB-DOMAINS  (pass rate < 60%)",
        "-" * 50,
    ]
    weak = [
        s
        for k, s in report.sub_domain_summaries.items()
        if s.pass_rate < 0.60 and k not in ("adversarial",)
    ]
    if weak:
        for s in sorted(weak, key=lambda x: x.pass_rate):
            lines.append(
                f"  {s.sub_domain:<18} {s.pass_rate * 100:.1f}%  ({s.failed} failed / {s.total} total)"
            )
    else:
        lines.append("  None — all sub-domains >= 60% pass rate ✓")

    lines += ["", "=" * 70, ""]
    return "\n".join(lines)


def report_to_dict(report: EvalReport) -> dict:
    """Convert EvalReport to a JSON-serializable dict for persistence."""
    return {
        "total_queries": report.total_queries,
        "overall_pass_rate": report.overall_pass_rate,
        "adversarial_pass_rate": report.adversarial_pass_rate,
        "overall_precision_at_5": report.overall_precision_at_5,
        "overall_recall_at_5": report.overall_recall_at_5,
        "overall_mrr": report.overall_mrr,
        "overall_musical_accuracy": report.overall_musical_accuracy,
        "overall_relevance": report.overall_relevance,
        "overall_actionability": report.overall_actionability,
        "mean_latency_ms": report.mean_latency_ms,
        "run_metadata": report.run_metadata,
        "sub_domain_summaries": {
            k: {
                "sub_domain": v.sub_domain,
                "total": v.total,
                "passed": v.passed,
                "partial": v.partial,
                "failed": v.failed,
                "pass_rate": v.pass_rate,
                "topic_hit_rate": v.topic_hit_rate,
                "precision_at_5": v.precision_at_5,
                "recall_at_5": v.recall_at_5,
                "mrr_score": v.mrr_score,
                "musical_accuracy": v.musical_accuracy,
                "relevance": v.relevance,
                "actionability": v.actionability,
                "mean_latency_ms": v.mean_latency_ms,
            }
            for k, v in report.sub_domain_summaries.items()
        },
        "query_scores": [
            {
                "query_id": s.query_id,
                "sub_domain": s.sub_domain,
                "difficulty": s.difficulty,
                "adversarial": s.adversarial,
                "status_code": s.status_code,
                "topic_hit": s.topic_hit,
                "precision_at_5": s.precision_at_5,
                "recall_at_5": s.recall_at_5,
                "mrr_score": s.mrr_score,
                "musical_accuracy": s.musical_accuracy,
                "relevance": s.relevance,
                "actionability": s.actionability,
                "verdict": s.verdict,
                "latency_ms": s.latency_ms,
                "warnings": s.warnings,
            }
            for s in report.query_scores
        ],
    }
