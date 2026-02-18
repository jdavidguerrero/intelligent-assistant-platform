"""
create_session_note tool — structured insight capture from practice sessions.

Unlike log_practice_session (which records time and topic), session notes
capture qualitative insights: discoveries, problems solved, ideas, and
next steps. They form the producer's knowledge journal.

Storage format (session_notes.json):
    [
        {
            "note_id": "20250217T143022",
            "created_at": "2025-02-17T14:30:22",
            "category": "discovery",
            "title": "Sidechain creates pumping without volume rides",
            "content": "Found that using a very fast attack (0.1ms) on the kick...",
            "tags": ["sidechain", "kick", "compression"],
            "linked_topic": "bass design",
            "action_items": ["try with 808", "experiment with release time"]
        },
        ...
    ]

Note categories:
    discovery   — Something new learned or figured out
    problem     — An issue encountered and (optionally) solved
    idea        — Creative concept to explore later
    reference   — A tip, technique, or reference to remember
    next_steps  — What to work on next (follow-up from a session)
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# Default storage path
DEFAULT_NOTES_FILE = Path("data/session_notes.json")

# Domain validation
MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 3000
MAX_LINKED_TOPIC_LENGTH = 200
MAX_ACTION_ITEMS = 10
MAX_ACTION_ITEM_LENGTH = 200

VALID_CATEGORIES: frozenset[str] = frozenset(
    {"discovery", "problem", "idea", "reference", "next_steps"}
)

# Tags auto-extracted from content when not provided
_MUSIC_KEYWORDS: tuple[str, ...] = (
    "sidechain",
    "compression",
    "reverb",
    "delay",
    "eq",
    "filter",
    "bass",
    "kick",
    "synth",
    "chord",
    "melody",
    "arrangement",
    "mixing",
    "mastering",
    "bpm",
    "key",
    "scale",
    "harmonic",
    "midi",
    "automation",
    "modulation",
    "oscillator",
    "envelope",
    "arp",
    "arpeggio",
    "pad",
    "lead",
    "breakdown",
    "drop",
    "loop",
    "sample",
    "stem",
    "layering",
)


@dataclass(frozen=True)
class SessionNote:
    """
    Immutable value object for a captured session insight.

    Attributes:
        note_id: Timestamp-based unique ID (YYYYMMDDTHHmmss)
        created_at: ISO-8601 datetime
        category: Note type (discovery | problem | idea | reference | next_steps)
        title: Short summary (max 200 chars)
        content: Full note content (max 3000 chars)
        tags: Music production keyword tags (auto-extracted + user-provided)
        linked_topic: Optional practice topic this note relates to
        action_items: Optional follow-up tasks
    """

    note_id: str
    created_at: str
    category: str
    title: str
    content: str
    tags: tuple[str, ...]
    linked_topic: str
    action_items: tuple[str, ...]


class CreateSessionNote(MusicalTool):
    """
    Capture a structured insight or discovery from a practice session.

    Use to record qualitative learnings, creative ideas, solved problems,
    or next steps — the "knowledge journal" complement to session logging.

    Unlike log_practice_session (time tracking), session notes focus on
    the substance of what was learned or discovered.

    Example:
        tool = CreateSessionNote()
        result = tool(
            category="discovery",
            title="Sidechain pumping trick with very fast attack",
            content="Using 0.1ms attack on the compressor with the kick as sidechain source...",
            linked_topic="bass design",
            action_items=["try with 808", "test on organic house track"],
        )
    """

    def __init__(self, notes_file: Path | None = None) -> None:
        """
        Args:
            notes_file: Path to the JSON notes file. Defaults to DEFAULT_NOTES_FILE.
                        Pass a temp path in tests to avoid touching real files.
        """
        self._notes_file = notes_file or DEFAULT_NOTES_FILE

    @property
    def name(self) -> str:
        return "create_session_note"

    @property
    def description(self) -> str:
        return (
            "Capture a structured insight, discovery, or idea from a music production session. "
            "Use when the user wants to save a technique they discovered, a problem they solved, "
            "a creative idea for later, or action items for the next session. "
            "Categories: 'discovery' (new technique), 'problem' (issue solved), "
            "'idea' (creative concept), 'reference' (tip to remember), "
            "'next_steps' (follow-up tasks). "
            "Different from log_practice_session — notes capture WHAT was learned, "
            "not just that a session happened."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="category",
                type=str,
                description=(
                    "Note type. One of: 'discovery', 'problem', 'idea', 'reference', 'next_steps'. "
                    "discovery = something new learned; problem = issue encountered/solved; "
                    "idea = creative concept to explore; reference = tip to remember; "
                    "next_steps = follow-up tasks for next session."
                ),
                required=True,
            ),
            ToolParameter(
                name="title",
                type=str,
                description=(
                    f"Short summary of the insight (max {MAX_TITLE_LENGTH} chars). "
                    "Examples: 'Sidechain pumping without volume rides', "
                    "'8A → 9A transition sounds dark and heavy'."
                ),
                required=True,
            ),
            ToolParameter(
                name="content",
                type=str,
                description=(
                    f"Full description of the insight (max {MAX_CONTENT_LENGTH} chars). "
                    "Include details, parameters, context, and anything needed to reproduce it."
                ),
                required=True,
            ),
            ToolParameter(
                name="linked_topic",
                type=str,
                description=(
                    "Optional practice topic this note relates to "
                    "(e.g., 'bass design', 'arrangement', 'chord progressions'). "
                    "Links this note to log_practice_session entries."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="action_items",
                type=list,
                description=(
                    f"Optional list of follow-up tasks (max {MAX_ACTION_ITEMS} items). "
                    "Examples: ['try with 808', 'test on organic house track', 'export stem']."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="tags",
                type=list,
                description=(
                    "Optional list of tags. If omitted, tags are auto-extracted from content. "
                    "Examples: ['sidechain', 'compression', 'kick']."
                ),
                required=False,
                default=None,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Create and persist a session note.

        Returns:
            ToolResult with:
                data:
                    note_id:     Unique note identifier
                    created_at:  ISO-8601 timestamp
                    category:    Note category
                    title:       Note title
                    content:     Full note content
                    tags:        Tags (auto-extracted or provided)
                    linked_topic: Related practice topic
                    action_items: Follow-up tasks
                    notes_file:  Path where note was saved
                    total_notes: Total notes in file after save
        """
        category: str = (kwargs.get("category") or "").strip().lower()
        title: str = (kwargs.get("title") or "").strip()
        content: str = (kwargs.get("content") or "").strip()
        linked_topic: str = (kwargs.get("linked_topic") or "").strip()
        action_items_raw = kwargs.get("action_items")
        tags_raw = kwargs.get("tags")

        # -------------------------------------------------------------------
        # Validation
        # -------------------------------------------------------------------
        if not category:
            return ToolResult(success=False, error="category cannot be empty")
        if category not in VALID_CATEGORIES:
            return ToolResult(
                success=False,
                error=(
                    f"Invalid category: '{category}'. "
                    f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
                ),
            )

        if not title:
            return ToolResult(success=False, error="title cannot be empty")
        if len(title) > MAX_TITLE_LENGTH:
            return ToolResult(
                success=False,
                error=f"title too long (max {MAX_TITLE_LENGTH} chars, got {len(title)})",
            )

        if not content:
            return ToolResult(success=False, error="content cannot be empty")
        if len(content) > MAX_CONTENT_LENGTH:
            return ToolResult(
                success=False,
                error=f"content too long (max {MAX_CONTENT_LENGTH} chars, got {len(content)})",
            )

        if len(linked_topic) > MAX_LINKED_TOPIC_LENGTH:
            return ToolResult(
                success=False,
                error=f"linked_topic too long (max {MAX_LINKED_TOPIC_LENGTH} chars)",
            )

        # Validate action_items
        action_items: list[str] = []
        if action_items_raw is not None:
            if not isinstance(action_items_raw, list):
                return ToolResult(success=False, error="action_items must be a list of strings")
            if len(action_items_raw) > MAX_ACTION_ITEMS:
                return ToolResult(
                    success=False,
                    error=f"Too many action_items (max {MAX_ACTION_ITEMS})",
                )
            for i, item in enumerate(action_items_raw):
                if not isinstance(item, str):
                    return ToolResult(
                        success=False,
                        error=f"action_items[{i}] must be a string",
                    )
                item = item.strip()
                if not item:
                    continue
                if len(item) > MAX_ACTION_ITEM_LENGTH:
                    return ToolResult(
                        success=False,
                        error=f"action_items[{i}] too long (max {MAX_ACTION_ITEM_LENGTH} chars)",
                    )
                action_items.append(item)

        # Extract or validate tags
        if tags_raw is not None:
            if not isinstance(tags_raw, list):
                return ToolResult(success=False, error="tags must be a list of strings")
            tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]
        else:
            # Auto-extract from title + content
            tags = _extract_tags(title + " " + content)

        # -------------------------------------------------------------------
        # Build note
        # -------------------------------------------------------------------
        now = datetime.now(UTC)
        note_id = now.strftime("%Y%m%dT%H%M%S")
        created_at = now.isoformat()

        note = SessionNote(
            note_id=note_id,
            created_at=created_at,
            category=category,
            title=title,
            content=content,
            tags=tuple(tags),
            linked_topic=linked_topic,
            action_items=tuple(action_items),
        )

        # -------------------------------------------------------------------
        # Persist
        # -------------------------------------------------------------------
        try:
            total_notes = _save_note(note, self._notes_file)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to save note: {str(e)}")

        note_dict = asdict(note)
        note_dict["notes_file"] = str(self._notes_file)
        note_dict["total_notes"] = total_notes

        return ToolResult(
            success=True,
            data=note_dict,
            metadata={
                "category": category,
                "tags_auto_extracted": tags_raw is None,
                "has_action_items": len(action_items) > 0,
            },
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _extract_tags(text: str) -> list[str]:
    """
    Auto-extract music production keyword tags from text.

    Pure function — no I/O.

    Args:
        text: Combined title + content text

    Returns:
        List of matching keyword tags (lowercase, deduplicated, sorted)
    """
    text_lower = text.lower()
    found = sorted(
        {kw for kw in _MUSIC_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)}
    )
    return found


def _save_note(note: SessionNote, notes_file: Path) -> int:
    """
    Append note to JSON file and return total note count.

    Side-effect function — writes to disk.

    Args:
        note: SessionNote to persist
        notes_file: Path to notes JSON file

    Returns:
        Total number of notes in file after save
    """
    notes_file.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if notes_file.exists():
        try:
            existing = json.loads(notes_file.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []

    note_dict = asdict(note)
    # Convert tuples to lists for JSON serialization
    note_dict["tags"] = list(note.tags)
    note_dict["action_items"] = list(note.action_items)
    existing.append(note_dict)

    notes_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(existing)


def load_notes(notes_file: Path | None = None) -> list[dict]:
    """
    Load all session notes from storage.

    Args:
        notes_file: Path to notes JSON file. Defaults to DEFAULT_NOTES_FILE.

    Returns:
        List of note dicts (empty if file doesn't exist)
    """
    path = notes_file or DEFAULT_NOTES_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []
