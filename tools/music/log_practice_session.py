"""
log_practice_session tool — persist practice sessions to JSON storage.

Side-effect tool: writes to disk. Core analysis logic (gap detection)
is kept pure in this module as private functions operating on plain dicts.

Storage format (sessions.json):
    [
        {
            "session_id": "20250217T143022",
            "logged_at": "2025-02-17T14:30:22",
            "topic": "bass design",
            "duration_minutes": 120,
            "notes": "Practiced 808 layering and sidechain compression",
            "tags": ["bass", "mixing", "compression"]
        },
        ...
    ]
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# Default storage path relative to project root
DEFAULT_SESSIONS_FILE = Path("data/practice_sessions.json")

# Domain validation bounds
MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 720  # 12 hours max per session
MAX_TOPIC_LENGTH = 200
MAX_NOTES_LENGTH = 2000

# Topics that suggest practice gaps when not seen recently
CORE_TOPICS: tuple[str, ...] = (
    "arrangement",
    "mixing",
    "mastering",
    "synthesis",
    "sound design",
    "bass design",
    "eq",
    "compression",
    "music theory",
    "chord progressions",
    "performance",
)


@dataclass(frozen=True)
class PracticeSession:
    """
    Immutable value object for a logged practice session.

    Attributes:
        session_id: Timestamp-based unique identifier (YYYYMMDDTHHmmss)
        logged_at: ISO-8601 datetime when session was logged
        topic: What was practiced (e.g., "bass design", "arrangement")
        duration_minutes: Session length in minutes
        notes: Optional free-text notes or discoveries
        tags: Derived tags extracted from topic + notes
    """

    session_id: str
    logged_at: str
    topic: str
    duration_minutes: int
    notes: str
    tags: tuple[str, ...]


class LogPracticeSession(MusicalTool):
    """
    Record a music production practice session to persistent storage.

    Logs topic, duration, and notes to a JSON file. After logging,
    performs gap analysis: identifies core topics not practiced in
    the last 7 days and surfaces them as suggestions.

    The gap analysis is what transforms this from a simple logger into
    an intelligent practice advisor — "You logged bass design 5 times
    this week but haven't touched arrangement in 12 days."

    Example:
        tool = LogPracticeSession()
        result = tool(
            topic="bass design",
            duration_minutes=90,
            notes="Worked on 808 layering and sidechain routing",
        )
        # data: {"session_id": "...", "total_sessions": 12, "gaps": ["arrangement"]}
    """

    def __init__(self, sessions_file: Path = DEFAULT_SESSIONS_FILE) -> None:
        """
        Args:
            sessions_file: Path to JSON storage file. Default: data/practice_sessions.json
        """
        self._sessions_file = sessions_file

    @property
    def name(self) -> str:
        return "log_practice_session"

    @property
    def description(self) -> str:
        return (
            "Record a music production practice session. Logs topic, duration, "
            "and notes, then identifies gaps — core areas not practiced recently. "
            "Use when the user says they finished a session, practiced something, "
            "or worked on a musical skill."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="topic",
                type=str,
                description=(
                    "What was practiced (e.g., 'bass design', 'arrangement', "
                    "'mixing kick and bass', 'chord progressions')"
                ),
                required=True,
            ),
            ToolParameter(
                name="duration_minutes",
                type=int,
                description="Session length in minutes (1–720)",
                required=True,
            ),
            ToolParameter(
                name="notes",
                type=str,
                description="Optional notes, discoveries, or things to follow up",
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Log a practice session and return gap analysis.

        Args:
            topic: What was practiced
            duration_minutes: Session length in minutes
            notes: Optional free-text notes

        Returns:
            ToolResult with session_id, total_sessions, and gap suggestions
        """
        topic: str = kwargs["topic"]
        duration_minutes: int = kwargs["duration_minutes"]
        notes: str = kwargs.get("notes") or ""

        # Domain validation (type validation already done by base class)
        topic = topic.strip()
        if not topic:
            return ToolResult(success=False, error="topic cannot be empty")
        if len(topic) > MAX_TOPIC_LENGTH:
            return ToolResult(
                success=False,
                error=f"topic too long (max {MAX_TOPIC_LENGTH} chars)",
            )
        if duration_minutes < MIN_DURATION_MINUTES:
            return ToolResult(
                success=False,
                error=f"duration_minutes must be at least {MIN_DURATION_MINUTES}",
            )
        if duration_minutes > MAX_DURATION_MINUTES:
            return ToolResult(
                success=False,
                error=f"duration_minutes must be at most {MAX_DURATION_MINUTES} (12h max)",
            )
        if len(notes) > MAX_NOTES_LENGTH:
            return ToolResult(
                success=False,
                error=f"notes too long (max {MAX_NOTES_LENGTH} chars)",
            )

        # Build session
        now = datetime.now(UTC)
        session_id = now.strftime("%Y%m%dT%H%M%S")
        session = PracticeSession(
            session_id=session_id,
            logged_at=now.isoformat(),
            topic=topic,
            duration_minutes=duration_minutes,
            notes=notes,
            tags=_extract_tags(topic, notes),
        )

        # Persist to JSON
        all_sessions = self._load_sessions()
        all_sessions.append(_session_to_dict(session))
        self._save_sessions(all_sessions)

        # Gap analysis: which core topics haven't been practiced recently?
        gaps = _find_practice_gaps(all_sessions, days=7)

        return ToolResult(
            success=True,
            data={
                "session_id": session_id,
                "topic": topic,
                "duration_minutes": duration_minutes,
                "total_sessions": len(all_sessions),
                "gaps": gaps,
            },
            metadata={
                "logged_at": session.logged_at,
                "storage": str(self._sessions_file),
            },
        )

    def _load_sessions(self) -> list[dict[str, Any]]:
        """Load existing sessions from JSON file. Returns empty list if not found."""
        if not self._sessions_file.exists():
            return []
        try:
            text = self._sessions_file.read_text(encoding="utf-8")
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_sessions(self, sessions: list[dict[str, Any]]) -> None:
        """Persist sessions list to JSON file. Creates parent dirs if needed."""
        self._sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self._sessions_file.write_text(
            json.dumps(sessions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Pure helper functions (no I/O, no side effects)
# ---------------------------------------------------------------------------


def _extract_tags(topic: str, notes: str) -> tuple[str, ...]:
    """
    Extract lowercase keyword tags from topic and notes.

    Splits on whitespace and punctuation, lowercases, deduplicates.

    Args:
        topic: Session topic string
        notes: Optional session notes

    Returns:
        Sorted tuple of unique tags (at least 1 word from topic)
    """
    combined = f"{topic} {notes}"
    words = re.findall(r"[a-zA-Z]+", combined)
    # Filter out common stop words and very short tokens
    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "i",
        "my",
        "it",
        "is",
        "was",
        "been",
    }
    tags = {w.lower() for w in words if len(w) > 2 and w.lower() not in stop_words}
    return tuple(sorted(tags))


def _session_to_dict(session: PracticeSession) -> dict[str, Any]:
    """Convert PracticeSession to JSON-serializable dict."""
    d = asdict(session)
    d["tags"] = list(session.tags)  # tuple → list for JSON
    return d


def _find_practice_gaps(
    sessions: list[dict[str, Any]],
    days: int = 7,
) -> list[str]:
    """
    Identify core topics not practiced in the last N days.

    Pure function — no I/O. Operates on serialized session dicts.

    Args:
        sessions: List of session dicts (from JSON storage)
        days: Lookback window in days

    Returns:
        List of core topic names not seen in recent sessions
    """
    if not sessions:
        return list(CORE_TOPICS)

    now = datetime.now(UTC)
    recent_topics: set[str] = set()

    for session in sessions:
        logged_at_str = session.get("logged_at", "")
        try:
            logged_at = datetime.fromisoformat(logged_at_str)
        except ValueError:
            continue

        # Ensure timezone-aware comparison
        if logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=UTC)

        age_days = (now - logged_at).days
        if age_days <= days:
            topic = session.get("topic", "").lower()
            tags = session.get("tags", [])
            recent_topics.add(topic)
            recent_topics.update(t.lower() for t in tags)

    gaps = []
    for core_topic in CORE_TOPICS:
        # Check if any recent topic/tag contains this core topic keyword
        if not any(core_topic in recent for recent in recent_topics):
            gaps.append(core_topic)

    return gaps
