"""core/ableton/types.py — Immutable value objects for Ableton Live session state.

Hierarchy mirroring the Live Object Model (LOM):

    SessionState
    └── Track (N tracks + return tracks)
        ├── Device (M devices per track)
        │   └── Parameter (P params per device)
        └── Clip (K clips per track)

Every type is a frozen dataclass.  No I/O, no timestamps, no env vars.

LOM path format examples
────────────────────────
Track 2, device 1, parameter 3:
    live_set tracks 2 devices 1 parameters 3

Return track 0, device 0:
    live_set return_tracks 0 devices 0

Master track:
    live_set master_track

Clip slot 4 on track 1:
    live_set tracks 1 clip_slots 4 clip
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TrackType(str, Enum):
    """Ableton track types as returned by the LOM ``track.type`` property."""

    AUDIO = "audio"
    MIDI = "midi"
    RETURN = "return"
    MASTER = "master"
    GROUP = "group"


class FilterType(int, Enum):
    """EQ Eight filter-type indices (0-based, as stored in the LOM)."""

    LP_48 = 0  # Low-pass 48 dB/oct
    LP_12 = 1  # Low-pass 12 dB/oct
    LOW_SHELF = 2  # Low shelf
    BELL = 3  # Bell / peaking
    NOTCH = 4  # Notch
    HIGH_SHELF = 5  # High shelf
    HP_12 = 6  # High-pass 12 dB/oct
    HP_48 = 7  # High-pass 48 dB/oct


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Parameter:
    """A single device parameter as read from the LOM.

    ``value``, ``min_value``, ``max_value`` are the raw 0–1 values stored by
    Ableton internally.  Use :mod:`core.ableton.device_maps` to convert them
    to human-readable units (Hz, dB, etc.).
    """

    name: str
    """Display name returned by ``live.object.get 'name'``."""

    value: float
    """Current raw value (0.0 – 1.0 for most parameters, int for quantized)."""

    min_value: float
    """Minimum raw value reported by the LOM."""

    max_value: float
    """Maximum raw value reported by the LOM."""

    default_value: float
    """Default raw value."""

    display_value: str
    """Human-readable value string returned by ``live.object.get 'str_for_value'``."""

    lom_path: str
    """Full LOM path to this parameter, e.g. ``live_set tracks 0 devices 1 parameters 3``."""

    index: int = 0
    """0-based parameter index within its parent device's parameters list."""

    is_quantized: bool = False
    """True for discrete/integer parameters (filter type, model selector, etc.)."""


# ---------------------------------------------------------------------------
# EQ Band helper  (synthesised from EQ8 parameter groups)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EQBand:
    """Human-readable representation of one EQ Eight band.

    Derived from :func:`core.ableton.session.get_eq_bands`; not read directly
    from the LOM (LOM stores raw 0-1 values).
    """

    band: int
    """1-based band number (1 = Band A … 8 = Band H)."""

    freq_hz: float
    """Centre/corner frequency in Hertz."""

    gain_db: float
    """Gain in dB (–15 to +15).  0 for LP/HP/notch types."""

    q: float
    """Quality factor (0.1 – 10 for Bell; not meaningful for LP/HP)."""

    filter_type: FilterType
    """Filter topology."""

    enabled: bool
    """Whether this band is active (ParameterIsActive)."""


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Device:
    """An Ableton device loaded on a track.

    ``class_name`` is the internal class identifier (e.g. ``"OriginalSimpler"``,
    ``"Compressor2"``, ``"AutoEq"``).  Unlike ``name`` (which the user can
    rename), ``class_name`` is stable across sessions and is the reliable key
    for device-map lookups.
    """

    name: str
    """User-visible name (can be renamed by the user)."""

    class_name: str
    """Stable internal class name used for device-map lookups."""

    is_active: bool
    """Whether the device is enabled (not bypassed)."""

    parameters: tuple[Parameter, ...]
    """Ordered parameter list — index matches LOM parameter index."""

    lom_path: str
    """Full LOM path, e.g. ``live_set tracks 2 devices 1``."""

    index: int = 0
    """0-based device index within its parent track's devices list."""


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    """An Ableton clip (audio or MIDI).

    ``notes`` is populated only for MIDI clips and only when the scanner is
    asked for deep scan mode.  Each note is a dict::

        {"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 100}
    """

    name: str
    length_bars: float
    is_playing: bool
    is_triggered: bool
    is_midi: bool
    lom_path: str
    color: int = 0
    notes: tuple[dict, ...] = field(default_factory=tuple)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    """An Ableton track (audio, MIDI, return, or master).

    ``volume_db`` is already converted to dB; ``pan`` is in range –1.0 to +1.0.
    The raw LOM values (0–1 for volume, 0–1 for pan) are converted by the
    scanner in ``ingestion/ableton_bridge.py``.
    """

    name: str
    index: int
    type: TrackType
    arm: bool
    solo: bool
    mute: bool
    volume_db: float
    """Track volume in dB (–∞ to +6 dB; 0 dB = raw LOM value 0.8499)."""

    pan: float
    """Track pan in range [–1.0 (full left) … +1.0 (full right)].  Centre = 0."""

    devices: tuple[Device, ...]
    clips: tuple[Clip, ...]
    lom_path: str
    color: int = 0


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionState:
    """Full snapshot of an Ableton Live session.

    Populated by the ALS Listener M4L device via the WebSocket bridge and
    deserialised in :mod:`ingestion.ableton_bridge`.  This object is pure data
    — no methods that touch I/O.

    ``tracks`` contains only regular tracks (audio + MIDI + group).
    ``return_tracks`` contains return/send tracks.
    ``master_track`` is the master bus.
    """

    tracks: tuple[Track, ...]
    return_tracks: tuple[Track, ...]
    master_track: Track | None

    tempo: float
    """Session tempo in BPM."""

    time_sig_numerator: int
    time_sig_denominator: int
    is_playing: bool
    current_song_time: float
    """Current playhead position in beats."""

    scene_count: int
    timestamp: float = 0.0
    """Unix timestamp (seconds) of when this snapshot was taken."""


# ---------------------------------------------------------------------------
# LOM Command  (used by commands.py → ingestion/ableton_bridge.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LOMCommand:
    """A single write operation to be forwarded to the ALS Listener.

    The WebSocket protocol sends commands as JSON::

        {
            "type": "set_parameter",
            "lom_path": "live_set tracks 2 devices 1 parameters 5",
            "property": "value",
            "value": 0.72
        }
    """

    type: str
    """Command type: ``"set_parameter"`` | ``"set_property"`` | ``"call_method"``."""

    lom_path: str
    """Target LOM path."""

    property: str
    """Property name to set (usually ``"value"``)."""

    value: float | int | str
    """New value to assign."""

    description: str = ""
    """Human-readable description for logging and debugging."""

    def to_dict(self) -> dict:
        """Serialise to the WebSocket wire format."""
        return {
            "type": self.type,
            "lom_path": self.lom_path,
            "property": self.property,
            "value": self.value,
        }
