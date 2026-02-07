"""
Tests for core.chunking module.

These tests verify the token-based chunking implementation is correct,
deterministic, and handles edge cases properly.
"""

import pytest
import tiktoken

from core.chunking import chunk_text

ENCODING_NAME = "cl100k_base"
ENCODING = tiktoken.get_encoding(ENCODING_NAME)


class TestEmptyInput:
    """Test that empty or whitespace-only text returns an empty list."""

    def test_empty_string_returns_empty_list(self) -> None:
        assert chunk_text("", source_path="/docs/test.txt") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert chunk_text("   \n\t", source_path="/docs/test.txt") == []


class TestOverlapValidation:
    """Test that overlap >= chunk_size raises ValueError."""

    def test_overlap_equal_to_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("text", source_path="/x", chunk_size=10, overlap=10)

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("text", source_path="/x", chunk_size=10, overlap=20)


class TestTokenInvariant:
    """
    Core invariant: encode(chunk.text) == doc_tokens[token_start:token_end].

    This is the fundamental correctness property of token-based chunking.
    """

    def test_chunk_tokens_equal_document_slice(self) -> None:
        text = "The quick brown fox jumps over the lazy dog. " * 50
        doc_tokens = ENCODING.encode(text)

        chunks = chunk_text(
            text,
            source_path="/docs/test.txt",
            chunk_size=50,
            overlap=10,
        )

        for chunk in chunks:
            chunk_tokens = ENCODING.encode(chunk.text)
            expected_tokens = doc_tokens[chunk.token_start : chunk.token_end]
            assert (
                chunk_tokens == expected_tokens
            ), f"Chunk {chunk.chunk_index}: tokens mismatch at [{chunk.token_start}:{chunk.token_end}]"


class TestOverlapCorrectness:
    """Test that consecutive chunks overlap by exactly the specified amount."""

    def test_token_spans_overlap_correctly(self) -> None:
        text = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta " * 30
        overlap = 15
        chunk_size = 50

        chunks = chunk_text(
            text,
            source_path="/docs/test.txt",
            chunk_size=chunk_size,
            overlap=overlap,
        )

        assert len(chunks) >= 2

        for i in range(len(chunks) - 1):
            current = chunks[i]
            next_ = chunks[i + 1]

            # Next chunk starts exactly `overlap` tokens before current ends
            assert next_.token_start == current.token_end - overlap

    def test_overlapping_text_matches(self) -> None:
        """Verify the actual text in overlap regions is identical."""
        text = "word " * 200
        doc_tokens = ENCODING.encode(text)
        overlap = 10

        chunks = chunk_text(
            text,
            source_path="/docs/test.txt",
            chunk_size=50,
            overlap=overlap,
        )

        for i in range(len(chunks) - 1):
            current = chunks[i]
            next_ = chunks[i + 1]

            # The overlap region spans from next_.token_start to current.token_end
            overlap_start = next_.token_start
            overlap_end = current.token_end
            actual_overlap_size = overlap_end - overlap_start
            expected_overlap_tokens = doc_tokens[overlap_start:overlap_end]

            # Verify both chunks contain this overlap
            current_tokens = ENCODING.encode(current.text)
            next_tokens = ENCODING.encode(next_.text)

            assert current_tokens[-actual_overlap_size:] == expected_overlap_tokens
            assert next_tokens[:actual_overlap_size] == expected_overlap_tokens


class TestMonotonicity:
    """Test that token spans are strictly monotonic."""

    def test_token_start_strictly_increases(self) -> None:
        text = "Testing monotonicity of token spans. " * 50
        chunks = chunk_text(
            text,
            source_path="/docs/test.txt",
            chunk_size=40,
            overlap=10,
        )

        for i in range(len(chunks) - 1):
            assert chunks[i + 1].token_start > chunks[i].token_start

    def test_chunk_index_sequential(self) -> None:
        text = "Sequential index test. " * 100
        chunks = chunk_text(text, source_path="/docs/test.txt", chunk_size=30, overlap=5)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestCoverage:
    """Test that chunks fully cover the document."""

    def test_first_chunk_starts_at_zero(self) -> None:
        chunks = chunk_text("Any text here.", source_path="/docs/test.txt")
        assert chunks[0].token_start == 0

    def test_last_chunk_ends_at_total_tokens(self) -> None:
        text = "Coverage test content. " * 40
        total_tokens = len(ENCODING.encode(text))

        chunks = chunk_text(text, source_path="/docs/test.txt", chunk_size=50, overlap=10)

        assert chunks[-1].token_end == total_tokens


class TestMetadata:
    """Test that metadata fields populate correctly."""

    def test_explicit_doc_id_preserved(self) -> None:
        chunks = chunk_text(
            "Some content.",
            source_path="/docs/test.txt",
            doc_id="explicit-id-123",
        )
        assert chunks[0].doc_id == "explicit-id-123"

    def test_auto_generated_doc_id_is_deterministic(self) -> None:
        text = "Deterministic ID test."
        path = "/docs/test.txt"

        chunks1 = chunk_text(text, source_path=path)
        chunks2 = chunk_text(text, source_path=path)

        assert chunks1[0].doc_id == chunks2[0].doc_id

    def test_auto_generated_doc_id_differs_for_different_content(self) -> None:
        path = "/docs/test.txt"

        chunks1 = chunk_text("Content A", source_path=path)
        chunks2 = chunk_text("Content B", source_path=path)

        assert chunks1[0].doc_id != chunks2[0].doc_id

    def test_source_name_is_basename(self) -> None:
        chunks = chunk_text(
            "Some content.",
            source_path="/very/deep/path/to/document.pdf",
        )
        assert chunks[0].source_name == "document.pdf"

    def test_source_name_with_trailing_slash(self) -> None:
        """Test that trailing slashes are stripped before extracting basename."""
        chunks = chunk_text(
            "Some content.",
            source_path="/path/to/file.txt/",
        )
        assert chunks[0].source_name == "file.txt"

    def test_source_name_with_multiple_trailing_slashes(self) -> None:
        """Test that multiple trailing slashes are handled correctly."""
        chunks = chunk_text(
            "Some content.",
            source_path="/path/to/file.txt///",
        )
        assert chunks[0].source_name == "file.txt"

    def test_source_name_without_path_separator(self) -> None:
        """Test that a filename without path separator is returned as-is."""
        chunks = chunk_text(
            "Some content.",
            source_path="file.txt",
        )
        assert chunks[0].source_name == "file.txt"

    def test_source_name_root_path(self) -> None:
        """Test edge case of root path returns empty string."""
        chunks = chunk_text(
            "Some content.",
            source_path="/",
        )
        assert chunks[0].source_name == ""

    def test_source_path_preserved(self) -> None:
        path = "/path/to/file.txt"
        chunks = chunk_text("Content.", source_path=path)
        assert chunks[0].source_path == path


class TestEncodingParameter:
    """Test that encoding_name affects tokenization."""

    def test_different_encodings_produce_different_token_counts(self) -> None:
        # This text tokenizes differently across encodings
        text = "Testing encoding differences: émojis 🎉 and unicode →�"

        chunks_cl100k = chunk_text(
            text,
            source_path="/docs/test.txt",
            encoding_name="cl100k_base",
        )

        chunks_p50k = chunk_text(
            text,
            source_path="/docs/test.txt",
            encoding_name="p50k_base",
        )

        # Verify each uses its own encoding's token count
        cl100k_count = len(tiktoken.get_encoding("cl100k_base").encode(text))
        p50k_count = len(tiktoken.get_encoding("p50k_base").encode(text))

        assert chunks_cl100k[0].token_end == cl100k_count
        assert chunks_p50k[0].token_end == p50k_count
