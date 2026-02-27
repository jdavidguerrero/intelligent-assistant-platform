"""
ableton_bridge/auto_setup.py — Rack loading + parameter-setting orchestrator.

Translates per-stem analysis + problem attribution into concrete Ableton
control commands, then applies them via the ALS Listener WebSocket.

Pipeline
========
1. For each stem in the session:
   a. Select the appropriate processing chain (kick_chain, bass_chain, etc.)
      based on stem type detection.
   b. Build SetupAction objects describing which parameters to change.
2. Show the user a preview list of SetupAction (with checkboxes in the UI).
3. User approves → apply_setup_actions() fires the commands over WebSocket.
4. Return SetupResult with per-action status.

Rack presets
============
The Rack presets (.adg files) must be placed at:
    ableton_bridge/rack_presets/mixing/<name>.adg
    ableton_bridge/rack_presets/bus/<name>.adg
    ableton_bridge/rack_presets/mastering/<name>.adg

Loading a preset uses the 'load_device' LOM method (requires Ableton 11.1+).
If loading fails the orchestrator falls back to direct parameter setting on
existing devices.

Parameter mapping
=================
Uses core/ableton/device_maps.py for parameter name → index lookups.
EQ Eight bands are numbered 1–8; compressor/utility use named params.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.mix_analysis.attribution import StemContribution, VolumeBalanceSuggestion
from core.mix_analysis.stems import StemFootprint, StemType

_WS_HOST = "localhost"
_WS_PORT = 11005
_TIMEOUT_SEC = 10.0

# Path to rack presets relative to project root
_RACK_DIR = Path(__file__).parent / "rack_presets"

# Stem type → mixing chain preset filename
_CHAIN_FOR_TYPE: dict[StemType, str] = {
    StemType.kick: "kick_chain",
    StemType.bass: "bass_chain",
    StemType.pad: "melodic_chain",
    StemType.percussion: "percussion_chain",
    StemType.vocal: "melodic_chain",
    StemType.fx: "fx_chain",
    StemType.unknown: "melodic_chain",
}

# EQ band index for frequency ranges (1-based, Ableton EQ Eight)
_FREQ_TO_EQ_BAND: list[tuple[float, float, int]] = [
    # (min_hz, max_hz, band_index)
    (20.0, 80.0, 1),
    (80.0, 300.0, 2),
    (300.0, 700.0, 3),
    (700.0, 2000.0, 4),
    (2000.0, 5000.0, 5),
    (5000.0, 10000.0, 6),
    (10000.0, 20000.0, 7),
]


def _band_for_freq(freq_hz: float) -> int:
    for lo, hi, band in _FREQ_TO_EQ_BAND:
        if lo <= freq_hz < hi:
            return band
    return 4  # default to mid band


ProgressCallback = Callable[[int, int, str, str], None]


def _noop(current: int, total: int, track: str, status: str) -> None:
    pass


# ---------------------------------------------------------------------------
# SetupAction
# ---------------------------------------------------------------------------


@dataclass
class SetupAction:
    """One atomic setup action on one track's device parameter.

    Fields:
        track_name:     Ableton track name.
        track_index:    0-based track index.
        action_type:    'set_parameter' | 'set_property' | 'load_rack'.
        device_name:    Human-readable device name (e.g. 'EQ Eight').
        device_class:   Ableton class name (e.g. 'Eq8').
        parameter_name: Parameter label (e.g. 'Band 3 Gain').
        value:          Target value (float for parameters, str for properties).
        reason:         Why this action is recommended.
        rack_path:      Absolute path to .adg preset (only for load_rack actions).
        applied:        True once the action has been executed.
        error:          Non-None if the action failed.
    """

    track_name: str
    track_index: int
    action_type: str  # 'set_parameter' | 'load_rack'
    device_name: str
    device_class: str
    parameter_name: str
    value: float | str
    reason: str
    rack_path: str | None = None
    applied: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_name": self.track_name,
            "track_index": self.track_index,
            "action_type": self.action_type,
            "device_name": self.device_name,
            "parameter_name": self.parameter_name,
            "value": self.value,
            "reason": self.reason,
            "rack_path": self.rack_path,
            "applied": self.applied,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# SetupResult
# ---------------------------------------------------------------------------


@dataclass
class SetupResult:
    """Result of applying a list of SetupActions."""

    total: int
    applied: int
    failed: int
    elapsed_sec: float
    actions: list[SetupAction] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "applied": self.applied,
            "failed": self.failed,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "actions": [a.as_dict() for a in self.actions],
        }


# ---------------------------------------------------------------------------
# Action builders (pure — no side effects)
# ---------------------------------------------------------------------------


def _eq_actions_for_problem(
    track_name: str,
    track_index: int,
    problem_category: str,
    contributions: list[StemContribution],
    footprint: StemFootprint,
) -> list[SetupAction]:
    """Build EQ Eight parameter actions for a frequency problem."""
    actions: list[SetupAction] = []

    # Find this track in contributions
    contrib = next((c for c in contributions if c.track_name == track_name), None)
    if not contrib or contrib.contribution_pct < 10.0:
        return []

    # Determine the frequency and gain from problem type
    if problem_category == "muddiness":
        freq_hz, gain_db, q = 280.0, -3.0, 1.4
    elif problem_category == "boominess":
        freq_hz, gain_db, q = 80.0, -3.5, 0.7
    elif problem_category == "harshness":
        freq_hz, gain_db, q = 5000.0, -2.5, 2.0
    elif problem_category == "thinness":
        freq_hz, gain_db, q = 250.0, 2.0, 1.2
    else:
        return []

    band = _band_for_freq(freq_hz)
    reason = (
        f"{track_name} contributes {contrib.contribution_pct:.0f}% of master {problem_category}. "
        f"{contrib.recommended_fix}"
    )

    for param_name, param_value in [
        (f"Band {band} Freq", freq_hz),
        (f"Band {band} Gain", gain_db),
        (f"Band {band} Q", q),
        (f"Band {band} Mode", 0.0),  # 0 = bell/peak mode
    ]:
        actions.append(
            SetupAction(
                track_name=track_name,
                track_index=track_index,
                action_type="set_parameter",
                device_name="EQ Eight",
                device_class="Eq8",
                parameter_name=param_name,
                value=param_value,
                reason=reason if "Freq" in param_name else "",
            )
        )

    return actions


def _compressor_actions(
    track_name: str,
    track_index: int,
    stem_type: StemType,
    genre: str,
) -> list[SetupAction]:
    """Build Compressor parameter actions based on stem type and genre."""
    # Genre-typical compressor settings per stem type
    settings: dict[StemType, dict[str, float]] = {
        StemType.kick: {"Threshold": -18.0, "Ratio": 4.0, "Attack Time": 5.0, "Release Time": 80.0},
        StemType.bass: {"Threshold": -14.0, "Ratio": 3.0, "Attack Time": 20.0, "Release Time": 120.0},
        StemType.pad: {"Threshold": -12.0, "Ratio": 2.0, "Attack Time": 50.0, "Release Time": 200.0},
        StemType.percussion: {"Threshold": -16.0, "Ratio": 3.5, "Attack Time": 3.0, "Release Time": 60.0},
        StemType.vocal: {"Threshold": -14.0, "Ratio": 3.0, "Attack Time": 15.0, "Release Time": 150.0},
        StemType.fx: {"Threshold": -10.0, "Ratio": 2.0, "Attack Time": 30.0, "Release Time": 300.0},
        StemType.unknown: {"Threshold": -12.0, "Ratio": 2.5, "Attack Time": 20.0, "Release Time": 150.0},
    }
    params = settings.get(stem_type, settings[StemType.unknown])

    actions = []
    for param_name, param_value in params.items():
        actions.append(
            SetupAction(
                track_name=track_name,
                track_index=track_index,
                action_type="set_parameter",
                device_name="Compressor",
                device_class="Compressor2",
                parameter_name=param_name,
                value=param_value,
                reason=(
                    f"Genre-typical {genre} compressor settings for {stem_type.value} stem."
                ),
            )
        )
    return actions


def _utility_actions(
    track_name: str,
    track_index: int,
    suggestion: VolumeBalanceSuggestion,
) -> list[SetupAction]:
    """Build Utility gain actions for volume balance corrections."""
    return [
        SetupAction(
            track_name=track_name,
            track_index=track_index,
            action_type="set_parameter",
            device_name="Utility",
            device_class="Utility",
            parameter_name="Gain",
            value=suggestion.adjustment_db,
            reason=suggestion.reason,
        )
    ]


# ---------------------------------------------------------------------------
# build_setup_actions — pure orchestration
# ---------------------------------------------------------------------------


def build_setup_actions(
    session_tracks: list[dict[str, Any]],
    stem_footprints: dict[str, StemFootprint],
    attributed_problems: dict[str, list[StemContribution]],
    volume_suggestions: list[VolumeBalanceSuggestion],
    genre: str,
) -> list[SetupAction]:
    """Build the full list of setup actions without applying them.

    This is the 'preview' step: returns all planned actions so the UI
    can display them with checkboxes before the user confirms.

    Args:
        session_tracks:      List of track dicts from ALS Listener session_state.
        stem_footprints:     Map of track_name → StemFootprint.
        attributed_problems: Map of problem_category → list[StemContribution].
        volume_suggestions:  List of VolumeBalanceSuggestion objects.
        genre:               Genre key for genre-specific settings.

    Returns:
        List of SetupAction objects sorted by track_index, then by device priority.
    """
    # Build track_name → track_index map (session_tracks is list[Track])
    name_to_idx: dict[str, int] = {
        t.name: i
        for i, t in enumerate(session_tracks)
    }

    actions: list[SetupAction] = []

    # 1. EQ actions from attributed problems
    for problem_category, contributions in attributed_problems.items():
        for contrib in contributions:
            track_name = contrib.track_name
            track_idx = name_to_idx.get(track_name, -1)
            if track_idx < 0:
                continue
            fp = stem_footprints.get(track_name)
            if fp is None:
                continue
            actions.extend(
                _eq_actions_for_problem(
                    track_name, track_idx, problem_category, contributions, fp
                )
            )

    # 2. Compressor actions for each stem
    for track_name, fp in stem_footprints.items():
        track_idx = name_to_idx.get(track_name, -1)
        if track_idx < 0:
            continue
        actions.extend(_compressor_actions(track_name, track_idx, fp.stem_type, genre))

    # 3. Volume balance actions
    for suggestion in volume_suggestions:
        track_idx = name_to_idx.get(suggestion.track_name, -1)
        if track_idx < 0:
            continue
        actions.extend(_utility_actions(suggestion.track_name, track_idx, suggestion))

    # Sort: track index, then action type (eq first, then compressor, then utility)
    priority = {"EQ Eight": 0, "Compressor": 1, "Utility": 2}
    actions.sort(key=lambda a: (a.track_index, priority.get(a.device_name, 9)))

    return actions


# ---------------------------------------------------------------------------
# apply_setup_actions — side effects (uses AbletonBridge)
# ---------------------------------------------------------------------------


def apply_setup_actions(
    actions: list[SetupAction],
    *,
    progress: ProgressCallback = _noop,
    timeout_sec: float = _TIMEOUT_SEC,
) -> SetupResult:
    """Apply a list of SetupActions to Ableton via the ALS Listener.

    Sends set_parameter commands over WebSocket for each action.
    Skips empty reason strings (derived parameter actions).

    Args:
        actions:     SetupAction list from build_setup_actions() (or user-filtered).
        progress:    Callback(current, total, track, status) for UI updates.
        timeout_sec: Per-command WebSocket timeout.

    Returns:
        SetupResult with per-action status.
    """
    start = time.monotonic()
    total = len(actions)
    applied = 0
    failed = 0

    try:
        from ingestion.ableton_bridge import AbletonBridge

        bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
        session = bridge.get_session()

        # Build track_name → device_lom lookup
        from core.ableton.session import find_device, find_track  # type: ignore

    except Exception as exc:
        # Bridge not available — mark all as failed
        for i, action in enumerate(actions):
            action.error = f"Bridge unavailable: {exc}"
            progress(i + 1, total, action.track_name, "Error")
        return SetupResult(
            total=total,
            applied=0,
            failed=total,
            elapsed_sec=time.monotonic() - start,
            actions=actions,
        )

    for i, action in enumerate(actions):
        progress(i + 1, total, action.track_name, f"Setting {action.parameter_name}...")
        try:
            track = find_track(session, action.track_name)
            device = find_device(track, class_name=action.device_class)

            cmd = {
                "type": "set_parameter",
                "track_idx": action.track_index,
                "device_idx": device.index if hasattr(device, "index") else 0,
                "param_name": action.parameter_name,
                "value": float(action.value) if isinstance(action.value, int | float) else action.value,
                "id": f"setup_{i}",
            }
            bridge.send_commands([cmd])
            action.applied = True
            applied += 1
            progress(i + 1, total, action.track_name, "✓")

        except Exception as exc:
            action.error = str(exc)
            failed += 1
            progress(i + 1, total, action.track_name, f"Error: {exc}")

    return SetupResult(
        total=total,
        applied=applied,
        failed=failed,
        elapsed_sec=round(time.monotonic() - start, 2),
        actions=actions,
    )
