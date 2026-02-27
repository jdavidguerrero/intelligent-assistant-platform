"""core/session_intelligence/recommendations.py — Merge all 3 layers, deduplicate, prioritize.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.
"""

from __future__ import annotations

from core.session_intelligence.types import AuditFinding, AuditReport, SessionMap

# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

# Priority: lower number = higher priority (shown first).
# P1: critical universal
# P2: critical gain
# P3: pattern anomalies (warnings)
# P4: universal warnings
# P5: gain warnings
# P6: genre suggestions
# P7: universal info
# P8: gain info
_PRIORITY: dict[tuple[str, str], int] = {
    ("universal", "critical"): 1,
    ("universal", "warning"): 4,
    ("universal", "info"): 7,
    ("universal", "suggestion"): 6,
    ("pattern", "critical"): 3,
    ("pattern", "warning"): 3,
    ("pattern", "info"): 7,
    ("pattern", "suggestion"): 6,
    ("genre", "critical"): 2,
    ("genre", "warning"): 5,
    ("genre", "info"): 8,
    ("genre", "suggestion"): 6,
}

# Layer-source tiebreak for "gain staging" findings which live inside the
# "universal" layer but belong to the gain staging module. They are
# differentiated by having rule_ids starting with "gs_".
# Within the same priority, gain-staging findings come after standard
# universal findings (tiebreak only, same P-level applies).


def _priority(finding: AuditFinding) -> int:
    """Return numeric priority for a finding (lower = more important).

    Gain staging rule_ids (prefixed "gs_") that are critical are treated
    as P2; gain staging warnings as P5; gain staging info as P8.

    Args:
        finding: The finding to score.

    Returns:
        Integer priority in [1, 8].
    """
    is_gain = finding.rule_id.startswith("gs_")
    if is_gain:
        if finding.severity == "critical":
            return 2
        elif finding.severity == "warning":
            return 5
        else:
            return 8
    return _PRIORITY.get((finding.layer, finding.severity), 9)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_audit_report(
    session_map: SessionMap,
    *,
    universal_findings: list[AuditFinding],
    gain_findings: list[AuditFinding],
    pattern_findings: list[AuditFinding],
    genre_findings: list[AuditFinding],
    generated_at: float,
) -> AuditReport:
    """Merge findings from all layers, deduplicate, and build AuditReport.

    Priority order (P1 = highest):
        P1: critical universal (e.g. no EQ, no HP)
        P2: critical gain (e.g. headroom danger)
        P3: pattern anomalies (unusual for this user)
        P4: universal warnings (e.g. extreme compression)
        P5: gain warnings (e.g. tight headroom)
        P6: genre/universal suggestions
        P7: universal info (e.g. bypassed plugins, muted channels)
        P8: gain info (e.g. untouched faders)

    Deduplication: if the same ``(channel_lom_path, rule_id)`` pair appears
    in multiple layers, the highest-priority one is kept (lower P wins).

    Args:
        session_map: The session map this report is based on.
        universal_findings: Findings from :func:`run_universal_audit`.
        gain_findings: Findings from :func:`run_gain_staging_audit`.
        pattern_findings: Findings from :func:`detect_pattern_anomalies`.
        genre_findings: Findings from :func:`run_genre_audit`.
        generated_at: Unix timestamp (seconds) when the report was generated.

    Returns:
        :class:`AuditReport` with merged, deduplicated, sorted findings.
    """
    all_findings: list[AuditFinding] = (
        universal_findings + gain_findings + pattern_findings + genre_findings
    )

    # Deduplicate: keep highest-priority (lowest P number) per (lom_path, rule_id)
    seen: dict[tuple[str, str], AuditFinding] = {}
    for finding in all_findings:
        key = (finding.channel_lom_path, finding.rule_id)
        if key not in seen:
            seen[key] = finding
        else:
            existing = seen[key]
            if _priority(finding) < _priority(existing):
                seen[key] = finding

    deduplicated = list(seen.values())
    deduplicated.sort(key=_priority)

    findings_tuple = tuple(deduplicated)

    critical_count = sum(1 for f in findings_tuple if f.severity == "critical")
    warning_count = sum(1 for f in findings_tuple if f.severity == "warning")
    suggestion_count = sum(1 for f in findings_tuple if f.severity == "suggestion")
    info_count = sum(1 for f in findings_tuple if f.severity == "info")

    return AuditReport(
        session_map=session_map,
        findings=findings_tuple,
        critical_count=critical_count,
        warning_count=warning_count,
        suggestion_count=suggestion_count,
        info_count=info_count,
        generated_at=generated_at,
    )


def filter_findings_by_layer(
    findings: tuple[AuditFinding, ...],
    layer: str,
) -> list[AuditFinding]:
    """Filter findings to a specific layer.

    Args:
        findings: Tuple of findings from an :class:`AuditReport`.
        layer: Layer name to filter to (``"universal"``, ``"pattern"``, ``"genre"``).

    Returns:
        List of findings belonging to the specified layer.
    """
    return [f for f in findings if f.layer == layer]


def filter_findings_by_severity(
    findings: tuple[AuditFinding, ...],
    severity: str,
) -> list[AuditFinding]:
    """Filter findings to a specific severity.

    Args:
        findings: Tuple of findings from an :class:`AuditReport`.
        severity: Severity level to filter to (``"critical"``, ``"warning"``,
                  ``"info"``, ``"suggestion"``).

    Returns:
        List of findings with the specified severity.
    """
    return [f for f in findings if f.severity == severity]
