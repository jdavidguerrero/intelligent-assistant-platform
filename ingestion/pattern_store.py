"""ingestion/pattern_store.py — Pattern storage for Layer 2.

Learns from user sessions and persists pattern data to JSON.
All pure analysis logic is in core/session_intelligence/pattern_learner.py.

Side effects: reads and writes ``ingestion/user_data/patterns.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_STORE_PATH: Path = Path(__file__).parent / "user_data" / "patterns.json"


class PatternStore:
    """JSON-backed storage for user mixing patterns.

    Stores per-instrument-type parameter distributions across sessions.
    The patterns.json format::

        {
            "sessions_saved": 5,
            "patterns": {
                "pad": {
                    "sample_count": 12,
                    "volume_db_values": [-12.0, -11.5, ...],
                    "has_hp_values": [true, true, false, ...],
                    "comp_ratio_values": [0.174, 0.2, ...]
                },
                ...
            }
        }
    """

    def __init__(self, store_path: Path = _DEFAULT_STORE_PATH) -> None:
        """Initialize the PatternStore.

        Args:
            store_path: Path to the JSON file. Defaults to
                        ``ingestion/user_data/patterns.json``.
        """
        self.store_path = store_path

    def load(self) -> dict[str, Any]:
        """Load patterns from JSON file.

        Returns:
            Parsed JSON dict, or empty dict if the file does not exist.
        """
        if not self.store_path.exists():
            return {}
        with open(self.store_path) as f:
            return json.load(f)

    def save(self, data: dict[str, Any]) -> None:
        """Save patterns dict to JSON file. Creates parent directories if needed.

        Args:
            data: Dict to serialize to JSON.
        """
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_patterns(self) -> dict[str, Any]:
        """Load and return the patterns sub-dict.

        Returns:
            The ``"patterns"`` value from the store, or empty dict.
        """
        return self.load().get("patterns", {})

    def get_sessions_saved(self) -> int:
        """Return number of sessions saved.

        Returns:
            Integer count of sessions recorded so far.
        """
        return self.load().get("sessions_saved", 0)

    def add_session_data(self, session_data: list[dict[str, Any]]) -> None:
        """Append per-channel data from a completed session to the pattern store.

        Each dict in ``session_data`` comes from
        :func:`core.session_intelligence.pattern_learner.learn_from_channel`.
        Expected keys: ``instrument_type``, ``volume_db``, ``has_hp``,
        optionally ``comp_ratio``.

        Args:
            session_data: List of channel data dicts.
        """
        store = self.load()
        patterns: dict[str, Any] = store.get("patterns", {})
        sessions_saved: int = store.get("sessions_saved", 0)

        for channel_data in session_data:
            instrument_type: str = channel_data.get("instrument_type", "unknown")
            if instrument_type == "unknown":
                continue

            if instrument_type not in patterns:
                patterns[instrument_type] = {
                    "sample_count": 0,
                    "volume_db_values": [],
                    "has_hp_values": [],
                    "hp_freq_values": [],
                    "comp_ratio_values": [],
                }

            instr = patterns[instrument_type]
            instr["sample_count"] = instr.get("sample_count", 0) + 1

            if "volume_db" in channel_data:
                instr.setdefault("volume_db_values", []).append(channel_data["volume_db"])

            if "has_hp" in channel_data:
                instr.setdefault("has_hp_values", []).append(channel_data["has_hp"])
                # Track presence of HP as a synthetic freq value for pattern detection
                if channel_data["has_hp"]:
                    # Use a placeholder Hz value indicating HP was present
                    instr.setdefault("hp_freq_values", []).append(1.0)

            if "comp_ratio" in channel_data:
                instr.setdefault("comp_ratio_values", []).append(channel_data["comp_ratio"])

        store["patterns"] = patterns
        store["sessions_saved"] = sessions_saved + 1
        self.save(store)

    def clear(self) -> None:
        """Clear all patterns (for testing / reset).

        Removes the JSON file if it exists.
        """
        if self.store_path.exists():
            self.store_path.unlink()
