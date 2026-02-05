"""
Tests for core.text module.

These tests verify the pure text extraction and normalization functions.
"""

import pytest

from core.text import (
    normalize_whitespace,
    strip_markdown_frontmatter,
    strip_markdown_code_blocks,
    strip_markdown_links,
    strip_markdown_formatting,
    extract_markdown_text,
    extract_plaintext,
)


class TestNormalizeWhitespace:
    """Test whitespace normalization."""

    def test_empty_string(self) -> None:
        assert normalize_whitespace("") == ""

    def test_collapses_multiple_spaces(self) -> None:
        assert normalize_whitespace("hello    world") == "hello world"

    def test_collapses_tabs(self) -> None:
        assert normalize_whitespace("hello\t\tworld") == "hello world"

    def test_preserves_paragraph_breaks(self) -> None:
        result = normalize_whitespace("para1\n\npara2")
        assert result == "para1\n\npara2"

    def test_collapses_excessive_newlines(self) -> None:
        result = normalize_whitespace("para1\n\n\n\n\npara2")
        assert result == "para1\n\npara2"

    def test_normalizes_crlf(self) -> None:
        result = normalize_whitespace("line1\r\nline2")
        assert result == "line1\nline2"

    def test_strips_leading_trailing(self) -> None:
        result = normalize_whitespace("  hello  ")
        assert result == "hello"


class TestStripMarkdownFrontmatter:
    """Test frontmatter removal."""

    def test_no_frontmatter(self) -> None:
        text = "# Hello\n\nContent"
        assert strip_markdown_frontmatter(text) == text

    def test_removes_yaml_frontmatter(self) -> None:
        text = "---\ntitle: Test\nauthor: Me\n---\n# Content"
        result = strip_markdown_frontmatter(text)
        assert result == "# Content"

    def test_preserves_content_after_frontmatter(self) -> None:
        text = "---\nkey: value\n---\n\nParagraph one.\n\nParagraph two."
        result = strip_markdown_frontmatter(text)
        assert "Paragraph one" in result
        assert "Paragraph two" in result


class TestStripMarkdownCodeBlocks:
    """Test code block removal."""

    def test_removes_fenced_code_block(self) -> None:
        text = "Before\n```python\ncode here\n```\nAfter"
        result = strip_markdown_code_blocks(text)
        assert "code here" not in result
        assert "Before" in result
        assert "After" in result

    def test_removes_tilde_code_block(self) -> None:
        text = "Before\n~~~\ncode\n~~~\nAfter"
        result = strip_markdown_code_blocks(text)
        assert "code" not in result

    def test_handles_multiple_code_blocks(self) -> None:
        text = "A\n```\ncode1\n```\nB\n```\ncode2\n```\nC"
        result = strip_markdown_code_blocks(text)
        assert "code1" not in result
        assert "code2" not in result
        assert "A" in result
        assert "B" in result
        assert "C" in result


class TestStripMarkdownLinks:
    """Test link removal."""

    def test_converts_link_to_text(self) -> None:
        text = "See [documentation](http://example.com) here"
        result = strip_markdown_links(text)
        assert result == "See documentation here"

    def test_converts_image_to_alt(self) -> None:
        text = "![alt text](image.png)"
        result = strip_markdown_links(text)
        assert result == "alt text"

    def test_handles_reference_links(self) -> None:
        text = "See [docs][ref] for more"
        result = strip_markdown_links(text)
        assert result == "See docs for more"


class TestStripMarkdownFormatting:
    """Test inline formatting removal."""

    def test_removes_bold_asterisks(self) -> None:
        assert strip_markdown_formatting("**bold**") == "bold"

    def test_removes_bold_underscores(self) -> None:
        assert strip_markdown_formatting("__bold__") == "bold"

    def test_removes_italic_asterisks(self) -> None:
        assert strip_markdown_formatting("*italic*") == "italic"

    def test_removes_strikethrough(self) -> None:
        assert strip_markdown_formatting("~~deleted~~") == "deleted"

    def test_removes_inline_code(self) -> None:
        assert strip_markdown_formatting("`code`") == "code"

    def test_handles_mixed_formatting(self) -> None:
        text = "This is **bold** and *italic* with `code`"
        result = strip_markdown_formatting(text)
        assert result == "This is bold and italic with code"


class TestExtractMarkdownText:
    """Test full markdown extraction pipeline."""

    def test_full_extraction(self) -> None:
        md = """---
title: Test Doc
---

# Header

This is **bold** text with a [link](http://example.com).

```python
def hello():
    pass
```

Final paragraph.
"""
        result = extract_markdown_text(md)

        # Should remove frontmatter
        assert "title:" not in result
        # Should remove code block
        assert "def hello" not in result
        # Should keep header
        assert "# Header" in result
        # Should convert link
        assert "link" in result
        assert "http://" not in result
        # Should remove bold markers
        assert "**" not in result
        # Should keep final paragraph
        assert "Final paragraph" in result


class TestExtractPlaintext:
    """Test plaintext extraction."""

    def test_normalizes_whitespace(self) -> None:
        text = "Hello    world\n\n\n\nNew paragraph"
        result = extract_plaintext(text)
        assert result == "Hello world\n\nNew paragraph"
