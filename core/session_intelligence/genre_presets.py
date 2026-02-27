"""core/session_intelligence/genre_presets.py — Layer 3: opt-in genre preset matching.

All functions are pure: they receive preset data as dicts (loaded externally
by ingestion/session_auditor.py) and return AuditFinding objects tagged as
``layer="genre"``, ``severity="suggestion"``, ``icon="💡"``.

Pure module — no I/O, no env vars, no imports from db/, api/, or ingestion/.
YAML loading is handled exclusively by ``ingestion/session_auditor.py``.
"""

from __future__ import annotations

from core.session_intelligence.pattern_learner import (
    _get_current_hp_freq,
    _infer_instrument_type,
)
from core.session_intelligence.types import AuditFinding, ChannelInfo, SessionMap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_channel_against_preset(
    channel: ChannelInfo,
    preset: dict,
) -> list[AuditFinding]:
    """Check a single channel against the genre preset instrument rules.

    Args:
        channel: Channel to inspect.
        preset: Loaded YAML preset dict.

    Returns:
        List of suggestion findings for this channel.
    """
    instruments_config: dict = preset.get("instruments", {})
    preset_name: str = preset.get("name", "Unknown Genre")

    instrument_type = _infer_instrument_type(channel)
    if instrument_type not in instruments_config:
        return []

    instr_config: dict = instruments_config[instrument_type]
    findings: list[AuditFinding] = []

    # ------------------------------------------------------------------
    # HP frequency check
    # ------------------------------------------------------------------
    hp_range: list[float] | None = instr_config.get("hp_freq_range")
    if hp_range and len(hp_range) == 2:
        current_hp = _get_current_hp_freq(channel)
        if current_hp is None:
            suggestion = instr_config.get("suggestion", "")
            findings.append(
                AuditFinding(
                    layer="genre",
                    severity="suggestion",
                    icon="💡",
                    channel_name=channel.name,
                    channel_lom_path=channel.lom_path,
                    device_name=None,
                    rule_id=f"genre_hp_{instrument_type}",
                    message=(
                        f"{channel.name}: No HP filter — "
                        f"{preset_name} typically uses HP at "
                        f"{hp_range[0]:.0f}–{hp_range[1]:.0f} Hz"
                    ),
                    reason=(
                        f"{preset_name} convention. "
                        + (suggestion if suggestion else "HP filter recommended for this instrument type.")
                    ),
                    confidence=0.70,
                    fix_action=None,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_genre_audit(
    session_map: SessionMap,
    preset: dict,
) -> list[AuditFinding]:
    """Run genre preset checks against the session map.

    Args:
        session_map: Mapped session.
        preset: Loaded YAML preset dict. Expected shape::

            {
              "name": "Organic House",
              "instruments": {
                "pad": {
                  "hp_freq_range": [100, 250],
                  "width_range": [100, 150],
                  "comp_ratio_range": [1.5, 3.0],
                  "suggestion": "HP critical to avoid muddiness"
                },
                ...
              },
              "buses": {
                "drums": "Glue compression 2:1 for cohesion",
                ...
              }
            }

    Returns:
        List of :class:`AuditFinding` with ``layer="genre"``,
        ``severity="suggestion"``, ``icon="💡"``.
        All findings are clearly labeled as opt-in suggestions.
        Returns empty list if ``preset`` is empty.
    """
    if not preset:
        return []

    findings: list[AuditFinding] = []
    for channel in session_map.all_channels:
        findings.extend(_check_channel_against_preset(channel, preset))

    return findings
