"""Tests for ingestion/memory_store.py"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ingestion.memory_store import MemoryStore

FROZEN_NOW = datetime(2026, 2, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "test_memory.db")


class TestMemoryStoreCRUD:
    def test_save_and_get_roundtrip(self, store: MemoryStore) -> None:
        entry = store.create_entry("preference", "I prefer A minor", FROZEN_NOW)
        store.save(entry)
        retrieved = store.get(entry.memory_id)
        assert retrieved is not None
        assert retrieved.content == "I prefer A minor"
        assert retrieved.memory_type == "preference"

    def test_get_missing_returns_none(self, store: MemoryStore) -> None:
        assert store.get("nonexistent-id") is None

    def test_delete_existing_returns_true(self, store: MemoryStore) -> None:
        entry = store.create_entry("session", "test session", FROZEN_NOW)
        store.save(entry)
        assert store.delete(entry.memory_id) is True

    def test_delete_missing_returns_false(self, store: MemoryStore) -> None:
        assert store.delete("nonexistent-id") is False

    def test_delete_removes_entry(self, store: MemoryStore) -> None:
        entry = store.create_entry("session", "to be deleted", FROZEN_NOW)
        store.save(entry)
        store.delete(entry.memory_id)
        assert store.get(entry.memory_id) is None

    def test_update_changes_content(self, store: MemoryStore) -> None:
        entry = store.create_entry("preference", "original content", FROZEN_NOW)
        store.save(entry)
        updated = store.update(entry.memory_id, "new content", FROZEN_NOW)
        assert updated.content == "new content"

    def test_update_missing_raises_key_error(self, store: MemoryStore) -> None:
        with pytest.raises(KeyError):
            store.update("nonexistent", "content", FROZEN_NOW)

    def test_list_all_returns_all_saved(self, store: MemoryStore) -> None:
        for i in range(5):
            e = store.create_entry("session", f"entry {i}", FROZEN_NOW)
            store.save(e)
        assert len(store.list_all()) == 5

    def test_list_by_type_filters(self, store: MemoryStore) -> None:
        pref = store.create_entry("preference", "pref content", FROZEN_NOW)
        sess = store.create_entry("session", "session content", FROZEN_NOW)
        store.save(pref)
        store.save(sess)
        prefs = store.list_by_type("preference")
        assert len(prefs) == 1
        assert prefs[0].memory_type == "preference"

    def test_set_pinned_true(self, store: MemoryStore) -> None:
        entry = store.create_entry("creative", "idea", FROZEN_NOW)
        store.save(entry)
        result = store.set_pinned(entry.memory_id, True)
        assert result is True
        updated = store.get(entry.memory_id)
        assert updated is not None
        assert updated.pinned is True

    def test_set_pinned_missing_returns_false(self, store: MemoryStore) -> None:
        assert store.set_pinned("nonexistent", True) is False


class TestCreateEntry:
    def test_generates_unique_ids(self, store: MemoryStore) -> None:
        e1 = store.create_entry("session", "a", FROZEN_NOW)
        e2 = store.create_entry("session", "b", FROZEN_NOW)
        assert e1.memory_id != e2.memory_id

    def test_created_at_matches_now(self, store: MemoryStore) -> None:
        e = store.create_entry("preference", "test", FROZEN_NOW)
        assert e.created_at == FROZEN_NOW.isoformat()

    def test_default_source_is_auto(self, store: MemoryStore) -> None:
        e = store.create_entry("session", "test", FROZEN_NOW)
        assert e.source == "auto"

    def test_manual_source_stored(self, store: MemoryStore) -> None:
        e = store.create_entry("preference", "test", FROZEN_NOW, source="manual")
        store.save(e)
        retrieved = store.get(e.memory_id)
        assert retrieved is not None
        assert retrieved.source == "manual"


class TestMemoryStoreSearch:
    def test_search_returns_top_k(self, store: MemoryStore) -> None:
        emb = [0.1] * 1536
        for i in range(10):
            e = store.create_entry("preference", f"memory {i}", FROZEN_NOW)
            store.save(e, embedding=emb)
        results = store.search_relevant(emb, FROZEN_NOW, top_k=3)
        assert len(results) <= 3

    def test_search_skips_entries_without_embedding(self, store: MemoryStore) -> None:
        e = store.create_entry("preference", "no embedding", FROZEN_NOW)
        store.save(e)  # no embedding
        results = store.search_relevant([0.1] * 1536, FROZEN_NOW, top_k=5)
        assert all(entry.memory_id != e.memory_id for entry, _ in results)

    def test_search_filters_expired_session(self, store: MemoryStore) -> None:
        old_time = FROZEN_NOW - timedelta(days=40)
        e = store.create_entry("session", "expired session", old_time)
        store.save(e, embedding=[0.1] * 1536)
        results = store.search_relevant([0.1] * 1536, FROZEN_NOW, top_k=5)
        expired_ids = [entry.memory_id for entry, _ in results]
        assert e.memory_id not in expired_ids

    def test_search_filters_by_memory_types(self, store: MemoryStore) -> None:
        pref = store.create_entry("preference", "pref", FROZEN_NOW)
        sess = store.create_entry("session", "sess", FROZEN_NOW)
        store.save(pref, embedding=[0.1] * 1536)
        store.save(sess, embedding=[0.1] * 1536)
        results = store.search_relevant([0.1] * 1536, FROZEN_NOW, memory_types=["preference"])
        types_returned = {e.memory_type for e, _ in results}
        assert "session" not in types_returned

    def test_search_scores_in_range(self, store: MemoryStore) -> None:
        e = store.create_entry("growth", "growth milestone", FROZEN_NOW)
        store.save(e, embedding=[1.0] + [0.0] * 1535)
        results = store.search_relevant([1.0] + [0.0] * 1535, FROZEN_NOW, top_k=1)
        assert len(results) == 1
        _, score = results[0]
        assert 0.0 <= score <= 1.0

    def test_search_returns_empty_when_no_entries(self, store: MemoryStore) -> None:
        results = store.search_relevant([0.1] * 1536, FROZEN_NOW)
        assert results == []

    def test_search_min_score_excludes_low_scoring_entries(self, store: MemoryStore) -> None:
        """Entries whose cosine*decay < min_score are silenced (trigger threshold)."""
        # orthogonal embedding → cosine ≈ 0.0, score < 0.35
        e = store.create_entry("preference", "orthogonal memory", FROZEN_NOW)
        store.save(e, embedding=[1.0] + [0.0] * 1535)
        # query points in completely different direction
        results = store.search_relevant(
            [0.0] * 1535 + [1.0],
            FROZEN_NOW,
            min_score=0.35,
        )
        assert all(entry.memory_id != e.memory_id for entry, _ in results)

    def test_search_min_score_zero_returns_all_with_embedding(self, store: MemoryStore) -> None:
        """min_score=0.0 disables the trigger — all entries with embeddings are returned."""
        emb = [0.1] * 1536
        entries = [store.create_entry("preference", f"mem {i}", FROZEN_NOW) for i in range(3)]
        for e in entries:
            store.save(e, embedding=emb)
        results = store.search_relevant(emb, FROZEN_NOW, min_score=0.0)
        assert len(results) == 3
