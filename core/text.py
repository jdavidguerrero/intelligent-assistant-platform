"""
Pure text extraction and normalization utilities.

This module provides string-to-string transformation functions with no side effects.
The ingestion/ layer handles I/O (reading files), then delegates text processing here.

All functions are pure: same input always produces same output, no external state.
"""

import re


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in text while preserving paragraph structure.

    - Collapses multiple spaces/tabs into single space
    - Normalizes line endings to \\n
    - Collapses 3+ consecutive newlines into 2 (preserves paragraph breaks)
    - Strips leading/trailing whitespace

    Args:
        text: Input text with potentially messy whitespace.

    Returns:
        Text with normalized whitespace.

    Example:
        >>> normalize_whitespace("Hello   world\\n\\n\\n\\nNew paragraph")
        'Hello world\\n\\nNew paragraph'
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse horizontal whitespace (spaces, tabs) into single space
    text = re.sub(r"[^\S\n]+", " ", text)

    # Collapse 3+ newlines into 2 (preserve paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Strip overall leading/trailing whitespace
    return text.strip()


def strip_markdown_frontmatter(text: str) -> str:
    """
    Remove YAML frontmatter from markdown content.

    Frontmatter is delimited by --- at the start of the document.

    Args:
        text: Markdown text potentially containing frontmatter.

    Returns:
        Text with frontmatter removed.

    Example:
        >>> strip_markdown_frontmatter("---\\ntitle: Hello\\n---\\n# Content")
        '# Content'
    """
    if not text.startswith("---"):
        return text

    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", text[3:])
    if end_match:
        # Skip past the frontmatter
        return text[3 + end_match.end() :].lstrip("\n")

    return text


def strip_markdown_code_blocks(text: str) -> str:
    """
    Remove fenced code blocks from markdown content.

    Removes blocks delimited by ``` or ~~~, preserving surrounding text.
    Useful when you want to chunk prose without code examples.

    Args:
        text: Markdown text with code blocks.

    Returns:
        Text with code blocks removed (replaced with single newline).

    Example:
        >>> strip_markdown_code_blocks("Before\\n```python\\ncode\\n```\\nAfter")
        'Before\\n\\nAfter'
    """
    # Match fenced code blocks (``` or ~~~)
    pattern = r"(```|~~~)[^\n]*\n.*?\1"
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def strip_markdown_links(text: str) -> str:
    """
    Convert markdown links to plain text, keeping link text.

    Converts [text](url) to just text, and ![alt](url) to alt.

    Args:
        text: Markdown text with links.

    Returns:
        Text with link syntax removed, link text preserved.

    Example:
        >>> strip_markdown_links("See [docs](http://example.com) for info")
        'See docs for info'
    """
    # Image links: ![alt](url) -> alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Regular links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Reference links: [text][ref] -> text
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)

    return text


def strip_markdown_formatting(text: str) -> str:
    """
    Remove common markdown inline formatting.

    Strips bold, italic, strikethrough, and inline code markers.

    Args:
        text: Markdown text with formatting.

    Returns:
        Plain text without markdown formatting.

    Example:
        >>> strip_markdown_formatting("This is **bold** and *italic*")
        'This is bold and italic'
    """
    # Bold: **text** or __text__
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)

    # Italic: *text* or _text_ (be careful not to match within words)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # Strikethrough: ~~text~~
    text = re.sub(r"~~([^~]+)~~", r"\1", text)

    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", r"\1", text)

    return text


def extract_markdown_text(content: str) -> str:
    """
    Extract plain text from markdown content.

    Removes frontmatter, code blocks, links, and formatting to produce
    clean prose suitable for chunking and embedding.

    Args:
        content: Raw markdown content.

    Returns:
        Normalized plain text.

    Example:
        >>> md = "---\\ntitle: Doc\\n---\\n# Hello\\n\\nThis is **bold**."
        >>> extract_markdown_text(md)
        '# Hello\\n\\nThis is bold.'
    """
    text = strip_markdown_frontmatter(content)
    text = strip_markdown_code_blocks(text)
    text = strip_markdown_links(text)
    text = strip_markdown_formatting(text)
    text = normalize_whitespace(text)
    return text


def extract_plaintext(content: str) -> str:
    """
    Normalize plain text content.

    For .txt files that don't need markdown processing,
    just normalize whitespace.

    Args:
        content: Raw text content.

    Returns:
        Normalized text.
    """
    return normalize_whitespace(content)
