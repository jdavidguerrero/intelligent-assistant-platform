"""
MCP Musical Intelligence — resource handlers with pagination and filtering.

Why this module exists (Day 2 extraction from handlers.py):
    Day 1 put resource logic directly in handlers.py for speed. Day 2 extracts
    it here because resources have their own concerns: file I/O, JSON parsing,
    pagination, filtering, and stats computation. These are distinct from tool
    concerns (external calls, parameter validation, LLM synthesis).

    handlers.py registers the @mcp.resource() decorators.
    resources.py contains the implementation functions called by those decorators.

Resource design principles:
    1. Always return valid JSON — never raise, never return partial data.
       Broken JSON silently kills the MCP client's ability to use the resource.
    2. Graceful degradation — if the file doesn't exist, return empty state.
       The resource being unavailable is not an error worth propagating.
    3. Pagination by default — resources can grow unbounded. Always paginate.
    4. Filtering as first-class — clients should not have to filter on their side.
    5. Summary stats alongside data — saves a round-trip for common aggregations.

Pagination model:
    All paginated resources accept:
        limit:  int  — max items per page (default 20, max 100)
        offset: int  — skip first N items (default 0)
    All paginated responses include:
        total:   total number of matching items
        offset:  current offset
        limit:   current limit
        items:   the page of items

Filter model:
    Filters are resource-specific:
        practice-logs:  date_from, date_to, topic_contains
        session-notes:  category, tag, date_from, date_to
        setlist:        (no extra filters — always tagged 'setlist')
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File path constants — match Week 3 tool defaults
# ---------------------------------------------------------------------------

_SESSIONS_FILE = Path("data/practice_sessions.json")
_NOTES_FILE = Path("data/session_notes.json")

# Pagination limits
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ---------------------------------------------------------------------------
# practice-logs resource
# ---------------------------------------------------------------------------


def read_practice_logs(
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
    date_from: str = "",
    date_to: str = "",
    topic_contains: str = "",
) -> str:
    """
    Read practice session logs with optional filtering and pagination.

    Filters are applied before pagination. All filters are optional.
    Returns valid JSON regardless of file state.

    Args:
        limit:          Max sessions per page (1–100, default 20)
        offset:         Skip first N sessions (default 0)
        date_from:      ISO date string 'YYYY-MM-DD' — only sessions on or after
        date_to:        ISO date string 'YYYY-MM-DD' — only sessions on or before
        topic_contains: Case-insensitive substring match against session topic

    Returns:
        JSON string with keys: sessions, total, offset, limit, stats
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    offset = max(0, offset)

    if not _SESSIONS_FILE.exists():
        return _empty_paginated("sessions")

    try:
        raw = json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read practice logs: %s", exc)
        return _error_response("sessions", str(exc))

    sessions: list[dict[str, Any]] = raw if isinstance(raw, list) else []

    # Apply filters
    filtered = _filter_sessions(sessions, date_from, date_to, topic_contains)

    # Compute stats before pagination
    stats = _compute_session_stats(filtered)

    # Paginate
    page = filtered[offset : offset + limit]

    return json.dumps(
        {
            "sessions": page,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "stats": stats,
        },
        indent=2,
        default=str,
    )


def _filter_sessions(
    sessions: list[dict[str, Any]],
    date_from: str,
    date_to: str,
    topic_contains: str,
) -> list[dict[str, Any]]:
    """Apply date range and topic filters to session list. Pure function."""
    result = sessions

    if date_from:
        try:
            df = datetime.fromisoformat(date_from).date()
            result = [s for s in result if _session_date(s) >= df]
        except ValueError:
            logger.warning("Invalid date_from=%r — ignoring filter", date_from)

    if date_to:
        try:
            dt = datetime.fromisoformat(date_to).date()
            result = [s for s in result if _session_date(s) <= dt]
        except ValueError:
            logger.warning("Invalid date_to=%r — ignoring filter", date_to)

    if topic_contains:
        needle = topic_contains.lower()
        result = [s for s in result if needle in str(s.get("topic", "")).lower()]

    return result


def _session_date(session: dict[str, Any]):  # type: ignore[return]
    """Extract date from a session record. Returns date.min on parse failure."""
    from datetime import date

    raw = session.get("logged_at") or session.get("date") or ""
    if not raw:
        return date.min
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        return date.min


def _compute_session_stats(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate statistics over a list of sessions.

    Returns a summary dict with totals and breakdowns.
    Pure function — no I/O.

    Stats computed:
        total_sessions:     count of all sessions
        total_minutes:      sum of all duration_minutes
        topics:             dict mapping topic → total minutes
        most_practiced:     topic with most minutes (None if empty)
        least_practiced:    topic with least minutes (None if 0 or 1 topics)
        avg_session_min:    average session duration in minutes
    """
    if not sessions:
        return {
            "total_sessions": 0,
            "total_minutes": 0,
            "topics": {},
            "most_practiced": None,
            "least_practiced": None,
            "avg_session_min": 0.0,
        }

    topic_minutes: dict[str, int] = {}
    total_minutes = 0

    for s in sessions:
        topic = str(s.get("topic", "unknown"))
        mins = int(s.get("duration_minutes", 0))
        topic_minutes[topic] = topic_minutes.get(topic, 0) + mins
        total_minutes += mins

    sorted_topics = sorted(topic_minutes.items(), key=lambda x: x[1], reverse=True)

    return {
        "total_sessions": len(sessions),
        "total_minutes": total_minutes,
        "topics": dict(sorted_topics),
        "most_practiced": sorted_topics[0][0] if sorted_topics else None,
        "least_practiced": sorted_topics[-1][0] if len(sorted_topics) > 1 else None,
        "avg_session_min": round(total_minutes / len(sessions), 1) if sessions else 0.0,
    }


# ---------------------------------------------------------------------------
# session-notes resource
# ---------------------------------------------------------------------------


def read_session_notes(
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
    category: str = "",
    tag: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """
    Read session notes with optional filtering and pagination.

    All filters are optional and cumulative (AND logic).
    Returns valid JSON regardless of file state.

    Args:
        limit:     Max notes per page (1–100, default 20)
        offset:    Skip first N notes (default 0)
        category:  Filter by category: discovery|problem|idea|reference|next_steps
        tag:       Case-insensitive substring match against any note tag
        date_from: ISO date string 'YYYY-MM-DD' — only notes on or after
        date_to:   ISO date string 'YYYY-MM-DD' — only notes on or before

    Returns:
        JSON string with keys: notes, total, offset, limit, category_counts
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    offset = max(0, offset)

    if not _NOTES_FILE.exists():
        return _empty_paginated("notes")

    try:
        raw = json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read session notes: %s", exc)
        return _error_response("notes", str(exc))

    notes: list[dict[str, Any]] = raw if isinstance(raw, list) else []

    # Compute category counts over full dataset (before filtering)
    category_counts = _compute_category_counts(notes)

    # Apply filters
    filtered = _filter_notes(notes, category, tag, date_from, date_to)

    # Paginate
    page = filtered[offset : offset + limit]

    return json.dumps(
        {
            "notes": page,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "category_counts": category_counts,
        },
        indent=2,
        default=str,
    )


def _filter_notes(
    notes: list[dict[str, Any]],
    category: str,
    tag: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    """Apply category, tag, and date filters to notes list. Pure function."""
    result = notes

    if category:
        cat = category.lower().strip()
        result = [n for n in result if str(n.get("category", "")).lower() == cat]

    if tag:
        needle = tag.lower()
        result = [n for n in result if any(needle in str(t).lower() for t in (n.get("tags") or []))]

    if date_from:
        try:
            df = datetime.fromisoformat(date_from).date()
            result = [n for n in result if _note_date(n) >= df]
        except ValueError:
            logger.warning("Invalid date_from=%r — ignoring filter", date_from)

    if date_to:
        try:
            dt = datetime.fromisoformat(date_to).date()
            result = [n for n in result if _note_date(n) <= dt]
        except ValueError:
            logger.warning("Invalid date_to=%r — ignoring filter", date_to)

    return result


def _note_date(note: dict[str, Any]):  # type: ignore[return]
    """Extract date from a note record. Returns date.min on parse failure."""
    from datetime import date

    raw = note.get("created_at") or note.get("date") or ""
    if not raw:
        return date.min
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        return date.min


def _compute_category_counts(notes: list[dict[str, Any]]) -> dict[str, int]:
    """Count notes per category. Pure function."""
    counts: dict[str, int] = {}
    for note in notes:
        cat = str(note.get("category", "unknown"))
        counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# knowledge-base/metadata resource
# ---------------------------------------------------------------------------


def read_kb_metadata() -> str:
    """
    Read metadata about the music production knowledge base.

    Queries the database for chunk counts and source breakdown.
    Gracefully returns unavailable status when DB is not configured.

    Returns:
        JSON string with keys: status, total_chunks, sources, topics
    """
    import os

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        return json.dumps(
            {
                "status": "unavailable",
                "reason": "DATABASE_URL not configured",
                "total_chunks": 0,
                "sources": [],
                "topics": [],
            },
            indent=2,
        )

    try:
        from sqlalchemy import func

        from db.models import ChunkRecord
        from db.session import get_session

        with get_session() as session:
            # Total chunk count
            total: int = session.query(func.count(ChunkRecord.id)).scalar() or 0

            # Per-source breakdown (top 20 sources by chunk count)
            source_rows = (
                session.query(
                    ChunkRecord.source_name,
                    ChunkRecord.source_path,
                    func.count(ChunkRecord.id).label("chunk_count"),
                )
                .group_by(ChunkRecord.source_name, ChunkRecord.source_path)
                .order_by(func.count(ChunkRecord.id).desc())
                .limit(20)
                .all()
            )

            sources = [
                {
                    "source_name": row.source_name,
                    "source_path": row.source_path,
                    "chunk_count": row.chunk_count,
                    "percentage": round(row.chunk_count / total * 100, 1) if total else 0.0,
                }
                for row in source_rows
            ]

            # Source type breakdown (pdf vs youtube vs md)
            type_counts = _classify_source_types(sources)

        return json.dumps(
            {
                "status": "ok",
                "total_chunks": total,
                "sources": sources,
                "source_types": type_counts,
            },
            indent=2,
            default=str,
        )

    except Exception as exc:
        logger.error("Failed to read KB metadata: %s", exc)
        return json.dumps(
            {
                "status": "error",
                "reason": str(exc),
                "total_chunks": 0,
                "sources": [],
                "source_types": {},
            },
            indent=2,
        )


def _classify_source_types(sources: list[dict[str, Any]]) -> dict[str, int]:
    """
    Classify source paths into types (pdf, youtube, markdown, other).

    Pure function — no I/O.

    Args:
        sources: List of source dicts with 'source_path' key

    Returns:
        Dict mapping type name → total chunk count
    """
    type_counts: dict[str, int] = {"pdf": 0, "youtube": 0, "markdown": 0, "other": 0}
    for src in sources:
        path = str(src.get("source_path", "")).lower()
        count = int(src.get("chunk_count", 0))
        if path.endswith(".pdf"):
            type_counts["pdf"] += count
        elif "youtube" in path or path.endswith(".txt") and "yt_" in path:
            type_counts["youtube"] += count
        elif path.endswith(".md"):
            type_counts["markdown"] += count
        else:
            type_counts["other"] += count
    return type_counts


# ---------------------------------------------------------------------------
# setlist resource
# ---------------------------------------------------------------------------


def read_setlist() -> str:
    """
    Read the current setlist draft (session notes tagged 'setlist').

    Setlists are stored as session notes with the 'setlist' tag.
    This resource returns all such notes, ordered by creation date.

    Returns:
        JSON string with keys: setlist_notes, total, last_updated
    """
    if not _NOTES_FILE.exists():
        return json.dumps({"setlist_notes": [], "total": 0, "last_updated": None})

    try:
        raw = json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read setlist: %s", exc)
        return json.dumps(
            {"setlist_notes": [], "total": 0, "last_updated": None, "error": str(exc)}
        )

    notes: list[dict[str, Any]] = raw if isinstance(raw, list) else []

    setlist_notes = [n for n in notes if "setlist" in (n.get("tags") or [])]

    last_updated: str | None = None
    if setlist_notes:
        dates = [str(n.get("created_at") or n.get("date") or "") for n in setlist_notes]
        valid_dates = [d for d in dates if d]
        last_updated = max(valid_dates) if valid_dates else None

    return json.dumps(
        {
            "setlist_notes": setlist_notes,
            "total": len(setlist_notes),
            "last_updated": last_updated,
        },
        indent=2,
        default=str,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _empty_paginated(item_key: str) -> str:
    """Return a valid empty paginated response JSON string."""
    return json.dumps(
        {
            item_key: [],
            "total": 0,
            "offset": 0,
            "limit": _DEFAULT_LIMIT,
        }
    )


def _error_response(item_key: str, error: str) -> str:
    """Return a valid error response JSON string — always parseable."""
    return json.dumps(
        {
            item_key: [],
            "total": 0,
            "offset": 0,
            "limit": _DEFAULT_LIMIT,
            "error": error,
        }
    )
