"""audit_session tool — Run the 3-layer Session Intelligence audit on the current Ableton session.

Layer 1 (Universal): objective checks — missing EQ, missing HP, extreme compression, etc.
Layer 2 (Pattern): anomaly detection vs user's historical patterns (needs >= 3 saved sessions).
Layer 3 (Genre): opt-in style suggestions for a specific genre.

Use when the user says:
  - "Audit my session"
  - "What's wrong with my mix?"
  - "Check my session for issues"
  - "Run a mix check"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

try:
    from ingestion.ableton_bridge import AbletonBridge
except ImportError:
    AbletonBridge = None  # type: ignore[assignment,misc]

try:
    from ingestion.session_auditor import SessionAuditor
except ImportError:
    SessionAuditor = None  # type: ignore[assignment,misc]

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005


class AuditSession(MusicalTool):
    """Run the 3-layer Session Intelligence audit on the current Ableton session."""

    @property
    def name(self) -> str:
        return "audit_session"

    @property
    def description(self) -> str:
        return (
            "Run a 3-layer audit of the current Ableton Live session. "
            "Layer 1 (Universal): objective checks — missing EQ/HP filters, extreme compression. "
            "Layer 2 (Pattern): anomaly detection vs your historical mixing patterns (needs >= 3 saved sessions). "
            "Layer 3 (Genre): opt-in style suggestions when a genre preset is provided. "
            "Returns grouped findings with severity levels (critical/warning/info/suggestion). "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre_preset",
                type=str,
                description=(
                    "Optional genre preset name for Layer 3 suggestions. "
                    "Available: organic_house, melodic_techno, deep_house, techno. "
                    "Leave empty to run Layers 1+2 only."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="force_refresh",
                type=bool,
                description="Bypass session cache and fetch live data from Ableton.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="severity_filter",
                type=str,
                description=(
                    "Filter findings by severity. "
                    "Options: '' (all), 'critical', 'warning', 'info', 'suggestion'. "
                    "Default: all."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the 3-layer audit and return grouped findings."""
        genre_preset: str = str(kwargs.get("genre_preset", "") or "").strip()
        force_refresh: bool = bool(kwargs.get("force_refresh", False))
        severity_filter: str = str(kwargs.get("severity_filter", "") or "").strip().lower()

        if AbletonBridge is None:
            return ToolResult(success=False, error="AbletonBridge not available")

        try:
            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session(force_refresh=force_refresh)
        except ConnectionError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Error reading session: {exc}")

        if SessionAuditor is None:
            return ToolResult(success=False, error="SessionAuditor not available")

        try:
            auditor = SessionAuditor()
            report = auditor.run_audit(session, genre_preset=genre_preset or None)
        except Exception as exc:
            return ToolResult(success=False, error=f"Audit failed: {exc}")

        # Build findings list
        findings = report.findings
        if severity_filter and severity_filter in ("critical", "warning", "info", "suggestion"):
            findings = tuple(f for f in findings if f.severity == severity_filter)

        findings_data = [
            {
                "layer": f.layer,
                "severity": f.severity,
                "icon": f.icon,
                "channel": f.channel_name,
                "rule": f.rule_id,
                "message": f.message,
                "reason": f.reason,
                "confidence": round(f.confidence, 2),
                "fix_available": f.fix_action is not None,
                "fix_action": f.fix_action_dict(),
            }
            for f in findings
        ]

        # Group by layer for readability
        grouped: dict[str, list[dict]] = {"universal": [], "pattern": [], "genre": []}
        for f in findings_data:
            grouped.setdefault(f["layer"], []).append(f)

        summary = (
            f"[X] {report.critical_count} critical, "
            f"[!] {report.warning_count} warning, "
            f"[i] {report.info_count} info, "
            f"[*] {report.suggestion_count} suggestion"
        )

        return ToolResult(
            success=True,
            data={
                "summary": summary,
                "total_findings": len(findings),
                "critical_count": report.critical_count,
                "warning_count": report.warning_count,
                "info_count": report.info_count,
                "suggestion_count": report.suggestion_count,
                "findings_by_layer": grouped,
                "genre_preset": genre_preset or None,
            },
            metadata={
                "ws_host": _WS_HOST,
                "ws_port": _WS_PORT,
                "total_channels": len(report.session_map.all_channels),
                "generated_at": report.generated_at,
            },
        )
