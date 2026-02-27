"""api/routes/session_intelligence.py — Session Intelligence audit endpoints.

Endpoints
=========
    POST /session/audit           — Full 3-layer audit (all channels)
    GET  /session/patterns        — Current user pattern history
    POST /session/patterns/save   — Save current session as pattern reference
    POST /session/apply-fix       — Execute a single fix_action via Ableton bridge

All endpoints are thin controllers. Business logic lives in ingestion/session_auditor.py
and core/session_intelligence/.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from ingestion.ableton_bridge import AbletonBridge
except ImportError:
    AbletonBridge = None  # type: ignore[assignment,misc]

try:
    from ingestion.pattern_store import PatternStore
except ImportError:
    PatternStore = None  # type: ignore[assignment,misc]

try:
    from ingestion.session_auditor import SessionAuditor
except ImportError:
    SessionAuditor = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session-intelligence"])

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005

# Shared singletons — lazy-initialized on first request
_auditor: Any = None
_pattern_store: Any = None


def _get_auditor() -> Any:
    global _auditor
    if _auditor is None:
        if SessionAuditor is None:
            raise RuntimeError("SessionAuditor not available")
        _auditor = SessionAuditor()
    return _auditor


def _get_pattern_store() -> Any:
    global _pattern_store
    if _pattern_store is None:
        if PatternStore is None:
            raise RuntimeError("PatternStore not available")
        _pattern_store = PatternStore()
    return _pattern_store


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_finding(f: Any) -> dict[str, Any]:
    """Convert an AuditFinding to a JSON-serializable dict."""
    return {
        "layer": f.layer,
        "severity": f.severity,
        "icon": f.icon,
        "channel_name": f.channel_name,
        "channel_lom_path": f.channel_lom_path,
        "device_name": f.device_name,
        "rule_id": f.rule_id,
        "message": f.message,
        "reason": f.reason,
        "confidence": f.confidence,
        "fix_action": f.fix_action_dict(),
    }


def _serialize_report(report: Any) -> dict[str, Any]:
    """Convert an AuditReport to a JSON-serializable dict."""
    session_map = report.session_map
    buses = [
        {
            "name": b.name,
            "bus_type": b.bus_type,
            "channel_count": len(b.channels),
            "channels": [ch.name for ch in b.channels],
        }
        for b in session_map.buses
    ]
    return {
        "generated_at": report.generated_at,
        "critical_count": report.critical_count,
        "warning_count": report.warning_count,
        "suggestion_count": report.suggestion_count,
        "info_count": report.info_count,
        "findings": [_serialize_finding(f) for f in report.findings],
        "session_map": {
            "buses": buses,
            "orphan_channel_count": len(session_map.orphan_channels),
            "return_channel_count": len(session_map.return_channels),
            "total_channels": len(session_map.all_channels),
            "mapped_at": session_map.mapped_at,
        },
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AuditRequest(BaseModel):
    """Request body for POST /session/audit."""

    genre_preset: str | None = None
    """Optional genre preset name (e.g. ``"organic_house"``). ``None`` = Layers 1+2 only."""

    force_refresh: bool = False
    """Bypass session cache and fetch live data from Ableton."""


class ApplyFixRequest(BaseModel):
    """Request body for POST /session/apply-fix."""

    lom_path: str = ""
    """LOM path to the target object, e.g. ``"live_set tracks 2 devices 1 parameters 5"``."""

    lom_id: int = 0
    """Integer LOM ID for reliable navigation (preferred over lom_path when non-zero)."""

    property: str
    """Property to set, typically ``"value"`` or ``"is_active"``."""

    value: float | int | str
    """New value to assign."""

    description: str = ""
    """Human-readable label for logging."""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/audit")
def audit_session(request: AuditRequest) -> dict[str, Any]:
    """Run the full 3-layer audit on the current Ableton session.

    Connects to the ALS Listener device (WebSocket port 11005), builds a
    SessionMap, and runs all three audit layers:

    - **Layer 1 — Universal**: objective rule-based checks (no EQ, no HP, etc.)
    - **Layer 2 — Pattern**: anomaly detection against user's history (needs >= 3 sessions)
    - **Layer 3 — Genre** (opt-in): style-specific suggestions for the selected genre

    Args:
        request: Audit parameters (optional genre preset, optional cache bypass).

    Returns:
        JSON-serialized AuditReport with all findings.

    Raises:
        422: Cannot connect to Ableton (ALS Listener not running).
        500: Unexpected audit failure.
    """
    if AbletonBridge is None:
        raise HTTPException(status_code=500, detail="AbletonBridge not available")

    try:
        bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
        session = bridge.get_session(force_refresh=request.force_refresh)
    except ConnectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot connect to Ableton ALS Listener: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Error reading Ableton session")
        raise HTTPException(status_code=500, detail=f"Error reading session: {exc}") from exc

    try:
        auditor = _get_auditor()
        report = auditor.run_audit(session, genre_preset=request.genre_preset)
    except Exception as exc:
        logger.exception("Audit pipeline failed")
        raise HTTPException(status_code=500, detail=f"Audit failed: {exc}") from exc

    return _serialize_report(report)


@router.get("/patterns")
def get_patterns() -> dict[str, Any]:
    """Return the current user pattern history.

    Reads ingestion/user_data/patterns.json and returns the stored
    per-instrument-type distribution data. Returns an empty result if no
    sessions have been saved yet.

    Returns:
        Dict with ``sessions_saved`` count and ``patterns`` dict.
    """
    store = _get_pattern_store()
    data = store.load()
    return {
        "sessions_saved": data.get("sessions_saved", 0),
        "patterns": data.get("patterns", {}),
    }


@router.post("/patterns/save")
def save_patterns() -> dict[str, Any]:
    """Save the current Ableton session as a pattern reference.

    Reads the live Ableton session, extracts per-channel learnable data
    (volume, HP presence, compression ratio), and appends it to the
    pattern history. Layer 2 anomaly detection activates after 3 saves.

    Returns:
        Dict with ``channels_learned`` count and updated ``sessions_saved``.

    Raises:
        422: Cannot connect to Ableton.
        500: Unexpected error.
    """
    if AbletonBridge is None:
        raise HTTPException(status_code=500, detail="AbletonBridge not available")

    try:
        bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
        session = bridge.get_session()
    except ConnectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot connect to Ableton ALS Listener: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Error reading Ableton session for pattern save")
        raise HTTPException(status_code=500, detail=f"Error reading session: {exc}") from exc

    try:
        auditor = _get_auditor()
        channels_learned = auditor.save_session_patterns(session)
        sessions_saved = _get_pattern_store().get_sessions_saved()
    except Exception as exc:
        logger.exception("Failed to save session patterns")
        raise HTTPException(status_code=500, detail=f"Failed to save patterns: {exc}") from exc

    return {
        "channels_learned": channels_learned,
        "sessions_saved": sessions_saved,
    }


@router.post("/apply-fix")
def apply_fix(request: ApplyFixRequest) -> dict[str, Any]:
    """Execute a single fix_action via the Ableton bridge.

    Takes a structured fix action (lom_path + property + value) from an
    AuditFinding and sends it to the ALS Listener as a LOM write command.

    Args:
        request: Fix action parameters (lom_path, property, value).

    Returns:
        Dict with the bridge acknowledgement.

    Raises:
        422: Invalid fix request or Ableton connection error.
        500: Unexpected error.
    """
    if not request.lom_path and not request.lom_id:
        raise HTTPException(status_code=422, detail="lom_path or lom_id is required")
    if not request.property:
        raise HTTPException(status_code=422, detail="property is required")

    if AbletonBridge is None:
        raise HTTPException(status_code=500, detail="AbletonBridge not available")

    from core.ableton.types import LOMCommand

    cmd = LOMCommand(
        type="set_property",
        lom_path=request.lom_path,
        property=request.property,
        value=request.value,
        description=request.description or f"apply_fix: {request.lom_path or request.lom_id}",
        lom_id=request.lom_id,
    )

    try:
        bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
        ack = bridge.send_command(cmd)
    except ConnectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot connect to Ableton ALS Listener: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("apply_fix failed")
        raise HTTPException(status_code=500, detail=f"apply_fix failed: {exc}") from exc

    return {
        "applied": True,
        "lom_path": request.lom_path,
        "lom_id": request.lom_id,
        "property": request.property,
        "value": request.value,
        "ack": ack,
    }
