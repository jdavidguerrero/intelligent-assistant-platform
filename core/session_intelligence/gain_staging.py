"""core/session_intelligence/gain_staging.py — Layer 1 + Layer 2 gain staging checks.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.
"""

from __future__ import annotations

from core.ableton.types import TrackType
from core.session_intelligence.types import AuditFinding, ChannelInfo, SessionMap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEADROOM_CRITICAL_DB: float = -3.0   # above this = danger zone
_HEADROOM_WARNING_DB: float = -6.0    # above this = tight

# Fader level we suggest instead when a channel is too hot (safer headroom).
_SUGGESTED_SAFE_VOLUME_DB: float = -6.0

# Raw volume value that corresponds to -6.0 dB in Ableton's LOM.
# Ableton volume: raw 0.0 = -inf, raw 0.85 = 0.0 dB, raw 1.0 = +6 dB.
# For our fix_action we pass a dB value; the bridge converts it.
_SUGGESTED_SAFE_VOLUME_RAW: float = 0.85 * (10 ** (_SUGGESTED_SAFE_VOLUME_DB / 20.0))

# Bass/sub name heuristics
_BASS_NAME_PATTERNS: frozenset[str] = frozenset({"bass", "sub", "808"})

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "warning": 1,
    "info": 2,
    "suggestion": 3,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_bass_or_sub_channel(channel: ChannelInfo) -> bool:
    """Return True if channel name or parent bus suggests bass/sub content.

    Args:
        channel: Channel to inspect.

    Returns:
        True if any bass/sub pattern matches the channel name or parent bus name.
    """
    lower_name = channel.name.lower()
    if any(p in lower_name for p in _BASS_NAME_PATTERNS):
        return True
    if channel.parent_bus is not None:
        lower_bus = channel.parent_bus.lower()
        if any(p in lower_bus for p in _BASS_NAME_PATTERNS):
            return True
    return False


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_untouched_faders(session_map: SessionMap) -> list[AuditFinding]:
    """Return findings for channels where fader is at default 0.0 dB.

    Skips master channel. Each matching channel produces a severity="info"
    finding.

    Args:
        session_map: The session to audit.

    Returns:
        List of :class:`AuditFinding` with rule_id="gs_untouched_fader".
    """
    findings: list[AuditFinding] = []
    for channel in session_map.all_channels:
        if channel.track_type == TrackType.MASTER:
            continue
        if channel.volume_db != 0.0:
            continue
        findings.append(
            AuditFinding(
                layer="universal",
                severity="info",
                icon="ℹ️",
                channel_name=channel.name,
                channel_lom_path=channel.lom_path,
                device_name=None,
                rule_id="gs_untouched_fader",
                message="Fader never adjusted — at 0.0 dB default",
                reason="Common in rough mixes — likely needs gain staging",
                confidence=0.60,
                fix_action=None,
            )
        )
    return findings


def check_low_headroom(session_map: SessionMap) -> list[AuditFinding]:
    """Return findings for channels with very high fader levels.

    Critical if ``volume_db > _HEADROOM_CRITICAL_DB`` (-3.0 dB).
    Warning if ``_HEADROOM_WARNING_DB < volume_db <= _HEADROOM_CRITICAL_DB``
    (-6.0 < db <= -3.0).

    Skips master channel. Includes muted tracks (muted channels may be
    unmuted later and their levels matter).

    Args:
        session_map: The session to audit.

    Returns:
        List of :class:`AuditFinding` sorted by severity.
    """
    findings: list[AuditFinding] = []

    for channel in session_map.all_channels:
        if channel.track_type == TrackType.MASTER:
            continue

        vol = channel.volume_db
        # Volume lives at mixer_device.volume (a Parameter — set "value" property,
        # 0–1 raw scale).  Prefer integer lom_id navigation (reliable across all
        # Max versions) over path-string navigation which can silently fail.
        if channel.volume_lom_id:
            vol_fix = (
                ("lom_id", channel.volume_lom_id),
                ("lom_path", channel.lom_path + " mixer_device volume"),
                ("property", "value"),
                ("value", _SUGGESTED_SAFE_VOLUME_RAW),
            )
        else:
            vol_fix = (
                ("lom_path", channel.lom_path + " mixer_device volume"),
                ("property", "value"),
                ("value", _SUGGESTED_SAFE_VOLUME_RAW),
            )

        if vol > _HEADROOM_CRITICAL_DB:
            findings.append(
                AuditFinding(
                    layer="universal",
                    severity="critical",
                    icon="❌",
                    channel_name=channel.name,
                    channel_lom_path=channel.lom_path,
                    device_name=None,
                    rule_id="gs_low_headroom",
                    message=f"Fader at {vol:.1f} dB — limited headroom",
                    reason="High individual channel levels reduce master headroom",
                    confidence=0.90,
                    fix_action=vol_fix,
                )
            )
        elif vol > _HEADROOM_WARNING_DB:
            findings.append(
                AuditFinding(
                    layer="universal",
                    severity="warning",
                    icon="⚠️",
                    channel_name=channel.name,
                    channel_lom_path=channel.lom_path,
                    device_name=None,
                    rule_id="gs_low_headroom",
                    message=f"Fader at {vol:.1f} dB — limited headroom",
                    reason="High individual channel levels reduce master headroom",
                    confidence=0.80,
                    fix_action=vol_fix,
                )
            )

    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))


def check_low_freq_not_mono(session_map: SessionMap) -> list[AuditFinding]:
    """Return warnings for bass/sub channels that appear to be panned.

    Checks: ``abs(pan) > 0.1`` AND channel name/bus suggests bass/sub content.

    Args:
        session_map: The session to audit.

    Returns:
        List of :class:`AuditFinding` with rule_id="gs_bass_not_mono".
    """
    findings: list[AuditFinding] = []
    for channel in session_map.all_channels:
        if channel.track_type == TrackType.MASTER:
            continue
        if not _is_bass_or_sub_channel(channel):
            continue
        if abs(channel.pan) <= 0.1:
            continue
        pan_pct = channel.pan * 100.0
        findings.append(
            AuditFinding(
                layer="universal",
                severity="warning",
                icon="⚠️",
                channel_name=channel.name,
                channel_lom_path=channel.lom_path,
                device_name=None,
                rule_id="gs_bass_not_mono",
                message=f"Low-frequency channel panned to {pan_pct:.0f}% — bass should be mono",
                reason=(
                    "Sub frequencies are non-directional; panning bass causes "
                    "phase issues on mono systems"
                ),
                confidence=0.80,
                fix_action=None,
            )
        )
    return findings


def run_gain_staging_audit(session_map: SessionMap) -> list[AuditFinding]:
    """Run all gain staging checks and return combined findings sorted by severity.

    Combines results from :func:`check_untouched_faders`,
    :func:`check_low_headroom`, and :func:`check_low_freq_not_mono`.

    Args:
        session_map: The session to audit.

    Returns:
        List of :class:`AuditFinding` sorted by severity (critical → info).
    """
    findings: list[AuditFinding] = []
    findings.extend(check_untouched_faders(session_map))
    findings.extend(check_low_headroom(session_map))
    findings.extend(check_low_freq_not_mono(session_map))
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
