"""core/session_intelligence/universal_audit.py — Layer 1: Universal audit checks.

Eight rule-based checks that apply to every session regardless of genre or
production style.  All functions are pure — no I/O, no side effects.

Each ``check_*`` function returns ``None`` if the channel passes, or an
:class:`AuditFinding` if a problem is detected.

``run_universal_audit`` applies all checks to every channel in the session map
and returns findings sorted by severity (critical → warning → info → suggestion).
"""

from __future__ import annotations

from core.ableton.device_maps import comp2_raw_to_ratio
from core.ableton.types import TrackType
from core.session_intelligence.types import AuditFinding, ChannelInfo, SessionMap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KICK_PATTERNS: frozenset[str] = frozenset({"kick", "kck", "bd", "bass drum", "bassdrum"})
_SUB_PATTERNS: frozenset[str] = frozenset({"sub", "808", "subbass"})

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "warning": 1,
    "info": 2,
    "suggestion": 3,
}

# Compressor 2 ratio raw value that approximates 4:1 (a safe default).
# Using our quadratic model: raw = sqrt((ratio - 1) / 99) → sqrt(3/99) ≈ 0.174
_COMP2_SAFE_RATIO_RAW: float = 0.174


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def _is_kick_or_sub(channel_name: str) -> bool:
    """Return True if channel name suggests kick drum or sub bass.

    Args:
        channel_name: Track name as shown in Ableton.

    Returns:
        True if the name matches any known kick or sub pattern.
    """
    lower = channel_name.lower()
    return any(p in lower for p in _KICK_PATTERNS | _SUB_PATTERNS)


def _has_instrument(channel: ChannelInfo) -> bool:
    """Return True if channel has at least one instrument device.

    Args:
        channel: Channel to inspect.

    Returns:
        True if any device has ``device_type == "instrument"``.
    """
    return any(d.device_type == "instrument" for d in channel.devices)


def _get_hp_filter_raw(channel: ChannelInfo) -> float | None:
    """Return the raw HP filter frequency value if an active HP band is found.

    Checks all Eq8 devices for a band with filter_type 6 (HP_12) or 7 (HP_48).
    Returns the raw frequency value of the first active HP band found.

    HP_12 = FilterType value 6, HP_48 = FilterType value 7.

    Args:
        channel: Channel to inspect.

    Returns:
        Raw frequency value of the first active HP band, or ``None`` if none found.
    """
    # EQ8 band layout: band N uses params at indices base, base+1, ..., base+4
    # base = 2 + (band-1)*5
    # Within band: [freq, gain, q, filter_type, active]
    # We check all Eq8 devices for any HP band.
    for device in channel.devices:
        if device.class_name not in ("Eq8", "AutoEq", "FilterEQ3"):
            continue
        params = device.params  # tuple of (name, display_value, raw_value)
        # Walk bands 1–8: each band has 5 params starting at index 2 + (band-1)*5
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
            # Filter types 6 = HP_12, 7 = HP_48
            is_hp = int(round(ft_raw)) in (6, 7)
            is_active = bool(active_raw)
            if is_hp and is_active:
                return freq_raw
    return None


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_no_eq(channel: ChannelInfo) -> AuditFinding | None:
    """Check: instrument channel with no EQ device at all.

    Skips channels that are return tracks, master, or have no instrument.
    Returns a critical finding if the channel has an instrument but no EQ.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    if channel.track_type in (TrackType.RETURN, TrackType.MASTER):
        return None
    if not _has_instrument(channel):
        return None
    has_eq = any(d.device_type == "eq" for d in channel.devices)
    if has_eq:
        return None
    return AuditFinding(
        layer="universal",
        severity="critical",
        icon="❌",
        channel_name=channel.name,
        channel_lom_path=channel.lom_path,
        device_name=None,
        rule_id="no_eq",
        message=f"{channel.name}: No EQ device found",
        reason=(
            "Every instrument channel should have at least one EQ to shape tone "
            "and remove unwanted frequency content. Without EQ, tracks can clash "
            "in the mix and consume unnecessary headroom."
        ),
        confidence=0.95,
        fix_action=None,
    )


def check_no_highpass(channel: ChannelInfo) -> AuditFinding | None:
    """Check: instrument channel with no high-pass filter active.

    Skips kick and sub channels — they intentionally preserve sub-bass content.
    Returns a critical finding if the channel has an instrument and an EQ device
    but no active HP band.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    if channel.track_type in (TrackType.RETURN, TrackType.MASTER):
        return None
    if not _has_instrument(channel):
        return None
    if _is_kick_or_sub(channel.name):
        return None
    has_eq = any(d.device_type == "eq" for d in channel.devices)
    if not has_eq:
        return None  # check_no_eq already covers this case
    hp_raw = _get_hp_filter_raw(channel)
    if hp_raw is not None:
        return None
    return AuditFinding(
        layer="universal",
        severity="critical",
        icon="❌",
        channel_name=channel.name,
        channel_lom_path=channel.lom_path,
        device_name=None,
        rule_id="no_highpass",
        message=f"{channel.name}: No active high-pass filter",
        reason=(
            "A high-pass filter removes sub-bass rumble that most instruments "
            "don't need, leaving headroom for kick and bass. Without it, tracks "
            "accumulate low-end mud that clouds the mix."
        ),
        confidence=0.90,
        fix_action=None,
    )


def check_extreme_compression(channel: ChannelInfo) -> AuditFinding | None:
    """Check: Compressor2 ratio > 10:1.

    Iterates all Compressor2 devices and looks for the ``Ratio`` parameter
    by name.  Converts raw value to ratio using :func:`comp2_raw_to_ratio`.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    for device in channel.devices:
        if device.class_name != "Compressor2":
            continue
        for pi, (param_name, _disp, raw_value) in enumerate(device.params):
            if param_name.lower() == "ratio":
                ratio = comp2_raw_to_ratio(raw_value)
                if ratio > 10.0:
                    # Navigate to the specific parameter object so the bridge
                    # can call api.set('value', raw) — not a track property.
                    fix = (
                        ("lom_path", device.lom_path + " parameters " + str(pi)),
                        ("property", "value"),
                        ("value", _COMP2_SAFE_RATIO_RAW),
                    )
                    return AuditFinding(
                        layer="universal",
                        severity="warning",
                        icon="⚠️",
                        channel_name=channel.name,
                        channel_lom_path=channel.lom_path,
                        device_name=device.name,
                        rule_id="extreme_compression",
                        message=(
                            f"{channel.name}: Extreme compression ratio "
                            f"{ratio:.1f}:1 on {device.name}"
                        ),
                        reason=(
                            "Ratios above 10:1 squash dynamics aggressively and "
                            "can make a track sound lifeless or pumping. "
                            "Consider using 4:1 for transparent compression."
                        ),
                        confidence=0.85,
                        fix_action=fix,
                    )
    return None


def check_untouched_fader(channel: ChannelInfo) -> AuditFinding | None:
    """Check: fader never adjusted from the LOM default of 0.0 dB.

    Skips master channel.  Returns an info finding when the volume is exactly
    0.0 dB — likely never adjusted rather than deliberately set.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    if channel.track_type == TrackType.MASTER:
        return None
    if channel.volume_db != 0.0:
        return None
    return AuditFinding(
        layer="universal",
        severity="info",
        icon="ℹ️",
        channel_name=channel.name,
        channel_lom_path=channel.lom_path,
        device_name=None,
        rule_id="untouched_fader",
        message=f"{channel.name}: Fader at default 0.0 dB — may not have been set",
        reason=(
            "A fader at exactly 0 dB often means it was never touched during mixing. "
            "Intentional 0 dB faders are fine, but worth verifying the balance was "
            "set consciously."
        ),
        confidence=0.60,
        fix_action=None,
    )


def check_bypassed_plugin(channel: ChannelInfo) -> AuditFinding | None:
    """Check: any device is bypassed (is_active == False).

    Returns a finding for the first bypassed device found.
    Skips devices with unknown class names (likely placeholders).

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    for device in channel.devices:
        if device.is_active:
            continue
        if device.class_name == "":
            continue
        fix = (
            ("lom_path", device.lom_path),
            ("property", "is_active"),
            ("value", 1),
        )
        return AuditFinding(
            layer="universal",
            severity="info",
            icon="ℹ️",
            channel_name=channel.name,
            channel_lom_path=channel.lom_path,
            device_name=device.name,
            rule_id="bypassed_plugin",
            message=f"{channel.name}: Device '{device.name}' is bypassed",
            reason=(
                "Bypassed devices still consume memory and may indicate unfinished "
                "mixing decisions. Either activate the device or remove it if no "
                "longer needed."
            ),
            confidence=0.80,
            fix_action=fix,
        )
    return None


def check_muted_with_cpu(channel: ChannelInfo) -> AuditFinding | None:
    """Check: muted channel with active plugins loaded.

    A muted channel with several plugins wastes CPU.  Returns an info finding.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    if not channel.is_muted:
        return None
    if len(channel.devices) == 0:
        return None
    return AuditFinding(
        layer="universal",
        severity="info",
        icon="ℹ️",
        channel_name=channel.name,
        channel_lom_path=channel.lom_path,
        device_name=None,
        rule_id="muted_with_cpu",
        message=(
            f"{channel.name}: Muted with {len(channel.devices)} device(s) loaded"
        ),
        reason=(
            "Muted tracks still process audio through all loaded plugins, "
            "consuming CPU. If the track won't be used in the final mix, "
            "consider freezing it or removing unused devices."
        ),
        confidence=0.70,
        fix_action=None,
    )


def check_mono_on_stereo(channel: ChannelInfo) -> AuditFinding | None:
    """Check: Utility (StereoGain) width set to 0% on a non-kick/sub channel.

    A mono width on a non-kick channel is usually unintentional and collapses
    the stereo field.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    if _is_kick_or_sub(channel.name):
        return None
    for device in channel.devices:
        if device.class_name != "StereoGain":
            continue
        for param_name, _disp, raw_value in device.params:
            # Width param name variants: "Stereo Width", "Width"
            if "width" in param_name.lower():
                # raw=0.0 → 0% width (mono); raw=0.25 → 100% (normal stereo)
                # The Utility width maps raw 0–1 to 0–400%.
                # 0% width (mono) = raw 0.0
                if raw_value == 0.0:
                    return AuditFinding(
                        layer="universal",
                        severity="warning",
                        icon="⚠️",
                        channel_name=channel.name,
                        channel_lom_path=channel.lom_path,
                        device_name=device.name,
                        rule_id="mono_on_stereo",
                        message=f"{channel.name}: Utility width at 0% (mono) on non-kick/sub channel",
                        reason=(
                            "A width of 0% collapses the stereo field to mono. "
                            "This is intentional for kick and sub but usually "
                            "undesirable for melodic or pad channels."
                        ),
                        confidence=0.75,
                        fix_action=None,
                    )
    return None


def check_duplicate_device_type(channel: ChannelInfo) -> AuditFinding | None:
    """Check: multiple devices of the same type (e.g. two EQs, two compressors).

    Returns an info finding for the first duplicate type found.

    Args:
        channel: Channel to inspect.

    Returns:
        :class:`AuditFinding` or ``None``.
    """
    counts: dict[str, int] = {}
    for device in channel.devices:
        if device.device_type == "unknown":
            continue
        counts[device.device_type] = counts.get(device.device_type, 0) + 1

    for dtype, count in counts.items():
        if count > 1:
            return AuditFinding(
                layer="universal",
                severity="info",
                icon="ℹ️",
                channel_name=channel.name,
                channel_lom_path=channel.lom_path,
                device_name=None,
                rule_id="duplicate_device_type",
                message=f"{channel.name}: {count} {dtype} devices loaded",
                reason=(
                    f"Having {count} {dtype} devices on the same channel may be intentional "
                    "but could also be a sign of accidental duplication. "
                    "Confirm each device is serving a distinct purpose."
                ),
                confidence=0.65,
                fix_action=None,
            )
    return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_CHECKS = [
    check_no_eq,
    check_no_highpass,
    check_extreme_compression,
    check_untouched_fader,
    check_bypassed_plugin,
    check_muted_with_cpu,
    check_mono_on_stereo,
    check_duplicate_device_type,
]


def run_universal_audit(session_map: SessionMap) -> list[AuditFinding]:
    """Run all 8 universal checks on every channel in the session map.

    Applies each check to every channel in ``session_map.all_channels``
    (orphans + bus members + returns — master is excluded).

    Args:
        session_map: :class:`SessionMap` produced by
                     :func:`core.session_intelligence.mapper.map_session_to_map`.

    Returns:
        List of :class:`AuditFinding`, sorted by severity (critical → warning →
        info → suggestion).  Empty list if no issues found.
    """
    findings: list[AuditFinding] = []
    for channel in session_map.all_channels:
        for check_fn in _CHECKS:
            finding = check_fn(channel)
            if finding is not None:
                findings.append(finding)
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
