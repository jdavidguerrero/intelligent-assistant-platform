"""
Tests for core.config module.

These tests verify ChunkingConfig validation and predefined configurations.
"""

import pytest

from core.config import (
    ChunkingConfig,
    DEFAULT_CONFIG,
    SMALL_CHUNK_CONFIG,
    LARGE_CHUNK_CONFIG,
    NO_OVERLAP_CONFIG,
)


class TestChunkingConfigValidation:
    """Test ChunkingConfig parameter validation."""

    def test_default_values(self) -> None:
        config = ChunkingConfig()
        assert config.chunk_size == 512
        assert config.overlap == 50
        assert config.encoding_name == "cl100k_base"

    def test_custom_values(self) -> None:
        config = ChunkingConfig(chunk_size=256, overlap=25, encoding_name="p50k_base")
        assert config.chunk_size == 256
        assert config.overlap == 25
        assert config.encoding_name == "p50k_base"

    def test_overlap_equal_to_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            ChunkingConfig(chunk_size=100, overlap=100)

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            ChunkingConfig(chunk_size=50, overlap=100)

    def test_negative_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingConfig(chunk_size=-10, overlap=5)

    def test_zero_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingConfig(chunk_size=0, overlap=0)

    def test_negative_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            ChunkingConfig(chunk_size=100, overlap=-5)

    def test_zero_overlap_is_valid(self) -> None:
        config = ChunkingConfig(chunk_size=100, overlap=0)
        assert config.overlap == 0


class TestChunkingConfigImmutability:
    """Test that ChunkingConfig is frozen."""

    def test_cannot_modify_chunk_size(self) -> None:
        config = ChunkingConfig()
        with pytest.raises(AttributeError):
            config.chunk_size = 1024  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        config = ChunkingConfig()
        # Should not raise
        config_set = {config}
        assert len(config_set) == 1


class TestPredefinedConfigs:
    """Test predefined configuration constants."""

    def test_default_config(self) -> None:
        assert DEFAULT_CONFIG.chunk_size == 512
        assert DEFAULT_CONFIG.overlap == 50
        assert DEFAULT_CONFIG.encoding_name == "cl100k_base"

    def test_small_chunk_config(self) -> None:
        assert SMALL_CHUNK_CONFIG.chunk_size == 256
        assert SMALL_CHUNK_CONFIG.overlap == 25

    def test_large_chunk_config(self) -> None:
        assert LARGE_CHUNK_CONFIG.chunk_size == 1024
        assert LARGE_CHUNK_CONFIG.overlap == 100

    def test_no_overlap_config(self) -> None:
        assert NO_OVERLAP_CONFIG.chunk_size == 512
        assert NO_OVERLAP_CONFIG.overlap == 0
