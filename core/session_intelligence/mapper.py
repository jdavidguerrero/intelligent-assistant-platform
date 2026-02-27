"""core/session_intelligence/mapper.py — SessionState → SessionMap conversion.

Maps a raw :class:`core.ableton.types.SessionState` snapshot (from the bridge)
to a semantic :class:`SessionMap` that the audit layers can work with.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.
The caller supplies a ``mapped_at`` timestamp rather than this module calling
``time.time()`` — keeping the core fully deterministic and testable.
"""

from __future__ import annotations

from core.ableton.device_maps import (
    COMPRESSOR_CLASS_NAMES,
    EQ_CLASS_NAMES,
)
from core.ableton.types import Device, Parameter, SessionState, Track, TrackType
from core.session_intelligence.types import (
    BusInfo,
    ChannelInfo,
    DeviceInfo,
    SessionMap,
)

# ---------------------------------------------------------------------------
# Device classification
# ---------------------------------------------------------------------------

# Class names considered "instruments" (sound sources).
INSTRUMENT_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "InstrumentVector",  # Drift
        "MultiSampler",  # Sampler
        "OriginalSimpler",  # Simpler
        "InstrumentImpulse",  # Impulse
        "Operator",  # Operator
        "AnalogVst",  # Analog
        "CollisionVst",  # Collision
        "ElectricVst",  # Electric
        "MeldaVst",  # External Melda plugins
        "VstPluginDevice",  # Generic VST
        "Vst3PluginDevice",  # Generic VST3
        "AuPluginDevice",  # AU plugin (macOS)
    }
)

# Extend the device_maps sets to cover additional class names.
_EQ_CLASS_NAMES: frozenset[str] = EQ_CLASS_NAMES | frozenset({"FilterEQ3"})
_COMPRESSOR_CLASS_NAMES: frozenset[str] = COMPRESSOR_CLASS_NAMES | frozenset(
    {"MultibandDynamics"}
)
_UTILITY_CLASS_NAMES: frozenset[str] = frozenset({"StereoGain"})


def _classify_device_type(class_name: str) -> str:
    """Classify a device by its class_name into a semantic device type.

    Args:
        class_name: Stable internal Ableton class name (e.g. ``"Eq8"``).

    Returns:
        One of: ``"eq"``, ``"compressor"``, ``"utility"``, ``"instrument"``, ``"unknown"``.
    """
    if class_name in _EQ_CLASS_NAMES:
        return "eq"
    if class_name in _COMPRESSOR_CLASS_NAMES:
        return "compressor"
    if class_name in _UTILITY_CLASS_NAMES:
        return "utility"
    if class_name in INSTRUMENT_CLASS_NAMES:
        return "instrument"
    return "unknown"


# ---------------------------------------------------------------------------
# Bus name fuzzy matching
# ---------------------------------------------------------------------------

# Patterns checked case-insensitively against group track names.
BUS_NAME_PATTERNS: dict[str, list[str]] = {
    "drums": ["drum", "perc", "beat", "rhythm", "kit"],
    "bass": ["bass"],
    "melodic": ["harm", "chord", "key", "synth", "melodic", "melody"],
    "vocal": ["voc", "voice", "sing", "rap"],
    "fx": ["fx", "effect", "sfx", "riser", "impact", "ambient", "ear"],
}


def _infer_bus_type(bus_name: str) -> str:
    """Infer bus type from bus name using case-insensitive substring matching.

    Args:
        bus_name: Group track name from Ableton (e.g. ``"DRUMS GROUP"``).

    Returns:
        One of: ``"drums"``, ``"bass"``, ``"melodic"``, ``"vocal"``, ``"fx"``, ``"unknown"``.
    """
    lower = bus_name.lower()
    for bus_type, patterns in BUS_NAME_PATTERNS.items():
        for pattern in patterns:
            if pattern in lower:
                return bus_type
    return "unknown"


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _params_to_tuple(
    parameters: tuple[Parameter, ...],
) -> tuple[tuple[str, str, float], ...]:
    """Convert a Parameter tuple to the audit-layer param tuple format.

    Returns:
        Tuple of ``(name, display_value, raw_value)`` triples.
    """
    return tuple((p.name, p.display_value, p.value) for p in parameters)


def _device_to_device_info(device: Device) -> DeviceInfo:
    """Convert a raw :class:`Device` to a semantic :class:`DeviceInfo`.

    Args:
        device: Raw device object from the session snapshot.

    Returns:
        :class:`DeviceInfo` with semantic type classification and flattened params.
    """
    return DeviceInfo(
        name=device.name,
        class_name=device.class_name,
        is_active=device.is_active,
        device_type=_classify_device_type(device.class_name),
        params=_params_to_tuple(device.parameters),
        lom_path=device.lom_path,
    )


def _track_to_channel_info(track: Track, *, parent_bus: str | None) -> ChannelInfo:
    """Convert a raw :class:`Track` to a :class:`ChannelInfo`.

    Args:
        track:      Raw track object from the session snapshot.
        parent_bus: Name of the owning group track, or ``None`` if orphan/return.

    Returns:
        :class:`ChannelInfo` with semantic device classification.
    """
    return ChannelInfo(
        name=track.name,
        index=track.index,
        track_type=track.type,
        parent_bus=parent_bus,
        is_orphan=parent_bus is None and track.type not in (TrackType.RETURN, TrackType.MASTER),
        volume_db=track.volume_db,
        pan=track.pan,
        is_muted=track.mute,
        is_solo=track.solo,
        devices=tuple(_device_to_device_info(d) for d in track.devices),
        lom_path=track.lom_path,
        volume_lom_id=track.volume_lom_id,
    )


# ---------------------------------------------------------------------------
# Main mapping function
# ---------------------------------------------------------------------------


def map_session_to_map(session: SessionState, *, mapped_at: float = 0.0) -> SessionMap:
    """Map a :class:`SessionState` to a semantic :class:`SessionMap`.

    Grouping algorithm:
    - GROUP tracks become :class:`BusInfo` entries.
    - Non-group regular tracks are assigned to the most recent GROUP track
      with a lower index.  Tracks before the first GROUP (or in sessions with
      no groups) are marked as orphans.
    - Return tracks → ``return_channels``.
    - Master track → ``master_channel``.

    Args:
        session:   :class:`SessionState` from ``AbletonBridge.get_session()``.
        mapped_at: Unix timestamp (seconds) of when mapping was triggered.
                   Callers from ``ingestion/`` should pass ``time.time()``.
                   Defaults to 0.0 for deterministic tests.

    Returns:
        :class:`SessionMap` with buses, orphans, returns, and master.
    """
    # -----------------------------------------------------------------------
    # 1. Separate regular tracks into groups and members
    # -----------------------------------------------------------------------
    current_bus_name: str | None = None
    bus_members: dict[str, list[Track]] = {}  # bus_name → member tracks
    bus_order: list[str] = []  # preserves insertion order
    orphan_tracks: list[Track] = []

    for track in session.tracks:
        if track.type == TrackType.GROUP:
            current_bus_name = track.name
            if current_bus_name not in bus_members:
                bus_members[current_bus_name] = []
                bus_order.append(current_bus_name)
        else:
            if current_bus_name is not None:
                bus_members[current_bus_name].append(track)
            else:
                orphan_tracks.append(track)

    # -----------------------------------------------------------------------
    # 2. Build BusInfo objects
    # -----------------------------------------------------------------------
    buses: list[BusInfo] = []
    for bus_name in bus_order:
        member_channels = tuple(
            _track_to_channel_info(t, parent_bus=bus_name)
            for t in bus_members[bus_name]
        )
        buses.append(
            BusInfo(
                name=bus_name,
                bus_type=_infer_bus_type(bus_name),
                channels=member_channels,
            )
        )

    # -----------------------------------------------------------------------
    # 3. Build orphan channels
    # -----------------------------------------------------------------------
    orphan_channels = tuple(
        _track_to_channel_info(t, parent_bus=None) for t in orphan_tracks
    )

    # -----------------------------------------------------------------------
    # 4. Build return channels
    # -----------------------------------------------------------------------
    return_channels = tuple(
        _track_to_channel_info(t, parent_bus=None) for t in session.return_tracks
    )

    # -----------------------------------------------------------------------
    # 5. Build master channel
    # -----------------------------------------------------------------------
    master_channel = (
        _track_to_channel_info(session.master_track, parent_bus=None)
        if session.master_track is not None
        else None
    )

    # -----------------------------------------------------------------------
    # 6. Build all_channels (orphans + bus members + returns, NOT master)
    # -----------------------------------------------------------------------
    bus_member_channels: list[ChannelInfo] = []
    for bus in buses:
        bus_member_channels.extend(bus.channels)

    all_channels = tuple(
        list(orphan_channels) + bus_member_channels + list(return_channels)
    )

    return SessionMap(
        buses=tuple(buses),
        orphan_channels=orphan_channels,
        return_channels=return_channels,
        master_channel=master_channel,
        all_channels=all_channels,
        mapped_at=mapped_at,
    )
