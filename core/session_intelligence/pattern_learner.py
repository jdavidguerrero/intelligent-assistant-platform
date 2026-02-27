"""core/session_intelligence/pattern_learner.py — Layer 2: pattern-based anomaly detection.

All functions are pure: they receive pattern data as dicts (loaded externally
by ingestion/pattern_store.py) and return AuditFinding objects.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.
"""

from __future__ import annotations

from typing import Any

from core.session_intelligence.types import AuditFinding, ChannelInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum sessions saved before Layer 2 activates.
MIN_SESSIONS_REQUIRED: int = 3

# Known instrument type keys and heuristic patterns used to infer them.
_INSTRUMENT_PATTERNS: dict[str, list[str]] = {
    "kick": ["kick", "kck", "bd"],
    "snare": ["snare", "snr", "clap"],
    "hihat": ["hihat", "hh", "hat", "cymbal"],
    "pad": ["pad", "atmos", "texture", "ambient"],
    "bass": ["bass", "sub", "808"],
    "vocal": ["voc", "voice", "sing", "rap"],
    "lead": ["lead", "melody", "arp", "pluck"],
    "fx": ["fx", "effect", "riser", "impact", "sfx"],
    "chord": ["chord", "harm", "key", "piano", "plano"],
}

# Bus-type → instrument type fallback when name heuristic is insufficient.
_BUS_TYPE_TO_INSTRUMENT: dict[str, str] = {
    "drums": "kick",
    "bass": "bass",
    "melodic": "pad",
    "vocal": "vocal",
    "fx": "fx",
}


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _median(values: list[float]) -> float:
    """Compute median of a list of floats. Returns 0.0 for empty list.

    Args:
        values: List of float values.

    Returns:
        Median value, or 0.0 if list is empty.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _mad(values: list[float], median: float) -> float:
    """Compute Median Absolute Deviation of a list given a precomputed median.

    Args:
        values: List of float values.
        median: Precomputed median of ``values``.

    Returns:
        Median Absolute Deviation (MAD).
    """
    deviations = [abs(v - median) for v in values]
    return _median(deviations)


def _is_anomaly(value: float, values: list[float], *, n_mad: float = 2.0) -> bool:
    """Return True if ``value`` is outside ``median ± n_mad * MAD``.

    Returns False if ``len(values) < 3`` (insufficient data).

    Args:
        value: The value to test.
        values: Historical values to compare against.
        n_mad: Number of MADs to use as threshold (default 2.0).

    Returns:
        True if value is anomalous, False otherwise.
    """
    if len(values) < 3:
        return False
    med = _median(values)
    mad = _mad(values, med)
    # If MAD is 0 (all values identical) use a tiny epsilon so exact
    # duplicates never trigger a false anomaly.
    threshold = n_mad * mad if mad > 0 else 0.0
    return abs(value - med) > threshold


# ---------------------------------------------------------------------------
# Instrument type inference
# ---------------------------------------------------------------------------


def _infer_instrument_type(channel: ChannelInfo) -> str:
    """Infer instrument type key from channel info.

    Uses channel name patterns first, then parent_bus as a fallback.

    Args:
        channel: Channel to classify.

    Returns:
        One of: ``"kick"``, ``"snare"``, ``"hihat"``, ``"pad"``, ``"bass"``,
        ``"lead"``, ``"vocal"``, ``"fx"``, ``"chord"``, ``"unknown"``.
    """
    lower_name = channel.name.lower()
    for instrument_type, patterns in _INSTRUMENT_PATTERNS.items():
        if any(p in lower_name for p in patterns):
            return instrument_type

    # Fallback: use parent bus type mapping
    if channel.parent_bus is not None:
        lower_bus = channel.parent_bus.lower()
        for bus_keyword, instrument_type in _BUS_TYPE_TO_INSTRUMENT.items():
            if bus_keyword in lower_bus:
                return instrument_type

    return "unknown"


# ---------------------------------------------------------------------------
# HP frequency detection
# ---------------------------------------------------------------------------


def _get_current_hp_freq(channel: ChannelInfo) -> float | None:
    """Return estimated HP cutoff frequency in Hz from channel's EQ devices.

    Searches all EQ-type devices for an active HP band. Returns a truthy
    float (the raw frequency value) when found, or ``None`` if no HP filter
    is detected.

    Note: We return the raw EQ frequency value, not calibrated Hz, because
    this function is used primarily for presence/absence detection.

    Args:
        channel: Channel to inspect.

    Returns:
        Raw EQ frequency value of the first active HP band, or ``None``.
    """
    for device in channel.devices:
        if device.class_name not in ("Eq8", "AutoEq", "FilterEQ3"):
            continue
        params = device.params
        # EQ8 band layout: band N uses params at indices base, base+1, ..., base+4
        # base = 2 + (band-1)*5
        # Within band: [freq, gain, q, filter_type, active]
        # FilterType 6 = HP_12, 7 = HP_48
        for band_n in range(1, 9):
            base = 2 + (band_n - 1) * 5
            active_idx = base + 4
            filter_type_idx = base + 3
            freq_idx = base
            if active_idx >= len(params) or filter_type_idx >= len(params):
                break
            _name_a, _disp_a, active_raw = params[active_idx]
            _name_ft, _disp_ft, ft_raw = params[filter_type_idx]
            _name_fr, _disp_fr, freq_raw = params[freq_idx]
            is_hp = int(round(ft_raw)) in (6, 7)
            is_active = bool(active_raw)
            if is_hp and is_active:
                return freq_raw
    return None


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------


def detect_pattern_anomalies(
    channel: ChannelInfo,
    patterns: dict[str, Any],
    *,
    sessions_saved: int,
) -> list[AuditFinding]:
    """Compare a channel's current settings against user's historical patterns.

    Args:
        channel: The channel to check.
        patterns: Dict loaded from patterns.json. Shape::

            {
                "pad": {
                    "sample_count": 12,
                    "volume_db_values": [-12.0, -11.5, ...],
                    "comp_ratio_values": [2.0, 2.5, ...],
                    "hp_freq_values": [120.0, 150.0, ...],
                    "utility_width_values": [120.0, 130.0, ...],
                },
                ...
            }

        sessions_saved: Total sessions saved. Must be >= :data:`MIN_SESSIONS_REQUIRED`
                        for Layer 2 to activate.

    Returns:
        List of :class:`AuditFinding` with ``layer="pattern"`` for any
        detected anomalies. Empty if ``sessions_saved < MIN_SESSIONS_REQUIRED``.
    """
    if sessions_saved < MIN_SESSIONS_REQUIRED:
        return []

    instrument_type = _infer_instrument_type(channel)
    if instrument_type not in patterns:
        return []

    pat = patterns[instrument_type]
    sample_count: int = pat.get("sample_count", 0)
    confidence = min(sample_count / 10.0, 1.0)

    findings: list[AuditFinding] = []

    # ------------------------------------------------------------------
    # Volume anomaly
    # ------------------------------------------------------------------
    vol_values: list[float] = pat.get("volume_db_values", [])
    if _is_anomaly(channel.volume_db, vol_values):
        med = _median(vol_values)
        findings.append(
            AuditFinding(
                layer="pattern",
                severity="warning",
                icon="⚠️",
                channel_name=channel.name,
                channel_lom_path=channel.lom_path,
                device_name=None,
                rule_id="pattern_volume",
                message=(
                    f"Your {instrument_type}s are usually at {med:.1f} dB "
                    f"— this is at {channel.volume_db:.1f} dB"
                ),
                reason=f"Based on {sample_count} saved sessions",
                confidence=confidence,
                fix_action=None,
            )
        )

    # ------------------------------------------------------------------
    # Missing HP filter (user usually applies one)
    # ------------------------------------------------------------------
    hp_values: list[float] = pat.get("hp_freq_values", [])
    current_hp = _get_current_hp_freq(channel)
    if len(hp_values) >= 3 and current_hp is None:
        med = _median(hp_values)
        findings.append(
            AuditFinding(
                layer="pattern",
                severity="warning",
                icon="⚠️",
                channel_name=channel.name,
                channel_lom_path=channel.lom_path,
                device_name=None,
                rule_id="pattern_no_hp",
                message=(
                    f"You usually HP {instrument_type}s at ~{med:.0f} Hz "
                    f"— this one has no HP"
                ),
                reason=f"Based on {sample_count} saved sessions",
                confidence=confidence,
                fix_action=None,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Learning helper
# ---------------------------------------------------------------------------


def learn_from_channel(channel: ChannelInfo) -> dict[str, Any]:
    """Extract learnable data from a channel for pattern storage.

    Returns a dict with the current parameter values that can be appended
    to the user's pattern history by ``ingestion/pattern_store.py``.

    Args:
        channel: Channel to extract data from.

    Returns:
        Dict with keys: ``instrument_type``, ``volume_db``, ``has_hp``,
        ``comp_ratio`` (if a compressor is present).
    """
    instrument_type = _infer_instrument_type(channel)
    has_hp = _get_current_hp_freq(channel) is not None

    data: dict[str, Any] = {
        "instrument_type": instrument_type,
        "volume_db": channel.volume_db,
        "has_hp": has_hp,
    }

    # Extract compressor ratio if present
    for device in channel.devices:
        if device.device_type == "compressor":
            for param_name, _disp, raw_value in device.params:
                if param_name.lower() == "ratio":
                    data["comp_ratio"] = raw_value
                    break
            break

    return data
