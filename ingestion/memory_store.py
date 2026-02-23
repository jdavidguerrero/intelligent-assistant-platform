"""SQLite-backed store for musical memory entries.

Local-first: data/memory.db stays on disk, never sent to Supabase.
Embeddings stored as JSON-serialized float arrays (TEXT column).
Cosine similarity computed in Python stdlib (math) — linear scan is
fine for <10K personal memory entries.

Schema (auto-created on first use):
    memory_entries(
        memory_id TEXT PK,
        memory_type TEXT,
        content TEXT,
        created_at TEXT,
        updated_at TEXT,
        pinned INTEGER,
        tags TEXT,       -- JSON array
        source TEXT,
        embedding TEXT   -- JSON float array, nullable
    )
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from core.memory.decay import compute_decay_weight, filter_active_memories
from core.memory.types import MemoryEntry, MemoryType

DEFAULT_DB_PATH = Path("data/memory.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_entries (
    memory_id   TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    pinned      INTEGER NOT NULL DEFAULT 0,
    tags        TEXT NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL DEFAULT 'auto',
    embedding   TEXT
);
"""


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in pure Python. Returns 0.0 for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    """Convert a SQLite row to a MemoryEntry."""
    return MemoryEntry(
        memory_id=row["memory_id"],
        memory_type=row["memory_type"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        pinned=bool(row["pinned"]),
        tags=tuple(json.loads(row["tags"])),
        source=row["source"],
    )


class MemoryStore:
    """SQLite-backed persistent store for MemoryEntry objects.

    Thread-safety: uses WAL mode + check_same_thread=False.
    Suitable for single-process FastAPI servers.

    Args:
        db_path: Path to the SQLite database file. Created on first use.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    # ------------------------------------------------------------------ #
    # CRUD                                                                 #
    # ------------------------------------------------------------------ #

    def save(self, entry: MemoryEntry, embedding: list[float] | None = None) -> None:
        """Persist a MemoryEntry, optionally with its embedding vector.

        If an entry with the same memory_id already exists, it is replaced.

        Args:
            entry: The MemoryEntry to save.
            embedding: Optional 1536-dim embedding for semantic search.
        """
        emb_json = json.dumps(embedding) if embedding is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_entries
                    (memory_id, memory_type, content, created_at, updated_at,
                     pinned, tags, source, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.memory_id,
                    entry.memory_type,
                    entry.content,
                    entry.created_at,
                    entry.updated_at,
                    int(entry.pinned),
                    json.dumps(list(entry.tags)),
                    entry.source,
                    emb_json,
                ),
            )
            conn.commit()

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Fetch a single entry by ID. Returns None if not found.

        Args:
            memory_id: The UUID string of the entry.

        Returns:
            MemoryEntry or None.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        return _row_to_entry(row) if row else None

    def update(self, memory_id: str, content: str, now: datetime) -> MemoryEntry:
        """Update the content of an existing entry and refresh updated_at.

        Args:
            memory_id: ID of the entry to update.
            content: New content string.
            now: Current datetime (caller supplies — no datetime.now() here).

        Returns:
            Updated MemoryEntry.

        Raises:
            KeyError: If memory_id does not exist.
            ValueError: If content is invalid.
        """
        if not content.strip():
            raise ValueError("content must not be empty")
        if len(content) > 2000:
            raise ValueError(f"content must be <= 2000 chars, got {len(content)}")
        updated_at = now.isoformat()
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE memory_entries SET content = ?, updated_at = ? WHERE memory_id = ?",
                (content, updated_at, memory_id),
            )
            conn.commit()
            if result.rowcount == 0:
                raise KeyError(f"memory_id not found: {memory_id!r}")
        entry = self.get(memory_id)
        assert entry is not None  # just updated
        return entry

    def delete(self, memory_id: str) -> bool:
        """Delete an entry permanently.

        Args:
            memory_id: ID to delete.

        Returns:
            True if an entry was deleted, False if not found.
        """
        with self._connect() as conn:
            result = conn.execute("DELETE FROM memory_entries WHERE memory_id = ?", (memory_id,))
            conn.commit()
        return result.rowcount > 0

    def list_all(self) -> list[MemoryEntry]:
        """Return all entries, unordered.

        Returns:
            List of MemoryEntry objects.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory_entries").fetchall()
        return [_row_to_entry(r) for r in rows]

    def list_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Return all entries of a specific type.

        Args:
            memory_type: One of preference | session | growth | creative.

        Returns:
            Filtered list of MemoryEntry objects.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_entries WHERE memory_type = ?", (memory_type,)
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def set_pinned(self, memory_id: str, pinned: bool) -> bool:
        """Pin or unpin an entry (pinned entries never decay).

        Args:
            memory_id: ID of the entry.
            pinned: True to pin, False to unpin.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE memory_entries SET pinned = ? WHERE memory_id = ?",
                (int(pinned), memory_id),
            )
            conn.commit()
        return result.rowcount > 0

    def create_entry(
        self,
        memory_type: MemoryType,
        content: str,
        now: datetime,
        tags: tuple[str, ...] = (),
        source: str = "auto",
        pinned: bool = False,
    ) -> MemoryEntry:
        """Factory: create a MemoryEntry with a new UUID and timestamps.

        Does NOT persist — call save() after to write to DB.

        Args:
            memory_type: Type of memory.
            content: Memory content.
            now: Current datetime. Caller supplies — no datetime.now() here.
            tags: Optional keyword tags.
            source: "auto" or "manual".
            pinned: Whether to pin immediately.

        Returns:
            New MemoryEntry (not yet persisted).
        """
        iso_now = now.isoformat()
        return MemoryEntry(
            memory_id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content,
            created_at=iso_now,
            updated_at=iso_now,
            pinned=pinned,
            tags=tags,
            source=source,
        )

    # ------------------------------------------------------------------ #
    # Semantic search with decay weighting                                 #
    # ------------------------------------------------------------------ #

    def search_relevant(
        self,
        query_embedding: list[float],
        now: datetime,
        top_k: int = 5,
        memory_types: list[MemoryType] | None = None,
        min_score: float = 0.35,
    ) -> list[tuple[MemoryEntry, float]]:
        """Find memories semantically relevant to a query, weighted by decay.

        Algorithm:
        1. Load all entries from SQLite
        2. filter_active_memories() removes expired entries
        3. For each active entry with an embedding: score = cosine * decay_weight
        4. Filter out entries with score < min_score (memory trigger threshold)
        5. Sort descending, return top_k

        Args:
            query_embedding: 1536-dim embedding of the current query.
            now: Current timezone-aware datetime.
            top_k: Maximum results to return.
            memory_types: Optional filter — only consider these types.
            min_score: Minimum combined score (cosine * decay) to surface a memory.
                Entries below this threshold are silenced even if they exist.
                Default 0.35 prevents tangentially-related memories from leaking
                into unrelated queries.

        Returns:
            List of (MemoryEntry, score) tuples, sorted by score descending.
            Score is in [0.0, 1.0] (cosine * decay_weight).
        """
        all_entries = self.list_all()
        active = filter_active_memories(all_entries, now)

        if memory_types:
            active = [e for e in active if e.memory_type in memory_types]

        # Load embeddings in one pass
        with self._connect() as conn:
            rows = conn.execute("SELECT memory_id, embedding FROM memory_entries").fetchall()
        embedding_map: dict[str, list[float]] = {}
        for row in rows:
            if row["embedding"]:
                embedding_map[row["memory_id"]] = json.loads(row["embedding"])

        scored: list[tuple[MemoryEntry, float]] = []
        for entry in active:
            emb = embedding_map.get(entry.memory_id)
            if emb is None:
                continue
            cosine = _cosine(query_embedding, emb)
            decay = compute_decay_weight(entry, now).effective_weight
            score = round(cosine * decay, 4)
            if score >= min_score:
                scored.append((entry, score))

        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]
