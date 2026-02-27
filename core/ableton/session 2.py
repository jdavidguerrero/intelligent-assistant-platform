"""core/ableton/session.py — Pure query helpers over :class:`SessionState`.

All functions are deterministic and take a ``SessionState`` (or sub-object)
as input.  Zero I/O, zero side effects, zero imports from db/ or api/.

Usage
─────
::

    session = bridge.get_session()          # ingestion layer
    track = find_track(session, "Pads")     # core layer
    eq = find_device(track, class_name="Eq8")
    band3 = get_eq_bands(eq)[2]             # 0-indexed list → band 3
"""

from __future__ import annotations

from core.ableton.device_maps import (
    CLASS_COMPRESSOR,
    COMPRESSOR_CLASS_NAMES,
    EQ_CLASS_NAMES,
    eq8_band_indices,
    eq8_raw_to_freq,
    eq8_raw_to_gain,
    eq8_raw_to_q,
)
from core.ableton.types import (
    Device,
    EQBand,
    FilterType,
    Parameter,
    SessionState,
    Track,
    TrackType,
)

# ---------------------------------------------------------------------------
# Track lookup
# ---------------------------------------------------------------------------


def find_track(session: SessionState, name_or_index: str | int) -> Track:
    """Return the first track matching ``name_or_index``.

    Searches ``session.tracks``, ``session.return_tracks``, and
    ``session.master_track`` in that order.

    Args:
        session:       Full session snapshot.
        name_or_index: Track name (case-insensitive substring match) or
                       0-based integer index into ``session.tracks``.

    Returns:
        Matching :class:`Track`.

    Raises:
        ValueError: If no track matches.
    """
    all_tracks: list[Track] = list(session.tracks) + list(session.return_tracks)
    if session.master_track is not None:
        all_tracks.append(session.master_track)

    if isinstance(name_or_index, int):
        if 0 <= name_or_index < len(session.tracks):
            return session.tracks[name_or_index]
        raise ValueError(
            f"Track index {name_or_index} out of range (session has {len(session.tracks)} tracks)"
        )

    needle = name_or_index.lower()
    # 1. Exact match first
    for t in all_tracks:
        if t.name.lower() == needle:
            return t
    # 2. Substring match
    for t in all_tracks:
        if needle in t.name.lower():
            return t

    track_names = [t.name for t in all_tracks]
    raise ValueError(f"No track matching {name_or_index!r}.  Available: {track_names}")


def find_track_by_type(session: SessionState, track_type: TrackType) -> list[Track]:
    """Return all tracks of the given type.

    Args:
        session:    Full session snapshot.
        track_type: :class:`TrackType` enum value.

    Returns:
        List of matching tracks (may be empty).
    """
    return [t for t in (*session.tracks, *session.return_tracks) if t.type == track_type]


# ---------------------------------------------------------------------------
# Device lookup
# ---------------------------------------------------------------------------


def find_device(
    track: Track,
    *,
    name: str | None = None,
    class_name: str | None = None,
) -> Device:
    """Return the first device on ``track`` matching ``name`` or ``class_name``.

    At least one of ``name`` or ``class_name`` must be provided.

    Args:
        track:      Parent track.
        name:       Case-insensitive substring match against device display name.
        class_name: Exact match against ``device.class_name`` (preferred — stable
                    across sessions regardless of user renaming).

    Returns:
        Matching :class:`Device`.

    Raises:
        ValueError: If no device matches or no search criterion given.
    """
    if name is None and class_name is None:
        raise ValueError("Provide at least one of name= or class_name=")

    for device in track.devices:
        if class_name is not None and device.class_name == class_name:
            return device
        if name is not None and name.lower() in device.name.lower():
            return device

    candidates = [(d.name, d.class_name) for d in track.devices]
    raise ValueError(
        f"No device matching name={name!r} / class_name={class_name!r} on track {track.name!r}.  "
        f"Devices: {candidates}"
    )


def find_eq(track: Track) -> Device:
    """Return the first EQ Eight (or Auto Eq) on ``track``.

    Shortcut for :func:`find_device` with ``class_name`` in :data:`EQ_CLASS_NAMES`.

    Raises:
        ValueError: If no EQ device is present.
    """
    for device in track.devices:
        if device.class_name in EQ_CLASS_NAMES:
            return device
    raise ValueError(f"No EQ device found on track {track.name!r}")


def find_compressor(track: Track) -> Device:
    """Return the first Compressor 2 or Glue Compressor on ``track``.

    Raises:
        ValueError: If no compressor is present.
    """
    for device in track.devices:
        if device.class_name in COMPRESSOR_CLASS_NAMES:
            return device
    raise ValueError(f"No compressor found on track {track.name!r}")


# ---------------------------------------------------------------------------
# Parameter lookup
# ---------------------------------------------------------------------------


def find_parameter(device: Device, param_name: str) -> Parameter:
    """Return the first parameter matching ``param_name`` (case-insensitive).

    Args:
        device:     Parent device.
        param_name: Display name (or case-insensitive prefix/substring).

    Returns:
        Matching :class:`Parameter`.

    Raises:
        ValueError: If not found.
    """
    needle = param_name.lower()
    # Exact
    for p in device.parameters:
        if p.name.lower() == needle:
            return p
    # Substring
    for p in device.parameters:
        if needle in p.name.lower():
            return p
    param_names = [p.name for p in device.parameters]
    raise ValueError(
        f"Parameter {param_name!r} not found in device {device.name!r}.  "
        f"Parameters: {param_names}"
    )


def get_parameter_by_index(device: Device, index: int) -> Parameter:
    """Return device parameter at ``index`` (0-based).

    Raises:
        ValueError: If index is out of range.
    """
    if not 0 <= index < len(device.parameters):
        raise ValueError(
            f"Parameter index {index} out of range for device {device.name!r} "
            f"(has {len(device.parameters)} parameters)"
        )
    return device.parameters[index]


# ---------------------------------------------------------------------------
# EQ Eight band helpers
# ---------------------------------------------------------------------------


def get_eq_bands(device: Device) -> list[EQBand]:
    """Parse an EQ Eight device's parameters into a list of :class:`EQBand`.

    Returns 8 bands (band 1 = Band A … band 8 = Band H).  Bands whose
    ``ParameterIsActive`` parameter is missing default to ``enabled=True``.

    Args:
        device: Must be an EQ Eight (``class_name == "Eq8"``).

    Returns:
        List of 8 :class:`EQBand` in order A → H.

    Raises:
        ValueError: If ``device`` does not look like an EQ Eight.
    """
    if device.class_name not in EQ_CLASS_NAMES:
        raise ValueError(
            f"get_eq_bands() requires an EQ Eight device, got class_name={device.class_name!r}"
        )

    params = device.parameters
    if len(params) < 42:
        raise ValueError(
            f"EQ Eight should have 42 parameters, device {device.name!r} has {len(params)}"
        )

    bands: list[EQBand] = []
    for band_n in range(1, 9):
        idx = eq8_band_indices(band_n)
        freq_raw = params[idx["freq"]].value
        gain_raw = params[idx["gain"]].value
        q_raw = params[idx["q"]].value
        type_raw = int(params[idx["filter_type"]].value)
        active_raw = params[idx["active"]].value if idx["active"] < len(params) else 1.0

        bands.append(
            EQBand(
                band=band_n,
                freq_hz=eq8_raw_to_freq(freq_raw),
                gain_db=eq8_raw_to_gain(gain_raw),
                q=eq8_raw_to_q(q_raw),
                filter_type=FilterType(type_raw),
                enabled=bool(active_raw),
            )
        )
    return bands


# ---------------------------------------------------------------------------
# Compressor parameter helpers
# ---------------------------------------------------------------------------


class CompressorSettings:
    """Snapshot of a compressor's key parameters in human units."""

    __slots__ = (
        "threshold_db",
        "ratio",
        "attack_ms",
        "release_ms",
        "gain_db",
        "knee_db",
        "dry_wet",
    )

    def __init__(
        self,
        threshold_db: float,
        ratio: float,
        attack_ms: float,
        release_ms: float,
        gain_db: float,
        knee_db: float = 0.0,
        dry_wet: float = 1.0,
    ) -> None:
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.gain_db = gain_db
        self.knee_db = knee_db
        self.dry_wet = dry_wet

    def __repr__(self) -> str:
        return (
            f"CompressorSettings(threshold={self.threshold_db:.1f}dB, "
            f"ratio={self.ratio:.1f}:1, "
            f"attack={self.attack_ms:.1f}ms, "
            f"release={self.release_ms:.0f}ms, "
            f"gain={self.gain_db:.1f}dB)"
        )


def get_compressor_params(device: Device) -> CompressorSettings:
    """Extract key compressor parameters from an Ableton Compressor 2 or Glue Compressor device.

    The LOM stores compressor parameters in display units (dB, ms, ratio) for
    these devices — not raw 0–1.  This function reads ``display_value`` strings
    and ``value`` fields as appropriate.

    Args:
        device: A Compressor 2 or Glue Compressor device.

    Returns:
        :class:`CompressorSettings` with threshold, ratio, attack, release, gain.

    Raises:
        ValueError: If ``device.class_name`` is not a recognised compressor class.
    """
    if device.class_name not in COMPRESSOR_CLASS_NAMES:
        raise ValueError(
            f"get_compressor_params() requires a compressor, got {device.class_name!r}"
        )

    def _get(name: str, default: float = 0.0) -> float:
        try:
            p = find_parameter(device, name)
            return float(p.value)
        except ValueError:
            return default

    return CompressorSettings(
        threshold_db=_get("Threshold", -20.0),
        ratio=_get("Ratio", 4.0),
        attack_ms=_get("Attack", 10.0),
        release_ms=_get("Release", 100.0),
        gain_db=_get("Gain", 0.0),
        knee_db=_get("Knee", 0.0)
        if device.class_name == CLASS_COMPRESSOR
        else _get("Soft Knee", 0.0),
        dry_wet=_get("Dry/Wet", 1.0),
    )


# ---------------------------------------------------------------------------
# Session summary helper
# ---------------------------------------------------------------------------


def session_summary(session: SessionState) -> dict:
    """Return a compact summary dict suitable for MCP tool responses.

    Keys:
        tracks:         List of {name, type, index, device_count, device_names}.
        return_tracks:  Same format.
        tempo:          BPM (float).
        is_playing:     bool.
        track_count:    int.
    """

    def _track_info(t: Track) -> dict:
        return {
            "name": t.name,
            "type": t.type.value,
            "index": t.index,
            "mute": t.mute,
            "solo": t.solo,
            "arm": t.arm,
            "volume_db": round(t.volume_db, 1),
            "device_count": len(t.devices),
            "device_names": [d.name for d in t.devices],
        }

    return {
        "track_count": len(session.tracks),
        "tracks": [_track_info(t) for t in session.tracks],
        "return_tracks": [_track_info(t) for t in session.return_tracks],
        "tempo": session.tempo,
        "time_signature": f"{session.time_sig_numerator}/{session.time_sig_denominator}",
        "is_playing": session.is_playing,
        "scene_count": session.scene_count,
    }
