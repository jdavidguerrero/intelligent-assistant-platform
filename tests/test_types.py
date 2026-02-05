"""
Tests for core.types module.

These tests verify the protocol definitions and conversion utilities.
"""

from dataclasses import dataclass

import pytest

from core.types import ChunkDict, ChunkProtocol, chunk_to_dict
from core.chunking import Chunk, chunk_text


class TestChunkProtocol:
    """Test that ChunkProtocol works as expected."""

    def test_core_chunk_satisfies_protocol(self) -> None:
        chunks = chunk_text("Hello world", source_path="/test.txt")
        chunk = chunks[0]

        # Runtime check
        assert isinstance(chunk, ChunkProtocol)

    def test_custom_class_satisfies_protocol(self) -> None:
        @dataclass
        class CustomChunk:
            doc_id: str
            chunk_index: int
            text: str

        custom = CustomChunk(doc_id="abc", chunk_index=0, text="hello")
        assert isinstance(custom, ChunkProtocol)


class TestChunkToDict:
    """Test chunk_to_dict conversion function."""

    def test_converts_core_chunk(self) -> None:
        chunks = chunk_text("Hello world", source_path="/path/to/doc.txt", doc_id="doc-123")
        chunk = chunks[0]

        result = chunk_to_dict(chunk)

        assert result["doc_id"] == "doc-123"
        assert result["source_path"] == "/path/to/doc.txt"
        assert result["source_name"] == "doc.txt"
        assert result["chunk_index"] == 0
        assert result["text"] == "Hello world"
        assert result["token_start"] == 0
        assert result["token_end"] > 0

    def test_override_fields(self) -> None:
        chunks = chunk_text("Hello", source_path="/test.txt")
        chunk = chunks[0]

        result = chunk_to_dict(
            chunk,
            source_path="/override/path.txt",
            source_name="override.txt",
            token_start=100,
            token_end=200,
        )

        assert result["source_path"] == "/override/path.txt"
        assert result["source_name"] == "override.txt"
        assert result["token_start"] == 100
        assert result["token_end"] == 200

    def test_works_with_minimal_protocol_object(self) -> None:
        @dataclass
        class MinimalChunk:
            doc_id: str
            chunk_index: int
            text: str

        minimal = MinimalChunk(doc_id="min-id", chunk_index=5, text="minimal text")

        result = chunk_to_dict(
            minimal,
            source_path="/provided/path.txt",
            source_name="provided.txt",
            token_start=0,
            token_end=10,
        )

        assert result["doc_id"] == "min-id"
        assert result["chunk_index"] == 5
        assert result["text"] == "minimal text"
        assert result["source_path"] == "/provided/path.txt"


class TestChunkDict:
    """Test ChunkDict TypedDict structure."""

    def test_chunk_dict_has_all_required_keys(self) -> None:
        # This is a compile-time check, but we can verify at runtime too
        chunk_dict: ChunkDict = {
            "doc_id": "test",
            "source_path": "/path",
            "source_name": "name",
            "chunk_index": 0,
            "text": "content",
            "token_start": 0,
            "token_end": 10,
        }

        assert "doc_id" in chunk_dict
        assert "source_path" in chunk_dict
        assert "source_name" in chunk_dict
        assert "chunk_index" in chunk_dict
        assert "text" in chunk_dict
        assert "token_start" in chunk_dict
        assert "token_end" in chunk_dict
