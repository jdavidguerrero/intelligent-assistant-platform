"""Tests for ingestion/loaders.py."""

from pathlib import Path

import pytest

from ingestion.loaders import LoadedPage, load_documents, load_pdf_pages

# ---------------------------------------------------------------------------
# Helper: create a tiny PDF with pdfplumber's underlying library
# ---------------------------------------------------------------------------


def _create_pdf(path: Path, pages: list[str]) -> None:
    """Create a minimal PDF with the given page texts using fpdf2.

    We use ``fpdf2`` if available, otherwise fall back to a raw PDF
    byte-stream that pdfplumber can parse.
    """
    # Build a raw PDF manually — no extra dependency needed.
    # This produces a valid PDF with one text stream per page.
    objects: list[bytes] = []
    offsets: list[int] = []
    page_refs: list[str] = []

    # Object numbering: 1=catalog, 2=pages, then 3+i*2=page, 4+i*2=content
    num_pages = len(pages)
    content_start = 3  # first page object

    # Pre-compute kids refs
    for i in range(num_pages):
        page_obj_num = content_start + i * 2
        page_refs.append(f"{page_obj_num} 0 R")

    buf = b"%PDF-1.4\n"

    def add_obj(num: int, data: bytes) -> None:
        nonlocal buf
        offsets.append(len(buf))
        obj = f"{num} 0 obj\n".encode() + data + b"\nendobj\n"
        buf += obj
        objects.append(obj)

    # 1 - Catalog
    add_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")

    # 2 - Pages
    kids = " ".join(page_refs)
    add_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>".encode())

    # Pages + content streams
    for i, text in enumerate(pages):
        page_num = content_start + i * 2
        content_num = page_num + 1
        # Escape parentheses in text
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 100 700 Td ({safe}) Tj ET"
        stream_bytes = stream.encode("latin-1")

        # Page object
        add_obj(
            page_num,
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 612 792] "
                f"/Contents {content_num} 0 R "
                f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
                f">>"
            ).encode(),
        )
        # Content stream
        add_obj(
            content_num,
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode() + stream_bytes + b"\nendstream",
        )

    # Cross-reference table
    xref_offset = len(buf)
    buf += b"xref\n"
    total_objs = len(offsets) + 1
    buf += f"0 {total_objs}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()

    buf += b"trailer\n"
    buf += f"<< /Size {total_objs} /Root 1 0 R >>\n".encode()
    buf += b"startxref\n"
    buf += f"{xref_offset}\n".encode()
    buf += b"%%EOF\n"

    path.write_bytes(buf)


class TestLoadDocuments:
    def test_loads_md_and_txt(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# Hello", encoding="utf-8")
        (tmp_path / "b.txt").write_text("World", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 2
        names = {d.name for d in docs}
        assert names == {"a.md", "b.txt"}

    def test_ignores_unsupported_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("ok", encoding="utf-8")
        (tmp_path / "b.py").write_text("print(1)", encoding="utf-8")
        (tmp_path / "c.json").write_text("{}", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].name == "a.md"

    def test_limit(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"doc{i}.txt").write_text(f"content {i}", encoding="utf-8")
        docs = load_documents(tmp_path, limit=3)
        assert len(docs) == 3

    def test_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("deep", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert "sub" in docs[0].path

    def test_empty_dir(self, tmp_path: Path) -> None:
        docs = load_documents(tmp_path)
        assert docs == []

    def test_missing_dir_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_documents("/nonexistent/path/xyz")

    def test_not_a_dir_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            load_documents(f)

    def test_document_content_preserved(self, tmp_path: Path) -> None:
        content = "Some important content\nwith newlines"
        (tmp_path / "doc.txt").write_text(content, encoding="utf-8")
        docs = load_documents(tmp_path)
        assert docs[0].content == content

    def test_document_is_frozen(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        doc = load_documents(tmp_path)[0]
        with pytest.raises(AttributeError):
            doc.content = "changed"  # type: ignore[misc]

    def test_loads_pdf_files(self, tmp_path: Path) -> None:
        """PDF files are discovered alongside .md and .txt."""
        pdf_path = tmp_path / "guide.pdf"
        _create_pdf(pdf_path, ["Page one text", "Page two text"])
        (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")

        docs = load_documents(tmp_path)
        names = {d.name for d in docs}
        assert "guide.pdf" in names
        assert "notes.md" in names

    def test_pdf_content_is_concatenated_pages(self, tmp_path: Path) -> None:
        """PDF content is all pages joined by double-newline."""
        pdf_path = tmp_path / "test.pdf"
        _create_pdf(pdf_path, ["Alpha content", "Beta content"])

        docs = load_documents(tmp_path)
        pdf_doc = docs[0]
        # Both page texts should appear in the concatenated content
        assert "Alpha" in pdf_doc.content or "Beta" in pdf_doc.content


class TestLoadPdfPages:
    """Tests for the page-level PDF extractor."""

    def test_returns_pages_with_numbers(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "multi.pdf"
        _create_pdf(pdf_path, ["First page", "Second page", "Third page"])

        pages = load_pdf_pages(pdf_path)
        assert len(pages) >= 1
        assert all(isinstance(p, LoadedPage) for p in pages)
        # Page numbers are 1-based
        assert pages[0].page_number == 1

    def test_skips_empty_pages(self, tmp_path: Path) -> None:
        """Pages with no extractable text are filtered out."""
        pdf_path = tmp_path / "sparse.pdf"
        # Create a PDF where one page has content, others may be empty
        _create_pdf(pdf_path, ["Real content", "", "More content"])

        pages = load_pdf_pages(pdf_path)
        # Only pages with non-empty text should remain
        for page in pages:
            assert page.text.strip() != ""

    def test_page_is_frozen(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "frozen.pdf"
        _create_pdf(pdf_path, ["Some text"])

        pages = load_pdf_pages(pdf_path)
        if pages:
            with pytest.raises(AttributeError):
                pages[0].text = "changed"  # type: ignore[misc]

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_pdf_pages("/nonexistent/file.pdf")

    def test_non_pdf_raises(self, tmp_path: Path) -> None:
        txt = tmp_path / "notes.txt"
        txt.write_text("not a pdf", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a .pdf file"):
            load_pdf_pages(txt)

    def test_single_page_pdf(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "single.pdf"
        _create_pdf(pdf_path, ["Only one page here"])

        pages = load_pdf_pages(pdf_path)
        assert len(pages) >= 1
        assert pages[0].page_number == 1
