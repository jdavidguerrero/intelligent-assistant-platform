"""
OCR loader for scanned PDF documents using Google Cloud Vision API.

Handles PDFs that contain only images (no embedded text), where
standard pdfplumber extraction returns empty strings.

Usage::

    from ingestion.loaders_ocr import load_scanned_pdf_pages, is_scanned_pdf

    if is_scanned_pdf("path/to/book.pdf"):
        pages = load_scanned_pdf_pages("path/to/book.pdf")
    else:
        pages = load_pdf_pages("path/to/book.pdf")  # standard loader

Requirements:
    - google-cloud-vision: pip install google-cloud-vision
    - pdf2image: pip install pdf2image
    - poppler: brew install poppler  (macOS) or apt-get install poppler-utils

Authentication:
    Google Vision API requires one of:
    1. GOOGLE_APPLICATION_CREDENTIALS env var → path to service account JSON
    2. Application Default Credentials (gcloud auth application-default login)
    3. GOOGLE_API_KEY env var → API key with Vision API enabled

OCR Cache:
    Extracted text is cached in a .ocr_cache/ folder adjacent to the PDF,
    keyed by (file_path, page_number). This avoids re-calling the API on
    repeated ingestion runs (important: Vision API charges per page).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import pathlib
import time
from dataclasses import dataclass

import pdfplumber

from ingestion.loaders import load_pdf_pages

# pdf2image is an optional dependency (requires poppler).
# Import at module level so it can be patched in tests.
try:
    from pdf2image import convert_from_path  # type: ignore[import]
except ImportError:  # pragma: no cover
    convert_from_path = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pages with fewer chars than this are considered "image-only" (scanned).
_TEXT_THRESHOLD = 50

# Max pages to sample when detecting if a PDF is scanned.
_SCAN_SAMPLE_PAGES = 10

# DPI for PDF → image conversion. 300 is standard for OCR quality.
_OCR_DPI = 300

# Retry settings for transient Vision API errors.
_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 2.0

# Cache folder name (placed next to each PDF).
_CACHE_DIR_NAME = ".ocr_cache"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OcrPage:
    """A single page extracted via OCR.

    Attributes:
        page_number: 1-based page number within the PDF.
        text: OCR-extracted text from the page.
        source: Extraction method used ("google_vision" or "cache").
    """

    page_number: int
    text: str
    source: str = "google_vision"


# ---------------------------------------------------------------------------
# Scan detection
# ---------------------------------------------------------------------------


def is_scanned_pdf(file_path: str | pathlib.Path) -> bool:
    """Detect whether a PDF is image-only (scanned) or has embedded text.

    Samples the first ``_SCAN_SAMPLE_PAGES`` pages with pdfplumber.  If none
    of them yield more than ``_TEXT_THRESHOLD`` characters, the PDF is
    classified as scanned.

    Args:
        file_path: Path to the PDF file.

    Returns:
        True if the PDF appears to be image-only; False if it has text.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If *file_path* is not a .pdf file.
    """
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix!r}")

    with pdfplumber.open(path) as pdf:
        pages_to_check = min(_SCAN_SAMPLE_PAGES, len(pdf.pages))
        for i in range(pages_to_check):
            text = pdf.pages[i].extract_text() or ""
            if len(text.strip()) > _TEXT_THRESHOLD:
                return False  # Found a page with real text → not scanned

    return True  # All sampled pages had no meaningful text → scanned


# ---------------------------------------------------------------------------
# OCR cache
# ---------------------------------------------------------------------------


def _cache_dir(pdf_path: pathlib.Path) -> pathlib.Path:
    """Return the cache directory for a given PDF (sibling folder)."""
    return pdf_path.parent / _CACHE_DIR_NAME


def _cache_key(pdf_path: pathlib.Path, page_number: int) -> str:
    """Compute a stable cache key for a page.

    Uses SHA-256 of the absolute path + page number so the cache is
    invalidated if the file is moved or modified.
    """
    content = f"{pdf_path.resolve()}:{page_number}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _load_from_cache(pdf_path: pathlib.Path, page_number: int) -> str | None:
    """Load cached OCR text for a page, or None if not cached."""
    cache_file = _cache_dir(pdf_path) / f"{_cache_key(pdf_path, page_number)}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data.get("text")
    except Exception:  # noqa: BLE001
        return None


def _save_to_cache(pdf_path: pathlib.Path, page_number: int, text: str) -> None:
    """Persist OCR text for a page to the local cache."""
    cache_dir = _cache_dir(pdf_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_cache_key(pdf_path, page_number)}.json"
    data = {"page_number": page_number, "text": text, "path": str(pdf_path)}
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Google Vision OCR
# ---------------------------------------------------------------------------


def _ocr_image_bytes_vision(image_bytes: bytes) -> str:
    """Run Google Vision OCR on raw image bytes.

    Args:
        image_bytes: PNG/JPEG image bytes.

    Returns:
        Extracted text string (may be empty if no text found).

    Raises:
        ImportError: If google-cloud-vision is not installed.
        RuntimeError: If the Vision API call fails after retries.
    """
    try:
        from google.cloud import vision  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-cloud-vision is required for OCR. "
            "Install it with: pip install google-cloud-vision"
        ) from exc

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.document_text_detection(image=image)
            if response.error.message:
                raise RuntimeError(f"Vision API error: {response.error.message}")
            return response.full_text_annotation.text or ""
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "Vision API attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)

    raise RuntimeError(f"Vision API failed after {_MAX_RETRIES} attempts: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_scanned_pdf_pages(
    file_path: str | pathlib.Path,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    dpi: int = _OCR_DPI,
    use_cache: bool = True,
) -> list[OcrPage]:
    """Extract text from a scanned PDF using Google Vision OCR.

    Converts each PDF page to an image (via pdf2image/poppler), then
    sends the image to Google Cloud Vision for text extraction.  Results
    are cached locally to avoid repeated API calls.

    Args:
        file_path: Path to the scanned PDF file.
        start_page: First page to process (1-based, inclusive).
        end_page: Last page to process (1-based, inclusive).
            ``None`` means process all remaining pages.
        dpi: Resolution for PDF → image conversion.  Higher = better
            OCR quality but larger images.  Default: 300.
        use_cache: Whether to read/write the local OCR cache.

    Returns:
        List of :class:`OcrPage` objects for pages with non-empty text.
        Pages that yield no text are silently skipped.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If *file_path* is not a .pdf file.
        ImportError: If pdf2image or google-cloud-vision are not installed.
        RuntimeError: If Vision API fails after retries.
    """
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix!r}")

    if convert_from_path is None:
        raise ImportError(
            "pdf2image is required for scanned PDF loading. "
            "Install with: pip install pdf2image\n"
            "Also install poppler: brew install poppler (macOS) "
            "or apt-get install poppler-utils (Ubuntu)"
        )

    # Count total pages for range validation
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)

    end = min(end_page or total_pages, total_pages)
    start = max(1, start_page)

    logger.info(
        "OCR: processing pages %d-%d of %s (total=%d)",
        start,
        end,
        path.name,
        total_pages,
    )

    pages: list[OcrPage] = []

    # Process one page at a time to keep memory usage bounded
    for page_num in range(start, end + 1):
        # Check cache first
        if use_cache:
            cached_text = _load_from_cache(path, page_num)
            if cached_text is not None:
                logger.debug("OCR cache hit: %s page %d", path.name, page_num)
                if cached_text.strip():
                    pages.append(OcrPage(page_number=page_num, text=cached_text, source="cache"))
                continue

        # Convert single page to image
        images = convert_from_path(
            str(path),
            dpi=dpi,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            logger.warning("No image produced for page %d of %s", page_num, path.name)
            continue

        # Convert PIL image → PNG bytes for Vision API
        img_bytes_io = io.BytesIO()
        images[0].save(img_bytes_io, format="PNG")
        img_bytes = img_bytes_io.getvalue()

        # OCR via Google Vision
        text = _ocr_image_bytes_vision(img_bytes)

        # Cache the result (even if empty, to avoid re-calling)
        if use_cache:
            _save_to_cache(path, page_num, text)

        if text.strip():
            pages.append(OcrPage(page_number=page_num, text=text, source="google_vision"))

        logger.info("OCR: page %d/%d done (%d chars)", page_num, end, len(text))

    logger.info(
        "OCR complete: %d/%d pages with text from %s",
        len(pages),
        end - start + 1,
        path.name,
    )
    return pages


def ocr_pages_to_loaded_pages(pages: list[OcrPage]) -> list:
    """Convert OcrPage objects to LoadedPage format for pipeline compatibility.

    Converts ``OcrPage`` (from OCR loader) to ``LoadedPage`` (from standard
    loader) so the existing ingestion pipeline can process them without
    modification.

    Args:
        pages: List of OCR-extracted pages.

    Returns:
        List of ``LoadedPage`` objects compatible with the ingestion pipeline.
    """
    from ingestion.loaders import LoadedPage

    return [LoadedPage(page_number=p.page_number, text=p.text) for p in pages]


def load_pdf_auto(
    file_path: str | pathlib.Path,
    *,
    use_cache: bool = True,
) -> list:
    """Auto-detect PDF type and load with the appropriate strategy.

    Tries pdfplumber first (free, fast).  Falls back to Google Vision OCR
    if the PDF is image-only (scanned).

    Args:
        file_path: Path to the PDF file.
        use_cache: Passed through to OCR loader if OCR is needed.

    Returns:
        List of ``LoadedPage`` objects (compatible with ingestion pipeline).

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If *file_path* is not a .pdf file.
    """
    path = pathlib.Path(file_path)

    if is_scanned_pdf(path):
        logger.info("%s is a scanned PDF — using Google Vision OCR", path.name)
        ocr_pages = load_scanned_pdf_pages(path, use_cache=use_cache)
        return ocr_pages_to_loaded_pages(ocr_pages)
    else:
        logger.info("%s has embedded text — using pdfplumber", path.name)
        return load_pdf_pages(path)


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _cli_ingest_scanned(
    pdf_path: str,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    dry_run: bool = False,
) -> None:
    """CLI entry point for OCR ingestion of a single scanned PDF.

    Usage::

        python -m ingestion.loaders_ocr path/to/scanned.pdf
        python -m ingestion.loaders_ocr path/to/scanned.pdf --start 1 --end 50
        python -m ingestion.loaders_ocr path/to/scanned.pdf --dry-run

    Args:
        pdf_path: Path to the scanned PDF.
        start_page: First page to OCR (1-based).
        end_page: Last page to OCR (1-based). None = all.
        dry_run: If True, only detect scan type and page count, no OCR.
    """
    path = pathlib.Path(pdf_path)
    print(f"PDF: {path.name}")

    scanned = is_scanned_pdf(path)
    print(f"Scanned (image-only): {scanned}")

    if dry_run:
        with pdfplumber.open(path) as pdf:
            print(f"Total pages: {len(pdf.pages)}")
        print("Dry run — no OCR performed.")
        return

    if not scanned:
        print("This PDF has embedded text. Use the standard ingestion pipeline.")
        print("Command: python -m ingestion.ingest --data-dir <dir>")
        return

    pages = load_scanned_pdf_pages(path, start_page=start_page, end_page=end_page)
    print(f"\nOCR complete: {len(pages)} pages with text")
    if pages:
        print(f"\nSample (page {pages[0].page_number}):")
        print(pages[0].text[:300])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="OCR loader for scanned PDFs using Google Vision API."
    )
    parser.add_argument("pdf_path", help="Path to the scanned PDF file.")
    parser.add_argument("--start", type=int, default=1, help="First page (1-based).")
    parser.add_argument("--end", type=int, default=None, help="Last page (1-based).")
    parser.add_argument("--dry-run", action="store_true", help="Detect only, no OCR.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _cli_ingest_scanned(
        args.pdf_path,
        start_page=args.start,
        end_page=args.end,
        dry_run=args.dry_run,
    )
