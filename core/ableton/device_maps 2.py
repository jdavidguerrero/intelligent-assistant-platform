"""core/ableton/device_maps.py — Parameter layouts for Ableton's built-in devices.

Each device map provides:

1. ``PARAM_INDICES`` — 0-based indices into the device's ``parameters`` list
   for named parameters.  Index-based lookup is more reliable than name
   matching because parameter names change with locale.

2. ``from_raw / to_raw`` helpers — convert between human-readable units
   (Hz, dB, ms, %) and Ableton's internal 0–1 raw values.

3. ``DeviceMap`` protocol — a typed dict describing per-parameter metadata.

Supported devices
─────────────────
* EQ Eight          (class_name: ``"Eq8"``)
* Compressor 2      (class_name: ``"Compressor2"``)
* Glue Compressor   (class_name: ``"GlueCompressor"``)
* Utility           (class_name: ``"StereoGain"``)
* Auto Filter       (class_name: ``"AutoFilter"``)
* Saturator         (class_name: ``"Saturator"``)

All value-range constants are from Ableton Live 11.x (confirmed with LOM
introspection).  Ranges may change in major Live versions; always validate
against the ``min_value``/``max_value`` reported by the LOM at runtime.

Pure module — no I/O, no env vars, no imports from other project layers.
"""

from __future__ import annotations

import math
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Value conversion helpers
# ---------------------------------------------------------------------------


def _log_to_raw(value: float, min_val: float, max_val: float) -> float:
    """Map a log-scale human value → Ableton 0–1 raw.

    Ableton stores frequency and Q parameters using::

        raw = log10(value / min_val) / log10(max_val / min_val)
    """
    if value <= 0 or min_val <= 0 or max_val <= 0:
        raise ValueError(f"log_to_raw requires positive values, got {value}, {min_val}, {max_val}")
    return math.log10(value / min_val) / math.log10(max_val / min_val)


def _raw_to_log(raw: float, min_val: float, max_val: float) -> float:
    """Map an Ableton 0–1 raw → log-scale human value."""
    return min_val * (max_val / min_val) ** raw


def _lin_to_raw(value: float, min_val: float, max_val: float) -> float:
    """Map a linear human value → Ableton 0–1 raw."""
    return (value - min_val) / (max_val - min_val)


def _raw_to_lin(raw: float, min_val: float, max_val: float) -> float:
    """Map an Ableton 0–1 raw → linear human value."""
    return min_val + raw * (max_val - min_val)


# ---------------------------------------------------------------------------
# EQ Eight (class_name: "Eq8")
# ---------------------------------------------------------------------------
# Parameter layout (42 total):
#   Index 0:  Device On
#   Index 1:  Scale (output gain  –12 … +12 dB, linear, raw: 0–1)
#   Bands 1–8 (5 parameters each, starting at index 2):
#     2 + (band-1)*5 + 0 : Frequency  (20 – 20 000 Hz, log)
#     2 + (band-1)*5 + 1 : Gain       (–15 … +15 dB, linear)
#     2 + (band-1)*5 + 2 : Q          (0.1 – 10, log)
#     2 + (band-1)*5 + 3 : Filter Type (0 = LP48 … 7 = HP48, quantized)
#     2 + (band-1)*5 + 4 : ParameterIsActive (0 or 1, quantized)
# ---------------------------------------------------------------------------

EQ8_FREQ_MIN: float = 20.0
EQ8_FREQ_MAX: float = 20_000.0
EQ8_GAIN_MIN: float = -15.0
EQ8_GAIN_MAX: float = 15.0
EQ8_Q_MIN: float = 0.1
EQ8_Q_MAX: float = 10.0


def eq8_band_indices(band: int) -> dict[str, int]:
    """Return parameter indices for EQ Eight band N (1-based, 1–8).

    >>> eq8_band_indices(3)
    {'freq': 12, 'gain': 13, 'q': 14, 'filter_type': 15, 'active': 16}
    """
    if not 1 <= band <= 8:
        raise ValueError(f"EQ Eight band must be 1–8, got {band}")
    base = 2 + (band - 1) * 5
    return {
        "freq": base,
        "gain": base + 1,
        "q": base + 2,
        "filter_type": base + 3,
        "active": base + 4,
    }


def eq8_freq_to_raw(freq_hz: float) -> float:
    """Convert Hz → EQ Eight raw frequency value (0–1).

    >>> round(eq8_freq_to_raw(1000.0), 4)
    0.5
    """
    if freq_hz < EQ8_FREQ_MIN or freq_hz > EQ8_FREQ_MAX:
        raise ValueError(
            f"EQ Eight frequency must be {EQ8_FREQ_MIN}–{EQ8_FREQ_MAX} Hz, got {freq_hz}"
        )
    return _log_to_raw(freq_hz, EQ8_FREQ_MIN, EQ8_FREQ_MAX)


def eq8_raw_to_freq(raw: float) -> float:
    """Convert EQ Eight raw value (0–1) → Hz."""
    return _raw_to_log(raw, EQ8_FREQ_MIN, EQ8_FREQ_MAX)


def eq8_gain_to_raw(gain_db: float) -> float:
    """Convert dB gain → EQ Eight raw value (0–1).  0 dB = 0.5 raw.

    >>> eq8_gain_to_raw(0.0)
    0.5
    """
    if gain_db < EQ8_GAIN_MIN or gain_db > EQ8_GAIN_MAX:
        raise ValueError(f"EQ Eight gain must be {EQ8_GAIN_MIN}–{EQ8_GAIN_MAX} dB, got {gain_db}")
    return _lin_to_raw(gain_db, EQ8_GAIN_MIN, EQ8_GAIN_MAX)


def eq8_raw_to_gain(raw: float) -> float:
    """Convert EQ Eight raw value (0–1) → dB gain."""
    return _raw_to_lin(raw, EQ8_GAIN_MIN, EQ8_GAIN_MAX)


def eq8_q_to_raw(q: float) -> float:
    """Convert Q → EQ Eight raw value (0–1).

    >>> round(eq8_q_to_raw(1.0), 4)
    0.5
    """
    if q < EQ8_Q_MIN or q > EQ8_Q_MAX:
        raise ValueError(f"EQ Eight Q must be {EQ8_Q_MIN}–{EQ8_Q_MAX}, got {q}")
    return _log_to_raw(q, EQ8_Q_MIN, EQ8_Q_MAX)


def eq8_raw_to_q(raw: float) -> float:
    """Convert EQ Eight raw value (0–1) → Q."""
    return _raw_to_log(raw, EQ8_Q_MIN, EQ8_Q_MAX)


# ---------------------------------------------------------------------------
# Compressor 2 (class_name: "Compressor2")
# ---------------------------------------------------------------------------
# Key parameters (indices may vary by version — match by name if index fails):
#   "Threshold"   –60 … 0 dB     (linear in dB: raw = (thresh+60)/60)
#   "Ratio"        1 … ∞:1       (special mapping; raw 0–1 ≈ ratio 1:1 – ∞:1)
#   "Attack"       0 … 200 ms    (log scale)
#   "Release"      1 … 10 000 ms (log scale)
#   "Gain"         0 … 35 dB     (linear)
#   "Knee"         0 … 6 dB      (linear)
# ---------------------------------------------------------------------------

COMP2_THRESHOLD_MIN: float = -60.0
COMP2_THRESHOLD_MAX: float = 0.0
COMP2_ATTACK_MIN: float = 0.0  # ms
COMP2_ATTACK_MAX: float = 200.0  # ms
COMP2_RELEASE_MIN: float = 1.0  # ms
COMP2_RELEASE_MAX: float = 10_000.0  # ms
COMP2_GAIN_MIN: float = 0.0  # dB
COMP2_GAIN_MAX: float = 35.0  # dB
COMP2_KNEE_MIN: float = 0.0  # dB
COMP2_KNEE_MAX: float = 6.0  # dB

COMP2_PARAM_NAMES: dict[str, str] = {
    "threshold": "Threshold",
    "ratio": "Ratio",
    "attack": "Attack",
    "release": "Release",
    "gain": "Gain",
    "knee": "Knee",
    "dry_wet": "Dry/Wet",
    "model": "Model",
    "lookahead": "Lookahead",
}


def comp2_threshold_to_raw(threshold_db: float) -> float:
    """Convert dB threshold → Compressor 2 raw (0–1)."""
    if threshold_db < COMP2_THRESHOLD_MIN or threshold_db > COMP2_THRESHOLD_MAX:
        raise ValueError(
            f"Compressor threshold must be {COMP2_THRESHOLD_MIN}–{COMP2_THRESHOLD_MAX} dB, got {threshold_db}"
        )
    return _lin_to_raw(threshold_db, COMP2_THRESHOLD_MIN, COMP2_THRESHOLD_MAX)


def comp2_attack_to_raw(attack_ms: float) -> float:
    """Convert ms attack → Compressor 2 raw (0–1), log scale."""
    if attack_ms < 0 or attack_ms > COMP2_ATTACK_MAX:
        raise ValueError(f"Attack must be 0–{COMP2_ATTACK_MAX} ms, got {attack_ms}")
    # Attack 0 ms is a special case (raw = 0)
    if attack_ms == 0:
        return 0.0
    return _log_to_raw(max(attack_ms, 0.01), 0.01, COMP2_ATTACK_MAX)


def comp2_release_to_raw(release_ms: float) -> float:
    """Convert ms release → Compressor 2 raw (0–1), log scale."""
    if release_ms < COMP2_RELEASE_MIN or release_ms > COMP2_RELEASE_MAX:
        raise ValueError(
            f"Release must be {COMP2_RELEASE_MIN}–{COMP2_RELEASE_MAX} ms, got {release_ms}"
        )
    return _log_to_raw(release_ms, COMP2_RELEASE_MIN, COMP2_RELEASE_MAX)


def comp2_gain_to_raw(gain_db: float) -> float:
    """Convert dB makeup gain → Compressor 2 raw (0–1)."""
    if gain_db < COMP2_GAIN_MIN or gain_db > COMP2_GAIN_MAX:
        raise ValueError(f"Makeup gain must be {COMP2_GAIN_MIN}–{COMP2_GAIN_MAX} dB, got {gain_db}")
    return _lin_to_raw(gain_db, COMP2_GAIN_MIN, COMP2_GAIN_MAX)


# ---------------------------------------------------------------------------
# Glue Compressor (class_name: "GlueCompressor")
# ---------------------------------------------------------------------------

GLUE_PARAM_NAMES: dict[str, str] = {
    "threshold": "Threshold",
    "ratio": "Ratio",
    "attack": "Attack",
    "release": "Release",
    "gain": "Gain",
    "soft_knee": "Soft Knee",
    "range": "Range",
    "dry_wet": "Dry/Wet",
}

# Same threshold range as Compressor 2
GLUE_THRESHOLD_MIN: float = -60.0
GLUE_THRESHOLD_MAX: float = 0.0


def glue_threshold_to_raw(threshold_db: float) -> float:
    """Convert dB threshold → Glue Compressor raw (0–1)."""
    if threshold_db < GLUE_THRESHOLD_MIN or threshold_db > GLUE_THRESHOLD_MAX:
        raise ValueError(
            f"Glue threshold must be {GLUE_THRESHOLD_MIN}–{GLUE_THRESHOLD_MAX} dB, got {threshold_db}"
        )
    return _lin_to_raw(threshold_db, GLUE_THRESHOLD_MIN, GLUE_THRESHOLD_MAX)


# ---------------------------------------------------------------------------
# Utility (class_name: "StereoGain")
# ---------------------------------------------------------------------------

UTILITY_GAIN_MIN: float = -35.0  # dB
UTILITY_GAIN_MAX: float = 35.0  # dB
UTILITY_WIDTH_MIN: float = 0.0  # % (0 = mono)
UTILITY_WIDTH_MAX: float = 400.0  # %

UTILITY_PARAM_NAMES: dict[str, str] = {
    "gain": "Gain",
    "width": "Stereo Width",
    "mono": "Mono",
    "phase_l": "Phase Invert L",
    "phase_r": "Phase Invert R",
    "channel_mode": "Channel Mode",
    "dc_filter": "DC Filter",
}


def utility_gain_to_raw(gain_db: float) -> float:
    """Convert dB gain → Utility raw (0–1)."""
    if gain_db < UTILITY_GAIN_MIN or gain_db > UTILITY_GAIN_MAX:
        raise ValueError(
            f"Utility gain must be {UTILITY_GAIN_MIN}–{UTILITY_GAIN_MAX} dB, got {gain_db}"
        )
    return _lin_to_raw(gain_db, UTILITY_GAIN_MIN, UTILITY_GAIN_MAX)


def utility_width_to_raw(width_pct: float) -> float:
    """Convert stereo width % → Utility raw (0–1).

    100% = normal stereo.  0% = mono.  200% = exaggerated stereo.
    """
    if width_pct < UTILITY_WIDTH_MIN or width_pct > UTILITY_WIDTH_MAX:
        raise ValueError(
            f"Utility width must be {UTILITY_WIDTH_MIN}–{UTILITY_WIDTH_MAX}%, got {width_pct}"
        )
    return _lin_to_raw(width_pct, UTILITY_WIDTH_MIN, UTILITY_WIDTH_MAX)


def utility_raw_to_width(raw: float) -> float:
    """Convert Utility raw (0–1) → stereo width %."""
    return _raw_to_lin(raw, UTILITY_WIDTH_MIN, UTILITY_WIDTH_MAX)


# ---------------------------------------------------------------------------
# Auto Filter (class_name: "AutoFilter")
# ---------------------------------------------------------------------------

AF_FREQ_MIN: float = 13.0
AF_FREQ_MAX: float = 21_700.0
AF_RES_MIN: float = 0.0
AF_RES_MAX: float = 4.0

AF_PARAM_NAMES: dict[str, str] = {
    "frequency": "Frequency",
    "resonance": "Resonance",
    "filter_type": "Filter Type",
    "slope": "Slope",
    "drive": "Drive",
    "dry_wet": "Dry/Wet",
}


def af_freq_to_raw(freq_hz: float) -> float:
    """Convert Hz → Auto Filter raw (0–1, log scale)."""
    if freq_hz < AF_FREQ_MIN or freq_hz > AF_FREQ_MAX:
        raise ValueError(
            f"Auto Filter frequency must be {AF_FREQ_MIN}–{AF_FREQ_MAX} Hz, got {freq_hz}"
        )
    return _log_to_raw(freq_hz, AF_FREQ_MIN, AF_FREQ_MAX)


# ---------------------------------------------------------------------------
# Saturator (class_name: "Saturator")
# ---------------------------------------------------------------------------

SAT_PARAM_NAMES: dict[str, str] = {
    "drive": "Drive",
    "type": "Shaper Type",
    "output": "Output",
    "dry_wet": "Dry/Wet",
    "color": "Color",
}


# ---------------------------------------------------------------------------
# Registry: class_name → parameter-name dict
# ---------------------------------------------------------------------------

DEVICE_PARAM_NAMES: dict[str, dict[str, str]] = {
    "Eq8": {
        f"band_{n}_{k}": v
        for n in range(1, 9)
        for k, v in {
            "freq": f"EqFrequency{n}",
            "gain": f"EqGain{n}",
            "q": f"EqQ{n}",
            "type": f"FilterType{n}",
            "active": f"ParameterIsActive{n}",
        }.items()
    },
    "Compressor2": COMP2_PARAM_NAMES,
    "GlueCompressor": GLUE_PARAM_NAMES,
    "StereoGain": UTILITY_PARAM_NAMES,
    "AutoFilter": AF_PARAM_NAMES,
    "Saturator": SAT_PARAM_NAMES,
}


# ---------------------------------------------------------------------------
# ParameterSpec — metadata for a single parameter in a known device
# ---------------------------------------------------------------------------


class ParameterSpec(NamedTuple):
    """Specification for a single parameter in a known device."""

    display_name: str
    """Human-readable name as shown in the Ableton UI."""

    min_value: float
    """Minimum value in human units (Hz, dB, ms, etc.)."""

    max_value: float
    """Maximum value in human units."""

    unit: str
    """Unit label, e.g. ``"Hz"``, ``"dB"``, ``"ms"``."""

    to_raw: object  # Callable[[float], float]
    """Convert human value → Ableton raw 0–1."""

    from_raw: object  # Callable[[float], float]
    """Convert Ableton raw 0–1 → human value."""

    is_log: bool = False
    """Whether the parameter uses logarithmic mapping."""


# EQ Eight per-band spec table (bands 1-8)
def eq8_band_specs(band: int) -> dict[str, ParameterSpec]:
    """Return :class:`ParameterSpec` for each parameter of EQ Eight band N."""
    if not 1 <= band <= 8:
        raise ValueError(f"EQ Eight band must be 1–8, got {band}")
    return {
        "freq": ParameterSpec(
            f"Band {band} Frequency",
            EQ8_FREQ_MIN,
            EQ8_FREQ_MAX,
            "Hz",
            eq8_freq_to_raw,
            eq8_raw_to_freq,
            is_log=True,
        ),
        "gain": ParameterSpec(
            f"Band {band} Gain",
            EQ8_GAIN_MIN,
            EQ8_GAIN_MAX,
            "dB",
            eq8_gain_to_raw,
            eq8_raw_to_gain,
        ),
        "q": ParameterSpec(
            f"Band {band} Q",
            EQ8_Q_MIN,
            EQ8_Q_MAX,
            "",
            eq8_q_to_raw,
            eq8_raw_to_q,
            is_log=True,
        ),
    }


# ---------------------------------------------------------------------------
# Known class names (use for isinstance/type checks in session.py)
# ---------------------------------------------------------------------------

CLASS_EQ8: str = "Eq8"
CLASS_COMPRESSOR: str = "Compressor2"
CLASS_GLUE: str = "GlueCompressor"
CLASS_UTILITY: str = "StereoGain"
CLASS_AUTOFILTER: str = "AutoFilter"
CLASS_SATURATOR: str = "Saturator"
CLASS_SIMPLER: str = "OriginalSimpler"
CLASS_REVERB: str = "Reverb"
CLASS_DELAY: str = "StereoDelay"

EQ_CLASS_NAMES: frozenset[str] = frozenset({CLASS_EQ8, "AutoEq"})
COMPRESSOR_CLASS_NAMES: frozenset[str] = frozenset({CLASS_COMPRESSOR, CLASS_GLUE})
