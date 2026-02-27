"""core/session_intelligence/types.py — Immutable value objects for the Session Audit system.

All types are frozen dataclasses.  Pure module — no I/O, no env vars,
no imports from db/, api/, or ingestion/.

Hierarchy:
    SessionMap
    ├── BusInfo (group tracks)
    │   └── ChannelInfo (member tracks)
    │       └── DeviceInfo (per device)
    ├── orphan_channels (tracks not in any group)
    ├── return_channels
    └── master_channel

AuditReport
    ├── session_map: SessionMap
    └── findings: tuple[AuditFinding, ...]
"""

from __future__ import annotations

from dataclasses import dataclass

from core.ableton.types import TrackType

# ---------------------------------------------------------------------------
# Device-level
# ---------------------------------------------------------------------------

_VALID_DEVICE_TYPES: frozenset[str] = frozenset(
    {"eq", "compressor", "utility", "instrument", "unknown"}
)


@dataclass(frozen=True)
class DeviceInfo:
    """Semantic device information extracted from a raw Device object.

    ``class_name`` is the stable internal Ableton identifier (e.g. ``"Eq8"``,
    ``"Compressor2"``, ``"StereoGain"``).  ``device_type`` is our semantic
    classification for audit purposes.
    """

    name: str
    """User-visible device name (may have been renamed)."""

    class_name: str
    """Stable internal class name — ``"Eq8"``, ``"Compressor2"``, etc."""

    is_active: bool
    """False if the device is bypassed."""

    device_type: str
    """Semantic type: ``"eq"`` | ``"compressor"`` | ``"utility"`` | ``"instrument"`` | ``"unknown"``."""

    params: tuple[tuple[str, str, float], ...]
    """Parameter snapshot as tuple-of-tuples for hashability.

    Each element: ``(param_name, display_value, raw_value)``.
    Tuple-of-tuples (not dict) keeps the dataclass frozen and hashable.
    """

    lom_path: str
    """Full LOM path, e.g. ``live_set tracks 2 devices 1``."""


# ---------------------------------------------------------------------------
# Channel-level
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelInfo:
    """Semantic channel information extracted from a raw Track object.

    A *channel* is our audit-layer name for what Ableton calls a *track*.
    We rename it to avoid confusion with the group/bus distinction.
    """

    name: str
    index: int
    track_type: TrackType
    parent_bus: str | None
    """Name of the parent group track, or ``None`` if this channel is an orphan."""

    is_orphan: bool
    """True if the channel is not a member of any group bus."""

    volume_db: float
    pan: float
    is_muted: bool
    is_solo: bool
    devices: tuple[DeviceInfo, ...]
    lom_path: str
    volume_lom_id: int = 0
    """Integer LOM ID for the mixer_device.volume Parameter. Use in fix_actions for reliable navigation."""


# ---------------------------------------------------------------------------
# Bus-level
# ---------------------------------------------------------------------------

_VALID_BUS_TYPES: frozenset[str] = frozenset(
    {"drums", "bass", "melodic", "vocal", "fx", "unknown"}
)


@dataclass(frozen=True)
class BusInfo:
    """A group bus in the session (corresponds to a GROUP track in Ableton).

    ``bus_type`` is inferred by fuzzy-matching the group track name against
    known patterns (drums, bass, melodic, vocal, fx).
    """

    name: str
    """Group track name as defined in Ableton (e.g. ``"DRUMS"``)."""

    bus_type: str
    """Inferred semantic type: ``"drums"`` | ``"bass"`` | ``"melodic"`` | ``"vocal"`` | ``"fx"`` | ``"unknown"``."""

    channels: tuple[ChannelInfo, ...]
    """Ordered member channels belonging to this bus."""


# ---------------------------------------------------------------------------
# Session-level map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionMap:
    """Complete semantic map of an Ableton session.

    Built by :func:`core.session_intelligence.mapper.map_session_to_map`
    from a raw :class:`core.ableton.types.SessionState`.
    """

    buses: tuple[BusInfo, ...]
    """Group buses discovered in the session."""

    orphan_channels: tuple[ChannelInfo, ...]
    """Regular channels not belonging to any group bus."""

    return_channels: tuple[ChannelInfo, ...]
    """Ableton return/send tracks."""

    master_channel: ChannelInfo | None
    """Master bus channel, or ``None`` if not present in the session snapshot."""

    all_channels: tuple[ChannelInfo, ...]
    """All channels including orphans and returns (NOT master).

    Convenience field for audit loops so callers don't need to flatten
    ``buses`` + ``orphan_channels`` + ``return_channels`` manually.
    """

    mapped_at: float
    """Unix timestamp (seconds) when this map was built."""


# ---------------------------------------------------------------------------
# Audit findings
# ---------------------------------------------------------------------------

_VALID_LAYERS: frozenset[str] = frozenset({"universal", "pattern", "genre"})
_VALID_SEVERITIES: frozenset[str] = frozenset({"critical", "warning", "info", "suggestion"})


@dataclass(frozen=True)
class AuditFinding:
    """A single finding produced by one audit check.

    ``fix_action`` is serialised as a tuple of ``(key, value)`` pairs rather
    than a dict so the frozen dataclass remains hashable.  Use
    :meth:`fix_action_dict` to convert back to a dict for bridge consumption.
    """

    layer: str
    """Audit layer that produced this finding: ``"universal"`` | ``"pattern"`` | ``"genre"``."""

    severity: str
    """``"critical"`` | ``"warning"`` | ``"info"`` | ``"suggestion"``."""

    icon: str
    """Display icon: ``"❌"`` | ``"⚠️"`` | ``"ℹ️"`` | ``"💡"``."""

    channel_name: str
    """Name of the channel (track) this finding applies to."""

    channel_lom_path: str
    """LOM path to the channel."""

    device_name: str | None
    """Name of the specific device involved, or ``None`` for track-level findings."""

    rule_id: str
    """Stable rule identifier, e.g. ``"no_eq"``, ``"no_highpass"``."""

    message: str
    """Short human-readable summary of the finding."""

    reason: str
    """Explanation of why this is a problem and what to do about it."""

    confidence: float
    """Confidence score in [0.0, 1.0] for this finding."""

    fix_action: tuple[tuple[str, object], ...] | None
    """Serialised fix action as tuple-of-pairs, or ``None`` if no auto-fix is available.

    Example::

        (("lom_path", "live_set tracks 0 devices 1"), ("property", "is_active"), ("value", 1))
    """

    def __post_init__(self) -> None:
        """Validate invariants."""
        if self.layer not in _VALID_LAYERS:
            raise ValueError(
                f"AuditFinding.layer must be one of {sorted(_VALID_LAYERS)}, got {self.layer!r}"
            )
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"AuditFinding.severity must be one of {sorted(_VALID_SEVERITIES)}, got {self.severity!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"AuditFinding.confidence must be in [0.0, 1.0], got {self.confidence}"
            )

    def fix_action_dict(self) -> dict | None:
        """Convert fix_action tuple back to dict for bridge consumption.

        Returns:
            Dict representation of the fix action, or ``None`` if no fix is defined.
        """
        if self.fix_action is None:
            return None
        return dict(self.fix_action)


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditReport:
    """Complete audit report for a session.

    Aggregates all findings from all audit layers alongside the session map
    used to generate them.
    """

    session_map: SessionMap
    findings: tuple[AuditFinding, ...]
    critical_count: int
    warning_count: int
    suggestion_count: int
    info_count: int
    generated_at: float
    """Unix timestamp (seconds) when this report was generated."""
