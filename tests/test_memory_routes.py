"""Tests for /memory CRUD endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.deps import get_embedding_provider, get_memory_store
from api.main import app
from ingestion.memory_store import MemoryStore

FROZEN_NOW = datetime(2026, 2, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def tmp_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(db_path=tmp_path / "test_routes_memory.db")


@pytest.fixture()
def fake_embedder() -> MagicMock:
    mock = MagicMock()
    mock.embed_texts.return_value = [[0.1] * 1536]
    return mock


@pytest.fixture(autouse=True)
def _setup_and_teardown(tmp_store: MemoryStore, fake_embedder: MagicMock):  # type: ignore[no-untyped-def]
    app.dependency_overrides.clear()
    app.dependency_overrides[get_memory_store] = lambda: tmp_store
    app.dependency_overrides[get_embedding_provider] = lambda: fake_embedder
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


class TestMemoryListEndpoint:
    def test_list_empty_returns_200(self) -> None:
        resp = client.get("/memory/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["total"] == 0

    def test_list_returns_saved_entries(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("preference", "prefer A minor", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.get("/memory/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_filtered_by_type(self, tmp_store: MemoryStore) -> None:
        pref = tmp_store.create_entry("preference", "pref content", FROZEN_NOW)
        sess = tmp_store.create_entry("session", "session content", FROZEN_NOW)
        tmp_store.save(pref)
        tmp_store.save(sess)
        resp = client.get("/memory/?memory_type=preference")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["entries"][0]["memory_type"] == "preference"


class TestMemoryCreateEndpoint:
    def test_create_returns_201(self) -> None:
        resp = client.post(
            "/memory/", json={"memory_type": "preference", "content": "I prefer A minor"}
        )
        assert resp.status_code == 201

    def test_create_response_has_correct_fields(self) -> None:
        resp = client.post("/memory/", json={"memory_type": "session", "content": "FM discovery"})
        data = resp.json()
        assert "memory_id" in data
        assert data["memory_type"] == "session"
        assert data["content"] == "FM discovery"
        assert data["source"] == "manual"

    def test_create_invalid_type_returns_422(self) -> None:
        resp = client.post("/memory/", json={"memory_type": "invalid", "content": "test"})
        assert resp.status_code == 422

    def test_create_empty_content_returns_422(self) -> None:
        resp = client.post("/memory/", json={"memory_type": "preference", "content": ""})
        assert resp.status_code == 422

    def test_create_calls_embedder(self, fake_embedder: MagicMock) -> None:
        client.post("/memory/", json={"memory_type": "preference", "content": "test content"})
        fake_embedder.embed_texts.assert_called_once_with(["test content"])

    def test_create_with_tags(self) -> None:
        resp = client.post(
            "/memory/",
            json={
                "memory_type": "creative",
                "content": "try granular reverb",
                "tags": ["reverb", "granular"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "reverb" in data["tags"]
        assert "granular" in data["tags"]

    def test_create_pinned_entry(self) -> None:
        resp = client.post(
            "/memory/",
            json={"memory_type": "preference", "content": "always use 24-bit", "pinned": True},
        )
        assert resp.status_code == 201
        assert resp.json()["pinned"] is True


class TestMemoryGetEndpoint:
    def test_get_existing_returns_200(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("growth", "improved EQ skills", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.get(f"/memory/{entry.memory_id}")
        assert resp.status_code == 200
        assert resp.json()["memory_id"] == entry.memory_id

    def test_get_missing_returns_404(self) -> None:
        resp = client.get("/memory/nonexistent-id")
        assert resp.status_code == 404

    def test_get_returns_correct_content(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("session", "discovered sidechain trick", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.get(f"/memory/{entry.memory_id}")
        assert resp.json()["content"] == "discovered sidechain trick"


class TestMemoryUpdateEndpoint:
    def test_update_changes_content(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("preference", "original", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.patch(f"/memory/{entry.memory_id}", json={"content": "updated content"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "updated content"

    def test_update_missing_returns_404(self) -> None:
        resp = client.patch("/memory/nonexistent", json={"content": "new"})
        assert resp.status_code == 404

    def test_update_empty_content_returns_422(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("preference", "something", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.patch(f"/memory/{entry.memory_id}", json={"content": ""})
        assert resp.status_code == 422


class TestMemoryDeleteEndpoint:
    def test_delete_returns_204(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("creative", "idea", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.delete(f"/memory/{entry.memory_id}")
        assert resp.status_code == 204

    def test_delete_missing_returns_404(self) -> None:
        resp = client.delete("/memory/nonexistent")
        assert resp.status_code == 404

    def test_delete_removes_entry(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("session", "to delete", FROZEN_NOW)
        tmp_store.save(entry)
        client.delete(f"/memory/{entry.memory_id}")
        assert tmp_store.get(entry.memory_id) is None


class TestMemoryPinEndpoints:
    def test_pin_sets_pinned_true(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("creative", "idea", FROZEN_NOW)
        tmp_store.save(entry)
        resp = client.post(f"/memory/{entry.memory_id}/pin")
        assert resp.status_code == 200
        assert resp.json()["pinned"] is True

    def test_unpin_sets_pinned_false(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("creative", "idea", FROZEN_NOW, pinned=True)
        tmp_store.save(entry)
        resp = client.delete(f"/memory/{entry.memory_id}/pin")
        assert resp.status_code == 200
        assert resp.json()["pinned"] is False

    def test_pin_missing_returns_404(self) -> None:
        resp = client.post("/memory/nonexistent/pin")
        assert resp.status_code == 404

    def test_unpin_missing_returns_404(self) -> None:
        resp = client.delete("/memory/nonexistent/pin")
        assert resp.status_code == 404

    def test_pin_persists_to_store(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("preference", "test", FROZEN_NOW)
        tmp_store.save(entry)
        client.post(f"/memory/{entry.memory_id}/pin")
        stored = tmp_store.get(entry.memory_id)
        assert stored is not None
        assert stored.pinned is True


class TestMemorySearchEndpoint:
    def test_search_returns_200(self, tmp_store: MemoryStore) -> None:
        entry = tmp_store.create_entry("preference", "A minor preference", FROZEN_NOW)
        tmp_store.save(entry, embedding=[0.1] * 1536)
        resp = client.post("/memory/search", json={"query": "what key do I prefer?"})
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_search_empty_store_returns_empty(self) -> None:
        resp = client.post("/memory/search", json={"query": "anything"})
        assert resp.status_code == 200
        assert resp.json()["entries"] == []
        assert resp.json()["total"] == 0

    def test_search_respects_top_k(self, tmp_store: MemoryStore) -> None:
        for i in range(5):
            e = tmp_store.create_entry("preference", f"preference {i}", FROZEN_NOW)
            tmp_store.save(e, embedding=[0.1] * 1536)
        resp = client.post("/memory/search", json={"query": "preference", "top_k": 2})
        assert resp.status_code == 200
        assert resp.json()["total"] <= 2

    def test_search_invalid_top_k_returns_422(self) -> None:
        resp = client.post("/memory/search", json={"query": "test", "top_k": 0})
        assert resp.status_code == 422

    def test_search_calls_embedder(self, fake_embedder: MagicMock) -> None:
        client.post("/memory/search", json={"query": "some query"})
        fake_embedder.embed_texts.assert_called_once_with(["some query"])
