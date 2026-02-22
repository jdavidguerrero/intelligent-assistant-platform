"""Regression detection — compare current eval run against a saved baseline.

Usage
-----
    baseline = load_baseline("eval_results/baseline.json")
    current  = report_to_dict(current_report)
    delta    = compare(baseline, current, threshold=0.05)
    if delta.has_regressions:
        print(delta.render())
        sys.exit(1)

Regression is defined as: any per-sub-domain pass_rate drops by more than
``threshold`` (default 5%) compared to the baseline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MetricDelta:
    """Change in a single metric between baseline and current."""

    metric: str
    sub_domain: str
    baseline: float
    current: float

    @property
    def delta(self) -> float:
        return self.current - self.baseline

    @property
    def is_regression(self) -> bool:
        """True if the current value is LOWER than baseline by more than threshold."""
        # threshold is applied at the compare() level
        return self.delta < 0

    @property
    def direction(self) -> str:
        if self.delta > 0.001:
            return "▲"
        if self.delta < -0.001:
            return "▼"
        return "─"


@dataclass
class RegressionReport:
    """Full comparison between baseline and current run."""

    deltas: list[MetricDelta]
    threshold: float
    regressions: list[MetricDelta] = field(default_factory=list)
    improvements: list[MetricDelta] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    def render(self) -> str:
        lines: list[str] = [
            "=" * 65,
            "  Regression Report",
            "=" * 65,
            f"  Regression threshold: {self.threshold * 100:.1f}%",
            "",
        ]

        if self.regressions:
            lines += [f"  ⚠  REGRESSIONS DETECTED ({len(self.regressions)})", "-" * 50]
            for d in self.regressions:
                lines.append(
                    f"  {d.direction} {d.sub_domain:<18} {d.metric:<20}"
                    f"  {d.baseline:.3f} → {d.current:.3f}"
                    f"  ({d.delta:+.3f})"
                )
            lines.append("")

        if self.improvements:
            lines += [f"  ✓  Improvements ({len(self.improvements)})", "-" * 50]
            for d in self.improvements:
                lines.append(
                    f"  {d.direction} {d.sub_domain:<18} {d.metric:<20}"
                    f"  {d.baseline:.3f} → {d.current:.3f}"
                    f"  ({d.delta:+.3f})"
                )
            lines.append("")

        stable = [
            d for d in self.deltas if d not in self.regressions and d not in self.improvements
        ]
        lines += [f"  ─  Stable metrics: {len(stable)}", "=" * 65, ""]

        if not self.has_regressions:
            lines.insert(2, "  ✓  No regressions detected — all metrics within threshold")

        return "\n".join(lines)


def load_baseline(path: str | Path) -> dict:
    """Load a previously saved eval report dict from JSON."""
    with open(path) as f:
        return json.load(f)


def save_baseline(report_dict: dict, path: str | Path) -> None:
    """Persist an eval report dict to JSON for future regression checks."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report_dict, f, indent=2)


def compare(
    baseline: dict,
    current: dict,
    threshold: float = 0.05,
    metrics: list[str] | None = None,
) -> RegressionReport:
    """Compare current eval run against baseline.

    Parameters
    ----------
    baseline:
        Saved eval report dict (from ``report_to_dict()``).
    current:
        Current eval report dict.
    threshold:
        Minimum absolute drop to count as a regression (e.g. 0.05 = 5pp).
    metrics:
        List of metric keys to compare in sub_domain_summaries.
        Defaults to: pass_rate, precision_at_5, recall_at_5, mrr_score.

    Returns
    -------
    RegressionReport
    """
    if metrics is None:
        metrics = ["pass_rate", "precision_at_5", "recall_at_5", "mrr_score"]

    all_deltas: list[MetricDelta] = []

    # Overall metrics
    overall_metrics = [
        "overall_pass_rate",
        "overall_precision_at_5",
        "overall_recall_at_5",
        "overall_mrr",
    ]
    for metric in overall_metrics:
        base_val = baseline.get(metric, 0.0)
        curr_val = current.get(metric, 0.0)
        all_deltas.append(
            MetricDelta(
                metric=metric,
                sub_domain="overall",
                baseline=base_val,
                current=curr_val,
            )
        )

    # Per-sub-domain metrics
    base_domains: dict = baseline.get("sub_domain_summaries", {})
    curr_domains: dict = current.get("sub_domain_summaries", {})

    for domain in set(list(base_domains.keys()) + list(curr_domains.keys())):
        base_d = base_domains.get(domain, {})
        curr_d = curr_domains.get(domain, {})
        for metric in metrics:
            base_val = float(base_d.get(metric, 0.0))
            curr_val = float(curr_d.get(metric, 0.0))
            all_deltas.append(
                MetricDelta(
                    metric=metric,
                    sub_domain=domain,
                    baseline=base_val,
                    current=curr_val,
                )
            )

    regressions = [d for d in all_deltas if d.delta < -threshold]
    improvements = [d for d in all_deltas if d.delta > threshold]

    return RegressionReport(
        deltas=all_deltas,
        threshold=threshold,
        regressions=regressions,
        improvements=improvements,
    )
