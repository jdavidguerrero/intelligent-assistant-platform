"""ingestion/session_auditor.py — Orchestrates the 3-layer audit pipeline.

Side effects live here: loads YAML presets from disk, reads patterns.json.
All pure analysis delegates to core/session_intelligence/.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from core.ableton.types import SessionState
from core.session_intelligence.gain_staging import run_gain_staging_audit
from core.session_intelligence.genre_presets import run_genre_audit
from core.session_intelligence.mapper import map_session_to_map
from core.session_intelligence.pattern_learner import (
    detect_pattern_anomalies,
    learn_from_channel,
)
from core.session_intelligence.recommendations import generate_audit_report
from core.session_intelligence.types import AuditReport, SessionMap
from core.session_intelligence.universal_audit import run_universal_audit
from ingestion.pattern_store import PatternStore

_PRESETS_DIR: Path = (
    Path(__file__).parent.parent / "core" / "session_intelligence" / "genre_presets"
)


class SessionAuditor:
    """Runs the full 3-layer audit pipeline on an Ableton session.

    Layer 1 — Universal: rule-based checks applicable to all sessions.
    Layer 2 — Pattern: anomaly detection against user's historical patterns.
    Layer 3 — Genre: opt-in checks calibrated to a specific genre style.
    """

    def __init__(self, *, pattern_store: PatternStore | None = None) -> None:
        """Initialize the SessionAuditor.

        Args:
            pattern_store: Optional :class:`PatternStore` instance. If not
                           provided, a default store is created pointing to
                           ``ingestion/user_data/patterns.json``.
        """
        self.pattern_store = pattern_store or PatternStore()
        self._presets: dict[str, dict] = {}  # loaded lazily per genre

    def _load_preset(self, genre: str) -> dict:
        """Load a genre YAML preset by name. Returns empty dict if not found.

        The genre name is normalised: lowercased and spaces replaced with
        underscores before appending ``.yaml``.

        Args:
            genre: Genre preset name, e.g. ``"organic_house"`` or
                   ``"Organic House"``.

        Returns:
            Parsed YAML dict, or empty dict if the file does not exist.
        """
        if genre in self._presets:
            return self._presets[genre]
        filename = genre.lower().replace(" ", "_") + ".yaml"
        path = _PRESETS_DIR / filename
        if not path.exists():
            return {}
        with open(path) as f:
            result = yaml.safe_load(f) or {}
        self._presets[genre] = result
        return result

    def run_audit(
        self,
        session: SessionState,
        *,
        genre_preset: str | None = None,
    ) -> AuditReport:
        """Run the full 3-layer audit.

        Args:
            session: Live session state from ``AbletonBridge.get_session()``.
            genre_preset: Optional genre preset name (e.g. ``"organic_house"``).
                         If ``None``, only Layers 1+2 run (no genre suggestions).

        Returns:
            :class:`AuditReport` with all findings merged and prioritized.
        """
        session_map: SessionMap = map_session_to_map(session, mapped_at=time.time())

        # ------------------------------------------------------------------
        # Layer 1 — Universal
        # ------------------------------------------------------------------
        universal = run_universal_audit(session_map)
        gain = run_gain_staging_audit(session_map)

        # ------------------------------------------------------------------
        # Layer 2 — Patterns
        # ------------------------------------------------------------------
        patterns_data = self.pattern_store.load()
        sessions_saved: int = patterns_data.get("sessions_saved", 0)
        patterns: dict = patterns_data.get("patterns", {})

        pattern_findings = []
        for channel in session_map.all_channels:
            pattern_findings.extend(
                detect_pattern_anomalies(
                    channel,
                    patterns,
                    sessions_saved=sessions_saved,
                )
            )

        # ------------------------------------------------------------------
        # Layer 3 — Genre (opt-in)
        # ------------------------------------------------------------------
        genre_findings = []
        if genre_preset:
            preset = self._load_preset(genre_preset)
            if preset:
                genre_findings = run_genre_audit(session_map, preset)

        return generate_audit_report(
            session_map,
            universal_findings=universal,
            gain_findings=gain,
            pattern_findings=pattern_findings,
            genre_findings=genre_findings,
            generated_at=time.time(),
        )

    def save_session_patterns(self, session: SessionState) -> int:
        """Learn from a completed session and save patterns.

        Extracts per-channel learnable data using
        :func:`core.session_intelligence.pattern_learner.learn_from_channel`
        and appends it to the pattern store.

        Args:
            session: Live session state.

        Returns:
            Number of channels learned from.
        """
        session_map: SessionMap = map_session_to_map(session)
        channel_data = [learn_from_channel(ch) for ch in session_map.all_channels]
        self.pattern_store.add_session_data(channel_data)
        return len(channel_data)
