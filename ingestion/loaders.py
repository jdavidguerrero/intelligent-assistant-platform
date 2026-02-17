"""
File loaders for the ingestion pipeline.

Recursively discovers and reads ``.md``, ``.txt``, and ``.pdf`` files
from a directory.
"""

from dataclasses import dataclass
from pathlib import Path

import pdfplumber

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt", ".pdf"})


@dataclass(frozen=True)
class LoadedDocument:
    """A document loaded from disk."""

    path: str
    name: str
    content: str


@dataclass(frozen=True)
class LoadedPage:
    """A single page extracted from a PDF file.

    Attributes:
        page_number: 1-based page number within the PDF.
        text: Raw text extracted from the page by pdfplumber.
    """

    page_number: int
    text: str


def load_pdf_pages(file_path: str | Path) -> list[LoadedPage]:
    """
    Extract text from each page of a PDF using pdfplumber.

    Args:
        file_path: Path to the PDF file.

    Returns:
        List of ``LoadedPage`` objects, one per page with non-empty text.
        Pages that yield no text (e.g. scanned images without OCR) are
        skipped.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If *file_path* is not a ``.pdf`` file.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix!r}")

    pages: list[LoadedPage] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(LoadedPage(page_number=i, text=text))
    return pages


def load_documents(
    data_dir: str | Path,
    *,
    limit: int | None = None,
) -> list[LoadedDocument]:
    """
    Recursively load ``.md``, ``.txt``, and ``.pdf`` files from *data_dir*.

    For PDF files, all pages are concatenated into a single ``content``
    string (page-aware chunking is handled downstream in the pipeline).

    Args:
        data_dir: Root directory to scan.
        limit: Maximum number of files to return.  ``None`` means no limit.

    Returns:
        List of ``LoadedDocument`` objects sorted by path.

    Raises:
        FileNotFoundError: If *data_dir* does not exist.
        ValueError: If *data_dir* is not a directory.
    """
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Data directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {root}")

    documents: list[LoadedDocument] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if not path.is_file():
            continue

        if path.suffix.lower() == ".pdf":
            pages = load_pdf_pages(path)
            content = "\n\n".join(p.text for p in pages)
        else:
            content = path.read_text(encoding="utf-8")

        documents.append(
            LoadedDocument(
                path=str(path),
                name=path.name,
                content=content,
            )
        )
        if limit is not None and len(documents) >= limit:
            break

    return documents
