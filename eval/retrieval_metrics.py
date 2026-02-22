"""Retrieval quality metrics for the evaluation framework.

Metrics
-------
Precision@K
    Fraction of top-K returned sources that are relevant (match
    at least one expected_source pattern).

Recall@K
    Fraction of expected sources that appear in the top-K results.
    If expected_sources is empty (adversarial), returns NaN.

MRR (Mean Reciprocal Rank)
    1 / rank of the first relevant source in the returned list.
    If no relevant source found, MRR = 0.

All functions are pure — no I/O or side effects.
"""

from __future__ import annotations

import math


def _is_relevant(source: str, expected_sources: list[str]) -> bool:
    """Return True if *source* matches any expected source pattern (case-insensitive substring)."""
    source_lower = source.lower()
    return any(pat.lower() in source_lower for pat in expected_sources)


def precision_at_k(
    returned_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
) -> float:
    """Fraction of the top-K returned sources that are relevant.

    Parameters
    ----------
    returned_sources:
        Ordered list of source names from the /ask response.
    expected_sources:
        Ground-truth source patterns (partial match).
    k:
        Cutoff.

    Returns
    -------
    float in [0, 1].  Returns 0.0 if k == 0 or returned_sources is empty.
    """
    if not returned_sources or k == 0 or not expected_sources:
        return 0.0
    top_k = returned_sources[:k]
    relevant = sum(1 for s in top_k if _is_relevant(s, expected_sources))
    return relevant / min(k, len(top_k))


def recall_at_k(
    returned_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
) -> float:
    """Fraction of expected sources that appear in the top-K returned sources.

    Returns NaN when expected_sources is empty (adversarial queries have no
    expected sources and recall is undefined).
    """
    if not expected_sources:
        return math.nan
    top_k = returned_sources[:k]
    found = sum(1 for pat in expected_sources if any(_is_relevant(s, [pat]) for s in top_k))
    return found / len(expected_sources)


def mrr(
    returned_sources: list[str],
    expected_sources: list[str],
) -> float:
    """Mean Reciprocal Rank — 1/rank of the first relevant source.

    Returns 0.0 if no relevant source is found in returned_sources.
    Returns NaN when expected_sources is empty.
    """
    if not expected_sources:
        return math.nan
    for rank, source in enumerate(returned_sources, start=1):
        if _is_relevant(source, expected_sources):
            return 1.0 / rank
    return 0.0


def aggregate_metrics(
    results: list[dict],  # list of per-query metric dicts
    metric_keys: list[str] | None = None,
) -> dict[str, float]:
    """Aggregate per-query metrics by mean, ignoring NaN values.

    Parameters
    ----------
    results:
        List of dicts, each with keys like ``"precision_at_5"``, ``"recall_at_5"``,
        ``"mrr"``.
    metric_keys:
        Keys to aggregate.  If None, all keys present in the first result dict
        are used.

    Returns
    -------
    Dict mapping each metric key to its mean (NaN-excluded).
    """
    if not results:
        return {}
    keys = metric_keys or list(results[0].keys())
    aggregated: dict[str, float] = {}
    for key in keys:
        values = [r[key] for r in results if key in r and not math.isnan(r[key])]
        aggregated[key] = sum(values) / len(values) if values else math.nan
    return aggregated
