"""Tests for category extraction function."""

from core.categories import extract_category


class TestExtractCategory:
    """Tests for extract_category() function."""

    def test_course_category_extraction(self) -> None:
        """Extract category from course path."""
        path = "data/music/courses/pete-tong-producer-academy/the-kick/01-intro.md"
        assert extract_category(path) == "the-kick"

    def test_different_course_category(self) -> None:
        """Extract different category."""
        path = "data/music/courses/pete-tong-producer-academy/drums/05-processing.md"
        assert extract_category(path) == "drums"

    def test_youtube_tutorials(self) -> None:
        """YouTube tutorials map to 'youtube-tutorials'."""
        path = "data/music/youtube/tutorials/video-123.md"
        assert extract_category(path) == "youtube-tutorials"

    def test_unknown_structure(self) -> None:
        """Unknown structure returns 'unknown'."""
        path = "data/other/random/file.md"
        assert extract_category(path) == "unknown"

    def test_root_path(self) -> None:
        """Root path returns 'unknown'."""
        assert extract_category("data/music/file.md") == "unknown"

    def test_empty_path(self) -> None:
        """Empty path returns 'unknown'."""
        assert extract_category("") == "unknown"
