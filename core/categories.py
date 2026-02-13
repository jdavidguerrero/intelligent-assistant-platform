"""Category extraction for evaluation."""


def extract_category(source_path: str) -> str:
    """
    Extract category from source_path for evaluation.

    Args:
        source_path: Full path to source document.

    Returns:
        Category string extracted from path. Returns "unknown" if no category found.

    Examples:
        >>> extract_category("data/music/courses/pete-tong-producer-academy/the-kick/01.md")
        "the-kick"
        >>> extract_category("data/music/youtube/tutorials/video.md")
        "youtube-tutorials"
        >>> extract_category("data/other/file.md")
        "unknown"
    """
    if not source_path:
        return "unknown"

    parts = source_path.split("/")

    # Pattern: data/music/courses/.../CATEGORY/...
    if "courses" in parts:
        try:
            idx = parts.index("courses")
            if idx + 2 < len(parts):  # has .../courses/SCHOOL/CATEGORY/...
                return parts[idx + 2]
        except (ValueError, IndexError):
            pass

    # Pattern: data/music/youtube/tutorials/...
    if "youtube" in parts and "tutorials" in parts:
        return "youtube-tutorials"

    return "unknown"
