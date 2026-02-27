"""core/ableton/commands.py — LOM command generators.

Each function returns one or more :class:`~core.ableton.types.LOMCommand`
objects ready to be sent to the ALS Listener via the ingestion bridge.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.

LOM write protocol (over WebSocket)
────────────────────────────────────
Each command maps to a JSON message sent to the ALS Listener::

    {"type": "set_parameter", "lom_path": "<path>", "property": "value", "value": <v>}

Track property writes use the same shape with a track LOM path::

    {"type": "set_property", "lom_path": "live_set tracks 0", "property": "mute", "value": 1}

Usage
─────
::

    commands = set_eq_band(track, eq_device, band=3, freq_hz=280, gain_db=-3, q=2.0)
    await bridge.send_commands(commands)
"""

from __future__ import annotations

from core.ableton.device_maps import (
    comp2_attack_to_raw,
    comp2_gain_to_raw,
    comp2_release_to_raw,
    comp2_threshold_to_raw,
    eq8_band_indices,
    eq8_freq_to_raw,
    eq8_gain_to_raw,
    eq8_q_to_raw,
    utility_gain_to_raw,
    utility_width_to_raw,
)
from core.ableton.types import Device, LOMCommand, Parameter, Track

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _param_cmd(
    param: Parameter,
    value: float,
    description: str = "",
) -> LOMCommand:
    """Build a ``set_parameter`` command for an existing :class:`Parameter`."""
    return LOMCommand(
        type="set_parameter",
        lom_path=param.lom_path,
        property="value",
        value=value,
        description=description or f"Set {param.name} = {value}",
    )


def _param_path_cmd(
    device: Device,
    param_index: int,
    value: float,
    description: str = "",
) -> LOMCommand:
    """Build a ``set_parameter`` command by parameter index within a device."""
    # LOM path convention: device_path + " parameters " + index
    lom_path = f"{device.lom_path} parameters {param_index}"
    return LOMCommand(
        type="set_parameter",
        lom_path=lom_path,
        property="value",
        value=value,
        description=description,
    )


# ---------------------------------------------------------------------------
# Generic parameter write
# ---------------------------------------------------------------------------


def set_parameter(param: Parameter, value: float) -> LOMCommand:
    """Return a command to set ``param`` to ``value`` (raw 0–1).

    Use this when you already have a :class:`Parameter` object from the
    session state and the raw value to set.

    Args:
        param: Parameter read from session state.
        value: New raw value (must be within ``param.min_value``–``param.max_value``).

    Returns:
        Single :class:`LOMCommand`.

    Raises:
        ValueError: If ``value`` is outside the parameter's range.
    """
    if value < param.min_value or value > param.max_value:
        raise ValueError(
            f"Value {value} out of range for parameter {param.name!r} "
            f"({param.min_value}–{param.max_value})"
        )
    return _param_cmd(param, value, f"Set '{param.name}' → {value:.4f}")


# ---------------------------------------------------------------------------
# EQ Eight commands
# ---------------------------------------------------------------------------


def set_eq_band(
    track: Track,
    device: Device,
    *,
    band: int,
    freq_hz: float | None = None,
    gain_db: float | None = None,
    q: float | None = None,
    filter_type: int | None = None,
    enabled: bool | None = None,
) -> list[LOMCommand]:
    """Generate commands to adjust one band of an EQ Eight.

    Only the provided keyword arguments are written; omitted ones are left at
    their current values.

    Args:
        track:       Parent track (used for description only).
        device:      EQ Eight device.
        band:        1-based band number (1–8).
        freq_hz:     New frequency in Hz (20–20 000).
        gain_db:     New gain in dB (–15 to +15).
        q:           New Q factor (0.1–10).
        filter_type: New filter type (0–7, see :class:`FilterType`).
        enabled:     Enable / disable this band.

    Returns:
        List of :class:`LOMCommand` (one per adjusted parameter).

    Raises:
        ValueError: If ``band`` is out of range or any value is invalid.
    """
    if not 1 <= band <= 8:
        raise ValueError(f"EQ Eight band must be 1–8, got {band}")

    idx = eq8_band_indices(band)
    cmds: list[LOMCommand] = []
    label = f"[{track.name}] EQ8 Band {band}"

    if freq_hz is not None:
        raw = eq8_freq_to_raw(freq_hz)
        cmds.append(_param_path_cmd(device, idx["freq"], raw, f"{label} freq → {freq_hz:.0f} Hz"))

    if gain_db is not None:
        raw = eq8_gain_to_raw(gain_db)
        cmds.append(_param_path_cmd(device, idx["gain"], raw, f"{label} gain → {gain_db:+.1f} dB"))

    if q is not None:
        raw = eq8_q_to_raw(q)
        cmds.append(_param_path_cmd(device, idx["q"], raw, f"{label} Q → {q:.2f}"))

    if filter_type is not None:
        if not 0 <= filter_type <= 7:
            raise ValueError(f"EQ Eight filter type must be 0–7, got {filter_type}")
        cmds.append(
            _param_path_cmd(
                device, idx["filter_type"], float(filter_type), f"{label} type → {filter_type}"
            )
        )

    if enabled is not None:
        cmds.append(
            _param_path_cmd(
                device,
                idx["active"],
                1.0 if enabled else 0.0,
                f"{label} {'enable' if enabled else 'disable'}",
            )
        )

    if not cmds:
        raise ValueError("set_eq_band() called with no parameters to change")

    return cmds


# ---------------------------------------------------------------------------
# Compressor commands
# ---------------------------------------------------------------------------


def set_compressor(
    track: Track,
    device: Device,
    *,
    threshold_db: float | None = None,
    ratio: float | None = None,
    attack_ms: float | None = None,
    release_ms: float | None = None,
    gain_db: float | None = None,
) -> list[LOMCommand]:
    """Generate commands to adjust a Compressor 2 or Glue Compressor.

    Args:
        track:        Parent track (for descriptions).
        device:       Compressor device.
        threshold_db: New threshold in dB (–60 to 0).
        ratio:        New ratio (raw 0–1; use device's own scale).
        attack_ms:    New attack in ms (0–200).
        release_ms:   New release in ms (1–10 000).
        gain_db:      New makeup gain in dB (0–35).

    Returns:
        List of :class:`LOMCommand`.
    """
    from core.ableton.session import find_parameter

    cmds: list[LOMCommand] = []
    label = f"[{track.name}] Compressor"

    if threshold_db is not None:
        raw = comp2_threshold_to_raw(threshold_db)
        p = find_parameter(device, "Threshold")
        cmds.append(_param_cmd(p, raw, f"{label} threshold → {threshold_db:.1f} dB"))

    if ratio is not None:
        # Ratio is stored differently per device; use raw 0-1 directly.
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"Compressor ratio must be raw 0–1, got {ratio}")
        p = find_parameter(device, "Ratio")
        cmds.append(_param_cmd(p, ratio, f"{label} ratio → {ratio:.2f} (raw)"))

    if attack_ms is not None:
        raw = comp2_attack_to_raw(attack_ms)
        p = find_parameter(device, "Attack")
        cmds.append(_param_cmd(p, raw, f"{label} attack → {attack_ms:.1f} ms"))

    if release_ms is not None:
        raw = comp2_release_to_raw(release_ms)
        p = find_parameter(device, "Release")
        cmds.append(_param_cmd(p, raw, f"{label} release → {release_ms:.0f} ms"))

    if gain_db is not None:
        raw = comp2_gain_to_raw(gain_db)
        p = find_parameter(device, "Gain")
        cmds.append(_param_cmd(p, raw, f"{label} makeup → {gain_db:.1f} dB"))

    if not cmds:
        raise ValueError("set_compressor() called with no parameters to change")

    return cmds


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------


def set_utility(
    track: Track,
    device: Device,
    *,
    width_pct: float | None = None,
    gain_db: float | None = None,
    mono: bool | None = None,
) -> list[LOMCommand]:
    """Generate commands to adjust a Utility device.

    Args:
        track:     Parent track.
        device:    Utility device (class_name == "StereoGain").
        width_pct: New stereo width in percent (0–400; 100 = normal stereo).
        gain_db:   New gain in dB (–35 to +35).
        mono:      Enable / disable mono summing.

    Returns:
        List of :class:`LOMCommand`.
    """
    from core.ableton.session import find_parameter

    cmds: list[LOMCommand] = []
    label = f"[{track.name}] Utility"

    if width_pct is not None:
        raw = utility_width_to_raw(width_pct)
        p = find_parameter(device, "Stereo Width")
        cmds.append(_param_cmd(p, raw, f"{label} width → {width_pct:.0f}%"))

    if gain_db is not None:
        raw = utility_gain_to_raw(gain_db)
        p = find_parameter(device, "Gain")
        cmds.append(_param_cmd(p, raw, f"{label} gain → {gain_db:+.1f} dB"))

    if mono is not None:
        p = find_parameter(device, "Mono")
        cmds.append(_param_cmd(p, 1.0 if mono else 0.0, f"{label} mono → {mono}"))

    if not cmds:
        raise ValueError("set_utility() called with no parameters to change")

    return cmds


# ---------------------------------------------------------------------------
# Track property commands
# ---------------------------------------------------------------------------


def mute_track(track: Track) -> LOMCommand:
    """Return a command to mute ``track``."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="mute",
        value=1,
        description=f"Mute [{track.name}]",
    )


def unmute_track(track: Track) -> LOMCommand:
    """Return a command to unmute ``track``."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="mute",
        value=0,
        description=f"Unmute [{track.name}]",
    )


def solo_track(track: Track) -> LOMCommand:
    """Return a command to solo ``track``."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="solo",
        value=1,
        description=f"Solo [{track.name}]",
    )


def unsolo_track(track: Track) -> LOMCommand:
    """Return a command to unsolo ``track``."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="solo",
        value=0,
        description=f"Unsolo [{track.name}]",
    )


def arm_track(track: Track) -> LOMCommand:
    """Return a command to arm ``track`` for recording."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="arm",
        value=1,
        description=f"Arm [{track.name}]",
    )


def disarm_track(track: Track) -> LOMCommand:
    """Return a command to disarm ``track``."""
    return LOMCommand(
        type="set_property",
        lom_path=track.lom_path,
        property="arm",
        value=0,
        description=f"Disarm [{track.name}]",
    )
