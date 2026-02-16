"""
Tests for ingestion pipeline helper functions.

Tests retry logic and quality gate without requiring database or OpenAI API.
"""

from unittest.mock import MagicMock, patch

import pytest

from ingestion.ingest import MIN_CHUNK_TOKENS, _embed_with_retry, _extract_text
from ingestion.loaders import LoadedDocument


class TestEmbedWithRetry:
    """Test exponential backoff retry for embedding calls."""

    def test_succeeds_on_first_try(self) -> None:
        embedder = MagicMock()
        embedder.embed_texts.return_value = [[0.1, 0.2]]
        result = _embed_with_retry(embedder, ["hello"], max_retries=3, base_seconds=0.0)
        assert result == [[0.1, 0.2]]
        assert embedder.embed_texts.call_count == 1

    @patch("ingestion.ingest.time.sleep")
    def test_retries_on_failure_then_succeeds(self, mock_sleep: MagicMock) -> None:
        embedder = MagicMock()
        embedder.embed_texts.side_effect = [
            RuntimeError("rate limit"),
            [[0.1, 0.2]],
        ]
        result = _embed_with_retry(embedder, ["hello"], max_retries=3, base_seconds=0.01)
        assert result == [[0.1, 0.2]]
        assert embedder.embed_texts.call_count == 2
        mock_sleep.assert_called_once()

    @patch("ingestion.ingest.time.sleep")
    def test_raises_after_exhausting_retries(self, mock_sleep: MagicMock) -> None:
        embedder = MagicMock()
        embedder.embed_texts.side_effect = RuntimeError("always fails")
        with pytest.raises(RuntimeError, match="Embedding failed after 2 attempts"):
            _embed_with_retry(embedder, ["hello"], max_retries=2, base_seconds=0.01)
        assert embedder.embed_texts.call_count == 2

    @patch("ingestion.ingest.time.sleep")
    def test_backoff_increases_exponentially(self, mock_sleep: MagicMock) -> None:
        embedder = MagicMock()
        embedder.embed_texts.side_effect = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            RuntimeError("fail 3"),
        ]
        with pytest.raises(RuntimeError):
            _embed_with_retry(embedder, ["hello"], max_retries=3, base_seconds=1.0)

        # Check sleep durations: 1*2^0=1.0, 1*2^1=2.0, 1*2^2=4.0
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 2.0, 4.0]


class TestExtractTextDispatcher:
    """Test that _extract_text delegates to the correct core strategy."""

    def test_markdown_file(self) -> None:
        doc = LoadedDocument(path="/data/doc.md", name="doc.md", content="**bold**")
        result = _extract_text(doc)
        assert "**" not in result
        assert "bold" in result

    def test_txt_file(self) -> None:
        doc = LoadedDocument(path="/data/doc.txt", name="doc.txt", content="hello    world")
        result = _extract_text(doc)
        assert result == "hello world"


class TestMinChunkTokensConstant:
    """Verify the quality gate constant is sensible."""

    def test_min_chunk_tokens_is_positive(self) -> None:
        assert MIN_CHUNK_TOKENS > 0

    def test_min_chunk_tokens_is_reasonable(self) -> None:
        # Should be small enough to not drop real content
        assert MIN_CHUNK_TOKENS <= 50
